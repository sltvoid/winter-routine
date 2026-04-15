# Morning Briefing Runbook

Run once per morning. Produces:
- 4 rows in `llm_runs` (`rt_yesterday`, `email_daily`, `daily_briefing`, `calendar_write`)
- 1 row in `agent_runs` (plain-text narrative for iOS)
- N Google Calendar events (one per schedule_block)
- 0–3 rows in `agent_memory` (only genuinely new patterns)

Every tool call uses `$MCP_BASE_URL` + `$MCP_API_KEY` — see
[`api-catalog.md`](api-catalog.md) for signatures.

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
   (Stage 0.5 queries, Stage 3.5 gcal creates, Stage 4 recalls).
5. **Stage 3.5 and Stage 4 are mandatory.** The run is not "done" until
   the `calendar_write` manifest row and the memory recall/save loop have
   both completed.

Budget target: reach Stage 3.5 with at least 60% of your turn budget remaining.

---

## Helper scripts

All repetitive logic lives in `scripts/`. Use these instead of writing
curl/Python inline. Every script is a thin, auditable wrapper.

| Script | Purpose |
|--------|---------|
| `scripts/mcp.sh <tool> <json> [out]` | POST to an MCP tool. Injects base URL + API key. `@file.json` body syntax supported. |
| `scripts/extract.py` | Stage 0.5b — reads the 8 `/tmp/*.json` responses, writes `/tmp/data.json`. |
| `scripts/payloads.py rt` | Stage 1 body → `/tmp/rt_yesterday.json` (mechanical). |
| `scripts/payloads.py email` | Stage 2 body → `/tmp/email_daily.json` (mechanical). |
| `scripts/payloads.py briefing_base <date> <dow>` | Stage 3 skeleton → `/tmp/briefing_base.json` (mechanical fields filled, synthesis fields empty). |
| `scripts/payloads.py briefing_finalize <overlay.json>` | Merge skeleton + AI overlay → `/tmp/briefing.json`. Exits non-zero if blocks < 8. |
| `scripts/write_run.sh <run_type> <step_label> <payload_file>` | Wraps payload in `write_llm_run` envelope and POSTs. Prints row id. |
| `scripts/write_agent.sh <goal> <narrative_file>` | Wraps text narrative in `write_agent_run` envelope and POSTs. Prints row id. |

Required env for all scripts: `MCP_BASE_URL`, `MCP_API_KEY`.
Required for `write_run.sh` / `write_agent.sh`: also `MODEL`, `PIPELINE_ID`,
and for `write_run.sh` optionally `YESTERDAY_ET`.

---

## Pre-flight — Read api-catalog.md

Before any curl, read `api-catalog.md` in this workspace. It documents every
response schema. Do **not** probe response structure with `jq 'keys'`, `jq '.[0]'`,
or `jq '.'` — if a field path is unclear, re-read the catalog. Structure-discovery
turns are pure waste and are the primary cause of mid-Stage-3.5 budget failure.

---

## Step 0 — Anchor the date

Compute the target date **once** and reuse it:

```bash
TODAY_ET=$(TZ=America/Toronto date +%F)
YESTERDAY_ET=$(TZ=America/Toronto date -v-1d +%F 2>/dev/null || TZ=America/Toronto date -d 'yesterday' +%F)
PIPELINE_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
DAY_OF_WEEK=$(TZ=America/Toronto date -v-1d +%A 2>/dev/null || TZ=America/Toronto date -d 'yesterday' +%A)
TODAY_DOW=$(TZ=America/Toronto date +%A)
```

`YESTERDAY_ET` is the briefing's subject — all focus/career data refers to
yesterday. `DAY_OF_WEEK` must match `YESTERDAY_ET` (used in the briefing's
`day_of_week` field). `TODAY_ET` and `TODAY_DOW` are only used in Stage 3.5
when writing today's schedule to Google Calendar.

---

## Stage 0 — Compute daily insights (MANDATORY FIRST CALL)

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

**All 8 calls in one bash turn with `&` + `wait`.** Output always goes to
`/tmp/<name>.json`. Do not pretty-print — field extraction happens in
Stage 0.5b.

Apple Health sync lag: today's row often has HRV but `sleep_seconds` and `steps`
are not yet synced. Treat today's metrics as "if present, use; if null, skip".

```bash
scripts/mcp.sh query_health "{\"date\":\"$YESTERDAY_ET\",\"mode\":\"daily\"}" /tmp/health_yesterday.json &
scripts/mcp.sh query_health '{"mode":"workouts"}' /tmp/health_workouts.json &
scripts/mcp.sh query_health "{\"date\":\"$TODAY_ET\",\"mode\":\"daily\"}" /tmp/health_today.json &
scripts/mcp.sh query_raw_sql "{\"database\":\"health_db\",\"sql\":\"SELECT AVG(value)/3600.0 AS avg_hours FROM apple_health_daily_metrics_v2 WHERE metric_type='sleep_seconds' AND metric_date >= CURRENT_DATE - 7\"}" /tmp/sleep_baseline.json &
scripts/mcp.sh query_raw_sql "{\"database\":\"email_db\",\"sql\":\"SELECT e.subject, e.from_name, e.received_at AT TIME ZONE 'America/Toronto' AS received_et, e.email_type, s.category, s.priority FROM emails e LEFT JOIN structured_emails s ON e.message_id = s.message_id WHERE (e.received_at AT TIME ZONE 'America/Toronto')::date = '$YESTERDAY_ET' ORDER BY e.received_at DESC\"}" /tmp/emails_daily.json &
scripts/mcp.sh query_calendar '{}' /tmp/calendar_blocks.json &
scripts/mcp.sh recall_memory '{"query":"productivity focus workout YouTube pattern goals","limit":10}' /tmp/agent_memory.json &
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT output_response FROM llm_runs WHERE run_type = 'weekly_trend' AND created_at >= NOW() - INTERVAL '8 days' ORDER BY created_at DESC LIMIT 1\"}" /tmp/weekly_trend.json &
wait
echo "Stage 0.5 ok: 8 queries complete"
```

---

## Stage 0.5b — Single-pass field extraction

Immediately after `wait`, run the extraction script. It reads all 8
`/tmp/*.json` files and writes `/tmp/data.json`. Stages 1–3 read only
`/tmp/data.json` — never re-open the individual files. Do not inspect
intermediate outputs.

```bash
python3 scripts/extract.py
```

The script is defensive against missing/null fields (Apple Health sync lag,
empty workout rows, no weekly_trend row yet, etc.). See `scripts/extract.py`
for the exact field contract it emits.

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
python3 scripts/payloads.py briefing_base "$YESTERDAY_ET" "$DAY_OF_WEEK"
```

### 3b. Write the synthesis overlay

Write `/tmp/briefing_overlay.json` containing **only** the fields the AI
synthesizes. Everything else stays as the skeleton provided.

Required overlay shape:

```json
{
  "morning_brief": {
    "headline": "One punchy sentence.",
    "context": "2-3 sentences on what yesterday sets up for today.",
    "energy_read": "HRV + sleep + workout → physiological forecast."
  },
  "reasoning": {
    "prediction": "If/then prediction tying actions to outcomes.",
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
      "category": "career | deep_work | health | rest | admin",
      "rationale": "Why this block at this time, grounded in yesterday's data."
    }
  ],
  "actionable_items": [
    {"item": "What to do.", "priority": "high|medium|low", "urgency": "now|today|this_week", "source": "email|rescuetime|health|cross-domain"}
  ]
}
```

Synthesis rules (these govern the overlay):

1. `reasoning.cross_domain_insight` **must connect two sources**. "YouTube was high" is not cross-domain. "YouTube 85 min Mac eroded the same window where VS Code could have run" is.
2. `risk_flags` entries **must include specific numbers**.
3. If `health_summary.sleep_hours_yesterday` differs from `sleep_7d_avg`
   by more than 1 hour, flag it in `risk_flags` or `morning_brief.energy_read`.
   (Read the already-filled values with
   `jq '.health_summary' /tmp/briefing_base.json`.)
4. `device_strategy.windows_allowed_for` must be specific, never generic.
5. `actionable_items` must have a `source` field tracing the data it came from.
6. `schedule_blocks` must contain **8–14 entries** covering today's wake-to-sleep
   hours. < 8 blocks fails the run. **Synthesize fresh** — do NOT reuse blocks
   from `query_calendar` (those are yesterday's plan).

### 3c. Merge, validate, write

```bash
python3 scripts/payloads.py briefing_finalize /tmp/briefing_overlay.json
# Exits non-zero + stderr warning if schedule_blocks < 8.
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

Then submit:

```bash
scripts/write_agent.sh "Morning briefing pipeline for $YESTERDAY_ET ($DAY_OF_WEEK)" /tmp/narrative.txt
```

---

## Stage 3.5 — Write schedule_blocks to Google Calendar

Use the **Google Calendar connector** (`gcal_list_events`, `gcal_delete_event`,
`gcal_create_event`). Calendar ID: **`ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com`** (the "Steph Main" calendar — do NOT pass the display name "Steph Main" as `calendarId`, it falls back to `primary` and writes to the wrong calendar). Subject: **today**
(`$TODAY_ET`), not yesterday.

**Execute this stage in exactly 3 turns** — anything more and you're out of
budget:

### Turn 1 — List + (in parallel) delete stale events

Call `gcal_list_events` for `$TODAY_ET` (00:00 to 23:59, `-04:00` EDT /
`-05:00` EST). In the **same turn** or the next, issue one parallel
`gcal_delete_event` call per returned event whose `description` starts with
`"Rationale:"`. Track the count as `deleted_prior`. Never delete events
whose description doesn't start with `Rationale:` — that marker is the only
safety barrier.

### Turn 2 — Create all schedule_block events in parallel

Source of truth: the `schedule_blocks` array in `/tmp/briefing.json` (the
briefing you just wrote in Stage 3). **Do NOT use the blocks from
`query_calendar`** — that response is the prior briefing. Re-read the JSON
you saved to `/tmp/briefing.json`.

Issue **one `gcal_create_event` call per entry in
`/tmp/briefing.json.schedule_blocks`, all in parallel in a single turn**.
Do not loop sequentially — that burns 12 turns for 12 events.

For each block, build the payload:

- `calendarId`: `"ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com"`
- `summary`: `"<emoji> <block.activity>"` (emoji lookup below)
- `description`: `"Rationale: <block.rationale>\nDevice: <block.device>"`
  — the `Rationale:` prefix is load-bearing for dedupe
- `start.dateTime`: `"<TODAY_ET>T<HH:MM>:00-04:00"` (EDT; use `-05:00` in EST)
- `end.dateTime`: same format
- `start.timeZone` / `end.timeZone`: `"America/Toronto"`

Parse `time_range` ("H:MM AM - H:MM PM") into 24h HH:MM. Skip any block where
parsing fails, start hour < 7, end hour > 22, or duration ≤ 0. Track
`events_written` and `skipped` counts.

Emoji lookup by `category`:

| category | emoji |
|----------|-------|
| `deep_work` | 🎯 |
| `career`, `applications`, `job_search` | 💼 |
| `interview` | 🎤 |
| `project` | 🚀 |
| `engineering_rebuild` | 🛠️ |
| `health`, `gym` | 🏋️ |
| `meal` | 🍽️ |
| `email` | 📧 |
| `admin`, `prep` | 📋 |
| `leisure`, `break`, `rest` | ☕ |
| `wind_down` | 🌙 |
| anything else | 📋 |

### Turn 3 — Write the `calendar_write` manifest

**This is mandatory.** Skipping it means the pipeline is not "done".

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/write_llm_run" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d "{
    \"run_type\":\"calendar_write\",
    \"model\":\"none\",
    \"pipeline_id\":\"$PIPELINE_ID\",
    \"step_label\":\"stage3_5_calendar\",
    \"input_payload\":\"{\\\"date\\\":\\\"$TODAY_ET\\\"}\",
    \"output_response\":\"{\\\"events_written\\\":<N>,\\\"skipped\\\":<N>,\\\"deleted_prior\\\":<N>}\"
  }"
```

Rules:
- **Never delete non-Winter events.** The description-prefix check is the only safety barrier. Do not broaden the filter.
- **DST awareness.** EDT is `-04:00`, EST is `-05:00`. November to mid-March → `-05:00`. Otherwise `-04:00`.
- **Idempotent.** Running Stage 3.5 twice in the same day produces the same calendar state (delete + re-create).

---

## Stage 4 — Dispatch memory candidates

**Execute in exactly 2 turns.** Read candidates from `/tmp/data.json` keys
`mem_anom`, `mem_parity`, `mem_career`. Skip any that are `null`.

### Turn 1 — Parallel recalls

For every non-null candidate, issue a `recall_memory` call in parallel,
all `&`-backgrounded, then `wait`:

```bash
scripts/mcp.sh recall_memory '{"query":"<key>","limit":3}' /tmp/recall_<slug>.json &
# ... one per candidate ...
wait
```

### Turn 2 — Parallel saves (skip matches)

For each candidate whose `/tmp/recall_*.json` does NOT contain a row with a
matching stored key, issue a `save_memory` call in parallel. Use the
candidate's `content`, `category`, and `key` **verbatim** — no rewrites.

```bash
scripts/mcp.sh save_memory "$(jq -c '{content, category, key}' <<<"$CANDIDATE_JSON")" &
wait
```

Rules:
- Never save > 3 memories per run.
- Do not invent candidates — if Stage 0 returned `null`, skip.
- Memory dispatch is not mirrored in `agent_runs`.

---

## Failure handling

- Any tool returning `{"status":"error",...}` → log the error, continue with
  the remaining stages. A failed Stage 1 does not block Stage 3.
- HTTP non-200 (e.g., 401, 404, 5xx) → retry once with a 5s delay. If still
  failing, exit with non-zero status so the Routine records a failure.
- Never retry a **write** tool more than once — `write_llm_run` and
  `write_agent_run` create new rows on each call, so retries produce
  duplicates.

---

## Date gotchas

- `rescuetime_activity_slice.ts_utc` and `bucket_start_utc` are **ET-as-UTC**.
  Cast `::timestamp` to strip the bogus offset before comparing against ET values.
- `rescuetime_activity_slice.source_day` is a plain date — safe without casts.
- `emails.received_at` is real UTC — `AT TIME ZONE 'America/Toronto'` works.
- `apple_health_daily_metrics_v2.metric_date` is a plain ET date.
