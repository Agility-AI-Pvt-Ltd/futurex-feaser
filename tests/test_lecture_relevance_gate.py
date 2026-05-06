import unittest

from lecturebot.graph import route_relevance
from lecturebot.tools import _fallback_relevance_check, irrelevant_question_node


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
