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

## Late-Session Model And Prompt Testing

After the repo hardening work, the session moved into Claude Routine model and
token testing. The main question was whether Claude Opus, Claude Sonnet, or the
existing Codex `gpt-5.5` daily automation best fit the daily briefing use case.

All Claude Routine tests below were diagnostic replays because same-day rows for
`TODAY_ET=2026-06-01` already existed. That means the tests are useful for
prompt obedience, output quality, and token/runtime behavior, but they do not
prove a fresh live write path.

### Opus diagnostic replay - first final-prompt test

Attachment reviewed:

- `/Users/steventa/.codex/attachments/236eb450-97ed-4233-b580-f0e0b4f8dde0/pasted-text.txt`
- transcript size: 82,377 bytes

Observed behavior:

- repo preflight fetched `origin/main`, fast-forwarded from `bbafcfc` to
  `77eb455998474db0829b9dc4b9c5707f1ad245e5`, and passed smoke test
- replay guard entered `diagnostic_replay` for pipeline
  `eaf8f616-9519-46f1-963a-5ad1fab79a96`
- no `MODEL` export failure occurred
- Stage 0 through Stage 4 completed
- Calendar stayed manifest-only with `actual_calendar_creates=0`
- memory candidates were exact-key dedupes and saved none
- hero and rank 1 action were artifact/productivity aligned:
  `Ship one repo change`
- career stall was preserved as diagnostic-only, not promoted into the hero

Issue found:

- Opus created/pushed a redundant branch even though `HEAD` already matched
  `origin/main`. The prompt was tightened afterward with a repo preflight rule:
  fetch/fast-forward only; do not create branches, set upstreams, commit, or
  push.

Assessment:

- best Claude quality/control at that point
- still higher session budget than desired
- useful for stabilization, not the best daily default

### Sonnet diagnostic replay - compact prompt, first pass

Attachment reviewed:

- `/Users/steventa/.codex/attachments/55abad2a-0b48-4276-ad2d-9b8218977e8b/pasted-text.txt`
- transcript size: 80,965 bytes
- user-observed usage: 38 percent to 49 percent, or 11 percentage points

Observed behavior:

- pipeline `6e467579-32b4-4af3-b8ca-af87eccc39de`
- git HEAD
  `77eb455998474db0829b9dc4b9c5707f1ad245e5`
- replay guard action: `diagnostic_replay`
- `TODAY_ET=2026-06-01` and `YESTERDAY_ET=2026-05-31`
- Stage 4 completed
- calendar manifest-only mode held, with `actual_calendar_creates=0`
- hero and rank 1 action were productivity aligned:
  `Ship one concrete repo change`
- career remained diagnostic-only

Important date interpretation:

- The run happened around 9 PM Eastern on June 1, 2026.
- `TODAY_ET=2026-06-01` was correct for America/Toronto at that time.
- The model's warning about external session metadata saying June 2 was noise;
  `anchor_env.sh` and America/Toronto wall-clock should be authoritative.

Prompt update made afterward:

- Added date sanity guidance:
  - use America/Toronto as source of truth
  - do not treat external session metadata as authoritative over
    `anchor_env.sh`
  - only flag a date mismatch if `TODAY_ET` is wrong for America/Toronto
    wall-clock time

Assessment:

- functionally clean diagnostic replay
- quality good enough
- token usage acceptable but not fully optimized

### Opus diagnostic replay - stricter compact prompt

Attachment reviewed:

- `/Users/steventa/.codex/attachments/7293d1f0-7150-459f-ae3b-ec0e52eca861/pasted-text.txt`
- transcript size: 41,265 bytes
- user-observed usage: 51 percent to 62 percent, or 11 percentage points
- runtime: about 7 minutes

Observed behavior:

- pipeline `278cf930-6632-4bc7-a721-1e67b377bdcd`
- git HEAD
  `77eb455998474db0829b9dc4b9c5707f1ad245e5`
- replay guard action: `diagnostic_replay`
- date check correctly accepted `TODAY_ET=2026-06-01` for 9:24 PM ET
- no branch, commit, or push behavior
- no `MODEL` export issue
- Calendar stayed manifest-only with
  `calendar_search_skipped_for_token_budget`
- Stage 4 completed
- fatal and recovered errors were empty
- briefing hero was `Ship one concrete repo change`
- career-stall headline was preserved but demoted to a risk flag

Issue found:

- Opus hand-wrote Stage 3.5 calendar-manifest Python instead of using
  `scripts/calendar_plan.py`. It worked, but it wasted reasoning/output and
  increased drift risk.

Prompt update recommended afterward:

- Stage 3.5 must use `scripts/calendar_plan.py`
- do not inspect, rewrite, or inline calendar planning logic unless
  `scripts/calendar_plan.py` fails

Assessment:

- best Claude transcript discipline so far
- still 11 percentage points of session budget because Opus spends more
  reasoning even when output is compact
- acceptable for debugging, not ideal for daily scheduled use

### Sonnet diagnostic replay - same prompt as Opus

Attachment reviewed:

- `/Users/steventa/.codex/attachments/0eb6413e-6d0d-4526-9584-689b146e8409/pasted-text.txt`
- transcript size: 104,356 bytes
- user-observed usage: 62 percent to 70 percent, or 8 percentage points
- runtime: about 8 minutes

Observed behavior:

- pipeline `aa70da85-fd13-4e95-aeb0-534fde06a46f`
- git HEAD
  `77eb455998474db0829b9dc4b9c5707f1ad245e5`
- replay guard action: `diagnostic_replay`
- Stage 4 completed
- no rows or events persisted
- hero was productivity-aligned:
  `Ship one coding artifact today`
- career remained demoted in the final result

Issue found:

- Sonnet ignored the intent of the calendar optimization. It performed/read raw
  Google Calendar event data and reconstructed calendar search files, causing a
  104 KB transcript.
- This was safe only because diagnostic replay prevented writes.

Prompt update made afterward:

- Calendar manifest-only mode became absolute for Claude Routine tests:
  - do not call Google Calendar search/read/freebusy/list/create/update/delete
  - do not inspect existing calendar events
  - do not reconstruct `/tmp/calendar_search_primary.json` or
    `/tmp/calendar_search_briefing.json`
  - always write `/tmp/calendar_busy.json` directly with
    `status="skipped_for_token_budget"`, empty `busy_windows`, and
    `busy_window_count=0`

Assessment:

- Sonnet is the better daily Claude candidate on cost
- Sonnet needs stricter prompt constraints than Opus for Calendar suppression
- Still not proven as a fresh live-write routine

## Token And Model Conclusion

Observed budget ranges:

- Opus diagnostic replay: about 11 to 13 percentage points
- Sonnet diagnostic replay: about 8 to 11 percentage points
- desired daily production target: 8 to 10 percentage points
- acceptable debug/replay target: 10 to 13 percentage points

Model conclusion:

- Claude Haiku saved run was not acceptable for this workflow; it promoted
  stale career action.
- Claude Opus produced the best Claude test quality/control but costs too much
  for default daily use.
- Claude Sonnet is the best Claude daily candidate if the routine remains in
  Claude, but it needs strict no-calendar-search and no-source-dump rules.
- Codex `gpt-5.5` remains the best proven production path because it already
  produced valid DB rows, goal-aligned content, and verified Calendar writes.

## VM Database Comparison

The VM `llm_db` comparison used read-only MCP queries against current saved
rows.

Codex production row:

- `daily_briefing id=3303`
- model: `gpt-5.5`
- pipeline: `f9b64bed-c69b-487c-aceb-6d20781ffdda`
- date: `2026-06-01`
- hero: `Ship one repo change`
- `hero_action_type=artifact`
- priority actions: 4
- schedule blocks: 14
- paired `calendar_write id=3304`
- `events_written=14`
- `target_verified=yes`
- paired `agent_runs id=6b9a9500-11ca-473e-9950-dbfeebbfe1ba`

Claude/Haiku saved row:

- `daily_briefing id=3309`
- model: `claude-haiku-4-5`
- pipeline: `f75a218f-4018-4a2c-9f98-388adfc89975`
- date: `2026-06-01`
- hero: `Send one real application`
- `hero_action_type=career`
- priority actions: 5
- schedule blocks: 8
- paired `calendar_write id=3310`
- `events_written=0`
- `target_verified=no`
- paired `agent_runs id=aba42369-cb73-430e-89a0-0c709ba9774b`

Comparison result:

- Codex/gpt-5.5 is much better than the saved Claude/Haiku row.
- Codex/gpt-5.5 is still the only path with a strong saved production proof
  from this session.
- The latest Claude Sonnet and Opus tests improved quality, but they were
  diagnostic replays and therefore do not beat the Codex production evidence.

Working model ranking from available evidence:

1. Codex `gpt-5.5` saved daily run: best real production result
2. Claude Opus diagnostic replay: best Claude quality/control, higher cost
3. Claude Sonnet diagnostic replay: acceptable and cheaper, but less obedient
4. Claude Haiku saved run: bad fit for this workflow

## Active Codex Automation Update

The active Codex daily automation was updated after the model comparison:

- automation id: `mcp-morning-briefing-clean-canary`
- name: `MCP Morning Briefing Daily`
- status preserved: `ACTIVE`
- schedule preserved: 6:00 AM ET daily
- model preserved: `gpt-5.5`
- reasoning effort preserved: `xhigh`
- execution environment preserved: `local`
- live Calendar behavior preserved

Prompt hardening added:

- repo freshness preflight:
  - `git fetch origin main`
  - compare `HEAD` to `origin/main`
  - fast-forward merge only
  - do not create branches, set upstreams, commit, or push
- stronger career demotion:
  - if `career_search_closed=true`,
    `career_pulse.structured_pipeline_status="suspended"`, or active goal is
    not career search, keep career stall as diagnostic/risk only
  - do not make career the hero, rank 1 action, or first schedule block unless
    live goal context proves career is active
- missing/partial goal-context fallback:
  - perform one compact active-goal read before synthesis
  - if unavailable, default to hands-on technical skill-building, project
    blocks, artifact shipping, and Windows distraction control
- stricter token discipline:
  - do not print source files, script bodies, runbook/API excerpts, long
    command outputs, full JSON payloads, native write arguments, final
    response, or Calendar event responses
- explicit Calendar decision:
  - keep Codex production Calendar live
  - do not switch the active Codex automation to Claude-style manifest-only
    mode

Durable automation memory was updated at:

- `/Users/steventa/.codex/automations/mcp-morning-briefing-clean-canary/memory.md`

## Open Follow-Ups

- Add a repo-side compact dry-run mode for `scripts/write_run.sh` and
  `scripts/write_agent.sh`, because dry-run would-call envelopes are now the
  dominant transcript bloat source.
- If Claude Routine testing continues, run the final Sonnet prompt once more
  with absolute manifest-only Calendar mode and verify it does not inspect
  existing Calendar events or dump source files.
- Consider updating the live `goal_policy_versions.valid_until` for the active
  productivity goal. It was observed as `2026-05-29` despite `status='active'`,
  which is confusing for future agents. This is a live data decision, not a
  repo-only change.
- Watch the next active Codex daily run and verify the newly added hardening:
  repo HEAD included in final report, career diagnostic-only when appropriate,
  project/deep-work block present, and no source/calendar payload dumps.

## Documentation Sweep Notes

Follow-up documentation cleanup should preserve the distinction between the two
daily paths:

- `morning-briefing.md` and `morning-briefing-clean-canary.md` describe the
  Codex production/canary path with live Google Calendar busy-window reads and
  conflict-free event creation.
- The ignored local `claude-routine-morning-briefing.md` prompt is for Claude
  Sonnet/no-`MODEL` testing and should stay Calendar manifest-only to conserve
  Claude Routine budget.
- README and API examples should describe `MODEL` as optional helper metadata
  that defaults to `routine-selected`, not as a required exported env var.
- Session notes mentioning the Claude Haiku row are historical evidence, not the
  current recommendation.

## 2026-06-05 Production Split Update

The current production design separates briefing synthesis from Calendar
execution:

- Claude Code Routine is the briefing producer. It runs the daily briefing
  pipeline, writes `rt_yesterday`, `email_daily`, `daily_briefing`, the
  narrative `agent_run`, and a manifest-only `calendar_write` row.
- Claude does not create Google Calendar events in the daily prompt. This keeps
  token usage lower and avoids large Calendar response transcripts.
- Codex owns Calendar execution through the active late watchdog. It reads the
  latest same-day `daily_briefing.schedule_blocks[]`, searches Calendar
  directly, plans around hard conflicts, creates only missing future events, and
  writes the repair/verification `calendar_write` manifest.
- The Claude prompt still uses the routine-selected model. No `MODEL` export is
  required in the prompt.
- The paste-ready Claude prompt may include the literal MCP key because the
  Routine UI has no separate environment-variable field. This worklog and repo
  files intentionally do not contain the literal key.

Latest clean Claude diagnostic handoff reviewed:

- pipeline: `2ea3ce53-9c9d-4df0-ae85-072b2fd20127`
- mode: `diagnostic_replay`
- artifacts reviewed from Downloads:
  - `briefing(4).json`
  - `briefing_overlay(3).json`
  - `rt_yesterday(4).json`
  - `email_daily(4).json`
  - `narrative(4).txt`
  - `calendar_handoff(2).json`
  - `run_summary(2).json`
- validation command passed:
  `python3 scripts/validate_payloads.py --briefing /Users/steventa/Downloads/briefing\(4\).json --narrative /Users/steventa/Downloads/narrative\(4\).txt --briefing-context /Users/steventa/Downloads/briefing\(4\).json --calendar-handoff /Users/steventa/Downloads/calendar_handoff\(2\).json`
- validation result: `validate_payloads: ok`

Quality outcome:

- no production writes during diagnostic replay
- `calendar_write_allowed=false`
- no Google Calendar create attempts from Claude
- career-stalled memory suppressed rather than saved or recommended
- no closed-career recommendation leakage
- no unsupported "nothing shipped" overclaim
- Stage 0 device headline preserved while prose corrected the Mac/Windows split
- `calendar_handoff.json` had three distinct recommended blocks:
  - `Project artifact delivery`
  - `Deep-work coding practice`
  - `Admin and inbox processing`

Repo hardening completed and pushed:

- `5e2545a Harden Claude routine handoff safeguards`
  - added `CLAUDE.md`
  - ignored `routine-artifacts/`
  - documented inline-key handling for Claude Routine prompts
  - suppressed `career_stalled_*` Stage 4 memory candidates when career search
    is closed or suspended
  - made manifest-only Calendar rows first-class
- `ae0da0c Calibrate briefing handoff output validation`
  - added guards against shipping overclaims from weak CI/deploy evidence
  - added closed-career narrative leakage validation
  - added `calendar_handoff.json` validation
  - tightened `write_agent.sh` and runbook guidance
- `1c9491d Harden calendar watchdog busy-window planning`
  - added `scripts/calendar_busy_from_search.py`
  - taught the watchdog to derive busy windows from bounded Calendar search
  - treats long Work/Office/Focus blocks as schedulable capacity, not conflicts
  - uses `calendar_coverage.py --skip-started`
  - uses `calendar_plan.py --busy /tmp/calendar_busy.json --skip-started`
  - creates only from `/tmp/calendar_create_args_private.json`
  - verified with `67` passing tests

Active automation state:

- `mcp-morning-briefing-calendar-watchdog-late` is the active Codex Calendar
  executor.
- It runs daily at `07:05` America/Toronto.
- It uses model `gpt-5.5` with `medium` reasoning.
- It runs locally in `/Users/steventa/Documents/CodingJunk/Winter-Routine`.
- It must not call `_get_availability`, update/delete Calendar events, rerun
  Stage 0, or write non-Calendar briefing rows.
- Expected successful manifest traits are `target_verified=yes` and
  `primary_copies=0`.

Operational next test:

1. Run the production Claude Routine prompt.
2. Let the late Codex watchdog run after the briefing row exists.
3. Inspect the latest `calendar_write` row.
4. Accept the split as production-ready if the row shows:
   - same-day `daily_briefing` dependency found
   - missing future blocks created or correctly no-oped
   - `target_verified=yes`
   - `primary_copies=0`
   - no raw Calendar transcript leakage
   - no closed-career memory or recommendation leakage
