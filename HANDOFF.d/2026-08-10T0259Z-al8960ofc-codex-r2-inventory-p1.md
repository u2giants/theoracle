# R2 source-span inventory reader P1 handoff

## 0. ⚠️ DECISIONS ONLY THE OWNER CAN MAKE

None. Nothing in P2 needs Albert before implementation. Already settled, do not re-ask:

- 2026-08-09: execute `plan_r2_source_span_inventory_reader.md` in P0 through P8 order.
- 2026-08-09: keep the scorer, evidence rules, budgets, merge/apply flags, and one-production-gate
  limit frozen.
- 2026-08-10: P1 passed and the next session starts at P2. Do not rerun a model bake-off or deploy.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
upload business documents and ask questions. Workers find duties and process facts, keep exact
source quotes, and prepare reviewable business knowledge. The repository is `u2giants/theoracle` at
`C:\repos\oracle`, branch `main`. The web app runs at `https://oracle.designflow.app`; workers run in
Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`; data lives in Supabase project
`eqccjfbyrywsqkxxpjvg`.

The current work replaces a model-first responsibility reader with an inventory-first reader. Pure
rules live in `apps/workers/src/lib/responsibility-reader.ts`; worker calls and saved results live in
`apps/workers/src/lib/source-workflow-read.ts`; schemas and prompts live in
`packages/ai/src/prompts/workflow-read.ts`.

## 2. What we set out to do this session, and why

Albert asked to complete P1 of `plan_r2_source_span_inventory_reader.md`. The old reader scored only
12/30 on a pinned production document because duties became work only when a model emitted them or a
small retry queue found them. P0 proved that source inventory and deterministic completion have a
credible path for all 30 expected duties. P1's job was to create one stable, exact source-bound work
item for every duty before model output is considered.

## 3. Current state, what is true right now

- P1 is complete in commit `a9c1cb8283154d9a9bca0aa86b40f39e5b435a0e`, pushed to `main`.
- GitHub Actions run `31351346476` passed every check in 2m14s.
- `ResponsibilityInventorySeed` and its audit-parent type are in
  `apps/workers/src/lib/responsibility-reader.ts`. IDs derive only from chunk ID, exact offsets,
  normalized span hash, and a destination suffix when needed.
- `buildResponsibilitySourceInventory` now returns active seeds plus audit-only split parents. It
  fails loudly for duplicate chunk/seed identities, missing chunks, invalid offsets, quote mismatch,
  and unrelated overlapping recognition.
- Owner headings remain in normalized `sourceSpan`; `evidenceQuote` always remains the exact raw
  slice. Repeated identical text gets different stable IDs because offsets differ.
- Clear multi-destination duties become one active child per destination. Clear multi-verb duties
  become one exact clause child per verb/object. Their parents stay audit-only. Unsafe compound text
  remains one incomplete parent marked `ambiguous_multi_verb`.
- `buildResponsibilityBaseReadPlan` exposes `inventorySeeds` and `inventoryAuditParents` at the real
  production seam. P2 can consume them without rebuilding inventory.
- Generic verifier coverage is in
  `apps/workers/src/__verify__/r2-responsibility-reader.ts`. It uses invented roles, objects, and
  destinations, not pinned company fixture terms.
- Local `@oracle/workers` typecheck, R2 responsibility verifier, and `git diff --check` passed before
  commit. No database, provider setting, worker deployment, production fixture, merge flag, or apply
  flag changed. P2 through P8 have not started.

## 4. Everything we tried that did NOT work

1. The first verification command used a package script name that does not exist. The package manager
   warned and returned without running the verifier. The correct command is
   `pnpm --filter @oracle/workers run verify:r2-responsibilities`; it then ran and passed.
2. The first generic fixture expected seven active seeds. The correct count is eight: two repeated
   single duties, three destination children, two compound-duty children, and one modal-prose duty.
   The assertion was corrected, not the reader.
3. The first destination fixture used names beginning with `Archive`. `archive` is also a duty verb,
   so the strict multi-verb detector honestly treated those names as possible actions and refused the
   destination split. Generic `Hub North/South/West` names test the intended destination grammar
   without that lexical collision. Do not special-case `Archive` in runtime code.

## 5. Root causes and key findings

- `sourceDutySpanDetails` already had reliable ordered raw binding. P1 extends its internal detail
  record with an exact compound-parent span so children and their audit-only parent share provenance.
- Stable identity must include offsets. A content hash alone collapses repeated identical duties in
  one chunk.
- Destination children legitimately share the parent's exact evidence offsets. The overlap guard
  therefore permits only declared parent/child or sibling relationships and rejects unrelated overlap.
- Existing destination safety rules were reusable as pure grammar: directed action, supported
  preposition, non-empty object head, unique normalized destinations, and date/person-list guards.
- An ambiguous compound cannot be thrown away or guessed. It remains one active incomplete seed with
  `ambiguous_multi_verb`, ready for P2/P3 completion rules while staying out of merge-ready output.

## 6. Exact next steps

1. Read `AGENTS.md`, `HANDOFF.md`, this file, and all of
   `plan_r2_source_span_inventory_reader.md`. Confirm its STATUS table says P0 and P1 complete and P2
   open. You will know it worked when P2 is the only valid starting step.
2. Confirm local `main` equals `origin/main`, inspect all local changes, and preserve unrelated
   untracked `.ai`, screenshot, and browser files. You will know it worked when only P2 files will be
   edited or staged.
3. Inspect the P1 types and builder plus the P2 production consumer in
   `apps/workers/src/lib/source-workflow-read.ts`. You will know it worked when the existing base-model
   proposal path and final complete-only assembly are understood.
4. Mark P2 in progress in the plan. Implement exact exclusive proposal matching, three separate
   inventory counts, split omission classes, and deterministic completion exactly as P2 specifies.
   You will know it worked when empty model output keeps source inventory and clear list duties finish
   without a model.
5. Route every deterministic result through the existing strict validator. Keep unmatched proposals
   audit-only and reject repeated-text ambiguity, partial overlap, and parent/child cross-matches. You
   will know it worked when no proposal alone can become merge-ready.
6. Run the P2 verifier and relevant typechecks, update the STATUS row only after they pass, then
   continue P3 and P4 in order. You will know it worked when every residual seed is scheduled once or
   named as failed, and only complete records reach final elements.
7. Stop at context cut B after P4 and create a new write-once handoff. Do not run production before P7.
   You will know it worked when a fresh verification session can begin P5 without this chat.

## 7. Constraints and gotchas in force

- Work only on `main`; commit as `Albert Hazan <u2giants@users.noreply.github.com>`.
- Preserve unrelated untracked work and stage exact files only.
- Do not redesign the approved plan, rerun the bake-off, weaken quote/field rules, add fixture terms
  to runtime code, raise budgets, or hard-code a model.
- Frozen reader limits are 40 calls, 500,000 input tokens, and $10. Post-pass limits are one quote
  repair, five omission retries, and one retry per chunk.
- Merge and apply remain false. No database or production mutation is authorized before P7.
- Destination and multi-verb parents are audit-only. Incomplete seeds never become evidence or merge
  input.
- `HANDOFF.d/` now contains six open files, above the warning limit. Do not delete another session's
  file. Albert should later decide which older workstreams are truly finished.

## 8. Access and environment

- Checkout: `C:\repos\oracle`, repository `u2giants/theoracle`, branch `main`.
- GitHub CLI is authenticated; push and Actions evidence succeeded in this session.
- 1Password secrets live only in vault `vibe_coding`. P2 should not need them.
- Later P7 deployment uses item `Trigger.dev Personal Access Token (management)`.
- Later protected DB checks use item `Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle,
  eqccjfbyrywsqkxxpjvg)`, field `oracle_session_pooler`. Never print or save values.
- Production systems are Supabase `eqccjfbyrywsqkxxpjvg`, Trigger.dev
  `proj_wgpzsvhmsopqhvwqaycn`, and web `https://oracle.designflow.app`.

## 9. Open questions and risks

- P2 risk: destination names that are also recognized duty verbs can look like compound actions.
  Preserve the strict ambiguous result; do not add business-specific exceptions.
- P2 risk: exclusive matching must distinguish repeated identical text by offsets, not quote text alone.
- P2 risk: deterministic objects must retain timing, cadence, system, and destination words. Never thin
  the object merely because optional fields repeat them.
- Decision dated 2026-08-10: P1 passed on local gates and GitHub Actions. This approves P2 only, not a
  production run or any relaxation of the frozen contract.

## Handoff self-audit

1. Yes. Sections 1 through 3 define the app, goal, production shape, exact P1 behavior, commit, push,
   CI, and untouched systems for a street-new developer.
2. Yes. Sections 4 and 5 preserve every failed attempt and the non-obvious identity, overlap,
   ambiguity, and lexical-collision findings.
3. Yes. Sections 6 through 9 give ordered P2 actions with a success gate for each, all constraints,
   access locations without values, and dated risks and decisions.
4. Yes. A line-by-line owner-decision sweep of sections 1 through 9 found no new owner choice. Section
   0 says so and lists every already-settled decision that must not be re-asked.

Self-audit result: passed. All ten required sections are present, failures and exact next steps are
complete, secrets are location-only, and a fresh developer can start P2 without this chat.
