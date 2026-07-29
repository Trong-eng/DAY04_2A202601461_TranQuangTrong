from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chat import run_model_tool_loop


class FailingProvider:
    def complete(self, *args, **kwargs):
        raise AssertionError("provider should not be called for preflight clarification")


class ChatPreflightTests(unittest.TestCase):
    def test_missing_article_url_uses_clarify_tool(self) -> None:
        result = run_model_tool_loop(
            provider=FailingProvider(),
            messages=[{"role": "user", "content": "Tóm tắt bài này giúp mình"}],
            tools=[],
            model=None,
            max_tool_rounds=4,
        )

        self.assertEqual(result["status"], "waiting_for_user")
        self.assertIn("URL", result["assistant_text"])
        self.assertEqual(result["rounds"][0]["tool_calls"][0]["name"], "clarify")
        self.assertEqual(result["rounds"][0]["tool_calls"][0]["args"]["response_type"], "text")


if __name__ == "__main__":
    unittest.main()
