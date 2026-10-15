#!/usr/bin/env bash
# Wraps a JSON payload file in the write_llm_run envelope.
# In dry-run mode, prints the exact would-call envelope and exits without HTTP.
# In live mode, POSTs it and prints the resulting row id.
#
# Usage:
#   scripts/write_run.sh <run_type> <step_label> <payload_file> [response_out]
#
# Environment:
#   MODEL          optional model string to record; defaults to routine-selected
#   PIPELINE_ID    UUID linking the stages of one morning run
#   ROUTINE_MODE   dry_run (default) or live
#   ALLOW_WRITES   must be 1 when ROUTINE_MODE=live
#   YESTERDAY_ET   optional recorded as input_payload.date
#   TODAY_ET       optional recorded as input_payload.today
#
# Example:
#   MODEL=claude-sonnet-4-5 PIPELINE_ID=$UUID YESTERDAY_ET=2026-04-14 \
#     scripts/write_run.sh rt_yesterday stage1_rt /tmp/rt_yesterday.json
set -euo pipefail

run_type="${1:?run_type required}"
step_label="${2:?step_label required}"
payload_file="${3:?payload_file required}"
response_out="${4:-/tmp/write_${run_type}_response.json}"
body_file="/tmp/write_${run_type}_body.json"

: "${PIPELINE_ID:?PIPELINE_ID must be set}"
MODEL="${MODEL:-routine-selected}"
ROUTINE_MODE="${ROUTINE_MODE:-dry_run}"
if [ "${DRY_RUN:-}" = "1" ]; then
  ROUTINE_MODE="dry_run"
fi
_ceiling="$(dirname "${BASH_SOURCE[0]}")/mode_ceiling.sh"
if [ -f "$_ceiling" ]; then
  # shellcheck source=mode_ceiling.sh
  . "$_ceiling"
  routine_mode_ceiling
else
  echo "$(basename "${BASH_SOURCE[0]}"): mode_ceiling.sh missing beside this script — the dry_run pin in the env file is NOT enforced" >&2
fi

# Spec §3.5: every row should carry input_payload.today so future same-day
# detection can rely on it. Warn (do not fail) when TODAY_ET is missing.
if [ -z "${TODAY_ET:-}" ]; then
  echo "write_run.sh: warning TODAY_ET not set; ${run_type} row will lack input_payload.today" >&2
fi

# complete_missing idempotency gate (spec §3.4/§3.5): when MISSING_RUN_TYPES is
# SET (the guard's complete_missing path), persist ONLY the listed run types and
# skip rows that already exist, so a catch-up run cannot duplicate them. An empty
# value (set but "") gates ALL llm writes (complete_missing with nothing missing —
# Stage 4 still runs live separately). UNSET = normal full run (no gating).
if [ "${MISSING_RUN_TYPES+set}" = "set" ]; then
  case " ${MISSING_RUN_TYPES} " in
    *" $run_type "*) : ;;
    *)
      echo "write_run.sh: skip ${run_type} — already present (not in MISSING_RUN_TYPES)" >&2
      exit 0
      ;;
  esac
fi

python3 - "$run_type" "$step_label" "$payload_file" "$body_file" "$MODEL" <<'PY'
import json, os, sys
run_type, step_label, payload_file, body_file, model = sys.argv[1:6]
input_payload = {
    "date": os.environ.get("YESTERDAY_ET", ""),
    "today": os.environ.get("TODAY_ET", ""),
    "source": os.environ.get("ROUTINE_SOURCE", "winter-routine"),
    "routine_mode": os.environ.get("ROUTINE_MODE", "dry_run"),
}
envelope = {
    "run_type": run_type,
    "model": model,
    "pipeline_id": os.environ["PIPELINE_ID"],
    "step_label": step_label,
    "input_payload": json.dumps(input_payload, separators=(",", ":")),
    "output_response": open(payload_file).read(),
}
with open(body_file, "w") as f:
    json.dump(envelope, f)
PY

# Dry-run fidelity (2026-10-14): a dry run never reaches the write path, so it
# never sees the platform's schema verdict — a briefing the local validator
# passed was rejected server-side. For daily_briefing, ask the platform's
# read-only validate_payload and fail the same way a live write would (exit 4,
# nothing stored either way). The MCP env comes from the shell or, failing
# that, from MCP_ENV_FILE (a step that forgot `source /tmp/mcp.env` is still
# checked). Anything but a clear ok/error answer is reported as UNVERIFIED and
# the dry run continues on the local result; ROUTINE_SERVER_VALIDATE=0 opts out.
if [ "$ROUTINE_MODE" != "live" ] && [ "$run_type" = "daily_briefing" ] && [ "${ROUTINE_SERVER_VALIDATE:-1}" = "1" ]; then
  envfile="${MCP_ENV_FILE:-/tmp/mcp.env}"
  if [ -n "${MCP_BASE_URL:-}" ] && [ -n "${MCP_API_KEY:-}" ]; then
    env_source="shell"
  elif [ -f "$envfile" ]; then
    env_source="file"
  else
    env_source=""
  fi
  if [ -z "$env_source" ]; then
    echo "write_run.sh: dry run — platform check SKIPPED (no MCP env in the shell and no ${envfile}); the local validator is the only check" >&2
  else
    vargs="/tmp/validate_${run_type}_args.json"
    vresp="/tmp/validate_${run_type}_response.json"
    rm -f "$vresp"
    python3 -c 'import json,sys; print(json.dumps({"payload_type": "daily_briefing", "payload": open(sys.argv[1]).read()}))' "$payload_file" > "$vargs"
    vhere="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    set +e
    if [ "$env_source" = "file" ]; then
      ( { set +x; } 2>/dev/null; set +u; . "$envfile"; "$vhere/mcp.sh" validate_payload "@${vargs}" "$vresp" )
    else
      "$vhere/mcp.sh" validate_payload "@${vargs}" "$vresp"
    fi
    vrc=$?
    set -e
    if [ "$vrc" -ne 0 ]; then
      echo "write_run.sh: dry run — platform check UNVERIFIED (validate_payload exit ${vrc}); continuing on the local result" >&2
    elif jq -e '.status == "ok"' "$vresp" >/dev/null 2>&1; then
      :
    elif jq -e '.status == "error"' "$vresp" >/dev/null 2>&1; then
      reason="$(jq -r '[(.errors // [])[], (.error // empty)] | map(tostring) | join("; ") | if . == "" then "no reason given" else . end' "$vresp" | tr '\n' ' ' | cut -c1-400)"
      echo "write_run.sh: dry run — the platform would REJECT this ${run_type}, nothing stored: ${reason}" >&2
      exit 4
    else
      echo "write_run.sh: dry run — platform check UNVERIFIED (unexpected answer: $(head -c 200 "$vresp" 2>/dev/null | tr '\n' ' ')); continuing on the local result" >&2
    fi
  fi
fi

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
# Exit codes after a live write (2026-10-14): the platform answers HTTP 200 with
# {"status":"error"} when it REJECTS a write (e.g. a schema limit) and stores
# NOTHING — before this gate the helper printed `null` and exited 0, so a
# rejected briefing went unnoticed. 4 = rejected, nothing stored: fix the
# artifact, re-validate, and call the helper once more (not a retry of a write
# that may have succeeded). 5 = outcome unknown: do NOT call it again; check for
# the row with a read first.
set +e
"$here/mcp.sh" write_llm_run "@${body_file}" "$response_out"
rc=$?
set -e
if [ "$rc" -eq 2 ] || [ "$rc" -eq 3 ]; then
  # mcp.sh refused before sending (2 = MCP env missing, 3 = write gate / mode ceiling):
  # nothing reached the platform, so fixing the cause and calling again is safe.
  echo "write_run.sh: ${run_type} write NOT SENT (mcp.sh exit ${rc}: env or write gate) — fix the cause and call again" >&2
  exit "$rc"
fi
if [ "$rc" -ne 0 ]; then
  echo "write_run.sh: ${run_type} write OUTCOME UNKNOWN (mcp.sh exit ${rc}) — do not call again; check for the row with a read first" >&2
  exit 5
fi
if jq -e '.status == "ok" and (.data.id != null)' "$response_out" >/dev/null 2>&1; then
  jq -r '.data.id' "$response_out"
  exit 0
fi
# "Failed to insert: ..." is raised around the INSERT/COMMIT itself: a COMMIT
# whose acknowledgement was lost reports it even though the row is durable, so
# it is an unknown outcome (5), never a rejection. Every other status:error is
# returned before the insert (schema, required fields, JSON) and stored nothing.
if jq -e '.status == "error" and ((.error // "") | startswith("Failed to insert") | not)' "$response_out" >/dev/null 2>&1; then
  reason="$(jq -r '.error // "no reason given"' "$response_out" | tr '\n' ' ' | cut -c1-400)"
  echo "write_run.sh: ${run_type} write REJECTED by the platform, nothing stored: ${reason}" >&2
  exit 4
fi
echo "write_run.sh: ${run_type} write OUTCOME UNKNOWN (unexpected response: $(head -c 200 "$response_out" 2>/dev/null | tr '\n' ' ')) — do not call again; check for the row with a read first" >&2
exit 5
