# Weekly Learner Session Summary - 2026-06-02

## Scope

This session focused only on the weekly/deep learner work: Claude Routine prompt design, current data-platform learner infrastructure, MCP contract alignment, and a paused Codex automation for a deeper learner.

Morning briefing details are intentionally out of scope except where they informed output discipline and MCP routine patterns.

## Claude Routine Prompt

We drafted a paste-ready Claude Code Routine prompt for the weekly learner.

Key decisions:

- Use Opus from the Claude Routine UI.
- Do not export `MODEL` globally in the Claude prompt.
- Keep the MCP credential block inline for Claude Routine compatibility, but do not echo or log secrets during execution.
- Treat the learner as a profile/memory update pipeline, not a daily briefing.
- Do not call Google Calendar.
- Require Stage 4 evidence audit before any write.
- Require Stage 5 completion unless a freshness guard cleanly aborts before writes.

The prompt was aligned to current data-platform semantics rather than the older local learner runbook where they conflicted.

## Existing Data-Platform Learner Infrastructure

We checked the data-platform repo and live VM state.

Found infrastructure:

- `ctx-agent-learner`
  - Kubernetes CronJob for the learner.
  - Schedule: `0 2 1,15 * *` in `America/Toronto`.
  - Purpose: durable profile update and learner memory sync.
  - Live VM state observed: `suspend=true`, last schedule `<none>`, image `localhost/context-engine:v44`.

- `ctx-weekly-profile`
  - Kubernetes CronJob for upstream weekly profile evidence.
  - Schedule: Sunday 9 PM ET.
  - Live VM state observed: `suspend=true`, last schedule `2026-03-16T01:00:00Z`, image `localhost/context-engine:v44`.

Conclusion:

- There is an existing learner automation, but it is suspended baseline infrastructure.
- It is not currently the active best path for learner/profile updates.
- The Claude/Codex MCP routine path is the better operator path until we validate output quality.

## Contract Corrections

The main correction was memory lifecycle.

Current HTTP MCP/data-platform contract supports learner memory lifecycle through:

- `save_memory`
- `update_memory`
- `expire_memory`

It should not use:

- `forget_memory`
- `bulk_forget_memory`

Reason:

- HTTP MCP does not expose hard-delete memory tools.
- Durable learner cleanup should be soft-expiry, not hard deletion.
- `learning_agent` memory rows are source-owned and should preserve auditability.

Canonical learner memory keys must follow:

```text
section_name:trait_slug
```

The valid profile sections are:

```text
learning_style
work_patterns
health_correlations
career_patterns
communication_style
distraction_profile
```

Learner traits should preserve the legacy compatibility field:

```text
type = positive | anti_pattern
```

Newer trait taxonomy fields should also be present for added or updated traits:

```text
trait_kind = behavior_pattern | preference | constraint | anti_pattern | health_correlation | communication_style
evidence_class = observed_behavior | self_reported_preference | inferred_mechanism | validated_correlation | contradiction | operational_constraint
status = active | weakened | needs_rescope
```

Runtime memories should only be created for active, runtime-useful traits. Weakened, rescope, removed, or hypothesis-only traits should not become active learner memories.

## Codex Automation Created

We created a new Codex automation:

```text
Deep Learner Profile Update
```

Saved automation ID:

```text
deep-learner-profile-update
```

Current state:

```text
status = PAUSED
rrule = RRULE:FREQ=WEEKLY;BYHOUR=10;BYMINUTE=40;BYDAY=MO
model = gpt-5.5
reasoning_effort = xhigh
execution_environment = local
```

Workspaces:

```text
/Users/steventa/Documents/CodingJunk/Codex/data-platform
/Users/steventa/Documents/CodingJunk/Winter-Routine
```

The automation is paused intentionally because it can mutate:

- `user_profile`
- `agent_memory`
- `llm_runs`
- `agent_runs`

It should stay paused until we inspect a manual weekly learner run and confirm the output quality.

## Deep Learner Automation Shape

The Codex automation is designed to be deeper than the suspended VM learner baseline.

It reads:

- latest `user_profile`
- recent profile history
- recent `weekly_profile_stats`
- recent `weekly_profile_narrative`
- recent `weekly_trend`
- prior learner/profile `agent_runs`
- active learner/runtime-relevant memories
- source freshness across major data stores

It enforces:

- freshness and duplicate guards before writes
- current profile required
- enough weekly evidence required
- no writes if source evidence has not advanced since the latest learner run, unless explicitly replayed
- compact output discipline
- no hard-delete memory tools
- exact learner memory keys
- mandatory evidence audit before writes

It writes, when allowed:

- soft-expired stale learner memories
- saved or updated active learner memories
- new append-only `user_profile` version
- structured `learning_agent` row in `llm_runs`
- user-visible `agent_runs` narrative with `agent_kind=deep_learner`

## Quality Bar

The learner should not summarize weekly reports. It should infer durable patterns across weeks.

Required lenses:

- artifact conversion quality
- device contamination
- AI/chat time versus IDE/editor artifact conversion
- distraction substitution
- recovery versus discipline
- career source-of-truth from current evidence only
- stale career/job-search demotion when current phase is not career search
- down-ranking `context_db`, old Claude exports, and classifier-only career signals unless current sources corroborate them

Confidence thresholds:

- `0.90+`: 4+ weeks of consistent evidence and a clear mechanism.
- `0.70-0.89`: 3+ weeks and a plausible mechanism.
- `<0.70`: hypothesis only, not profile or memory state.

## Recommended Next Step

Run the weekly learner manually with the Claude Routine prompt and inspect:

- whether it passes freshness guards
- whether Stage 4 audit is meaningful
- whether profile changes are specific and evidence-backed
- whether stale career material stays demoted
- whether memory writes use canonical `section_name:trait_slug` keys
- whether output is compact enough for routine use

After that, decide whether to:

- keep the Codex automation paused and adjust the prompt
- enable the Codex automation
- update/unsuspend the VM `ctx-agent-learner`
- keep Claude Routine as the official learner path

## Opus Manual Test Result

Attachment reviewed:

```text
/Users/steventa/.codex/attachments/51ad20cf-34cb-4a9d-981c-ab059bf230e7/pasted-text.txt
```

Transcript size:

```text
18,651 bytes
```

Observed behavior:

- The run used an older Claude Routine learner prompt that still required `forget_memory` and `bulk_forget_memory`.
- The Stage -1 learner MCP smoke test found 13 exposed tools.
- Present relevant tools included `query_raw_sql`, `recall_memory`, `save_memory`, `update_memory`, `expire_memory`, `update_profile`, `write_llm_run`, and `write_agent_run`.
- Missing tools were `forget_memory` and `bulk_forget_memory`.
- Opus stopped before Stage 0 as instructed by the prompt's smoke-test gate.
- No pipeline ID was assigned.
- No learner reads, writes, profile updates, memory writes, or agent run writes were attempted.

Assessment:

- This was a safe abort, not a learner quality result.
- It proves the smoke gate worked and Opus did not improvise destructive memory operations.
- It did not test weekly learner synthesis quality because the pipeline never reached source reads.
- The root cause was prompt drift: the pasted prompt required old hard-delete memory tools.
- The correct fix is to use the revised learner prompt with `expire_memory` and `update_memory`, not to reintroduce `forget_memory` or `bulk_forget_memory`.

Next test requirement:

- Re-run Claude Routine with the corrected prompt only.
- Stage -1 should require `expire_memory` and `update_memory`.
- Stage 5 should soft-expire stale memories and upsert active memories.
- Hard-delete memory tools should remain out of scope.

## Repo Fix After Opus Test

The Opus transcript showed the pasted prompt and checked-in learner references could still pull the routine toward old hard-delete memory tools.

Repo updates made:

- `learning-agent.md`
  - changed from biweekly/monthly wording to weekly/deep learner wording
  - removed `MODEL` export from the runbook
  - changed the evidence window to 42 days
  - replaced `forget_memory` and `bulk_forget_memory` with `expire_memory` and `update_memory`
  - changed Stage 5 to soft-expire stale memories and update/save exact-key active learner memories
  - aligned trait schema with `type`, `trait_kind`, `evidence_class`, `status`, and canonical `section_name:trait_slug` memory keys

- `api-catalog.md`
  - replaced old hard-delete memory tool entries with `update_memory` and `expire_memory`
  - documented that the live tool list is authoritative and normal learner runs should not call hard-delete tools

- `scripts/mcp.sh`
  - marked `update_memory` and `expire_memory` as write tools so they are not retried

- `scripts/learning_compose.py`
  - added support for object-form `traits_removed`
  - added support for section `summary`
  - added support for updated taxonomy/status fields on existing traits

Verification:

- `bash -n scripts/mcp.sh scripts/write_run.sh scripts/write_agent.sh`
- focused import test for `scripts/learning_compose.py` covering object removals, summary update, taxonomy/status overlay, and trait add

## Opus Retry After Repo Fix

Attachment reviewed:

```text
/Users/steventa/.codex/attachments/a3c8e09f-5f60-4888-a81c-ce6227b0466d/pasted-text.txt
```

Transcript size:

```text
15,932 bytes
```

Observed behavior:

- Claude Routine fetched and fast-forwarded the repo successfully.
- Git HEAD used by the run was:

```text
a8a111aca8df38a9d3ca7c9391944db12e880891
```

- This confirmed GitHub `main` contained the repo-side learner lifecycle fix.
- The checked-in runbook was correct and explicitly pointed at `expire_memory` and `update_memory`.
- The Claude Routine UI prompt was still stale and still required `forget_memory` and `bulk_forget_memory`.
- The Stage -1 smoke gate failed on those two missing hard-delete tools.
- Opus stopped before Stage 0.
- No pipeline ID was assigned.
- No Stage 1 reads happened.
- No writes happened to `user_profile`, `agent_memory`, `llm_runs`, or `agent_runs`.

Assessment:

- The repo fix worked.
- The remaining blocker was the pasted Claude Routine prompt in the UI.
- This was again a safe pre-pipeline abort, not a learner quality result.
- The run still did not test Stage 3 synthesis quality or Stage 5 write quality.

Corrected Claude Routine prompt requirements:

```text
query_raw_sql
recall_memory
save_memory
update_memory
expire_memory
update_profile
write_llm_run
write_agent_run
```

Prompt cleanup required:

- Remove `forget_memory` from the required-tools list.
- Remove `bulk_forget_memory` from the required-tools list.
- Replace any "delete expired memories" wording with soft expiry via `expire_memory`.
- Replace memory dedupe/save wording with exact-key update-or-save via `update_memory` and `save_memory`.
- Keep `MODEL` unexported; Opus is selected in the Claude Routine UI.

Next test:

- Paste the corrected Routine prompt into Claude Routine.
- Re-run with Opus selected.
- Expected outcome: Stage -1 should pass; the next meaningful result will be either a freshness guard abort after Stage 1.5 or a full Stage 5 learner run.

## Codex Scheduled Test-Run Fix

Problem:

- Manual continuation could reach HTTPS MCP and write test rows.
- Scheduled Codex automation runs were blocking before Stage 1 when HTTPS MCP DNS/connectivity failed.
- Native `mcp__data_platform` had read tools, but the scheduled test-row path needed native `write_test_llm_run` and `write_test_agent_run` so it would not fall back to production write tools.

Repo fix:

- Data-platform branch `codex/run-scope-test-tools` contains commit `6259840 feat(mcp): add scoped test run write tools`.
- The branch is pushed to `origin/codex/run-scope-test-tools`.
- The commit adds scoped test-write behavior across MCP/API contracts so learner comparison rows can be written with:
  - `run_scope='test'`
  - `source='manual_mcp_test'`
- Focused branch verification:

```text
/Users/steventa/.venvs/data-platform-mcp/bin/python -m pytest mcp-server/tests/test_write.py -q
43 passed in 0.17s
```

Local Codex config fix:

- Added these local data-platform MCP tool entries to `/Users/steventa/.codex/config.toml`:
  - `write_test_agent_run`
  - `write_test_llm_run`
- Updated `/Users/steventa/.codex/automations/deep-learner-profile-update/automation.toml` and the persisted automation DB prompt so the learner test-run path:
  - tries HTTPS MCP first
  - falls back to native data-platform tools only when `query_raw_sql`, `recall_memory`, `write_test_llm_run`, and `write_test_agent_run` are all available
  - keeps production writes forbidden

Proof collected:

- Public HTTPS MCP currently returns `status=ok`, `15` tools, including:
  - `query_raw_sql`
  - `recall_memory`
  - `write_test_agent_run`
  - `write_test_llm_run`
- The local data-platform MCP server self-registration lists:
  - `write_agent_run`
  - `write_llm_run`
  - `write_test_agent_run`
  - `write_test_llm_run`
- A fresh `codex exec` process reported:

```text
visible=yes
evidence=Tool discovery exposed both `mcp__data_platform.write_test_llm_run` and `mcp__data_platform.write_test_agent_run` in this process without invoking them.
```

- A running Codex Desktop app-server probe also reported:

```text
visible=yes
Evidence: Tool discovery exposed `mcp__data_platform.write_test_llm_run` and `mcp__data_platform.write_test_agent_run`; neither write tool was called.
```

Automation state:

- `deep-learner-profile-update` was restored to `PAUSED`.
- Schedule remains:

```text
RRULE:FREQ=WEEKLY;BYHOUR=10;BYMINUTE=40;BYDAY=MO
model=gpt-5.5
reasoning_effort=xhigh
```

Direct SQLite trigger note:

- Setting `next_run_at` directly did not cause the already-running Codex Desktop app-server to start a new automation thread.
- No new automation thread was created by that probe.
- Existing recent test rows remained the prior manual/test runs; no new proof-trigger rows were added.

Operational conclusion:

- The repo-side and config-side fixes are in place.
- Fresh Codex processes can see the native test-write tools.
- The running Codex Desktop app-server can also see the native test-write tools.
- The remaining unproven step is a full scheduled learner run; the tool availability blocker is fixed.

## Desktop-Managed Full Prompt Proof

A full saved-prompt learner proof was run through the Codex Desktop app-server
using the persisted `deep-learner-profile-update` prompt. This is the closest
available manual trigger for the Desktop-managed execution path; the local CLI
does not expose a first-class "run this scheduled automation now" command.

Result:

- `pipeline_id`: `ffb18993-fa2f-4fcc-87ba-8ebcb3a9d0fa`
- Transport used by the run: `native_data_platform_fallback`
- HTTPS probe result inside the run: `failed_retry_rc_7`
- Git head accepted by the run: `117327d1a5cd550729490ad0b261fa249f5d909a`
- Profile: v15
- Newest weekly evidence: `llm_runs.id=3248`, `2026-05-28`
- Folded status: already folded; reinforcement-only diff
- Profile preview: `ok`, `sections=15`
- Audit: `5 passed`, `0 dropped`
- `write_test_llm_run`: `llm_runs.id=3331`
- `write_test_agent_run`: `agent_runs.id=7615209b-c2e8-480d-a090-f7c221a4313b`

Independent HTTPS MCP verification confirmed both rows:

```text
llm   3331                                  pipeline=ffb18993-fa2f-4fcc-87ba-8ebcb3a9d0fa run_scope=test source=manual_mcp_test label=learning_agent step=stage3_diff_test
agent 7615209b-c2e8-480d-a090-f7c221a4313b pipeline=ffb18993-fa2f-4fcc-87ba-8ebcb3a9d0fa run_scope=test source=manual_mcp_test goal=Weekly behavioral profile analysis (TEST RUN)
```

Root cause of "manual works, scheduled fails":

- The successful manual path used direct HTTPS MCP and already had network
  access when it ran.
- The failed scheduled runs stopped in preflight when HTTPS MCP could not be
  reached from that runner context.
- At that point the native Codex `data-platform` surface did not yet expose
  `write_test_llm_run` and `write_test_agent_run`, so the prompt correctly
  aborted before Stage 1 instead of risking production writes.
- After the data-platform scoped test-write tools were added and Codex config
  approval entries were registered, fresh Codex processes and the running
  Desktop app-server could both see the native test-write tools.

Prompt fixes applied after the proof:

- Added a quote-safe date-anchor rule because the proof generated
  `RUN_START_ET=2026-06-02 13:31` in a sourced env file, which bash treated as
  an invalid second command.
- Added a native fallback compactness rule because native `query_raw_sql`
  streamed large `sections`, `output_response`, and `final_response` JSON into
  the protocol log. The final `/tmp` artifacts were small, but the tool stream
  still inflated context.
- Mirrored the updated automation prompt into
  `/Users/steventa/.codex/sqlite/codex-dev.db`; the automation remains
  `PAUSED` with the same weekly schedule and `model=gpt-5.5`.

Conclusion:

- The original automated blocker is fixed: the scheduled/Desktop Codex path can
  now fall back to native test-write tools and complete Stage 5 with test rows
  only.
- The next scheduled run should be cheaper and less fragile because the prompt
  now forbids unquoted sourced date values and large native SQL result streams.

## Replay Guard Decision

Decision:

- Claude remains the preferred weekly learner writer because it produced richer
  synthesis than the Codex control path.
- Already-folded weekly evidence must force reinforcement-only production
  behavior.
- New interpretations from already-folded evidence may be preserved as
  candidate insights, but they are not eligible for profile or memory mutation
  until a newer weekly trend confirms them.

Reason:

- Claude row `3332` usefully surfaced
  `health_patterns:recovery_not_the_bottleneck`, but it came from evidence that
  profile v15 had already folded.
- Letting replayed evidence create durable profile traits or memories would
  create retroactive drift.
- Keeping those observations in `hypotheses_for_next_run` preserves the richer
  thinking while making production writes depend on fresh evidence.

Runbook update:

- Added `Stage 1.5 -- Replay / folded-evidence guard` to
  `learning-agent.md`.
- Added a synthesis rule that keeps new interpretations from already-folded
  evidence out of `traits_added`, `traits_updated`, `traits_removed`,
  `memories_to_create`, and `memories_to_expire`.
