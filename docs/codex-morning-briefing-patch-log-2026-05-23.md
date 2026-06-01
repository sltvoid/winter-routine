# Codex Morning Briefing Patch Log - 2026-05-23

This note records the process used to move the morning briefing routine from
dry-run review toward a Codex-native live canary. It is meant to explain the
operational decisions and code patches without exposing secrets.

## Starting Point

The original scheduled routine was designed around a remote Claude Code
environment that cloned this repo, used HTTP MCP via `scripts/mcp.sh`, wrote
`llm_runs`, wrote an iOS-visible `agent_runs` row, created Google Calendar
events, and saved memory candidates.

For Codex, the first goal was different: make the routine testable and
reviewable inside the Codex app before enabling daily live execution.

The first dry-run prompt required:

- no database writes,
- no memory/profile/calendar writes,
- exact would-write envelopes in chat,
- current data-platform docs as the source of truth when they conflict with
  this repo,
- clean `agent_runs.final_response` with no leading `Response contract:` block,
- `tool_calls[0].classification.agent_kind = "morning_briefing"`.

## Main Decisions

### Use Native Data-Platform MCP For Codex

HTTP MCP through `scripts/mcp.sh` failed in the Codex automation runner because
the network path depended on unavailable DNS, HTTPS, Tailscale, or SSH access.
Several canaries stopped before Stage 0 with curl or SSH transport errors.

The Codex app already had the local `data-platform` MCP server installed, so the
canary was changed to prefer native `mcp__data_platform__.*` tools first. This
made `compute_daily_insights`, supplementary reads, `write_llm_run`, and
`write_agent_run` usable without relying on the broken HTTP transport.

The smoke test is now diagnostic only. The live gate is Stage 0:
`compute_daily_insights` must succeed exactly once for `YESTERDAY_ET`.

### Keep Stage 0 Authoritative

The pipeline preserves the three Stage 0 headlines verbatim downstream:

- anomalies headline,
- parity headline,
- career headline.

Supplementary SQL and read tools are allowed only for fill-in fields such as
device totals, health metrics, email details, schedule context, and source
quality. They must not override focus, app parity, or career verdicts from
`compute_daily_insights`.

### Do Not Save Morning Memory Candidates

The morning briefing now treats Stage 0 memory candidates as diagnostics only.
No `save_memory` call should happen in this pipeline. Durable pattern promotion
belongs to the learner routine.

### Calendar Is Write-Only, But Needs Auth

Calendar writes are create-only:

- do not list events,
- do not delete events,
- do not read calendar state,
- always record a `calendar_write` manifest row.

The first live canary created 7 of 8 events. One Google Calendar call failed
with a reauthentication error, so Calendar auth must be refreshed before daily
schedule enablement.

## Live Canary Result Before Patch

Native canary `d7423244-c3f2-41ef-b4cb-b802c0a538da` wrote:

| Row | ID |
| --- | --- |
| `rt_yesterday` | `3125` |
| `email_daily` | `3126` |
| `daily_briefing` | `3127` |
| `calendar_write` | `3128` |
| `agent_runs` | `73498beb-3d07-4245-b061-eef7153a86c3` |

Good results:

- native Stage 0 succeeded,
- all database writes succeeded,
- final response was clean plain text,
- agent classification was correct,
- 7 calendar events were created,
- no memory keys were saved.

Issues found during row inspection:

- `email_daily.career_days_since_last_genuine` was `0` even though Stage 0 said
  no genuine outreach was found in the trend window.
- `email_daily.actionable_emails` was a counts object instead of an array of
  email items.
- `rt_yesterday.artifact_conversion.top_artifact_tools` included `bf6`, a
  distraction, because it reused the top-apps list.
- `daily_briefing.focus_yesterday.productive_ratio` was a placeholder value.
- `health_summary.sleep_note` and several `source_quality.notes` fields were
  empty.

## Code Patches

### `scripts/extract.py`

The extractor now:

- preserves `days_since_last_genuine = null` instead of coercing it to `0`,
- adds `career_days_note` when no genuine signal exists in the trend window,
- carries compact `email_rows` for downstream email payloads,
- rounds health metrics for readable output,
- carries `analyzed_date` from the Stage 0 response so payloads do not depend on
  shell environment variables for date fields.

### `scripts/payloads.py`

The payload builder now:

- builds `artifact_conversion` from positive artifact/editor evidence only,
- excludes distraction apps from `top_artifact_tools`,
- emits `actionable_emails` as an array of reviewable email objects,
- excludes obvious agent/system login noise from actionable email candidates,
- keeps `career_days_since_last_genuine` as `null` when unknown,
- computes the real productive-to-distracting ratio from device totals,
- fills health sleep notes and source-quality notes,
- supports current `hero` and `priority_actions` briefing fields.

### `scripts/validate_payloads.py`

The validator now checks:

- `daily_briefing.hero`,
- `daily_briefing.priority_actions`,
- no legacy `actionable_items` in final briefing output,
- `rt_yesterday.artifact_conversion`,
- no negative-productivity apps in `top_artifact_tools`,
- `email_daily.actionable_emails` is an array,
- `career_days_since_last_genuine` is not false `0` when today has zero genuine
  signals,
- agent classification metadata.

## Validation Commands

Local validation was run against the previous canary input files in `/tmp`:

```bash
python3 -m py_compile scripts/extract.py scripts/payloads.py scripts/validate_payloads.py
python3 scripts/extract.py
python3 scripts/payloads.py rt
python3 scripts/payloads.py email
python3 scripts/payloads.py briefing_base 2026-05-23 Saturday 2026-05-22 Friday
python3 scripts/payloads.py briefing_finalize /tmp/briefing_overlay.json
python3 scripts/validate_payloads.py --rt /tmp/rt_yesterday.json --email /tmp/email_daily.json --briefing /tmp/briefing.json
```

Expected result:

```text
validate_payloads: ok
```

Verified generated fields:

- artifact tools: `Visual Studio Code` only,
- actionable email count: `2`,
- `career_days_since_last_genuine: null`,
- briefing productive ratio: `5.0h productive / 3.2h distracting (1.6:1)`,
- sleep note includes sleep average and HRV comparison.

## Post-Patch Database-Only Retry

After validation, a database-only retry wrote corrected rows without creating
new Google Calendar events. Calendar creation was intentionally skipped to avoid
duplicating the 7 events already created by the previous canary.

Pipeline:

```text
7f70b6eb-cbff-49a0-8734-8bce2cab74d9
```

Rows:

| Row | ID |
| --- | --- |
| `rt_yesterday` | `3129` |
| `email_daily` | `3130` |
| `daily_briefing` | `3131` |
| `calendar_write` | `3132` |
| `agent_runs` | `18b5cc3a-7cea-4e57-b943-1d38b1933af7` |

The `calendar_write` manifest recorded:

```text
events_written=0
skipped=8
deleted_prior=0
write_policy=database_only_rerun_no_calendar_create
```

Database verification confirmed:

- `artifact_conversion.top_artifact_tools` only includes `Visual Studio Code`,
- `email_daily.actionable_emails` is an array,
- `career_days_since_last_genuine` is `null`,
- briefing productive ratio is correct,
- briefing sleep note is populated,
- `agent_runs.tool_calls[0].classification.agent_kind = "morning_briefing"`.

## Current Recommendation

Keep the live canary automation paused until Google Calendar auth is refreshed.

After Calendar auth is refreshed:

1. Run one full native Codex canary with Calendar creation enabled.
2. Inspect the new `rt_yesterday`, `email_daily`, `daily_briefing`,
   `calendar_write`, and `agent_runs` rows.
3. Confirm the Calendar manifest has `events_written` equal to the number of
   eligible schedule blocks, `deleted_prior=0`, and no reauth error.
4. Enable the daily schedule only after that successful full canary.

## Notes For Future Changes

- Do not reintroduce HTTP smoke test as a hard gate for Codex native canaries.
- Do not let `query_raw_sql` override Stage 0 verdicts or headlines.
- Do not save Stage 0 memory candidates from this morning pipeline.
- Do not prefix `agent_runs.final_response` with a response-contract block.
- Be careful with calendar reruns: because the runbook is write-only and does
  not read/delete existing events, a second full calendar run can duplicate
  events for the same date.
