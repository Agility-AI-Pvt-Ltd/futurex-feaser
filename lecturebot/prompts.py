from __future__ import annotations

import json
from typing import List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


def _history_for_answer_prompt(history: List[dict]) -> List:
    prompt_messages = []
    for message in history:
        content = message.get("content", "").strip()
        if not content:
            continue
        if message.get("role") == "user":
            prompt_messages.append(HumanMessage(content=content))
        elif message.get("role") == "assistant":
            prompt_messages.append(AIMessage(content=content))
    return prompt_messages


def get_rag_chat_messages(
    question: str,
    context_text: str,
    history: List[dict],
    memory_summary: str = "",
    conversation_relation: str = "standalone",
    history_context_used: str = "",
):
    return [
        SystemMessage(
            content=(
                "You are a helpful AI assistant for a student learning platform. "
                "Your primary job is to answer from the transcript context provided below. "
                "Treat the transcript context as ground truth. "
                "If the transcript context covers the topic even partially, use it. "
                "Only say the answer is unavailable if the context is genuinely unrelated. "
                "When using the transcript, mention the source name. "
                "If the transcript is insufficient, you may supplement with general knowledge, "
                "but clearly separate that from transcript-backed information."
            )
        ),
        SystemMessage(
            content=(
                "--- CONVERSATION MEMORY SUMMARY ---\n"
                f"{memory_summary or 'No prior session summary yet.'}"
            )
        ),
        SystemMessage(
            content=(
                "--- CONVERSATION ANALYSIS ---\n"
                f"relation={conversation_relation}\n"
                f"context_used={history_context_used or 'none'}"
            )
        ),
        SystemMessage(content=f"--- TRANSCRIPT CONTEXT ---\n{context_text}"),
        *_history_for_answer_prompt(history),
        HumanMessage(content=question),
    ]


def get_question_analysis_messages(
    question: str,
    history: List[dict],
    memory_summary: str = "",
):
    recent_history = history[-6:]
    conversation_text = "\n".join(
        f"{message['role']}: {message['content']}" for message in recent_history
    )
    output_schema = {
        "relation": "standalone | follow_up_to_user | follow_up_to_ai | answering_previous_question | clarification | greeting",
        "confidence": "low | medium | high",
        "reason": "short explanation",
        "resolved_question": "self-contained rewritten user intent for retrieval and answering",
        "history_context_used": "short summary of the relevant earlier turn, or 'none'",
    }
    return [
        SystemMessage(
            content=(
                "Analyze whether the user's latest message depends on earlier conversation. "
                "Reason silently and return only valid JSON. "
                "If the user is continuing or clarifying, rewrite it into a self-contained question."
            )
        ),
        SystemMessage(
            content=(
                "--- MEMORY SUMMARY ---\n"
                f"{memory_summary or 'No prior session summary yet.'}\n\n"
                "--- OUTPUT JSON SCHEMA ---\n"
                f"{json.dumps(output_schema)}"
            )
        ),
        HumanMessage(
            content=(
                "--- RECENT CONVERSATION ---\n"
                f"{conversation_text or 'No previous messages.'}\n\n"
                "--- LATEST USER MESSAGE ---\n"
                f"{question}"
            )
        ),
    ]


def get_memory_summary_messages(
    previous_summary: str,
    recent_history: List[dict],
    question: str,
    answer: str,
    max_chars: int,
):
    conversation_text = "\n".join(
        f"{message['role']}: {message['content']}" for message in recent_history
    )
    return [
        SystemMessage(
            content=(
                "Update the running memory summary for a tutoring chatbot. "
                "Keep stable learner facts, goals, preferences, unresolved questions, and key topics. "
                "Drop small talk and keep it concise. "
                f"Return only the updated summary, no more than {max_chars} characters."
            )
        ),
        HumanMessage(
            content=(
                "--- PREVIOUS SUMMARY ---\n"
                f"{previous_summary or 'No previous summary.'}\n\n"
                "--- RECENT CONVERSATION BEFORE THIS TURN ---\n"
                f"{conversation_text or 'No previous messages.'}\n\n"
                "--- CURRENT TURN ---\n"
                f"user: {question}\nassistant: {answer}"
            )
        ),
    ]
