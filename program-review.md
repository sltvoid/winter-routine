# Program Review — Sunday lifeOS week composer

The weekly content producer for the lifeOS program layer (data-platform spec
`docs/specs/2026-06-11-lifeos-surfaces-spec.md` §3). Runs Sunday morning
(after ~10:30 AM ET, so the goal-policy review and the verifier's Sunday
rollup have landed). Composes next week's rotation from evidence and writes
it through `write_program`.

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
wait
```

Operator remarks land as goal/preference `agent_memory` rows — anything the
operator said during the week ("more Rust", "ease off") is input here; record
each consumed remark's key in `generated_from` (the goal-policy v57 pattern).

## Stage 1 — Kill-condition gate (deterministic, before any composition)

Read `rep_weeks[0].rollup` (the verifier's Sunday rollup; data-platform
computes these VM-side whether or not this routine runs):

- `consecutive_non_green >= 4` → **STOP composing.** Write no program. Surface
  a goal-level rethink request to the operator (the spec's response is a
  conversation, not "build more system").
- `auto_weeks_no_operator_input >= 8` AND `green_rate_trend.declining` →
  **STOP composing**, ask for a frame conversation.
- Otherwise proceed. Note `email/warn/lock` demotion counts in the review
  notes when nonzero — rung demotions themselves are platform-side.

## Stage 2 — Compose next week's rotation

Frame facts (read from the active program; never modify): anchor 19:00–20:00
ET weekdays, Saturday milestone block 90–120 min, Sunday rest, floors 30 min,
green week = 4 of 6, five families.

Composition rules:
1. Every slot Mon–Sat gets a pre-decided rep with `family`, `title`, and
   `success` (one observable artifact or completion condition). No slot may
   require a decision at execution time.
2. Drills follow the current progression (rustlings: continue from the last
   completed set per `rep_days`/dojo evidence; don't restart).
3. Thursday comms rep scopes Saturday's milestone (design doc = the scoping).
4. Pull Saturday milestones from the program's `milestone_queue`; replenish
   the queue when it runs low (2+ scoped milestones ahead).
5. Respond to evidence: floors missed on a family → lighter or
   friction-removed reps there next week, not heavier; momentum on milestones
   → bigger scoped milestone, same block.
6. Honor operator remarks above all defaults.

## Stage 3 — Write

```bash
scripts/mcp.sh write_program "$(cat /tmp/next_program.json)" /tmp/write_result.json
```

Payload shape: `{"program": {"valid_from": "<next Mon>", "valid_until":
"<next Sun>", "frame": <copy of active frame verbatim>, "rotation": {mon..sun},
"milestone_queue": [...], "generated_from": {"evidence": [rep_weeks ids,
memory keys, remark keys]}, "source": "claude_program_review"}}`.

Expect `{"status":"ok", "status":"active"}`. A `"status":"draft"` response
means a frame delta was detected and clamped — report it; do not retry with
tweaks (the frame is operator-only).

## Definition of done

- One `program_versions` row written (active, or draft+reported).
- Review notes (3–6 lines: what changed and why, evidence cited) written via
  `write_agent_run` with `agent_kind='program_review'`.
- No frame fields modified; no enforcement opinions expressed as config.
