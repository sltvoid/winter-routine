import json
import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class McpHelperTests(unittest.TestCase):
    def test_mcp_sh_treats_test_write_tools_as_non_retrying_write_tools(self):
        script = (REPO_ROOT / "scripts" / "mcp.sh").read_text()

        case_block = script.split('case "$tool" in', 1)[1].split("esac", 1)[0]

        self.assertIn("write_test_llm_run", case_block)
        self.assertIn("write_test_agent_run", case_block)

    def test_smoke_test_accepts_single_key_object_tool_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            fake_curl = tmp / "curl"
            payload = {
                "status": "ok",
                "tools": [
                    {"compute_daily_insights": {}},
                    {"query_health": {}},
                    {"query_raw_sql": {}},
                    {"query_calendar": {}},
                    {"recall_memory": {}},
                    {"save_memory": {}},
                    {"write_llm_run": {}},
                    {"write_agent_run": {}},
                ],
            }
            fake_curl.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env python3
                    import pathlib, sys
                    out = None
                    args = sys.argv[1:]
                    for idx, arg in enumerate(args):
                        if arg == "-o" and idx + 1 < len(args):
                            out = args[idx + 1]
                    text = {json.dumps(json.dumps(payload))}
                    if out:
                        pathlib.Path(out).write_text(text)
                    else:
                        print(text)
                    """
                )
            )
            fake_curl.chmod(fake_curl.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{tmp}:{env['PATH']}",
                    "MCP_BASE_URL": "https://example.test",
                    "MCP_API_KEY": "test-key",
                }
            )
            result = subprocess.run(
                ["bash", "scripts/smoke_test.sh", str(tmp / "tools.json")],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("smoke_test: ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
