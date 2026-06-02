# Learning Agent Runbook

Weekly/deep behavioral profile analysis. Run manually or on the weekly routine
cadence after upstream weekly profile evidence exists. Use Opus selected in the
Claude Routine UI. Do not export `MODEL`; the shell write helpers default to
`routine-selected` when the routine runtime does not expose a model variable.

Produces:

- 1 row in `agent_runs` (Opus narrative + diff, visible on iOS activity feed)
- 1 row in `user_profile` (next version with updated `sections`)
- N rows added, updated, or soft-expired in `agent_memory` (new active derived
  patterns plus stale trait expiry)

Reads (no writes) from: `llm_runs` (prior weekly_trend rows + prior
learning_agent rows), `user_profile` (current version), `agent_memory`
(existing learning_agent memories), raw tables when doing the evidence
audit.

---

## Output discipline (READ FIRST — Opus is expensive)

This runbook uses Opus, which costs ~8× Haiku per token. The morning-briefing
runbook's "60% budget remaining" rule is tighter here: aim to enter Stage 3
(the synthesis) with **at least 75% of your turn budget remaining** so Opus
has room to think.

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

Before any curl, read `api-catalog.md` once. Do **not** probe response shape
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

## Step 0 — Anchor the run

```bash
export TODAY_ET=$(TZ=America/Toronto date +%F)
export RUN_START_ET=$(TZ=America/Toronto date +'%F %H:%M')
export PIPELINE_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
# The learning agent window is 42 days back from today.
export WINDOW_START_ET=$(TZ=America/Toronto date -d '42 days ago' +%F 2>/dev/null || TZ=America/Toronto date -v-42d +%F)
```

Do not set `MODEL` here. If a routine environment exposes the selected model,
the operator prompt may pass it through; otherwise the write helpers record
`routine-selected`.

---

## Stage 1 — Load inputs (ALL IN ONE TURN, PARALLEL)

Load the four input streams in parallel. Every response goes to a `/tmp/*.json`
file; nothing is pretty-printed.

```bash
# 1a) Current user_profile (latest version).
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT version, sections, change_summary, created_at FROM user_profile ORDER BY version DESC LIMIT 1\"}" /tmp/profile_current.json &

# 1b) Production weekly_trend rows in the last 42 days.
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id, created_at::date AS d, output_response FROM llm_runs WHERE run_type = 'weekly_trend' AND COALESCE(run_scope, 'production') = 'production' AND created_at >= NOW() - INTERVAL '42 days' ORDER BY created_at DESC\"}" /tmp/weekly_trends.json &

# 1c) Recent production prior learning_agent runs for continuity.
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id, goal, created_at, final_response FROM agent_runs WHERE COALESCE(run_scope, 'production') = 'production' AND (goal ILIKE '%behavioral profile%' OR goal ILIKE '%learner%' OR goal ILIKE '%profile analysis%') ORDER BY created_at DESC LIMIT 6\"}" /tmp/prior_learner_runs.json &

# 1d) Active existing learning_agent memories (both for dedupe and audit).
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id, key, category, content, confidence, source, updated_at FROM agent_memory WHERE source = 'learning_agent' AND (expires_at IS NULL OR expires_at > NOW()) ORDER BY updated_at DESC\"}" /tmp/existing_memories.json &

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
enough signal to justify an Opus run.

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

## Stage 3 — Synthesis (the Opus step)

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
   run. If Opus wants to add more, it has to drop the weakest candidates
   to fit the cap.
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

### 5c. Soft-expire stale memories (parallel)

```bash
# One expire_memory call per exact canonical key.
jq -c '.memories_to_expire[]?' /tmp/diff.json | while read -r entry; do
  key=$(jq -r '.key' <<<"$entry")
  safe_key=${key//[^a-zA-Z0-9]/_}
  scripts/mcp.sh expire_memory "$(jq -n --arg key "$key" '{key:$key, source:"learning_agent"}')" /tmp/expire_${safe_key}.json &
done
wait
```

### 5d. Save or update active memories (parallel, dedupe via recall first)

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

### 5e. Write the new profile

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
scripts/write_run.sh learning_agent stage3_diff /tmp/diff.json
```

### 5g. Write the narrative to agent_runs

Compose `/tmp/narrative.txt` with this shape (iOS activity feed):

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
AGENT_KIND=deep_learner AGENT_EXECUTION_MODE=scheduled_claude \
  scripts/write_agent.sh "Weekly behavioral profile analysis v${new_version}" /tmp/narrative.txt
```

---

## Failure handling

- If Stage 1 returns fewer than 2 weekly_trend rows → abort (staleness guard).
- If Stage 3 produces zero changes → still write a `agent_runs` row with
  narrative "no profile changes this run, hypotheses for next run: ..."
  so we have a paper trail.
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

Every `save_memory` is NOT idempotent, but Stage 5c's recall→update/save
loop provides dedupe at the key level. If the same run is executed twice in a
row without enough new weekly trends in between, Stage 1's staleness guard
fires.

---

## Budget and cadence

- **Expected run cost:** Opus is expensive; keep source reads compact and avoid
  printing payloads.
- **Never run with fewer than 2 weekly trends in the last 42 days.** The
  upstream weekly_profile pipeline must be healthy before this runbook is
  useful.
