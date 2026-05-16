import unittest

from fastapi import HTTPException

from api.input_validation import ensure_meaningful_text, is_meaningful_text


class InputValidationTests(unittest.TestCase):
    def test_rejects_symbol_only_input(self):
        for value in [".", '"', "-", "+", "   ", "!!!"]:
            self.assertFalse(is_meaningful_text(value))

        with self.assertRaises(HTTPException) as exc:
            ensure_meaningful_text(".")

        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(exc.exception.detail, "Please enter correct input.")

    def test_rejects_obvious_gibberish(self):
        for value in ["asdf", "qwerty", "abc", "aaaa", "asdasd", "hjkl"]:
            self.assertFalse(is_meaningful_text(value))

    def test_accepts_meaningful_idea_lab_text(self):
        valid_inputs = [
            "AI tutor for college students",
            "B2B invoicing tool for freelancers",
            "SMB hiring assistant",
            "Help parents track school fees",
        ]

        for value in valid_inputs:
            self.assertTrue(is_meaningful_text(value))
            self.assertEqual(ensure_meaningful_text(value), value)


if __name__ == "__main__":
    unittest.main()
