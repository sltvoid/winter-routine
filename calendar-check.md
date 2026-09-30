# Calendar Check

The live daily email-to-calendar routine: a claude.ai **Code routine** named "Calendar Check", this repo attached, daily 06:00 America/Toronto, connectors Gmail + Google Calendar. It reads Gmail and Proton mail (the data platform's `emails` table, origin `proton`) and writes future events to the Steph Main calendar only. `email-calendar-scan.md` is a different, dormant flow and does not govern this one.

Preflight: read `CLAUDE.md` (Credential Handling, Git Boundary). This routine never edits, commits or pushes repo files.

## Operations

- **Routine:** claude.ai Code routine "Calendar Check", `trig_01CNwmb17WAU9jWZrmbEMeKi`. Repo `sltvoid/winter-routine` (branch `main`), connectors **Gmail** + **Google-Calendar** only, schedule `CRON_TZ=America/Toronto 0 6 * * *` (set the timezone explicitly; the UI default is UTC, which drifts an hour in winter). The earlier Home scheduled task `trig_01PESdRDfmSD8hU8znLWqbYY` is DISABLED; keep it off, or both run at 06:00.
- **Task body:** `claude-routine-calendar-check.v1.md` (gitignored). It writes `/tmp/mcp.env` (CLAUDE.md, Credential Handling) and points here.
- **The key:** its permanent home is the cluster Secret `context-api-secrets` → `MCP_API_KEY` (the same key the Weekly Program Review uses). To re-paste it without printing it: `ssh freebie "kubectl get secret context-api-secrets -n databases -o jsonpath='{.data.MCP_API_KEY}' | base64 -d" | tr -d '\n' | pbcopy`, then paste between the quotes in the task body.
- **Why the Proton query is narrow:** the routine sandbox's auto-mode classifier blocks a bulk read of email bodies as PII handling. Keep the keyword filter, the sender-domain-only column and the 400-char cap; if a run reports the Proton read as blocked, do not widen the query to work around it. The 7-day window (v6) returns about 40 rows against about 12 at 48 h. If that row count is ever what gets blocked, shorten the interval (e.g. 3 days) rather than changing the columns.
- **Where Proton mail comes from:** the data platform's in-cluster Proton Mail Bridge → `email-collector` (v4+ stores readable text previews) → `email_db.emails` (origin `proton`). Mail the platform itself sends (`ops.steventa.me`) is never ingested.
- **Deleted something by mistake?** Google Calendar keeps deleted events in Trash for 30 days: calendar.google.com → Settings → Trash (web only).
- **Checking a run:** each run ends with the summary in step 7; "Proton: N emails read" means the platform read worked, "Proton: not configured" means `/tmp/mcp.env` was missing.

## Instructions


You are the daily email-to-calendar routine. Use the Gmail connector (read), the Google Calendar connector (write — Steph Main only), and the data platform's HTTP API (read-only) to read Proton mail. Run once; do not ask questions; end with a short summary.

TARGET CALENDAR
- Write ONLY to the calendar named "Steph Main", ID:
  ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com
- Never create, update, or delete events on "primary", on "CC", or on any other calendar. Pass the calendar ID explicitly on every create, update, and delete.
- Timezone: America/Toronto for every event.

SCAN
1. Read Gmail received in the last 7 days (search `newer_than:7d`, all inbox categories, not just Primary). Follow `nextPageToken` until every thread is listed.
2. Keep only emails that establish a concrete FUTURE commitment or FYI window for Steven: flights and travel (booked itinerary, boarding, check-in), reservations (restaurants, tickets), deliveries with a delivery window, appointments and installations, movers, building notices (elevator bookings, fire drills, water shutdowns, maintenance, garage) from BOTH buildings (see BUILDINGS below), interviews and confirmed meetings, and payment or action deadlines that are explicit and dated.
3. Skip: marketing, newsletters, price alerts, transit alerts, product and security news, "how was your visit" reviews, OLG or lottery draws, Google Flights and airline marketing, available volunteer shifts (unless the email confirms a sign-up), and anything whose date or time is vague or already past.

BUILDINGS
2d. Two buildings send notices, and both are kept:
   - **55 Mercer** (TSCC 3016, via Condo Control, usually in Proton): Steven's home. Title them "… (55 Mercer)", e.g. "No Hot Water (55 Mercer)".
   - **Legacy Park** (BuildingLink, `legacypark2017@gmail.com`, usually in Gmail): **his mom's building**. Steven no longer lives there but wants to know. Title them "Legacy Park (Mom's) …", e.g. "Legacy Park (Mom's) Water Shutoff", and start the 📝 FYI line with "Mom's building (Legacy Park), not 55 Mercer." Always free/transparent.
   Never label a Legacy Park notice as 55 Mercer, or the reverse; if the sender does not say which building, list it under "needs review".

PROTON MAIL (second source)
2a. `source /tmp/mcp.env` (written by the task body's first Bash step — CLAUDE.md, Credential Handling). If that file is missing, skip Proton and report "Proton: not configured" in the summary. Otherwise read calendar-relevant Proton mail from the last 7 days with ONE call. The query is deliberately narrow: only emails whose subject or text carries a scheduling word, the sender's DOMAIN rather than the full address, at most 400 characters of text, and no calendar invitations or the operator's own replies. Never print, echo or re-write the key anywhere. Write this exact JSON body (it holds no key) to /tmp/proton_q.json with a quoted heredoc, then:
    curl -sS -X POST "$MCP_BASE_URL/api/mcp/tools/query_raw_sql" -H "X-API-Key: $MCP_API_KEY" -H "Content-Type: application/json" --data @/tmp/proton_q.json
    Body: {"database": "email_db", "sql": "SELECT message_id, split_part(from_addr, '@', 2) AS sender_domain, subject, to_char(received_at AT TIME ZONE 'America/Toronto', 'YYYY-MM-DD HH24:MI') AS received_et, left(btrim(regexp_replace(regexp_replace(regexp_replace(body_preview, '<(style|head)[^>]*>.*?</(style|head)>', ' ', 'gis'), '<[^>]+>|&nbsp;', ' ', 'g'), '\\s+', ' ', 'g')), 400) AS text FROM emails WHERE origin = 'proton' AND received_at > NOW() - INTERVAL '7 days' AND (subject || ' ' || coalesce(body_preview, '')) ~* '(appointment|reservation|booking|booked|confirm|itinerary|flight|check-in|delivery|scheduled|shutdown|outage|maintenance|elevator|inspection|interview|meeting|due date|payment due|deadline|renewal|install|viewing|move-in|RSVP|event|session|consult|ticket)' AND subject !~* '^(Invitation|Updated invitation|Accepted|Declined|Tentative):' AND split_part(lower(from_addr), '@', 2) NOT IN ('calendar.proton.me', 'steventa.me') ORDER BY received_at"}
2b. Apply the same Keep/Skip rules (steps 2–3) to these emails. The stored text is only the first ~1000 characters of each email and can be mostly markup: if a date or time is not visible in the subject or text, list the email under "needs review" instead of guessing. Emails sent FROM steventa.me addresses are the operator's own replies — use them only as thread context (e.g. a time he proposed), never as a confirmation.

ALREADY ON A CALENDAR — ALWAYS SKIP (both sources)
2c. Skip calendar invitations and invitation replies (subjects starting "Invitation:", "Updated invitation", "Accepted:", "Declined:", "Tentative:", or bodies saying "accepted your invitation"), and every event reminder from calendar.proton.me or calendar-notification@google.com. Those events already live in a calendar; creating them on Steph Main would show them twice in Proton, which subscribes to Steph Main.

BEFORE EACH WRITE
3a. The 7-day window means most emails were already seen on earlier runs. Work through the kept emails oldest first, so that when several emails concern the same event, the newest one is applied last and wins.
4. First search Steph Main (text search, ±60 days) for this email's source marker `src:gmail:<Gmail message id>` or `src:proton:<message_id>`. If found, the email was already handled on an earlier run: count it as skipped-as-duplicate and move on. Never re-apply an email that already has its marker on an event; that is how Steven's own edits to an event survive the daily re-reads. If no marker is found, search Steph Main for an existing event with the same provider, date, and time (±90 minutes) or the same title. If one exists, do not create another. If this (unmarked) email changes the time, place, or details of an existing future event, update that event instead of creating a new one, and add this email's `🔖 src:` line under the existing one. If an email says an event is cancelled, search Steph Main on the cancelled event's own date (not only from today onward). If that date has already passed, skip it; there is nothing to decide. Otherwise do NOT delete it: leave it on the calendar and list it under "needs review" (event, date, and the email that cancels it) for Steven to confirm.

EVENT FORMAT
5. Title: what it is, in plain words (e.g. "Flight UA8119: New York to Toronto", "Sportsnet Grill Reservation", "Elevator Booking (55 Mercer)"). Location: the venue or address when known. Busy for true commitments (flights, interviews, meetings, reservations); free/transparent for deliveries, notices, and FYI items. Description, only lines that apply:
   ⏰ Plan to arrive by: …
   📋 Helpful to prepare: …
   🎒 Remember to bring: …
   🅿️ Parking: …
   📝 FYI: … (confirmation numbers, booking references, what the email said)
   👤 Possibly for: … (only when the email is not clearly for Steven)
   🕒 Added YYYY-MM-DD by Calendar Check · email of YYYY-MM-DD  (always; dates in America/Toronto. The first date is today, the second is when the source email was received. When a later email updates the event, keep this line and append ` · updated YYYY-MM-DD from email of YYYY-MM-DD`.)
   🔖 src:gmail:<Gmail message id>  or  🔖 src:proton:<message_id>  (ALWAYS the last line(s) of the description, one per email applied, so the next run recognises the event)
   Never paste tracking or login links; never invent details that are not in the email.

AFTER WRITING
6. Read back Steph Main for each event you created or changed and confirm it is there. Then check "primary" and "CC" for the same date and title, and apply the DELETION GATE below to anything you find there.

DELETION GATE (every delete, on every calendar)
6a. Delete an event ONLY when it is a duplicate: another event that stays (normally the Steph Main one) covers the same thing — same date, start within 30 minutes, and the same venue or an equivalent title.
6b. Before deleting a duplicate, compare the two descriptions. Copy any detail the doomed copy has that the kept event lacks (party size, table notes, reference numbers, instructions) into the kept event's 📝 FYI line, then delete.
6c. Anything that is NOT a duplicate is never deleted, whoever made it: leave it in place and list it under "needs review" with one line on why it looked relevant. Steven decides.
6d. In the summary, list every delete as: calendar it was on → the kept event it duplicated → details carried over (or "none"). Deleted events stay in Google Calendar's Trash for 30 days.

SUMMARY
7. Report: created (title, date), updated, deleted, skipped-as-duplicate, and needs-review, one line each. If nothing qualified, say "No new events." Add one line: "Proton: N emails read" or "Proton: not configured".

## Signoff

v6.1 · 2026-09-29 ET · BUILDINGS rule (operator): Legacy Park (BuildingLink) is Steven's mom's building. Keep its notices, titled "Legacy Park (Mom's) …" with a Mom's-building FYI line, never confused with 55 Mercer (his home). Renewals stay on the renewal date (operator: "renewal should just be there"), no cancel-by shift.
v6 · 2026-09-29 ET · Scan window 48 h → 7 days on both sources: v5 caught the hot-water (09-24) and power-outage (09-15) notices only through later reminders, and missed the dentist confirmation (09-24) entirely. To keep the daily re-reads safe: emails are applied oldest first, so the newest wins; an email whose marker is already on an event is never re-applied, so Steven's hand edits stick; cancellations are looked up on the event's own date, and skipped once that date has passed. Every event gains a `🕒 Added … · email of …` line above the `🔖` marker(s).
v5.1 · 2026-09-27 ET · Operations section (routine id, settings, key source, why the query is narrow, Trash recovery); instructions unchanged.
v5 · 2026-09-27 ET · DELETION GATE: delete only true duplicates of an event that stays, carrying over any extra details first; cancellations and every non-duplicate are kept and listed under needs-review (operator rule).
v4 · 2026-09-26 ET · step 6 may only delete copies carrying this routine's own `🔖 src:` marker; other look-alikes on primary/CC go to needs-review (the v3 proof run deleted a Google auto-event and an older CC entry).
v3 · 2026-09-26 ET · Proton query narrowed (scheduling keywords, sender domain only, 400-char text, invitations and own replies excluded) after v2's full-body query was blocked by the routine environment's PII classifier.
v2 · 2026-09-26 ET · Code routine with this repo attached; Proton read via `/tmp/mcp.env` + `query_raw_sql`; calendar invitations/replies/reminders skipped; every event stamped `🔖 src:` so a re-scanned email is recognised.
v1 · 2026-09-25 ET · Home scheduled task, Gmail only, written in the UI.
