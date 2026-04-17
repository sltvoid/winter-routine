# Learning Agent Runbook

Biweekly behavioral profile analysis. Run on the 1st and 15th of each month
at 2:00 AM ET. Always Opus (never Haiku or Sonnet) — this runbook is
explicitly built for `claude-opus-4-7` because monthly synthesis requires
the most capable model.

Produces:

- 1 row in `agent_runs` (Opus narrative + diff, visible on iOS activity feed)
- 1 row in `user_profile` (next version with updated `sections`)
- N rows added to / removed from `agent_memory` (new derived patterns + expired
  traits)

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
2. **No re-reading of files between stages.** Stages 1–2 write `/tmp/ctx.json`;
   Stage 3 reads that single file and nothing else until Stage 4's audit.
3. **No raw-SQL probing of schema.** Column names are in this runbook or in
   `api-catalog.md`. If a column is missing, the run fails fast with a
   logged error — do not guess.
4. **Batch parallel tool calls in one turn** (Stages 1 and 5).
5. **Stage 4 (evidence audit) is mandatory.** Skipping it produces the
   fabrication class of errors that made v6 need a patch session
   (see data-platform `session-2026-04-17`).

---

## Pre-flight — Read api-catalog.md

Before any curl, read `api-catalog.md` once. Do **not** probe response shape
with `jq 'keys'` or `jq '.'` — if a field path is unclear, re-read the
catalog. The learning agent uses 9 of the 11 HTTP tools:

- **Reads:** `query_raw_sql`, `recall_memory`
- **Writes:** `save_memory`, `forget_memory`, `bulk_forget_memory`,
  `update_profile`, `write_agent_run`
- **Optional:** `compute_daily_insights` (only if investigating a specific
  recent day during audit), `query_health` (only if a health-specific trait
  needs re-verification)

---

## Step 0 — Anchor the run

```bash
export TODAY_ET=$(TZ=America/Toronto date +%F)
export RUN_START_ET=$(TZ=America/Toronto date +'%F %H:%M')
export PIPELINE_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
# Record runs as Opus — picked up by both write_run.sh (Stage 5e) and
# write_agent.sh (Stage 5f). Set here so both turn boundaries inherit it.
export MODEL=claude-opus-4-7
# The learning agent window is 14 days back from today.
export WINDOW_START_ET=$(TZ=America/Toronto date -d '14 days ago' +%F 2>/dev/null || TZ=America/Toronto date -v-14d +%F)
```

---

## Stage 1 — Load inputs (ALL IN ONE TURN, PARALLEL)

Load the four input streams in parallel. Every response goes to a `/tmp/*.json`
file; nothing is pretty-printed.

```bash
# 1a) Current user_profile (latest version).
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT version, sections, change_summary, created_at FROM user_profile ORDER BY version DESC LIMIT 1\"}" /tmp/profile_current.json &

# 1b) All weekly_trend rows in the last 35 days (should be 4-5 rows).
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id, created_at::date AS d, output_response FROM llm_runs WHERE run_type = 'weekly_trend' AND created_at >= NOW() - INTERVAL '35 days' ORDER BY created_at DESC\"}" /tmp/weekly_trends.json &

# 1c) All prior learning_agent runs in the last 35 days for continuity.
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id, goal, created_at::date AS d, final_response FROM agent_runs WHERE goal ILIKE '%behavioral profile%' AND created_at >= NOW() - INTERVAL '35 days' ORDER BY created_at DESC LIMIT 3\"}" /tmp/prior_learner_runs.json &

# 1d) All existing learning_agent memories (both for dedupe and audit).
scripts/mcp.sh query_raw_sql "{\"database\":\"llm_db\",\"sql\":\"SELECT id, key, category, content, confidence, updated_at FROM agent_memory WHERE source = 'learning_agent' ORDER BY updated_at DESC\"}" /tmp/existing_memories.json &

wait
echo "Stage 1 ok: 4 input streams loaded"
```

### Pre-flight staleness guard

If `weekly_trends.json` contains fewer than 2 rows, **abort the run**:

```bash
rows=$(jq '.data | length' /tmp/weekly_trends.json)
if [ "$rows" -lt 2 ]; then
  echo "ABORT: only $rows weekly_trend rows in last 35d — need ≥2 for diff."
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
      "traits_added":   [ { "trait": "...", "type": "positive|negative|neutral", "evidence": [...], "confidence": 0.0, "evidence_count": 0, "first_observed": "YYYY-MM-DD", "last_validated": "YYYY-MM-DD" } ],
      "traits_updated": [ { "trait": "...", "change": "short description", "new_confidence": 0.0, "new_last_validated": "YYYY-MM-DD" } ],
      "traits_removed": [ "trait name" ]
    }
  },
  "memories_to_create": [
    { "key": "domain:short_key", "category": "pattern|fact|goal", "content": "Specific, numeric, actionable.", "confidence": 0.0, "source": "learning_agent" }
  ],
  "memories_to_expire": [
    { "key": "domain:short_key", "reason": "why this is no longer true" }
  ],
  "bulk_expire": [
    { "key_pattern": "some-prefix%", "source": "learning_agent", "reason": "why" }
  ],
  "hypotheses_for_next_run": [
    "Unverified-but-suggestive patterns to re-check at the next run."
  ]
}
```

### Synthesis rules

1. **Every numeric claim in `traits_added`, `memories_to_create`, or
   `version_notes` must cite a specific data source** — either a
   `weekly_trend` row's `trends.<metric>` field or a raw-data query you will
   run in Stage 4. No numbers from memory or prior profile versions alone.
2. **Confidence thresholds are strict:**
   - ≥ 0.9: 4+ weeks of consistent signal AND a clear mechanism
   - 0.7–0.89: 3+ weeks AND a plausible mechanism
   - < 0.7: stays in `hypotheses_for_next_run`, not in the profile
3. **A trait can be removed only if** it either contradicts the last 2
   weekly trends, OR has not appeared in any weekly trend for 4+ weeks.
4. **Memories to expire are by key**, not by id. Stage 5 will resolve keys
   → ids via `recall_memory`.
5. **Do not invent time-of-day patterns** without an hourly query to back
   them up — this is the single most common class of fabrication.
6. **Budget:** No more than 10 traits_added + 10 memories_to_create per
   run. If Opus wants to add more, it has to drop the weakest candidates
   to fit the cap.

---

## Stage 4 — Evidence audit (MANDATORY)

For every `traits_added` and `memories_to_create` entry that contains
a numeric claim, issue a raw-SQL query that reproduces the number. Compare
claim vs measurement with a ±5% tolerance. If any claim fails the audit,
**remove it from the diff before Stage 5** (do not "fix" the number by
guessing — drop the trait).

The audit runs in **one bash turn** with all queries in parallel:

```bash
# Example — adapt the queries to the specific traits in /tmp/diff.json.
# Each query writes to /tmp/audit_<slot>.json. Do not pretty-print.

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

### 5a. Resolve memory-expire keys → ids (one parallel batch)

For each entry in `diff.memories_to_expire`, call `recall_memory` with the
key as the query, then pick the row whose stored key matches exactly.
Store the id mapping in `/tmp/expire_ids.json`.

```bash
jq -c '.memories_to_expire[]' /tmp/diff.json | while read -r entry; do
  key=$(jq -r '.key' <<<"$entry")
  scripts/mcp.sh recall_memory "{\"query\":\"$key\",\"limit\":3}" /tmp/recall_${key//[^a-zA-Z0-9]/_}.json &
done
wait
# Compose /tmp/expire_ids.json from the recall results (jq merge).
```

### 5b. Delete expired memories + bulk-deletes (parallel)

```bash
# One forget_memory call per resolved id.
for id in $(jq -r '.[].id' /tmp/expire_ids.json); do
  scripts/mcp.sh forget_memory "{\"memory_id\":$id}" /tmp/forget_${id}.json &
done

# One bulk_forget_memory call per bulk_expire entry.
jq -c '.bulk_expire[]?' /tmp/diff.json | while read -r entry; do
  scripts/mcp.sh bulk_forget_memory "$entry" /tmp/bulk_forget_$(date +%s%N).json &
done
wait
```

### 5c. Save new memories (parallel, dedupe via recall first)

For each entry in `diff.memories_to_create`, call `recall_memory` on the
key; if an exact-key match already exists, skip. Otherwise save.

```bash
jq -c '.memories_to_create[]' /tmp/diff.json | while read -r cand; do
  key=$(jq -r '.key' <<<"$cand")
  scripts/mcp.sh recall_memory "{\"query\":\"$key\",\"limit\":3}" /tmp/recall_save_${key//[^a-zA-Z0-9]/_}.json
  if jq -e --arg k "$key" '.data[]? | select(.key == $k)' /tmp/recall_save_${key//[^a-zA-Z0-9]/_}.json >/dev/null; then
    continue
  fi
  scripts/mcp.sh save_memory "$cand" /tmp/save_${key//[^a-zA-Z0-9]/_}.json &
done
wait
```

### 5d. Compose and write the new profile

`scripts/learning_compose.py` applies `diff.section_updates` to
`ctx.current_profile.sections` and writes `/tmp/new_sections.json` (all
sections included — the `update_profile` tool does not diff, it stores the
full sections). It exits non-zero on any structural problem (missing remove
target, duplicate trait add, unknown section).

```bash
python3 scripts/learning_compose.py || exit 3

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

### 5e. Persist the structured diff to `llm_runs`

Before the narrative write, save the full `diff.json` as a `learning_agent`
row in `llm_runs` so future audits can re-inspect what Stage 3 produced
and what Stage 4 dropped. This is the audit trail that was missing from
v6.

```bash
scripts/write_run.sh learning_agent stage3_diff /tmp/diff.json
```

### 5f. Write the narrative to agent_runs

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

Then submit. `MODEL` and `PIPELINE_ID` are exported in Step 0; both scripts
pick them up from the env so the iOS feed shows the correct model and the
rows link to the same pipeline.

```bash
scripts/write_agent.sh "Monthly behavioral profile analysis v${new_version}" /tmp/narrative.txt
```

---

## Failure handling

- If Stage 1 returns fewer than 2 weekly_trend rows → abort (staleness guard).
- If Stage 3 produces zero changes → still write a `agent_runs` row with
  narrative "no profile changes this run, hypotheses for next run: ..."
  so we have a paper trail.
- If Stage 4 drops more than 50% of claims → abort. That many fabrications
  means the synthesis went off the rails; investigate before retrying.
- Any single tool 5xx → retry once with a 5s delay. Writes are NOT
  retried — they produce duplicates.

---

## Dedupe and re-run behavior

Every `update_profile` call creates a new version (append-only). If this
runbook is accidentally invoked twice on the same day, you get v7 and v8
with identical `sections` but different `change_summary` timestamps. That
is acceptable — the profile reader always picks the latest.

Every `save_memory` is NOT idempotent, but Stage 5c's recall→skip→save
loop provides dedupe at the key level (not content level). If the same
run is executed twice in a row without enough new weekly trends in
between, Stage 1's staleness guard fires.

---

## Budget and cadence

- **Expected run cost:** ~30k Opus input + ~10k Opus output = ~$0.75 per
  run at current pricing. Biweekly cadence = ~$1.50/month.
- **Never run more often than biweekly.** One weekly_trend row is not
  enough signal to justify the Opus cost — the staleness guard enforces
  this.
- **Never run with fewer than 2 weekly trends in the last 14 days.** The
  upstream weekly_profile pipeline must be healthy before this runbook
  is useful.
