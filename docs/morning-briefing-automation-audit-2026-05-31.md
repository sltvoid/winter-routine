# Morning Briefing Automation Audit - 2026-05-31

Scope: Codex automations under `/Users/steventa/.codex/automations` that match
the Winter-Routine morning briefing pipeline, calendar repair, calendar
watchdog, proof, or legacy canary/dry-run prompts.

No automation definitions were changed during this audit.

## Active Morning Briefing Automations

| ID | Purpose | Schedule | Last run | Recommendation |
| --- | --- | --- | --- | --- |
| `mcp-morning-briefing-clean-canary` | Real daily morning briefing writer. Writes platform rows, agent row, and briefing-calendar events. | Daily 06:00 ET | 2026-05-31 06:01 ET, `PENDING_REVIEW`, summary: writes succeeded; inspect Stage 0 headline preservation | Keep active. This is the primary daily automation. |
| `mcp-morning-briefing-calendar-watchdog-early` | Calendar-only coverage check and repair from the already-written `daily_briefing`. | Daily 06:15 ET | 2026-05-31 06:16 ET, `PENDING_REVIEW`, summary: coverage verified; no repair needed | Keep active. This matches the runbook's first watchdog pass 10-15 minutes after the daily briefing. |
| `mcp-morning-briefing-calendar-watchdog-late` | Second calendar-only coverage check and repair fallback. | Daily 06:55 ET | 2026-05-31 06:55 ET, `PENDING_REVIEW`, summary: no-op verified; main automation can stay active | Conditionally keep active. It matches the runbook's second pass, but it is redundant on days when the early watchdog already verifies coverage. Pause later if early watchdog remains reliable for several consecutive days and review noise matters more than Calendar reliability. |

## Paused Morning Briefing Automations

| ID | Purpose | Schedule | Last run | Recommendation |
| --- | --- | --- | --- | --- |
| `calendar-create-debug-probe` | Calendar-only repair job for an already-written morning briefing. | Paused, daily 09:05 ET rule retained | 2026-05-29 07:58 ET | Keep paused as a manual repair template, or delete if you want zero dormant jobs. Do not reactivate on a schedule while watchdogs are active. |
| `morning-briefing-calendar-write-proof` | One-day proof that a detached automation could write to the briefing calendar. Hard-gated to `TODAY_ET=2026-05-29`. | Paused, Friday 14:05 ET rule retained | 2026-05-29 14:07 ET | Delete. The proof date is past and the prompt itself recommends pausing or deleting after the proof. |
| `mcp-morning-briefing-live-canary` | Older supervised live canary. | Paused, daily 07:05 ET rule retained | 2026-05-23 21:55 ET | Delete or keep only as historical reference. It is superseded by `mcp-morning-briefing-clean-canary` / `MCP Morning Briefing Daily`. |
| `mcp-morning-briefing-routine` | Old dry-run routine. | Paused, daily 07:00 ET rule retained | 2026-05-23 17:10 ET | Delete or keep only as historical reference. It is not part of the live daily path. |

## Adjacent Non-Morning Automation

`email-to-steph-main-calendar-scan` is active at daily 08:35 ET and writes to the
same Steph Main / briefing group calendar, but it is not a morning briefing
automation. Recent runs report no candidates or no changes. Treat it as a
separate email-to-calendar workflow, not a duplicate morning briefing job.

## Cleanup Recommendation

Recommended steady state:

- Keep `mcp-morning-briefing-clean-canary` active.
- Keep `mcp-morning-briefing-calendar-watchdog-early` active.
- Keep `mcp-morning-briefing-calendar-watchdog-late` active for now, then
  revisit after several clean mornings.
- Keep `calendar-create-debug-probe` paused as an emergency/manual repair
  template.
- Delete `morning-briefing-calendar-write-proof`.
- Delete or leave paused the old `mcp-morning-briefing-live-canary` and
  `mcp-morning-briefing-routine`; they are no longer necessary for operations.

## Evidence Checked

- Automation TOML files under `/Users/steventa/.codex/automations/*/automation.toml`.
- Scheduler state from `/Users/steventa/.codex/sqlite/codex-dev.db`.
- Current runbooks:
  - `morning-briefing-clean-canary.md`
  - `morning-briefing-calendar-watchdog.md`
  - `morning-briefing-calendar-repair.md`
