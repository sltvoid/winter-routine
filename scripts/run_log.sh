#!/usr/bin/env bash
# Compact JSONL log for fatal and recovered morning-briefing errors.
#
# Usage:
#   scripts/run_log.sh recovered "Stage 0.5" "env lost and rerun succeeded"
#   scripts/run_log.sh fatal "Stage 3.5" "calendar search failed"
#   scripts/run_log.sh summary
set -euo pipefail

LOG_PATH="${RUN_LOG_PATH:-/tmp/morning_briefing_run_log.jsonl}"
cmd="${1:-}"

write_event() {
  local severity="$1"
  local stage="$2"
  local message="$3"
  mkdir -p "$(dirname "$LOG_PATH")"
  jq -nc \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg severity "$severity" \
    --arg stage "$stage" \
    --arg message "$message" \
    '{ts: $ts, severity: $severity, stage: $stage, message: $message}' >> "$LOG_PATH"
  echo "run_log.sh: ${severity} ${stage}"
}

case "$cmd" in
  recovered|fatal)
    if [ "$#" -lt 3 ]; then
      echo "usage: scripts/run_log.sh $cmd <stage> <message>" >&2
      exit 2
    fi
    stage="$2"
    shift 2
    write_event "$cmd" "$stage" "$*"
    ;;
  summary)
    if [ ! -s "$LOG_PATH" ]; then
      jq -nc '{fatal_errors: [], recovered_errors: []}'
      exit 0
    fi
    jq -sc '{
      fatal_errors: [.[] | select(.severity == "fatal") | (.stage + ": " + .message)],
      recovered_errors: [.[] | select(.severity == "recovered") | (.stage + ": " + .message)]
    }' "$LOG_PATH"
    ;;
  *)
    echo "usage: scripts/run_log.sh recovered|fatal|summary [stage] [message]" >&2
    exit 2
    ;;
esac
