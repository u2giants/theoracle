# HANDOFF — R2 inventory reader P2 (2026-08-10 16:54 UTC, al8960ofc/codex)

## 0. ⚠️ DECISIONS ONLY THE OWNER CAN MAKE

None. Nothing in this workstream needs Albert before P3 starts.

Already settled, do not re-ask:

- 2026-08-09: execute `plan_r2_source_span_inventory_reader.md` in P0 through P8 order.
- 2026-08-09: keep the scorer, evidence rules, reader budgets, merge/apply flags, and one-production-gate limit frozen.
- 2026-08-10: P0, P1, and P2 are complete. P3 is next. Do not deploy or run the pinned production fixture before P7.
- 2026-08-10: GLM 5.2 independently approved the corrected P2 implementation for P3.

The next session can start P3 without sending Albert a decision request.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
upload business documents and ask questions. TypeScript workers find duties and process facts, bind
them to exact source quotes, and prepare reviewable business knowledge. The repository is
`u2giants/theoracle` at `C:\repos\oracle`, branch `main`. It is a `pnpm` and Turbo TypeScript
monorepo. The web app runs at `https://oracle.designflow.app`; workers run in Trigger.dev project
`proj_wgpzsvhmsopqhvwqaycn`; data lives in Supabase project `eqccjfbyrywsqkxxpjvg`.

This work changes the responsibility reader from model-first discovery to source-inventory-first
completion. Pure inventory, matching, completion, and validation rules live in
`apps/workers/src/lib/responsibility-reader.ts`. Worker orchestration and saved audit output live in
`apps/workers/src/lib/source-workflow-read.ts`. The verifier is
`apps/workers/src/__verify__/r2-responsibility-reader.ts`. The ordered implementation contract is
`plan_r2_source_span_inventory_reader.md`.

## 2. What we set out to do this session, and why

Albert asked to complete P2 of the R2 source-span inventory reader plan, then asked for an
independent GLM 5.2 review. P1 already built stable source-bound duty seeds. P2 had to turn clear
list duties into complete records without a model, attach model proposals exclusively to existing
seeds, preserve unmatched proposals only for audit, distinguish source/model/merge-ready coverage,
and split omission reporting into detection gaps versus completion gaps.

The business purpose is to prevent model omissions or duplicate phrasing from deciding which duties
exist. Source text defines the inventory first. Models may fill fields but may not invent merge-ready
duties.

## 3. Current state — what is true right now

- P2 is complete and `plan_r2_source_span_inventory_reader.md:25` marks it complete. The plan banner
  says P3 is next.
- `apps/workers/src/lib/responsibility-reader.ts:758` deterministically completes clear,
  list-structured, single-verb seeds. It preserves full post-verb object text and creates a
  destination-specific object for destination children.
- `apps/workers/src/lib/responsibility-reader.ts:796` exclusively matches proposals to seeds. One
  proposal can claim only one seed; a seed can accept at most one proposal; unmatched or ambiguous
  proposals remain audit-only. A newly exposed non-overlapping raw duty span is rerun through the
  same pure inventory builder before it can become a seed.
- `apps/workers/src/lib/responsibility-reader.ts:1453` treats a destination parent as covered only
  when every contained child seed has a complete element. Omission rows now say either
  `inventory_detection_gap` or `completion_gap`.
- `apps/workers/src/lib/responsibility-reader.ts:2200` lets the normal validator recognize an
  already split destination seed. It validates the child-specific span and does not expand the
  parent destination list again.
- `apps/workers/src/lib/source-workflow-read.ts:2323` applies completion and matching before normal
  validation. `apps/workers/src/lib/source-workflow-read.ts:2899` persists separate source,
  model-discovered, and merge-ready counts and ID lists plus unmatched and incomplete IDs.
- The combined repair revalidation also receives inventory seed context, so a repaired destination
  child cannot be expanded a second time.
- The verifier directly covers deterministic validation, destination one-to-one output, shortened
  partial-overlap proposal rejection, overlap/offset/quote/source integrity failures, unmatched
  proposals, ambiguous incomplete seeds, and zero model-discovery coverage when model output is
  empty.
- GLM 5.2 session `r2-inventory-p2-review` first returned `CHANGES REQUIRED BEFORE P3`, then after
  corrections returned `APPROVED FOR P3`. Its final report was generated locally at
  `.ai/reviews/glm-r2-inventory-p2-review-20260810T162228Z.md`; `.ai` is unrelated untracked working
  material and is not part of this session's commit.
- Local verification passed: `pnpm --filter @oracle/workers run verify:r2-responsibilities`,
  `pnpm --filter @oracle/workers typecheck`, `pnpm --filter @oracle/workers lint`, and
  `git diff --check`.
- This handoff is being written before the closeout commit. The closeout session must update this
  section's Git evidence through the final report after commit/push/CI. No deployment or production
  fixture was run because the plan reserves both for P7.
- P3 through P8 have not started. P3 is the only valid next implementation step.

## 4. Everything we tried that did NOT work

1. The first P2 implementation passed its local verifier and typecheck, but GLM 5.2 found two real
   production blockers. Local tests did not initially send deterministic records through the normal
   validator, so they missed destination children being expanded again from the shared parent quote.
   For three destinations, that could create nine elements. The fix passes seed context to the same
   validator, uses the child-specific fidelity span, and blocks re-expansion for an already split
   child.
2. The first unseeded-duty discovery path reran the inventory builder for a unique proposal quote and
   then asserted the combined inventory. A common shortened quote, such as the source sentence
   without its final period, partially overlapped the existing seed and could throw, failing the
   whole worker. The fix rejects newly discovered overlapping seeds before the integrity assertion;
   the proposal remains unmatched audit-only.
3. The first omission coverage logic compared a destination child against the full parent span. No
   single child contains every destination, so a fully covered parent could still appear as a
   `completion_gap` and trigger a retry. The fix checks that all contained child seed IDs have
   complete elements.
4. The first audit override mixed destination expansion element IDs with inventory seed IDs. That
   falsely listed complete destination seeds as incomplete. Keeping pre-split destination child IDs
   unchanged through validation fixed the count and ID contract.
5. GLM suggested asserting seven complete deterministic elements in the generic verifier fixture.
   That was wrong: two multi-verb seeds are intentionally incomplete at P2, so five are complete.
   The real test now asserts five clear records and separately proves there are no hidden `_dst_`
   expansion artifacts.
6. The first verifier command used the wrong script name,
   `verify:r2-responsibility-reader`. The package script is `verify:r2-responsibilities`; using the
   correct name passed.

## 5. Root causes and key findings

- Destination child seeds intentionally share the exact parent evidence quote and raw offsets. Seed
  identity plus `splitValue`, not quote text alone, is what distinguishes them. This is enforced in
  `apps/workers/src/lib/responsibility-reader.ts:796`.
- Passing deterministic output through the same validator is correct, but the validator needs seed
  context to know that a destination list was already split. Without it, legacy deterministic
  expansion runs again. The fixed context lookup starts at
  `apps/workers/src/lib/responsibility-reader.ts:2200`.
- Partial source overlap must be rejected before adding a discovered seed. Integrity assertions are
  still loud for invalid stored inventory; ordinary imperfect model quotes are audit failures, not
  worker crashes.
- Merge-ready audit IDs must stay in the inventory seed ID domain. Destination `_dst_` IDs belong to
  the legacy unsplit expansion path and must not replace already split seed IDs.
- Clear deterministic completion is deliberately narrow. List-structured, single-verb duties with a
  grounded owner can complete. Ambiguous or multi-verb seeds remain incomplete for P3's exhaustive
  completion work.
- GLM's final review used model `zai-coding-plan/glm-5.2`. Its follow-up read 133,184 cached tokens
  and returned `APPROVED FOR P3`.

## 6. Exact next steps

1. Read `AGENTS.md`, `HANDOFF.md`, this file, and all of
   `plan_r2_source_span_inventory_reader.md`. Confirm its STATUS table marks P0 through P2 complete
   and P3 open. You will know it worked when P3 is the only valid starting step.
2. Confirm local `main` equals `origin/main` and preserve unrelated untracked `.ai`, screenshot, and
   browser files. Do not stage or delete them. You will know it worked when `git status --short`
   shows no unexpected tracked edits before P3 begins.
3. Implement P3 exactly as written in the plan: shallow strict completion schema, completion-only
   prompt, stable token estimator and packer, low/expected/high budget forecast, exhaustive residual
   queue, budget reservation through `SourceReaderBudget.reserveRead`, and loud unscheduled/failure
   audit. You will know it worked when every residual seed is scheduled once within forecasted
   limits or records a loud reason it was not scheduled.
4. Add the P3 tests named by the plan in
   `apps/workers/src/__verify__/r2-responsibility-reader.ts` and
   `packages/ai/src/__verify__/workflow-read-smoke.ts`. Include empty model output, exact one-response
   per seed, extra/missing response rejection, stable packing, and budget exhaustion. You will know
   it worked when both verifiers and both package typechecks pass.
5. Continue P4 through P6 in plan order, using local evidence and the required independent read-only
   review. You will know it worked when only complete records enter final `elementsJson`, every seed
   has a terminal audit state, and the P6 reviewer says `APPROVED FOR CI AND LIVE REGATE`.
6. Do not deploy or run the pinned production fixture until P7. At P7, follow the plan's single
   production gate and then apply the frozen P8 score rule. You will know the constraint held when
   P3 through P6 contain local/review evidence only and exactly one production run is recorded at P7.

## 7. Constraints and gotchas in force

- Work only on `main`; commit as `Albert Hazan <u2giants@users.noreply.github.com>`.
- Preserve unrelated untracked work and stage exact files only. Many `.ai`, screenshot, and browser
  artifacts predate this session and belong to other workstreams.
- Do not rerun the model bake-off, weaken quote or field rules, add fixture-specific terms to runtime
  code, raise budgets, hard-code a model, or run an early production gate.
- Frozen reader limits are 40 calls, 500,000 input tokens, and $10. Post-pass limits are one quote
  repair, five omission retries, and one retry per chunk.
- Merge and apply remain false. No database or schema change is authorized for P3.
- A proposal never creates a merge-ready duty by itself. It must bind exclusively to an existing or
  newly inventory-built, non-overlapping source seed.
- Destination siblings can share quote and offsets. Never deduplicate them by quote text or offsets;
  use `inventorySeedId` and `splitValue`.
- `HANDOFF.d/` exceeds the five-open-file warning threshold. Never delete another session's handoff
  without proof that its workstream is complete.

## 8. Access and environment

- Checkout: `C:\repos\oracle`, repository `u2giants/theoracle`, branch `main`.
- GitHub CLI is authenticated. Git identity is verified as
  `Albert Hazan <u2giants@users.noreply.github.com>`.
- GLM review harness is `ai-glm` with `AI_GLM_CALLER=codex`; reusable session name is
  `r2-inventory-p2-review`.
- Secrets live only in 1Password vault `vibe_coding`. P2 did not read, create, rotate, or expose a
  secret. No `.env` file changed.
- Later P7 deployment uses the Trigger.dev management credential stored in 1Password item
  `Trigger.dev Personal Access Token (management)`. Later protected DB checks use the current Oracle
  Supabase DB item and `oracle_session_pooler` field. Never print or save their values.
- Production targets are the web app at `https://oracle.designflow.app`, Trigger.dev project
  `proj_wgpzsvhmsopqhvwqaycn`, and Supabase project `eqccjfbyrywsqkxxpjvg`. They were not mutated in
  P2.

## 9. Open questions and risks

- No owner question is open before P3.
- Risk: P3 completion responses must preserve immutable seed identity and return exactly one record
  per requested seed. Extra, missing, or duplicate IDs must fail loudly.
- Risk: the P3 packer must forecast calls, tokens, and cost before dispatch. Production truncation is
  not an acceptable scheduling strategy.
- Risk: omission retries still use forced span IDs in the legacy path. P4 must rebuild orchestration
  around exhaustive inventory completion without allowing a forced retry record to bypass seed
  identity.
- Decision dated 2026-08-10: two multi-verb generic fixture seeds remain incomplete at P2 by design;
  do not loosen deterministic completion merely to raise the local complete count.
- Decision dated 2026-08-10: GLM's final `APPROVED FOR P3` closes the two original blockers. A third
  GLM turn is unnecessary unless P3 changes the reviewed P2 seam.

## Handoff self-audit

1. Yes. Sections 1 through 3 explain the product, repository, runtime, goal, exact code seams,
   verification, and current phase so a brand-new developer can continue without this chat.
2. Yes. Sections 4 and 5 preserve every failed attempt, both GLM blockers, the wrong GLM test-count
   suggestion, and all non-obvious destination/identity findings needed to continue as effectively
   as this session.
3. Yes. Sections 1 through 9 include background, intended outcome, current state, failures,
   decisions, constraints, access, risks, and exact next actions. Section 3 contains local evidence;
   the closeout report will provide the final commit, push, and CI evidence.
4. Yes. A line-by-line sweep of sections 1 through 9 found no sentence needing Albert's judgement.
   Section 0 therefore explicitly says none and lists the dated decisions that must not be re-asked.

Self-audit result: passed. All ten sections are present; secrets are location-only; failed paths and
why they failed are preserved; every next step has a verification gate; and a street-new developer
can start P3 without asking a question.
