# Email Calendar Scan

This routine scans recent email and creates only user-relevant future calendar
events on Steph Main.

## Sources

- Email source: data-platform MCP email-calendar tools. Prefer
  `prepare_email_calendar_scan` instead of raw SQL or `query_raw_sql`.
- Calendar write target: Google Calendar plugin, calendar ID
  `ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com`.
- Do not modify raw email data.
- Do not create, update, or delete events on `primary`.

If the data-platform MCP email source or the Google Calendar plugin is
unavailable, stop and report the exact failure. Do not fall back to browser UI,
local Google credentials, macOS Calendar, or direct database credentials.

## MCP Workflow

1. Call `prepare_email_calendar_scan(window_hours=48)` for normal recurring
   runs. For backfills above 72 hours, call it only when the user explicitly
   asked for a backfill and set `manual_backfill=true`.
2. If the Google Calendar plugin is available, run a bounded read-only search on
   Steph Main before treating the run as healthy. If the plugin returns an auth
   or transport error, report the exact error and do not attempt any calendar
   write.
3. If `calendar_actions[]`, `review[]`, and `skipped[]` are all empty, run the
   read-only source sentinel before reporting a clean run. Use
   `query_emails(mode="detail")` through the data-platform MCP for the current
   and prior two local dates across exposed email types, including `career` and
   `personal_gmail`, and look for high-signal condo source mail:
   `notify@buildinglink.com`, `BuildingLink`, `Community Update`, `water`,
   `shutdown`, `interruption`, `maintenance`, `garage`, and `elevator`. This
   sentinel may only report `possible_missed_candidate`; it must never create,
   update, or delete calendar events and must never invent event details outside
   `calendar_actions[]`.
4. If the sentinel finds high-signal condo mail that was not represented in
   `calendar_actions[]`, `review[]`, or `skipped[]`, report it as
   `possible_missed_candidate` with sender, subject, received time, and the
   reason the run is not clean. Do not call `record_email_calendar_decision`
   unless the MCP returned a candidate id.
5. For each returned `calendar_actions[]` item, use the Google Calendar plugin
   to search Steph Main in the provided duplicate window.
6. If a duplicate exists, do not create another event. Call
   `record_email_calendar_decision` with `status="duplicate"`.
7. If `conflict_check_required=true`, search existing events in the candidate
   window before creating. If a busy conflict exists, do not create the event;
   call `record_email_calendar_decision` with `status="conflict"` and include
   the conflict event ids when available.
8. For non-conflicting creates/updates/deletes, use only the Google Calendar
   plugin against Steph Main. Then read back Steph Main and `primary` to verify
   the action landed on Steph Main and did not create a `primary` copy.
9. Record the final result with `record_email_calendar_decision`. Successful
   `created`, `updated`, or `deleted` decisions must include
   `target_verified=true` and `primary_copies=0`. If verification fails, record
   `status="target_verification_failed"` and report it.
10. Use `query_email_calendar_review_queue` when the run needs to summarize
   unresolved `needs_review`, `conflict`, `error`, or verification-failed items.

## User Context

- Condo resident floor: 3rd floor.
- Condo parking level: unknown.
- All-day-style FYIs should be created from 8:00 AM to 9:00 AM
  America/Toronto because the Calendar plugin does not support true all-day
  event creation.

## Scan Window

- Normal recurring run: rolling last 48 hours of email.
- Backfills are manual only. Do not run a 14-day or 30-day scan unless the user
  explicitly asks for it, and pass `manual_backfill=true` to MCP.
- Only create or modify events whose scheduled time is now or in the future.
- Skip past-finished events.
- Keep a short final report with created, updated, canceled/deleted, duplicate,
  skipped high-signal, and error counts.

## Classification Rules

- Ignore `calendar-notification@google.com`; those are calendar-derived agenda
  emails and must never create events.
- Condo / BuildingLink notices from `@buildinglink.com`: create transparent FYI
  events only for concrete dates or date/times. Apply 3rd-floor context. Treat
  multi-section `Community Update` emails as high-signal source mail because
  calendar-relevant notices can appear below an unrelated first section. Skip
  floor-specific notices that exclude the 3rd floor. Skip notices for missed
  units or another floor unless the email clearly includes the user's unit. Skip
  P1/P2/P3-specific garage-cleaning notices while parking level is unknown, but
  create building-wide garage closures or access restrictions.
- Building-wide all-day-style notices, bill due dates, and other FYI dates are
  transparent 8:00 AM to 9:00 AM America/Toronto events.
- Billing notices: create a transparent FYI only when a concrete due date is
  present. Include provider and amount when visible. Do not create events for
  bill-ready, statement-ready, invoice-available, card-expired, or past-due
  emails without a concrete due date or deadline.
- Explicit account/action deadlines: when an email gives a resolvable deadline,
  such as `complete within 48 hours` or `complete within 72 hours`, compute the
  deadline from `received_at` and create a transparent FYI only if it is future
  and clearly action-required. If the deadline is vague or already past, skip
  and report it.
- Reservations, deliveries, interviews, and meetings: create events only when
  the email confirms the user is attending or has a scheduled
  delivery/reservation/meeting window. Use busy/opaque for true commitments such
  as interviews or confirmed meetings. Use transparent for deliveries and
  FYI/reminder items.
- Cancellation handling: if an email clearly cancels a scheduled event, search
  Steph Main for an exact or near-exact future match by provider, title, date,
  and time. Delete only when the match is unambiguous. If uncertain, do not
  delete; report `needs_review`.
- Update handling: if an email changes a meeting link, panel, location, time, or
  other details for an existing future event, update the matching Steph Main
  event instead of creating a duplicate. If time changed, search both old and
  new times when possible. If no reliable match exists, report `needs_review`.
- OpenTable, Booking, and reservation HTML previews: create only when concrete
  date/time and venue are extractable from the email preview. Do not infer from
  review emails such as `How was ...?`.
- Volunteer emails: create a transparent FYI for shift-release moments only when
  the release date/time is concrete, such as `shifts will be released Wednesday,
  May 27 at 7pm`. Do not create calendar events for available shifts unless the
  email confirms the user signed up for a specific shift.
- Workshop, webinar, newsletter, retail, flight-price, transit-alert, product,
  security-news, and marketing emails are not calendar events unless there is
  clear evidence the user registered, booked, must attend, or has a concrete
  action deadline.
- OLG / lottery ticket confirmations and draw dates are not calendar events.
- Google Flights and airline marketing emails are not calendar events unless
  they are actual booked itinerary, boarding, or check-in messages.

## Deduplication

Before creating an event, search Steph Main for likely duplicates using title,
provider/source, date, and time. Do not create duplicates.

For updates and cancellations, modify or delete only an unambiguous future match
on Steph Main. If a match is uncertain, leave the calendar unchanged and report
`needs_review`.

## Failure Reporting

Report, and record where possible, any of these as high-signal failures:

- data-platform MCP email-calendar tool unavailable.
- Google Calendar plugin unavailable.
- Google Calendar plugin auth or token failure, even when there are no prepared
  actions.
- Steph Main duplicate search fails.
- Calendar write succeeds but read-back verification fails.
- Any created/updated/deleted event appears on `primary`.
- Email body is missing or preview-limited and the date/time cannot be
  confidently extracted.
- `possible_missed_candidate`: high-signal condo source mail exists in MCP email
  detail but `prepare_email_calendar_scan` returned no corresponding action,
  review, or skipped item.
