---
summary: Dead ends and key findings copied verbatim from 16 handoffs retired 2026-11-11, when the owner declared the pre-Company-Map workstreams abandoned.
kind: archive
status: done
read-when: reconsidering an approach the old Oracle, Oracle 2 or Jev integration work already tried
---

# Retired handoffs of abandoned workstreams — dead ends and findings

On 2026-11-11 Albert Hazan answered "Yes, abandoned" (his chat, verbatim) to whether the old Oracle workstreams behind issues 14, 15, 24, 27, 50 and 58 are abandoned. Their handoffs, and three older ones with no issue from the same retired system, were deleted under the successor rule. Below, for each file: its issue and its "what did not work" and "findings" sections, verbatim. Every full file is recoverable with `git show dea3256c9ec1:<path>`.

---

## `HANDOFF.d/2026-08-06T1510Z-t16-codex-legacy-migrated-handoff.md`

Issue: none. Size 184997 bytes.

No numbered dead-end section. Headings, for recovery from git history:

- Current resume point after completion audit and Grok 4.5 review, 2026-07-29
- GAP-4 live gate released, production sample blocked, 2026-07-29
- GAP-2 live gate released, default intentionally off, 2026-07-29
- GAP-1 release state, 2026-07-29
- GAP-13 released, 2026-07-29
- GAP-12 released, 2026-07-29
- GAP-11 production lifecycle handoff, 2026-07-29
- Authoritative latest closeout — 2026-07-29
- Latest closeout — 2026-07-28
- Prior closeout — 2026-07-28
- Prior closeout — 2026-07-28
- Prior closeout — 2026-07-28
- Prior closeout — 2026-07-27
- Prior closeout — 2026-07-26
- Canonical plan registry
- What this application is
- What we set out to do this session, and why
- Current state
- Everything we tried that did NOT work
- Root causes and key findings
- Exact next steps
- Constraints and gotchas
- Access and environment
- Open questions and risks
- HANDOFF self-audit — 2026-07-28
- HISTORICAL PLAN UPDATE — 2026-07-21
- LATEST SNAPSHOT — Shape-aware reader Stage 2 deployed (2026-07-13)
- Macro understanding implementation — 2026-07-02
- ACTIVE (2026-07-06): Macro-first redesign → see `MACRO_FIRST_REDESIGN.md`
- ACTIVE (2026-07-06): Vision transcription & claim-extraction test plan → see `test_code_changes.md`
- Four model-adapter bugs fixed + extraction bake-off — 2026-06-26 (DONE: fixed, proven, deployed, prod set)
- Fail-loud routing + conversation-aware extraction completion — 2026-06-26
- Test plan run — 2026-06-26
- Current carried-over items — verified / cleaned up 2026-06-29
- Meeting transcript picker (2026-06-24)
- China bilingual claim layer — merged to main, migration applied; worker deployed (2026-06-20)
- 2026-06-16 extraction A/B + employee-access update
- Historical completed work / superseded notes
- What is done (since the prior HANDOFF)
- Recall.ai integration — how the pieces fit
- Tooling and identifiers
- Cert material (do not commit)
- Risks and unknowns
- Handoff completeness audit — 2026-07-26

---

## `HANDOFF.d/2026-08-06T1510Z-t16-codex-project-status-closeout.md`

Issue: none. Size 12937 bytes.

### 4. Everything we tried that did not work

The earlier session spawned a verification sub-agent for the retired Pop workflow harness. The
attempted Trigger `source-outline` dispatch aborted before it ran, so it provided no live proof.
When this session checked that agent (`019f2f6d-bc45-7941-9c9f-17e2cc9a061e`), it no longer
existed. Do not cite that agent or aborted dispatch as successful verification.

The old planned query expected the pre-Stage-3 `source_workflow_maps` shape and candidate
`workflowTrace` links. Current source and handoff history show that path was intentionally retired;
restarting it would test deleted ownership rather than the production architecture. The valid
replacement evidence is the 2026-07-07 workflow-reader gate and subsequent R0/R0.1 production
replays.

The R2 deeper-reader architecture itself did not meet its goal. Although its deterministic
inventory/repair controls passed local and CI checks, the single authorized production gate scored
12/30. It was not a token or cost exhaustion failure: the preceding evidence used only a fraction
of the available budget. The hard stop correctly prevented a second gate and any business-model
merge/apply.

### 5. Root causes and key findings

The original Pop failure was structural: image transcription and atomic extraction fragmented one
workflow into disconnected claims. The current source-workflow reader fixes that class by capturing
the graph once and validating exact evidence; see `evals/macro-first-battery.md` and
`MACRO_FIRST_IMPLEMENTATION_PLAN.md` sections 1 and R0.

Passing the process-diagram fixture does not prove general business understanding. The present
bottleneck is responsibility documents: strict field completeness and repair still fail to retain
enough correct owner/action/target/system/timing/direction records. The frozen production result is
12/30, so later durable business-model stages cannot safely proceed.

The project documentation has two time layers. `fix_enhancement.md` is diagnosis/history and its
old section 6.9 is not a current task list. Current authority is the status table at the top of
`MACRO_FIRST_IMPLEMENTATION_PLAN.md`, then the focused R2/reliability/deferred-gap plans. The
legacy handoff is valuable evidence but its older next-action blocks are historical.

---

## `HANDOFF.d/2026-08-27T1600Z-al8960ofc-claude-r2-reason-feedback-regressed.md`

Issue: none. Size 9488 bytes.

### 4. What did not work

Three gates, three failures: 22/30, 23/30, 13/30 against a threshold of 27. Nothing was retried and
nothing was tuned to flatter any number.

The third is a genuine self-inflicted regression, not just a miss. Worker `20260827.3` carried the
reason-code feedback; **all 192 completion outcomes came back `provider_failed` with `Responsibility
completion omitted seeds`**. The model stopped returning exactly one record per requested seed, so the
canonicalizer threw, both attempts of both batches failed, and the completion stage contributed
nothing — the 46 records are the base read alone. This happened on the EXHAUSTIVE batch too, where no
seed carried feedback, which rules out the feedback data and indicts the prompt.

Note for whoever handles the rollback next time: **Trigger.dev refuses to promote an older
deployment.** The rollback had to be a forward deploy of the reverted code.

Binding dead ends: do not relax the fidelity validator; do not weaken the matcher, key or threshold;
do not raise budgets, retries or concurrency; do not re-ask a rejected seed the SAME question (worth
nothing, measured); and do not grow the completion system prompt (worth catastrophically less than
nothing, measured).

### 5. Root causes and findings

Two cycles of findings still stand. The late completion pass had been starved and never ran; fixing it
was worth one row. The remaining losses are validator rejections with specific, already-audited
reasons.

The new finding is about the system itself, and it is the most valuable thing this run bought:
`RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT` is brittle under growth, and its failure mode is **total,
not gradual**. An addition that looked purely additive destroyed the one-record-per-seed contract
across every batch.

**Every deterministic gate passed on the change that caused this.** They test plumbing, not the
model's obedience. There is no check anywhere in this repo that a prompt edit still yields one record
per seed from a live model. That gap is why a broken prompt reached production.

---

## `HANDOFF.d/2026-09-20T1411Z-916-codex-connected-answers.md`

Issue: #15. Size 5299 bytes.

### 4. Failed approaches
Earlier July CLI used an old model/Windows sandbox and did not finish a useful release.
Those edits were superseded by current upstream. September audit showed that historical
R2 failure banners were stale: approved v2 rescored the same map at 23/25. Do not re-run
R2 or weaken its evidence checks to solve answer retrieval. A bigger prompt/model cannot
repair discarded context. Complete source audit evidence is retained in `bugs.md`.

### 5. Findings
Chat searched latest message only and printed relationship support IDs without premises.
PLM/file heuristics erased explicitly requested neighboring domains. Shared business
model proposals remain shadow-only. These findings justify repairing the answer path
while retaining approved-claim boundaries. Separate ingestion/Brain defects are not
included in this single-outcome release.

---

## `HANDOFF.d/2026-09-20T1411Z-916-codex-jev-integration-plan.md`

Issue: #14. Size 45120 bytes.

### 4. Everything tried that did NOT work

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

### 5. Root causes and key findings

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

---

## `HANDOFF.d/2026-09-22T2033Z-916-codex-live-proof-interrupted.md`

Issue: #15. Size 24909 bytes.

### 4. Everything tried that did not work

1. **Bigger/alternate model first:** rejected because the failure was discarded evidence and false
   absence language, not raw model capacity. The released answer ledger fixes the contract instead.
2. **Reuse July unfinished code:** rejected because September upstream superseded it.
3. **Call `/api/chat` directly from browser automation:** the browser safety layer rejected
   `javascript:`/scripted POST execution. Its instruction explicitly prohibited bookmarklets,
   developer console, raw browser protocol, or indirect workarounds. Do not retry them.
4. **Use the normal UI without modeling side effects:** rejected by independent review because
   `/api/messages` briefly inserts `pending` and schedules `lull-interjection`.
5. **Guard with Albert's typing row:** rejected because the normal UI deletes Albert's exact typing
   key after send, creating a race. The approved solution used a separate disabled synthetic
   employee key that the browser could not delete.
6. **Early production-proof plan drafts:** independent reviewer correctly rejected them for an
   unbounded pending-extraction interval, ambiguous browser-delete ordering, unproven channel-row
   mutations, unproven 60-second debounce, and guard expiry. The final plan bounded the two-hour
   guard, 90-minute proof, extraction-cron window, triggers/FKs, and immutable snapshots.
7. **Global time-window audit query:** it falsely treated unrelated scheduled contradiction checks as
   test audit rows. Scope audit by the isolated channel/message/call window instead. The Q1 context
   packs have `included_message_ids=[]`, so direct message-ID membership alone also misses them;
   the retained run was correlated through the exact answer time window and task/run records.
8. **Primary Gemini validation/repair attempt:** live HTTP 400, `INVALID_ARGUMENT`, because the strict
   schema produced too many serving states. Anthropic fallback succeeded and was recorded. Do not
   erase the failed attempt or assume the configured route equals the actual provider.
9. **Release-gate command sequencing:** an earlier PR used PowerShell semicolons, so a merge command
   ran after `ai-task-gates` returned STOP for an incorrectly declared `deployment` class. The issue
   records the incident. It was corrected by separately declaring the actual `production` class and
   checking each exit before the next command; never use command chaining across a protected gate.

### 5. Root causes and key findings

- Retrieval faithfulness and answer faithfulness are separate contracts. The live partial run before
  PR #17 had approved criteria/exceptions in context but still called them missing.
- The released reconciliation ledger in `apps/web/lib/business-answer-reconciliation.ts` forces each
  retrieved claim into an answer/gap decision, while `apps/web/app/api/chat/route.ts` renders approved
  statements/citations canonically and permits only bounded reviewed interpretation.
- The different-provider gate is live, but the Q1 proof exercised fallback: OpenAI produced the answer;
  Gemini could not serve the strict repair schema; Anthropic repaired successfully. A future code task
  should audit that schema class, but wrap-up scope froze new fixes.
- Q1 proves the production code can return a long, cited answer with 16 approved claims and a separate
  repair call. It does **not** yet prove holistic quality because the full answer and context were not
  independently scored.
- Q2 is the follow-up continuity test: `How does that affect the China team, and which responsibilities
  belong to Licensing, Design, Sales, and China?`
- Q3 is the held-out topic-reset test: `New topic: how should warehouse staff handle damaged cartons?`
  It must not inherit licensing/file context or assert globally that no procedure exists merely because
  bounded retrieval found none.
- `plan_connected_business_answers.md` is canonical for this slice. Its 2026-09-22 STATUS table now
  distinguishes released code from the partial live outcome; do not redo implementation steps 1–5.

---

## `HANDOFF.d/2026-09-28T0044Z-edge-dev3-codex-oracle-consultant-overhaul.md`

Issue: #24. Size 12079 bytes.

### 4. Failed approaches and exclusions

Historical prompt-only correction regressed the R2 responsibility result and was reverted, as recorded by the August handoff. September connected-answer code had landed but full live acceptance was still incomplete. Do not repeat those experiments to start this plan or present historical scores as current production measurements.

The proposal to make FalkorDB the only store was rejected: accepted evidence and checkpoints need independent recoverability. Graphiti's model-generated changes cannot directly update confirmed policy. Filled schemas and valid citation IDs do not establish truth. Jev is not needed to check missing fields or permissions. Running several memory frameworks together was rejected. Archived Open Deep Research is a design reference only. No paid benchmark or candidate deployment was performed during planning.

Routine research discovered stale links and misleading latest-release labels; the research report records the actual current repository snapshots and warns against interpreting a monorepo CLI tag or old Neo4j release as a deployable library version.

### 5. Findings and evidence

See plan §5 for exact source references. The existing prompt already investigates dependencies; relational process/object/relationship tables already exist; strict reconciliation and review already exist. Therefore simply buying a graph database or adding more prompts is not a demonstrated fix. The replacement makes connected processes, temporal evidence, corrections and measurable consulting outcomes explicit.

`apps/workers/package.json:37` pins Trigger.dev 4.5.15, despite older prose calling it v3. `apps/workers/src/trigger/document-ingestion.ts:186` already provides structure-aware text chunking; the new parser must demonstrate additional layout/region fidelity rather than falsely claim none exists. The actual shadow helper is `apps/workers/src/lib/business-model-merge.ts`, not a hypothetical responsibility-named file.

Research facts and design judgments are separated. FalkorDB server uses SSPL; its GraphRAG SDK has a different license. Graphiti is an Apache-2.0 library with temporal/candidate capabilities, not an enterprise authorization system. All these details and pinned references live in the research document.

---

## `HANDOFF.d/2026-09-28T0210Z-edge-dev3-codex-oracle-s01-to-s02.md`

Issue: #24. Size 9955 bytes.

### 4. What did not work

The independent reviewer rejected earlier S01 commits until these defects were corrected: relabeling a holdout case as development; listing a source with no span; changing case text and checksum together; repeating evidence; using only the first manifest version as a baseline; silently disabling baseline validation when Git history was absent; providing descriptions instead of adversarial input; and allowing meaningless placeholder inputs. The final validator reads the first committed manifest **of each version** from full Git history, fails closed when that history is missing, checks source coverage and fixture shapes, and has a direct test for each failure pattern. Do not revert to mutable checksums alone or a shallow-history fallback that silently accepts changes.

The public synthetic answer keys are visible. They are procedurally held out from development, not a secret benchmark. Real business keys must stay private. The existing PR workflow uses a shallow checkout and does not yet run the new Python gate; S02's planned CI integration must fetch full history. Avoid claiming CI ran that gate for S01.

### 5. Key findings

The existing answer path already has retrieval and citation reconciliation (`packages/ai/src/retrieval.ts`, `apps/web/lib/business-answer-reconciliation.ts`, and `apps/web/lib/__verify__/business-answer-journey.ts`). Those guards do not establish business comprehension. `evals/oracle2/acceptance-spec.md` defines human grading and access boundaries; `evals/oracle2/synthetic-cases.jsonl` contains the case/source data; `evals/oracle2/manifest.schema.json` and `scripts/oracle2/validate_manifest.py` define and enforce counts, spans, splits, versioning and adversarial payload shape. `docs/oracle2-baseline.md` defines equal-source comparison; `docs/verification/oracle2/S01-baseline.md` records actual availability. No company data or provider credential was accessed in S01.

---

## `HANDOFF.d/2026-09-28T1943Z-edge-dev3-claude-worker-release.md`

Issue: #50. Size 1526 bytes.

No numbered dead-end section. Headings, for recovery from git history:

- What this is
- State
- Next step

---

## `HANDOFF.d/2026-09-29T0251Z-edge-dev3-claude-s02-providers-release.md`

Issue: #24. Size 6542 bytes.

### 4. What did not work

- Qwen reviewer rejected dispatches 4–6 times on procedure; it is now
  quarantined ("live-qualification-required"); Grok was used next.
- Claude Code classifier blocks: self-hosted runner setup ("Create RCE Surface"),
  editing `verify_worker_bundle.mjs`, and production deploys — Albert did those.
- `op read 'op://…/Trigger.dev Personal Access Token (management)/…'` fails:
  parentheses are invalid in secret references; use the item id instead.
- `default_transaction_read_only` via the Supabase pooler did not take effect;
  use `conn.read_only = True`.

### 5. Key findings

- StepFun account limit: 10 requests/minute (429 "top up"). step-5-preview
  occasionally returns off-schema JSON; #51 retries once.
- Z.ai key works only on the Coding Plan endpoint; general endpoint says
  "Insufficient balance".
- Model evaluation (S02): primary `claude-sonnet-5`, fallback
  `gpt-5.5-2026-04-23`; Albert says these are too expensive — cheaper pair not
  yet chosen.

---

## `HANDOFF.d/2026-10-11T1641Z-edge-dev3-codex-holistic-original-readiness.md`

Issue: #27. Size 24765 bytes.

### 4. Failed attempts and dead ends

Legacy completed status and thin PDF text layers did not prove reading completeness.
Do not reuse old chunks as original evidence. Direct OpenAI's separate account
returned credit_balance_exhausted; do not retry known quota-only holds. Initial
OpenRouter visual attempts found genuine omissions; retain them and use the
qualified combined provenance rather than claiming failed attempts succeeded.
The funded key existed in the correctly named vault note, with extra surrounding
quotes. The operator initially missed it; the secure value and canonical references
were repaired without rotation. No actual key was printed.

GLM's earlier SDK-argument high finding was false: pinned web SDK 4.4.6 declares
trigger(id,payload,options,requestOptions). Its fourth argument is required for
dedicated clientConfig. Authenticated browser proof removes generic token fallbacks
and confirms this. Valid duplicate-delivery, timeout and deployment-entry findings
were repaired. Final low findings about prompt braces/nested directories/browser
coverage were repaired before the final APPROVE. Qwen allowance and StepFun credit
holds are known; do not retry them. GLM's sandbox cleanup warnings preserve orphan
copies; do not delete other sessions' recovery sandboxes to suppress warnings.

Local compose and CI share fixed ports: stop only this owned local project during
self-hosted CI, preserve volumes, restart after CI. Never run down --volumes on the
company workspace. PR #83's default CI project is distinct from the owned project.
The Vercel connector lacks permission; authoritative GitHub commit/deployment status
proved delivery. The system has no global vercel command; do not infer deployment
failure from that tooling absence. SSH defaults failed; the saved login metadata and existing password via protected injection work for read-only checks. Resolve the exact username/port from the vault item in §8; do not publish them.

### 5. Root causes and non-obvious findings

Whole original reading and holistic graph understanding are separate gates.
Confirmation of complete source reading establishes no company truth. Actual
GraphRAG extraction includes process steps, handoffs, responsibilities, rules,
exceptions, decisions, artifacts, dependencies and contradictions, with exact
source quotes. Immutable graph identity binds source revisions, parser, model,
configuration and implementation. Permission/revision changes invalidate readiness.

Source braces must be escaped before appending the SDK's own context/question
slots; literal source placeholders now survive the real integration. Duplicate
worker delivery cannot overwrite another worker's processing status. Pending and
processing expiry uses status timestamps, avoiding queue-age false timeouts.
Worker holds candidate-only and narrowly scoped PostgreSQL run/source permissions;
never give it confirmed projection, checkpoint, service-role, or owner-signing keys.

Historical pre-ruling OpenRouter key metadata: limit 15, remaining 0, reset daily, usage_daily
15.46848864. Account total credits 1335, total usage 1313.763795784. Key-specific
resets occur at midnight UTC, October 11 at 8:00 PM EDT. This is not subscription
billing. Do not represent account credit as exhausted.

Self-hosting is supported and already works locally. Read-only Hetz checks found
31,339 MiB RAM, 21,891 MiB available, 43 GiB disk free. Coolify server and destination were verified usable on the existing network; resolve their exact identities from protected discovery receipts, not public prose. No Oracle Coolify project/resource exists yet. No host mutation
has occurred. Preserve existing applications and runtime settings.

---

## `HANDOFF.d/2026-10-11T2059Z-edge-dev3-codex-workflow-integrity-plan.md`

Issue: #27. Size 12704 bytes.

### 4. Failed attempts and rejected paths

Prior prompt-only improvements did not repair artifact persistence. SDK endpoint
deduplication and repeated-label reconciliation lost distinct routes/claims;
recovery now retains occurrences and source observations. Duplicate uploads
amplified apparent source diversity. Audits stopped on output truncation, not a
demonstrated bad quote. Whole-corpus reruns waste already qualified readings.

Do not install five orchestration/catalog applications; generate executable
model code freely; infer observed event logs from SOPs; claim soundness proves
company truth; treat a missing quote as permission to invent one; resolve company
policy from a source review; or reopen stopped grading. The plan §7 records each
dead end and replacement, and §8 defines selected project patterns.

### 5. Root causes and findings

[ProcessModel lists](https://github.com/u2giants/theoracle/blob/36e91038ee6b1126f9d9c27adce7583a6b74c654/services/oracle-brain/oracle_brain/graph/graphrag.py#L158-L162)
are not converted by
[the graph return path](https://github.com/u2giants/theoracle/blob/36e91038ee6b1126f9d9c27adce7583a6b74c654/services/oracle-brain/oracle_brain/graph/graphrag.py#L419-L454).
An independently emitted CONTRADICTS relation can survive; do not say every
conflict is dropped. The in-memory readings cache is not a durable findings path.

[Existing entity/relationship kinds](https://github.com/u2giants/theoracle/blob/36e91038ee6b1126f9d9c27adce7583a6b74c654/services/oracle-brain/oracle_brain/graph/graphrag.py#L29-L31)
do not specify executable splits/joins/starts/ends/conditions. Responsibility and
dependency are not automatically control flow.
[Whole-original answering](https://github.com/u2giants/theoracle/blob/36e91038ee6b1126f9d9c27adce7583a6b74c654/services/oracle-brain/oracle_brain/graph/graphrag.py#L650-L680)
can hide graph omissions. New ledger→projection→retrieval→browser proofs must
test artifacts separately. Identifier-count seals also need payload hashes for
new findings, workflows and metrics. Plan §§6/8 specify exact contracts.

---

## `HANDOFF.d/archive-parent24/2026-09-29T2306Z-edge-dev-mimocode-s03-pilot-journey.md`

Issue: #24. Size 3587 bytes.

### 4. What did not work

- Local Postgres on Windows is unreliable (autovacuum crash 0xC0000142); full `verify_phase.py S03 --mode offline` needs the CI runner (edge-dev3) with Docker Compose stores.
- `ai-task-gates check --before pr` reports `unknown action: pr` — the CLI action vocabulary does not include "pr". Used `start --class code` at task declaration.

### 5. Key findings

- The existing `test_provider_policy.py` already covers all S03 gate cases for provider policy (unapproved fallback, changed endpoint/terms, expired scope, source text in telemetry).
- The S02 authority model (`appointments` table + `has_authority`) supports all five adversarial cases required by the S03 gate with minimal extension.

---

## `HANDOFF.d/archive-parent24/2026-10-01T1544Z-edge-dev-mimo-s03-coordination-wrapup.md`

Issue: #27. Size 16724 bytes.

### 4. Everything we tried that did NOT work

- **First spawn of all three sub-agents stalled** (status `idle`/`stopped`, no deliverable: no S03 code, #50 still open, handoffs unchanged). Parent resumed each with "finish or return verbatim blocker evidence." All three then completed. Lesson: always verify sub-agent output on disk/GitHub, never trust `success` alone.
- `ai-task-gates check --before shipment|merge|pr` → `unknown action`. Only `start --class <class>` works reliably. Classes: `code` for implementation, `prose` for docs/handoffs (found in `ai-devops-reviewer-install/config/task-gates.json`), `deployment` for deploys.
- Local Windows Postgres via scoop is unreliable (autovacuum `0xC0000142` crash). Full `verify_phase.py S03 --mode offline` needs the CI runner with Docker Compose stores — do not try to reproduce the gate on this machine.
- `npx trigger.dev@4.5.15 mcp --readonly` is the reliable Trigger read path; raw REST `/deployments` rejects unscoped params.
- `op read 'op://…/Trigger.dev Personal Access Token (management)/…'` fails: parentheses are invalid in secret references; use the item id instead.
- When adding npm deps, `pnpm-lock.yaml` must be updated or CI `--frozen-lockfile` fails immediately.

### 5. Root causes and key findings

- S02 authority model (`appointments` + `has_authority`) already supports all five S03 adversarial authority cases with minimal extension (`test_authority.py`).
- `test_provider_policy.py` already covered S03 provider-policy gate cases (unapproved fallback, changed terms, telemetry leak, no outbound on deny).
- A CI-caught `NotNullViolation` in `create_draft` was fixed post-push (`status='draft'`); faster than local pre-verify when local stores are unavailable.
- Handoff pile (11–12 files) is **not** a count problem (owner ruling 2026-08-13). Stale = issue already closed. Successor-rule condition 1 ("status line says committed and pushed") is why nothing could be deleted — owners must mark status when they ship.
- Squash-merged PR branches are deletable when `headRefOid` equals the branch tip and the PR is MERGED; branches without an exact PR head match must stay.

---

## `HANDOFF.d/archive-parent24/2026-10-06T1657Z-edge-dev-mimo-s03-acceptance-wrapup.md`

Issue: #58. Size 7832 bytes.

### 4. Everything we tried that did NOT work

- Local scoop Postgres on edge-dev (autovacuum crash); Docker Desktop winget (UAC exit 4294967291); WSL staged but needs reboot (`docker-s03-continue.ps1`).
- Codex plan-review: many REJECT cycles then “model at capacity”; Grok door `cancelled`; DeepSeek provider call failed.
- Multi-file admin upload single FormData → 413 non-JSON.
- `asJson` double-encoded jsonb → 500 on questions (fixed `sql.json` / `parseJson`).
- Invented 3-row process table + 24 questions **not grounded in ingested docs** (Albert rejected that methodology).

### 5. Root causes and key findings

- Platform request body limit (~4.5MB) vs one-request multi-file upload.
- Trigger dispatch depends on **prod** `TRIGGER_SECRET_KEY` on Vercel (incident 2026-06-04: dev key silently drops work).
- Thin pilot retrieval is keyword-overlap; almost never abstains on short tables — not proof of complex-topic understanding.
- Answer builder quotes process-table rows verbatim — **source table wording is the control point** for fact correctness.

---

## `HANDOFF.d/archive-parent24/2026-10-08T1739Z-edge-dev-mimo-s03-onsite-grading.md`

Issue: #58. Size 11777 bytes.

### 4. Everything we tried that did NOT work

- Vercel device-code login via isolated Playwright browser — no session (login pages only). Fixed by opening **Chrome** for Albert and running `vercel login` until signed in.
- `vercel redeploy --yes` — invalid flag; must pass a deployment URL.
- `psycopg2` / `pg8000` unavailable in system and `MIMO_PYTHON`. Used `psql` + `1password_op_run` instead. PowerShell heredocs do not work — generate SQL to a file, then `psql -f`.
- Claim wipe SQL: successive FK failures (`extraction_candidate_evidence` has no `source_claim_id`; then `extraction_validation_results` → candidates; then `section_claims`; then `gaps.related_contradiction_id` → contradictions). Each attempt rolled back. Final script handles the full FK list from `information_schema` (see `wipe-old-logic-claims.sql`).
- Markdown review packets for Ilona/Jessica — **wrong delivery**. Albert: tasks belong on the site (`claim_review_question` / `/claims`), as done before. Packets remain private reference only.
- Combined 8-doc consultant source: large business-process.md drowned LTR retrieval. Authoritative bank run used per-doc / paired-doc sources.
- Bash tool is PowerShell here: `export`, `<<heredoc`, and bare `VAR=1` lines fail and cancel sibling tool calls.

### 5. Root causes and key findings

- `pdf-parse` + Trigger esbuild = `__require.ensure is not a function` (webpack-only). `unpdf` is the serverless-safe replacement (`apps/workers/src/trigger/document-ingestion.ts`).
- Direct Supabase host `db.PRIVATE_REFERENCE_SHA256_9190ea2866aa7bf92e2806946d58e5728957851544cade4e900fa8436872652d.supabase.co` is IPv6-only from edge-dev; **session pooler** (`oracle_session_pooler` field on item `qcuyabwseaptvuzvtjejffi2ou`) works via psql.
- `document-ingestion-sweep` retries only `pending_processing`/`processing` — **failed** docs need a status reset.
- Admin → Documents writes production Supabase (`PRIVATE_REFERENCE_SHA256_9190ea2866aa7bf92e2806946d58e5728957851544cade4e900fa8436872652d`), not edge-dev3 Docker Postgres (oracle2 pilot store only; volume is ephemeral — re-compose + `oracle2-bootstrap-run.py`).
- `/claims` isolation is by `gaps.target_employee_id` + `claim_review_question` + status in open/queued/asked; two gaps on the same `related_claim_ids` collapse to one claim row — S03 assignments must use **distinct claims per item** (fixed 5 collisions).
- Trigger secret key vs PAT: `tr_prod_` / `tr_dev_` trigger runs; `tr_pat_` is management (deploys, envvars). CLI `whoami` rejects good PATs — verify via `GET https://api.trigger.dev/api/v2/whoami`.
- Consultant pilot engine is extractive (quotes blocks); rarely abstains on A-category items; attaches a standing hypothetical label to every answer.
