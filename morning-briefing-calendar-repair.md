# Morning Briefing Calendar Repair

Purpose: create the Google Calendar events that were planned by an already
written morning briefing when the main pipeline skipped Calendar writes because
bounded search or plugin auth failed.

This is a **Calendar-only repair**. It must not rerun Stage 0, regenerate the
briefing, or duplicate `rt_yesterday`, `email_daily`, `daily_briefing`, or
`agent_runs` rows.

## Hard Rules

1. Work only in `/Users/steventa/Documents/CodingJunk/Winter-Routine`.
2. Read this file before running.
3. Use the latest existing `daily_briefing` row for `TODAY_ET` unless a specific
   `DAILY_BRIEFING_ID` is provided.
4. Use recent same-day `calendar_write` rows as repair context, not as sole
   proof of full coverage. A prior repair can have `target_verified=yes` while
   verifying only the subset it created. Stop as a no-op only after bounded
   target-calendar search confirms every valid briefing `schedule_blocks[]`
   entry already has a matching briefing-calendar event.
5. Do not call `compute_daily_insights`.
6. Do not write `rt_yesterday`, `email_daily`, `daily_briefing`, `agent_runs`,
   memory, notes, or raw SQL mutations.
7. Write exactly one `calendar_write` manifest row after the repair attempt,
   even when zero events are created.
8. Use only Google Calendar plugin tools for Calendar search, create, and
   read-back verification.
9. Do not call `_get_availability`.
10. Do not update or delete existing Calendar events.
11. Do not print or persist existing event titles, descriptions, locations,
    attendees, URLs, or IDs. Use only compact busy-window data.
12. Calendar-only repair mirrors the briefing's generated schedule for the day.
    Do not skip a block solely because it already started or is in the past.
    Only skip blocks that are invalid, outside the planning window, already
    present on the briefing calendar, or conflicting with a busy window.

## Environment

Anchor these once:

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

## Source Briefing

Use `mcp__data_platform__.query_raw_sql` read-only on `llm_db`:

```sql
SELECT id, pipeline_id, output_response, created_at
FROM llm_runs
WHERE run_type = 'daily_briefing'
  AND output_response->>'date' = '<TODAY_ET>'
ORDER BY created_at DESC
LIMIT 1;
```

If the query returns no row, stop before Calendar writes with
`status=blocked_no_daily_briefing`.

Save `output_response` to `/tmp/briefing.json` and the row id to local scratch
state.

Then load same-day `calendar_write` context:

```sql
SELECT id, pipeline_id, output_response, created_at
FROM llm_runs
WHERE run_type = 'calendar_write'
  AND output_response->>'date' = '<TODAY_ET>'
ORDER BY created_at DESC
LIMIT 5;
```

Use this to populate `repair_of_calendar_write_id` and understand prior repair
attempts. Do not treat a successful prior manifest as sufficient proof that all
briefing blocks exist.

## Bounded Busy Search

Search only:

- `primary`
- `$BRIEFING_CALENDAR_ID`

Use `mcp__codex_apps__google_calendar._search_events` with explicit
`time_min`, `time_max`, and `timezone_str=America/Toronto`.

If using local search result files, classify the bounded search pair before
deciding whether the repair is blocked:

```bash
python3 scripts/calendar_search_policy.py \
  --primary /tmp/calendar_search_primary.json \
  --briefing /tmp/calendar_search_briefing.json \
  --out /tmp/calendar_search_policy.json
```

If either search fails with an auth/reauth/permission/scope-looking error, run
exactly one bounded re-check on the same `primary` and briefing calendar IDs
with the same `time_min`, `time_max`, and `timezone_str`. Replace the raw search
files with the re-check results and classify the pair again.

If either search still fails after that one auth-like re-check, create zero
events and write a `calendar_write` manifest with:

- `busy_source=failed`
- `events_written=0`
- `target_verified=no`
- `calendar_auth_rechecks=1`
- exact compact error

When search succeeds, derive `/tmp/calendar_busy.json`:

```json
{
  "status": "ok",
  "busy_source": "search",
  "calendar_ids": ["primary", "<briefing-calendar-id>"],
  "time_min": "<RFC3339>",
  "time_max": "<RFC3339>",
  "busy_windows": [
    {"start": "<RFC3339>", "end": "<RFC3339>", "calendar_id": "<id>"}
  ],
  "busy_window_count": 0
}
```

Busy-window rules:

- Treat opaque events as busy.
- Treat transparent events on `primary` as non-blocking.
- Treat all events on `$BRIEFING_CALENDAR_ID` as busy so reruns do not pile
  duplicate briefing blocks onto the same calendar.
- For no-op decisions, compare the existing briefing-calendar events against the
  source briefing's expected block start/end/title shape. Do this locally and
  report only counts. Do not print or persist existing event IDs or full event
  details.

If all valid briefing blocks already exist on the briefing calendar and
`primary` read-back shows no created/repair IDs copied to primary, write a
zero-create `calendar_write` manifest with `status=noop`, then return `noop`.

## Create Plan

Run:

```bash
python3 scripts/calendar_plan.py \
  --briefing /tmp/briefing.json \
  --busy /tmp/calendar_busy.json
```

Only create events emitted in `/tmp/calendar_create_args_private.json`.
For repair runs after the day has started, still create generated briefing
blocks that are earlier in the day when they are missing. This keeps Google
Calendar as a faithful mirror of the morning briefing. Duplicate prevention
comes from treating existing briefing-calendar events as busy, not from skipping
started blocks.

Calendar event titles should be the schedule block `activity` text directly.
Do not add a `Briefing:` prefix. The event is already scoped by the briefing
group calendar.

Every create call must use:

```json
{
  "calendar_id": "$BRIEFING_CALENDAR_ID",
  "attendees": [],
  "self_attendance": "omit",
  "add_google_meet": false,
  "transparency": "opaque",
  "visibility": "private"
}
```

Do not set `self_attendance=accepted`.

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
details.

## Calendar Manifest

Always write one `calendar_write` row through
`mcp__data_platform__.write_llm_run`.

Use `run_type=calendar_write`, `step_label=calendar_only_repair`, and the
current repair `PIPELINE_ID`.

Include at least:

- `mode=calendar_write`
- `date`
- `repair=true`
- `repair_source_daily_briefing_id`
- `repair_of_calendar_write_id` when known
- `busy_source`
- `busy_window_count`
- `busy_calendar_ids`
- `calendar_auth_rechecks` when an auth-like read failure required a bounded
  re-check; expected `0` or `1`
- `events_written`
- `deleted_prior=0`
- `skipped`
- `conflict_skipped`
- `past_or_started_skipped` if any optional operator override used
  `--skip-started`; expected `0` for the standard repair path
- `target_verified`
- `primary_copies`
- compact errors if any

## Output

Return only this compact shape:

```text
morning_briefing_calendar_repair
status=<ok|blocked_no_daily_briefing|blocked_search_failed|needs_review|noop>
pipeline_id=<uuid>
daily_briefing_id=<id|none>
calendar_write_id=<id|none>
repair_of_calendar_write_id=<id|none>
date=<YYYY-MM-DD>
busy_source=<search|failed>
busy_windows=<count>
events_written=<count>
deleted_prior=0
skipped=<count>
conflict_skipped=<count>
past_or_started_skipped=<count, expected 0>
target_verified=<yes|no|unknown>
primary_copies=<count|unknown>
errors=<none or compact exact error>
recommendation=<keep main automation active|reauth Google Calendar|inspect primary-copy behavior|manual replay only>
```

## Interpretation

- `status=ok`, `target_verified=yes`, and `primary_copies=0` means the missed
  Calendar side effect was repaired and the main morning automation can remain
  active.
- Search failure means the plugin auth/connector state failed before create.
- Create failure means the write permission or event write shape failed.
- `primary_copies>0` means inspect `self_attendance` behavior before allowing
  future briefing Calendar writes.
