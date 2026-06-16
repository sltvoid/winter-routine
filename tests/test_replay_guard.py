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
    """Iteration 2 (adversarial review): when same-day rows exist, the default is
    to COMPLETE the gaps live (gated llm writes + live idempotent Stage 4). The
    no-write diagnostic is now reachable only via the explicit
    --diagnostic-on-existing flag."""

    def _summary(self, rows, *, allow_full_replay=False, diagnostic_on_existing=False):
        return replay_guard._summary(
            today=TODAY,
            pipeline_id="P",
            matching_rows=rows,
            allow_full_replay=allow_full_replay,
            diagnostic_on_existing=diagnostic_on_existing,
        )

    def test_complete_missing_calendar(self):
        # rows exist + calendar_write missing, no explicit diagnostic -> complete_missing.
        rows = [
            _row("daily_briefing", id="1", output_date=TODAY),
            _row("rt_yesterday", id="2", output_date=YESTERDAY),
            _row("email_daily", id="3", output_date=YESTERDAY),
        ]
        s = self._summary(rows)
        self.assertEqual(s["action"], "complete_missing")
        self.assertEqual(s["status"], "ok")
        self.assertEqual(s["missing_run_types"], ["calendar_write"])
        self.assertEqual(
            set(s["present_run_types"]), {"rt_yesterday", "email_daily", "daily_briefing"}
        )

    def test_explicit_diagnostic_overrides_complete(self):
        # The explicit --diagnostic-on-existing flag = no-write inspection, even with gaps.
        rows = [_row("daily_briefing", id="1", output_date=TODAY)]
        s = self._summary(rows, diagnostic_on_existing=True)
        self.assertEqual(s["action"], "diagnostic_replay")

    def test_all_present_completes_to_heal_memory(self):
        # The literal §1 incident: all llm + narrative present but the Stage 4 memory
        # is invisible to the guard. Default -> complete_missing with EMPTY
        # missing_run_types, so no llm row is rewritten but Stage 4 runs live.
        rows = [
            _row("daily_briefing", id="1", output_date=TODAY),
            _row("rt_yesterday", id="2", output_date=YESTERDAY),
            _row("email_daily", id="3", output_date=YESTERDAY),
            _row("calendar_write", id="4", output_date=TODAY),
            _row("agent_runs", id="5", goal="Morning briefing pipeline for 2026-06-15"),
        ]
        s = self._summary(rows)
        self.assertEqual(s["action"], "complete_missing")
        self.assertEqual(s["status"], "ok")
        self.assertEqual(s["missing_run_types"], [])

    def test_briefing_missing_completes(self):
        # R3: rt/email present, briefing missing -> complete_missing (gate skips the
        # present rt/email; the missing briefing is written). NOT a no-write stop.
        rows = [
            _row("rt_yesterday", id="2", output_date=YESTERDAY),
            _row("email_daily", id="3", output_date=YESTERDAY),
        ]
        s = self._summary(rows)
        self.assertEqual(s["action"], "complete_missing")
        self.assertEqual(s["status"], "ok")
        self.assertIn("daily_briefing", s["missing_run_types"])


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
