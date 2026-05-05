import unittest

from pipeline.qa_graph import (
    QA_SUMMARIZE_THRESHOLD,
    qa_generate_answer_node,
    qa_memory_node,
    qa_modify_query_node,
)
from pipeline.tools import (
    cross_question_node,
    engagement_question_node,
    generate_engagement_reply_from_analysis,
    idea_vagueness_filter_node,
    llm_agent_node,
    modify_query_node,
)


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("FakeLLM received more calls than expected")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, str):
            return FakeResponse(response)
        return response


class LlmInjectionTests(unittest.TestCase):
    def test_qa_memory_node_uses_injected_llm_for_summarization(self):
        history = [
            {"q": f"Question {idx}", "a": f"Answer {idx}"}
            for idx in range(QA_SUMMARIZE_THRESHOLD + 1)
        ]
        llm = FakeLLM(["compressed summary"])

        result = qa_memory_node(
            {
                "qa_history": history,
                "qa_summary": "old summary",
                "trace": [],
            },
            llm,
        )

        self.assertEqual(result["qa_summary"], "compressed summary")
        self.assertEqual(len(llm.prompts), 1)

    def test_qa_modify_query_node_uses_injected_llm(self):
        llm = FakeLLM(['"standalone india launch viability"'])
        result = qa_modify_query_node(
            {
                "question": "will it work in india",
                "idea": "smart mirror startup",
                "problem_solved": "helps retail shoppers preview outfits",
                "conversation_history": [],
                "trace": [],
            },
            llm,
        )

        self.assertEqual(result["qa_retrieval_query"], "standalone india launch viability")
        self.assertEqual(len(llm.prompts), 1)

    def test_qa_generate_answer_node_uses_injected_llm(self):
        llm = FakeLLM(["Final QA answer"])
        result = qa_generate_answer_node(
            {
                "question": "What is the biggest risk?",
                "idea": "smart mirror startup",
                "rag_context": "Competitors are strong.",
                "qa_history": [{"q": "Earlier?", "a": "Yes."}],
                "qa_summary": "Older turns summary",
                "trace": [],
            },
            llm,
        )

        self.assertEqual(result["qa_answer"], "Final QA answer")
        self.assertEqual(len(llm.prompts), 1)

    def test_idea_vagueness_filter_node_uses_injected_llm(self):
        llm = FakeLLM(['{"is_vague": true, "reason": "too generic"}'])
        result = idea_vagueness_filter_node(
            {
                "idea": "app idea",
                "problem_solved": "something",
                "ideal_customer": "everyone",
                "is_new_chat": True,
            },
            llm,
        )

        self.assertTrue(result["is_vague"])
        self.assertIn("too generic", result["vague_message"])

    def test_modify_query_node_uses_injected_llm(self):
        llm = FakeLLM(
            ['["mirror startup competitors", "smart mirror fashion tools", "smart mirror yc startups"]']
        )
        result = modify_query_node(
            {
                "idea": "smart mirror startup",
                "problem_solved": "helps shoppers preview outfits",
                "conversation_history": [],
                "current_message": "focus on fashion retail",
            },
            llm,
        )

        self.assertEqual(
            result["optimized_queries"],
            [
                "mirror startup competitors",
                "smart mirror fashion tools",
                "smart mirror yc startups",
            ],
        )

    def test_cross_question_node_uses_injected_llm(self):
        llm = FakeLLM(["What evidence do you have that salons would pay for this first?"])
        result = cross_question_node(
            {
                "idea": "booking assistant for salons",
                "problem_solved": "reduces no-shows",
                "ideal_customer": "small salon owners",
                "conversation_history": [],
                "current_message": "",
                "analysis": "",
            },
            llm,
        )

        self.assertIn("salons", result["analysis"])

    def test_llm_agent_node_uses_injected_llm(self):
        llm = FakeLLM(['{"score":"7/10"}'])
        result = llm_agent_node(
            {
                "idea": "smart mirror startup",
                "ideal_customer": "fashion retailers",
                "search_results": "Search evidence",
                "conversation_id": "conv-1",
            },
            llm,
        )

        self.assertEqual(result["analysis"], '{"score":"7/10"}')

    def test_engagement_question_node_uses_injected_llm(self):
        llm = FakeLLM(["What is the fastest way you can validate willingness to pay this month?"])
        result = engagement_question_node(
            {
                "idea": "smart mirror startup",
                "analysis": '{"score":"6/10","idea_fit":"good","competitors":"many","opportunity":"large","targeting":"broad","next_step":"validate pricing"}',
            },
            llm,
        )

        self.assertIn("validate", result["engagement_question"].lower())

    def test_generate_engagement_reply_from_analysis_uses_injected_llm(self):
        llm = FakeLLM(["That is a promising signal, but pricing proof is still the next milestone."])
        result = generate_engagement_reply_from_analysis(
            "smart mirror startup",
            '{"score":"6/10","idea_fit":"good","competitors":"many","opportunity":"large","targeting":"broad","next_step":"validate pricing"}',
            "How will you validate pricing?",
            "I will run five paid pilots.",
            llm,
        )

        self.assertIn("pricing", result.lower())


if __name__ == "__main__":
    unittest.main()
