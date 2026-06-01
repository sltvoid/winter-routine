#!/usr/bin/env bash
# Stage 0.5c — trim large MCP responses to the fields Stages 1-3 actually need.
#
# Why: extract.py only reads a narrow slice of each /tmp/*.json, but the AI
# re-reads calendar_blocks / agent_memory / weekly_trend directly as synthesis
# context in Stage 3b. Trimming cuts input tokens on that re-read.
#
# Each trim is best-effort — if jq fails or the schema doesn't match, the
# original file is left untouched. Never fatal.
set -u

PAYLOAD_DIR="${TRIM_PAYLOADS_DIR:-/tmp}"
TRIM_WARN_BYTES="${TRIM_WARN_BYTES:-51200}"

payload_path() {
  printf '%s/%s' "$PAYLOAD_DIR" "$1"
}

trim() {
  local file="$1"
  local filter="$2"
  [ -f "$file" ] || return 0
  local tmp="${file}.trim"
  if jq -c "$filter" "$file" > "$tmp" 2>/dev/null && [ -s "$tmp" ]; then
    mv "$tmp" "$file"
  else
    rm -f "$tmp"
  fi
}

warn_if_large() {
  local file="$1"
  [ -f "$file" ] || return 0
  local bytes
  bytes=$(wc -c < "$file" | tr -d '[:space:]')
  if [ "$bytes" -gt "$TRIM_WARN_BYTES" ]; then
    echo "trim_payloads.sh: WARNING $(basename "$file") is ${bytes} bytes after trim (>${TRIM_WARN_BYTES})" >&2
  fi
}

# calendar_blocks: keep only the fields synthesis needs to reason about
# today's existing events. Drops attendees, conferenceData, creator, etc.
trim "$(payload_path calendar_blocks.json)" \
  '{data: [((.data // []) | if type == "array" then . else [] end)[] | {summary, description, start, end}]}'

# agent_memory: keep only key/content/category/created_at. Drops embedding
# scores, snippets, and other retrieval metadata.
trim "$(payload_path agent_memory.json)" \
  '{data: [((.data // []) | if type == "array" then . else [] end)[] | {key, content, category, created_at}]}'

# active_goal_memory: same shape as agent_memory, but kept separate so briefing
# synthesis can distinguish durable goal context from broad recall context.
trim "$(payload_path active_goal_memory.json)" \
  '{data: [((.data // []) | if type == "array" then . else [] end)[] | {key, content, category, created_at}]}'

# active_goal_policy: keep only the policy fields that shape schedule synthesis.
trim "$(payload_path active_goal_policy.json)" \
  '{data: [((.data // []) | if type == "array" then . else [] end)[] | {id, status, valid_from, valid_until, goals, enforcement}]}'

# weekly_trend: output_response is a multi-KB JSON blob. Truncate to the
# first 1200 chars — enough to expose the headline/summary context without
# blowing the input budget.
trim "$(payload_path weekly_trend.json)" \
  '{data: [((.data // []) | if type == "array" then . else [] end)[] | {output_response: (.output_response // "" | .[0:1200])}]}'

warn_if_large "$(payload_path calendar_blocks.json)"
warn_if_large "$(payload_path agent_memory.json)"
warn_if_large "$(payload_path active_goal_memory.json)"
warn_if_large "$(payload_path active_goal_policy.json)"
warn_if_large "$(payload_path weekly_trend.json)"

echo "trim_payloads.sh: ok"
