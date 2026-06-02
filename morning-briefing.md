# Morning Briefing Runbook

Run once per morning. Produces:
- 4 rows in `llm_runs` (`rt_yesterday`, `email_daily`, `daily_briefing`, `calendar_write`)
- 1 row in `agent_runs` (plain-text narrative for iOS)
- N Google Calendar events (one per conflict-free schedule_block)
- 0-3 rows in `agent_memory` (only genuinely new Stage 0 memory candidates)

Every tool call uses `$MCP_BASE_URL` + `$MCP_API_KEY` — see
[`api-catalog.md`](api-catalog.md) for signatures.

Same-day diagnostic replay mode runs the full read/build/validate flow but
persists none of the rows or calendar/memory writes above.

---

## Output discipline (READ FIRST)

Previous runs died mid-Stage 3.5 after burning the bash-output budget on
debug printing in Stages 0–3. To prevent this:

1. **No `jq .` pretty-prints of full payloads.** Save responses to `/tmp/*.json`
   with `-o` or `>` redirection. When you need a field, extract exactly that
   field (`jq -r '.data.sections.anomalies.headline'`).
2. **No `cat /tmp/*.json` of large files.** If you must inspect, use
   `jq 'keys'` or `jq '.data | length'`.
3. **No redundant `echo "=== Stage N ==="` banners.** One-line status after
   each stage is enough.
4. **Batch independent tool calls in parallel** within a single turn
   (Stage 0.5 queries, Stage 4 recalls, Stage 4 saves).
5. **Stage 4 is mandatory.** The run is not "done" until the memory recall/save
   loop has completed. Stage 4 target: 2 turns total, one recall turn and one
   save turn. In diagnostic replay, the save turn becomes a `would_save` list
   and does not call `save_memory`.

Budget target: reach Stage 3.5 with at least 60% of your turn budget remaining.

---

## Helper scripts

All repetitive logic lives in `scripts/`. Use these instead of writing
curl/Python inline. Every script is a thin, auditable wrapper.

| Script | Purpose |
|--------|---------|
| `scripts/mcp.sh <tool> <json> [out]` | POST to an MCP tool. Injects base URL + API key. `@file.json` body syntax supported. |
| `scripts/smoke_test.sh` | Mandatory scheduled-routine preflight that calls `/api/mcp/list_tools` and verifies the 8 daily-briefing tools. |
| `scripts/anchor_env.sh [/tmp/morning_briefing_dates.env]` | Step 0 — computes date anchors once and writes only non-secret date/pipeline exports for later shell turns. |
| `scripts/trim_payloads.sh` | Stage 0.5c — best-effort jq trimming of `/tmp/calendar_blocks.json`, `/tmp/agent_memory.json`, `/tmp/weekly_trend.json` to cut input tokens when the AI re-reads them for synthesis context. |
| `scripts/extract.py` | Stage 0.5b — reads the 11 `/tmp/*.json` responses, writes `/tmp/data.json`. |
| `scripts/payloads.py rt` | Stage 1 body → `/tmp/rt_yesterday.json` (mechanical). |
| `scripts/payloads.py email` | Stage 2 body → `/tmp/email_daily.json` (mechanical). |
| `scripts/payloads.py briefing_base <today> <today_dow> <yesterday> <yesterday_dow>` | Stage 3 skeleton → `/tmp/briefing_base.json` (mechanical fields filled, synthesis fields empty). |
| `scripts/payloads.py briefing_finalize <overlay.json>` | Merge skeleton + AI overlay → `/tmp/briefing.json`. Exits non-zero if blocks < 6. |
| `scripts/validate_payloads.py` | Validates current `daily_briefing` and `agent_runs` contract before writes. |
| `scripts/write_run.sh <run_type> <step_label> <payload_file>` | Wraps payload in `write_llm_run` envelope. Defaults to dry-run; live writes require `ROUTINE_MODE=live ALLOW_WRITES=1`. |
| `scripts/write_agent.sh <goal> <narrative_file>` | Wraps text narrative in `write_agent_run` envelope with classification metadata. Defaults to dry-run; live writes require `ROUTINE_MODE=live ALLOW_WRITES=1`. |
| `scripts/run_log.sh recovered|fatal|summary` | Records recovered and fatal errors as compact JSONL and emits final `fatal_errors` / `recovered_errors` arrays. |

Required env for all scripts: `MCP_BASE_URL`, `MCP_API_KEY`.
Required for `write_run.sh` / `write_agent.sh`: also `PIPELINE_ID`, and for
`write_run.sh` optionally `MODEL`, `YESTERDAY_ET`, `TODAY_ET`.
Live writes require `ROUTINE_MODE=live` and `ALLOW_WRITES=1`; otherwise write
helpers print the would-call envelope and do not persist.

Scheduled Claude routines must not hard-code or export a fixed model. Use the
model selected in the routine UI for native writes. If you use the shell write
helpers and your environment exposes a selected model name, pass that through as
`MODEL`; otherwise leave model selection to the routine runtime.

Scheduled Claude routines must set only:

```bash
export ROUTINE_MODE="live"
export ALLOW_WRITES="1"
```

---

## Pre-flight — Read api-catalog.md

Before any curl, read `api-catalog.md` in this workspace. It documents every
response schema. Do **not** probe response structure with `jq 'keys'`, `jq '.[0]'`,
or `jq '.'` — if a field path is unclear, re-read the catalog. Structure-discovery
turns are pure waste and are the primary cause of mid-Stage-3.5 budget failure.

Before the pipeline, run the smoke test:

```bash
scripts/smoke_test.sh
```

It must return `smoke_test: ok` with all 8 required daily-briefing tools
present. Otherwise stop and emit a compact diagnostic summary; do not attempt
further stages. The platform may expose more than 8 tools overall, but these 8
must be available: `compute_daily_insights`, `query_health`, `query_raw_sql`,
`query_calendar`, `recall_memory`, `save_memory`, `write_llm_run`, and
`write_agent_run`.

---

## Step 0 — Anchor the date

Compute the target date **once** and reuse it:

```bash
scripts/anchor_env.sh /tmp/morning_briefing_dates.env
source /tmp/morning_briefing_dates.env
```

`YESTERDAY_ET` is the briefing's subject — all focus/career data refers to
yesterday. `YESTERDAY_DAY_OF_WEEK` must match `YESTERDAY_ET`.
`TODAY_ET` and `TODAY_DAY_OF_WEEK` describe the plan being written for today.
Never use today's day name as the analyzed-data day label.

`/tmp/morning_briefing_dates.env` contains only non-secret date/pipeline values.
Do not inline `MCP_API_KEY` in per-command or background-job text, and do not
write the API key to any local env file. Credentials must be exported once in
the active routine shell or provided by the routine environment.

---

## Stage -1 — Same-day replay guard

Before Stage 0, run a read-only same-day guard. This is the only data read
allowed before `compute_daily_insights`; it exists to prevent accidental
duplicate `llm_runs`, `agent_runs`, `agent_memory`, and Google Calendar writes.

Query recent same-day morning rows into `/tmp/morning_existing_runs.json`:

```bash
scripts/mcp.sh query_raw_sql "{
  \"database\":\"llm_db\",
  \"sql\":\"SELECT id::text AS id, run_type, pipeline_id, created_at, output_response->>'date' AS output_date, input_payload->>'today' AS input_today, output_response->>'target_verified' AS target_verified, output_response->>'primary_copies' AS primary_copies, output_response->>'events_written' AS events_written, NULL::text AS goal FROM llm_runs WHERE run_type IN ('rt_yesterday','email_daily','daily_briefing','calendar_write') AND (output_response->>'date' = '$TODAY_ET' OR input_payload->>'today' = '$TODAY_ET') UNION ALL SELECT id::text AS id, 'agent_runs' AS run_type, pipeline_id, created_at, NULL::text AS output_date, NULL::text AS input_today, NULL::text AS target_verified, NULL::text AS primary_copies, NULL::text AS events_written, goal FROM agent_runs WHERE goal ILIKE 'Morning briefing pipeline for $TODAY_ET%' ORDER BY created_at DESC\"
}" /tmp/morning_existing_runs.json
```

Then run:

```bash
python3 scripts/replay_guard.py \
  --today-et "$TODAY_ET" \
  --pipeline-id "$PIPELINE_ID" \
  --diagnostic-on-existing
```

Interpretation:

- `action=continue`: no same-day rows exist; continue the live pipeline.
- `action=diagnostic_replay`: same-day rows exist; continue all read, build,
  validation, calendar-planning, and memory-recall stages, but set
  `ROUTINE_MODE=dry_run`, `ALLOW_WRITES=0`, and `DIAGNOSTIC_REPLAY=1`.
- `action=calendar_only_repair`: stop the full pipeline and repair Calendar
  from the existing `daily_briefing` row only.
- `action=full_replay_explicit`: only possible when `ALLOW_FULL_REPLAY=1` was
  intentionally set; continue live and expect duplicate/new rows.

In `DIAGNOSTIC_REPLAY=1`, do not call `write_llm_run`, `write_agent_run`,
Google Calendar create-event, or `save_memory` directly. Shell write helpers may
be run only in dry-run mode so they emit would-call envelopes for inspection.

---

## Stage 0 — Compute daily insights (MANDATORY FIRST PIPELINE CALL)

```bash
scripts/mcp.sh compute_daily_insights "{\"date\":\"$YESTERDAY_ET\"}" /tmp/insights.json
```

The response contains `sections.anomalies`, `sections.parity`, `sections.career`.
**Quote their `headline` fields verbatim** in every downstream stage — do not
rephrase. Read them via targeted jq (e.g.
`jq -r '.data.sections.anomalies.headline' /tmp/insights.json`), never with a
full pretty-print.

**Do NOT run `query_raw_sql` for:** hourly focus, device splits, top-apps,
career email counts, or email classifications. `compute_daily_insights` is the
authoritative source for all of those. Only run raw SQL for data it doesn't
cover (health, workouts, non-career email, Spotify, calendar).

---

## Stage 0.5 — Gather supplementary data

**All 11 calls in one bash turn with `&` + `wait`.** Output always goes to
`/tmp/<name>.json`. Do not pretty-print — field extraction happens in
Stage 0.5b.

Before the parallel block, run `source /tmp/morning_briefing_dates.env` in the
same active shell. Do not inline `MCP_API_KEY`, `MCP_BASE_URL`, or repeated
`export ... &&` prefixes inside individual background jobs; job-control output
can leak command text and repeated inline exports are where prior env drift
started.

Apple Health sync lag: today's row often has HRV but `sleep_seconds` and `steps`
are not yet synced. Treat today's metrics as "if present, use; if null, skip".

```bash
scripts/mcp.sh query_health "{\"date\":\"$YESTERDAY_ET\",\"mode\":\"daily\"}" /tmp/health_yesterday.json &
scripts/mcp.sh query_health '{"mode":"workouts"}' /tmp/health_workouts.json &
scripts/mcp.sh query_health "{\"date\":\"$TODAY_ET\",\"mode\":\"daily\"}" /tmp/health_today.json &
scripts/mcp.sh query_raw_sql "{\"database\":\"health_db\",\"sql\":\"SELECT AVG(value)/3600.0 AS avg_hours FROM apple_health_daily_metrics_v2 WHERE metric_type='sleep_seconds' AND metric_date >= CURRENT_DATE - 7\"}" /tmp/sleep_baseline.json &
scripts/mcp.sh query_raw_sql "{\"database\":\"rescuetime_db\",\"sql\":\"SELECT device, ROUND(SUM(seconds)/3600.0, 2) AS total_hours, ROUND(SUM(CASE WHEN productivity >= 1 THEN seconds ELSE 0 END)/3600.0, 2) AS productive_hours, ROUND(SUM(CASE WHEN productivity <= -1 THEN seconds ELSE 0 END)/3600.0, 2) AS distracting_hours, ROUND(SUM(CASE WHEN productivity = 0 THEN seconds ELSE 0 END)/3600.0, 2) AS neutral_hours FROM rescuetime_activity_slice WHERE source_day = '$YESTERDAY_ET' GROUP BY device\"}" /tmp/rt_totals.json &
scripts/mcp.sh query_raw_sql "{\"database\":\"email_db\",\"sql\":\"SELECT subject, from_name, received_at AT TIME ZONE 'America/Toronto' AS received_et, email_type FROM emails WHERE (received_at AT TIME ZONE 'America/Toronto')::date = '$YESTERDAY_ET' ORDER BY received_at DESC\"}" /tmp/emails_daily.json &
scripts/mcp.sh query_calendar '{}' /tmp/calendar_blocks.json &
scripts/mcp.sh recall_memory '{"query":"productivity focus workout YouTube pattern goals","limit":10}' /tmp/agent_memory.json &
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT output_response FROM llm_runs WHERE run_type = 'weekly_trend' AND created_at >= NOW() - INTERVAL '8 days' ORDER BY created_at DESC LIMIT 1\"}" /tmp/weekly_trend.json &
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id, status, valid_from, valid_until, goals, enforcement FROM goal_policy_versions WHERE status = 'active' ORDER BY created_at DESC LIMIT 1\"}" /tmp/active_goal_policy.json &
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT key, content, category, created_at FROM agent_memory WHERE category IN ('goal','preference') ORDER BY created_at DESC LIMIT 20\"}" /tmp/active_goal_memory.json &
wait
echo "Stage 0.5 ok: 11 queries complete"
bash scripts/trim_payloads.sh
```

`trim_payloads.sh` warns if any context file remains over 50 KB after trimming.
Treat warnings as a synthesis-budget risk: inspect with targeted `jq` paths, not
full file dumps.

---

## Stage 0.5b — Single-pass field extraction

Immediately after `wait` (and the trim step), run the extraction script. It
reads all 11 `/tmp/*.json` files and writes `/tmp/data.json`. Stages 1–3 read only
`/tmp/data.json` — never re-open the individual files. Do not inspect
intermediate outputs.

```bash
python3 scripts/extract.py
```

The script is defensive against missing/null fields (Apple Health sync lag,
empty workout rows, no weekly_trend row yet, etc.). See `scripts/extract.py`
for the exact field contract it emits.

The active goal files are not optional context for synthesis. `extract.py`
folds them into `/tmp/data.json.goal_context`, including strict schedule
categories, artifact targets, lock cutoff, Windows distraction budget, memory
keys, and whether the career search is closed.

---

## Stage 0.75 — Calendar busy-window read

Before Stage 3 synthesis, derive Google Calendar busy windows for today's
planning window using bounded event search only. Do not call
`_get_availability` for this routine; the only scheduling question is whether
`primary` or the briefing calendar has occupied slots in the 7:00 AM-10:00 PM
ET planning window. Do not use `query_calendar`.

Raw Google Calendar search responses must never be printed. Save raw search
responses to `/tmp/calendar_search_primary.json` and
`/tmp/calendar_search_briefing.json`; the transcript may show only counts/status,
calendar IDs, and the bounded time window. If a tool or command cannot write the
raw response to a file without printing it, do not use that call path in the
scheduled routine.

Window:

- `time_min`: `$TODAY_ET` 7:00 AM America/Toronto as RFC3339 with offset
- `time_max`: `$TODAY_ET` 10:00 PM America/Toronto as RFC3339 with offset
- `calendar_ids`: `primary` and
  `ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com`

Write compact raw search responses to `/tmp/calendar_search_primary.json` and
`/tmp/calendar_search_briefing.json` when using the local file workflow. If an
auth/reauth/permission/scope-looking failure occurs, classify it and run one
bounded re-check before declaring Calendar blocked:

```bash
python3 scripts/calendar_search_policy.py \
  --primary /tmp/calendar_search_primary.json \
  --briefing /tmp/calendar_search_briefing.json \
  --out /tmp/calendar_search_policy.json
```

Persist a compact derived summary to `/tmp/calendar_busy.json`. The summary
should contain only: `status`, `calendar_ids`, `time_min`, `time_max`,
`busy_windows`, and `busy_window_count`.

Rules:

- Busy windows are hard constraints for `schedule_blocks`.
- Query only `primary` and the briefing calendar for the same 7:00 AM-10:00 PM
  ET window.
- Do not print or persist titles, locations, descriptions, attendees, URLs, or
  IDs in `/tmp/calendar_busy.json`. Persist only
  start/end/calendar_id/transparency-derived busy windows.
- Do not print raw event-search JSON to stdout. Redirect search stdout to the
  `/tmp/calendar_search_*.json` files and print only counts/status after
  `scripts/calendar_search_policy.py` and `/tmp/calendar_busy.json` are derived.
- Treat opaque events as busy. Treat transparent events as non-blocking unless
  they are on the briefing calendar, where they should be treated as busy to
  avoid piling briefing blocks onto that calendar.
- In live mode, create Calendar events when bounded event search succeeds.
- If bounded event search fails in live mode, skip Google Calendar create-event
  calls only after the one allowed auth-like re-check also fails, then write a
  `calendar_write` manifest with `busy_source=failed` and
  `calendar_auth_rechecks=1`. The scheduled Calendar watchdog should then
  repair missing events from the same `daily_briefing` row instead of rerunning
  Stage 0.

---

## Stage 1 — Write `rt_yesterday`

`scripts/payloads.py rt` builds the full rt_yesterday body from `/tmp/data.json`
(total/productive/distracting hours, focus_score, dod_delta_pp, device_split,
top_apps, hourly_focus, anomalies_headline, parity_headline) — all mechanical,
no AI judgment. `scripts/write_run.sh` wraps it in the `write_llm_run` envelope
and posts.

```bash
python3 scripts/payloads.py rt
scripts/write_run.sh rt_yesterday stage1_rt /tmp/rt_yesterday.json
# stdout prints the row id; capture if you want it for the final summary
```

---

## Stage 2 — Write `email_daily`

`scripts/payloads.py email` builds the full email_daily body from
`/tmp/data.json` (total_count, by_type, actionable_emails, career_summary
verbatim, career counts, 7d trend). Mechanical, no AI judgment.

```bash
python3 scripts/payloads.py email
scripts/write_run.sh email_daily stage2_email /tmp/email_daily.json
```

---

## Stage 3 — Write `daily_briefing` + `agent_run`

### 3a. Build the skeleton

`scripts/payloads.py briefing_base` builds a skeleton with the mechanical
fields already filled from `/tmp/data.json`:

- `date`, `day_of_week`, `sources_used`
- `career_pulse.*` (status/on_pace/pipeline_trend/today count/7d trend)
- `health_summary.*` (sleep, HRV, RHR, workout, recommendation)
- `focus_yesterday.*` (device_split, overall_focus_pct, best/worst hours, top_apps)
- `device_strategy.primary` and `device_strategy.rationale` (verbatim headline)

```bash
python3 scripts/payloads.py briefing_base "$TODAY_ET" "$TODAY_DAY_OF_WEEK" "$YESTERDAY_ET" "$YESTERDAY_DAY_OF_WEEK"
```

### 3b. Write the synthesis overlay

Write `/tmp/briefing_overlay.json` containing **only** the fields the AI
synthesizes. Everything else stays as the skeleton provided.

Required overlay shape:

```json
{
  "hero": {
    "headline": "Verb-led card action.",
    "reason": "Short time-rooted reason.",
    "urgency": "now|today|this_week",
    "secondary": "Optional short secondary line.",
    "action_type": "artifact|focus_correction|communication|calendar|recovery|admin|learning|career|health",
    "avoid": ["youtube.com"],
    "target": {"label": "Concrete target", "source": "rescuetime|health|calendar|email|goal_policy|cross-domain"},
    "success_condition": "Observable done condition.",
    "source_action_rank": 1,
    "evidence": [{"source": "rescuetime|health|calendar|email|goal_policy", "signal": "Specific numeric signal."}]
  },
  "morning_brief": {
    "headline": "One punchy sentence.",
    "context": "2-3 sentences on what yesterday sets up for today.",
    "energy_read": "HRV + sleep + workout → physiological forecast."
  },
  "reasoning": {
    "yesterday_lesson": "Single clearest lesson with numeric deltas.",
    "cross_domain_insight": "One connection across two sources."
  },
  "risk_flags": [
    {"risk": "Short label", "evidence": "Specific numbers.", "mitigation": "Concrete action."}
  ],
  "device_strategy": {
    "avoid_triggers": ["youtube.com"],
    "windows_allowed_for": "Specific conditions."
  },
  "schedule_blocks": [
    {
      "time_range": "9:00 AM - 10:00 AM",
      "activity": "Description",
      "device": "macbook | windows | none | any",
      "category": "project | deep_work | gym | meal | leisure | wind_down | admin | interview | applications | engineering_rebuild",
      "rationale": "Why this block at this time, grounded in yesterday's data."
    }
  ],
  "priority_actions": [
    {"rank": 1, "action": "What to do.", "urgency": "now|today|this_week", "source": "email|rescuetime|health|career|cross-domain|user_profile", "context": "Why this matters now."}
  ]
}
```

`hero` is **card copy**, not briefing copy. It must fit the ForYou hero/widget:

- `headline`: verb-led, 3-6 words, 44 chars max. Example: `Ship one concrete repo change`.
- `reason`: 1-2 short time/evidence-trigger sentences, 28 words / 160 chars max.
- `secondary`: 8 words / 56 chars max, or `null`.

Put detailed rationale in `priority_actions[].context`, not in `hero`.

Synthesis rules (these govern the overlay):

1. `reasoning.cross_domain_insight` **must connect two sources**. "YouTube was high" is not cross-domain. "YouTube 85 min Mac eroded the same window where VS Code could have run" is.
2. `risk_flags` entries **must include specific numbers**.
3. If `health_summary.sleep_hours_yesterday` differs from `sleep_7d_avg`
   by more than 1 hour, flag it in `risk_flags` or `morning_brief.energy_read`.
   (Read the already-filled values with
   `jq '.health_summary' /tmp/briefing_base.json`.)
4. `device_strategy.windows_allowed_for` must be specific, never generic.
5. `priority_actions` must have `rank`, `action`, `urgency`, `source`, and
   `context` fields tracing the data it came from. Do not emit
   `actionable_items`; `payloads.py` only maps that legacy field as a fallback.
6. `schedule_blocks` must contain **6–8 entries** covering today's core wake-to-sleep
   hours. Fewer than 6 blocks fails the run. Bias to fewer, wider blocks —
   pair adjacent activities (e.g. "deep_work + break" as one 2h block with a
   break note in rationale) instead of 20-minute fragments. **Synthesize fresh** —
   do NOT reuse blocks from `query_calendar` (those are yesterday's plan).
   Blocks must not overlap `/tmp/calendar_busy.json.busy_windows`.
7. `device_split[*].total_hours` is **authoritative** for device-magnitude
   claims. `top_apps[*].minutes` is only the single peak app per category,
   NOT the device total. When reasoning about "X% of yesterday was on Y
   device" or "app Z consumed the day", divide by `device_split` totals or
   the top-level `total_hours` — never by `top_apps.minutes`.
8. `schedule_blocks[*].category` must use the canonical steering taxonomy:
   `project`, `deep_work`, `gym`, `meal`, `leisure`, `wind_down`, `admin`,
   `interview`, `applications`, or `engineering_rebuild`. Do not invent
   `health`, `rest`, `career`, or `focus` categories.
9. The active goal policy is the action-selection authority when
   `/tmp/data.json.goal_context.active_goal` is present. For the current
   skill-building/productivity goal, all LLM-generated actions must first serve
   coding practice, artifact shipping, focus protection, system design study,
   or project/deep-work execution. Hero and rank-1 priority action must serve
   the active goal first unless there is a concrete hard blocker such as an
   urgent health, calendar, or communication deadline. Lower-ranked actions
   must either serve the active goal directly or support it by protecting focus,
   sleep, workouts, meals, or recovery. Do not promote stale career, generic
   email, or inbox cleanup above the active goal.
10. The active goal is skill-building when
    `/tmp/data.json.goal_context.active_goal` says so. Include at least one
    `project` or `deep_work` block for hands-on building/practice in a free
    window before the lock cutoff. If `artifact_target_min` is present, one
    pre-cutoff `project`/`deep_work` block should meet or exceed it.
11. If `/tmp/data.json.goal_context.career_search_closed=true` or
    `career_pulse.structured_pipeline_status="suspended"`, preserve the Stage 0
    career headline verbatim in diagnostic fields, but do **not** turn it into
    hero copy, `priority_actions`, `applications` blocks, `interview` blocks, or
    outbound job-search tasks. Demote stale career-stall signals to
    `risk_flags[]`, `reasoning.cross_domain_insight`, or source-quality caveats.

### 3c. Merge, validate, write

```bash
python3 scripts/payloads.py briefing_finalize /tmp/briefing_overlay.json
# Exits non-zero if hero, priority_actions, or schedule_blocks are invalid.
python3 scripts/validate_payloads.py --briefing /tmp/briefing.json
scripts/write_run.sh daily_briefing stage3_briefing /tmp/briefing.json
```

### 3d. Write narrative to `agent_runs`

Save the narrative to `/tmp/narrative.txt` using the iOS activity-feed format:

```
ACTIONABLE ITEMS
<numbered list>

---

FOCUS & PRODUCTIVITY
<device split, DoD comparison, hourly breakdown, top apps, productive:distraction ratio>

---

HEALTH
<today vs yesterday, workout detail, sleep reality check, fatigue signals>

---

EMAIL & CAREER
<total count, structured categories, career 7d trend, actionable emails only>

---

CROSS-SOURCE PATTERNS
<3-5 numbered insights connecting signals across sources, with specific numbers>

---

RECOMMENDATIONS
<3-5 specific actions tied to the patterns above>
```

Then submit. `write_agent.sh` adds the required iOS/read-model
classification metadata:

```json
[
  {
    "classification": {
      "run_origin": "manual_mcp",
      "execution_mode": "scheduled_claude",
      "agent_kind": "morning_briefing",
      "visibility": "user_visible"
    }
  }
]
```

The narrative must be clean plain text. Do **not** prefix it with a
`Response contract:` block.

```bash
AGENT_EXECUTION_MODE=scheduled_claude scripts/write_agent.sh "Morning briefing pipeline for $TODAY_ET ($TODAY_DAY_OF_WEEK), analyzing $YESTERDAY_ET ($YESTERDAY_DAY_OF_WEEK)" /tmp/narrative.txt
```

---

## Stage 3.5 — Write schedule_blocks to Google Calendar

This stage is mandatory. It writes today's `schedule_blocks` from `/tmp/briefing.json` to Google Calendar and then records a `calendar_write` manifest in `llm_runs`.

If `DIAGNOSTIC_REPLAY=1`, this stage is still mandatory but no-write: build the
calendar plan, count would-create / would-skip / would-conflict-skip entries,
write the manifest JSON locally, and report it as `would_write`. Do not call
Google Calendar create-event and do not persist the `calendar_write` row.

Calendar behavior is **busy-window-aware, create-only**:

- Do **not** call `gcal_list_events`.
- Do **not** call `gcal_delete_event`.
- Do **not** update existing calendar events.
- Do **not** create or invite attendee copies on `primary`. Calendar event
  creation targets only the briefing group calendar.
- Use bounded event search as the production busy-window source. Do not call
  `_get_availability`; event search gives the occupied slots needed here.
- Keep only compact busy-window data.
- `deleted_prior` is always `0`.
- Source of truth is only `/tmp/briefing.json.schedule_blocks`.

Calendar ID:

```text
ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com
```

Subject date is **today** (`$TODAY_ET`), not yesterday. The briefing analyzes `$YESTERDAY_ET`, but the calendar events are the plan for `$TODAY_ET`.

### Stage 3.5a — Create calendar payloads

Read `/tmp/briefing.json.schedule_blocks`. For each block:

- Parse `time_range` like `9:00 AM - 10:30 AM`.
- Skip blocks where parsing fails.
- Skip blocks with start hour before `7`.
- Skip blocks with end hour after `22`.
- Skip blocks with duration `<= 0`.
- Skip blocks that overlap `/tmp/calendar_busy.json.busy_windows`.
- Create one event per valid block.

Event fields:

- `calendarId`: `ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com`
- `attendees`: `[]`
- `self_attendance`: `omit`
- `add_google_meet`: `false`
- `summary`: `<emoji> <block.activity>`
- `description`:
  ```text
  Rationale: <block.rationale>
  Device: <block.device>
  Pipeline: <PIPELINE_ID>
  ```
- `start.dateTime`: `$TODAY_ET` plus parsed start time
- `end.dateTime`: `$TODAY_ET` plus parsed end time
- `start.timeZone`: `America/Toronto`
- `end.timeZone`: `America/Toronto`

Do not set `self_attendance=accepted`; that creates an accepted attendee copy
on `primary` in addition to the briefing-calendar event.

Emoji lookup by `category`:

| category | emoji |
|----------|-------|
| `deep_work` | 🎯 |
| `applications` | 💼 |
| `interview` | 🎤 |
| `project` | 🚀 |
| `engineering_rebuild` | 🛠️ |
| `gym` | 🏋️ |
| `meal` | 🍽️ |
| `admin` | 📋 |
| `leisure` | ☕ |
| `wind_down` | 🌙 |
| anything else | 📋 |

Create all valid events in parallel in one batch/turn, unless
`DIAGNOSTIC_REPLAY=1`. In diagnostic replay, stop after producing the
would-create list and counts. Do not loop sequentially through connector calls
if the environment supports parallel tool calls.

Track:

- `events_written`: count of successful creates
- `skipped`: count of skipped blocks
- `conflict_skipped`: count of blocks skipped for busy-window overlap
- `target_verified`: `yes` only when bounded read-back on the briefing group
  calendar finds the created event IDs in the same 7:00 AM-10:00 PM ET window
- `primary_copies`: count of created event IDs also found by bounded read-back
  on `primary`; expected value is `0`
- `deleted_prior`: always `0`

After create-event calls, do a bounded read-back on both the briefing group
calendar and `primary` for the same 7:00 AM-10:00 PM ET window. Do not print or
persist titles, descriptions, locations, attendees, URLs, or other event detail;
use only IDs/counts for verification. If any created event ID appears on
`primary`, report it as `primary_copies` and mark the run for inspection.

### Stage 3.5b — Write `calendar_write` manifest

After event creation, write a `calendar_write` row via `write_llm_run`. In
`DIAGNOSTIC_REPLAY=1`, write the same manifest to `/tmp/calendar_manifest.json`
and skip the `write_llm_run` call.

Required payload:

```json
{
  "mode": "calendar_write",
  "date": "<TODAY_ET>",
  "calendar_id": "ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com",
  "events_written": 0,
  "skipped": 0,
  "conflict_skipped": 0,
  "target_verified": "yes",
  "primary_copies": 0,
  "deleted_prior": 0,
  "busy_source": "search",
  "busy_window_count": 0,
  "busy_calendar_ids": ["primary", "<briefing calendar id>"],
  "write_policy": "busy_window_search_create_only_no_update_no_delete"
}
```

Use:

- `run_type`: `calendar_write`
- `model`: `none`
- `pipeline_id`: `$PIPELINE_ID`
- `step_label`: `stage3_5_calendar`
- `input_payload`: `{"date":"<TODAY_ET>","source":"routine","write_policy":"busy_window_search_create_only_no_update_no_delete"}`
- `output_response`: the manifest JSON above

Example HTTPS write shape:

```bash
calendar_manifest=$(jq -nc \
  --arg date "$TODAY_ET" \
  --arg calendar_id "ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com" \
  --argjson events_written "$EVENTS_WRITTEN" \
  --argjson skipped "$SKIPPED" \
  --argjson conflict_skipped "$CONFLICT_SKIPPED" \
  --arg target_verified "$TARGET_VERIFIED" \
  --argjson primary_copies "$PRIMARY_COPIES" \
  --arg busy_source "$BUSY_SOURCE" \
  --argjson busy_window_count "$BUSY_WINDOW_COUNT" \
  '{
    mode: "calendar_write",
    date: $date,
    calendar_id: $calendar_id,
    events_written: $events_written,
    skipped: $skipped,
    conflict_skipped: $conflict_skipped,
    target_verified: $target_verified,
    primary_copies: $primary_copies,
    deleted_prior: 0,
    busy_source: $busy_source,
    busy_window_count: $busy_window_count,
    busy_calendar_ids: ["primary", $calendar_id],
    write_policy: "busy_window_search_create_only_no_update_no_delete"
  }')

input_payload=$(jq -nc \
  --arg date "$TODAY_ET" \
  '{date: $date, source: "routine", write_policy: "busy_window_search_create_only_no_update_no_delete"}')

curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/write_llm_run" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d "$(jq -nc \
    --arg run_type "calendar_write" \
    --arg model "none" \
    --arg pipeline_id "$PIPELINE_ID" \
    --arg step_label "stage3_5_calendar" \
    --arg input_payload "$input_payload" \
    --arg output_response "$calendar_manifest" \
    '{
      run_type: $run_type,
      model: $model,
      pipeline_id: $pipeline_id,
      step_label: $step_label,
      input_payload: $input_payload,
      output_response: $output_response
    }')" \
  > /tmp/calendar_write.json

CALENDAR_WRITE_ID=$(jq -r '.data.id // empty' /tmp/calendar_write.json)
echo "Stage 3.5 ok: calendar_write row $CALENDAR_WRITE_ID, busy_source=$BUSY_SOURCE, busy_windows=$BUSY_WINDOW_COUNT, events_written=$EVENTS_WRITTEN, skipped=$SKIPPED, conflict_skipped=$CONFLICT_SKIPPED, target_verified=$TARGET_VERIFIED, primary_copies=$PRIMARY_COPIES, deleted_prior=0"
```

For diagnostic replay, replace the curl block with:

```bash
printf '%s\n' "$calendar_manifest" > /tmp/calendar_manifest.json
echo "Stage 3.5 diagnostic ok: would_write calendar_write, busy_source=$BUSY_SOURCE, busy_windows=$BUSY_WINDOW_COUNT, would_create=$EVENTS_WRITTEN, skipped=$SKIPPED, conflict_skipped=$CONFLICT_SKIPPED"
```

Rules:

- Never read existing calendar event details.
- Never delete calendar events.
- Never update calendar events.
- Never use `query_calendar` output as the source for event writes.
- Event-search fallback may read event search results, but only start/end and
  transparency may be persisted to `/tmp/calendar_busy.json` or used downstream.
- Do not skip the `calendar_write` manifest, even if zero events were written.
  In diagnostic replay, this means a local `/tmp/calendar_manifest.json` only.
- If busy-window search or calendar event creation fails, still write the
  manifest with the observed `busy_source`, `events_written`, `skipped`,
  `conflict_skipped`, `target_verified`, `primary_copies`, and an `errors`
  field.

---

## Stage 4 — Memory recall + save

`compute_daily_insights` returns up to 3 `memory_candidate` objects (one per
section: anomalies, parity, career), each shaped
`{content, category, key}` or `null`. `extract.py` already surfaced these
into `/tmp/data.json` as `mem_anom`, `mem_parity`, `mem_career`.
Never invent candidates. If a section returned `null`, skip it.

Execute this stage in **2 turns**.

### Turn 1 — Parallel recall (dedupe check)

For each non-null candidate, call `recall_memory` with the candidate's
`key` as the query. Run all non-null candidates in parallel in a single
turn.

```bash
for slot in anom parity career; do
  key=$(jq -r ".mem_${slot}.key // empty" /tmp/data.json)
  [ -z "$key" ] && continue
  recall_body=$(jq -nc --arg query "$key" '{query: $query, limit: 3}')
  scripts/mcp.sh recall_memory "$recall_body" /tmp/recall_${slot}.json &
done
wait
```

A candidate is a "match" and must be skipped in Turn 2 if its
`/tmp/recall_<slot>.json` contains a row whose stored key equals the
candidate's key. `pg_trgm` fuzzy match may return near-misses; only an exact
key match counts as a dedupe hit.

### Turn 2 — Parallel saves (skip matches)

For each candidate whose `/tmp/recall_*.json` does not contain a row with a
matching stored key, issue one `save_memory` call. Use the candidate's
`content`, `category`, and `key` verbatim.

If `DIAGNOSTIC_REPLAY=1`, do not run Turn 2 saves. Instead, build a compact
`would_save` list of non-matching candidate keys and report
`memory keys saved: none`.

```bash
for slot in anom parity career; do
  cand=$(jq -c ".mem_${slot}" /tmp/data.json)
  [ "$cand" = "null" ] && continue
  cand_key=$(jq -r '.key // empty' <<<"$cand")
  [ -z "$cand_key" ] && continue
  if jq -e --arg k "$cand_key" '.data[]? | select(.key == $k)' /tmp/recall_${slot}.json >/dev/null; then
    continue
  fi
  scripts/mcp.sh save_memory "$cand" /tmp/save_${slot}.json &
done
wait
```

After the save turn, collect saved keys from successful `/tmp/save_*.json`
responses. If no candidates were saved, final summary must say
`memory keys saved: none`.

Rules:
- Save at most 3 memories per run; the three candidate slots enforce this.
- Skip any candidate whose exact key already exists.
- Never retry `save_memory`; duplicates can result.
- Do not mirror memory candidates into `agent_runs`.

---

## Final summary

Emit one compact summary with:

- `pipeline_id`
- mode: `live`, `diagnostic_replay`, or `full_replay_explicit`
- if diagnostic replay, existing same-day row IDs from `/tmp/replay_guard.json`
- row IDs for `rt_yesterday`, `email_daily`, `daily_briefing`,
  `calendar_write`, and the narrative `write_agent_run` (or `would_write` for
  no-write diagnostic stages)
- memory keys saved, or `none`
- if diagnostic replay, memory keys that would have been saved
- `fatal_errors` from `scripts/run_log.sh summary`, or `[]`
- `recovered_errors` from `scripts/run_log.sh summary`, or `[]`

If Stage 4 did not complete, the run is a failure; say so explicitly.

Before writing the final summary, run:

```bash
scripts/run_log.sh summary
```

---

## Failure handling

- Any tool returning `{"status":"error",...}` → log one compact line and
  continue with the remaining stages. A failed Stage 1 does not block Stage 3.
- If a stage fails and then succeeds after a bounded recovery, record it with
  `scripts/run_log.sh recovered "<stage>" "<compact message>"`. Example:
  `scripts/run_log.sh recovered "Stage 0.5" "parallel env missing; reran after sourcing /tmp/morning_briefing_dates.env"`.
- If a stage remains blocked or a mandatory write/read cannot complete, record
  it with `scripts/run_log.sh fatal "<stage>" "<compact message>"`.
- Never retry a **write** tool: `save_memory`, `write_llm_run`, and
  `write_agent_run` create new rows on each successful call, so retries can
  produce duplicates.
- If Stage 4 is not complete, final summary must explicitly say the run failed.

---

## Date gotchas

- `rescuetime_activity_slice.ts_utc` and `bucket_start_utc` are **ET-as-UTC**.
  Cast `::timestamp` to strip the bogus offset before comparing against ET values.
- `rescuetime_activity_slice.source_day` is a plain date — safe without casts.
- `emails.received_at` is real UTC — `AT TIME ZONE 'America/Toronto'` works.
- `apple_health_daily_metrics_v2.metric_date` is a plain ET date.
