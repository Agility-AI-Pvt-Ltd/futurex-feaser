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
import json
from typing import Any
from langgraph.graph import StateGraph, START, END

from core.config import settings
from core.logging import get_logger
from core.json_utils import parse_json_from_text
from pipeline.state import AgentState
from pipeline.prompts.qa import get_qa_prompt
from pipeline.tools import FeasibilityReportSchema
from pipeline.feasibility_parser import parse_feasibility_report
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
            "Please ask a more specific follow-up question so I can answer from the idea-lab report. "
            "For example, ask about competitors, pricing, demand signals, or target users."
        )
        trace = _append_trace(
            state,
            "qa_filter",
            "Blocked vague QA question before report-grounded answering.",
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
        trace = _append_trace(state, "qa_modify_query", "Skipped - question was empty.")
        return {"qa_retrieval_query": "", "trace": trace}

    history = state.get("conversation_history", [])[-4:]
    history_str = "\n".join(
        [f"User: {h.get('user', '')}\nAI: {h.get('ai', '')}" for h in history]
    )

    rewrite_prompt = (
        "You rewrite follow-up startup questions into standalone report-grounded questions.\n"
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
        "Rewrote user question into standalone report-grounded question.",
        {"original_question": original_question, "rewritten_query": rewritten},
    )
    return {"qa_retrieval_query": rewritten, "trace": trace}


@ls_traceable(run_type="tool", name="qa_use_report_context_node", tags=["qa", "node"])
def qa_use_report_context_node(state: AgentState) -> dict:
    print("--- QA NODE: qa_use_report_context_node ---")
    question = state.get("question", "").strip()
    retrieval_query = state.get("qa_retrieval_query", "").strip() or question
    context = (state.get("analysis") or "").strip() or "No idea-lab report found."

    trace = _append_trace(
        state,
        "qa_use_report_context",
        "Loaded idea-lab report as QA context.",
        {
            "question": question,
            "retrieval_query": retrieval_query,
            "context_chars": len(context),
        },
    )
    return {"rag_context": context, "top_chunks": [], "trace": trace}


@ls_traceable(run_type="tool", name="qa_generate_answer_node", tags=["qa", "node"])
def qa_generate_answer_node(state: AgentState, llm) -> dict:
    print("--- QA NODE: qa_generate_answer_node ---")

    question   = state.get("question", "")
    idea       = state.get("idea", "your startup idea")
    context    = state.get("rag_context") or state.get("analysis") or "No idea-lab report found."
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


def qa_check_refinement_needed_node(state: AgentState, llm) -> dict:
    """
    Lightweight LLM gate to check if the latest user question + assistant answer contains
    new insights or pivot decisions that warrant updating the feasibility report.
    """
    print("--- QA NODE: qa_check_refinement_needed_node ---")
    question = state.get("question", "").strip()
    answer = state.get("qa_answer", "").strip()
    analysis = state.get("analysis", "").strip()

    if not analysis or not question or not answer:
        return {"should_refine": False, "refinement_reason": "Missing inputs."}

    prompt = (
        "You are an AI startup analyst evaluating if a conversation turn changes a startup's feasibility analysis.\n"
        "Analyze the following conversation turn between a founder and a startup advisor:\n\n"
        f"Founder: {question}\n"
        f"Advisor: {answer}\n\n"
        "Original Feasibility Report summary keys/data:\n"
        f"{analysis[:1500]}\n\n"
        "Task:\n"
        "Determine if the founder provided new concrete facts, target audience shifts, strategic pivots, "
        "competitor observations, or decisions that modify the core assumptions, next steps, or the feasibility score of the original report.\n"
        "If the user is just asking generic questions, saying thank you, or no new concrete data is added, output False.\n"
        "Return a JSON object with two fields:\n"
        "1. \"should_refine\": boolean (true or false)\n"
        "2. \"reason\": string (brief explanation of why)\n\n"
        "JSON Response:"
    )

    try:
        response = llm.invoke(prompt)
        content = _extract_llm_content(response)
        parsed = parse_json_from_text(content, expected_type=dict)
        should_refine = bool(parsed.get("should_refine", False))
        reason = str(parsed.get("reason", "No reason provided."))
        print(f"  [Refinement Gate] should_refine: {should_refine}. Reason: {reason}")
    except Exception as e:
        logger.warning("qa_check_refinement_needed failed: %s", e)
        should_refine = False
        reason = f"Error in gate: {e}"

    trace = _append_trace(
        state,
        "qa_check_refinement_needed",
        f"Evaluated refinement gate. decision={should_refine}",
        {"should_refine": should_refine, "reason": reason},
    )
    return {"should_refine": should_refine, "refinement_reason": reason, "trace": trace}


def qa_refine_report_node(state: AgentState, llm) -> dict:
    """
    Regenerates the feasibility report incorporating the new Q&A discussion insights.
    """
    print("--- QA NODE: qa_refine_report_node ---")
    question = state.get("question", "")
    answer = state.get("qa_answer", "")
    original_analysis = state.get("analysis", "")
    idea = state.get("idea", "the startup idea")

    prompt = (
        "You are an elite startup analysis agent. Refine the existing feasibility report of the startup idea based on the new Q&A turn.\n\n"
        f"Startup Idea: {idea}\n\n"
        f"=== ORIGINAL FEASIBILITY REPORT ===\n"
        f"{original_analysis}\n"
        "====================================\n\n"
        f"=== NEW DISCUSSION TURN ===\n"
        f"Founder: {question}\n"
        f"Advisor: {answer}\n"
        "============================\n\n"
        "Instructions:\n"
        "1. Incorporate the new discussion points (corrections, choices, competitor details) into the appropriate section(s) of the feasibility report.\n"
        "2. If the new information affects feasibility, adjust the \"score\" field accordingly (e.g. '75/100'). Keep only the numeric score in \"score\".\n"
        "3. Put the score explanation in \"score_rationale\", never inside \"score\".\n"
        "4. Keep all other unchanged details in the report intact.\n"
        "5. Your response must be in valid JSON conforming to the requested schema.\n"
    )

    try:
        if hasattr(llm, "with_structured_output"):
            structured_llm = llm.with_structured_output(FeasibilityReportSchema)
            response = structured_llm.invoke(prompt)
            if isinstance(response, FeasibilityReportSchema):
                refined = response.model_dump_json()
                logger.info("qa_refine_report.structured_output_success")
                trace = _append_trace(state, "qa_refine_report", "Successfully refined report structure.", {"refined": True})
                return {"analysis": refined, "trace": trace}
            elif isinstance(response, dict):
                refined = json.dumps(response, ensure_ascii=False)
                logger.info("qa_refine_report.structured_output_dict_success")
                trace = _append_trace(state, "qa_refine_report", "Successfully refined report (dict).", {"refined": True})
                return {"analysis": refined, "trace": trace}
    except Exception as exc:
        logger.warning("qa_refine_report structured output failed: %s. Falling back to text.", exc)

    try:
        response = llm.invoke(prompt)
        content = _extract_llm_content(response)
        refined = json.dumps(parse_feasibility_report(content), ensure_ascii=False)
        trace = _append_trace(state, "qa_refine_report", "Refined report using fallback text generation.", {"refined": True, "fallback": True})
        return {"analysis": refined, "trace": trace}
    except Exception as exc:
        logger.error("qa_refine_report fallback failed: %s", exc)
        trace = _append_trace(state, "qa_refine_report", f"Failed to refine report: {exc}", {"refined": False, "error": str(exc)})
        return {"trace": trace}


def route_refinement(state: AgentState) -> str:
    if state.get("should_refine", False):
        print("--- QA ROUTER: Routing to qa_refine_report ---")
        return "refine"
    print("--- QA ROUTER: Routing to END ---")
    return "skip"


# ── Graph wiring ───────────────────────────────────────────────────────────────
def build_qa_graph(*, memory_llm=None, rewrite_llm=None, answer_llm=None, refine_llm=None):
    qa_workflow = StateGraph(AgentState)

    memory_llm = memory_llm or get_llm(temperature=0.2)
    rewrite_llm = rewrite_llm or get_llm(temperature=0.2)
    answer_llm = answer_llm or get_llm()

    qa_workflow.add_node("qa_load_state", qa_load_state_node)
    qa_workflow.add_node("qa_filter", qa_filter_node)
    qa_workflow.add_node("qa_invalid_response", qa_invalid_response_node)
    qa_workflow.add_node("qa_memory", lambda state: qa_memory_node(state, memory_llm))
    qa_workflow.add_node("qa_modify_query", lambda state: qa_modify_query_node(state, rewrite_llm))
    qa_workflow.add_node("qa_use_report_context", qa_use_report_context_node)
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
    qa_workflow.add_edge("qa_modify_query", "qa_use_report_context")
    qa_workflow.add_edge("qa_use_report_context", "qa_generate_answer")
    qa_workflow.add_edge("qa_generate_answer", END)
    qa_workflow.add_edge("qa_invalid_response", END)

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
            "    qa_load_state --> qa_filter\n"
            "    qa_filter -- qa_invalid_response --> qa_invalid_response\n"
            "    qa_filter -- qa_memory --> qa_memory\n"
            "    qa_invalid_response --> END\n"
            "    qa_memory --> qa_modify_query\n"
            "    qa_modify_query --> qa_use_report_context\n"
            "    qa_use_report_context --> qa_generate_answer\n"
            "    qa_generate_answer --> END"
        )
