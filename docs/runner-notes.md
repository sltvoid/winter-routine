# Runner Notes — model-tailored prompt blocks (canonical copies)

The gitignored paste bodies (`claude-routine-*.md`) each carry a
`## Model Notes` section tailored to the runner that typically executes them
(**Opus 4.8** as of 2026-07-02). This file is the git-tracked canonical copy of
those blocks, so they are versioned and reviewable even though the paste bodies
(which carry the live key) are not. When the operator switches a routine's
runner (e.g. to a GPT-class model), add that model's block here first, then
mirror into the paste body.

Quality reference: data-platform `docs/reference/fable-analysis-fidelity.md`
(the seven analysis signatures + the 6-point acceptance check). The blocks
below compress those signatures into per-pipeline imperatives, weighted toward
Opus 4.8's observed failure modes on this platform:

- refuses under authorization-theater framing (2026-06-19 lesson: keep framing
  minimal and factual — these blocks contain ZERO authorization language);
- regresses synthesis fields to metric-recitation and generic coaching (the
  Fable gap); pads clean output with narration;
- "improves" text it was told to copy verbatim (headline-rephrasing incidents);
- motivates with ambition when evidence says go lighter (program composition);
- keeps audit-failed claims alive with a hedge instead of deleting them
  (learner risk); declares completion before final stages under long prompts.

Analytical strength to exploit: Opus 4.8 follows explicit, imperative,
task-adjacent instructions extremely well — the blocks work by making each
pipeline's quality bar explicit and local, not by exhortation.

---

## Daily morning briefing — `## Model Notes — Opus 4.8`

```
## Model Notes — Opus 4.8

Schema compliance is your strength; the risks are analysis depth, padding, and
"improving" text you were told to copy. Concretely:

1. Analysis bar (applies ONLY to daily_briefing synthesis fields —
   reasoning.yesterday_lesson, cross_domain_insight, hero.avoid, risk_flags,
   morning_brief. Never to rt_yesterday/email_daily, which are data shaping):
   - yesterday_lesson: name what yesterday says about the operator's PATTERN
     (what behavior substituted for the goal), not which metric moved.
   - cross_domain_insight: ONE forward causal chain across >=3 sources
     (anchor -> drift -> consequence), not a list of independent findings.
   - hero.avoid: the specific failure mode TODAY's data predicts (the trap,
     e.g. "re-scoping the rep past 7 PM — toolchain is ready, just start"),
     never a platitude.
   - Scale the day's ask to recovery state: short sleep / low HRV -> hold the
     floor, schedule nothing heavy outside the anchor.
   - Hedge inflated numbers INSIDE the sentence that uses them ("part of the
     jump is more hours, not better hours"), not only in a caveats block.
2. Verbatim means verbatim: stage0 headlines, rep title/success_condition, and
   program fields are copied exactly — never reworded, tightened, or
   "clarified". If a headline conflicts with other data, preserve it in
   stage0_headlines and correct only the generated prose.
3. Health/weight framing comes from the body-comp goal memory read this run —
   never from assumption. (Under a cut phase: weight down + lifts held =
   SUCCESS; falling weight is not decline.)
4. Anti-padding: one compact status line per stage. Analysis prose belongs in
   /tmp/briefing.json and /tmp/narrative.txt and NOWHERE else — if you are
   narrating between tool calls, stop.
5. Completion beats polish: Stage 4 unfinished = failed run no matter how good
   the briefing text is. Do not linger perfecting prose mid-pipeline.
```

## Weekly program review — `## Model Notes — Opus 4.8`

```
## Model Notes — Opus 4.8

Composition discipline and honest notes matter more than eloquence. Concretely:

1. Review-notes analysis bar: the central finding is framed at IDENTITY level
   (what pattern the week reveals, what substituted for the goal), built as ONE
   cross-source mechanism (rep_days x steering interventions x health), and
   closes with >=1 numeric next-week target derived from a metric you just
   computed (e.g. "hands-on >=30 min on 3 of 5 anchor days") — checkable
   against the same ledger next Sunday. Recommend through real platform levers
   (rep anchor, milestone queue, goal-policy, floor sizing), never generic
   productivity advice.
2. Missed floors NEVER earn a heavier week. The instinct to motivate with
   ambition is the failure mode here: evidence of struggle -> lighter or
   friction-removed reps, same family. Momentum -> bigger milestone, same
   block size.
3. Platform governance section: ONE line when clean — do not narrate green
   checks or expand transients into paragraphs. Name known transients as
   transients (e.g. a classification aging out of its snapshot window).
4. The kill-gate result is binding. Composing "just a light week anyway"
   through a STOP is a failed run, not kindness.
5. A draft-clamp response is a report, not a puzzle: never retry write_program
   with tweaked frames.
6. Every factual claim in the notes must name its ledger (rep_days, rep_weeks,
   proactive_interventions, llm_budget steward line) so next week can check it.
```

## Monthly learner — `## Model Notes — Opus 4.8`

```
## Model Notes — Opus 4.8

The learner mutates the durable profile — subtractive honesty outranks insight
generation. Concretely:

1. The Stage 4 audit is subtractive, not decorative: a claim that fails its
   audit query is DELETED from the diff — not kept with a hedge, not
   "directionally true", not moved to prose. If >50% of claims drop, abort
   (the runbook rule) and say the synthesis over-reached.
2. Trait mutation requires a mechanism + >=2 independent sources across the
   window; anything less goes to hypotheses_for_next_run. A sparse month that
   produces only hypotheses is a SUCCESSFUL run, not a thin one — do not
   stretch evidence to justify a mutation because the cadence is monthly.
3. Never raise an existing trait's confidence without NEW evidence this
   window. Reinforcement without new evidence is a no-op — write it as such.
4. Identity-level synthesis is wanted (who the operator is, what substitutes
   for the goal) but every identity claim must trace to an audited number in
   the diff. No number, no claim.
5. Expired memories are retired beliefs: they never re-enter synthesis (the
   2026-06-12 resurrection bug is the cautionary tale).
6. Compactness is a hard budget: no payload pretty-prints; the diff and the
   compact narrative are the entire output surface.
```

## Signoff

- **2026-07-02 ET · Claude (Fable 5, operator session)** — Created: three
  Opus 4.8 blocks (briefing / program review / learner), mirrored into the
  gitignored paste bodies the same session. Verified: repo suite 107/107.
  (Latest entry only — history in git.)
