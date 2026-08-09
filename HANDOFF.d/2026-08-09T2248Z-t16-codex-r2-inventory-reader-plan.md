# R2 source-span inventory reader plan handoff

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
upload business documents and ask questions. TypeScript workers extract claims and business process
structure, validate exact quotes, and prepare reviewable knowledge. The repository is
`u2giants/theoracle` at `C:\repos\oracle`, on `main`. The web app runs at
`https://oracle.designflow.app`; workers run in Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`;
the database is Supabase project `eqccjfbyrywsqkxxpjvg`.

## 2. What we set out to do this session, and why

Albert asked to proceed with the deeper reader design after the bounded workflow-model bake-off
failed. The goal was to produce a fresh-developer implementation plan that fixes the responsibility
reader's repeated 11 to 12 out of 30 result without weakening evidence rules or running another
model comparison.

The durable plan is `plan_r2_source_span_inventory_reader.md`. It makes exact duty spans the
inventory first, then schedules field completion for every incomplete duty in token-packed batches.

## 3. Current state

- The prior implementation and bake-off are complete at repository baseline commit `4e7420f`.
- GitHub CI for that baseline passed in run `31117917894`.
- GPT-4.1 scored 11/30 and 12/30, mean 11.5. See `evals/bakeoffs/workflow-read.md`.
- Claude Sonnet 5 and Gemini 2.5 Pro were ineligible because the catalog had not proved the required
  deep strict schema support. This is not the next workstream.
- The new design is fully written in `plan_r2_source_span_inventory_reader.md` with all steps open.
- `AGENTS.md`, `MACRO_FIRST_IMPLEMENTATION_PLAN.md`, and the predecessor plan now route a fresh
  session to the new plan.
- No reader code, tests, database, production worker, production fixture, or deployment changed in
  this planning session.
- The first plan was committed and pushed at `a78fafc`; CI run `31340678699` passed.
- Grok 4.5's first review returned `CHANGES REQUIRED BEFORE IMPLEMENTATION`. The corrected plan adds
  deterministic completion, exact destination/multi-verb rules, residual failure classification,
  exclusive proposal matching, explicit budget math, provider-failure behavior, and stale-doc fixes.
- Grok session `019fe8db-eef0-7f83-b974-a372bd6330da` approved the design for implementation on its
  third pass after the destination-child fidelity and object-boundary contracts were frozen.

## 4. Everything we tried that did not work

1. The earlier deeper architecture separated incomplete inventory, added deterministic destination
   expansion, allowed five focused omission retries, and added one combined repair call. Its single
   production gate scored 12/30. It protected quality but did not provide work for every source duty.
2. The bounded GPT-4.1 bake-off seemed reasonable because the same model had once scored higher under
   looser controls. Two fresh runs scored 11 and 12, proving model choice was not the main limit.
3. Claude Sonnet 5 and Gemini 2.5 Pro could not be compared fairly because the required deep strict
   response schema was not qualified. Re-qualifying them would still leave the model-first queue.
4. Raising retry slots, loosening field rules, or using incomplete records as map evidence were
   rejected. They would hide omissions, accept wrong data, or move bad records downstream.
5. Grok rejected the first source-span plan as build-ready because exhaustive model completion still
   repeated the known weak field-fill step and split/budget/matching rules were vague. Those findings
   were valid and are incorporated in the current plan.

## 5. Root causes and key findings

- `sourceDutySpanDetails` at `apps/workers/src/lib/responsibility-reader.ts:519` already finds and
  binds exact duty spans, but the runtime uses them mainly after base model reads to find omissions.
- `buildResponsibilityBaseReadPlan` at `apps/workers/src/lib/responsibility-reader.ts:375` guarantees
  model reads for duty-bearing chunks, not one durable work item per duty.
- The orchestration at `apps/workers/src/lib/source-workflow-read.ts:2305` is model-first. A duty must
  be emitted by the base read or scarce retries before it can become complete.
- The retry loop at `apps/workers/src/lib/source-workflow-read.ts:2377` is frozen at five total and one
  per chunk. The combined repair plan at line 2601 is also bounded. Neither is exhaustive.
- Final assembly at `apps/workers/src/lib/source-workflow-read.ts:2808` is already safe because it
  consumes complete records only. Preserve this boundary.
- The failed bake-off left budget available, so the primary problem is scheduling and inventory
  ownership, not context size or model price.
- Inventory accounting alone is insufficient. Clear list duties must complete deterministically,
  while residual model work is justified row-by-row by P0's failure matrix.

## 6. Exact next steps

1. Read `plan_r2_source_span_inventory_reader.md` in full and start at P0 only after the Grok
   correction review approves it. You will know P0 worked when the clean baseline passes and every
   latest-gate/bake-off miss is assigned a failure class and closing mechanism.
2. Implement P1 in `apps/workers/src/lib/responsibility-reader.ts`, adding stable exact source-span
   inventory seeds. You will know it worked when generic local fixtures produce stable IDs, offsets,
   quotes, and loud duplicate/binding failures without a model call.
3. Stop at context cut point A and start a fresh session. You will know the handoff is safe when the
   runtime anti-leak test proves no pinned business terms entered the implementation.
4. Implement P2 and P3 exactly, including the shallow completion schema and exhaustive token packer.
   You will know it worked when empty base output preserves inventory and a generic 40-duty fixture
   schedules all seeds or durably names every budget-exhausted seed.
5. Implement P4 through the real production seam. You will know it worked when only complete records
   enter map elements and incomplete seeds remain visible in `validationJson` with degraded status.
6. Run every section 10 command and the anti-leak sweep. You will know it worked when all commands and
   `git diff --check` pass.
7. Complete the P6 independent read-only correction loop. You will know it worked when the reviewer
   says `APPROVED FOR CI AND LIVE REGATE` with no open P0/P1 findings.
8. In a fresh release session, commit and push reviewed code, wait for CI, deploy workers, and run the
   one allowed production gate. You will know it worked when one terminal map has a full 30-row score
   and unchanged merge/apply flags and protected table counts.
9. Apply P8's exact score rule and update durable evidence. You will know it worked when docs, commit,
   push, and CI all match the sole production result.

## 7. Constraints and gotchas

- Work on `main`; no feature branch unless Albert changes the rule.
- Commit author and committer must both be Albert Hazan's noreply GitHub identity.
- No second model bake-off and no early production gate.
- No database migration or shared-backend change is authorized.
- Keep exact quote and field-fidelity validation strict.
- Keep frozen 40/500k/$10 and 1/5/1 limits unchanged.
- Keep models configurable through `workflow_read`; do not hard-code a provider.
- Incomplete inventory belongs only in audit state, never map evidence or merge input.
- Merge and apply remain false even if the score passes.
- Use invented generic examples in tests. Runtime code must not contain fixture-derived terms.
- Never print or persist secrets. Serialize 1Password reads.
- Preserve unrelated local work and stage only this workstream.

## 8. Access and environment

Expected machine is Windows `t16`, local path `C:\repos\oracle`, branch `main`. `gh` is used for
GitHub and CI. Trigger.dev deployment uses the item `Trigger.dev Personal Access Token (management)`
from 1Password vault `vibe_coding`. Protected database checks use item
`Supabase DB Direct URL - The Oracle (CURRENT PROD …)`, field `oracle_session_pooler`, from the same
vault. Secret values must never appear in files, logs, or process arguments.

## 9. Open questions and risks

- Decision, 2026-08-09: use a dedicated shallow completion schema. This is frozen and separates
  residual field work from candidate-bound quote repair.
- Risk: deterministic parsing may miss free prose. Keep model proposals and the five retries only for
  true inventory-detection gaps, then measure them separately.
- Risk: exhaustive completion may reach the frozen budget. Token-pack batches and report unscheduled
  IDs loudly rather than truncating silently.
- Risk: inventory can rise without quality. Publish source, discovery, and merge-ready coverage as
  three separate measures.
- Grok review total: $1.127844, 2,510,800 reported tokens, 2,334,080 cached, 21 turns across three
  passes, model `grok-4.5-build`; final verdict `APPROVED FOR IMPLEMENTATION`.
- No owner question is open before P0.

## Self-audit

1. Yes, a brand-new developer can continue without this chat. Sections 1 through 3 define the app,
   goal, repo, runtime, evidence, and exact current state; section 6 gives ordered gates.
2. Yes, they can continue with the same session knowledge. Sections 4 and 5 preserve every failed
   approach, the key line-level findings, and the reason for the architecture inversion.
3. Yes, all execution details are present. Sections 6 through 9 cover exact actions, verification,
   constraints, access, secrets by location only, decisions, and risks. Commit, push, CI, deployment,
   and production status are explicit in section 3.
