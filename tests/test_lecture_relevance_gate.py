import unittest

from lecturebot.graph import route_after_question_analysis, route_relevance
from lecturebot.tools import (
    _fallback_relevance_check,
    _fallback_question_analysis,
    _looks_like_whole_transcript_summary_request,
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
        self.assertEqual(
            _fallback_question_analysis({"question": "Give me key points of this lecture"})[
                "answer_mode"
            ],
            "whole_transcript_summary",
        )
        self.assertEqual(
            route_after_question_analysis({"answer_mode": "whole_transcript_summary"}),
            "summary",
        )
        self.assertEqual(route_after_question_analysis({"answer_mode": "rag"}), "rag")

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
