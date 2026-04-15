# claude-routine-instructions

Scheduled-agent instructions for the personal data platform.

A Claude Code Routine (scheduled remote agent) clones this repo, reads the
appropriate `*.md` runbook, and executes it against the platform's HTTPS MCP
surface at `$MCP_BASE_URL/api/mcp/*`.

This repo contains **prompts and protocols only** — no code, no credentials.
The platform itself lives in a private repo.

## Runbooks

| File | When to run | Writes |
|------|-------------|--------|
| [`morning-briefing.md`](morning-briefing.md) | Once per morning (7:00 AM ET) | `llm_runs` (3 rows) + `agent_runs` (1 row) |
| [`proactive-agent.md`](proactive-agent.md) | Every 30 min during work hours (future) | `agent_runs` |
| [`api-catalog.md`](api-catalog.md) | Reference — not a runbook | — |

## Required environment

The Routine must have these set:

| Variable | Purpose |
|----------|---------|
| `MCP_BASE_URL` | e.g. `https://<tailnet-name>.ts.net` or the NodePort URL |
| `MCP_API_KEY` | Matches the `MCP_API_KEY` entry in the platform's `context-api-secrets` |

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
2. **Read tools are SELECT-only.** `query_raw_sql` runs under the `mcp_reader`
   role with a 10s timeout; destructive SQL will fail at the DB layer.
3. **Write tools are narrow.** Only `save_memory`, `write_llm_run`, and
   `write_agent_run` mutate state. Do not attempt to write via `query_raw_sql`.
4. **Dedupe before saving memories.** Every runbook shows the recall→skip→save
   loop — follow it verbatim.
5. **Date anchoring.** Compute today's ET date once at the start of the run
   and reuse it. Don't re-query `CURRENT_DATE` mid-pipeline.

## Output conventions

- Write briefing JSON to `llm_runs` via `write_llm_run` (consumed by the iOS
  app's morning card).
- Write the human-readable narrative to `agent_runs` via `write_agent_run`
  (consumed by the iOS app's activity feed).
- Both writes are idempotent **only** within the same `pipeline_id` — re-runs
  create new rows unless you pass the same pipeline_id explicitly.
