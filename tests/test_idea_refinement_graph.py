import unittest

from pipeline.idea_refinement_graph import (
    idea_refinement_apply_node,
    idea_refinement_filter_node,
    idea_refinement_modify_query_node,
    route_idea_refinement_filter,
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
        response = self.responses.pop(0)
        return FakeResponse(response)


class IdeaRefinementGraphTests(unittest.TestCase):
    def test_filter_routes_vague_refinement(self):
        result = idea_refinement_filter_node(
            {"refinement_text": "improve it", "trace": []},
            FakeLLM([]),
        )

        self.assertFalse(result["is_valid_refinement"])
        self.assertEqual(route_idea_refinement_filter(result), "vague")

    def test_filter_accepts_concrete_refinement(self):
        llm = FakeLLM(['{"is_valid_refinement": true, "reason": "Adds competitor-matching features."}'])
        result = idea_refinement_filter_node(
            {
                "idea": "AI study planner",
                "problem_solved": "helps students plan exam revision",
                "ideal_customer": "college students",
                "analysis": '{"competitors":"Competitors have reminders."}',
                "refinement_text": "Add adaptive reminders and calendar sync for missed study sessions.",
                "trace": [],
            },
            llm,
        )

        self.assertTrue(result["is_valid_refinement"])
        self.assertEqual(route_idea_refinement_filter(result), "valid")

    def test_modify_query_and_apply_create_next_version(self):
        query_llm = FakeLLM(["AI study planner with adaptive reminders and calendar sync"])
        query_result = idea_refinement_modify_query_node(
            {
                "idea": "AI study planner",
                "problem_solved": "helps students plan exam revision",
                "ideal_customer": "college students",
                "refinement_text": "Add adaptive reminders and calendar sync.",
                "trace": [],
            },
            query_llm,
        )

        apply_llm = FakeLLM(
            [
                '{"startup_idea":"AI study planner with adaptive reminders",'
                '"problem_solved":"helps students recover missed study sessions",'
                '"ideal_customer":"college students preparing for exams",'
                '"score_delta":5,'
                '"score_after":"75/100",'
                '"rationale":"Directly addresses a competitor feature gap."}'
            ]
        )
        apply_result = idea_refinement_apply_node(
            {
                "idea": "AI study planner",
                "problem_solved": "helps students plan exam revision",
                "ideal_customer": "college students",
                "analysis": '{"competitors":"Competitors have reminders."}',
                "refinement_query": query_result["refinement_query"],
                "refinement_text": "Add adaptive reminders and calendar sync.",
                "refinement_score_before": "70/100",
                "refinement_version": 1,
                "trace": [],
            },
            apply_llm,
        )

        self.assertEqual(apply_result["refined_idea"], "AI study planner with adaptive reminders")
        self.assertEqual(apply_result["refinement_score_delta"], 5)
        self.assertEqual(apply_result["refinement_score_after"], "75/100")
        self.assertIn("already present", apply_llm.prompts[0])
        self.assertIn("score_delta to 0", apply_llm.prompts[0])

    def test_apply_clamps_score_delta_to_remaining_room_under_100(self):
        apply_llm = FakeLLM(
            [
                '{"startup_idea":"AI study planner with reminders",'
                '"problem_solved":"helps students recover missed study sessions",'
                '"ideal_customer":"college students preparing for exams",'
                '"score_delta":10,'
                '"score_after":"108/100",'
                '"rationale":"Useful improvement."}'
            ]
        )

        result = idea_refinement_apply_node(
            {
                "idea": "AI study planner",
                "problem_solved": "helps students plan exam revision",
                "ideal_customer": "college students",
                "analysis": '{"competitors":"Competitors have reminders."}',
                "refinement_query": "Add reminders",
                "refinement_text": "Add reminders.",
                "refinement_score_before": "98/100",
                "refinement_version": 1,
                "trace": [],
            },
            apply_llm,
        )

        self.assertEqual(result["refinement_score_delta"], 2)
        self.assertEqual(result["refinement_score_after"], "100/100")

    def test_apply_keeps_score_at_100_when_already_maxed(self):
        apply_llm = FakeLLM(
            [
                '{"startup_idea":"AI study planner",'
                '"problem_solved":"helps students plan exam revision",'
                '"ideal_customer":"college students",'
                '"score_delta":5,'
                '"score_after":"105/100",'
                '"rationale":"Repeated feature."}'
            ]
        )

        result = idea_refinement_apply_node(
            {
                "idea": "AI study planner",
                "problem_solved": "helps students plan exam revision",
                "ideal_customer": "college students",
                "analysis": '{"next_step":"Add reminders."}',
                "refinement_query": "Add reminders",
                "refinement_text": "Add reminders.",
                "refinement_score_before": "100/100",
                "refinement_version": 1,
                "trace": [],
            },
            apply_llm,
        )

        self.assertEqual(result["refinement_score_delta"], 0)
        self.assertEqual(result["refinement_score_after"], "100/100")


if __name__ == "__main__":
    unittest.main()
