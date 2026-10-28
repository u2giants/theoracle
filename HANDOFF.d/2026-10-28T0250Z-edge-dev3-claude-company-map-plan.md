# Handoff — Company Map plan published; implementation not started

Written 2026-10-27, 11:05 PM EDT, edge-dev3, Claude (Fable 5.1). Session: review of parent #24 and the new plan.

## Status line
Plan [plan_oracle_company_map.md](../plan_oracle_company_map.md) written; committed and pushed on branch `claude/ai-mckinsey-consultant-review-3cae51`, PR to `main` (number recorded in the plan STATUS once opened). No implementation code exists yet. Every STATUS row in the plan is ⬜ open. Nothing deployed, no secrets created.

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
