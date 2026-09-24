import unittest
from pathlib import Path


class TrimPayloadsContractTests(unittest.TestCase):
    def test_trim_script_warns_when_post_trim_files_stay_large(self):
        script = Path("scripts/trim_payloads.sh").read_text()

        self.assertIn("TRIM_WARN_BYTES", script)
        self.assertIn("wc -c", script)
        self.assertIn("trim_payloads.sh: WARNING", script)
        self.assertIn("browser_activity.json", script)

    def test_weekly_trend_trim_is_removed(self):
        # The weekly_trend read no longer exists (retired 2026-06-11); the
        # trim block and its warn_if_large call are dead weight.
        script = Path("scripts/trim_payloads.sh").read_text()
        self.assertNotIn("weekly_trend", script)


if __name__ == "__main__":
    unittest.main()
