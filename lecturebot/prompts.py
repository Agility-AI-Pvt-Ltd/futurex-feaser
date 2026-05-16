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
                "Your primary job is to answer questions using ONLY the transcript context provided below. "
                "Treat the transcript context as absolute ground truth. "
                "\nFollow these rules strictly in order of priority: "
                "1. Greetings & Pleasantries: If the user is just saying hi or hello, respond naturally to the greeting. "
                "2. Unclear/Gibberish: If the user's message is gibberish or unclear, politely ask them to clarify. "
                "3. Factual Questions: Provide a highly detailed, comprehensive, and friendly explanation based on the context. Act like an engaging human tutor. "
                "Use formatting like bolding and bullet points to make the answer easy to read. "
                "If the context addresses the underlying topic (even if it doesn't match the exact premise of the question), focus entirely on explaining what IS discussed in rich detail, rather than defensively stating what is missing. "
                "If you find an answer or related topic, always append the source name at the end (e.g., '(Source: recording.vtt)'). "
                "Only if the context is completely irrelevant to the question should you state that the information is not in the transcript. DO NOT hallucinate external facts."
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


def get_transcript_chunk_summary_messages(
    *,
    transcript_name: str,
    chunk_text: str,
    chunk_number: int,
    total_chunks: int,
):
    return [
        SystemMessage(
            content=(
                "You summarize lecture transcript text for a student learning platform. "
                "Use only the provided transcript text. Capture concrete topics, definitions, "
                "examples, arguments, instructor guidance, and important transitions. "
                "Do not invent material that is not present."
            )
        ),
        HumanMessage(
            content=(
                f"Transcript: {transcript_name or 'uploaded transcript'}\n"
                f"Chunk {chunk_number} of {total_chunks}\n\n"
                "--- TRANSCRIPT TEXT ---\n"
                f"{chunk_text}\n\n"
                "--- TASK ---\n"
                "Write a detailed but compact summary of this chunk."
            )
        ),
    ]


def get_transcript_summary_merge_messages(
    *,
    transcript_name: str,
    chunk_summaries: List[str],
    max_chars: int,
):
    joined_summaries = "\n\n".join(
        f"--- CHUNK {index + 1} SUMMARY ---\n{summary}"
        for index, summary in enumerate(chunk_summaries)
    )
    return [
        SystemMessage(
            content=(
                "You create a comprehensive study summary from ordered lecture chunk summaries. "
                "Use only the supplied summaries. Preserve the lecture's structure and key details. "
                "Make the result useful for answering later overview, recap, key-points, and notes questions. "
                f"Return only the summary, no more than {max_chars} characters."
            )
        ),
        HumanMessage(
            content=(
                f"Transcript: {transcript_name or 'uploaded transcript'}\n\n"
                f"{joined_summaries}\n\n"
                "--- FINAL SUMMARY ---"
            )
        ),
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
        "answer_mode": "rag | whole_transcript_summary",
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
                " Set answer_mode='whole_transcript_summary' when the user asks for an overview, "
                "summary, recap, main points, key points, notes, gist, or asks what the whole lecture/transcript is about. "
                "Use answer_mode='rag' for specific factual questions that should be answered from relevant transcript chunks."
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


def get_relevance_check_messages(
    question: str,
    resolved_question: str,
    context_text: str,
    memory_summary: str = "",
):
    output_schema = {
        "relevance": "relevant | partially_relevant | irrelevant",
        "confidence": "low | medium | high",
        "reason": "short explanation grounded in the transcript context",
    }
    return [
        SystemMessage(
            content=(
                "Decide whether the student's question is answerable from the transcript context. "
                "Return only valid JSON. "
                "Use 'relevant' when the transcript directly covers the question. "
                "Use 'partially_relevant' when the transcript covers related material but not the exact ask. "
                "Use 'irrelevant' when the transcript does not meaningfully cover the topic."
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
                "--- USER QUESTION ---\n"
                f"{question}\n\n"
                "--- RESOLVED QUESTION ---\n"
                f"{resolved_question}\n\n"
                "--- TRANSCRIPT CONTEXT ---\n"
                f"{context_text or 'No transcript context retrieved.'}"
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
