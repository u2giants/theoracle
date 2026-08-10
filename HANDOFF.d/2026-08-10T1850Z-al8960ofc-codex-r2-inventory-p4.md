# HANDOFF: R2 source-span inventory reader P4

Created 2026-08-10 18:50 UTC on `al8960ofc` by Codex.

## 0. Decisions only the owner can make

P4 and the next P5/P6 code gates need no owner decision.

Other open project decisions found while auditing the legacy handoffs:

- Blocking reliability proof: approve and provide a safe contradiction fixture for ERR-005. Recommendation: use a synthetic, non-confidential fixture. This blocks REL-2 closure and REL-7 release automation.
- Blocking image proof: approve one non-sensitive image for the live image-upload check. Recommendation: use a synthetic process diagram. This blocks REL-6.
- Recoverable product choice: decide whether Authentik is still wanted as a login method. Recommendation: remove it from the roadmap unless there is a current business need. This is GAP-3.
- Optional cloud change: approve Vertex cache and batch storage only if that feature is wanted now. Recommendation: leave it deferred until the current macro program passes. This is GAP-6.
- Security action: authorize secret rotation only when a planned maintenance window exists. Recommendation: keep it blocked until then. This is GAP-9.

The next session should put this whole list to Albert in one message only if it is working on those
legacy items. Do not interrupt P5 or P6 with these unrelated choices.

Already settled, do not re-ask:

- 2026-08-09: execute the inventory-reader plan in P0 through P8 order.
- 2026-08-10: P0 through P4 are complete and P5 is next.
- Do not deploy, run the pinned production fixture, change the scorer, raise budgets, enable merge or
  apply, or run another model bake-off before P7.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
upload business documents and ask questions. Workers find duties and process facts, bind them to
exact source quotes, and prepare reviewable business knowledge. The repository is
`u2giants/theoracle` at `C:\repos\oracle`, branch `main`. It is a TypeScript `pnpm` and Turbo
monorepo. The web app runs at `https://oracle.designflow.app`; workers run in Trigger.dev project
`proj_wgpzsvhmsopqhvwqaycn`; data lives in Supabase project `eqccjfbyrywsqkxxpjvg`.

This work changes the responsibility reader from model-first discovery to source-inventory-first
completion. The canonical contract is `plan_r2_source_span_inventory_reader.md`.

## 2. What we set out to do, and why

Albert asked to complete P4 and describe unfinished work in the legacy handoffs. P0 through P3 had
built stable source-bound seeds, deterministic completion, exclusive proposal matching, and an
exhaustive completion batch engine. The production worker did not yet call that engine.

P4 had to wire the engine into the real worker before the older retry and quote-repair steps. It
also had to ensure that only complete, source-seeded duties reach saved map elements and that every
batch, failure, unscheduled duty, and final gap remains visible in saved audit data.

## 3. Current state

- `plan_r2_source_span_inventory_reader.md` marks P0 through P4 complete and P5 next.
- `apps/workers/src/lib/source-workflow-read.ts` now reads live `workflow_read` model pricing and
  token limits, fails loudly when prices are unavailable, packs every residual seed within the
  frozen remaining budget, and reserves one read-call slot for candidate-bound quote repair.
- The worker runs `executeResponsibilityCompletionBatches` after base reads and deterministic
  completion, but before legacy omission retries.
- Completion uses the dedicated shallow schema and prompt, writes model runs, usage details, and
  context packs, canonicalizes immutable seed evidence, accepts strict improvements only, and
  records one terminal result for every scheduled or budget-exhausted seed.
- The five legacy retry slots now receive only `inventory_detection_gap` rows. They cannot be spent
  on normal seeded `completion_gap` rows.
- Combined repair now sets `maxFieldRepairs: 0`; it is candidate-bound quote repair only and cannot
  repeat field completion.
- Final responsibility elements are sorted by source seed order. The worker throws if a complete
  element lacks a source seed or maps to one seed more than once.
- Saved `validationJson` now contains the full source inventory, audit-only split parents,
  merge-ready IDs, incomplete IDs, final gaps, batch manifests, forecasts, outcomes, unscheduled
  IDs, model/context IDs, route/model/provider facts, attempts, output facts, and failure reasons.
- Kept and dropped counts now use explicit complete versus incomplete source inventory, not raw
  diagnostic-row counts.
- `apps/workers/src/__verify__/r2-responsibility-reader.ts` proves the production file orders
  completion, detection-only retry, quote repair, and merge-ready assembly correctly and persists
  the completion audit.
- Verification passed: AI workflow-read smoke, worker R2 verifier, AI typecheck, worker typecheck,
  worker lint, and `git diff --check`.
- P4 has not been deployed or run against production. P7 owns the only allowed deployment and
  production gate. P5 local verification and P6 independent review have not started.
- P4 and the audited handoff cleanup are committed and pushed on `main` as `fce082d`. GitHub Actions
  run `31421233372` passed every check. No deployment or production fixture was run.

## 4. Everything tried that did not work

1. The first compile failed because `ResponsibilityReaderDiagnostic` has `detail`, not `reason`.
   The completion validator now records `detail` plus incomplete-audit decision reasons.
2. The pre-P4 production flow ran the five omission retries immediately after base reads. That
   allowed normal seeded completion gaps to consume scarce retry slots. P4 filters the retry input
   to `inventory_detection_gap` only.
3. The old combined repair mixed quote repair with up to six field repairs. Keeping that path would
   duplicate the new exhaustive completion pass and make scheduling hard to audit. P4 disables its
   field side and leaves grounded quote selection intact.
4. Raw validation diagnostics were previously used as the responsibility dropped count. One duty
   can produce several diagnostics, so that was not an inventory count. P4 uses source inventory
   minus merge-ready inventory.

## 5. Root causes and key findings

- P3's batch engine was correct but disconnected from `generateSourceWorkflowMap`; this was the
  primary P4 gap.
- Completion calls must not reserve the same initial batch twice. The executor reserves all initial
  calls before concurrency; the provider callback writes audit rows but does not reserve again.
- The catalog, not a hard-coded price, is the correct source for input and output cost. Missing
  pricing now stops the run rather than making the budget forecast false.
- Seed identity is the only safe final ordering key. Provider completion timing cannot affect saved
  element or audit order.
- A reserved quote-repair call is removed from the completion call allowance before packing. Quote
  repair remains optional and separate from field completion.

## 6. Exact next steps

1. Re-read `AGENTS.md`, this handoff, and all of `plan_r2_source_span_inventory_reader.md`. You will
   know the resume point is correct when the banner says P0 through P4 complete and P5 next.
2. Complete every P5 command in section 10 of the plan, including the full worker tests, all three
   package typechecks, lint, format/diff checks, migration drift check, production-used
   orchestration verifier, and fixture-term anti-leak sweep. You will know it worked when every
   command exits zero without changing the frozen fixture or scorer.
3. Inspect the P4 diff for budget math, retry classification, one-to-one seed assembly, and durable
   audit completeness. Add direct tests for any branch that P5 finds weak. You will know it worked
   when a generic empty-base fixture, malformed batch, provider retry, budget shortage, detection
   retry, quote repair, and concurrent completion ordering all have passing evidence.
4. Run P6's independent read-only review. Fix every valid P0/P1 finding and repeat until the verdict
   is `APPROVED FOR CI AND LIVE REGATE`. You will know it worked when no unresolved blocking or high
   finding remains.
5. Only in P7, commit/push the reviewed work if it is not already committed, wait for green CI,
   deploy the Trigger worker, and run exactly one pinned production gate. You will know it worked
   when the run is terminal and the full 30-row score plus unchanged merge/apply flags are saved.
6. Apply P8's frozen score rule and update durable evidence. You will know closure is correct when
   the result, next decision, commit, push, and CI state all agree.

## 7. Constraints and gotchas

- Work only on `main`; commit as `Albert Hazan <u2giants@users.noreply.github.com>`.
- Preserve unrelated untracked `.ai`, screenshot, and browser files. Stage exact paths only.
- Frozen limits remain 40 reads, 500,000 input tokens, $10 estimated cost, one quote repair, five
  detection retries, and one retry per chunk.
- Do not run another model bake-off, hard-code a model or price, add fixture words, weaken evidence
  rules, change the scorer, raise budgets, add a database migration, or enable merge/apply.
- Do not reserve initial completion calls inside `runResponsibilityCompletionModel`; the executor
  reserves them before concurrency. Only a retry reserves itself.
- Production deployment and the pinned fixture are forbidden until P7.
- Root `HANDOFF.md` is a static pointer. Do not edit another session's handoff.

## 8. Access and environment

- Checkout: `C:\repos\oracle`; repository `u2giants/theoracle`; branch `main`.
- Git identity was verified as `Albert Hazan <u2giants@users.noreply.github.com>`.
- GitHub CLI is authenticated. P4 needed no production or secret access.
- Secrets live only in 1Password vault `vibe_coding`. No secret value was read or changed.
- P7 deployment uses Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn` and the management token stored
  in 1Password item `Trigger.dev Personal Access Token (management)`.
- Production targets are `https://oracle.designflow.app` and Supabase project
  `eqccjfbyrywsqkxxpjvg`. P4 did not mutate either one.

## 9. Open questions and risks

- No owner question blocks P5 or P6.
- Risk: P5 should verify the catalog ID lookup for every configured `workflow_read` provider form,
  especially Vertex's `google/<model>` alias.
- Risk: provider calls that fail before returning structured usage have terminal seed outcomes but
  may not create a normal successful model-run row. P5/P6 should confirm existing provider-attempt
  logging is sufficient for this failure path.
- Risk: the reserved quote-repair allowance reserves a call slot before packing, while exact quote
  input tokens are unknown until candidates exist. The global reader budget still enforces the
  actual call. P5/P6 should confirm this matches the frozen plan.
- Risk: legacy reliability and product gaps remain open independently of R2. They are listed in
  section 0 and routed by the two canonical gap plans.

## Handoff self-audit

1. Yes. Sections 1 through 3 define the product, goal, exact code state, verification, and unfinished
   boundary so a new developer can begin P5 without this chat.
2. Yes. Sections 4 and 5 preserve the failed compile, old retry/repair/counting problems, and the
   non-obvious reservation, pricing, identity, and ordering findings.
3. Yes. Sections 1 through 9 include purpose, state, failures, findings, exact gated next steps,
   constraints, access, commit/deploy status, risks, and legacy open work.
4. Yes. A line-by-line sweep found five owner decisions outside P4. All five are consolidated in
   section 0 with recommendations and what they block. P5 and P6 need none.

Self-audit passed. All ten sections are present, every next step has a verification gate, secret
references contain locations only, and a street-new developer can continue as effectively as this
session.
