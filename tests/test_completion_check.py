import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import completion_check


TODAY = "2026-06-15"
YESTERDAY = "2026-06-14"


def _row(run_type, *, id="1", pipeline_id="P", output_date=None, input_today=None, goal=None):
    return {
        "id": id,
        "run_type": run_type,
        "pipeline_id": pipeline_id,
        "output_date": output_date,
        "input_today": input_today,
        "briefing_date": None,
        "goal": goal,
    }


def _full_set():
    return [
        _row("daily_briefing", id="1", output_date=TODAY),
        _row("rt_yesterday", id="2", output_date=YESTERDAY),
        _row("email_daily", id="3", output_date=YESTERDAY),
        _row("calendar_write", id="4", output_date=TODAY),
        _row("agent_runs", id="5", goal="Morning briefing pipeline for 2026-06-15"),
    ]


class CompletionCheckTests(unittest.TestCase):
    def test_completion_check_ok(self):
        result = completion_check._evaluate(_full_set(), TODAY, YESTERDAY)
        self.assertTrue(result["complete"])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["duplicate_run_types"], [])

    def test_completion_check_flags_duplicates(self):
        # AC4: regression guard against the 3664/3665 dup situation.
        rows = _full_set() + [_row("rt_yesterday", id="99", output_date=YESTERDAY)]
        result = completion_check._evaluate(rows, TODAY, YESTERDAY)
        self.assertIn("rt_yesterday", result["duplicate_run_types"])
        self.assertFalse(result["complete"])

    def test_completion_check_flags_missing(self):
        rows = [r for r in _full_set() if r["run_type"] != "calendar_write"]
        result = completion_check._evaluate(rows, TODAY, YESTERDAY)
        self.assertIn("calendar_write", result["missing"])
        self.assertFalse(result["complete"])

    def test_main_writes_output_and_returns_zero_when_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            existing = tmpdir / "existing.json"
            out = tmpdir / "out.json"
            existing.write_text(json.dumps({"status": "ok", "data": _full_set()}))
            argv = [
                "completion_check.py",
                "--existing-runs", str(existing),
                "--today-et", TODAY,
                "--yesterday-et", YESTERDAY,
                "--out", str(out),
            ]
            buf = io.StringIO()
            with redirect_stdout(buf), patch.object(sys, "argv", argv):
                rc = completion_check.main()
            payload = json.loads(out.read_text())
        self.assertEqual(rc, 0)
        self.assertTrue(payload["complete"])
        self.assertIn("completion: ok", buf.getvalue())

    def test_main_returns_nonzero_on_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            existing = tmpdir / "existing.json"
            out = tmpdir / "out.json"
            rows = _full_set() + [_row("email_daily", id="98", output_date=YESTERDAY)]
            existing.write_text(json.dumps({"status": "ok", "data": rows}))
            argv = [
                "completion_check.py",
                "--existing-runs", str(existing),
                "--today-et", TODAY,
                "--yesterday-et", YESTERDAY,
                "--out", str(out),
            ]
            buf = io.StringIO()
            with redirect_stdout(buf), patch.object(sys, "argv", argv):
                rc = completion_check.main()
        self.assertNotEqual(rc, 0)
        self.assertIn("duplicates", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
