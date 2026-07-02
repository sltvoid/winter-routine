# Toolcard — Daily Morning Briefing (hot path)

The 10 tools this pipeline touches, condensed. Full catalog: `api-catalog.md`
(do NOT open it after pre-flight; this card is sufficient). All tools:
`POST $MCP_BASE_URL/api/mcp/tools/<name>`, header `X-API-Key: $MCP_API_KEY`,
via `scripts/mcp.sh <tool> '<json>' /tmp/out.json`. Every response is
`{"status":"ok","data":...,"row_count":N}` or `{"status":"error","error":"..."}`.
Discovery: `POST $MCP_BASE_URL/api/mcp/list_tools`.

## Reads

- `compute_daily_insights` `{date: "YYYY-MM-DD"}` (yesterday ET; MANDATORY
  first call) → `data.sections.{anomalies,parity,career,location}`, each
  `{verdict, headline, ..., memory_candidate: {content,category,key}|null}`.
  Headlines are quoted VERBATIM downstream. anomalies adds
  `overall_focus_pct, dod_delta_pp, crashes[], peaks[], location_context?`;
  parity adds `baseline_7d_avg_min, top_productive, top_distraction`; career
  adds `today_genuine, stall_since, trend_14d[]`; location adds
  `traveled/timezone_shift` flags.
- `query_health` `{date?, mode: "daily"|"workouts"}` — date DEFAULTS TO TODAY,
  always pass it. daily → rows `{metric_type, value, unit, sample_count}`
  (`sleep_seconds` [/3600 for h], `hrv_ms`, `resting_heart_rate_bpm`, `steps`
  often null in morning sync). workouts → `[{title, started_at,
  duration_seconds, total_volume_kg, total_sets}]`;
  latest: `jq '.data[0]'`.
- `query_raw_sql` `{database, sql}` — SELECT-only, 10s timeout. Databases:
  `llm_db, email_db, rescuetime_db, health_db, news_db, spotify_data,
  context_db`. Gotcha: `rescuetime_activity_slice.ts_utc` is ET-as-UTC — cast
  `ts_utc::timestamp` before ET comparisons; `source_day` is safe.
- `query_calendar` `{}` → latest briefing's schedule_blocks (prior-plan
  context ONLY — never a busy-window source).
- `recall_memory` `{query, category?, limit?}` — pg_trgm fuzzy; only an EXACT
  stored-key match counts as a dedupe hit.
- `get_active_program` `{}` → `{status, program{id, frame, rotation,
  milestone_queue}, stale, today_rep|null}` (lifeOS; rest day = null rep).
- `get_skill_summary` `{days: 14}` — best-effort; on error `extract.py`
  degrades `skill_pulse` to zeros. Never block the run on it.

## Writes (never retry a write that may have reached the server)

- `save_memory` `{content, category, key?, confidence?, source?, expires_at?}`
  — categories `preference|pattern|fact|goal|external`; always recall the
  exact key first, skip on match.
- `write_llm_run` `{run_type, model, output_response (JSON string),
  input_payload?, pipeline_id?, step_label?}` → `data.id` (int,
  `jq '.data.id'`). model = selected model or `routine-selected`.
- `write_agent_run` `{goal, final_response, model?, tool_calls?, iterations?,
  pipeline_id?}` → `data.id` (uuid, `jq -r '.data.id'`). tool_calls carries
  the iOS classification array (see runbook Stage 3d).

Prefer `scripts/write_run.sh` / `scripts/write_agent.sh` — they add envelopes,
honor `ROUTINE_MODE`/`ALLOW_WRITES`/`MISSING_RUN_TYPES`, and print row ids.

## Signoff

- **2026-07-02 ET · Claude (Fable 5, operator session)** — Created from
  api-catalog.md (condensed; ~75% token cut vs the full catalog). Verified:
  shapes cross-checked against catalog sections + live pipeline usage.
  (Latest entry only — history in git.)
