"""Write-helper status gate (2026-10-14).

The platform's MCP HTTP route answers HTTP 200 with {"status": "error"} when it
rejects a write, so the helpers must read the body, not the transport: exit 4 =
rejected and nothing stored (fix and call once more), exit 5 = outcome unknown.
In dry_run, write_run.sh also asks the platform's read-only validate_payload for
the daily_briefing so a dry run sees what a live write would.
"""

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_STUB = r'''#!/usr/bin/env bash
echo "$1" >> "$STUB_CALLS"
body="$2"; if [[ "$body" == @* ]]; then body="$(cat "${body#@}")"; fi
printf '%s\n' "${body:0:200}" >> "$STUB_CALLS.bodies"
out="${3:-}"
if [ -n "${STUB_EXIT:-}" ]; then exit "$STUB_EXIT"; fi
if [ "$1" = "validate_payload" ]; then
  resp="$STUB_VALIDATE_RESPONSE"
else
  resp="$STUB_RESPONSE"
fi
if [ -n "$out" ]; then printf '%s' "$resp" > "$out"; else printf '%s' "$resp"; fi
'''


class _Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        scripts = self.tmp / "scripts"
        scripts.mkdir()
        for name in ("write_run.sh", "write_agent.sh", "validate_payloads.py", "mode_ceiling.sh"):
            shutil.copy(REPO_ROOT / "scripts" / name, scripts / name)
        stub = scripts / "mcp.sh"
        stub.write_text(_STUB)
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        self.calls = self.tmp / "calls.txt"
        self.calls.write_text("")
        self.payload = self.tmp / "payload.json"
        self.payload.write_text(json.dumps({"mode": "test"}))
        self.response = self.tmp / "response.json"

    def env(self, **extra):
        env = os.environ.copy()
        for key in ("MCP_BASE_URL", "MCP_API_KEY", "MISSING_RUN_TYPES", "DRY_RUN", "STUB_EXIT",
                    "ROUTINE_SERVER_VALIDATE", "ROUTINE_MODE", "ALLOW_WRITES"):
            env.pop(key, None)
        env.update({
            "MCP_ENV_FILE": str(self.tmp / "no-mcp.env"),   # hermetic: never the machine's /tmp/mcp.env
            "PIPELINE_ID": "test-pipeline",
            "STUB_CALLS": str(self.calls),
            "STUB_RESPONSE": json.dumps({"status": "ok", "data": {"id": 4242}}),
            "STUB_VALIDATE_RESPONSE": json.dumps({"status": "ok", "valid": True, "errors": []}),
        })
        env.update(extra)
        return env

    def run_write(self, run_type, **env_extra):
        return subprocess.run(
            ["bash", str(self.tmp / "scripts" / "write_run.sh"), run_type, "stage_x",
             str(self.payload), str(self.response)],
            cwd=self.tmp, env=self.env(**env_extra), text=True, capture_output=True, check=False)


class LiveGateTests(_Harness):
    LIVE = {"ROUTINE_MODE": "live", "ALLOW_WRITES": "1", "MCP_BASE_URL": "http://stub", "MCP_API_KEY": "k"}

    def test_ok_prints_the_row_id(self):
        r = self.run_write("rt_yesterday", **self.LIVE)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "4242")

    def test_platform_rejection_exits_4_with_the_reason(self):
        r = self.run_write("daily_briefing", **self.LIVE, STUB_RESPONSE=json.dumps(
            {"status": "error", "error": "daily_briefing schema validation failed: rep/title is too long", "data": None}))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("REJECTED", r.stderr)
        self.assertIn("rep/title is too long", r.stderr)
        self.assertEqual(r.stdout.strip(), "")   # never prints `null` as if it were an id

    def test_failed_insert_is_outcome_unknown_not_a_rejection(self):
        # a COMMIT whose ack was lost reports "Failed to insert" after the row is durable
        r = self.run_write("rt_yesterday", **self.LIVE, STUB_RESPONSE=json.dumps(
            {"status": "error", "error": "Failed to insert: server closed the connection unexpectedly"}))
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn("OUTCOME UNKNOWN", r.stderr)

    def test_pre_send_refusal_is_not_sent_and_propagates(self):
        for code in ("2", "3"):
            r = self.run_write("rt_yesterday", **self.LIVE, STUB_EXIT=code)
            self.assertEqual(r.returncode, int(code), r.stdout + r.stderr)
            self.assertIn("NOT SENT", r.stderr)
            self.assertNotIn("OUTCOME UNKNOWN", r.stderr)

    def test_auth_failure_body_is_outcome_unknown(self):
        r = self.run_write("rt_yesterday", **self.LIVE, STUB_RESPONSE=json.dumps({"detail": "Invalid or missing MCP API key"}))
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn("OUTCOME UNKNOWN", r.stderr)

    def test_transport_failure_is_outcome_unknown(self):
        r = self.run_write("rt_yesterday", **self.LIVE, STUB_EXIT="7")
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn("mcp.sh exit 7", r.stderr)

    def test_ok_without_an_id_is_outcome_unknown(self):
        r = self.run_write("rt_yesterday", **self.LIVE, STUB_RESPONSE=json.dumps({"status": "ok", "data": {}}))
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)


class DryRunServerValidationTests(_Harness):
    DRY = {"ROUTINE_MODE": "dry_run", "ALLOW_WRITES": "0", "MCP_BASE_URL": "http://stub", "MCP_API_KEY": "k"}

    def test_platform_rejection_fails_the_dry_run(self):
        r = self.run_write("daily_briefing", **self.DRY, STUB_VALIDATE_RESPONSE=json.dumps(
            {"status": "error", "valid": False, "errors": ["daily_briefing validation failed at rep/title: too long"]}))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("would REJECT", r.stderr)
        self.assertIn("rep/title", r.stderr)
        self.assertNotIn("would_call", r.stdout)
        self.assertEqual(self.calls.read_text().split(), ["validate_payload"])

    def test_platform_accepts_and_the_envelope_is_printed(self):
        r = self.run_write("daily_briefing", **self.DRY)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["would_call"], "write_llm_run")
        self.assertEqual(self.calls.read_text().split(), ["validate_payload"])

    def test_unreachable_platform_only_warns(self):
        r = self.run_write("daily_briefing", **self.DRY, STUB_EXIT="7")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("UNVERIFIED", r.stderr)
        self.assertEqual(json.loads(r.stdout)["would_call"], "write_llm_run")

    def test_unexpected_answer_is_loudly_unverified(self):
        for body in ({"detail": "Invalid or missing MCP API key"}, "<html>502 Bad Gateway</html>"):
            r = self.run_write("daily_briefing", **self.DRY,
                               STUB_VALIDATE_RESPONSE=body if isinstance(body, str) else json.dumps(body))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("UNVERIFIED", r.stderr)
            self.assertEqual(json.loads(r.stdout)["would_call"], "write_llm_run")

    def test_env_is_read_from_the_env_file_when_the_shell_lacks_it(self):
        envfile = self.tmp / "mcp.env"
        envfile.write_text("export MCP_BASE_URL='http://stub'\nexport MCP_API_KEY='k'\nexport ROUTINE_MODE='dry_run'\nexport ALLOW_WRITES='0'\n")
        r = self.run_write("daily_briefing", ROUTINE_MODE="dry_run", ALLOW_WRITES="0", MCP_ENV_FILE=str(envfile),
                           STUB_VALIDATE_RESPONSE=json.dumps({"status": "error", "errors": ["rep/title too long"]}))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertEqual(self.calls.read_text().split(), ["validate_payload"])

    def test_a_live_env_file_never_leaks_into_a_dry_run(self):
        # the platform check sources MCP_ENV_FILE in a subshell: a file that says live
        # must not flip the helper to live after the check (no POST, envelope printed)
        envfile = self.tmp / "mcp.env"
        envfile.write_text("export MCP_BASE_URL='http://stub'\nexport MCP_API_KEY='k'\nexport ROUTINE_MODE='live'\nexport ALLOW_WRITES='1'\n")
        r = self.run_write("daily_briefing", ROUTINE_MODE="dry_run", ALLOW_WRITES="0", MCP_ENV_FILE=str(envfile))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["would_call"], "write_llm_run")
        self.assertEqual(self.calls.read_text().split(), ["validate_payload"])   # the check, never a write

    def test_platform_check_sends_the_briefing_as_a_json_string(self):
        self.run_write("daily_briefing", **self.DRY)
        sent = json.loads((self.tmp / "calls.txt.bodies").read_text().strip().splitlines()[0] + "")
        self.assertEqual(sent["payload_type"], "daily_briefing")
        self.assertIsInstance(sent["payload"], str)
        self.assertEqual(json.loads(sent["payload"]), {"mode": "test"})

    def test_missing_env_and_file_says_skipped(self):
        r = self.run_write("daily_briefing", ROUTINE_MODE="dry_run", ALLOW_WRITES="0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("SKIPPED", r.stderr)

    def test_other_run_types_are_not_sent(self):
        r = self.run_write("rt_yesterday", **self.DRY)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls.read_text().strip(), "")

    def test_offline_and_opt_out_skip_the_call(self):
        offline = {k: v for k, v in self.DRY.items() if not k.startswith("MCP_")}
        self.assertEqual(self.run_write("daily_briefing", **offline).returncode, 0)   # no env, no file
        self.assertEqual(self.run_write("daily_briefing", **self.DRY, ROUTINE_SERVER_VALIDATE="0").returncode, 0)
        self.assertEqual(self.calls.read_text().strip(), "")


class ModeCeilingTests(_Harness):
    """A dry_run pin in the env file caps every helper, whatever was exported."""

    def _pin(self, mode):
        envfile = self.tmp / "mcp.env"
        envfile.write_text(f"export MCP_BASE_URL='http://stub'\nexport MCP_API_KEY='k'\nexport ROUTINE_MODE='{mode}'\nexport ALLOW_WRITES='{'1' if mode == 'live' else '0'}'\n")
        return str(envfile)

    def test_dry_run_pin_beats_an_exported_live(self):
        r = self.run_write("rt_yesterday", ROUTINE_MODE="live", ALLOW_WRITES="1", MCP_BASE_URL="http://stub",
                           MCP_API_KEY="k", MCP_ENV_FILE=self._pin("dry_run"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("mode ceiling", r.stderr)
        self.assertEqual(json.loads(r.stdout)["would_call"], "write_llm_run")
        self.assertEqual(self.calls.read_text().strip(), "")          # nothing was POSTed

    def test_live_pin_leaves_the_exported_mode_alone(self):
        r = self.run_write("rt_yesterday", ROUTINE_MODE="live", ALLOW_WRITES="1", MCP_BASE_URL="http://stub",
                           MCP_API_KEY="k", MCP_ENV_FILE=self._pin("live"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "4242")
        self.assertNotIn("mode ceiling", r.stderr)

    def test_template_without_a_mode_line_changes_nothing(self):
        envfile = self.tmp / "mcp.env"
        envfile.write_text("export MCP_BASE_URL='http://stub'\nexport MCP_API_KEY='k'\n")
        r = self.run_write("rt_yesterday", ROUTINE_MODE="live", ALLOW_WRITES="1", MCP_BASE_URL="http://stub",
                           MCP_API_KEY="k", MCP_ENV_FILE=str(envfile))
        self.assertEqual(r.stdout.strip(), "4242", r.stderr)

    def test_pin_caps_write_agent_too(self):
        narrative = self.tmp / "n.txt"
        narrative.write_text("Morning: one rep at 19:00.\n")
        env = self.env(ROUTINE_MODE="live", ALLOW_WRITES="1", MCP_BASE_URL="http://stub", MCP_API_KEY="k",
                       AGENT_KIND="deep_learner", MCP_ENV_FILE=self._pin("dry_run"))
        r = subprocess.run(["bash", str(self.tmp / "scripts" / "write_agent.sh"), "goal", str(narrative), str(self.response)],
                           cwd=self.tmp, env=env, text=True, capture_output=True, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["would_call"], "write_agent_run")
        self.assertEqual(self.calls.read_text().strip(), "")


class RealMcpShCeilingTests(unittest.TestCase):
    """The real scripts/mcp.sh: the pin refuses a write tool before any HTTP."""

    def _run(self, pin):
        with tempfile.TemporaryDirectory() as tmp:
            envfile = Path(tmp) / "mcp.env"
            envfile.write_text(f"export ROUTINE_MODE='{pin}'\n")
            env = os.environ.copy()
            env.update({"MCP_BASE_URL": "http://127.0.0.1:9", "MCP_API_KEY": "k", "ROUTINE_MODE": "live",
                        "ALLOW_WRITES": "1", "MCP_ENV_FILE": str(envfile), "NO_PROXY": "*", "no_proxy": "*"})
            for key in ("MCP_SSH_HOST", "MCP_CURL_RESOLVE", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
                env.pop(key, None)
            return subprocess.run(["bash", str(REPO_ROOT / "scripts" / "mcp.sh"), "save_memory", "{}", str(Path(tmp) / "out.json")],
                                  env=env, text=True, capture_output=True, check=False, timeout=60)

    def test_dry_run_pin_refuses_the_write_tool(self):
        r = self._run("dry_run")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("mode ceiling", r.stderr)
        self.assertIn("REFUSED write tool 'save_memory'", r.stderr)

    def test_live_pin_reaches_the_transport(self):
        r = self._run("live")
        self.assertNotEqual(r.returncode, 3, r.stderr)          # passed the gate; port 9 refuses the connection
        self.assertIn("HTTP call failed", r.stderr)


class AgentGateTests(_Harness):
    def run_agent(self, **env_extra):
        narrative = self.tmp / "narrative.txt"
        narrative.write_text("Morning: one 15-minute grep rep at 19:00, then the gym.\n")
        env = self.env(ROUTINE_MODE="live", ALLOW_WRITES="1", MCP_BASE_URL="http://stub", MCP_API_KEY="k",
                       AGENT_KIND="deep_learner", **env_extra)
        return subprocess.run(["bash", str(self.tmp / "scripts" / "write_agent.sh"), "Morning briefing pipeline for test",
                               str(narrative), str(self.response)],
                              cwd=self.tmp, env=env, text=True, capture_output=True, check=False)

    def test_ok_prints_the_row_id(self):
        r = self.run_agent()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "4242")

    def test_rejection_exits_4(self):
        r = self.run_agent(STUB_RESPONSE=json.dumps({"status": "error", "error": "goal is required"}))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("goal is required", r.stderr)

    def test_failed_insert_is_outcome_unknown(self):
        r = self.run_agent(STUB_RESPONSE=json.dumps({"status": "error", "error": "Failed to insert: server closed the connection unexpectedly"}))
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)


def _calendar_block():
    runbook = (REPO_ROOT / "morning-briefing.md").read_text()
    i = runbook.index("/tmp/write_calendar_write_body.json")
    start = runbook.rfind("```bash", 0, i) + len("```bash\n")
    end = runbook.index("```", start)
    return runbook[start:end]


class CalendarWriteBlockTests(unittest.TestCase):
    """Run the runbook's Stage 3.5 write block itself (not just grep it)."""

    def _run(self, mode, allow, stub_response=None, missing=None):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "scripts").mkdir()
        stub = tmp / "scripts" / "mcp.sh"
        stub.write_text(_STUB)
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        calls = tmp / "calls.txt"; calls.write_text("")
        script = tmp / "block.sh"
        script.write_text("set -eo pipefail\n" + _calendar_block() + "\necho \"ID=$CALENDAR_WRITE_ID\"\n")
        env = {"PATH": os.environ["PATH"], "HOME": str(tmp), "STUB_CALLS": str(calls),
               "STUB_RESPONSE": stub_response or json.dumps({"status": "ok", "data": {"id": 77}}),
               "STUB_VALIDATE_RESPONSE": "{}", "ROUTINE_MODE": mode, "ALLOW_WRITES": allow,
               "TODAY_ET": "2026-10-15", "PIPELINE_ID": "p-cal", "EVENTS_WRITTEN": "0", "SKIPPED": "1",
               "CONFLICT_SKIPPED": "0", "TARGET_VERIFIED": "skipped_manifest_only", "PRIMARY_COPIES": "0",
               "BUSY_SOURCE": "skipped_for_token_budget", "BUSY_WINDOW_COUNT": "0", "WOULD_CREATE": "6"}
        if missing is not None:
            env["MISSING_RUN_TYPES"] = missing
        for f in ("/tmp/write_calendar_write_body.json", "/tmp/calendar_write.json"):
            try: os.remove(f)
            except FileNotFoundError: pass
        r = subprocess.run(["bash", str(script)], cwd=tmp, env=env, text=True, capture_output=True, check=False)
        return r, calls

    def test_dry_run_prints_an_envelope_and_calls_nothing(self):
        r, calls = self._run("dry_run", "0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"would_call": "write_llm_run"', r.stdout.replace('"would_call":"write_llm_run"', '"would_call": "write_llm_run"'))
        self.assertIn("ID=would_write", r.stdout)
        self.assertEqual(calls.read_text().strip(), "")
        body = json.load(open("/tmp/write_calendar_write_body.json"))
        self.assertEqual((body["run_type"], body["model"], body["step_label"], body["pipeline_id"]),
                         ("calendar_write", "none", "stage3_5_calendar", "p-cal"))
        self.assertEqual(json.loads(body["input_payload"]), {"date": "2026-10-15", "source": "routine",
                                                             "write_policy": "busy_window_search_create_only_no_update_no_delete"})
        manifest = json.loads(body["output_response"])
        self.assertEqual((manifest["mode"], manifest["would_create"], manifest["actual_calendar_creates"]), ("calendar_write", 6, 0))

    def test_live_writes_through_mcp_sh_and_reports_the_row_id(self):
        r, calls = self._run("live", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ID=77", r.stdout)
        self.assertEqual(calls.read_text().split(), ["write_llm_run"])

    def test_live_rejection_reports_not_stored(self):
        r, calls = self._run("live", "1", stub_response=json.dumps({"status": "error", "error": "boom"}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ID=\n", r.stdout + "\n")
        self.assertIn("NOT stored: boom", r.stderr)

    def test_complete_missing_without_calendar_write_skips(self):
        r, calls = self._run("live", "1", missing="agent_runs")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ID=present", r.stdout)
        self.assertEqual(calls.read_text().strip(), "")


class RunbookRuleTests(unittest.TestCase):
    def test_calendar_write_goes_through_mcp_sh_with_a_dry_run_branch(self):
        runbook = (REPO_ROOT / "morning-briefing.md").read_text()
        self.assertNotIn('curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/write_llm_run"', runbook)
        self.assertIn('scripts/mcp.sh write_llm_run "@/tmp/write_calendar_write_body.json" /tmp/calendar_write.json', runbook)
        self.assertIn('CALENDAR_WRITE_ID="would_write"', runbook)

    def test_stage_3c_lets_a_complete_missing_skip_proceed(self):
        runbook = (REPO_ROOT / "morning-briefing.md").read_text()
        self.assertIn("skip daily_briefing — already present", runbook)
        self.assertIn("Exit 0 = go on to 3d/3.5", runbook)

    def test_toolcard_agrees_with_the_exit_codes(self):
        card = (REPO_ROOT / "toolcards" / "daily.md").read_text()
        self.assertNotIn("never retry a write that may have reached the server", card)
        self.assertIn("**4** = the platform rejected the write", card)
        self.assertIn("`Failed to insert: …`", card)

    def test_runbook_and_prompt_explain_exit_4_and_5(self):
        runbook = " ".join((REPO_ROOT / "morning-briefing.md").read_text().split())
        prompt = " ".join((REPO_ROOT / "morning-briefing.api-prompt.md").read_text().split())
        for text in (runbook, prompt):
            self.assertIn("exit", text.lower())
            self.assertIn("stored nothing", text.replace("stored **nothing**", "stored nothing"))
        self.assertIn("call the helper **once more**", runbook)
        self.assertIn("Exit 5 means the outcome is unknown", prompt)


if __name__ == "__main__":
    unittest.main()
