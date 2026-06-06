# Claude Routine — Weekly Learner / Behavioral Profile Pipeline (PRODUCTION)

> Paste-ready body for the Claude Routine UI. Tightened companion to
> `learning-agent.md`. Mirror of the prior scheduled prompt with the Stage 0.5
> fold precheck added and redundancy removed. All safety guards preserved.
> (Consider `.gitignore`-ing this file, like `claude-routine-morning-briefing.md`.)

---

AUTHORIZED ROUTINE: Weekly Learner / Behavioral Profile Pipeline — PRODUCTION.
You are running as a scheduled Claude Routine in Cowork. Execute the weekly
learner pipeline against the personal data platform in PRODUCTION MODE for the
Monday learning/profile update. The user is not present; execute autonomously,
make reasonable choices, and note them. Take a "write" action only where this
prompt or `learning-agent.md` explicitly calls for it. When in doubt, produce a
report.

This is NOT a morning briefing. Never call `query_calendar` or any Google
Calendar tool; never create, update, inspect, or summarize calendar events.

## Transport — connector mode (Cowork)
Reach the platform only through the `mcp__steventa-data-platform__*` connector
tools (transport + auth are brokered server-side).
- Do NOT export `MCP_BASE_URL` / `MCP_API_KEY`. No API key belongs in this prompt.
- Do NOT call `scripts/mcp.sh`, `scripts/write_run.sh`, or `scripts/write_agent.sh`
  (their curl path hits the sandbox egress wall here).
- Each `scripts/mcp.sh <tool> '<json>' /tmp/<out>.json` in `learning-agent.md`
  maps 1:1 to calling `mcp__steventa-data-platform__<tool>` with the same JSON
  args. The tool returns `{"result":"<envelope>"}`; unwrap `.result` and write the
  inner `{"status":...,"data":...,"row_count":...}` to that same `/tmp/<out>.json`
  so downstream `jq`, `learning_compose.py`, and `validate_payloads.py` run
  unchanged. (Bash cannot reach the endpoint, so anything needed on disk must be
  written from the connector response.)
- Stage 5 writes call `write_llm_run` / `write_agent_run` directly; capture the
  row id from the response `data`.
- Connector arg types are strict: pass `tool_calls`, `output_response`,
  `input_payload`, and `source_profile_ids` as JSON STRINGS, not arrays/objects
  (a bare array is rejected with "Input should be a valid string").

## Run mode (non-secret)
Export at the start of each Bash session (Bash shells are independent — `export`s
do NOT persist across calls; persist anchors to `/tmp/anchors.env` and re-source,
or recompute):
  export ROUTINE_MODE="live"
  export ALLOW_WRITES="1"
  export ROUTINE_SOURCE="claude_weekly_learner_production"
  export PERSISTED_MODEL="routine-selected"
Do not export MODEL. For persisted rows use model="routine-selected" unless the
runtime exposes a selected model.

## Repo preflight
  git fetch origin main
  ff-only merge if HEAD != origin/main (no `git add/commit/push`, no branches)
Require HEAD to contain `5b500aa71a026f900acf2db2c95cdb0892b458e0` (compose fix
7fb19ab + replay/folded-evidence guard 5b500aa):
  git merge-base --is-ancestor 5b500aa71a026f900acf2db2c95cdb0892b458e0 HEAD
If older, STOP and emit a compact diagnostic; do not run on an older commit.

## Stage -1 — Connector readiness
Confirm these tools exist in the toolset (all `mcp__steventa-data-platform__*`):
query_raw_sql, recall_memory, save_memory, update_memory, expire_memory,
update_profile, write_llm_run, write_agent_run. Do NOT run a `list_tools` smoke
test and do NOT call `scripts/mcp.sh`. If any is missing, STOP with a compact
diagnostic (connector not loaded; run the curl path elsewhere). Do not fall back
to curl or to `write_test_*`.

## Task
Read `learning-agent.md` and execute the weekly learner flow as a production run
via the connector. May update the real profile / memories / learner rows — but
ONLY after the fold precheck, all guards, the profile preview, and the evidence
audit pass.

Stages:
  -1   repo freshness + connector readiness
  0    anchor dates + pipeline_id
  0.5  FOLD PRECHECK (run FIRST — cheap short-circuit, see below)
  1    load profile, production weekly_trends, prior production learner runs,
       learning memories  (full payloads only if NOT folded)
  1.5  freshness / duplicate / folded-evidence guard (confirm precheck)
  2    consolidate /tmp/ctx.json
  3    synthesis -> /tmp/diff.json
  4    mandatory evidence audit
  5    production writes only if guards pass

## Stage 0.5 — Fold precheck (do this before loading heavy inputs)
At weekly cadence the newest trend is usually already folded. Decide with ONE
query before pulling any large payload:
  SELECT
    (SELECT max(created_at) FROM llm_runs WHERE run_type='weekly_trend'
       AND COALESCE(run_scope,'production')='production') AS newest_trend,
    (SELECT max(created_at) FROM agent_runs
       WHERE COALESCE(run_scope,'production')='production'
       AND (goal ILIKE '%learner%' OR goal ILIKE '%behavioral profile%')) AS last_learner,
    (SELECT max(created_at) FROM user_profile) AS profile_ts;
If `newest_trend` is older than BOTH `last_learner` and `profile_ts`, treat the
newest trend as folded → no-mutation path:
- compact Stage 1 only (profile `version` + `change_summary`, weekly-trend
  ids/dates, newest trend `headline`/`dominant_change`); do NOT pull full
  `profile.sections`;
- confirm in Stage 1.5; skip Stage 2/3 synthesis and Stage 5a compose;
- persist only the Stage 5f/5g audit rows (see Folded-evidence rule).
If ambiguous (a trend newer than the last learner run exists), run the full flow.

## Output discipline
Compact status lines only (stage, status, counts, row IDs, errors). No general
repo audit. Do not print source files, script bodies, catalog excerpts,
`/tmp/ctx.json`, full `/tmp/diff.json`, full profile sections, full weekly_trend
payloads, final_response, or new_sections.json. Redirect MCP/helper output to
`/tmp/*.json`. Batch independent calls in parallel. Target: reach Stage 3 with
>=75% budget remaining (most folded runs never reach Stage 3).

## Stage 1 inputs
Filter production with `COALESCE(run_scope,'production')='production'`. Pull only
synthesis-relevant `weekly_trend` fields (headline, dominant_change,
negative_trends, positive_trends, trends), not the full blob. Keep historical
rows compact; keep large JSON in `/tmp/*.json` and extract only needed fields.

## Stage 1.5 — Folded-evidence guard
Confirm the precheck against the prior learner narrative / profile source IDs. If
folded: no new traits, no memory create/update/expire, no `update_profile`; keep
new interpretations under `hypotheses_for_next_run` as candidates not eligible
for mutation until a newer weekly_trend confirms them. A folded run may still
write the compact no-mutation `llm_runs` + `agent_runs` audit rows.

## Stage 4 — Evidence audit (mandatory on mutation runs)
Run each `audit_plan` SELECT. Numeric claims must match within tolerance
(normally +/-5%); categorical exact; missing data drops the claim. Write
`/tmp/audit_results.json` (passed/dropped); remove failed claims from
`/tmp/diff.json` before Stage 5. If >50% of claims drop, ABORT before writes.

## Stage 5 — Writes
Mutation runs: 5a compose preview (`scripts/learning_compose.py` MUST succeed and
write `/tmp/new_sections.json` before any write — the old failure
`learning_compose: section 'work_patterns' has no traits list` is NOT acceptable;
on success report "profile preview: ok, sections=N"; on failure ABORT before any
profile/memory write); 5b recall_memory key verify; 5c expire_memory; 5d
save/update_memory; 5e update_profile; 5f write_llm_run(diff); 5g
write_agent_run(narrative).
Folded / no-mutation runs: skip 5a–5e (report profile preview "N/A (folded)");
do 5f + 5g only — write_llm_run with step_label="stage3_diff_folded_no_mutation",
write_agent_run goal "Weekly behavioral profile analysis (no mutation v{N})".

Production mutation boundary — allowed writes: save_memory, update_memory,
expire_memory, update_profile, write_llm_run, write_agent_run. NEVER call
forget_memory, bulk_forget_memory, write_test_llm_run, write_test_agent_run.
Never retry a write that may have inserted (duplicates). A pre-insertion input
VALIDATION error has not inserted anything — fix the argument and call once
(not a duplicate-causing retry).

Agent-run classification: run_origin="claude_weekly_learner_production",
execution_mode="scheduled_claude", agent_kind="deep_learner",
visibility="user_visible", run_scope="production" (as a JSON-string in tool_calls).

## Section key guard
Use the live profile section keys from `/tmp/ctx.json` as truth. Use
`health_patterns`, not `health_correlations`. Do not invent new section keys.

## Definition of done
Report: pipeline_id; git HEAD + whether it contains 5b500aa; TODAY_ET /
WINDOW_START_ET; newest weekly_trend id/date; profile version before run;
folded-evidence status; profile preview status (ok / failed / N/A folded);
profile update executed (new version, or none); memory writes (created/updated/
expired keys, or none); llm_runs row id; agent_runs row id; audit passed/dropped
counts; fatal_errors and recovered_errors; whether Stage 5 completed. If Stage 5
did not complete and no guard intentionally aborted before writes, the run is a
FAILURE.

Begin now.
