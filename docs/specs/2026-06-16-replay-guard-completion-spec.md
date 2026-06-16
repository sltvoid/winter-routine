# Tech Spec — Morning-Briefing Replay Guard: Robust Same-Day Detection + Partial-Completion

- **Status:** Draft for implementation handoff
- **Date:** 2026-06-16
- **Owner:** (assign)
- **Affected components:** `scripts/replay_guard.py`, `morning-briefing.md` (Stage -1 SQL + Stage -1/Stage 4 handling), `scripts/write_run.sh` (idempotency note), new `scripts/completion_check.py`
- **Branch:** `claude/sweet-thompson-qf42s6`

---

## 1. Background & motivation

The daily morning-briefing pipeline ran for 2026-06-15 and wrote `rt_yesterday`,
`email_daily`, `daily_briefing` (id 3637) and the narrative `agent_run` at
`2026-06-15T01:19Z`. It did **not** reach Stage 4, so the parity memory candidate
(`parity_2026-06-14_youtube.com`) was never persisted.

On a later manual catch-up run, two defects surfaced:

1. **Same-day detection is incomplete.** The Stage -1 replay-guard query only
   surfaced `daily_briefing` (3637) and the `agent_run`. It missed the prior
   run's `rt_yesterday` / `email_daily` rows, so the operator was told they were
   "non-duplicate" and re-persisted them — creating **duplicate** rows
   (`rt_yesterday` 3664, `email_daily` 3665).

2. **No partial-completion path.** Because a same-day `daily_briefing` existed,
   the guard (run with `--diagnostic-on-existing`) selected `diagnostic_replay`
   = full no-write mode. The genuinely-missing artifact (the Stage 4 memory) was
   therefore **not** auto-completed; it required manual intervention.

### Root cause of (1)

`rt_yesterday` / `email_daily` rows carry `output_response.date = <analyzed day>`
(yesterday), set by `scripts/payloads.py` (`date = data.analyzed_date or
$YESTERDAY_ET`). They only carry `input_payload.today = <today>` when
`write_run.sh` is invoked with `TODAY_ET` exported — and the prior run's rows did
**not** have `today` populated. The Stage -1 SQL filters these run types by:

```sql
output_response->>'date' = '$TODAY_ET' OR input_payload->>'today' = '$TODAY_ET'
```

With `date = yesterday` and `today` empty, neither predicate matches, so the
rows are invisible to the guard. `replay_guard._matches_today()` then never sees
them either.

---

## 2. Goals / non-goals

### Goals
- G1. Same-day detection reliably includes `rt_yesterday` / `email_daily` /
  `calendar_write` rows that belong to today's run, regardless of which date
  field they carry, so duplicates cannot be produced by a re-run.
- G2. A re-run that finds a same-day `daily_briefing` but missing sibling rows
  (any of `rt_yesterday`, `email_daily`, `calendar_write`, or the Stage 4
  memory) **completes only the missing artifacts idempotently**, with no
  operator intervention and no duplication of existing rows.
- G3. An end-of-run completion check confirms all expected artifacts exist for
  the pipeline and reports/self-heals gaps.

### Non-goals
- N1. Changing the Routine UI schedule or timezone (operator-side; see §9).
- N2. Adding `DELETE`/`UPDATE` for `llm_runs` (the MCP surface is append-only).
- N3. Reworking calendar placement (handled by the existing Codex watchdog).

---

## 3. Detailed design

### 3.1 Broaden the Stage -1 detection query (`morning-briefing.md`)

Add `$YESTERDAY_ET` to the query and detect this run's sibling rows by **(a)**
analyzed-date match and **(b)** pipeline correlation with a same-day
`daily_briefing`. Replace the current `WHERE` for the `llm_runs` branch with:

```sql
WHERE run_type IN ('rt_yesterday','email_daily','daily_briefing','calendar_write')
  AND created_at >= (TIMESTAMP '$TODAY_ET 00:00' AT TIME ZONE 'America/Toronto') - INTERVAL '18 hours'
  AND (
        output_response->>'date' = '$TODAY_ET'
     OR input_payload->>'today'  = '$TODAY_ET'
     -- rt_yesterday / email_daily carry the analyzed (yesterday) date:
     OR (run_type IN ('rt_yesterday','email_daily')
         AND output_response->>'date' = '$YESTERDAY_ET')
     -- any sibling row sharing a pipeline with today's daily_briefing:
     OR pipeline_id IN (
          SELECT pipeline_id FROM llm_runs
          WHERE run_type = 'daily_briefing'
            AND output_response->>'date' = '$TODAY_ET'
        )
  )
```

Notes:
- The `created_at` lower bound keeps the scan bounded and prevents matching an
  `email_daily` whose analyzed date legitimately equals a *different* day's
  yesterday. Tune the 18h window to comfortably cover an evening-before run plus
  a same-morning run.
- Keep the existing `agent_runs` UNION branch unchanged.

The guard must continue to receive `--today-et`; add `--yesterday-et`.

### 3.2 Pipeline-correlation pass in `replay_guard.py`

`_matches_today()` currently checks only `input_today`, `output_date`,
`briefing_date`, `goal`. Make detection two-pass:

1. Compute `same_day_pipelines = { row.pipeline_id : row matches today via the
   existing per-row predicates AND run_type == 'daily_briefing' }` (plus any row
   already matching today directly).
2. A row is **same-day** if it matches the existing predicates **OR**
   `row.pipeline_id ∈ same_day_pipelines` **OR**
   (`run_type ∈ {rt_yesterday, email_daily}` AND `output_date == yesterday_et`).

Add `--yesterday-et` (required) and thread it through `main()` → `_summary()`.

### 3.3 New action: `complete_missing`

Extend `_summary()` to compute the missing set and prefer completion over blanket
diagnostic when it is safe. Define:

```
EXPECTED_LLM_TYPES = {"rt_yesterday", "email_daily", "daily_briefing", "calendar_write"}
present_types      = set(by_type)            # from detected same-day rows
missing_types      = EXPECTED_LLM_TYPES - present_types
```

Decision precedence (highest first):

| Condition | action | status | mode for runbook |
|---|---|---|---|
| `--allow-full-replay` | `full_replay_explicit` | ok | live, expect dupes |
| no matching rows | `continue` | ok | live full run |
| watchdog-only, no briefing | `continue_after_watchdog_only` | ok | live full run |
| `daily_briefing` present **and** `missing_types` ∪ `memory_missing` ≠ ∅ | **`complete_missing`** | ok | live, **write only missing** |
| `daily_briefing` present, nothing missing, calendar unverified | `calendar_only_repair` | stop | calendar repair only |
| `daily_briefing` present, nothing missing | `diagnostic_replay` (if `--diagnostic-on-existing`) else `same_day_rows_exist` | ok / stop | no-write / stop |

`complete_missing` must emit, in the summary JSON:

```json
{
  "action": "complete_missing",
  "missing_run_types": ["calendar_write"],
  "present_run_types": ["rt_yesterday","email_daily","daily_briefing"],
  "existing_row_ids": { "...": [ids] },
  "recommendation": "Same-day daily_briefing exists; write ONLY the missing artifacts (run_types + Stage 4 memory) live and idempotently. Do not rewrite existing rows."
}
```

Memory presence is **not** knowable from `llm_runs`; the guard cannot see
`agent_memory`. So `memory_missing` is determined in Stage 4 by the existing
exact-key recall (already idempotent). The guard's job is only to keep Stage 4
*enabled* on the `complete_missing` path.

### 3.4 Runbook handling of `complete_missing` (`morning-briefing.md`)

Add to the Stage -1 interpretation list:

- `action=complete_missing`: run the full read/build/validate flow. For
  **writes**, set `ROUTINE_MODE=live ALLOW_WRITES=1` but gate each write on
  membership in `missing_run_types`:
  - Stage 1 writes `rt_yesterday` **only if** `"rt_yesterday" ∈ missing_run_types`.
  - Stage 2 writes `email_daily` **only if** `"email_daily" ∈ missing_run_types`.
  - Stage 3 writes `daily_briefing` **only if** `"daily_briefing" ∈ missing_run_types`
    (normally present → skipped).
  - Stage 3.5 writes the `calendar_write` manifest **only if**
    `"calendar_write" ∈ missing_run_types`.
  - Stage 4 always runs; the exact-key recall skips already-present memories.

  Provide the gate as an env list, e.g. `MISSING_RUN_TYPES="calendar_write"`,
  sourced from `/tmp/replay_guard.json`, and have each stage `case`-check it.

### 3.5 Idempotency contract (`write_run.sh` + runbook)

`write_llm_run` is append-only, so idempotency is the caller's responsibility.
Codify it:

- Writes are guarded by `missing_run_types` (above), so a present row is never
  re-written.
- `write_run.sh` should **always** be invoked with `TODAY_ET` and `YESTERDAY_ET`
  exported, so every future `rt_yesterday`/`email_daily` row carries
  `input_payload.today` — making §3.1's `input_today` predicate sufficient on its
  own going forward (the analyzed-date / pipeline fallbacks remain for
  historical rows). Add an assertion in `write_run.sh`: if `TODAY_ET` is empty,
  print a warning to stderr (do not fail).

### 3.6 End-of-run completion verifier (`scripts/completion_check.py`, new)

After Stage 4, query the same-day rows once more and assert the expected set:

```
expected = {rt_yesterday, email_daily, daily_briefing, calendar_write, agent_runs}
```

Output `/tmp/completion_check.json` with `{complete: bool, missing: [...],
duplicate_run_types: [...]}`. `duplicate_run_types` flags any run_type with >1
same-day row (so duplication is detected, not silently accepted). The final
summary prints `completion: ok` or `completion: INCOMPLETE missing=[...]` /
`duplicates=[...]`. This is a read-only safety net; it does not write.

---

## 4. Acceptance criteria

- AC1. Given a same-day `daily_briefing` plus same-pipeline `rt_yesterday` /
  `email_daily` rows whose `output_response.date = yesterday` and whose
  `input_payload.today` is empty, the guard reports them under
  `present_run_types` and does **not** recommend re-writing them.
- AC2. Given a same-day `daily_briefing` with `calendar_write` missing and the
  parity memory absent, the guard returns `action=complete_missing` with
  `missing_run_types=["calendar_write"]`; a live run then creates exactly the
  calendar manifest row + the one memory, and **zero** duplicate `rt_yesterday`
  / `email_daily` rows.
- AC3. Given a complete same-day set with nothing missing, behavior is unchanged
  (`diagnostic_replay` under `--diagnostic-on-existing`, else
  `same_day_rows_exist`).
- AC4. `completion_check.py` flags `duplicate_run_types` when two same-day rows
  of a type exist (regression test against the 3664/3665 situation).
- AC5. No new network calls in `replay_guard.py` / `completion_check.py` beyond
  the single existing `query_raw_sql` read each.

---

## 5. Test plan

Add `tests/` fixtures (JSON `query_raw_sql` responses) and unit tests:

- `test_replay_guard_detects_sibling_by_pipeline` (AC1).
- `test_replay_guard_detects_rt_email_by_analyzed_date` (AC1).
- `test_replay_guard_complete_missing_calendar` (AC2 guard half).
- `test_replay_guard_complete_nothing_missing_diagnostic` (AC3).
- `test_completion_check_flags_duplicates` (AC4).
- `test_completion_check_ok` (happy path).

Run `python3 -m pytest tests/` (repo already uses pytest per `.gitignore`).

---

## 6. Rollout

1. Land guard + SQL + tests behind no flag (detection broadening is strictly
   safer — it can only *add* detected rows).
2. Land `complete_missing` + runbook stage gating.
3. Land `completion_check.py` + final-summary wiring.
4. Backfill-safe: historical rows without `today` are matched via analyzed-date
   / pipeline fallbacks.

---

## 7. Risk & mitigations

- **R1: analyzed-date fallback over-matches** an unrelated prior day's
  `email_daily`. Mitigation: the `created_at` window (§3.1) + pipeline
  correlation; prefer pipeline correlation as the primary signal.
- **R2: `complete_missing` races a concurrently-running cron.** Mitigation: the
  pipeline already runs once/day; add an advisory note that manual completion
  runs should not overlap the scheduled slot.
- **R3: partial write of `daily_briefing` (the anchor) is missing.** If
  `daily_briefing` itself is missing, this is *not* a partial-completion case —
  fall through to `continue` (full live run), not `complete_missing`.

---

## 8. Data cleanup (separate, operator decision)

Duplicate rows created during diagnosis — `llm_runs` **3664** (`rt_yesterday`)
and **3665** (`email_daily`), both analyzing 2026-06-14 — duplicate the prior
run's equivalents. There is no MCP delete/expire for `llm_runs`. Options:
(a) leave them and confirm downstream consumers select latest-by-`created_at`
(benign) vs. aggregate (double-count); (b) operator DB cleanup out-of-band;
(c) explicit one-time raw `DELETE` of exactly those two ids. Recommend (a)
after a quick read of consumer logic. **Out of scope for this spec's code
changes.**

---

## 9. Open questions

- Q1. Schedule/timezone: the run fired 01:19Z (≈21:19 ET) but the runbook says
  "~7 AM ET." Is the Routine intentionally evening-before, or is the UI schedule
  mis-set? Resolve operator-side.
- Q2. Should `complete_missing` also re-verify calendar via the Codex watchdog,
  or only write the manifest? Current spec: manifest only (matches existing
  manifest-only policy).

---

## 10. Implementation notes & deviations (2026-06-16, TDD)

Implemented across 4 commits (`d870116` Phase 1, `0d61401` Phase 2, `f51b1f5`
Phase 3, `9c5fe0c` review iteration 2); 105 tests pass. AC1–AC5 met. Deviations
from the draft, all driven by adversarial review:

1. **`complete_missing` is the DEFAULT when same-day rows exist** (not just
   "briefing present AND missing siblings"). This was forced by two gaps the draft
   could not close as written:
   - **R3 (briefing-missing):** the draft said fall through to `continue`, but a
     full `continue` re-writes the present rt/email (dups). Instead, `complete_missing`
     now fires even with the briefing anchor missing; the gate skips present rows,
     so the briefing is written without duplicating rt/email.
   - **Memory-only (the literal §1 incident):** the draft's trigger was
     `missing_types ∪ memory_missing ≠ ∅`, but the guard cannot see `agent_memory`,
     so a run with all 4 llm_runs + narrative present but the Stage 4 memory missing
     was never healed. Fix: when same-day rows exist, the guard returns
     `complete_missing` with a possibly-EMPTY `missing_run_types`, and **Stage 4
     always runs live** — its idempotent exact-key recall writes only the genuinely
     missing memory.
2. **`diagnostic_replay` is now explicit-only** — reachable via `--diagnostic-on-existing`
   (an inspection run), not the always-on default. The runbook no longer passes it
   by default.
3. **Gate keys on `${MISSING_RUN_TYPES+set}`** (set-vs-unset), so an exported-but-empty
   value skips ALL llm/agent writes (memory-only case) while UNSET = normal full run.
4. **Write-gate is centralized** in `write_run.sh`/`write_agent.sh` (§3.4's per-stage
   `case`-checks were not used — DRY, can't-forget-a-stage).
5. **`calendar_only_repair` removed** (and `_calendar_ok`): under the manifest-only
   policy, calendar verification is the Codex watchdog's job; the action was dead.
6. **`run_scope='production'` filter added** to the Stage -1 SQL + its pipeline
   subquery (review LOW) so a test/canary briefing can't contaminate detection.

Outstanding (not code): merge `claude/sweet-thompson-qf42s6` → `main`; bump the
Routine UI `REQUIRED_HEAD`; update the Routine UI "Same-Day Rows" section to honor
the guard `action` (it currently collapses to live/diagnostic); decide on the
3664/3665 duplicate-row cleanup (§8).
