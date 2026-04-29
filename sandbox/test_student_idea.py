"""
Simple end-to-end tester for the student idea feasibility flow.

Usage:
    python3 sandbox/test_student_idea.py

Optional:
    python3 sandbox/test_student_idea.py \
      --idea "AI study planner for college students" \
      --clarification "It personalizes schedules using deadlines and energy levels."
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8888/api"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test the student idea feasibility API flow.")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL. Default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--idea",
        default="AI tutor for college students with adaptive study plans",
        help="Initial student idea.",
    )
    parser.add_argument(
        "--user-name",
        default="Student",
        help="User name to send in the payload.",
    )
    parser.add_argument(
        "--ideal-customer",
        default="college students",
        help="Ideal customer description.",
    )
    parser.add_argument(
        "--problem-solved",
        default="helps students study consistently and prepare better for exams",
        help="Problem solved by the idea.",
    )
    parser.add_argument(
        "--author-id",
        default="student_test_user",
        help="Author identifier.",
    )
    parser.add_argument(
        "--clarification",
        default=(
            "The product would analyze syllabus deadlines, learning pace, and weak subjects "
            "to build personalized daily study plans."
        ),
        help="Second-turn clarification answer that triggers research and final analysis.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Request timeout in seconds.",
    )
    parser.add_argument(
        "--qa-question",
        default="What existing competitors and tools are most relevant for this student idea?",
        help="Question to ask the QA/RAG endpoint after analysis completes.",
    )
    parser.add_argument(
        "--qa-wait-seconds",
        type=int,
        default=5,
        help="Seconds to wait after the second /chat call before querying /qa.",
    )
    return parser.parse_args()


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def pretty_print(title: str, payload: Any) -> None:
    print(f"\n=== {title} ===")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(payload)


def pretty_print_top_chunks(chunks: list[dict[str, Any]]) -> None:
    print("\n=== QA TOP CHUNKS ===")
    if not chunks:
        print("No chunks were returned.")
        return

    for chunk in chunks:
        rank = chunk.get("rank", "?")
        chunk_id = chunk.get("id", "")
        source = chunk.get("source", "unknown")
        score = chunk.get("score", "")
        text = chunk.get("text", "") or ""

        print(f"\n--- Chunk {rank} ---")
        print(f"id: {chunk_id}")
        print(f"source: {source}")
        print(f"score: {score}")
        print("text:")
        print(text)


def main() -> int:
    args = parse_args()
    chat_url = f"{args.base_url.rstrip('/')}/chat"
    qa_url = f"{args.base_url.rstrip('/')}/qa"

    first_payload = {
        "idea": args.idea,
        "user_name": args.user_name,
        "ideal_customer": args.ideal_customer,
        "problem_solved": args.problem_solved,
        "authorId": args.author_id,
        "conversation_id": None,
    }

    try:
        first_response = post_json(chat_url, first_payload, timeout=args.timeout)
    except requests.RequestException as exc:
        print(f"First /chat request failed: {exc}", file=sys.stderr)
        return 1

    pretty_print("FIRST RESPONSE", first_response)

    conversation_id = first_response.get("conversation_id")
    if not conversation_id:
        print("Missing conversation_id in first response.", file=sys.stderr)
        return 1

    second_payload = {
        "idea": args.clarification,
        "user_name": args.user_name,
        "ideal_customer": args.ideal_customer,
        "problem_solved": args.problem_solved,
        "authorId": args.author_id,
        "conversation_id": conversation_id,
    }

    try:
        second_response = post_json(chat_url, second_payload, timeout=args.timeout)
    except requests.RequestException as exc:
        print(f"Second /chat request failed: {exc}", file=sys.stderr)
        return 1

    pretty_print("SECOND RESPONSE", second_response)

    print(f"\nWaiting {args.qa_wait_seconds} second(s) before QA so background embeddings can finish...")
    time.sleep(args.qa_wait_seconds)

    qa_payload = {
        "conversation_id": conversation_id,
        "question": args.qa_question,
    }

    try:
        qa_response = post_json(qa_url, qa_payload, timeout=args.timeout)
    except requests.RequestException as exc:
        print(f"QA /qa request failed: {exc}", file=sys.stderr)
        return 1

    pretty_print("QA RESPONSE", qa_response)
    pretty_print_top_chunks(qa_response.get("top_chunks") or [])

    print("\n=== SUMMARY ===")
    print(f"conversation_id: {conversation_id}")
    print(f"log_folder: scrape_run_logs")
    print(f"rag_log_folder: rag_run_logs")
    print("If scraping was triggered, inspect the newest .txt file in scrape_run_logs/ for the full web research log.")
    print("Inspect the newest .txt file in rag_run_logs/ to see the QA query and top-k retrieved chunks.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
