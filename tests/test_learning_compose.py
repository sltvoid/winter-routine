import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LearningComposeTests(unittest.TestCase):
    def _run_compose(self, ctx: dict, diff: dict):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ctx_path = tmp / "ctx.json"
            diff_path = tmp / "diff.json"
            out_path = tmp / "new_sections.json"
            ctx_path.write_text(json.dumps(ctx))
            diff_path.write_text(json.dumps(diff))

            env = os.environ.copy()
            env.update(
                {
                    "LEARNING_CTX_PATH": str(ctx_path),
                    "LEARNING_DIFF_PATH": str(diff_path),
                    "LEARNING_OUTPUT_PATH": str(out_path),
                }
            )
            result = subprocess.run(
                ["python3", "scripts/learning_compose.py"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            output = json.loads(out_path.read_text()) if out_path.exists() else None
            return result, output

    def test_freeform_profile_section_upserts_learner_traits_without_dropping_existing_fields(self):
        ctx = {
            "current_profile": {
                "sections": {
                    "work_patterns": {
                        "summary": "Old summary",
                        "artifact_conversion_bottleneck": "Existing freeform note",
                    }
                }
            }
        }
        diff = {
            "section_updates": {
                "work_patterns": {
                    "summary": "New summary",
                    "traits_added": [
                        {
                            "trait": "Windows uncapped low focus",
                            "confidence": 0.82,
                            "evidence": ["weekly_trend:3248"],
                        }
                    ],
                    "traits_updated": [
                        {
                            "trait": "Artifact conversion bottleneck",
                            "status": "active",
                            "evidence_note": "Latest weekly trend revalidated it.",
                            "new_confidence": 0.9,
                            "new_last_validated": "2026-06-02",
                        }
                    ],
                    "traits_removed": [
                        {
                            "trait": "Old stale pattern",
                            "reason": "Contradicted by the last two trends.",
                        }
                    ],
                }
            }
        }

        result, output = self._run_compose(ctx, diff)

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        section = output["work_patterns"]
        self.assertEqual(section["summary"], "New summary")
        self.assertEqual(section["artifact_conversion_bottleneck"], "Existing freeform note")
        traits = {t["trait"]: t for t in section["traits"]}
        self.assertEqual(traits["Artifact conversion bottleneck"]["confidence"], 0.9)
        self.assertEqual(traits["Artifact conversion bottleneck"]["status"], "active")
        self.assertEqual(traits["Windows uncapped low focus"]["confidence"], 0.82)
        self.assertEqual(section["learner_removed_traits"][0]["trait"], "Old stale pattern")

    def test_structured_profile_section_still_rejects_missing_update_target(self):
        ctx = {
            "current_profile": {
                "sections": {
                    "work_patterns": {
                        "summary": "Existing structured section",
                        "traits": [{"trait": "Known trait", "confidence": 0.8}],
                    }
                }
            }
        }
        diff = {
            "section_updates": {
                "work_patterns": {
                    "traits_updated": [{"trait": "Missing trait", "new_confidence": 0.9}]
                }
            }
        }

        result, output = self._run_compose(ctx, diff)

        self.assertEqual(result.returncode, 3)
        self.assertIsNone(output)
        self.assertIn("traits_updated target 'Missing trait' not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
