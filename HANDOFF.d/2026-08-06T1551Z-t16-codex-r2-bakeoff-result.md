# R2 responsibility-reader bake-off result

Created: 2026-08-06 15:51 UTC on machine `t16` by Codex.
Workstream status: OPEN because R2 still fails its frozen acceptance gate and R3-R10 remain blocked.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
ask company questions and upload documents; workers extract source-backed statements and build
reviewable structure; administrators review claims, gaps, translations, workflow maps, model
behavior, and quality results. The target is a durable business model whose answers remain
traceable to exact source evidence.

The code is the `u2giants/theoracle` TypeScript/pnpm monorepo at `C:\repos\oracle`, branch `main`.
The Next.js web app runs at `https://oracle.designflow.app`; Trigger.dev project
`proj_wgpzsvhmsopqhvwqaycn` runs workers; Supabase project `eqccjfbyrywsqkxxpjvg` stores production
data. `MACRO_FIRST_IMPLEMENTATION_PLAN.md` is the canonical forward plan.

## 2. What we set out to do this session, and why

Albert asked to pull the latest repository and continue the last session. Ground-truth recovery
showed local and GitHub `main` were already identical at `1b7d1c8`, the tree was clean, and the
newest open handoff stopped after the deeper R2 responsibility reader scored 12/30. Albert then
explicitly approved the recommended bounded production model bake-off.

The technical goal was to test whether changing only the eligible `workflow_read` model could
reach the frozen 27/30 responsibility gate. The fixture, answer key, `field-aware-v3` scorer,
strict evidence policy, reader budgets, post-pass limits, and disabled merge/apply settings could
not change. The precommitted decision rule was: mean >=27 may seat a winner; 24-26 requires deeper
architecture; <=23 fails the bake-off, requires deeper architecture, and forbids a second bake-off.

## 3. Current state — what is true right now

The bake-off is complete and failed honestly. Production capability data marked Claude Sonnet 5
and Gemini 2.5 Pro ineligible because `deep_schema_accepted=false`; GPT-4.1 was the only eligible
specified candidate. Two serialized forced reads of frozen disposable document
`c4ba034f-fb6c-40ee-a98e-fd20166a438b` produced:

- Trigger `run_06ftfd4h0b8erk4pr99u2hlg01`, map
  `5f1491c7-e38b-4c07-a063-121244215dda`: 11/30, 79 responsibilities, 395 kept / 164 dropped,
  23 calls, 58,923 input tokens, estimated input cost $0.294615.
- Trigger `run_06ftffk1dpavmptpve978aot01`, map
  `14724714-edc1-4012-a932-44cfd6c8ed23`: 12/30, 81 responsibilities, 350 kept / 148 dropped,
  22 calls, 55,620 input tokens, estimated input cost $0.278100.

Mean score is 11.5/30 with a one-point spread. Both final model attempts prove provider `openai`,
model `gpt-4.1`, success, no fallback, and prompt `responsibility-read-v2.4-span-bound`. The
detailed evidence is `evals/bakeoffs/workflow-read.md:1`; the canonical R2 status is updated at
`MACRO_FIRST_IMPLEMENTATION_PLAN.md:22`, `plan_r2_deeper_responsibility_architecture.md:3`, and
`evals/r2-responsibilities.md:672`.

Production was restored and re-read after the runs: primary `openai/gpt-4.1`; pool
`[openai/gpt-4.1, anthropic/claude-sonnet-5, google/gemini-2.5-pro]`; merge false; apply false;
`business_objects=0`; `business_object_versions=0`; `business_model_changes=0`. The fixture's
latest map is the second bake-off map and is terminal `degraded`; its prior maps remain immutable
and superseded.

Only documentation is changed locally at handoff-writing time. No product code, schema,
deployment, fixture chunks, claims, or production business-model rows were changed. The docs and
this handoff still need commit, push, and CI verification in this same closeout.

## 4. Everything we tried that did NOT work

1. The first SQL settings write used an already-serialized JSON string. Read-back exposed the
   known double-encoding trap: the primary and pool values contained escaped JSON strings. The
   values were immediately corrected with `to_jsonb(text)` and `jsonb_build_array(text...)`, then
   verified as JSON types `string` and `array`. Do not copy the rejected `JSON.stringify(value)::jsonb`
   pattern. Run 1 remains valid because its durable model attempts prove every actual call used
   GPT-4.1 successfully after correction; no fallback or malformed route was used.
2. Trigger.dev MCP and the local Trigger CLI both returned `Invalid or Missing Access Token`.
   This is the documented client-authentication issue, not proof that the credentials are bad.
   The working route was the Trigger SDK with the production environment key from 1Password.
3. The first ad-hoc scorer query filtered a PostgreSQL `timestamp without time zone` using an ISO
   timestamp that the client interpreted differently, so it found no map. Scoring by the durable
   map UUID removed the ambiguity. Do not use mixed local/UTC timestamp filtering for these maps.
4. Claude Sonnet 5 and Gemini 2.5 Pro could not be run because production capability truth marks
   both as not accepting the deep schema. Do not force them by disabling enforcement; that would
   invalidate the bake-off and hide a known schema failure.
5. Model choice did not improve R2. GPT-4.1's two scores, 11 and 12, remain far below 27 and align
   with the preceding 12/30 gate. The failure is not budget exhaustion: both runs used about 22-23
   of 40 calls, 56k-59k of 500k input tokens, one permitted repair, and under $0.30 of the $10 cap.

## 5. Root causes and key findings

The result rules out a bounded candidate swap as the R2 solution. The stable failure clusters from
the earlier deeper gate remain: inventory is low, explicit multi-destination duties disappear,
objects lose required qualifiers, action direction reverses, and cadence/timing details thin out.
The model had ample budget, so increasing limits is not justified.

Only one specified model currently passes the production deep-schema eligibility contract. A
three-name configured fallback pool is not the same as three eligible bake-off candidates; runtime
capability enforcement correctly prevents the two invalid candidates from silently participating.

The exact next decision is now deterministic, not owner-choice ambiguity: the frozen rule requires
another deeper-architecture step and forbids another bake-off. The resume point is recorded in
`MACRO_FIRST_IMPLEMENTATION_PLAN.md:32` and
`plan_r2_deeper_responsibility_architecture.md:27`.

## 6. Exact next steps

1. Commit and push the four evidence/plan documents plus this handoff on `main`, using Albert Hazan
   as both author and committer. You will know it worked when local and `origin/main` contain the
   same new SHA and `git status` is clean.
2. Verify the documentation-only GitHub Actions run is green. You will know it worked when the
   pushed SHA has a successful Actions conclusion; no worker or Vercel deployment is required
   because no runtime file changed.
3. In a fresh session, read `MACRO_FIRST_IMPLEMENTATION_PLAN.md`,
   `plan_r2_deeper_responsibility_architecture.md`, and `evals/bakeoffs/workflow-read.md`; write a
   bounded next deeper-architecture implementation plan that directly addresses inventory
   discovery, field completion, explicit multi-destination output, direction, cadence, and timing.
   You will know the plan is executable when it freezes the existing fixture/scorer/budgets and
   contains tests, an independent review gate, exactly one future production gate, and explicit
   no-write/merge/apply guards.
4. Do not implement until that new architecture plan has been independently reviewed. You will
   know review passed when the review records no unresolved P0/P1 findings and all accepted changes
   are incorporated before code work.
5. After implementation, local verification, commit, green CI, and worker deployment, run exactly
   one fresh pinned production gate. You will know R2 can proceed only if the unchanged scorer is
   >=27/30; 24-26 or <=23 must follow the new plan's precommitted stop rule. Do not enable merge or
   apply merely because inventory improves.

## 7. Constraints and gotchas in force

Use `main` only. GitHub is source of truth. Never modify generated Drizzle SQL manually and do not
introduce an app-repo migration for this R2 work. Preserve exact quote validation, immutable maps,
the frozen answer key SHA, `field-aware-v3`, 27/30 threshold, 40 calls / 500k input tokens / $10
reader limits, 1 general repair / 5 omission retries / 1 retry per chunk, and false merge/apply.

No second model bake-off, Batch G prompt polish, answer-key leakage, company-specific hard-coding,
scorer weakening, schema-enforcement bypass, multi-model voting, or hidden fallback is allowed.
Do not rerun the retired outline/lens/macro/coverage harness. Do not edit root `HANDOFF.md` or either
older file under `HANDOFF.d/`; each belongs to another session.

## 8. Access and environment

Checkout: `C:\repos\oracle`, machine `t16`, branch `main`. Production web:
`https://oracle.designflow.app`. Supabase project: `eqccjfbyrywsqkxxpjvg`. Trigger.dev project:
`proj_wgpzsvhmsopqhvwqaycn`.

GitHub access works. Production database access worked through the session-pooler field in
1Password vault `vibe_coding`, item `Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle,
eqccjfbyrywsqkxxpjvg)`. Trigger dispatch worked through the production API-key field in item
`Trigger.dev Secret Key - The Oracle (local .env.local)`. The Trigger MCP and CLI were not
authenticated in this process; do not rotate credentials because of that known client issue.
Never copy secret values into files, logs, commits, or chat.

## 9. Open questions and risks

- 2026-08-06: the next deeper architecture is not designed yet. The observed deficits name its
  required targets, but implementation must not start from an improvised code patch.
- 2026-08-06: production's configured fallback pool includes two models that are currently deep-
  schema-ineligible. Runtime enforcement keeps this safe, but future catalog changes could alter
  eligibility; any change must be measured, not assumed.
- 2026-08-06: the latest fixture map is degraded and scored 12/30. It is disposable evaluation
  evidence, not served business-model content; merge/apply remain off and durable model tables are
  empty.
- 2026-08-06: other open reliability and deferred product workstreams remain documented in the
  older handoffs and canonical gap plans. This session changed only R2's decision state.

## Self-audit

1. **Yes, a street-new developer can continue without this chat.** Sections 1-3 define the
   application, systems, exact objective, authorization, runs, maps, scores, current settings, and
   unshipped documentation state; section 6 gives ordered work with verification gates.
2. **Yes, they can continue as effectively as this session.** Section 4 preserves every failed
   attempt and why; section 5 records the model-eligibility and non-budget root findings; sections
   7-8 preserve all frozen controls, access paths, and authentication traps without secret values.
3. **Yes, every execution-critical detail is present.** Sections 1-2 cover background and intended
   outcome, section 3 covers evidence and commit/deploy state, sections 4-5 cover failures and
   findings, section 6 covers exact next actions, section 7 covers constraints, section 8 covers
   access, and section 9 covers dated questions and risks. All nine required sections are present
   and the final reread found no missing term, identifier, decision, or verification gate.
