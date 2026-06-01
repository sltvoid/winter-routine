import json
import os
import subprocess
import tempfile
import unittest


class RunLogTests(unittest.TestCase):
    def test_run_log_records_recovered_and_fatal_errors_for_summary(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            log_path = tmp.name
        env = {**os.environ, "RUN_LOG_PATH": log_path}

        subprocess.run(
            ["bash", "scripts/run_log.sh", "recovered", "Stage 0.5", "env lost and rerun succeeded"],
            check=True,
            env=env,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["bash", "scripts/run_log.sh", "fatal", "Stage 3.5", "calendar search failed"],
            check=True,
            env=env,
            capture_output=True,
            text=True,
        )
        summary = subprocess.run(
            ["bash", "scripts/run_log.sh", "summary"],
            check=True,
            env=env,
            capture_output=True,
            text=True,
        )

        payload = json.loads(summary.stdout)
        self.assertEqual(payload["recovered_errors"], ["Stage 0.5: env lost and rerun succeeded"])
        self.assertEqual(payload["fatal_errors"], ["Stage 3.5: calendar search failed"])


if __name__ == "__main__":
    unittest.main()
