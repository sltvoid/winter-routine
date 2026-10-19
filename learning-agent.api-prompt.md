# Claude Routine — Monthly Learner / Behavioral Profile Pipeline (PRODUCTION, lifeOS)

> **API runner edition · v6-api · 2026-10-19 ET.** The committed, key-free prompt the
> data-platform `winter-routine-learner` CronJob (every Sunday 12:00 ET; the gate below
> runs the learner only on the FIRST Sunday of the month) feeds to headless Claude Code;
> the runner pre-writes /tmp/mcp.env. Mirrors the Routine UI paste body
> `claude-routine-monthly-learner.v6.md`; runbook of record: learning-agent.md.

---

## Credentials

This run is launched by the data-platform runner (`winter-routine-runner`),
which has already written `/tmp/mcp.env` with `MCP_BASE_URL`, `MCP_API_KEY`,
`ROUTINE_MODE` and `ALLOW_WRITES` before you start. Do NOT write that file
yourself and do NOT ask for the key. Every later Bash step begins with
`source /tmp/mcp.env` (CLAUDE.md -> Credential Handling).

Never echo, log, print, summarize, commit, or include the key's literal value
in curl output, jq output, artifacts, run summaries, repo files, or the final
response. Reference it only as $MCP_API_KEY. Never cat/print /tmp/mcp.env.

Do not export MODEL. The runner sets it. Never re-export ROUTINE_MODE or
ALLOW_WRITES: the runner's values in /tmp/mcp.env are the mode of record and
scripts/mcp.sh enforces them mechanically.

## Run Mode

The mode is decided by the runner, never by this prompt: `source /tmp/mcp.env`
and read `ROUTINE_MODE`.

**ROUTINE_MODE=dry_run → DIAGNOSTIC.** Any day. ALLOW_WRITES is 0, write tools
are mechanically refused by scripts/mcp.sh, NOTHING is persisted (no
update_profile, no memory writes, no llm_runs/agent_runs rows, no test-write
tools). Run Stage -1 through Stage 4 as the runbook says — the Stage 0.5 fold /
sparse short-circuit is allowed and usually taken — then print the would-write
diff (section_updates, memory operations, hypotheses) and the would-write
narrative and learner_digest JSON, labeled exactly "DIAGNOSTIC — NOT WRITTEN"
(the runner passes the run on that label). If the runner's note at the end of
this prompt asks for DIAGNOSTIC_FULL, do NOT take the short-circuit: execute the
entire pipeline through the Stage 4 evidence audit and label the summary
"DIAGNOSTIC_FULL — NOT WRITTEN", stating how far below the mutation threshold
the evidence is (rep_weeks_in_window vs 4).

**ROUTINE_MODE=live → FIRST SUNDAY of the month only.** TZ=America/Toronto
date +%u must print 7 AND date +%d must print 01..07; otherwise stop and report
exactly "not first Sunday — skipped" (the runner reads that line as a clean
skip, ~30 s, no reads). On the first Sunday execute Stage 5 per the runbook.
Commissioned phase-change runs are not launched through this path.

## Environment / Transport

This prompt runs inside the data-platform runner's container: scripts/mcp.sh
reaches the MCP HTTP route on the in-cluster context-api over plain HTTP at
$MCP_BASE_URL (from /tmp/mcp.env). There is no connector transport and no
repo-less fallback on this path — the runner clones the repo before you start,
and a missing checkout or an unreachable endpoint is a hard stop with a compact
diagnostic. Never substitute test-write tools.

## Repository preflight
Before smoke test or pipeline work, make this checkout current with GitHub main:
  git fetch origin main
  CURRENT_HEAD="$(git rev-parse HEAD)"
  REMOTE_HEAD="$(git rev-parse origin/main)"
  if [ "$CURRENT_HEAD" != "$REMOTE_HEAD" ]; then
    git merge --ff-only origin/main
  fi
  git rev-parse HEAD
Required minimum fixed HEAD (lifeOS retarget banner + program rules; contains
the older compose-fix/replay-guard/fold-precheck guards):
  44d6d780a962f6a9b692d84431e27f159ddc7568
Verify final HEAD contains the required minimum:
  REQUIRED_HEAD="44d6d780a962f6a9b692d84431e27f159ddc7568"
  if ! git merge-base --is-ancestor "$REQUIRED_HEAD" HEAD; then
    echo "FATAL: HEAD is older than the lifeOS learner production guard."
    exit 2
  fi
If final HEAD is older than the required minimum, stop and emit a compact
diagnostic; do not run the learner on an older commit. Routines may fetch and
fast-forward only — never git add/commit/push or create branches. A dirty tree
that blocks the ff-merge is itself a stop condition; investigate, do not stash.

## Task
Read learning-agent.md in this workspace and execute the learner flow as a
production run at MONTHLY cadence.
This routine may update the real user profile, write real learner memories,
and persist production learner rows, but only after the fold precheck, all
guards, profile preview, and evidence audit pass.
It is not a morning briefing and must not call Google Calendar tools.
Stages:
  Stage -1    repo freshness + learner MCP smoke test
  Stage 0     anchor dates and pipeline_id
  Stage 0.5   FOLD PRECHECK against lifeOS evidence (run first; cheap short-circuit)
  Stage 1     load profile, lifeOS evidence (program reviews, rep weeks/days,
              interventions, health correlates), prior learner runs, learning memories
  Stage 1.2   python3 scripts/learner_evidence.py -> /tmp/evidence.json
              (deterministic packet; the ONLY evidence Stage 3 reads)
  Stage 1.5   freshness / duplicate / folded-evidence guard
  Stage 2     consolidate /tmp/ctx.json
  Stage 3     synthesis -> /tmp/diff.json
  Stage 4     mandatory evidence audit
  Stage 5     production writes only if allowed:
              memory verification, profile preview, memory writes,
              update_profile, write_llm_run, write_agent_run,
              + the learner_digest iOS card row (shape in learning-agent.md
              §5g; would-write in diagnostic)

## MCP smoke test
Run:
  scripts/mcp.sh list_tools '{}' /tmp/tools.json
Required tools:
  query_raw_sql
  recall_memory
  save_memory
  update_memory
  expire_memory
  update_profile
  write_llm_run
  write_agent_run
  get_active_program
  get_skill_summary
  get_direction
The list_tools response may return tools as a string array. Check required tool
presence against `.tools[]` directly. Do not rely only on `.tools[].name`.
If any required tool is missing, stop. Do not use test-write tools as a
production fallback.

## Stage 0.5 Fold Precheck (do this before loading heavy inputs)
At monthly cadence the newest lifeOS evidence is usually NOT yet folded, but
that is decidable with ONE query before pulling any large payload:
  scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT GREATEST(COALESCE((SELECT max(computed_at) FROM rep_weeks), 'epoch'::timestamptz), COALESCE((SELECT max(created_at) FROM program_versions WHERE status IN ('active','superseded')), 'epoch'::timestamptz)) AS newest_evidence, (SELECT count(*) FROM rep_weeks WHERE week_start >= CURRENT_DATE - 90) AS rep_weeks_in_window, (SELECT max(created_at) FROM agent_runs WHERE COALESCE(run_scope,'production')='production' AND (goal ILIKE '%learner%' OR goal ILIKE '%behavioral profile%')) AS last_learner, (SELECT max(created_at) FROM user_profile) AS profile_ts\"}" /tmp/foldcheck.json
Decision:
- If newest_evidence is older than BOTH last_learner and profile_ts, the
  evidence is already folded — take the no-mutation path.
- If rep_weeks_in_window < 4, the lifeOS evidence is too sparse for durable
  trait mutation (bootstrap months) — take the no-mutation path as well; do
  NOT abort. New interpretations go under hypotheses_for_next_run.
On the no-mutation path:
- run a COMPACT Stage 1 only (profile version + change_summary, rep_weeks
  dates/green flags, latest program review id, newest rollup headline values
  for hypotheses); do NOT fetch full profile.sections;
- confirm in Stage 1.5; skip Stage 2/3 synthesis and the Stage 5 compose preview;
- persist only the Stage 5f/5g no-mutation audit rows.
Otherwise run the full flow below.

## Output discipline
1. No general repo audit.
2. Do not print source files, script bodies, api-catalog excerpts, /tmp/ctx.json,
   full /tmp/diff.json, full user_profile.sections, full program/rollup payloads,
   full final_response, or full new_sections.json.
3. Redirect all MCP/helper output to /tmp/*.json.
4. Print only compact status lines: stage, status, counts, row IDs, errors.
5. Stage 3 may read only /tmp/ctx.json.
6. Stage 4 audit may read /tmp/diff.json and issue targeted SQL.
7. Batch independent calls in parallel where the runbook says to.
8. Budget target: reach Stage 3 with at least 75% of turn budget remaining
   (no-mutation runs short-circuit at Stage 0.5 and never reach Stage 3).

## Model Notes — Opus 4.8

The learner mutates the durable profile — subtractive honesty outranks insight
generation. Concretely:

1. The Stage 4 audit is subtractive, not decorative: a claim that fails its
   audit query is DELETED from the diff — not kept with a hedge, not
   "directionally true", not moved to prose. If >50% of claims drop, abort
   (the runbook rule) and say the synthesis over-reached.
2. Trait mutation requires a mechanism + >=2 independent sources across the
   window; anything less goes to hypotheses_for_next_run. A sparse month that
   produces only hypotheses is a SUCCESSFUL run, not a thin one — do not
   stretch evidence to justify a mutation because the cadence is monthly.
3. Never raise an existing trait's confidence without NEW evidence this
   window. Reinforcement without new evidence is a no-op — write it as such.
4. Identity-level synthesis is wanted (who the operator is, what substitutes
   for the goal) but every identity claim must trace to an audited number in
   the diff. No number, no claim.
5. Expired memories are retired beliefs: they never re-enter synthesis (the
   2026-06-12 resurrection bug is the cautionary tale).
6. Compactness is a hard budget: no payload pretty-prints; the diff and the
   compact narrative are the entire output surface.

## No Calendar
Do not call query_calendar.
Do not call Google Calendar tools.
Do not create, update, inspect, or summarize calendar events.

## Production Mutation Boundary
Production writes are allowed only after Stage 4 audit and Stage 5 profile
preview pass.
Allowed production write tools:
- save_memory
- update_memory
- expire_memory
- update_profile
- write_llm_run
- write_agent_run
Never call:
- forget_memory
- bulk_forget_memory
- write_test_llm_run
- write_test_agent_run
- write_program (the program review routine owns it; the learner never
  composes or modifies programs)
Never retry write tools. If a write tool returns an error, log one compact line
and continue only if the runbook says the remaining writes are safe. A write that
may have reached the server is never retried (duplicates result). A request the
tool rejected before executing (pre-insertion validation error) has written
nothing — fix the argument and issue it once; that is not a duplicate-causing
retry.

## Section Key Guard
Use the live profile section keys from `/tmp/ctx.json` as the source of truth.
Known live profile sections include:
- career
- communication_preferences
- confidence_and_caveats
- current_phase
- decision_psychology
- distraction_profile
- future_ai_instructions
- health_patterns
- identity_life_context
- interests_and_taste
- learning_style
- meta
- relationships_life_design
- systems_and_data
- work_patterns
Do not use `health_correlations` in `section_updates`; use `health_patterns`.
Do not invent new section keys unless they already exist in the current profile.

## Required validation focus
1. On a mutation run, Stage 5 profile preview must run scripts/learning_compose.py
   before any profile or memory write. On a no-mutation run there is no write to
   gate: skip compose and report "profile preview: N/A (folded/sparse)".
2. The old failure is not acceptable:
   learning_compose: section 'work_patterns' has no traits list
3. If compose succeeds, report compactly: profile preview: ok, sections=<count>.
4. If compose fails on a mutation run, abort before production profile or memory
   writes.
5. If the newest lifeOS evidence is already folded (or sparse per Stage 0.5),
   production mutation is not allowed: produce reinforcement-only output, skip
   the full profile fetch + compose, and do not call update_profile or memory
   write tools.
6. A clean production run should have recovered_errors none.

## Date Anchors
Compute once; because Bash sessions do not share env, persist to a file and
re-source in later sessions (or recompute):
  export TODAY_ET=$(TZ=America/Toronto date +%F)
  export RUN_START_ET=$(TZ=America/Toronto date +'%Y-%m-%dT%H:%M:%S%z')
  export PIPELINE_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
  export WINDOW_START_ET=$(TZ=America/Toronto date -d '90 days ago' +%F 2>/dev/null || TZ=America/Toronto date -v-90d +%F)
  printf 'TODAY_ET=%s\nRUN_START_ET=%s\nPIPELINE_ID=%s\nWINDOW_START_ET=%s\n' \
    "$TODAY_ET" "$RUN_START_ET" "$PIPELINE_ID" "$WINDOW_START_ET" > /tmp/anchors.env
RUN_START_ET must not contain spaces.

## Stage 1 / 1.2
Run the 13 reads and the packet exactly as learning-agent.md Stage 1 and
Stage 1.2 say (`source /tmp/mcp.env; source /tmp/anchors.env` first);
/tmp/evidence.json is the only evidence Stage 3 reads. Inputs listed in
coverage.missing_inputs are degraded sections, never a reason to abort.

## Stage 1.5 Replay / Folded-Evidence Guard
Determine whether the newest lifeOS evidence (newest rep_weeks rollup /
program review) is already folded into the current profile or a later
production learner run (Stage 0.5 usually answers this; confirm against the
prior learner narrative or profile source references).
If folded or sparse, the run must be reinforcement-only for production:
- do not add new profile traits
- do not create/update/expire memories
- do not call update_profile
- do not fetch full profile.sections and do not run the compose preview
- keep any newly noticed interpretation under hypotheses_for_next_run or
  candidate_insights, marked not eligible for mutation until newer lifeOS
  evidence confirms them
It is still correct to write a compact production agent_runs narrative and
llm_runs diff as the visible "no mutation / reinforcement-only" audit trail.

## Stage 4 Evidence Audit
Stage 4 is mandatory on mutation runs.
For each audit_plan entry, run the specified SELECT query with query_raw_sql.
Compare measured result to the claim:
- numeric claims must match within the audit_plan tolerance, normally +/- 5%
- categorical claims must match exactly
- missing data means the claim is dropped
SQL notes (learned from live audits):
- rep_days/rep_weeks/program_versions/proactive_interventions live in llm_db;
  rep floor truth is rep_days.floor_met (computed by the nightly verifier),
  not recomputed RescueTime sums — audit against the ledger.
- RescueTime focus% = SUM(seconds where productivity >= 1) / SUM(all seconds).
  productivity >= 2 is "very productive" only and understates focus; name the
  exact threshold in the audit_plan formula.
- RescueTime ts_utc/bucket_start_utc are ET-stored-as-UTC; cast ::timestamp
  before comparing to ET values; source_day is safe for date filters.
- Postgres has no ROUND(double precision, int): cast, e.g. ROUND(x::numeric, 2).
Write /tmp/audit_results.json with passed and dropped claim IDs.
Then remove failed claims from /tmp/diff.json before Stage 5.
If Stage 4 drops more than 50% of claims, abort before production writes.

## Stage 5 Production Writes
If Stage 0.5 / Stage 1.5 marked the evidence as folded or sparse, skip 5a-5e and
execute only 5f and 5g (set new_version = current profile version; label the
narrative NO MUTATION). Otherwise:
5a. Verify proposed memory operations with recall_memory.
5b. If a proposed memory create key already exists from recall_memory with
    source="learning_agent", update that exact existing memory with update_memory
    only if the audited diff genuinely strengthens an active trait.
5c. If a proposed memory expire key exists from recall_memory with
    source="learning_agent", expire it with expire_memory only if the audited
    diff supports expiry.
5d. Compose profile preview by running scripts/learning_compose.py.
5e. If compose preview passes, call update_profile with the composed sections.
5f. Persist /tmp/diff.json with write_llm_run (step_label "stage3_diff", or
    "stage3_diff_folded_no_mutation" on a no-mutation run).
5g. Persist compact learner narrative with write_agent_run using goal
    "Monthly behavioral profile analysis (lifeOS v<N>)".
Never retry write tools.
The agent narrative/tool classification should include:
- run_origin="claude_monthly_learner_production"
- execution_mode="scheduled_claude"
- agent_kind="deep_learner"
- visibility="user_visible"
- run_scope="production"

## Definition of done
Final summary must include:
- mode: DIAGNOSTIC (not written; test phase), live (first Sunday), or live COMMISSIONED
- pipeline_id
- git HEAD used and whether it contains 44d6d78
- TODAY_ET and WINDOW_START_ET
- newest lifeOS evidence timestamp used + rep_weeks_in_window count
- fold precheck result (folded / sparse / mutation-eligible)
- current profile version before run
- profile preview status: ok / failed / N/A (folded/sparse)
- profile update executed: new version id/version, or "none"
- memory writes executed: created/updated/expired keys, or "none"
- llm_runs row id from write_llm_run
- agent_runs row id from write_agent_run
- audit passed/dropped counts
- fatal_errors and recovered_errors
- whether Stage 5 completed
If Stage 5 does not complete and no guard intentionally aborted before writes,
the run is a FAILURE.
Begin now.

## Signoff

v6 · 2026-09-23 ET · UI: NEEDS RE-PASTE (every-Sunday cron + first-Sunday gate; packet step; /tmp/mcp.env; runbook canonical)
(v5 07-03 learner_digest · v4 07-03 de-scaffold · v3 07-02 · v2 07-02 model notes · v1 06-12 —
details in git history.)

## Signoff

v6-api · 2026-10-19 ET · API runner edition of the v6 paste body: credentials from the
runner's /tmp/mcp.env, mode from ROUTINE_MODE (dry_run = DIAGNOSTIC, live = first-Sunday
gate). Body text otherwise identical to v6.
