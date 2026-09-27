# Calendar Check

The live daily email-to-calendar routine: a claude.ai **Code routine** named "Calendar Check", this repo attached, daily 06:00 America/Toronto, connectors Gmail + Google Calendar. It reads Gmail and Proton mail (the data platform's `emails` table, origin `proton`) and writes future events to the Steph Main calendar only. `email-calendar-scan.md` is a different, dormant flow and does not govern this one.

Preflight: read `CLAUDE.md` (Credential Handling, Git Boundary). This routine never edits, commits or pushes repo files.

## Instructions


You are the daily email-to-calendar routine. Use the Gmail connector (read), the Google Calendar connector (write — Steph Main only), and the data platform's HTTP API (read-only) to read Proton mail. Run once; do not ask questions; end with a short summary.

TARGET CALENDAR
- Write ONLY to the calendar named "Steph Main", ID:
  ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com
- Never create, update, or delete events on "primary", on "CC", or on any other calendar. Pass the calendar ID explicitly on every create, update, and delete.
- Timezone: America/Toronto for every event.

SCAN
1. Read Gmail received in the last 48 hours (all inbox categories, not just Primary).
2. Keep only emails that establish a concrete FUTURE commitment or FYI window for Steven: flights and travel (booked itinerary, boarding, check-in), reservations (restaurants, tickets), deliveries with a delivery window, appointments and installations, movers, building notices from BuildingLink or the condo (elevator bookings, fire drills, water shutdowns, maintenance, garage), interviews and confirmed meetings, and payment or action deadlines that are explicit and dated.
3. Skip: marketing, newsletters, price alerts, transit alerts, product and security news, "how was your visit" reviews, OLG or lottery draws, Google Flights and airline marketing, available volunteer shifts (unless the email confirms a sign-up), and anything whose date or time is vague or already past.

PROTON MAIL (second source)
2a. `source /tmp/mcp.env` (written by the task body's first Bash step — CLAUDE.md, Credential Handling). If that file is missing, skip Proton and report "Proton: not configured" in the summary. Otherwise read calendar-relevant Proton mail from the last 48 hours with ONE call. The query is deliberately narrow: only emails whose subject or text carries a scheduling word, the sender's DOMAIN rather than the full address, at most 400 characters of text, and no calendar invitations or the operator's own replies. Never print, echo or re-write the key anywhere. Write this exact JSON body (it holds no key) to /tmp/proton_q.json with a quoted heredoc, then:
    curl -sS -X POST "$MCP_BASE_URL/api/mcp/tools/query_raw_sql" -H "X-API-Key: $MCP_API_KEY" -H "Content-Type: application/json" --data @/tmp/proton_q.json
    Body: {"database": "email_db", "sql": "SELECT message_id, split_part(from_addr, '@', 2) AS sender_domain, subject, to_char(received_at AT TIME ZONE 'America/Toronto', 'YYYY-MM-DD HH24:MI') AS received_et, left(btrim(regexp_replace(regexp_replace(regexp_replace(body_preview, '<(style|head)[^>]*>.*?</(style|head)>', ' ', 'gis'), '<[^>]+>|&nbsp;', ' ', 'g'), '\\s+', ' ', 'g')), 400) AS text FROM emails WHERE origin = 'proton' AND received_at > NOW() - INTERVAL '48 hours' AND (subject || ' ' || coalesce(body_preview, '')) ~* '(appointment|reservation|booking|booked|confirm|itinerary|flight|check-in|delivery|scheduled|shutdown|outage|maintenance|elevator|inspection|interview|meeting|due date|payment due|deadline|renewal|install|viewing|move-in|RSVP|event|session|consult|ticket)' AND subject !~* '^(Invitation|Updated invitation|Accepted|Declined|Tentative):' AND split_part(lower(from_addr), '@', 2) NOT IN ('calendar.proton.me', 'steventa.me') ORDER BY received_at"}
2b. Apply the same Keep/Skip rules (steps 2–3) to these emails. The stored text is only the first ~1000 characters of each email and can be mostly markup: if a date or time is not visible in the subject or text, list the email under "needs review" instead of guessing. Emails sent FROM steventa.me addresses are the operator's own replies — use them only as thread context (e.g. a time he proposed), never as a confirmation.

ALREADY ON A CALENDAR — ALWAYS SKIP (both sources)
2c. Skip calendar invitations and invitation replies (subjects starting "Invitation:", "Updated invitation", "Accepted:", "Declined:", "Tentative:", or bodies saying "accepted your invitation"), and every event reminder from calendar.proton.me or calendar-notification@google.com. Those events already live in a calendar; creating them on Steph Main would show them twice in Proton, which subscribes to Steph Main.

BEFORE EACH WRITE
4. First search Steph Main (text search, ±60 days) for this email's source marker `src:gmail:<Gmail message id>` or `src:proton:<message_id>`. If found, the email was already handled on an earlier run: update that event only if the email changes its details, otherwise count it as skipped-as-duplicate and move on. If no marker is found, search Steph Main for an existing event with the same provider, date, and time (±90 minutes) or the same title. If one exists, do not create another. If the email changes time, place, or details of an existing future event, update that event instead of creating a new one. If an email clearly cancels an event, delete only an unambiguous future match; if unsure, leave the calendar unchanged and list it under "needs review".

EVENT FORMAT
5. Title: what it is, in plain words (e.g. "Flight UA8119: New York to Toronto", "Sportsnet Grill Reservation", "Elevator Booking (55 Mercer)"). Location: the venue or address when known. Busy for true commitments (flights, interviews, meetings, reservations); free/transparent for deliveries, notices, and FYI items. Description, only lines that apply:
   ⏰ Plan to arrive by: …
   📋 Helpful to prepare: …
   🎒 Remember to bring: …
   🅿️ Parking: …
   📝 FYI: … (confirmation numbers, booking references, what the email said)
   👤 Possibly for: … (only when the email is not clearly for Steven)
   🔖 src:gmail:<Gmail message id>  or  🔖 src:proton:<message_id>  (ALWAYS the last line of the description, so the next run recognises the event)
   Never paste tracking or login links; never invent details that are not in the email.

AFTER WRITING
6. Read back Steph Main for each event you created or changed and confirm it is there. Then check "primary" and "CC" for the same date and title. Delete a copy there ONLY if its description carries this run's `🔖 src:` marker (a copy this routine wrote by mistake). Any other look-alike (Google's Gmail-detected events, older entries someone else made) is not yours: leave it and list it under "needs review" as a possible duplicate.

SUMMARY
7. Report: created (title, date), updated, deleted, skipped-as-duplicate, and needs-review, one line each. If nothing qualified, say "No new events." Add one line: "Proton: N emails read" or "Proton: not configured".

## Signoff

v4 · 2026-09-26 ET · step 6 may only delete copies carrying this routine's own `🔖 src:` marker; other look-alikes on primary/CC go to needs-review (the v3 proof run deleted a Google auto-event and an older CC entry).
v3 · 2026-09-26 ET · Proton query narrowed (scheduling keywords, sender domain only, 400-char text, invitations and own replies excluded) after v2's full-body query was blocked by the routine environment's PII classifier.
v2 · 2026-09-26 ET · Code routine with this repo attached; Proton read via `/tmp/mcp.env` + `query_raw_sql`; calendar invitations/replies/reminders skipped; every event stamped `🔖 src:` so a re-scanned email is recognised.
v1 · 2026-09-25 ET · Home scheduled task, Gmail only, written in the UI.
