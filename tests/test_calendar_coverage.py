import json
import tempfile
import unittest
from pathlib import Path

from scripts import calendar_coverage


class CalendarCoverageTests(unittest.TestCase):
    def _write(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload))

    def test_all_matching_blocks_present_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            briefing = tmpdir / "briefing.json"
            search = tmpdir / "briefing_search.json"
            self._write(
                briefing,
                {
                    "date": "2026-05-29",
                    "schedule_blocks": [
                        {
                            "time_range": "9:00 AM - 10:00 AM",
                            "activity": "Ship one repo change",
                            "category": "project",
                        },
                        {
                            "time_range": "10:00 AM - 11:00 AM",
                            "activity": "Admin triage",
                            "category": "admin",
                        },
                    ],
                },
            )
            self._write(
                search,
                {
                    "events": [
                        {
                            "summary": "Ship one repo change",
                            "start": "2026-05-29T09:00:00-04:00",
                            "end": "2026-05-29T10:00:00-04:00",
                        },
                        {
                            "summary": "Admin triage",
                            "start": "2026-05-29T10:00:00-04:00",
                            "end": "2026-05-29T11:00:00-04:00",
                        },
                    ]
                },
            )

            summary, create_args = calendar_coverage.build_coverage(
                briefing_path=briefing,
                briefing_search_path=search,
            )

        self.assertEqual(summary["status"], "noop")
        self.assertEqual(summary["valid_block_count"], 2)
        self.assertEqual(summary["already_present"], 2)
        self.assertEqual(summary["missing"], 0)
        self.assertEqual(create_args, [])

    def test_missing_blocks_emit_create_args_without_duplicate_present_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            briefing = tmpdir / "briefing.json"
            search = tmpdir / "briefing_search.json"
            self._write(
                briefing,
                {
                    "date": "2026-05-29",
                    "schedule_blocks": [
                        {
                            "time_range": "9:00 AM - 10:00 AM",
                            "activity": "Ship one repo change",
                            "category": "project",
                        },
                        {
                            "time_range": "10:00 AM - 11:00 AM",
                            "activity": "Admin triage",
                            "category": "admin",
                        },
                    ],
                },
            )
            self._write(
                search,
                {
                    "events": [
                        {
                            "summary": "Ship one repo change",
                            "start": "2026-05-29T09:00:00-04:00",
                            "end": "2026-05-29T10:00:00-04:00",
                        }
                    ]
                },
            )

            summary, create_args = calendar_coverage.build_coverage(
                briefing_path=briefing,
                briefing_search_path=search,
            )

        self.assertEqual(summary["status"], "missing")
        self.assertEqual(summary["already_present"], 1)
        self.assertEqual(summary["missing"], 1)
        self.assertEqual(create_args[0]["title"], "Admin triage")
        self.assertEqual(create_args[0]["start_time"], "2026-05-29T10:00:00-04:00")
        self.assertEqual(create_args[0]["self_attendance"], "omit")
        self.assertEqual(create_args[0]["attendees"], [])
        self.assertFalse(create_args[0]["add_google_meet"])

    def test_skip_started_omits_past_windows_from_late_watchdog_creates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            briefing = tmpdir / "briefing.json"
            search = tmpdir / "briefing_search.json"
            self._write(
                briefing,
                {
                    "date": "2026-05-29",
                    "schedule_blocks": [
                        {
                            "time_range": "9:00 AM - 10:00 AM",
                            "activity": "Already started block",
                            "category": "project",
                        },
                        {
                            "time_range": "10:00 AM - 11:00 AM",
                            "activity": "Future block",
                            "category": "project",
                        },
                    ],
                },
            )
            self._write(search, {"events": []})

            summary, create_args = calendar_coverage.build_coverage(
                briefing_path=briefing,
                briefing_search_path=search,
                skip_started=True,
                now="2026-05-29T09:30:00-04:00",
            )

        self.assertEqual(summary["status"], "missing")
        self.assertEqual(summary["valid_block_count"], 1)
        self.assertEqual(summary["missing"], 1)
        self.assertEqual(summary["past_or_started_skipped"], 1)
        self.assertEqual(create_args[0]["title"], "Future block")


if __name__ == "__main__":
    unittest.main()
