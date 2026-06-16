import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class WriteRunHelperTests(unittest.TestCase):
    def test_write_run_dry_run_defaults_model_without_exported_model(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "payload.json"
            response_path = Path(tmpdir) / "response.json"
            payload_path.write_text(json.dumps({"mode": "test"}))

            env = os.environ.copy()
            env.pop("MODEL", None)
            env.update(
                {
                    "PIPELINE_ID": "test-pipeline",
                    "ROUTINE_MODE": "dry_run",
                    "ALLOW_WRITES": "0",
                }
            )

            result = subprocess.run(
                [
                    "bash",
                    "scripts/write_run.sh",
                    "rt_yesterday",
                    "stage1_rt",
                    str(payload_path),
                    str(response_path),
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        envelope = json.loads(result.stdout)
        self.assertEqual(envelope["arguments"]["model"], "routine-selected")

    def test_write_run_does_not_export_model(self):
        script = (REPO_ROOT / "scripts" / "write_run.sh").read_text()

        self.assertNotIn("export MODEL", script)

    def _run(self, run_type, *, env_extra=None, pop=()):  # noqa: D401
        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "payload.json"
            response_path = Path(tmpdir) / "response.json"
            payload_path.write_text(json.dumps({"mode": "test"}))
            env = os.environ.copy()
            for key in pop:
                env.pop(key, None)
            env.update({"PIPELINE_ID": "test-pipeline", "ROUTINE_MODE": "dry_run", "ALLOW_WRITES": "0"})
            env.update(env_extra or {})
            return subprocess.run(
                ["bash", "scripts/write_run.sh", run_type, "stage1_rt",
                 str(payload_path), str(response_path)],
                cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
            )

    def test_write_run_skips_run_type_not_in_missing(self):
        # complete_missing idempotency: a present row (not in MISSING_RUN_TYPES)
        # must be skipped without emitting a would-call envelope.
        result = self._run("rt_yesterday", env_extra={"MISSING_RUN_TYPES": "calendar_write"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertNotIn("would_call", result.stdout)
        self.assertIn("skip", (result.stderr + result.stdout).lower())

    def test_write_run_writes_run_type_in_missing(self):
        result = self._run("rt_yesterday", env_extra={"MISSING_RUN_TYPES": "rt_yesterday calendar_write"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("would_call", result.stdout)

    def test_write_run_no_gate_when_missing_unset(self):
        result = self._run("rt_yesterday", pop=("MISSING_RUN_TYPES",))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("would_call", result.stdout)

    def test_write_run_skips_all_when_missing_empty(self):
        # complete_missing with nothing missing: MISSING_RUN_TYPES is SET but empty,
        # so every llm write is skipped (Stage 4 still runs live, separately).
        result = self._run("rt_yesterday", env_extra={"MISSING_RUN_TYPES": ""})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertNotIn("would_call", result.stdout)
        self.assertIn("skip", (result.stderr + result.stdout).lower())

    def test_write_run_gate_is_mode_independent_skips_in_live(self):
        # The gate runs BEFORE the ALLOW_WRITES live guard: a present row is skipped
        # cleanly (rc=0) in live mode and never reaches the mcp write.
        result = self._run("rt_yesterday", env_extra={
            "MISSING_RUN_TYPES": "calendar_write", "ROUTINE_MODE": "live", "ALLOW_WRITES": "0"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("skip", (result.stderr + result.stdout).lower())

    def test_write_run_gate_passes_then_refuses_live_without_allow(self):
        # run_type IS missing -> gate passes -> live path refused for ALLOW_WRITES=0 (rc=3).
        result = self._run("rt_yesterday", env_extra={
            "MISSING_RUN_TYPES": "rt_yesterday", "ROUTINE_MODE": "live", "ALLOW_WRITES": "0"})
        self.assertEqual(result.returncode, 3, result.stderr + result.stdout)

    def test_write_run_substring_does_not_false_match(self):
        # "rt" must not match inside the "rt_yesterday" token.
        result = self._run("rt", env_extra={"MISSING_RUN_TYPES": "rt_yesterday"})
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertNotIn("would_call", result.stdout)
        self.assertIn("skip", (result.stderr + result.stdout).lower())

    def test_write_run_warns_when_today_et_empty(self):
        # Spec §3.5: warn (not fail) when TODAY_ET is unset so future rows carry today.
        result = self._run("rt_yesterday", pop=("TODAY_ET", "MISSING_RUN_TYPES"))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("today_et", result.stderr.lower())

    def _run_agent(self, *, env_extra=None, pop=()):
        with tempfile.TemporaryDirectory() as tmpdir:
            narrative = Path(tmpdir) / "narrative.txt"
            response = Path(tmpdir) / "response.json"
            narrative.write_text("Morning briefing narrative for testing.")
            env = os.environ.copy()
            for key in pop:
                env.pop(key, None)
            env.update({"PIPELINE_ID": "test-pipeline", "ROUTINE_MODE": "dry_run", "ALLOW_WRITES": "0"})
            env.update(env_extra or {})
            return subprocess.run(
                ["bash", "scripts/write_agent.sh",
                 "Morning briefing pipeline for 2026-06-15", str(narrative), str(response)],
                cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
            )

    def test_write_agent_skips_narrative_when_agent_runs_not_in_missing(self):
        # complete_missing: the narrative must be skipped (no dup) when the guard
        # says agent_runs is already present. Gate runs before validation/write.
        result = self._run_agent(env_extra={"MISSING_RUN_TYPES": "rt_yesterday"})
        combined = (result.stderr + result.stdout).lower()
        self.assertIn("skip", combined)
        self.assertNotIn("would_call", result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
