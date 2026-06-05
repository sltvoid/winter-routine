# claude-routine-instructions

Scheduled-agent instructions for the personal data platform.

A Claude Code Routine (scheduled remote agent) clones this repo, reads the
appropriate `*.md` runbook, and executes it against the platform's HTTPS MCP
surface at `$MCP_BASE_URL/api/mcp/*`.

This repo contains **routine prompts, runbooks, helper scripts, and tests** for
the scheduled agents. It must not contain committed credentials. The platform
itself lives in a private repo.

Claude Code should read [`CLAUDE.md`](CLAUDE.md) before judging scheduled
Routine prompts. It documents the trusted personal MCP endpoint, the
Claude-Routine inline-key constraint, and the repo's no-git-mutation boundary.

## Runbooks

| File | When to run | Writes |
|------|-------------|--------|
| [`morning-briefing.md`](morning-briefing.md) | Once per morning (7:00 AM ET) | `llm_runs` (4 rows) + `agent_runs` (1 row) + Google Calendar busy-window-aware create + `agent_memory` (0-3 rows) |
| `claude-routine-morning-briefing.md` | Ignored local Claude Routine daily prompt wrapper for Sonnet/no-model-export tests | Morning rows plus manifest-only `calendar_write`; no Google Calendar event creates |
| [`morning-briefing-clean-canary.md`](morning-briefing-clean-canary.md) | Active local Codex daily canary and manual review runbook | `llm_runs` (4 rows) + `agent_runs` (1 row) + Google Calendar busy-window-aware create |
| [`morning-briefing-calendar-watchdog.md`](morning-briefing-calendar-watchdog.md) | 10-15 min and 45-60 min after the morning briefing | Calendar-only repair row + missing Google Calendar events |
| [`calendar-create-debug-automation.md`](calendar-create-debug-automation.md) | One-shot Google Calendar plugin create probe | Google Calendar only: at most 1 diagnostic event |
| [`morning-briefing-calendar-repair.md`](morning-briefing-calendar-repair.md) | Calendar-only repair for an existing morning briefing | `calendar_write` repair row + Google Calendar events |
| [`learning-agent.md`](learning-agent.md) | Weekly Monday learner run after upstream weekly evidence exists | `llm_runs` + `agent_runs`; profile/memory writes only when fresh evidence passes replay guard and audit |
| [`api-catalog.md`](api-catalog.md) | Reference — not a runbook | — |

## Operational Notes

- [`docs/codex-morning-briefing-patch-log-2026-05-23.md`](docs/codex-morning-briefing-patch-log-2026-05-23.md) documents the earlier Codex native canary process, payload patches, validation commands, written row IDs, and the Calendar-auth gate from that rollout.
- Active local Codex schedulers: `mcp-morning-briefing-clean-canary` runs the
  daily briefing at 6:00 AM ET; `mcp-morning-briefing-calendar-watchdog-early`
  and `mcp-morning-briefing-calendar-watchdog-late` run the Calendar-only
  coverage repair checks shortly afterward.

## Required environment

The Routine must have these set:

| Variable | Purpose |
|----------|---------|
| `MCP_BASE_URL` | e.g. `https://<tailnet-name>.ts.net` or the NodePort URL |
| `MCP_API_KEY` | Matches the `MCP_API_KEY` entry in the platform's `context-api-secrets` |
| `MODEL` | Optional helper override for persisted row metadata; shell helpers default to `routine-selected` when unset |
| `ROUTINE_MODE` | `dry_run` or `live`; defaults to `dry_run` in write helpers |
| `ALLOW_WRITES` | Must be `1` for `ROUTINE_MODE=live`; otherwise write helpers refuse to persist |
| `TEST_RUN` / `RUN_SCOPE` | Learner comparison/test paths only; production routines should not set these |

Do not paste a literal `MCP_API_KEY` into runbooks, commits, PRs, chat output,
or logs. If a Claude Routine UI cannot provide secret environment variables, put
the literal key only in that UI prompt, never in the repository.

Every tool call follows the same shape:

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/<tool_name>" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '<JSON kwargs>'
```

The full inventory is in [`api-catalog.md`](api-catalog.md).

## Safety rules

1. **Never log `$MCP_API_KEY`.** Don't `echo` it, don't paste it into a response.
2. **Run the smoke test first.** `scripts/smoke_test.sh` must confirm the 8
   daily-briefing tools before the scheduled routine attempts Stage 0.
3. **Write helpers default to dry-run.** Live scheduled runs must set
   `ROUTINE_MODE=live` and `ALLOW_WRITES=1`.
4. **Read tools are SELECT-only.** `query_raw_sql` runs under the `mcp_reader`
   role with a 10s timeout; destructive SQL will fail at the DB layer.
5. **Write tools are narrow.** `save_memory`, `update_memory`,
   `expire_memory`, `update_profile`, `write_llm_run`, and `write_agent_run`
   mutate platform state. Learner test rows must use `write_test_llm_run` and
   `write_test_agent_run`. Calendar bounded event searches are safe read-only
   checks; Calendar event creation mutates Google Calendar. Do not attempt to
   write via `query_raw_sql`.
6. **Calendar population is covered by the watchdog.** If the daily morning
   run cannot write Calendar events because bounded Calendar search fails, keep
   the same `daily_briefing` row and let the watchdog perform calendar-only
   coverage detection and missing-event creation. Do not rerun Stage 0 just to
   repair Calendar.
7. **Morning briefing saves only deduped Stage 0 memory candidates.** Recall by
   exact key first, save at most 3, and never retry `save_memory`.
8. **Date anchoring.** Compute today's and yesterday's ET dates once at the
   start of the run and reuse them. Don't re-query `CURRENT_DATE` mid-pipeline.

## Output conventions

- Write briefing JSON to `llm_runs` via `write_llm_run` (consumed by the iOS
  app's morning card).
- Write the human-readable narrative to `agent_runs` via `write_agent_run`
  (consumed by the iOS app's activity feed).
- Agent rows must include `tool_calls[0].classification.agent_kind =
  "morning_briefing"` so API clients can render them as briefings.
- Both writes are idempotent **only** within the same `pipeline_id` — re-runs
  create new rows unless you pass the same pipeline_id explicitly.
