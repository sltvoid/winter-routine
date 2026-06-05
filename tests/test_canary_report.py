import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import canary_report


class CanaryReportCalendarVerificationTests(unittest.TestCase):
    def _write_json(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload))

    def _run_report(self, *, target_verified: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            data = tmpdir / "data.json"
            briefing = tmpdir / "briefing.json"
            agent = tmpdir / "agent.json"
            self._write_json(
                data,
                {
                    "analyzed_date": "2026-06-04",
                    "anom_headline": "Focus was steady",
                    "parity_headline": "Codex led YouTube",
                    "career_headline": "Career pipeline stalled",
                },
            )
            self._write_json(
                briefing,
                {
                    "date": "2026-06-05",
                    "stage0_headlines": {
                        "anomalies": "Focus was steady",
                        "parity": "Codex led YouTube",
                        "career": "Career pipeline stalled",
                    },
                    "schedule_blocks": [{}, {}, {}, {}, {}, {}],
                    "priority_actions": [{"action": "Ship"}],
                },
            )
            self._write_json(
                agent,
                {
                    "final_response": "Morning briefing.",
                    "tool_calls": json.dumps(
                        [{"classification": {"agent_kind": "morning_briefing"}}]
                    ),
                },
            )
            argv = [
                "canary_report.py",
                "--pipeline-id",
                "test-pipeline",
                "--mode",
                "dry_run",
                "--today-et",
                "2026-06-05",
                "--yesterday-et",
                "2026-06-04",
                "--calendar-events-written",
                "0",
                "--calendar-would-create",
                "8",
                "--calendar-busy-source",
                "skipped_for_token_budget",
                "--calendar-target-verified",
                target_verified,
                "--calendar-primary-copies",
                "0",
                "--data",
                str(data),
                "--briefing",
                str(briefing),
                "--agent-envelope",
                str(agent),
            ]
            output = io.StringIO()
            with patch("sys.argv", argv), redirect_stdout(output):
                code = canary_report.main()
            return code, output.getvalue()

    def test_dry_run_calendar_skip_cannot_claim_target_verified_yes(self):
        code, output = self._run_report(target_verified="yes")

        self.assertEqual(1, code)
        self.assertIn("overall_status=needs_review", output)
        self.assertIn("calendar target verification yes invalid for dry_run/skipped_for_token_budget", output)

    def test_dry_run_calendar_skip_accepts_skipped_manifest_only(self):
        code, output = self._run_report(target_verified="skipped_manifest_only")

        self.assertEqual(0, code)
        self.assertIn("overall_status=ok", output)
        self.assertIn("target_verified=skipped_manifest_only", output)


if __name__ == "__main__":
    unittest.main()
