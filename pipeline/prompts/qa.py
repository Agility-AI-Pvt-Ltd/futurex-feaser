from typing import Optional


def get_qa_prompt(
    idea: str,
    context: str,
    query: str,
    qa_history: Optional[list] = None,
    qa_summary: Optional[str] = "",
) -> str:
    """
    Generates the RAG Q&A prompt with sliding-window conversation memory.

    Args:
        idea:        The startup idea name/concept.
        context:     RAG-retrieved text chunks from Qdrant.
        query:       The user's current question.
        qa_history:  List of recent {\"q\": ..., \"a\": ...} turns (last N, already windowed).
        qa_summary:  LLM-generated summary of older turns that fell outside the window.
    """
    qa_history = qa_history or []

    # Build the memory block ─────────────────────────────────────────────────
    memory_block = ""
    if qa_summary:
        memory_block += (
            "=== SUMMARY OF EARLIER CONVERSATION ===\n"
            f"{qa_summary}\n"
            "========================================\n\n"
        )
    if qa_history:
        turns_str = "\n".join(
            [f"User: {t.get('q', '')}\nAssistant: {t.get('a', '')}" for t in qa_history]
        )
        memory_block += (
            "=== RECENT CONVERSATION (last turns) ===\n"
            f"{turns_str}\n"
            "=========================================\n\n"
        )

    return (
        f"You are an expert startup advisor assisting a user with their idea: '{idea}'.\n\n"
        f"They have already generated a feasibility report and are now having a follow-up Q&A session.\n\n"
        f"{memory_block}"
        f"=== RETRIEVED CONTEXT FROM RESEARCH & REPORT ===\n"
        f"{context}\n"
        f"=================================================\n\n"
        f"User's Current Question: {query}\n\n"
        f"Instructions:\n"
        f"1. Use the conversation history above to understand context and avoid repeating yourself.\n"
        f"2. Answer thoroughly based on the retrieved context and prior conversation.\n"
        f"3. If the context does not cover the point, say so politely and offer reasoned general advice.\n"
        f"4. Do not ignore the user's specific constraints or nuances.\n"
        f"5. Format the response clearly using markdown for readability."
    )
