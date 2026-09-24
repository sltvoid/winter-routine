import argparse
import json
import tempfile
import unittest
from pathlib import Path

from scripts import calendar_plan

BRIEFING = {
    "date": "2026-09-24",
    "schedule_blocks": [
        {"time_range": "7:00 PM - 8:00 PM", "activity": "Dojo rep", "category": "project"},
        {"time_range": "8:00 PM - 9:00 PM", "activity": "Wind down", "category": "wind_down"},
    ],
}


def _args(tmp: Path, busy: dict) -> argparse.Namespace:
    (tmp / "briefing.json").write_text(json.dumps(BRIEFING))
    (tmp / "busy.json").write_text(json.dumps(busy))
    return argparse.Namespace(
        briefing=str(tmp / "briefing.json"), busy=str(tmp / "busy.json"),
        calendar_id="cal@group.calendar.google.com", timezone="America/Toronto",
        date=None, start_hour=7, end_hour=22, publish_categories=None,
        skip_started=False, now=None,
    )


class CalendarPlanStatusTests(unittest.TestCase):
    def test_token_budget_skip_is_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _, summary, _ = calendar_plan.build_plan(_args(Path(d), {
                "status": "skipped_for_token_budget", "busy_windows": [], "busy_window_count": 0}))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["busy_source"], "skipped_for_token_budget")
        self.assertEqual(summary["candidate_count"], 2)

    def test_real_busy_failure_still_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _, summary, _ = calendar_plan.build_plan(_args(Path(d), {"status": "error", "busy_windows": []}))
        self.assertEqual(summary["status"], "busy_source_failed")
        self.assertEqual(summary["busy_source"], "failed")

    def test_search_ok_keeps_search_source(self):
        with tempfile.TemporaryDirectory() as d:
            _, summary, _ = calendar_plan.build_plan(_args(Path(d), {"status": "ok", "busy_windows": []}))
        self.assertEqual((summary["status"], summary["busy_source"]), ("ok", "search"))


if __name__ == "__main__":
    unittest.main()
