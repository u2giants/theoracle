# Handoff — Company Map plan published; implementation not started

Written 2026-10-27, 11:05 PM EDT, edge-dev3, Claude (Fable 5.1). Session: review of parent #24 and the new plan.

## Status line
Plan [plan_oracle_company_map.md](../plan_oracle_company_map.md) written; committed and pushed on branch `claude/ai-mckinsey-consultant-review-3cae51`, merged to `main` via PRs #239, #257, #258. No implementation code exists yet. Every STATUS row in the plan is ⬜ open. Nothing deployed, no secrets created.

## What a successor does
1. Read the plan's STATUS table and Part 1, then start at step 0.
2. Step 0 includes retiring the old parent24 handoffs into `HANDOFF.d/archive-parent24/` and marking the six old Oracle plans SUPERSEDED. That step also retires **this** file under the successor rule (its only obligation is "start the plan").
3. Create `SCALEDOWN_API_KEY` and `BRAIN_SHARED_TOKEN` items in 1Password vault `vibe_coding` before step 4 (skill `secrets-to-1password`).

## Owner rulings this session (Albert, 2026-10-27, verbatim where quoted)
- Corpus is "hundreds of documents, diagrams & flowcharts, and tens of thousands of lines of transcripts", plus interviews.
- "we don't need to be evaluating atomic claims. the whole point of this is to see the big picture from a lot of noisy data."
- "none of the data going into this will be secret data, we don't need complicated permissions and security system."
- FalkorDB stays: "i don't want to have to reprogram this system down the road."
- Implementer is GLM 5.1 / Sol 6.1 class; plan must be detailed enough for that.
- Human grading "within reason".
- Earlier the same day: "treat this as brand new" (no comparison with the old Oracle) and "we already have a teams bot working from the old oracle."

## Dead ends recorded (do not retry)
See plan §7. Headline: the sixteen-step overhaul plan, thin single-document journey, Graphiti, graphrag-sdk as pipeline, Docling, Trigger.dev Python workers, per-claim approval, candidate/confirmed split.

## Related files
- Review that led here: [docs/review-2026-10-27-consultant-plan-and-code.md](../docs/review-2026-10-27-consultant-plan-and-code.md)
- ScaleDown call analysis: [scaledown-report.md](../scaledown-report.md)

## Closing note (2026-10-28, 8:55 AM EDT, same session)
- Tracking: parent https://github.com/u2giants/theoracle/issues/240 with children #241–#255 (one per step 0–14), attached as sub-issues.
- Owner ruling 2026-10-28 (Albert): no repository lock; only Claude Opus or Fable reviews; GPT and GLM never review. Albert pastes the review prompt that sits at the bottom of each child issue ("How this step gets checked") into a fresh Opus/Fable session; the implementer opens the PR, does not merge, posts `Ready for review: PR #n`. Mechanics in plan §11.
- Nothing implemented yet. Next action: start Step 0 (https://github.com/u2giants/theoracle/issues/241) in a GLM 5.1 / Sol 6.1 session.
- Known CI noise: `Oracle offline suites` / `test_ci_trust_boundary` (KeyError 'uses') fails on `main` itself; unrelated to this program, not fixed here (scope freeze).
