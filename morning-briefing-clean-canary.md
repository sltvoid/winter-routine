# Morning Briefing Clean Canary

Purpose: run the morning briefing as the supervised Codex canary with the same
write contract as `morning-briefing.md`, but with strict token discipline.

This runbook is used by the active local Codex daily automation and can also be
used for manual review. Do not infer scheduler state from this file; inspect the
automation record when deciding whether to pause or resume it.

## Hard Rules

1. Read `README.md`, `api-catalog.md`, and this file before starting.
2. Prefer native `mcp__data_platform__.*` tools for platform data reads and
   database writes. Do not run `scripts/smoke_test.sh` as a gate.
3. Source the automation env file when present, but never print
   `MCP_API_KEY`.
4. Anchor `TODAY_ET`, `TODAY_DAY_OF_WEEK`, `YESTERDAY_ET`,
   `YESTERDAY_DAY_OF_WEEK`, and one `PIPELINE_ID` before Stage 0.
5. Stage 0 is exactly one `compute_daily_insights` call for `YESTERDAY_ET`.
   Stop before writes if it fails.
6. Never print full JSON payloads. Use local files and concise summaries only.
7. Do not use raw SQL to override focus, app, or career verdicts/headlines
   from Stage 0.
8. Do not call `save_memory`; Stage 4 memory candidates are diagnostic only.
9. Never retry `write_llm_run` or `write_agent_run` after a row may have been
   created.
10. Agent rows must include
    `tool_calls[0].classification.agent_kind = morning_briefing` and must not
    prefix `final_response` with `Response contract:`.
11. Calendar scheduling must be busy-window-aware: read occupied slots before
    synthesis, avoid overlaps, and never update or delete existing events.
12. Google Calendar state must come from the Google Calendar plugin only:
    use `mcp__codex_apps__google_calendar._search_events` for bounded reads
    and read-back verification, and use
    `mcp__codex_apps__google_calendar._create_event` for creates. Do not use
    `mcp__data_platform__.query_calendar`, raw SQL, or prior briefing blocks as
    Google Calendar availability or write substitutes.
13. Same-day replays must be explicit. Before Stage 0, run the replay guard.
    If same-day rows already exist and `ALLOW_FULL_REPLAY=1` is not set, stop
    before Stage 0 and recommend either no-op or calendar-only repair.

## Repository Freshness Preflight

Before Stage -1, run `git fetch origin main`, compare `HEAD` to `origin/main`,
and fast-forward only when `HEAD` is an ancestor of `origin/main`:

```bash
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main
git merge-base --is-ancestor HEAD origin/main && git merge --ff-only origin/main
```

This preflight is read/update-only: do not create branches, set upstreams,
commit, or push. If `git fetch` fails because the environment cannot reach
GitHub, compare the existing local `origin/main` ref to `HEAD`; continue only
when they match, and report that remote freshness was not certified. If local
`HEAD` is behind or has diverged from `origin/main`, stop before Stage 0.
**Local-ahead is allowed:** when `origin/main` is an ancestor of `HEAD` (local
has unpushed commits), continue and report the ahead state — a local work
session must never silently kill the morning briefing (this exact case caused
the 2026-06-10..11 briefing outage: two unpushed 06-09 commits failed the old
ancestor check every morning).

## Calendar Connector Boundary

The morning briefing has two separate transports:

- Platform data and persistence: `mcp__data_platform__.*` or the repo HTTP
  wrapper when available.
- Google Calendar availability, event creation, and read-back verification:
  Google Calendar plugin tools only.

If the Google Calendar plugin returns an authentication or reauthentication
error for either `primary` or `$BRIEFING_CALENDAR_ID`, treat it as a retryable
Calendar connector read failure, not as a schedule conflict. Run exactly one
bounded re-check on the same calendar IDs and the same 7:00 AM-10:00 PM ET
window before setting `busy_source=failed`. If the re-check succeeds, continue
with `busy_source=search` and create conflict-free Calendar events. If the
re-check still fails, create zero Calendar events, write the `calendar_write`
manifest with the compact auth error, and report that the Google Calendar plugin
needs reauthentication. Do not describe this as a data-platform MCP failure.

After the plugin is reauthenticated, do not rerun the whole pipeline unless the
user explicitly asks for a replay. Prefer the scheduled
`morning-briefing-calendar-watchdog.md` or a calendar-only repair from the
already-written `/tmp/briefing.json` or latest `daily_briefing` row, then
perform target-calendar and `primary` read-back verification.

## Token Budget Target

Target 20k-40k total tokens for a supervised native run.

Avoid these token sinks:

- `jq .`, `cat /tmp/*.json`, or `jq -c .` on full payloads.
- Pasting `output_response`, `final_response`, or calendar responses into chat.
- Printing full native write arguments for review.
- Reading old automation memory beyond the most recent relevant entries.

Allowed concise output:

- Stage status lines.
- Row IDs.
- Counts: schedule blocks, priority actions, calendar successes/skips. In dry
  runs, report calendar event candidates as `would_create`, not as written.
- Calendar busy-source status, busy-window count, and conflict-skip count.
- Headline-preservation status.
- Agent classification and text-safety status.
- Errors.

## Native MCP Fallback File Adapter

Repo shell scripts can call the HTTP MCP surface, but they cannot invoke
Codex-native MCP tools directly. When HTTP is unavailable and Codex native
tools are used, write each native response through `scripts/native_mcp_files.py`
instead of custom one-off Python snippets:

```bash
python3 scripts/native_mcp_files.py write \
  --label compute_daily_insights \
  --out /tmp/insights.json < /tmp/native_compute_daily_insights.json
```

For several native responses, use a bundle file:

```json
{
  "files": [
    {"label":"query_health_yesterday","out":"/tmp/health_yesterday.json","payload":{"status":"ok","data":[]}},
    {"label":"query_calendar","out":"/tmp/calendar_blocks.json","payload":{"status":"ok","data":[]}}
  ]
}
```

Then run:

```bash
python3 scripts/native_mcp_files.py bundle --input /tmp/native_bundle.json
```

The helper writes exact MCP-shaped JSON files and prints only compact
`label/status/count` lines.

## Environment

```bash
set -euo pipefail

if [ -f /Users/steventa/.codex/automations/mcp-morning-briefing-live-canary/env.sh ]; then
  set +u
  . /Users/steventa/.codex/automations/mcp-morning-briefing-live-canary/env.sh >/dev/null 2>&1
  set -u
fi

export MODEL="${MODEL:-gpt-5.5}"
export ROUTINE_MODE="${ROUTINE_MODE:-dry_run}"
export ALLOW_WRITES="${ALLOW_WRITES:-0}"
export AGENT_EXECUTION_MODE="${AGENT_EXECUTION_MODE:-scheduled_codex_dry_run}"
export BRIEFING_CALENDAR_ID="ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com"
export CALENDAR_BUSY_CALENDAR_IDS="${CALENDAR_BUSY_CALENDAR_IDS:-primary,$BRIEFING_CALENDAR_ID}"
export TODAY_ET="$(TZ=America/Toronto date +%F)"
export TODAY_DAY_OF_WEEK="$(TZ=America/Toronto date +%A)"
export YESTERDAY_ET="$(TZ=America/Toronto date -v-1d +%F 2>/dev/null || TZ=America/Toronto date -d 'yesterday' +%F)"
export YESTERDAY_DAY_OF_WEEK="$(TZ=America/Toronto date -v-1d +%A 2>/dev/null || TZ=America/Toronto date -d 'yesterday' +%A)"
export PIPELINE_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
```

## Stage -1 - Same-Day Replay Guard

Before Stage 0, run a read-only same-day guard. This is the only read allowed
before `compute_daily_insights`; it exists to prevent accidental duplicate
`llm_runs`, `agent_runs`, and Google Calendar events.

Query recent same-day morning rows into `/tmp/morning_existing_runs.json`:

```bash
scripts/mcp.sh query_raw_sql "{
  \"database\":\"llm_db\",
  \"sql\":\"SELECT id::text AS id, run_type, pipeline_id, created_at, output_response->>'date' AS output_date, input_payload->>'today' AS input_today, output_response->>'target_verified' AS target_verified, output_response->>'primary_copies' AS primary_copies, output_response->>'events_written' AS events_written, output_response->>'watchdog' AS watchdog, output_response->>'repair' AS repair, output_response->>'status' AS status, output_response->>'errors' AS errors, NULL::text AS goal FROM llm_runs WHERE run_type IN ('rt_yesterday','email_daily','daily_briefing','calendar_write') AND (output_response->>'date' = '$TODAY_ET' OR input_payload->>'today' = '$TODAY_ET') UNION ALL SELECT id::text AS id, 'agent_runs' AS run_type, pipeline_id, created_at, NULL::text AS output_date, NULL::text AS input_today, NULL::text AS target_verified, NULL::text AS primary_copies, NULL::text AS events_written, NULL::text AS watchdog, NULL::text AS repair, NULL::text AS status, NULL::text AS errors, goal FROM agent_runs WHERE goal ILIKE 'Morning briefing pipeline for $TODAY_ET%' ORDER BY created_at DESC\"
}" /tmp/morning_existing_runs.json
```

For native fallback, make the same `query_raw_sql` call with
`mcp__data_platform__.query_raw_sql`, then save it with:

```bash
python3 scripts/native_mcp_files.py write \
  --label morning_existing_runs \
  --out /tmp/morning_existing_runs.json < /tmp/native_morning_existing_runs.json
```

Then run:

```bash
python3 scripts/replay_guard.py \
  --today-et "$TODAY_ET" \
  --pipeline-id "$PIPELINE_ID"
```

If it prints `action=same_day_rows_exist`, stop and report no-op unless the user
explicitly requested a full replay. If it prints `action=calendar_only_repair`,
stop the full pipeline and repair Calendar from the existing
`daily_briefing`/`/tmp/briefing.json`. Only continue to Stage 0 when it prints
`status=ok action=continue` or `status=ok action=continue_after_watchdog_only`,
or when `ALLOW_FULL_REPLAY=1` was explicitly set for a known replay case.

## Stage 0 - Native Gate

Call native `compute_daily_insights` exactly once:

```json
{"date":"$YESTERDAY_ET"}
```

Persist the response to `/tmp/insights.json` for local scripts. In Codex, do
not paste the full response into chat; note only the three headline strings and
whether the call succeeded.

## Stage 0.5 - Supplementary Reads

Run these native reads in parallel and save each result to the matching local
file:

| Tool | Args | File |
| --- | --- | --- |
| `query_health` | `{"date":"$YESTERDAY_ET","mode":"daily"}` | `/tmp/health_yesterday.json` |
| `query_health` | `{"mode":"workouts"}` | `/tmp/health_workouts.json` |
| `query_health` | `{"date":"$TODAY_ET","mode":"daily"}` | `/tmp/health_today.json` |
| `query_raw_sql` | 7-day sleep average | `/tmp/sleep_baseline.json` |
| `query_raw_sql` | per-device RescueTime totals for `YESTERDAY_ET` | `/tmp/rt_totals.json` |
| `query_raw_sql` | host-level `browser_activity_events` aggregate for `YESTERDAY_ET` | `/tmp/browser_activity.json` |
| `query_raw_sql` | email subjects for `YESTERDAY_ET` | `/tmp/emails_daily.json` |
| `query_calendar` | `{}` | `/tmp/calendar_blocks.json` |
| `recall_memory` | broad productivity/focus query | `/tmp/agent_memory.json` |
| `query_raw_sql` | latest weekly trend | `/tmp/weekly_trend.json` |
| `query_raw_sql` | active `goal_policy_versions` row (`status='active'`) | `/tmp/active_goal_policy.json` |
| `query_raw_sql` | recent `agent_memory` goal/preference rows | `/tmp/active_goal_memory.json` |
| `get_active_program` | `{}` | `/tmp/active_program.json` |

Then run:

```bash
bash scripts/trim_payloads.sh
python3 scripts/extract.py
```

Do not inspect the intermediate files unless a script fails.

The active goal files are not optional context for synthesis. They are the
current policy input. `scripts/extract.py` folds them into
`/tmp/data.json.goal_context`, including strict categories, artifact target,
lock cutoff, Windows distraction budget, and whether the career search is
closed.

Browser activity is semantic enrichment for RescueTime browser/app time, not
additional time. Use it to explain what browser time did (repo/build/AI/docs or
distraction), while RescueTime remains authoritative for total duration and
device magnitude. Keep the query compact and redacted: host, device, browser,
minutes, event count, and up to three path hints; never print raw URLs or titles.

## Stage 0.75 - Calendar Busy-Window Read

Before writing `/tmp/briefing_overlay.json`, derive Google Calendar busy windows
for today's planning horizon using bounded Google Calendar plugin event search
only. Use `mcp__codex_apps__google_calendar._search_events`; do not call
`_get_availability` for this routine. The only scheduling question is whether
`primary` or `$BRIEFING_CALENDAR_ID` has occupied slots in the 7:00 AM-10:00 PM
ET planning window.

Query only `primary` and `$BRIEFING_CALENDAR_ID` for `$TODAY_ET` 7:00 AM-10:00 PM
America/Toronto. Persist compact raw search responses as
`/tmp/calendar_search_primary.json` and `/tmp/calendar_search_briefing.json`
when using the shell/file workflow, then classify the pair:

```bash
python3 scripts/calendar_search_policy.py \
  --primary /tmp/calendar_search_primary.json \
  --briefing /tmp/calendar_search_briefing.json \
  --out /tmp/calendar_search_policy.json
```

If the policy output says `retry_recommended=true` and
`recommended_action=bounded_recheck_once`, do exactly one bounded re-check on
both calendars with the same `time_min`, `time_max`, and `timezone_str`. Replace
the raw search files with the re-check results and run
`scripts/calendar_search_policy.py` again before deciding whether Calendar is
blocked.

Persist a compact derived summary as `/tmp/calendar_busy.json`:

```json
{
  "status": "ok",
  "calendar_ids": ["primary", "<briefing calendar id>"],
  "time_min": "<RFC3339>",
  "time_max": "<RFC3339>",
  "busy_windows": [{"start":"<RFC3339>","end":"<RFC3339>","calendar_id":"<id>"}],
  "busy_window_count": 0
}
```

Rules:

- Busy windows are hard constraints for the synthesized `schedule_blocks`.
- Do not print or persist titles, locations, descriptions, attendees, URLs, or
  IDs in `/tmp/calendar_busy.json`. Persist only
  start/end/calendar_id/transparency-derived busy windows.
- Treat opaque events as busy. Treat transparent events as non-blocking unless
  they are on `$BRIEFING_CALENDAR_ID`, where they should be treated as busy to
  avoid piling briefing blocks onto that calendar.
- Do not use `query_calendar` as a busy-window source. It is prior briefing context,
  not actual Google Calendar busy/free state.
- Do not use any data-platform MCP tool or SQL query to infer Google Calendar
  busy/free status.
- In live mode, create Calendar events when bounded event search succeeds.
- If bounded event search fails in live mode, do not create Google Calendar
  events until after the one allowed auth-like re-check has also failed.
  Continue with local payload validation and write a `calendar_write` manifest
  with `busy_source=failed`, `events_written=0`, `calendar_auth_rechecks=1`,
  `watchdog_repair_expected=true`, and the compact error. The scheduled
  Calendar watchdog owns the later missing-event repair from the same
  `daily_briefing` row.

## Stages 1-3 - Build And Validate Locally

```bash
python3 scripts/payloads.py rt
python3 scripts/payloads.py email
python3 scripts/payloads.py briefing_base "$TODAY_ET" "$TODAY_DAY_OF_WEEK" "$YESTERDAY_ET" "$YESTERDAY_DAY_OF_WEEK"
```

Write `/tmp/briefing_overlay.json` and `/tmp/narrative.txt` without printing
either file. Keep Stage 0 headlines verbatim inside `/tmp/briefing.json`.
`scripts/payloads.py briefing_base` persists them under
`stage0_headlines.{anomalies,parity,career}`; do not remove or overwrite that
field in the overlay.
Use `/tmp/calendar_busy.json` as a hard scheduling constraint: every generated
`schedule_blocks[*].time_range` must fit outside the busy windows, and each
block rationale should mention when existing calendar slots materially shaped the
placement.

### Schedule block contract (drives proactive steering, not just the calendar)

`schedule_blocks[*].category` now gates the goal-policy steering actuator: during
a *matching* block the platform tightens/relaxes Windows lock/warn enforcement.
Categories that don't match the steering taxonomy bind to nothing and the policy
silently no-ops. So:

- **Use ONLY these canonical categories:** `project`, `gym`, `meal`, `leisure`,
  `wind_down`, `admin`, `interview`, `applications`, `engineering_rebuild`
  (aliases normalized server-side: `deep_work`→`project`, `break`→`leisure`,
  `prep`→`interview`, `job_search`→`applications`, `email`→`admin`). Do **NOT**
  invent `health`, `rest`, `career`, or `focus` — they match no policy category.
- Honor `goal_context.preferences` verbatim as scheduling constraints — the
  work-schedule preference reserves weekday business hours for the day job
  (untracked employer device: sparse telemetry there is expected, not free
  time). Never fill confirmed work hours with leisure/personal blocks.
- Map work sensibly: focused coding/study/building → `project`; workouts → `gym`;
  meals → `meal`; downtime/breaks → `leisure`; evening/sleep prep → `wind_down`;
  inbox/admin → `admin`.
- **The anchor block comes from the lifeOS program.** When
  `/tmp/data.json.program_context.today_rep` exists, emit one `project` block at
  the program's anchor slot (default 19:00–20:00 ET) labeled with the rep title
  ("Dojo rep: <title>") — this is the block the active goal policy binds to and
  steering protects. Move it only around hard calendar conflicts; never
  re-decide the rep. Saturdays (`milestone` family) size it 90–120 min. If the
  program is stale-carryover, keep serving the rep and add a `risk_flags[]`
  note.
- Fallback when no program exists — **the active goal is skill-building.**
  Include **at least one `project` (or `deep_work`) block** for genuine
  hands-on building/practice, placed in a free window **before 8:00 PM ET**
  (the lock cutoff). Without a matching `project` block the day's enforcement
  stays inert.
- If `/tmp/data.json.goal_context.artifact_target_min` is present, at least one
  pre-cutoff `project`/`deep_work` block should meet or exceed that duration.
  Otherwise validation will warn that the active policy's artifact target has
  no matching schedule container.
- If `/tmp/data.json.goal_context.career_search_closed=true`, preserve the
  Stage 0 career headline verbatim in diagnostic fields, but do **not** turn it
  into `priority_actions`, `applications` blocks, `interview` blocks, outbound
  job-search tasks, or hero copy. Demote stale career-stall signals to
  `risk_flags[]`, `reasoning.cross_domain_insight`, or source-quality caveats.
  Also suppress `mem_career` in the diagnostic memory section; do not report it
  as a saved or would-save memory while career search is closed.
- `hero.evidence[]` must use server-compatible objects with `source` and
  `signal`; do not emit `detail`. `priority_actions[].source` must be one of
  `rescuetime`, `email`, `calendar`, `health`, `career`, `cross-domain`, or
  `user_profile`. When the active goal policy drives an action, use
  `user_profile` and cite the policy in `context`; do not emit `goal_policy` as
  a priority-action source.
- Use `rt_yesterday.artifact_conversion.browser_*`,
  `browser_artifact_evidence`, `browser_distraction_evidence`, and
  `browser_category_minutes` to interpret browser time. Do not add browser
  minutes on top of `focus_yesterday.device_split` or RescueTime totals.
  Low CI/deploy/build-browser minutes are weak evidence, not proof that no work
  shipped. Use "no deploy/CI evidence visible" unless a commit, PR, deploy, or
  explicit source proves the stronger claim. Do not write "nothing shipped",
  "the work was never deployed", or "artifact target remains unmet" from weak
  evidence alone.
- `focus_yesterday.device_split[*].total_hours` is authoritative for device
  magnitude. Preserve exact Stage 0 headlines in `stage0_headlines`, but do not
  repeat contradicted device-share prose such as "all Mac", "Mac share 100%",
  or "100% Mac screen time" when another device has nonzero tracked hours.

```bash
python3 scripts/payloads.py briefing_finalize /tmp/briefing_overlay.json
python3 scripts/validate_payloads.py --rt /tmp/rt_yesterday.json --email /tmp/email_daily.json --briefing /tmp/briefing.json --narrative /tmp/narrative.txt --briefing-context /tmp/briefing.json
python3 scripts/calendar_plan.py --briefing /tmp/briefing.json --busy /tmp/calendar_busy.json
```

Build and validate the agent envelope before any agent write:

```bash
AGENT_EXECUTION_MODE=scheduled_codex ROUTINE_MODE=dry_run \
  scripts/write_agent.sh \
  "Morning briefing pipeline for $TODAY_ET ($TODAY_DAY_OF_WEEK), analyzing $YESTERDAY_ET ($YESTERDAY_DAY_OF_WEEK)" \
  /tmp/narrative.txt >/tmp/write_agent_dry_run_summary.json
```

The validator must pass with zero control characters in `final_response`.

## Native Writes

For native writes, use the local payload files as source material but do not
print the large write arguments. Record only IDs:

1. `write_llm_run`: `rt_yesterday`, `stage1_rt`.
2. `write_llm_run`: `email_daily`, `stage2_email`.
3. `write_llm_run`: `daily_briefing`, `stage3_briefing`.
4. `write_agent_run`: one iOS-visible row using `/tmp/write_agent_body.json`.

If a native write returns an ID, record it and continue. Do not retry it.

## Stage 3.5 - Calendar-Aware Create

In dry-run mode, do not call Google Calendar create-event. Parse valid event
candidates and report them as `would_create`.

In live mode, use `mcp__codex_apps__google_calendar._create_event` after a
successful bounded plugin event-search busy-window read on both `primary` and
`$BRIEFING_CALENDAR_ID`. Do not call `_get_availability`. Do not update or
delete events.

Source of truth: `/tmp/briefing.json.schedule_blocks`, parsed once by
`scripts/calendar_plan.py` into:

- `/tmp/calendar_create_plan.json` — parsed candidate plan for local debugging;
  do not print it in chat.
- `/tmp/calendar_plan_summary.json` — compact counts for reports and manifests.
- `/tmp/calendar_create_args_private.json` — connector arguments for valid
  create calls; do not print it in chat.

Rules:

- Calendar ID:
  `ff7309f0b8bd71efd0d2776e7d3755c9a68e9c08e220a5ef0601788d5f6aeaa6@group.calendar.google.com`
- Create on the briefing group calendar only. Use `attendees=[]`,
  `self_attendance=omit`, and `add_google_meet=false` for every create-event
  call so Google Calendar does not add an accepted attendee copy on `primary`.
- Do not set `self_attendance=accepted`.
- Calendar event titles should be the schedule block `activity` text directly.
  Do not add a `Briefing:` prefix; the event is already scoped by the briefing
  group calendar.
- `deleted_prior=0` always.
- Skip unparseable blocks, blocks before 7:00 AM, blocks after 10:00 PM, and
  non-positive durations.
- Skip any block that overlaps `/tmp/calendar_busy.json.busy_windows`.
- Do not reimplement time parsing by hand during the run. Use
  `scripts/calendar_plan.py` and create only the candidates it emits.
- Calendar noise can be reduced without weakening proactive steering by setting
  `schedule_blocks[*].calendar_publish=false` on low-value blocks, or by running
  `scripts/calendar_plan.py --publish-categories project,gym,meal,wind_down`.
  The full `schedule_blocks` list remains the policy source; this only controls
  which blocks become Google Calendar events.
- Dry run: create zero events and write zero rows.
- Live run: create all valid events in parallel and always write a
  `calendar_write` row, including errors if any.
- After live create-event calls, do a bounded read-back on the briefing group
  calendar and `primary` for the same 7:00 AM-10:00 PM ET window. Verify by
  event ID/count only; do not print or persist titles, descriptions, locations,
  attendees, URLs, or other event detail. `target_verified=yes` only when the
  created event IDs are found on the briefing group calendar. `target_verified`
  must not be `yes` when `actual_calendar_creates=0`; use
  `skipped_manifest_only` for diagnostic replay or manifest-only skipped
  calendar mode. `primary_copies` must be `0`; any value above `0` means the run
  needs inspection.
- `calendar_write` must include `busy_source`, `busy_window_count`,
  `conflict_skipped`, `busy_calendar_ids`, `target_verified`,
  `actual_calendar_creates`, and `primary_copies`. Use `busy_source=search` for
  a successful bounded-search busy-window read and `busy_source=failed` when
  bounded search fails.

## Stage 4 - Memory Diagnostics

Recall each non-null Stage 0 memory candidate key with `limit=3`. Do not save
anything.

Final report must say: `memory keys saved: none`.

## Final Compact Report

After local files and write IDs are available, run:

```bash
python3 scripts/canary_report.py \
  --pipeline-id "$PIPELINE_ID" \
  --mode "$ROUTINE_MODE" \
  --today-et "$TODAY_ET" \
  --yesterday-et "$YESTERDAY_ET" \
  --rt-id "$RT_YESTERDAY_ID" \
  --email-id "$EMAIL_DAILY_ID" \
  --briefing-id "$DAILY_BRIEFING_ID" \
  --calendar-write-id "$CALENDAR_WRITE_ID" \
  --agent-run-id "$AGENT_RUN_ID" \
  --calendar-events-written "$EVENTS_WRITTEN" \
  --calendar-would-create "$WOULD_CREATE" \
  --calendar-skipped "$SKIPPED" \
  --calendar-conflict-skipped "$CONFLICT_SKIPPED" \
  --calendar-deleted-prior 0 \
  --calendar-busy-source "$BUSY_SOURCE" \
  --calendar-busy-windows "$BUSY_WINDOW_COUNT" \
  --calendar-target-verified "$TARGET_VERIFIED" \
  --calendar-primary-copies "$PRIMARY_COPIES" \
  --next-action "keep active unless errors require repair"
```

Return that concise report, not the payloads.
