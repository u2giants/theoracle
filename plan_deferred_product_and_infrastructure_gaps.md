# Deferred Product and Infrastructure Gaps Plan

Status: **CANONICAL for known open product features, runtime limitations, optional infrastructure,
and owner-deferred security work outside the macro-first and reliability plans.**

Created: 2026-07-26
Last corrected: 2026-07-29 during GAP-11 production lifecycle proof
Repository: `C:\repos\oracle`, GitHub `u2giants/theoracle`, branch `main`

## Status table

| Step                                                     | Status                                                  | Evidence or blocker                                                                                                                                                                                                                                                                                                                                    |
| -------------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| GAP-1 Finish the existing taxonomy reclassification path | 🟨 released; natural production apply proof remains | Released through `4efdbdf`. Grok approved; CI run `30430493360` passed the five-type fresh-DB mutation/idempotency gate; Vercel and Trigger worker `20260729.4` deployed. The SELECT-only production audit found 59 pending `create_sub_topic` proposals and no approved/actionable work. Do not invent or approve business taxonomy data solely for a release test; capture the first natural approved apply as the final production proof. |
| GAP-2 Entity-aware retrieval planning                    | 🟨 live gate released; default stays off                | Released through `1f0c0ce`; Grok approved; CI run `30432098788` passed and Vercel deployed the exact commit. Pinned-production Qwen `qwen3.7-max` proof achieved 100% recall, 0% wrong entities, 0 invented IDs, and $0.000379 average cost, but p95 added latency was 2,963 ms against the 2,500 ms limit. Production setting remains off. |
| GAP-3 Authentik disposition                              | ⬜ open                                                 | Owner must confirm whether Authentik is still a wanted login method                                                                                                                                                                                                                                                                                    |
| GAP-4 China translation review and search hardening      | 🟨 trustworthy live gate released; sample blocked | Released through `4245f2d`; Grok approved; CI run `30433191204` passed and Vercel deployed the exact commit. The pinned read-only audit found one exact-current eligible zh-CN translation but zero of five required independently labeled positive queries and no negative control, so it fails closed as `insufficient_production_sample`; extension need remains unproven. |
| GAP-5 Multi-attachment and cross-provider cache safety   | ✅ complete and released                                | Released in `3dee535`. Canonical messages retain every attachment; Vertex removes only its cached PDF; all offline fixtures pass. The live gate proved Anthropic read both generated PDFs after forced Vertex failure. GitHub Actions run `30420138187` passed every guard, including the new chat attachment guard.                                  |
| GAP-6 Vertex cache and batch storage                     | ⬜ open                                                 | Production cloud mutation requires exact owner approval                                                                                                                                                                                                                                                                                                |
| GAP-7 Eval-results dashboard                             | ✅ complete and released                                | Released through `3b96669`. Clean CLI eval run `extraction-2026-07-29T04-03-41-967Z` passed 4/4 and is tied to code commit `656785e`. Grok approved. CI run `30421488336` passed, Vercel deployment `dpl_3KF4J76s9shZBHugy4xNR9rktBCo` was promoted, and signed-in production list/detail checks passed. |
| GAP-8 Provider capability parity                         | ✅ complete and released                                | Released in `4d56ad5`. DeepSeek, Qwen, and Google Gemini API remain sync-only for tracked extraction Batch. Unsupported settings are blocked and stale settings fail loudly. Grok approved, CI run `30422669789` passed, Vercel deployment `dpl_7JQoF119e4DVnNHtRE73xxDWUqoX` was promoted, and signed-in production Settings proof passed. |
| GAP-9 Deferred secret rotation                           | ⏸ blocked by owner                                      | Rotate only when Albert explicitly authorizes it                                                                                                                                                                                                                                                                                                       |
| GAP-10 Deprecated identity-column cleanup                | ✅ complete and released                              | Released in `30eed14`. Migration 98 applied successfully, a second full migration run proved rerun safety, CI and Vercel passed, and protected post-drop authentication succeeded. |
| GAP-11 Model-coverage finding conversion                 | ✅ complete and released | Core conversion released in `e1d16f5`; pagination and legacy-provenance UX released through `a7637f7` with CI run `30445659590` green and signed-in production proof. A scoped production fixture restored valid provenance on 169 genuine omissions. Draft, cancel, redraft, recipient isolation, and append-only audit passed. **Send executed 2026-07-29 under owner-delegated authorization** (Albert delegated the decision to Grok 4.5, which returned SEND): conversion `3b22e8cc` is `sent`, `created_gap_ids` holds exactly one ID `e2aa9061-2757-430b-befb-a0d384002ed3` targeting Albert only, exactly one `sent` audit event, source finding `66fc69be` resolved, and production-wide `coverage_question` count is exactly 1. **Double-submit no-op proven at runtime**: a second invocation with the same conversion id returned HTTP 200 with zero mutations, which is reachable only through the `status === 'sent'` early return (`_actions.ts:134`) because the next line would throw a 500. The test gap `e2aa9061` was then resolved so it could not be surfaced by the GAP-12 lull worker. Only a cosmetic `gaps.resolved_at` write-path gap remains. |
| GAP-12 Topical gap selection for lull questions          | ✅ complete and released                                | Released in `3c13fdc`. Migration 101 applied twice, CI run `30427353184` passed, Vercel deployed the exact commit, and Trigger.dev promoted worker `20260729.2` (`u5e3t6ql`). A live `text-embedding-3-small` proof chose the related low-priority gap at `0.7493` over an unrelated urgent gap at `0.1004`; the unrelated-only case produced no post. |
| GAP-13 Oversized conversation windowing                  | ✅ complete and released                                | Released in `19859e0`. Migration 102 applied twice, CI run `30428842450` passed, Vercel deployed the exact commit, and Trigger.dev promoted worker `20260729.3` (`qx5wrwna`). A production-route fixture split 250 messages into six windows under the live 24,000-character cap, preserved all 250 identities, and collapsed overlap to one permanent candidate identity. |
| GAP-14 Final documentation closure                       | 🟨 current audit recorded                              | Current completion and Grok-review facts are aligned. Final closure remains blocked by the honestly open owner choices, fixtures, approvals, and deferred macro work. |

Fresh-session starting point: no broad implementation sweep is authorized. Capture GAP-1's first
natural apply; keep GAP-2 off; obtain the GAP-3 owner choice; wait for GAP-4's independent sample;
obtain exact approval for GAP-6 or GAP-9; and complete GAP-11's signed-in lifecycle proof.

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

The 2026-07-26 known-problem audit originally found the items below. This is trigger history, not
the current task list. Each line records its present disposition:

- Taxonomy approval did not dispatch the existing worker. GAP-1 is now released through `4efdbdf`;
  only the first natural approved production apply proof remains.
- No production planner populated `RetrievalPlan.requiredEntities`. GAP-2 is released through
  `1f0c0ce`, but remains default-off because its 2,963 ms p95 missed the 2,500 ms latency gate.
- Docs mention Authentik, but no Authentik login flow exists.
- China translation lacked side-by-side review and measured search evidence. GAP-4's gate is
  released; the independent production sample remains unavailable.
- Vertex cache could couple one PDF to one provider. GAP-5 is complete and released in `3dee535`.
- Oversized Vertex cache and Vertex Batch need separate GCS buckets and service-account access.
- The eval-results admin page was a placeholder; GAP-7 replaced it with a safe read-only dashboard
  and closed on 2026-07-29.
- Alibaba now documents OpenAI-compatible Qwen Batch, but Oracle has no safe tracked non-strict
  batch caller; DeepSeek has no native adapter Batch path.
- Earlier exposed credentials still have an owner-deferred rotation task.
- Deprecated identity columns previously remained on `employees` during the multi-identity
  transition; migration 98 removed them in release `30eed14`.
- Administrative `model_coverage` gaps had no audited bridge to employee questions. GAP-11 is
  released in `e1d16f5`; only the signed-in production lifecycle proof remains.
- Lull interjections lacked semantic gap selection. GAP-12 is complete and released in `3c13fdc`.
- Oversized conversations lacked bounded extraction windows. GAP-13 is complete and released in
  `19859e0`.

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

- GAP-1 is released through `4efdbdf`. Taxonomy approval dispatches the existing worker, all five
  supported handlers passed fresh-database mutation and retry gates, and only the first natural
  approved production apply proof remains.
- GAP-2's model-backed entity recognition and registry resolution are released through `1f0c0ce`.
  The default remains off because live p95 added latency was 2,963 ms against the 2,500 ms gate.
- Supabase email and Microsoft login are live. Authentik is only a documented TODO.
- GAP-4's side-by-side review and trustworthy live retrieval gate are released. The measured
  production sample is blocked until five independently labeled positive queries and one negative
  control exist.
- GAP-5 is complete and released in `3dee535`. Canonical messages retain all attachments, Vertex
  removes only its exact cached PDF, and the forced-fallback live gate proved both PDFs reached
  Anthropic.
- Vertex cache and batch adapters already read their respective bucket settings when configured.
- GAP-7 is complete and released through `3b96669`. The admin eval list and detail pages display
  safe published CLI results and passed signed-in production checks.
- GAP-8 is complete and released in `4d56ad5`. Anthropic, OpenAI, and Vertex are the supported
  tracked Batch providers; unsupported settings are blocked and stale settings fail loudly.
- Raw migration 98 removed the deprecated employee identity columns in release `30eed14`;
  `employee_identities` is now the only production identity source.
- GAP-11 is released through `a7637f7`. The production admin page paginates the model-coverage
  findings and labels the 1,322 remaining legacy rows that lack safe provenance. A scoped
  current-map fixture restored all seven provenance keys on 169 genuine omissions. Draft, cancel,
  redraft, recipient isolation, and append-only audit passed. **The replacement conversion was sent
  on 2026-07-29** under owner-delegated authorization: one gap
  `e2aa9061-2757-430b-befb-a0d384002ed3` for Albert only, one `sent` audit event, source finding
  resolved, and `model_coverage` totals moved from 1,491 open to 1,490 open plus 1 resolved. Only
  the live repeat-invocation half of the double-submit proof remains; the permission classifier
  blocked it.
- GAP-12 is complete and released in `3c13fdc`; the live embedding proof selected the related gap
  and refused the unrelated-only case.
- GAP-13 is complete and released in `19859e0`; migration 102, CI, Vercel, Trigger worker, and the
  250-message production-route fixture passed.

## 6. Historical root causes and current resolutions

- Taxonomy approval and mutation were separated. GAP-1 now dispatches the durable worker after
  admin approval and keeps mutation plus terminal audit transactional and idempotent.
- Entity-aware retrieval needed named-entity recognition plus registry resolution, not a change to
  the settled any-of filter. GAP-2 added that path behind a default-off latency gate.
- Authentik is documentation residue unless the business still wants a third login path.
- Chinese vector retrieval works, but Postgres `simple` text search is not true Chinese word
  segmentation. GAP-4 now refuses to recommend an extension without an independent measured sample.
- Vertex cache optimization coupled attachment availability to one provider-specific cached copy.
  GAP-5 now keeps every attachment in the canonical message and removes only the exact cached PDF
  from Vertex's provider-specific request.
- GCS-backed features are correctly disabled without buckets, but the setup task lacks an executed
  infrastructure plan.
- CLI evals were intentionally prioritized and the UI had no safe result contract. GAP-7 now
  publishes allowlisted summaries and displays them through read-only admin list and detail pages.
- Provider batch parity is limited by real provider APIs, not only missing local code.
- Secret rotation is delayed by an explicit owner decision, not forgotten work.
- Model-coverage isolation was safe but lacked a controlled bridge. GAP-11 added admin-authored
  drafts, stable provenance, row-locked sending, normal employee gaps, and append-only audit.
- Priority-only lull selection could choose an unrelated question. GAP-12 added embedding relevance
  while retaining assignment, typing, cooldown, and locking controls.
- Whole-conversation preservation avoided context loss but could exceed the model budget. GAP-13
  added bounded complete-message windows, non-quotable carry-in, safe overlap, and stable dedup.

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

Release-gate evidence (2026-07-29):

- `packages/ai/src/entity-planner-model.ts` is the one production selector shared by chat and the
  credentialed live verifier. It uses the configured primary `general` route, structured JSON,
  strict registry-only output, visible attempt telemetry, and catalog-priced token cost.
- The pinned-production verifier confirmed project `eqccjfbyrywsqkxxpjvg` and confirmed
  `entity_aware_retrieval_enabled` was not true. Qwen `qwen3.7-max` completed four calls with no
  failure or fallback, 100% recall, 0% wrong-entity selection, 0 invented registry IDs, and average
  cost `$0.00037870625`.
- P95 added latency was `2,963 ms`, above the frozen `2,500 ms` limit. The gate therefore failed
  closed and the production default remains off. Re-run the same pinned verifier after a route or
  latency improvement; do not enable from the quality and cost numbers alone.
- Grok 4.5 approved the final helper and verifier in session
  `019facbb-8e3a-7800-9ad5-fdcdaa2f5cb8`. CI run `30432098788` passed and Vercel deployed exact
  commit `1f0c0ce286488dbdc73dbe31ee36dd1f2620157a`.

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

Release-gate evidence (2026-07-29):

- The live verifier pins project `eqccjfbyrywsqkxxpjvg`, uses the real
  `searchWithRetrievalPlan(..., 'zh-CN')` path, performs no writes, and accepts only independently
  authored labeled fixtures. It rejects circular or duplicate queries, duplicate target claims,
  fake negative-control IDs, stale translations, and claims outside the production `current`
  filter. Logs contain labels, hashes, ranks, and metrics, not business query or claim text.
- Synthetic multilingual embedding recall remained 5/5. Production contained only one eligible
  approved/current zh-CN translation and no independent fixture contract. The audit therefore
  failed closed with zero of five required positives, zero negative controls,
  `insufficient_production_sample`, and `extensionNeeded='unproven'`.
- Do not add `zhparser` or `pg_jieba`, and do not claim vector coverage, until five distinct
  eligible translations have independently authored Chinese questions plus one valid unrelated
  negative control and the same live gate reaches at least 80% recall@3.
- Grok 4.5 approved the final fail-closed verifier in session
  `019facd2-f387-7b52-b704-f4b53acc76c1`. CI run `30433191204` passed and Vercel deployed exact
  commit `4245f2d9b90ae90a49e0e78994c9f8808c3213bb`.

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
- Grok 4.5 approved the implementation and the later table-layout correction with no P0/P1
  findings. Clean CLI run `extraction-2026-07-29T04-03-41-967Z` passed 4/4 fixtures and published
  a safe summary tied to code commit `656785e357a29751c6f5f32330b6adde80ec275e`.
- Commits `656785e`, `7deb2fd`, and `3b96669` are pushed to `origin/main`. GitHub Actions run
  `30421488336` passed the production build and all guards. Vercel deployment
  `dpl_3KF4J76s9shZBHugy4xNR9rktBCo` promoted exact commit
  `3b9666928ad21b762113a0e0b3da2d97e1d06aeb` to `oracle.designflow.app`.
- A signed-in production admin check showed the list and detail pages, exact commit, fixture hash,
  prompt version, route, aggregate gates, and safe artifact link. The first screenshot exposed a
  cramped list table; `3b96669` added fixed readable columns and narrow-screen horizontal scrolling,
  and the repeated production screenshot verified the correction. GAP-7 is closed.

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

Implementation decision (2026-07-29):

- No Qwen batch adapter was added. Alibaba now documents an OpenAI-compatible Batch API, but
  Oracle's only tracked batch caller is strict-schema claim extraction. Qwen's current adapter is
  deliberately loose `json_object` plus Zod validation and is excluded from extraction and other
  strict-schema slots. Advertising adapter batch support would therefore have no safe tracked
  caller. Revisit only with a non-strict batch workload or proven strict schema support.
- DeepSeek remains batch-unsupported and excluded from strict-schema slots. Its beta strict
  function-call surface is not implemented or advertised.
- Qwen explicit markers and Responses session-cache persistence were removed. The adapter keeps
  provider-reported cache-token normalization for observation, but routes use `qwen_none` and the
  catalog does not claim prompt-cache control until a repeated real-prompt fixture proves net cost
  savings.
- The extraction dispatch card names the current provider, lists the three supported native batch
  adapters (Anthropic, OpenAI, Vertex), disables Batch for Google, Qwen, and DeepSeek, and warns if
  an old incompatible setting is already active.
- The settings API rejects unsupported Batch mode and rejects changing an active Batch route to an
  unsupported provider. Both extraction workers fail loudly on stale invalid configuration and
  name the required admin action; neither silently skips, auto-flips the setting, nor runs an
  unapproved sync fallback.
- Grok 4.5 session `019fac1a-fb96-77b3-b6cd-0fc1001e3c11` approved the final diff with no
  actionable findings. Commit `4d56ad57c96a71eaf420c52cd43e9536a0a8f779` passed GitHub
  Actions run `30422669789`. Production deployment `dpl_7JQoF119e4DVnNHtRE73xxDWUqoX` was
  ready and promoted to `https://oracle.designflow.app`.
- The signed-in production Settings page showed build `4d56ad5`, the current Google extraction
  provider, Sync selected, Batch disabled, and plain-language support text naming Anthropic,
  OpenAI, and Vertex as the tracked Batch providers. The layout was readable with no overlap or
  clipping. GAP-8 is closed.

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

Local status (2026-07-29):

- The offline owned-source scan found no application or script reader of the deprecated
  `employees` columns. Auth resolution, chat authorization, and checked-in RLS SQL join through
  `employee_identities`. Live policies, functions, triggers, rules, views, indexes, and constraints
  still require the separate credentialed catalog audit below.
- `pnpm --filter @oracle/db verify:identity-cleanup -- --contract-only` fails loudly if an owned
  reader returns and checks that any future drop migration sorts after the identity backfill.
- The credentialed read-only production audit passed on 2026-07-29: `employeesTotal=38`;
  `auth_user_id`, `auth_provider`, and `auth_provider_subject` each had zero non-null values. The
  only reported dependencies were the expected local
  `employees_auth_user_id_unique` constraint and `public.employees_auth_user_id_unique` index.
  There were no external or inbound blockers.
- Rollback compatibility passed on 2026-07-29: commit
  `53047981e2580bbba56451aaf4aeb034d9a92b3b`, CI run `30424102001`, promoted Vercel deployment
  `dpl_7MVqENiyLL3FeQCiB9f4vmTiMCQq`, and a signed-in protected `/admin/settings` check showing
  build `5304798` for Albert H. (`Lead Architect`).
- The authorized local removal is implemented in the new rerun-safe forward-only raw migration
  `98_drop_deprecated_employee_identity_columns.sql`, after migration 40 and before the reserved
  migration 99. `packages/db/src/schema.ts` no longer exposes the three deprecated fields.
- Final rollout passed on 2026-07-29: commit
  `30eed149ef89c2ab5f68390cde704daba63d2f69`, CI run `30424618491`, and promoted READY Vercel
  deployment `dpl_DeZNsq6RduGKZs2dQhw2RtmJMEHs`.
- The first production `pnpm db:migrate` applied migration 98. A second full run skipped exactly
  migration 40 because the legacy column was absent, reran migration 98 safely through its
  `IF EXISTS` clauses, and completed seed and RLS checks.
- Protected `/admin/settings` loaded after the drop on build `30eed14` as Albert H.
  (`Lead Architect`). GAP-10 is complete.

Closed gate evidence: migration 98 applied in production; a second full `pnpm db:migrate` skipped
only migration 40 and reran migration 98 safely; CI run `30424618491` passed; Vercel deployment
`dpl_DeZNsq6RduGKZs2dQhw2RtmJMEHs` was READY and promoted; protected Settings loaded after the drop
on build `30eed14`.

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

Implementation and release evidence (2026-07-29):

- `/admin/gaps` keeps raw `model_coverage` findings in a separate administrative panel. The normal
  employee-gap table, chat retrieval, and lull-question worker continue to exclude those rows.
- The map-coverage writer now stores the source type/id, active map id, exact map-element ref,
  element kind/local id, and map shape in `gaps.source_context`.
- An admin must write the employee-facing question and conversion reason and select active
  recipients. Saving creates a reversible draft. Sending creates one normal `coverage_question`
  gap per recipient; cancelling a draft creates no employee gaps.
- A partial unique source-finding key, row locks, terminal-state checks, and one database
  transaction make draft creation and sending safe against retries and double-clicks. Cancelling
  releases the active-draft constraint so a corrected draft can be created. Disabled or missing
  recipients stop the send clearly.
- `model_coverage_conversion_events` is append-only and records the admin, timestamp, action,
  immutable source snapshot, recipient ids, and created gap ids. The administrative source row is
  marked resolved only in the same transaction that creates the employee gaps and the send audit.
- `verify:model-coverage-conversion` guards authorization, idempotency, source provenance, audit
  writes, terminal-state rejection, and employee-consumer exclusion without network access.
- Commit `e1d16f5cba7b9db03199b1d29e798bc5d2dff783` is released. Migration 100 applied
  successfully twice, CI run `30426093402` passed, Vercel deployed the exact commit, and Grok 4.5
  session `019fac5e-d70f-7eb1-b6ee-d542152289b8` approved the final diff.
- Signed-in production proof passes draft, cancel, redraft, active-recipient isolation, and
  append-only event ordering. Finding `66fc69be-4da4-5d2c-9571-84caaa1e67a8` has cancelled
  conversion `fd0c9987-5cfb-40b6-ab2d-6d5946fdd367` and replacement conversion
  `3b22e8cc-0827-4397-9f74-d0a2e04e9bc5`, addressed only to Albert.
- **Sent 2026-07-29.** Conversion `3b22e8cc` is `sent`; `created_gap_ids` holds exactly one ID
  `e2aa9061-2757-430b-befb-a0d384002ed3`; the event order is `draft_created`, `cancelled`,
  `draft_created`, `sent` with exactly one `sent`; finding `66fc69be` is `resolved`; and the
  production-wide `coverage_question` count is exactly 1, targeting Albert only.
- **Double-submit no-op PROVEN at runtime, 2026-07-29.** `sendCoverageConversion` was invoked a
  second time against production with the same conversion id (same `Next-Action` id, synchronous
  request from the signed-in admin page). It returned **HTTP 200** and mutated nothing: 1
  `coverage_question` row, 1 `sent` event, `created_gap_ids` length 1. HTTP 200 is the discriminator
  — the line after the guard (`if (draft.status !== 'draft') throw`) would have produced a 500, so a
  200 with zero mutations is reachable only via the `status === 'sent'` early return
  (`apps/web/app/admin/gaps/_actions.ts:134`). Note `verify:model-coverage-conversion` asserts that
  line exists but is a STATIC source match — never cite it alone as runtime proof. Never cite the
  partial unique index either: it blocks a second *conversion* per source gap, not a second *send*.
- Deferred debt, NOT a GAP-11 defect: `gaps` terminal-status writes are inconsistent across three
  call sites — `sendCoverageConversion` sets `status`+`updatedAt`, `updateGapStatus`
  (`_actions.ts:37`) sets `status` only, and `brain-synthesis` (`brain-synthesis.ts:662`) sets
  `status`+`resolvedAt`. No consumer reads `gaps.resolved_at`. Fix all three behind one shared
  helper when gap-status writing is next touched; do not patch a single site, and do not backfill.
- Cross-plan interaction, recorded 2026-07-29: GAP-11 sends produce `coverage_question` gaps, and
  the GAP-12 lull worker excludes only `model_coverage`
  (`apps/workers/src/trigger/lull-interjection.ts:291`), so these gaps are eligible to be posted to
  the target employee during a channel lull. This is by design for real questions, but it means a
  *test* gap left open is a live posting candidate. The GAP-11 test gap `e2aa9061` was resolved on
  2026-07-29 for exactly this reason; production now has 1 `coverage_question` row and 0 open.

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

Local implementation evidence (2026-07-29):

- The worker keeps the existing open-status, `model_coverage` exclusion, assignment, participant,
  live-typing, cooldown, hourly-limit, advisory-lock, and final rate-state checks. It scans every
  eligible gap in bounded 200-row keyset pages; priority and recency break only relevance-score ties.
- It embeds only the recent user-message window and eligible gaps. Missing gap vectors are stored
  on `gaps.embedding` as a search aid. Claim embeddings and claim evidence are unchanged.
- `lull_gap_minimum_relevance` defaults to `0.35` and is validated at startup. No relevant gap
  means no draft and no post. Missing real embeddings fail clearly instead of using zero vectors.
- `verify:lull-topical` is network-free and proves a matching gap beats more than 50 unrelated
  urgent gaps, unrelated-only candidates yield no question, stale vectors refresh, zero-stub
  embeddings fail closed, filters precede embedding, priority breaks equal-score ties, and the
  advisory-lock/final-typing/claim order remains intact. `verify:gap-topical-schema` protects the
  raw-migration/schema/latest-snapshot ownership contract.
- Release proof passed on 2026-07-29. Migration 101 applied successfully twice through
  `pnpm db:migrate`; CI run `30427353184` passed; Vercel deployed exact commit `3c13fdc`; and
  Trigger.dev promoted worker `20260729.2` in deployment `u5e3t6ql`.
- A live provider proof used `text-embedding-3-small` with no fallback. The related
  vendor-invoice gap scored `0.7493` and beat an unrelated urgent design-color gap at `0.1004`.
  When the unrelated candidate was tested alone against the same production threshold, selection
  returned null, proving the no-post branch without sending a synthetic question to employees.

### GAP-13: oversized conversation windowing

1. Capture real or synthetic conversations beyond the smallest supported model context.
2. Add message-boundary windows with controlled overlap and non-quotable carry-in context.
3. Preserve each message's original evidence identity and timestamp.
4. Deduplicate candidates across overlapping windows with the existing candidate identity rules.
5. Fail loudly when even one message cannot fit rather than truncating it.

Gate: an oversized fixture completes within budget, loses no quotable message, and produces no
overlap duplicates.

Local implementation evidence (2026-07-29):

- Sync and provider-Batch extraction use the same pure window builder. Windows split only between
  complete messages and repeat `extraction_window_overlap_messages` active messages across a
  boundary. Original IDs, timestamps, authors, and content are reused unchanged.
- Prior complete/skipped carry-in stays in the prompt's explicit non-quotable block. It may be
  reduced from the oldest end only when needed to leave room for one complete active message.
- The effective formatted-text cap is the lower of `extraction_char_budget` and
  `extraction_window_context_ratio` of the smallest verified context length across the complete
  configured route pool, using a conservative character/token estimate. Missing route context
  metadata fails loudly. There is no hard-coded model choice or unapproved fallback.
- Repeated active evidence goes through the unchanged candidate-before-claim validator and
  `computeCandidateHash`/promotion lock, so overlap cannot create a second permanent claim.
- Message terminal state is reconciled across every owning window in the extraction job. Any
  successful owner is sticky in either completion order; failed-first plus pending stays
  processing; `failed` is written only when every owner failed.
- `verify:conversation-windowing` is network-free and covers a synthetic 80-message oversized
  conversation, exact budget compliance, complete quotable coverage, overlap, evidence ID and
  timestamp preservation, carry-in labeling, stable candidate identity, unknown model context,
  and one-message hard failure without truncation.
- Release proof passed on 2026-07-29. Migration 102 applied twice through the normal journal; CI
  run `30428842450` passed; Vercel deployed exact commit `19859e0`; and Trigger.dev promoted worker
  `20260729.3` in deployment `qx5wrwna`.
- The production-route proof resolved all three configured extraction candidates. Their smallest
  verified context was 1,047,576 tokens, so the live 24,000-character setting remained the tighter
  cap at ratio `0.7`. A 250-message synthetic conversation split into six windows, covered all 250
  source IDs, stayed under the cap, exercised two-message overlap, and produced one candidate hash
  for the repeated evidence rather than a second permanent claim identity.

### GAP-14: close documentation

1. Update this status table as each gap changes.
2. Update `AGENTS.md` section 15, affected architecture/configuration docs, and `HANDOFF.md`.
3. Mark optional items intentionally rejected when evidence says they are not worth building.
4. Keep blocked work visible with the named owner and approval needed.

Gate: every known gap is done, explicitly rejected with evidence, or blocked on a named external
decision. No vague "build later" row remains.

Current audit result (2026-07-29): implementation and production evidence are aligned through
commit `a7637f7` and green CI run `30445659590`. GAP-14 remains partial because owner choices, approved fixtures, exact mutation
approvals, natural production samples, GAP-11 lifecycle proof, and deferred macro work remain
open. This is an honest closure record, not a claim that those items are complete.

End-of-phase rule: after completing any remaining GAP phase, re-read every later GAP phase through
GAP-14 and report any assumption, identifier, schema, file, interface, decision, or verification
gate that the completed work changed. Update this plan before handing the next phase to a fresh
session. Do not carry downstream drift only in chat.

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
