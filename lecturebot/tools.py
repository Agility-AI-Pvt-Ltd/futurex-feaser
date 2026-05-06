from __future__ import annotations

import json

from core.config import settings
from core.llm_factory import get_llm
from core.logging import get_logger, truncate_for_log
from core.observability import ls_traceable
from pipeline.tools import _extract_json_payload
from lecturebot.prompts import (
    get_memory_summary_messages,
    get_question_analysis_messages,
    get_relevance_check_messages,
    get_rag_chat_messages,
)
from lecturebot.rag import search_similar
from lecturebot.state import ChatPipelineState


logger = get_logger(__name__)
ANSWER_FALLBACK = (
    "I could not generate a full answer right now because the model service is temporarily "
    "unavailable. Please try again in a moment."
)
LOW_SIGNAL_USER_MESSAGES = {"hi", "hii", "hello", "hey", "ok", "okay", "thanks"}
DEFAULT_RELATION = "standalone"
RELEVANCE_REFUSAL = (
    "That question does not seem to be covered by this transcript, so I should not answer it as if it were. "
    "Please ask about topics actually discussed in the uploaded lecture."
)


def _recent_history(history: list[dict], limit: int) -> list[dict]:
    if limit <= 0:
        return []
    return history[-limit:]


def _build_retrieval_query(state: ChatPipelineState) -> str:
    # The analyze_question_node already uses the LLM to rewrite the user's question
    # into a standalone 'resolved_question' that incorporates necessary context.
    # We should search ONLY using this focused resolved_question for maximum semantic accuracy.
    return state.get("resolved_question", state["question"]).strip()


def _fallback_question_analysis(state: ChatPipelineState) -> dict:
    question = state["question"].strip()
    history = state.get("history", [])
    relation = DEFAULT_RELATION
    history_context_used = "none"

    lowered = question.lower()
    if lowered in LOW_SIGNAL_USER_MESSAGES:
        relation = "greeting"
    elif history and (
        any(token in lowered for token in {"that", "this", "it", "they", "he", "she"})
        or len(question.split()) <= 6
    ):
        last_message = history[-1]
        relation = (
            "follow_up_to_ai"
            if last_message.get("role") == "assistant"
            else "follow_up_to_user"
        )
        history_context_used = last_message.get("content", "").strip()[:200] or "none"

    return {
        "conversation_relation": relation,
        "relation_confidence": "low",
        "relation_reason": "fallback heuristic",
        "resolved_question": question,
        "history_context_used": history_context_used,
    }


def _fallback_relevance_check(state: ChatPipelineState) -> dict:
    if state.get("conversation_relation") == "greeting":
        return {
            "relevance_label": "relevant",
            "relevance_confidence": "low",
            "relevance_reason": "Greeting messages are allowed without transcript grounding.",
        }

    if state.get("context_chunks"):
        return {
            "relevance_label": "partially_relevant",
            "relevance_confidence": "low",
            "relevance_reason": "Retrieved transcript chunks exist, so allow a grounded partial answer.",
        }

    return {
        "relevance_label": "irrelevant",
        "relevance_confidence": "low",
        "relevance_reason": "No transcript context was retrieved for the question.",
    }


@ls_traceable(run_type="tool", name="lecture_analyze_question_node", tags=["lecturebot", "node"])
def analyze_question_node(state: ChatPipelineState) -> dict:
    trace_id = state.get("trace_id", "unknown")
    try:
        llm = get_llm(model=settings.LECTURE_OPENAI_MODEL_NAME, temperature=0.0)
        messages = get_question_analysis_messages(
            question=state["question"],
            history=state.get("history", []),
            memory_summary=state.get("memory_summary", ""),
        )
        response = llm.invoke(messages)
        parsed = json.loads(_extract_json_payload(response.content or ""))
        result = {
            "conversation_relation": parsed.get("relation", DEFAULT_RELATION),
            "relation_confidence": parsed.get("confidence", "medium"),
            "relation_reason": parsed.get("reason", ""),
            "resolved_question": parsed.get("resolved_question", state["question"]),
            "history_context_used": parsed.get("history_context_used", "none"),
        }
    except Exception:
        logger.exception("question_analysis.error trace_id=%s", trace_id)
        result = _fallback_question_analysis(state)
    return result


@ls_traceable(run_type="retriever", name="lecture_retrieve_context_node", tags=["lecturebot", "retrieval"])
def retrieve_context_node(state: ChatPipelineState) -> dict:
    trace_id = state.get("trace_id", "unknown")
    retrieval_query = _build_retrieval_query(state)
    try:
        context_chunks = search_similar(
            retrieval_query,
            top_k=5,
            transcript_id=state.get("transcript_id"),
            source_name=state.get("transcript_source", ""),
            session_name=state.get("transcript_session_name", ""),
            object_path=state.get("transcript_object_path", ""),
            collection_name=state.get("transcript_collection_name", ""),
        )
    except Exception:
        logger.exception("lecture_rag.retrieval.error trace_id=%s", trace_id)
        context_chunks = []

    context_text = "\n\n".join(
        f"[Source: {chunk['source']}]\n{chunk['text']}" for chunk in context_chunks
    )
    sources = sorted({chunk["source"] for chunk in context_chunks if chunk["source"]})
    return {
        "retrieval_query": retrieval_query,
        "context_chunks": context_chunks,
        "context_text": context_text,
        "sources": sources,
    }


@ls_traceable(run_type="tool", name="lecture_relevance_check_node", tags=["lecturebot", "relevance"])
def relevance_check_node(state: ChatPipelineState) -> dict:
    trace_id = state.get("trace_id", "unknown")

    if state.get("conversation_relation") == "greeting":
        return {
            "relevance_label": "relevant",
            "relevance_confidence": "high",
            "relevance_reason": "Greeting messages bypass transcript relevance gating.",
        }

    try:
        llm = get_llm(model=settings.LECTURE_OPENAI_MODEL_NAME, temperature=0.0)
        messages = get_relevance_check_messages(
            question=state["question"],
            resolved_question=state.get("resolved_question", state["question"]),
            context_text=state.get("context_text", ""),
            memory_summary=state.get("memory_summary", ""),
        )
        response = llm.invoke(messages)
        parsed = json.loads(_extract_json_payload(response.content or ""))
        label = parsed.get("relevance", "irrelevant")
        if label not in {"relevant", "partially_relevant", "irrelevant"}:
            raise ValueError(f"Unexpected relevance label: {label}")
        result = {
            "relevance_label": label,
            "relevance_confidence": parsed.get("confidence", "medium"),
            "relevance_reason": parsed.get("reason", ""),
        }
    except Exception:
        logger.exception("relevance_check.error trace_id=%s", trace_id)
        result = _fallback_relevance_check(state)
    return result


@ls_traceable(run_type="tool", name="lecture_irrelevant_question_node", tags=["lecturebot", "relevance"])
def irrelevant_question_node(state: ChatPipelineState) -> dict:
    reason = state.get("relevance_reason", "").strip()
    if reason:
        answer = f"{RELEVANCE_REFUSAL} Reason: {reason}"
    else:
        answer = RELEVANCE_REFUSAL
    return {"answer": answer, "sources": []}


@ls_traceable(run_type="tool", name="lecture_answer_question_node", tags=["lecturebot", "node"])
def answer_question_node(state: ChatPipelineState) -> dict:
    trace_id = state.get("trace_id", "unknown")
    try:
        llm = get_llm(model=settings.LECTURE_OPENAI_MODEL_NAME, temperature=0.3)
        messages = get_rag_chat_messages(
            question=state.get("resolved_question", state["question"]),
            context_text=state.get("context_text", ""),
            history=_recent_history(
                state.get("history", []),
                settings.LECTURE_RECENT_HISTORY_MESSAGES,
            ),
            memory_summary=state.get("memory_summary", ""),
            conversation_relation=state.get("conversation_relation", DEFAULT_RELATION),
            history_context_used=state.get("history_context_used", ""),
        )
        response = llm.invoke(messages)
        answer = (response.content or "").strip() or ANSWER_FALLBACK
    except Exception:
        logger.exception("answer_question.error trace_id=%s", trace_id)
        answer = ANSWER_FALLBACK

    logger.info(
        "lecture_chat.answer trace_id=%s answer=%s",
        trace_id,
        truncate_for_log(answer, settings.LECTURE_LOG_PROMPT_CHARS),
    )
    return {"answer": answer}


@ls_traceable(run_type="tool", name="lecture_summarize_memory_node", tags=["lecturebot", "node"])
def summarize_memory_node(state: ChatPipelineState) -> dict:
    trace_id = state.get("trace_id", "unknown")
    history = state.get("history", [])
    previous_summary = state.get("memory_summary", "")
    if len(history) < settings.LECTURE_SUMMARY_TRIGGER_MESSAGES and not previous_summary:
        return {"updated_memory_summary": previous_summary}

    try:
        llm = get_llm(model=settings.LECTURE_OPENAI_MODEL_NAME, temperature=0.0)
        messages = get_memory_summary_messages(
            previous_summary=previous_summary,
            recent_history=_recent_history(
                history,
                settings.LECTURE_RECENT_HISTORY_MESSAGES,
            ),
            question=state["question"],
            answer=state.get("answer", ""),
            max_chars=settings.LECTURE_MEMORY_SUMMARY_CHARS,
        )
        response = llm.invoke(messages)
        updated_summary = (response.content or "").strip()
        updated_summary = updated_summary[: settings.LECTURE_MEMORY_SUMMARY_CHARS]
    except Exception:
        logger.exception("memory_summary.error trace_id=%s", trace_id)
        updated_summary = previous_summary
    return {"updated_memory_summary": updated_summary}
