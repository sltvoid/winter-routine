# Claude Routine Daily Briefing Worklog - 2026-06-01

This note documents the Claude Code Routine daily-briefing hardening work and
the evidence gathered from the test runs. It intentionally omits the literal
MCP API key.

## Scope

The work centered on the scheduled Claude Code Routine for the daily morning
briefing. The routine reads `morning-briefing.md`, calls the personal data
platform MCP, writes `llm_runs` / `agent_runs`, optionally writes the briefing
calendar, and performs Stage 4 memory recall/save.

The user's current operating goal is productivity and hands-on technical
skill-building, not job search. The active goal data observed in MCP was:

- consistent hands-on technical skill-building
- focused deep-work blocks for coding practice, system design study, and
  personal projects
- strict `project` schedule categories
- 60 minute artifact target
- 8 minute Windows distraction budget

## Sensitive Prompt Handling

An early routine prompt contained the literal MCP API key. The repo was treated
as prompts/protocols only and the prompt was not committed as a tracked file.
The local prompt filename `claude-routine-morning-briefing.md` is ignored by
`.gitignore` so paste-ready routine prompts can be kept local without being
pushed.

The user later clarified that Claude Code Routines do not provide a separate
environment-variable UI, so the paste-ready routine prompt must include the
literal credential export block. Chat and docs should still avoid reprinting
the key unless the user explicitly asks for paste-ready prompt text.

## Repo Hardening Already Applied

### Commit `7156e0d` - routine contract update

Added or expanded the main morning briefing runbook, calendar repair/watchdog
docs, helper scripts, smoke test, replay guard, calendar planning/coverage
helpers, payload builders, validators, and focused tests.

### Commit `44ae369` - routine contract hardening

Hardened the daily briefing payload contract:

- fuller hero schema validation
- server enum drift guardrails
- default `MODEL` handling in shell write helpers
- goal context extraction improvements
- closed-career handling
- trim/budget checks for context payloads

### Commit `2e459cf` - diagnostic tightening

Added:

- `scripts/anchor_env.sh` for one-time date/pipeline anchoring
- `scripts/run_log.sh` for compact fatal/recovered error tracking
- stricter runbook output discipline
- final summary requirements
- calendar raw-output redaction guidance
- validator handling for `career_pulse.structured_pipeline_status="suspended"`

## Claude Routine Test Runs Reviewed

### Diagnostic run `8ad126fe-4125-42d2-9d21-20c1b5667ef0`

Observed behavior:

- smoke test initially failed due missing env in the Bash call, then passed
- replay guard correctly switched to diagnostic replay
- Stage 0 through Stage 4 completed
- no rows were written for that pipeline
- raw Google Calendar JSON leaked into the transcript
- `MODEL` raised `KeyError`, indicating the routine was using a stale checkout
  or cached script despite the current repo defaulting `MODEL`
- validator rejected `hero.action_type="project"` and a career priority action;
  Claude corrected to `artifact` and removed the career action

MCP verification showed:

- `llm_runs: 0 rows`
- `agent_runs: 0 rows`

### Diagnostic run `7984292e-d8dd-422f-b72e-0f7b2a5e008a`

Observed behavior after the manifest-only prompt update:

- `git pull --ff-only` ran and reported the checkout was current
- smoke test passed
- replay guard correctly switched to diagnostic replay because same-day rows
  already existed
- Stage 0.75 skipped raw calendar search for token budget
- Stage 3.5 used `calendar_mode=manifest_only`
- `actual_calendar_creates=0`
- Stage 4 completed and all three candidate memory keys were deduped
- no fatal or recovered errors were logged

MCP verification showed:

- `llm_runs: 0 rows`
- `agent_runs: 0 rows`

The run still produced a large transcript because the model printed/read too
much runbook and dry-run would-write output. The next optimization should be a
compact dry-run writer mode, not only Calendar suppression.

## Persisted DB State Observed

For June 1, 2026, replay guard was legitimate because same-day rows already
existed.

Latest saved same-day rows included:

- `daily_briefing id=3309`, pipeline `f75a218f-4018-4a2c-9f98-388adfc89975`
- `calendar_write id=3310`, same pipeline, `events_written=0`

The latest saved `daily_briefing` row was career-biased:

- hero: `Send one real application`
- `hero_action_type=career`
- rank 1 priority action: send a genuine career application/outreach email

An earlier same-day row was better aligned:

- `daily_briefing id=3303`
- hero: `Ship one repo change`
- `hero_action_type=artifact`
- `calendar_write id=3304` wrote 14 events

The improved diagnostic prompt generated a cleaner artifact-focused briefing,
but replay guard prevented it from replacing the already-saved career-biased
row. The fix therefore needed to harden future writes rather than rely on a
same-day diagnostic replay.

## Current Change

The active productivity goal is now enforced as a validation contract, not only
as prompt guidance.

Changed files:

- `scripts/validate_payloads.py`
- `morning-briefing.md`
- `tests/test_goal_context_and_validation.py`
- `tests/test_runbook_contract.py`
- `docs/claude-routine-daily-briefing-worklog-2026-06-01.md`

Validator behavior:

- detects active productivity/skill-building goal context
- requires the hero to align with artifact shipping, focus correction, or
  learning unless there is a concrete hard blocker
- requires rank 1 priority action to directly serve the active goal unless
  there is a concrete hard blocker
- requires lower-ranked priority actions to either serve the goal directly or
  support it through focus protection, sleep, workouts, meals, recovery, or
  distraction control
- rejects generic inbox/career cleanup when it is promoted above the active
  goal

Runbook behavior:

- makes the active goal policy the action-selection authority
- explicitly states that stale career, generic email, and inbox cleanup must not
  be promoted above the active goal
- keeps career-stall signals as diagnostics/risk flags when career search is
  closed or suspended

Tests added:

- active productivity goal rejects non-goal hero and top action
- active productivity goal allows artifact and focus-protection actions
- runbook contains the active-goal action-selection contract

## Routine Prompt Decisions

The current paste-ready routine prompt should keep:

- literal credential export block, because Claude Code Routines have no env-var
  UI
- `git pull --ff-only` before smoke test
- no `MODEL` export
- credential export at the start of every MCP-related Bash block
- manifest-only calendar test mode
- raw calendar JSON ban
- active goal action-selection rule
- career-closed / career-suspended demotion rule
- Stage 4 mandatory completion
- compact final summary with fatal/recovered errors

## Open Follow-Ups

- Consider a repo-side compact dry-run mode for `scripts/write_run.sh` and
  `scripts/write_agent.sh`, because dry-run would-call envelopes still inflate
  Claude Routine transcripts.
- Consider updating the live `goal_policy_versions.valid_until` for the active
  productivity goal. It was observed as `2026-05-29` despite `status='active'`,
  which is confusing for future agents. This is a live data decision, not a
  repo-only change.
- Run the updated routine on a non-duplicate morning to verify the fresh live
  write path writes a productivity-aligned `daily_briefing` row.
