# API Catalog

All 8 tools exposed at `$MCP_BASE_URL/api/mcp/tools/<name>`. POST only.
Auth via `X-API-Key: $MCP_API_KEY`.

Every tool returns:

```json
{"status": "ok", "data": <payload>, "row_count": <n>}
```

or on error:

```json
{"status": "error", "error": "<message>"}
```

## Discovery

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/list_tools" \
  -H "X-API-Key: $MCP_API_KEY"
```

---

## Read tools (mcp_reader role, SELECT-only, 10s timeout)

### `compute_daily_insights`

Pre-computed Phase 1 insights for the morning pipeline. Always call this
**first** — it replaces per-device / per-hour / career SQL queries.

| Arg | Type | Required | Notes |
|-----|------|----------|-------|
| `date` | string | yes | `YYYY-MM-DD`. Use yesterday's ET date. |

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/compute_daily_insights" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{"date":"2026-04-13"}'
```

Returns three sections (`anomalies`, `parity`, `career`), each with a closed-enum
`verdict`, a verbatim `headline`, and an optional `memory_candidate`. Quote
headlines verbatim in downstream writes — do not rephrase.

### `query_calendar`

Latest `daily_briefing.schedule_blocks`. Takes no args.

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_calendar" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{}'
```

### `query_health`

| Arg | Type | Required | Notes |
|-----|------|----------|-------|
| `date` | string | no | Defaults to today ET. |
| `mode` | string | no | `daily` (default) or `workouts`. |

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_health" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{"date":"2026-04-13","mode":"daily"}'

curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_health" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{"mode":"workouts"}'
```

### `query_raw_sql`

| Arg | Type | Required | Notes |
|-----|------|----------|-------|
| `database` | string | yes | One of: `llm_db`, `email_db`, `rescuetime_db`, `health_db`, `news_db`, `spotify_data`, `job_tracker`, `context_db`. |
| `sql` | string | yes | Single SELECT statement. |

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_raw_sql" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{"database":"rescuetime_db","sql":"SELECT device, ROUND(SUM(seconds)/3600.0,1) AS hours FROM rescuetime_activity_slice WHERE source_day = '\''2026-04-13'\'' GROUP BY device"}'
```

Timezone gotcha: `ts_utc` on `rescuetime_activity_slice` is ET-as-UTC.
Cast `ts_utc::timestamp` before comparing against ET values. `source_day`
is safe as-is.

### `recall_memory`

| Arg | Type | Required | Notes |
|-----|------|----------|-------|
| `query` | string | yes | Free-text search (pg_trgm fuzzy match). |
| `category` | string | no | `preference`, `pattern`, `fact`, `goal`, or `external`. |
| `limit` | int | no | Default 10. |

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/recall_memory" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{"query":"focus_crash_2026-04-13_11h","limit":3}'
```

---

## Write tools (postgres role)

### `save_memory`

| Arg | Type | Required | Notes |
|-----|------|----------|-------|
| `content` | string | yes | The stored text. |
| `category` | string | yes | `preference`, `pattern`, `fact`, `goal`, `external`. |
| `key` | string | no | Idempotency key — pass through verbatim from `compute_daily_insights` candidates. |
| `confidence` | float | no | Default 0.8. |
| `source` | string | no | Default `mcp_agent`. |
| `expires_at` | string | no | ISO-8601 timestamp. |

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/save_memory" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{"content":"Focus crash 11am on 2026-04-13: 59 min at 0%.","category":"pattern","key":"focus_crash_2026-04-13_11h"}'
```

Always `recall_memory` with the same `key` first; skip if it exists.

### `write_llm_run`

| Arg | Type | Required | Notes |
|-----|------|----------|-------|
| `run_type` | string | yes | e.g. `rt_yesterday`, `email_daily`, `daily_briefing`. |
| `model` | string | yes | The model you ran as (e.g. `claude-haiku-4-5`). |
| `output_response` | string | yes | JSON string — the run's payload. |
| `input_payload` | string | no | JSON string of inputs. Default `{}`. |
| `pipeline_id` | string | no | UUID linking stages of one pipeline. |
| `step_label` | string | no | Human label for this stage. |

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/write_llm_run" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{
    "run_type":"daily_briefing",
    "model":"claude-haiku-4-5",
    "output_response":"{\"date\":\"2026-04-14\",\"morning_brief\":{...}}",
    "pipeline_id":"<uuid>",
    "step_label":"stage3_briefing"
  }'
```

### `write_agent_run`

| Arg | Type | Required | Notes |
|-----|------|----------|-------|
| `goal` | string | yes | Human-readable. Shown on iOS. |
| `final_response` | string | yes | Plain-text narrative (same content as the synthesis). |
| `model` | string | no | Default `claude-opus-4-6`. |
| `tool_calls` | string | no | JSON string array of tools called. Default `[]`. |
| `iterations` | int | no | Default 1. |
| `pipeline_id` | string | no | Same UUID as the matching `write_llm_run`. |

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/write_agent_run" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{
    "goal":"Morning briefing pipeline for 2026-04-14 (Tuesday)",
    "final_response":"ACTIONABLE ITEMS\n1. ...",
    "model":"claude-haiku-4-5",
    "pipeline_id":"<uuid>"
  }'
```

---

## Databases reachable via `query_raw_sql`

| Database | Holds |
|----------|-------|
| `rescuetime_db` | `rescuetime_activity_slice` — per-activity seconds, productivity, device |
| `email_db` | `emails`, `structured_emails` |
| `health_db` | `apple_health_daily_metrics_v2`, `hevy_workouts` |
| `llm_db` | `llm_runs`, `agent_runs`, `agent_memory`, `agent_workflows`, `notes`, `user_profile` |
| `news_db` | `news_articles` |
| `spotify_data` | `play_history`, `tracks` |
| `job_tracker` | legacy job application rows |
| `context_db` | feature extracts |
