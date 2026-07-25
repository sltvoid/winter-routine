# Program Review — Sunday lifeOS week composer

The weekly content producer for the lifeOS program layer (data-platform spec
`docs/specs/2026-06-11-lifeos-surfaces-spec.md` §3). Runs **Sunday ~21:15 ET** —
after the verifier's 20:35 Sunday rollup, so the kill-gate reads the week
just ended, not last week's. (The 10:07 goal-policy review ran that
morning.) Composes next week's rotation from evidence and writes it through
`write_program`; Monday's 7 AM briefing serves the result. **Never run this routine before Sunday:** an
early active write supersedes the current week's program and pushes the
remaining days onto stale-carryover serving.

**Authority model — read before editing this runbook:** weekly content never
arms anything. The platform clamps every write server-side: content-only rows
auto-activate; ANY frame delta (anchor hours, floor minutes, green-week bar,
families) is reverted to the ratified frame and the row is demoted to a
confirm-gated draft. This routine therefore never attempts frame changes —
if the evidence argues for one (e.g. a ratchet after 3 consecutive green
weeks), it says so in the review notes for the operator instead.

## Stage 0 — Reads (parallel, via `scripts/mcp.sh` or native tools)

```bash
scripts/mcp.sh get_active_program '{}' /tmp/active_program.json &
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT week_start, floors_met, bar, green, rollup FROM rep_weeks ORDER BY week_start DESC LIMIT 8"}' /tmp/rep_weeks.json &
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT day, family, rep_title, floor_met, floor_minutes, artifact FROM rep_days WHERE day >= CURRENT_DATE - 14 ORDER BY day"}' /tmp/rep_days.json &
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT key, content, created_at FROM agent_memory WHERE category IN ('"'"'goal'"'"','"'"'preference'"'"') AND (expires_at IS NULL OR expires_at > NOW()) ORDER BY created_at DESC LIMIT 20"}' /tmp/goal_memory.json &
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT id, status, valid_from, valid_until, enforcement FROM goal_policy_versions WHERE status = '"'"'active'"'"' ORDER BY created_at DESC LIMIT 1"}' /tmp/goal_policy.json &
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT check_id, status, count(*) AS days FROM operator_steward_checks WHERE created_at > NOW() - INTERVAL '"'"'7 days'"'"' AND status NOT IN ('"'"'closed'"'"','"'"'no_op_valid'"'"') GROUP BY 1,2 ORDER BY 3 DESC"}' /tmp/gov_stewards.json &
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT status, left(evidence_summary,200) AS evidence FROM operator_steward_checks WHERE check_id='"'"'llm_budget'"'"' ORDER BY created_at DESC LIMIT 1"}' /tmp/gov_budget.json &
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT snapshot_status, count(*) FROM source_freshness_agent_runs WHERE generated_at > NOW() - INTERVAL '"'"'7 days'"'"' GROUP BY 1"}' /tmp/gov_freshness.json &
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT slug, status, created_at::date AS day FROM delegation_tickets WHERE status IN ('"'"'proposed'"'"','"'"'accepted'"'"') OR created_at > NOW() - INTERVAL '"'"'7 days'"'"' ORDER BY created_at DESC LIMIT 10"}' /tmp/gov_tickets.json &
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT status, count(*) FROM agent_runs WHERE created_at > NOW() - INTERVAL '"'"'7 days'"'"' AND status NOT IN ('"'"'completed'"'"','"'"'skipped'"'"') GROUP BY 1"}' /tmp/gov_agent_health.json &
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT final_outcome, outcome_data->'"'"'episode'"'"'->>'"'"'peak_action'"'"' AS action, outcome_data->'"'"'delivery'"'"'->>'"'"'tag'"'"' AS delivery, count(*) AS n, round(avg((outcome_data->>'"'"'distraction_delta'"'"')::numeric),1) AS avg_delta, round(avg((outcome_data->>'"'"'time_to_comply_min'"'"')::numeric),0) AS avg_ttc FROM proactive_interventions WHERE final_outcome IS NOT NULL AND final_outcome NOT IN ('"'"'grouped'"'"') AND issued_at > NOW() - INTERVAL '"'"'7 days'"'"' GROUP BY 1,2,3 ORDER BY 4 DESC"}' /tmp/gov_efficacy.json &
wait
```

The six `/tmp/gov_*.json` reads feed Stage 2.5 (platform governance) and
Stage 2.6 (steering efficacy). They are counts/summaries only — do not
deep-read individual run payloads.

Add one more read to the same parallel batch — the operator's north-star
direction (live since platform v110; skip gracefully with one status line if
the tool is absent):

```bash
scripts/mcp.sh get_direction '{}' /tmp/direction.json &
```

## Stage 0.9 — Direction re-read (mandatory when /tmp/direction.json has an active row)

The active direction is the destination layer above the program (platform
spec docs/specs/2026-07-02-north-star-direction-spec.md). Rules:

1. Composition serves the direction's `skill.current_phase`. In the current
   habit-building phase that means: floors and consistency FIRST; do not
   ratchet difficulty until the phase says so — and a slipped week is framed
   in the review notes as *leverage postponed* (the direction's why), never
   abstract discipline.
2. If the week's evidence argues the CURRENT PHASE itself is wrong (e.g. the
   kill-gate fires, or floors have been missed for weeks), say so in the
   review notes as a **direction recommendation for the operator** — a phase
   change lands as a direction draft the operator approves; this routine
   never writes direction.
3. If `domains_past_review` is non-empty, add one review-notes line naming
   the overdue domains (the operator bumps them by approving an updated
   draft).
4. Cite the direction version id in the review notes when it shaped a
   composition choice.

Operator remarks land as goal/preference `agent_memory` rows — anything the
operator said during the week ("more Rust", "ease off") is input here; record
each consumed remark's key in `generated_from` (the goal-policy v57 pattern).

## Diagnostic mode (any day, no writes)

When the routine prompt's REVIEW_MODE is "diagnostic" (the test phase), on
any non-Sunday run, or whenever DIAGNOSTIC=1: execute every stage below but
SKIP Stage 3 entirely — no write_program call, no write_agent_run. Instead,
print the would-write program JSON compactly (one line per rotation day) and
the would-write review notes in the final summary, labeled DIAGNOSTIC — NOT
WRITTEN. Diagnostic sessions export ROUTINE_MODE=dry_run ALLOW_WRITES=0,
which scripts/mcp.sh enforces mechanically: write tools are refused at the
wrapper, so a diagnostic run cannot write even by mistake.

## Stage 1 — Kill-condition gate (deterministic, before any composition)

Read `rep_weeks[0].rollup` (the verifier's Sunday rollup; data-platform
computes these VM-side whether or not this routine runs):

- `consecutive_non_green >= 4` → check the **recalibration release valve**
  first: if a `program_versions` row exists with
  `source = 'operator_recalibration'` (or non-null `operator_input`) created
  AFTER the newest `rep_weeks` row's `computed_at`, the goal-level
  conversation already happened and the operator recalibrated — **PROCEED**,
  composing against the recalibrated active frame, and open the review notes
  with one line of gate history ("kill-gate lifted by operator recalibration
  <date>"). Otherwise → **STOP composing.** Write no program. Surface a
  goal-level rethink request to the operator (the spec's response is a
  conversation, not "build more system"). The valve exists because the gate
  is a request FOR a conversation — once the conversation is on record,
  re-firing every week until a green week posts would punish the exact
  response the gate asked for (added 2026-07-09 after the first live gate
  firing).
- `auto_weeks_no_operator_input >= 8` AND `green_rate_trend.declining` →
  **STOP composing**, ask for a frame conversation.
- Otherwise proceed. Note `email/warn/lock` demotion counts in the review
  notes when nonzero — rung demotions themselves are platform-side.

## Stage 1.6 — Job-stretch gate (active during job season)

While the operator-context memory records job season (2026-07-22; quiet-mode
operating model, data-platform `docs/reference/quiet-mode.md` §7): the
sequencing decision-of-record is **job-first — the stretching version of the
job IS the reskill**. The day job runs on an untracked employer device, so
this gate is one question, self-reported, no tooling:

> "What was the week's hardest job artifact?" (one line)

Record the answer (or its absence) in the review notes. **Three to four
consecutive weeks without a real answer** = the job's learning curve has
flattened = recommend flipping the deliberate reskill to the main event —
as a direction-phase recommendation for the operator (Stage 0.9 machinery),
never as an enforcement change. A missing answer in a single week is noise;
do not nag about it mid-week — this question exists only here.

## Stage 2 — Compose next week's rotation

Frame facts: READ them from the active program row on every run — anchor
hours, floor minutes, green-week bar, families, and the rotation's day shape
(which days carry reps, where the milestone sits) are program DATA, never
constants of this runbook. Never modify the frame; recommend frame changes in
the notes instead. (Historical trap: this paragraph once hardcoded "floors
30, green 4 of 6, Saturday 90–120 min" and went stale the day the operator
recalibrated to 15-min floors / bar 2 on 2026-07-09.)

Composition rules:
1. Every slot Mon–Sat gets a pre-decided rep with `family`, `title`, and
   `success` (one observable artifact or completion condition). No slot may
   require a decision at execution time.
2. Drills follow the active program's own progression (e.g. rustlings sets
   when the dojo rotation is active): continue from the last COMPLETED
   evidence per `rep_days`/dojo commits; don't restart, don't import a
   progression the active rotation doesn't carry.
3. When the active rotation pairs a scoping comms rep with a weekend
   milestone, the comms rep scopes the milestone (design doc = the scoping);
   when it doesn't (e.g. the 2026-07-10 recalibrated shape), skip this rule.
4. Pull Saturday milestones from the program's `milestone_queue`; replenish
   the queue when it runs low (2+ scoped milestones ahead).
5. Respond to evidence: floors missed on a family → lighter or
   friction-removed reps there next week, not heavier; momentum on milestones
   → bigger scoped milestone, same block.
5b. Friday is the week's LIGHTEST slot (slack/repair by frame philosophy):
   never place a progression peak there — repeat or lightly extend earlier
   material. Drill progression advances on COMPLETION EVIDENCE (rep_days
   artifacts/dojo commits), not by calendar position; without evidence,
   later-week drills repeat or consolidate rather than advance.
6. Honor operator remarks above all defaults.

## Stage 2.5 — Platform governance (weekly; absorbs the retired Gemini daily reviews)

Since 2026-07-02 the platform's three Gemini Flash-Lite daily review agents
(`data_quality_review`, `llm_contract_review`, `llm_agent_evaluation`) are
retired from the metered API — reflection belongs on the subscription runner
(this routine), detection stays deterministic (stewards + Prometheus pagers,
which page same-day without any LLM). This stage is their weekly replacement:
**interpretation of the week's governance evidence, not re-detection.**

From the `/tmp/gov_*.json` reads, compose a `Platform governance:` section
(2–6 lines) appended to the Stage 3 review-notes narrative:

1. Non-green steward check-ids with day counts (`gov_stewards`) — note which
   are known transients (e.g. a classification aging out of its snapshot
   window) vs. new this week.
2. The LLM budget line, quoted from the `llm_budget` steward evidence
   (`gov_budget`) — it already carries spend, pace, and top workloads.
3. Freshness week shape (`gov_freshness`): "all green" or "N unknown/red —
   <one-clause cause if evident from steward overlap>".
4. Tickets needing the operator (`gov_tickets`): proposed/accepted by slug, or
   "none open". Never create, close, or edit tickets — recommendations only.
5. Failed / `budget_blocked` agent runs (`gov_agent_health`) when nonzero.

Rules: if everything is clean, the section is exactly ONE line — "Platform
governance: clean week (stewards green, budget <spend line>, freshness green,
no open tickets)." Never pad a clean week into paragraphs. Never propose
config or code changes as fact — flag for the operator. If the Stage 1
kill-gate stops composition, still include this section in the stop-narrative
(governance interpretation is independent of program composition).

## Stage 2.6 — Steering efficacy (weekly; reads the v116 outcome ledger)

Since platform v116 (2026-07-09) every closed WARN/LOCK steering **episode**
(a burst of fires ≤35 min apart = one behavioral incident) is
deterministically classified into `proactive_interventions.final_outcome`:
`reduced` / `held` / `backfired` / `insufficient_data` (episode members carry
`grouped`; the anchor's `outcome_data` holds before/after distraction, the
delivery tag, and `time_to_comply_min`). This stage is **interpretation of
already-measured numbers, never re-measurement** — same philosophy as 2.5.

From `/tmp/gov_efficacy.json` compose a `Steering efficacy:` line (1–3 lines)
appended to the review narrative directly after the governance section:

1. The week's episode count and outcome split, locks vs warns.
2. The delivery story when it dominates: `undelivered` episodes mean the
   ask never reached a device — check the benign cause FIRST (the PC simply
   not in use that week, e.g. all-Mac weeks; cross-check the day device
   splits) before framing it as a listener outage; either way it is a
   delivery story, not a behavioral failure.
3. Typical time-to-comply when the sample is meaningful.
4. **At most ONE** concrete tuning recommendation, advisory text only (e.g.
   "the low-artifact streak of 6 never fired; 4 would have caught Tue/Thu") —
   never edit ConfigMaps, never present as fact; skip the recommendation
   entirely on thin weeks. Operator decides. When you DO recommend, ship it
   **paste-ready**: name the exact file + key + value (e.g. "in
   `k8s/proactive-activity-rules-configmap.yaml` set
   `low_artifact_lock_streak: 4`, then kubectl apply") — a recommendation
   that requires composing an edit dies in the inbox; one that takes ten
   seconds survives (grill decision 2026-07-09).

When the week has no classified episodes (or all `insufficient_data`), the
line is exactly one: `Steering efficacy: insufficient tracked activity this
week (no actuated interventions landed in tracked windows).` Graceful skip
pre-v116 or on read error: one status line and move on.

## Stage 2.7 — Insight leads (weekly; reads the in-VM insight sweep)

Since platform v129 (2026-07-18, ADR 0011) an in-VM Gemini **insight sweep**
runs Sunday 05:37 ET: a bounded read-only agent that compares the subject
week to the baseline week across focus/health/finance/music/location/
interventions and emits **≤5 evidence-cited insights** (an empty list is a
successful sweep) into `llm_runs` with `run_type='insight_sweep'`.

Read the latest run (via `list_agent_outputs` filtered to `insight_sweep`,
then `get_run_detail`, or `query_raw_sql` on llm_runs). Then, for EACH
insight:

1. Treat it as a **lead, not a finding**: confirm or dismiss it against this
   review's own evidence (day splits, rep ledger, health reads). Gemini has
   no deploy history and no goal context — e.g. an "interventions dropped"
   lead may simply be a platform change working as designed; you have the
   change timeline, it does not.
2. Confirmed leads inform Stage 2's rotation choices and may seed the ONE
   Stage 2.6-style advisory recommendation — never a second one.
3. The review narrative carries one `Insight leads:` line per insight:
   confirmed/dismissed + a clause of reasoning. Dismissals are valuable —
   say why (noise, known cause, already-handled).

Graceful skip (exactly one line) when: no sweep row exists this week, the
sweep's insights are empty, or the read errors. Never re-run or simulate
the sweep from this routine — its absence is the platform's own
automation-proof target's problem, not yours.

## Stage 3 — Write

```bash
scripts/mcp.sh write_program "$(cat /tmp/next_program.json)" /tmp/write_result.json
```

Payload shape: `{"program": {"valid_from": "<next Mon>", "valid_until":
"<next Sun>", "frame": <copy of active frame verbatim>, "rotation": {mon..sun},
"milestone_queue": [...], "generated_from": {"evidence": [rep_weeks ids,
memory keys, remark keys]}, "source": "claude_program_review"}}`.

The response shape is `{"status": "active"|"draft", "id": "<uuid>",
"frame_delta": bool}`. Expect `"status":"active"`. A `"status":"draft"`
response means a frame delta was detected and clamped — report it; do not
retry with tweaks (the frame is operator-only). There is no `"ok"` status.

After the review-notes `write_agent_run`, write the iOS digest row (spec
2026-07-03-ios-digest — `GET /api/winter/digest` serves it as cards; restate
facts already in the notes, no new analysis):

```bash
scripts/mcp.sh write_llm_run "$(jq -nc \
  --arg out "$(jq -nc \
    --arg wv "<week_verdict, <=120 chars>" \
    --arg nf "<next_week_focus, <=120>" \
    --arg st "<sunday_target, <=160, names the ledger it is checked against>" \
    --arg gl "<governance one-liner, <=160>" \
    --argjson flags "$(jq -nc '["<operator flag 1, <=160>", "<flag 2 or omit>"]')" \
    '{week_verdict:$wv,next_week_focus:$nf,sunday_target:$st,governance_line:$gl,operator_flags:$flags}')" \
  '{run_type:"weekly_digest",model:"routine-selected",output_response:$out,step_label:"stage3_ios_digest"}')" /tmp/weekly_digest_write.json
```

Rules: ≤2 `operator_flags`; every value restated from the review notes
verbatim-or-tighter; in DIAGNOSTIC mode print the would-write digest JSON
(one line per field) instead of calling the write tool.

## Definition of done

- One `program_versions` row written (active, or draft+reported).
- Review notes (3–6 lines: what changed and why, evidence cited) written via
  `write_agent_run` with `agent_kind='program_review'`, **plus the Stage 2.5
  `Platform governance:` section** (one line when clean) **and the Stage 2.6
  `Steering efficacy:` line**.
- One `weekly_digest` llm_runs row (the iOS card feed source) — or its
  would-write JSON in diagnostic mode.
- No frame fields modified; no enforcement opinions expressed as config.
- No tickets created/edited; governance items are recommendations only.

## Signoff

2026-07-03 ET · operator session — Stage 3 gains the `weekly_digest` iOS
card write (spec 2026-07-03-ios-digest); DoD updated. (History in git.)
