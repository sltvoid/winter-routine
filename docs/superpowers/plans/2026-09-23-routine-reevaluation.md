# Routine Re-evaluation (Winter-Routine side) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trim the daily briefing to what the app cannot get elsewhere, move the Sunday review to 21:15 ET with a real input channel for its job-stretch gate, rebuild the monthly learner on lifeOS ledgers, and put the MCP key in one sandbox file per run.

**Architecture:** Runbooks (`*.md`) are read from the git checkout at run time by claude.ai cloud routines; helper scripts under `scripts/` do the mechanical work and are covered by `unittest` in `tests/`. Three gitignored paste bodies (`claude-routine-*.v<N>.md`) carry the live MCP key and are re-pasted into the Routine UI by the operator. Trigger schedules live in the claude.ai routines API (`RemoteTrigger`), not in this repo.

**Tech Stack:** bash + `jq` + python3 (3.10 on the Mac, 3.12 in the cloud sandbox), `unittest` (run with `python3 -m unittest discover -s tests`), HTTPS MCP via `scripts/mcp.sh`.

**Spec:** `docs/specs/2026-09-23-routine-reevaluation-spec.md` (Designs A, B, C, E live here; §2.7, §2.8 and Design D are in the data-platform plan `docs/superpowers/plans/2026-09-23-routine-reevaluation-platform.md` of that repo).

## Global Constraints

- Every edit to a runbook, paste body, or `docs/` file ends by updating that file's `## Signoff` block (bare style: version/date line + `UI:` status for paste bodies). An edit without a signoff update is incomplete (`CLAUDE.md` → Signoff convention).
- Paste bodies are renamed on version bump (`mv claude-routine-<name>.v<N>.md claude-routine-<name>.v<N+1>.md`); the top header line reads `**v<N+1> · last revised 2026-09-23 ET**`; `.gitignore` already covers `/claude-routine-*.md` — never add exact filenames.
- No literal MCP key in any tracked file, commit, plan, or terminal output. Paste-body steps below say "(key line unchanged)" where the key sits.
- Server hero limits are the source of truth (data-platform `shared/hero_surface_contract.py`): headline 44 chars/6 words, reason 160/28, secondary 56/8, `target.label` ≤ 80, `target.source` ≤ 40, `evidence` ≤ 3 items, `success_condition` ≤ 140, `avoid` ≤ 140.
- Stage 0.5 of the daily runbook has exactly **14** reads after this plan (was 16).
- Tap rule: a tap is surfaced only when `is_new` (pending since `YESTERDAY_ET` or later AND never surfaced by any channel — `NOT EXISTS` on `decision_surfacings`); one combined `priority_actions` entry at the LAST rank, `urgency: "today"`, `source: "user_profile"`; never rank 1, never the headline, never a risk flag.
- Commit after every task with the repo's `type(scope): summary` style; do not push until Task 12.
- Frame decision (job season vs settled-job) is OUT of scope: rule 16 and the Stage 1.6 decision text stay byte-identical.

---

### Task 1: Design E — one sandbox key file (CLAUDE.md + daily runbook + contract test)

**Files:**
- Modify: `CLAUDE.md` (section `## Credential Handling`, lines ~66–72)
- Modify: `morning-briefing.md` (paragraph at lines ~110–113 that starts "`/tmp/morning_briefing_dates.env` contains only non-secret")
- Test: `tests/test_runbook_contract.py`

**Interfaces:**
- Produces: the canonical wording `source /tmp/mcp.env` that Tasks 9–11 (paste bodies) and Task 8 (learner runbook) reuse verbatim.

- [ ] **Step 1: Write the failing tests**

Append to `class RunbookContractTests` in `tests/test_runbook_contract.py` (after `test_parallel_stage_env_handling_avoids_inline_secret_exports`):

```python
    def test_credentials_live_in_one_sandbox_file(self):
        self.assertIn("source /tmp/mcp.env", self.runbook)
        self.assertNotIn("write the API key to any local env file", self.runbook)
        claude_md = Path("CLAUDE.md").read_text()
        self.assertIn("/tmp/mcp.env", claude_md)
        self.assertIn("umask 077", claude_md)
        self.assertIn("Never re-export the literal in later steps", claude_md)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/steventa/Documents/CodingJunk/Winter-Routine && python3 -m unittest tests.test_runbook_contract.RunbookContractTests.test_credentials_live_in_one_sandbox_file -v`
Expected: FAIL — `'source /tmp/mcp.env' not found in ...`

- [ ] **Step 3: Replace the CLAUDE.md Credential Handling section**

Replace the whole `## Credential Handling` section (the paragraph ending "…do not write it into files, artifacts, PRs, or git history.") with:

```markdown
## Credential Handling

The repository must never contain a committed literal MCP API key; runbooks and
scripts use `$MCP_API_KEY`. Treat the key as a secret: do not echo, print, log,
summarize, or commit it; do not include it in curl text shown to the user; do
not write it into artifacts, PRs, or git history.

Inside a run the key lives in exactly ONE place: `/tmp/mcp.env`, written once
by the routine's first Bash step —

```bash
umask 077
cat > /tmp/mcp.env <<'ENV'
export MCP_BASE_URL='https://a8f2e1.steventa.me'
export MCP_API_KEY='<the key from the paste body>'
ENV
```

— and loaded by every later step with `source /tmp/mcp.env`. Never re-export
the literal in later steps: each inline export lands in the run transcript,
which is durable and fetchable through the routines API; the sandbox file is
ephemeral. Never `cat`, copy, or print `/tmp/mcp.env`, and never write the key
into any other file (`/tmp/morning_briefing_dates.env`, `/tmp/anchors.env`,
and every `/tmp/*.json` stay key-free). (2026-09-23 decision, spec
`docs/specs/2026-09-23-routine-reevaluation-spec.md` Design E.)
```

Then update the `## Signoff` block at the bottom of `CLAUDE.md` to:

```markdown
## Signoff

2026-09-23 ET · operator session — Credential Handling: the key lives in one
sandbox file (`/tmp/mcp.env`) per run; inline re-exports retired (spec Design
E). Earlier: 2026-07-03 environment section condensed. (History in git.)
```

- [ ] **Step 4: Replace the daily runbook's credential paragraph**

In `morning-briefing.md`, replace the paragraph

```
`/tmp/morning_briefing_dates.env` contains only non-secret date/pipeline values.
Do not inline `MCP_API_KEY` in per-command or background-job text, and do not
write the API key to any local env file. Credentials must be exported once in
the active routine shell or provided by the routine environment.
```

with

```
`/tmp/morning_briefing_dates.env` contains only non-secret date/pipeline values.
Credentials live ONLY in `/tmp/mcp.env`, written once by the routine's first
step (CLAUDE.md → Credential Handling). Every stage's shell begins with
`source /tmp/mcp.env` and `source /tmp/morning_briefing_dates.env`. Do not
inline `MCP_API_KEY` in per-command or background-job text, and do not write
the key into any other local file.
```

(The Stage 0.5 sentence "Do not inline `MCP_API_KEY`, `MCP_BASE_URL`, or repeated `export ... &&` prefixes inside individual background jobs" stays as is.) The runbook signoff is updated once, in Task 5.

- [ ] **Step 5: Run the test suite**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` (the new test passes; nothing else changed).

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md morning-briefing.md tests/test_runbook_contract.py
git commit -m "feat(credentials): the MCP key lives in one sandbox file per run (spec Design E)"
```

---

### Task 2: `extract.py` — tap `is_new`, counts, finance read dropped

**Files:**
- Modify: `scripts/extract.py` (docstring lines 11–27; `_operator_taps` lines ~294–321; `main()` output dict lines ~443–445)
- Create: `tests/test_extract_taps.py`

**Interfaces:**
- Produces in `/tmp/data.json`: `operator_taps: [{kind, ref, pending_since, action, is_new: bool}]` (oldest first), `operator_taps_total: int`, `operator_taps_new: int`. Consumed by runbook rule 15 (Task 5). No `plaid_relink` kind exists any more.
- Reads `os.environ["YESTERDAY_ET"]` (exported by `scripts/anchor_env.sh` / the sourced dates file). Missing anchor ⇒ every tap `is_new=False` (mute, never nag).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_extract_taps.py`:

```python
import os
import unittest
from unittest.mock import patch

from scripts import extract


class OperatorTapsTests(unittest.TestCase):
    def _load_factory(self, llm_rows, finance_rows=None):
        def fake_load(path, default):
            if path == "/tmp/operator_taps_llm.json":
                return {"data": llm_rows}
            if path == "/tmp/operator_taps_finance.json":
                # The finance read is retired; a stale file on disk must be ignored.
                return {"data": finance_rows or []}
            return default
        return fake_load

    def test_is_new_when_pending_since_is_yesterday_or_later(self):
        rows = [
            {"kind": "ticket_proposed", "ref": "t-old", "pending_since": "2026-09-01", "action": "Decide"},
            {"kind": "goal_policy_draft", "ref": "g-new", "pending_since": "2026-09-22", "action": "Approve"},
            {"kind": "ticket_research_complete", "ref": "t-today", "pending_since": "2026-09-23", "action": "Decide"},
        ]
        with patch.object(extract, "_load", side_effect=self._load_factory(rows)), \
             patch.dict(os.environ, {"YESTERDAY_ET": "2026-09-22"}):
            taps = extract._operator_taps()
        self.assertEqual([t["ref"] for t in taps], ["t-old", "g-new", "t-today"])  # oldest first
        self.assertEqual([t["is_new"] for t in taps], [False, True, True])

    def test_missing_anchor_mutes_every_tap(self):
        rows = [{"kind": "ticket_proposed", "ref": "t1", "pending_since": "2026-09-23", "action": "Decide"}]
        env = {k: v for k, v in os.environ.items() if k != "YESTERDAY_ET"}
        with patch.object(extract, "_load", side_effect=self._load_factory(rows)), \
             patch.dict(os.environ, env, clear=True):
            taps = extract._operator_taps()
        self.assertEqual(taps[0]["is_new"], False)

    def test_finance_relink_rows_are_no_longer_folded(self):
        finance = [{"item_id": "item-1", "pending_since": "2026-09-23"}]
        with patch.object(extract, "_load", side_effect=self._load_factory([], finance)), \
             patch.dict(os.environ, {"YESTERDAY_ET": "2026-09-22"}):
            taps = extract._operator_taps()
        self.assertEqual(taps, [])

    def test_counts_ride_data_json(self):
        rows = [
            {"kind": "ticket_proposed", "ref": "a", "pending_since": "2026-09-01", "action": "Decide"},
            {"kind": "ticket_proposed", "ref": "b", "pending_since": "2026-09-23", "action": "Decide"},
        ]
        with patch.object(extract, "_load", side_effect=self._load_factory(rows)), \
             patch.dict(os.environ, {"YESTERDAY_ET": "2026-09-22"}):
            taps = extract._operator_taps()
            counts = extract._tap_counts(taps)
        self.assertEqual(counts, {"operator_taps_total": 2, "operator_taps_new": 1})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_extract_taps -v`
Expected: FAIL — `test_finance_relink_rows_are_no_longer_folded` sees a `plaid_relink` tap; `test_counts_ride_data_json` errors with `AttributeError: module 'scripts.extract' has no attribute '_tap_counts'`; `is_new` KeyErrors.

- [ ] **Step 3: Implement**

In `scripts/extract.py`, replace the whole `_operator_taps` function with:

```python
def _operator_taps() -> list[dict]:
    """Fold the operator tap queue (quiet-mode design, data-platform
    session/2026-07-24-benefit-mode-study.md; mirror-only since 2026-09-23,
    spec docs/specs/2026-09-23-routine-reevaluation-spec.md §2.1).

    Source is the single Stage 0.5 llm_db tap query (drafts + proposed /
    research_complete tickets, already filtered to never-surfaced objects via
    NOT EXISTS on decision_surfacings). The finance relink read is retired —
    money re-auth is owned by the Sunday harvest push + the app's
    plaid_harvest cards (ADR 0015/0019). An absent file degrades to an empty
    queue.

    Emits [{kind, ref, pending_since, action, is_new}] sorted oldest-first.
    is_new = pending_since >= YESTERDAY_ET (the run's anchor): the tap
    appeared since the previous briefing. A missing anchor mutes every tap
    (False) — the briefing must never nag by accident."""
    yesterday = os.environ.get("YESTERDAY_ET") or ""
    taps: list[dict] = []
    llm_rows = (_load("/tmp/operator_taps_llm.json", {}) or {}).get("data") or []
    for row in llm_rows:
        since = str(row.get("pending_since") or "")
        taps.append({
            "kind": row.get("kind"),
            "ref": row.get("ref"),
            "pending_since": row.get("pending_since"),
            "action": row.get("action"),
            "is_new": bool(yesterday) and bool(since) and since >= yesterday,
        })
    taps.sort(key=lambda t: str(t.get("pending_since") or ""))
    return taps


def _tap_counts(taps: list[dict]) -> dict:
    return {
        "operator_taps_total": len(taps),
        "operator_taps_new": sum(1 for t in taps if t.get("is_new")),
    }
```

In `main()`, replace

```python
        # operator tap queue — pending one-tap actions (quiet-mode design 2026-07-24)
        "operator_taps": _operator_taps(),
    }
```

with

```python
        # operator tap queue — mirror only (spec 2026-09-23 §2.1): new taps ride
        # the last priority rank; the app/digest own the standing queue
        "operator_taps": taps,
        **_tap_counts(taps),
    }
```

and add `taps = _operator_taps()` as the first line after `skill = _skill_fields(_load("/tmp/skill.json", {}))`.

In the module docstring, delete the line `  /tmp/weekly_trend.json        raw_sql latest weekly_trend run (optional)` and add, after the `/tmp/active_goal_memory.json` line:

```
  /tmp/operator_taps_llm.json   raw_sql never-surfaced drafts + ticket decisions (optional)
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_extract_taps -v && python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: 4 tests `ok`; suite `OK`.

- [ ] **Step 5: Commit**

```bash
git add scripts/extract.py tests/test_extract_taps.py
git commit -m "feat(extract): taps carry is_new + counts; finance relink read retired (spec §2.1, §2.5)"
```

---

### Task 3: Validator — server hero limits, career terms, block-length warnings

**Files:**
- Modify: `scripts/validate_payloads.py` (constants lines 19–34; `CAREER_SEARCH_TERMS` lines ~126–139; hero block lines ~656–676; schedule-block loop lines ~722–735)
- Create: `tests/test_validator_server_limits.py`

**Interfaces:**
- Produces: `validate_briefing(path, errors, warnings)` now fails on the server limits and warns on long block copy. Runbook rule 6 (Task 5) cites the same numbers.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_validator_server_limits.py`:

```python
import json
import tempfile
import unittest

from scripts import validate_payloads


def _valid_payload() -> dict:
    return {
        "date": "2026-09-24",
        "goal_context": {"career_search_closed": True},
        "hero": {
            "headline": "Log the 15-min drill rep",
            "reason": "Drill rep opens at 7 PM; 0/15 min so far.",
            "urgency": "today",
            "secondary": "Floor is 15 min",
            "action_type": "learning",
            "avoid": "youtube.com",
            "target": {"label": "Dojo rep: 15-min no-AI drill", "source": "program"},
            "success_condition": "15+ core_coding minutes logged.",
            "source_action_rank": 1,
            "evidence": [{"source": "program", "signal": "Drill rep open — 0/15 min"}],
        },
        "priority_actions": [
            {"rank": 1, "action": "Do the 7 PM drill rep: 15 hands-on minutes.",
             "source": "program", "urgency": "today", "context": "Program anchor slot."},
        ],
        "schedule_blocks": [
            {"time_range": "7:00 AM - 9:00 AM", "activity": "Wake, breakfast", "category": "meal", "device": "none", "rationale": "Ease in."},
            {"time_range": "9:00 AM - 12:00 PM", "activity": "Employer workday (employer device)", "category": "admin", "device": "none", "rationale": "Day job on the untracked device."},
            {"time_range": "12:00 PM - 1:00 PM", "activity": "Lunch", "category": "meal", "device": "none", "rationale": "Protein-anchored meal."},
            {"time_range": "1:00 PM - 5:00 PM", "activity": "Employer workday (employer device)", "category": "admin", "device": "none", "rationale": "Day job continues."},
            {"time_range": "5:00 PM - 7:00 PM", "activity": "Gym + dinner", "category": "gym", "device": "none", "rationale": "Hold lift loads."},
            {"time_range": "7:00 PM - 8:00 PM", "activity": "Dojo rep: 15-min drill", "category": "project", "device": "macbook", "rationale": "Program anchor slot."},
        ],
        "morning_brief": {},
        "risk_flags": [],
        "health_summary": {},
        "focus_yesterday": {},
        "device_strategy": {},
        "sources_used": [],
    }


class ServerLimitTests(unittest.TestCase):
    def _run(self, payload):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        with tmp:
            json.dump(payload, tmp)
        errors, warnings = [], []
        validate_payloads.validate_briefing(tmp.name, errors, warnings)
        return errors, warnings

    def test_valid_payload_passes_with_day_job_wording(self):
        errors, _ = self._run(_valid_payload())
        self.assertEqual([], errors)

    def test_target_label_over_80_chars_is_rejected(self):
        p = _valid_payload(); p["hero"]["target"]["label"] = "x" * 81
        errors, _ = self._run(p)
        self.assertTrue(any("hero.target.label exceeds 80" in e for e in errors), errors)

    def test_target_label_of_80_chars_is_accepted(self):
        p = _valid_payload(); p["hero"]["target"]["label"] = "x" * 80
        errors, _ = self._run(p)
        self.assertEqual([], errors)

    def test_target_source_over_40_chars_is_rejected(self):
        p = _valid_payload(); p["hero"]["target"]["source"] = "s" * 41
        errors, _ = self._run(p)
        self.assertTrue(any("hero.target.source exceeds 40" in e for e in errors), errors)

    def test_more_than_three_evidence_items_is_rejected(self):
        p = _valid_payload()
        p["hero"]["evidence"] = [{"source": "program", "signal": f"s{i}"} for i in range(4)]
        errors, _ = self._run(p)
        self.assertTrue(any("hero.evidence has 4 items" in e for e in errors), errors)

    def test_success_condition_over_140_chars_is_rejected(self):
        p = _valid_payload(); p["hero"]["success_condition"] = "y" * 141
        errors, _ = self._run(p)
        self.assertTrue(any("hero.success_condition exceeds 140" in e for e in errors), errors)

    def test_job_board_still_reads_as_career_search(self):
        p = _valid_payload()
        p["schedule_blocks"][1]["activity"] = "Browse the job board"
        errors, _ = self._run(p)
        self.assertTrue(any("turns closed career search into scheduled work" in e for e in errors), errors)

    def test_long_block_copy_warns_not_fails(self):
        p = _valid_payload()
        p["schedule_blocks"][5]["activity"] = "a" * 61
        p["schedule_blocks"][5]["rationale"] = "r" * 141
        errors, warnings = self._run(p)
        self.assertEqual([], errors)
        self.assertTrue(any("schedule_blocks[6].activity is 61 chars" in w for w in warnings), warnings)
        self.assertTrue(any("schedule_blocks[6].rationale is 141 chars" in w for w in warnings), warnings)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_validator_server_limits -v`
Expected: the four limit tests and `test_long_block_copy_warns_not_fails` FAIL (no limit / no warning yet); `test_valid_payload_passes_with_day_job_wording`, `test_job_board_still_reads_as_career_search` and `test_target_label_of_80_chars_is_accepted` already pass.

- [ ] **Step 3: Implement**

In `scripts/validate_payloads.py`, after `HERO_SECONDARY_MAX_WORDS = 8` add:

```python
# Server-side limits (data-platform shared/hero_surface_contract.py) — the
# server REJECTS the whole daily_briefing write when any of these is exceeded
# (2026-09-23: the routine's label passed locally and was rejected remotely).
HERO_TARGET_LABEL_MAX_CHARS = 80
HERO_TARGET_SOURCE_MAX_CHARS = 40
HERO_EVIDENCE_MAX_ITEMS = 3
HERO_SUCCESS_CONDITION_MAX_CHARS = 140
# Card copy: schedule_blocks feed the digest "Now/Next" card (title = activity,
# body = time_range · category · rationale) and the block Live Activities.
SCHEDULE_BLOCK_ACTIVITY_MAX_CHARS = 60
SCHEDULE_BLOCK_RATIONALE_MAX_CHARS = 140
```

Replace `CAREER_SEARCH_TERMS` with:

```python
CAREER_SEARCH_TERMS = {
    "application",
    "applications",
    "apply",
    "interview",
    "job application",
    "job board",
    "job hunt",
    "job posting",
    "job search",
    "job-search",
    "outbound",
    "outreach",
    "recruiter",
}
# NOTE (2026-09-23): the bare words "job"/"jobs" and "genuine" left this set —
# "day job" / "employer workday" are the operator's confirmed schedule, not
# job-search copy, and "genuine" only ever matched the preserved Stage 0
# career headline.
```

In the hero block, replace

```python
        evidence = hero.get("evidence")
        if "evidence" in hero and not isinstance(evidence, list):
            _fail(errors, "daily_briefing.hero.evidence must be a list")
        elif isinstance(evidence, list):
            for index, item in enumerate(evidence, start=1):
```

with

```python
        evidence = hero.get("evidence")
        if "evidence" in hero and not isinstance(evidence, list):
            _fail(errors, "daily_briefing.hero.evidence must be a list")
        elif isinstance(evidence, list):
            if len(evidence) > HERO_EVIDENCE_MAX_ITEMS:
                _fail(errors, f"daily_briefing.hero.evidence has {len(evidence)} items (> {HERO_EVIDENCE_MAX_ITEMS}, server limit)")
            for index, item in enumerate(evidence, start=1):
```

and replace

```python
        else:
            for key in ("label", "source"):
                if not target.get(key):
                    _fail(errors, f"daily_briefing.hero.target.{key} is required")
```

with

```python
        else:
            for key in ("label", "source"):
                if not target.get(key):
                    _fail(errors, f"daily_briefing.hero.target.{key} is required")
            label = target.get("label")
            if isinstance(label, str) and len(label.strip()) > HERO_TARGET_LABEL_MAX_CHARS:
                _fail(errors, f"daily_briefing.hero.target.label exceeds {HERO_TARGET_LABEL_MAX_CHARS} chars (server limit)")
            target_source = target.get("source")
            if isinstance(target_source, str) and len(target_source.strip()) > HERO_TARGET_SOURCE_MAX_CHARS:
                _fail(errors, f"daily_briefing.hero.target.source exceeds {HERO_TARGET_SOURCE_MAX_CHARS} chars (server limit)")
        success_condition = hero.get("success_condition")
        if isinstance(success_condition, str) and len(success_condition.strip()) > HERO_SUCCESS_CONDITION_MAX_CHARS:
            _fail(errors, f"daily_briefing.hero.success_condition exceeds {HERO_SUCCESS_CONDITION_MAX_CHARS} chars (server limit)")
```

In the schedule-block loop, after

```python
            if category not in CANONICAL_SCHEDULE_CATEGORIES:
                _fail(errors, f"schedule_blocks[{index}].category is not canonical: {category!r}")
```

add

```python
            activity = str(block.get("activity") or "").strip()
            if len(activity) > SCHEDULE_BLOCK_ACTIVITY_MAX_CHARS:
                warnings.append(
                    f"schedule_blocks[{index}].activity is {len(activity)} chars "
                    f"(> {SCHEDULE_BLOCK_ACTIVITY_MAX_CHARS}) — it is the Now/Next card title and the Live Activity label"
                )
            rationale = str(block.get("rationale") or "").strip()
            if len(rationale) > SCHEDULE_BLOCK_RATIONALE_MAX_CHARS:
                warnings.append(
                    f"schedule_blocks[{index}].rationale is {len(rationale)} chars "
                    f"(> {SCHEDULE_BLOCK_RATIONALE_MAX_CHARS}) — it is the Now/Next card body"
                )
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_validator_server_limits -v && python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: 8 tests `ok`; suite `OK`. If `tests/test_goal_context_and_validation.py::test_closed_career_rejects_hero_and_actions` fails, its fixture relied on the bare word `job` — read the fixture and change the offending text to "job search" (the intent of that test is unchanged).

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_payloads.py tests/test_validator_server_limits.py tests/test_goal_context_and_validation.py
git commit -m "fix(validator): mirror the server hero limits, drop bare 'job' from career terms, warn on long block copy (spec §2.2)"
```

---

### Task 4: `calendar_plan.py` — a deliberate busy-search skip is `ok`

**Files:**
- Modify: `scripts/calendar_plan.py` (summary dict in `build_plan`, lines ~163–176)
- Create: `tests/test_calendar_plan.py`

**Interfaces:**
- Produces: `summary["status"] == "ok"` and `summary["busy_source"] == "skipped_for_token_budget"` when `/tmp/calendar_busy.json.status == "skipped_for_token_budget"`; `main()` exits 0. A real failure (`status` anything else but `ok`) keeps `busy_source_failed` / exit 1.

- [ ] **Step 1: Write the failing test**

Create `tests/test_calendar_plan.py`:

```python
import argparse
import json
import tempfile
import unittest
from pathlib import Path

from scripts import calendar_plan

BRIEFING = {
    "date": "2026-09-24",
    "schedule_blocks": [
        {"time_range": "7:00 PM - 8:00 PM", "activity": "Dojo rep", "category": "project"},
        {"time_range": "8:00 PM - 9:00 PM", "activity": "Wind down", "category": "wind_down"},
    ],
}


def _args(tmp: Path, busy: dict) -> argparse.Namespace:
    (tmp / "briefing.json").write_text(json.dumps(BRIEFING))
    (tmp / "busy.json").write_text(json.dumps(busy))
    return argparse.Namespace(
        briefing=str(tmp / "briefing.json"), busy=str(tmp / "busy.json"),
        calendar_id="cal@group.calendar.google.com", timezone="America/Toronto",
        date=None, start_hour=7, end_hour=22, publish_categories=None,
        skip_started=False, now=None,
    )


class CalendarPlanStatusTests(unittest.TestCase):
    def test_token_budget_skip_is_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _, summary, _ = calendar_plan.build_plan(_args(Path(d), {
                "status": "skipped_for_token_budget", "busy_windows": [], "busy_window_count": 0}))
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["busy_source"], "skipped_for_token_budget")
        self.assertEqual(summary["candidate_count"], 2)

    def test_real_busy_failure_still_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _, summary, _ = calendar_plan.build_plan(_args(Path(d), {"status": "error", "busy_windows": []}))
        self.assertEqual(summary["status"], "busy_source_failed")
        self.assertEqual(summary["busy_source"], "failed")

    def test_search_ok_keeps_search_source(self):
        with tempfile.TemporaryDirectory() as d:
            _, summary, _ = calendar_plan.build_plan(_args(Path(d), {"status": "ok", "busy_windows": []}))
        self.assertEqual((summary["status"], summary["busy_source"]), ("ok", "search"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_calendar_plan -v`
Expected: `test_token_budget_skip_is_ok` FAILS (`'busy_source_failed' != 'ok'`); the other two pass.

- [ ] **Step 3: Implement**

In `scripts/calendar_plan.py` replace

```python
    summary = {
        "status": "ok" if busy.get("status") == "ok" else "busy_source_failed",
        "calendar_id": calendar_id,
        "time_min": horizon_start.isoformat(),
        "time_max": horizon_end.isoformat(),
        "busy_source": busy.get("busy_source") or ("search" if busy.get("status") == "ok" else "failed"),
```

with

```python
    busy_status = busy.get("status")
    # A manifest-only run SKIPS the busy search on purpose (the scheduled
    # routine's Calendar Policy) — that is a valid plan, not a failure
    # (2026-09-23: it exited 1 every morning and the runner had to explain it).
    if busy_status == "ok":
        status, busy_source = "ok", busy.get("busy_source") or "search"
    elif busy_status == "skipped_for_token_budget":
        status, busy_source = "ok", "skipped_for_token_budget"
    else:
        status, busy_source = "busy_source_failed", busy.get("busy_source") or "failed"
    summary = {
        "status": status,
        "calendar_id": calendar_id,
        "time_min": horizon_start.isoformat(),
        "time_max": horizon_end.isoformat(),
        "busy_source": busy_source,
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_calendar_plan -v && python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: 3 `ok`; suite `OK` (`test_validator_rejects_failed_calendar_status_when_busy_stub_was_skipped` still passes — it tests the validator, which still rejects a `failed` manifest).

- [ ] **Step 5: Commit**

```bash
git add scripts/calendar_plan.py tests/test_calendar_plan.py
git commit -m "fix(calendar_plan): a deliberate busy-search skip is a valid plan, exit 0 (spec §2.3)"
```

---

### Task 5: `morning-briefing.md` — 14 reads, mirror-only taps, card-copy caps

**Files:**
- Modify: `morning-briefing.md` (Stage 0.5 block lines ~210–245; Stage 0.5b paragraph ~264–267; rule 6 ~430–436; rule 15 ~511–524; §3d format ~544–575; `## Signoff`)
- Test: `tests/test_runbook_contract.py`

**Interfaces:**
- Consumes: `operator_taps[].is_new`, `operator_taps_new` (Task 2); validator limits (Task 3).

- [ ] **Step 1: Write the failing tests**

Append to `class RunbookContractTests` in `tests/test_runbook_contract.py`:

```python
    def test_stage_zero_five_has_fourteen_reads_and_no_dead_sources(self):
        self.assertIn("All 14 calls in one bash turn", self.runbook)
        self.assertIn('echo "Stage 0.5 ok: 14 queries complete"', self.runbook)
        self.assertNotIn("weekly_trend", self.runbook)
        self.assertNotIn("operator_taps_finance", self.runbook)
        self.assertNotIn("relink_needed", self.runbook)
        self.assertIn("NOT EXISTS (SELECT 1 FROM decision_surfacings", self.runbook)

    def test_taps_are_a_mirror_at_the_last_rank(self):
        normalized = " ".join(self.runbook.split())
        self.assertIn("15. **Taps are a mirror, never the lead.**", normalized)
        self.assertIn("only taps whose `is_new` is true", normalized)
        self.assertIn("ONE combined `priority_actions` entry at the LAST rank", normalized)
        self.assertIn("never rank 1, never the headline, never a `risk_flags` entry", normalized)
        self.assertNotIn("Taps first.", normalized)

    def test_schedule_blocks_and_narrative_are_card_copy(self):
        normalized = " ".join(self.runbook.split())
        self.assertIn("`activity` ≤ 60 chars", normalized)
        self.assertIn("`rationale` ≤ 140 chars", normalized)
        self.assertIn("each section at most three lines", normalized)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_runbook_contract -v 2>&1 | grep -E 'FAIL|ok$' | head`
Expected: the three new tests FAIL; the rest `ok`.

- [ ] **Step 3: Edit Stage 0.5**

In `morning-briefing.md`, change `**All 16 calls in one bash turn with `&` + `wait`.**` to `**All 14 calls in one bash turn with `&` + `wait`.**`.

Delete this line from the parallel block:

```
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT output_response FROM llm_runs WHERE run_type = 'weekly_trend' AND created_at >= NOW() - INTERVAL '8 days' ORDER BY created_at DESC LIMIT 1\"}" /tmp/weekly_trend.json &
```

Delete the `operator_taps_finance` line:

```
scripts/mcp.sh query_raw_sql "{\"database\":\"finance_db\",\"sql\":\"SELECT item_id, updated_at::date::text AS pending_since FROM plaid_items WHERE status = 'relink_needed' AND environment <> 'sandbox'\"}" /tmp/operator_taps_finance.json &
```

Replace the `operator_taps_llm` line with (one line in the file):

```
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT 'direction_draft' AS kind, dv.id::text AS ref, dv.created_at::date::text AS pending_since, 'Approve or reject direction draft (python -m agent.direction_admin approve <id> --confirm in the context-api pod)' AS action FROM direction_versions dv WHERE dv.status = 'draft' AND NOT EXISTS (SELECT 1 FROM decision_surfacings d WHERE d.object_id = dv.id::text) UNION ALL SELECT 'goal_policy_draft', gp.id::text, gp.created_at::date::text, 'Approve or reject goal-policy draft (python -m agent.goal_policy_admin in the context-api pod)' FROM goal_policy_versions gp WHERE gp.status = 'draft' AND NOT EXISTS (SELECT 1 FROM decision_surfacings d WHERE d.object_id = gp.id::text) UNION ALL SELECT 'ticket_' || t.status, t.id::text, t.created_at::date::text, 'Decide in the Winter app Decisions sheet (or the decision-digest email links)' FROM delegation_tickets t WHERE t.status IN ('proposed','research_complete') AND NOT EXISTS (SELECT 1 FROM decision_surfacings d WHERE d.object_id = t.id::text) ORDER BY 3\"}" /tmp/operator_taps_llm.json &
```

Change `echo "Stage 0.5 ok: 16 queries complete"` to `echo "Stage 0.5 ok: 14 queries complete"`.

In the Stage 0.5b paragraph, change `empty workout rows, no weekly_trend row yet, etc.)` to `empty workout rows, no tap rows, etc.)`.

- [ ] **Step 4: Edit rule 6, rule 15, and §3d**

Rule 6 — after the sentence `Blocks must not overlap `/tmp/calendar_busy.json.busy_windows`.` append (same list item):

```
   Blocks are **card copy**: `activity` ≤ 60 chars (it is the digest's
   "Now/Next" card title and the Live Activity label) and `rationale` ≤ 140
   chars (the card body prints `time_range · category · rationale`). One
   `admin` block per employer-workday half is fine; do not split further.
   The validator warns past these lengths.
```

Rule 15 — replace the whole item 15 (from `15. **Taps first.**` to `…the one-line consequence, nothing more.`) with:

```
15. **Taps are a mirror, never the lead.** `/tmp/data.json.operator_taps` is
    the operator tap queue filtered to objects no channel has surfaced yet
    (the Stage 0.5 query carries `NOT EXISTS` on `decision_surfacings`); the
    app's Decisions sheet, push, and the decision-digest crons own the
    standing queue and its shelf lifecycle (ADR 0016/0019). Surface only
    taps whose `is_new` is true (`operator_taps_new` > 0): they become ONE
    combined `priority_actions` entry at the LAST rank, `urgency` `today`,
    `source: "user_profile"`, `action` starting with `Tap:` or `Approve:`,
    `context` naming each ref and its kind. Never rank 1, never the headline,
    never a `risk_flags` entry, never a schedule block. When
    `operator_taps_new` is 0 — whatever `operator_taps_total` says — emit
    nothing about taps: no count, no "pending" filler, no age. The briefing
    records no appearance; a tap mentioned here is not "surfaced" in the
    ADR 0016 sense.
```

§3d — after the format block (the fenced block ending with `<3-5 specific actions tied to the patterns above>`) add the paragraph:

```
The narrative is a mirror of `/tmp/briefing.json` for the activity feed, not
a second analysis: keep the six sections (the validator and the feed expect
them) but each section at most three lines, `ACTIONABLE ITEMS` at most three
entries, and restate the JSON's numbers rather than deriving new ones.
```

- [ ] **Step 5: Update the signoff**

Replace the `## Signoff` block of `morning-briefing.md` with:

```markdown
## Signoff

- **2026-09-23 ET · Claude (Fable 5.1, operator session)** — Spec
  `docs/specs/2026-09-23-routine-reevaluation-spec.md` Design A: Stage 0.5
  is 14 reads (retired `weekly_trend` + the finance relink tap read; the
  llm_db tap query carries `NOT EXISTS` on `decision_surfacings`); rule 15
  is mirror-only (new taps, last rank, never the lead); rule 6 + §3d carry
  card-copy caps; credentials paragraph → `/tmp/mcp.env` (Design E).
  Verified: suite green. (Latest entry only — history in git.)
```

- [ ] **Step 6: Run the tests**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add morning-briefing.md tests/test_runbook_contract.py
git commit -m "feat(morning-briefing): 14 reads, mirror-only taps at the last rank, card-copy caps (spec Design A)"
```

---

### Task 6: `program-review.md` — freshness line, ticket counts, Stage 1.6 channel, shelf line

**Files:**
- Modify: `program-review.md` (Stage 0 block lines ~20–47; Stage 1.6 lines ~109–124; Stage 2.5 intro + item 4 lines ~159–188; Stages 2.7/2.8 lines ~224–278; Definition of done ~315–325; `## Signoff`)
- Create: `tests/test_program_review_contract.py`

**Interfaces:**
- Produces: the memory key contract `job_artifact_<YYYY-MM-DD of the week's Monday>` (category `fact`) that the operator writes; consumed by Stage 1.6.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_program_review_contract.py`:

```python
import unittest
from pathlib import Path


class ProgramReviewContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runbook = Path("program-review.md").read_text()
        cls.normalized = " ".join(cls.runbook.split())

    def test_rollup_freshness_line_after_stage_zero(self):
        self.assertIn("## Stage 0.5 — Rollup freshness line", self.runbook)
        self.assertIn("older than 24 h", self.normalized)
        self.assertIn("WARN: newest rollup is", self.runbook)

    def test_tickets_are_counted_by_live_status(self):
        # The Stage 0 SQL sits inside a single-quoted JSON arg, so literals are
        # written '"'"'x'"'"' — flatten that shell quoting before matching.
        flat = self.runbook.replace("'\"'\"'", "'")
        self.assertIn("('proposed','research_ready','research_complete','blocked') GROUP BY 1", flat)
        self.assertNotIn("'accepted'", flat)
        self.assertIn("N research_complete awaiting decision", self.normalized)

    def test_job_artifact_memory_channel(self):
        self.assertIn("job_artifact_%", self.runbook)
        self.assertIn("`job_artifact_<week_start>`", self.runbook)
        self.assertIn("category `fact`", self.normalized)
        self.assertIn("clock started", self.normalized)

    def test_reviewers_are_weekly_not_retired(self):
        self.assertNotIn("retired from the metered API", self.runbook)
        self.assertIn("run weekly (Mon/Wed/Fri, ADR 0009)", self.normalized)

    def test_shelf_line_from_the_scorecard(self):
        self.assertIn("input_payload.funnel.shelved", self.runbook)
        self.assertIn("Shelved decisions:", self.runbook)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_program_review_contract -v`
Expected: all 5 FAIL.

- [ ] **Step 3: Edit Stage 0 (two reads)**

In the Stage 0 parallel block, replace the `gov_tickets` line with these two lines:

```
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT status, count(*) AS n FROM delegation_tickets WHERE status IN ('"'"'proposed'"'"','"'"'research_ready'"'"','"'"'research_complete'"'"','"'"'blocked'"'"') GROUP BY 1 ORDER BY 1"}' /tmp/gov_tickets.json &
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT slug, created_at::date AS day FROM delegation_tickets WHERE status = '"'"'proposed'"'"' ORDER BY created_at DESC LIMIT 5"}' /tmp/gov_tickets_proposed.json &
```

and add, before `wait`:

```
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT key, content, created_at::date AS day FROM agent_memory WHERE key LIKE '"'"'job_artifact_%'"'"' AND created_at > NOW() - INTERVAL '"'"'35 days'"'"' ORDER BY created_at DESC"}' /tmp/job_artifact.json &
```

Change the sentence `The six `/tmp/gov_*.json` reads feed Stage 2.5` to `The seven `/tmp/gov_*.json` reads feed Stage 2.5`.

- [ ] **Step 4: Insert Stage 0.5 (freshness line) after the Stage 0 section**

Insert before `## Stage 0.9 — Direction re-read`:

```markdown
## Stage 0.5 — Rollup freshness line (deterministic)

The kill gate reads `rep_weeks[0]`; on the scheduled Sunday 21:15 ET run that
row was computed at 20:35 the same evening. Check the age once:

```bash
age_h=$(python3 -c 'import json,sys;from datetime import datetime,timezone;r=json.load(open("/tmp/rep_weeks.json"))["data"][0];print(round((datetime.now(timezone.utc)-datetime.fromisoformat(r["computed_at"].replace("Z","+00:00"))).total_seconds()/3600,1))' 2>/dev/null || echo "?")
echo "rollup age: ${age_h}h (week_start $(jq -r '.data[0].week_start' /tmp/rep_weeks.json))"
```

If the age is older than 24 h, print
`WARN: newest rollup is <age>h old (week_start <date>) — expected <24h on a
21:15 Sunday run` and copy that line verbatim into the review notes; then
continue (the gate reads what it has). The line makes a mis-scheduled run
visible in its own artifact — the 2026-08..09 reviews ran at 04:00 ET and
silently read the previous week for two months.
```

(The `rep_weeks` Stage 0 query must select `computed_at` — change its SQL to `SELECT week_start, floors_met, bar, green, rollup, computed_at FROM rep_weeks ORDER BY week_start DESC LIMIT 8`.)

- [ ] **Step 5: Rewrite Stage 1.6's input paragraph (decision text unchanged)**

Replace only the paragraph

```
> "What was the week's hardest job artifact?" (one line)

Record the answer (or its absence) in the review notes.
```

with

```
> "What was the week's hardest job artifact?" (one line)

**Input channel (2026-09-23):** the operator answers during the week by
saving ONE `agent_memory` row — key `job_artifact_<week_start>` where
`<week_start>` is the ISO date of that week's Monday (e.g.
`job_artifact_2026-09-21`), category `fact`, content = the one line — from
any Claude session via the MCP `save_memory` tool, or as a one-line Info-Me
note the vault routine mirrors. Stage 0 reads `/tmp/job_artifact.json`
(keys like `job_artifact_%`, last 35 days). Quote the row for the week just
ended verbatim in the review notes (`Job artifact: <content>`); absence is
a recorded non-answer (`Job artifact: no job_artifact_<week_start> row`).
The consecutive-non-answer count starts from the first review after this
channel shipped — state `clock started 2026-09-27` in the notes until a
real answer lands, then count from there.
```

Everything after that paragraph in Stage 1.6 (`**Three to four consecutive weeks…`) stays byte-identical.

- [ ] **Step 6: Edit Stage 2.5 intro + item 4**

Replace the Stage 2.5 intro paragraph (`Since 2026-07-02 the platform's three Gemini Flash-Lite daily review agents … interpretation of the week's governance evidence, not re-detection.**`) with:

```
The platform's three Gemini review agents (`data_quality_review`,
`llm_contract_review`, `llm_agent_evaluation`) run weekly (Mon/Wed/Fri,
ADR 0009) and watch the platform for the platform; this stage is the
operator-facing reading of the same week — detection stays deterministic
(stewards + Prometheus pagers), this is **interpretation of the week's
governance evidence, not re-detection.**
```

Replace item 4 (`Tickets needing the operator (`gov_tickets`): proposed/accepted by slug, or "none open".`) with:

```
4. Tickets by live status (`gov_tickets`): "tickets: N proposed / N
   research_complete awaiting decision / N research_ready / N blocked", plus
   the ≤5 newest `proposed` slugs from `gov_tickets_proposed`; "no open
   tickets" when every count is 0.
```

Also change the section heading `## Stage 2.5 — Platform governance (weekly; absorbs the retired Gemini daily reviews)` to `## Stage 2.5 — Platform governance (weekly operator-facing reading)`.

- [ ] **Step 7: Edit Stages 2.7 and 2.8**

In Stage 2.7, after `Graceful skip (exactly one line) when: no sweep row exists this week, …` add the sentence: `On a 21:15 ET Sunday run the 05:37 sweep row exists; a skip here is a real absence — say so.`

In Stage 2.8, replace item 3's opening `3. The `shadow_asks_7d` block` paragraph's preceding list with the same list plus a new item:

```
4. Quote the shelved-decision count from the scorecard row's
   `input_payload.funnel.shelved` as one line: `Shelved decisions: N` (the
   glossary promises this review carries it). On a 21:15 ET run the 09:07
   scorecard row exists; a skip here is a real absence — say so.
```

- [ ] **Step 8: Definition of done + signoff**

In `## Definition of done`, after the bullet ending `**and the Stage 2.6 `Steering efficacy:` line**.` add:

```
- The Stage 0.5 rollup-age line (and its WARN when > 24 h), the Stage 1.6
  `Job artifact:` line, and the Stage 2.8 `Shelved decisions:` line.
```

Replace `## Signoff` with:

```markdown
## Signoff

2026-09-23 ET · operator session — spec Design B: Stage 0.5 rollup-freshness
line; tickets counted by live status; Stage 1.6 gains the `job_artifact_`
memory channel (decision text unchanged); Stage 2.5 intro corrected (the
reviewers run weekly); Stage 2.8 quotes the shelved count. Trigger moves to
Sunday 21:15 ET in the same session. (History in git.)
```

- [ ] **Step 9: Run the tests and commit**

Run: `python3 -m unittest tests.test_program_review_contract -v && python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: 5 `ok`; suite `OK`.

```bash
git add program-review.md tests/test_program_review_contract.py
git commit -m "feat(program-review): rollup freshness line, live ticket counts, job_artifact memory channel, shelf line (spec Design B)"
```

---

### Task 7: `scripts/learner_evidence.py` — the deterministic evidence packet

**Files:**
- Create: `scripts/learner_evidence.py`
- Create: `tests/test_learner_evidence.py`

**Interfaces:**
- Consumes the Stage 1 envelopes written by Task 8's runbook (`{"status": "ok", "data": [...]}` files):
  `/tmp/program_versions.json` rows `{id, status, source, valid_from, valid_until, has_operator_input: bool, recompose_count}`;
  `/tmp/rep_weeks.json` rows `{week_start, floors_met, bar, green, rollup: {consecutive_non_green, auto_weeks_no_operator_input, ...}}` newest first;
  `/tmp/rep_days.json` rows `{day, family, floor_met, floor_minutes, artifact, travel_excused}`;
  `/tmp/steering.json` rows `{issued_at, action, final_outcome, delivery_tag}`;
  `/tmp/health_daily.json` rows `{metric_date, metric_type, value}` for `sleep_seconds`/`hrv_ms`/`steps`;
  `/tmp/workouts.json` rows `{day}`;
  `/tmp/skill.json` = `get_skill_summary` envelope (`.window.core_coding_min`, `.window.ai_assisted_coding_min`, `.window.hands_on_share`, `.streak.core_coding_days`);
  `/tmp/remarks.json` rows `{key, created_at, content}`;
  `/tmp/direction.json` = `get_direction` envelope (`.direction.version`, `.direction.domains.skill.current_phase`);
  `/tmp/program_reviews.json` rows `{created_at, head}`.
- Produces: `/tmp/evidence.json` exactly as spec §4.3; `build_evidence(window_start, window_end, loader) -> dict` for tests; exit code always 0 unless the output cannot be written.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_learner_evidence.py`:

```python
import unittest

from scripts import learner_evidence as le


def _env(rows):
    return {"status": "ok", "data": rows}


FULL = {
    "/tmp/program_versions.json": _env([
        {"id": "p1", "status": "active", "source": "claude_program_review", "valid_from": "2026-08-31",
         "valid_until": "2026-09-06", "has_operator_input": False, "recompose_count": 0},
        {"id": "p0", "status": "active", "source": "operator_recalibration", "valid_from": "2026-07-22",
         "valid_until": "2026-07-27", "has_operator_input": True, "recompose_count": 1},
    ]),
    "/tmp/rep_weeks.json": _env([
        {"week_start": "2026-09-14", "floors_met": 0, "bar": 2, "green": False,
         "rollup": {"consecutive_non_green": 1, "auto_weeks_no_operator_input": 9}},
        {"week_start": "2026-09-07", "floors_met": 2, "bar": 2, "green": True,
         "rollup": {"consecutive_non_green": 0, "auto_weeks_no_operator_input": 8}},
        {"week_start": "2026-08-31", "floors_met": 0, "bar": 2, "green": False,
         "rollup": {"consecutive_non_green": 5, "auto_weeks_no_operator_input": 8}},
        {"week_start": "2026-08-24", "floors_met": 0, "bar": 2, "green": False,
         "rollup": {"consecutive_non_green": 4, "auto_weeks_no_operator_input": 8}},
    ]),
    "/tmp/rep_days.json": _env([
        {"day": "2026-09-09", "family": "drill", "floor_met": True, "floor_minutes": 20, "artifact": True, "travel_excused": False},
        {"day": "2026-09-10", "family": "drill", "floor_met": True, "floor_minutes": 15, "artifact": False, "travel_excused": False},
        {"day": "2026-09-12", "family": "milestone", "floor_met": False, "floor_minutes": 0, "artifact": False, "travel_excused": True},
        {"day": "2026-09-16", "family": "drill", "floor_met": False, "floor_minutes": 0, "artifact": False, "travel_excused": False},
    ]),
    "/tmp/steering.json": _env([
        {"issued_at": "2026-09-10T23:10:00+00:00", "action": "WARN_LOCAL", "final_outcome": "reduced", "delivery_tag": "delivered"},
        {"issued_at": "2026-09-11T14:10:00+00:00", "action": "LOCK_WINDOWS", "final_outcome": "backfired", "delivery_tag": "undelivered"},
    ]),
    "/tmp/health_daily.json": _env([
        {"metric_date": "2026-09-09", "metric_type": "sleep_seconds", "value": 7.5 * 3600},
        {"metric_date": "2026-09-10", "metric_type": "sleep_seconds", "value": 6.0 * 3600},
        {"metric_date": "2026-09-16", "metric_type": "sleep_seconds", "value": 6.0 * 3600},
        {"metric_date": "2026-09-09", "metric_type": "hrv_ms", "value": 50},
    ]),
    "/tmp/workouts.json": _env([{"day": "2026-09-09"}, {"day": "2026-09-16"}]),
    "/tmp/skill.json": {"status": "ok", "window": {"days": 90, "core_coding_min": 35, "ai_assisted_coding_min": 900, "hands_on_share": 0.037},
                        "streak": {"core_coding_days": 0}},
    "/tmp/remarks.json": _env([{"key": "operator_context_2026_07_job_engrossed", "created_at": "2026-07-22", "content": "x" * 300}]),
    "/tmp/direction.json": {"status": "ok", "direction": {"version": 3, "domains": {"skill": {"current_phase": "settled-job skill season"}}}},
    "/tmp/program_reviews.json": _env([
        {"created_at": "2026-09-13T08:12:00+00:00", "head": "KILL-GATE STOPPED — no program written"},
        {"created_at": "2026-09-20T08:14:00+00:00", "head": "Weekly program review — week of 2026-09-21"},
    ]),
}


class EvidencePacketTests(unittest.TestCase):
    def _build(self, files):
        return le.build_evidence("2026-06-25", "2026-09-23", loader=lambda p: files.get(p))

    def test_full_packet_values(self):
        ev = self._build(FULL)
        self.assertEqual(ev["window"], {"start": "2026-06-25", "end": "2026-09-23", "days": 90})
        self.assertEqual(ev["program"]["operator_recalibrations"], 1)
        self.assertEqual(ev["program"]["auto_versions"], 1)
        self.assertEqual(ev["program"]["kill_gate_stops"], ["2026-09-13"])
        self.assertEqual(ev["rep_weeks"]["green_rate"], 0.25)
        self.assertEqual(ev["rep_weeks"]["consecutive_non_green_now"], 1)
        self.assertEqual(ev["rep_weeks"]["auto_weeks_no_operator_input"], 9)
        fam = {r["family"]: r for r in ev["rep_days"]["by_family"]}
        self.assertEqual((fam["drill"]["slots"], fam["drill"]["floors"], fam["drill"]["artifacts"]), (3, 2, 1))
        self.assertEqual(fam["drill"]["avg_minutes"], 11.7)
        self.assertEqual(ev["rep_days"]["days_with_floor"], 2)
        self.assertEqual(ev["rep_days"]["longest_floor_streak"], 2)
        self.assertEqual(ev["rep_days"]["travel_excused_days"], 1)
        self.assertEqual(ev["steering"]["episodes"], 2)
        self.assertEqual(ev["steering"]["outcomes"]["backfired"], 1)
        self.assertEqual(ev["steering"]["by_action"]["LOCK_WINDOWS"], 1)
        self.assertEqual(ev["steering"]["delivery"]["undelivered"], 1)
        self.assertEqual(ev["steering"]["evening_share"], 0.5)  # 23:10Z = 19:10 ET
        self.assertEqual(ev["health"]["floor_rate_sleep_ge_7h"], 1.0)   # 09-09 slept 7.5h, floor met
        self.assertEqual(ev["health"]["floor_rate_sleep_lt_6_5h"], 0.5) # 09-10 met, 09-16 missed
        self.assertEqual(ev["health"]["floor_rate_workout_days"], 0.5)  # 09-09 met, 09-16 missed
        self.assertEqual(ev["health"]["floor_rate_rest_days"], 0.5)     # 09-10 met, 09-12 missed
        self.assertEqual(ev["health"]["workout_days"], 2)
        self.assertEqual(ev["skill"], {"hands_on_min": 35, "ai_assisted_min": 900, "hands_on_share": 0.037, "streak_days": 0})
        self.assertEqual(len(ev["context"]["operator_remarks"][0]["excerpt"]), 240)
        self.assertEqual(ev["context"]["direction"], {"version": 3, "skill_phase_excerpt": "settled-job skill season"})
        self.assertEqual(ev["coverage"], {"rep_weeks_in_window": 4, "sparse": False, "missing_inputs": []})

    def test_empty_inputs_degrade_to_nulls_and_missing_list(self):
        ev = self._build({})
        self.assertIsNone(ev["program"])
        self.assertIsNone(ev["health"])
        self.assertEqual(ev["coverage"]["rep_weeks_in_window"], 0)
        self.assertTrue(ev["coverage"]["sparse"])
        self.assertIn("/tmp/rep_weeks.json", ev["coverage"]["missing_inputs"])
        self.assertEqual(len(ev["coverage"]["missing_inputs"]), 10)

    def test_sparse_flag_flips_at_four_rep_weeks(self):
        three = dict(FULL); three["/tmp/rep_weeks.json"] = _env(FULL["/tmp/rep_weeks.json"]["data"][:3])
        self.assertTrue(self._build(three)["coverage"]["sparse"])
        self.assertFalse(self._build(FULL)["coverage"]["sparse"])

    def test_rates_are_null_when_denominator_is_zero(self):
        files = dict(FULL); files["/tmp/workouts.json"] = _env([])
        ev = self._build(files)
        self.assertIsNone(ev["health"]["floor_rate_workout_days"])
        self.assertEqual(ev["health"]["workout_days"], 0)

    def test_errored_envelope_counts_as_missing(self):
        files = dict(FULL); files["/tmp/steering.json"] = {"status": "error", "error": "boom"}
        ev = self._build(files)
        self.assertIsNone(ev["steering"])
        self.assertEqual(ev["coverage"]["missing_inputs"], ["/tmp/steering.json"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_learner_evidence -v`
Expected: `ImportError`/`AttributeError` — module missing.

- [ ] **Step 3: Implement `scripts/learner_evidence.py`**

```python
#!/usr/bin/env python3
"""Stage 1.2 of the monthly learner — fold the lifeOS Stage 1 reads into ONE
deterministic evidence packet, /tmp/evidence.json (spec
docs/specs/2026-09-23-routine-reevaluation-spec.md §4.3).

No LLM, no network. Every input is an MCP envelope {"status","data"} written
by the runbook's Stage 1; a missing or errored file degrades that section to
null and lists the path in coverage.missing_inputs. Health rows and rep days
live in different databases, so the correlates are joined here on the ET
date. Exit code is 0 unless the output cannot be written.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/Toronto")
SPARSE_REP_WEEKS = 4
INPUTS = [
    "/tmp/program_versions.json", "/tmp/rep_weeks.json", "/tmp/rep_days.json",
    "/tmp/steering.json", "/tmp/health_daily.json", "/tmp/workouts.json",
    "/tmp/skill.json", "/tmp/remarks.json", "/tmp/direction.json",
    "/tmp/program_reviews.json",
]
SLEEP_GOOD_H = 7.0
SLEEP_SHORT_H = 6.5


def _default_loader(path: str) -> Any:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as exc:  # unreadable = missing
        print(f"learner_evidence: could not parse {path}: {exc}", file=sys.stderr)
        return None


def _rows(payload: Any) -> list[dict] | None:
    """Rows of an ok envelope, else None (missing / error / malformed)."""
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return None
    data = payload.get("data")
    return data if isinstance(data, list) else None


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def _day(value: Any) -> str:
    return str(value or "")[:10]


def _program(rows: list[dict]) -> dict:
    versions = [{
        "id": r.get("id"), "status": r.get("status"), "source": r.get("source"),
        "valid_from": _day(r.get("valid_from")), "valid_until": _day(r.get("valid_until")),
        "operator_input": bool(r.get("has_operator_input")),
        "recompose_count": int(r.get("recompose_count") or 0),
    } for r in rows]
    recal = sum(1 for v in versions if v["source"] == "operator_recalibration" or v["operator_input"])
    return {"versions": versions, "operator_recalibrations": recal,
            "auto_versions": len(versions) - recal, "kill_gate_stops": []}


def _rep_weeks(rows: list[dict]) -> dict:
    ordered = sorted(rows, key=lambda r: _day(r.get("week_start")), reverse=True)
    newest = (ordered[0].get("rollup") or {}) if ordered else {}
    return {
        "rows": [{"week_start": _day(r.get("week_start")), "floors_met": r.get("floors_met"),
                  "bar": r.get("bar"), "green": bool(r.get("green"))} for r in ordered],
        "green_rate": _rate(sum(1 for r in ordered if r.get("green")), len(ordered)),
        "consecutive_non_green_now": newest.get("consecutive_non_green"),
        "auto_weeks_no_operator_input": newest.get("auto_weeks_no_operator_input"),
    }


def _rep_days(rows: list[dict]) -> dict:
    by_family: dict[str, dict] = defaultdict(lambda: {"slots": 0, "floors": 0, "artifacts": 0, "minutes": 0.0})
    by_weekday: dict[str, dict] = defaultdict(lambda: {"slots": 0, "floors": 0})
    floor_days: set[str] = set()
    travel = 0
    for r in rows:
        fam = str(r.get("family") or "none")
        d = _day(r.get("day"))
        f = by_family[fam]
        f["slots"] += 1
        f["minutes"] += float(r.get("floor_minutes") or 0)
        if r.get("floor_met"):
            f["floors"] += 1
            floor_days.add(d)
        if r.get("artifact"):
            f["artifacts"] += 1
        if r.get("travel_excused"):
            travel += 1
        try:
            wd = date.fromisoformat(d).strftime("%a").lower()
        except ValueError:
            wd = "?"
        by_weekday[wd]["slots"] += 1
        if r.get("floor_met"):
            by_weekday[wd]["floors"] += 1
    # longest run of consecutive calendar days with a floor met
    longest = run = 0
    prev: date | None = None
    for d in sorted(floor_days):
        cur = date.fromisoformat(d)
        run = run + 1 if prev and cur - prev == timedelta(days=1) else 1
        longest = max(longest, run)
        prev = cur
    return {
        "by_family": [{"family": k, "slots": v["slots"], "floors": v["floors"], "artifacts": v["artifacts"],
                       "avg_minutes": round(v["minutes"] / v["slots"], 1) if v["slots"] else None}
                      for k, v in sorted(by_family.items())],
        "by_weekday": [{"weekday": k, **v} for k, v in sorted(by_weekday.items())],
        "days_with_floor": len(floor_days),
        "longest_floor_streak": longest,
        "travel_excused_days": travel,
    }


def _steering(rows: list[dict]) -> dict:
    outcomes = Counter(); actions = Counter(); delivery = Counter()
    evening = 0
    for r in rows:
        outcomes[str(r.get("final_outcome") or "insufficient_data")] += 1
        actions[str(r.get("action") or "?")] += 1
        delivery[str(r.get("delivery_tag") or "undelivered")] += 1
        try:
            hour = datetime.fromisoformat(str(r["issued_at"]).replace("Z", "+00:00")).astimezone(ET).hour
            if 19 <= hour < 22:
                evening += 1
        except (KeyError, ValueError, TypeError):
            pass
    return {
        "episodes": len(rows),
        "outcomes": {k: outcomes.get(k, 0) for k in ("reduced", "held", "backfired", "insufficient_data")},
        "by_action": {k: actions.get(k, 0) for k in ("WARN_LOCAL", "LOCK_WINDOWS")},
        "delivery": {k: delivery.get(k, 0) for k in ("enforced", "delivered", "delivered_not_enforced", "undelivered")},
        "evening_share": _rate(evening, len(rows)),
    }


def _health(health_rows: list[dict], workout_rows: list[dict] | None, rep_rows: list[dict] | None,
            window_end: str) -> dict:
    sleep_h: dict[str, float] = {}
    hrv: dict[str, float] = {}
    for r in health_rows:
        d = _day(r.get("metric_date"))
        if r.get("metric_type") == "sleep_seconds" and r.get("value") is not None:
            sleep_h[d] = float(r["value"]) / 3600.0
        elif r.get("metric_type") == "hrv_ms" and r.get("value") is not None:
            hrv[d] = float(r["value"])
    end = date.fromisoformat(window_end)
    cut30 = (end - timedelta(days=30)).isoformat()
    s30 = [v for d, v in sleep_h.items() if d >= cut30]
    h30 = [v for d, v in hrv.items() if d >= cut30]
    workout_days = {_day(r.get("day")) for r in (workout_rows or []) if r.get("day")}
    floor_by_day = {_day(r.get("day")): bool(r.get("floor_met")) for r in (rep_rows or [])}

    def rate(pred: Callable[[str], bool]) -> float | None:
        picked = [met for d, met in floor_by_day.items() if pred(d)]
        return _rate(sum(1 for m in picked if m), len(picked))

    return {
        "sleep_avg_h_30d": round(sum(s30) / len(s30), 2) if s30 else None,
        "sleep_avg_h_90d": round(sum(sleep_h.values()) / len(sleep_h), 2) if sleep_h else None,
        "hrv_avg_30d": round(sum(h30) / len(h30), 1) if h30 else None,
        "workout_days": len(workout_days),
        "floor_rate_sleep_ge_7h": rate(lambda d: d in sleep_h and sleep_h[d] >= SLEEP_GOOD_H),
        "floor_rate_sleep_lt_6_5h": rate(lambda d: d in sleep_h and sleep_h[d] < SLEEP_SHORT_H),
        "floor_rate_workout_days": rate(lambda d: d in workout_days) if workout_rows is not None else None,
        "floor_rate_rest_days": rate(lambda d: d not in workout_days) if workout_rows is not None else None,
        "samples": {"sleep_days": len(sleep_h),
                    "joined_rep_days": sum(1 for d in floor_by_day if d in sleep_h)},
    }


def _skill(payload: Any) -> dict | None:
    if not isinstance(payload, dict) or payload.get("status") not in (None, "ok"):
        return None
    window = payload.get("window") or {}
    streak = payload.get("streak") or {}
    if not window:
        return None
    return {"hands_on_min": window.get("core_coding_min") or 0,
            "ai_assisted_min": window.get("ai_assisted_coding_min") or 0,
            "hands_on_share": window.get("hands_on_share"),
            "streak_days": streak.get("core_coding_days") or 0}


def _context(remark_rows: list[dict] | None, direction: Any) -> dict:
    remarks = [{"key": r.get("key"), "created_at": _day(r.get("created_at")),
                "excerpt": str(r.get("content") or "")[:240]} for r in (remark_rows or [])]
    d = (direction or {}).get("direction") if isinstance(direction, dict) else None
    dir_out = None
    if isinstance(d, dict):
        skill = ((d.get("domains") or {}).get("skill") or {})
        dir_out = {"version": d.get("version"), "skill_phase_excerpt": str(skill.get("current_phase") or "")[:240]}
    return {"operator_remarks": remarks, "direction": dir_out}


def build_evidence(window_start: str, window_end: str, *, loader: Callable[[str], Any] = _default_loader) -> dict:
    raw = {p: loader(p) for p in INPUTS}
    rows = {p: _rows(raw[p]) for p in INPUTS}
    missing = [p for p in INPUTS if rows[p] is None and p not in ("/tmp/skill.json", "/tmp/direction.json")]
    skill = _skill(raw["/tmp/skill.json"])
    if skill is None:
        missing.append("/tmp/skill.json")
    if not isinstance(raw["/tmp/direction.json"], dict):
        missing.append("/tmp/direction.json")
    missing = [p for p in INPUTS if p in missing]  # keep INPUTS order

    program = _program(rows["/tmp/program_versions.json"]) if rows["/tmp/program_versions.json"] is not None else None
    if program is not None and rows["/tmp/program_reviews.json"] is not None:
        program["kill_gate_stops"] = sorted(_day(r.get("created_at")) for r in rows["/tmp/program_reviews.json"]
                                           if str(r.get("head") or "").startswith("KILL-GATE"))
    rep_weeks_rows = rows["/tmp/rep_weeks.json"]
    n_weeks = len(rep_weeks_rows or [])
    days = (date.fromisoformat(window_end) - date.fromisoformat(window_start)).days
    return {
        "window": {"start": window_start, "end": window_end, "days": days},
        "program": program,
        "rep_weeks": _rep_weeks(rep_weeks_rows) if rep_weeks_rows is not None else None,
        "rep_days": _rep_days(rows["/tmp/rep_days.json"]) if rows["/tmp/rep_days.json"] is not None else None,
        "steering": _steering(rows["/tmp/steering.json"]) if rows["/tmp/steering.json"] is not None else None,
        "health": (_health(rows["/tmp/health_daily.json"], rows["/tmp/workouts.json"], rows["/tmp/rep_days.json"], window_end)
                   if rows["/tmp/health_daily.json"] is not None else None),
        "skill": skill,
        "context": _context(rows["/tmp/remarks.json"], raw["/tmp/direction.json"]),
        "coverage": {"rep_weeks_in_window": n_weeks, "sparse": n_weeks < SPARSE_REP_WEEKS, "missing_inputs": missing},
    }


def main() -> int:
    start = os.environ.get("WINDOW_START_ET")
    end = os.environ.get("TODAY_ET")
    if not start or not end:
        print("learner_evidence: WINDOW_START_ET and TODAY_ET must be exported (source /tmp/anchors.env)", file=sys.stderr)
        return 2
    packet = build_evidence(start, end)
    with open("/tmp/evidence.json", "w") as f:
        json.dump(packet, f)
    cov = packet["coverage"]
    print(f"learner_evidence: /tmp/evidence.json written rep_weeks={cov['rep_weeks_in_window']} "
          f"sparse={cov['sparse']} missing={len(cov['missing_inputs'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m unittest tests.test_learner_evidence -v`
Expected: 5 `ok`. If `test_full_packet_values` disagrees on a hand-computed number, re-derive it from the fixture by hand before touching the code (the fixture comments state each expectation's reasoning).

- [ ] **Step 5: Live proof from the Mac (read-only, spec §6 step 4)**

With the local paste body's credentials exported in the shell (never printed), run the Stage 1 reads exactly as Task 8's runbook writes them (copy the `scripts/mcp.sh` lines from Task 8 Step 3 "Stage 1"), then:

```bash
export TODAY_ET=$(TZ=America/Toronto date +%F) WINDOW_START_ET=$(TZ=America/Toronto date -v-90d +%F)
python3 scripts/learner_evidence.py && jq '{coverage, rep_weeks: .rep_weeks.green_rate, kill: .program.kill_gate_stops, health: .health.samples, skill}' /tmp/evidence.json
```

Expected: `missing_inputs: []`, `rep_weeks_in_window` ≥ 12, `kill_gate_stops` contains `2026-09-06` and `2026-09-13`, `health.samples.joined_rep_days` > 0. Read the whole packet once by eye (`jq . /tmp/evidence.json | head -120`). Record the numbers in the commit message body.

- [ ] **Step 6: Commit**

```bash
git add scripts/learner_evidence.py tests/test_learner_evidence.py
git commit -m "feat(learner): deterministic lifeOS evidence packet (spec §4.3)"
```

---

### Task 8: `learning-agent.md` rewrite on lifeOS ledgers + README rows

**Files:**
- Modify: `learning-agent.md` (full rewrite of everything before `## Stage 3 — Synthesis`; targeted edits inside Stages 3/5; delete the weekly-trend guard everywhere)
- Modify: `README.md` (rows 28–29 of the runbook table)
- Test: `tests/test_runbook_contract.py` (`LearningAgentRunbookContractTests`)

**Interfaces:**
- Consumes: `scripts/learner_evidence.py` (Task 7) and `/tmp/evidence.json`.
- Produces: `/tmp/ctx.json = {current_profile, evidence, prior_learner_runs, existing_memories}`; `scripts/learning_compose.py` still reads `current_profile.sections` from it (unchanged).

- [ ] **Step 1: Write the failing tests**

In `tests/test_runbook_contract.py`, replace `test_stage_one_reads_only_production_weekly_trend_and_prior_learner_rows` with:

```python
    def test_stage_one_reads_lifeos_ledgers_not_weekly_trend(self):
        self.assertNotIn("weekly_trend", self.runbook)
        self.assertIn("COALESCE(run_scope, 'production') = 'production'", self.runbook)
        for path in ("/tmp/program_versions.json", "/tmp/rep_weeks.json", "/tmp/rep_days.json",
                     "/tmp/steering.json", "/tmp/health_daily.json", "/tmp/workouts.json",
                     "/tmp/skill.json", "/tmp/remarks.json", "/tmp/direction.json",
                     "/tmp/program_reviews.json"):
            self.assertIn(path, self.runbook)
        self.assertIn("python3 scripts/learner_evidence.py", self.runbook)
        self.assertIn("rep_weeks_in_window < 4", self.normalized)
        self.assertIn("Monthly behavioral profile analysis (lifeOS v", self.runbook)
        self.assertIn("source /tmp/mcp.env", self.runbook)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_runbook_contract.LearningAgentRunbookContractTests -v`
Expected: the new test FAILS (`weekly_trend` present).

- [ ] **Step 3: Rewrite the top of `learning-agent.md`**

Replace everything from the first line through the end of `## Stage 2 — Consolidate context` (i.e. up to but not including `## Stage 3 — Synthesis (the selected-model step)`) with:

````markdown
# Learning Agent Runbook — monthly lifeOS learner

Monthly behavioral-profile maintenance. Runs on the **first Sunday of the
month, ~12:00 ET** (the trigger fires every Sunday noon; the paste body's
gate skips every other Sunday in ~30 s) plus commissioned runs on phase
changes. Reads ~90 days of lifeOS evidence and maintains the versioned
`user_profile` via MCP. Use the model selected in the Routine UI; do not
export `MODEL` (write helpers record `routine-selected`).

Produces:

- 1 row in `llm_runs` (`run_type='learning_agent'`) — the structured diff +
  audit trail.
- 1 row in `agent_runs` — the learner narrative (iOS activity feed).
- 1 `learner_digest` llm_runs row (iOS card).
- On a mutation run: 1 `user_profile` version + N `agent_memory` rows
  added/updated/soft-expired. On a folded/sparse run: audit rows only.

Reads (no writes) from: `user_profile`, `program_versions`, `rep_weeks`,
`rep_days`, `proactive_interventions`, `agent_runs` (program reviews, prior
learner runs), `agent_memory`, `apple_health_daily_metrics_v2`,
`hevy_workouts`, `get_skill_summary`, `get_direction`.

History: the weekly-trend design (2026-04..06) is gone — its producers were
retired 2026-06-11 (lifeOS spec §9). Rewritten 2026-09-23 (spec
`docs/specs/2026-09-23-routine-reevaluation-spec.md` Design C).

---

## Output discipline (READ FIRST — synthesis is expensive)

Aim to enter Stage 3 with **at least 75% of your turn budget remaining**.

1. **No `jq .` pretty-prints of full payloads.** Save to `/tmp/*.json` and
   extract only specific fields.
2. **Do not print source file contents**, script bodies, API catalog excerpts,
   full SQL result payloads, full profile sections, or helper script bodies.
   Do not inspect helper scripts for write schemas during a routine run.
   Do not open `api-catalog.md` after pre-flight; treat the pre-flight read as
   cached context.
3. **Do not print `/tmp/ctx.json`. Do not print full `/tmp/diff.json`.**
   Stage 2 may print only compact counts. Stage 3 may summarize counts and
   claim IDs only.
4. **No re-reading of files between stages.** Stages 1–2 write `/tmp/ctx.json`;
   Stage 3 reads that single file and nothing else until Stage 4's audit.
5. **No raw-SQL probing of schema.** Column names are in this runbook. If a
   column is missing, the run fails fast with a logged error — do not guess.
6. **Batch parallel tool calls in one turn** (Stages 1 and 5).
7. **Stage 4 (evidence audit) is mandatory** on mutation runs.

---

## Pre-flight

Credentials live only in `/tmp/mcp.env` (CLAUDE.md → Credential Handling);
every Bash step begins with `source /tmp/mcp.env; source /tmp/anchors.env`.
Smoke test: `scripts/mcp.sh list_tools '{}' /tmp/tools.json` must list
`query_raw_sql recall_memory save_memory update_memory expire_memory
update_profile write_llm_run write_agent_run get_active_program
get_skill_summary get_direction`. Tools used:

- **Reads:** `query_raw_sql`, `recall_memory`, `get_skill_summary`, `get_direction`
- **Writes:** `save_memory`, `update_memory`, `expire_memory`,
  `update_profile`, `write_llm_run`, `write_agent_run`

`TEST_RUN=1` forbids production writes (only `write_test_llm_run` /
`write_test_agent_run`). Never `forget_memory` / `bulk_forget_memory`.

---

## Step 0 — Anchor the run

```bash
export TODAY_ET=$(TZ=America/Toronto date +%F)
export RUN_START_ET=$(TZ=America/Toronto date +'%Y-%m-%dT%H:%M:%S%z')
export PIPELINE_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
export WINDOW_START_ET=$(TZ=America/Toronto date -d '90 days ago' +%F 2>/dev/null || TZ=America/Toronto date -v-90d +%F)
printf 'export TODAY_ET=%s\nexport RUN_START_ET=%s\nexport PIPELINE_ID=%s\nexport WINDOW_START_ET=%s\n' \
  "$TODAY_ET" "$RUN_START_ET" "$PIPELINE_ID" "$WINDOW_START_ET" > /tmp/anchors.env
```

Separate Bash invocations do not share env: re-`source /tmp/anchors.env`
(and `/tmp/mcp.env`) in every later step. `/tmp/anchors.env` is key-free.

---

## Stage 0.5 — Fold precheck (cheap short-circuit; run before Stage 1)

```bash
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT GREATEST(COALESCE((SELECT max(computed_at) FROM rep_weeks), 'epoch'::timestamptz), COALESCE((SELECT max(created_at) FROM program_versions WHERE status IN ('active','superseded')), 'epoch'::timestamptz)) AS newest_evidence, (SELECT count(*) FROM rep_weeks WHERE week_start >= '$WINDOW_START_ET') AS rep_weeks_in_window, (SELECT max(created_at) FROM agent_runs WHERE COALESCE(run_scope,'production')='production' AND (goal ILIKE '%learner%' OR goal ILIKE '%behavioral profile%')) AS last_learner, (SELECT max(created_at) FROM user_profile) AS profile_ts\"}" /tmp/foldcheck.json
```

Decision:
- `newest_evidence` older than BOTH `last_learner` and `profile_ts` → the
  evidence is already **folded** → no-mutation path.
- `rep_weeks_in_window < 4` → **sparse** (bootstrap months) → no-mutation
  path as well; do NOT abort. New interpretations go under
  `hypotheses_for_next_run`.

No-mutation path: run a COMPACT Stage 1 (profile version + change_summary
only — not full sections; the lifeOS reads still run so the packet exists
for hypotheses), build the packet, confirm in Stage 1.5, skip Stage 2/3
synthesis and the Stage 5a compose preview, persist only the 5f/5g audit
rows. Otherwise run the full flow.

---

## Stage 1 — Load inputs (ALL IN ONE TURN, PARALLEL)

Every response goes to a `/tmp/*.json` file; nothing is pretty-printed. Keep
`user_profile.sections` intact on a mutation run (`learning_compose.py` needs
the full object). All production inputs filter
`COALESCE(run_scope, 'production') = 'production'` where the column exists.

```bash
source /tmp/mcp.env; source /tmp/anchors.env
# 1a) Current user_profile (latest version). Full sections ONLY on a mutation run.
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT version, sections, change_summary, created_at FROM user_profile ORDER BY version DESC LIMIT 1\"}" /tmp/profile_current.json &
# 1b) Program history in window.
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id::text AS id, status, source, valid_from::text AS valid_from, valid_until::text AS valid_until, (operator_input IS NOT NULL) AS has_operator_input, recompose_count FROM program_versions WHERE valid_from >= '$WINDOW_START_ET' ORDER BY valid_from\"}" /tmp/program_versions.json &
# 1c) Rep weeks in window (newest first).
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT week_start::text AS week_start, floors_met, bar, green, rollup FROM rep_weeks WHERE week_start >= '$WINDOW_START_ET' ORDER BY week_start DESC\"}" /tmp/rep_weeks.json &
# 1d) Rep days RAW rows in window (the packet aggregates).
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT day::text AS day, family, floor_met, floor_minutes, artifact, travel_excused FROM rep_days WHERE day >= '$WINDOW_START_ET' ORDER BY day\"}" /tmp/rep_days.json &
# 1e) Steering episode outcomes in window (anchors only).
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT issued_at::text AS issued_at, action, final_outcome, outcome_data->'delivery'->>'tag' AS delivery_tag FROM proactive_interventions WHERE issued_at >= '$WINDOW_START_ET' AND final_outcome IS NOT NULL AND final_outcome <> 'grouped' ORDER BY issued_at\"}" /tmp/steering.json &
# 1f) Health correlates: daily sleep/HRV/steps + workout days.
scripts/mcp.sh query_raw_sql "{\"database\":\"health_db\",\"sql\":\"SELECT metric_date::text AS metric_date, metric_type, value FROM apple_health_daily_metrics_v2 WHERE metric_date >= '$WINDOW_START_ET' AND metric_type IN ('sleep_seconds','hrv_ms','steps') ORDER BY metric_date\"}" /tmp/health_daily.json &
scripts/mcp.sh query_raw_sql "{\"database\":\"health_db\",\"sql\":\"SELECT DISTINCT (started_at AT TIME ZONE 'America/Toronto')::date::text AS day FROM hevy_workouts WHERE started_at >= '$WINDOW_START_ET' ORDER BY 1\"}" /tmp/workouts.json &
# 1g) Hands-on vs AI-assisted over the window (best-effort).
scripts/mcp.sh get_skill_summary '{"days":90}' /tmp/skill.json &
# 1h) Operator remarks + the active direction.
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT key, created_at::text AS created_at, content FROM agent_memory WHERE category IN ('goal','preference') AND (expires_at IS NULL OR expires_at > NOW()) AND created_at >= '$WINDOW_START_ET' ORDER BY created_at DESC LIMIT 20\"}" /tmp/remarks.json &
scripts/mcp.sh get_direction '{}' /tmp/direction.json &
# 1i) Program-review notes in window (kill-gate stops are detected by prefix).
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT created_at::text AS created_at, left(final_response, 200) AS head FROM agent_runs WHERE COALESCE(run_scope, 'production') = 'production' AND goal ILIKE 'Weekly program review%' AND created_at >= '$WINDOW_START_ET' ORDER BY created_at DESC LIMIT 16\"}" /tmp/program_reviews.json &
# 1j) Prior production learner runs (continuity), compacted.
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id, goal, created_at, left(final_response::text, 6000) AS final_response_excerpt FROM agent_runs WHERE COALESCE(run_scope, 'production') = 'production' AND (goal ILIKE '%behavioral profile%' OR goal ILIKE '%learner%' OR goal ILIKE '%profile analysis%') ORDER BY created_at DESC LIMIT 6\"}" /tmp/prior_learner_runs.json &
# 1k) Active learning_agent memories — expired rows are retired beliefs, never re-enter synthesis.
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id, key, category, left(content::text, 4000) AS content_excerpt, confidence, source, updated_at FROM agent_memory WHERE source = 'learning_agent' AND (expires_at IS NULL OR expires_at > NOW()) ORDER BY updated_at DESC\"}" /tmp/existing_memories.json &
wait
echo "Stage 1 ok: 12 reads"
```

## Stage 1.2 — Evidence packet (deterministic)

```bash
python3 scripts/learner_evidence.py
jq '.coverage' /tmp/evidence.json
```

`/tmp/evidence.json` (contract: spec §4.3) is the ONLY evidence Stage 3
reads. Any input listed in `coverage.missing_inputs` is a degraded section
(`null`), never a reason to abort — say which in the narrative.

---

## Stage 1.5 — Replay / folded-evidence guard

Confirm the Stage 0.5 decision against the packet and the prior narrative:
folded (newest rollup/program already referenced by a later learner run or
the profile) or sparse (`coverage.sparse`) ⇒ **reinforcement-only**:

- do not add profile traits; do not update traits except to restate active
  ones as reinforcement; do not create/update/expire memories;
- do not call `update_profile`, `save_memory`, `update_memory`, `expire_memory`;
- do not fetch full `profile.sections`; skip the compose preview;
- newly noticed interpretations go to `hypotheses_for_next_run`.

Production folded/sparse runs still persist the compact no-mutation audit
rows (5f/5g).

---

## Stage 2 — Consolidate context (single-pass)

```bash
jq -n \
  --slurpfile profile /tmp/profile_current.json \
  --slurpfile evidence /tmp/evidence.json \
  --slurpfile priors /tmp/prior_learner_runs.json \
  --slurpfile mems /tmp/existing_memories.json \
  '{
    current_profile: ($profile[0].data[0] // null),
    evidence: ($evidence[0]),
    prior_learner_runs: ($priors[0].data // []),
    existing_memories: ($mems[0].data // [])
  }' > /tmp/ctx.json
echo "Stage 2 ok: context written to /tmp/ctx.json"
jq '{profile_version: .current_profile.version, rep_weeks: .evidence.coverage.rep_weeks_in_window, sparse: .evidence.coverage.sparse, priors_count: (.prior_learner_runs | length), memories_count: (.existing_memories | length)}' /tmp/ctx.json
```

### Bootstrap guard

If `current_profile` is null the `user_profile` table has never been seeded —
**abort** and ask the operator to run data-platform `scripts/seed_profile.py`.

```bash
if [ "$(jq -r '.current_profile // "null"' /tmp/ctx.json)" = "null" ]; then
  echo "ABORT: user_profile is empty. Seed it with data-platform scripts/seed_profile.py before running the learning agent."
  exit 2
fi
```

From this point on, read only `/tmp/ctx.json`.

---
````

- [ ] **Step 4: Targeted edits inside Stages 3–5 and the tail**

In Stage 3 synthesis rules, replace rule 3

```
3. **A trait can be removed only if** it either contradicts the last 2
   weekly trends, OR has not appeared in any weekly trend for 4+ weeks.
```

with

```
3. **A trait can be removed only if** it is contradicted by the evidence
   packet in two consecutive monthly runs, OR nothing in the packet's 90-day
   window supports it.
```

Replace rule 10

```
10. If Stage 1.5 marked the newest weekly trend as already folded, any new
    interpretation must stay in `hypotheses_for_next_run` as a candidate
    insight. Do not place it in `traits_added`, `traits_updated`,
    `traits_removed`, `memories_to_create`, or `memories_to_expire` until a
    newer weekly trend confirms it.
```

with

```
10. If Stage 1.5 marked the run folded or sparse, any new interpretation
    stays in `hypotheses_for_next_run`. Do not place it in `traits_added`,
    `traits_updated`, `traits_removed`, `memories_to_create`, or
    `memories_to_expire` until a later packet confirms it.
```

In the diff shape, change `"source_table": "table_or_weekly_trend_row_id",` to `"source_table": "rep_days|rep_weeks|program_versions|proactive_interventions|apple_health_daily_metrics_v2|hevy_workouts|rescuetime_activity_slice|agent_memory",`.

Add to the end of the Stage 4 "Specific anti-fabrication checks" list:

```
- **Floor truth is the ledger:** rep floors come from `rep_days.floor_met`
  (the nightly verifier), never recomputed RescueTime sums.
- **Focus %** = `SUM(seconds WHERE productivity >= 1) / SUM(seconds)`; name
  the threshold in the formula. `ts_utc` is ET-as-UTC — cast `::timestamp`.
- Postgres has no `ROUND(double precision, int)` — `ROUND(x::numeric, 2)`.
```

In Stage 5b-test, change the goal `"Weekly behavioral profile analysis (TEST RUN)"` to `"Monthly behavioral profile analysis (TEST RUN)"`.

In 5b-prod, change `If Stage 1.5 marked the newest weekly trend as already folded, or if Stage 4` to `If Stage 1.5 marked the run folded or sparse, or if Stage 4`.

In 5e, replace

```
source_ids=$(jq -c '[.weekly_trends[].id]' /tmp/ctx.json)
```

with

```
# source_profile_ids is int[] of llm_runs ids; the lifeOS packet has no
# llm_runs provenance, so cite the prior learner diff rows instead.
source_ids=$(jq -c '[.prior_learner_runs[]?.id | select(type == "number")]' /tmp/ctx.json)
[ "$source_ids" = "[]" ] && source_ids='[]'
```

In 5g, replace the goal block

```
goal="Weekly behavioral profile analysis v${new_version}"
if jq -e '
  ...
' /tmp/diff.json >/dev/null; then
  goal="Weekly behavioral profile analysis (no mutation v${new_version})"
fi
```

with

```
goal="Monthly behavioral profile analysis (lifeOS v${new_version})"
if jq -e '
  (.folded_evidence == true)
  or (((.section_updates // {}) | length) == 0
      and ((.memories_to_create // []) | length) == 0
      and ((.memories_to_expire // []) | length) == 0)
' /tmp/diff.json >/dev/null; then
  goal="Monthly behavioral profile analysis (lifeOS v${new_version}, no mutation)"
fi
```

and `AGENT_RUN_ORIGIN=claude_weekly_learner_production` → `AGENT_RUN_ORIGIN=claude_monthly_learner_production`.

In `## Failure handling`, replace `- If Stage 1 returns fewer than 2 weekly_trend rows → abort (staleness guard).` with `- Fewer than 4 rep_weeks rows in the window → sparse → no-mutation audit run (never an abort).`

In `## Budget and cadence`, replace the second bullet (`**Never run with fewer than 2 weekly trends…`) with `- **Cadence:** first Sunday of the month, ~12:00 ET; every other Sunday the paste-body gate skips in ~30 s. Commissioned runs on phase changes say so in the triggering message.`

Replace `## Signoff` with:

```markdown
## Signoff

2026-09-23 ET · operator session — rewritten on the lifeOS ledgers (spec
Design C): Stage 1 = 12 reads, Stage 1.2 = `scripts/learner_evidence.py`
packet, sparse guard replaces the weekly-trend abort, goal string
`Monthly behavioral profile analysis (lifeOS vN)`, credentials via
`/tmp/mcp.env`. (History in git.)
```

- [ ] **Step 5: README rows**

In `README.md`, replace row 28's "When to run" cell text `Sunday ~21:15 ET lifeOS week composer (after the 10:07 goal-policy review + the verifier's 20:35 rollup)` with `Sunday 21:15 ET lifeOS week composer (trigger "Weekly Program Review", `CRON_TZ=America/Toronto 15 21 * * 0`; after the verifier's 20:35 rollup, the 05:37 insight sweep and the 09:07 scorecard)`, and row 29's `Monthly learner (first Sunday + commissioned on phase changes; see the lifeOS retarget banner)` with `Monthly learner — first Sunday ~12:00 ET (trigger fires every Sunday noon, the body gate skips the rest) + commissioned on phase changes; evidence packet `scripts/learner_evidence.py``.

- [ ] **Step 6: Run the suite and commit**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`.

```bash
git add learning-agent.md README.md tests/test_runbook_contract.py
git commit -m "feat(learner): runbook rewritten on lifeOS ledgers with the evidence packet (spec Design C)"
```

---

### Task 9: Morning paste body v7 (gitignored; operator re-pastes)

**Files:**
- Rename: `claude-routine-morning-briefing.v6.md` → `claude-routine-morning-briefing.v7.md`

- [ ] **Step 1: Rename and edit**

```bash
git mv -k claude-routine-morning-briefing.v6.md claude-routine-morning-briefing.v7.md 2>/dev/null || mv claude-routine-morning-briefing.v6.md claude-routine-morning-briefing.v7.md
```

Edit `claude-routine-morning-briefing.v7.md` (key line unchanged in value):

1. Header line 3 → `> **v7 · last revised 2026-09-23 ET** · paste-ready body for the Routine UI.`
2. Replace the `## Credentials` section body with:

```
Your FIRST Bash step writes the credentials once, then every later step
begins with `source /tmp/mcp.env` (CLAUDE.md → Credential Handling):

  umask 077
  cat > /tmp/mcp.env <<'ENV'
  export MCP_BASE_URL='https://a8f2e1.steventa.me'
  export MCP_API_KEY='<KEY LINE — copy the existing literal here, unchanged>'
  export ROUTINE_MODE='live'
  export ALLOW_WRITES='1'
  ENV
  source /tmp/mcp.env

Never re-export the literal in later steps, never cat/print /tmp/mcp.env.
Do not export MODEL. The model is selected in the Claude Routine UI.
```

3. In `## Task`, the Stage 0.5 line → `Stage 0.5  health, RescueTime totals, browser, email, calendar, memory, goal policy, ACTIVE PROGRAM, skill, never-surfaced taps — 14 reads in parallel`.
4. Append to `## Briefing Quality Rules` as item 9: `9. Taps are a mirror, never the lead: surface only taps whose is_new is true, as ONE combined priority action at the LAST rank; never rank 1, never the headline, never a risk flag; zero words when none are new (runbook rule 15).`
5. Signoff → `v7 · 2026-09-23 ET · UI: NEEDS RE-PASTE (single key file /tmp/mcp.env; 14 reads; mirror-only taps)` and fold the old first line into the history line.

- [ ] **Step 2: Verify nothing tracked changed and the key is still absent from git**

Run: `git status --short && git check-ignore -q claude-routine-morning-briefing.v7.md && echo ignored-ok`
Expected: no tracked changes; `ignored-ok`.

---

### Task 10: Program-review paste body v9

**Files:**
- Rename: `claude-routine-program-review.v6.md` → `claude-routine-program-review.v9.md`

- [ ] **Step 1: Rename and edit**

```bash
mv claude-routine-program-review.v6.md claude-routine-program-review.v9.md
```

Edit:

1. Header → `> **v9 · last revised 2026-09-23 ET** · paste-ready body for the Routine UI.` and the schedule line → `> Weekly, **Sunday 21:15 ET** — routine "Weekly Program Review", cron ``CRON_TZ=America/Toronto 15 21 * * 0`` (after the 20:35 rollup, the 05:37 insight sweep, the 09:07 scorecard).`
2. Replace the `## Credentials` section body with the same block as Task 9 step 2, but the `ENV` file carries `MCP_BASE_URL`, `MCP_API_KEY` (unchanged literal) and `export ROUTINE_SOURCE='claude_program_review_production'`; `ROUTINE_MODE`/`ALLOW_WRITES` stay per Run Mode (exported in the step that runs Stage 3). Drop the sentence "separate Bash invocations do not share env, so re-export each session" and replace it with "later steps `source /tmp/mcp.env`".
3. In `## Task` stages, insert after Stage 0: `  Stage 0.5  rollup freshness line (WARN if rep_weeks[0].computed_at > 24 h old)` and change Stage 1.6's absent line to `  Stage 1.6  job-stretch gate — reads the operator's job_artifact_<week_start> memory row (rules in program-review.md)`.
4. `## Definition of Done` gains `- the rollup-age line, the Job artifact line, the Shelved decisions line`.
5. Signoff → `v9 · 2026-09-23 ET · UI: NEEDS RE-PASTE (21:15 ET slot; /tmp/mcp.env; Stage 0.5/1.6/2.8 lines)`.

- [ ] **Step 2: Verify**

Run: `git status --short && git check-ignore -q claude-routine-program-review.v9.md && echo ignored-ok`
Expected: clean; `ignored-ok`.

---

### Task 11: Monthly learner paste body v6

**Files:**
- Rename: `claude-routine-monthly-learner.v5.md` → `claude-routine-monthly-learner.v6.md`

- [ ] **Step 1: Rename and edit**

```bash
mv claude-routine-monthly-learner.v5.md claude-routine-monthly-learner.v6.md
```

Edit:

1. Header → `> **v6 · last revised 2026-09-23 ET** …`; the cadence lines → `Monthly: FIRST SUNDAY of the month, ~12:00 ET (the trigger fires EVERY Sunday at noon — ``CRON_TZ=America/Toronto 0 12 * * 0`` — and the live gate below skips all but the first Sunday), plus commissioned runs on phase changes.`
2. `## Task`: replace `Read learning-agent.md in this workspace — INCLUDING its lifeOS retarget banner, which overrides the weekly_trend-era stage details — and execute` with `Read learning-agent.md in this workspace and execute`; in the stage list insert after Stage 1: `  Stage 1.2   python3 scripts/learner_evidence.py -> /tmp/evidence.json (deterministic packet)`.
3. Replace the `## Credentials` section body with the Task 9 block (MCP vars + `ROUTINE_SOURCE`, `AGENT_RUN_ORIGIN='claude_monthly_learner_production'`, `PERSISTED_MODEL='routine-selected'`; `ROUTINE_MODE`/`ALLOW_WRITES` per Run Mode). Drop "re-export each session".
4. Delete the body's `## Stage 1 Inputs (lifeOS evidence — replaces the retired weekly_trend inputs)` section entirely (the runbook is canonical now) and replace it with two lines: `## Stage 1 / 1.2` / `Run the 12 reads and the packet exactly as learning-agent.md Stage 1 and Stage 1.2 say; /tmp/evidence.json is the only evidence Stage 3 reads.`
5. `## MCP smoke test` required tools gain `get_skill_summary` and `get_direction`.
6. Signoff → `v6 · 2026-09-23 ET · UI: NEEDS RE-PASTE (every-Sunday cron + first-Sunday gate; packet step; /tmp/mcp.env; runbook canonical)`.

- [ ] **Step 2: Verify**

Run: `git status --short && git check-ignore -q claude-routine-monthly-learner.v6.md && echo ignored-ok`
Expected: clean; `ignored-ok`.

---

### Task 12: Push, trigger updates, proofs

**Files:** none in the repo (routines API + live checks).

- [ ] **Step 1: Full suite, then push**

Run: `python3 -m unittest discover -s tests 2>&1 | tail -3 && git log --oneline origin/main..main`
Expected: `OK`; the task commits listed.

```bash
git push origin main
```

- [ ] **Step 2: Weekly trigger — retime, rename, re-enable**

`RemoteTrigger update`, `trigger_id: trig_01TUcmdDJU8765zteDvoStcK`, body:

```json
{"name": "Weekly Program Review", "cron_expression": "CRON_TZ=America/Toronto 15 21 * * 0", "enabled": true}
```

Then `RemoteTrigger get` on the same id. Expected: `enabled: true`, `next_run_at` = `2026-09-28T01:15:00Z` (Sunday 09-27 21:15 EDT).

- [ ] **Step 3: Monthly trigger — every Sunday noon**

`RemoteTrigger update`, `trigger_id: trig_01MV43DVqekDGxza44V4QGiM`, body:

```json
{"cron_expression": "CRON_TZ=America/Toronto 0 12 * * 0"}
```

Then `get`. Expected: `next_run_at` = `2026-09-27T16:00:00Z` (the gate will skip it; the first real run is 10-04).

- [ ] **Step 4: Hand the operator the three re-pastes**

Tell the operator: paste `claude-routine-morning-briefing.v7.md` into "Winter-MorningRoutine", `claude-routine-program-review.v9.md` into "Weekly Program Review", `claude-routine-monthly-learner.v6.md` into "Monthly Learner" (claude.ai → Code → Routines → edit prompt). Until the morning body is re-pasted, the 09-24 run still uses inline exports but everything else lands (the runbook is read from `main`).

- [ ] **Step 5: Live proofs (record each in `docs/specs/…-spec.md` §6 or a session note)**

- 09-24 06:35 ET morning run: `RemoteTrigger list_runs` → `get_run_log`; expect `Stage 0.5 ok: 14 queries complete`, no server rejection, `calendar_plan.py` exit 0, `priority_actions` with no `Tap:` at rank 1, `validate_payloads: ok` (warnings allowed). SQL check:
  `SELECT id, output_response->'priority_actions'->0->>'action' FROM llm_runs WHERE run_type='daily_briefing' ORDER BY created_at DESC LIMIT 1`.
- 09-27 21:15 ET review: notes contain `rollup age: <1h`, `Job artifact:`, `Shelved decisions:`, populated Stages 2.7/2.8; `program_versions` gains a row valid 09-28..10-04.
- 10-04 12:00 ET learner: `get_run_log` shows `learner_evidence: /tmp/evidence.json written … missing=0`, a fold decision, and either `user_profile` v18 or a `NO MUTATION` narrative; `learner_digest` row exists.
