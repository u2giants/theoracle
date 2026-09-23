---
issue: 14
status: OPEN
owner: codex/jev-integration-plan-final
---

# TypeSafe Jev integration plan handoff

Canonical plan: [`../plan_typesafe_jev_decision_layer.md`](../plan_typesafe_jev_decision_layer.md)

## 0. ⚠️ DECISIONS ONLY THE OWNER CAN MAKE

Put this entire list to Albert in one message before any company data is sent to TypeSafe. Do not raise these one at a time.

### Blocking company-data pilots

1. **Approve the vendor/data terms and per-class allowlist.** Recommendation: require TypeSafe enterprise zero-data-retention terms plus acceptable DPA/security/subprocessor coverage, then explicitly allow or deny internal company, employee communication, licensed, HR/personnel, and customer-personal data. Unknown or mixed-unapproved data stays blocked. This blocks Oracle-data pilots, but not synthetic foundation work.
2. **Approve a capped evaluation balance.** Recommendation: start with $5, which is ample at the documented price, and increase only if Oracle's own evaluations prove value.

### A wrong guess is recoverable, but do not guess

None. The plan fixes the pilot order and keeps every first run shadow-only.

### Outside this workstream and nobody here owns it

The newest R2 handoff still asks whether to continue reason-code feedback and to repair the stored OpenAI key prefix. This Jev work must not answer or absorb those decisions; keep following `HANDOFF.d/2026-08-27T1600Z-al8960ofc-claude-r2-reason-feedback-regressed.md`.

### Already settled — do NOT re-ask

- 2026-09-20: Jev is a separate decision primitive, not a seventh generation provider.
- 2026-09-20: every use case begins shadow-only and fails open to current behavior.
- 2026-09-20: Jev never replaces generation, exact evidence, permissions, approvals, lifecycle rules, auth, locks, transactions, cooldowns, or caps.
- 2026-09-20: production model is pinned to `jev-1.13.0`; upgrades require re-evaluation.
- 2026-09-20: each live behavior is a separate session/proof; no bundled rollout.

## 1. What this application is

The Oracle is POP Creations / Spruce Line's evidence-backed enterprise knowledge system. Employees use web and Teams chat; workers turn messages and documents into quote-supported operational claims; admins review claims, contradictions, gaps, taxonomy, and synthesized Brain sections. Repository `u2giants/theoracle` runs a TypeScript/pnpm monorepo on Vercel, Trigger.dev, and Supabase. Production web is `https://oracle.designflow.app`.

## 2. What this session set out to do, and why

Albert asked for a full implementation plan after a whole-codebase audit found places where TypeSafe AI's Jev could reduce AI cost. The technical goal was to convert those findings into a fresh-session-ready, staged build specification without weakening the Oracle's defining evidence and safety boundaries.

The plan is issue #14 and lives at `plan_typesafe_jev_decision_layer.md`.

## 3. Current state — what is true right now

- The primary audit began on `63cdcaa`, was first reconciled on `824c1ff`, and on 2026-09-22 was rebased/re-audited against application code `499d8b0dc3a726ea59dc93114cbb165e1f96f9d3`, including PR #17's evidence reconciliation, canonical rendering, and independent semantic review. It is now rebased on current `origin/main` `b7a7acad0056acbc45c152fe1f2ac4730c107906`; PR #18 changed documentation only.
- No TypeSafe/Jev package, code, secret, setting, schema, deployment, or production call exists.
- The plan is written with all steps open and links back to this handoff.
- Issue #14 exists, is assigned, and tracks implementation.
- The substantive publication branch was `codex/jev-integration-plan-final`; the documentation-only M0 amendment branch is `codex/jev-plan-approval-status`.
- The substantive plan was approved by exact-head review `20260923T015902-1579-11000` at `fab526bd92546acacb599a13c48824e9595b5a1e` and merged in documentation-only PR #19 as `c5dc22269305cb7a84463890e00f015df1670df7`. The later M0 executable-safety amendment is not covered by that approval and may merge only with its own exact-head APPROVE artifact; the PR/reviewer artifact is authoritative for that gate. Issue #14 remains open/assigned for implementation, which must start with M0; no Jev runtime or production behavior is enabled.
- The shared canonical checkout at `D:\repos\oracle` had six unrelated uncommitted pipeline files and was 141 commits behind when the audit began. It was preserved untouched. Implementation must use new current-upstream worktrees.
- The newest R2 responsibility handoff is still open and production is restored to its known-good 23/30 map. Jev's responsibility quote-selection work is evaluation-only and may not change that live path.
- Issue #15 closed after partial first acceptance; PR #17 subsequently landed its evidence-reconciliation correction on main. The Jev plan now treats the actual `499d8b0` ledger/render/review topology as the Step 9 baseline and does not invent the old draft/retry path. `HANDOFF.d/2026-09-20T1411Z-916-codex-connected-answers.md` remains a **SUCCESSOR REVIEW candidate**, owned by `codex/019f5f18-a461-7861-a0ec-be5ba1f7bb6c`; this session did not edit/delete it or claim unverified second live acceptance.

## 4. Everything tried that did NOT work

- The first attempt to declare task class `review` failed because `review` is an action, not a valid change class. The plan began as `prose`, then the gate correctly escalated protected plan/handoff files to `reviewer-safety`; implementation must choose its actual code class and check again before stronger actions.
- Pulling the shared checkout was not safe: five of its six uncommitted files overlap the 141 upstream commits. The work moved to a clean managed worktree at exact upstream instead of stashing, committing, or overwriting another session's work.
- Adding Jev as a normal generation adapter was rejected: its contract is Noul/Choice/Score, not text or arbitrary schema generation.
- Replacing extraction/chat/synthesis/translation was rejected because Jev cannot create strings or records.
- Immediate production gating was rejected because false negatives could silently lose knowledge; shadow evidence is mandatory.
- One global confidence threshold was rejected because recoverable routing and irreversible knowledge suppression have different risk.
- Using `jev-latest`, full transcripts/documents, or vendor benchmark claims as proof was rejected because model drift, privacy/context rot, and domain mismatch would make the system untrustworthy.
- Exact-head plan review `20260920T144330-126977-19851` rejected commit `7161680` because entity activation could reduce recall and the plan omitted deterministic multi-result MCP ranking, batch-extraction parity, CI wiring, held-out evaluation, total deadlines, a locked chat fallback, and audit-persistence failure behavior. The successor must not restore those gaps; the corrected plan addresses the entire class and requires a fresh exact-head approval.
- Exact-head review `20260920T145239-147556-8085` rejected commit `c54bde8` because generation audit tables cannot represent safe pending/effect state, caller-supplied data classes can be downgraded, extraction skips lacked replay, contradiction negatives lacked durable disposition, and later advisory/review flows were under-specified. The plan now requires dedicated decision/subject tables, provenance-derived class sets, bounded extraction recovery, versioned contradiction dispositions, an exact chat-review lifecycle, and separately planned advisory ideas.
- Exact-head review `20260920T150229-171356-19209` rejected commit `8b8a35e` because hard-negative gates lacked production canaries, overlapping extraction windows could conflict, pending calls lacked crash recovery, chat retries lacked complete generation accounting, and audit retention/erasure was undefined. The corrected plan adds sampled current-model canaries with automatic shadow fallback, window-owner reconciliation, a stale-pending reaper, separate first/retry generation records, typed subject FKs, and bounded retention/erasure tests.
- Exact-head review `20260920T151325-219412-26184` rejected commit `dd804fe` because not every call site had a representable subject, `skipped_by_decision` omitted existing status constraints/failure cleanup, canary comparator/human evidence was not durable, the named alert source could not read Jev data, crash reconciliation lacked a scheduled entrypoint, entity evidence named the wrong table, and rollout flags were incomplete. The plan added typed candidate links/composite uniqueness, all extraction status consumers and mixed-batch cleanup, comparator/adjudication/control-event records, a Jev alert banner, a scheduled reconciler later consolidated into the existing ten-minute drain, correct entity linkage, and exact settings/activation evidence; later reviews replaced subjectless MCP with short-lived query origins.
- Clean-current-main review `20260920T152816-307830-29161` rejected commit `4edd0d0` because second chat-check failure could leak an unverified retry, the admin lacked an adjudication action that invokes health fallback, vendor approval was not a versioned runtime policy, some call sites still lacked subjects, retention precedence was ambiguous, document classification was absent, and weekly canary quotas were not concurrency-safe. The plan now refuses after any unavailable second check, makes adjudication+health one executable transaction, adds immutable versioned data policies and document classification, covers eval/live/retrieval subjects, defines erasure/event FK precedence, and atomically reserves ISO-week canary quotas.
- Exact-head review `20260920T154133-378291-22764` rejected commit `387d608` because extraction batch-only subjects survived message erasure, duplicate pending calls could consume canary quota twice, entity comparison assumed nonexistent model-run persistence, disposition identity omitted policy/model versions, document events lacked before/after linkage, two chat checks were not modeled as two decisions, and admin mount files/table count were incomplete. The plan now adds source-message links plus an erasure trigger, unique canary reservations, an entity-query comparator contract, policy/model-aware identity, document-specific events, parent-linked chat decisions, and exact layout/navigation integration.
- Exact-head review `20260920T155057-401043-26365` rejected commit `46133a3` because run rows lacked deadline/discard fields, duplicate pending decisions and concurrent adjudications were not serialized, request sizing ignored full multi-question payloads, two existing safety commands were omitted from required/CI checks, and admin scope wording was broad. The plan now specifies deadline/discard taxonomy, partial-unique provider-call identity, locked single-head adjudication, conservative serialized byte/question limits, `verify:r5`/`verify:r11.1` wiring, and decision-review-only admin scope.
- Exact-head review `20260920T160013-461865-2153` rejected commit `c77f726` because in-flight results were not fenced against off/revocation/auto-shadow, reactivation could reuse an unsafe result, identity omitted the exact input hash, canary quotas were not configuration-scoped, and decisions did not link exact document evidence rows. The plan now adds activation generations and a shared final-effect/control lock, input-hash/config-fingerprint identity, fresh per-configuration canary cohorts, and typed claim/candidate evidence plus document-chunk subjects with erasure tests.
- Exact-head review `20260920T161235-526732-907` rejected commit `01924af` because the seven decision tables lacked RLS, dependent web code could auto-deploy before its migration, and direct claim deletion did not invalidate a multi-claim decision. The plan now requires tested RLS for every table, a schema-only Step 1A production migration before any auto-deployed reader in Step 1B, pre/post admin smoke tests, and deletion tests for either claim in a multi-claim decision.
- Exact-head review `20260920T162023-570305-28553` rejected commit `8241ee8` because two planned schedules exceeded Trigger.dev headroom, query-only decisions lacked a reliable erasure origin, Steps 8A/8B shared one STATUS row, the $5 cap was not enforced, and new hand-written migrations were not routed into the catalog. The plan now reuses the existing ten-minute drain schedule with daily leasing, requires erasable query-origin records and short-lived MCP origins, splits 8A/8B, atomically reserves a fail-closed immutable-epoch spend cap with no auto-refill, and updates the SQL migration catalog with every new file.
- Exact-head review `20260920T163049-631927-139` rejected commit `26394ca` because multi-message query erasure was incomplete, extraction skips could outlive replay evidence, the shared retrieval function lacked caller isolation/fallback parity, chat output hashes lacked schema, Step 7 bundled unrelated classifications, and Score bounds were absent. The plan now links every contributing query message, snapshots replay-critical skip metadata on extraction batches, makes caller context mandatory and limits reranking to chat across both retrieval branches, splits a schema-only output-hash step from chat code, defers classifications, and validates Score levels 2–10.
- Exact-head review `20260920T171331-807104-21694` rejected commit `5f15493` because retention could refill the spend cap, free-text classes could omit pasted internal/licensed content, active config changes did not force renewed acceptance, and the shared scheduler lacked a visible-failure regression test. The plan now adds a permanent spend-epoch ledger, maps arbitrary free text to the full conservative class union, forces every model/pack/threshold/policy change back to shadow with new exact-fingerprint evidence, and requires mixed healthy/transient-failure scheduler tests that preserve retries but fail the Trigger run.
- Exact-head review `20260920T172342-836712-30169` rejected commit `8ba1369` because spend reservation omitted SDK retries/crash settlement, approved resolved-model identity was not durable, extraction replay had no replacement batch status, `invalid_response` was absent from discard reasons, and the handoff retained obsolete five-minute wording. The plan now pins two retries/reserves three attempts with idempotent stale settlement, stores the approved resolved model per use case, transitions replayed owners to explicit `replay_queued`, completes the discard enum, and consistently uses the existing ten-minute scheduler.
- Exact-head review `20260920T173343-867093-19084` rejected commit `7b28c8f` because creating a 1Password item did not provision the separate Vercel and Trigger.dev production environments. The plan now adds protected, names-only verified secret injection plus a fresh merged-SHA redeploy and public-synthetic target-path proof for Vercel before Step 3 and Trigger `prod` before Step 6.
- Exact-head review `20260920T174018-896298-20623` rejected commit `cd06a41` because an arbitrary MCP request could not safely qualify as synthetic, entity candidate labels/aliases lacked typed provenance and erasure, and Jev probability could outrank an exact capability name. The plan now uses a code-owned byte/hash-locked MCP probe, links and conservatively classifies every supplied entity candidate with whole-run invalidation, and pins enabled exact-name matches before all Jev ranking.
- Exact-head review `20260920T175500-962763-18364` rejected commit `7d11af2` with eight high- and seven medium-severity gaps: generic settings/direct SQL could bypass Jev controls; documents could be marked `public_synthetic`; entity/live-Recall provenance was incomplete; Step 6 lacked durable capture, schema-first split, and cross-run membership; Step 7 judged after promotion; Step 8A was not pair-aware; immutable/same-run promises lacked constraints; MCP lacked handler tests/docs; Step 5 used a record metric for quote-only work; and Step 9A reranked before enrichment. The rebased draft now addresses the entire list: typed owner-only DB functions/constraints, document synthetic rejection, complete subjects, handler/README tests, quote metrics, normalized Step 6A/6B ownership and force directive, Step 7A/7B pre-promotion review hold, pair-aware Step 8A, frozen Step 8B snapshots, and current-main post-enrichment Step 9 with shadow-only reconciled-answer audit. None is accepted until the fresh exact-head review approves it.
- Exact-head review `20260922T213853-14212-27125` rejected commit `f0e0975` because deployed database connections did not separate the migration owner from web/workers, held duplicate candidates had no admin resolution path, contradiction pairs lacked canonical race protection, and explicit capture omitted the real message API/composer/RLS surfaces. The repaired draft adds separate least-privilege runtime roles and real-credential probes, held-duplicate accept/reject actions, schema-first canonical pair uniqueness plus leased reservation, and the complete message/API/UI/direct-write capture contract. None is accepted until the next exact-head review approves it.
- Exact-head review `20260922T215441-22913-5675` rejected commit `c09f5bb` because the DB-role cutover lacked a whole-application privilege manifest/regression gate, human admin authority was not attestable behind one web role, the entity pilot omitted the route/context contract, Step 9B omitted persistence ordering/writer failure semantics, contradiction repair missed scalar/JSON sibling references, and Step 5 misstated 27/30 as existing evidence. The repaired draft adds a machine-checked access manifest and staged platform cutovers, `auth.uid()`-derived human-control RPC, a DB-backed chat entity seam/test, exact model-run/Jev transaction ordering, complete contradiction-reference repair, and the correct restored 23/30 versus 27/30 threshold distinction. None is accepted until the next exact-head review approves it.
- Exact-head review `20260922T221548-27928-9129` rejected commit `5059615` because RLS alone cannot make capture audit fields immutable or prevent content edits from leaving stale extraction skips. The repaired draft makes capture fields trigger-enforced write-once, replaces direct content updates with an authenticated versioned RPC, snapshots content version/hash in memberships, atomically invalidates/requeues pre-extraction edits, fences worker races, and rejects post-extraction edits in favor of a correction message. None is accepted until the next exact-head review approves it.
- Exact-head review `20260922T222530-174-1009` rejected commit `475fc48` because Step 4 depended on fields absent from the foundation migration, soft-deleted messages did not invalidate decisions, and claim-support failure semantics conflicted with the global current-behavior fallback. The repaired draft moves origin/scope/hash/ordinal fields into Step 1A, invalidates on `messages.deleted_at`, and makes only a successful audited support-review outcome restrictive while every outage/stale/low-confidence path preserves current promotion with no backlog. None is accepted until the next exact-head review approves it.
- Exact-head review `20260922T223549-226-24395` rejected commit `60656f0` because Step 7 needed a constrained post-transport claim effect, direct message inserts could spoof capture fields, custom runtime roles lacked RLS policies for existing operations, and role credentials lacked a secure delivery/rotation contract. The repaired draft separates immutable pre-transport inputs from one function-owned finalization output, adds insert/update capture triggers and protected-column grants, makes runtime RLS/function coverage part of the access manifest, and specifies versioned login roles with protected 1Password generation, pooler URL construction, platform delivery, proof, rollback, and blue/green rotation. None is accepted until the next exact-head review approves it.
- Exact-head review `20260922T224913-1365-18730` rejected commit `66205dc` because Step 6A could break existing message inserts; runtime-role cutover omitted exact client implementation; immutability conflicted with privacy deletions; vendor ZDR/credential posture was not runtime-authoritative; company-data policy/activation lacked an executable admin path; Live Recall could not recover safely after a crash; claim auto-approval was outside the decision transaction; definer functions lacked a universal hardening contract; the production MCP route was not wired; the retrieval verifier targeted the wrong boundary; new-claim holds had no resolution lifecycle; and no-work drain maintenance was untested. The repaired draft now specifies backward-compatible message triggers, three no-fallback DB clients and staged cutovers, enumerated redaction-only mutation, fingerprinted zero-retention posture, guarded admin policy/mode actions, an at-most-once durable Recall delivery machine, atomic promotion/auto-approval, universal definer ownership/search-path/ACL rules, mandatory production MCP injection, the web-level rerank verifier, atomic claim-review resolution, and no-work maintenance tests. None is accepted until the next exact-head review approves it.
- Exact-head review `20260922T231905-841-22795` rejected commit `ae1dbab` because a migration-seeded synthetic policy could not know the protected credential fingerprint; physical source deletion could be blocked by existing `NO ACTION` evidence/chunk FKs; erasure could strand held candidates/claims after decision deletion; later schema phases omitted the runtime-access manifest; Live Recall sweeping lacked an executable scheduler contract; and credential rotation lacked bounded PostgreSQL role authority. The repaired draft now creates the first policy only after secret provisioning through an idempotent guarded transaction, defines one ordered FK-safe source-erasure procedure that resolves business rows first, extends the manifest/RLS/grants in every schema phase, runs a bounded Recall sweeper through the existing ten-minute drain with visible failure, and confines rotation to a target-specific NOLOGIN CREATEROLE role plus registry/function tests. None is accepted until the next exact-head review approves it.
- Exact-head review `20260922T234219-286-29517` rejected commit `3266b29` because Live Recall still combined schema migration with dependent code/live proof, and decision invalidation named executable deletion handling only for messages/documents despite promising every typed parent. The repaired draft splits Live Recall into schema-only migration/unchanged-code smoke, separate durable non-posting delivery deployment, and a third live-proof outcome; it also adds one fixed, hardened pre-delete invalidation trigger with explicit FK behavior and tests for every supported parent, including `model_runs`, Brain sections, and relationships. None is accepted until the next exact-head review approves it.
- Exact-head review `20260922T235301-168-16908` rejected commit `63bdc75` because the Recall webhook could acknowledge before any durable inbox row; policy replacement inserted before revoking despite an immediate unique index; duplicate holds lacked a truthful candidate-target output; SDK logging was not explicitly disabled against an environment override; and user-facing controls lacked real-browser proof. The repaired draft persists a strict normalized webhook inbox before 202 with sweeper/pre-persistence crash tests, orders locked policy replacement as revoke-old then insert-new in one transaction, adds `review_hold_candidate`, pins SDK logging off with hostile-env tests, and requires keyboard/mobile/visual browser evidence for capture and Decisions UI. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T000828-286-3822` rejected commit `da7a5b0` because the Recall route still buffered an unbounded body before validation, database-side dynamic password SQL could expose the secret in managed logs, and the post-send crash test incorrectly expected fabricated business rows. The repaired draft adds an actual-byte-counted 256 KiB stream cap covering false/missing/chunked lengths, replaces server-side plaintext rotation with client-side libpq SCRAM-verifier generation under a target-limited rotator role plus log-sentinel proof, and specifies `send_unknown`+alert with zero assistant/intervention rows after an unconfirmed send. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T002008-816-24184` rejected commit `966b565` because Live Recall lacked exact state retention/source-erasure rules, the live proof had no positive one-post contract, `send_unknown` had no reconciliation owner/action, and spend reservation still relied on a token estimate. The repaired draft now clears ingress/draft content on explicit 24-hour/7-day state limits, retains/deletes hash-only rows on exact per-state TTLs, folds message/channel erasure into the delivery transaction, adds authenticated admin reconciliation with truthful posted/not-found outcomes, requires one deployment-bound external post and one matching internal trail, and reserves all three attempts at the vendor's proven maximum billable token ceiling with contract-breach shutdown tests. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T003251-1809-24970` rejected commit `1fce1f5` because the plan named nonexistent Recall bot/session FKs, did not define immutable event-key coordinates, assumed the send endpoint returns an external message ID, and retained a contradictory warning/error SDK logging rule. The repaired draft uses one real channel FK plus bounded external IDs, a database-derived content-independent coordinate key with separate payload hash/conflict handling, a code-owned response-shape probe and truthful nullable-ID receipt, and one universal SDK `logLevel:'off'` rule. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T004406-899-23967` rejected commit `a4e22a6` because ingress requirements were stricter than the unproven Recall contract, channel resolution remained race-prone, contradiction dedup could destroy loser-row business/audit values, and removing DB accessors could break top-level scripts outside package typechecking. The repaired draft adds a separate pre-schema inbound-contract capture with strong/weak identity and revision rules, a unique bot-to-channel registry with locked creation, a full immutable contradiction loser archive with rollback tests, and explicit operational-script migration plus repository-wide forbidden-import and smoke checks. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T010324-1795-2681` rejected commit `8502ba4` because a strict scanner would fail before staged caller cutover, weak Recall events had no executable task contract, maintenance could starve behind an unbounded extraction backlog, and new contradiction reservation/archive data escaped source erasure. The repaired draft adds monotonic inventory/dual/worker-strict/strict scanner phases, distinct strong-delivery and weak-legacy tasks/inboxes, fixed pre-batch maintenance budgets with bounded cursors, and complete reservation/archive source closure, retention, erasure, and race tests. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T012018-1180-16491` rejected commit `292ba19` because `review_held` conflicted with existing promotion/duplicate checks, contradiction dedup simultaneously required assignment mutation and a byte-identical survivor, and credential rotation lacked named files plus PostgreSQL/libpq compatibility gates. The repaired draft replaces both candidate checks and adds typed hold variants plus a deferred cross-row trigger, limits survivor mutation to two deterministic assignment fields with exact tests, and specifies the C helper/build/test paths, libpq 17.11 pin, and PostgreSQL 16+ preflight. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T014006-1033-8843` rejected commit `1d08717` because the current lexical raw-SQL runner would execute `100+` before `11–99` and could overwrite later constraints, while nullable decision/subject identity fields made ordinary uniqueness porous. The repaired draft adds a separate M0 numeric-order runner/CI/clean-and-snapshot double-run production prerequisite, reserves ordered `103–107` Jev migrations, uses `NULLS NOT DISTINCT` run identities, and creates one null-safe target-specific subject index with raw concurrent-insert tests. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T020743-317-21929` rejected status-only commit `8012eee` because this handoff and the plan still told successors to republish the already merged plan and start at Step 0. The correction now makes M0 the mandatory first implementation outcome and blocks every Jev schema migration until M0's production double-run proof.
- Exact-head review `20260923T021248-1824-1164` rejected commit `f021859` because M0 tried to prove a future Step 7 constraint while forbidding that migration, and its verifier could import the auto-running migration entrypoint. The correction makes future ordering a pure synthetic-name fixture, limits M0 database proof to currently shipped SQL, and extracts a side-effect-free ordering module that validates before URL lookup or connection.
- Exact-head review `20260923T021841-738-14796` rejected commit `70a5d21` because M0 lacked an exact production-project guard, compared counts instead of row values, left three lexical-order consumers, and did not name its proof implementation/commands. The correction adds an exact `eqccjfbyrywsqkxxpjvg` same-connection target guard, an apply-once checksum ledger and value-level allowlisted fingerprints, shared ordering for every consumer, and named baseline/idempotency scripts with exact snapshot/production commands.
- Exact-head review `20260923T022944-1710-21011` rejected commit `a1946b7` because legacy self-managed SQL transactions could separate effects from ledger records, guarded migration still seeded, cross-command comparisons lacked a consistent protected artifact, the guarded command was not assigned to package files/scripts, and unsalted unbounded row hashes leaked information. The correction adds classified legacy crash recovery versus atomic new migrations, migration-only production commands with seed spies, same-snapshot keyed bounded proofs chained through protected artifacts, and exact CLI/package ownership.
- Exact-head review `20260923T023736-338-26751` rejected commit `0c8030d` because fresh proof assumed `pgcrypto` before extension bootstrap, proof upload was not atomic with commit, CI still used old database/commands, and key/project/snapshot operations lacked named owners. The correction bootstraps `01_extensions` before HMAC, stores immutable proof rows atomically with ledger effects, migrates the exact CI/preparation paths, and names the proof-key, Supabase lookup, snapshot, wrapper, cleanup, and fault-test contracts.
- Exact-head review `20260923T024711-1543-26668` rejected commit `cb4f8a0` because generated Drizzle work was outside the recovery contract, catalog-only drift was not fingerprinted, proof expiry/key rotation could strand the chain, old migration callers remained, SQL tokenization and snapshot protection were underspecified, and database logs were not covered by secret-leak tests. The correction adds a resumable Drizzle/raw release ledger with every journal-boundary fault test, canonical row-plus-catalog roots, renewable versioned dual-signed proof keys, complete caller/doc cutover, a lexical tokenizer contract, encrypted/ACL-bound expiring snapshots, and database/log sentinel scans. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T030427-1632-10135` rejected commit `307a89b` because it blurred the merged base plan with the pending amendment, omitted view security and exact row/control-table encodings, lacked forward-only M0 recovery and canonical control DDL, left old production bypasses ambiguous, and assumed compatible local PostgreSQL tooling. The correction separates both publication states, fingerprints view security and explicit row/control manifests without self-reference, owns versioned bootstrap DDL, makes recovery forward-only, closes every old-entrypoint production bypass, and provisions a digest-pinned same-major socket-only PostgreSQL rehearsal container. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T031744-1249-22829` rejected commit `11b732b` because the snapshot transaction began before its advisory lock, `CLAUDE.md` still authorized a Supabase MCP bypass, the wrapper omitted protected production database-URL retrieval, and one shared identity-cleanup sorter was unnamed. The correction acquires a session lock before any snapshot and tests two runners, updates/scans every operator guide including `CLAUDE.md`, owns all three production secrets with separate leak sentinels, and migrates/tests the shared sorter. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T032828-120-28781` rejected commit `335f22d` because repository code cannot prevent Supabase-owner SQL, fresh setup omitted its sole bootstrap action, the socket-only container was unreachable from Windows host commands, and signing-key retirement had no exact policy. The correction limits prevention claims to a dedicated versioned migration-role/credential cutover and detects administrator break glass, adds fresh/snapshot bootstrap commands, exposes only a verified/firewalled ephemeral loopback port, and fixes proof/key audit retention at 400 days with boundary tests. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T033920-1527-22451` rejected commit `accf113` because M0 depended on a later SCRAM helper, rotating the live shared credential before Steps 1A–1D could outage web/workers, role/ownership changes contradicted the bootstrap allowlist, between-run row hashes could not distinguish legitimate traffic, and fresh idempotency was missing. The correction leaves credential/role cutover to its already ordered later phases, limits M0 to same-snapshot row effects plus cross-run catalog/control continuity, removes bootstrap role changes, and runs fresh idempotency explicitly. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T034808-1981-27919` rejected commit `7b073f0` because excluded proof fields were not bound through the full retained chain, catalog roots omitted non-view ownership and mutable sequence state, and retired-command scanning did not classify commands in five older project records. The correction verifies every retained proof with a full-prior-row digest and non-head tamper tests, fingerprints all ownership plus same-run sequence state/`setval`, updates active old guidance, and permits only hash-pinned line-level historical evidence. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T035748-1688-29143` rejected commit `670da84` because 400-day deletion could orphan the proof chain, container selection preceded protected production-version discovery, and the existing drift checker/CI plus migration 61 comment were omitted. The correction adds atomic signed retention checkpoints with crash/rotation tests, a protected read-only version preflight before container start, full Drizzle/raw/control/release/proof drift checks in existing CI, and a hash-pinned immutable-migration-comment exception. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T040717-73-2804` rejected commit `7ece417` because strict production drift in pre-merge CI was circular, standalone seeding could still write production, mutable-sequence locks conflicted with live traffic, and `MACRO_FIRST_REDESIGN.md` retained an active MCP bypass. The correction splits fresh candidate CI from post-deploy strict proof, makes seeding local/fresh-only with direct-entry tests, confines exact mutable-sequence proof to exclusive rehearsal while statically blocking production sequence mutations, and updates the missed active guide. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T041548-364-5498` rejected commit `de632b6` because several fresh verifiers still hard-coded `oracle_fresh`, the strict post-deploy artifact/waiter had no implementation or command, and two `AGENTS.md` incident commands escaped the history inventory. The correction moves every fresh verifier to one parsed dynamic-name guard, names/tests `wait-migration-release.ts` and its exact strict command/artifact, updates the active incident rule, and hash-pins only its two past-tense command lines. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T042414-1304-11274` rejected commit `f128b5d` because new M0 safety files escaped task classification, one fixture used the wrong migration 98 filename, advisory-lock acquisition was unbounded, and the 15-minute catalog check consumed the whole existing CI budget. The correction classifies/tests every runner/guard/proof/manifest/wrapper path as shared-db, uses the real deprecated-identity filename, enforces a 30-second lock deadline with stuck-holder tests, and splits a required 25-minute migration-proof job from ordinary 15-minute CI. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T043520-18-28188` rejected commit `7faf70d` because no single process owned rehearsal cleanup, snapshot dumping lacked protected target-verified credentials, several DB files escaped task gates, more eval/handoff history escaped scanning, and CI left no setup/teardown headroom. The correction adds one interruption-tested lifecycle orchestrator, pipes the exact target-guarded production URL into dump without exposure, strongly gates all top-level DB source/M0 wrappers, inventories every historical line individually, and gives the required migration-proof job an explicit 40-minute sub-budget. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T044818-106-20081` rejected commit `c6b0db2` because `pg_dump` could not share an in-memory verifier connection, baseline postconditions were not complete per migration, the new CI job was not proven required, M0 tests/access were unnamed, and definition of done omitted M0. The correction binds dump to a verified exported snapshot through a protected temporary libpq service file, requires total per-file predicates with partial-state tests, preserves the required `build` check as an aggregator, names every M0 suite/command/prerequisite/1Password item, and adds exact M0 completion criteria. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T045809-1629-30803` rejected commit `b855c35` because indirect sequence advances escaped textual scans, one destructive worker verifier trusted `DIRECT_URL`, clone restores lacked referenced roles, three safety scripts escaped task gates, and the protected check is actually `Build @oracle/web`. The correction instruments every migration in exclusive rehearsal and refuses any sequence-changing normal release, target-guards the worker verifier, recreates signed NOLOGIN shadow roles before ownership-preserving restore, gates all named scripts, and preserves/verifies the exact required check context before merge. None is accepted until the next exact-head review approves it.
- Exact-head review `20260923T051035-1771-5826` rejected commit `1a14481` because Ubuntu CI could not run Windows safety behavior, backward compatibility was only asserted, nested DB tests escaped task gates, and migration 13 retained an unclassified stale comment. The correction splits portable Ubuntu, real Windows-hosted guard, and 916-alien live rehearsal suites; adds static expand rules plus an exact-current-main application smoke against candidate schema; recursively gates DB source; and hash-pins the immutable migration-13 comment. None is accepted until the next exact-head review approves it.

## 5. Root causes and key findings

- Oracle pays generative-model prices for several closed decisions: entity selection, quote-candidate selection, contradiction category, extraction worthiness, relevance, and evidence support.
- Some classifications/confidence are supplied by the same generator that creates the claim. Deterministic gates prove occurrence and allowed IDs, but an independent semantic support signal can add a veto/review layer.
- MCP and domain routing rely on lexical heuristics that miss paraphrases and require synonym maintenance.
- Jev's documented $0.042/million input-token price makes high-volume bounded questions economically interesting, but it is English-first, literal, weak at math/dates, sensitive to noisy/adversarial state, and cannot generate text.
- Privacy is the first production blocker. “Not used for training” is not the same as zero retention; enterprise ZDR is the recommended requirement.
- The correct architecture is a separate observed decision client beside `OracleAIClient`, with pinned/versioned question packs, per-use-case thresholds, and current-path fallbacks.
- Active entity selection initially unions all current-selector results and uses Jev only to add/reorder allowed candidates; it is not a cost-saving replacement. Any replacement needs a new plan/status row after sealed held-out proof.
- Every activation uses disjoint tuning and sealed held-out evidence, predeclared sample/class counts, independent label checks for material gates, a total abortable deadline, explicit CI wiring, sync/batch parity where applicable, and fail-open behavior on any audit-record write failure.
- The foundation includes a narrow additive decision-audit migration; it does not overload generation runs. Active extraction skips are linked to exact messages and have a dry-run-first replay script, while contradiction negatives are durable only for the current claim hashes and pack/threshold versions.
- Every hard-negative gate keeps deterministic production canaries running through the old model, routes disagreements to the decision-review page, and automatically falls back to `shadow` on a safety miss or rolling threshold breach. Extraction dispositions belong to window-owner rows so overlap reconciliation cannot mark an already extracted message skipped.
- Pending calls are reaped after crashes; chat retries record both generation attempts and both Jev checks; typed subject links plus bounded retention prevent stale personal/source references.

## 6. Exact next steps

1. Create a new current-upstream worktree and read `AGENTS.md`, the approved plan's STATUS/M0 section, `packages/db/src/migrate.ts`, and `packages/db/migrations/sql/README.md`; declare the actual code task class before editing.
2. Execute **Step M0 only**: repair numeric raw-SQL ordering, land its CI verifier, complete independent review/PR/merge, then run and record the guarded production double-run proof. No Jev schema file belongs in that session.
3. Update the plan STATUS row, this workstream's successor handoff, and issue #14 with the M0 commit, checks, deployment/migration evidence, and exact production result. Keep issue #14 open.
4. Only after M0 is proven may separate sessions proceed to the vendor/privacy boundary and Step 1A. Continue one STATUS row and one unproven live outcome per session, re-reading downstream phases at each cut.

## 7. Constraints and gotchas in force

- Use a new current-upstream worktree for every write-capable session; never edit the dirty shared checkout.
- Declare task class and recheck before review, wait, ship, deploy, database, infrastructure, or production actions.
- One unproven live outcome per session; code without live proof gets exactly one owned leftover-proof issue.
- Never push directly to protected `main`; merge owned PRs outside DesignFlow.
- Secrets live only in 1Password `vibe_coding`; never print values.
- Pin `jev-1.13.0`; do not use a moving alias after threshold tuning.
- Fail open to current behavior on uncertainty/provider failure; never fail open past a safety/evidence gate.
- The additive decision policy/run/subject/adjudication/control-event/canary-counter/reservation schema, source-erasure trigger, durable document classification, and extraction-status constraint migrations in plan Steps 1/6 are required through the normal Oracle Drizzle migration path; do not add any other schema change without revising the plan and task class.
- Do not alter the active R2 prompt/matcher/route/budget/production behavior.
- Update the plan STATUS table after every executed step and retire predecessor handoffs under the successor rule.

## 8. Access and environment

- Machine: `916-alien`, PowerShell 7, Node 20+, pnpm 9.5.
- GitHub CLI is authenticated for `u2giants`.
- Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`; production `https://oracle.designflow.app`.
- Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`.
- Supabase project `eqccjfbyrywsqkxxpjvg`.
- 1Password vault: `vibe_coding`. Planned item: `TypeSafe AI - The Oracle`; do not assume it exists until Step 0.
- TypeSafe official docs and all exact local commands are linked in plan §§10–12.

## 9. Open questions and risks

- Will enterprise ZDR/DPA/security terms cover employee, company, personnel, and licensed data? If not, restrict or stop those pilots.
- Will Oracle's own labeled cases confirm vendor-reported price/latency and sufficient accuracy? If not, remove the pilot rather than lowering the gate.
- Can extraction/contradiction false negatives reach the required recall? They remain shadow/fallback paths until proven.
- Will Chinese and mixed-language inputs perform acceptably? They remain on current behavior unless separately measured.
- Could synchronous verification add more latency than its quality value? Measure p50/p95 and reject low-value placements.
- Feature-pack sprawl is a maintenance risk. Every rejected pilot must remove dead flags/code and preserve only its evaluation record.

## Part B — sub-agent audit record

### `jev_ai_core`

- Asked: audit only `packages/ai/**` for Jev opportunities and no-go boundaries.
- Did: inspected retrieval, prompts, routing, provider boundaries, evals, and entity planning; used child audits for non-overlapping prompt/retrieval/route scopes.
- Found: highest-value direct fits are entity selection, offered quote-candidate selection, extraction pre-triage, domain fallback, reranking, and typed post-classification. Provider adapters, generation, embeddings, schema repair, exact validation, and failure routing are unsuitable.
- Work: read-only; no branch commit or live work remains.
- Deliberately did not: implement or call Jev, alter prompts, or make security decisions.

### `jev_workers`

- Asked: audit only `apps/workers/**`.
- Did: traced extraction, document ingestion, contradiction, Recall, workflow/responsibility, Brain, taxonomy, and repair paths.
- Found: highest savings are message prefilter, contradiction negative-path screening, and live-intervention gate; strongest quality addition is independent claim support/auto-approval veto. Generation paths remain unsuitable.
- Work: read-only; no branch commit or live work remains.
- Deliberately did not: edit workers, deploy, or change production flags.

### `jev_web`

- Asked: audit only `apps/web/**`.
- Did: used non-overlapping child audits across MCP/chat, Teams/API, admin/upload, and review flows.
- Found: safest first pilot is MCP capability discovery; additional fits are chat grounding, entity selection, retrieval reranking, claim-review advice, entity dedup advice, A/B judging, and meeting triage. Auth, crypto, approvals, ingest decisions, MIME/binary validation, and text generation remain deterministic/current.
- Work: read-only; no branch commit or live work remains.
- Deliberately did not: edit web code, test live users, or expose company data.

### `jev_engines_db`

- Asked: audit Oracle engines, DB, shared, and auth.
- Did: traced claim classifications, contradiction policy, responsibility merge, entity resolution, review routing, synthesis guards, promotion, locks, and auth.
- Found: bounded claim classification, contradiction adjudication, merge routing, entity disambiguation, reviewer-group suggestion, and semantic support screening are possible; promotion, exact evidence, auth, permissions, and transactions must stay deterministic.
- Work: read-only; no branch commit or live work remains.
- Deliberately did not: propose DB fan-out changes or weaken provenance.

### `jev_ops_docs`

- Asked: audit configuration, docs, scripts, CI/deployment, observability, privacy, and eval assets.
- Did: confirmed Node compatibility, existing logging tables, secret/documentation locations, deployment gates, and the pinned responsibility baseline.
- Found: Jev needs a separate decision contract, existing run/context logging, pinned model, privacy gate, and cost-per-correct-decision evaluation. The R2 fixture offers a measurable offline test but must not disturb the active R2 workstream.
- Work: read-only; no branch commit or live work remains.
- Deliberately did not: create credentials, change CI, deploy, or approve vendor terms.

### `review_controls`

- Asked: read-only analysis of the latest review's settings, data-class, immutability, and adjudication-constraint findings.
- Actually did: no branch commit or file edit. No final report was recoverable before wrap-up; do not assume this dispatch cleared any finding.
- Found: the exact independent review remains the source of truth for this scope.
- Worktree/branch: no owned code change to retire.
- Deliberately did not: implement or approve database controls.

### `review_step6`

- Asked: read-only analysis of Step 6's durable capture signal, schema-first release ordering, and cross-run ownership.
- Actually did: no branch commit or file edit. No final report was recoverable before wrap-up.
- Found: these findings remain open and are the first concrete plan edits for the successor.
- Worktree/branch: no owned code change to retire.
- Deliberately did not: modify the plan, schema, or workers.

### `review_claims`

- Asked: read-only analysis of Step 5 metrics, Step 7 pre-promotion veto placement, and Step 8A pair-aware sweeps.
- Actually did: no branch commit or file edit. No final report was recoverable before wrap-up.
- Found: the quote-specific metric was drafted into the plan; Step 7 and Step 8A remain open.
- Worktree/branch: no owned code change to retire.
- Deliberately did not: edit claims/promotion/contradiction code.

### `review_retrieval`

- Asked: read-only analysis of Step 4 query provenance, Step 8B live-context provenance, and Step 9A enrichment order.
- Actually did: returned source-backed plan wording; no file edit or commit.
- Found: entity planning consumes up to three user turns; live Recall must freeze and link every recent/retrieved source; relationships/supports are unavailable until business-answer enrichment finishes.
- Worktree/branch: created a detached read-only `jev-review-retrieval-20260920` worktree; it contains no edits and is safe for a future cleanup session after verifying no process owns it.
- Deliberately did not: edit the plan or application.

### `review_mcp_docs`

- Asked: read-only analysis of MCP handler-level verification and documentation.
- Actually did: returned exact verifier/README coverage; no file edit or commit.
- Found: `verify:mcp` covered only the registry helper, while the real `tool_search` handler and README remained lexical-only. The partial plan repair now calls for a captured real handler with injected fakes and same-PR README updates.
- Worktree/branch: no owned code change to retire.
- Deliberately did not: edit or invoke MCP behavior.

### `resume_controls`

- Asked: verify findings 1/2/9/10 against current main and the partial repair.
- Actually did: read-only source/plan audit at `499d8b0`; no edits/commits.
- Found: settings and document boundaries were mostly repaired; the plan needed exact migration-owner/current-user semantics, per-column/state mutation allowlists, direct service-role tests, and exact same-run composite constraints. All are now drafted.
- Worktree: clean read-only analysis checkout; safe to retire after process verification.
- Deliberately did not: implement or approve database changes.

### `resume_step6`

- Asked: resolve durable capture, schema release order, and cross-run ownership.
- Actually did: read-only trace of worker/schema paths at `499d8b0`; no edits/commits.
- Found: current reconciliation filters one job run and scans JSON. The plan now adds Step 6A schema proof, indexed normalized membership across all runs, compatibility backfill/trigger, ordered locks, and server-owned `force_extract` from exact command/UI actions.
- Worktree: clean read-only analysis checkout; safe to retire after process verification.
- Deliberately did not: alter messages, batches, workers, or production.

### `resume_claims`

- Asked: resolve Step 7 pre-promotion and Step 8A pair selection.
- Actually did: read-only promotion/watcher trace at `499d8b0`; no edits/commits.
- Found: both workers currently promote before the proposed check, and the sweep excludes a whole claim when any contradiction exists. The plan now splits a review-hold schema step, fences support inside promotion before all mutation, and uses canonical exact-pair selection/redispatch regressions.
- Worktree: clean read-only analysis checkout; safe to retire after process verification.
- Deliberately did not: mutate claims/evidence or worker code.

### `resume_step9`

- Asked: reconcile the plan with PR #17 on current main.
- Actually did: read-only trace of reconciliation, rendering, review, retrieval, and tests at `499d8b0`; no edits/commits.
- Found: ordinary chat no longer has the plan's assumed draft/retry topology. Step 9 now reranks only no-attachment reconciled chat after enrichment, and 9B is a shadow audit of the real ledger/rendered answer with no second repair/bypass; attachments are separate.
- Worktree: clean read-only analysis checkout; safe to retire after process verification.
- Deliberately did not: change chat behavior or claim second live acceptance.

## Handoff self-audit

1. **Can a new developer continue without session context? Yes.** §§1–3 define the app, goal, current SHA, branch, issue, dirty-checkout blocker, no-code state, and active R2 collision.
2. **Can they continue as effectively as this session? Yes.** §§4–5 preserve the failed/rejected paths and every non-obvious architectural, economic, model, and privacy finding; Part B preserves every delegated audit's scope and conclusion.
3. **Is flawless-execution detail present? Yes.** §6 gives ordered next actions with proof gates; §§7–9 give rules, access, risks, and open questions; the linked plan contains exact files, tests, adversarial cases, rollout gates, and rollback.
4. **Would Albert see every decision by reading only §0? Yes.** The line-by-line sweep of §§1–9 and Part B found two decisions: vendor/data terms and capped spend, both in §0 with recommendations and blocked scope. The unrelated active R2 decision is also surfaced in §0 and explicitly assigned to its existing handoff. All other choices are settled and listed under “do NOT re-ask.”

Checklist result: all sections M0–9 exist, the owner sweep is complete, current-main drift and the rejected exact-head history are explicit, every review finding has a source-backed repair, exact next gates are runnable, secrets are location-only, and every sub-agent dispatch is separately accounted for. A new developer can resume from §6 without this chat after the M0 amendment's own exact-head approval and merge; the substantive plan is already merged, implementation remains open on issue #14, and work starts with M0. **Handoff self-audit re-passed on 2026-09-23.**
