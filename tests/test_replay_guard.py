import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import replay_guard


TODAY = "2026-06-15"
YESTERDAY = "2026-06-14"


def _row(run_type, *, id="1", pipeline_id=None, output_date=None, input_today=None,
         briefing_date=None, goal=None, **extra):
    row = {
        "id": id,
        "run_type": run_type,
        "pipeline_id": pipeline_id,
        "output_date": output_date,
        "input_today": input_today,
        "briefing_date": briefing_date,
        "goal": goal,
    }
    row.update(extra)
    return row


class SelectSameDayTests(unittest.TestCase):
    """Phase 1 (spec §3.2): detection must include rt_yesterday/email_daily
    siblings of today's run even when they carry only the analyzed (yesterday)
    date and an empty input_today."""

    def test_detects_sibling_by_pipeline(self):
        # AC1: a same-day daily_briefing (output_date=today) shares pipeline P
        # with rt/email rows whose output_date=yesterday and input_today empty.
        rows = [
            _row("daily_briefing", id="1", pipeline_id="P", output_date=TODAY, input_today=TODAY),
            _row("rt_yesterday", id="2", pipeline_id="P", output_date=YESTERDAY, input_today=""),
            _row("email_daily", id="3", pipeline_id="P", output_date=YESTERDAY, input_today=""),
        ]
        selected = replay_guard._select_same_day(rows, TODAY, YESTERDAY)
        ids = {r["id"] for r in selected}
        self.assertEqual(ids, {"1", "2", "3"})

    def test_detects_rt_email_by_analyzed_date(self):
        # AC1: rt/email rows carrying output_date=yesterday are same-day even
        # with no daily_briefing / no matching pipeline.
        rows = [
            _row("rt_yesterday", id="2", pipeline_id="Q", output_date=YESTERDAY, input_today=""),
            _row("email_daily", id="3", pipeline_id="Q", output_date=YESTERDAY, input_today=""),
        ]
        selected = replay_guard._select_same_day(rows, TODAY, YESTERDAY)
        ids = {r["id"] for r in selected}
        self.assertEqual(ids, {"2", "3"})

    def test_does_not_match_unrelated_prior_day(self):
        # An rt_yesterday whose analyzed date is an OLDER day (not our yesterday)
        # and which shares no today-pipeline must not be selected.
        rows = [
            _row("rt_yesterday", id="9", pipeline_id="Z", output_date="2026-06-10", input_today=""),
        ]
        selected = replay_guard._select_same_day(rows, TODAY, YESTERDAY)
        self.assertEqual(selected, [])


class CompleteMissingTests(unittest.TestCase):
    """Phase 2 (spec §3.3): a same-day daily_briefing with missing siblings
    completes only the missing artifacts instead of a no-write diagnostic."""

    def _summary(self, rows, *, allow_full_replay=False, diagnostic_on_existing=False):
        return replay_guard._summary(
            today=TODAY,
            pipeline_id="P",
            matching_rows=rows,
            allow_full_replay=allow_full_replay,
            diagnostic_on_existing=diagnostic_on_existing,
        )

    def test_complete_missing_calendar(self):
        # AC2: briefing + rt + email present, calendar_write missing -> complete_missing,
        # and it must win even when --diagnostic-on-existing is set (the incident case).
        rows = [
            _row("daily_briefing", id="1", output_date=TODAY),
            _row("rt_yesterday", id="2", output_date=YESTERDAY),
            _row("email_daily", id="3", output_date=YESTERDAY),
        ]
        s = self._summary(rows, diagnostic_on_existing=True)
        self.assertEqual(s["action"], "complete_missing")
        self.assertEqual(s["status"], "ok")
        self.assertEqual(s["missing_run_types"], ["calendar_write"])
        self.assertEqual(
            set(s["present_run_types"]), {"rt_yesterday", "email_daily", "daily_briefing"}
        )

    def test_complete_nothing_missing_diagnostic(self):
        # AC3: all four present (+ verified calendar) under --diagnostic -> diagnostic_replay.
        rows = [
            _row("daily_briefing", id="1", output_date=TODAY),
            _row("rt_yesterday", id="2", output_date=YESTERDAY),
            _row("email_daily", id="3", output_date=YESTERDAY),
            _row("calendar_write", id="4", output_date=TODAY, target_verified="yes", primary_copies="0"),
        ]
        s = self._summary(rows, diagnostic_on_existing=True)
        self.assertEqual(s["action"], "diagnostic_replay")
        self.assertEqual(s["missing_run_types"], [])

    def test_complete_nothing_missing_no_flag_stops(self):
        # AC3 else-branch: all present, no flag -> same_day_rows_exist (stop), unchanged.
        rows = [
            _row("daily_briefing", id="1", output_date=TODAY),
            _row("rt_yesterday", id="2", output_date=YESTERDAY),
            _row("email_daily", id="3", output_date=YESTERDAY),
            _row("calendar_write", id="4", output_date=TODAY, target_verified="yes", primary_copies="0"),
        ]
        s = self._summary(rows, diagnostic_on_existing=False)
        self.assertEqual(s["action"], "same_day_rows_exist")
        self.assertEqual(s["status"], "stop")


class MainWiringTests(unittest.TestCase):
    def _run_main(self, rows, *, today=TODAY, yesterday=YESTERDAY, extra_args=()):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            existing = tmpdir / "existing.json"
            out = tmpdir / "out.json"
            existing.write_text(json.dumps({"status": "ok", "data": rows}))
            argv = [
                "replay_guard.py",
                "--existing-runs", str(existing),
                "--today-et", today,
                "--yesterday-et", yesterday,
                "--pipeline-id", "P",
                "--out", str(out),
                *extra_args,
            ]
            buf = io.StringIO()
            with redirect_stdout(buf), patch.object(sys, "argv", argv):
                rc = replay_guard.main()
            return rc, json.loads(out.read_text())

    def test_main_detects_siblings_end_to_end(self):
        # AC1 end-to-end: --yesterday-et is accepted and the broadened selection
        # surfaces the rt/email siblings that carry only the analyzed date.
        rows = [
            _row("daily_briefing", id="1", pipeline_id="P", output_date=TODAY, input_today=TODAY),
            _row("rt_yesterday", id="2", pipeline_id="P", output_date=YESTERDAY, input_today=""),
            _row("email_daily", id="3", pipeline_id="P", output_date=YESTERDAY, input_today=""),
        ]
        _, summary = self._run_main(rows)
        self.assertIn("rt_yesterday", summary["existing_run_types"])
        self.assertIn("email_daily", summary["existing_run_types"])
        self.assertIn("daily_briefing", summary["existing_run_types"])


if __name__ == "__main__":
    unittest.main()
