#!/usr/bin/env bash
# Wraps a JSON payload file in the write_llm_run envelope and POSTs it.
# Prints the resulting row id to stdout on success.
#
# Usage:
#   scripts/write_run.sh <run_type> <step_label> <payload_file> [response_out]
#
# Environment:
#   MODEL          model string to record (e.g. claude-haiku-4-5, or "none")
#   PIPELINE_ID    UUID linking the four stages of one morning run
#   YESTERDAY_ET   (optional) recorded as input_payload.date; defaults to empty
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

python3 - "$run_type" "$step_label" "$payload_file" "$body_file" <<'PY'
import json, os, sys
run_type, step_label, payload_file, body_file = sys.argv[1:5]
envelope = {
    "run_type": run_type,
    "model": os.environ["MODEL"],
    "pipeline_id": os.environ["PIPELINE_ID"],
    "step_label": step_label,
    "input_payload": json.dumps({"date": os.environ.get("YESTERDAY_ET", "")}),
    "output_response": open(payload_file).read(),
}
with open(body_file, "w") as f:
    json.dump(envelope, f)
PY

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$here/mcp.sh" write_llm_run "@${body_file}" "$response_out"
jq -r '.data.id' "$response_out"
