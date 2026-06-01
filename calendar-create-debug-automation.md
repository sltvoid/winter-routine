# Calendar Create Debug Automation

Purpose: isolate whether Google Calendar event creation works from a scheduled
Codex automation without running the morning briefing pipeline or writing
platform rows.

This is a **one-shot diagnostic**. Keep it disabled except when debugging Google
Calendar plugin behavior after reauthentication.

## Scope

- Use only the Google Calendar plugin.
- Do not call data-platform MCP tools.
- Do not run the morning briefing pipeline.
- Do not write `llm_runs`, `agent_runs`, memory, notes, or SQL rows.
- Do not update or delete existing Calendar events.
- Create at most one diagnostic event per run.

## Calendar IDs

- Busy-window source calendars:
  - `primary`
  - `ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com`
- Create target:
  - `ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com`

## Environment

Anchor these once at the start:

```bash
export TODAY_ET="$(TZ=America/Toronto date +%F)"
export PROBE_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
export BRIEFING_CALENDAR_ID="ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com"
export TIMEZONE="America/Toronto"
```

Use the same planning window as the morning briefing:

- `time_min`: `$TODAY_ET 7:00 AM America/Toronto`
- `time_max`: `$TODAY_ET 10:00 PM America/Toronto`

## Procedure

1. Search bounded events on `primary` using
   `mcp__codex_apps__google_calendar._search_events`.
2. Search bounded events on `$BRIEFING_CALENDAR_ID` using
   `mcp__codex_apps__google_calendar._search_events`.
3. If either search returns an auth, reauth, permission, or scope error:
   - Run exactly one bounded re-check on both calendars with the same
     `time_min`, `time_max`, and `timezone_str`.
   - For local file workflows, classify the search pair with:
     `python3 scripts/calendar_search_policy.py --primary /tmp/calendar_search_primary.json --briefing /tmp/calendar_search_briefing.json --out /tmp/calendar_search_policy.json`.
4. If either search still returns an auth, reauth, permission, or scope error
   after that one re-check:
   - Stop before create.
   - Report `status=blocked_before_create`.
   - Report the exact tool error compactly.
5. Derive compact busy windows only from start/end/calendar/transparency:
   - Treat opaque events as busy.
   - Treat transparent events on `primary` as non-blocking.
   - Treat events on `$BRIEFING_CALENDAR_ID` as busy to avoid piling probes.
   - Do not print or persist titles, descriptions, locations, attendees, URLs,
     or existing event IDs.
6. Pick the first free 5-minute slot between 7:00 AM and 10:00 PM ET.
7. Create exactly one event on `$BRIEFING_CALENDAR_ID`:

```json
{
  "calendar_id": "$BRIEFING_CALENDAR_ID",
  "title": "Calendar create probe",
  "description": "Diagnostic one-shot probe from Codex automation. Probe ID: $PROBE_ID",
  "start_time": "<chosen-start-rfc3339>",
  "end_time": "<chosen-end-rfc3339>",
  "timezone_str": "America/Toronto",
  "attendees": [],
  "self_attendance": "omit",
  "add_google_meet": false,
  "transparency": "opaque",
  "visibility": "private"
}
```

8. Save only the created event ID in local scratch state for the report. Do not
   print the full create response.
9. Read back the same 7:00 AM-10:00 PM ET window on `$BRIEFING_CALENDAR_ID` and
   `primary` with `_search_events`.
10. Verify by event ID counts only:
   - `target_verified=yes` only if the created event ID is found on the target
     briefing calendar.
   - `primary_copies` is the count of the created event ID found on `primary`.
   - Expected: `target_verified=yes`, `primary_copies=0`.

## Output

Return only this compact report shape:

```text
calendar_create_probe
status=<ok|blocked_before_create|needs_review|failed>
probe_id=<uuid>
date=<YYYY-MM-DD>
busy_search_primary=<ok|failed>
busy_search_briefing=<ok|failed>
calendar_auth_rechecks=<0|1>
busy_windows=<count>
slot=<start/end or none>
create_attempted=<yes|no>
created_event_id_present=<yes|no>
target_verified=<yes|no|unknown>
primary_copies=<int|unknown>
errors=<none or compact exact error>
recommendation=<keep main automation active|reauth Google Calendar|inspect primary-copy behavior|manual replay only>
```

## Interpretation

- If search fails before create, the problem is Calendar plugin auth/scope or
  connector transport, not event creation.
- If search succeeds but create fails, the problem is create permission or event
  write shape.
- If create succeeds and target read-back finds the event with
  `primary_copies=0`, Calendar creation works in automation context.
- If create succeeds but `primary_copies>0`, inspect `self_attendance` handling
  before enabling briefing-calendar writes.
