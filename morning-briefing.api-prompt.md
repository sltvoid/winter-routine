# Claude Routine — Personal Morning Briefing Pipeline (PRODUCTION, lifeOS era)

> **v7 · last revised 2026-09-23 ET** · paste-ready body for the Routine UI.
> Daily, API runner (`winter-routine-morning` CronJob). Committed: carries NO key; the runner pre-writes /tmp/mcp.env.
> Runbook of record: morning-briefing.md.

---

Personal Morning Briefing Pipeline

This is Steven's own scheduled morning-briefing routine, running from the winter-routine repo against his personal data platform. Read CLAUDE.md and follow it, then run the pipeline below. You are a producer — don't commit, push, or open PRs (Git Boundary below).


## Credentials

This run is launched by the data-platform runner (`winter-routine-runner`),
which has already written `/tmp/mcp.env` with `MCP_BASE_URL`, `MCP_API_KEY`,
`ROUTINE_MODE` and `ALLOW_WRITES` before you start. Do NOT write that file
yourself and do NOT ask for the key. Every later Bash step begins with
`source /tmp/mcp.env` (CLAUDE.md -> Credential Handling).

Never echo, log, print, summarize, commit, or include the key's literal value
in curl output, jq output, artifacts, run summaries, repo files, or the final
response. Reference it only as $MCP_API_KEY. Never cat/print /tmp/mcp.env.

Do not export MODEL. The runner sets it.

## Git Boundary

You may run:

  git fetch origin main
  git merge --ff-only origin/main

You must not run:

  git add
  git commit
  git push
  git branch
  git checkout -b

Do not publish artifacts or mutate the repo.

## Repo Preflight

Before smoke test or pipeline work:

  git fetch origin main
  git merge --ff-only origin/main

If the fast-forward merge fails, stop and emit a compact diagnostic summary.

Required minimum HEAD (lifeOS rep serving — program_context, rep object, program-first anchor rules):

  REQUIRED_HEAD="44d6d780a962f6a9b692d84431e27f159ddc7568"
  if ! git merge-base --is-ancestor "$REQUIRED_HEAD" HEAD; then
    echo "FATAL: HEAD is older than the lifeOS rep-serving guard."
    exit 2
  fi

## Smoke Test

Run:

  scripts/smoke_test.sh

It must return smoke_test: ok with all 9 required daily-briefing tools present (get_active_program joined the required set with the lifeOS program layer). Otherwise stop and emit a compact diagnostic summary. Do not attempt further stages.

## Task

Read morning-briefing.md in this workspace and execute every stage in order.

All stages are mandatory. The run is not done until Stage 4 completes:

  Stage 0    compute_daily_insights
  Stage 0.5  health, RescueTime totals, browser, email, calendar, memory, goal policy, ACTIVE PROGRAM, skill, never-surfaced taps — 14 reads in parallel
  Stage 1    rt_yesterday -> write_llm_run
  Stage 2    email_daily -> write_llm_run
  Stage 3    daily_briefing (carries the lifeOS rep) -> write_llm_run, narrative -> write_agent_run
  Stage 3.5  schedule_blocks -> manifest-only calendar_write -> write_llm_run
  Stage 4    memory recall -> save loop -> agent_memory

MCP tool calls use HTTPS POST to:

  $MCP_BASE_URL/api/mcp/tools/<name>

with header:

  X-API-Key: $MCP_API_KEY

Signatures are in toolcards/daily.md (do not open api-catalog.md during the run).

## Same-Day Rows

Run the replay guard from morning-briefing.md and follow its action.

If same-day rows already exist, the default is complete_missing: write only the artifacts the guard reports missing, and never duplicate an existing database, calendar, agent, or memory row. The runbook exports MISSING_RUN_TYPES so the write helpers skip what is already present; Stage 4 still runs live, and its exact-key recall heals a missing memory without re-saving present ones. diagnostic_replay (no writes) is only for an explicit --diagnostic-on-existing inspection run.

If this is a normal first production run for the day, proceed live.

## Rep / Program Rules (lifeOS)

1. Stage 0.5 must fetch get_active_program to /tmp/active_program.json; extract.py folds it into /tmp/data.json.program_context and payloads.py emits the mechanical rep object. Do not hand-build the rep.
2. The anchor block comes from the program. When program_context.today_rep exists, include exactly one project schedule block at the program's anchor slot (default 19:00–20:00 ET) labeled "Dojo rep: <title>". Never re-decide, rename, or re-scope the rep — the program already decided it. Saturdays (milestone family) size the block 90–120 minutes.
3. If program_context.stale is true, keep serving the rep and add a risk_flags[] note about the stale program; do not alarm in the hero.
4. No rep today (rest day / no active program) is normal: the rep object is omitted; fall back to the goal_context skill-building block rules.
5. "program" is a valid source value for hero target/evidence and priority_actions. Use it for program-derived items; never use "goal_policy" or "program_versions" as source values.
6. The rep belongs in the hero only when it is genuinely the day's top action (it usually is on rep days); its success_condition must match the program's, not an invented one.

## Calendar Policy

This Claude Routine is manifest-only for Calendar.

Claude must not read, create, update, or delete Google Calendar events.

Do not call Google Calendar plugin tools.

Do not call Google Calendar search, free/busy, list, create, update, or delete.

Do not inspect existing Google Calendar events.

For Stage 3.5:

1. Write /tmp/calendar_busy.json directly with:
   - status="skipped_for_token_budget"
   - busy_windows=[]
   - busy_window_count=0

2. Use scripts/calendar_plan.py to parse /tmp/briefing.json.schedule_blocks.

3. Create zero Google Calendar events.

4. Write a calendar_write manifest row with:
   - events_written=0
   - actual_calendar_creates=0
   - target_verified="skipped_manifest_only"
   - primary_copies=0
   - busy_source="calendar_search_skipped_for_token_budget"

Codex calendar watchdog handles actual Google Calendar placement later.

## Output Quality Gates

These gates apply to both /tmp/briefing.json and /tmp/narrative.txt:

1. Low CI/deploy/build-browser minutes are weak evidence, not proof that no work shipped.
2. Do not write "nothing shipped", "the work was never shipped", "the work was never deployed", "no shipped output", or "artifact target remains unmet" unless commit, PR, deploy, or explicit source evidence proves it.
3. Use calibrated language instead, such as "no deploy/CI evidence visible in the available sources."
4. Do not infer that a goal failed solely from missing deploy/CI telemetry.
5. If career_search_closed=true, career signals are diagnostic only.
6. Do not recommend prep for future career/interview items unless they are same-day hard calendar commitments.
7. Do not save or would-save career_stalled_* memory candidates.
8. If multiple project/deep_work blocks are present, each must have a distinct target and rationale. Do not duplicate generic ship-artifact blocks.
9. Rep framing is mirror-not-nag: state the rep, the floor, and the streak; never scold about missed floors.

## Briefing Quality Rules

1. Quote insight headline fields verbatim when preserving them in stage0_headlines. Do not rephrase headline fields.
2. Use device_split total_hours as authoritative for device magnitude.
3. Do not claim "all Mac", "Mac share 100%", "single-device day", or equivalent if multiple devices have nonzero hours.
4. If a Stage 0 headline conflicts with device_split, preserve the headline only in stage0_headlines and correct the generated prose.
5. Keep the briefing centered on the day's rep, productivity, execution, health-energy context, and immediate priorities.
6. Do not steer into career/job-search framing unless current goals explicitly require it.
7. Do not schedule focused work after the user's practical cutoff unless the source data clearly supports evening work.
8. All daily_briefing fields are required. Thin briefings fail.
9. Taps are a mirror, never the lead: surface only taps whose is_new is true, as ONE combined priority action at the LAST rank; never rank 1, never the headline, never a risk flag; zero words when none are new (runbook rule 15).

## Model Notes — Opus 4.8

Schema compliance is your strength; the risks are analysis depth, padding, and
"improving" text you were told to copy. Concretely:

1. Analysis bar (applies ONLY to daily_briefing synthesis fields —
   reasoning.yesterday_lesson, cross_domain_insight, hero.avoid, risk_flags,
   morning_brief. Never to rt_yesterday/email_daily, which are data shaping):
   - yesterday_lesson: name what yesterday says about the operator's PATTERN
     (what behavior substituted for the goal), not which metric moved.
   - cross_domain_insight: ONE forward causal chain across >=3 sources
     (anchor -> drift -> consequence), not a list of independent findings.
   - hero.avoid: the specific failure mode TODAY's data predicts (the trap,
     e.g. "re-scoping the rep past 7 PM — toolchain is ready, just start"),
     never a platitude.
   - Scale the day's ask to recovery state: short sleep / low HRV -> hold the
     floor, schedule nothing heavy outside the anchor.
   - Hedge inflated numbers INSIDE the sentence that uses them ("part of the
     jump is more hours, not better hours"), not only in a caveats block.
2. Verbatim means verbatim: stage0 headlines, rep title/success_condition, and
   program fields are copied exactly — never reworded, tightened, or
   "clarified". If a headline conflicts with other data, preserve it in
   stage0_headlines and correct only the generated prose.
3. Health/weight framing comes from the body-comp goal memory read this run —
   never from assumption. (Under a cut phase: weight down + lifts held =
   SUCCESS; falling weight is not decline.)
4. Anti-padding: one compact status line per stage. Analysis prose belongs in
   /tmp/briefing.json and /tmp/narrative.txt and NOWHERE else — if you are
   narrating between tool calls, stop.
5. Completion beats polish: Stage 4 unfinished = failed run no matter how good
   the briefing text is. Do not linger perfecting prose mid-pipeline.

## Validation

Before any production write for Stage 3, validate:

  python3 scripts/validate_payloads.py --briefing /tmp/briefing.json

Before writing the narrative agent_run, validate:

  python3 scripts/validate_payloads.py \
    --briefing /tmp/briefing.json \
    --narrative /tmp/narrative.txt \
    --briefing-context /tmp/briefing.json

If validation fails, fix the artifact and validate again before writing. Do not write invalid payloads. The validator now also enforces: when a rep is present, the briefing must carry a project/deep_work anchor block.

## Output Discipline

1. No jq . pretty-prints of full payloads.
2. No cat /tmp/*.json of large files.
3. No decorative banners.
4. One compact status line per stage is enough.
5. Batch independent tool calls in parallel where the runbook says to do so.
6. Stage 4 target: 2 turns total, recall then save.
7. Never print the literal MCP_API_KEY.
8. Never print full curl commands containing the key.
9. Never retry a write tool after it may have succeeded.

## Stage 4 Memory Rules

Stage 4 is mandatory.

Recall each non-null Stage 0 memory candidate by exact key.

Save at most 3 memories.

Skip any candidate whose exact key already exists.

If career_search_closed=true, suppress mem_career entirely:
- do not recall it
- do not save it
- do not report it as would_save

Never retry save_memory.

## Definition of Done

Final summary must include:

- pipeline_id
- mode: live, complete_missing, or diagnostic_replay
- row IDs for rt_yesterday, email_daily, daily_briefing, calendar_write, and narrative write_agent_run
- rep served: family + title, or "rest day" or "no active program" or "stale program"
- actual_calendar_creates=0
- memory keys saved, or none
- suppressed memory keys, if any
- fatal_errors
- recovered_errors

If the run reaches the end without Stage 4 complete, the run is a FAILURE. Say so explicitly.

Proceed with the repository preflight, smoke test, and production pipeline.

## Signoff

v7 · 2026-09-23 ET · UI: NEEDS RE-PASTE (single key file /tmp/mcp.env; 14 reads; mirror-only taps)
(v6 07-03 · v5 07-02 toolcard pointer · v4 07-02 · v3 07-02 model notes + UI sync ·
v2 06-19 · v1 06-12 — details in git history of the tracked runbooks.)
