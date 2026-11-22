---
summary: "Oracle #607 continuation after both Luna batches were reconciled. Carries measured costs, decisive gate failures, and the protected blind-review checkpoint."
kind: handoff
status: open
read-when: resuming step 2.3 after Luna native and pinned batch reconciliation
issue: 607
owner: codex/oracle-607-luna-reconciled
---

# Oracle #607 after Luna batch reconciliation

## 0. Business decisions only Albert can make

None before preparing a recovery strategy. If the authorized corpus cannot supply a defensible holdout or no eligible route can pass within the spending limit, present Albert with the evidence and the smallest business decision needed. Examples include authority to expand the private data window or a decision to defer rollout. Leave the thresholds and source policy in force until explicitly changed. After the 14-day pilot, present measured cost per kept thread and the all-employee projection so Albert can decide whether to keep exact quotes. At full-run acceptance, show the function page and unsent questions after verifying five answers with new evidence. These decisions remain in the [intake plan](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md#status--read-this-first).

## 1. Application

Oracle maps how POP Creations and Spruce Line work, cites original evidence when answering employee questions, and drafts follow-up questions. This work covers project-manager Teams, ClickUp and authorized email records. The Vercel web app, Coolify Brain and Supabase data are described in the [developer guide](https://github.com/u2giants/theoracle/blob/main/AGENTS.md). This work uses Oracle's separate private Coolify sandbox.

## 2. Objective

Continue [#607](https://github.com/u2giants/theoracle/issues/607) at 2.3. Reconcile the existing paid reruns, measure accuracy, recall, quote validity, truncation and cost using the frozen benchmark, and select a path only if it clears every applicable gate. The owner authorized sandbox work and required production to stay untouched.

## 3. Verified state

The benchmark used main at [6e570044](https://github.com/u2giants/theoracle/commit/6e57004407ac9e5c01ac669269b994c405a0f496). Steps 2.1 and 2.2 remain complete. The two prerequisite manifests match their receipts, and all 37 listed files verified. GLM 5.3 Flash remains the flat baseline. See the [step 2.1 receipt](https://github.com/u2giants/theoracle/issues/607#issuecomment-7024467855) and [step 2.2 receipt](https://github.com/u2giants/theoracle/issues/607#issuecomment-7027642220).

Both Luna batches produced 57 usable replies. OpenAI's native batch needed no retry and cost $0.02931684. OpenRouter's pinned batch had one malformed first reply and recovered it on exactly one retry. Provider charges were $0.03152040 plus $0.00121705 for the retry. No batch is pending. The total costs per 1,000 passages were $0.514 and $0.574 respectively. The 95% quote lower bounds were 97.28% and 96.24%, below 98%. The 95% correctness lower bounds reached at most 93.28% and 94.83% when every unreviewed or withheld claim counted as correct. Neither reached 95%. The Haiku native batch cost $0.633 per 1,000, reached a 100% quote lower bound, and had a best-case correctness lower bound of 93.70%. The archived four and GLM Flash → Luna had already failed correctness. See the [reconciliation receipt](https://github.com/u2giants/theoracle/issues/607#issuecomment-7071834212) and [archived results](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-20-pm-intake-relations.md).

The completed imports and aggregate calculation live in the private sandbox. The new sealed packet has 12 routes, 5,313 novel claims, 72 hidden controls and 1,063 second checks. Its four files verified against the manifest digest in the issue receipt. Semantic grading and recall are open. No application change, production deploy, outreach or review verdict publication occurred.

## 4. Failed approaches

Prior automatic graders failed blinded controls even with multiple attempts at reformatting the evidence. Masked lead scoring lost context needed to judge attribution, scope and authority. Exact matching can reuse existing verdicts but cannot decide that two differently worded claims mean the same thing. Exclude all failed grader verdicts. The earlier failures are documented in the [predecessor handoff](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-20T2108Z-edge-dev3-codex-intake-blind-review.md#4-failed-approaches-and-recoveries).

## 5. Gate findings

Qualification uses whole-thread, origin- and length-stratified resampling. Even zero truncations produces a 9.50% upper bound on the 30 sampled threads. The full 150-thread freeze, including the 120-thread reserve, can at best reach 1.98%. The existing method needs at least 299 independent zero-event threads to show a bound at or below 1%. Repeated predictions on the existing passages leave that denominator unchanged. The new batch failures stand even without novel judgments. An exact-overlap measure remains a limited diagnostic. The full [2.3 plan](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md#phase-2--choose-the-cheapest-models-that-pass-context-cut-point-start-a-fresh-session-here) defines eligibility and all four gates.

## 6. Next steps and verification

Start by writing a short recovery strategy on [#607](https://github.com/u2giants/theoracle/issues/607), with an owner, time and spend limits, a go/no-go check per stage, and a separate track for evidence review and statistical qualification. Reuse the settled batch imports. No further rerun of those original jobs is needed.

1. **Prove protected review is feasible on a small tuning set.** Locate an approved reader that can show complete original thread context without exporting it from custody. Keep model labels sealed. Validate a rubric using tuning threads only, including wrong actor, obsolete status, one-off versus standing practice, unsupported implication, and a valid differently worded relation. Run a fresh hidden-control calibration with preregistered success criteria and a second reviewer who did not author the evaluated claim. The earlier automatic and masked workflows failed. Stop and record the specific custody or calibration blocker if this gate cannot pass. Verify access, provenance separation, control outcomes and an adjudication trail in the sandbox before opening scoring claims.
2. **Prove the benchmark can establish the truncation ceiling.** Inventory eligible distinct threads by source, length, thread identity and sampling frame using counts only. Preserve the frozen 30 and the ordered 120 reserve. Under the current method at least 149 additional independent held-out threads are needed beyond those 150, and 299 is sufficient only in the zero-event case. Check representativeness, repeated conversations and selection weights before treating them as independent. Freeze additions, sample order, eligibility, cluster method and failure stop rule before examining outputs. Budget the expansion. If the approved pool is too small, document the shortfall and the smallest scope decision in §0. Treat any alternative statistical design as a proposal to validate prospectively, with the same confidence and 1% threshold.
3. **Find a promising low-cost change before paying for full validation.** On tuning only, group failures in the archived decisions by wrong subject, predicate, scope, time or evidence, and separate missed relations from unsupported claims. Use those counts to prioritize the plan's registered variants in order: low-mention skip (reuse measured loss), short joint call, wider context, and verified recurring machine-generated digest suppression (reuse the existing near-duplicate screen). Keep the original prompt and route as the control, change one factor at a time, and count failed calls, retries, and each stage's cost. Evaluate structured source fields where the plan already supports them. A narrower prompt or validator change can improve precision while hurting recall, so compare both before selecting a finalist. Use synthetic samples for plumbing checks and the 50 tuning threads for calibration. Avoid exploratory changes against the held-out threads.
4. **Grade and qualify only when the preceding gates hold.** Reverify the sealed packet. Read sources first, record source-supported relations absent from every output, carry forward exact duplicate judgments, and keep narrower corrections, rejects and withheld judgments distinct. Settle the seeded independent disagreements before unsealing. Measure semantic recall by matching equivalent claims to supported gold relations. Run the frozen finalist against the preregistered evaluation with whole-thread bounds for correctness ≥95%, recall ≥90%, quotes ≥98% and truncation ≤1%. Include malformed replies and cost per 1,000 attempted passages. Try the plan's eligible failure-only fallback if a single model fails and the evidence justifies it. If no single route or pair meets all bounds, record the stop and the next business decision, if any, on #607. A passing route also needs the same 15 questions to score at least as well as the reference before seating.
5. **Carry downstream dependencies.** See the [predecessor's next actions](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-20T2108Z-edge-dev3-codex-intake-blind-review.md#6-next-actions-and-verification). After a winner, verify batch economics, failure handling, cache hit share and business-area sorting. The 14-day pilot and 90-day run need separate production authority. The Ilona question comparison has seven private evidence-backed drafts. Its separately scoped Brain-generated comparison, full ClickUp history and import are still open. Leave #607 and its live-proof checkbox open through acceptance.

## 7. Constraints

Keep production untouched during sandbox work. Source wording, identifiers, provider job IDs, raw responses and keys stay in protected custody. Use only the plan's eligible routes for qualification and follow the approved review protocol. Expanded trials are diagnostic. Use a separate current-upstream worktree for repo changes and leave the earlier handoff in place because 2.3 is open.

## 8. Protected access

Use the Oracle Company Map private Coolify sandbox in the [predecessor's custody section](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-20T2108Z-edge-dev3-codex-intake-blind-review.md#8-access-and-custody). The sandbox's logical `step-2.3-relations` group contains `haiku-luna-native-batch`, `luna-router-batch-fallback` and `direct-16k-blind-packet-both-luna-routes`. The reproducible bounds and aggregate are in `luna-reconciliation-01a200b5`. Use the sandbox's existing access route and vault references. Both batch jobs are terminal and fully imported. No provider key is needed for offline grading or bounds recomputation.

## 9. Risks and readiness

As of November 21, 2026, the protected lead and independent source review still need a calibrated reading route. The confidence ceiling for the frozen sample persists even with perfect replies. The verified logs and blind packet are in the private sandbox, with only aggregate evidence on GitHub. No model qualified and no production seat changed.

Self-audit passed.

1. Sections 1–3, 6 and 8 identify the application, starting point and custody needed by a fresh developer.
2. Sections 3–5 preserve both settled runs, their costs and the failed review and confidence paths.
3. Sections 6–9 give the exact sequence, checks, constraints and remaining dependencies. The predecessor remains linked for downstream verification procedures.
4. Section 0 holds both later acceptance decisions and the conditional scope or deferral decision if the technical strategy runs out of authorized paths. No owner approval is required to draft the strategy.

## Start a fresh session

> Use main of u2giants/theoracle. Read this handoff from the STATUS of the project-manager intake plan. Resume #607 at step 2.3 and draft the recovery strategy under §6. Preserve both completed Luna batches and steps 2.1 and 2.2. Verify a protected review path and a defensible holdout, propose bounded tuning and qualification tests, and record the go/no-go checks on #607. Keep production untouched.
