import json
import unittest
from unittest.mock import patch

from core.config import settings
from pipeline.output_guardrails import (
    DEFAULT_CLARIFYING_QUESTION,
    REPORT_KEYS,
    guard_clarifying_question,
    guard_engagement_question,
    guard_feasibility_report,
    guard_markdown_answer,
    guard_qa_history,
    guard_stored_analysis,
    normalize_score,
    report_issues,
    sanitize_markdown,
)
from pipeline.qa_graph import qa_generate_answer_node
from pipeline.tools import cross_question_node, llm_agent_node


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
        return FakeResponse(response)


FULL_REPORT = {
    "chain_of_thought": ["Read the market data", "Read Reddit"],
    "idea_fit": "Strong fit for exam-season stress.",
    "competitors": "- **Notion**: generic planner",
    "opportunity": "Students want adaptive plans.",
    "score": "71/100",
    "score_rationale": "Real pain, crowded space.",
    "targeting": "Engineering students in India.",
    "next_step": "1. Interview 10 students",
}

MARKDOWN_REPORT = """Sure! Here's the feasibility analysis.

## Idea Fit
The idea *strongly* resonates with students.

## Competitors
| Name | Pricing | Weakness |
|------|---------|----------|
| Notion | $10/mo | Not AI-native |
| [Todoist](https://todoist.com) | Free | No coaching |

#### Opportunity
- Gap in **adaptive** planning
• Reddit users complain about `rigid` planners

**Score:** 72/100 - strong demand but crowded market and low willingness to pay

### Targeting:
1) Engineering students
2) MBA aspirants

Next Steps:
<ul><li>Interview 10 students</li><li>Build a landing page</li></ul>
"""


class ReportGuardrailTests(unittest.TestCase):
    def test_markdown_report_becomes_ui_json(self):
        report = json.loads(guard_feasibility_report(MARKDOWN_REPORT))

        self.assertEqual(tuple(report), REPORT_KEYS)
        self.assertEqual(report_issues(report), [])
        self.assertEqual(report["idea_fit"], "The idea strongly resonates with students.")
        self.assertEqual(
            report["competitors"],
            "- **Notion**: Pricing: $10/mo; Weakness: Not AI-native\n"
            "- **Todoist (https://todoist.com)**: Pricing: Free; Weakness: No coaching",
        )
        self.assertEqual(
            report["opportunity"],
            "- Gap in **adaptive** planning\n- Reddit users complain about rigid planners",
        )
        self.assertEqual(report["score"], "72/100")
        self.assertEqual(
            report["score_rationale"],
            "Strong demand but crowded market and low willingness to pay",
        )
        self.assertEqual(report["targeting"], "1. Engineering students\n2. MBA aspirants")
        self.assertIn("- Interview 10 students", report["next_step"])
        self.assertIn("- Build a landing page", report["next_step"])

    def test_aliased_keys_and_structured_values_are_normalized(self):
        raw = """```json
{"Chain of Thought": "Step 1: Look at facts\\nStep 2: Reddit pain points",
 "ideaFit": "## Idea Fit\\nGood fit",
 "competitors": [{"name": "Notion", "strength": "brand"}, {"name": "Motion", "weakness": "price"}],
 "market_opportunity": {"size": "$2B", "growth": "12% CAGR"},
 "feasibility_score": "7.5 out of 10. Rationale: crowded but differentiated enough to win.",
 "target_customers": "College students",
 "next_steps": ["Interview users", "Ship MVP"],
 "extra": "dropped"}
```"""
        report = json.loads(guard_feasibility_report(raw))

        self.assertEqual(tuple(report), REPORT_KEYS)
        self.assertEqual(report["chain_of_thought"], ["Look at facts", "Reddit pain points"])
        self.assertEqual(report["idea_fit"], "Good fit")
        self.assertEqual(report["competitors"], "- **Notion**: Strength: brand\n- **Motion**: Weakness: price")
        self.assertEqual(report["opportunity"], "- **Size**: $2B\n- **Growth**: 12% CAGR")
        self.assertEqual(report["score"], "75/100")
        self.assertEqual(report["score_rationale"], "Crowded but differentiated enough to win.")
        self.assertEqual(report["targeting"], "College students")
        self.assertEqual(report["next_step"], "- Interview users\n- Ship MVP")

    def test_raw_newlines_inside_json_strings_still_parse(self):
        raw = json.dumps(FULL_REPORT).replace(
            '"Strong fit for exam-season stress."', '"Strong fit\nfor exam-season stress."'
        )

        report = json.loads(guard_feasibility_report(raw))

        self.assertEqual(report["idea_fit"], "Strong fit\nfor exam-season stress.")
        self.assertEqual(report_issues(report), [])

    def test_truncated_json_is_salvaged_without_llm(self):
        raw = (
            '{"chain_of_thought": ["a"], "idea_fit": "Fits well", "competitors": "Notion, Motion", '
            '"opportunity": "Growing", "score": "68/100", "targeting": "Students", "next_step": "Interview 1'
        )

        report = json.loads(guard_feasibility_report(raw))

        self.assertEqual(report["idea_fit"], "Fits well")
        self.assertEqual(report["score"], "68/100")
        self.assertEqual(report["next_step"], "")

    def test_llm_repair_fills_gaps_without_overwriting_rule_output(self):
        raw = '{"idea_fit": "Original fit text", "competitors": "Notion", "opportunity": "Big", "targeting": "Students"}'
        llm = FakeLLM([json.dumps({**FULL_REPORT, "idea_fit": "LLM rewrote this"})])

        report = json.loads(guard_feasibility_report(raw, llm=llm))

        self.assertEqual(len(llm.prompts), 1)
        self.assertIn("'score' is missing or empty", llm.prompts[0])
        self.assertIn("'next_step' is missing or empty", llm.prompts[0])
        self.assertEqual(report["idea_fit"], "Original fit text")
        self.assertEqual(report["score"], "71/100")
        self.assertEqual(report["next_step"], "1. Interview 10 students")

    def test_llm_repair_is_skipped_for_valid_reports_and_when_disabled(self):
        llm = FakeLLM([])
        guard_feasibility_report(json.dumps(FULL_REPORT), llm=llm)
        self.assertEqual(llm.prompts, [])

        with patch.object(settings, "OUTPUT_GUARDRAIL_LLM_REPAIR_ENABLED", False):
            report = json.loads(guard_feasibility_report('{"idea_fit": "Only this"}', llm=llm))
        self.assertEqual(llm.prompts, [])
        self.assertEqual(report["idea_fit"], "Only this")

    def test_unparseable_output_still_renders_as_report(self):
        llm = FakeLLM([RuntimeError("provider down")])

        report = json.loads(guard_feasibility_report("I think this is a decent idea overall.", llm=llm))

        self.assertEqual(tuple(report), REPORT_KEYS)
        self.assertEqual(report["idea_fit"], "I think this is a decent idea overall.")

    def test_guard_is_idempotent(self):
        once = guard_feasibility_report(MARKDOWN_REPORT)
        self.assertEqual(guard_feasibility_report(once), once)

    def test_normalize_score(self):
        cases = {
            "75": "75/100",
            "75/100": "75/100",
            "7.5/10": "75/100",
            "Score: 82 out of 100": "82/100",
            "68%": "68/100",
            "**72/100**": "72/100",
            "140/100": "100/100",
            "Moderate (3 competitors)": "",
            "": "",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_score(raw)[0], expected)
        self.assertEqual(normalize_score(7.5)[0], "75/100")
        self.assertEqual(
            normalize_score("72. Strong demand from students and parents"),
            ("72/100", "Strong demand from students and parents"),
        )


class MarkdownGuardrailTests(unittest.TestCase):
    def test_sanitize_markdown_rewrites_unsupported_syntax(self):
        raw = (
            "#### Pricing\n"
            "* Use *tiered* pricing via [Stripe](https://stripe.com)\n"
            "+ Free tier with `limits`\n"
            "> Quote from Reddit\n"
            "___\n"
            "```python\nprint('x')\n```\n"
            "**Unclosed bold\n"
            "&amp; done<br>next"
        )

        self.assertEqual(
            sanitize_markdown(raw),
            "### Pricing\n"
            "- Use tiered pricing via Stripe (https://stripe.com)\n"
            "- Free tier with limits\n"
            "Quote from Reddit\n"
            "---\n"
            "print('x')\n"
            "Unclosed bold\n"
            "& done\n"
            "next",
        )

    def test_json_wrapped_answer_is_unwrapped(self):
        raw = '{"answer": "#### Pricing\\n* Use *tiered* pricing\\n+ Free tier"}'

        self.assertEqual(
            guard_markdown_answer(raw),
            "### Pricing\n- Use tiered pricing\n- Free tier",
        )

    def test_report_shaped_answer_becomes_markdown_sections(self):
        answer = guard_markdown_answer(json.dumps(FULL_REPORT))

        self.assertTrue(answer.startswith("**Score:** 71/100"))
        self.assertIn("### Competitors\n- **Notion**: generic planner", answer)

    def test_plain_answer_keeps_its_lead_in(self):
        answer = "Here's how you could price it: start with a free tier."

        self.assertEqual(guard_markdown_answer(answer), answer)


class QuestionGuardrailTests(unittest.TestCase):
    def test_clarifying_question_wrappers_are_removed(self):
        cases = {
            '"What is your pricing model?"': "What is your pricing model?",
            "Sure! Here is my clarifying question: **Who pays** for this?": "**Who pays** for this?",
            '```json\n{"question": "Who is your first customer?"}\n```': "Who is your first customer?",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(guard_clarifying_question(raw), expected)

    def test_clarifying_question_never_parses_as_json(self):
        self.assertEqual(guard_clarifying_question("42"), DEFAULT_CLARIFYING_QUESTION)
        self.assertEqual(guard_clarifying_question(""), DEFAULT_CLARIFYING_QUESTION)

    def test_multiple_questions_use_llm_rewrite(self):
        llm = FakeLLM(["Who would pay first, students or their parents?"])

        question = guard_clarifying_question("1. Who pays? 2. How much? 3. Why now?", llm=llm)

        self.assertEqual(question, "Who would pay first, students or their parents?")
        self.assertIn("it asks 3 questions instead of one", llm.prompts[0])

    def test_rules_fall_back_when_llm_rewrite_is_still_wrong(self):
        llm = FakeLLM(["Who pays? And when?"])

        question = guard_clarifying_question(
            "Your idea targets a crowded student market today. Who pays? How much? Why now?",
            llm=llm,
        )

        self.assertEqual(question, "Your idea targets a crowded student market today. Who pays?")

    def test_engagement_question_is_plain_single_question(self):
        self.assertEqual(
            guard_engagement_question('**Engagement Question:** "What would make your first 10 users come back daily?"'),
            "What would make your first 10 users come back daily?",
        )
        self.assertEqual(
            guard_engagement_question("Which beachhead segment will you target first? And how will you reach them?"),
            "Which beachhead segment will you target first?",
        )


class StoredAnalysisTests(unittest.TestCase):
    def test_old_markdown_report_is_upgraded_on_read(self):
        report = json.loads(guard_stored_analysis(MARKDOWN_REPORT, is_first_turn=False))

        self.assertEqual(report["score"], "72/100")

    def test_first_turn_question_stays_a_question(self):
        self.assertEqual(
            guard_stored_analysis('"Who is your first paying customer?"', is_first_turn=True),
            "Who is your first paying customer?",
        )

    def test_unrecognised_later_turn_is_left_alone(self):
        text = "Error in analysis"
        self.assertEqual(guard_stored_analysis(text, is_first_turn=False), text)


class GuardrailLoggingTests(unittest.TestCase):
    LOGGER = "pipeline.output_guardrails"

    def _single_line(self, logs) -> str:
        lines = [line for line in logs.output if "guardrail." in line]
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def test_valid_report_still_logs_ok(self):
        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            guard_feasibility_report(json.dumps(FULL_REPORT), conversation_id="conv-ok")

        line = self._single_line(logs)
        self.assertIn("INFO:pipeline.output_guardrails:guardrail.report status=ok conversation_id=conv-ok", line)
        self.assertIn("fixes=[] issues=[] remaining=[] llm_calls=0", line)
        self.assertIn("source=json", line)

    def test_rule_fixes_are_named(self):
        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            guard_feasibility_report(MARKDOWN_REPORT)

        line = self._single_line(logs)
        self.assertIn("status=rules_fixed", line)
        for fix in ("markdown_not_json", "score_normalized", "table", "html", "link", "italic"):
            self.assertIn(f'"{fix}"', line)

    def test_llm_repair_and_fallback_are_logged(self):
        raw = '{"idea_fit": "Original fit text", "competitors": "Notion", "opportunity": "Big", "targeting": "Students"}'
        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            guard_feasibility_report(raw, llm=FakeLLM([json.dumps(FULL_REPORT)]))
        self.assertIn("status=llm_repaired", self._single_line(logs))
        self.assertIn("llm_calls=1", self._single_line(logs))

        with self.assertLogs(self.LOGGER, level="WARNING") as logs:
            guard_feasibility_report("Plain text.", llm=FakeLLM([RuntimeError("down")]))
        self.assertTrue(any("WARNING" in line and "guardrail.report status=fallback" in line for line in logs.output))

    def test_question_and_answer_guards_log(self):
        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            guard_clarifying_question("Who pays?", conversation_id="conv-q")
            guard_engagement_question('**Question:** "Which exam will you launch around?"')
            guard_markdown_answer('{"answer": "| Plan | Price |\\n|---|---|\\n| Pro | $9 |"}', kind="qa_answer")
            guard_clarifying_question("42")

        lines = [line for line in logs.output if "guardrail." in line]
        self.assertIn("guardrail.clarifying_question status=ok conversation_id=conv-q", lines[0])
        self.assertIn("guardrail.engagement_question status=rules_fixed", lines[1])
        self.assertIn('"preamble"', lines[1])
        self.assertIn("guardrail.qa_answer status=rules_fixed", lines[2])
        self.assertIn('"json_wrapped"', lines[2])
        self.assertIn('"table"', lines[2])
        self.assertTrue(lines[3].startswith("WARNING:"))
        self.assertIn("guardrail.clarifying_question status=default_used", lines[3])

    def test_history_reads_log_one_line_each(self):
        history = [{"q": "a", "a": "Plain answer."}, {"q": "b", "a": "| Plan | Price |\n|---|---|\n| Pro | $9 |"}]
        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            cleaned = guard_qa_history(history, conversation_id="conv-h")
            guard_stored_analysis(json.dumps(FULL_REPORT), is_first_turn=False, conversation_id="conv-h")

        lines = [line for line in logs.output if "guardrail." in line]
        self.assertEqual(len(lines), 2)
        self.assertIn("guardrail.qa_history status=rules_fixed conversation_id=conv-h", lines[0])
        self.assertIn("items=2 changed=1", lines[0])
        self.assertIn("guardrail.stored_analysis status=ok", lines[1])
        self.assertEqual(cleaned[1]["a"], "- **Pro**: Price: $9")

    def test_logs_never_contain_user_text(self):
        secret = "ZEBRA-PRIVATE-PITCH"
        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            guard_feasibility_report(MARKDOWN_REPORT.replace("Notion", secret))
            guard_clarifying_question(f"Is {secret} your first customer? And second?")
            guard_markdown_answer(f"#### {secret}")

        self.assertFalse(any(secret in line for line in logs.output))

    def test_node_passes_conversation_id(self):
        with self.assertLogs(self.LOGGER, level="INFO") as logs:
            llm_agent_node(
                {
                    "idea": "AI planner",
                    "ideal_customer": "students",
                    "search_results": "evidence",
                    "conversation_id": "conv-node",
                },
                FakeLLM([json.dumps(FULL_REPORT)]),
            )

        self.assertIn("conversation_id=conv-node", self._single_line(logs))


class NodeIntegrationTests(unittest.TestCase):
    def test_llm_agent_node_returns_ui_report_from_markdown(self):
        llm = FakeLLM([MARKDOWN_REPORT])

        result = llm_agent_node(
            {"idea": "AI planner", "ideal_customer": "students", "search_results": "evidence"},
            llm,
        )

        report = json.loads(result["analysis"])
        self.assertEqual(report_issues(report), [])
        self.assertEqual(len(llm.prompts), 1)

    def test_cross_question_node_returns_single_question(self):
        llm = FakeLLM(["Here's a clarifying question: Who is your first paying customer?"])

        result = cross_question_node(
            {
                "idea": "AI planner",
                "problem_solved": "missed deadlines",
                "ideal_customer": "students",
                "conversation_history": [],
            },
            llm,
        )

        self.assertEqual(result["analysis"], "Who is your first paying customer?")

    def test_qa_answer_is_sanitized(self):
        llm = FakeLLM(["| Plan | Price |\n|---|---|\n| Free | $0 |\n| Pro | $9 |"])

        result = qa_generate_answer_node(
            {"question": "How should I price it?", "idea": "AI planner", "analysis": "{}", "trace": []},
            llm,
        )

        self.assertEqual(result["qa_answer"], "- **Free**: Price: $0\n- **Pro**: Price: $9")


if __name__ == "__main__":
    unittest.main()
