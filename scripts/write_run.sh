#!/usr/bin/env bash
# Wraps a JSON payload file in the write_llm_run envelope.
# In dry-run mode, prints the exact would-call envelope and exits without HTTP.
# In live mode, POSTs it and prints the resulting row id.
#
# Usage:
#   scripts/write_run.sh <run_type> <step_label> <payload_file> [response_out]
#
# Environment:
#   MODEL          model string to record (e.g. claude-haiku-4-5, or "none")
#   PIPELINE_ID    UUID linking the stages of one morning run
#   ROUTINE_MODE   dry_run (default) or live
#   ALLOW_WRITES   must be 1 when ROUTINE_MODE=live
#   YESTERDAY_ET   optional recorded as input_payload.date
#   TODAY_ET       optional recorded as input_payload.today
#
# Example:
#   MODEL=claude-haiku-4-5 PIPELINE_ID=$UUID YESTERDAY_ET=2026-04-14 \
#     scripts/write_run.sh rt_yesterday stage1_rt /tmp/rt_yesterday.json
set -euo pipefail

run_type="${1:?run_type required}"
step_label="${2:?step_label required}"
payload_file="${3:?payload_file required}"
response_out="${4:-/tmp/write_${run_type}_response.json}"
body_file="/tmp/write_${run_type}_body.json"

: "${MODEL:?MODEL must be set}"
: "${PIPELINE_ID:?PIPELINE_ID must be set}"
ROUTINE_MODE="${ROUTINE_MODE:-dry_run}"
if [ "${DRY_RUN:-}" = "1" ]; then
  ROUTINE_MODE="dry_run"
fi

python3 - "$run_type" "$step_label" "$payload_file" "$body_file" <<'PY'
import json, os, sys
run_type, step_label, payload_file, body_file = sys.argv[1:5]
input_payload = {
    "date": os.environ.get("YESTERDAY_ET", ""),
    "today": os.environ.get("TODAY_ET", ""),
    "source": os.environ.get("ROUTINE_SOURCE", "winter-routine"),
    "routine_mode": os.environ.get("ROUTINE_MODE", "dry_run"),
}
envelope = {
    "run_type": run_type,
    "model": os.environ["MODEL"],
    "pipeline_id": os.environ["PIPELINE_ID"],
    "step_label": step_label,
    "input_payload": json.dumps(input_payload, separators=(",", ":")),
    "output_response": open(payload_file).read(),
}
with open(body_file, "w") as f:
    json.dump(envelope, f)
PY

if [ "$ROUTINE_MODE" != "live" ]; then
  python3 - "$body_file" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    body = json.load(f)
print(json.dumps({
    "would_call": "write_llm_run",
    "arguments": body,
    "expected_provenance_note": "write_llm_run attaches output_response.model_signoff at write time; dry run did not persist it.",
}, indent=2))
PY
  exit 0
fi

if [ "${ALLOW_WRITES:-}" != "1" ]; then
  echo "write_run.sh: refusing live write because ALLOW_WRITES=1 is not set" >&2
  exit 3
fi

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$here/mcp.sh" write_llm_run "@${body_file}" "$response_out"
jq -r '.data.id' "$response_out"
