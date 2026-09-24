# Tech Spec — Routine Re-evaluation: Daily Briefing Trim, Weekly Review Retime, Monthly Learner Rebuild

- **Status:** Design approved + grilled in session (2026-09-23 ET); implementation plan next
- **Date:** 2026-09-23
- **Owner:** operator (Steven) · drafted by Claude (Fable 5.1, operator session)
- **Affected components:** `morning-briefing.md`,
  (plus data-platform `services/connectors/plaid-collector/` for Design D and
  `agent/live_activity.py` for §2.8) `scripts/extract.py`,
  `scripts/validate_payloads.py`, `scripts/calendar_plan.py`,
  `program-review.md`, `learning-agent.md`, new `scripts/learner_evidence.py`,
  the three gitignored paste bodies, three claude.ai routine triggers, and two
  data-platform docs (ADR 0012 note, `docs/reference/quiet-mode.md` row)
- **Out of scope (operator decision, this session):** the job-season vs
  settled-job frame question (briefing rule 16 / review Stage 1.6 stay as they
  are); MCP key rotation (standing do-not-rotate directive); a from-scratch
  rewrite of the morning runbook.

---

## 1. Findings (what the ledgers and run logs say)

Evidence gathered 2026-09-23 22:00 ET from `llm_db`, the routine run logs
(`RemoteTrigger list_runs` / `get_run_log`), and the repo at `c17484b`.

### 1.1 Daily morning briefing — healthy, stale in content

- Lands every morning since 2026-09-06 at ~06:38–06:48 ET (trigger
  `trig_01JvpEgzQnjQ1vntCTxkJoeS`, cron `35 10 * * *` UTC, model opus-5-5).
- The 2026-09-23 run (session `cse_015yRPzG4PAwRMmrfhYceq1e`) reported three
  defects it had to work around:
  1. `validate_payloads.py` passed a `hero.target.label` the server rejected —
     the server enforces `HERO_TARGET_LABEL_MAX_CHARS = 80`
     (data-platform `shared/hero_surface_contract.py`); the local validator
     has no label limit.
  2. The validator's rank-1 alignment rule fails any rank-1 action that lacks a
     productivity term, while runbook rule 15 puts the oldest operator tap at
     rank 1; and the career-term list contains the bare word `job`, so "day
     job" blocks fail as closed-career-search copy. The model reworded blocks
     to "Employer workday" to pass.
  3. `scripts/calendar_plan.py` exits 1 with `busy_source_failed` when the busy
     search was skipped on purpose (manifest-only policy).
- Stage 0.5 still reads `weekly_trend`, retired 2026-06-11 (lifeOS spec §9).
- Since v158/ADR 0019 (2026-08-20) the app's Decisions sheet + push and the two
  decision-digest crons (ADR 0016) own the operator tap queue. The briefing
  still counts `proposed` + `research_complete` tickets and drafts, so it has
  opened every day with "N taps pending, oldest from Aug 2" (52 days on
  09-23) — three of the digest's ~7 daily cards were about parked taps.
- `schedule_blocks` now feed the digest's "Now/Next" card
  (`api/winter_digest.py::_next_block_card`) and the block Live Activities
  (`agent/live_activity.py`), so block text is card copy.

### 1.2 Weekly program review — runs 17 hours early, currently disabled

- Trigger `trig_01TUcmdDJU8765zteDvoStcK` is still named "Weekly Learner";
  cron `0 8 * * 0` UTC = **Sunday 04:00 ET**. The runbook, README and paste
  body all say Sunday ~21:15 ET.
- Consequence, every week: the kill gate read the previous week's `rep_weeks`
  rollup (the verifier rolls up Sunday 20:35 ET), and Stages 2.7 (insight
  sweep, 05:37) and 2.8 (benefit scorecard, 09:07) always skipped "not run
  yet". The 09-20 review notes say so explicitly.
- 09-06 and 09-13 stopped on the kill gate (no program for those weeks);
  09-20 proceeded on the stale 09-07 rollup.
- `enabled: false` as of 2026-09-23 00:24 ET (`updated_at`). Assumed
  accidental (operator confirmed the re-enable in session).

### 1.3 Monthly learner — has not run since 2026-06-28

- Trigger `trig_01MV43DVqekDGxza44V4QGiM`, cron `16 4 1 * *` UTC = the 1st of
  each month 00:16 ET. The body's live gate requires day-of-week 7 AND
  day-of-month 01–07, so 08-01 (Sat) and 09-01 (Tue) both exited in 26 s:
  "not first Sunday — skipped".
- `user_profile` is frozen at v17 (2026-07-10, a commissioned run); the last
  `learning_agent` llm_run is 2026-06-28.
- `learning-agent.md` is still the weekly-trend design with a retarget banner;
  the paste body (v5) already carries a lifeOS Stage 1 (1a–1h) that
  "overrides" the runbook. The runbook's own staleness guard would abort on
  zero `weekly_trend` rows.

### 1.4 Cross-cutting

- The MCP key appears in plaintext in every run log's `tool_use Bash` text
  (each step re-exports it). Run logs are fetchable through the routines API.
  Flagged; not acted on (do-not-rotate directive).
- The paste bodies on disk are byte-identical to the live trigger bodies
  (verified by diff, key redacted), so "UI: pending re-paste" in the signoffs
  is stale bookkeeping — noted, not a defect.

---

## 2. Design A — daily briefing trim

### 2.1 Taps stop leading (runbook rule 15 + `extract.py`)

- Stage 0.5 keeps the `llm_db` tap query (drafts + `proposed` +
  `research_complete` tickets — it mirrors the platform's own `gather_taps`)
  and DROPS the finance read: `plaid_items.status = 'relink_needed'` matches
  no live row (statuses are active/dormant/retired), its action text names the
  retired relink email, and the replacement `plaid_harvest_links` table is
  credential-bearing and refused to the reader role by design. Money re-auth
  is owned by the Sunday harvest push + the app's `plaid_harvest` cards
  (ADR 0015/0019). `extract.py` drops the `plaid_relink` branch.
- `extract.py::_operator_taps` adds `is_new: bool` per tap —
  `pending_since >= YESTERDAY_ET` — and emits `operator_taps` (all, sorted
  oldest-first, unchanged shape + `is_new`) plus two counts
  `operator_taps_total` and `operator_taps_new` in `/tmp/data.json`.
- Rule 15 is rewritten:
  - Surface ONLY taps with `is_new == true`. The `llm_db` tap query also
    carries `NOT EXISTS (SELECT 1 FROM decision_surfacings d WHERE
    d.object_id = <ref>::text)` per branch, so a tap the decision digest has
    already surfaced is never re-mentioned — "new" means pending AND never
    yet surfaced by any channel. The briefing is a pure mirror: it records
    no appearance, so the shelf lifecycle (ADR 0016) stays digest-owned.
    Everything else produces nothing — no headline lead, no
    priority action, no risk flag, no "N taps pending" filler. The Decisions
    sheet, push, and digest crons own the standing queue (ADR 0016/0019).
  - Surfaced taps become ONE combined `priority_actions` entry at the LAST
    rank, `urgency: "today"`, `source: "user_profile"`, action starting with
    `Tap:` / `Approve:`, context naming refs and ages. Never rank 1.
  - `morning_brief.headline` never mentions taps.
- Rules 10/11 already make the rep (rep days) or the goal-serving action the
  hero and rank 1; no change there. Rule 16 untouched.

### 2.2 Validator drift closed (`validate_payloads.py`)

- Mirror every server hero limit from `shared/hero_surface_contract.py`:
  `target.label` ≤ 80 chars, `target.source` ≤ 40, `evidence` ≤ 3 items,
  `success_condition` ≤ 140, `avoid` ≤ 140 (already). A local constant block
  names the server file as its source.
- `CAREER_SEARCH_TERMS`: drop bare `job` and `jobs`; add `job search`
  (present), `job-search` (present), `job board`, `job posting`, `job hunt`,
  `job application`. "day job", "employer workday" no longer trip the
  closed-career rule. `genuine` also leaves the set (it only ever matched the
  Stage 0 career headline, which is preserved separately).
- The rank-1 alignment rule stays as is — with 2.1 taps are never rank 1, so
  the conflict disappears without weakening the rule.
- New WARNINGS (not failures): `schedule_blocks[].activity` > 60 chars,
  `schedule_blocks[].rationale` > 140 chars (card copy, §2.4).

### 2.3 Calendar plan exit (`calendar_plan.py`)

- When `/tmp/calendar_busy.json.status == "skipped_for_token_budget"`, the
  summary is `status: "ok"`, `busy_source: "skipped_for_token_budget"`,
  exit 0. Only a real busy-search failure keeps `busy_source_failed` / exit 1.
- The existing test that rejects `failed` on a skipped stub stays green.

### 2.4 Schedule blocks and narrative as card copy (runbook)

- Rule 6 gains: `activity` ≤ 60 chars, `rationale` ≤ 140 chars (the digest
  prints `time_range · category · rationale` under `Now/Next: <activity>`).
  One `admin` block per employer-workday half is fine; do not split further.
- Stage 3d narrative: same six sections (the feed and the validator expect
  them), each capped at three lines; it restates the JSON, it does not add
  analysis. `ACTIONABLE ITEMS` ≤ 3 entries.

### 2.5 Dead read removed

- The `weekly_trend` query and the finance tap query leave Stage 0.5
  (16 → 14 reads; the status line and paste-body count follow). `extract.py` already tolerates the absent
  file; its docstring line for `/tmp/weekly_trend.json` is removed.

### 2.6 Paste body v7 (`claude-routine-morning-briefing.v7.md`)

- Changes: the Stage 0.5 read count, one sentence stating the tap rule
  ("taps: new-since-yesterday only, last rank, never the headline"), and the
  Design E credential step. Signoff: `UI: NEEDS RE-PASTE` (Design E).

### 2.7 data-platform docs (same session)

- `docs/adr/0012-quiet-mode-serving-charter.md`: dated note under the
  "morning briefing leads with the operator tap queue" bullet — superseded by
  ADR 0016/0019; the briefing surfaces new taps only.
- `docs/reference/quiet-mode.md`: the "Briefing leads with taps" table row
  updated to the new rule with the commit reference.

### 2.8 Live Activities skip `device: none` blocks (data-platform, context-engine)

Decided in the 2026-09-23 grill. The ledger shows every schedule block
becomes a Live Activity, including "Employer workday (employer device)" and
meal/wind-down blocks that have no pace to measure ("credited 0 / expected 0"
for hours). `agent/live_activity.py::_today_blocks` skips any block whose
`device` is `none`; the briefing already sets `none` on exactly those blocks
(rule 13), so no new field is needed. Test: a `none` block never starts an
activity; `any`/`macbook`/`windows` blocks unchanged. Ships as the next
context-engine tag with the ADR 0012 note below.

---

## 3. Design B — weekly review retime + re-enable

### 3.1 Trigger (partial update, no body)

```json
{"name": "Weekly Program Review",
 "cron_expression": "CRON_TZ=America/Toronto 15 21 * * 0",
 "enabled": true}
```

First fire: Sunday 2026-09-27 21:15 ET — after the 20:35 rollup, the 05:37
sweep, the 09:07 scorecard and the 18:07 money story. `CRON_TZ=` is the form
the newer routines already use, so DST needs no manual hour bump.

### 3.2 Runbook (`program-review.md`)

- After Stage 0: **rollup freshness line** — if
  `rep_weeks[0].computed_at` is older than 24 h, print
  `WARN: newest rollup is <age>h old (week_start <date>) — expected <24h on a
  21:15 Sunday run` and continue. The kill gate reads what it has; the
  warning is copied into the review notes so a mis-scheduled run is visible.
- Stage 0 `gov_tickets` read becomes counts by live status:
  `SELECT status, count(*) FROM delegation_tickets WHERE status IN
  ('proposed','research_ready','research_complete','blocked') GROUP BY 1`
  plus the 5 newest `proposed` slugs. Stage 2.5 item 4 reports
  "tickets: N proposed / N research_complete awaiting decision / N
  research_ready / N blocked".
- **Stage 1.6 gets an input channel (grill decision A).** The job-stretch
  question has never had one: no memory row has ever carried an answer and a
  scheduled run has no operator present, so every review logged "answer
  unavailable" and the 3–4-week escalation clock could never start. Now: the
  operator saves ONE line during the week as an `agent_memory` row, key
  `job_artifact_<week_start ISO Monday>`, category `fact`, any source
  (MCP `save_memory` from any Claude session, or an Info-Me note the vault
  routine mirrors). Stage 0 reads `SELECT key, content FROM agent_memory
  WHERE key LIKE 'job_artifact_%' AND created_at > NOW() - INTERVAL '35 days'`.
  Stage 1.6 quotes the row for the week just ended verbatim; absence is a
  recorded non-answer ("no job_artifact row for week <date>"); the
  consecutive-non-answer count starts from the first review after this
  ships (state it in the notes: "clock started <date>"). The gate's decision
  (flip recommendation via Stage 0.9) is unchanged. Also: the runbook names
  the exact key format so the operator can write it without looking it up.
- Stage 2.5 intro: the three Gemini reviewers are not retired — they run
  weekly (Mon/Wed/Fri, ADR 0009); this stage is the operator-facing
  interpretation, theirs is platform-facing. One sentence.
- Stages 2.7/2.8 gain one line each: "on a 21:15 run this row exists; a skip
  here is a real absence, say so".
- Stage 2.8 also quotes the **shelved-decision count** from the scorecard
  row's `input_payload.funnel.shelved` (the glossary promises the Sunday
  review carries this one-line count; the runbook never had it). No new
  query.

### 3.3 Paste body v9 (`claude-routine-program-review.v9.md`)

- Header line becomes v9, the schedule note says the trigger now fires at
  21:15 ET under `CRON_TZ`, and the routine is named "Weekly Program Review".
  Task list unchanged (it already names 2.7/2.8); the Design E credential
  step replaces the "re-export each session" paragraph. Signoff: `UI: NEEDS
  RE-PASTE`.

---

## 4. Design C — monthly learner rebuild

### 4.1 Trigger (partial update)

```json
{"cron_expression": "CRON_TZ=America/Toronto 0 12 * * 0"}
```

Every Sunday at noon ET; the body's first-Sunday gate keeps the other Sundays
to a ~30 s skip. First real run: Sunday 2026-10-04. (Noon is deliberately
before the 21:15 review: the learner reads the previous Sunday's review, which
is immaterial over a 90-day window, and the two Opus runs never collide.)

### 4.2 Runbook rewrite (`learning-agent.md`)

The paste body's lifeOS stage list and Stage 1 inputs (1a–1h) become the
canonical runbook text; the retarget banner and every `weekly_trend` reference
go. Structure:

- **Stage 0** — anchors; `WINDOW_START_ET = TODAY_ET − 90d`.
- **Stage 0.5 — fold precheck** (the body's single query, verbatim):
  `newest_evidence` = greatest of newest `rep_weeks.computed_at` and newest
  `program_versions.created_at`; `rep_weeks_in_window`; `last_learner`;
  `profile_ts`. Folded (evidence older than both) or sparse
  (`rep_weeks_in_window < 4`) → no-mutation path.
- **Stage 1 — reads (one parallel turn)** into `/tmp/*.json`:
  1a profile (version + change_summary; full sections only on a mutation run),
  1b `program_versions` rows in window (id, status, source, valid_from,
  valid_until, `operator_input IS NOT NULL`, recompose_count),
  1c `rep_weeks` rows in window, 1d `rep_days` RAW rows in window (day,
  family, floor_met, floor_minutes, artifact, travel_excused),
  1e `proactive_interventions` in window (issued_at, action, final_outcome,
  `outcome_data->'delivery'->>'tag'`), 1f health: `apple_health_daily_metrics_v2`
  rows for `sleep_seconds`/`hrv_ms`/`steps` in window + `hevy_workouts`
  `started_at::date` in window, 1g `get_skill_summary {"days": 90}`,
  1h operator remarks (`agent_memory` goal/preference, live, in window) +
  `get_direction`, 1i the 6 newest `program_review` agent_runs
  (created_at, `left(final_response, 200)`), 1j prior learner runs, 1k live
  `learning_agent` memories.
- **Stage 1.2 — evidence packet**: `python3 scripts/learner_evidence.py`
  folds 1b–1i into `/tmp/evidence.json` (§4.3). Deterministic, no LLM.
- **Stage 1.5** guard as in the body (reinforcement-only when folded/sparse).
- **Stage 2** — `/tmp/ctx.json = {current_profile, evidence, prior_learner_runs,
  existing_memories}`.
- **Stage 3** — synthesis contract unchanged, with rule 3 restated: a trait is
  removed only if contradicted by two consecutive monthly packets or absent
  from the packet's evidence for 90 days; `audit_plan.source_table` names
  lifeOS/health/rescuetime tables.
- **Stage 4** — unchanged, plus the body's SQL notes (ledger is truth for
  floors; focus% threshold named; ET-as-UTC cast; `ROUND(x::numeric, n)`).
- **Stage 5** — unchanged (compose gate, memory verification, writes,
  `learner_digest`); goal string `Monthly behavioral profile analysis
  (lifeOS v<N>)`; the continuity matcher (`%behavioral profile%`) still
  matches.
- The weekly-trend staleness abort is deleted; the bootstrap guard stays.

### 4.3 `scripts/learner_evidence.py` contract

Inputs: the Stage 1 `/tmp/*.json` envelopes. Every missing or errored file
degrades to `null` for that section and is listed in
`coverage.missing_inputs`; the script never exits non-zero on missing data.
Health rows and rep days live in different databases, so the join is done in
Python on the ET date.

```json
{
  "window": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "days": 90},
  "program": {"versions": [{"id", "status", "source", "valid_from", "valid_until",
                            "operator_input": true, "recompose_count": 0}],
              "operator_recalibrations": 0, "auto_versions": 0,
              "kill_gate_stops": ["YYYY-MM-DD"]},
  "rep_weeks": {"rows": [{"week_start", "floors_met", "bar", "green"}],
                "green_rate": 0.0, "consecutive_non_green_now": 0,
                "auto_weeks_no_operator_input": 0},
  "rep_days": {"by_family": [{"family", "slots", "floors", "artifacts", "avg_minutes"}],
               "by_weekday": [{"weekday", "slots", "floors"}],
               "days_with_floor": 0, "longest_floor_streak": 0,
               "travel_excused_days": 0},
  "steering": {"episodes": 0, "outcomes": {"reduced": 0, "held": 0, "backfired": 0,
               "insufficient_data": 0}, "by_action": {"WARN_LOCAL": 0, "LOCK_WINDOWS": 0},
               "delivery": {"enforced": 0, "delivered": 0, "delivered_not_enforced": 0,
               "undelivered": 0}, "evening_share": 0.0},
  "health": {"sleep_avg_h_30d": 0.0, "sleep_avg_h_90d": 0.0, "hrv_avg_30d": 0.0,
             "workout_days": 0,
             "floor_rate_sleep_ge_7h": 0.0, "floor_rate_sleep_lt_6_5h": 0.0,
             "floor_rate_workout_days": 0.0, "floor_rate_rest_days": 0.0,
             "samples": {"sleep_days": 0, "joined_rep_days": 0}},
  "skill": {"hands_on_min": 0, "ai_assisted_min": 0, "hands_on_share": 0.0,
            "streak_days": 0},
  "context": {"operator_remarks": [{"key", "created_at", "excerpt"}],
              "direction": {"version": 0, "skill_phase_excerpt": ""}},
  "coverage": {"rep_weeks_in_window": 0, "sparse": false, "missing_inputs": []}
}
```

`kill_gate_stops` = dates of `program_review` agent_runs whose
`final_response` begins with `KILL-GATE` (deterministic string match on the
09-06/09-13 wording). Rates are `null` when the denominator is 0.

### 4.4 Paste body v6 (`claude-routine-monthly-learner.v6.md`)

- Drops "INCLUDING its lifeOS retarget banner, which overrides…" (the runbook
  is now canonical), adds the Stage 1.2 packet step to the stage list, and a
  cadence note: "the trigger fires every Sunday noon ET; this gate skips all
  but the first Sunday". `LEARNER_MODE: LIVE` unchanged.
- **Re-paste required**: the live body quotes stage details the rewrite
  changes. Signoff: `UI: NEEDS RE-PASTE`.

---

## 4a. Design D — Amex: Platinum joins the Cobalt item (data-platform, plaid-collector v27)

Added during the 2026-09-23 grill (operator: "B is right, 2005 is the
Cobalt"). Lives in data-platform, not this repo; tracked here because it was
decided in the same session.

- **Live state:** one Amex item `0eBYdvRj…` (dormant, personal) with ONE
  account, mask 2005 = the **Cobalt** (1,619 rows since 2024-07-14, tags and
  placements attached). A July Amex item is retired with no accounts. The
  collector inserts `plaid_accounts` rows only at fresh-link completion
  (`contact_probe.py`, `link_admin.py`); a sync never adds accounts, and every
  personal-money consumer joins through `plaid_accounts`.
- **Rejected:** a fresh link selecting both cards — it re-pulls Cobalt's
  730-day history under new transaction ids (duplicate rows across two items,
  and deleting either side loses tags/placements or re-inserts on a later
  Plaid revision).
- **Chosen:** update-mode relink with account selection on the EXISTING item.
  1. `plaid_client.hosted_link_create` gains `account_selection: bool`; in
     update mode it adds `"update": {"account_selection_enabled": true}` to
     the `/link/token/create` payload.
  2. `link_admin.py relink <item_id> --add-accounts` passes the flag (the
     existing relink path otherwise unchanged: harvest window opened,
     `clear_relink`).
  3. The sync loop upserts `plaid_accounts` from the `accounts_get` it already
     makes per item (`INSERT … ON CONFLICT (plaid_account_id) DO NOTHING`,
     never overwriting `card_label`), so a newly added card gets its row on
     the first sync after the relink and its transactions are visible to the
     `plaid_accounts` joins immediately. Plaid backfills the new account's
     history through the item's existing cursor (bounded by the item's
     original `days_requested` = 730).
  4. Operator step: run the relink (bank contact happens at the moment of
     relink, ADR 0015 amendment), tick the Platinum in Link, done; the next
     6-hourly tick proves it (`added N` on the new account, a second
     `plaid_accounts` row for the item).
- **Tests:** payload shape with/without the flag; sync inserts an unknown
  account and leaves a known one's `card_label` alone; CLI flag wiring.
- **Docs:** CLAUDE.md plaid-collector row (v27 note), `container-image-tags.md`,
  the Plaid session record; `plaid_items` gotcha 4 gains "an item may carry
  more than one card — never assume one account per Amex item".

---

## 4b. Design E — the key lives in one sandbox file (all three routines)

Grill decision A (2026-09-23). Each runbook step re-exported `MCP_API_KEY`
inside its Bash command text, so the key appeared ~15× per run in the run
transcript — which is durable and fetchable through the routines API — while
the rule "never write the key to a local env file" protected the ephemeral
sandbox `/tmp` instead. Zero exposure is impossible while the key rides
inline (routines have no secret env), so the posture becomes once-per-run:

- The first Bash step of every paste body writes the credentials ONCE:
  `umask 077; printf 'MCP_BASE_URL=%s\nMCP_API_KEY=%s\n' … > /tmp/mcp.env`
  (the only place the literal appears in the transcript). Every later step
  begins `set -a; . /tmp/mcp.env; set +a` (or `source`) — no re-export.
- Rule flip in `CLAUDE.md` → Credential Handling and in each runbook's
  credential paragraph: the key may live ONLY in `/tmp/mcp.env`, mode 600,
  inside the run sandbox; never printed, `cat`-ed, copied, or referenced by
  value; `/tmp/morning_briefing_dates.env` and `/tmp/anchors.env` stay
  key-free (unchanged). `scripts/anchor_env.sh` unchanged.
- `tests/test_runbook_contract.py::test_parallel_stage_env_handling_avoids_
  inline_secret_exports` is repointed to the new wording (no inline exports
  in stage commands; one env file).
- Paste bodies (all three) carry the new first step and drop "re-export each
  session" — this is the reason the morning and review bodies are re-pasted
  after all (they were optional under A/B alone). Signoffs: `UI: NEEDS
  RE-PASTE`.

---

---

## 5. Tests

- `tests/test_goal_context_and_validation.py`: hero `target.label` 81 chars
  rejected, 80 accepted; `target.source` 41 rejected; `evidence` 4 items
  rejected; "Employer workday"/"day job" blocks accepted under closed career
  search; "job board"/"job posting" still rejected; block-length warnings.
- `tests/test_calendar_coverage.py` (or a new `test_calendar_plan.py`):
  skipped busy stub → summary `ok`, `busy_source skipped_for_token_budget`,
  exit 0; a `status: "error"` stub still exits 1.
- New `tests/test_extract_taps.py`:
  `is_new` true for `pending_since == YESTERDAY_ET`, false for older; counts.
- `tests/test_runbook_contract.py`: rule 15 wording (new taps only, last
  rank, never the headline); Stage 0.5 has neither `weekly_trend` nor the
  finance tap read; the
  learner test `test_stage_one_reads_only_production_weekly_trend…` is
  replaced by a lifeOS-reads test (1b–1k present, no `weekly_trend`).
- New `tests/test_learner_evidence.py`: full fixtures → every section
  populated with hand-computed values; empty envelopes → nulls +
  `missing_inputs`; sparse flag at 3 vs 4 rep weeks; cross-db health join on
  the ET date; `kill_gate_stops` string match.
- New `tests/test_program_review_contract.py`: the freshness line, the
  ticket-status read, the 2.5 intro sentence, the `job_artifact_` memory
  read + key format, the shelf line.

Run: `python3 -m unittest discover -s tests` from the repo root (Python 3.10
on the Mac).

---

## 6. Rollout and proof

Ownership (grill decision): Claude implements, tests, pushes winter-routine
`main`, updates the three triggers through the routines API, and builds +
deploys both VM images with their proof runs. The operator re-pastes the
three bodies in the Routine UI and completes the Amex account-selection
relink in Link when the CLI prints the URL.

1. Implement + tests green on the Mac; commit to `main`; push to GitHub
   (the cloud routines clone GitHub `main` at run time).
2. Trigger updates via `RemoteTrigger update` (partial bodies in §3.1/§4.1),
   then `get` to confirm `enabled`, `cron_expression`, `next_run_at`.
3. Paste bodies: rename on disk (`mv` to the new `v<N>`), operator re-pastes
   all three (Design E changes every body's first step).
4. **Pre-deploy proof for the packet** (live proof runs are mandatory):
   run the Stage 1 reads + `learner_evidence.py` from the Mac against the
   live endpoint (`scripts/mcp.sh` with the local env) and read the packet
   by eye before the first cloud run.
5. **Live proofs:** the 09-24 06:35 morning run (expect: no tap lead, no
   server rejection, calendar plan exit 0, 14 reads); the 09-27 21:15 review
   (expect: rollup age < 1 h, Stages 2.7/2.8 populated); the 10-04 12:00
   learner (expect: fold precheck decides, packet in `ctx.json`, audit
   passes, profile v18 or an honest NO MUTATION).
6. Budget two point releases after the first live learner run (every new
   routine has failed its first live run for a reason no test caught).
7. Design D: plaid-collector v27 built + imported + all three plaid CronJobs
   repinned; then `link_admin.py relink 0eBYdvRj… --add-accounts` from a
   one-off Job (the operator ticks the Platinum); proof = a second
   `plaid_accounts` row on the item and `added N` for it on the next tick.
8. Design 2.7a: context-engine tag with the `device: none` skip; proof = the
   next morning's Live Activity ledger shows no employer/meal/wind-down rows.
9. Optional UI cleanup (no API delete exists): the operator deletes the two
   dead routines `Z-DONE Learning Agent` and the `ZZ-DEPRECATED` Winter
   trigger from https://claude.ai/code/routines.

---

## 7. Assumptions

- The weekly trigger's `enabled: false` (2026-09-23 00:24 ET) was not a
  deliberate retirement — the operator chose "re-enable" in session.
- The routines API accepts `CRON_TZ=` on update as it does on create (the
  newer routines were created with it).
- The learner's Stage 3/4/5 contracts are sound; only the evidence inputs and
  guards change.

## Signoff

2026-09-23 ET · operator session (Claude, Fable 5.1) — spec created from the
re-evaluation session; designs A/B/C approved section by section, then
grilled: finance tap read dropped, NOT EXISTS surfacing guard, Live Activity
`device: none` skip (§2.8), Stage 1.6 memory channel, shelf line, Design D
(Amex account selection), Design E (single sandbox key file), rollout
ownership. (History in git.)
