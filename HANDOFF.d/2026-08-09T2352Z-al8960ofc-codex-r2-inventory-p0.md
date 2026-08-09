# R2 source-span inventory reader P0 handoff

## 0. ⚠️ DECISIONS ONLY THE OWNER CAN MAKE

None. Nothing in this workstream needs Albert before P1. Albert already approved the source-span
inventory plan, the unchanged scorer and evidence rules, the frozen budgets, and the one-gate rule.

Already settled, do not re-ask:

- 2026-08-09: implement `plan_r2_source_span_inventory_reader.md` in P0 through P8 order.
- 2026-08-09: do not reopen the model bake-off, run Batch G, weaken validation, or add fixture terms
  to runtime code.
- 2026-08-09: stop at each plan context cut and leave a new write-once handoff.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
upload business documents and ask questions. TypeScript workers find duties and process facts, bind
them to exact source quotes, and prepare reviewable business knowledge. The repository is
`u2giants/theoracle` at `C:\repos\oracle`, branch `main`. The web app runs at
`https://oracle.designflow.app`; workers run in Trigger.dev project
`proj_wgpzsvhmsopqhvwqaycn`; data lives in Supabase project `eqccjfbyrywsqkxxpjvg`.

The current work changes the responsibility reader. Its orchestration is
`apps/workers/src/lib/source-workflow-read.ts`; its pure rules are
`apps/workers/src/lib/responsibility-reader.ts`; its AI schemas and prompts are
`packages/ai/src/prompts/workflow-read.ts`.

## 2. What we set out to do this session, and why

Albert asked to execute `plan_r2_source_span_inventory_reader.md` exactly, starting at P0. The prior
model-first reader scored only 12/30 on a pinned production responsibility document. Two GPT-4.1
bake-off maps scored 11/30 and 12/30. The approved design inverts control: exact source spans create
the duty inventory before model output, pure rules complete clear duties, and model calls fill every
remaining seed within the frozen budget.

P0's purpose was to prove that architecture, rather than scorer changes, has a credible mechanism
for at least 27 of the 30 answer-key rows. Runtime code could not change until that gate passed.

## 3. Current state, what is true right now

- Local `main` was safely fast-forwarded from `1988398` to remote commit
  `17dfb1920b7a4de92f674afc3cf418c540167a58`. No unrelated untracked file was changed.
- Git identity was verified as `Albert Hazan <u2giants@users.noreply.github.com>`.
- P0 is complete in `plan_r2_source_span_inventory_reader.md:23`; the fresh-session pointer is P1.
- The durable P0 matrix is at the end of `evals/r2-responsibilities.md`. It covers all 30 rows across
  deeper map `193376a7-848e-48e8-b5ec-8cca51285b3f` and bake-off maps
  `5f1491c7-e38b-4c07-a063-121244215dda` and `14724714-edc1-4012-a932-44cfd6c8ed23`.
- The matrix finds credible non-scorer mechanisms for 30/30 rows. No `scorer_mismatch` is suspected.
  P0 therefore clears the required 27-row stop gate.
- `apps/workers/src/__verify__/r2-residual-matrix-source.ts` is a verifier-only, read-only utility
  used to re-score the three immutable saved maps. It contains map IDs, not secrets.
- P1 through P8 have not started. No runtime code, database, worker, model setting, merge/apply flag,
  or production fixture changed. No production gate ran.
- Before the handoff commit, the P0 baseline passed worker, AI, and engines typechecks plus both
  current R2 responsibility verifiers. The next session must verify the final commit and remote CI
  state recorded by this session's commit before editing P1.

## 4. Everything we tried that did NOT work

1. The local plan was initially absent because local `main` was behind `origin/main`. A read-only
   fetch showed the plan on the remote and proved incoming files did not overlap unrelated untracked
   files. A fast-forward-only update then succeeded. Do not recreate the plan locally.
2. The first 1Password secret reference used the full item title. Parentheses made that reference
   invalid, so no secret was returned and the verifier stopped because `PROD_DB_URL` was empty. The
   working method is to list item metadata in vault `vibe_coding`, resolve the exact item's safe ID,
   then read field `oracle_session_pooler` by ID. Never print the field.
3. Tool output for the three map scores was truncated because all match evidence was verbose. The
   complete matched/missed sets were still present through the scorer results and were reduced into
   the durable 30-row matrix. Do not rely on chat output; use the committed matrix and rerun the
   verifier only if the saved maps need independent confirmation.

## 5. Root causes and key findings

- `plan_r2_source_span_inventory_reader.md:151` identifies the core failure: the current reader is
  model-first, so duties do not become durable work unless a model emits them or one of five scarce
  retries finds them.
- The three saved maps repeat almost the same miss set despite fresh calls. This supports an
  architecture cause, not a provider choice or scorer defect.
- The residual matrix maps all 30 rows to inventory, deterministic completion, source-only compound
  splitting, or residual completion. The recurring misses are missing numbered duties, compound
  source sentences, thinned objects, and owner/action/direction fidelity.
- Row 17 is not a scorer defect. The current object includes a nearby negative reorder note, causing
  a valid negation conflict. Deterministic field completion can isolate the duty fields while the
  immutable evidence quote remains exact.
- Row 29 contains tension between a `[Lic Coordinator]` heading and sentence text saying `Licensed
  team provides`. It remains a real owner/action fidelity problem for exclusive source-span matching,
  not permission to weaken the answer-key matcher.
- Frozen facts rechecked in P0: fixture SHA
  `398927caaf945cc313429d70836713980a29ae41d8109bc3592fd146dfca90be`, answer key
  `licensed-team-responsibilities-v1`, matcher `field-aware-v3`, pass 27/30, reader budget 40 calls /
  500,000 input tokens / $10, post-pass 1 quote repair / 5 omission retries / 1 per chunk, and merge /
  apply false.

## 6. Exact next steps

1. Re-read `AGENTS.md`, `HANDOFF.md`, this file, and all of
   `plan_r2_source_span_inventory_reader.md`. Confirm its STATUS table still says P0 complete and P1
   open. You will know this worked when P1 is the only valid starting step.
2. Confirm `main` equals `origin/main`, inspect all local changes, and preserve the large unrelated
   untracked `.ai`, screenshot, and browser files. You will know this worked when no unrelated path is
   staged or edited.
3. Read P1's full source set before editing:
   `apps/workers/src/lib/responsibility-reader.ts` and
   `apps/workers/src/__verify__/r2-responsibility-reader.ts`. Also follow imports needed to understand
   `sourceDutySpanDetails`, stable hashing, destination expansion, validation types, and fixture guards.
   You will know this worked when the existing span-binding and expansion contracts are understood
   without guessing.
4. Mark P1 `in progress` in the plan immediately. Implement only P1: a pure
   `ResponsibilityInventorySeed` builder with exact raw bindings, stable IDs, duplicate/overlap/bad
   offset failures, inherited owner normalization, locked destination children, locked multi-verb
   children, audit-only parents, and no model fields. Use `apply_patch`. You will know this worked when
   every recognized generic duty span gets one stable parent or valid child seed before model output.
5. Add P1's invented generic tests to the existing worker verifier. Do not use terms from the pinned
   company fixture in runtime code. You will know this worked when identical reruns are byte-stable,
   malformed bindings fail loudly, and ambiguous compounds remain incomplete rather than guessed.
6. Run P1's verification gate plus the relevant typecheck. Update the STATUS table to P1 complete
   only after it passes. You will know this worked when all P1 tests pass and `git diff --check` is
   clean.
7. Continue P2 through P4 in order. At context cut B, stop and create a different write-once handoff
   before the fresh verification session. Do not run production before P7. You will know this worked
   when the control flow is inventory-first and the plan's cut-point rule is honored.

## 7. Constraints and gotchas in force

- Work only on `main`. Verify Albert's Git identity before every commit.
- The plan is authoritative. Do not redesign it, rerun the bake-off, run Batch G, loosen the scorer or
  evidence rules, add fixture words to runtime code, skip stop gates, or raise budgets.
- Use deterministic inventory and deterministic completion before residual model calls.
- Merge and apply remain false. No database change is authorized.
- Update the plan STATUS row immediately whenever a step changes state.
- Preserve all unrelated work. Stage only this workstream's exact files.
- Use `apply_patch` for edits. Do not edit generated Drizzle migrations.
- Production access stays read-only until P7 except for P7's one explicitly authorized normal-path
  disposable upload and worker deployment.
- Exactly one production gate is allowed for the reviewed P7 release.
- There are five open files in `HANDOFF.d/` after this file, so the warning threshold of more than
  five is not crossed.

## 8. Access and environment

- Checkout: `C:\repos\oracle`, repository `u2giants/theoracle`, branch `main`.
- GitHub CLI is expected for push and CI evidence. Verify it with a real call before relying on it.
- 1Password CLI is authenticated as a service account. Secrets are in vault `vibe_coding` only.
- Production DB connection location: item `Supabase DB Direct URL - The Oracle (CURRENT PROD,
  theoracle, eqccjfbyrywsqkxxpjvg)`, field `oracle_session_pooler`. Resolve the item ID first because
  its title cannot be used directly in an `op://` reference.
- Trigger deployment credential location for P7: item `Trigger.dev Personal Access Token
  (management)` in vault `vibe_coding`.
- Production systems: Supabase `eqccjfbyrywsqkxxpjvg`, Trigger.dev
  `proj_wgpzsvhmsopqhvwqaycn`, web `https://oracle.designflow.app`.
- The P0 DB query was read-only and secrets were kept only in the process environment. No value was
  printed, saved, or committed.

## 9. Open questions and risks

- Open question from the approved plan: generic free-form prose recognition may be weaker than list
  recognition. P1 and P5 must measure it with invented fixtures, not the pinned answer key.
- Risk: destination and multi-verb splitting can over-split ordinary attribute lists. Locked guards
  in plan section 8 must be copied exactly and tested directly.
- Risk: the worktree contains many unrelated untracked `.ai` artifacts and screenshots. A broad stage
  command could accidentally commit them. Always stage explicit paths.
- Risk: the matrix is an architecture forecast, not proof of final 27/30 behavior. P5 must prove at
  least 27 supportable inventory rows locally, and P7 permits exactly one production result.
- Decision dated 2026-08-09: P0 passed because 30/30 rows have credible mechanisms and no scorer
  mismatch is suspected. This allows P1 but does not pre-approve later gates.

## Handoff self-audit

1. Yes. Sections 1 through 3 define the app, goal, exact repo state, completed P0 proof, and untouched
   production state for a brand-new developer.
2. Yes. Sections 4 and 5 preserve every failed attempt and non-obvious finding, including the safe
   1Password ID lookup and the two unusual residual rows.
3. Yes. Sections 6 through 9 give ordered actions with a success gate for each, every locked
   constraint, access locations without values, risks, and the dated decision.
4. Yes. A line-by-line sweep of sections 1 through 9 found no sentence needing Albert's judgment.
   Section 0 states that clearly and lists the already settled decisions that must not be re-asked.

Self-audit result: passed. All ten required sections are present, secrets are location-only, commit /
push / deploy state is explicit, and a fresh session can begin P1 without this chat.
