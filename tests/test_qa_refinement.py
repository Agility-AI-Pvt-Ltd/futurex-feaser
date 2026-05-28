import unittest
import json
from unittest.mock import MagicMock
from pipeline.state import AgentState
from pipeline.qa_graph import qa_check_refinement_needed_node, qa_refine_report_node, route_refinement
from pipeline.tools import FeasibilityReportSchema

class TestQaRefinement(unittest.TestCase):
    def test_refinement_needed_gate_true(self):
        # Setup mock LLM that returns should_refine=True
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"should_refine": true, "reason": "Founder pivoted from B2C to B2B"}'
        mock_llm.invoke.return_value = mock_response

        state: AgentState = {
            "question": "Actually we are doing B2B.",
            "qa_answer": "Got it. That changes the market.",
            "analysis": json.dumps({
                "chain_of_thought": ["Analyzing B2C startup"],
                "idea_fit": "Good",
                "competitors": "B2C players",
                "opportunity": "Medium",
                "score": "6/10",
                "targeting": "B2C target",
                "next_step": "Validate"
            }),
            "idea": "B2C startup",
            "conversation_history": [],
            "trace": []
        }

        result = qa_check_refinement_needed_node(state, mock_llm)
        self.assertTrue(result["should_refine"])
        self.assertEqual(result["refinement_reason"], "Founder pivoted from B2C to B2B")

    def test_refinement_needed_gate_false(self):
        # Setup mock LLM that returns should_refine=False
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"should_refine": false, "reason": "Generic greeting"}'
        mock_llm.invoke.return_value = mock_response

        state: AgentState = {
            "question": "hello",
            "qa_answer": "Hi, how can I help you?",
            "analysis": "{}",
            "idea": "test",
            "conversation_history": [],
            "trace": []
        }

        result = qa_check_refinement_needed_node(state, mock_llm)
        self.assertFalse(result["should_refine"])

    def test_route_refinement(self):
        self.assertEqual(route_refinement({"should_refine": True}), "refine")
        self.assertEqual(route_refinement({"should_refine": False}), "skip")

    def test_refine_report_structured_output_success(self):
        mock_llm = MagicMock()
        # Setup structured output mock
        mock_structured_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured_llm
        
        mock_schema_instance = FeasibilityReportSchema(
            chain_of_thought=["Refined to B2B model"],
            idea_fit="Excellent B2B Fit",
            competitors="B2B competitors",
            opportunity="Large enterprise market",
            score="8/10",
            targeting="Enterprise procurement teams",
            next_step="Talk to 5 CTOs"
        )
        mock_structured_llm.invoke.return_value = mock_schema_instance

        state: AgentState = {
            "question": "Actually we are doing B2B.",
            "qa_answer": "Got it. That changes the market.",
            "analysis": "{}",
            "idea": "B2B startup",
            "conversation_history": [],
            "trace": []
        }

        result = qa_refine_report_node(state, mock_llm)
        refined_report = json.loads(result["analysis"])
        self.assertEqual(refined_report["score"], "8/10")
        self.assertEqual(refined_report["idea_fit"], "Excellent B2B Fit")

    def test_refine_report_fallback_text_success(self):
        mock_llm = MagicMock()
        # Make with_structured_output fail to test fallback path
        mock_llm.with_structured_output.side_effect = Exception("Not supported")
        
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "chain_of_thought": ["Refined to B2B model via fallback"],
            "idea_fit": "B2B Fallback Fit",
            "competitors": "B2B competitors",
            "opportunity": "Large enterprise market",
            "score": "9/10",
            "targeting": "Enterprise procurement teams",
            "next_step": "Talk to 5 CTOs"
        })
        mock_llm.invoke.return_value = mock_response

        state: AgentState = {
            "question": "Actually we are doing B2B.",
            "qa_answer": "Got it. That changes the market.",
            "analysis": "{}",
            "idea": "B2B startup",
            "conversation_history": [],
            "trace": []
        }

        result = qa_refine_report_node(state, mock_llm)
        refined_report = json.loads(result["analysis"])
        self.assertEqual(refined_report["score"], "9/10")
        self.assertEqual(refined_report["idea_fit"], "B2B Fallback Fit")

if __name__ == "__main__":
    unittest.main()
