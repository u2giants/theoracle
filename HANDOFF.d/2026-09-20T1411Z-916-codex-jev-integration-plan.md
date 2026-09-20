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

- The primary read-only audit used upstream `63cdcaa`; before publication the plan was rebased and reconciled against current `origin/main` `824c1ff9f2caa47428c63df038d229a44e2db515`, including the newly merged connected-business-answer chat/retrieval path.
- No TypeSafe/Jev package, code, secret, setting, schema, deployment, or production call exists.
- The plan is written with all steps open and links back to this handoff.
- Issue #14 exists, is assigned, and tracks implementation.
- The publication branch is `codex/jev-integration-plan-final`; this handoff and plan are documentation only.
- The shared canonical checkout at `D:\repos\oracle` had six unrelated uncommitted pipeline files and was 141 commits behind when the audit began. It was preserved untouched. Implementation must use new current-upstream worktrees.
- The newest R2 responsibility handoff is still open and production is restored to its known-good 23/30 map. Jev's responsibility quote-selection work is evaluation-only and may not change that live path.
- Issue #15 and `HANDOFF.d/2026-09-20T1411Z-916-codex-connected-answers.md` own live proof for the newly merged cross-domain answer path. Jev retrieval/grounding Steps 9A/9B wait for that proof to close or be explicitly handed over.

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

1. Land this documentation-only plan and handoff. You'll know it worked when the PR is merged, issue #14 links to the plan, and `main` contains both backlinks.
2. In a new worktree/session, execute plan Step 0 and record the vendor/data/spend decisions. You'll know it worked when the issue records the boundary, the protected 1Password item exists if approved, and a test blocks disallowed data before network access.
3. In a separate code session, implement Step 1A only: the decision/control schema and RLS in a schema-only PR, then run and verify the guarded production migration before any reader merges. You'll know it worked when migration/drift and direct-access checks pass, production's journal/RLS state is proven, and the existing admin layout still loads.
4. In the next code session, implement Step 1B plus Step 2: versioned runtime data policy, document classification, decision client, concurrency-safe canaries, crash/retention maintenance, review/adjudication UI, and observability. You'll know it worked when concurrency/crash/retention/admin fixtures, the mocked contract verifier, package typechecks, redaction/failure tests, CI, and the post-deploy admin smoke pass with no product behavior change.
5. Run Step 3 as the first product pilot: MCP capability discovery. You'll know it worked when shadow results beat or match the lexical baseline, all safety constraints remain deterministic, and the single live behavior is proven or explicitly rejected.
6. Continue one STATUS row and one live outcome per session. Re-read all downstream phases before each start and update the plan immediately.

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

## Handoff self-audit

1. **Can a new developer continue without session context? Yes.** §§1–3 define the app, goal, current SHA, branch, issue, dirty-checkout blocker, no-code state, and active R2 collision.
2. **Can they continue as effectively as this session? Yes.** §§4–5 preserve the failed/rejected paths and every non-obvious architectural, economic, model, and privacy finding; Part B preserves every delegated audit's scope and conclusion.
3. **Is flawless-execution detail present? Yes.** §6 gives ordered next actions with proof gates; §§7–9 give rules, access, risks, and open questions; the linked plan contains exact files, tests, adversarial cases, rollout gates, and rollback.
4. **Would Albert see every decision by reading only §0? Yes.** The line-by-line sweep of §§1–9 and Part B found two decisions: vendor/data terms and capped spend, both in §0 with recommendations and blocked scope. The unrelated active R2 decision is also surfaced in §0 and explicitly assigned to its existing handoff. All other choices are settled and listed under “do NOT re-ask.”

Checklist result: all sections 0–9 exist, the owner sweep is complete, current/commit/push/deploy state is explicit, failed approaches and audit findings are preserved, every next step has a verification gate, secrets are location-only, and all sub-agent workstreams are accounted for. **Handoff self-audit passed on 2026-09-20.**
