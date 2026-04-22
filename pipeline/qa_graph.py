"""
pipeline/qa_graph.py
────────────────────
LangGraph pipeline for Q&A over an existing feasibility conversation.
This flow reuses the shared AgentState shape used by /chat and adds QA traceability.

Memory:
  - Keeps the last QA_WINDOW_SIZE (7) turns verbatim in every prompt.
  - When total stored turns exceed QA_SUMMARIZE_THRESHOLD (14), the oldest
    turns are compressed into a rolling LLM summary so context stays bounded.
"""

from datetime import datetime, timezone
from langgraph.graph import StateGraph, START, END

from pipeline.state import AgentState
from pipeline.prompts.qa import get_qa_prompt
from rag.retriever import conversation_chunk_count, retrieve_context
from core.llm_factory import get_llm


# ── Memory constants ───────────────────────────────────────────────────────────
QA_WINDOW_SIZE = 7          # recent turns kept verbatim in context
QA_SUMMARIZE_THRESHOLD = 14 # compress when total history exceeds this


# ── Helpers ────────────────────────────────────────────────────────────────────
def _append_trace(state: AgentState, step: str, message: str, metadata: dict | None = None) -> list[dict]:
    trace = list(state.get("trace", []))
    trace.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "message": message,
            "metadata": metadata or {},
        }
    )
    return trace


# ── Nodes ──────────────────────────────────────────────────────────────────────
def qa_load_state_node(state: AgentState) -> dict:
    print("--- QA NODE: qa_load_state_node ---")
    trace = _append_trace(
        state,
        "qa_load_state",
        "Loaded persisted conversation state and history for QA.",
        {
            "conversation_id": state.get("conversation_id"),
            "history_turns": len(state.get("conversation_history", [])),
            "qa_turns": len(state.get("qa_history", [])),
            "has_analysis": bool(state.get("analysis")),
            "has_search_results": bool(state.get("search_results")),
        },
    )
    return {"trace": trace}


def qa_memory_node(state: AgentState) -> dict:
    """
    Sliding-window memory manager for the QA chat.

    Behaviour:
    - total turns <= QA_SUMMARIZE_THRESHOLD:
        Trim to last QA_WINDOW_SIZE for context. No LLM call.
    - total turns >  QA_SUMMARIZE_THRESHOLD:
        Compress everything outside the window into a rolling LLM summary.
        The window + updated summary are written back to state so routes.py
        can persist them and the answer node can inject them into the prompt.
    """
    print("--- QA NODE: qa_memory_node ---")

    qa_history: list[dict] = list(state.get("qa_history") or [])
    qa_summary: str = state.get("qa_summary") or ""
    total = len(qa_history)
    print(f"  [Memory] Total QA turns in history: {total}")

    if total <= QA_SUMMARIZE_THRESHOLD:
        active_window = qa_history[-QA_WINDOW_SIZE:] if total > QA_WINDOW_SIZE else qa_history
        trace = _append_trace(
            state,
            "qa_memory",
            f"Window OK ({total} turns <= threshold {QA_SUMMARIZE_THRESHOLD}). "
            f"Using last {len(active_window)} turns as context.",
            {"total_turns": total, "window_size": len(active_window), "summarized": False},
        )
        return {"qa_history": active_window, "qa_summary": qa_summary, "trace": trace}

    # ── Compression path ───────────────────────────────────────────────────────
    to_compress = qa_history[:-QA_WINDOW_SIZE]
    active_window = qa_history[-QA_WINDOW_SIZE:]
    print(f"  [Memory] Compressing {len(to_compress)} old turn(s) into rolling summary...")

    llm = get_llm(temperature=0.2)
    old_turns_str = "\n".join(
        [f"Q: {t.get('q', '')}\nA: {t.get('a', '')}" for t in to_compress]
    )
    summary_prompt = (
        "You are a memory manager for a startup Q&A assistant.\n"
        "Compress the following old Q&A turns into a concise but complete summary.\n"
        "If there is an existing summary, integrate the new turns into it.\n"
        "Preserve key facts, numbers, competitor names, and decisions mentioned.\n\n"
        + (f"=== EXISTING SUMMARY ===\n{qa_summary}\n========================\n\n" if qa_summary else "")
        + f"=== OLD Q&A TURNS TO COMPRESS ===\n{old_turns_str}\n==================================\n\n"
        "Return ONLY the updated summary text, no extra commentary."
    )

    try:
        new_summary = (llm.invoke(summary_prompt).content or "").strip()
        print(f"  [Memory] Summary generated ({len(new_summary)} chars).")
    except Exception as e:
        print(f"  [Memory] Warning: Summarization failed: {e}. Keeping old summary.")
        new_summary = qa_summary

    trace = _append_trace(
        state,
        "qa_memory",
        f"Compressed {len(to_compress)} old turn(s) into rolling summary. "
        f"Window now holds {len(active_window)} recent turn(s).",
        {
            "total_turns_before": total,
            "compressed_turns": len(to_compress),
            "window_size": len(active_window),
            "summarized": True,
            "summary_chars": len(new_summary),
        },
    )
    return {"qa_history": active_window, "qa_summary": new_summary, "trace": trace}


def qa_modify_query_node(state: AgentState) -> dict:
    print("--- QA NODE: qa_modify_query_node ---")
    original_question = state.get("question", "").strip()
    idea = state.get("idea", "")
    problem_solved = state.get("problem_solved", "")

    if not original_question:
        trace = _append_trace(state, "qa_modify_query", "Skipped — question was empty.")
        return {"qa_retrieval_query": "", "trace": trace}

    history = state.get("conversation_history", [])[-4:]
    history_str = "\n".join(
        [f"User: {h.get('user', '')}\nAI: {h.get('ai', '')}" for h in history]
    )

    llm = get_llm(temperature=0.2)
    rewrite_prompt = (
        "You rewrite follow-up startup questions into standalone retrieval queries.\n"
        "Use startup context to disambiguate pronouns/short phrases.\n"
        "Do not invent facts. Keep it concise and explicit.\n"
        "Return ONLY the rewritten query text, no markdown.\n\n"
        f"Startup idea: {idea}\n"
        f"Problem solved: {problem_solved}\n"
        f"Recent conversation:\n{history_str}\n\n"
        f"User follow-up question: {original_question}\n\n"
        "Example:\n"
        "Input: will it work in india\n"
        "Output: will the smart mirror startup work in india\n"
    )

    try:
        rewritten = (llm.invoke(rewrite_prompt).content or "").strip().strip('"')
    except Exception:
        rewritten = ""

    if not rewritten:
        rewritten = f"For the startup idea '{idea}', {original_question}".strip()

    trace = _append_trace(
        state,
        "qa_modify_query",
        "Rewrote user question into standalone retrieval query.",
        {"original_question": original_question, "rewritten_query": rewritten},
    )
    return {"qa_retrieval_query": rewritten, "trace": trace}


def qa_retrieve_context_node(state: AgentState) -> dict:
    print("--- QA NODE: qa_retrieve_context_node ---")
    question = state.get("question", "").strip()
    retrieval_query = state.get("qa_retrieval_query", "").strip() or question
    conv_id = state.get("conversation_id", "")

    print(f"  [QA] Original question: {question}")
    print(f"  [QA] Retrieval query : {retrieval_query}")
    print(f"  [QA] Searching Qdrant for conv_id: {conv_id}")

    chunk_count = conversation_chunk_count(conv_id)
    print(f"  [QA] Persisted chunk count for conv_id {conv_id}: {chunk_count}")

    if chunk_count > 0:
        context, chunks = retrieve_context(conversation_id=conv_id, query=retrieval_query, top_k=5)
    else:
        context, chunks = "No relevant context found.", []
        print("  [QA] No persisted chunks found for this conversation before retrieval.")

    if not chunks:
        fallback_context = (
            f"[Persisted analysis]\n{state.get('analysis', '')}\n\n"
            f"[Persisted web research]\n{state.get('search_results', '')}"
        ).strip()
        context = fallback_context or "No relevant context found."
        print("  [QA] No vector chunks found, using persisted fallback context.")

    trace = _append_trace(
        state,
        "qa_retrieve_context",
        "Retrieved RAG context for the user question.",
        {
            "question": question,
            "retrieval_query": retrieval_query,
            "persisted_chunk_count": chunk_count,
            "top_chunks": len(chunks),
            "used_fallback": len(chunks) == 0,
        },
    )
    return {"rag_context": context, "top_chunks": chunks, "trace": trace}


def qa_generate_answer_node(state: AgentState) -> dict:
    print("--- QA NODE: qa_generate_answer_node ---")

    question   = state.get("question", "")
    idea       = state.get("idea", "your startup idea")
    context    = state.get("rag_context", "No relevant context found.")
    qa_history = state.get("qa_history", [])   # already windowed by qa_memory_node
    qa_summary = state.get("qa_summary", "")

    llm = get_llm()
    prompt = get_qa_prompt(
        idea=idea,
        context=context,
        query=question,
        qa_history=qa_history,
        qa_summary=qa_summary,
    )
    response = llm.invoke(prompt)

    trace = _append_trace(
        state,
        "qa_generate_answer",
        "Generated final QA response with LLM.",
        {
            "model_response_chars": len(response.content or ""),
            "memory_window_turns": len(qa_history),
            "has_summary": bool(qa_summary),
        },
    )
    return {"qa_answer": response.content, "trace": trace}


# ── Graph wiring ───────────────────────────────────────────────────────────────
qa_workflow = StateGraph(AgentState)
qa_workflow.add_node("qa_load_state",      qa_load_state_node)
qa_workflow.add_node("qa_memory",          qa_memory_node)        # sliding-window + summarize
qa_workflow.add_node("qa_modify_query",    qa_modify_query_node)
qa_workflow.add_node("qa_retrieve_context", qa_retrieve_context_node)
qa_workflow.add_node("qa_generate_answer", qa_generate_answer_node)

qa_workflow.add_edge(START,                  "qa_load_state")
qa_workflow.add_edge("qa_load_state",        "qa_memory")
qa_workflow.add_edge("qa_memory",            "qa_modify_query")
qa_workflow.add_edge("qa_modify_query",      "qa_retrieve_context")
qa_workflow.add_edge("qa_retrieve_context",  "qa_generate_answer")
qa_workflow.add_edge("qa_generate_answer",   END)

qa_app = qa_workflow.compile()


def get_qa_graph_mermaid() -> str:
    """Returns a Mermaid diagram for QA graph visualization."""
    try:
        return qa_app.get_graph().draw_mermaid()
    except Exception:
        return (
            "graph TD\n"
            "    START --> qa_load_state\n"
            "    qa_load_state --> qa_memory\n"
            "    qa_memory --> qa_modify_query\n"
            "    qa_modify_query --> qa_retrieve_context\n"
            "    qa_retrieve_context --> qa_generate_answer\n"
            "    qa_generate_answer --> END"
        )
