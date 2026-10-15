# shellcheck shell=bash
# Mode ceiling (2026-10-14). Sourced by mcp.sh, write_run.sh and write_agent.sh.
#
# The routine's env file (MCP_ENV_FILE, default /tmp/mcp.env) is written by
# whoever launched the run: the API runner writes ROUTINE_MODE='dry_run' for a
# shadow run, the cloud routine's paste body writes ROUTINE_MODE='live', and the
# shared template writes no mode at all. When the file pins dry_run, no helper
# may write, whatever a later step exported — the runbook itself says
# `export ROUTINE_MODE=live` on its live paths (complete_missing included), so a
# dry run that followed it literally would write for real. A file saying live,
# or no mode line, changes nothing: the exported env decides as before.
routine_mode_ceiling() {
  local file="${MCP_ENV_FILE:-/tmp/mcp.env}" pinned=""
  [ -f "$file" ] || return 0
  pinned="$(sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?ROUTINE_MODE=['\"]?([A-Za-z_]+)['\"]?[[:space:]]*$/\2/p" "$file" | tail -n 1)"
  [ "$pinned" = "dry_run" ] || return 0
  if [ "${ROUTINE_MODE:-dry_run}" != "dry_run" ] || [ "${ALLOW_WRITES:-0}" != "0" ]; then
    echo "mode ceiling: ${file} pins ROUTINE_MODE=dry_run; ignoring the exported ROUTINE_MODE=${ROUTINE_MODE:-unset} ALLOW_WRITES=${ALLOW_WRITES:-unset}" >&2
  fi
  ROUTINE_MODE="dry_run"
  ALLOW_WRITES="0"
}
