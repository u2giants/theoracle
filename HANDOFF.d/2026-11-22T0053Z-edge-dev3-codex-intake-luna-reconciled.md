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

None for the current sandbox work. After the 14-day pilot, present measured cost per kept thread and the all-employee projection so Albert can decide whether to keep exact quotes. At full-run acceptance, show the function page and unsent questions after verifying five answers with new evidence. These decisions remain in the [intake plan](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md#status--read-this-first).

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

1. Establish a calibrated lead review surface for the protected original texts and an independent check by a non-author. Before grading, reverify the sealed packet. Read sources first, record source-supported relations missed by every candidate, use prior verdicts on exact duplicates, preserve distinct narrower corrections, rejects and withheld judgments, and settle second-review disagreements before unsealing. Verify by a passing blind calibration, complete dispositions, resolved disagreements and a source-backed semantic recall result with whole-thread bounds.
2. Follow the registered order for call shapes. Reuse the archive's low-mention skip and near-duplicate screen measurements where supported. Fresh short joint calls and wider context remain open. Count any retries. No new candidate can qualify on the current holdout under the registered truncation method, so resolve the sampling dependency before a qualification run. Follow the prerequisites in the [plan](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md). Record verified results per 1,000 passages on #607 and link from STATUS when 2.3 is concluded. Require the 15-question comparison before seating a passing route.
3. For downstream steps, carry forward the [predecessor's next actions](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-20T2108Z-edge-dev3-codex-intake-blind-review.md#6-next-actions-and-verification). If a route eventually passes, verify batching and caching, evaluate business-area sorting, and get separate authority for the 14-day pilot and 90-day run. The Ilona question comparison has seven private evidence-backed drafts and still needs the separately scoped Brain-generated comparison. Leave #607 and its live-proof checkbox open through acceptance.

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
4. Section 0 holds both deferred owner decisions. The review and sampling dependencies in sections 6 and 9 are technical, with no owner approval requested.
