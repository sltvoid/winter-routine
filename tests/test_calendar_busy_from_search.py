import json
import tempfile
import unittest
from pathlib import Path

from scripts import calendar_busy_from_search


class CalendarBusyFromSearchTests(unittest.TestCase):
    def _write(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload))

    def test_primary_hard_events_block_but_work_container_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            primary = tmpdir / "primary.json"
            briefing = tmpdir / "briefing.json"
            self._write(
                primary,
                {
                    "events": [
                        {
                            "summary": "Work",
                            "start": "2026-06-05T09:00:00-04:00",
                            "end": "2026-06-05T17:00:00-04:00",
                        },
                        {
                            "summary": "Doctor appointment",
                            "start": "2026-06-05T13:00:00-04:00",
                            "end": "2026-06-05T13:30:00-04:00",
                        },
                        {
                            "summary": "FYI hold",
                            "start": "2026-06-05T18:00:00-04:00",
                            "end": "2026-06-05T19:00:00-04:00",
                            "transparency": "transparent",
                        },
                    ]
                },
            )
            self._write(briefing, {"events": []})

            summary = calendar_busy_from_search.build_busy_summary(
                primary_path=primary,
                briefing_path=briefing,
            )

        self.assertEqual(summary["busy_window_count"], 1)
        self.assertEqual(summary["primary_busy_count"], 1)
        self.assertEqual(summary["work_container_skipped"], 1)
        self.assertEqual(summary["transparent_primary_skipped"], 1)
        self.assertEqual(summary["busy_windows"][0]["start"], "2026-06-05T13:00:00-04:00")

    def test_briefing_events_always_block_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            primary = tmpdir / "primary.json"
            briefing = tmpdir / "briefing.json"
            self._write(primary, {"events": []})
            self._write(
                briefing,
                {
                    "events": [
                        {
                            "summary": "Project block",
                            "start": "2026-06-05T14:00:00-04:00",
                            "end": "2026-06-05T15:00:00-04:00",
                        }
                    ]
                },
            )

            summary = calendar_busy_from_search.build_busy_summary(
                primary_path=primary,
                briefing_path=briefing,
            )

        self.assertEqual(summary["busy_window_count"], 1)
        self.assertEqual(summary["briefing_busy_count"], 1)
        self.assertEqual(
            summary["busy_windows"][0]["calendar_id"],
            calendar_busy_from_search.DEFAULT_BRIEFING_CALENDAR_ID,
        )


if __name__ == "__main__":
    unittest.main()
