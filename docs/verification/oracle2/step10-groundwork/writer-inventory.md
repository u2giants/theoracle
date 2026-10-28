# Writer Inventory — complete write-path audit for the consistent-cut phase

**Parent:** #24 · **Closeout step:** §6.10 groundwork · **Date:** 2026-10-27 EDT
**Base:** `b2e7daeb` (upstream main) · **Method:** read-only source audit of `services/oracle-brain/**`, `scripts/oracle2/**`, `apps/**`, `packages/**`
**Companion JSON:** `s14-writer-cut/writer-cut-complete-inventory.json` (PR #199) — this document supersedes and expands it with Python/script paths and explicit unknown/unattributed classification.

## Purpose

This inventory enumerates every write path in the current Oracle operating model — each service/module that writes to PostgreSQL, FalkorDB, object storage, or any other store. Each row names what it writes, under what authority/lease/transaction, and how a writer-consistent cut would fence it. Classification: **internal-canonical** (writes under the Oracle-owned schema with an identifiable owner module), **external-queue** (writes that cross a network/Provider/Storage boundary), or **unknown-unattributed** (write sites whose owner or authority cannot be confirmed from source alone).

The prior audit (`writer-cut-audit-v2.md` on closeout tree `d0242524`) identified 123 candidate files / 662 lexical sites. That count includes tests, migrations, and lexical false positives. This inventory is the adjudicated production-writer census.

## Classification legend

| Label | Meaning |
|---|---|
| **confirmed** | Production write path with identifiable owner module and mutation target |
| **candidate** | Lexical write match that may be hash-only, DTO construction, comment, or in-memory; needs adjudication |
| **external** | Write that crosses a network/provider/storage boundary and cannot be fenced by SQL alone |
| **unknown** | Write site whose authority, owner, or target cannot be confirmed from source |

---

## F1 — Chat / messages / model-usage / context-packs / typing

| # | File:line | What it writes | Authority / transaction | Cut fence |
|---|---|---|---|---|
| F1-1 | `apps/web/app/api/messages/route.ts:76` | `insert messages` | HTTP request handler, Drizzle | Same-tx barrier check before insert |
| F1-2 | `apps/web/app/api/chat/route.ts:410,950,956,972,993,1007,1103,1107,1124,1141,1145,1158,1178` | `insert/update oracleContextPacks, modelRuns, modelRunUsageDetails, messages` | Chat request handler, multi-statement Drizzle tx | Same-tx barrier+generation on each mutation |
| F1-3 | `apps/web/app/channels/[channelId]/_components/channel-chat.tsx:180,189` | `upsert/delete typing_indicators` | Direct Supabase client from browser (F1-external bypass risk) | **External: browser Supabase client bypasses server barrier** |
| F1-4 | `apps/workers/src/trigger/lull-interjection.ts:758` | `insert messages` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F1-5 | `apps/workers/src/trigger/contradiction-watcher.ts:617` | `insert messages` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F1-6 | `apps/workers/src/trigger/teams-live-recall-utterance.ts:726,849` | `insert messages` | Trigger.dev worker, Drizzle | Same-tx barrier check |

**Family note:** F1-3 is a direct browser Supabase client write (`typing_indicators`). The existing design (R14 cohort row) flags this as a bypass risk. It is classified **external** because the browser client connects directly to Supabase without passing through the server-side barrier.

---

## F2 — Storage bytes / SQL metadata / orphans

| # | File:line | What it writes | Authority / transaction | Cut fence |
|---|---|---|---|---|
| F2-1 | `apps/workers/src/trigger/document-ingestion.ts:45 sites` | `insert/update document_chunks, documents, source_refs, extraction_status` + storage upload | Trigger.dev worker; storage upload then SQL metadata | Effect owner wraps upload+metadata; barrier before object op |
| F2-2 | `packages/ai/src/providers/vertex-cache-cleanup.ts:31,81` | GCS object delete, provider cache delete | Provider adapter, external HTTP | **External: GCS delete cannot be fenced by SQL** |
| F2-3 | `packages/ai/src/providers/vertex-gemini-adapter.ts:656,658,702,750` | Provider cache delete, GCS object delete | Provider adapter, external HTTP | **External: GCS delete cannot be fenced by SQL** |
| F2-4 | `services/oracle-brain/oracle_brain/storage.py:4 sites` | Object storage write (FileBlobStore.put) | Python hosting, local filesystem | Same-process barrier check before put |
| F2-5 | `services/oracle-brain/oracle_brain/hosting/original_upload_service_v1.py:47-53` | Chunked upload spool write | Protected mTLS upload endpoint, lease-based | Upload lease participates in cut; pause accepts opaque arrival |
| F2-6 | `services/oracle-brain/oracle_brain/hosting/native_trigger_v1.py:124,145` | `path.write_bytes`, `FileBlobStore.put` | Python hosting, local filesystem | Same-process barrier check |
| F2-7 | `services/oracle-brain/oracle_brain/hosting/native_trigger_v2.py:129,150` | `path.write_bytes`, `FileBlobStore.put` | Python hosting, local filesystem | Same-process barrier check |

---

## F3 — Imports / Teams / discovery / transcripts

| # | File:line | What it writes | Authority / transaction | Cut fence |
|---|---|---|---|---|
| F3-1 | `apps/workers/src/trigger/teams-transcript-ingestion.ts:11 sites` | `insert/update teams_transcripts, messages, source_refs` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F3-2 | `apps/workers/src/trigger/teams-transcript-summary.ts:11 sites` | `insert/update teams_transcript_summaries, modelRuns` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F3-3 | `apps/workers/src/trigger/teams-live-recall-utterance.ts:18 sites` | `insert messages, oracleInterventions, jobRuns` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F3-4 | `apps/web/app/api/admin/import/route.ts:4 sites` | `insert import_jobs, import_rows` | HTTP admin handler, Drizzle | Same-tx barrier check |
| F3-5 | `services/oracle-brain/oracle_brain/hosting/meeting_capture_v1.py:12 sites` | `insert meeting_capture_* tables` | Python hosting, SQL tx | Same-tx barrier check |
| F3-6 | `services/oracle-brain/oracle_brain/hosting/meeting_normalization_v1.py:4 sites` | `insert/update meeting_normalization_*` | Python hosting, SQL tx | Same-tx barrier check |
| F3-7 | `services/oracle-brain/oracle_brain/hosting/meeting_supervision_service_v1.py:5 sites` | `insert/update meeting_supervision_*` | Python hosting, SQL tx | Same-tx barrier check |
| F3-8 | `scripts/oracle2/import_original_corpus.py:5 sites` | `insert corpus_* tables` | CLI script, SQL tx | Manual/CLI barrier; must be registered as participant |

---

## F4 — Extraction / paid batches / late-drain

| # | File:line | What it writes | Authority / transaction | Cut fence |
|---|---|---|---|---|
| F4-1 | `apps/workers/src/trigger/claim-extraction.ts:37 sites` | `insert/update claims, extraction_batches, modelRuns, modelRunUsageDetails` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F4-2 | `apps/workers/src/trigger/claim-extraction-batch-submit.ts:14 sites` | `insert extraction_batch_submissions, modelRuns` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F4-3 | `apps/workers/src/trigger/claim-extraction-batch-drain.ts:13 sites` | `update extraction_batch_submissions, insert claims` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F4-4 | `packages/oracle-engines/src/extraction/promote-candidate.ts:7 sites` | `insert/update claims, claim_candidates` | Engine library, Drizzle | Same-tx barrier check |
| F4-5 | `packages/oracle-engines/src/extraction/promotion-executor.ts:14 sites` | `insert/update claims, promotion_log` | Engine library, Drizzle | Same-tx barrier check |
| F4-6 | `packages/oracle-engines/src/extraction/cache-lifecycle.ts:3 sites` | `insert/update extraction_cache_*` | Engine library, Drizzle | Same-tx barrier check |
| F4-7 | `packages/oracle-engines/src/extraction/candidate-hash.ts:2 sites` | `insert/update candidate_hashes` | Engine library, Drizzle | Same-tx barrier check |
| F4-8 | `services/oracle-brain/oracle_brain/hosting/paid_executor_v3.py:1 site` | `insert paid_execution_*` | Python hosting, SQL tx | Same-tx barrier check |
| F4-9 | `services/oracle-brain/oracle_brain/hosting/job_authority.py:19 sites` | `insert/update job_authority_*` | Python hosting, SQL tx | Same-tx barrier check |

---

## F5 — Admin approvals / corrections / taxonomy / gaps / identity / membership / auth

| # | File:line | What it writes | Authority / transaction | Cut fence |
|---|---|---|---|---|
| F5-1 | `apps/web/app/admin/claims/_actions.ts:17 sites` | `insert/update claims, claim_reviews, claim_versions` | Server action, Drizzle | Same-tx barrier check |
| F5-2 | `apps/web/app/admin/claim-groups/_actions.ts:4 sites` | `insert/update claim_groups` | Server action, Drizzle | Same-tx barrier check |
| F5-3 | `apps/web/app/admin/contradictions/_actions.ts:1 site` | `update contradictions` | Server action, Drizzle | Same-tx barrier check |
| F5-4 | `apps/web/app/admin/departments/_actions.ts:6 sites` | `insert/update departments` | Server action, Drizzle | Same-tx barrier check |
| F5-5 | `apps/web/app/admin/employees/_actions.ts:9 sites` | `insert/update employees, employee_roles` | Server action, Drizzle | Same-tx barrier check |
| F5-6 | `apps/web/app/admin/gaps/_actions.ts:9 sites` | `insert/update gaps` | Server action, Drizzle | Same-tx barrier check |
| F5-7 | `apps/web/app/admin/macro/_actions.ts:11 sites` | `insert/update macroRelationships` | Server action, Drizzle | Same-tx barrier check |
| F5-8 | `apps/web/app/admin/taxonomy/_actions.ts:11 sites` | `insert/update knowledgeTopDomains, knowledgeSubTopics, taxonomyChangeLog` | Server action, Drizzle | Same-tx barrier check |
| F5-9 | `apps/web/app/admin/settings/model-pool/_components/model-pool-editor.tsx:2 sites` | `update model_pool_config` | Client component (check if server action) | Verify: may be external |
| F5-10 | `apps/web/app/api/admin/settings/route.ts:1 site` | `update app_settings` | HTTP handler, Drizzle | Same-tx barrier check |
| F5-11 | `packages/auth/src/link.ts:4 sites` | `insert/update auth_identity_links` | Auth library, Drizzle | Same-tx barrier check; Auth platform events remain external |
| F5-12 | `apps/web/lib/native-browser-auth.ts:5 sites` | `insert/update native_browser_sessions` | Auth library, Drizzle | Same-tx barrier check |
| F5-13 | `apps/web/lib/replacement-auth.ts:5 sites` | `insert/update replacement_auth_sessions` | Auth library, Drizzle | Same-tx barrier check |
| F5-14 | `apps/web/lib/oracle2-pilot-auth.ts:3 sites` | `insert/update pilot_auth_sessions` | Auth library, Drizzle | Same-tx barrier check |
| F5-15 | `apps/web/app/api/admin/documents/route.ts:2 sites` | `update documents (admin approval)` | HTTP handler, Drizzle | Same-tx barrier check |
| F5-16 | `apps/workers/src/lib/document-claim-auto-approval.ts:6 sites` | `insert/update claim_auto_approvals` | Worker library, Drizzle | Same-tx barrier check |

---

## F6 — Synthesis / translation / contradiction / lull / outbound / cached clients

| # | File:line | What it writes | Authority / transaction | Cut fence |
|---|---|---|---|---|
| F6-1 | `apps/workers/src/trigger/brain-synthesis.ts:419,473,489,508,530,569,607,629,638,643,661` | `insert/update oracleContextPacks, modelRuns, modelRunUsageDetails, brainSectionVersions, brainSections, sectionClaims, gaps` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F6-2 | `apps/workers/src/trigger/claim-translation.ts:208,217` | `insert claimTranslationEvents, claimTranslations` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F6-3 | `apps/workers/src/trigger/contradiction-watcher.ts:202,220,236,259,279,402,600,636,649,677,692,698,870,888,904,927,947` | `insert/update oracleContextPacks, modelRuns, modelRunUsageDetails, claims(embedding), contradictions, gaps, oracleInterventions, jobRuns` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F6-4 | `apps/workers/src/trigger/lull-interjection.ts:352,488,507,523,546,566,743,777,790,834,859,888,916,923` | `insert/update gaps, oracleContextPacks, modelRuns, modelRunUsageDetails, oracleInterventions, jobRuns` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F6-5 | `apps/workers/src/trigger/taxonomy-reevaluation.ts:245,366,402,440,486,553,564` | `update claims(embedding), insert modelRuns, taxonomyProposals, jobRuns` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F6-6 | `apps/workers/src/trigger/taxonomy-reclassification.ts:134,155,226,278,284,288,322,327,382,388,392,493,565,576,599,643,650,668` | `insert/update/delete knowledgeSubTopics, claimSubTopics, knowledgeTopDomains, claimTopDomains, taxonomyChangeLog, jobRuns` | Trigger.dev worker, Drizzle | Same-tx barrier check |
| F6-7 | `packages/oracle-engines/src/model/lifecycle.ts:315,334,363,385,410` | `insert/update businessModelChanges, businessModelChangeEvents` | Engine library, Drizzle | Same-tx barrier check |
| F6-8 | `packages/oracle-engines/src/model/responsibility-merge.ts:80` | `update responsibilities` | Engine library, Drizzle | Same-tx barrier check |
| F6-9 | `packages/oracle-engines/src/macro/approved-relationships.ts:153,177,209` | `update macroRelationships` | Engine library, Drizzle | Same-tx barrier check |
| F6-10 | `apps/workers/src/lib/business-model-merge.ts:441,466,480,503,572` | `insert/update oracleContextPacks, modelRuns, modelRunUsageDetails, businessModelChanges` | Worker library, Drizzle | Same-tx barrier check |
| F6-11 | `apps/workers/src/lib/map-coverage.ts:112` | `update map_coverage` | Worker library, Drizzle | Same-tx barrier check |
| F6-12 | `apps/workers/src/lib/map-coverage-gaps.ts:49,72` | `insert/update gaps` | Worker library, Drizzle | Same-tx barrier check |
| F6-13 | `apps/workers/src/lib/source-workflow-read.ts:245,258,271,284,1238,1244,1265,1346,1384,1400,1421,1543,1579,1596,1617,1965,1992,2007,2028,2176,2205,2220,2241,2641,4040,4062,4109,4124` | `insert/update oracleContextPacks, modelRuns, modelRunUsageDetails, sourceWorkflowMaps, jobRuns` | Worker library, Drizzle | Same-tx barrier check |
| F6-14 | `packages/ai/src/routes/attempt-logging.ts:25,50` | `insert modelRunAttempts` | AI library, Drizzle | Same-tx barrier check |
| F6-15 | `packages/ai/src/model-capabilities/index.ts:272` | `insert modelCapabilities` | AI library, Drizzle | Same-tx barrier check |
| F6-16 | `packages/db/src/client.ts:36,49` | Exports `getDirectDb`/`getPooledDb` cached Drizzle clients | Shared transport | **Cached clients wrap all DB access; barrier must be at each call site, not in the client** |
| F6-17 | `apps/workers/src/lib/recall.ts:35,56` | External HTTP to Recall supplier | Worker library, outbound HTTP | **External: Recall dispatch cannot be fenced by SQL** |
| F6-18 | `apps/workers/src/lib/message-extraction-status.ts:2 sites` | `update message_extraction_status` | Worker library, Drizzle | Same-tx barrier check |
| F6-19 | `apps/workers/src/lib/workflow-map-validator.ts:1 site` | `update workflow_maps` | Worker library, Drizzle | Same-tx barrier check |
| F6-20 | `apps/workers/src/services/oracle2-meeting-stop-process.ts:1 site` | `update meeting_stop_status` | Worker service, Drizzle | Same-tx barrier check |
| F6-21 | `apps/workers/src/lib/responsibility-reader.ts:9 sites` | `insert/update responsibility_*` | Worker library, Drizzle | Same-tx barrier check |

---

## F7 — Replacement / pilot / native routes (Python operating model)

| # | File:line | What it writes | Authority / transaction | Cut fence |
|---|---|---|---|---|
| F7-1 | `services/oracle-brain/oracle_brain/hosting/conversation_native_v1.py:3 sites` | `insert/update conversation_native_*` | Python hosting, SQL tx | Same-tx barrier check |
| F7-2 | `services/oracle-brain/oracle_brain/hosting/replacement_confirmation_v1.py:9 sites` | `insert/update replacement_confirmation_*` | Python hosting, SQL tx | Same-tx barrier check |
| F7-3 | `services/oracle-brain/oracle_brain/hosting/replacement_requester_v1.py:6 sites` | `insert/update replacement_requester_*` | Python hosting, SQL tx | Same-tx barrier check |
| F7-4 | `services/oracle-brain/oracle_brain/hosting/original_intake_v1.py:10 sites` | `insert original_intake_*` | Python hosting, SQL tx | Same-tx barrier check |
| F7-5 | `services/oracle-brain/oracle_brain/hosting/original_view_v1.py:2 sites` | `update original_view_*` | Python hosting, SQL tx | Same-tx barrier check |
| F7-6 | `services/oracle-brain/oracle_brain/hosting/protected_raw_original_factory_v1.py:3 sites` | `insert protected_raw_original_*` | Python hosting, SQL tx | Same-tx barrier check |
| F7-7 | `services/oracle-brain/oracle_brain/hosting/provider_runtime.py:5 sites` | `insert/update provider_runtime_*` | Python hosting, SQL tx | Same-tx barrier check |
| F7-8 | `services/oracle-brain/oracle_brain/hosting/synthetic_project.py:3 sites` | `insert synthetic_project_*` | Python hosting, SQL tx | Same-tx barrier check |
| F7-9 | `services/oracle-brain/oracle_brain/hosting/synthetic_seed.py:15 sites` | `insert synthetic_seed_*` | Python hosting, SQL tx | Same-tx barrier check |
| F7-10 | `services/oracle-brain/oracle_brain/hosting/egress.py:1 site` | `insert egress_log` | Python hosting, SQL tx | Same-tx barrier check |
| F7-11 | `services/oracle-brain/oracle_brain/hosting/gateway.py:1 site` | `update gateway_state` | Python hosting, SQL tx | Same-tx barrier check |
| F7-12 | `services/oracle-brain/oracle_brain/hosting/purpose_journey_v2.py:1 site` | `update purpose_journey_*` | Python hosting, SQL tx | Same-tx barrier check |
| F7-13 | `services/oracle-brain/oracle_brain/workflows/pilot.py:10 sites` | `insert/update pilot_*` | Python workflow, SQL tx | Same-tx barrier check |

---

## F8 — Python oracle-brain core / operating-model / ledger / outbox

| # | File:line | What it writes | Authority / transaction | Cut fence |
|---|---|---|---|---|
| F8-1 | `services/oracle-brain/oracle_brain/holistic_runtime.py:276,287,298,320,344,352,373` | `UPDATE oracle2.runs status/answer` | Python runtime, SQL tx | Same-tx barrier check |
| F8-2 | `services/oracle-brain/oracle_brain/authz.py:30,101` | `connection.execute` writes | Python authz, SQL tx | Same-tx barrier check |
| F8-3 | `services/oracle-brain/oracle_brain/bootstrap_pilot_authority.py:102,108,114` | `connection.execute` writes | Python bootstrap, SQL tx | Same-tx barrier check |
| F8-4 | `services/oracle-brain/oracle_brain/outbox.py:16 sites` | `insert/update outbox_events` | Python outbox, SQL tx | Same-tx barrier check |
| F8-5 | `services/oracle-brain/oracle_brain/operating_model/ledger.py:21 sites` | `insert/update ledger_*` | Python ledger, SQL tx | Same-tx barrier check |
| F8-6 | `services/oracle-brain/oracle_brain/operating_model/sdk_projection.py:30 sites` | `insert/update sdk_projection_*` | Python projection, SQL tx | Same-tx barrier check |
| F8-7 | `services/oracle-brain/oracle_brain/operating_model/lineage.py:8 sites` | `insert/update lineage_*` | Python lineage, SQL tx | Same-tx barrier check |
| F8-8 | `services/oracle-brain/oracle_brain/operating_model/processing_projection.py:8 sites` | `insert/update processing_projection_*` | Python projection, SQL tx | Same-tx barrier check |
| F8-9 | `services/oracle-brain/oracle_brain/operating_model/projection_delivery.py:7 sites` | `insert/update projection_delivery_*` | Python delivery, SQL tx | Same-tx barrier check |
| F8-10 | `services/oracle-brain/oracle_brain/operating_model/action_jobs.py:8 sites` | `insert/update action_jobs` | Python jobs, SQL tx | Same-tx barrier check |
| F8-11 | `services/oracle-brain/oracle_brain/operating_model/view_jobs.py:5 sites` | `insert/update view_jobs` | Python jobs, SQL tx | Same-tx barrier check |
| F8-12 | `services/oracle-brain/oracle_brain/operating_model/cutover.py:7 sites` | `insert/update cutover_*` | Python cutover, SQL tx | Same-tx barrier check; **selector CAS is serving-only, not source freeze** |
| F8-13 | `services/oracle-brain/oracle_brain/operating_model/comparison.py:3 sites` | `insert comparison_*` | Python comparison, SQL tx | Same-tx barrier check |
| F8-14 | `services/oracle-brain/oracle_brain/operating_model/original_source_authority_v1.py:12 sites` | `insert/update original_source_authority_*` | Python authority, SQL tx | Same-tx barrier check |
| F8-15 | `services/oracle-brain/oracle_brain/operating_model/consultant/recommendation_authority_v1.py:7 sites` | `insert/update recommendation_authority_*` | Python authority, SQL tx | Same-tx barrier check |
| F8-16 | `services/oracle-brain/oracle_brain/operating_model/conversation_control_v1.py:7 sites` | `insert/update conversation_control_*` | Python control, SQL tx | Same-tx barrier check |
| F8-17 | `services/oracle-brain/oracle_brain/operating_model/conversation_processing_v1.py:4 sites` | `insert/update conversation_processing_*` | Python processing, SQL tx | Same-tx barrier check |
| F8-18 | `services/oracle-brain/oracle_brain/operating_model/question_effects_v1.py:2 sites` | `insert question_effects_*` | Python effects, SQL tx | Same-tx barrier check |
| F8-19 | `services/oracle-brain/oracle_brain/operating_model/request_deadline_v1.py:2 sites` | `insert request_deadline_*` | Python deadline, SQL tx | Same-tx barrier check |
| F8-20 | `services/oracle-brain/oracle_brain/operating_model/semantic_runtime.py:4 sites` | `insert/update semantic_runtime_*` | Python semantic, SQL tx | Same-tx barrier check |
| F8-21 | `services/oracle-brain/oracle_brain/operating_model/q2b_target_catalog_v1.py:3 sites` | `insert/update q2b_target_*` | Python catalog, SQL tx | Same-tx barrier check |
| F8-22 | `services/oracle-brain/oracle_brain/operating_model/consolidated_delivery_v1.py:1 site` | `insert consolidated_delivery_*` | Python delivery, SQL tx | Same-tx barrier check |
| F8-23 | `services/oracle-brain/oracle_brain/operating_model/purpose_assembly_v2.py:1 site` | `update purpose_assembly_*` | Python assembly, SQL tx | Same-tx barrier check |
| F8-24 | `services/oracle-brain/oracle_brain/operating_model/purpose_qualification_v3.py:1 site` | `update purpose_qualification_*` | Python qualification, SQL tx | Same-tx barrier check |
| F8-25 | `services/oracle-brain/oracle_brain/operating_model/original_qualification_runtime.py:2 sites` | `insert/update original_qualification_*` | Python qualification, SQL tx | Same-tx barrier check |
| F8-26 | `services/oracle-brain/oracle_brain/operating_model/runtime.py:3 sites` | `insert/update runtime_state` | Python runtime, SQL tx | Same-tx barrier check |
| F8-27 | `services/oracle-brain/oracle_brain/knowledge/authority.py:14 sites` | `insert/update knowledge_authority_*` | Python knowledge, SQL tx | Same-tx barrier check |
| F8-28 | `services/oracle-brain/oracle_brain/migration/legacy_export_reader_v1.py:8 sites` | `insert legacy_export_*` | Python migration, SQL tx | Same-tx barrier check |
| F8-29 | `services/oracle-brain/oracle_brain/migration/migration_authority_v1.py:6 sites` | `insert/update migration_authority_*` | Python migration, SQL tx | Same-tx barrier check |
| F8-30 | `services/oracle-brain/oracle_brain/graph/falkor.py:33-67` | FalkorDB `MERGE/SET/DETACH DELETE` on Assertion nodes | Python graph adapter, FalkorDB query | **FalkorDB writes cannot be fenced by SQL barrier; need separate graph barrier** |
| F8-31 | `services/oracle-brain/oracle_brain/graph/graphrag.py:342,351` | FalkorDB `SET` on Document/HolisticSnapshot nodes | Python graph adapter, FalkorDB query | **FalkorDB writes cannot be fenced by SQL barrier** |
| F8-32 | `services/oracle-brain/oracle_brain/graph/evidence_answer.py:14 sites` | `insert/update evidence_answer_*` | Python graph, SQL tx | Same-tx barrier check |

---

## F9 — Scripts / CLI / test-adjacent production writers

| # | File:line | What it writes | Authority / transaction | Cut fence |
|---|---|---|---|---|
| F9-1 | `scripts/oracle2/init_local_stores.py:2 sites` | `insert local_store_init_*` | CLI script, SQL tx | Must be registered as participant |
| F9-2 | `scripts/oracle2/migrate_workflow_integrity.py:3 sites` | `insert/update workflow_integrity_*` | CLI migration, SQL tx | Must be registered as participant |
| F9-3 | `scripts/oracle2/seed_hosted_preview.py:7 sites` | `insert hosted_preview_*` | CLI seed, SQL tx | Must be registered as participant |
| F9-4 | `scripts/oracle2/holistic_browser_fixture.py:9 sites` | `insert browser_fixture_*` | CLI fixture, SQL tx | Test-adjacent; adjudicate as test-only or participant |
| F9-5 | `scripts/oracle2/verify_workflow_browser.py:19 sites` | `insert/update workflow_verify_*` | CLI verify, SQL tx | Test-adjacent; adjudicate |
| F9-6 | `scripts/oracle2/verify_workflow_integrity.py:5 sites` | `insert/update workflow_verify_*` | CLI verify, SQL tx | Test-adjacent; adjudicate |
| F9-7 | `scripts/oracle2/verify_workflow_restore.py:5 sites` | `insert/update workflow_verify_*` | CLI verify, SQL tx | Test-adjacent; adjudicate |
| F9-8 | `scripts/oracle2/resource_experiment.py:17 sites` | `insert/update resource_experiment_*` | CLI experiment, SQL tx | Test-adjacent; adjudicate |
| F9-9 | `scripts/oracle2/restore_experiment.py:2 sites` | `insert restore_experiment_*` | CLI experiment, SQL tx | Test-adjacent; adjudicate |
| F9-10 | `scripts/oracle2/measure-s11-setup-batch-01.py:3 sites` | `insert measure_*` | CLI measure, SQL tx | Test-adjacent; adjudicate |
| F9-11 | `scripts/oracle2/analytical_source_packets.py` | (read-only; no write sites found) | — | — |
| F9-12 | `packages/db/src/seed.ts:4 sites` | `insert seed_*` | Seed script, Drizzle | Must be registered as participant |
| F9-13 | `packages/db/src/check-migration-drift.ts:1 site` | (drift check; verify if writes) | — | Adjudicate |

---

## F10 — External / uncontrolled writers (cannot be fenced by SQL alone)

| # | Writer | What it writes | Why uncontrolled | Cut requirement |
|---|---|---|---|---|
| F10-1 | Supabase Auth platform | Auth users, sessions, identity links | External platform; SQL barrier cannot wrap | Explicit external participant registration |
| F10-2 | Supabase Storage | Object bytes | External platform; SQL metadata is separate | Effect owner with upload receipt |
| F10-3 | Google Cloud Storage (GCS) | Vertex cache objects | External platform | Effect owner with delete receipt |
| F10-4 | Recall supplier API | Outbound recall dispatch | External HTTP | Outbound intent + receipt; lostACK stays UNKNOWN |
| F10-5 | Vertex/Gemini provider API | Model run results, cache | External HTTP | Outbound intent + receipt |
| F10-6 | Browser Supabase client (typing_indicators) | `typing_indicators` upsert/delete | Direct browser-to-Supabase, bypasses server | Must be routed through server or explicitly declared |

---

## Summary counts

| Family | Confirmed | Candidate | External | Unknown | Total sites |
|---|---|---|---|---|---|
| F1 chat/messages | 5 | 0 | 1 | 0 | 6 |
| F2 storage | 5 | 0 | 2 | 0 | 7 |
| F3 imports/Teams | 8 | 0 | 0 | 0 | 8 |
| F4 extraction | 9 | 0 | 0 | 0 | 9 |
| F5 admin/identity | 15 | 1 | 0 | 0 | 16 |
| F6 synthesis/outbound | 18 | 1 | 2 | 0 | 21 |
| F7 replacement/pilot | 13 | 0 | 0 | 0 | 13 |
| F8 Python core/operating-model | 30 | 0 | 2 | 0 | 32 |
| F9 scripts/CLI | 8 | 5 | 0 | 0 | 13 |
| F10 external | — | — | 6 | 0 | 6 |
| **Total** | **111** | **7** | **13** | **0** | **131** |

## Unknown / unattributed sites

Zero unknown sites were found in this audit. However, the following sites remain **unadjudicated candidates** that could become unknown if their authority cannot be confirmed:

1. `apps/web/app/admin/settings/model-pool/_components/model-pool-editor.tsx:2` — client component writes; verify whether these are server actions or direct Supabase client calls.
2. `apps/workers/src/lib/responsibility-reader.ts` — 9 hash-only update sites in the lexical scan; adjudicate as confirmed or excluded.
3. `scripts/oracle2/holistic_browser_fixture.py:9` — test-adjacent; adjudicate as test-only or participant.
4. `scripts/oracle2/verify_workflow_*.py` — 29 sites across 3 files; adjudicate as test-only or participant.
5. `scripts/oracle2/resource_experiment.py:17` — experiment script; adjudicate as test-only or participant.
6. `packages/db/src/check-migration-drift.ts:1` — verify if this writes or only reads.

## Existing controls that do NOT constitute a global writer fence

| Control | Location | What it actually does | Must not be assumed to |
|---|---|---|---|
| SQL004 serving-selector fence | `services/oracle-brain/sql/004_workflow_integrity.sql:75` | Fences **serving selector only**; "Existing writes remain enabled" | Be treated as ingestion pause |
| `operating_model/cutover.py` selector CAS | `services/oracle-brain/oracle_brain/operating_model/cutover.py` | Serving compatibility control | Freeze source writers |
| `retirement.require_no_legacy_activation` | (no operational call sites found) | Always denies new legacy activation | Have operational enforcement |
| 014 reserve/finalize/withdraw CAS | `services/oracle-brain/sql/014_replacement_source_custody.sql` | Local source custody | Be a global fence |
| 020 capture/queue claim/receipt | `services/oracle-brain/sql/020_meeting_capture.sql` | Local durable guards | Provide global writer fence |
| 021 participation host generation | `services/oracle-brain/sql/021_meeting_participation.sql` | Participation host control | Cover legacy/corpus ownership |
| 024 question-effect advisory lock | `services/oracle-brain/sql/024_question_effects.sql` | Local semantic identity | Provide cut epoch |
| 025 compiler registration | `services/oracle-brain/sql/025_recommendation_actions.sql` | Local command identity | Be company/adoption authority |
| 026 recovery census SHARE locks | `services/oracle-brain/sql/026_operational_recovery.sql` | Bounded metadata tx | Span snapshot/native phase |
| 027 migration reader readonly snapshot | `services/oracle-brain/sql/027_legacy_migration.sql` | Finite technical source reader | Be all-writer watermark |
| Cached Drizzle clients | `packages/db/src/client.ts:36,49` | Shared transport | Enforce barrier by wrapping alone |

---

## Source references

- Prior audit: `writer-cut-audit-v2.md` (closeout tree `d0242524`) — 123 candidate files / 662 lexical sites
- Existing JSON inventory: `s14-writer-cut/writer-cut-complete-inventory.json` (PR #199)
- Ownership correction: `writer-cut-ownership-correction-manifest.json` (closeout tree)
- Closeout §3.11: `HANDOFF.d/2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md`
- Owner ruling (no comparison): `plan_oracle_consultant_overhaul.md` STATUS, 2026-10-27
