import json
import unittest

from core.config import Settings
from core.json_utils import parse_json_from_text
from pipeline.feasibility_parser import normalize_feasibility_report_json, parse_feasibility_report


class JsonUtilsTests(unittest.TestCase):
    def test_parse_json_from_text_handles_leading_prose(self):
        parsed = parse_json_from_text(
            'Sure! Here is the result:\n{"intent": "chat", "valid": true}',
            expected_type=dict,
        )

        self.assertEqual(parsed["intent"], "chat")
        self.assertTrue(parsed["valid"])

    def test_parse_json_from_text_handles_common_json_mistakes(self):
        parsed = parse_json_from_text(
            "{ intent: 'chat', valid: true, }",
            expected_type=dict,
        )

        self.assertEqual(parsed["intent"], "chat")
        self.assertTrue(parsed["valid"])

    def test_feasibility_report_normalization_recovers_malformed_json(self):
        raw = """```json
        {
          idea_fit: 'Strong demand signal',
          competitors: 'Several existing tools',
          opportunity: 'Niche workflow gap',
          score: '75/100',
          targeting: 'SMB operators',
          next_step: 'Interview five users',
          chain_of_thought: 'Step 1: Review market data',
        }
        ```"""

        report = parse_feasibility_report(raw)
        normalized = json.loads(normalize_feasibility_report_json(raw))

        self.assertEqual(report["score"], "75/100")
        self.assertEqual(report["chain_of_thought"], ["Step 1: Review market data"])
        self.assertEqual(normalized["targeting"], "SMB operators")

    def test_allowed_origins_csv_parsing(self):
        settings = Settings(
            ALLOWED_ORIGINS="http://localhost:3000, https://example.com",
            _env_file=None,
        )

        self.assertEqual(
            settings.allowed_origins,
            ["http://localhost:3000", "https://example.com"],
        )


if __name__ == "__main__":
    unittest.main()
