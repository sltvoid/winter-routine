#!/usr/bin/env bash
# Verify the HTTP MCP surface before a routine run.
# Does not print MCP_API_KEY.
set -euo pipefail

required_tools=(
  compute_daily_insights
  query_health
  query_raw_sql
  query_calendar
  recall_memory
  save_memory
  write_llm_run
  write_agent_run
)

if [ "${MCP_BASE_URL:-}" = "" ] || [ "${MCP_API_KEY:-}" = "" ]; then
  echo "smoke_test: MCP_BASE_URL and MCP_API_KEY must be set" >&2
  exit 2
fi

tmp="${1:-/tmp/mcp_list_tools.json}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$here/mcp.sh" list_tools '{}' "$tmp"

python3 - "$tmp" "${required_tools[@]}" <<'PY'
from __future__ import annotations

import json
import sys

path = sys.argv[1]
required = set(sys.argv[2:])
with open(path) as f:
    payload = json.load(f)

if payload.get("status") != "ok":
    print(f"smoke_test: list_tools status was {payload.get('status')!r}", file=sys.stderr)
    sys.exit(3)

data = payload.get("data")
if isinstance(data, dict):
    raw_tools = data.get("tools") or data.get("tool_names") or data.get("available_tools") or []
elif isinstance(data, list):
    raw_tools = data
else:
    raw_tools = payload.get("tools") or []

tools = set()
for item in raw_tools:
    if isinstance(item, str):
        tools.add(item)
    elif isinstance(item, dict):
        name = item.get("name") or item.get("tool") or item.get("id")
        if isinstance(name, str):
            tools.add(name)
        else:
            tools.update(k for k in item.keys() if isinstance(k, str))

missing = sorted(required - tools)
if missing:
    print("smoke_test: missing required tools: " + ", ".join(missing), file=sys.stderr)
    print("smoke_test: available tools: " + ", ".join(sorted(tools)), file=sys.stderr)
    sys.exit(4)

print(f"smoke_test: ok, {len(required)} required tools present")
PY
