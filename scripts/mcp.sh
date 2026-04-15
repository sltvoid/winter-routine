#!/usr/bin/env bash
# Thin wrapper around MCP tool calls. Removes curl boilerplate from the runbook.
#
# Usage:
#   scripts/mcp.sh <tool_name> <json_body> [output_path]
#
# Examples:
#   scripts/mcp.sh list_tools '{}'
#   scripts/mcp.sh compute_daily_insights '{"date":"2026-04-14"}' /tmp/insights.json
#   scripts/mcp.sh write_llm_run "@/tmp/rt_run.json"   # @file.json = read body from file
#
# If output_path is omitted, the response is written to stdout.
# If json_body starts with '@', the remainder is treated as a path to read.
#
# Requires: MCP_BASE_URL, MCP_API_KEY in the environment.
set -euo pipefail

if [ "${MCP_BASE_URL:-}" = "" ] || [ "${MCP_API_KEY:-}" = "" ]; then
  echo "mcp.sh: MCP_BASE_URL and MCP_API_KEY must be set" >&2
  exit 2
fi

tool="${1:?tool name required}"
body="${2:-}"
[ -z "$body" ] && body='{}'
out="${3:-}"

# Allow @path syntax to read body from file
if [[ "$body" == @* ]]; then
  body_path="${body#@}"
  body="$(cat "$body_path")"
fi

# Dispatch: list_tools is the one endpoint that isn't under /tools/
if [ "$tool" = "list_tools" ]; then
  url="$MCP_BASE_URL/api/mcp/list_tools"
else
  url="$MCP_BASE_URL/api/mcp/tools/$tool"
fi

if [ -n "$out" ]; then
  curl -s -X POST "$url" \
    -H 'Content-Type: application/json' \
    -H "X-API-Key: $MCP_API_KEY" \
    -d "$body" \
    -o "$out"
else
  curl -s -X POST "$url" \
    -H 'Content-Type: application/json' \
    -H "X-API-Key: $MCP_API_KEY" \
    -d "$body"
fi
