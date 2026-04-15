# Morning Briefing Runbook

Run once per morning. Produces:
- 3 rows in `llm_runs` (`rt_yesterday`, `email_daily`, `daily_briefing`)
- 1 row in `agent_runs` (plain-text narrative for iOS)
- 0–3 rows in `agent_memory` (only genuinely new patterns)

Every tool call uses `$MCP_BASE_URL` + `$MCP_API_KEY` — see
[`api-catalog.md`](api-catalog.md) for signatures.

---

## Step 0 — Anchor the date

Compute the target date **once** and reuse it:

```bash
TODAY_ET=$(TZ=America/Toronto date +%F)
YESTERDAY_ET=$(TZ=America/Toronto date -v-1d +%F 2>/dev/null || TZ=America/Toronto date -d 'yesterday' +%F)
PIPELINE_ID=$(uuidgen | tr 'A-Z' 'a-z')
DAY_OF_WEEK=$(TZ=America/Toronto date +%A)
```

`YESTERDAY_ET` is the briefing's subject — all focus/career data refers to
yesterday. `TODAY_ET` is only used when labelling today's schedule.

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

## Stage 0.5 — Gather supplementary data (in parallel if possible)

### Health — daily metrics and workouts

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_health" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d "{\"date\":\"$YESTERDAY_ET\",\"mode\":\"daily\"}"

curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_health" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{"mode":"workouts"}'
```

Get today's health too for HRV / resting HR delta:

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_health" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d "{\"date\":\"$TODAY_ET\",\"mode\":\"daily\"}"
```

### Non-career email (actionable items, newsletters)

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_raw_sql" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d "{\"database\":\"email_db\",\"sql\":\"SELECT e.subject, e.from_name, e.received_at AT TIME ZONE 'America/Toronto' AS received_et, e.email_type, s.category, s.priority FROM emails e LEFT JOIN structured_emails s ON e.message_id = s.message_id WHERE (e.received_at AT TIME ZONE 'America/Toronto')::date = '$YESTERDAY_ET' ORDER BY e.received_at DESC\"}"
```

### Calendar (briefing schedule_blocks)

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_calendar" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{}'
```

### Agent memory (continuity across runs)

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/recall_memory" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d '{"query":"productivity focus workout YouTube pattern goals","limit":10}'
```

### Recent weekly trend (optional, skip if missing)

```bash
curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/query_raw_sql" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $MCP_API_KEY" \
  -d "{\"database\":\"llm_db\",\"sql\":\"SELECT output_response FROM llm_runs WHERE run_type = 'weekly_trend' AND created_at >= NOW() - INTERVAL '8 days' ORDER BY created_at DESC LIMIT 1\"}"
```

---

## Stage 1 — Write `rt_yesterday`

Build a JSON object with these fields, using `sections.anomalies` + `sections.parity`:

- `total_hours`, `productive_hours`, `distracting_hours`
- `focus_score` ← `sections.anomalies.overall_focus_pct`
- `dod_delta_pp` ← `sections.anomalies.dod_delta_pp`
- `device_split` (from `sections.parity.top_productive.devices` /
  `top_distraction.devices` + any raw SQL if richer breakdown needed)
- `top_apps` (top_productive + top_distraction)
- `hourly_focus` (from `sections.anomalies.crashes` + `peaks`)
- `anomalies_headline` ← `sections.anomalies.headline` **verbatim**
- `parity_headline` ← `sections.parity.headline` **verbatim**

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

Build a JSON object:

- `total_count`, `by_type` breakdown
- `actionable_emails` (from non-career SQL — interviews, financial alerts, disputes)
- `career_summary` ← `sections.career.headline` **verbatim**
- `career_today_genuine` ← `sections.career.today_genuine`
- `career_today_noise` ← `sections.career.today_noise`
- `career_stall_since` ← `sections.career.stall_since`
- `career_days_since_last_genuine` ← `sections.career.days_since_last_genuine`
- `career_7d_trend` ← `sections.career.trend_14d` (last 7 entries)

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
    "hrv_ms": 0,
    "hrv_delta": "+/- N from prior day",
    "resting_hr_bpm": 0,
    "sleep_hours": 0,
    "sleep_note": "Cross-reference Apple Health sleep with late-night screen activity. Flag double-counts.",
    "steps": 0,
    "active_kcal": 0,
    "workout_status": "Last workout name, time, volume.",
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
      "time_range": "9:00-10:00 AM",
      "activity": "Description",
      "device": "macbook | windows | none | any",
      "category": "career | deep_work | health | rest | admin",
      "rationale": "Why this block at this time, grounded in yesterday's data."
    }
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
4. `health_summary.sleep_note` **must cross-reference RT** — raw Apple Health sleep double-counts.
5. `device_strategy.windows_allowed_for` must be specific, never generic.
6. `actionable_items` must have a `source` field tracing the data it came from.

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

## Stage 4 — Dispatch memory candidates (mechanical loop)

For each of the three insight sections (`anomalies`, `parity`, `career`):

1. If `section.memory_candidate` is `null` → **skip**.
2. Otherwise, `recall_memory` with `query = memory_candidate.key`:
   ```bash
   curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/recall_memory" \
     -H 'Content-Type: application/json' \
     -H "X-API-Key: $MCP_API_KEY" \
     -d "{\"query\":\"<memory_candidate.key>\",\"limit\":3}"
   ```
3. If the recall returns any row whose stored key matches → **skip** (already recorded).
4. Else, `save_memory` with the candidate's fields **verbatim** — do not rewrite `content`, do not mutate `key`:
   ```bash
   curl -s -X POST "$MCP_BASE_URL/api/mcp/tools/save_memory" \
     -H 'Content-Type: application/json' \
     -H "X-API-Key: $MCP_API_KEY" \
     -d '{"content":"<memory_candidate.content>","category":"<memory_candidate.category>","key":"<memory_candidate.key>"}'
   ```

Rules:
- Do not invent candidates — if Python returned `null`, the threshold wasn't met.
- Do not save more than 3 memories per run.
- The memory dispatch is **not** reflected in the `agent_runs` body. It happens alongside.

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
