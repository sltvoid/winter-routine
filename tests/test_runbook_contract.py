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
        self.assertIn("Raw Google Calendar search responses must never be printed", self.runbook)
        self.assertIn("/tmp/calendar_search_primary.json", self.runbook)
        self.assertIn("only counts/status", self.runbook)

    def test_parallel_stage_env_handling_avoids_inline_secret_exports(self):
        self.assertIn("Do not inline `MCP_API_KEY`", self.runbook)
        self.assertIn("source /tmp/morning_briefing_dates.env", self.runbook)
        self.assertIn("scripts/anchor_env.sh", self.runbook)

    def test_active_goal_is_action_selection_authority(self):
        normalized = " ".join(self.runbook.split())
        self.assertIn("active goal policy is the action-selection authority", normalized)
        self.assertIn("Hero and rank-1 priority action must serve the active goal first", normalized)
        self.assertIn("Do not promote stale career, generic email, or inbox cleanup", normalized)


if __name__ == "__main__":
    unittest.main()
