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

# calendar_blocks: keep only the fields synthesis needs to reason about
# today's existing events. Drops attendees, conferenceData, creator, etc.
trim /tmp/calendar_blocks.json \
  '{data: [((.data // []) | if type == "array" then . else [] end)[] | {summary, description, start, end}]}'

# agent_memory: keep only key/content/category/created_at. Drops embedding
# scores, snippets, and other retrieval metadata.
trim /tmp/agent_memory.json \
  '{data: [((.data // []) | if type == "array" then . else [] end)[] | {key, content, category, created_at}]}'

# weekly_trend: output_response is a multi-KB JSON blob. Truncate to the
# first 1200 chars — enough to expose the headline/summary context without
# blowing the input budget.
trim /tmp/weekly_trend.json \
  '{data: [((.data // []) | if type == "array" then . else [] end)[] | {output_response: (.output_response // "" | .[0:1200])}]}'

echo "trim_payloads.sh: ok"
