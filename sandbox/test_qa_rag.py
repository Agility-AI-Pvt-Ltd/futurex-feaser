"""
Sandbox diagnostic for the QA RAG path.

Usage:
    backend/.venv/bin/python backend/sandbox/test_qa_rag.py \
        --conversation-id <uuid> \
        --question "who had exhibited symptoms of depression"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.database import SessionLocal
from models.conversation import AgentStateModel, ChatSession
from pipeline.qa_graph import qa_app, qa_retrieve_context_node
from rag.retriever import conversation_chunk_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--retrieval-query", default="")
    parser.add_argument("--full-graph", action="store_true")
    args = parser.parse_args()

    state = {
        "conversation_id": args.conversation_id,
        "question": args.question,
        "qa_retrieval_query": args.retrieval_query or args.question,
        "analysis": "",
        "search_results": "",
        "trace": [],
    }

    print("=== QA RAG Diagnostic ===")
    print(f"conversation_id: {args.conversation_id}")
    print(f"question: {args.question}")
    print(f"retrieval_query: {state['qa_retrieval_query']}")
    print(f"persisted_chunk_count: {conversation_chunk_count(args.conversation_id)}")

    result = qa_retrieve_context_node(state)
    print(f"top_chunks: {len(result.get('top_chunks', []))}")
    print("trace_tail:")
    print(json.dumps(result.get("trace", [])[-1:], indent=2))
    print("rag_context_preview:")
    print((result.get("rag_context", "") or "")[:1200])

    if args.full_graph:
        print("\n=== Full QA Graph Run ===")
        db = SessionLocal()
        try:
            state_model = db.query(AgentStateModel).filter(
                AgentStateModel.conversation_id == args.conversation_id
            ).first()
            sessions = db.query(ChatSession).filter(
                ChatSession.conversation_id == args.conversation_id
            ).order_by(ChatSession.timestamp.asc()).all()

            if not state_model or not sessions:
                print("Unable to load persisted state for this conversation.")
                return 1

            first = sessions[0]
            graph_state = {
                "idea": first.idea or "your startup idea",
                "user_name": first.user_name or "",
                "ideal_customer": first.ideal_customer or "",
                "problem_solved": first.what_problem_it_solves or "",
                "messages": [],
                "search_results": state_model.search_results or "",
                "analysis": state_model.analysis or "",
                "is_new_chat": False,
                "conversation_id": args.conversation_id,
                "conversation_history": [{"user": s.human_message, "ai": s.ai_message} for s in sessions],
                "optimized_query": state_model.optimized_query or "",
                "optimized_queries": [],
                "current_message": args.question,
                "question": args.question,
                "rag_context": "",
                "top_chunks": [],
                "qa_answer": "",
                "trace": [],
                "qa_history": state_model.qa_history or [],
                "qa_summary": state_model.qa_summary or "",
            }

            graph_result = asyncio.run(qa_app.ainvoke(graph_state))
            print(f"top_chunks_full_graph: {len(graph_result.get('top_chunks', []))}")
            print("answer_preview:")
            print((graph_result.get("qa_answer", "") or "")[:1600])
        finally:
            db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
