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
  path="/api/mcp/list_tools"
else
  path="/api/mcp/tools/$tool"
fi
url="$MCP_BASE_URL$path"

is_write_tool=0
case "$tool" in
  save_memory|update_memory|expire_memory|write_llm_run|write_test_llm_run|write_agent_run|write_test_agent_run|update_profile)
    is_write_tool=1
    ;;
esac

curl_args=(-sS --connect-timeout 10)
remote_retry_args=""
if [ "$is_write_tool" = "0" ]; then
  curl_args+=(--retry 2 --retry-delay 2)
  remote_retry_args=" --retry 2 --retry-delay 2"
fi
if [ -n "${MCP_CURL_RESOLVE:-}" ]; then
  curl_args+=(--resolve "$MCP_CURL_RESOLVE")
fi

if [ -n "${MCP_SSH_HOST:-}" ]; then
  remote_base="${MCP_SSH_BASE_URL:-http://127.0.0.1:30007}"
  remote_url="$remote_base$path"
  remote_url_quoted="$(printf '%q' "$remote_url")"
  content_header_quoted="$(printf '%q' "Content-Type: application/json")"
  api_header_quoted="$(printf '%q' "X-API-Key: $MCP_API_KEY")"
  remote_cmd="curl -sS --connect-timeout 10${remote_retry_args} -X POST $remote_url_quoted -H $content_header_quoted -H $api_header_quoted --data-binary @-"
  ssh_args=(-o BatchMode=yes -o LogLevel=ERROR -o ConnectTimeout="${MCP_SSH_CONNECT_TIMEOUT:-10}" "$MCP_SSH_HOST")

  if [ -n "$out" ]; then
    printf '%s' "$body" | ssh "${ssh_args[@]}" "$remote_cmd" > "$out" || {
      code=$?
      echo "mcp.sh: SSH HTTP call failed for tool '$tool' via host '$MCP_SSH_HOST' with exit $code" >&2
      exit "$code"
    }
  else
    printf '%s' "$body" | ssh "${ssh_args[@]}" "$remote_cmd" || {
      code=$?
      echo "mcp.sh: SSH HTTP call failed for tool '$tool' via host '$MCP_SSH_HOST' with exit $code" >&2
      exit "$code"
    }
  fi
  exit 0
fi

if [ -n "$out" ]; then
  curl "${curl_args[@]}" -X POST "$url" \
    -H 'Content-Type: application/json' \
    -H "X-API-Key: $MCP_API_KEY" \
    -d "$body" \
    -o "$out" || {
    code=$?
    host="$(python3 - "$url" <<'PY'
import sys
from urllib.parse import urlparse

print(urlparse(sys.argv[1]).hostname or "unknown")
PY
)"
    echo "mcp.sh: HTTP call failed for tool '$tool' at host '$host' with curl exit $code" >&2
    exit "$code"
  }
else
  curl "${curl_args[@]}" -X POST "$url" \
    -H 'Content-Type: application/json' \
    -H "X-API-Key: $MCP_API_KEY" \
    -d "$body" || {
    code=$?
    host="$(python3 - "$url" <<'PY'
import sys
from urllib.parse import urlparse

print(urlparse(sys.argv[1]).hostname or "unknown")
PY
)"
    echo "mcp.sh: HTTP call failed for tool '$tool' at host '$host' with curl exit $code" >&2
    exit "$code"
  }
fi
