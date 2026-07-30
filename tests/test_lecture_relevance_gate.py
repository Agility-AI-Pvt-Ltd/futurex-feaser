import unittest

from lecturebot.graph import route_after_question_analysis, route_relevance
from lecturebot.tools import (
    RAG_ANSWER_MODE,
    _fallback_relevance_check,
    _fallback_question_analysis,
    _looks_like_whole_transcript_summary_request,
    _summary_intent_texts,
    irrelevant_question_node,
)


class LectureRelevanceGateTests(unittest.TestCase):
    def test_fallback_marks_irrelevant_when_no_context_chunks(self):
        result = _fallback_relevance_check(
            {
                "question": "Who won the world cup?",
                "context_chunks": [],
            }
        )

        self.assertEqual(result["relevance_label"], "irrelevant")

    def test_fallback_marks_partial_when_context_exists(self):
        result = _fallback_relevance_check(
            {
                "question": "Explain the optimization example",
                "context_chunks": [{"text": "Gradient descent was discussed"}],
            }
        )

        self.assertEqual(result["relevance_label"], "partially_relevant")

    def test_route_relevance_sends_irrelevant_to_refusal(self):
        self.assertEqual(route_relevance({"relevance_label": "irrelevant"}), "irrelevant")
        self.assertEqual(route_relevance({"relevance_label": "relevant"}), "answer")

    def test_summary_intent_routes_around_rag(self):
        self.assertTrue(_looks_like_whole_transcript_summary_request("Give me a summary of it"))
        self.assertTrue(
            _looks_like_whole_transcript_summary_request(
                "Give me a complete overview of this lecture"
            )
        )
        self.assertTrue(
            _looks_like_whole_transcript_summary_request("I want a summarization of this transcript")
        )
        self.assertFalse(
            _looks_like_whole_transcript_summary_request("What is gradient descent in this lecture?")
        )
        self.assertEqual(
            _fallback_question_analysis({"question": "Give me key points of this lecture"})[
                "answer_mode"
            ],
            "whole_transcript_summary",
        )
        self.assertEqual(
            _fallback_question_analysis({"question": "Give me a complete overview"})[
                "answer_mode"
            ],
            "whole_transcript_summary",
        )
        self.assertEqual(
            route_after_question_analysis({"answer_mode": "whole_transcript_summary"}),
            "summary",
        )
        self.assertEqual(route_after_question_analysis({"answer_mode": "rag"}), "rag")

    def test_summary_intent_uses_llm_normalized_question_text(self):
        state = {"question": "plz give summry of the sesion"}
        analysis = {
            "answer_mode": RAG_ANSWER_MODE,
            "normalized_question": "Please give a summary of the session",
            "resolved_question": "Please summarize the whole lecture session",
        }

        self.assertTrue(
            _looks_like_whole_transcript_summary_request(
                *_summary_intent_texts(state, analysis)
            )
        )

    def test_fallback_includes_normalized_question(self):
        result = _fallback_question_analysis({"question": "What is gradient descent?"})

        self.assertEqual(result["normalized_question"], "What is gradient descent?")
        self.assertEqual(result["answer_mode"], RAG_ANSWER_MODE)

    def test_irrelevant_question_node_returns_refusal_answer(self):
        result = irrelevant_question_node(
            {
                "relevance_reason": "The transcript is about calculus, not cricket.",
            }
        )

        self.assertIn("does not seem to be covered", result["answer"])
        self.assertEqual(result["sources"], [])


if __name__ == "__main__":
    unittest.main()
