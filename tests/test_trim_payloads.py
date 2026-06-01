import unittest
from pathlib import Path


class TrimPayloadsContractTests(unittest.TestCase):
    def test_trim_script_warns_when_post_trim_files_stay_large(self):
        script = Path("scripts/trim_payloads.sh").read_text()

        self.assertIn("TRIM_WARN_BYTES", script)
        self.assertIn("wc -c", script)
        self.assertIn("trim_payloads.sh: WARNING", script)


if __name__ == "__main__":
    unittest.main()
