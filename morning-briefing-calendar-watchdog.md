# Morning Briefing Calendar Watchdog

Purpose: make the morning briefing Calendar side effect reliable. This
automation runs after the daily morning briefing and repairs missing Google
Calendar events from the already-written `daily_briefing` row.

This is a **Calendar-only watchdog**. It must not rerun Stage 0, regenerate the
briefing, or duplicate `rt_yesterday`, `email_daily`, `daily_briefing`, or
`agent_runs` rows.

## When To Run

Schedule this watchdog shortly after the daily briefing, and again later if the
first watchdog is blocked by Google Calendar auth:

- First pass: 10-15 minutes after the morning briefing automation.
- Second pass: 45-60 minutes after the morning briefing automation.

The watchdog is idempotent: it performs bounded Calendar reads, compares the
briefing schedule against existing target-calendar events, and creates only
missing blocks.

## Hard Rules

1. Work only in `/Users/steventa/Documents/CodingJunk/Winter-Routine`.
2. Read this file and `morning-briefing-calendar-repair.md` before running.
3. Use the latest existing `daily_briefing` row for `TODAY_ET` unless a
   specific `DAILY_BRIEFING_ID` is provided.
4. Do not call `compute_daily_insights`.
5. Do not write `rt_yesterday`, `email_daily`, `daily_briefing`, `agent_runs`,
   memory, notes, or raw SQL mutations.
6. Do not update or delete existing Calendar events.
7. Do not call `_get_availability`.
8. Use only Google Calendar plugin tools for Calendar search, create, and
   read-back verification.
9. Always write exactly one `calendar_write` manifest row, including no-op and
   blocked runs.
10. Calendar event titles must equal the schedule block `activity` text.
11. Every create call must use `attendees=[]`, `self_attendance=omit`, and
    `add_google_meet=false`.

## Environment

Anchor once:

```bash
export TODAY_ET="$(TZ=America/Toronto date +%F)"
export PIPELINE_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
export MODEL="${MODEL:-gpt-5.5}"
export ROUTINE_MODE=live
export BRIEFING_CALENDAR_ID="ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com"
export TIMEZONE="America/Toronto"
```

Planning window:

- `time_min`: `$TODAY_ET 7:00 AM America/Toronto`
- `time_max`: `$TODAY_ET 10:00 PM America/Toronto`

## Source Rows

Read the latest same-day briefing:

```sql
SELECT id, pipeline_id, output_response, created_at
FROM llm_runs
WHERE run_type = 'daily_briefing'
  AND output_response->>'date' = '<TODAY_ET>'
ORDER BY created_at DESC
LIMIT 1;
```

If there is no same-day briefing, write a zero-create `calendar_write` manifest
with `status=blocked_no_daily_briefing`, then stop.

Read recent same-day Calendar manifests:

```sql
SELECT id, pipeline_id, output_response, created_at
FROM llm_runs
WHERE run_type = 'calendar_write'
  AND output_response->>'date' = '<TODAY_ET>'
ORDER BY created_at DESC
LIMIT 5;
```

Use the most recent incomplete or failed row as `repair_of_calendar_write_id`
when present. Do not treat a prior success as sufficient proof by itself; the
watchdog must still search the target calendar and run coverage detection.

Claude manifest-only rows are intentionally incomplete for Calendar creation.
Treat a same-day `calendar_write` row as repairable/incomplete when any of
these are true:

- `target_verified=skipped_manifest_only`
- `actual_calendar_creates=0`
- `busy_source=calendar_search_skipped_for_token_budget`
- `busy_source=skipped_for_token_budget`

## Bounded Search

Search only:

- `primary`
- `$BRIEFING_CALENDAR_ID`

Use `mcp__codex_apps__google_calendar._search_events` with explicit
`time_min`, `time_max`, and `timezone_str=America/Toronto`.

If using local files, save compact raw results as:

- `/tmp/calendar_search_primary.json`
- `/tmp/calendar_search_briefing.json`

Classify the pair:

```bash
python3 scripts/calendar_search_policy.py \
  --primary /tmp/calendar_search_primary.json \
  --briefing /tmp/calendar_search_briefing.json \
  --out /tmp/calendar_search_policy.json
```

If the policy says `retry_recommended=true`, run exactly one bounded re-check on
both calendars with the same window and classify again.

If either search still fails, write a `calendar_write` manifest with:

- `status=blocked_search_failed`
- `repair=true`
- `busy_source=failed`
- `events_written=0`
- `target_verified=no`
- `primary_copies=0`
- `calendar_auth_rechecks=1` when the bounded re-check was used
- compact error text

## Work Container Rule

If the target day contains a same-day primary-calendar event titled `Work`,
`Office`, `Focus`, `Deep Work`, or similar lasting 4+ hours, treat it as
schedulable work capacity, not as a blocking conflict. The watchdog may place
briefing target events inside that container.

Hard conflicts remain meetings, appointments, travel, and personal commitments.
Do not skip or block a project/deep-work briefing event solely because it falls
inside a long work container.

## Busy Window Derivation

After successful bounded search, derive compact busy windows before planning
creates:

```bash
python3 scripts/calendar_busy_from_search.py \
  --primary /tmp/calendar_search_primary.json \
  --briefing /tmp/calendar_search_briefing.json \
  --out /tmp/calendar_busy.json
```

This helper enforces the split between Claude and Codex:

- Claude has already chosen the day's candidate work in
  `daily_briefing.schedule_blocks[]`.
- Codex decides only whether each candidate can be placed safely.
- Primary-calendar hard events block creation.
- Long primary-calendar Work/Office/Focus containers are available capacity and
  do not block creation.
- Existing briefing-calendar events block duplicates.
- The helper emits only start/end/calendar/count fields; do not print raw event
  details.

## Coverage Detection

Compare the source briefing schedule with the briefing target calendar to get
coverage counts:

```bash
python3 scripts/calendar_coverage.py \
  --briefing /tmp/briefing.json \
  --briefing-search /tmp/calendar_search_briefing.json \
  --skip-started \
  --summary-out /tmp/calendar_coverage_summary.json \
  --create-args-out /tmp/calendar_missing_create_args_private.json
```

The `--skip-started` guard prevents a late watchdog from creating events whose
candidate window has already started or elapsed. Such entries should be counted
as skipped with reason `past_or_started`, not created retroactively.

If `calendar_coverage.py` reports `status=noop`, all valid briefing blocks are
already present. Write a no-op `calendar_write` manifest with
`target_verified=yes`, `events_written=0`, and `primary_copies=0`, then stop.

If it reports `status=missing`, run conflict-aware planning against the derived
busy windows and use that output for create calls:

```bash
python3 scripts/calendar_plan.py \
  --briefing /tmp/briefing.json \
  --busy /tmp/calendar_busy.json \
  --skip-started \
  --plan-out /tmp/calendar_create_plan.json \
  --summary-out /tmp/calendar_plan_summary.json \
  --create-args-out /tmp/calendar_create_args_private.json
```

Create each event in `/tmp/calendar_create_args_private.json` using the Google
Calendar plugin. Do not create events from
`/tmp/calendar_missing_create_args_private.json`; that file is coverage
evidence only. Do not print full create responses; keep only created event IDs
in local scratch state for read-back verification.

Manifest counts should use:

- `valid_block_count` and `already_present` from
  `/tmp/calendar_coverage_summary.json`
- `skipped`, `conflict_skipped`, and `past_or_started_skipped` from
  `/tmp/calendar_plan_summary.json`
- `events_written` from successful Google Calendar create calls

## Read-Back Verification

After creates, search the same bounded window on:

- `$BRIEFING_CALENDAR_ID`
- `primary`

Verify by created event IDs only:

- `target_verified=yes` only when every created event ID is found on the
  briefing calendar.
- `primary_copies` is the count of created event IDs found on `primary`.
- Expected `primary_copies=0`.

Do not print titles, descriptions, locations, attendees, URLs, or other event
details in the final report.

## Manifest

Always write one `calendar_write` row through
`mcp__data_platform__.write_llm_run`.

Use:

- `run_type=calendar_write`
- `model=none`
- `step_label=calendar_watchdog`
- `pipeline_id=$PIPELINE_ID`

Manifest fields:

- `mode=calendar_write`
- `date`
- `repair=true`
- `watchdog=true`
- `repair_source_daily_briefing_id`
- `repair_of_calendar_write_id` when known
- `busy_source`
- `busy_window_count`
- `busy_calendar_ids`
- `calendar_auth_rechecks`
- `valid_block_count`
- `already_present`
- `events_written`
- `deleted_prior=0`
- `skipped`
- `conflict_skipped`
- `target_verified`
- `primary_copies`
- `errors`

## Output

Return only this compact shape:

```text
morning_briefing_calendar_watchdog
status=<ok|noop|blocked_no_daily_briefing|blocked_search_failed|needs_review>
pipeline_id=<uuid>
daily_briefing_id=<id|none>
calendar_write_id=<id|none>
repair_of_calendar_write_id=<id|none>
date=<YYYY-MM-DD>
busy_source=<search|failed>
busy_windows=<count>
calendar_auth_rechecks=<0|1>
valid_blocks=<count>
already_present=<count>
events_written=<count>
deleted_prior=0
skipped=<count>
conflict_skipped=<count>
target_verified=<yes|no|unknown>
primary_copies=<count|unknown>
errors=<none or compact exact error>
recommendation=<keep main automation active|reauth Google Calendar|inspect primary-copy behavior>
```

## Success Criteria

- `status=ok` or `status=noop`
- `target_verified=yes`
- `primary_copies=0`
- every valid `daily_briefing.schedule_blocks[]` entry is either already present
  on the briefing calendar or was created and verified by this watchdog
