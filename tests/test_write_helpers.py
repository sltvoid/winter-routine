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


if __name__ == "__main__":
    unittest.main()
