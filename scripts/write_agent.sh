#!/usr/bin/env bash
# Wraps a plain-text narrative file in the write_agent_run envelope.
# In dry-run mode, prints the exact would-call envelope and exits without HTTP.
# In live mode, POSTs it and prints the resulting row id.
#
# Usage:
#   scripts/write_agent.sh <goal> <narrative_file> [response_out]
#
# Environment:
#   MODEL                  optional model string; defaults to routine-selected
#   PIPELINE_ID            UUID linking this narrative to its llm_runs siblings
#   ROUTINE_MODE           dry_run (default) or live
#   ALLOW_WRITES           must be 1 when ROUTINE_MODE=live
#   AGENT_EXECUTION_MODE   scheduled_claude (default), scheduled_codex, etc.
set -euo pipefail

goal="${1:?goal required}"
narrative_file="${2:?narrative_file required}"
response_out="${3:-/tmp/write_agent_response.json}"
body_file="/tmp/write_agent_body.json"

: "${PIPELINE_ID:?PIPELINE_ID must be set}"
MODEL="${MODEL:-routine-selected}"
ROUTINE_MODE="${ROUTINE_MODE:-dry_run}"
if [ "${DRY_RUN:-}" = "1" ]; then
  ROUTINE_MODE="dry_run"
fi

# complete_missing idempotency gate (spec §3.4): skip the narrative agent_run
# when MISSING_RUN_TYPES is set and does not include "agent_runs" (it already
# exists), so a catch-up run cannot duplicate it. Runs before validation/write.
if [ -n "${MISSING_RUN_TYPES:-}" ]; then
  case " $MISSING_RUN_TYPES " in
    *" agent_runs "*) : ;;
    *)
      echo "write_agent.sh: skip narrative — agent_runs already present (not in MISSING_RUN_TYPES)" >&2
      exit 0
      ;;
  esac
fi

python3 - "$goal" "$narrative_file" "$body_file" "$MODEL" <<'PY'
import json, os, sys
goal, narrative_file, body_file, model = sys.argv[1:5]
tool_call = {
    "classification": {
        "run_origin": os.environ.get("AGENT_RUN_ORIGIN", "manual_mcp"),
        "execution_mode": os.environ.get("AGENT_EXECUTION_MODE", "scheduled_claude"),
        "agent_kind": os.environ.get("AGENT_KIND", "morning_briefing"),
        "visibility": os.environ.get("AGENT_VISIBILITY", "user_visible"),
    },
    "pipeline_id": os.environ["PIPELINE_ID"],
}
extra_tool_calls = []
raw_extra = os.environ.get("EXTRA_TOOL_CALLS_JSON")
if raw_extra:
    parsed = json.loads(raw_extra)
    if isinstance(parsed, list):
        extra_tool_calls = parsed
    else:
        raise SystemExit("EXTRA_TOOL_CALLS_JSON must be a JSON array")

envelope = {
    "goal": goal,
    "final_response": open(narrative_file).read(),
    "model": model,
    "pipeline_id": os.environ["PIPELINE_ID"],
    "iterations": int(os.environ.get("AGENT_ITERATIONS", "1")),
    "tool_calls": json.dumps([tool_call, *extra_tool_calls], separators=(",", ":")),
}
with open(body_file, "w") as f:
    json.dump(envelope, f)
PY

python3 "$(dirname "${BASH_SOURCE[0]}")/validate_payloads.py" --agent-envelope "$body_file" >&2
if [ "${AGENT_KIND:-morning_briefing}" = "morning_briefing" ] && [ -f /tmp/briefing.json ]; then
  python3 "$(dirname "${BASH_SOURCE[0]}")/validate_payloads.py" \
    --narrative "$narrative_file" \
    --briefing-context /tmp/briefing.json >&2
fi

if [ "$ROUTINE_MODE" != "live" ]; then
  python3 - "$body_file" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    body = json.load(f)
print(json.dumps({
    "would_call": "write_agent_run",
    "arguments": body,
    "expected_provenance_note": "write_agent_run sets source=manual_mcp and appends Model signoff at write time; dry run did not persist it.",
}, indent=2))
PY
  exit 0
fi

if [ "${ALLOW_WRITES:-}" != "1" ]; then
  echo "write_agent.sh: refusing live write because ALLOW_WRITES=1 is not set" >&2
  exit 3
fi

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$here/mcp.sh" write_agent_run "@${body_file}" "$response_out"
jq -r '.data.id' "$response_out"
