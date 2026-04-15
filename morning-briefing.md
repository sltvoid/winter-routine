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
INSIGHTS=$(curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/compute_daily_insights" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d "{\"date\":\"$YESTERDAY_ET\"}")
```

The response contains `sections.anomalies`, `sections.parity`, `sections.career`.
**Quote their `headline` fields verbatim** in every downstream stage — do not
rephrase.

**Do NOT run `query_raw_sql` for:** hourly focus, device splits, top-apps,
career email counts, or email classifications. `compute_daily_insights` is the
authoritative source for all of those. Only run raw SQL for data it doesn't
cover (health, workouts, non-career email, Spotify, calendar).

---

## Stage 0.5 — Gather supplementary data

**All 8 curls in one bash turn with `&` + `wait`.** Every curl gets `-o /tmp/<name>.json`.
Do not pretty-print any output — field extraction happens entirely in Stage 0.5b.

Apple Health sync lag: today's row often has HRV but `sleep_seconds` and `steps`
are not yet synced. Treat today's metrics as "if present, use; if null, skip".

```bash
# 1 — yesterday health metrics
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_health" \
  -H 'Content-Type: application/json' -H "X-API-Key: $MCP_API_KEY" \
  -d "{\"date\":\"$YESTERDAY_ET\",\"mode\":\"daily\"}" \
  -o /tmp/health_yesterday.json &

# 2 — workouts
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_health" \
  -H 'Content-Type: application/json' -H "X-API-Key: $MCP_API_KEY" \
  -d '{"mode":"workouts"}' \
  -o /tmp/health_workouts.json &

# 3 — today health (HRV delta)
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_health" \
  -H 'Content-Type: application/json' -H "X-API-Key: $MCP_API_KEY" \
  -d "{\"date\":\"$TODAY_ET\",\"mode\":\"daily\"}" \
  -o /tmp/health_today.json &

# 4 — sleep 7-day baseline
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_raw_sql" \
  -H 'Content-Type: application/json' -H "X-API-Key: $MCP_API_KEY" \
  -d "{\"database\":\"health_db\",\"sql\":\"SELECT AVG(value)/3600.0 AS avg_hours FROM apple_health_daily_metrics_v2 WHERE metric_type='sleep_seconds' AND metric_date >= CURRENT_DATE - 7\"}" \
  -o /tmp/sleep_baseline.json &

# 5 — non-career email
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_raw_sql" \
  -H 'Content-Type: application/json' -H "X-API-Key: $MCP_API_KEY" \
  -d "{\"database\":\"email_db\",\"sql\":\"SELECT e.subject, e.from_name, e.received_at AT TIME ZONE 'America/Toronto' AS received_et, e.email_type, s.category, s.priority FROM emails e LEFT JOIN structured_emails s ON e.message_id = s.message_id WHERE (e.received_at AT TIME ZONE 'America/Toronto')::date = '$YESTERDAY_ET' ORDER BY e.received_at DESC\"}" \
  -o /tmp/emails_daily.json &

# 6 — calendar (prior schedule_blocks — do NOT reuse these as today's plan)
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_calendar" \
  -H 'Content-Type: application/json' -H "X-API-Key: $MCP_API_KEY" \
  -d '{}' \
  -o /tmp/calendar_blocks.json &

# 7 — agent memory
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/recall_memory" \
  -H 'Content-Type: application/json' -H "X-API-Key: $MCP_API_KEY" \
  -d '{"query":"productivity focus workout YouTube pattern goals","limit":10}' \
  -o /tmp/agent_memory.json &

# 8 — weekly trend (optional; skip if data.length == 0)
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_raw_sql" \
  -H 'Content-Type: application/json' -H "X-API-Key: $MCP_API_KEY" \
  -d "{\"database\":\"llm_db\",\"sql\":\"SELECT output_response FROM llm_runs WHERE run_type = 'weekly_trend' AND created_at >= NOW() - INTERVAL '8 days' ORDER BY created_at DESC LIMIT 1\"}" \
  -o /tmp/weekly_trend.json &

wait
echo "Stage 0.5 ok: 8 queries complete"
```

---

## Stage 0.5b — Single-pass field extraction

Immediately after `wait`, run **one Python script** that reads all 8 `/tmp/*.json`
files and writes `/tmp/data.json`. All stages 1–3 read only `/tmp/data.json` —
never re-open the individual files. Do not inspect intermediate outputs.

```python
# python3 /tmp/extract_all.py  (write this script, run it, done)
import json, collections

ins = json.load(open('/tmp/insights.json'))['data']['sections']
anom, par, car = ins['anomalies'], ins['parity'], ins['career']

def metric(path, key):
    return next((r['value'] for r in json.load(open(path))['data']
                 if r['metric_type'] == key), None)

sleep_s   = metric('/tmp/health_yesterday.json', 'sleep_seconds')
hrv_y     = metric('/tmp/health_yesterday.json', 'hrv_ms')
rhr       = metric('/tmp/health_yesterday.json', 'resting_heart_rate_bpm')
hrv_t     = metric('/tmp/health_today.json',     'hrv_ms')
wkt_data  = json.load(open('/tmp/health_workouts.json'))['data']
slp_avg   = json.load(open('/tmp/sleep_baseline.json'))['data'][0]['avg_hours']
em        = json.load(open('/tmp/emails_daily.json'))['data']

wkt = wkt_data[0] if wkt_data else {}

out = {
    # anomalies
    'anom_headline':   anom['headline'],
    'focus_pct':       anom['overall_focus_pct'],
    'dod_delta':       anom['dod_delta_pp'],
    'crashes':         anom['crashes'],
    'peaks':           anom['peaks'],
    # parity
    'parity_headline': par['headline'],
    'top_prod':        par['top_productive'],
    'top_dist':        par['top_distraction'],
    'baseline_7d_min': par['baseline_7d_avg_min'],
    # career
    'career_headline': car['headline'],
    'career_genuine':  car['today_genuine'],
    'career_noise':    car['today_noise'],
    'career_stall':    car['stall_since'],
    'career_days':     car['days_since_last_genuine'],
    'career_trend':    car.get('trend_14d', []),
    # health
    'sleep_h':         round((sleep_s or 0) / 3600, 1),
    'sleep_7d_avg':    round(slp_avg, 1),
    'hrv_yesterday':   hrv_y,
    'hrv_today':       hrv_t,
    'resting_hr':      rhr,
    'workout':         wkt,
    # email
    'email_total':     len(em),
    'email_by_type':   dict(collections.Counter(e.get('email_type','unknown') for e in em)),
    # memory candidates (may be null)
    'mem_anom':        anom.get('memory_candidate'),
    'mem_parity':      par.get('memory_candidate'),
    'mem_career':      car.get('memory_candidate'),
}
json.dump(out, open('/tmp/data.json', 'w'))
print("extraction ok")
```

---

## Stage 1 — Write `rt_yesterday`

**Source:** `/tmp/data.json` (written by Stage 0.5b). Do not re-read
`/tmp/insights.json` or any individual health/email file.

Build a JSON object with these fields:

- `total_hours`, `productive_hours`, `distracting_hours` ← derive from `top_prod` + `top_dist` minutes
- `focus_score` ← `data.focus_pct`
- `dod_delta_pp` ← `data.dod_delta`
- `device_split` ← from `data.top_prod.devices` / `data.top_dist.devices`
- `top_apps` ← `data.top_prod` + `data.top_dist`
- `hourly_focus` ← `data.crashes` + `data.peaks`
- `anomalies_headline` ← `data.anom_headline` **verbatim**
- `parity_headline` ← `data.parity_headline` **verbatim**

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/write_llm_run" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d "{
    \"run_type\":\"rt_yesterday\",
    \"model\":\"$MODEL\",
    \"pipeline_id\":\"$PIPELINE_ID\",
    \"step_label\":\"stage1_rt\",
    \"input_payload\":\"{\\\"date\\\":\\\"$YESTERDAY_ET\\\"}\",
    \"output_response\":\"<rt_yesterday JSON, escaped>\"
  }"
```

---

## Stage 2 — Write `email_daily`

**Source:** `/tmp/data.json` only.

Build a JSON object:

- `total_count` ← `data.email_total`
- `by_type` ← `data.email_by_type`
- `actionable_emails` ← filter `data.email_by_type` for non-marketing/non-newsletter types
- `career_summary` ← `data.career_headline` **verbatim**
- `career_today_genuine` ← `data.career_genuine`
- `career_today_noise` ← `data.career_noise`
- `career_stall_since` ← `data.career_stall`
- `career_days_since_last_genuine` ← `data.career_days`
- `career_7d_trend` ← last 7 entries of `data.career_trend`

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/write_llm_run" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d "{
    \"run_type\":\"email_daily\",
    \"model\":\"$MODEL\",
    \"pipeline_id\":\"$PIPELINE_ID\",
    \"step_label\":\"stage2_email\",
    \"input_payload\":\"{\\\"date\\\":\\\"$YESTERDAY_ET\\\"}\",
    \"output_response\":\"<email_daily JSON, escaped>\"
  }"
```

---

## Stage 3 — Write `daily_briefing` + `agent_run`

### 3a. Build the briefing JSON

Use the schema below. Every field is required unless marked optional.
Thin briefings (just `summary` + `schedule_blocks`) are **not acceptable** —
the iOS app renders every field.

```json
{
  "date": "<YESTERDAY_ET>",
  "day_of_week": "<DAY_OF_WEEK>",
  "sources_used": ["rescuetime", "email", "health", "calendar"],

  "morning_brief": {
    "headline": "One punchy sentence — the single most important thing about today.",
    "context": "2-3 sentences. What happened yesterday that sets up today?",
    "energy_read": "HRV + sleep + workout → physiological forecast for today."
  },

  "reasoning": {
    "prediction": "If/then prediction tying actions to outcomes.",
    "yesterday_lesson": "The single clearest lesson — quote numeric deltas.",
    "cross_domain_insight": "One connection across two sources (workout→focus, sleep→HRV, YouTube→career pace)."
  },

  "risk_flags": [
    {
      "risk": "Short label",
      "evidence": "Specific numbers.",
      "mitigation": "Concrete action."
    }
  ],

  "career_pulse": {
    "status": "On pace | At risk | Stalled | Quiet",
    "on_pace": true,
    "pipeline_trend": "<quote sections.career.headline verbatim>",
    "career_emails_today": 0,
    "career_emails_7d_trend": [{"day": "YYYY-MM-DD", "count": 0}],
    "structured_pipeline_status": "active | suspended"
  },

  "health_summary": {
    "sleep_hours_yesterday": 0,
    "sleep_7d_avg": 0,
    "hrv_ms": 0,
    "hrv_ms_today": 0,
    "resting_hr_bpm": 0,
    "workout_status": "Last workout name, date, duration, sets, volume.",
    "workout_recommendation": "green_light | rest | active_recovery"
  },

  "focus_yesterday": {
    "date": "<YESTERDAY_ET>",
    "device_split": [
      {"device": "macbook", "total_hours": 0, "productive_hours": 0, "distracting_hours": 0, "focus_pct": 0}
    ],
    "overall_focus_pct": 0,
    "productive_ratio": "N:1",
    "best_hours": "from sections.anomalies.peaks",
    "worst_hours": "from sections.anomalies.crashes + sections.parity.top_distraction",
    "gap": "Any hours with no RT data",
    "top_apps": [
      {"activity": "app", "minutes": 0, "productivity": 2, "device": "macbook"}
    ]
  },

  "device_strategy": {
    "primary": "macbook",
    "rationale": "<quote sections.parity.headline verbatim>",
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
    // MANDATORY: 8–14 total blocks covering wake (~7am) to sleep (~10pm).
    // Empty array = run failure. Do NOT copy schedule_blocks from
    // query_calendar's response — that is the PRIOR briefing's blocks.
    // Synthesize fresh today's plan based on yesterday's focus data + health.
  ],

  "actionable_items": [
    {
      "item": "What to do.",
      "priority": "high | medium | low",
      "urgency": "now | today | this_week",
      "source": "email | rescuetime | health | cross-domain"
    }
  ]
}
```

Synthesis rules:

1. `reasoning.cross_domain_insight` **must connect two sources**. "YouTube was high" is not cross-domain. "YouTube 85 min Mac eroded the same window where VS Code could have run" is.
2. `risk_flags` entries **must include specific numbers**.
3. `career_pulse.on_pace` must be set explicitly (true/false).
4. `health_summary` fields come **verbatim from `/tmp/data.json`** (keys:
   `sleep_h`, `sleep_7d_avg`, `hrv_yesterday`, `hrv_today`, `resting_hr`, `workout`)
   — never fabricate. If `sleep_h` differs from `sleep_7d_avg`
   by more than 1 hour, flag it in `risk_flags` or `morning_brief.energy_read`.
5. `device_strategy.windows_allowed_for` must be specific, never generic.
6. `actionable_items` must have a `source` field tracing the data it came from.
7. `schedule_blocks` must contain **8–14 entries** covering today's wake-to-sleep
   hours. Empty or < 8 blocks fails the run. **Synthesize fresh** — do NOT
   reuse the blocks returned by `query_calendar` (those are yesterday's plan).

### 3b-pre. Validate the briefing

Before writing, save the briefing to `/tmp/briefing.json` and check:

```bash
BLOCKS=$(jq '.schedule_blocks | length' /tmp/briefing.json)
if [ "$BLOCKS" -lt 8 ]; then
  echo "FAIL: schedule_blocks has only $BLOCKS entries (need ≥8)" >&2
  exit 1
fi
jq -e '.day_of_week and .date and (.schedule_blocks | length >= 8)
  and (.actionable_items | length >= 3) and (.morning_brief.headline)
  and (.reasoning.cross_domain_insight)' /tmp/briefing.json > /dev/null \
  || { echo "FAIL: briefing validation"; exit 1; }
```

### 3b. Write `daily_briefing` to llm_runs

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/write_llm_run" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d "{
    \"run_type\":\"daily_briefing\",
    \"model\":\"$MODEL\",
    \"pipeline_id\":\"$PIPELINE_ID\",
    \"step_label\":\"stage3_briefing\",
    \"input_payload\":\"{\\\"date\\\":\\\"$YESTERDAY_ET\\\"}\",
    \"output_response\":\"<briefing JSON, escaped>\"
  }"
```

### 3c. Write narrative to `agent_runs`

The narrative uses the proactive-agent text format (see section headers below).
This is what the iOS activity feed shows.

```
ACTIONABLE ITEMS
<numbered list>

---

FOCUS & PRODUCTIVITY
<device split, DoD comparison, hourly breakdown, top apps, productive:distraction ratio>

---

HEALTH
<today vs yesterday table, workout detail, sleep reality check, fatigue signals>

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

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/write_agent_run" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d "{
    \"goal\":\"Morning briefing pipeline for $YESTERDAY_ET ($DAY_OF_WEEK)\",
    \"final_response\":\"<narrative, escaped>\",
    \"model\":\"$MODEL\",
    \"pipeline_id\":\"$PIPELINE_ID\"
  }"
```

---

<!--
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
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/write_llm_run"
-H 'Content-Type: application/json'
-H "X-API-Key: $MCP_API_KEY"
-d "{
"run_type":"calendar_write",
"model":"none",
"pipeline_id":"$PIPELINE_ID",
"step_label":"stage3_5_calendar",
"input_payload":"{\"date\":\"$TODAY_ET\"}",
"output_response":"{\"events_written\":<N>,\"skipped\":<N>,\"deleted_prior\":<N>}"
}"

Rules:
- **Never delete non-Winter events.** The description-prefix check is the only safety barrier. Do not broaden the filter.
- **DST awareness.** EDT is `-04:00`, EST is `-05:00`. November to mid-March → `-05:00`. Otherwise `-04:00`.
- **Idempotent.** Running Stage 3.5 twice in the same day produces the same calendar state (delete + re-create).
-->
---

### Turn 2 — Parallel saves (skip matches)

For each candidate whose `/tmp/recall_*.json` does NOT contain a row with a
matching stored key, issue a `save_memory` call in parallel. Use the
candidate's `content`, `category`, and `key` **verbatim** — no rewrites.

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
