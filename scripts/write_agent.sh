#!/usr/bin/env bash
# Wraps a plain-text narrative file in the write_agent_run envelope and POSTs.
# Prints the resulting row id to stdout.
#
# Usage:
#   scripts/write_agent.sh <goal> <narrative_file> [response_out]
#
# Environment:
#   MODEL         model string (default claude-haiku-4-5 if unset)
#   PIPELINE_ID   UUID linking this narrative to its llm_runs siblings
set -euo pipefail

goal="${1:?goal required}"
narrative_file="${2:?narrative_file required}"
response_out="${3:-/tmp/write_agent_response.json}"
body_file="/tmp/write_agent_body.json"

: "${PIPELINE_ID:?PIPELINE_ID must be set}"
MODEL="${MODEL:-claude-haiku-4-5}"

python3 - "$goal" "$narrative_file" "$body_file" "$MODEL" <<'PY'
import json, os, sys
goal, narrative_file, body_file, model = sys.argv[1:5]
envelope = {
    "goal": goal,
    "final_response": open(narrative_file).read(),
    "model": model,
    "pipeline_id": os.environ["PIPELINE_ID"],
}
with open(body_file, "w") as f:
    json.dump(envelope, f)
PY

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$here/mcp.sh" write_agent_run "@${body_file}" "$response_out"
jq -r '.data.id' "$response_out"
