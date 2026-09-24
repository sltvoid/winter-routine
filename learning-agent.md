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
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id::text AS id, status, source, valid_from::text AS valid_from, valid_until::text AS valid_until, (operator_input IS NOT NULL AND operator_input NOT IN ('[]'::jsonb, '{}'::jsonb, 'null'::jsonb)) AS has_operator_input, recompose_count FROM program_versions WHERE valid_from >= '$WINDOW_START_ET' ORDER BY valid_from\"}" /tmp/program_versions.json &
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
      "source_table": "rep_days|rep_weeks|program_versions|proactive_interventions|apple_health_daily_metrics_v2|hevy_workouts|rescuetime_activity_slice|agent_memory",
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
3. **A trait can be removed only if** it is contradicted by the evidence
   packet in two consecutive monthly runs, OR nothing in the packet's 90-day
   window supports it.
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
10. If Stage 1.5 marked the run folded or sparse, any new interpretation
    stays in `hypotheses_for_next_run`. Do not place it in `traits_added`,
    `traits_updated`, `traits_removed`, `memories_to_create`, or
    `memories_to_expire` until a later packet confirms it.

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
- **Floor truth is the ledger:** rep floors come from `rep_days.floor_met`
  (the nightly verifier), never recomputed RescueTime sums.
- **Focus %** = `SUM(seconds WHERE productivity >= 1) / SUM(seconds)`; name
  the threshold in the formula. `ts_utc` is ET-as-UTC — cast `::timestamp`.
- Postgres has no `ROUND(double precision, int)` — `ROUND(x::numeric, 2)`.

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
  "goal": "Monthly behavioral profile analysis (TEST RUN)",
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

If Stage 1.5 marked the run folded or sparse, or if Stage 4
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
# source_profile_ids is int[] of llm_runs ids; the lifeOS packet has no
# llm_runs provenance, so cite the prior learner diff rows instead.
source_ids=$(jq -c '[.prior_learner_runs[]?.id | select(type == "number")]' /tmp/ctx.json)
[ "$source_ids" = "[]" ] && source_ids='[]'

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

goal="Monthly behavioral profile analysis (lifeOS v${new_version})"
if jq -e '
  (.folded_evidence == true)
  or (((.section_updates // {}) | length) == 0
      and ((.memories_to_create // []) | length) == 0
      and ((.memories_to_expire // []) | length) == 0)
' /tmp/diff.json >/dev/null; then
  goal="Monthly behavioral profile analysis (lifeOS v${new_version}, no mutation)"
fi

AGENT_KIND=deep_learner AGENT_EXECUTION_MODE=scheduled_claude \
  AGENT_RUN_ORIGIN=claude_monthly_learner_production \
  scripts/write_agent.sh "$goal" /tmp/narrative.txt
```

After the narrative, write the iOS digest row (spec 2026-07-03-ios-digest —
`GET /api/winter/digest` serves it as cards; restate facts already in the
narrative, no new analysis). On a no-mutation run set `mutations` to
"none — sparse month" or "none — evidence folded" accordingly:

```bash
scripts/mcp.sh write_llm_run "$(jq -nc \
  --arg out "$(jq -nc \
    --arg v "<verdict, <=120 chars>" \
    --arg m "<mutations summary, <=120>" \
    --arg h "<top hypothesis, <=160>" \
    --arg w "<next window, <=120>" \
    '{verdict:$v,mutations:$m,top_hypothesis:$h,next_window:$w}')" \
  '{run_type:"learner_digest",model:"routine-selected",output_response:$out,step_label:"stage5g_ios_digest"}')" /tmp/learner_digest_write.json
```

In DIAGNOSTIC mode print the would-write digest JSON (one line per field)
instead of calling the write tool.

---

## Failure handling

- Fewer than 4 rep_weeks rows in the window → sparse → no-mutation audit run (never an abort).
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
- **Cadence:** first Sunday of the month, ~12:00 ET; every other Sunday the
  paste-body gate skips in ~30 s. Commissioned runs on phase changes say so
  in the triggering message.

## Signoff

2026-09-23 ET · operator session — rewritten on the lifeOS ledgers (spec
Design C): Stage 1 = 12 reads, Stage 1.2 = `scripts/learner_evidence.py`
packet, sparse guard replaces the weekly-trend abort, goal string
`Monthly behavioral profile analysis (lifeOS vN)`, credentials via
`/tmp/mcp.env`. (History in git.)
