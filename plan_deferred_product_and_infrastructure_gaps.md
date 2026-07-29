# Deferred Product and Infrastructure Gaps Plan

Status: **CANONICAL for known open product features, runtime limitations, optional infrastructure,
and owner-deferred security work outside the macro-first and reliability plans.**

Created: 2026-07-26
Last corrected: 2026-07-28 during GAP-5 release
Repository: `C:\repos\oracle`, GitHub `u2giants/theoracle`, branch `main`

## Status table

| Step                                                     | Status                                                  | Evidence or blocker                                                                                                                                                                                                                                                                                                                                    |
| -------------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| GAP-1 Finish the existing taxonomy reclassification path | 🟨 local implementation complete; release proof blocked | Admin dispatch, visible failure/retry states, row-locked terminal idempotency, stale-base checks, run-ID audit, and post-commit Brain follow-up are implemented. Static checks pass; the DB concurrency/rollback guard is wired into fresh-database CI. Production SELECT audit, deployment, real run proof, and CI execution remain. |
| GAP-2 Entity-aware retrieval planning                    | 🟨 local implementation complete; default stays off     | Registry-only resolution, model selection, loud deterministic fallback, and offline fixtures are implemented. Fixture recall is 100%, wrong-entity rate is 0%, and unresolved names invent 0 IDs. Enabling by default remains blocked until a live provider run records added latency and cost. |
| GAP-3 Authentik disposition                              | ⬜ open                                                 | Owner must confirm whether Authentik is still a wanted login method                                                                                                                                                                                                                                                                                    |
| GAP-4 China translation review and search hardening      | 🟨 local implementation complete; live vector gate remains | Side-by-side English/Chinese review, model/version/status/stale display, append-only generation and review history, approve/reject/retranslate actions, and CI guards are implemented. `simple` search is measured by the offline fixture; run the credentialed live vector fixture before closing. No Chinese search extension was added. |
| GAP-5 Multi-attachment and cross-provider cache safety   | ✅ complete and released                                | Released in `3dee535`. Canonical messages retain every attachment; Vertex removes only its cached PDF; all offline fixtures pass. The live gate proved Anthropic read both generated PDFs after forced Vertex failure. GitHub Actions run `30420138187` passed every guard, including the new chat attachment guard.                                  |
| GAP-6 Vertex cache and batch storage                     | ⬜ open                                                 | Production cloud mutation requires exact owner approval                                                                                                                                                                                                                                                                                                |
| GAP-7 Eval-results dashboard                             | 🟨 local implementation complete; release proof remains | CLI evals publish a minimal safe summary with exact commit and fixture hashes. The read-only admin list/detail pages provide stage, commit, date, and pass/fail filters. Static authorization and confidential-data exclusion guards are included. Commit, CI, deployment, and production admin proof remain. |
| GAP-8 Provider capability parity                         | ⬜ open                                                 | Batch, Qwen explicit cache, and DeepSeek beta strict-schema paths remain limited                                                                                                                                                                                                                                                                       |
| GAP-9 Deferred secret rotation                           | ⏸ blocked by owner                                      | Rotate only when Albert explicitly authorizes it                                                                                                                                                                                                                                                                                                       |
| GAP-10 Deprecated identity-column cleanup                | ⬜ open                                                 | Must prove every reader uses `employee_identities` first                                                                                                                                                                                                                                                                                               |
| GAP-11 Model-coverage finding conversion                 | ⬜ open                                                 | Administrative findings are isolated correctly but lack the audited convert-to-question flow                                                                                                                                                                                                                                                           |
| GAP-12 Topical gap selection for lull questions          | ⬜ open                                                 | Typing presence is implemented; semantic relevance is not                                                                                                                                                                                                                                                                                              |
| GAP-13 Oversized conversation windowing                  | ⬜ open                                                 | Current behavior processes an oversized conversation whole and logs it                                                                                                                                                                                                                                                                                 |
| GAP-14 Final documentation closure                       | ⬜ open                                                 | Depends on the relevant earlier steps                                                                                                                                                                                                                                                                                                                  |

Fresh-session starting point: GAP-1 is the first product gap with an unsafe partial behavior.
GAP-2 and the read-only design portions of GAP-4, GAP-5, GAP-7, and GAP-10 can run independently.

## 1. Ultimate goal

Every feature the repository advertises must either work completely, fail clearly, or be labeled as
not available. Optional cloud features must have a safe setup path. Deferred security work must
remain visible and blocked on the correct owner rather than disappearing from memory.

If a step conflicts with this goal, the goal wins. Stop and flag the conflict before changing user
access, taxonomy, evidence, retrieval, production infrastructure, or credentials.

## 2. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
chat with it, upload documents, review claims, and use approved knowledge. Admins manage models,
taxonomy, translations, transcripts, business structure, and quality. Next.js runs the web app,
Trigger.dev runs workers, Supabase stores data and auth, and provider adapters call AI models.

The repo is a TypeScript `pnpm` monorepo. GitHub `main` is code truth. Production web is
`https://oracle.designflow.app`.

## 3. What triggered this work

The 2026-07-26 known-problem audit found open or deferred items in `AGENTS.md` section 15,
`DECISIONS.md`, `docs/architecture.md`, `docs/configuration.md`, `china_imp.md`, and source code:

- Taxonomy proposals other than `create_top_domain` can be marked approved and queued in the audit
  log, but the existing `taxonomy-reclassification` worker is not triggered by the approval path.
- `RetrievalPlan.requiredEntities` is enforced but no production planner populates it.
- Docs mention Authentik, but no Authentik login flow exists.
- China translation lacks side-by-side admin review; true Chinese keyword segmentation is deferred.
- Vertex file cache supports one PDF per turn and a cross-provider fallback can lose the document.
- Oversized Vertex cache and Vertex Batch need separate GCS buckets and service-account access.
- The eval-results admin page is intentionally a placeholder.
- Qwen Batch requires a native DashScope implementation; DeepSeek has no public Batch API.
- Earlier exposed credentials still have an owner-deferred rotation task.
- Deprecated identity columns remain on `employees` during the multi-identity transition.
- R0 creates administrative `model_coverage` gaps and excludes them from employee questions, but
  there is no audited action that converts one into a human question.
- Lull interjections now respect active typing, but select gaps by priority and participant rather
  than semantic relevance to recent messages.
- An oversized conversation is processed whole even when it exceeds the configured extraction
  budget; a sliding-window strategy remains deferred.

## 4. Scope

In scope:

- Complete or remove each advertised partial feature above.
- Preserve evidence, review, audit, RLS, and identity safety.
- Define owner approval gates for cloud and credential work.
- Update user-facing and developer docs to match the chosen final behavior.

Not in this plan:

- Macro-first stages and quote repair.
- Runtime incident verification, migration drift, or release automation.
- New unrelated product features.
- Direct production infrastructure mutation without current-chat authorization.
- Automatic taxonomy mutation without an admin approval event.

## 5. Current code state

- `approveTaxonomyProposal` in `apps/web/app/admin/taxonomy/_actions.ts` applies only
  `create_top_domain`; other proposal types write `approve_pending_reclassification_*`.
- `apps/workers/src/trigger/taxonomy-reclassification.ts` already implements transactional handlers
  for create sub-topic, reassign claims, merge/retire sub-topic, and merge top domains. It logs
  split proposals as manual intervention and skips unknown or invalid payloads.
- No call from the taxonomy approval action triggers that worker, so approved proposals can remain
  queued indefinitely.
- `packages/ai/src/retrieval-plan.ts` declares a future model-backed plan builder direction, while
  `buildRetrievalPlanFromQuery()` remains keyword-based.
- `RetrievalPlan.requiredEntities` is applied as any-of filtering in
  `packages/ai/src/retrieval.ts`, but production callers leave it empty.
- Supabase email and Microsoft login are live. Authentik is only a documented TODO.
- The China claim layer, `zh-CN` locale, translation worker, and locale-aware retrieval are live.
- `apps/web/app/api/chat/route.ts` explicitly documents the one-cached-PDF limitation.
- Vertex cache and batch adapters already read their respective bucket settings when configured.
- `apps/web/app/admin/ai/evals/page.tsx` lists CLI gates but does not display stored eval results.
- OpenAI, Vertex, and Anthropic implement the optional batch adapter methods. Qwen and DeepSeek do
  not.
- New identity code uses `employee_identities`; deprecated columns remain for compatibility.
- `model_coverage` gaps are written idempotently and excluded from employee-facing consumers.
- `lull-interjection.ts` queries live typing indicators, but its gap choice has no embedding score.
- Conversation extraction preserves whole conversations and logs oversized ones instead of
  truncating them.
- No implementation work in this plan was performed by the planning session.

## 6. Root causes and key findings

- Taxonomy approval state and mutation state were separated. A durable worker exists, but the
  approval path records only a queue note and never dispatches the worker, so "approved" can mean
  "accepted but not applied."
- Entity-aware retrieval needs named-entity recognition plus registry resolution, not a change to
  the settled any-of filter.
- Authentik is documentation residue unless the business still wants a third login path.
- Chinese vector retrieval works, but Postgres `simple` text search is not true Chinese word
  segmentation.
- Vertex cache optimization coupled attachment availability to one provider-specific cached copy.
- GCS-backed features are correctly disabled without buckets, but the setup task lacks an executed
  infrastructure plan.
- CLI evals were intentionally prioritized; no stored result contract was designed for the UI.
- Provider batch parity is limited by real provider APIs, not only missing local code.
- Secret rotation is delayed by an explicit owner decision, not forgotten work.
- Model-coverage isolation is safe, but there is no controlled bridge from a model-quality finding
  to an employee question.
- Whole-conversation preservation avoids context loss, but a source larger than a model's true
  limit still needs bounded overlapping windows.

## 7. Rejected approaches

- Do not mark a taxonomy proposal fully applied before its data changes commit.
- Do not auto-apply taxonomy changes from a model proposal.
- Do not change `requiredEntities` from any-of to all-of.
- Do not add an AI planner call to every query without a latency, cost, and fallback gate.
- Do not build Authentik solely because old docs mention it.
- Do not install unsupported Supabase extensions without confirming hosted availability and
  rollback.
- Do not silently drop attachments on provider fallback.
- Do not create broad cloud credentials for Vertex buckets.
- Do not invent a DeepSeek Batch API.
- Do not rotate any credential without owner approval.
- Do not drop deprecated identity columns until live readers and rollback compatibility are proven.
- Do not expose `model_coverage` rows directly to employee gap consumers.
- Do not choose a lull question by embeddings alone; priority, assignment, and safety still apply.
- Do not split conversations in a way that makes carry-in text quotable or breaks message evidence.

## 8. Design decisions

Locked:

- Admin approval is the only taxonomy mutation authority.
- Claim evidence is unchanged by taxonomy reclassification.
- Entity filters remain any-of.
- Missing optional infrastructure must produce a clear disabled state or warning.
- Model routing remains configurable.
- Secrets live in 1Password vault `vibe_coding`; values never enter docs or git.
- Production/shared cloud mutation requires exact owner authorization.

Recommended decisions, with a defined default:

- Authentik: if the owner does not confirm a current business need before GAP-3 starts, remove the
  TODO and Authentik-facing claims instead of building a third login system.
- Chinese search: keep vector plus `simple` search unless a measured China query set fails the
  acceptance target and hosted extension support is proven.
- Eval UI: store and show only signed/immutable gate summaries, not raw confidential prompts.
- Provider batch: label unsupported providers clearly rather than adding weak emulation.

## 9. Implementation plan

Primary file map:

| Step   | Primary files                                                                                                                                                                                                                                          |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| GAP-1  | `apps/web/app/admin/taxonomy/_actions.ts`, taxonomy proposal UI, existing `apps/workers/src/trigger/taxonomy-reclassification.ts`, `packages/db/src/schema.ts` only if the current status/audit contract cannot represent queued/applied/skipped truth |
| GAP-2  | `packages/ai/src/retrieval-plan.ts`, `packages/ai/src/retrieval.ts`, `apps/web/app/api/chat/route.ts`, retrieval verifies                                                                                                                              |
| GAP-3  | `packages/auth/src/**`, `apps/web/app/auth/**`, `apps/web/app/_components/login-form.tsx`, `docs/{architecture,configuration}.md`                                                                                                                      |
| GAP-4  | `apps/web/app/admin/claims/page.tsx`, `apps/web/app/admin/claims/_actions.ts`, `apps/workers/src/trigger/claim-translation.ts`, `packages/ai/src/retrieval.ts`, `china_imp.md`                                                                         |
| GAP-5  | `apps/web/app/api/chat/route.ts`, `packages/ai/src/providers/cache-utils.ts`, Vertex/OpenAI/Anthropic adapter content translators, provider-shape verifies                                                                                             |
| GAP-6  | `packages/ai/src/providers/vertex-gemini-adapter.ts`, `docs/{configuration,deployment}.md`, the separately approved infrastructure-owning repo                                                                                                         |
| GAP-7  | `apps/web/app/admin/ai/evals/page.tsx`, eval CLI outputs under `packages/ai/evals/`, `packages/db/src/schema.ts` only if durable summaries need storage                                                                                                |
| GAP-8  | `packages/ai/src/providers/{qwen-adapter,deepseek-adapter}.ts`, `packages/ai/src/providers/types.ts`, adapter request-shape verifies, provider capability sources                                                                                      |
| GAP-9  | Runtime env consumers documented in `docs/configuration.md`, 1Password vault `vibe_coding`, Vercel/Trigger/Recall/GCP control planes                                                                                                                   |
| GAP-10 | `packages/db/src/schema.ts`, `packages/auth/src/**`, RLS/functions/views/migrations referring to deprecated employee identity columns                                                                                                                  |
| GAP-11 | `apps/web/app/admin/gaps/**`, `apps/workers/src/lib/map-coverage-gaps.ts`, `packages/db/src/schema.ts` only if no existing audit table fits                                                                                                            |
| GAP-12 | `apps/workers/src/trigger/lull-interjection.ts`, `packages/oracle-engines/src/interjection.ts`, gap/message embedding storage and verifies                                                                                                             |
| GAP-13 | Conversation selection/windowing helpers used by `apps/workers/src/trigger/claim-extraction.ts` and `claim-extraction-batch-submit.ts`, extraction verifies                                                                                            |
| GAP-14 | `AGENTS.md`, `HANDOFF.md`, affected topic docs, this plan                                                                                                                                                                                              |

### GAP-1: finish the existing taxonomy reclassification path

1. Audit approved, queued, applied, skipped, and manual-intervention proposals by type with
   SELECT-only queries over `taxonomy_proposals`, `taxonomy_change_log`, and `job_runs`.
2. Read every existing handler in `taxonomy-reclassification.ts` and compare its accepted payload
   fields with proposal creation code. Correct the contracts in shared types rather than adding a
   second worker.
3. Choose one explicit dispatch path: recommended default is an admin "Apply approved changes"
   action that triggers `taxonomy-reclassification` and shows the Trigger run ID. Do not dispatch
   inside the approval transaction where an external trigger can outlive a rolled-back commit.
4. Keep the worker's existing transaction boundary: structural mutation and
   `reclassification_applied_*` or `reclassification_skipped_*` audit row commit together.
5. Show each proposal's real state in the admin UI: approved and queued, applying, applied, skipped
   with reason, or manual intervention required. Do not call queued or skipped work complete.
6. Keep `split_top_domain` and `split_sub_topic` manual until a separate claim-allocation review
   design proves safe. Unknown or invalid payloads stay skipped with a visible reason.
7. Preserve `claims` and `claim_evidence`; only taxonomy links and taxonomy review state may change.
8. After a successful taxonomy change, enqueue any required Brain re-synthesis through an explicit,
   observable follow-up that cannot make the taxonomy transaction partially fail.
9. Add idempotency, stale-base, duplicate-dispatch, retry, rollback, invalid-payload, and
   partial-failure tests around the existing worker and new dispatch action.

Gate: every supported proposal type either commits its exact mutation and audit atomically or
remains visibly pending apply; retry creates no duplicate changes.

### GAP-2: entity-aware retrieval planning

1. Build an offline query fixture with named people, systems, products, vendors, and multi-entity
   questions.
2. Add registry candidate lookup and strict entity resolution in `packages/ai/src/retrieval-plan.ts`.
3. Add `buildRetrievalPlanWithModel` behind a setting and model route, with deterministic
   keyword-plan fallback that alerts in observability.
4. Populate `requiredEntities` only with resolved canonical IDs and preserve any-of semantics.
5. Measure added latency, cost, recall, and wrong-entity rate before enabling by default.

Gate: fixture recall improves materially, wrong-entity filtering stays below the recorded limit,
unresolved names do not invent IDs, and fallback is visible.

Implementation evidence (2026-07-27):

- `packages/ai/src/retrieval-plan.ts` now performs bounded registry candidate lookup, strict
  whole-surface resolution, and model-assisted selection that can only narrow registry matches.
- Candidate lookup retains useful tokens across the whole query and bounds database output to 200
  rows; required entity types override conflicting broad heuristic exclusions.
- `apps/web/app/api/chat/route.ts` uses the new planner only when
  `settings.entity_aware_retrieval_enabled` is exactly `true`; absent or false keeps the zero-cost
  deterministic path.
- Model selection uses the configured `general` auxiliary route. Failure emits the structured
  `entity_aware_retrieval_fallback` warning and returns the existing deterministic keyword plan.
- Each enabled model call emits `entity_aware_retrieval_model_call` with latency, provider/model,
  token counts, reported cost, candidate count, and attempt count, but never the employee's query
  text. Only the primary configured candidate is passed, enforcing one provider attempt.
- `pnpm --filter @oracle/ai verify:entity-aware-retrieval` passes five people/system/customer/
  licensor/vendor/product and multi-entity fixtures: baseline resolved entities 0, entity-aware
  recall 100%, wrong-entity rate 0%, invented IDs 0, and one modeled extra call when enabled.
- The local deterministic portion completed in under 100 ms. Provider latency and dollar cost
  remain intentionally unmeasured until an approved live gate, so the setting is not seeded or
  enabled by default.

### GAP-3: Authentik disposition

1. Confirm whether POP Creations needs Authentik in addition to Supabase email and Microsoft.
2. If no, remove Authentik claims from schema comments, architecture diagrams, and configuration
   docs, while preserving generic future-provider extension points.
3. If yes, write a separate auth threat model, callback contract, identity-link rules, test tenant,
   and rollout/rollback plan before implementation.
4. Never link accounts by unverified email or bypass `employee_identities`.

Gate: docs and UI advertise only working login methods, or a separately approved Authentik plan
exists with security review.

### GAP-4: China review and search hardening

1. Add side-by-side English and Chinese claim display to the admin claim review path.
2. Show translation model, version, status, source language, and stale state.
3. Add approve/reject/retranslate actions with audit events; do not overwrite historical output.
4. Build a representative Chinese query fixture and measure vector plus `simple` search.
5. Only if the fixture fails, investigate hosted `zhparser` or `pg_jieba` availability through a
   read-only capability check, then write a separate migration and rollback gate.
6. Keep existing-claim translation opt-in; do not create a blind full backfill.

Gate: admins can compare and audit translations, Chinese retrieval passes the fixture, and no
extension is added without measured need.

Implementation evidence (2026-07-27):

- Admin Claims renders canonical and translated summaries side by side, including source language,
  model/provider, prompt version, review status, stale state, and append-only history count.
- Admin-only approve, reject, and forced retranslate actions write
  `claim_translation_events`. Review forms carry source hash, translated-content hash, and
  `updated_at` concurrency tokens, so an old browser page cannot approve newly replaced text.
- Rejected, pending, and stale translations are excluded from both retrieval paths, which fall
  back to the canonical English summary.
- The translation worker preserves the prior output before replacement and resets every new output
  to `pending_review`. Existing-claim translation remains an explicit checkbox action.
- `verify:chinese-retrieval` records `simple` search recall at 0/5 for the current representative
  spaceless-Chinese queries and checks
  approved/current, pending, rejected, and stale serving cases. The parity guard proves the shared
  SQL join applies approval and source-hash freshness in both paths. The web guard verifies each
  action has its own admin check and that review forms/actions use concurrency tokens. These guards
  also run in the Vercel build command. `verify:chinese-retrieval-live` measures multilingual vector
  recall@3 with the real embedding model and must reach 80% before this gap is marked complete.
- No `zhparser`, `pg_jieba`, or other hosted extension was added. Extension work remains conditional
  on a failing live vector-plus-simple fixture and a separate availability/rollback review.

### GAP-5: attachment and cache safety

1. Build fixtures for two PDFs, PDF plus image, and a forced Vertex-to-Anthropic fallback.
2. Refactor chat attachment assembly so the canonical message retains every attachment.
3. Let the Vertex adapter deduplicate the one cached PDF from inline content only for its own call.
4. Ensure another provider receives all supported inline attachments after fallback.
5. If provider size limits prevent safe fallback, constrain the configured fallback pool and show a
   clear error rather than answering without the document.

Gate: every fixture either delivers all attachments to the selected provider or fails clearly;
no degraded answer silently loses a document.

Implementation evidence (2026-07-28):

- Chat now assembles one provider-neutral canonical conversation that retains every PDF, image,
  and text attachment. A failed download or unsupported file stops the answer with a clear
  `attachment_delivery_failed` response instead of continuing without that file.
- The Vertex adapter hashes inline PDF bytes and removes exactly one matching PDF only after its
  file-backed cache was created. Other PDFs, images, and the full conversation remain live.
- Attachment-capable fallback candidates receive the unchanged canonical message. PDF fallback is
  limited to the providers with a native PDF request shape. Payloads above the conservative
  14 MiB decoded inline budget are constrained to a safe Vertex file-cache chain when possible,
  or fail clearly before model dispatch. In that oversized mode the adapter requires successful
  GCS upload and cache preparation before model dispatch. Upload failure stops before
  `generateContent`; smaller requests catch the same failure and safely continue with the complete
  inline message.
- `verify:chat-attachment-safety` covers two PDFs, PDF plus image, forced Vertex-to-Anthropic
  fallback, oversized Vertex-only constraint, and explicit oversized failure.
  `verify:vertex-file-cache` proves the cached PDF is removed while the second PDF and image remain.
  The existing file-part translation guard proves Anthropic, OpenAI-compatible, and Gemini request
  conversion. Both GAP-5 network-free guards run in GitHub CI and the Vercel pre-build guard set.
- The credentialed `verify:attachment-fallback-live` gate passed on 2026-07-28. It forced the
  Vertex attempt to fail before network I/O, then live Anthropic read both generated marker PDFs
  from the unchanged fallback message. The run used Vercel's approved development credential and
  touched no database, GCS bucket, production data, or shared-cloud resource.
- Release commit `3dee535c44af199694561cc0b8285209a289a679` is pushed to `origin/main`.
  GitHub Actions run `30420138187` passed the production TypeScript build and every static guard,
  including `verify:vertex-file-cache` and `verify:chat-attachment-safety`. GAP-5 is closed.

### GAP-6: Vertex cache and batch storage

1. Read current GCP project, region, service account, and bucket state with the dedicated read-only
   AI identity.
2. Write exact least-privilege infrastructure changes for separate context-cache and batch buckets,
   lifecycle retention, region, encryption, CORS if needed, and rollback.
3. Obtain owner approval naming the exact resources and actions.
4. Apply through the repo that owns the infrastructure, never by undocumented live edits.
5. Store only bucket names in runtime configuration and secrets in 1Password.
6. Run oversized cache and batch fixtures, then verify lifecycle cleanup.

Gate: both features work with least privilege, disabled environments remain clear, and storage does
not retain source material beyond the documented policy.

### GAP-7: eval-results dashboard

1. Inventory current CLI eval outputs and decide the smallest stable stored summary contract.
2. Persist run metadata, commit SHA, fixture version, gate result, counts, and safe artifact links.
3. Replace the placeholder page with a read-only admin dashboard.
4. Exclude raw confidential prompts, source text, and credentials.
5. Add filters for stage, commit, date, and pass/fail.

Gate: an admin can tie a release to its exact eval gates, while CLI remains the execution owner.

Implementation evidence (2026-07-28):

- The extraction CLI remains the only execution path. It writes detailed, source-derived output
  only to ignored `runs/`, plus a versioned safe summary under `published/`.
- The safe contract stores timestamps, exact commit SHA, a deterministic fixture-set hash, route,
  mode, stage gate, counts, aggregate metrics, and allowlisted safe artifact paths. It rejects
  unknown versions, malformed counts or metrics, duplicate run IDs, and unsafe artifact paths.
- `/admin/ai/evals` is read-only and inherits the server-side admin guard. It filters by stage,
  commit prefix, UTC completion date, and pass/fail. `/admin/ai/evals/[runId]` displays the exact
  release and fixture identity, stage counts and metrics, and safe links.
- Empty, no-match, invalid-store, unknown-run, and confidential-artifact states are explicit.
  `verify:eval-results-dashboard` guards admin authorization, every required filter, the safe
  summary contract, path allowlisting, and exclusion of prompts, source text, per-fixture failure
  notes, and credentials.

### GAP-8: provider capability parity

1. Keep DeepSeek marked unsupported until it publishes a usable public Batch API.
2. Evaluate Qwen's native DashScope batch contract against the existing optional adapter interface.
3. If demand and cost justify it, add a native Qwen adapter path with submit, retrieve, retry,
   usage, and request-shape tests.
4. Evaluate Qwen native explicit prompt caching only from measured cost savings; keep
   `qwen_none` truthful until then.
5. Keep DeepSeek out of strict-schema slots unless its beta strict function-call endpoint, schema
   subset transformer, and request-shape guards are implemented and proven.
6. Do not emulate batch with untracked synchronous fan-out or claim JSON mode is strict schema.

Gate: UI and docs accurately show provider support; any new Qwen path passes a real small batch
without bypassing attempt and usage records.

### GAP-9: secret rotation

1. Remain blocked until Albert explicitly authorizes rotation in the current task.
2. Inventory only the named exposed credential classes without reading values into the transcript:
   Recall API/webhook, exposed Vercel token, and exposed Google service-account JSON.
3. Map every consumer and rollback before rotating.
4. Rotate one credential class at a time, update 1Password first, update every runtime consumer,
   redeploy, verify, then revoke the old value.
5. For Entra, always append purpose-named credentials unless replacing every consumer is explicitly
   intended.

Gate: each consumer passes a real authenticated check and the old value is revoked only afterward.

### GAP-10: deprecated identity columns

1. Search every code, view, policy, function, and script for `employees.auth_user_id`,
   `auth_provider`, and `auth_provider_subject`.
2. Query production null/non-null counts and inbound dependencies with read-only access.
3. Migrate any remaining reader to `employee_identities`.
4. Keep rollback compatibility for one release.
5. Drop deprecated columns only through the normal forward migration after all gates pass.

Gate: no runtime reader uses the columns, live dependency counts are zero, auth tests pass, and a
rollback release can still authenticate before the final drop.

### GAP-11: audited model-coverage conversion

1. Add an admin-only action on the model-quality finding view.
2. Require the admin to write the employee-facing question, select recipients, and explain why a
   model omission should become a human knowledge question.
3. Create a normal gap through the existing assignment/review path and link it to the original
   `model_coverage` row.
4. Record reviewer, timestamp, original map element, new gap ID, and action in an append-only audit.
5. Keep the original administrative row non-employee-facing.

Gate: conversion is explicit, idempotent, auditable, reversible before sending, and no employee
consumer ever reads a raw `model_coverage` row.

### GAP-12: topical gap selection for lull questions

1. Build a fixture of channels with recent messages and open gaps from matching and unrelated
   domains.
2. Add or reuse embeddings for gaps without changing claim evidence.
3. Score eligible gaps against recent channel messages after priority, assignment, and participant
   filters.
4. Use a minimum relevance threshold; ask nothing when no gap is relevant.
5. Keep live typing, cooldown, hourly limit, advisory lock, and final rate-state recheck unchanged.

Gate: the fixture selects the relevant gap, refuses unrelated gaps, and never posts while someone
is actively typing.

### GAP-13: oversized conversation windowing

1. Capture real or synthetic conversations beyond the smallest supported model context.
2. Add message-boundary windows with controlled overlap and non-quotable carry-in context.
3. Preserve each message's original evidence identity and timestamp.
4. Deduplicate candidates across overlapping windows with the existing candidate identity rules.
5. Fail loudly when even one message cannot fit rather than truncating it.

Gate: an oversized fixture completes within budget, loses no quotable message, and produces no
overlap duplicates.

### GAP-14: close documentation

1. Update this status table as each gap changes.
2. Update `AGENTS.md` section 15, affected architecture/configuration docs, and `HANDOFF.md`.
3. Mark optional items intentionally rejected when evidence says they are not worth building.
4. Keep blocked work visible with the named owner and approval needed.

Gate: every known gap is done, explicitly rejected with evidence, or blocked on a named external
decision. No vague "build later" row remains.

## 10. Tests required

- Taxonomy transaction, idempotency, stale-base, audit, and rollback tests for every proposal type.
- Entity resolution fixtures for exact, alias, ambiguous, unknown, and multi-entity queries.
- Auth callback and identity-link security tests only if Authentik is approved.
- Translation history, stale-state, authorization, and Chinese retrieval fixtures.
- Multi-attachment provider-shape and forced-fallback tests.
- Vertex oversized-cache and batch lifecycle tests after approved infrastructure exists.
- Eval dashboard authorization and confidential-data exclusion tests.
- Qwen request-shape, submit/retrieve, retry, and usage tests if built.
- Auth and identity regression tests before deprecated-column removal.
- Model-coverage conversion authorization, idempotency, and employee-exclusion tests.
- Lull relevance fixtures plus existing typing, cooldown, and locking tests.
- Oversized conversation window, overlap-dedup, evidence-identity, and hard-failure tests.
- Existing lint, typecheck, build, and relevant package verifies remain green.

## 11. Constraints and gotchas

- Do not weaken evidence or claim approval rules.
- Do not auto-apply taxonomy proposals.
- Do not mutate production/shared cloud infrastructure without exact current-task approval.
- Do not rotate credentials without approval.
- Never put secret values in files, git, logs, plans, or chat.
- Serialize 1Password reads.
- Use forward-only journaled database migrations.
- Do not install a Chinese search extension until hosted support, need, backup, and rollback pass.
- Main-only repo policy and correct Albert git identity apply.
- UI work requires local serving and visual verification.

## 12. Access and environment

- Local repo: `C:\repos\oracle`.
- Production web: `https://oracle.designflow.app`.
- Supabase project: `eqccjfbyrywsqkxxpjvg`.
- Trigger.dev project: `proj_wgpzsvhmsopqhvwqaycn`.
- Vercel project: `prj_rP6Jlima7iK1paffEPhLqxlswGsC`.
- Secrets live only in 1Password vault `vibe_coding`.
- Use authenticated CLI/connectors only after a real read check.
- Use a dedicated read-only cloud identity for production discovery.
- Test logins and service credentials must be referenced by 1Password item purpose, never value.

## 13. Definition of done, risks, and open questions

Done means:

- GAP-1 through GAP-14 are done, intentionally rejected, or explicitly blocked with owner and reason.
- Implemented work has named tests, commit SHA, push, green CI, deployment proof, and docs.
- User-facing claims match real working features.
- No partial feature silently claims success.
- `HANDOFF.md` links the next open step and this plan's status is current.

Risks:

- Taxonomy reclassification can move large claim sets incorrectly. Require dry-run counts and
  atomic apply.
- Model-backed query planning can raise cost and latency. Keep a measured feature gate.
- Auth changes can lock users out. Use a test tenant and rollback.
- Attachment fallback can expose or omit files. Keep provider conversion explicit.
- GCS can retain sensitive source material. Use lifecycle deletion and least privilege.
- Secret rotation can break multiple consumers. Rotate one class at a time.

Open decisions:

- Authentik business need belongs to Albert.
- Production cloud resource creation belongs to Albert's explicit authorization.
- Secret rotation timing belongs to Albert.
- Chinese extension adoption is decided by measured fixture failure, not preference.

Rollback:

- Disable new feature flags and model routes.
- Revert web and worker code through GitHub.
- Preserve audit history.
- For additive database changes, stop writers and leave unused structures until a safe forward
  cleanup migration.

## Plan self-audit

1. **Can a new session execute this without chat context? Yes.** Sections 2–6 define the product,
   trigger, current code, and causes. Section 9 gives file-level behavior and measurable gates.
2. **Does it preserve rejected paths and decisions? Yes.** Sections 7–8 state what must not be
   built, the locked safety rules, and decision defaults.
3. **Is the goal clear enough for judgment calls? Yes.** Section 1 requires every advertised
   feature to work, fail clearly, or be removed, and says the goal wins on conflict.

Checklist result: all 13 required sections are present; scope, concrete phases, tests, access,
secrets rules, owner blockers, release proof, rollback, and documentation closure are explicit.
