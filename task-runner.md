# Task Runner — commissioned-research executor

The external half of the commissioned-agents loop (data-platform spec
`docs/specs/2026-07-25-email-actuation-and-commissioned-agents-spec.md` §6,
ADR 0013 Decision 3). The operator commissions *thinking* via a tap; this
routine picks the commission up, does grounded research against the
platform's own data, writes an artifact, and reports back with ONE outcome
email. It is dispatch path 2 (the Mac-independent spine) — the Mac launchd
fast path (`data-platform/mac-agent/task-runner/`) runs the same contract
every 30 minutes and will usually get there first; this routine exists so a
dead or asleep Mac only *delays* commissions. Runs daily; model selected in
the routine UI. Processing the same commission twice is wasteful but
harmless (artifacts are append-only); Stage 0 de-dups against existing
artifacts before doing any work.

**Commissioned-agent contract (ADR 0013, verbatim — read before every
run):** "read everything; write artifacts and inert drafts only; one
outcome email per commission; grounded-research rules (cite queries,
blocked-over-fiction); no deploys, no config, no enforcement writes, no
state jumps past human gates. A wrong analysis can cost a bad read, never a
bad actuation."

This routine therefore NEVER: edits ConfigMaps or manifests, runs kubectl,
changes any ticket's `status`, approves/rejects anything, or sends more
than one email per commission. Prepared actions (direction/goal-policy/
program draft proposals) are *described in the artifact* for the operator —
the draft-creation CLIs (`direction_admin`, `goal_policy_review`,
`program_admin`) are in-pod, session-only surfaces, not this routine's.

Every tool call uses `scripts/mcp.sh` against the MCP HTTP subset
(`$MCP_BASE_URL` + `$MCP_API_KEY`). Live writes require `ROUTINE_MODE=live`
and `ALLOW_WRITES=1` (the wrapper refuses `write_agent_run` otherwise);
diagnostic runs export `ROUTINE_MODE=dry_run ALLOW_WRITES=0` and print
would-write payloads instead.

---

## Output discipline (READ FIRST)

Same rules as the morning briefing: save responses to `/tmp/*.json` with the
third `mcp.sh` argument, extract single fields with `jq -r`, no full-payload
pretty-prints, no stage banners, batch independent reads in one turn. A
commission run is small — budget target is 2 commissions end-to-end in
under ~15 turns.

## Stage 0 — Read the commission queue

```bash
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT id, slug, title, research_question, target_scope, expected_artifact, requested_authority, evidence_refs, why_now_priority, created_at, metadata FROM delegation_tickets WHERE status = '"'"'research_ready'"'"' AND metadata->>'"'"'assignee'"'"' = '"'"'external_claude'"'"' ORDER BY created_at LIMIT 2"}' /tmp/commission_queue.json
```

- **Empty queue ⇒ done.** Exactly one line ("Task runner: no commissions
  pending") and stop. No writes, no email, no filler.
- **LIMIT 2 per run is a hard cap** — commissions are bounded work, not a
  backlog drain. Older first (`ORDER BY created_at`).
- De-dup: for each ticket, check for an existing artifact note
  (`search_notes` is not on the HTTP subset, so query directly):

```bash
scripts/mcp.sh query_raw_sql '{"database":"llm_db","sql":"SELECT id, created_at FROM notes WHERE kind = '"'"'commission_artifact'"'"' AND metadata->>'"'"'ticket_id'"'"' = '"'"'<TICKET_ID>'"'"' ORDER BY created_at DESC LIMIT 1"}' /tmp/commission_dedup.json
```

  A hit means another dispatch path already ran this commission — skip it
  with one status line, do not re-research, do not re-email.

## Stage 1 — Grounded research (per commission)

Read tools ONLY: `query_raw_sql`, `query_table`, `list_data_sources`,
`describe_data_source`, `get_source_freshness`, `list_agent_outputs`,
`get_run_detail`, `query_emails`, `query_health`, `query_calendar`,
`query_browser_activity`, `recall_memory`, `get_direction`,
`get_active_program`. Respect the schema gotchas (`ts_utc::timestamp`
ET-cast, finance seam/sign rules, EAV health) — they live in data-platform
CLAUDE.md and the `describe_data_source` tips.

Grounding rules (the platform's own researcher prompt, 2026-07-21, adopted
here verbatim in substance):

1. **Every factual claim in the artifact MUST come from a query you ran or
   from the ticket text itself.** Cite the claim to the query — each
   `evidence_refs` entry names the table(s) and the query's shape or exact
   SQL, so a reviewer can re-run it.
2. **Do not invent tables, thresholds, queue sizes, mechanisms, or
   infrastructure details.**
3. **Blocked-over-fiction:** if your queries cannot establish what the
   ticket asks, say exactly that in `finding_summary` and set
   `recommendation` to `blocked` — "an honest 'insufficient evidence' beats
   a plausible fiction" (`agent/delegation_ticket_llm.py`,
   `RESEARCH_GROUNDING_PROMPT`; spec §6: "cite queries,
   blocked-over-fiction"). A blocked artifact is a successful run.
4. Bounded: aim for ≤8 queries per commission; stop when the research
   question is answered or provably unanswerable from the data.

## Stage 2 — Write the artifact

Artifact shape mirrors the in-VM researcher's contract
(`RESEARCH_ARTIFACT_FIELDS`) so the two paths stay comparable — a JSON
object with ALL of: `finding_summary`, `evidence_refs`,
`recommended_next_action`, `implementation_plan`, `risk_notes`,
`blast_radius_notes`, `likely_touched_files_or_systems`, `test_plan`,
`recommendation` (one of `approve|reject|blocked|split`).

**Prepared actions live IN the artifact.** When the finding warrants a
direction/goal-policy/program change, `recommended_next_action` carries the
full prepared draft content (paste-ready JSON or CLI invocation) plus one
line flagging it for the operator-queue email — this routine never invokes
the draft CLIs itself.

Persist (both writes per commission, in this order):

1. **Narrative** via `write_agent_run` — goal exactly
   `Commission <ticket-id> research`, `final_response` = a plain-text
   narrative: finding first, then evidence citations, then the
   recommendation. (`agent_runs.source` lands as `manual_mcp`;
   `model` = the routine-UI-selected model.)

```bash
scripts/mcp.sh write_agent_run "$(jq -nc --arg goal "Commission <TICKET_ID> research" --arg resp "$(cat /tmp/commission_narrative.txt)" --arg model "$SELECTED_MODEL" '{goal:$goal, final_response:$resp, model:$model, tool_calls:"[]"}')" /tmp/commission_run_write.json
```

2. **Artifact body** as a note, `kind='commission_artifact'`,
   `metadata.ticket_id` = the ticket UUID (the Stage 0 de-dup key). The
   note tools are NOT on the MCP HTTP subset (`api/mcp_router.py`
   deliberately excludes them), so **on this dispatch path the artifact
   JSON is embedded verbatim at the end of the `write_agent_run` narrative**
   under a literal `--- ARTIFACT JSON ---` marker, and the run notes "note
   write unavailable on HTTP subset". The Mac fast path (full local
   toolset) writes the real `save_note` row. Do not fake the note via
   `query_raw_sql` — `mcp_reader` is SELECT-only and the raw-SQL tool must
   never be a write side door.

## Stage 3 — ONE outcome email

One email per commission, no exceptions — a second finding waits for the
next run. `send_email` is also NOT on the MCP HTTP subset: on this dispatch
path, compose the full email body, embed it in the artifact narrative under
`--- OUTCOME EMAIL (undeliverable from HTTP path) ---`, and rely on the
operator-queue dispatch email to carry the pointer; the Mac fast path sends
it for real via the local `send_email` tool.

Email format (both paths):

- Subject starts with `[Commission] <ticket slug or short title>` (the
  send tool adds its own `[Agent]` prefix — final subject reads
  `[Agent] [Commission] …`).
- Body ≤15 lines, plain text. Line 1 = the finding, one sentence. Then
  2–4 evidence lines (each citing its query). End with the recommended
  tap: what the operator should approve/reject/commission next, one line.
- No preamble, no sign-off boilerplate, no attachments.

## Stage 4 — Mark progress

No MCP write tool exists for ticket state (verified 2026-07-25: neither
`mcp-server/tools/` nor the HTTP registry exposes any `delegation_tickets`
writer), and the contract forbids state jumps anyway. So:

- **Leave the `research_ready → researching → research_complete` transition
  to the platform** (the operator-queue dispatch / steward wakeup pass owns
  ticket-state hygiene).
- Completion is recorded by Stage 2's two writes: the
  `commission_artifact` note (or its embedded fallback) + the `agent_runs`
  row with goal `Commission <ticket-id> research`. That pair IS the
  done-signal the de-dup check reads.

## Definition of done (per run)

- Every picked commission (≤2) has: an artifact with all nine fields, every
  claim cited, `recommendation` set (`blocked` is legal and honorable); one
  `agent_runs` row (goal `Commission <id> research`); one outcome email
  sent (Mac path) or embedded (HTTP path).
- Zero writes outside: notes (`commission_artifact`), `agent_runs`, the one
  email. Zero ticket-status changes. Zero config/deploy/enforcement
  touches.
- Empty queue runs produce one status line and nothing else.

## Signoff

2026-07-25 ET · commissioned-agents build session — initial version per
spec §6 / ADR 0013 (email actuation + commissioned external agents).
