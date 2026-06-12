# Learning Agent Runbook

> **lifeOS retarget (2026-06-11, data-platform spec §9 — REQUIRED READING
> before the next run):** the weekly-profile pipeline is retired
> (`weekly_profile_stats`/`weekly_profile_narrative`/`weekly_trend` run types
> closed; the platform CronJobs are deleted), so this runbook's `weekly_trend`
> inputs and abort guard no longer have a producer. The learner's new shape:
> **monthly cadence** (first Sunday, after that morning's program review) plus
> commissioned runs on phase changes. Evidence inputs move to the lifeOS
> ledgers: `program_versions` (review history), `rep_weeks`/`rep_days`
> (floors, artifacts, green weeks), `proactive_interventions` (steering
> outcomes), and health correlates — window ~90 days. Fold precheck compares
> against the newest `rep_weeks`/`program_versions` row instead of
> `weekly_trend`; sparse lifeOS evidence (fewer than 4 `rep_weeks` rows in
> window) folds to a no-mutation audit run rather than aborting. Goal naming
> becomes "Monthly behavioral profile analysis (lifeOS vN)" — update the
> continuity matcher in lockstep. The durable implementation home is RFC #11
> (`scripts/weekly_evidence.py` gate/finalize) built against lifeOS sources
> directly; until that lands, apply this banner over the stage details below
> and update the Cowork Routine schedule to monthly.


Weekly/deep behavioral profile analysis. Run manually or on the weekly routine
cadence after upstream weekly profile evidence exists. Use the model selected in
the Claude Routine UI. Do not export `MODEL`; the shell write helpers default
to `routine-selected` when the routine runtime does not expose a model variable.

Produces:

- 1 row in `llm_runs` containing the structured learner diff/audit trail.
- 1 row in `agent_runs` containing the learner narrative, visible on the iOS
  activity feed.
- When fresh weekly evidence passes the replay guard and audit: 1 row in
  `user_profile` plus N rows added, updated, or soft-expired in `agent_memory`.
- When evidence is already folded or produces zero eligible changes: compact
  `llm_runs` + `agent_runs` audit rows only; do not mutate profile or memory.

Reads (no writes) from: `llm_runs` (prior weekly_trend rows + prior
learning_agent rows), `user_profile` (current version), `agent_memory`
(existing learning_agent memories), raw tables when doing the evidence
audit.

---

## Output discipline (READ FIRST — Claude synthesis is expensive)

The synthesis step can be expensive, especially with richer Claude models. The
morning-briefing runbook's "60% budget remaining" rule is tighter here: aim to
enter Stage 3 (the synthesis) with **at least 75% of your turn budget remaining**
so the selected model has room to think.

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
5. **No raw-SQL probing of schema.** Column names are in this runbook or in
   `api-catalog.md`. If a column is missing, the run fails fast with a
   logged error — do not guess.
6. **Batch parallel tool calls in one turn** (Stages 1 and 5).
7. **Stage 4 (evidence audit) is mandatory.** Skipping it produces the
   fabrication class of errors that made v6 need a patch session
   (see data-platform `session-2026-04-17`).

---

## Pre-flight — Read api-catalog.md

(Connector mode: the loaded `mcp__steventa-data-platform__*` tool schemas plus
this runbook's Stage 5 contracts are authoritative for write shapes, so you can
skip the `api-catalog.md` read unless a specific write shape is unclear.)

Before any data-platform call, read `api-catalog.md` once. Do **not** probe response shape
with `jq 'keys'` or `jq '.'`. Do not re-read source files, helper scripts, or
the catalog later to rediscover write shapes; use this runbook's inline
contracts instead. The learning agent uses the routine-safe HTTP tools below:

- **Reads:** `query_raw_sql`, `recall_memory`
- **Writes:** `save_memory`, `update_memory`, `expire_memory`,
  `update_profile`, `write_llm_run`, `write_agent_run`
- **Optional:** `compute_daily_insights` (only if investigating a specific
  recent day during audit), `query_health` (only if a health-specific trait
  needs re-verification)

In `TEST_RUN=1`, production writes are forbidden. The only allowed write tools
are `write_test_llm_run` and `write_test_agent_run`.

Do not use `forget_memory` or `bulk_forget_memory` in normal learner runs. The
routine HTTP surface excludes hard-delete tools; learner cleanup is soft expiry.

---

## Tool access (transport) — decide ONCE, before Step 0

This runbook reaches the data platform two ways. Choose the transport at the
start of the run and use it consistently for every data-platform call.

**Connector mode (preferred — e.g. Cowork).** If tools named
`mcp__steventa-data-platform__<tool>` are present in your toolset, use them for
every data-platform call. In this mode:

- Do **not** export `MCP_BASE_URL` / `MCP_API_KEY`, do **not** call
  `scripts/mcp.sh`, and skip any `list_tools` smoke test — the connector handles
  transport and auth. Confirm readiness by checking these tools exist:
  `query_raw_sql`, `recall_memory`, `save_memory`, `update_memory`,
  `expire_memory`, `update_profile`, `write_llm_run`, `write_agent_run`.
- Each `scripts/mcp.sh <tool> '<json-args>' /tmp/<out>.json` shown below maps
  1:1 to calling `mcp__steventa-data-platform__<tool>` with those same JSON
  args. The tool returns the standard
  `{"status":...,"data":...,"row_count":...}` envelope as text — parse it and
  **write that envelope to the same `/tmp/<out>.json` path the command shows**,
  so the downstream `jq` steps, `scripts/learning_compose.py`, and
  `scripts/validate_payloads.py` run unchanged.
- The write helpers `scripts/write_run.sh` and `scripts/write_agent.sh` wrap the
  curl path. In connector mode, call
  `mcp__steventa-data-platform__write_llm_run` and
  `mcp__steventa-data-platform__write_agent_run` directly with the envelopes
  documented in Stage 5 / `api-catalog.md`, then capture the returned row id from
  the response `data`.
- The connector exposes the production tool set only. `write_test_llm_run` /
  `write_test_agent_run` are not connector tools, so `TEST_RUN=1` artifact
  writes require curl mode (or add those two tools to the adapter).
- **Arg types (the connector schema is strict).** Pass `tool_calls`,
  `output_response`, `input_payload`, and `source_profile_ids` as JSON
  **strings**, not arrays/objects. A bare array is rejected with `Input should
  be a valid string`; wrap it, e.g. `tool_calls="[{\"classification\":{...}}]"`.
- **Results are wrapped.** Each tool returns `{"result":"<envelope>"}` whose
  inner string is the usual `{"status":...,"data":...,"row_count":...}`. Unwrap
  `.result` and write that inner envelope to `/tmp/<out>.json` so the downstream
  `jq`/Python read it unchanged. Bash cannot reach the endpoint (egress wall),
  so anything you need on disk must be written from the connector response.
- **`learning_compose.py` I/O (so you need not open the script):** it reads
  `/tmp/ctx.json` (requires `current_profile.sections` as a JSON object) and
  `/tmp/diff.json` (`section_updates`), and writes the full
  `/tmp/new_sections.json`. The `user_profile` source column is `source_profiles`
  — `source_profile_ids` is only the `update_profile` argument name, so do not
  `SELECT source_profile_ids`.

**Curl mode (Codex / VS Code / Claude Code web, or any shell with network to the
endpoint).** If the connector tools are absent, use everything below exactly as
written — `scripts/mcp.sh`, `scripts/write_run.sh`, `scripts/write_agent.sh` —
with `MCP_BASE_URL` / `MCP_API_KEY` exported by the operator prompt.

Everything else — the SQL, JSON arg shapes, `/tmp` filenames, guards,
`learning_compose.py`, and the Stage 4 audit — is identical in both modes.

---

## Step 0 — Anchor the run

```bash
export TODAY_ET=$(TZ=America/Toronto date +%F)
export RUN_START_ET=$(TZ=America/Toronto date +'%Y-%m-%dT%H:%M:%S%z')
export PIPELINE_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
# The learning agent window is 42 days back from today.
export WINDOW_START_ET=$(TZ=America/Toronto date -d '42 days ago' +%F 2>/dev/null || TZ=America/Toronto date -v-42d +%F)
```

Do not set `MODEL` here. If a routine environment exposes the selected model,
the operator prompt may pass it through; otherwise the write helpers record
`routine-selected`.

In a sandboxed connector session, Bash calls are independent shells — `export`s
do not persist across calls. Write the anchors to a file (e.g.
`/tmp/anchors.env`) and re-source it in later Bash turns, or recompute them.

---

## Stage 0.5 — Fold precheck (cheap short-circuit; run before Stage 1)

At weekly cadence the newest weekly trend is usually already folded. That is
decidable with one small query before loading any heavy payload:

```bash
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT (SELECT max(created_at) FROM llm_runs WHERE run_type='weekly_trend' AND COALESCE(run_scope,'production')='production') AS newest_trend, (SELECT max(created_at) FROM agent_runs WHERE COALESCE(run_scope,'production')='production' AND (goal ILIKE '%learner%' OR goal ILIKE '%behavioral profile%')) AS last_learner, (SELECT max(created_at) FROM user_profile) AS profile_ts\"}" /tmp/foldcheck.json
```

If `newest_trend` is older than BOTH `last_learner` and `profile_ts`, treat the
newest trend as folded and take the no-mutation path: run a **compact** Stage 1
(profile `version` + `change_summary` only — not full `sections`; weekly-trend
ids/dates; and the newest trend's `headline`/`dominant_change` for hypotheses),
confirm in Stage 1.5, skip Stage 2/3 synthesis and the Stage 5a compose preview,
and persist only the Stage 5f/5g audit rows. This is the common path and avoids
pulling the full profile, trend bodies, and prior-run narratives.

If the precheck is ambiguous (a trend newer than the last learner run exists),
fall through to the full Stage 1 below.

---

## Stage 1 — Load inputs (ALL IN ONE TURN, PARALLEL)

Load the four input streams in parallel. Every response goes to a `/tmp/*.json`
file; nothing is pretty-printed. Keep the latest `user_profile.sections` intact
because `scripts/learning_compose.py` needs the full object for preview and
`update_profile`. Keep historical rows compact with bounded text excerpts.

```bash
# 1a) Current user_profile (latest version).
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT version, sections, change_summary, created_at FROM user_profile ORDER BY version DESC LIMIT 1\"}" /tmp/profile_current.json &

# 1b) Production weekly_trend rows in the last 42 days. Pull only the
#     synthesis-relevant fields, not the whole blob (drops source_quality,
#     model_signoff, sources_used, window, etc., ~halving the payload).
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id, created_at, created_at::date AS d, output_response->>'headline' AS headline, output_response->'dominant_change' AS dominant_change, output_response->'negative_trends' AS negative_trends, output_response->'positive_trends' AS positive_trends, output_response->'trends' AS trends FROM llm_runs WHERE run_type = 'weekly_trend' AND COALESCE(run_scope, 'production') = 'production' AND created_at >= NOW() - INTERVAL '42 days' ORDER BY created_at DESC\"}" /tmp/weekly_trends.json &

# 1c) Recent production prior learning_agent runs for continuity, compacted.
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id, goal, created_at, left(final_response::text, 6000) AS final_response_excerpt FROM agent_runs WHERE COALESCE(run_scope, 'production') = 'production' AND (goal ILIKE '%behavioral profile%' OR goal ILIKE '%learner%' OR goal ILIKE '%profile analysis%') ORDER BY created_at DESC LIMIT 6\"}" /tmp/prior_learner_runs.json &

# 1d) Active existing learning_agent memories (both for dedupe and audit).
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id, key, category, left(content::text, 4000) AS content_excerpt, confidence, source, updated_at FROM agent_memory WHERE source = 'learning_agent' AND (expires_at IS NULL OR expires_at > NOW()) ORDER BY updated_at DESC\"}" /tmp/existing_memories.json &

wait
echo "Stage 1 ok: 4 input streams loaded"
```

### Pre-flight staleness guard

If `weekly_trends.json` contains fewer than 2 rows, **abort the run**:

```bash
rows=$(jq '.data | length' /tmp/weekly_trends.json)
if [ "$rows" -lt 2 ]; then
  echo "ABORT: only $rows weekly_trend rows in last 42d — need ≥2 for diff."
  exit 2
fi
```

The learner's value is comparing multiple weekly trends. One trend is not
enough signal to justify a full synthesis run.

---

## Stage 1.5 — Replay / folded-evidence guard

Before synthesis, determine whether the newest production `weekly_trend` row is
already folded into the current profile or a later learner run. Treat evidence
as already folded when the current profile, current profile source IDs if
available, or a later production learner narrative clearly references the same
newest weekly trend/window.

The Stage 0.5 precheck usually settles this: if `newest_trend` predates both the
latest `user_profile` row and the latest production learner run, treat it as
folded (confirm against the prior learner narrative). On a folded result, do not
fetch full `profile.sections` and do not run the Stage 5a compose preview —
report profile preview as `N/A (folded)` and proceed to the no-mutation audit
writes only.

If the newest weekly trend is already folded, the learner must be
**reinforcement-only for production**:

- Do not add profile traits.
- Do not update profile traits except to restate existing active traits as
  reinforcement.
- Do not create, update, or expire memories.
- Do not call `update_profile`, `save_memory`, `update_memory`, or
  `expire_memory`.
- Put any newly noticed interpretation under `hypotheses_for_next_run` as a
  candidate insight to re-check when a newer weekly trend exists.

In `TEST_RUN=1`, it is acceptable to persist the reinforcement/candidate
analysis with `write_test_llm_run` and `write_test_agent_run`, but the diff must
make clear that candidate insights are not eligible for mutation until newer
weekly evidence confirms them.

In production mode, a folded-evidence run may still persist compact no-mutation
audit rows with `write_llm_run` and `write_agent_run`. It must not call
`update_profile`, `save_memory`, `update_memory`, or `expire_memory`.

This guard prevents replay drift: rerunning the learner over the same folded
weekly evidence should not keep creating new durable profile or memory facts.

---

## Stage 2 — Consolidate context (single-pass extraction)

Write a single consolidated context file that Stage 3 reads from. This keeps
Stage 3's input-token cost bounded and makes the synthesis reproducible.

```bash
jq -n \
  --slurpfile profile /tmp/profile_current.json \
  --slurpfile trends /tmp/weekly_trends.json \
  --slurpfile priors /tmp/prior_learner_runs.json \
  --slurpfile mems /tmp/existing_memories.json \
  '{
    current_profile: ($profile[0].data[0] // null),
    weekly_trends: ($trends[0].data // []),
    prior_learner_runs: ($priors[0].data // []),
    existing_memories: ($mems[0].data // [])
  }' > /tmp/ctx.json

echo "Stage 2 ok: context written to /tmp/ctx.json"
jq '{profile_version: .current_profile.version, trends_count: (.weekly_trends | length), priors_count: (.prior_learner_runs | length), memories_count: (.existing_memories | length)}' /tmp/ctx.json
```

### Bootstrap guard

If `current_profile` is null, the `user_profile` table has never been seeded
and this runbook cannot compute a diff. **Abort** and ask the operator to
run `scripts/seed_profile.py` in the data-platform repo first:

```bash
if [ "$(jq -r '.current_profile // "null"' /tmp/ctx.json)" = "null" ]; then
  echo "ABORT: user_profile is empty. Seed it with data-platform scripts/seed_profile.py before running the learning agent."
  exit 2
fi
```

From this point on, read only `/tmp/ctx.json`. Do not re-open the individual
input files.

---

## Stage 3 — Synthesis (the selected-model step)

Read `/tmp/ctx.json` once. Produce a diff document at `/tmp/diff.json` with
this exact shape:

```json
{
  "version_notes": "1-2 sentences on the overall theme of this version bump.",
  "section_updates": {
    "<section_name>": {
      "summary": "updated summary or null",
      "traits_added":   [ { "trait": "...", "type": "positive|anti_pattern", "trait_kind": "behavior_pattern|preference|constraint|anti_pattern|health_correlation|communication_style", "evidence_class": "observed_behavior|self_reported_preference|inferred_mechanism|validated_correlation|contradiction|operational_constraint", "evidence": [...], "confidence": 0.0, "evidence_count": 0, "first_observed": "YYYY-MM-DD", "last_validated": "YYYY-MM-DD" } ],
      "traits_updated": [ { "trait": "...", "trait_kind": "behavior_pattern|preference|constraint|anti_pattern|health_correlation|communication_style", "evidence_class": "observed_behavior|self_reported_preference|inferred_mechanism|validated_correlation|contradiction|operational_constraint", "status": "active|weakened|needs_rescope", "evidence_note": "why this trait strengthened, weakened, or needs rescope", "new_confidence": 0.0, "new_last_validated": "YYYY-MM-DD" } ],
      "traits_removed": [ { "trait": "trait name", "reason": "why it should no longer appear" } ]
    }
  },
  "memories_to_create": [
    { "key": "section_name:trait_slug", "category": "pattern|preference|fact|goal", "content": "Specific, numeric, actionable.", "confidence": 0.0, "source": "learning_agent" }
  ],
  "memories_to_expire": [
    { "key": "section_name:trait_slug", "reason": "why this is no longer true" }
  ],
  "audit_plan": [
    {
      "claim_id": "stable_slug_for_the_claim",
      "claim_path": "JSON path or prose pointer to the exact claim",
      "database": "rescuetime_db|health_db|llm_db|email_db|spotify_data|news_db|context_db",
      "source_table": "table_or_weekly_trend_row_id",
      "formula": "Plain-English formula that exactly matches the SQL",
      "claimed_value": 0.0,
      "tolerance_pct": 5,
      "sql": "SELECT ... AS v ..."
    }
  ],
  "hypotheses_for_next_run": [
    "Unverified-but-suggestive patterns to re-check at the next run."
  ]
}
```

### Synthesis rules

1. **Every numeric claim in `traits_added`, `traits_updated`,
   `memories_to_create`, or `version_notes` must have an `audit_plan` entry**
   with `claim_id`, `claim_path`, `database`, `source_table`, `formula`,
   `claimed_value`, `tolerance_pct`, and executable `sql`. The formula must
   name the exact metric, date/window, denominator, and unit. If you cannot
   write the formula before Stage 4, move the claim to
   `hypotheses_for_next_run`.
2. **Confidence thresholds are strict:**
   - ≥ 0.9: 4+ weeks of consistent signal AND a clear mechanism
   - 0.7–0.89: 3+ weeks AND a plausible mechanism
   - < 0.7: stays in `hypotheses_for_next_run`, not in the profile
3. **A trait can be removed only if** it either contradicts the last 2
   weekly trends, OR has not appeared in any weekly trend for 4+ weeks.
4. **Memories to expire are by key**, not by id. Stage 5 will resolve keys
   using exact-key matching. Stage 5 expires exact canonical keys only.
5. **Do not invent time-of-day patterns** without an hourly query to back
   them up — this is the single most common class of fabrication.
6. **Budget:** No more than 10 traits_added + 10 memories_to_create per
   run. If the selected model wants to add more, it has to drop the weakest
   candidates to fit the cap.
7. Use the live profile section keys from `/tmp/ctx.json` as the source of
   truth. Common live section keys include `career`,
   `communication_preferences`, `confidence_and_caveats`, `current_phase`,
   `decision_psychology`, `distraction_profile`, `future_ai_instructions`,
   `health_patterns`, `identity_life_context`, `interests_and_taste`,
   `learning_style`, `meta`, `relationships_life_design`,
   `systems_and_data`, and `work_patterns`. Do not invent new section keys.
   Do not use `health_correlations`; use `health_patterns` when that key is
   present in `/tmp/ctx.json`.
8. `memories_to_create` may only represent active, runtime-useful traits.
   Do not create memories for weakened, `needs_rescope`, removed, or
   hypothesis-only traits.
9. `memories_to_create` keys must exactly match active trait keys using
   `section_name:trait_slug`.
10. If Stage 1.5 marked the newest weekly trend as already folded, any new
    interpretation must stay in `hypotheses_for_next_run` as a candidate
    insight. Do not place it in `traits_added`, `traits_updated`,
    `traits_removed`, `memories_to_create`, or `memories_to_expire` until a
    newer weekly trend confirms it.

---

## Stage 4 — Evidence audit (MANDATORY)

For every `audit_plan` entry, issue its specified raw-SQL query. Compare
`claimed_value` vs measured value using that entry's `tolerance_pct` (normally
5%). If a claim fails the audit, **remove the claim-bearing trait/memory from
the diff before Stage 5** (do not "fix" the number by guessing — drop the
trait or memory).

The audit runs in **one bash turn** with all queries in parallel:

```bash
# Each audit_plan query writes to /tmp/audit_<claim_id>.json.
# Do not pretty-print the response. Do not run extra exploratory schema probes.

scripts/mcp.sh query_raw_sql "{\"database\":\"rescuetime_db\",\"sql\":\"<query reproducing claim 1>\"}" /tmp/audit_1.json &
scripts/mcp.sh query_raw_sql "{\"database\":\"rescuetime_db\",\"sql\":\"<query reproducing claim 2>\"}" /tmp/audit_2.json &
# ...
wait
```

Then filter `/tmp/diff.json` in place, dropping entries whose claim doesn't
match within ±5%. Log every dropped entry to stderr so the narrative can
explain the cut.

**Specific anti-fabrication checks (learned from v6):**

- **Hourly focus claims:** if a trait says "X% focus during hour H-H+1",
  query RescueTime for that exact hour. If no data exists (e.g., user was
  working out), the claim must be dropped.
- **Device-specific claims:** "Mac-only" means `device = 'macbook'` and
  no `device = 'windows'` rows in the top-10. "Mac-dominant" means > 60%
  Mac share.
- **Focus-percentage claims:** always disambiguate whether the % is raw
  `productivity ≥ 2`, `productivity ≥ 1`, or a weighted/normalised metric.
  Name the formula in the evidence field.
- **"Windows -X%" claims:** always specify whether the metric is Windows
  screen-time hours, Windows focus %, or overall screen-time. The v6 run
  confused these. Disambiguate in the trait content.

---

## Stage 5 — Writes (parallel where safe)

Execute writes in this order. Steps within a group can go in parallel;
groups are sequential.

### 5a. Compose profile preview

Before any production write, run `scripts/learning_compose.py` and require
`/tmp/new_sections.json` to exist. This is the production hard gate that keeps
memory writes and profile writes aligned.

This gate applies to mutation runs only. On a folded / no-mutation run (Stage
0.5 / 1.5) there is no profile or memory write to gate, so skip compose and the
full-profile fetch it needs, and report profile preview as `N/A (folded)`.

```bash
python3 scripts/learning_compose.py || exit 3
test -s /tmp/new_sections.json || exit 3
```

If this step fails in production mode, abort immediately before calling
`expire_memory`, `save_memory`, `update_memory`, `update_profile`,
`write_llm_run`, or `write_agent_run`. In `TEST_RUN=1`, record the compose
failure as a recovered error and continue only to test artifact writes if
`/tmp/diff.json` remains valid; do not mutate profile or memory.

### 5b. Verify memory exact keys (one parallel batch)

For each entry in `diff.memories_to_expire` and `diff.memories_to_create`, call
`recall_memory` with the key as the query, then pick the row whose stored key
matches exactly. This catches typoed keys before writes. `expire_memory` still
receives the exact `key` + `source`; a non-existing key should result in
`expired_count=0`, not a hard-delete attempt.

```bash
jq -r '(.memories_to_expire[]?.key), (.memories_to_create[]?.key)' /tmp/diff.json |
while IFS= read -r key; do
  [ -z "$key" ] && continue
  scripts/mcp.sh recall_memory "{\"query\":\"$key\",\"limit\":3}" /tmp/recall_${key//[^a-zA-Z0-9]/_}.json &
done
wait
# Review only exact source="learning_agent" key matches from the recall files.
```

### 5b-test. TEST_RUN artifact writes only

If `TEST_RUN=1`, stop here after recall verification and compose preview. Do
not execute production steps 5c-5g. `write_test_llm_run` and
`write_test_agent_run` mirror the production request shape but force test
scope server-side, so build the envelopes directly and call `scripts/mcp.sh`
with those test tool names.

Never use `scripts/write_run.sh` or `scripts/write_agent.sh` in `TEST_RUN=1`;
those helpers intentionally target the production `write_llm_run` and
`write_agent_run` tools. Validate the learner agent envelope before the test
write with `python3 scripts/validate_payloads.py --agent-envelope
/tmp/test_agent_body.json`.

Minimum test envelopes:

```json
{
  "run_type": "learning_agent",
  "model": "routine-selected",
  "pipeline_id": "$PIPELINE_ID",
  "step_label": "stage3_diff_test",
  "input_payload": "{\"stage\":\"learner_test\"}",
  "output_response": "{...diff json string...}"
}
```

```json
{
  "goal": "Weekly behavioral profile analysis (TEST RUN)",
  "final_response": "...compact learner narrative...",
  "model": "routine-selected",
  "pipeline_id": "$PIPELINE_ID",
  "tool_calls": "[{\"classification\":{\"run_origin\":\"manual_mcp_test\",\"execution_mode\":\"scheduled_claude\",\"agent_kind\":\"deep_learner\",\"visibility\":\"test\",\"run_scope\":\"test\"}}]"
}
```

After both writes, print only compact row IDs and the final done summary. Do not
print envelope bodies, helper source, catalog excerpts, `/tmp/diff.json`, or
`/tmp/new_sections.json`.

### 5b-prod. No-mutation production shortcut

If Stage 1.5 marked the newest weekly trend as already folded, or if Stage 4
leaves no eligible `section_updates`, `memories_to_create`, or
`memories_to_expire`, skip production mutation steps 5c-5e. Do not call
`expire_memory`, `save_memory`, `update_memory`, or `update_profile`.

Still persist the no-mutation audit trail with steps 5f and 5g. Set
`new_version` to the current profile version and label the narrative as
`NO MUTATION` so downstream readers do not interpret the run as a profile
version bump.

### 5c. Soft-expire stale memories (parallel, mutation runs only)

```bash
# One expire_memory call per exact canonical key.
jq -c '.memories_to_expire[]?' /tmp/diff.json | while read -r entry; do
  key=$(jq -r '.key' <<<"$entry")
  safe_key=${key//[^a-zA-Z0-9]/_}
  scripts/mcp.sh expire_memory "$(jq -n --arg key "$key" '{key:$key, source:"learning_agent"}')" /tmp/expire_${safe_key}.json &
done
wait
```

### 5d. Save or update active memories (parallel, mutation runs only)

For each entry in `diff.memories_to_create`, call `recall_memory` on the
key. If an exact `source="learning_agent"` key exists, update that row with
`update_memory`. Otherwise save.

```bash
jq -c '.memories_to_create[]' /tmp/diff.json | while read -r cand; do
  key=$(jq -r '.key' <<<"$cand")
  safe_key=${key//[^a-zA-Z0-9]/_}
  scripts/mcp.sh recall_memory "{\"query\":\"$key\",\"limit\":3}" /tmp/recall_save_${safe_key}.json
  existing_id=$(jq -r --arg k "$key" '.data[]? | select(.key == $k and .source == "learning_agent") | .id' /tmp/recall_save_${safe_key}.json | head -n 1)
  if [ -n "$existing_id" ]; then
    scripts/mcp.sh update_memory "$(jq -n --argjson id "$existing_id" --arg content "$(jq -r '.content' <<<"$cand")" --arg category "$(jq -r '.category' <<<"$cand")" --argjson confidence "$(jq -r '.confidence' <<<"$cand")" '{memory_id:$id, expected_source:"learning_agent", content:$content, category:$category, confidence:$confidence, clear_expires_at:true}')" /tmp/update_${safe_key}.json &
  else
    scripts/mcp.sh save_memory "$cand" /tmp/save_${safe_key}.json &
  fi
done
wait
```

### 5e. Write the new profile (mutation runs only)

`scripts/learning_compose.py` already applied `diff.section_updates` to
`ctx.current_profile.sections` in Stage 5a and wrote `/tmp/new_sections.json`
(all sections included — the `update_profile` tool does not diff, it stores the
full sections).

```bash
# Source IDs are llm_runs ids only. prior_learner_runs are agent_runs rows
# (UUIDs) and do not belong in source_profile_ids (int[] of llm_runs).
source_ids=$(jq -c '[.weekly_trends[].id]' /tmp/ctx.json)

scripts/mcp.sh update_profile "$(jq -n \
  --arg sections "$(cat /tmp/new_sections.json)" \
  --arg summary "$(jq -r '.version_notes' /tmp/diff.json)" \
  --arg source "$source_ids" \
  '{sections:$sections, change_summary:$summary, source_profile_ids:$source}')" /tmp/profile_write.json

new_version=$(jq -r '.data.version' /tmp/profile_write.json)
```

### 5f. Persist the structured diff to `llm_runs`

Before the narrative write, save the full `diff.json` as a `learning_agent`
row in `llm_runs` so future audits can re-inspect what Stage 3 produced
and what Stage 4 dropped. This is the audit trail that was missing from
v6.

```bash
step_label=stage3_diff
if jq -e '
  (.folded_evidence == true)
  or (((.section_updates // {}) | length) == 0
      and ((.memories_to_create // []) | length) == 0
      and ((.memories_to_expire // []) | length) == 0)
' /tmp/diff.json >/dev/null; then
  step_label=stage3_diff_folded_no_mutation
fi

scripts/write_run.sh learning_agent "$step_label" /tmp/diff.json
```

### 5g. Write the narrative to agent_runs

Compose `/tmp/narrative.txt` with this shape (iOS activity feed). If 5e was
skipped, set `new_version` from `.current_profile.version` in `/tmp/ctx.json`
and use `PROFILE v{current_version} NO MUTATION AUDIT` as the first line:

```
PROFILE v{new_version} SUMMARY
{version_notes verbatim}

---

CHANGES
{For each section: "- <section>: +N added, ~M updated, -P removed"}

---

NEW TRAITS
{For each traits_added: "- <trait> (<section>, confidence <n>)"}

---

EXPIRED
{For each traits_removed + memories_to_expire: "- <trait/memory_key> — <reason>"}

---

HYPOTHESES FOR NEXT RUN
{bullet list from diff.hypotheses_for_next_run}

---

AUDIT RESULTS
{One line per dropped claim from Stage 4: "- DROPPED <trait> (claim: X, measured: Y)"}
```

Then submit. `PIPELINE_ID` is exported in Step 0. Do not export `MODEL` from
this runbook; the helper scripts record `routine-selected` unless the routine
runtime provides a selected model variable.

```bash
if [ -z "${new_version:-}" ]; then
  new_version=$(jq -r '.current_profile.version' /tmp/ctx.json)
fi

goal="Weekly behavioral profile analysis v${new_version}"
if jq -e '
  (.folded_evidence == true)
  or (((.section_updates // {}) | length) == 0
      and ((.memories_to_create // []) | length) == 0
      and ((.memories_to_expire // []) | length) == 0)
' /tmp/diff.json >/dev/null; then
  goal="Weekly behavioral profile analysis (no mutation v${new_version})"
fi

AGENT_KIND=deep_learner AGENT_EXECUTION_MODE=scheduled_claude \
  AGENT_RUN_ORIGIN=claude_weekly_learner_production \
  scripts/write_agent.sh "$goal" /tmp/narrative.txt
```

---

## Failure handling

- If Stage 1 returns fewer than 2 weekly_trend rows → abort (staleness guard).
- If Stage 3 produces zero eligible changes → do not mutate profile or memory.
  Still write compact `llm_runs` and `agent_runs` audit rows with narrative
  "no profile changes this run, hypotheses for next run: ..." so we have a
  paper trail.
- If Stage 4 drops more than 50% of claims → abort. That many fabrications
  means the synthesis went off the rails; investigate before retrying.
- Read-tool 5xx errors may be retried once with a 5s delay. Writes are NOT
  retried — they produce duplicates.

---

## Dedupe and re-run behavior

Every `update_profile` call creates a new version (append-only). If this
runbook is accidentally invoked twice on the same day, you get v7 and v8
with identical `sections` but different `change_summary` timestamps. That
is acceptable — the profile reader always picks the latest.

Every `save_memory` is NOT idempotent, but Stage 5d's recall→update/save
loop provides dedupe at the key level. If the same run is executed twice against
already-folded evidence, Stage 1.5's replay guard forces a no-mutation audit
run instead of creating another profile version or duplicate memories.

---

## Budget and cadence

- **Expected run cost:** Rich Claude synthesis is expensive; keep source reads
  compact and avoid printing payloads.
- **Never run with fewer than 2 weekly trends in the last 42 days.** The
  upstream weekly_profile pipeline must be healthy before this runbook is
  useful.
