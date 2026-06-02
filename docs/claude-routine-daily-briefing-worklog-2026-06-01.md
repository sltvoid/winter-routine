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

### Diagnostic run `b6f9b529-4b8c-40ac-9ae0-d5af7f1a8986`

Observed behavior after the active-goal steering commit `66d52d8`:

- routine checkout reached `66d52d8`
- initial `git pull --ff-only` failed because the Claude routine was on a local
  branch with no upstream, but `HEAD` matched `origin/main`
- smoke test passed
- replay guard correctly switched to diagnostic replay
- Stage 0.75 skipped raw calendar search for token budget
- Stage 3 generated a productivity-aligned briefing narrative centered on
  MacBook, VS Code, 60+ minutes of focused coding, one visible commit/design
  artifact, and Windows distraction control
- validator caught one remaining career-language leak inside a schedule block
  rationale; Claude removed it and validation passed
- Stage 3.5 stayed manifest-only with `actual_calendar_creates=0`
- Stage 4 completed and all candidate memories were exact-match dedupes

MCP verification showed:

- `llm_runs: 0 rows`
- `agent_runs: 0 rows`

Remaining issue found:

- `scripts/write_run.sh` still raised `KeyError: 'MODEL'` when no `MODEL` was
  exported. Root cause: the script defaulted `MODEL` as a shell variable, but
  the Python envelope builder read `os.environ["MODEL"]`.

Follow-up fix:

- `scripts/write_run.sh` now passes the defaulted model value to Python as an
  argument instead of exporting `MODEL`.
- `tests/test_write_helpers.py` covers dry-run write behavior when `MODEL` is
  absent and asserts the helper does not contain `export MODEL`.

### Diagnostic run `e907ca85-d7db-4687-aebf-45087d0c3ac6`

Observed behavior after the write-helper fix commit `bbafcfc`:

- repo freshness preflight used `git fetch origin main`, compared `HEAD` to
  `origin/main`, and verified the checkout at
  `bbafcfcb05350929f9566a79976f4ce195e68837`
- smoke test passed with all 8 required daily-briefing tools present
- replay guard correctly switched to `diagnostic_replay` because same-day rows
  already existed
- Stage 0 through Stage 4 completed
- Stage 0.75 skipped raw Calendar search and recorded
  `calendar_search_skipped_for_token_budget`
- Stage 3 generated an artifact/productivity-centered briefing:
  - hero: `Ship one concrete coding artifact`
  - `hero.action_type=artifact`
  - rank 1 action: open MacBook IDE and commit one coding artifact before noon
  - career remained diagnostic-only with `career_search_closed=true` and
    `career_pulse.structured_pipeline_status="suspended"`
- `validate_payloads.py --briefing /tmp/briefing.json` passed on the generated
  briefing
- Stage 3.5 stayed manifest-only with `actual_calendar_creates=0`
- Stage 4 completed; all three memory candidates exact-key matched existing
  rows, so no saves were needed
- final run log reported `fatal_errors=[]` and `recovered_errors=[]`
- no runtime `MODEL` failure occurred and no `export MODEL=` recovery was used

MCP verification showed:

- `llm_runs: 0 rows`
- `agent_runs: 0 rows`

Remaining issue found:

- The run was 121,849 bytes. The largest contributors were full dry-run helper
  envelopes and broad runbook/API text, not Calendar JSON.
- The routine still printed full `output_response` content from dry-run
  `write_run.sh` / `write_agent.sh` calls, even when the prompt asked for
  compact summaries.

Status after this run:

- Golden for diagnostic replay behavior.
- Not yet golden for token efficiency.
- Not yet proven on a fresh non-duplicate live-write morning.

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
- `scripts/write_run.sh`
- `morning-briefing.md`
- `tests/test_goal_context_and_validation.py`
- `tests/test_runbook_contract.py`
- `tests/test_write_helpers.py`
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
- dry-run `write_run.sh` works without an exported `MODEL`
- `write_run.sh` does not contain `export MODEL`

## Routine Prompt Decisions

The current paste-ready routine prompt should keep:

- literal credential export block, because Claude Code Routines have no env-var
  UI
- `git fetch origin main` plus explicit `HEAD` vs `origin/main` comparison and
  fast-forward merge before smoke test
- no `MODEL` export at any point, including recovery
- credential export at the start of every MCP-related Bash block
- manifest-only calendar test mode
- raw calendar JSON ban
- active goal action-selection rule
- career-closed / career-suspended demotion rule
- Stage 4 mandatory completion
- compact final summary with fatal/recovered errors

## Open Follow-Ups

- Add a repo-side compact dry-run mode for `scripts/write_run.sh` and
  `scripts/write_agent.sh`, because dry-run would-call envelopes are now the
  dominant transcript bloat source.
- Tighten the prompt further so Claude inspects only targeted headings from
  `morning-briefing.md` / `api-catalog.md` instead of reading broad file
  sections.
- Consider updating the live `goal_policy_versions.valid_until` for the active
  productivity goal. It was observed as `2026-05-29` despite `status='active'`,
  which is confusing for future agents. This is a live data decision, not a
  repo-only change.
- Run the updated routine on a non-duplicate morning to verify the fresh live
  write path writes a productivity-aligned `daily_briefing` row.
