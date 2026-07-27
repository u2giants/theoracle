# Repository Reliability and Release Gaps Plan

Status: **CANONICAL for known reliability, verification, migration-drift, release-automation,
and misleading-code-note problems that are outside the macro-first feature sequence.**

Created: 2026-07-26
Repository: `C:\repos\oracle`, GitHub `u2giants/theoracle`, branch `main`
Production web: `https://oracle.designflow.app`
Workers: Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`
Database: Supabase project `eqccjfbyrywsqkxxpjvg`

## Status table

| Step | Status | Evidence or blocker |
|---|---|---|
| REL-1 Stale verification script and false comments | ⬜ open | No blocker |
| REL-2 Runtime reruns for ERR-003, ERR-004, ERR-005 | ⬜ open | Needs safe production fixtures and read access; no production mutation without the normal authorized workflow |
| REL-3 Support-query database regression test | ⬜ open | Depends on a seeded test database fixture |
| REL-4 Model-pool phantom fallback audit | ⬜ open | Read-only production settings/env audit first |
| REL-5 Migration 65 and generated-snapshot drift | ⬜ open | Coordinate with macro R1 drift audit to avoid duplicate migration work |
| REL-6 Live image upload verification | ⬜ open | Requires an owner-approved non-sensitive image fixture |
| REL-7 Database and Trigger.dev release automation | ⬜ open | Starts after REL-2 through REL-5 establish the current release contract |
| REL-8 Dead schema-repair helper removal | ⬜ open | Wait until macro R10 unless a current caller is introduced |
| REL-9 Close logs and documentation | ⬜ open | Depends on all earlier applicable steps |

Fresh-session starting point: REL-1 can begin now. REL-2, REL-3, and the read-only portion of REL-4
can run independently. Coordinate REL-5 with macro R1.

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

- ERR-003, ERR-004, and ERR-005 are deployed but never closed by the exact production reruns.
- `scripts/verify-workflow-map-prod.mjs` selects removed `source_outline_id` and uses
  `macro_relationships.confidence` instead of `confidence_score`.
- `apps/workers/src/lib/schema-repair.ts` has no callers and hard-codes a route.
- ERR-002 has no database-touching regression test for its three support queries.
- ERR-001 still contains an old instruction to add a DeepSeek key or remove a phantom fallback.
  Current pool state must be checked before that instruction is acted on.
- Migration 65 is hand-written only, while an old pending-work row warns that generated drift or
  fresh database creation may disagree.
- The Teams transcript worker's top comment says speaker email resolution and meeting-time
  anchoring are TODOs, but the same file already implements both.
- The lull-interjection header and `DECISIONS.md` still say typing presence is hard-coded false,
  but the worker now queries unexpired `typing_indicators` rows.
- The image ingestion feature passed code gates but lacks the recorded live upload proof.
- CI checks the build and migration drift, but database migration and Trigger.dev deployment are
  still manual release steps.
- Several docs describe already-completed model routing and catalog work as still pending.
- `DECISIONS.md` still carries an early `company_documents` bucket TODO even though the current
  project guide and runtime use that bucket.
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
- `scripts/verify-workflow-map-prod.mjs` is schema-stale and must not be trusted for R1.
- `packages/db/src/audit-r0-release-map.ts` is the current post-migration SELECT-only map audit.
- `packages/db/src/audit-r0-reader-drops.ts` intentionally covers only the old map.
- `apps/workers/src/lib/schema-repair.ts` has zero callers as of 2026-07-26.
- `apps/workers/src/trigger/teams-transcript-ingestion.ts` already resolves display names through
  directory email and anchors cue timestamps to `payload.meetingTime` when supplied.
- `AGENT_ERROR_LOG.md` marks ERR-003 through ERR-005 as deployed but needing rerun proof.
- `.github/workflows/pr-check.yml` is the only workflow.
- The worktree already contains user-owned untracked PNG files. Do not touch them.

No step in this plan was implemented by the planning session. Only Markdown plans and routers were
changed.

## 6. Root causes and key findings

- ERR-003 was a fan-out ownership bug. Every lens pass started macro and coverage work. The deployed
  latch and sequencing fix needs a one-outline proof of exactly one macro and one coverage run.
- ERR-004 was a data-model gap. Workflow maps became first-class, but the original incident entry
  was never closed with its named real-source checks.
- ERR-005 used an all-zero fake channel ID for document-only contradictions, violating a foreign
  key. The deployed guard needs a document-only contradiction rerun.
- ERR-002 came from `SELECT DISTINCT` queries ordering by expressions outside the select list.
  Manual production checks proved the fix, but there is no automated database regression.
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
- Do not close ERR-003 through ERR-005 from local tests alone. Their open item is production proof.

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
- Keep migration 65 hand-written if fresh-db and drift gates prove it reproducible; otherwise add
  the smallest journaled/generated reconciliation allowed by the migration runner.
- Choose workflow-dispatch or a documented manual approval job for database and Trigger releases
  based on least privilege and rollback clarity.

## 9. Implementation plan

Primary file map:

| Step | Primary files |
|---|---|
| REL-1 | `scripts/verify-workflow-map-prod.mjs`, `packages/db/src/audit-r0-release-map.ts`, `apps/workers/src/trigger/teams-transcript-ingestion.ts`, `apps/workers/src/trigger/lull-interjection.ts`, `AGENTS.md`, `DECISIONS.md`, `docs/architecture.md` |
| REL-2 | `apps/workers/src/trigger/{source-outline,document-lens-extraction,macro-relationship-extraction,source-coverage-audit,contradiction-watcher}.ts`, `AGENT_ERROR_LOG.md` |
| REL-3 | `apps/workers/src/trigger/{macro-relationship-extraction,source-coverage-audit}.ts`, `packages/db/src/prepare-fresh-supabase-test-db.ts`, package verify scripts |
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

### REL-2: close ERR-003, ERR-004, and ERR-005

1. Pin one safe outline/document fixture and record its source ID and hash in `AGENT_ERROR_LOG.md`.
2. Run one outline flow and query Trigger runs plus `job_runs`.
3. Pass ERR-003 when the outline creates one macro run and one coverage run, with no repeated lens
   fan-out.
4. Pass ERR-004 when the source has a non-empty workflow map, edge traces on applicable candidates,
   deterministic macro rows, and missing-edge findings where the answer key expects them.
5. Run a document-only contradiction fixture.
6. Pass ERR-005 when contradiction and gap rows persist, no fake channel intervention is inserted,
   and no foreign-key failure occurs.

Gate: update each incident to `FIXED` with run IDs, row counts, worker version, and date.

### REL-3: support-query regression test

1. Extract the three fixed query builders from
   `apps/workers/src/trigger/macro-relationship-extraction.ts` and
   `apps/workers/src/trigger/source-coverage-audit.ts` only if needed for direct testing.
2. Seed duplicate-producing joins and differing `created_at` values in the existing fresh test DB.
3. Execute cross-source, single-source, and coverage queries.
4. Assert no `42P10`, correct deduplication, deterministic ordering, and expected limits.

Gate: a named database verify runs in CI and fails when the old invalid `DISTINCT` ordering is
restored.

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

### REL-5: migration 65 and snapshot drift

1. Coordinate with macro R1's mandatory drift and journal audit.
2. Run `pnpm --filter @oracle/db check-drift` and the full fresh-database migration workflow.
3. Confirm `documents.context` and `documents.domain_hints` exist in both the live target and fresh
   fixture.
4. If the hand-written migration is fully journaled and reproducible, correct the stale warning and
   keep it. If not, author the smallest forward-only reconciliation migration or snapshot change.
5. Never edit an applied migration's production meaning.

Gate: fresh DB, drift, and live SELECT-only schema checks agree with no unexplained journal change.

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

## 10. Tests required

- Existing `pnpm lint`, `pnpm typecheck`, and `pnpm build`.
- Current AI, worker, engine, and database verify commands named in package scripts.
- New database support-query regression verify from REL-3.
- Fresh-database migration and drift checks.
- Trigger run-count assertions for ERR-003.
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
- Migration 65: preserve hand-written ownership if fresh-db and drift agree.

## Plan self-audit

1. **Can a new session execute this without chat context? Yes.** Sections 2–6 define the app,
   trigger, exact current state, and root causes. Section 9 names files, order, behavior, and gates.
2. **Does it preserve failed paths and decisions? Yes.** Sections 7–8 record the unsafe shortcuts,
   locked rules, and bounded choices.
3. **Is the goal strong enough for judgment calls? Yes.** Section 1 defines reliable, reproducible,
   evidence-backed releases and says the goal wins on conflict.

Checklist result: all 13 required sections are present; every build step has a verification gate;
scope, tests, access, secrets rules, landing evidence, rollback, and blockers are explicit.
