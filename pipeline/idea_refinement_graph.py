"""
pipeline/idea_refinement_graph.py
Dedicated LangGraph pipeline for iterative idea refinement.

This graph is intentionally separate from the feasibility analysis graph and
the Q&A graph. It uses the existing idea-lab report as the critic context, then
produces a new version of the startup idea, problem solved, and ideal customer.
"""

from __future__ import annotations

import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from core.json_utils import parse_json_from_text
from core.llm_factory import get_llm
from core.observability import ls_traceable
from pipeline.state import AgentState


def _append_trace(state: AgentState, step: str, message: str, metadata: dict | None = None) -> list[dict]:
    trace = list(state.get("trace", []))
    trace.append({"step": step, "message": message, "metadata": metadata or {}})
    return trace


def _extract_llm_content(response: Any) -> str:
    if isinstance(response, str):
        return response
    return getattr(response, "content", "") or ""


def _is_low_signal_refinement(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if len(normalized) < 12:
        return True

    tokens = [token for token in re.split(r"\W+", normalized) if token]
    if len(tokens) < 4:
        return True

    low_signal = {
        "ok",
        "okay",
        "improve it",
        "make it better",
        "refine",
        "refine it",
        "update it",
        "yes",
    }
    return normalized in low_signal


def _parse_score(score: str) -> int | None:
    match = re.search(r"(\d{1,3})", score or "")
    if not match:
        return None
    return max(0, min(100, int(match.group(1))))


def _bounded_score_delta(raw_delta: Any, score_number: int | None) -> int:
    try:
        score_delta = int(raw_delta)
    except Exception:
        score_delta = 0

    score_delta = max(0, min(10, score_delta))
    if score_number is None:
        return score_delta
    return min(score_delta, max(0, 100 - score_number))


def idea_refinement_load_state_node(state: AgentState) -> dict:
    print("--- IDEA REFINEMENT NODE: load_state ---")
    trace = _append_trace(
        state,
        "idea_refinement_load_state",
        "Loaded current idea version and report critic context.",
        {
            "conversation_id": state.get("conversation_id"),
            "has_analysis": bool(state.get("analysis")),
            "version": state.get("refinement_version"),
        },
    )
    return {"trace": trace}


@ls_traceable(run_type="tool", name="idea_refinement_filter_node", tags=["idea_refinement", "node"])
def idea_refinement_filter_node(state: AgentState, llm) -> dict:
    print("--- IDEA REFINEMENT NODE: filter ---")
    refinement_text = (state.get("refinement_text") or "").strip()
    report = (state.get("analysis") or "").strip()

    if _is_low_signal_refinement(refinement_text):
        message = (
            "Please describe the concrete feature, audience, positioning, or business-model "
            "change you want to add to the idea."
        )
        trace = _append_trace(
            state,
            "idea_refinement_filter",
            "Blocked vague refinement before applying changes.",
            {"blocked": True, "reason": "low_signal"},
        )
        return {
            "is_valid_refinement": False,
            "validation_message": message,
            "refinement_summary": message,
            "trace": trace,
        }

    prompt = (
        "You validate whether a founder's message is a concrete idea refinement.\n"
        "Use the existing idea-lab report as context. A valid refinement must add, remove, "
        "or change a specific product feature, customer segment, problem framing, pricing, "
        "distribution, or differentiation strategy.\n\n"
        f"=== CURRENT STARTUP IDEA ===\n{state.get('idea', '')}\n\n"
        f"=== CURRENT PROBLEM SOLVED ===\n{state.get('problem_solved', '')}\n\n"
        f"=== CURRENT IDEAL CUSTOMER ===\n{state.get('ideal_customer', '')}\n\n"
        f"=== IDEA-LAB REPORT / CRITIC CONTEXT ===\n{report[:5000]}\n\n"
        f"=== FOUNDER REFINEMENT TEXT ===\n{refinement_text}\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        '  "is_valid_refinement": true,\n'
        '  "reason": "short reason"\n'
        "}\n"
    )

    try:
        parsed = parse_json_from_text(_extract_llm_content(llm.invoke(prompt)), expected_type=dict)
        is_valid = bool(parsed.get("is_valid_refinement", False))
        reason = str(parsed.get("reason", ""))
    except Exception as exc:
        is_valid = False
        reason = f"Could not validate refinement: {exc}"

    message = reason or "Valid refinement." if is_valid else (
        reason
        or "Please provide a more concrete refinement with a feature, customer, problem, or strategy change."
    )
    trace = _append_trace(
        state,
        "idea_refinement_filter",
        "Validated refinement text.",
        {"blocked": not is_valid, "reason": reason},
    )
    return {
        "is_valid_refinement": is_valid,
        "validation_message": "" if is_valid else message,
        "refinement_summary": message,
        "trace": trace,
    }


def route_idea_refinement_filter(state: AgentState) -> str:
    if state.get("is_valid_refinement", False):
        print("--- IDEA REFINEMENT ROUTER: valid -> modify_query ---")
        return "valid"
    print("--- IDEA REFINEMENT ROUTER: vague -> invalid_response ---")
    return "vague"


def idea_refinement_invalid_response_node(state: AgentState) -> dict:
    print("--- IDEA REFINEMENT NODE: invalid_response ---")
    message = state.get("validation_message") or (
        "Please provide a more specific idea refinement before I create a new version."
    )
    trace = _append_trace(state, "idea_refinement_invalid_response", message)
    return {"refinement_summary": message, "trace": trace}


@ls_traceable(run_type="tool", name="idea_refinement_modify_query_node", tags=["idea_refinement", "node"])
def idea_refinement_modify_query_node(state: AgentState, llm) -> dict:
    print("--- IDEA REFINEMENT NODE: modify_query ---")
    refinement_text = (state.get("refinement_text") or "").strip()
    prompt = (
        "Rewrite the founder's idea-refinement message into one concise standalone product-improvement query.\n"
        "Use the current idea context to resolve pronouns. Do not add facts.\n\n"
        f"Startup idea: {state.get('idea', '')}\n"
        f"Problem solved: {state.get('problem_solved', '')}\n"
        f"Ideal customer: {state.get('ideal_customer', '')}\n"
        f"Founder refinement: {refinement_text}\n\n"
        "Return ONLY the rewritten query text."
    )

    try:
        refinement_query = _extract_llm_content(llm.invoke(prompt)).strip().strip('"')
    except Exception:
        refinement_query = ""

    if not refinement_query:
        refinement_query = refinement_text

    trace = _append_trace(
        state,
        "idea_refinement_modify_query",
        "Rewrote refinement text into a standalone improvement query.",
        {"refinement_query": refinement_query},
    )
    return {"refinement_query": refinement_query, "trace": trace}


@ls_traceable(run_type="tool", name="idea_refinement_apply_node", tags=["idea_refinement", "node"])
def idea_refinement_apply_node(state: AgentState, llm) -> dict:
    print("--- IDEA REFINEMENT NODE: apply ---")
    score_before = state.get("refinement_score_before") or ""
    score_number = _parse_score(score_before)
    score_instruction = (
        f"The current report score is {score_before}. "
        "Only increase the score when the founder adds a genuinely new, specific improvement "
        "that is not already present in the current startup idea, problem solved, ideal customer, "
        "or idea-lab report. If the refinement repeats something already implemented, already "
        "recommended, or already captured in the current version, set score_delta to 0. If the "
        "founder adds features that competitors already use successfully, or features that "
        "directly address competitor gaps, unserved needs, weak targeting, or next steps named "
        "in the report, increase the score by 1 to 10 points. If the refinement is useful but "
        "weakly tied to the report, increase by 0 to 3 points. Score movement must be either "
        "+N or 0, must never be negative, and score_after must never exceed 100/100."
    )
    if score_number is None:
        score_instruction = (
            "The current report score is unavailable. Estimate a small delta from 0 to 10 only "
            "for genuinely new improvements. If the refinement is already present or repeated, "
            "set score_delta to 0. Leave score_after as an empty string."
        )

    prompt = (
        "You are an idea-lab refinement agent. Create the next version of a startup idea.\n"
        "Use the idea-lab report as a critic. Preserve the core idea unless the founder's "
        "message clearly changes it. Improve exactly these three versioned fields: "
        "startup_idea, problem_solved, ideal_customer.\n\n"
        "Scoring rule:\n"
        f"{score_instruction}\n\n"
        "Duplicate guardrail:\n"
        "- Compare the standalone refinement query against the current version and critic context.\n"
        "- If the same feature, customer, positioning, or strategy already exists, do not reward it again.\n"
        "- In that case keep the fields stable where appropriate, set score_delta to 0, and explain that the "
        "refinement was already covered.\n\n"
        f"=== CURRENT VERSION NUMBER ===\n{state.get('refinement_version', 0)}\n\n"
        f"=== CURRENT STARTUP IDEA ===\n{state.get('idea', '')}\n\n"
        f"=== CURRENT PROBLEM SOLVED ===\n{state.get('problem_solved', '')}\n\n"
        f"=== CURRENT IDEAL CUSTOMER ===\n{state.get('ideal_customer', '')}\n\n"
        f"=== IDEA-LAB REPORT / CRITIC CONTEXT ===\n{state.get('analysis', '')[:7000]}\n\n"
        f"=== STANDALONE REFINEMENT QUERY ===\n{state.get('refinement_query', '')}\n\n"
        f"=== RAW FOUNDER REFINEMENT TEXT ===\n{state.get('refinement_text', '')}\n\n"
        "Return ONLY valid JSON with this shape:\n"
        "{\n"
        '  "startup_idea": "improved startup idea",\n'
        '  "problem_solved": "improved problem solved",\n'
        '  "ideal_customer": "improved ideal customer",\n'
        '  "score_delta": 4,\n'
        '  "score_after": "79/100",\n'
        '  "rationale": "brief explanation of edits and score movement"\n'
        "}\n"
    )

    try:
        parsed = parse_json_from_text(_extract_llm_content(llm.invoke(prompt)), expected_type=dict)
    except Exception as exc:
        parsed = {
            "startup_idea": state.get("idea", ""),
            "problem_solved": state.get("problem_solved", ""),
            "ideal_customer": state.get("ideal_customer", ""),
            "score_delta": 0,
            "score_after": score_before,
            "rationale": f"Could not apply refinement automatically: {exc}",
        }

    score_delta = _bounded_score_delta(parsed.get("score_delta", 0), score_number)

    if score_number is not None:
        score_after = f"{score_number + score_delta}/100"
    else:
        score_after = str(parsed.get("score_after") or "")

    result = {
        "refined_idea": str(parsed.get("startup_idea") or state.get("idea", "")),
        "refined_problem_solved": str(parsed.get("problem_solved") or state.get("problem_solved", "")),
        "refined_ideal_customer": str(parsed.get("ideal_customer") or state.get("ideal_customer", "")),
        "refinement_score_delta": score_delta,
        "refinement_score_after": score_after,
        "refinement_summary": str(parsed.get("rationale") or "Created a new idea refinement version."),
    }
    trace = _append_trace(
        state,
        "idea_refinement_apply",
        "Applied refinement and generated next idea version.",
        {
            "score_before": score_before,
            "score_after": score_after,
            "score_delta": score_delta,
        },
    )
    return {**result, "trace": trace}


def build_idea_refinement_graph(*, validation_llm=None, rewrite_llm=None, refinement_llm=None):
    workflow = StateGraph(AgentState)

    validation_llm = validation_llm or get_llm(temperature=0)
    rewrite_llm = rewrite_llm or get_llm(temperature=0.2)
    refinement_llm = refinement_llm or get_llm(temperature=0.2)

    workflow.add_node("idea_refinement_load_state", idea_refinement_load_state_node)
    workflow.add_node(
        "idea_refinement_filter",
        lambda state: idea_refinement_filter_node(state, validation_llm),
    )
    workflow.add_node("idea_refinement_invalid_response", idea_refinement_invalid_response_node)
    workflow.add_node(
        "idea_refinement_modify_query",
        lambda state: idea_refinement_modify_query_node(state, rewrite_llm),
    )
    workflow.add_node(
        "idea_refinement_apply",
        lambda state: idea_refinement_apply_node(state, refinement_llm),
    )

    workflow.add_edge(START, "idea_refinement_load_state")
    workflow.add_edge("idea_refinement_load_state", "idea_refinement_filter")
    workflow.add_conditional_edges(
        "idea_refinement_filter",
        route_idea_refinement_filter,
        {
            "vague": "idea_refinement_invalid_response",
            "valid": "idea_refinement_modify_query",
        },
    )
    workflow.add_edge("idea_refinement_invalid_response", END)
    workflow.add_edge("idea_refinement_modify_query", "idea_refinement_apply")
    workflow.add_edge("idea_refinement_apply", END)

    return workflow.compile()


idea_refinement_app = build_idea_refinement_graph()


def get_idea_refinement_graph_mermaid() -> str:
    """Returns a Mermaid diagram for idea refinement graph visualization."""
    try:
        return idea_refinement_app.get_graph().draw_mermaid()
    except Exception:
        return (
            "graph TD\n"
            "    START --> idea_refinement_load_state\n"
            "    idea_refinement_load_state --> idea_refinement_filter\n"
            "    idea_refinement_filter -- vague --> idea_refinement_invalid_response\n"
            "    idea_refinement_filter -- valid --> idea_refinement_modify_query\n"
            "    idea_refinement_invalid_response --> END\n"
            "    idea_refinement_modify_query --> idea_refinement_apply\n"
            "    idea_refinement_apply --> END"
        )
