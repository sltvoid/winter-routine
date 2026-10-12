# tests/test_api_prompt.py
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "morning-briefing.api-prompt.md"


class ApiPromptTest(unittest.TestCase):
    def test_prompt_exists_and_carries_no_key_literal(self):
        text = PROMPT.read_text()
        # The only legal spelling of the key in this file is the variable reference.
        self.assertNotRegex(text, r"MCP_API_KEY='[^$']")
        self.assertNotRegex(text, r"MCP_API_KEY=\"[^$\"]")
        self.assertNotIn("cat > /tmp/mcp.env", text)

    def test_prompt_keeps_the_runbook_handoff_and_env_contract(self):
        text = PROMPT.read_text()
        self.assertIn("source /tmp/mcp.env", text)
        self.assertIn("Read morning-briefing.md in this workspace and execute every stage in order.", text)
        self.assertIn("Do not export MODEL.", text)
        self.assertIn("winter-routine-runner", text)

    def test_prompt_is_not_gitignored(self):
        proc = subprocess.run(["git", "check-ignore", "-q", str(PROMPT)], cwd=ROOT)
        self.assertEqual(proc.returncode, 1, "api prompt must be tracked; the /claude-routine-*.md glob must not match it")


if __name__ == "__main__":
    unittest.main()
