import asyncio
import unittest

from fastapi import HTTPException

from api.routes import get_feasibility_score


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, result):
        self._result = result

    def query(self, *_args, **_kwargs):
        return _FakeQuery(self._result)


class ScoreEndpointTests(unittest.TestCase):
    def test_get_feasibility_score_returns_score_column_value(self):
        fake_report = type("Report", (), {"score": "88/100"})()
        fake_db = _FakeSession(fake_report)

        result = asyncio.run(get_feasibility_score("conv-123", fake_db))

        self.assertEqual(result.conversation_id, "conv-123")
        self.assertEqual(result.score, "88/100")

    def test_get_feasibility_score_raises_404_when_missing(self):
        fake_db = _FakeSession(None)

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(get_feasibility_score("missing-conv", fake_db))

        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
