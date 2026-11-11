---
summary: "Decision log from D15 (June 2026) onward: Teams/Recall, transcripts, model routing, macro layer, reader contracts, DesignFlow directory; older entries archived."
kind: living
status: current
read-when: code or a doc cites a decision id, or you are about to record or reverse a design decision
---

<!-- Privacy rendering: infrastructure references are non-executable publication placeholders. Original Git blob 46e5a2dad09283ec04e8dcd3ab30e44b250634da at ab73ef791ad48f187fa5d2998428aec99ce6bd82; exact originals are retained in the #27 private custody archive. No obligations, authority, timing or acceptance are changed. -->
# SECURITY NOTE

The Vercel token shared during overnight setup is in the chat transcript. **Rotate it at https://vercel.com/account/tokens before sharing this repo widely.** Also rotate any Supabase service-role / DB URL / Trigger.dev / OpenRouter keys that were pulled into `.env.local` during bootstrap (they remain only in the local untracked `.env.local`, but the token used to fetch them was in chat).

---

# Decisions log

## D-dflow-directory-source-of-truth — DesignFlow directory owns people + roles (2026-11-05)

- **Decision**: DesignFlow's `dflow_prod` user directory (`api.oracle_user_directory` on the shared company Supabase — a different database from Oracle's own) is the source of truth for company people and their DesignFlow roles. Oracle mirrors it read-only: the brain `directory_sync` job upserts `public.employees` matched by `lower(btrim(email))` (never deletes employees) and replaces each person's `employee_directory_roles` rows. Oracle-only fields stay local and are never written by the sync: `is_admin`, `locale`, `departments`/`department`, `role`, identity rows, claim-review groups, and `cmap.employee_flags`.
- **Why**: nobody should maintain a second people list. The admin Employees page shows the mirrored DesignFlow roles next to the Oracle-only fields, which remain admin-managed.

## 2026-09-20 — Connected explanations from approved evidence

Albert authorized the best next refactor after the holistic-understanding audit. Oracle
prompt v1.1 answers requested business explanations before continuing an interview, with
claim citations, labeled interpretations and explicit gaps. This intentionally updates
the interview-only emphasis of historical spec Part 10; the historical spec is retained.
Reviewed relationship premises are supplied as actual text, and citation IDs must belong
to the bounded context. This does not enable shadow business models or relax approval.
See `plan_connected_business_answers.md` STATUS and issue 15 for acceptance and live proof.

This file is the running log of every assumption, stub, and resolution made by the overnight build agent. Each entry cites the spec section it conforms to (or notes "spec underspecified") and the safer alternative that was ruled out.

---

## Older entries (Phase 0 through D14, May 2026) — moved

The entries from `Phase 0 — Bootstrap` through `D14.batch-api-support` (including all `D5.*`–`D14.*` IDs, the three `AI Architecture Retrofit` sections and the `Promotion executor` section, plus `D12a`) were moved verbatim to [`docs/decisions/decisions-2026-05-bootstrap-to-batch.md`](docs/decisions/decisions-2026-05-bootstrap-to-batch.md). A code comment citing one of those IDs in `DECISIONS.md` means that file.

## D15.recall-live-teams — Live Teams participation through Recall.ai (2026-06-04)

- **Decision**: Add an optional Recall.ai live Teams path. `/api/teams/live/start` creates a Recall bot with real-time transcription (`elevenlabs_streaming` first, `assembly_ai_v3_streaming` fallback). `/api/teams/live/recall` verifies Recall signatures and triggers `teams-live-recall-utterance`, which stores finalized utterances as `messages`, gates Oracle interjections, and posts short questions back to Teams chat through Recall.
- **Why**: Microsoft Graph still has no live Teams transcript stream. Native Microsoft app-hosted media bots would require an infrastructure exception. Recall externalizes the media/STT layer while The Oracle keeps its source-of-truth and validation architecture unchanged.
- **Scope rule**: Live utterances are evidence-shaped `messages` rows, not claims. They enter candidate-before-claim like every other message. Post-call Graph transcript ingestion remains the canonical backstop for complete transcripts.
- **Safety rule**: The worker ignores STT partials and acts only on finalized `transcript.data` utterances. It applies a cheap keyword gate before calling the interview model, then uses the existing interjection cooldown/rate-cap settings before posting.

## D-transcript-fuzzy-quote — fuzzy quote match for spoken transcripts (2026-06-04)

- **Decision**: `validateQuote` gains an opt-in `allowFuzzy` path. After strict verbatim + normalized matching fail, if the model quote's content tokens overlap the source utterance by >= `fuzzyMinOverlap` (default 0.5), accept as `normalized_match` (method `fuzzy_token_overlap`) and anchor the stored evidence to the REAL source utterance text, not the model's paraphrase. Enabled only on the message/transcript path (`claim-extraction.ts`); documents stay strict.
- **Why**: First real conversation to hit extraction was a Teams call. Spoken transcripts are disfluent and the model paraphrases them, so the polished quote never appears verbatim — strict matching rejected ~every transcript claim. Product-owner call (2026-06-04) to loosen for spoken sources.
- **Auditability**: deterministic token check (no LLM grader), and evidence stays a real transcript span — only the "model must reproduce verbatim" requirement is relaxed. Partially overrides the "no fuzzy" note in quote-validator.ts / docs/oracle/03. Knobs: fuzzyMinOverlap (0.5), >=4-token floor.

## D-raw-transcripts — persist raw VTT for re-runnability (2026-06-04)

- **Decision**: Persist each call's raw WebVTT in `raw_transcripts` at ingestion (idempotent on transcript_id). Hand-written `migrations/sql/62_raw_transcripts.sql`; worker uses raw `sql`, not in schema.ts.
- **Why**: `messages` are a lossy transform (merged turns, resolved speakers, dropped timing) and Microsoft expires ad-hoc transcripts. Raw VTT keeps the whole pipeline re-runnable from true source for iterative fine-tuning.

## D-transcript-approval-gate — human approval before transcript extraction (2026-06-24)

- **Decision**: Teams transcripts are ingested as `extraction_status='awaiting_approval'` (new enum value; `migrations/sql/75`) and held until an admin approves them at `/admin/transcripts`. `raw_transcripts.approval_status` (`migrations/sql/76`) tracks the decision; approve flips the channel's messages → `pending`, reject → `skipped`. The extraction cron is unchanged (it only ever selects `pending`).
- **Why**: Albert wanted to review meeting transcripts before they produce claims, rather than the prior auto-ingest-then-review-at-claim-level flow. Lowest-blast-radius gate — no extraction-worker change.

## D-scheduled-meeting-transcripts — capture scheduled meetings, not just ad-hoc (2026-06-24)

- **Decision**: Add a second standing subscription on `communications/onlineMeetings/getAllTranscripts` alongside the ad-hoc one (`ensureAllSubscriptions` keeps both alive via the existing `teams-subscription-renew` cron — no new schedule, respecting the 10/10 limit).
- **Why**: Only ad-hoc "Meet Now" calls were being captured; normal scheduled meetings (the common case) produced nothing — last real transcript was 2026-06-04.

## D-meeting-picker — discover meetings, choose which to ingest (2026-06-24, supersedes D-transcript-approval-gate)

- **Decision**: The Oracle does NOT auto-ingest meetings. Available meetings are discovered as metadata only — by the webhook (real-time, `discovered_via='subscription'`) and the on-demand `teams-transcript-discovery-scan` task (past meetings, `'scan'`) — into a new `meeting_transcripts` table (migration `77`). An admin picks meetings on `/admin/transcripts`; picking triggers `teams-transcript-ingestion`, which pulls the VTT, writes `messages` as `extraction_status='pending'` (auto-extract), anchors timestamps to the real meeting time, and flips the row to `ingested`.
- **Why**: The gate was at the wrong stage — it auto-ingested every transcript then gated *extraction*. The product need is to choose, from a list, which meetings get pulled in *at all*. Anchoring to real meeting time also stops `lull-interjection` from treating an ingested past meeting as a live conversation (it was spawning spurious gaps/interventions).
- **Deprecated by this**: the `awaiting_approval` enum value (migration 75) and `raw_transcripts.approval_status` columns (migration 76) are now unused. Left in place (removing a PG enum value is disruptive; the columns are harmless); do not build on them.

## D-fail-loud-model-routing — approved pools replace hidden fallbacks (2026-06-25)

- **Decision**: Remove route-level fallback targets and hard-coded worker fallback routes. Pipeline
  and auxiliary slots resolve an ordered candidate chain from the admin-selected primary plus an
  optional DB-approved pool. A missing provider key fails that candidate loudly and the approved
  pool may continue to its next member. An unset slot or exhausted pool fails loudly; an exhausted
  dispatch raises `AllCandidatesFailedError`.
- **Why**: A selected provider/model could silently run an unapproved fallback model when an adapter was missing or misconfigured, making cost, provenance, and capability debugging misleading. The approved pool is the only acceptable fallback chain because admins can inspect and edit it.
- **Observability**: `model_run_attempts` records each attempted route, including failed primary attempts and successful non-primary attempts. Admin pages show a banner when recent failed or non-primary attempts exist.
- **Capability guard**: Runtime resolution checks `model_capabilities` against slot requirements
  while `settings.enforce_model_capabilities=true`. The strict/deep-schema `workflow_read`,
  `macro`, and `model_merge` slots always enforce their requirements even when that setting is
  false. Other slots may use the bypass only for controlled debugging.

## D-conversation-aware-message-extraction — whole conversations, non-quotable carry-in (2026-06-26)

- **Decision**: Message extraction no longer pulls a global `LIMIT(100)` and then segments the truncated set. Sync and batch extraction share `selectPendingConversations`, which selects whole same-channel conversation segments bounded by the 60-minute gap heuristic and stops at `extraction_char_budget` / `BATCH_SIZE` only between conversations.
- **Why**: Operational claims often emerge from a multi-message discussion. Cutting at an arbitrary global count can split the connected context and cause missed or distorted claims.
- **Provenance rule**: Prior same-channel messages are included only as non-quotable carry-in context (`extraction_carry_in_count`). The active segment's message IDs remain the only valid evidence sources, so quote validation still rejects claims that cite carry-in context.
- **Oversized conversations**: If one conversation exceeds the configured budget, process it whole and log the oversized condition rather than silently truncating it. Future work can add a more sophisticated sliding-window strategy if real conversations exceed model limits.

## D-macro-understanding-boundary — source outlines guide extraction, not evidence (2026-07-02)

- **Decision**: Add a macro-understanding layer in conservative slices. It stores provisional document `source_outlines`/`source_groups`, claim-level `claim_kind`, reviewable `macro_relationships` with `macro_relationship_claims` support links, and historical `source_coverage_findings`. The old LLM writers are removed. Admins can review or manually author supported macro relationships and dismiss historical findings. Current audited human-question conversion starts only from deterministic `model_coverage` gaps.
- **Trust rule**: Source outlines and groups are non-quotable guidance. They can help extraction resolve workflow shape, acronyms, handoffs, branches, and likely lenses, but they cannot create approved knowledge by themselves. Atomic claims still require exact quotes from `document_chunks` or source messages, and quote validation remains the enforcement boundary.
- **Macro relationship rule**: Durable macro relationships cite validated claim IDs, not raw model interpretation. Any Brain/chat/MCP helper that serves approved macro relationships must verify every support claim is currently `approved` at read time; relationship status alone is not trusted.
- **Operational guardrails**: No new Trigger.dev schedule is introduced while the project is at the schedule limit. New macro tables are server-only/service-role surfaces in this slice; RLS is enabled without anon/authenticated policies. Vector columns can exist now, but expensive vector indexes must follow the existing gated `ORACLE_RUN_VECTOR_INDEXES=1` convention.

## D-macro-model-slot — the macro/holistic layer gets its own model slot + fallback pool; OpenAI, not Gemini (2026-07-03)

- **Decision**: The macro/holistic workers (`source-outline`, `macro-relationship-extraction`, `source-coverage-audit`) resolve a dedicated `macro` auxiliary slot (`default_macro_route` primary + fallback pool `model_pool_macro`) instead of borrowing the `general` utility slot. Macro was the first pooled auxiliary slot; auxiliary pools now also cover vision, workflow reading, model merge, translation, transcript summary, and general utility work. Primary seeded to `openai/gpt-4.1-mini`.
- **Why**: On the `general` slot (Qwen `qwen3.7-max`, loose `json_object`) the macro layer hard-failed on EVERY run with `AllCandidatesFailedError` (Qwen omits required arrays), producing zero macro relationships/coverage while the document still showed `complete` (`AGENT_ERROR_LOG.md` ERR-001). Macro is a reasoning/synthesis-over-claims task with deep nested output schemas, distinct from verbatim-quote extraction — it deserves an explicit, admin-visible model choice, not a silent inheritance from "utility".
- **Why OpenAI, not Gemini (verified in prod)**: Google Gemini 2.5 flash AND pro both `400` on the macro relationship/coverage schemas ("the specified schema produces a constraint that is too complex") even though Gemini has a strict-schema mode. So the first Gemini-primary seed would also have failed — the fallback pool saved the run by falling through to `openai/gpt-4.1-mini`. Corrected the primary to OpenAI; Gemini stays as a lower-priority fallback (it handles the simpler source-outline schema). Lesson: for the macro slot use an OpenAI strict-json-schema model; do NOT use Qwen (loose json) or Gemini (complex-schema reject) as primary.
- **Resilience is load-bearing, not optional**: both the Qwen and the Gemini primaries failed; only `model_pool_macro` made the layer survive. Kept as a settings row (admin-editable) wired through the existing pool machinery in `resolveRouteCandidates`.
- **Observability**: the two previously-invisible workers now write `job_runs`, and all three set `documents.macro_health` (`not_applicable|pending|complete|degraded|failed`, race-tolerant precedence, `apps/workers/src/lib/macro-health.ts`), so a failed holistic layer can no longer masquerade as a green `complete` document. A failure log for coding agents lives at `AGENT_ERROR_LOG.md` (referenced from `HANDOFF.md`).
- **Also fixed alongside**: three support-claim queries had a `42P10 SELECT DISTINCT/ORDER BY` bug (ERR-002); lens fan-out was made coverage-first so terminal workflow stages are no longer dropped; `macro_auto_max_support_claims` now actually raises the SQL `LIMIT`; the lens idempotency guard now includes the terminal `'complete'` status.
- **Deferred (in `fix_enhancement.md`)**: exposing `model_pool_macro` in the model-pool-editor UI; the followup fan-out debounce (ERR-003); the workflow-map artifact; `blocked_pending_support` gating (Bug D); before/after outline ordering.

## D-workflow-read-slot — workflow maps use a dedicated route, OpenAI primary until BO-2 rerun (2026-07-07)

- **Decision**: The source workflow reader resolves its own `workflow_read` slot (`default_workflow_read_route` + `model_pool_workflow_read`) instead of reusing extraction, `general`, or the legacy `macro` slot. Current primary is `openai/gpt-4.1`; pool is `["openai/gpt-4.1","anthropic/claude-sonnet-5","google/gemini-2.5-pro"]`.
- **Why**: The reader is a long-context structured map pass over all persisted chunks, not atomic claim extraction and not the older nested macro relationship/coverage pass. The 2026-07-07 Stage 2 gate validated the canonical swimlane fixture with OpenAI and recorded the evidence in `evals/macro-first-battery.md`.
- **Gate evidence**: final active map `72ed0ef9-8ea7-4e60-84a3-a7e9236eb7c8` from run `run_cmra2ork561l00jonzlrqxfcv` was `validated` with 63 nodes, 71 edges, 14 lanes, 1 path, `keptCount=149`, and `droppedCount=0`. Same-hash idempotency, force supersede, failure visibility, and repair were proven. The destructive clean re-ingest subcheck was skipped because the provenance guard correctly refused to delete fixture claims cited by Brain/gaps.
- **Provider boundaries**: Gemini 2.5 Pro rejected the workflow schema as too complex during the gate, so Gemini is not a safe primary for `workflow_read`. Anthropic Sonnet hit the pre-fix temperature request shape in the gate; request-shape handling is now covered by `corepack pnpm --filter @oracle/ai run verify:adapter-request-shapes`, but BO-2 must be rerun before promoting Sonnet. DeepSeek/Qwen JSON-object modes remain Zod-validated, not provider-enforced strict schema, and must not satisfy strict-schema slots.
- **Guardrail**: Any future provider/model promotion for `workflow_read` must update `docs/history/MODEL_BAKEOFF_SPEC.md`/`evals/macro-first-battery.md` evidence and keep `packages/ai/src/__verify__/adapter-request-shapes.ts` current for request-shape and persisted-catalog capability gates.

## D-r0-reader-quality-contract — shared quote policies, hard map refs, deterministic coverage (2026-07-21)

- **Decision**: Map validation and claim validation resolve one named source-kind quote policy. Native Markdown permits deterministic formatting removal, PDF/Word permits the existing OCR/layout normalization, vision transcription remains strict, transcript messages retain the existing fuzzy-token policy, and unknown sources remain strict. A validator diagnostic records the selected policy and which alternate named policies would have accepted a rejected quote; policy selection is never inferred after the fact.
- **Reference rule**: `mapElementRef` is not trusted merely because it has the right string shape. Before candidate evidence or promotion it must name a real element/relation on the active immutable map, and that target's source chunk must be in the current extraction window. Unknown, stale-map, and out-of-window refs fail deterministically.
- **Coverage rule**: Primary map-to-claim coverage is a deterministic shape-registry reconciliation, not an LLM score. Omissions upsert stable `model_coverage` gap IDs with exact source-map provenance. Those rows are administrative model-quality findings and every employee-facing gap consumer excludes them. An admin may now create a reversible reviewed draft and atomically send normal `coverage_question` gaps through the audited conversion flow.
- **Audit/budget rule**: Map diagnostics retain bounded rejected quotes and bounded raw reader output, distinguish root failures from endpoint/path cascades, and allow but count covered same-document cross-segment citations. Per-source read calls, estimated input tokens/cost, repairs, and concurrency are settings-backed fail-loud caps checked before model dispatch.
- **Migration rule**: The historical second `86_source_workflow_maps.sql` is preserved under `migrations/superseded/` but removed from the active `migrations/sql/*.sql` runner. Lexicographic execution previously let it run after `86_macro_first_schema.sql` and describe an obsolete shape. CI now migrates a fresh pgvector database and asserts the surviving generic-map columns and constraints before build.
- **Evidence**: The SELECT-only historical audit for map `9e84efda-755d-4a05-be5a-bbbadfce144e` classifies all 101 persisted drops as 36 root quote-not-found, 46 endpoint cascades, and 19 path cascades, with no unresolved reason class. The old validator did not persist rejected quotes/raw output, so alternate-policy verdicts for those 36 roots are not reconstructible; a post-fix model rerun is separately scheduled instead of guessing. The current production swimlane map replayed through the R0 validator with 0 drops, 56/56 relation-evidence survival, no duplicate element IDs, maximum one current claim per map ref, and no refs with three or more claims. Commands and complete gate status are recorded in `evals/shape-aware-stage2.md`.

## D-r2-entry-approvals — bounded narrative, read-only shadow backlog, responsibilities first (2026-07-27)

- **Narrative macro lane**: Approved at no more than five significant goal, constraint, risk,
  rationale, or open-question elements per narrative segment. Ordinary facts remain claims.
- **Shadow backlog**: Approved for R2 through R5 only as read-only proposals. Shadow rows cannot
  write business objects or versions and carry an explicit `applyEligible=false` marker. The
  application service also enforces the global fail-safe setting and rejects shadow rows.
- **Vertical-slice order**: Responsibilities remain first. Flat role-action-object records are the
  lowest-risk way to prove evidence linkage, semantic shortlisting, reviewed identity, and reuse
  before conditional rules, conversation state, or process topology.
- **Not decided**: Provisional employee answers remain an R6 decision. This approval does not
  authorize provisional serving.

## D-r2-evaluation-contract-v2 — one-span support and honest denominator (2026-09-10)

- **Decision**: R2 contract v2 evaluates only answer rows with a proven single source-bound duty.
  Action paraphrases are limited to the explicit `field-aware-v3` equivalences; object paraphrases
  are not allowed. Composite evidence across source spans is excluded.
- **Eligible set**: 25 rows are proven: 23 by deterministic canonical source records and rows 3/19
  by source-faithful records validated in production map `339ca8b1-e412-4447-8336-7586f08bd746`.
  Rows 14/15/16/23/26 are unsupported under this contract and are excluded from the denominator.
- **Threshold**: Preserve the original 90% quality standard against the honest denominator:
  `ceil(25 * 0.90) = 23`, so acceptance is 23/25 with every unsupported row remaining unmatched.
- **Versioning**: The v1 answer key, historical 27/30 gate and evidence remain immutable. Contract v2
  is a separate manifest and scorer; it does not rewrite old production results.
- **Measured result**: The active production map passes v2 at 23/25 with unsupported matches empty.
  This is a SELECT-only rescore of existing evidence, not a new production run or deployment.

## D-connected-answer-reconciliation — account for evidence before answering (2026-09-20)

- **Decision**: Every substantive evidence-backed request (excluding only clear greetings and
  acknowledgements) uses prompt contract
  `business-answer-reconciliation 1.0.0`. The reconciliation model must classify every
  retrieved claim exactly once and bind directly relevant facts to requested facets.
- **Relationship boundary**: A documented connection must reference an included approved
  relationship and only its supporting claims; the server renders the canonical relationship
  summary. Any model-derived connection is labeled as interpretation and independently reviewed.
- **Serving boundary**: Employee prose is rendered by the server from canonical approved
  claim summaries and exact claim IDs. Models may identify facets and supported connections,
  but cannot silently rewrite approved facts or declare a company-wide absence from bounded
  retrieval. Partial or missing facets require a reconciled, visibly bounded gap marker.
- **Acceptance gate**: A different provider reviews the question, evidence ledger, and
  rendered answer. One reconciliation repair is allowed; a second failure returns no answer.
  Reviewer candidates are the de-duplicated configured model-merge plus macro pools; fewer
  than two distinct providers is rejected before any reconciliation call.
  Citation membership remains only an identity check—the independent semantic review is the
  entailment and omission gate. Every model call has its own context pack and run audit.
- **Boundary**: An attachment on the current request, or the nearest prior attachment when the
  employee explicitly follows up or names a file/document type, stays on the attachment-aware
  generator until the file's content has entered approved evidence. An unrelated new request does
  not silently inherit a stale file.
  A different model family receives the same conversation and attachments and must approve the
  proposed answer before it is published.
  The reconciliation renderer preserves the employee's English or Simplified Chinese locale.
  Until relationships have approved translations, Chinese reconciliation receives their localized
  supporting claims but not the canonical English relationship summary; any connection is labeled
  interpretation and independently reviewed.
  No claim, approval, schema, or retrieval authorization rule is changed by this decision.

# Document ingestion: Word, image vision, auxiliary models, context (2026-06-14)

## D-image-vision-two-pass — transcribe images to text before extraction

- **Decision**: Uploaded images (PNG/JPEG/WebP/HEIC) are ingested in two passes. Pass 1 (`transcribeImageToText` in `document-ingestion.ts`) calls a vision model to render the image to faithful text — a structured text topology for diagrams (nodes `[Shape/Color: "label"]`, edges `[A] --(cond)--> [B]`, swimlane `### headers`), with verbatim labels kept inside the nodes. Pass 2 is the unchanged chunk → extract → quote-validate → promote pipeline run over that text.
- **Why**: Every claim's `exactQuote` must validate against a `document_chunk`. An image has no text to validate against, so a single-pass "image → claims" call would force bypassing quote validation and break the candidate-before-claim provenance guarantee. The transcription becomes the chunk text; the verbatim-label rule keeps quotes matchable. The topology output (vs free-form prose) gives the extractor un-scrambled structure.
- **Provider path**: Inline image input is implemented in the Vertex adapter (`toVertexParts` → Gemini `inlineData`, guard `verify:vertex-inline-image`); the worker formats the image part per provider (Gemini/Anthropic/OpenAI). Inference is provider-direct (`@google/genai`), never OpenRouter. The file-backed Vertex cache is skipped for images (a lone image is below the cache token minimum).

## D-auxiliary-models — configurable models outside OracleModelRole

- **Decision**: Admin-selectable models that are not one of the 3 strict pipeline roles are
  "auxiliary models" defined in a registry (`packages/ai/src/routes/auxiliary.ts`,
  `AUXILIARY_MODELS`) and resolved by `resolveRouteCandidates(db, id)`. Each has an admin-selected
  primary and may define an approved fallback pool. `OracleModelRole` stays frozen at
  `interview | extraction | synthesis`. The settings page, picker, and `/api/admin/models` iterate
  the registry; none special-case auxiliary ids.
- **Why**: Pipeline roles carry structure auxiliary models don't (stage requirements, approved model pools, batch dispatch). Folding vision into `OracleModelRole` would ripple through every `Record<OracleModelRole, …>` map. The registry adds the next utility model with one entry and no new branches.
- **Setting**: `default_vision_route` (+ `default_vision_reasoning_effort`), `default_general_purpose_route`, and `default_translation_route` are seeded with `ON CONFLICT DO NOTHING`. Unset means configuration error, not fallback.

## D-admin-document-upload — company docs decouple from chat channels

- **Decision**: `POST /api/admin/documents` (admin-only, multi-file) uploads knowledge documents directly from Admin → Documents with no channel — it stores the file, inserts a `documents` row, and triggers `document-ingestion`. The channel-based `POST /api/documents` remains for chat attachments.
- **Why**: There is no UI to create a chat channel (channels are only created by the Teams flows / admin raw-import), so the channel-coupled uploader made company-doc upload unreachable. `documents` has no channel dependency — the worker reads by id — so decoupling is clean and is the correct model for company/process knowledge.

## D-document-context-and-hints — uploader context as a soft signal

- **Decision**: `documents` gains nullable `context` (text) and `domain_hints` (jsonb of `knowledge_top_domains.id`). `context` is injected into both the extraction prompt and the Pass-1 image-vision prompt; `domain_hints` are rendered as a non-binding prior. Per-claim `domain_valid` stays authoritative — hints never force or override classification, which stays per-claim (a document legitimately spans multiple domains).
- **Migration ownership, verified 2026-07-29**: `migrations/sql/65_document_context_and_domain_hints.sql` is the authoritative raw-SQL owner and uses idempotent `ADD COLUMN IF NOT EXISTS`. The full `db:migrate` runner applies raw SQL after generated migrations, so a fresh database does recreate both columns. The latest Drizzle snapshot records the same nullable `text` / `jsonb` shape without requiring a duplicate generated migration. `verify:document-context-schema` now enforces this contract on the fresh-database CI fixture. `db:check-drift` correctly audits the separate generated-migration journal and does not report raw migration 65 as drift.

## D-business-process-domain — cross-functional process knowledge (2026-06-14)

- **Decision**: Add `business_process` as a top-level domain for end-to-end company workflows, operating model overviews, and cross-functional handoff maps. The legacy extractor still emits the old `general` enum value, so new extraction maps `general` to `business_process` instead of the former Customer Operations residual.
- **Why**: Whole-company process docs should not be buried under a single department, and broad questions such as "how does our overall process work?" should retrieve overview claims plus relevant department-specific process claims. The retrieval planner now expands broad process queries across `business_process` and neighboring process domains rather than depending on a global fallback.
- **Prompt change**: Extraction prompt version `2.0.1` tells the model to classify by operational meaning, not literal department keywords, and to use `general` for cross-functional/end-to-end workflow claims while also adding narrower domains when a claim materially belongs to them.
- **Follow-up prompt change**: Extraction prompt version `2.0.2` lets document ingestion use `document_chunks.id` as `sourceMessageId` and formats document input as labeled chunks. This keeps document quote validation strict while giving the model an exact source ID and reducing quotes that cross persisted chunk boundaries.

## D-document-ingestion-windowing — no silent document truncation (2026-06-15)

- **Decision**: Large uploaded documents are extracted through `buildDocumentChunkWindows()` in `apps/workers/src/trigger/document-ingestion.ts`. Each model call remains bounded, but the worker iterates every persisted chunk window and aggregates the results instead of truncating the document to the first N characters.
- **Why**: `business-process.md` was a 42,420-character Markdown document. The old first-15k-character cap made the upload appear to complete while extracting only the beginning of the process. Raising the cap into one giant call caused provider structured-output validation to fail. Windowing keeps calls reliable without losing later sections.
- **Quote policy**: Text/Markdown document quote validation uses `MARKDOWN_DOCUMENT_NORMALIZATION_POLICY`, which normalizes formatting syntax such as emphasis, headings/lists, links/images, inline code ticks, and table separators. It is deterministic formatting normalization only; document extraction still rejects paraphrases, fuzzy matches, and cross-chunk quotes.
- **Entity policy**: Unknown-only entity taxonomy results are allowed to promote while staging entity proposals. Invalid domains, ambiguous domains, and entity type mismatches still block promotion.
- **Verified production run**: Trigger worker `20260615.4` reprocessed document `ee1fa682-9e5c-4cf5-89c5-b2f95d047eea` (`business-process.md`) in run `run_cmqehatni237e0un5ioyywuez`: 12 chunks, 155 extraction candidates, 139 promoted pending-review claims, 16 rejections, document status `complete`.
- **Future sessions should**: Keep document windows aligned to whole `document_chunks.id` values, avoid reintroducing a document-level cap, and remember that newly promoted document claims are not retrievable by chat/synthesis until reviewed and approved.

## D16.claim-correction-lessons — approved revisions steer future extraction (2026-06-15)

- **Decision**: Extraction prompt version `2.1.0` includes a semi-stable "reviewer correction lessons" block built from approved claim revisions. `packages/ai/src/prompts/claim-correction-lessons.ts` reads `claim_review_events` where `action='revise'` and the replacement claim is `approved`, formats compact before/after examples plus recurring correction rules, and the sync message worker, batch-submit worker, and document-ingestion worker include it in their `OraclePromptPlan`.
- **Why**: Reviewer notes and revised claims do not magically train the model. The immediate, auditable feedback loop is to feed approved correction patterns back into the next extraction calls while preserving the original AI output and the human-approved replacement.
- **Boundary**: The lesson block is guidance only. It is not claim evidence, not Brain source material, and not fine-tuning. The candidate-before-claim validators still enforce quote provenance, taxonomy validity, sensitivity gates, and promotion rules.
- **Admin surface**: `/admin/ai/claim-lessons` shows counts, recent approved correction pairs, and the exact prompt block extraction will see.
