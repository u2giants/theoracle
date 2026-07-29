# Repository Reliability and Release Gaps Plan

Status: **CANONICAL for known reliability, verification, migration-drift, release-automation,
and misleading-code-note problems that are outside the macro-first feature sequence.**

Created: 2026-07-26
Last corrected: 2026-07-26 after Grok 4.5 repository review
Repository: `C:\repos\oracle`, GitHub `u2giants/theoracle`, branch `main`
Production web: `https://oracle.designflow.app`
Workers: Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`
Database: Supabase project `eqccjfbyrywsqkxxpjvg`

## Status table

| Step | Status | Evidence or blocker |
|---|---|---|
| REL-1 Stale verification script and false comments | ✅ done, 2026-07-26 | Deleted the obsolete pre-migration-89 workflow audit; corrected Teams, typing-presence, storage-bucket, and retrofit-status notes; REL-1 search/diff gates passed (full worker gate is temporarily blocked by a concurrent out-of-scope taxonomy test edit) |
| REL-2 Reconcile ERR-003, ERR-004, ERR-005 with the current reader | 🟨 partial, 2026-07-27 | ERR-003 is closed by source removal plus deployed worker `20260722.1`; ERR-004 and ERR-005 still require owner-authorized fixture reruns |
| REL-3 Retire or retarget the obsolete macro-support SQL smoke | ✅ done, 2026-07-27 | Zero-caller search proved the three query contracts and package command had no runtime or CI owner; deleted the smoke and package script without restoring retired writers |
| REL-4 Model-pool phantom fallback audit | ✅ done, 2026-07-27 | Released in `5f962b5`/`24bbf70`; CI `30269886119` attempt 2 green, migration/drift green, Vercel HTTP 200, and Trigger worker `20260727.2` deployment `h6ri0rb9` |
| REL-5 Migration 65 and generated-snapshot drift | ✅ done, 2026-07-29 | R1's fresh/rerun gates already proved raw migration replay; focused verifier now checks migration 65, latest snapshot, and applied columns; current production columns and the 12-row generated journal agree |
| REL-6 Live image upload verification | ⬜ open | Requires an owner-approved non-sensitive image fixture |
| REL-7 Database and Trigger.dev release automation | ⬜ open | Starts after REL-2 through REL-5 establish the current release contract |
| REL-8 Dead schema-repair helper removal | ⬜ open | Wait until macro R10 unless a current caller is introduced |
| REL-9 Close logs and documentation | ⬜ open | Depends on all earlier applicable steps |
| Claude conditional-review queue | ⏸ blocked | Four unresolved conditional suggestions remain in §9; the former ERR-002 smoke question was resolved by REL-3 and removed |

Fresh-session starting point: REL-2 must use only the current map-directed reader files named
below. REL-3 starts with a zero-caller proof before deciding whether the old smoke script should
be deleted or retargeted. Coordinate REL-5 with macro R1.

## 1. Ultimate goal

The Oracle must report failures clearly, reproduce its database safely, and release web, worker,
and database changes without relying on stale scripts or tribal knowledge. Every deployed fix must
have a recorded proof that the real failure stopped happening.

If a step conflicts with this goal, the goal wins. Stop and record the conflict before changing
code, data, release behavior, or evidence rules.

## 2. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
use the Vercel-hosted web app. Trigger.dev workers ingest chats and documents, create evidence-backed
claims, and build macro business structure. Supabase stores users, sources, claims, maps, audits,
and settings. It is a TypeScript `pnpm` and Turborepo monorepo with Next.js, Trigger.dev, Drizzle,
and provider-specific AI adapters.

Code truth is GitHub branch `main`. Production changes flow from the repo through CI and the normal
Vercel, Trigger.dev, and journaled database release paths.

## 3. What triggered this work

Known problems were spread across `AGENT_ERROR_LOG.md`, `AGENTS.md` section 15, code comments,
Kimi K3's 2026-07-26 full-repo review, and old handoff history:

- ERR-003 and ERR-004 were written for outline, lens, macro, and coverage workers that Stage 3 later
  deleted. ERR-003 is fixed in source by removal of the fan-out architecture; ERR-004 must be
  rewritten around the current map-directed reader. ERR-005 still needs its current-path rerun.
- The now-retired `scripts/verify-workflow-map-prod.mjs` selected removed
  `source_outline_id` and used `macro_relationships.confidence` instead of `confidence_score`.
- `apps/workers/src/lib/schema-repair.ts` has no callers and hard-codes a route.
- ERR-002's former runtime queries have no current writer callers. A standalone database smoke still
  contains those queries, is exposed by a package script, and is not wired into CI.
- ERR-001 still contains an old instruction to add a DeepSeek key or remove a phantom fallback.
  Current pool state must be checked before that instruction is acted on.
- Migration 65 is intentionally raw-SQL-owned. The former warning that generated drift or fresh
  database creation may disagree was stale and is closed by REL-5's snapshot, fresh-DB, live-schema,
  and generated-journal evidence.
- The Teams transcript worker's top comment said speaker email resolution and meeting-time
  anchoring were TODOs, but the same file already implemented both.
- The lull-interjection header and `DECISIONS.md` said typing presence was hard-coded false,
  but the worker already queried unexpired `typing_indicators` rows.
- The image ingestion feature passed code gates but lacks the recorded live upload proof.
- CI checks the build and migration drift, but database migration and Trigger.dev deployment are
  still manual release steps.
- Several docs described already-completed model routing and catalog work as still pending.
- `DECISIONS.md` carried an early `company_documents` bucket TODO even though the current
  project guide and runtime used that bucket.
- `DECISIONS.md` still lists delivered macro pool UI, fan-out, workflow-map, ungating, and ordering
  work as deferred.

## 4. Scope

In scope:

- Correct or retire stale verification code and false code comments.
- Close deployed-but-unverified runtime incidents with exact evidence.
- Add the missing database regression test.
- Reconcile the current model-pool fallback statement with production truth.
- Resolve migration 65's journal/snapshot reproducibility risk.
- Record one safe live image-ingestion proof.
- Add guarded release automation after the manual contract is proven.
- Remove dead repair code at the safe macro cleanup point.
- Update the error log, plan status, handoff, and router after every gate.

Not in this plan:

- The macro-first feature refactor or quote repair, which belongs to
  `MACRO_FIRST_IMPLEMENTATION_PLAN.md`.
- Taxonomy, retrieval, Authentik, China, attachment-cache, GCS, eval-dashboard, or secret-rotation
  product work, which belongs to `plan_deferred_product_and_infrastructure_gaps.md`.
- Weakening quote validation or changing evidence authority.
- Direct production DDL, `drizzle-kit push`, dashboard-only undocumented fixes, or live server edits.

## 5. Current code state

- R0 is deployed and verified; see `MACRO_FIRST_IMPLEMENTATION_PLAN.md` and
  `evals/shape-aware-stage2.md`.
- The schema-stale `scripts/verify-workflow-map-prod.mjs` was deleted in REL-1 because it duplicated
  the maintained audit while querying retired tables and columns.
- `packages/db/src/audit-r0-release-map.ts` is the current post-migration SELECT-only map audit.
- `packages/db/src/audit-r0-reader-drops.ts` intentionally covers only the old map.
- `apps/workers/src/lib/schema-repair.ts` has zero callers as of 2026-07-26.
- `apps/workers/src/trigger/teams-transcript-ingestion.ts` already resolves display names through
  directory email and anchors cue timestamps to `payload.meetingTime` when supplied.
- `source-outline.ts`, `document-lens-extraction.ts`, `macro-relationship-extraction.ts`, and
  `source-coverage-audit.ts` no longer exist. Migration 89 removed the retired outline/lens path.
- The current reader path is `source-workflow-read.ts` plus map-directed
  `document-ingestion.ts`, with deterministic map omissions in `map-coverage-gaps.ts`.
- `AGENT_ERROR_LOG.md` still describes ERR-003 and ERR-004 using the deleted architecture.
- ERR-002's former support-query smoke and package command were deleted in REL-3 after a
  repository-wide zero-caller search found no runtime or CI owner. The current map-coverage path
  queries `claims.map_element_ref` directly and does not share any of the retired SQL contracts.
- `.github/workflows/pr-check.yml` is the only workflow.
- The worktree already contains user-owned untracked PNG files. Do not touch them.

The planning session changed only Markdown plans and routers. REL-1 was implemented in the
follow-up session on 2026-07-26.

## 6. Root causes and key findings

- ERR-003 was a fan-out ownership bug in workers that no longer exist. Stage 3 removed the entire
  outline/lens/macro/coverage fan-out, so the correct close is architecture removal plus a deployed
  task-inventory check, not a new outline rerun.
- ERR-004's original data-model problem remains relevant, but its proof must use the current
  `source_workflow_maps`, `mapElementRef`, and deterministic `model_coverage` gap path.
- ERR-005 used an all-zero fake channel ID for document-only contradictions, violating a foreign
  key. The deployed guard needs a document-only contradiction rerun.
- ERR-002 came from `SELECT DISTINCT` queries in deleted writers. Manual production checks proved
  the historical fix. The remaining smoke script must be retired unless a current runtime caller
  of the same query contract is found.
- The stale workflow script drifted because it duplicated schema knowledge instead of importing or
  querying current names.
- The hard-coded schema repair helper violates configurable-model and observability rules even
  though its lack of callers keeps it from affecting runtime today.
- Old comments and pending-work rows were not de-staled after code landed, which makes correct code
  look unfinished.

## 7. Rejected approaches

- Do not weaken or fuzz document quote validation to make a runtime gate green.
- Do not run the stale workflow script and interpret its SQL error as a production data failure.
- Do not reuse `schema-repair.ts` for macro R0.1. It hard-codes a route and lacks the required
  element-scoped safety contract.
- Do not add `DEEPSEEK_API_KEY` merely because an old incident note says so. First prove DeepSeek
  is still configured as a runtime candidate and suitable for that slot.
- Do not edit migration history blindly or replay a generated migration over live objects.
- Do not automate deployment until the exact safe manual order, failure behavior, and rollback are
  encoded and tested.
- Do not rebuild deleted outline/lens/macro workers merely to reproduce an old incident.
- Do not keep an obsolete SQL smoke in CI when no current runtime path owns those queries.
- Do not close ERR-004 or ERR-005 from local tests alone. Their remaining item is current production
  proof after an owner-authorized fixture run.

## 8. Design decisions

Locked:

- GitHub and `main` are code truth.
- Migrations run through `pnpm db:migrate` and the Drizzle journal.
- Runtime verification uses non-sensitive fixtures and SELECT-only audits where mutation is not
  essential.
- Release automation must stop loudly and must never claim a deploy succeeded without checking it.
- Model routes remain configurable and every model attempt remains observable.
- The dead repair helper is deleted only when macro cleanup proves no migration-era caller needs it.

Open within stated criteria:

- Fix `verify-workflow-map-prod.mjs` if it provides checks absent from the current audit; otherwise
  delete it and point callers to the maintained audit.
- REL-5 resolved the migration 65 choice: keep it hand-written because fresh-db, snapshot, live
  schema, and generated-journal drift gates agree. Do not add duplicate generated DDL.
- Choose workflow-dispatch or a documented manual approval job for database and Trigger releases
  based on least privilege and rollback clarity.

## 9. Implementation plan

Primary file map:

| Step | Primary files |
|---|---|
| REL-1 | `scripts/verify-workflow-map-prod.mjs`, `packages/db/src/audit-r0-release-map.ts`, `apps/workers/src/trigger/teams-transcript-ingestion.ts`, `apps/workers/src/trigger/lull-interjection.ts`, `AGENTS.md`, `DECISIONS.md`, `docs/architecture.md` |
| REL-2 | `apps/workers/src/lib/source-workflow-read.ts`, `apps/workers/src/trigger/{source-workflow-read,document-ingestion,contradiction-watcher}.ts`, `apps/workers/src/lib/map-coverage-gaps.ts`, migration `89_map_directed_extraction_cleanup.sql`, `AGENT_ERROR_LOG.md` |
| REL-3 | `packages/db/src/verify-macro-support-queries.ts`, `packages/db/package.json`, `.github/workflows/pr-check.yml`, current runtime callers found by repository search |
| REL-4 | `packages/ai/src/routes/{candidates,auxiliary,capability-requirements}.ts`, `packages/ai/src/model-capabilities/**`, production `settings` rows |
| REL-5 | `packages/db/migrations/sql/65_document_context_and_domain_hints.sql`, `packages/db/src/schema.ts`, `packages/db/src/check-migration-drift.ts`, migration journal/snapshots |
| REL-6 | `apps/web/app/api/admin/documents/route.ts`, `apps/web/app/admin/documents/**`, `apps/workers/src/trigger/document-ingestion.ts` |
| REL-7 | `.github/workflows/pr-check.yml`, new narrowly scoped workflows under `.github/workflows/`, `docs/deployment.md`, `apps/workers/trigger.config.ts` |
| REL-8 | `apps/workers/src/lib/schema-repair.ts` and any caller/export found by the required search |
| REL-9 | `AGENT_ERROR_LOG.md`, `AGENTS.md`, `HANDOFF.md`, this plan |

### REL-1: stale verification code and false notes

1. Compare `scripts/verify-workflow-map-prod.mjs` with
   `packages/db/src/audit-r0-release-map.ts` and the current schema.
2. If the old script adds no unique check, delete it and replace every reference with the current
   audit. If it adds a useful check, update its columns, add a fixture test, and state its scope.
3. Correct the stale header comments in `teams-transcript-ingestion.ts` to describe email resolution
   and meeting-time anchoring as current behavior, while retaining the real unmatched-speaker case.
4. Correct the stale lull-interjection presence comment and decision history without erasing why
   presence was deferred in round 1. Keep embedding-based topical gap selection marked open.
5. Correct stale "remaining work" statements in `docs/architecture.md`, `AGENTS.md`, and
   `DECISIONS.md` only after verifying the corresponding code or deployment evidence.
6. Close the obsolete storage-bucket TODO only after a read-only Storage check confirms the bucket
   still exists in the current Supabase project.

Gate: `rg` finds no live instruction to use removed workflow-map columns and the Teams comment
matches the code at the email-resolution and `meetingTime` branches.

### REL-2: reconcile ERR-003, ERR-004, and ERR-005 with the current reader

1. For ERR-003, record that migration 89 and the current trigger directory removed
   `source-outline`, `document-lens-extraction`, `macro-relationship-extraction`, and
   `source-coverage-audit`. Do not recreate them.
2. Before marking the production incident fully closed, use a read-only Trigger.dev task inventory
   to confirm the deployed worker no longer advertises those four tasks. Record the worker version.
3. Rewrite ERR-004's remaining proof around the current path. Use an owner-authorized,
   non-sensitive document fixture pinned by source ID and hash.
4. Pass ERR-004 when `source-workflow-read` creates a non-empty `source_workflow_maps` row,
   document candidates carry valid active-map `mapElementRef` values where applicable, and
   deterministic `model_coverage` gaps represent omitted primary map elements without reaching
   employee-facing gap consumers.
5. Run the current document-only contradiction fixture through `contradiction-watcher`.
6. Pass ERR-005 when contradiction and normal gap rows persist, no `oracle_interventions` row uses
   a fake channel ID, and no foreign-key failure occurs.

Read-only evidence captured 2026-07-27:

- Trigger.dev deployment `deployment_hm4hhngt6jnit96rd1huc`, worker `20260722.1`, advertises
  `source-workflow-read` and `contradiction-watcher` and advertises none of the four retired tasks.
- Production has 3 validated/degraded non-empty maps and 74 candidate rows whose refs use one of
  those map IDs. A stricter latest-map membership audit found 54 of 75 historical referenced
  candidates on the latest active map and 21 on an older or otherwise non-current map. This is
  inventory evidence, not the pinned-fixture proof required by step 4.
- Production currently has 0 `model_coverage` gaps and 0 interventions with the all-zero channel
  ID. Those zero counts do not replace the omitted-element and document-only contradiction fixtures.

Gate: ERR-003 is `FIXED BY ARCHITECTURE REMOVAL` with repo and deployed task-inventory evidence.
ERR-004 and ERR-005 are `FIXED` only with run IDs, row counts, worker version, and date.

### REL-3: retire or retarget the obsolete macro-support SQL smoke

1. Search current runtime code for the three query contracts in
   `packages/db/src/verify-macro-support-queries.ts` and for every reference to the package script
   `verify:macro-support-queries`.
2. If no runtime owner exists, delete the smoke and package script, then mark ERR-002's optional
   follow-up `N/A after writer removal`. Do not wire dead architecture into CI.
3. If a current runtime owner exists because the code changed after this plan was reviewed, move
   the query into a shared helper, make the runtime caller and test import that helper, and seed the
   fresh test DB with duplicate joins and differing `created_at` values.
4. In the current-caller branch only, assert no `42P10`, correct deduplication, deterministic order,
   and expected limits, then wire the named verify into CI.

Gate: either no obsolete macro-support smoke remains, or one current shared query contract is
called by runtime and guarded in CI. The deleted writers are never restored.

Completion evidence (2026-07-27):

- `rg` found no runtime copy of `seed_claims`, `seed_domains`, `related_claims`, the single-source
  support query, the cross-source support query, or the retired coverage-audit query outside the
  obsolete smoke itself.
- `rg` found no package-command caller outside `packages/db/package.json` and no CI reference.
- The only current coverage query is `apps/workers/src/lib/map-coverage-gaps.ts`; it reads
  `claims.map_element_ref` for the active workflow map and does not own ERR-002's deleted join,
  deduplication, ordering, or limit contract.
- Deleted `packages/db/src/verify-macro-support-queries.ts` and removed
  `verify:macro-support-queries` from `packages/db/package.json`. No replacement CI job was added
  because that would preserve dead architecture.

### REL-4: model-pool fallback truth

1. Read production settings and model capabilities without printing secret values.
2. List candidates for `workflow_read`, `macro`, `model_merge`, and any `general` compatibility use.
3. Confirm whether DeepSeek is present, eligible, configured, and actually reachable.
4. If it is a phantom candidate, remove it from the affected configured pool through the normal
   settings path and record why. If it is not a candidate, close the old incident note as stale.
5. Never mark DeepSeek deep-schema eligible without its documented beta tool-call adapter path and
   request-shape coverage.

Gate: every advertised candidate is either callable for its slot or absent, and an exhausted pool
still raises `AllCandidatesFailedError`.

**Completed 2026-07-27.** The read-only production audit is reproducible with
`REL4_AUDIT_DATABASE_URL=<production pooler> pnpm --filter @oracle/ai
verify:rel4-model-pools`. The verifier prints only model ids, capability flags, resolution results,
and aggregate attempt status/count/timestamps. It does not print the database URL, provider keys,
prompts, model output, or provider error text. It exits nonzero if mandatory strict-slot enforcement
is inactive, DeepSeek enters any of the four prohibited pools, its strict/deep flags become true,
or its audited configured use moves outside `transcript_summary`.

- `workflow_read` resolves `openai/gpt-4.1` as primary. Anthropic Sonnet 5 and Gemini 2.5 Pro are
  present in the saved pool but are skipped because production catalog truth does not mark them
  deep-schema eligible.
- `macro` resolves `openai/gpt-4.1-mini` as primary and `openai/gpt-4.1` as its eligible fallback.
  Gemini 2.5 Pro is skipped for the same deep-schema gate.
- `model_merge` resolves OpenAI 4.1 Mini, Gemini 2.5 Flash, and Anthropic Haiku 4.5 with no skips.
- `general` resolves Qwen 3.7 Max, Anthropic Haiku 4.5, and Gemini 2.5 Flash with no skips.
- `transcript_summary` resolves `deepseek/deepseek-v4-flash` as primary and
  `qwen/qwen3.6-flash` as fallback with no skipped candidates. This is DeepSeek's configured role,
  not one of the four pools implicated by ERR-001.
- DeepSeek is absent from all four affected pools. Its two production catalog rows are
  `structured_outputs=false`, `strict_json_schema=false`, `deep_schema_accepted=false`, and
  `adapter_params_safe=true`. Three separate barriers protect the deep-schema slots: DeepSeek is
  not a saved pool member, runtime `normalizeDirectProviderCapabilities` forces its strict/deep
  capability flags off, and `shouldEnforceCapabilities` now makes enforcement mandatory for
  `workflow_read`, `macro`, and `model_merge` even when the global debug setting is false.
- The first assertion-enabled audit exposed `enforce_model_capabilities=false` in production. No
  production setting was changed. The permanent code remedy makes strict/deep-schema safety
  independent of that mutable debug flag.
- Release proof: commits `5f962b5` and `24bbf70`; GitHub Actions run `30269886119` attempt 2
  green, including migration/drift; Vercel production deploy successful with HTTP 200; Trigger.dev
  worker `20260727.2`, deployment `h6ri0rb9`. The mandatory strict-slot guard is now live, so REL-4
  is closed.
- DeepSeek is not a phantom provider. Sanitized attempt history contains one failed and one
  successful `transcript_summary` call for `deepseek-v4-flash` on 2026-07-09. That loose-schema
  role is its actual configured use and proves the production worker adapter/key path was reachable.
- No production setting needed mutation. The stale ERR-001 action was closed instead of adding a
  key or removing a candidate that is not in the affected pools.
- `pnpm --filter @oracle/ai verify:r2` passed, including the assertion that an exhausted approved
  candidate chain raises `AllCandidatesFailedError`. `pnpm --filter @oracle/ai
  verify:adapter-request-shapes` and `pnpm --filter @oracle/ai typecheck` also passed.

### REL-5: migration 65 and snapshot drift

1. Coordinate with macro R1's mandatory drift and journal audit.
2. Run `pnpm --filter @oracle/db check-drift` and the full fresh-database migration workflow.
3. Confirm `documents.context` and `documents.domain_hints` exist in both the live target and fresh
   fixture.
4. If the hand-written migration is fully journaled and reproducible, correct the stale warning and
   keep it. If not, author the smallest forward-only reconciliation migration or snapshot change.
5. Never edit an applied migration's production meaning.

Gate: fresh DB, drift, and live SELECT-only schema checks agree with no unexplained journal change.

**Completed 2026-07-29.** Migration 65 remains the smallest correct owner. No forward
reconciliation migration or generated SQL change was needed.

- The existing R1 CI workflow already runs the complete migration runner twice against an empty
  pgvector Postgres fixture. Because `migrate.ts` applies every raw SQL file in lexical order, this
  proves migration 65 creates both columns and is safe to rerun. GitHub Actions run `30417301245`
  passed both full runs and the populated raw-rerun fixture.
- Added `verify:document-context-contract` and `verify:document-context-schema`. The verifier
  requires migration 65 to idempotently own nullable `documents.context text` and
  `documents.domain_hints jsonb`, requires the latest journal snapshot to record the same shape,
  and uses only `information_schema` SELECTs to check the applied database. The applied-schema
  form is wired into the fresh-database CI gate.
- Local `pnpm --filter @oracle/db typecheck` and
  `pnpm --filter @oracle/db verify:document-context-contract` passed against snapshot
  `0011_pink_titanium_man`.
- The latest landed drift proof, GitHub Actions run `30417301245`, reported exactly 12 on-disk
  generated migrations and 12 production journal rows with matching hashes. Raw migration 65 is
  intentionally outside that generated-only journal and is covered by the full-run and schema
  contracts instead.
- A protected SELECT-only production check against current Supabase project
  `eqccjfbyrywsqkxxpjvg` confirmed `public.documents.context` is nullable `text` and
  `public.documents.domain_hints` is nullable `jsonb`. The production Drizzle journal contained
  12 rows, latest id/timestamp marker `12` / `1785158867458`.
- Corrected the stale `AGENTS.md`, `DECISIONS.md`, and historical `HANDOFF.md` warnings. They now
  distinguish the generated Drizzle journal from the raw migration chain and forbid duplicate DDL.

### REL-6: live image upload proof

1. Use a non-sensitive image fixture with a known text and diagram answer key.
2. Upload through Admin Documents, not the channel attachment path.
3. Record the document ID, Trigger run ID, vision model attempt, final status, source text, and claim
   quote validation counts.
4. Delete only disposable test data through an existing guarded cleanup path if owner-authorized.

Gate: upload reaches `complete`, produces expected source text and quote-backed candidates, and no
provider fallback loses the image.

### REL-7: guarded release automation

1. Document the current manual order in `docs/deployment.md`: CI, migration, web deploy, worker
   deploy, health checks, and evidence capture.
2. Add least-privilege GitHub environments and approval boundaries without storing secrets in git.
3. Add a database migration job that uses the journaled runner, performs drift/fresh checks first,
   and stops on any mismatch.
4. Add Trigger.dev deployment automation using the supported authenticated path and record the
   resulting worker version.
5. Keep production mutation behind explicit GitHub environment approval.
6. Add post-release checks for HTTP 200, expected build SHA where available, worker version, and
   migration journal state.

Gate: a dry run or non-production rehearsal proves failure stops later stages, then one approved
production release records commit SHA, CI run, migration, deployment IDs, and health checks.

### REL-8: remove dead schema repair

1. At macro R10, repeat the caller search for `repairStructuredOutput`.
2. If still unused, delete `apps/workers/src/lib/schema-repair.ts`.
3. Remove any exports, docs, or tests that exist solely for it.
4. If a real caller appears, replace the helper with the configurable, observed, stage-specific
   repair contract before allowing it to remain.

Gate: no hard-coded schema-repair route remains and all worker gates stay green.

### REL-9: close documentation and logs

1. Update this status table after each gate.
2. Update `AGENT_ERROR_LOG.md` with evidence, not summaries.
3. Remove resolved rows from `AGENTS.md` section 15 or mark them done with proof.
4. Update `HANDOFF.md` so it points only to the next open step in each plan.

Gate: every reliability item is done, intentionally rejected with reason, or blocked on a named
owner action. No bare open item remains.

### Conditional suggestions pending Claude review

These are not accepted implementation steps yet. Send all four remaining items to Claude with the
current plans and code, then record Claude's evidence-based accept, reject, or narrow decision
before moving one into a numbered plan step:

1. **ERR-003 deployment proof:** confirm whether repository deletion plus the deployed Trigger.dev
   task inventory is sufficient to close the old fan-out incident.
2. **Local environment warning:** check whether `.env.local` can still point at `oracle.old`.
   This is unverified and must not be called a known defect without evidence. Never read secret
   values into the review transcript.
3. **Bug D backbone review UI:** decide whether the old "backbone claims" review slice is still a
   wanted product feature under macro R6 or should remain intentionally unsupported.
4. **Teams AAD speaker matching:** decide whether resolving unmatched transcript speakers from
   participant AAD IDs is required work or an acceptable documented v1 limitation.

The former ERR-002 smoke-disposition question is resolved, not pending review: REL-3 proved the
query contracts and package command had no current runtime or CI owner, then deleted the obsolete
smoke and command.

Gate: Claude's critique is saved under `.ai/reviews/`, Codex verifies each accepted point against
the repo, and only accepted items are added to the canonical plan registry.

## 10. Tests required

- Existing `pnpm lint`, `pnpm typecheck`, and `pnpm build`.
- Current AI, worker, engine, and database verify commands named in package scripts.
- REL-3 zero-caller proof, or a current shared-query regression verify only if a runtime owner exists.
- Fresh-database migration and drift checks.
- Read-only deployed task inventory proving ERR-003's retired tasks are absent.
- Row-level workflow-map and contradiction assertions for ERR-004 and ERR-005.
- Workflow release failure-path test proving later stages do not run after a failed gate.

## 11. Constraints and gotchas

- Do not touch `detail-current.png` or `rfq-before.png`.
- Do not print production database URLs, tokens, keys, or private fixture contents.
- Serialize 1Password reads.
- No direct production DDL or `drizzle-kit push`.
- Do not modify old applied migration meaning.
- Production and shared cloud infrastructure are read-only unless the owner explicitly authorizes
  the exact mutation in the current task.
- Verify git identity before the first commit.
- Main-only repository policy applies.
- Runtime incident closure requires production evidence.

## 12. Access and environment

- Local repo: `C:\repos\oracle`.
- Package manager: `pnpm` through Corepack.
- GitHub CLI, Vercel, Trigger.dev, and 1Password have been authenticated in prior sessions; verify
  each with a read call before relying on it.
- Production database credentials live in 1Password vault `vibe_coding`; reference the item by its
  Oracle Supabase session-pooler purpose and never copy its value into docs.
- Trigger.dev management credentials live in the same vault under the documented Trigger.dev
  management token item.
- Use `https://oracle.designflow.app` for public HTTP verification.

## 13. Definition of done, risks, and open questions

Done means:

- REL-1 through REL-9 are marked done or intentionally retired with evidence.
- All named tests pass.
- Code and docs are committed and pushed to `main`.
- CI is green.
- Any changed web/worker/database runtime is deployed through the normal path.
- Deployment IDs, worker version, migration state, and production run IDs are recorded.
- `AGENT_ERROR_LOG.md`, `AGENTS.md`, this plan, and `HANDOFF.md` agree.
- Claude's conditional-review queue is resolved or remains explicitly blocked without being treated
  as accepted work.

Risks:

- Production fixtures can create unwanted claims or rows. Use isolated non-sensitive fixtures and
  guarded cleanup.
- Release automation can widen production access. Use least privilege and approvals.
- Migration reconciliation can damage history if treated as a replay. Use forward-only changes.
- Previously hidden failures may appear after ERR-004 endpoints recover. Record them honestly.

Rollback:

- Revert code and workflow changes through GitHub.
- Disable new release jobs without altering database history.
- Keep additive database changes unused if rollback cannot safely drop them.

Open questions have predetermined gates:

- Old workflow script: keep only if it has a unique maintained check.
- DeepSeek: configure only if current slot requirements and real probe pass.
- Migration 65: resolved. Preserve hand-written ownership; fresh DB, snapshot, live schema, and
  generated-journal drift checks agree.

## Plan self-audit

1. **Can a new session execute this without chat context? Yes.** Sections 2–6 define the app,
   trigger, exact current state, and root causes. Section 9 names files, order, behavior, and gates.
2. **Does it preserve failed paths and decisions? Yes.** Sections 7–8 record the unsafe shortcuts,
   locked rules, and bounded choices.
3. **Is the goal strong enough for judgment calls? Yes.** Section 1 defines reliable, reproducible,
   evidence-backed releases and says the goal wins on conflict.

Checklist result: all 13 required sections are present; every build step has a verification gate;
scope, tests, access, secrets rules, landing evidence, rollback, and blockers are explicit.
