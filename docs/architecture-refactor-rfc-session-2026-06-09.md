# Architecture Refactor RFC Session - 2026-06-09

## Scope

This session committed the pending `adapter/` work, then ran the full
improve-codebase-architecture process over the whole repo: multi-lens
exploration, competing interface designs per refactor candidate, comparison,
and five GitHub RFC issues. No production code was changed beyond the commit
below; all refactor work is specified in the RFCs, not yet implemented.

## Commit

- `daf49f8` — `feat(adapter): add learner MCP adapter exposing data-platform REST API`
  - Adds `adapter/README.md`, `adapter/learner_mcp_adapter.py`,
    `adapter/requirements.txt` (the stdio / streamable-HTTP MCP wrapper around
    the platform REST API, for Cowork and other Claude clients).
  - Adds `.venv/` to `.gitignore` so the adapter's 66MB virtualenv stays
    local-only. `__pycache__/` was already ignored.
  - Source files were scanned for hardcoded secrets before committing; none
    present (the README uses `<key>` placeholders, the script reads
    `MCP_API_KEY` from env).

## Exploration (what the friction is)

Six parallel read-only explore agents swept the repo (payload pipeline,
calendar cluster, transport seam, runbook contracts, learner cluster, test
architecture) plus a completeness critic — 41 raw findings, deduplicated into
five candidate clusters:

1. **Briefing payload pipeline** — the payload shape is encoded twice:
   `scripts/payloads.py` (839 lines) builds it, `scripts/validate_payloads.py`
   (1118 lines) re-encodes it as ~30 constant tables and 33 private helpers.
   Device canonicalization duplicated in both; `goal_context` re-interpreted in
   6+ places; two unrelated "is this artifact work" classifiers.
2. **Calendar cluster** — four scripts co-own one concept;
   `DEFAULT_BRIEFING_CALENDAR_ID` hardcoded in three, `CANONICAL_CATEGORIES`
   duplicated (third variant in the validator); event parsing copy-pasted;
   sequencing lives in runbook markdown; the overlap-skip seam is untested.
3. **MCP transport** — five independent call paths to the same REST API; the
   dry-run/live safety gate (`ROUTINE_MODE`/`ALLOW_WRITES`) re-implemented per
   script; retry policy embedded in `mcp.sh` untested; `mcp.sh save_memory` is
   an ungated live write today.
4. **Runbook duplication** — three morning-briefing variants repeat the same
   pipeline as inline bash+SQL prose (replay-guard SQL pasted verbatim in two);
   `test_runbook_contract.py` pins fragments but cannot catch semantic drift.
5. **Learner evidence** — fold/staleness/replay policy split across
   `replay_guard.py` (six untested helpers), `extract.py`, and ~200 lines of
   `learning-agent.md` prose; the skill_pulse migration is smeared across four
   files.

## Design process

For each candidate, three agents produced competing interfaces under different
constraints (minimal / flexible / common-caller-first). 14 of 15 designers
completed; the five judge agents and one designer hit the session usage limit
(reset 11:30pm ET), so the comparison and selection were done in the main
session instead. Total analysis spend: ~2.1M subagent tokens across 27 agents
in two workflows.

Notable convergence: all three payload-module designers independently produced
the same `compose / finalize / check` shape — strong evidence the boundary is
right.

## RFCs filed

| # | RFC | Chosen design | Key hybrid/selection notes |
|---|-----|---------------|----------------------------|
| [#7](https://github.com/sltvoid/winter-routine/issues/7) | Briefing payload contract module (`scripts/briefing.py`: compose / finalize / check) | Minimal (3 CLI verbs, self-describing artifacts via `mode`, finalize always writes for agent repair loops) | Plus declarative overlay/field spec driving placeholders, merge keys, and narrative-check roots |
| [#8](https://github.com/sltvoid/winter-routine/issues/8) | Calendar assess/decide pipeline (one module replaces four scripts) | Common-caller two-verb `assess`/`decide` | Single verb impossible: busy windows must precede AI schedule synthesis. Kills the unused second create-args file. Versioned Decision schema; explicit `skip_started` intent flag |
| [#9](https://github.com/sltvoid/winter-routine/issues/9) | Single MCP client port (`scripts/mcpc.py`, HTTP/SSH/fake transports) | Common-caller (exec shims, `--compat`) | Hardened with all-writes-gated stance (fail closed to dry-run with loud banner); testable retry; `adapter/` becomes a consumer of the same client |
| [#10](https://github.com/sltvoid/winter-routine/issues/10) | Profile-driven pipeline-stage CLI | Flexible (variants as `profiles/*.json`, exit-protocol AI handoffs) | Plus `status` verb / workspace state. Rejected the two-gate conductor's write-reordering: watchdog + replay guard depend on partial-state semantics |
| [#11](https://github.com/sltvoid/winter-routine/issues/11) | `weekly_evidence` gate/finalize module | Minimal (gate/finalize, exit-4 re-invoke loop — the AI agent is the only network transport in connector mode) | Plus in-file policy/origin registries as internals |

## Suggested landing order

`#9 → #8 → #7 → #11 → #10`

- #9 first: safety-critical (single-sources the live-write gate), smallest
  blast radius.
- #10 last: it layers above the other three.
- Every RFC's phase 1 is shims-only with zero runbook edits, so each lands
  without touching the live scheduled runs.

## Loose ends / context notes

- The Claude session was rooted in the empty sibling directory `Winter/`; all
  work happened here in `Winter-Routine`.
- "Apple new documentation" from the original request does not apply to this
  repo — there is no Apple SDK code; iOS only consumes `llm_runs`/`agent_runs`
  rows. Relevant only if the iOS app repo gets its own review.
- Subagent capacity was exhausted near the end of the session (resets 11:30pm
  ET 2026-06-09); judge synthesis was done in-session and issue filing via
  `gh` was unaffected.
