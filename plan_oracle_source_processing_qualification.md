# Oracle original-processing qualification and generated-truth separation

## STATUS — read first

Updated October 15, 2026, 9:16 PM EDT. Owner: parent #24 adopting Codex coordinator; work stays on existing [S03 #27](https://github.com/u2giants/theoracle/issues/27) under [#24](https://github.com/u2giants/theoracle/issues/24). This is an UNIMPLEMENTED architecture plan. Independent review is evidence for the coordinator decision, never implementation/SQL/apply/issuance/provider authority. No private originals, grants, database writes, provider dispatch or production action occurred.

| Step | State | Gate and evidence |
|---|---|---|
| Q0 source boundary audit | Source inspected; no live claim | §5–6 immutable source references |
| Q1 architecture review and exact scope | Open | Assigned exact-head independent review plus coordinator architecture decision, receipt on #27 |
| Q2 owner/caller prerequisite qualification | Open; current actual owner UNKNOWN | §9.1 owner/caller proof before source implementation |
| Q3 additive SQL and connection-aware resolver | Open; not started | §9.2–3 actual-role denial tests, no production apply |
| Q4 processing broker/compiled-artifact/executor chain | Open; not started | §9.4–5 typed admitted actor/purpose/source chain |
| Q5 local adversarial qualification | Open; not started | §10 concrete named role/TLS/race tests |
| Q6 shipment and separately admitted public invented live proof | Open; not authorized by this plan | §13 exact release/target/action and retained live checklist on #27 |

A fresh session starts at Q1 and Q2; it must not implement until the coordinator accepts the final reviewed architecture and exact source scope. Read both parent plan STATUS sections. Re-read all downstream Q steps at every phase boundary; preserve the S03→S16 and W01→W12 acceptance obligations.

Single coordination baton: [replacement handoff](https://github.com/u2giants/theoracle/blob/codex/oracle-replacement-holistic-plan/HANDOFF.d/2026-10-16T0101Z-edge-dev3-codex-replacement-coordination.md), initially unpublished pending its owning session's push. That session owns the reciprocal handoff link; this lane creates no second baton. [Documentary-journey plan](https://github.com/u2giants/theoracle/blob/codex/oracle-replacement-holistic-plan/plan_oracle_replacement_documentary_journey.md) owns E-public runtime admission; this plan owns the source-processing permission prerequisite only.

## 1. Ultimate goal

Oracle must generate better connected knowledge from permitted original documents without asking employees to approve the defective old claims first. Original-reading completeness, permission to process an original and confirmation of a newly generated business interpretation are separate facts. The replacement preserves conflicts, unknowns, history and evidence instead of inheriting false truth.

If a step conflicts with this goal, the goal wins — stop and flag it to the coordinator. No step authorizes reviewing discarded-system claims, contacting Ilona/Jessica or other employees, renewing spent authority, or claiming business acceptance from invented-data proof.

## 2. Application and environment

Repository [u2giants/theoracle](https://github.com/u2giants/theoracle), landing branch main, source audit base `97da85b630e79e1bc01ae02fd177cf15f8b8ebed`. Oracle is POP Creations' evidence-backed company consultant. Retained app uses Next.js/Vercel, TypeScript workers/Trigger.dev and Supabase; isolated replacement uses Python operating-model contracts, dedicated PostgreSQL ledger and rebuildable FalkorDB/GraphRAG projection. Public retained site is [oracle.designflow.app](https://oracle.designflow.app); availability is not replacement acceptance. New schema here is the dedicated Oracle-native ledger under `services/oracle-brain/sql`, not POP shared-db or retained Drizzle schema. No actual target or platform action is selected by this document.

## 3. Trigger and reproduction

Albert's current chat correction: “Obviously we shouldn't be asking ilona and Jessica to review claims made using the current faulty logic. The whole idea of this refactor is to generate better claims with more holistic / big-picture knowledge. why would we want to test the claims of the system we are discarding?”

The coordinator found that `PostgresSources.current` and SQL role policy require a confirmed interpreted draft before reading a qualified original. A preview seeded with confirmed draft data bypasses the missing new-generation journey. Reproduction is source-based: create an isolated SQL001..010 database with one sealed original/metadata, current actual fixed source role and a draft-status interpreted row; ordinary `current()` denies it. A Python-only processing method still cannot read the original because source_blocks RLS independently calls SQL008's confirmed-draft helper. No new live reproduction is claimed.

## 4. Scope

IN: reviewed architecture for an additive exact-source processing capability, original qualification separate generated truth, immutable actor/role/source/purpose bindings, metadata-only downstream validation, connection-safe revocation checks, explicit new scope semantics, negative tests and staged admission boundaries.

NOT IN THIS PLAN: implementation before Q1/Q2; any SQL/data execution, grants/credentials/roles/certificates issuance, private data, provider/model/embedding calls or spending, employee questions/reports/grading, old-system claim evaluation, generalized role refactoring, broad original visibility, ordinary confirmed-serving changes, table creation, production changes, host/Ansible edits, migrations in POP shared-db, or S04–S16 closure. No deletion of existing confirmation checks, no admin/synthetic fallback and no promotion of generated reported content to confirmed policy.

## 5. Current code and proven source facts

All source references in this section are at audit base [97da85b](https://github.com/u2giants/theoracle/tree/97da85b630e79e1bc01ae02fd177cf15f8b8ebed). They are inspected code, not assertions about an installed database.

| Source | Exact current behavior |
|---|---|
| `services/oracle-brain/oracle_brain/operating_model/authority_adapter.py:15-67` | `_check` enforces fixed binding; `current` joins drafts and requires confirmed; validates reading/provenance to SourceReceipt. `can_read` checks only read scope on its own connection. |
| `services/oracle-brain/sql/007_hosting_candidate_permissions.sql:25-47` | Installs source_blocks SELECT policy calling hosting_source_visible for existing three source-role groups. |
| `services/oracle-brain/sql/008_hosting_runtime_permissions.sql:10-48` | REPLACES that helper; session-role/runtime/admission/source/metadata/hash checks plus exactly one confirmed draft and rooted read lineage. Uses actual clock for role/source admission and SQL read lineage. |
| `services/oracle-brain/sql/008_hosting_runtime_permissions.sql:226-235` | Binding function returns current self-role runtime/registry/expiry; does not expose actor identity. |
| `services/oracle-brain/sql/002_pilot.sql:2-33` | sources.status permits processing/draft/confirmed/error; withdrawal lives drafts.status=withdrawn. |
| `services/oracle-brain/oracle_brain/knowledge/authority.py:79-114` | confirm_draft requires process-map scope and current confirm appointment; mutates interpreted draft/review event. Preserve unchanged. |
| `services/oracle-brain/oracle_brain/operating_model/source_binding.py:21-44` | Non-bypass role, externally sealed runtime/registry, verified ledger TLS and actual expiry checks. Does not alone authenticate transport caller. |
| `services/oracle-brain/oracle_brain/operating_model/ledger.py:41-47,128-145` | Reauthorizes refs; persist takes workspace authz lock then calls resolver callbacks, so separately connected callbacks cannot reacquire that lock. |
| `services/oracle-brain/oracle_brain/hosting/provider_runtime.py:154-185` | Broker metadata authorization independently requires current source/draft confirmation. A raw reader change alone cannot enable new dispatch. |
| `services/oracle-brain/oracle_brain/hosting/job_authority.py:115-190` | Immutable documentary job resolves actor, release, artifact population, source pins and confirmed-draft condition. No existing processing-job actor route is established. |
| `services/oracle-brain/oracle_brain/hosting/gateway.py:197-200` | Exact single peer worker URI SAN and HMAC required. |
| `services/oracle-brain/oracle_brain/hosting/custody.py:39-61` | Sealed worker/runtime/release registry; allowed job scopes are documentary-view/finding-review/semantic-verification. It does NOT already admit processing jobs. |
| `services/oracle-brain/oracle_brain/hosting/runtime.py:48-89` | Exact protected operator settings, verified ledger TLS, fixed worker identity, startup source-role binding. No qualified private embedding factory. |

Current actual-target SQL helper owner is UNKNOWN: migrations use CREATE OR REPLACE FUNCTION without OWNER TO, so actual owner derives from the applying identity. No database inspection occurred in this lane. A trusted processing caller/actor provenance chain is also NOT implemented/qualified merely because documentary gateway mTLS exists. Defining that source contract is coordinator-owned code/design work after accepted architecture, not an external wait. Actual owner/target qualification gates installation, not safe source fixture work.

## 6. Findings and policy evidence

`plan_oracle_consultant_overhaul.md:996-997`: “Signed confirmations establish source-reading completeness only, never business truth.” `plan_oracle_workflow_integrity.md:976-979`: “Distinguish reported instructions, confirmed policy, derived structural checks and measured activity” and “source confirmation alone does not grant workflow policy authority.” These are governing semantic boundaries, not permission to replay historical company processing.

The confirmed interpreted draft is wrongly overloaded as permission to obtain a previously qualified original. Original-reading permission may safely be separate only when bounded by exact source-role admissions, original provenance and explicit processing purpose. Hash equality is not permission. Existing `source-extraction` provider purpose is not an issued `source-extraction:<UUID>` appointment. Existing `_has_authority_conn` Python check uses transaction-start now(); SQL008 uses actual clock. New checks must not regress that stronger SQL behavior.

Withdrawal preservation is critical: ignoring drafts entirely would ignore the existing withdrawn marker because sources has no withdrawn status. New getters may accept exactly one draft OR confirmed availability row, but never withdrawn/missing/ambiguous, and must not use interpreted contents as truth. Actual original custody remains separately qualified; original hash in a receipt is not a fresh original-byte rehash.

## 7. Rejected approaches

- Seed old interpreted drafts as confirmed to make generation run: manufactures truth acceptance and skips the desired journey.
- Remove current()/confirm_draft/ordinary RLS confirmation checks: weakens existing serving and policy authority.
- Python-only new method ignoring RLS: actual fixed roles still see no original; an admin fallback would bypass the safety boundary.
- Broaden source_blocks policy to all raw originals for executor: unnecessary raw capability; metadata is sufficient for current identity checks on sealed derived output.
- Reuse provider-purpose text as an automatically existing appointment: unsupported new authority/issuance.
- Trust supplied principal/root or transport mTLS alone: role admissions and immutable actor context must agree; a peer identity is not every user's delegation.
- Acquire workspace advisory lock on a second connection inside Ledger.persist callbacks: self-deadlock. Shared processing validation must use caller-owned connection.
- Treat unknown SQL owner, peer wiring, private authority or architecture review as already qualified: fail closed at Q2, with coordinator ownership.

## 8. Decisions and exact boundary contract

Locked by coordinator direction October 15, 2026, 9:16 PM EDT: preserve ordinary confirmed serving and reported/confirmed distinctions; additive purpose-specific capability only; no new tables or admin fallback; no actual action authority. Architecture implementation remains OPEN pending independent review and coordinator decision. Exact processing scope name is proposed here, not issued.

## Minimal dedicated-ledger migration proposal

Proposed new canonical migration: `services/oracle-brain/sql/011_hosting_source_processing_permissions.sql`, additive and specific to the NEW dedicated Oracle ledger. Reuse existing tables `hosting_role_source_admissions`, `hosting_role_runtime_admissions`, `appointments`, `sources`, `source_blocks`, `operating_model_source_receipts`. No new table, generated Drizzle file, existing policy/helper replacement, broad table SELECT, PUBLIC grant, role creation, grant issuance or production apply.

Add a narrowly scoped raw getter, proposed `oracle2.hosting_processing_source_receipt(workspace, source, principal, expected_runtime_hash, expected_registry_hash)`. EXECUTE only for the existing source-reader and candidate-compiler groups. Never grant it to documentary-executor or gateway metadata. It returns ONLY the exact admitted original normalized reading and its original-metadata plus SourceRef tuple; never generated drafts or interpreted claims.

Add a separate metadata-only getter, proposed `oracle2.hosting_current_source_identity(...)`, for the existing documentary executor (and reader/compiler if needed). Return only SourceRef identity/revision and availability, no reading/metadata text or original locations. Require source-read authority, exact session/principal/runtime/source pins, current original seal and source availability. This permits validity checking of sealed reported generated artifacts without confirming the old process-map draft. It grants no policy-confirmation authority. Do not relabel generated findings confirmed.

Use fixed `SECURITY DEFINER` owners exactly matching the existing reviewed migration owner; verify that owner is the trusted dedicated-ledger schema owner, cannot be assumed by application login roles, has a fixed `search_path=pg_catalog,oracle2`, fully qualified tables, no dynamic SQL, and no write capability exposed by either function. Revoke PUBLIC EXECUTE explicitly. Check effective application-role EXECUTE denies raw getter to executor/gateway. No setter, role parameter or arbitrary SQL argument is accepted. A private owner-only shared helper may avoid copying SQL008's provenance/lineage validation; do not expose an argument that lets an app choose a weaker purpose.

Each getter must bind SESSION_USER to one exact role/source/revision admission; require its principal_id equals the authenticated actor from the pinned runtime/job context, not caller-supplied root identity. Runtime and source admission hashes must equal externally sealed SourceRoleBinding startup pins and be unexpired under clock_timestamp(). Refuse missing, duplicate, conflicting or cross-workspace rows, mismatched roles/runtime/registry/principal and unexpected memberships. Source state must be draft/confirmed, never missing/error/processing. Current SQL002 sources.status has NO withdrawn value; drafts.status carries the existing withdrawal marker. Therefore require exactly one linked draft with status draft OR confirmed, deny withdrawn/missing/ambiguous draft, and never inspect/approve its interpreted contents. This preserves existing withdrawal without demanding faulty generated-claim confirmation. Existing confirmed-serving helpers remain untouched.

Require exactly one original and one original-metadata row; strict ReadingProvenance key/types/limits; reading SHA matches metadata AND exact source-role admission; original SHA/parser/revision agree with all sealed admissions and any existing operating_model_source_receipts. Original SHA is an admitted source identity, not independent rehash of inaccessible original bytes: previously qualified custody/reading provenance remains mandatory. Never infer permission from equal hashes.

## Scope semantics and provisioning

`source-read:<source UUID>` is existing appointment authority. Proposed `source-extraction:<source UUID>` is NEW appointment semantics: the current source-extraction strings are provider purposes, not previously established source-processing grants. Declare it as permission to transform this one qualified original into REPORTED candidates, with no confirm, external message, meeting join, serving, spending or provider admission authority. The raw processing getter requires BOTH independently checked current owner-rooted read and extraction lineages; a genuine owner-root appointment retains the existing all-scope semantics. Every parent must remain current in the same workspace. No wildcard grants, implied renewal, inferred scope or runtime self-issuance.

Future issuance must use the existing reviewed external owner-rooted delegation route, least-privilege exact actor/source/expiry and immutable receipts. App administrators and candidate compiler cannot appoint root or self-grant. The TypeScript pilot delegate only accepts review/confirm and must not be silently widened. No grants are issued by this plan/migration. Provider/key/spending/purpose/census admission remains independent, unchanged and currently unproven.

## Reader, compiler, executor and broker call chain

1. Reader: `_check` fixed SourceRoleBinding before and after each operation; verified TLS with sslmode=verify-full. Processing raw getter pins exact session principal and both scopes before bytes leave the database. Transport peer/caller must originate in the existing independently admitted immutable runtime/job/certificate context, not a request field. SourceRoleBinding alone pins registry, not the HTTP caller; retain existing mTLS/job authority and require actor equality.
2. Compiler: accepts exact typed SourceReceipt and immutable expected SourceRef from the admitted reader; validates original/hash/provenance/revision, all quote spans and generated REPORTED state. Recheck both scopes and current source pins before dispatch and before persistence. Retain raw complete failed output privately. No generated interpretation can qualify its own original or promote itself.
3. Executor: use metadata-only current-identity checks on the exact manifest source population, plus existing immutable release/job/actor/read permissions and sealed artifact content/dependencies. Validate reported artifacts and their source identities without copying whole originals into the executor. Existing `current()`/`confirm_draft()` and ordinary confirmed-serving path remain unchanged. This requires an explicit generated-ledger resolver path; do not replace SourceReceipt with unchecked metadata in generic `Ledger.read()`.
4. Broker: `hosting/provider_runtime.py:authorize` currently independently checks confirmed drafts, so raw-reader changes alone do NOT enable native dispatch. Add an explicitly bounded processing-job authorization branch using the same exact-role metadata-only processing guard for fixed source-extraction jobs, preserving all provider/budget/registry/TLS peer checks. Its immutable job context must bind principal/source tuple/purpose/runtime; no boolean client flag. Documentary serving `hosting/job_authority.py` also checks confirmed drafts; new reported-artifact flow needs the metadata-only identity path, never deletion of the existing gate.

## Race and connection requirements

Do not add `_lock` inside a new independently opened reader connection when Ledger.persist already holds oracle2-authz on its own connection: persist lines135,143 calls authorize_refs while holding that lock, so nested lock acquisition deadlocks. Use an explicit processing resolver with a caller-supplied connection for nested checks, or a bounded connection-aware authorize_refs protocol. Existing ordinary resolver behavior stays unchanged. Never take connection/thread authority from request inputs.

Validate current lineages and admissions with clock_timestamp(), not transaction-start now(); a transaction waiting on locks can outlive an appointment. Reuse the existing workspace authority lock on the SAME connection where held; lock exact admission/source/original rows consistently where needed to serialize concurrent updates. Recheck actual clock and mutable identity immediately before returning data, before provider dispatch and before artifact commit. Expiry/withdrawal/revocation after an earlier receipt must deny the next operation. Do not hold database locks across network/provider calls or pretend an already dispatched request can be unsent. Current broker replay/reservation accounting remains authoritative.


## 9. Ordered implementation proposal and ownership

### 9.1 Q1/Q2 — architecture and owner/caller source contracts

Coordinator obtains independent exact-head architecture review of this complete plan and accepts/rejects exact scope on #27. Before source implementation, inspect existing source/migration/bootstrap identity contracts; freeze an explicit approved function-owner definition and a trusted processing actor context design. The source owner contract is a mandatory exact installer descriptor field for the trusted dedicated-ledger migration owner: its canonical role identity must equal the reviewed schema/existing helper owner and must be unreachable through any application membership or SET ROLE chain. Source fixtures pin their known isolated migration owner explicitly. No named production owner is invented, no new owner role is created, and actual-target catalog identity remains separate. Before any later target action, a separately admitted metadata-only catalog read must prove actual `pg_proc` owner, `SECURITY DEFINER` flag, `search_path`, EXECUTE grants, role memberships and target identity; UNKNOWN blocks target execution and must not cause a substitute owner/admin path. Source can specify proposed secure owner constraints without pretending the live owner is known.

Define processing actor from a trusted immutable job/admission context bound to worker URI/runtime/purpose/workspace/exact source tuple and admission expiry. Existing documentary job actor lookup is not silently borrowed. Freeze least-privilege allowed source-reader/compiler/executor and metadata-broker contract. Record an exact installer descriptor (owner role identity, expected helper/schema ownership, non-membership policy, target identity/TLS/runtime/source-registry pins) and a frozen typed processing context in proposed `operating_model/source_processing.py`; source tests validate mandatory fields and refusal, while actual construction remains blocked before install until separately admitted target metadata matches. Root coordinator owns this implementation proposal after architecture acceptance. Verification: named owner/caller contract plus all unknown target facts remain explicitly stopped for action; `test_processing_caller_cannot_supply_actor` is specified before implementation. Q1/Q2 design can be inspected in parallel; no SQL/code change begins until coordinator accepts actual reviewed architecture and exact source scope.

### 9.2 Q3a — additive native SQL011

Implement only the functions/ownership/EXECUTE grants described in §8 after its prerequisites. Do not edit SQL007/008 generated history or existing helper/RLS defaults. Own a target-checked native migration path and exact ordered migration receipt; isolated SQL001..011 is the first implementation test target. No live migration command is authorized by this plan. Verification: `test_processing_getter_roles_and_exact_pins` and direct privilege probes pass, old helper definitions/current() behavior unchanged, no new table or role.

### 9.3 Q3b — typed connection-aware processing resolver

Extend `operating_model/authority_adapter.py` with a separate processing getter/resolver, fixed externally supplied SourceRoleBinding and immutable trusted principal context. Never repurpose current()/can_read defaults. For compiler processing, require both exact scoped authorities per recheck; support caller-owned same connection when Ledger.persist already owns authz lock. Extend the narrowly opted-in processing source-resolution contract in `ledger.py`; default ordinary serving remains unchanged. Metadata-only executor resolver validates SourceRef against current identity and sealed generated artifact, never constructs fake SourceReceipt with empty/unchecked reading. Verification: `test_processing_resolver_preserves_serving_default`, `test_processing_persist_nested_lock_finishes`, `test_processing_receipt_changed_before_commit_denied`.

### 9.4 Q4a — trusted processing broker chain

In `hosting/provider_runtime.py`, `operating_model/native_factory.py` and exact native job schema, add ONLY the independently approved fixed source-processing job route. Bind principal/purpose/source pins and fresh original identity using the reviewed metadata-only guard; keep provider admission, reservation, response validation and spend coverage unchanged. The existing source-extraction path default and documentary paths are not widened by client flags. If current immutable job schema cannot express the new context, version exact source schema under review before construction; no ad hoc context or inherited prior authority. Verification: `test_processing_broker_wrong_actor_purpose_pin_denied`, `test_processing_broker_revocation_before_dispatch_denied`, `test_processing_completion_after_revoke_not_persisted`.

### 9.5 Q4b — metadata-only executor reported-artifact path

Extend exact generated-ledger/job resolver path in `hosting/job_authority.py` and the new opted-in `Ledger`/projection reader only after 9.3–9.4. Validates sealed generated reported artifact, current read authority, immutable job/release/source population and original identity through metadata-only getter. It does not pass old current() by fabricating draft confirmation or copy full source into executor. Existing generated-policy confirmation still requires authorized finding/model review. Verification: `test_executor_metadata_only_no_raw_privilege`, `test_reported_artifact_has_no_confirmed_policy_authority`, `test_generated_executor_old_serving_unchanged`.

### 9.6 Q5 — local proof then review/shipment

Complete §10 with real isolated PostgreSQL, actual bound identities and TLS, plus existing source-role/job/authority regressions. Freeze full source, obtain exact-head independent review and checks; publish a stage-preparatory PR, never claim S03 accepted from source/tests. Re-read W and S downstream obligations. Verification: exact command/test artifact and review receipts on #27, no skipped required local cases. No production/runtime action is taken here.

### 9.7 Q6 — separate public-invented E-public runtime gate

Only the documentary-journey plan owner constructs exact proposed runtime/action manifest after source release and independently admitted target qualification. Use public invented originals; no private material or employee message. Admission for new source processing, provider budget/purpose/model and actual target/owner/caller must all be current independently; missing fields remain UNKNOWN and stop. Source plan approval never substitutes. Verify actual original intake→new extraction→holistic assembly→SDK→reported answer without preconfirmed old map, then persist/restart/withdrawal denial; acceptance remains public invented only. Leave `- [ ] live proof` on #27, no new proof issue, until completed. S03 private/business acceptance remains separate and paused where applicable.

## 10. Required tests and adversarial input matrix

Future test modules: `tests/test_source_processing_qualification.py`, `test_source_processing_role_chain.py`, `test_source_processing_races.py` under `services/oracle-brain/`. The tests named below are specified deliverables, not present/passing evidence.

| External input | Hostile case | Required exact test |
|---|---|---|
| processing actor/context | request supplies root, wrong worker/job actor, wrong purpose | test_processing_caller_cannot_supply_actor |
| DB session and roles | foreign SESSION_USER, SET ROLE confusion, elevated/inherited membership, executor raw call | test_processing_getter_roles_and_exact_pins |
| function owner/grants | PUBLIC EXECUTE, mutable search_path, app-owned definer, changed owner | test_processing_function_owner_and_grants_denied |
| source scope | only read, only extraction, other source/workspace, wildcard | test_processing_requires_both_exact_scopes |
| grant lineage | revoked/expired leaf,parent,root; foreign parent; cycle/depth overflow | test_processing_lineage_invalid_denied |
| original/draft status | error/processing/missing source; withdrawn/missing/duplicate draft | test_processing_withdrawal_state_denied |
| source reading | duplicate original, duplicate/missing metadata, malformed/extra provenance, altered content | test_processing_provenance_exact_and_unique |
| source identity | stale revision/original/hash/parser/runtime/registry/principal, conflicting existing receipt | test_processing_source_identity_mismatch_denied |
| dates/locks | expiry while waiting; nested second-connection lock; revoke/revision between read/dispatch/commit | test_processing_persist_nested_lock_finishes; test_processing_receipt_changed_before_commit_denied |
| TLS and peer | plaintext, wrong CA/hostname/worker SAN/HMAC/cert, stale job registry | test_processing_peer_and_ledger_tls_denied |
| compiler output | confirmed policy flag, borrowed quote/source revision, incomplete output | test_reported_artifact_has_no_confirmed_policy_authority |
| executor source population | metadata leaks raw original, foreign source/release/actor, raw function call | test_executor_metadata_only_no_raw_privilege |
| provider boundary | unauthorized purpose/cap/key coverage, revocation before/after dispatch, replay | test_processing_broker_wrong_actor_purpose_pin_denied; test_processing_completion_after_revoke_not_persisted |
| ordinary serving | new path changes old current()/confirm scope or bypasses confirmed state | test_processing_resolver_preserves_serving_default; test_generated_executor_old_serving_unchanged |

Positive test `test_draft_original_generates_reported_candidate_without_confirmation` must preserve interpreted draft=draft, permit exact qualified original under both scopes, generate reported output with exact evidence, and still deny old current(). Target role/SQL tests require actual PostgreSQL; mocks/admin connections alone cannot pass. Reuse current test infrastructure and owned per-run stores/ports; never use recovery stores.

Retain `tests/test_authority.py`, `test_review_concurrency.py`, `test_hosting_source_binding.py`, `test_hosting_runtime_permissions.py`, `test_hosting_candidate_permissions.py`, `test_hosting_job_authority.py`, `test_hosting_executor_jobs.py` and the actual ledger suites and retained S03 phase guards. Discover exact relevant existing files with `rg --files` before implementation and report unavailable prerequisites instead of skipping. Use existing `uv run --extra test pytest` and `scripts/oracle2/verify_phase.py S03 --mode offline` only on isolated target-configured stores; this plan does not claim those commands ran.

## 11. Constraints and gotchas

AGENTS and docs/agents/08,11,13 govern. This plan/router publication is reviewer-safety because AGENTS discovery pointer is protected. It requires exact-head independent review; DB/deploy/infrastructure/production actions remain forbidden by its declaration. Future code and SQL require their own appropriate task class and gates, exact target proof and reviewed technical architecture. Database writes do not require a second AI write approval under standing rules; this fact does not authorize any write or waive existing architecture/target/role/release controls.

All writes use isolated current-upstream worktrees, protected main via PR, no server live edits, no broad staging or secret access. This dedicated Oracle ledger is not shared-db; native SQL belongs in its existing canonical path, retained generated Drizzle remains under its own runner. No legacy state adoptions, expired/spent receipt renewal, provider replay, old claim staff grading or employee contacts. Keep evidence private; public fixtures invented. Actual deployed/function ownership may differ from source and remains UNKNOWN until separately admitted proof.

Locks must follow one connection and established ordering; do not hold database transactions over provider network calls. No silent type fallback, fake provenance, empty reading receipt or normalization into a different identity. A technical review is not a human approval request. Runtime caller/owner uncertainty is AI-owned and blocks only actual dependent actions.

## 12. Access and environment

Read-only source/GitHub via existing authenticated gh was available during audit; local Python/uv exists. No database URL, secret, original object or platform credential was opened for this plan. Current runtime-plan owner freshly reports that preview DB `wfdrklofsczspazshaib` is only a proposed E-public target under historical PR138 invented transport scope, not qualified for W dedicated-ledger roles or SQL011. Concealed preview admin/worker/web URL field existence proves neither least-privilege metadata access nor current pg_proc scope/TLS admission. No current dedicated target or verified metadata-role route is established in this coordination scope. Root coordinator owns target selection and exact bounded metadata admission, not Albert; old native authority remains expired and cannot be presumed current. This is an action prerequisite, not a reason to leave source owner/caller design unowned. Secret vault is vibe_coding; exact future credential item titles/targets are UNKNOWN here and must be resolved by the AI through current approved custody before any action, never guessed or printed. No user command/click/setup is requested.

Own plan branch is codex/oracle-source-processing-qualification-plan, base97da85b. Sole runtime plan/handoff owner is separate coordinator child; its linked branch may be unpublished at initial freeze. New implementer resolves current upstream and same #27 ownership first. Public invented qualification uses owned isolated stores/identities and exact manifest; no public HTTP response or preview resource status is proof of this new boundary until Q6 runs.

## 13. Definition of done, risks, stop gates and rollback

Architecture delivery: all13 sections, source pointers, rejected paths, current unknowns, adversarial cases and reciprocal coordination handoff/router links exist; self-audit passes; exact-head independent architecture review and coordinator scope decision are recorded on #27; prose source committed/pushed via reviewed PR. Publication never means implementation is accepted. The linked runtime plan must treat this plan as unmet prerequisite until actual accepted source and action qualification exist.

Implementation delivery later requires additive reviewed SQL/resolver/broker/executor source, actual-role negative tests without skipped mandatory evidence, commit/push/CI and reviewed PR, exact deployed release+target+owner/caller proof and actual public-invented journey under current independent action admission. No private/business acceptance or S03/S04+ closure follows automatically. Final live proof stays unchecked on #27 until actual evidence exists; one named owner, no leftover issue.

Risks/open technical decisions: actual function owner UNKNOWN; processing actor/job provenance not implemented; existing withdrawal marker is draft status; metadata-only generated executor integration must preserve evidence validation and ordinary confirmed serving; provider/budget/embedding/current authority remains independent. Q2 fixes exact owner/caller source contract (coordinator-owned source implementation after accepted architecture); actual target facts remain blocked until root selects a target and separately admits a bounded read of pg_proc owner/config/ACL, schema owner, relevant memberships and TLS/session role metadata. This read must not touch source data, secrets or environment values. Missing exact descriptor or role scope stops the read; do not infer permission from URL presence. If no secure bounded source owner/caller/metadata chain can be proved, stop with all original capabilities retained and coordinator-owned #27 blocker.

Rollback: no implementation was made by this plan. Future implementation disables only the newly selected processing job route, revokes its new EXECUTE capabilities through a reviewed compensating migration, retains source/event/failed-output evidence and restores prior tested normal route. Never remove old confirmed serving, evidence, graph adapters, role separation or retained data. Already sent provider requests are accounted as spent, never replayed to simplify rollback. No removal of original confirmation controls or irreversible deletion.

### Self-audit

1. A new session can proceed without chat: YES for the defined first work, §§2–6 exact source facts, §8 complete permission contract, §9 ordered stop gates and §12 access explicitly say no implementation until coordinator acceptance and unknown owner/caller qualification. UNKNOWN target facts are not implementation guesses; they have named blocking evidence gates.
2. Background/nuance/rejections retained: YES §§3,6–8 preserve faulty-claim trigger, SQL008-over007 barrier, withdrawal encoding, new-scope semantics, actual clock/principal/lock traps, raw-vs-metadata separation and rejected shortcuts.
3. Goal supports correct choices: YES §§1,4,8,13 require new holistic reported knowledge, original custody/access and independent truth confirmation; any conflicting step stops for coordinator.

Checklist: all13 sections present; exact files and named gates; adversarial table every row has tests; locked/open decisions; explicit non-goals/access/secret limits; commit/push/CI/deployed verification criteria; single coordinator-owned reciprocal handoff registration; no unauthorized memory update. No business decision for Albert is pending in this scoped design. Independent reviewer/coordinator decision is technical, and no actual action is approved by planning.
