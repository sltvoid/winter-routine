import json
import tempfile
import unittest
from pathlib import Path

from scripts import calendar_search_policy


class CalendarSearchPolicyTests(unittest.TestCase):
    def test_reauth_text_response_is_retryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            primary = tmpdir / "primary.json"
            briefing = tmpdir / "briefing.json"
            primary.write_text(json.dumps({"events": [], "next_page_token": None}))
            briefing.write_text(
                json.dumps(
                    [
                        {
                            "type": "text",
                            "text": "This app connection requires reauthentication before other actions on this app can succeed.",
                        }
                    ]
                )
            )

            summary = calendar_search_policy.summarize_search_pair(
                primary_path=primary,
                briefing_path=briefing,
            )

        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["failure_kind"], "auth")
        self.assertTrue(summary["retry_recommended"])
        self.assertEqual(summary["recommended_action"], "bounded_recheck_once")

    def test_both_searches_ok_are_not_retryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            primary = tmpdir / "primary.json"
            briefing = tmpdir / "briefing.json"
            primary.write_text(json.dumps({"events": [], "next_page_token": None}))
            briefing.write_text(
                json.dumps({"events": [{"id": "hidden", "start": "2026-05-29T11:00:00-04:00"}]})
            )

            summary = calendar_search_policy.summarize_search_pair(
                primary_path=primary,
                briefing_path=briefing,
            )

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["failure_kind"], "none")
        self.assertFalse(summary["retry_recommended"])
        self.assertEqual(summary["primary_event_count"], 0)
        self.assertEqual(summary["briefing_event_count"], 1)


if __name__ == "__main__":
    unittest.main()
