# Claude Routine — Weekly Program Review / lifeOS Week Composer (PRODUCTION)

> **API runner edition · v9-api · 2026-10-19 ET.** The committed, key-free prompt the
> data-platform `winter-routine-program-review` CronJob (Sunday 21:15 ET) feeds to
> headless Claude Code; the runner pre-writes /tmp/mcp.env. Mirrors the Routine UI
> paste body `claude-routine-program-review.v9.md`; runbook of record: program-review.md.

---

## Run Mode

The mode is decided by the runner, never by this prompt: `source /tmp/mcp.env`
and read `ROUTINE_MODE`.

**ROUTINE_MODE=dry_run → DIAGNOSTIC.** Export DIAGNOSTIC=1. Runs on ANY day,
any time. ALLOW_WRITES is 0 and scripts/mcp.sh mechanically REFUSES all write
tools in this state, so a write cannot happen even by mistake. Execute every
stage in full (preflight, smoke, reads, kill-gate, composition, payload build)
but skip Stage 3's writes; instead print the would-write program compactly
(one line per rotation day), the would-write review notes and the would-write
weekly_digest JSON in the final summary, labeled exactly
"DIAGNOSTIC — NOT WRITTEN" (the runner passes the run on that label).

**ROUTINE_MODE=live → Sunday only.** TZ=America/Toronto date +%u must print 7;
otherwise stop and report exactly "not Sunday — skipped" (an early active write
supersedes the current week's program and pushes the remaining days onto
stale-carryover serving; the runner reads that line as a clean skip). On a
Sunday execute Stage 3 writes.

There is no repo-less fallback on this path: the runner clones the repo before
you start, and a missing checkout is a hard stop in either mode.

## Authority Model (read first)

Weekly content never arms anything. The platform clamps every write
server-side: content-only rows auto-activate; ANY frame delta (anchor hours,
floor minutes, green-week bar, families) is reverted to the ratified frame
and the row is demoted to a confirm-gated draft. Therefore:
- Never attempt frame changes. If evidence argues for one (e.g. a ratchet
  after 3 consecutive green weeks), SAY SO in the review notes for the
  operator instead of writing it.
- A "status":"draft" response from write_program means a frame delta was
  detected and clamped — report it compactly; do not retry with tweaks.

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

## Git Boundary

You may run: git fetch origin main; git merge --ff-only origin/main.
You must not run: git add / commit / push / branch / checkout -b.
If the fast-forward merge fails, stop and emit a compact diagnostic summary.

Required minimum HEAD (program-review runbook + write_program docs):

  REQUIRED_HEAD="44d6d780a962f6a9b692d84431e27f159ddc7568"
  if ! git merge-base --is-ancestor "$REQUIRED_HEAD" HEAD; then
    echo "FATAL: HEAD is older than the program-review guard."
    exit 2
  fi

## MCP Smoke Test

Run:

  scripts/mcp.sh list_tools '{}' /tmp/tools.json

Required tools:

  query_raw_sql
  get_active_program
  write_program
  write_agent_run
  recall_memory

The list_tools response may return tools as a string array; check presence
against .tools[] directly. If any required tool is missing, stop.

## Task

Read program-review.md in this workspace and execute it as a production run.
This routine writes exactly one program_versions row (active or
clamped-draft) plus one agent_runs review-notes narrative. It is not a
morning briefing: no calendar tools, no memory writes, no llm_runs rows.

Stages:

  Stage -1   repo preflight + smoke test
  Stage 0    parallel reads (active program, rep_weeks, rep_days 14d,
             goal/preference memories incl. operator remarks, active goal
             policy, + the seven /tmp/gov_*.json governance/efficacy reads
             + the operator's job_artifact_<week_start> memory rows)
  Stage 0.5  rollup freshness line (WARN if rep_weeks[0].computed_at > 24 h old)
  Stage 0.9  direction re-read (get_direction; serve the skill phase —
             rules in program-review.md; graceful one-line skip pre-v110)
  Stage 1    KILL-CONDITION GATE (deterministic, before any composition)
  Stage 1.6  job-stretch gate — reads the operator's job_artifact_<week_start>
             memory row (rules in program-review.md)
  Stage 2    compose next week's rotation
  Stage 2.5  platform-governance section (weekly interpretation — absorbs the
             retired Gemini daily reviews; rules in program-review.md)
  Stage 2.6  steering-efficacy line (interprets the v116 episode outcomes in
             proactive_interventions; ≤1 advisory tuning recommendation;
             rules in program-review.md; graceful one-line skip pre-v116)
  Stage 2.7  insight leads (reads the latest weekly insight_sweep run — the
             in-VM Gemini lead generator, ADR 0011; treat each insight as a
             lead to CONFIRM or DISMISS against this review's own evidence,
             cite the ones used; rules in program-review.md; graceful
             one-line skip when no sweep ran or insights are empty)
  Stage 3    write_program + review-notes narrative (carries the governance
             section + the efficacy line + used insight leads; one line each
             when clean) + the weekly_digest iOS card row
             (shape + command in program-review.md; would-write in diagnostic)

## Stage 1 Kill-Condition Gate (mandatory, before composing)

Read the newest rep_weeks row's rollup (the verifier computes these VM-side
whether or not this routine runs):

- consecutive_non_green >= 4  -> FIRST check the recalibration release
  valve: a program_versions row with source='operator_recalibration' (or
  non-null operator_input) created AFTER the newest rep_weeks row's
  computed_at means the goal-level conversation already happened -> PROCEED
  against the recalibrated frame, noting the gate history in one line.
  Otherwise STOP composing. Write no program. Write a review-notes narrative
  requesting a goal-level rethink with the operator (the platform spec's
  response is a conversation, not more system).
- auto_weeks_no_operator_input >= 8 AND green_rate_trend.declining -> STOP
  composing; write a narrative asking for a frame conversation.
- Fewer than 1 rep_weeks row (bootstrap weeks): proceed — compose from the
  active program's rotation and rep_days evidence alone.
- Otherwise proceed. When email/warn/lock demotion counts in the rollup are
  nonzero, mention them in the review notes (demotions themselves are
  platform-side).

## Stage 2 Composition Rules

Frame facts: READ them from the active program row every run — anchor
hours, floor minutes, green-week bar, families, and the rotation's day
shape are program DATA, not constants of this prompt (the old hardcoded
"floors 30 / green 4 of 6" went stale at the 2026-07-09 recalibration to
15-min floors / bar 2). Never modify the frame; recommend changes in notes.

1. Every slot Mon–Sat gets a pre-decided rep with family, title, and success
   (one observable artifact or completion condition). No slot may require a
   decision at execution time.
2. Drills follow the current progression (rustlings: continue from the last
   completed set per rep_days/dojo evidence; never restart from set 1).
3. Thursday's comms rep scopes Saturday's milestone (the design doc IS the
   scoping — the weekend block must start decision-free).
4. Pull Saturday milestones from the program's milestone_queue; replenish the
   queue in the new row so it always holds 2+ scoped milestones ahead.
5. Respond to evidence: floors missed on a family -> lighter or
   friction-removed reps there next week, never heavier; real momentum on
   milestones -> bigger scoped milestone, same block size.
5b. Friday is the week's LIGHTEST slot (slack/repair by frame philosophy):
   never place a progression peak there — repeat or lightly extend earlier
   material. Drill progression advances on COMPLETION EVIDENCE (rep_days
   artifacts/dojo commits), not by calendar position; without evidence,
   later-week drills repeat or consolidate rather than advance.
6. Operator remarks (goal/preference agent_memory rows written during the
   week) outrank all defaults. Record each consumed remark's key in
   generated_from.

## Model Notes — Opus 4.8

Composition discipline and honest notes matter more than eloquence. Concretely:

1. Review-notes analysis bar: the central finding is framed at IDENTITY level
   (what pattern the week reveals, what substituted for the goal), built as ONE
   cross-source mechanism (rep_days x steering interventions x health), and
   closes with >=1 numeric next-week target derived from a metric you just
   computed (e.g. "hands-on >=30 min on 3 of 5 anchor days") — checkable
   against the same ledger next Sunday. Recommend through real platform levers
   (rep anchor, milestone queue, goal-policy, floor sizing), never generic
   productivity advice.
2. Missed floors NEVER earn a heavier week. The instinct to motivate with
   ambition is the failure mode here: evidence of struggle -> lighter or
   friction-removed reps, same family. Momentum -> bigger milestone, same
   block size.
3. Platform governance section: ONE line when clean — do not narrate green
   checks or expand transients into paragraphs. Name known transients as
   transients (e.g. a classification aging out of its snapshot window).
4. The kill-gate result is binding (subject only to the Stage 1
   recalibration release valve). Composing "just a light week anyway"
   through a STOP is a failed run, not kindness.
5. A draft-clamp response is a report, not a puzzle: never retry write_program
   with tweaked frames.
6. Every factual claim in the notes must name its ledger (rep_days, rep_weeks,
   proactive_interventions, llm_budget steward line) so next week can check it.

## Stage 3 Write

Build /tmp/next_program.json:

  {"program": {
    "valid_from": "<next Monday>",
    "valid_until": "<next Sunday>",
    "frame": <copy of the active program's frame, verbatim>,
    "rotation": {"mon": {...}, ..., "sun": null},
    "milestone_queue": [...],
    "generated_from": {"evidence": [rep_weeks dates, rep_days summary,
                       consumed memory keys]},
    "source": "claude_program_review"
  }}

Then:

  scripts/mcp.sh write_program "@/tmp/next_program.json" /tmp/write_result.json

Expect {"status":"active"}. On {"status":"draft"} report the clamp and stop
(frame is operator-only). Never retry a write that may have reached the
server.

Finally write compact review notes (3–6 lines: what changed and why, evidence
cited, any ratchet/frame recommendation for the operator) via
write_agent_run with goal "Weekly program review for <next Monday> week" and
classification run_origin="claude_program_review_production",
agent_kind="program_review", execution_mode="scheduled_claude",
visibility="user_visible", run_scope="production".

## Output Discipline

1. No pretty-prints of full payloads; redirect MCP output to /tmp/*.json.
2. One compact status line per stage: stage, status, counts, row IDs.
3. Batch the Stage 0 reads in parallel.
4. Never print the literal MCP_API_KEY.
5. Never retry write tools.

## No Calendar / No Memory Writes

Do not call query_calendar or any Google Calendar tools.
Do not call save_memory, update_memory, expire_memory, forget_memory,
bulk_forget_memory, update_profile, write_llm_run, or any test-write tools.
recall_memory / query_raw_sql reads are allowed.

## Definition of Done

Final summary must include:

- git HEAD used and whether it contains the required guard commit
- mode: DIAGNOSTIC (not written; test phase) or live (Sunday)
- the would-write program, one line per rotation day, and the would-write review notes (diagnostic mode)
- kill-condition gate result (proceed / stopped, with the triggering values)
- newest rep_weeks week_start + floors_met/bar/green used as evidence
- operator remark keys consumed, or "none"
- program row id + status (active / draft-clamped), or "none (gate stopped)"
- next week's rotation summary (one line per day: family — title)
- milestone_queue depth after replenishment
- agent_runs review-notes row id
- the Platform governance line(s): non-green steward check-ids, the llm_budget
  spend line, freshness week shape, tickets needing the operator (or the
  single clean-week line)
- the Steering efficacy line (Stage 2.6), or its one-line skip
- the Insight leads outcome (Stage 2.7): each lead confirmed/dismissed with a
  clause of reasoning, or its one-line skip
- any frame recommendation surfaced to the operator
- the rollup-age line, the Job artifact line, the Shelved decisions line
- fatal_errors and recovered_errors

If no program row was written and the kill gate did not intentionally stop
the run, the run is a FAILURE. Begin now.

## Signoff

v9 · 2026-09-23 ET · UI: NEEDS RE-PASTE (21:15 ET slot; /tmp/mcp.env; Stage 0.5/1.6/2.8 lines)
(v8 07-18 Stage 2.7 insight leads · v6 07-03 · v5 07-03 de-scaffold · v4 07-02 Stage 0.9 direction · v3 07-02 · v2 07-02
governance · v1 06-12 — details in git history of program-review.md.)

## Signoff

v9-api · 2026-10-19 ET · API runner edition of the v9 paste body: credentials from the
runner's /tmp/mcp.env, mode from ROUTINE_MODE (dry_run = DIAGNOSTIC, live = Sunday
gate), repo-less fallback removed. Body text otherwise identical to v9.
