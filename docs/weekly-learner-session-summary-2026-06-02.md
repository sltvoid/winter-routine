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
