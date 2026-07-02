# Morning Briefing — Reference (cold path)

Material moved out of `morning-briefing.md`'s per-run hot path (2026-07-02
token diet). **Scheduled runs do not read this file** unless a stage
explicitly fails or the run is on a full-calendar path (Codex canary, manual
repair). Content is moved verbatim from the runbook of record; the hot file
holds a pointer per section.

---

## Helper scripts (full table)

All repetitive logic lives in `scripts/`. Use these instead of writing
curl/Python inline. Every script is a thin, auditable wrapper.

| Script | Purpose |
|--------|---------|
| `scripts/mcp.sh <tool> <json> [out]` | POST to an MCP tool. Injects base URL + API key. `@file.json` body syntax supported. |
| `scripts/smoke_test.sh` | Mandatory scheduled-routine preflight that calls `/api/mcp/list_tools` and verifies the required daily-briefing tools. |
| `scripts/anchor_env.sh [/tmp/morning_briefing_dates.env]` | Step 0 — computes date anchors once and writes only non-secret date/pipeline exports for later shell turns. |
| `scripts/trim_payloads.sh` | Stage 0.5c — best-effort jq trimming of `/tmp/calendar_blocks.json`, `/tmp/agent_memory.json`, `/tmp/weekly_trend.json` to cut input tokens when the AI re-reads them for synthesis context. |
| `scripts/extract.py` | Stage 0.5b — reads the Stage 0.5 `/tmp/*.json` responses, writes `/tmp/data.json`. |
| `scripts/payloads.py rt` | Stage 1 body → `/tmp/rt_yesterday.json` (mechanical). |
| `scripts/payloads.py email` | Stage 2 body → `/tmp/email_daily.json` (mechanical). |
| `scripts/payloads.py briefing_base <today> <today_dow> <yesterday> <yesterday_dow>` | Stage 3 skeleton → `/tmp/briefing_base.json` (mechanical fields filled, synthesis fields empty). |
| `scripts/payloads.py briefing_finalize <overlay.json>` | Merge skeleton + AI overlay → `/tmp/briefing.json`. Exits non-zero if blocks < 6. |
| `scripts/validate_payloads.py` | Validates current `daily_briefing` and `agent_runs` contract before writes. |
| `scripts/write_run.sh <run_type> <step_label> <payload_file>` | Wraps payload in `write_llm_run` envelope. Defaults to dry-run; live writes require `ROUTINE_MODE=live ALLOW_WRITES=1`. |
| `scripts/write_agent.sh <goal> <narrative_file>` | Wraps text narrative in `write_agent_run` envelope with classification metadata. Defaults to dry-run; live writes require `ROUTINE_MODE=live ALLOW_WRITES=1`. |
| `scripts/run_log.sh recovered\|fatal\|summary` | Records recovered and fatal errors as compact JSONL and emits final `fatal_errors` / `recovered_errors` arrays. |
| `scripts/calendar_plan.py` | Parses `/tmp/briefing.json.schedule_blocks` into a create/skip plan (used by manifest-only and full-create paths). |
| `scripts/calendar_busy_from_search.py` | Derives `/tmp/calendar_busy.json` from raw bounded event-search files. |
| `scripts/calendar_search_policy.py` | Classifies auth-like calendar failures and gates the one allowed re-check. |
| `scripts/completion_check.py` | Final read-only verifier — asserts the expected row set landed exactly once. |
| `scripts/replay_guard.py` | Stage -1 — decides continue / complete_missing / diagnostic_replay from same-day rows. |

---

## Stage 0.75 — Calendar busy-window read (FULL-CALENDAR PATHS ONLY)

> Scheduled Claude routine runs are **manifest-only** (trigger-body Calendar
> Policy) and skip this stage entirely — see the hot runbook. This section is
> the full busy-window procedure for create-capable paths (Codex canary,
> manual repair).

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

## Stage 3.5a — Full Google Calendar event creation (FULL-CALENDAR PATHS ONLY)

> Manifest-only scheduled runs create zero events — see the hot runbook's
> Stage 3.5. This is the create procedure for create-capable paths.

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
- `actual_calendar_creates`: count of actual Google Calendar create calls that succeeded
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

---

## Signoff

- **2026-07-02 ET · Claude (Fable 5, operator session)** — Created: cold-path
  extraction from morning-briefing.md (helper-script table, Stage 0.75
  busy-window procedure, Stage 3.5a full event creation), moved verbatim.
  Verified: repo suite green post-split; contract tests repointed where their
  pinned phrases moved here. (Latest entry only — history in git.)
