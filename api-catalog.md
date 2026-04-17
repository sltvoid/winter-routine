# API Catalog

All 11 tools exposed at `$MCP_BASE_URL/api/mcp/tools/<name>`. POST only.
Auth via `X-API-Key: $MCP_API_KEY`.

The morning-briefing runbook uses the first 8 (read + save_memory + 2
write tools). The learning-agent runbook additionally uses `forget_memory`,
`bulk_forget_memory`, and `update_profile`.

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

**Response shape:**
```
data.sections.anomalies  → {verdict, headline, overall_focus_pct, dod_delta_pp,
                             crashes: [{hour, focus_pct, minutes, severity}],
                             peaks:   [{hour, focus_pct, minutes}],
                             memory_candidate: {content, category, key} | null}
data.sections.parity     → {verdict, headline, baseline_7d_avg_min,
                             delta_vs_baseline_pct, mac_contamination_pct,
                             top_productive:  {app, minutes, devices: {<dev>: min}},
                             top_distraction: {app, minutes, devices: {<dev>: min}},
                             memory_candidate: {content, category, key} | null}
data.sections.career     → {verdict, headline, today_genuine, today_noise,
                             stall_since, days_since_last_genuine,
                             trend_14d: [{date, count}],
                             memory_candidate: {content, category, key} | null}
```

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

**Response shape — `mode: daily`:** `data` is an array of
`{metric_type, value, unit, sample_count}` rows, one row per metric.
Relevant `metric_type` values:

| metric_type | unit | notes |
|---|---|---|
| `sleep_seconds` | seconds | divide by 3600 for hours |
| `hrv_ms` | ms | heart rate variability |
| `resting_heart_rate_bpm` | bpm | |
| `active_energy_burned_kilocalories` | kcal | |
| `steps` | count | often null in morning sync |

Extract with: `jq '[.data[] | select(.metric_type=="sleep_seconds") | .value][0]'`

**Response shape — `mode: workouts`:** `data` is an array of
`{title, started_at, duration_seconds, total_volume_kg, total_sets}`.

Extract latest: `jq '.data[0] | {title, duration_min: (.duration_seconds/60|round), total_sets, total_volume_kg}'`

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

**Response shape:** `{"status":"ok","data":{"id":<int>,"run_type":"<string>"}}`
Extract row ID with: `jq '.data.id'`

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

**Response shape:** `{"status":"ok","data":{"id":"<uuid>","goal":"<string>"}}`
Extract row ID with: `jq -r '.data.id'`

---

### `forget_memory`

Delete a single memory by integer ID. Lookup the ID via `recall_memory`
or `query_raw_sql` on `agent_memory` first.

| Arg | Type | Required | Notes |
|-----|------|----------|-------|
| `memory_id` | int | yes | Primary key in `agent_memory`. |

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/forget_memory" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{"memory_id": 570}'
```

**Response shape:** `{"status":"ok","data":{"deleted":<id>}}`

---

### `bulk_forget_memory`

Bulk-delete memories by key-pattern (SQL `LIKE`) and/or `source`. At
least one filter is required — passing neither errors out.

| Arg | Type | Required | Notes |
|-----|------|----------|-------|
| `key_pattern` | string | no* | SQL LIKE pattern, e.g. `"upgrade-log%"`. |
| `source` | string | no* | e.g. `"learning_agent"`. |

*At least one of `key_pattern` or `source` must be provided.

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/bulk_forget_memory" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{"key_pattern":"upgrade-log%","source":"learning_agent"}'
```

**Response shape:** `{"status":"ok","data":{"deleted_count":<n>,"key_pattern":"...","source":"..."}}`

---

### `update_profile`

Insert a new `user_profile` version. Auto-increments version from the
current max. Used by the learning agent to persist a new profile diff.

| Arg | Type | Required | Notes |
|-----|------|----------|-------|
| `sections` | string | yes | JSON string of the full profile sections. |
| `change_summary` | string | yes | One-paragraph plain text describing the delta. |
| `source_profile_ids` | string | no | JSON array string of `llm_runs` IDs used as input. Default `"[]"`. |

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/update_profile" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d @/tmp/profile_update_body.json
```

**Response shape:** `{"status":"ok","data":{"id":<row_id>,"version":<n>}}`

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
