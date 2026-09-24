import unittest
from pathlib import Path


class ProgramReviewContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runbook = Path("program-review.md").read_text()
        cls.normalized = " ".join(cls.runbook.split())

    def test_rollup_freshness_line_after_stage_zero(self):
        self.assertIn("## Stage 0.5 — Rollup freshness line", self.runbook)
        self.assertIn("older than 24 h", self.normalized)
        self.assertIn("WARN: newest rollup is", self.runbook)

    def test_tickets_are_counted_by_live_status(self):
        # The Stage 0 SQL sits inside a single-quoted JSON arg, so literals are
        # written '"'"'x'"'"' — flatten that shell quoting before matching.
        flat = self.runbook.replace("'\"'\"'", "'")
        self.assertIn("('proposed','research_ready','research_complete','blocked') GROUP BY 1", flat)
        self.assertNotIn("'accepted'", flat)
        self.assertIn("N research_complete awaiting decision", self.normalized)

    def test_job_artifact_memory_channel(self):
        self.assertIn("job_artifact_%", self.runbook)
        self.assertIn("`job_artifact_<week_start>`", self.runbook)
        self.assertIn("category `fact`", self.normalized)
        self.assertIn("clock started", self.normalized)

    def test_job_artifact_week_start_ties_to_stage_zero_rep_weeks(self):
        # On the scheduled run, <week_start> is not a free choice — it must
        # equal the week the Stage 0 read already identified as current.
        self.assertIn(
            "on the scheduled run this equals `rep_weeks[0].week_start` from the Stage 0 read",
            self.normalized,
        )

    def test_reviewers_are_weekly_not_retired(self):
        self.assertNotIn("retired from the metered API", self.runbook)
        self.assertIn("run weekly (Mon/Wed/Fri, ADR 0009)", self.normalized)

    def test_shelf_line_from_the_scorecard(self):
        self.assertIn("input_payload.funnel.shelved", self.runbook)
        self.assertIn("Shelved decisions:", self.runbook)


if __name__ == "__main__":
    unittest.main()
