"""
pipeline/qa_graph.py
────────────────────
LangGraph pipeline for Q&A over an existing feasibility conversation.
This flow reuses the shared AgentState shape used by /chat and adds QA traceability.

Memory:
  - Keeps the last QA window size turns verbatim in every prompt.
  - When total stored turns exceed the summarize threshold, the oldest
    turns are compressed into a rolling LLM summary so context stays bounded.
"""

from datetime import datetime, timezone
from typing import Any
from langgraph.graph import StateGraph, START, END

from core.config import settings
from core.logging import get_logger, log_event
from pipeline.state import AgentState
from pipeline.prompts.qa import get_qa_prompt
from rag.retriever import conversation_chunk_count, retrieve_context
from core.llm_factory import get_llm
from core.observability import ls_traceable


# ── Memory constants ───────────────────────────────────────────────────────────
QA_WINDOW_SIZE = max(1, settings.QA_WINDOW_SIZE)
QA_SUMMARIZE_THRESHOLD = max(settings.QA_SUMMARIZE_THRESHOLD, QA_WINDOW_SIZE + 1)
logger = get_logger(__name__)


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


def _extract_llm_content(response: Any) -> str:
    if isinstance(response, str):
        return response
    return getattr(response, "content", "") or ""


def _is_low_signal_qa_question(question: str) -> bool:
    normalized = (question or "").strip().lower()
    if not normalized:
        return True
    if len(normalized) < 10:
        return True

    tokens = [token for token in normalized.replace("?", " ").split() if token]
    if len(tokens) < 3:
        return True

    low_signal_questions = {
        "ok", "okay", "why", "how", "what", "tell me", "more", "anything else",
        "hmm", "test", "testing",
    }
    return normalized in low_signal_questions


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


def qa_filter_node(state: AgentState) -> dict:
    print("--- QA NODE: qa_filter_node ---")
    question = (state.get("question") or "").strip()
    if _is_low_signal_qa_question(question):
        message = (
            "Please ask a more specific follow-up question so I can run retrieval usefully. "
            "For example, ask about competitors, pricing, demand signals, or target users."
        )
        trace = _append_trace(
            state,
            "qa_filter",
            "Blocked vague QA question before retrieval.",
            {"question": question, "blocked": True},
        )
        return {
            "input_valid": False,
            "validation_message": message,
            "qa_answer": message,
            "top_chunks": [],
            "rag_context": "",
            "trace": trace,
        }

    trace = _append_trace(
        state,
        "qa_filter",
        "QA question passed validation.",
        {"question": question, "blocked": False},
    )
    return {"input_valid": True, "trace": trace}


def route_qa_filter(state: AgentState) -> str:
    if not state.get("input_valid", True):
        print("--- QA ROUTER: Routing to qa_invalid_response_node ---")
        return "qa_invalid_response"
    print("--- QA ROUTER: Routing to qa_memory_node ---")
    return "qa_memory"


def qa_invalid_response_node(state: AgentState) -> dict:
    print("--- QA NODE: qa_invalid_response_node ---")
    return {
        "qa_answer": state.get("validation_message")
        or "Please ask a more specific question.",
        "top_chunks": [],
    }


@ls_traceable(run_type="tool", name="qa_memory_node", tags=["qa", "node"])
def qa_memory_node(state: AgentState, llm) -> dict:
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
        new_summary = _extract_llm_content(llm.invoke(summary_prompt)).strip()
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


@ls_traceable(run_type="tool", name="qa_modify_query_node", tags=["qa", "node"])
def qa_modify_query_node(state: AgentState, llm) -> dict:
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
        rewritten = _extract_llm_content(llm.invoke(rewrite_prompt)).strip().strip('"')
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


@ls_traceable(run_type="retriever", name="qa_retrieve_context_node", tags=["qa", "retrieval"])
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
        context, chunks = retrieve_context(
            conversation_id=conv_id,
            query=retrieval_query,
            top_k=settings.QA_TOP_K,
        )
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
        log_event(
            logger,
            "qa_rag_fallback_used",
            conversation_id=conv_id,
            question=question,
            retrieval_query=retrieval_query,
            persisted_chunk_count=chunk_count,
            fallback_has_analysis=bool(state.get("analysis")),
            fallback_has_search_results=bool(state.get("search_results")),
        )

    trace = _append_trace(
        state,
        "qa_retrieve_context",
        "Retrieved RAG context for the user question.",
        {
            "question": question,
            "retrieval_query": retrieval_query,
            "persisted_chunk_count": chunk_count,
            "requested_top_k": settings.QA_TOP_K,
            "top_chunks": len(chunks),
            "used_fallback": len(chunks) == 0,
        },
    )
    return {"rag_context": context, "top_chunks": chunks, "trace": trace}


@ls_traceable(run_type="tool", name="qa_generate_answer_node", tags=["qa", "node"])
def qa_generate_answer_node(state: AgentState, llm) -> dict:
    print("--- QA NODE: qa_generate_answer_node ---")

    question   = state.get("question", "")
    idea       = state.get("idea", "your startup idea")
    context    = state.get("rag_context", "No relevant context found.")
    qa_history = state.get("qa_history", [])   # already windowed by qa_memory_node
    qa_summary = state.get("qa_summary", "")

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
            "model_response_chars": len(_extract_llm_content(response)),
            "memory_window_turns": len(qa_history),
            "has_summary": bool(qa_summary),
        },
    )
    return {"qa_answer": _extract_llm_content(response), "trace": trace}


# ── Graph wiring ───────────────────────────────────────────────────────────────
def build_qa_graph(*, memory_llm=None, rewrite_llm=None, answer_llm=None):
    qa_workflow = StateGraph(AgentState)

    memory_llm = memory_llm or get_llm(temperature=0.2)
    rewrite_llm = rewrite_llm or get_llm(temperature=0.2)
    answer_llm = answer_llm or get_llm()

    qa_workflow.add_node("qa_load_state", qa_load_state_node)
    qa_workflow.add_node("qa_filter", qa_filter_node)
    qa_workflow.add_node("qa_invalid_response", qa_invalid_response_node)
    qa_workflow.add_node("qa_memory", lambda state: qa_memory_node(state, memory_llm))
    qa_workflow.add_node("qa_modify_query", lambda state: qa_modify_query_node(state, rewrite_llm))
    qa_workflow.add_node("qa_retrieve_context", qa_retrieve_context_node)
    qa_workflow.add_node("qa_generate_answer", lambda state: qa_generate_answer_node(state, answer_llm))

    qa_workflow.add_edge(START, "qa_load_state")
    qa_workflow.add_edge("qa_load_state", "qa_filter")
    qa_workflow.add_conditional_edges(
        "qa_filter",
        route_qa_filter,
        {
            "qa_invalid_response": "qa_invalid_response",
            "qa_memory": "qa_memory",
        },
    )
    qa_workflow.add_edge("qa_memory", "qa_modify_query")
    qa_workflow.add_edge("qa_modify_query", "qa_retrieve_context")
    qa_workflow.add_edge("qa_retrieve_context", "qa_generate_answer")
    qa_workflow.add_edge("qa_invalid_response", END)
    qa_workflow.add_edge("qa_generate_answer", END)

    return qa_workflow.compile()


qa_app = build_qa_graph()


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
