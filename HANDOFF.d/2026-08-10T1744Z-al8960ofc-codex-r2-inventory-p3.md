# HANDOFF — R2 inventory reader P3 (2026-08-10 17:44 UTC, al8960ofc/codex)

## 0. ⚠️ DECISIONS ONLY THE OWNER CAN MAKE

None. Nothing in this workstream needs Albert before P4 starts.

Already settled, do not re-ask:

- 2026-08-09: execute `plan_r2_source_span_inventory_reader.md` in P0 through P8 order.
- 2026-08-10: P0 through P3 are complete. P4 is next.
- Do not deploy, run the pinned production fixture, change the scorer, raise budgets, enable merge/apply, or run another model bake-off before the P7 gate.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
upload business documents and ask questions. TypeScript workers find duties and process facts, bind
them to exact source quotes, and prepare reviewable business knowledge. The repository is
`u2giants/theoracle` at `C:\repos\oracle`, branch `main`. It is a `pnpm` and Turbo TypeScript
monorepo. The web app runs at `https://oracle.designflow.app`; workers run in Trigger.dev project
`proj_wgpzsvhmsopqhvwqaycn`; data lives in Supabase project `eqccjfbyrywsqkxxpjvg`.

This work changes the responsibility reader from model-first discovery to source-inventory-first
completion. Pure seed, packing, and canonicalization rules live in
`apps/workers/src/lib/responsibility-reader.ts`. Orchestration helpers live in
`apps/workers/src/lib/source-workflow-read.ts`. The ordered contract is
`plan_r2_source_span_inventory_reader.md`.

## 2. What we set out to do this session, and why

Albert asked to complete P3. P0 classified the failures, P1 built stable source-bound duty seeds,
and P2 matched model proposals to those seeds and completed clear duties without a model. P3 had to
make every remaining seed schedulable exactly once, prove the model-call budget before dispatch,
reject malformed model replies as a whole batch, allow only a narrow one-time retry, and preserve
immutable evidence identity.

The business purpose is simple: an unfinished duty must never disappear because it missed a small
retry queue or because the model returned an incomplete list.

## 3. Current state — what is true right now

- `plan_r2_source_span_inventory_reader.md:3` says P0 through P3 are complete and P4 is next. Its
  status row at line 26 records the P3 evidence.
- `packages/ai/src/prompts/workflow-read.ts:9,115,224` defines a dedicated versioned completion
  prompt and shallow strict schema. The model fills known duties only. Evidence IDs, chunks, quotes,
  and offsets are not response fields.
- `apps/workers/src/lib/responsibility-reader.ts:94-278` defines immutable completion requests, a
  conservative token estimator, stable input/output/cost packing, unscheduled IDs, and all-or-none
  response canonicalization. Missing, duplicate, or extra IDs throw.
- `apps/workers/src/lib/source-workflow-read.ts:124-235` defines request content, full read-budget
  reservation before concurrency, low/expected/high forecasting, source-order execution, one retry
  only for timeout/schema/all-candidates failures, and a required strict-improvement selector.
- The P3 executor is deliberately not wired into the live `generateSourceWorkflowMap` path yet.
  That wiring, validation against existing seed state, final audit persistence, and order-stable map
  assembly are P4 by the written plan.
- `apps/workers/src/__verify__/r2-responsibility-reader.ts:92-263` proves a generic 40-duty empty-base
  case schedules every seed, repeats with identical batches, forecasts three cases, reserves the
  read budget, canonicalizes exact replies, rejects missing/extra replies, lists every unscheduled
  seed under shortage, applies no malformed records, and retries a timeout once.
- `packages/ai/src/__verify__/workflow-read-smoke.ts:17-36` proves the shallow schema and
  completion-only prompt contract.
- Verification passed: AI workflow-read smoke, worker R2 responsibility verifier, AI typecheck,
  worker typecheck, worker lint, and `git diff --check`.
- Grok 4.5 session `r2-inventory-p3-review` first returned `CHANGES REQUIRED BEFORE P4`. Its
  findings were corrected in the same session: real provider retry classification, the shared
  300-record schema/packer ceiling, non-bypassable strict-improvement selection, and ordered
  per-seed terminal outcomes. The follow-up verdict was `APPROVED FOR P4`. The two turns cost
  $1.0243416 total and reported 2,114,454 tokens, including 1,935,232 cached.
- Local `main` and `origin/main` both began at `89feb096e2ab85ec7463a12da693b2228eed59e8`.
- P3 code and plan are committed on `main` as `014f971` (`feat: complete R2 inventory reader P3`).
  Grok corrections are committed as `4f1a76e` (`fix: harden R2 completion scheduling`). This handoff
  is in separate closeout commits. All are pushed to `origin/main` in this session. P3 was not
  deployed or run against production; P7 owns deploy and the one production gate.

## 4. Everything we tried that did NOT work

1. The first executor draft imported the completion output type into the pure reader but omitted it
   from `source-workflow-read.ts`. The verifiers passed because they transpile without the full type
   gate, but worker typecheck caught the missing name. Adding the type-only import fixed it.
2. The first retry rule retried every error, including extra or missing response IDs. That conflicted
   with P3: only timeout, schema, or all-candidates failures may retry. The executor now fails malformed
   replies immediately and retries only the named transient classes, with an override hook for the
   production error type.
3. The first executor canonicalized identity but did not require the caller to prove field quality or
   strict improvement. It now requires `selectStrictImprovements`; returned selections are checked
   again so they cannot cross batches or duplicate IDs. P4 must connect this callback to the normal
   validator and current seed state.
4. The first schema used normal Zod objects, which may strip unknown fields. P3 calls for a strict
   shallow schema, so both the record and envelope now use `.strict()` and reject invented fields.
5. Grok's first review found that the default regex did not match the real
   `AllCandidatesFailedError` message, the packer could exceed the schema's 300-record ceiling, and
   a selector callback could drop rejected seeds without terminal audit. The correction uses typed
   retry checks, one shared ceiling, a pure complete-only improvement helper, and one ordered outcome
   for every seed. Grok re-read the corrected files and approved P4.

## 5. Root causes and key findings

- Budget proof must include both estimated input and output tokens plus configured input/output
  price. `SourceReaderBudget` still enforces the frozen read-call, input-token, and configured cost
  cap at reservation time; P3's packer adds the fuller forecast used before dispatch.
- All initial batch reservations happen before `mapWithConcurrency`. A failed reservation therefore
  stops dispatch before a partly scheduled queue can look complete.
- Response identity is never trusted. `canonicalizeResponsibilityCompletionBatch` rebuilds
  responsibility ID, chunk ID, and evidence quote from the request and returns records in request
  order, regardless of model order.
- A malformed batch is atomic: canonicalization throws before the strict-improvement selector sees
  any record. No part of that batch can be applied.
- A retry consumes a new `reserveRead`, not a repair allowance. If the exact same batch no longer
  fits, the executor returns every seed with the original failure plus `retry_not_budgeted`.
- P3 creates the production-ready completion seam but does not decide which seed is still incomplete.
  P4 must derive that residual queue from the combined validated base/model/deterministic state.

## 6. Exact next steps

1. Read `AGENTS.md`, `HANDOFF.md`, this file, and all of
   `plan_r2_source_span_inventory_reader.md`. Confirm P0 through P3 are complete and P4 is the only
   open starting step. You will know it worked when the plan banner says P4 is next.
2. Inspect the P3 seam at `responsibility-reader.ts:94-278` and
   `source-workflow-read.ts:124-235`. Preserve stable source order, immutable evidence, full
   pre-reservation, atomic malformed-batch failure, and the narrow retry rule. You will know it
   worked when the existing P3 tests still pass unchanged.
3. Implement P4 exactly as written. After base proposal matching and deterministic completion,
   derive every still-incomplete inventory seed, forecast and pack it, and call
   `executeResponsibilityCompletionBatches`. Use the configured `workflow_read` route, the dedicated
   completion prompt/schema, and the existing model/context audit writers. You will know it worked
   when every residual seed has one terminal outcome: complete, validation-rejected, provider-failed,
   or `budget_exhausted`.
4. Implement `selectStrictImprovements` with the normal `validateResponsibilityRead` and fidelity
   rules. Keep the prior record unless the candidate removes failure reasons or becomes complete;
   never weaken quote or field checks. You will know it worked when a bad completion leaves the seed
   incomplete with its old reasons and a valid completion becomes merge-ready.
5. Run completion before legacy omission retries. Spend legacy retries only on
   `inventory_detection_gap`, not seeded `completion_gap`. Run candidate-bound quote repair after
   completion and revalidate once. You will know it worked when no seeded duty disappears for lack
   of a retry slot.
6. Persist batch manifests, forecasts, attempts, provider failures, unscheduled IDs, outcomes, model
   run IDs, context pack IDs, usage, route, cache, and execution facts in `validationJson`. Assemble
   `elementsJson` from complete seeded records only and preserve stable order. You will know it worked
   when identical delayed/concurrent completions produce byte-stable element and audit ordering.
7. Add the production-used orchestration test required by P4, then continue P5 and P6. Do not deploy
   or touch the pinned production gate before P7. You will know it worked when every section 10 local
   command passes and the independent P6 reviewer says `APPROVED FOR CI AND LIVE REGATE`.

## 7. Constraints and gotchas in force

- Work only on `main`; commit as `Albert Hazan <u2giants@users.noreply.github.com>`.
- Preserve unrelated untracked `.ai`, screenshot, and browser files. Stage only exact P3/P4 files.
- Frozen reader limits are 40 calls, 500,000 input tokens, and $10. Post-pass limits remain one quote
  repair, five omission retries, and one retry per chunk.
- Do not run another model bake-off, hard-code a model, add fixture words, weaken evidence rules,
  change the scorer, raise budgets, add a database migration, or enable merge/apply.
- `reserveResponsibilityCompletionBatches` reserves all initial calls up front. Do not also reserve
  those same calls inside the P4 provider callback. Only the executor reserves a retry call.
- The strict-improvement selector is required. Do not replace it with an identity callback in
  production; that shortcut exists only in the isolated P3 scheduling verifier.
- Destination siblings can share exact quote and offsets. Identity is the seed ID plus split value,
  not quote text alone.
- `HANDOFF.d/` contains more than five open files. Do not delete another session's file without proof
  that its workstream is complete.

## 8. Access and environment

- Checkout: `C:\repos\oracle`; GitHub repository `u2giants/theoracle`; branch `main`.
- Git identity was verified as `Albert Hazan <u2giants@users.noreply.github.com>`.
- GitHub CLI is authenticated. P3 required no cloud or secret access.
- Secrets live only in 1Password vault `vibe_coding`. No secret or `.env` value was read or changed.
- Later P7 deployment uses Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn` and the management token
  stored in 1Password item `Trigger.dev Personal Access Token (management)`.
- Production targets are `https://oracle.designflow.app` and Supabase project
  `eqccjfbyrywsqkxxpjvg`. P3 did not mutate either one.

## 9. Open questions and risks

- No owner question is open before P4.
- Risk: P4 must avoid double-reserving initial completion batches when it adds the provider callback.
- Risk: production adapter failures should supply an explicit `isRetryableFailure` predicate so the
  one-retry rule can add provider-specific cases. The default now recognizes the real
  `AllCandidatesFailedError`, `AbortError`, `TimeoutError`, and known message forms.
- Risk: the P3 forecast accepts configured input/output prices. P4 must source them from the resolved
  route/catalog and fail loudly if pricing needed for the forecast is absent.
- Risk: P4 must reserve one candidate-bound quote-repair allowance in its remaining-budget inputs as
  required by P3. The pure packer cannot infer future orchestration costs by itself.
- Decision dated 2026-08-10: no deployment or pinned-fixture run occurs until P7.

## Handoff self-audit

1. Yes. Sections 1 through 3 explain the product, repository, goal, files, line references, proof,
   and exact unfinished boundary so a newcomer can continue without this chat.
2. Yes. Sections 4 and 5 preserve every failed draft and the non-obvious budget, identity, retry,
   atomicity, and P3/P4 boundary findings.
3. Yes. Sections 1 through 9 cover background, goal, current state, failed paths, findings, exact
   next actions with gates, constraints, access, risks, and commit/deploy state.
4. Yes. A line-by-line sweep of sections 1 through 9 found no sentence needing Albert's judgment.
   Section 0 explicitly says none and lists the settled decisions that must not be reopened.

Self-audit result: passed. All ten sections are present; secrets are location-only; every failed path
and risk is recorded; every next step has a verification gate; and a street-new developer can start
P4 as effectively as this session without asking a question.
