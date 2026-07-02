import unittest
from pathlib import Path


class RunbookContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runbook = Path("morning-briefing.md").read_text()

    def test_final_summary_has_fatal_and_recovered_error_fields(self):
        self.assertIn("fatal_errors", self.runbook)
        self.assertIn("recovered_errors", self.runbook)
        self.assertIn("scripts/run_log.sh summary", self.runbook)

    def test_calendar_search_output_must_be_file_only_and_redacted(self):
        # The full busy-window procedure moved to the cold-path reference file
        # (2026-07-02 token diet); the redaction contract lives there, and the
        # hot runbook must still carry the never-print rule + reference pointer.
        reference = Path("morning-briefing-reference.md").read_text()
        self.assertIn("Raw Google Calendar search responses must never be printed", reference)
        self.assertIn("/tmp/calendar_search_primary.json", reference)
        self.assertIn("only counts/status", reference)
        self.assertIn("raw Google Calendar responses are never printed", self.runbook)
        self.assertIn("morning-briefing-reference.md", self.runbook)

    def test_parallel_stage_env_handling_avoids_inline_secret_exports(self):
        self.assertIn("Do not inline `MCP_API_KEY`", self.runbook)
        self.assertIn("source /tmp/morning_briefing_dates.env", self.runbook)
        self.assertIn("scripts/anchor_env.sh", self.runbook)

    def test_active_goal_is_action_selection_authority(self):
        normalized = " ".join(self.runbook.split())
        self.assertIn("active goal policy is the action-selection authority", normalized)
        self.assertIn("Hero and rank-1 priority action must serve the active goal first", normalized)
        self.assertIn("Do not promote stale career, generic email, or inbox cleanup", normalized)

    def test_browser_activity_is_semantic_enrichment_not_extra_time(self):
        normalized = " ".join(self.runbook.split())
        self.assertIn("browser_activity_events", self.runbook)
        self.assertIn("Browser activity is **semantic enrichment**", self.runbook)
        self.assertIn("do not add browser minutes on top of", normalized)

    def test_device_magnitude_claims_must_use_device_split_over_headlines(self):
        normalized = " ".join(self.runbook.split())
        self.assertIn("device_split[*].total_hours` is **authoritative**", self.runbook)
        self.assertIn("do **not** reuse a Stage 0 device-share headline", normalized)
        self.assertIn('"Mac share 100%"', self.runbook)
        self.assertIn('"100% Mac screen time"', self.runbook)

    def test_manifest_only_calendar_does_not_claim_target_verified_yes(self):
        normalized = " ".join(self.runbook.split())
        self.assertIn("target_verified", self.runbook)
        self.assertIn("skipped_manifest_only", self.runbook)
        self.assertIn("must not be `yes` when `actual_calendar_creates=0`", normalized)

    def test_closed_career_suppresses_stage_four_career_memory(self):
        normalized = " ".join(self.runbook.split())
        self.assertIn("CAREER_MEMORY_SUPPRESSED", self.runbook)
        self.assertIn("Do not recall it, do not save it", normalized)
        self.assertIn("must not appear as saved or would-save", normalized)

    def test_output_calibration_rules_are_explicit(self):
        normalized = " ".join(self.runbook.split())
        self.assertIn("no deploy/CI evidence visible", self.runbook)
        self.assertIn("nothing shipped", self.runbook)
        self.assertIn("Do not recommend prep for future career/interview items", normalized)
        self.assertIn("--narrative /tmp/narrative.txt", self.runbook)
        self.assertIn("--briefing-context /tmp/briefing.json", self.runbook)
        self.assertIn("Do not duplicate generic", self.runbook)


class ClaudeContextContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = Path("CLAUDE.md").read_text()
        cls.gitignore = Path(".gitignore").read_text()
        cls.normalized = " ".join(cls.context.split())

    def test_claude_context_documents_endpoint_and_inline_key_constraint(self):
        # Phrasing follows the de-escalated CLAUDE.md (f0d174d); the contract
        # is unchanged: endpoint documented, no committed key, key is secret.
        self.assertIn("https://a8f2e1.steventa.me", self.context)
        self.assertIn("must never contain a committed literal MCP API key", self.context)
        self.assertIn("do not echo, print, log,", self.context)

    def test_claude_context_forbids_git_mutations_and_artifact_tracking(self):
        self.assertIn("must not `git add`", self.context)
        self.assertIn("`git commit`", self.context)
        self.assertIn("`git push`", self.context)
        self.assertIn("routine-artifacts/", self.gitignore)

    def test_claude_context_requires_calendar_handoff_validation(self):
        self.assertIn("--calendar-handoff", self.context)
        self.assertIn("1-3 distinct recommended blocks", self.context)
        self.assertIn("no deploy/CI evidence", self.context)


class CleanCanaryRunbookContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runbook = Path("morning-briefing-clean-canary.md").read_text()
        cls.normalized = " ".join(cls.runbook.split())

    def test_repository_freshness_preflight_has_fetch_failure_fallback(self):
        self.assertIn("git fetch origin main", self.runbook)
        self.assertIn("compare the existing local `origin/main` ref to `HEAD`", self.runbook)
        self.assertIn("remote freshness was not certified", self.runbook)
        self.assertIn("stop before Stage 0", self.runbook)


class LearningAgentRunbookContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runbook = Path("learning-agent.md").read_text()
        cls.normalized = " ".join(cls.runbook.split())

    def test_stage_one_reads_only_production_weekly_trend_and_prior_learner_rows(self):
        self.assertIn("COALESCE(run_scope, 'production') = 'production'", self.runbook)

    def test_output_discipline_forbids_printing_large_context_and_source_files(self):
        self.assertIn("Do not print `/tmp/ctx.json`", self.runbook)
        self.assertIn("Do not print source file contents", self.runbook)
        self.assertIn("Do not print full `/tmp/diff.json`", self.runbook)
        self.assertIn("Do not inspect helper scripts for write schemas during a routine run", self.normalized)
        self.assertIn("Do not open `api-catalog.md` after pre-flight", self.normalized)

    def test_test_mode_write_contract_is_inline_and_uses_test_tools_only(self):
        self.assertIn("`write_test_llm_run` and `write_test_agent_run` mirror the production request shape", self.normalized)
        self.assertIn("Never use `scripts/write_run.sh` or `scripts/write_agent.sh` in `TEST_RUN=1`", self.normalized)
        self.assertIn("validate_payloads.py --agent-envelope", self.normalized)

    def test_live_profile_section_names_are_authoritative(self):
        self.assertIn("Use the live profile section keys from `/tmp/ctx.json` as the source of truth", self.normalized)
        self.assertIn("health_patterns", self.runbook)
        self.assertNotIn("health_correlations`, `career_patterns`, `communication_style`", self.runbook)

    def test_audit_plan_requires_formula_source_claim_and_tolerance(self):
        for field in ("claim_id", "source_table", "formula", "claimed_value", "tolerance_pct"):
            self.assertIn(f'"{field}"', self.runbook)

    def test_compose_gate_precedes_memory_mutation_in_stage_five(self):
        compose_idx = self.runbook.index("### 5a. Compose profile preview")
        expire_idx = self.runbook.index("### 5c. Soft-expire stale memories")
        save_idx = self.runbook.index("### 5d. Save or update active memories")

        self.assertLess(compose_idx, expire_idx)
        self.assertLess(compose_idx, save_idx)
        self.assertIn("Before any production write", self.normalized)


class CalendarWatchdogRunbookContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runbook = Path("morning-briefing-calendar-watchdog.md").read_text()
        cls.normalized = " ".join(cls.runbook.split())

    def test_manifest_only_rows_are_repairable_and_late_windows_are_skipped(self):
        self.assertIn("target_verified=skipped_manifest_only", self.runbook)
        self.assertIn("busy_source=calendar_search_skipped_for_token_budget", self.runbook)
        self.assertIn("--skip-started", self.runbook)
        self.assertIn("past_or_started", self.runbook)

    def test_long_work_blocks_are_schedulable_capacity(self):
        self.assertIn("Work Container Rule", self.runbook)
        self.assertIn("schedulable work capacity", self.runbook)
        self.assertIn("Do not skip or block a project/deep-work briefing event solely", self.runbook)

    def test_watchdog_uses_busy_derivation_before_conflict_aware_planning(self):
        self.assertIn("calendar_busy_from_search.py", self.runbook)
        self.assertIn("--busy /tmp/calendar_busy.json", self.runbook)
        self.assertIn("Do not create events from", self.runbook)
        self.assertIn("coverage evidence only", self.normalized)


if __name__ == "__main__":
    unittest.main()
