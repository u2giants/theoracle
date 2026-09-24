<!-- Moved verbatim from AGENTS.md (issue #22). AGENTS.md is the router. -->

## 11. Intentional quirks and non-obvious decisions

### `document-ingestion`'s outer task catch overwrites `documents.processing_error`

Looks like:
An inner branch in `processDocument()` sets a specific `documents.processing_error`
(e.g. the workflow-reader strict branch writing `Source workflow read failed: …`),
so that message is what admins will see on a failed document.

Actually:
The task-level `run` catch (`apps/workers/src/trigger/document-ingestion.ts`, ~L1604)
unconditionally re-writes `documents.processing_error` with the THROWN error's
`.message` on any throw. If an inner branch sets a nice message but then re-throws a
different (raw) error, the outer catch clobbers the nice message. This silently broke
the strict workflow-read contract until the 2026-07-07 live gate exposed it.

Why / do not change without care:
The outer catch is the single loud failure surface for the whole task, which is good.
The rule for inner branches: if you want a specific `processing_error` to survive,
`throw new Error(thatSameMessage)` — do not set it and then throw a different error.
See fix `e6a5e07` for the pattern.

### One employee can have many auth identities

Looks like:
The old employee auth columns are gone, so identity data may look missing from `employees`.

Actually:
`employee_identities` is the real auth-link table. Production migration 98, a second full migration run, and post-drop protected-login proof all passed in release `30eed14`.

Why:
One person may log in through Google and Microsoft 365 and still be the same employee.

Do not change because:
Collapsing back to one auth identity per employee breaks real user linkage and RLS helpers.

### Employee removal is soft-disable, not hard delete

What changed:
Admin -> Employees exposes Disable/Re-enable controls backed by `employees.disabled_at`.

Why:
Employee rows are referenced by identities, messages, claims/evidence, documents, assignments, review events, and audit history. Hard-deleting a person can break provenance and historical records, while `disabled_at` already blocks login/linking and active RLS helpers.

Future sessions should:
Use `apps/web/app/admin/employees/_components/employee-access-form.tsx` and `updateEmployeeAccess()` for GUI access changes. Do not add hard-delete employee buttons unless you first design archival/reference cleanup across all employee FKs.

### All inference must go through `OracleAIClient`

Looks like:
It would be simpler for routes or workers to call provider SDKs directly.

Actually:
The provider adapters are the only supported inference boundary. They own prompt shaping, provider-native caching, reasoning translation, and usage normalization.

Why:
The project depends on provider-specific caching and structured-output behavior that generic wrappers and ad hoc calls hide.

Do not change because:
Direct SDK calls bypass context-pack logging, cache observability, route fallback, and consistent validation.

### Source outlines are not evidence

Looks like:
`source_outlines` and `source_groups` summarize a document, so it can be tempting to quote them or treat them as another evidence source.

Actually:
Source outlines are provisional macro guidance only. Durable claims still require exact quotes from messages or document chunks, and durable macro relationships cite approved claim IDs through `macro_relationship_claims`.

Why:
The Oracle's core guarantee is quote-level provenance. Outline prose can help the extractor notice source structure, but it is model-generated interpretation rather than source text.

Do not change because:
Letting outline prose validate quotes would create untraceable claims. Approved macro relationship helpers must continue to verify support claims are currently `approved` at read time.

### Log the actual AI result route, not only the planned route

Looks like:
The caller already resolved a route before calling `OracleAIClient`, so it can log that route in `model_runs` and `model_run_usage_details`.

Actually:
`ModelRouter` may dispatch to a non-primary approved candidate from the model pool. `OracleTextResult` and `OracleObjectResult` carry `routeId`, `provider`, `modelId`, `attemptedRoutes`, and `usedNonPrimary` after dispatch.

Why:
Cost/cache dashboards and model-routing debugging need the route that actually ran, while `model_run_attempts` preserves each candidate tried.

Do not change because:
Logging the pre-dispatch route hides non-primary dispatch and makes cache-hit/cost accounting wrong. New AI callers should use the result metadata when writing usage rows and call `logModelRunAttempts` / `logAllCandidatesFailedAttempts` for candidate visibility.

### Chat retrieval is deterministic, not AI-SDK tool calling

Looks like:
The chat route used to define `search_company_knowledge` and `check_open_gaps` tools, so re-adding `tools` to `providerOptions` might seem like restoring agentic retrieval.

Actually:
The native provider adapters do not execute Vercel AI SDK tool definitions from `providerOptions`. The chat route now performs retrieval deterministically before the model call and injects recent messages, open gaps, approved claims, and Brain snippets into prompt blocks.

Why:
All inference goes through raw provider adapters to preserve provider-native cache/usage fields. Passing AI SDK tools through this boundary looked useful but was decorative unless every native adapter learned tool orchestration.

Do not change because:
Reintroducing AI SDK tools in the chat route can create a false sense that the model is searching live. Add retrieval through `searchWithRetrievalPlan()` and prompt blocks, or implement tool orchestration explicitly inside the native adapter boundary.

### OpenRouter is enrichment-only

Looks like:
`openrouter.ts` and OpenRouter-related code mean inference still runs through OpenRouter.

Actually:
OpenRouter is only used to enrich the admin-side model catalog with pricing/capability metadata.

Why:
Inference requires native provider features and exact usage fields; catalog enrichment does not.

Do not change because:
Reintroducing OpenRouter into the inference path would erase provider-native cache and usage behavior that the rest of the system expects.

**DeepSeek inference is ALWAYS direct (policy).** `deepseek/*` routes run through
`DeepSeekAdapter` against `api.deepseek.com` (OpenAI-compatible, `DEEPSEEK_API_KEY`) —
NEVER OpenRouter. There is no OpenRouter inference adapter in `buildStandardAdapters()`.
`DEEPSEEK_API_KEY` must be set in EVERY environment that runs `deepseek/*` (Vercel chat +
the Trigger worker). If it is missing, `DeepSeekAdapter` is omitted at boot (loud
`console.error` in `standard-adapters.ts`) and any `deepseek/*` route fails to dispatch
and falls back to the next pool candidate. (`DEEPSEEK_API_KEY` was set in the PROD Trigger
env on 2026-07-09 via the Trigger management API + the Trigger PAT in 1Password; the
transcript summary now runs on `deepseek/deepseek-v4-flash`, live-verified worker
`20260709.1`.)

### `google/*` model settings are real Gemini API routes, not Vertex aliases

What changed:
`google/*` model IDs now resolve to the `GoogleGeminiAdapter`, while curated `vertex_*` routes continue to use `VertexGeminiAdapter`.

Why:
Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`) returned `NOT_FOUND` through the configured Vertex project/region, but worked through the Gemini API using the deployed service-account OAuth path. The extraction A/B/C eval route `google_gemini_3_1_flash_lite_extraction_eval` depends on this split.

Future sessions should:
Do not map `google/*` back to `vertex` in `packages/ai/src/routes/resolve.ts` unless the exact model has been verified in the configured Vertex region. `GEMINI_API_KEY` is optional; `GoogleGeminiAdapter` can also mint Gemini API OAuth tokens from `GOOGLE_APPLICATION_CREDENTIALS_JSON`.

### Trigger.dev schedule slots have one reserved opening

What changed:
The `extraction-ab-eval` worker is an immediate Trigger.dev task with no cron sweep. A cron fallback was attempted on 2026-06-16, but Trigger.dev deploy failed because the project had 10/10 schedules. The event-driven lull-interjection change later removed its every-minute schedule, leaving 9/10 schedules.

Why:
The A/B eval page queues rows and dispatches `extraction-ab-eval` immediately from Vercel through `TRIGGER_SECRET_KEY`. The one open schedule slot is operational headroom, not an invitation to restore polling.

Future sessions should:
Do not add new Trigger schedules casually. Keep the remaining slot available; reuse/consolidate an existing schedule or increase the Trigger.dev schedule limit before adding another `schedules.task()`. Deploy workers with `corepack pnpm --filter @oracle/workers run deploy`.

### Teams transcript ids + the getAllTranscripts PULL endpoint (don't reintroduce these bugs)

What changed:
Two non-obvious things in the scheduled-meeting transcript path (2026-06-24), both found by hitting them in prod:
1. `teams-transcript-ingestion` hashes a long derived transcript id to 32 chars for `client_message_id` (`deriveTranscriptId`). Scheduled online-meeting transcript ids are ~230-char base64 blobs; `teams:<id>:<n>` overflows `messages.client_message_id varchar(255)` and every insert fails. The full id is still kept in `metadata_json.transcriptId`.
2. The PULL endpoint for listing a user's transcripts is `users/{id}/onlineMeetings/getAllTranscripts(...)` — NOT `communications/onlineMeetings/getAllTranscripts(...)`. The `communications/...` form is the tenant-wide **subscription** resource only; using it for a GET silently 404s (and a swallowed 404 looks like "no transcripts", so the scan returns 0 with no error).

Why:
Both look like harmless simplifications but break ingestion/discovery for scheduled meetings specifically (ad-hoc "Meet Now" ids are short, so neither bug showed before).

Future sessions should:
Keep the id hashing (don't revert to the raw id) and keep the two endpoints distinct (subscription resource vs per-user pull). `getOnlineMeetingTranscripts` is also deliberately resilient — a first-page 403 throws (real access gap), but a request timeout or Graph's `startIndex=-1` nextLink 400 keeps partial results; don't make it throw on every non-404.

### Supabase project cutovers have platform integration surfaces

What changed:
The production Supabase project moved from Ohio (`vokucjpanhvqunimlvsp`, now `oracle.old`) to N. Virginia (`eqccjfbyrywsqkxxpjvg`, `theoracle`) on 2026-06-20.

Why:
A Supabase project cutover is not just `DATABASE_URL` / `DIRECT_URL` / browser key rotation. Vercel, GitHub, Trigger.dev, Supabase Auth providers, Microsoft Entra redirect URIs/client secrets, Supabase.com project integrations, and Recall live-bot envs can all hold project-specific URLs or secrets.

Future sessions should:
Use `docs/deployment.md` "Supabase project cutover checklist" before declaring a cutover done. Vercel's Supabase integration may inject `SUPABASE_*` / `POSTGRES_*` env vars that this app does not read; the runtime still depends on `NEXT_PUBLIC_SUPABASE_*`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, and `DIRECT_URL`.

### The prod DIRECT host is IPv6-only — query prod via the session pooler from a local script

Looks like:
The 1Password "Supabase DB Direct URL - The Oracle (CURRENT PROD …)" `password` field (`postgres@db.eqccjfbyrywsqkxxpjvg.supabase.co:5432`) is the obvious connection string to run a local Node/psql script against prod.

Actually:
That direct host now resolves to an **IPv6-only** address. A v4-only machine fails with `getaddrinfo ENOENT` (it resolved once mid-session, then stopped — don't trust intermittent success). Use the **session pooler** instead — same 1Password item, field **`oracle_session_pooler`**: `postgresql://postgres.eqccjfbyrywsqkxxpjvg:<db-pw>@aws-1-us-east-1.pooler.supabase.com:5432/postgres`.

Why:
Username MUST be `postgres.<ref>` (plain `postgres` → `tenant/user not found`); the pool host prefix is `aws-1` not `aws-0` (Ohio was `aws-1-us-east-2`); the host is region-wide and the username's ref does the tenant routing. Don't guess the pool host — copy it from the Supabase dashboard **Connect → Session pooler**, or read the `oracle_session_pooler` field.

### Local `.env.local` still points at `oracle.old`

What changed / verified:
As of 2026-06-26, local `C:\repos\oracle\.env.local` still points `DIRECT_URL`,
`DATABASE_URL`, and browser Supabase URL at the previous Ohio Supabase project
`vokucjpanhvqunimlvsp` (`oracle.old`), not current prod
`eqccjfbyrywsqkxxpjvg`.

Future sessions should:
Never run production migrations from the local env by default. Override
`DIRECT_URL`/`DATABASE_URL` with the current-prod 1Password item
`Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle,
eqccjfbyrywsqkxxpjvg)` field `oracle_session_pooler`, then run
`corepack pnpm --filter @oracle/db migrate`.

### Diagram / flowchart image ingestion: the verbatim-quote vs relationship-claim tension

What changed (2026-06-25, worker `20260625.1`):
`document-ingestion` now chunks structure-aware (`chunkTextStructured`), gives images a 32k extraction window, and switches to a handoff-oriented prompt when the transcription looks like a diagram (`looksLikeDiagramTranscription`). This made extraction emit `dependency`/handoff claims instead of one shallow `process_rule` per box.

Actually (the trap):
A handoff claim ("After X, Y happens in dept Z") synthesizes an edge, but every claim's `exactQuote` must be a verbatim substring of ONE persisted chunk. It only validates if the vision transcription renders each edge as **one self-contained line** (`[A:"…"] --(Arrow:"cond")--> [B:"…"]`) AND the extractor quotes that whole line. When the vision pass instead splits an edge across two lines, the extractor paraphrases, the quote fails, and the claim is rejected — a re-eval of the test flowchart went 102 claims → **0** this way.

Why this is fragile:
The vision model is non-deterministic and prod's `default_vision_route` was set to `google/gemini-3.1-flash-image-preview` — an image-**generation** model, wrong for dense reading. One run produced a clean 13k-char single-line-edge transcription (claims validated); the next produced a truncated 2.5k-char split-line transcription (all claims rejected).

Future sessions should:
UPDATE 2026-06-29: prod vision is now `qwen/qwen3-vl-235b-a22b-thinking`, extraction is `google/gemini-2.5-flash`, and Trigger.dev prod is on worker `20260626.7`. The earlier 0-claim blocker was resolved by using strict-schema extraction models and removing silent fallback paths. Use real *vision* models only (never image-generation models), keep one-line-per-edge in `IMAGE_TRANSCRIPTION_SYSTEM`, and use `scripts/reevaluate-document.mjs` for guarded single-document re-evaluation.

### Model routing is fail-loud and pool-bounded

Looks like:
The admin-selected model in Admin → Settings is the one that runs. The `model_runs` row showing a different provider/model looks like the configured choice.

Actually:
Pipeline and auxiliary slots run through `resolveRouteCandidates(db, slot)`: the selected primary plus the approved DB pool, in order. If a model cannot dispatch, the router tries only the next approved candidate; if all candidates fail or a primary is unset, the call fails loud.

Why:
The old hidden fallback path could run an unapproved model and still report success. The approved pool is the only acceptable fallback chain because admins can inspect and edit it.

Do not change because:
Do not reintroduce route-level fallback IDs or worker hard-coded route constants. When debugging "wrong model ran," check `model_run_attempts` and the admin banner for failed primary or non-primary-success attempts, and confirm the provider's key/adapter is registered (`buildStandardAdapters` logs provider availability in prod).

### Explicit Vertex caches are tracked in Postgres

Looks like:
The adapter could rely only on in-memory cache handles.

Actually:
`provider_cached_content` is the cross-process source of truth for explicit Vertex cache lifecycle, and `provider_metadata_json` now also tracks cleanup metadata for temporary GCS-backed cache sources.
Document ingestion records one source hash per extraction window and calls
`releaseVertexExplicitCaches()` after extraction plus macro follow-up dispatch
finishes, scoped by `source_hash`, `cleanup_owner='document-ingestion-worker'`,
and `created_by_job_run_id`.

Why:
Workers and web requests run in different processes and time windows. Cache accounting and cleanup have to survive process boundaries.

Do not change because:
Process-local cache tracking leaks money and makes cache reuse/cleanup invisible. Do not add a generic "delete every cache for this document" cleanup; use the lifecycle row scope so another run's active cache is not removed.

### Qwen explicit chat cache state is intentionally not persisted

Looks like:
`provider_response_sessions` exists, but the Qwen chat path does not currently write it.

Actually:
The table remains available for a future provider session feature. Current Qwen calls use Chat Completions and provider-managed implicit prefix caching only.

Why:
The prior explicit-marker and Responses session-cache path had no recorded Oracle-shaped proof of repeat hits or net savings.

Do not change because:
Do not write Qwen session handles or advertise explicit Qwen cache control until a credentialed fixture proves repeat hits, usage accounting, and net savings.

### Batch API methods on the adapter contract are optional

Looks like:
`OracleProviderAdapter.submitBatch` and `retrieveBatch` are marked `?` (optional). Existing adapters (Anthropic, DeepSeek, Qwen) don't implement them. The interface looks half-finished.

Actually:
The methods are optional on purpose. DeepSeek has no native adapter batch path. Alibaba now documents an OpenAI-compatible Qwen Batch API, but Oracle's only tracked batch caller requires strict schema and Qwen supplies loose JSON mode. OpenAI, Vertex, and Anthropic implement both methods today; future adapters opt in only when they have a safe tracked caller and live proof.

Why:
Forcing every adapter to implement batch would either block adding new providers behind a 50%-discount feature, or paper over it with stub `submitBatch` methods that throw — both worse than the optional pattern. The runtime helper `supportsBatch(adapter)` is the feature-detection contract. See DECISIONS.md D14.

Do not change because:
Making `submitBatch` / `retrieveBatch` required on the interface would force the DeepSeek and Qwen adapters to throw at construction, which would break the per-provider `tryAdd()` boot in `buildStandardAdapters()` and silently disable both providers.

Anthropic batch specifics: each request is a `messages.batches.create` entry with `custom_id` + `params` (same shape as a sync `messages.create`); when `jsonSchema` is provided we attach the forced single-tool input_schema per-request (mirrors `generateObject`). Status maps `processing_status: ended` → `'completed'` and we stream `messages.batches.results(id)` to produce `BatchResultItem`s. Per-item `result.type` → success (`succeeded` — tool_use input or text), or failure (`errored` / `canceled` / `expired`). `providerMetadata` is `{}` — the batch ID alone is sufficient for retrieve.

### Two-phase batch worker — submit and drain are independent tasks

Looks like:
`claim-extraction.ts`, `claim-extraction-batch-submit.ts`, and `claim-extraction-batch-drain.ts` look redundant. The flag `extraction_dispatch_mode` toggles them, but all three are scheduled.

Actually:
Each task reads `settings.extraction_dispatch_mode` at the top and bails when it doesn't match its dispatch mode. So at any given time only ONE of (sync) or (submit + drain) is active. The drain task is always scheduled because it always needs to poll outstanding `provider_batch_jobs` rows even after the flag flips back to `'sync'` (any in-flight batches should still be drained, not orphaned).

Why:
The flag is read every cron tick — flipping it doesn't require a redeploy. The drain task running unconditionally ensures no orphaned batches when admin flips back to sync. Per-task short-circuit at the top is the cleanest gate.

Do not change because:
Removing the always-on drain task would orphan any in-flight Vertex/OpenAI batches if the flag flipped back to sync mid-stream. Removing the gate from the sync task would double-process in batch mode.

### Model catalog quality filter runs at BOTH write and read time

Looks like:
The same filter logic appears in `packages/ai/src/model-capabilities/index.ts` (`refreshModelCatalog`) AND `apps/web/app/api/admin/model-catalog/route.ts` (`passesQualityFilter`). Looks duplicated.

Actually:
Intentional defense in depth. The write-time filter prevents new junk from landing in the DB. The read-time filter handles the legacy case: rows written BEFORE the write-time filter shipped (or when OpenRouter enrichment was unavailable) sit in the DB with no pricing and no capability flags. Deleting them would break pool selections that still reference deprecated model IDs. Filtering at read time hides them from admins without losing the FK target.

Why:
The write-time-only filter let junk creep back into the admin UI whenever an old OpenRouter outage produced unenriched rows. The read-time filter is the catch-all.

Do not change because:
Removing the read-time filter resurrects the original "junky models reappear" bug. Removing the write-time filter floods the DB with no-data rows that build up over time. Keep both.

### Design file operations are not product/design workflow

Looks like:
Design-file naming, server organization, invalid filename characters, Photoshop/Illustrator file bloat, linked assets, packaging, and archive cleanup could live under `creative_design`, `product_development`, or `it_systems` because the design team and design tools are involved.

Actually:
They live in the dedicated top-level domain `design_file_operations`. That domain is for technical creative-file hygiene: keeping design files valid, lightweight, findable, compatible, packaged, versioned, and safe to share. Product/design workflow remains separate: concept intake, design assignment, proofs, approvals, revisions, production handoff, and product lifecycle state belong in `product_development`, `creative_design`, `licensing_approvals`, or `production_lifecycle`.

Why:
The same employees participate in both knowledge bases, but the user intent is different. "How should I name/save/store this file?" should not retrieve product approval/status claims. "Where is this product in design approval?" should not retrieve filename/server-folder rules.

Do not change because:
Collapsing these domains causes retrieval bleed between computer/file-management practices and the business workflow of designs/products moving through the company. Keep `design_file_operations` as its own retrieval target and preserve its negative boundary against product workflow domains.

### Operations systems are not generic IT support

Looks like:
ERP, CRM, PLM, Google Sheets, and integration work could all live under `it_systems`.

Actually:
Business-system data-flow knowledge lives in `operations_systems`. That domain covers ERP/CRM/PLM workflows, field mapping, source-of-truth rules, validation, and integrations such as moving OrderList, MasterData, and TaskList from Google Sheets into Designflow PLM. Generic account access, password resets, permission troubleshooting, and system administration remain in `it_systems`.

Why:
The Oracle needs to guide operational integration decisions, not just answer technical support questions. "How do I log into Designflow?" and "Which MasterData fields become Designflow PLM item fields?" should retrieve different evidence.

Do not change because:
Collapsing `operations_systems` back into generic `it_systems` makes business-process integration knowledge compete with IT support noise and weakens retrieval for ERP/CRM/PLM data migration work.

### Business Process is for cross-functional workflow overviews

Looks like:
`business_process` could become a vague "company process" bucket for anything operational.

Actually:
It is only for end-to-end workflows, operating-model explanations, and handoffs that span multiple departments. A claim can and should carry `business_process` plus narrower domains like `licensing_approvals`, `product_development`, `production_lifecycle`, `customer_ops`, `logistics_shipping`, or `finance_pricing` when those areas are materially involved.

Why:
Broad questions such as "how does the overall company process work?" need to retrieve overview claims without losing department-specific facts.

Do not change because:
Mapping cross-functional extraction output back to `customer_ops` buries companywide workflow knowledge under a single department and makes broad process queries unreliable.

### Training enablement is not people/org ownership or HR records

Looks like:
Training people to do their jobs could live under `people_org` because it involves employees, departments, roles, and onboarding.

Actually:
Job-training knowledge lives in the dedicated top-level domain `training_enablement`. That domain covers onboarding plans, role-specific training checklists, SOP learning paths, work instructions, shadowing, cross-training, skill checks, and refresher training after workflow changes.

Why:
The retrieval intent is different. "Who owns onboarding for the design team?" is an ownership/org question. "What checklist should a new design hire follow to learn proof setup?" is training enablement.

Do not change because:
Collapsing `training_enablement` into `people_org` makes procedural learning material compete with org charts, escalation paths, and ownership facts. Keep sensitive HR/personnel records — compensation, discipline, performance evaluation, and personal conflicts — out of this domain.

### Claim revision is supersede-and-replace, not overwrite

Looks like:
If a pending or approved claim is 80% correct, the admin/reviewer could simply edit `claims.summary` and approve it.

Actually:
Claim revision creates a replacement claim, copies the supporting evidence/domain/entity metadata, marks the original claim `superseded`, links `claim_metadata.superseded_by_claim_id`, and writes an append-only `claim_review_events` row with before/after state and reviewer note. Admins can edit approved claims from `/admin/claims`; that edit creates a replacement claim in `pending_review`, so the replacement must be approved before it becomes active Brain/retrieval knowledge.

Why:
The original row is the AI's first interpretation of the evidence. Keeping it makes review quality auditable and gives future AI comparison tools a clean before/after pair to analyze.

Do not change because:
Overwriting claims in place destroys the evidence of what the model got wrong and weakens the provenance chain that makes Oracle answers explainable.

### Non-admin claim review is direct-assignment only for now

Looks like:
`knowledge_domain_review_departments` means department members should see every claim in their mapped domains.

Actually:
The table remains in the schema as a future routing/authorization map, but the current `/claims` page only shows claims that were directly assigned through a `claim_review_question` gap. The old "My review domains" queue is intentionally hidden, and the server action permission check only allows admins or the employee directly assigned to that claim.

Why:
The team wants explicit review sends, including multi-person and review-group assignment, before reopening broad domain queues.

Do not change because:
Re-enabling domain queues can expose large pending-review surfaces to non-admin employees. If domain review is restored later, update `/claims`, `canReviewClaim()`, and this guide together.

### Claim corrections become prompt lessons, not training or evidence

Looks like:
Reviewer notes and revised claims should make the model "learn" automatically or become Brain evidence.

Actually:
Approved replacement claims feed a semi-stable extraction prompt block through `packages/ai/src/prompts/claim-correction-lessons.ts`. The sync extraction worker, batch-submit worker, and document-ingestion worker include that block in future extraction calls; `/admin/ai/claim-lessons` shows the exact block.

Why:
The project needs an immediate auditable feedback loop from human corrections without pretending to fine-tune the model or treating review commentary as source evidence.

Do not change because:
Reviewer notes are not evidence. Keep correction lessons as prompt guidance only; the candidate-before-claim validators still decide whether new model output can become a claim.

### Ineligible models are SELECTABLE (red checkbox), not disabled

Looks like:
Models that don't meet a stage's required capabilities still have an active checkbox in the model-pool grid, just colored red.

Actually:
Admin override is intentional. Sometimes a model is fine for a stage even when one of the canonical capability flags is missing (e.g. OpenRouter hasn't enriched the model yet, but the admin knows it supports tools). Disabling the checkbox would force admins to wait for enrichment or edit settings via SQL.

Why:
The stage-requirements predicates are a heuristic, not ground truth. Red styling + the missing-caps hover tooltip make the override state obvious; no silent risk of accidental selection.

Do not change because:
Disabling the checkbox blocks valid admin overrides and forces SQL editing.

### Stage `thinking` requirement is on Synthesis, not Extraction

Looks like:
The Extraction model card has no reasoning-effort row visible, while Synthesis does — even though extraction is the more "thinking-heavy" task by feel.

Actually:
`thinking` was moved from `STAGE_REQUIREMENTS.extraction` → `STAGE_REQUIREMENTS.synthesis` on 2026-05-28 (`apps/web/lib/stage-requirements.ts`). Extraction benefits more from speed + verbatim quote fidelity; synthesis benefits from extended reasoning when consolidating a large approved-claim corpus into a single Brain section.

Why:
Earlier requirement set forced extraction into reasoning models that produced slower, more elaborate JSON for no provable accuracy win. Moving `thinking` to synthesis matches actual cost/quality observations.

Do not change because:
Putting `thinking` back on extraction excludes Gemini Flash and the cheap GPT-4o-mini path from the extraction pool — both proven good for extraction in our wet-tests.

### OpenAI model catalog uses a blocklist, not an allowlist

Looks like:
A new GPT or o-series model is missing from the admin catalog even though it appears in the OpenAI API response.

Actually:
The source in `packages/ai/src/model-capabilities/sources/openai.ts` uses a blocklist of non-chat categories. A model whose name hits a blocked prefix or substring (`-tts`, `-transcribe`, `-search-api`, etc.) is excluded. Otherwise it passes through automatically.

Why:
An allowlist required a code change for every new OpenAI model generation. GPT-5.x was invisible until `gpt-5` was manually added to the prefix list. The blocklist lets new chat models appear without a code change; only genuinely non-chat categories are excluded. See `DECISIONS.md` D13.

Do not change because:
Reverting to an allowlist means future GPT-6/o-series models will be silently missing from the catalog until someone notices and edits the list. Post-enrichment quality filters (no-data models, ≥$15.01/1M input) provide a second layer of junk removal in `index.ts`.

### Hand-written SQL migrations are authoritative for constraints, views, and data fixes

Looks like:
Drizzle-generated SQL should be enough, so editing old generated files might be acceptable.

Actually:
Generated files cover schema DDL only. Constraints, RLS, views, and data migrations live in `packages/db/migrations/sql/*.sql`.

Why:
The migration runner applies generated DDL plus hand-written SQL in deterministic order.

Do not change because:
Editing old generated files breaks replay expectations and production drift recovery.

### The Drizzle snapshot was baselined at migration 0007 — some tables exist only via hand SQL

Looks like:
`drizzle-kit generate` wants to CREATE tables that already exist in production —
`departments`, `employee_departments`, `provider_batch_jobs`,
`provider_response_sessions` — plus columns like `documents.context`,
`model_runs.dispatch_mode`, `provider_cached_content.provider_metadata_json`.
After the macro-understanding rollout, it may also want to re-emit the
`source_outlines`, `source_groups`, `macro_relationships`, and
`source_coverage_findings` tables from `sql/79_macro_understanding.sql`.
It looks like a fresh, legitimate migration.

Actually:
Those objects were added to `schema.ts` and materialized via **hand-written
`migrations/sql/*.sql`** files, but were never captured in a *generated* Drizzle
migration, so the Drizzle snapshot can drift behind `schema.ts`. Migration `0007`
re-syncs the snapshot through the China bilingual layer, but its **SQL was
trimmed by hand** to only the genuinely-new objects (`claim_translations`,
`claims.source_lang`, `employees.locale`). Migration `0008_sour_agent_brand.sql`
is intentionally SQL-empty: it exists only to commit Drizzle's generated
`meta/0008_snapshot.json` after the macro tables were added to `schema.ts` by
hand SQL. The macro tables are deliberately owned by hand-written
`sql/79_macro_understanding.sql`; if a future generated migration includes them,
hand-trim or explicitly document the reconciliation instead of replaying
already-applied objects.

Why:
A fresh DB still gets those tables — the hand-written `sql/` files create them in
the migrate runner's step 3 (after generated migrations in step 2). So both paths
work: existing DBs already have them; fresh DBs get them from hand SQL.

Do not change because:
Do NOT "fix" a future `generate` by committing its full output if it re-emits
`departments`/`provider_*`/macro tables/etc. — trim those statements (they already exist) and
keep only your new objects, exactly as `0007` does. Re-emitting them breaks
`pnpm db:migrate` on every already-migrated database.

### Claim retrieval has exactly one path, and the two SQL branches must stay in lockstep

Looks like:
`searchWithRetrievalPlan()` in `packages/ai/src/retrieval.ts` contains two near-duplicate SQL queries — a hybrid pgvector+tsvector path and a `_searchFallbackTsvector()` path — and a separate `verify:retrieval-filter-parity` script that seems redundant with typecheck.

Actually:
The fallback runs only when `OPENAI_API_KEY` is unset (dev, no embeddings). Both branches build their WHERE clauses from the same private helper `buildPlanMetadataFilters()`, and the parity guard statically asserts every filter the helper returns is interpolated into BOTH branches. `searchApprovedClaims()` (a weaker, plan-less retrieval) was deleted on 2026-05-28 — there is now exactly one endorsed retrieval entry point.

Why:
The recurring regression here was adding a narrowing filter to the hybrid path and forgetting the fallback, making dev-mode retrieval silently weaker (or vice versa). Typecheck can't catch it — the fragments are SQL strings. The guard runs in CI (`pr-check.yml`) and via `pnpm --filter @oracle/ai verify:retrieval-filter-parity`.

Do not change because:
Adding a second retrieval path (or a filter to only one branch) reintroduces the exact silent-divergence class the guard exists to prevent. New narrowing fields go in `buildPlanMetadataFilters()` and get interpolated into both branches — nowhere else.

### Raw-SQL list parameters are bound as JSON strings, not JS arrays

Looks like:
`buildPlanMetadataFilters()` in `packages/ai/src/retrieval.ts` could use the simpler `= ANY(${arr}::text[])` form instead of `IN (SELECT jsonb_array_elements_text(${JSON.stringify(arr)}::jsonb))`.

Actually:
Two driver pitfalls make the obvious forms fail at runtime (found 2026-06-10, the first day a hinted retrieval ran against an approved+embedded claim): a bare JS array in a drizzle ``sql`` template expands to a placeholder list `($1, $2)`, making `ANY((...)::text[])` a syntax error; and binding the array as one param (`sql.param`) relies on postgres-js serialization of unknown-typed params, which is unreliable. Also, a type modifier such as `vector(1536)` cannot be a bind parameter — `EMBEDDING_DIM` is inlined with `sql.raw`. The static verify guards and typecheck cannot catch any of this; it only fails when the query executes.

Do not change because:
Reverting to `ANY(${arr}::text[])` reintroduces a runtime-only failure that stays invisible until real data exercises the filter. New list filters in raw SQL should follow the JSON-string + `jsonb_array_elements_text` / `jsonb_to_recordset` pattern.

### Microsoft Graph Teams transcripts arrive after the call

Looks like:
The Oracle could "sit in" a Teams call and react live, or read the live transcript panel a bot can see on screen.

Actually:
Microsoft Graph exposes **no** live caption/transcript API, and Teams does not pipe spoken words into the meeting text chat. The Graph transcript path is therefore after-the-fact, and only if transcription was turned on. Ad-hoc "Meet Now" calls are reachable **only** through a `communications/adhocCalls/getAllTranscripts` change-notification subscription (beta endpoint; v1.0 rejects it), which is "listen going forward" — a transcript notifies only if the subscription existed before transcription started.

Live spoken participation now exists through the optional Recall.ai path: Recall provides the meeting bot and STT stream; The Oracle receives finalized `transcript.data` utterances via `/api/teams/live/recall`, writes them as `messages`, and posts only gated questions back to Teams chat through Recall.

Why:
Native live spoken awareness would require Microsoft media-bot infrastructure. Recall avoids changing Oracle's infrastructure by externalizing the Teams audio/STT transport while keeping Oracle's durable state in Postgres.

Do not change because:
Do not confuse the two paths. Graph is post-call evidence/backfill; Recall is live optional participation. Both must still write utterances to `messages` and let candidate-before-claim handle durable knowledge. See `docs/architecture.md` § "Teams transcript ingestion" and § "Teams live participation (Recall.ai)".

### The Graph subscription/transcript helper is duplicated on purpose

Looks like:
`apps/web/lib/microsoft-graph.ts` and `apps/workers/src/lib/graph-transcripts.ts` both implement the app-only token + subscription/transcript calls. Looks like copy-paste that should be a shared package.

Actually:
`apps/web` (the webhook) and `apps/workers` (the subscription manager + ingestion) are separate runtime processes, and cross-app imports aren't allowed. Both need the same small Graph surface. The web copy (`microsoft-graph.ts`) is the reference; the worker copy is intentionally self-contained.

Do not change because:
Forcing a shared package for ~150 lines pulls Graph code into a third location and couples the web and worker builds. If they drift, reconcile toward the web copy rather than introducing a shared dependency.

### ESLint config imports eslint-config-next natively, not via FlatCompat

Looks like:
`apps/web/eslint.config.mjs` imports `eslint-config-next/core-web-vitals` and spreads it directly, instead of the `FlatCompat`-based pattern `create-next-app` generates.

Actually:
With `eslint-config-next` v16 + ESLint 9, the `FlatCompat` path throws `TypeError: Converting circular structure to JSON` (the bundled react config has a circular `configs` object). v16 ships a native flat-config array, so importing it directly is the working path. The old `.eslintrc.json` + `next lint` were removed (Next 16 dropped the `next lint` subcommand).

Do not change because:
Reverting to `FlatCompat` reintroduces the circular-structure crash; reverting to `next lint` breaks entirely (`next lint` no longer exists in Next 16).

### Quote validation is fuzzy for transcripts, strict for documents

Looks like:
`validateQuote` has an `allowFuzzy` path that accepts a quote when its tokens merely *overlap* the source — contradicting the "deterministic verbatim provenance / no fuzzy match" principle in `docs/oracle/03` and the comment at the top of `quote-validator.ts`.

Actually:
Spoken Teams transcripts are disfluent and the extraction model paraphrases them, so the polished claim quote never appears verbatim in any utterance — strict matching rejected ~every transcript-derived claim. The fuzzy path (opt-in, enabled only on the message/transcript path in `claim-extraction.ts`; documents stay strict) is a **deterministic** token-overlap check (no LLM grader) and anchors the stored evidence to the **real** utterance text, not the model's paraphrase. See `DECISIONS.md` D-transcript-fuzzy-quote.

Why:
Without it the entire Teams-transcript feature produces zero promotable claims. Provenance is preserved as "this real utterance supports this claim" rather than "the model copied these exact words."

Do not change because:
Reverting to strict-only re-breaks transcript extraction. If tightening is wanted, raise `fuzzyMinOverlap` or restrict `allowFuzzy` to transcript-sourced messages — don't remove it.

### `raw_transcripts` is hand-written SQL, not in schema.ts

Looks like:
`raw_transcripts` (the original VTT per call) is missing from `packages/db/src/schema.ts`, and the ingestion worker reads/writes it with raw `sql` instead of Drizzle.

Actually:
It's defined only in the hand-written `packages/db/migrations/sql/62_raw_transcripts.sql` (idempotent `CREATE TABLE IF NOT EXISTS`), like the observability views. Keeping it out of `schema.ts` avoids a drizzle-kit drift entry for an ancillary raw-storage table the typed query layer never needs.

Why:
The VTT is stored so the whole pipeline stays re-runnable from true source after Microsoft expires the transcript (`messages` are a lossy transform). See `DECISIONS.md` D-raw-transcripts.

Do not change because:
Adding it to `schema.ts` would make drizzle-kit want to generate a migration for an already-applied hand-written table (drift). Leave it as hand-written SQL.

### The Oracle MCP server is lazy-loaded on purpose — `tools/list` stays at five tools

Looks like:
`apps/web/lib/mcp/capabilities.ts` defines real operations (search claims, list domains, read Brain sections) but none are registered as MCP tools. Only five generic tools appear in `tools/list` (`health`, `list_capabilities`, `tool_search`, `get_capability_details`, `invoke_tool`). It looks like indirection that could be simplified by registering each operation directly as its own MCP tool.

Actually:
This is a deliberate lazy-loaded capability registry. Real operations live in a hidden registry and are reached via `invoke_tool` after discovery through `tool_search` / `get_capability_details`. Keeping `tools/list` tiny means MCP clients that cache the initial list never miss capabilities — we intentionally do **not** rely on `tools/list_changed`. The `verify:mcp` guard (`apps/web/lib/mcp/__verify__/mcp-registry.ts`, wired into the Vercel build gate + `pr-check.yml`) asserts `tools/list` is exactly those five.

Why:
The endpoint is for external AI agents building software for us; the design follows the house lazy-registry standard (same shape as the `devops-mcp` / `synology-monitor` servers). It is read-only and only surfaces approved knowledge (`searchWithRetrievalPlan` filters `status = 'approved'`; Brain tools require `review_status = 'approved'`).

Do not change because:
- Registering capabilities directly as MCP tools reintroduces the exact anti-pattern the design avoids and breaks `verify:mcp` (build fails).
- The live endpoint is `/api/mcp/mcp`. The doubled segment is correct, not a typo: `mcp-handler` requires a `[transport]` route segment and `basePath: '/api/mcp'` derives the Streamable-HTTP endpoint as `<basePath>/mcp`.
- New write (tier-2+) capabilities MUST go through the `invoke_tool` preview/confirm gate; never let a write run without `args.confirmed === true`.
- Full design + "how to add a capability" lives in `apps/web/lib/mcp/README.md` — read it before changing the MCP surface.

### Uploaded images become knowledge via a two-pass vision→text→extract flow

Looks like:
`document-ingestion` could just send an uploaded image straight to a vision model and ask it for claims. Instead it runs a vision model first to produce a text transcription, then runs the normal extraction model over that text.

Actually:
This is deliberate and load-bearing for provenance. Pass 1 (`transcribeImageToText`) renders the image to faithful text (a structured text topology for diagrams — nodes/edges/swimlane headers, verbatim labels kept inside the nodes). Pass 2 is the unchanged chunk → extract → quote-validate → promote pipeline. Every claim's `exactQuote` is validated against a `document_chunk`, and an image has no text to validate against — so the transcription IS the chunk text, and the verbatim-label rule keeps quotes matchable. The transcription is persisted, so the whole thing stays re-runnable and auditable.

Why:
A single-pass "image → claims" call would force bypassing quote validation, breaking the candidate-before-claim provenance guarantee. Keep the two passes separate.

Do not change because:
Inline image input is implemented only in the Vertex adapter (`toVertexParts` → Gemini `inlineData`); the worker formats the part per provider. The vision route is pinned via the auxiliary registry, not the extraction route, so flipping the extraction model to a non-vision provider does not silently break image ingestion.

### Document extraction quotes must stay inside persisted chunks

Looks like:
The extractor could read a whole uploaded document and return any true statement with a quote from anywhere in the document.

Actually:
`document-ingestion` persists `document_chunks`, formats extraction input as labeled chunk blocks, and expects document-derived candidates to use the exact chunk id as `sourceMessageId`. The promotion executor validates every `exactQuote` against one persisted chunk. Existing uploaded rows keep their old chunks until re-uploaded or deliberately reprocessed with chunk recreation.

Why:
Document claims need quote-level provenance that can be re-run and audited. A quote spanning two chunks, even if semantically correct, cannot be promoted because there is no single chunk evidence row that contains it verbatim.

Do not change because:
Letting document extraction use document-level source ids, paraphrased quotes, or cross-chunk quotes breaks the candidate-before-claim evidence contract and can make valid-looking claims impossible to trace.

Large uploads are processed by `buildDocumentChunkWindows()` in bounded extraction windows. There should be no document-level "first N characters only" cap; each window covers whole persisted chunks and produces its own extraction batch/model run. Reintroducing a silent whole-document cap will make long company docs appear to process successfully while losing most of the knowledge.

### Markdown document quotes normalize formatting, not meaning

Looks like:
A Markdown upload should require the model to reproduce every `**`, table pipe, heading marker, and link exactly.

Actually:
Document quote validation uses `MARKDOWN_DOCUMENT_NORMALIZATION_POLICY` for text/markdown uploads. It deterministically strips or normalizes Markdown syntax such as emphasis markers, heading/list prefixes, inline code ticks, links/images to display text, and table separators before matching. It does not rewrite meaning, do fuzzy matching, or allow cross-chunk quotes.

Why:
Business-process docs commonly contain tables and formatted labels. Models often quote the visible text instead of the raw Markdown punctuation, so strict raw matching rejected true claims even when the source chunk contained the visible statement.

Do not change because:
Documents still need deterministic quote-level provenance. If a new format needs looser matching, add an explicit normalization policy for that format rather than enabling transcript-style fuzzy matching on documents.

### Extraction picker intentionally does not require vision

Looks like:
The Extraction stage handles uploaded-image knowledge, so the model picker should require vision.

Actually:
Images are transcribed by the separate auxiliary Image Vision model before Extraction sees them. `claim-extraction` and the extraction pass inside `document-ingestion` call `OracleAIClient.runObject<ExtractionOutput>()` over text blocks and expect structured JSON. The hard picker requirements for Extraction are therefore structured output plus context window, not image input.

Why:
Requiring vision on Extraction filters out strong text/JSON extraction models for a capability the runtime does not use. The provenance-critical image path remains protected by `default_vision_route`.

Do not change because:
Adding `vision` back to `STAGE_REQUIREMENTS.extraction` in `apps/web/lib/stage-requirements.ts` should only happen if a runtime path starts sending raw image parts directly into the extraction route again. Verify with `document-ingestion.ts` first.

### Auxiliary models are a registry, not a 4th pipeline role

Looks like:
The image-vision model selection looks like it should be a 4th `OracleModelRole` next to interview/extraction/synthesis.

Actually:
`OracleModelRole` is intentionally frozen at exactly 3 pipeline stages (each with stage requirements, approved pools, and batch dispatch). Vision, general-purpose, and translation are "auxiliary models" with an explicit primary, an optional approved pool, at most one capability filter, and no baked-in default route. They are defined in `AUXILIARY_MODELS` (`packages/ai/src/routes/auxiliary.ts`) and resolved by `resolveRouteCandidates`. The settings page, picker, and `/api/admin/models` iterate the registry; none of them special-case auxiliary ids by string.

Why:
Auxiliary models share primary-plus-approved-pool routing but do not share a pipeline role's batch-dispatch and role-map structure. Folding them into `OracleModelRole` would ripple through every `Record<OracleModelRole, …>` map. The registry adds new utility-model selections with zero new branches.

Do not change because:
Adding `'vision'` to `OracleModelRole` to "unify" things reintroduces exactly the ripple the registry avoids. Add a registry entry instead.

### One brain, but claims render per-reader-language; evidence and Brain never translate

Looks like:
`claim_translations` plus locale-aware retrieval looks like it could fragment into a separate Chinese knowledge graph, or like the whole claim (including its evidence quote) gets translated for China readers.

Actually:
There is exactly ONE knowledge graph. A claim stays canonical in `claims.source_lang` with its verbatim `claim_evidence.exactQuote` intact; `claim_translations` holds display-only summary renderings per language. `searchWithRetrievalPlan(db, plan, locale)` renders `COALESCE(translation, canonical)` for the reader's locale (and `'simple'` tsvector config for `zh-CN`, since Postgres can't tokenize spaceless Chinese). Three deliberate boundaries: (1) **evidence quotes are never translated** — they must stay byte-for-byte for the quote validator; (2) **Brain synthesis is English-only** — `getBrainSectionSnippets` has no locale path; (3) **translation is opt-in per claim** (admin selects claims to send to the China team) and **claim-review questions (`claim_review_question`) are translated per-recipient** so a question is translated to Chinese only when a recipient is a `zh-CN` employee (the verify path reuses main's review-question + review-groups mechanism, not a separate recertification worker).

Why:
Translating evidence would break verbatim provenance; auto-translating every claim or the Brain would burn tokens on knowledge no China employee needs. Per-recipient/opt-in keeps cost proportional to what's actually directed to China while keeping one shared brain. See `china_imp.md`.

Do not change because:
Feeding a translated quote into validation, or adding a locale branch to `getBrainSectionSnippets`, or auto-translating on approval, each reverses a deliberate decision. The locale-rendering SQL fragments live in `buildPlanMetadataFilters()` precisely so the parity guard forces both retrieval branches to stay in lockstep — add new locale logic there, not in one branch.

### The macro/holistic layer runs on its OWN model slot, and Gemini can't serve it

Looks like:
The Admin → Settings Extraction and Vision model pickers should control everything about processing a document, so if extraction is set to Gemini, the whole document pipeline (including the macro/holistic layer) must be using Gemini.

Actually:
The old macro/holistic writer layer — `source-outline`, `macro-relationship-extraction`, `source-coverage-audit`, and document lens fan-out — was deleted in macro-first Stage 3. The `macro` auxiliary slot (`default_macro_route` + `model_pool_macro`) remains reserved for later inferential macro passes; workflow reading uses `workflow_read`, and business-model alignment uses `model_merge`.

Do not change because:
The macro schemas are deep/nested and need a provider-enforced STRICT-json-schema model — and, VERIFIED IN PROD, **Google Gemini 2.5 flash AND pro reject the complex macro/workflow schemas with `400 "the specified schema produces a constraint that is too complex"`** even though Gemini has strict mode for simpler schemas. So the macro primary must be an **OpenAI** strict-json-schema model (`default_macro_route` seeded `openai/gpt-4.1-mini`). Do NOT set strict macro/workflow/model-merge slots to Qwen or DeepSeek (loose `json_object` + Zod validation only), or to Gemini as primary for complex schemas. The fallback pool `model_pool_macro` is load-bearing — both the Qwen and Gemini primaries failed, and only the pool made the layer resilient. Failures are now visible via `job_runs` + `documents.macro_health`; a fresh macro run must leave `documents.macro_health='complete'`.

### The source workflow reader has its OWN model slot and eval log

Looks like:
The workflow reader is just the first extraction step, so the Extraction model picker or the `macro` picker should control it.

Actually:
`source-workflow-read` resolves `workflow_read` (`default_workflow_read_route` + `model_pool_workflow_read`). It is a long-context, flat structured-output pass that writes `source_workflow_maps` before extraction runs. Its Stage 2 evidence is append-only in `evals/macro-first-battery.md`; keep that file current whenever you rerun the gate or BO-2.

Do not change because:
The 2026-07-07 live gate validated the canonical swimlane fixture with `openai/gpt-4.1` and seated it as primary. Gemini 2.5 Pro rejected the workflow schema as too complex. Anthropic Sonnet is still in the pool, and its temperature request-shape is now guarded by `verify:adapter-request-shapes`, but BO-2 must be rerun before promoting it. If `scripts/reevaluate-document.mjs` refuses to wipe the fixture because claims are cited by Brain/gaps, do not force-delete them; run the direct reader gate and record that limitation in the eval log.

### Qwen and DeepSeek are JSON-mode providers, not strict-schema providers

Looks like:
Qwen and DeepSeek both advertise JSON/object output, so they should be selectable for any stage that says it needs structured output.

Actually:
For Oracle purposes, Qwen and DeepSeek use provider JSON mode plus local Zod validation. They are useful direct providers, but they do not provide the same strict arbitrary JSON Schema guarantee as OpenAI strict `json_schema`, Anthropic forced tool output, or Vertex/Gemini `responseJsonSchema`. The catalog and runtime resolver normalize both families to `structuredOutputs=false` in `packages/ai/src/model-capabilities/index.ts` and `packages/ai/src/routes/candidates.ts`, so stale OpenRouter-enriched rows cannot make them eligible for strict-schema stages.

Do not change because:
Repeated runs failed by omitting required arrays or drifting from the exact schema while still returning syntactically valid JSON. Keep Qwen/DeepSeek available for loose/auxiliary uses, but out of `workflow_read`, `macro`, and `model_merge` style slots that require strict schema. DeepSeek's function-calling strict mode is documented only on the beta endpoint and is not implemented in `DeepSeekAdapter`; do not mark DeepSeek strict-schema eligible until the adapter uses the beta tool-call path and `verify:adapter-request-shapes` covers it. Qwen structured calls must keep `enable_thinking: false` because DashScope JSON mode is incompatible with thinking mode. See DECISIONS `D12a.qwen-deepseek-strict-schema-boundary`.

