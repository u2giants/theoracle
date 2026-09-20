# TypeSafe Jev Decision Layer Implementation Plan

Tracking issue: [u2giants/theoracle#14](https://github.com/u2giants/theoracle/issues/14)

Session handoff: [`HANDOFF.d/2026-09-20T1411Z-916-codex-jev-integration-plan.md`](HANDOFF.d/2026-09-20T1411Z-916-codex-jev-integration-plan.md)

Plan created: 2026-09-20

Source baseline: `origin/main` at `824c1ff9f2caa47428c63df038d229a44e2db515`

## STATUS — read this first

| Step | Status | Date | Evidence / owner |
| --- | --- | --- | --- |
| 0. Vendor, privacy, and test-data boundary | ⬜ open | 2026-09-20 | Issue #14; owner decision in §8 and §13 |
| 1A. Decision schema and production migration | ⬜ open | 2026-09-20 | Schema-only PR/outcome; must be migrated and verified before any dependent code merges |
| 1B. Decision-client foundation | ⬜ open | 2026-09-20 | Starts only after Step 1A production proof and Step 0's synthetic-only boundary |
| 2. Observability, cost, and failure contract | ⬜ open | 2026-09-20 | Must land with Step 1B or the client is not usable |
| 3. Low-sensitivity MCP capability-search pilot | ⬜ open | 2026-09-20 | Separate session and live-behavior outcome |
| 4. Bounded entity-selection pilot | ⬜ open | 2026-09-20 | Separate session and live-behavior outcome |
| 5. Responsibility quote-candidate evaluation | ⬜ open | 2026-09-20 | Separate session; must not alter the active R2 reader workstream |
| 6. Extraction prefilter shadow evaluation | ⬜ open | 2026-09-20 | Separate session and worker deployment outcome |
| 7. Claim-support and auto-approval veto checks | ⬜ open | 2026-09-20 | Separate session; veto/review only |
| 8A. Contradiction negative-path pilot | ⬜ open | 2026-09-20 | Separate session and contradiction live proof |
| 8B. Live-meeting intervention pilot | ⬜ open | 2026-09-20 | Separate session and Recall live proof; never combine with 8A |
| 9A. Retrieval-reranking pilot | ⬜ open | 2026-09-20 | Separate session and acceptance evidence |
| 9B-1. Chat-generation audit schema | ⬜ open | 2026-09-20 | Nullable output-hash schema-only migration/proof before dependent code |
| 9B-2. Chat-grounding pilot | ⬜ open | 2026-09-20 | Separate session after 9B-1 production proof and acceptance evidence |
| 9C. Advisory ideas disposition | ⬜ open | 2026-09-20 | Create separately scoped plans/issues or explicitly reject; no bundled implementation here |
| 10. Documentation, rollout reconciliation, and plan retirement | ⬜ open | 2026-09-20 | Close issue #14 only after every retained scope item is done or explicitly deferred |

Fresh-session rule: begin with the first open STATUS row, re-read that phase and every downstream phase before editing, and use the `fresh-session` skill at each marked context cut. Whoever executes a step updates this table immediately with a commit, test artifact, CI run, deployment ID, or exact rerunnable command. A bare count or issue number is not proof.

---

## 1. The ultimate goal

POP Creations should spend expensive generative AI only where the Oracle actually needs writing, synthesis, or open-ended extraction. Fast, cheap, typed judgments should handle bounded questions such as “does this segment contain operational knowledge?”, “which known entity is named?”, “does this evidence support the claim?”, and “which approved capability best matches this request?”

When complete, the Oracle will:

- make selected classifications, routing decisions, rankings, and verification judgments at a fraction of the present generative-model cost;
- preserve or improve evidence quality by adding an independent semantic check where today the same model both creates and scores its own output;
- expose probability, confidence, latency, token, cost, and resolved-model data for every Jev decision;
- fall back safely when Jev is uncertain, unavailable, rate-limited, or not approved to receive the data;
- never let Jev weaken exact-quote validation, permissions, lifecycle rules, human approvals, or transactional safeguards.

**If a step conflicts with this goal, the goal wins — stop and flag it.** Lower token price is not success if recall, evidence quality, privacy, or employee trust gets worse.

## 2. What this application is

The Oracle is POP Creations / Spruce Line's evidence-backed enterprise knowledge system. Employees ask questions through the web and Teams, and administrators upload documents and review extracted claims, gaps, contradictions, taxonomy proposals, and synthesized Brain sections. Every important answer is intended to trace back to approved claims and quote-level evidence.

- Repository: `u2giants/theoracle`
- Target branch: protected `main`; all work uses a feature branch and pull request
- Stack: TypeScript, Node 20+, pnpm/Turborepo, Next.js 16, Trigger.dev workers, Drizzle, Supabase
- Web production URL: `https://oracle.designflow.app`
- Vercel project: `prj_rP6Jlima7iK1paffEPhLqxlswGsC`
- Trigger.dev project: `proj_wgpzsvhmsopqhvwqaycn`
- Supabase production project: `eqccjfbyrywsqkxxpjvg` (`theoracle`, `us-east-1`)
- AI boundary today: `OracleAIClient` routes free-text or arbitrary structured generation through six direct providers: Anthropic, Vertex, Google, OpenAI, DeepSeek, and Qwen.

Jev is TypeSafe AI's text-only System One model. It does not write prose. It evaluates one text/JSON state against typed questions:

- `Choice`: one result from a known set, with probabilities and confidence;
- `Score`: a position on a defined ordered rubric, with probabilities and confidence;
- `Noul`: probability that a yes/no condition is true.

As documented on 2026-09-20, `jev-1.13.0` costs $0.042 per million input tokens, output tokens are free, the request limit is 64k tokens with a 32k state-plus-longest-question limit, and the primary training language is English. See [TypeSafe models](https://docs.typesafe.ai/models), [primitives](https://docs.typesafe.ai/primitives), and [known Jev 1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13).

## 3. What triggered this work

Albert requested a current review of TypeSafe AI / Jev and a whole-codebase audit to determine where its unusually low price could help the Oracle. The primary read-only audit ran against upstream `63cdcaa` on 2026-09-20 and covered `packages/ai`, workers, web/API/admin/MCP surfaces, Oracle engines, database/auth boundaries, documentation, deployment, and evaluation assets. Before publication the plan was rebased and reconciled against `824c1ff`, including the newly merged connected-business-answer retrieval/context/citation path.

The audit found real savings opportunities, but also a sharp architectural boundary: Jev is suitable for bounded semantic judgments, not generation. The Oracle currently pays generative models for several bounded decisions and sometimes trusts the generator's own confidence or classification. Other paths use brittle keyword/synonym heuristics that Jev could supplement. Conversely, the Oracle's highest-value work—claim discovery, exact evidence, workflow construction, chat, translation, and synthesis—cannot be moved to Jev without losing capability.

No Jev code, package, secret, setting, deployment, or production call exists yet. This plan is the build specification for issue #14.

## 4. Scope — in and out

### In scope

1. A separate TypeSafe decision client and typed question/result contract inside `@oracle/ai`.
2. Dedicated Oracle decision-run, subject, comparator, usage, cost, latency, health, and error observability for Jev calls, linked to existing generation model runs only when the current model supplies a comparator or retry.
3. Version-pinned, named, testable question packs with per-use-case thresholds and feature flags.
4. Shadow-first pilots, in this order:
   - MCP capability discovery;
   - bounded entity selection;
   - responsibility quote-candidate selection evaluation;
   - claim-extraction prefilter;
   - semantic claim/evidence support and auto-approval veto;
   - contradiction screening;
   - live Teams intervention screening;
   - retrieval reranking and chat-grounding verification;
   - the Jev decision/canary review and health workflow required by these pilots; broader admin advisory products remain deferred in Step 9C.
5. Privacy minimization, redaction where possible, version pinning, failure behavior, and rollback controls.
6. English and `zh-CN` evaluation where a use case can receive Chinese content.
7. Documentation and per-pilot live proof.

### Not in this plan

- Jev as a seventh `OracleProvider`, generative adapter, model-catalog entry, or auxiliary text-generation route.
- Replacing chat replies, claim discovery, claim summaries, reviewer questions, translations, transcript summaries, Brain prose, taxonomy naming, image transcription, workflow maps, responsibility records, embeddings, or JSON repair.
- Replacing exact quote/offset checks, source-pointer checks, schema validation, approved-status filters, permissions, authentication, direct-mention rules, safety confirmations, advisory locks, transactions, cooldowns, rate caps, or human approval.
- Automatically approving claims, merging entities, ingesting/dismissing meetings, assigning individual reviewers, or performing destructive actions from a Jev score.
- Reusing or overloading `model_runs` for Jev. Its required success boolean cannot represent a pending call, and its child tables have no durable policy-effect or subject-disposition contract. The foundation therefore includes the narrow decision-audit schema specified in Step 1.
- Changing the active R2 responsibility-reader prompt, matcher, budget, model, route, or production behavior. That workstream has its own plan and handoff.
- Moving every P2/P3 audit idea into production. Advisory pilots advance only when their measured value exceeds their complexity and privacy cost.

## 5. Current state of the code

### Repository and delivery state

- The plan baseline is clean `origin/main` at `824c1ff9f2caa47428c63df038d229a44e2db515`.
- There is no TypeSafe/Jev dependency or runtime integration.
- Issue #14 tracks this plan and is assigned to the originating Codex owner.
- This plan and its handoff are documentation-only; no code or production behavior is changed by landing them.

### Existing generation boundary

- `packages/ai/src/routes/types.ts:13` defines exactly six `OracleProvider` values.
- `packages/ai/src/providers/types.ts:153-184` defines the free-text/arbitrary-object provider adapter contract.
- `packages/ai/src/client/oracle-ai-client.ts:108-123` exposes `runText` and `runObject`; `runObject` accepts generated objects after schema validation, not semantic support validation.
- `packages/ai/src/routing/model-router.ts:107-140` selects the first successful configured generative route and uses fallbacks for provider failure, not task difficulty.
- `packages/db/src/schema.ts:1393-1417,1892-2020` stores generation-oriented model runs and usage. Those tables are useful dashboard precedents but cannot safely represent pending Jev decisions, behavior effects, source classifications, or replayable subject dispositions.
- `packages/db/src/schema.ts:1892-2020` provides usage detail, context-pack, and attempt records already used by production AI paths.

### Existing high-value seams

- Entity selection: `packages/ai/src/entity-planner-model.ts:55-154` asks a generative model to return known registry entities; `packages/ai/src/retrieval-plan.ts:227-276` still intersects the answer with allowed candidates.
- Domain routing: `packages/ai/src/retrieval-plan.ts:681-753,840-853` ranks domains with substring-hit counts; unmatched paraphrases fall back to broader search.
- Retrieval: `packages/ai/src/retrieval.ts:276-423` uses vector/text reciprocal-rank fusion plus a department bonus, then limits the result without a semantic reranker.
- MCP capability discovery: `apps/web/lib/mcp/registry.ts:67-98` uses token matching and maintained synonym groups.
- Chat output: `apps/web/app/api/chat/route.ts:223-315,515-663` now builds bounded cross-domain approved context, enforces known citation IDs, records coverage omissions, generates, and persists the answer; no independent semantic grounding judge runs before persistence. `apps/web/lib/business-answer-{retrieval,context,policy}.ts` is now part of this load-bearing path. Issue #15 still owns its release/live proof, so Jev retrieval/grounding work waits for closure or explicit handoff and may not alter that proof.
- Claim extraction: `apps/workers/src/trigger/claim-extraction.ts:361-468` sends every non-empty user segment to the extraction model. An unused message-triage route exists at `packages/ai/src/routes/catalog.ts:163-181`.
- Document extraction: `apps/workers/src/trigger/document-ingestion.ts:1057-1361` validates quote occurrence and taxonomy membership, but kind/domain/impact/confidence/sensitivity originate from the same extractor.
- Auto-approval: `apps/workers/src/lib/document-claim-auto-approval.ts:26-76` combines deterministic gates with the extractor's own high confidence; there is no independent semantic evidence-support veto.
- Contradiction watcher: `apps/workers/src/trigger/contradiction-watcher.ts:155-232,450-452` invokes a generative adjudicator for every vector-shortlisted pair.
- Live Recall: `apps/workers/src/trigger/teams-live-recall-utterance.ts:292-318,450-558,756-900` uses a keyword/length pre-gate, then a generative model to decide and draft.
- Responsibility quote repair: `packages/ai/src/prompts/workflow-read.ts:71-80,242-273` already constrains selection to offered exact quote candidates, which is a direct `Choice` shape.
- Deterministic evidence: `packages/oracle-engines/src/extraction/quote-validator.ts:48-299`, taxonomy/promotion validators, synthesis support-ID checks, auth linking, and transaction paths are authoritative and must remain so.

### Existing evaluation and active-work constraints

- `evals/r2-responsibilities.md` and `apps/workers/src/__verify__/r2-responsibility-reader.ts` hold the pinned responsibility evidence and matcher history.
- `evals/bakeoffs/workflow-read.md:28-36` records a GPT-4.1 responsibility baseline of 22–23 calls, 55,620–58,923 input tokens, and $0.278–$0.295.
- The newest open R2 handoff, `HANDOFF.d/2026-08-27T1600Z-al8960ofc-claude-r2-reason-feedback-regressed.md`, says production is restored to a known-good 23/30 map and that continuing its reason-feedback work needs an owner decision. Jev evaluation may read immutable fixtures but must not edit or deploy the R2 reader path.

## 6. Key findings and root cause

1. **The cost opportunity is real but narrow.** Jev's price is roughly two orders of magnitude below typical generative input prices, but it cannot write strings. Savings come from replacing or prefiltering bounded judgments, not from moving Oracle's core generation.
2. **Several current calls are decision-shaped.** Entity selection, quote-candidate selection, contradiction category, extraction-worthiness, relevance, evidence support, and review routing all have finite answer spaces that map directly to Noul/Choice/Score.
3. **Some current safeguards are circular.** The extractor creates a claim and supplies its confidence, kind, domain, impact, and sensitivity. Deterministic validators prove quote presence and allowed IDs, but not always whether the quote semantically supports the summary. An independent cheap judge can add value without becoming authoritative.
4. **Heuristics create recall and maintenance pressure.** MCP capability search and domain inference use token/synonym/substring rules. Jev can add paraphrase understanding while code preserves an exact fallback.
5. **Jev probabilities are not permissions.** Type-safe output guarantees shape, not truth. Choice confidence measures distribution concentration; Noul has no separate confidence. Every use case needs its own threshold, labeled evaluation, and uncertainty behavior.
6. **Large/noisy state reduces accuracy.** Jev 1.13 is documented as literal, weak at arithmetic/date comparison, vulnerable to adversarial state, and less accurate when irrelevant context grows. The Oracle must shortlist/filter deterministically before asking it.
7. **Privacy is the first production gate.** TypeSafe says customer inputs are not used to train model weights, but normal retention is not equivalent to zero data retention; enterprise ZDR and contract/DPA terms must be approved before employee conversations, claims, evidence, or personnel information leave the current provider boundary.
8. **The integration belongs beside—not inside—the generation adapters.** Forcing Jev into `generateText`/`generateObject` would misrepresent its contract, contaminate route/model capability logic, and invite accidental use for generation.

## 7. Approaches considered and rejected

| Rejected approach | Why it looked attractive | Why it is rejected |
| --- | --- | --- |
| Add `typesafe` to `OracleProvider` and implement another provider adapter | Reuses existing router and settings UI | Jev cannot satisfy `generateText` or arbitrary schema generation. It needs typed questions and probability results, not a fake generated object. |
| Replace claim extraction, workflow reading, chat, translation, or synthesis | Jev is extraordinarily cheap | These tasks must discover or write text/records. Chaining Choice calls to generate text is explicitly unsupported and would reduce capability. |
| Replace exact evidence/provenance checks with semantic probability | A semantic judge can catch unsupported claims | Exact occurrence, offsets, source IDs, approved status, permissions, and transactions are guarantees. Probability may add a veto/review signal but never replace them. |
| Enable a production skip gate immediately | The prefilter could save the most money quickly | A false negative silently loses knowledge. Shadow evaluation must first prove recall and threshold behavior on Oracle data. |
| Use one global confidence threshold | Simpler configuration | Risk differs by action. Routing an MCP search is recoverable; suppressing extraction or a severe contradiction is not. Each question pack needs independent thresholds. |
| Use `jev-latest` | Automatically receives improvements | Alias movement can invalidate tuned thresholds without a code change. Pin `jev-1.13.0`, log the resolved model, and upgrade through an explicit eval. |
| Send entire transcripts/documents as state | Maximizes available context | It increases privacy exposure, cost, and context rot. Deterministically shortlist the smallest sufficient text and metadata. |
| Ask Jev to count, calculate dates, enforce limits, or infer API capability | It understands text and returns scores | Jev 1.13 is weak at numeric/date precision; code and live API probes are authoritative and cheaper. |
| Start with live Teams or HR/sensitivity text | High call volume demonstrates savings | It is the most privacy-sensitive and operationally risky state. Start with synthetic/low-sensitivity capability routing, then graduate deliberately. |
| Modify the active R2 responsibility prompt while evaluating Jev | The pinned fixture is already available | The R2 workstream is separately governed and recently regressed. Jev evaluation must be additive and offline until that workstream is settled. |
| Treat TypeSafe marketing benchmarks as Oracle proof | Vendor reports strong speed/cost results | Oracle must measure accuracy, abstention, p50/p95 latency, total cost, and cost per correct decision on its own labeled cases. |

## 8. Design decisions already made

### Locked decisions — do not relitigate during implementation

1. **Separate decision boundary.** Add an `OracleDecisionClient` (name may vary only to match existing naming conventions) under `packages/ai/src/decisions/`. Do not extend the generation-provider adapter map.
2. **Official SDK and pinned model.** Use `@typesafe-ai/sdk`, pin `jev-1.13.0`, and make the fetch/client injectable for deterministic tests. Do not use community CLIs or an alias in production.
3. **Code owns policy.** Jev returns typed judgments and probabilities. Deterministic code decides whether to keep the current path, request review, or invoke a generative model.
4. **Shadow first.** Every use case initially records what Jev would have decided while preserving current behavior. Activation requires a written acceptance artifact and its own PR/session.
5. **Fail open to present behavior.** Timeout, overload, 429, malformed response, unavailable key, low confidence, or unsupported language must preserve the current code path. “Fail open” never means bypassing safety; it means do what Oracle already does today.
6. **No weakening of guarantees.** Jev may add a hold/veto/review signal. It may not bypass evidence, permissions, approvals, direct-mention rules, cooldowns, caps, or database guards.
7. **Per-use-case contracts.** Each question pack has a stable ID, version, exact instructions/criteria, state builder, threshold policy, feature flag, and test/eval artifact.
8. **Minimal state.** Send only the shortlisted text and metadata needed for that decision. Do not send binaries, full documents, raw attachments, or unrelated history.
9. **Complete observability.** Log provider `typesafe`, requested and resolved model, question-pack ID/version, input/output tokens, computed cost, latency, probabilities, confidence where applicable, outcome, threshold path, error class, and whether the result affected behavior.
10. **Dedicated decision-control schema.** Add the policy/run/subject/adjudication/control/canary tables specified below in the foundation migration; do not overload generation-oriented `model_runs`. No business claim, contradiction, message, or permission rule moves into these tables.
11. **No autonomous governance.** Claim approval, entity merge, meeting ingest/dismiss, reviewer assignment, and translation acceptance remain human/deterministic decisions.
12. **One production outcome per session.** MCP, entity selection, extraction prefilter, contradiction gate, live Recall gate, reranking, and grounding are separate implementation/live-proof sessions.
13. **Separated tuning and acceptance evidence.** Thresholds are chosen only on a versioned tuning set. Activation is judged on a sealed held-out set that was not used to write prompts, choose thresholds, or select examples. Each pilot records its minimum sample and class counts before the held-out run; material gates double-label at least 20% of cases, report agreement, and adjudicate disagreements before scoring.
14. **Audited effects only.** A Jev result may affect behavior only after its final dedicated decision row, typed subject links, usage, bounded answers, and policy outcome commit successfully. Any audit-persistence failure discards the Jev result and preserves the current path.
15. **Hard-negative canaries never stop.** Any active Jev decision that suppresses extraction, contradiction adjudication, or live-meeting analysis must atomically reserve the stated first-N ISO-week minimum (or all negatives when traffic is lower) and every tenth later negative into the unchanged current model path. Every disagreement plus at least 10 atomically reserved agreements per use case per ISO week (or all when fewer exist) enters human review, so shared model blind spots remain measurable. A human-confirmed safety miss or rolling error threshold automatically changes only that use case from `active` to `shadow` and alerts admins. Frozen acceptance is necessary but never substitutes for production drift detection.

### Open owner/business decisions

1. **Vendor/data approval:** approve a TypeSafe commercial account and the contract/DPA/security posture needed for Oracle data. Recommendation: require enterprise zero-data-retention terms before sending employee messages, company claims/evidence, licensed documents, or personnel data. This blocks Oracle-data pilots, not the synthetic client/harness work.
2. **Initial spend control:** approve an initial capped evaluation balance. Recommendation: $5 is ample for the planned shadow evaluations at the documented token price; increase only after measured value.

### Open implementation judgments with fixed criteria

- The exact class/file names may follow local conventions, but the separate decision boundary is locked.
- Direct SDK calls versus a tiny local wrapper are an implementation detail; the wrapper must expose injectable transport, redacted errors, and normalized Oracle usage.
- A use case may be dropped if its measured savings or quality gain does not justify added latency/privacy/maintenance. Record the negative result; do not lower the gate to force adoption.
- Unless a step states a stricter requirement, the held-out set has at least 100 cases and 25 cases in every safety-critical positive class. MCP and entity selection each use at least 100; extraction uses at least 200 with 50 high-value positives; claim support uses at least 150 with 50 unsupported/contradicted/qualified cases; contradiction uses at least 150 with 50 material contradictions. The immutable 30-case R2 fixture is held-out only; build a separate tuning set.

## 9. The plan — ordered, executable phases

### Phase A — Safe foundation

#### Step 0 — Establish vendor, privacy, and test-data boundaries

**Change / action**

- Record the owner decisions from §8 on issue #14.
- Complete the TypeSafe contract/DPA/security review before any Oracle company data is sent.
- Create a 1Password item in vault `vibe_coding` named `TypeSafe AI - The Oracle` with the server-side API key and notes identifying the approved data-class set and retention mode. Never put the value in chat, shell arguments, logs, screenshots, or Git.
- Until approval, use only repository-owned synthetic/public fixtures. `public_synthetic` is granted only by an exact code-owned fixture builder and expected fixture hash; it can never come from a caller flag, origin label, request text, or semantic inspection. Any altered fixture, appended context, or caller-supplied lookalike is classified through its real provenance and gains `unknown_restricted`. Do not assume an existing `TYPESAFE_API_KEY` is approved for company data.
- Record an explicit allow/deny matrix for `public_synthetic`, `internal_company`, `employee_communication`, `licensed_content`, `personnel_hr`, `customer_personal`, and `unknown_restricted`. Approval of one class never implies another; mixed input is allowed only when every derived class is allowed. `unknown_restricted` is denied by default.
- Record the approved matrix/evidence on issue #14 in Step 0. After Step 1 creates the schema, materialize it as a new immutable `oracle_decision_data_policies` version through the guarded admin control before any company-data pilot. Until then, runtime recognizes only seeded `v1-public-synthetic`; issue/1Password notes are evidence references, not the enforcement source.
- Record the trusted provenance mappings used by `data-classification.ts`; do not rely on semantic guessing or on a caller-provided downgrade. Where a document/source lacks durable classification metadata, leave it `unknown_restricted` until Step 1's reviewed admin classification flow writes an explicit value.
- Record the initial spend epoch approval (recommended cap: $5) on issue #14. Step 1B materializes it through the guarded admin action only after the permanent ledger exists; no active epoch is seeded by migration and no TypeSafe call can occur without one.

**Dependencies / parallelism**

- Synthetic client/harness work in Step 1 may proceed before vendor approval.
- Every Oracle-data pilot waits for the contract/DPA and credential note.

**Verification gate**

- Issue #14 contains the dated approval or explicit synthetic-only limitation.
- The 1Password item exists by title and field presence; no value appears in terminal output.
- Tests prove every unapproved member of the derived class set, mixed-class input, unknown provenance, and a falsified caller downgrade are refused before any network call.

**Natural cut:** end the session here if the owner/vendor decision is not complete. Do not pretend synthetic success authorizes company data.

#### Step 1A/1B — Add the decision schema, then the client foundation

**Files/functions**

- `packages/ai/package.json`: add pinned compatible `@typesafe-ai/sdk`; update `pnpm-lock.yaml` through pnpm, never by hand.
- New `packages/ai/src/decisions/types.ts`: define `DecisionState`, question-pack metadata, Noul/Choice/Score request types, normalized answer types, resolved model, usage, latency, raw-response boundary, derived data-class set, and policy outcome.
- New `packages/ai/src/decisions/typesafe-client.ts`: wrap `TypeSafeClient.systemOne`, default to the pinned model, inject the SDK client/fetch for tests, normalize errors, and calculate input cost from the documented price.
- New `packages/ai/src/decisions/question-pack.ts`: require stable pack ID/version, an approved data-class allowlist, expected language, complete question meanings, and a caller-approved total deadline. Build the final serialized SDK request before network access and enforce conservative UTF-8 byte ceilings of 64,000 total and 32,000 for state plus the longest serialized question, plus `MAX_QUESTIONS_PER_CALL=100`, the 255-option Choice limit, and Score levels restricted to the documented inclusive range 2–10. These byte caps intentionally underuse the documented token allowance rather than depend on an unavailable tokenizer. IDs are audit identifiers, not hidden instructions.
- `packages/db/src/schema.ts` plus a new generated Drizzle migration and, where constraints/triggers need it, a new hand-written migration under `packages/db/migrations/sql/`: add all nine decision-control tables, document columns, FKs, indexes, checks, and erasure trigger specified below through the repository's normal `pnpm db:generate` / `pnpm db:migrate` journaled path. Add every new hand-written migration and its purpose to `packages/db/migrations/sql/README.md` in the same PR. Never use `drizzle-kit push` or Supabase `apply_migration`.
  - `oracle_decision_data_policies`: immutable version, immutable allowed class set, contract/evidence URL, approver FK `ON DELETE SET NULL`, approved/revoked timestamps, and status. Seed only `v1-public-synthetic`; a partial unique index permits one active policy. Revocation may set status/revoked time and writes a control event, but widening requires a new version—never an in-place class-set edit.
  - `oracle_decision_spend_epochs`: immutable epoch ID, cap in integer microusd, atomically maintained reserved/spent microusd, status (`active|closed`), approver employee FK `ON DELETE SET NULL`, approval/control-event evidence, and created/closed timestamps. A partial unique index permits one active epoch. No automatic date rollover exists; closing/raising/replacing an epoch requires a new owner-authorized admin action and control event. Rows are retained permanently because they contain no source text/IDs beyond nullable approver and are the durable no-refill ledger.
  - `oracle_decision_runs`: `id`; optional `parent_decision_run_id` self-FK `ON DELETE SET NULL`; nullable `spend_epoch_id` FK `ON DELETE RESTRICT` (allowed null only for a pre-network `budget_blocked` result; a check requires it for every attempted call); `use_case`; `question_pack_id`; `question_pack_version`; `threshold_policy_version`; `data_policy_version` FK `ON DELETE RESTRICT`; `activation_generation`; `mode`; requested/resolved model; provider request ID; `input_hash`; `decision_key`; nullable `effective_config_fingerprint` set only after resolved-model validation; `data_classes_json`; `deadline_at`; `status` (`pending|succeeded|failed|discarded`); nullable `discard_reason` (`process_interrupted|source_erased|superseded|policy_revoked|control_changed|budget_blocked|invalid_response`); bounded option-ID/probability `answers_json`; `policy_outcome` (`shadow_only|fallback|continue_current|skip_current|rerank|retry|refuse|review`); `affected_behavior`; `is_canary`; input tokens, maximum billable attempts, `reserved_cost_microusd`, actual cost, `spend_settled_at`, latency fields; error class/redacted error; comparator kind/version/status (`not_sampled|pending|completed|failed`), bounded comparator outcome, agreement status (`unreviewed|agree|disagree`); optional `review_status` (`open|resolved|dismissed`), reviewer FK with `ON DELETE SET NULL`, `current_adjudication_id`, `adjudication_version` default 0, review reason code, review timestamp; created/completed timestamps. No free-text reviewer note or raw state is stored. Durable identity includes `use_case`, mode, activation generation, exact `input_hash`, decision/pack/threshold/data-policy versions, requested model, and eventually resolved model. A partial unique constraint over all pre-resolution fields including `input_hash` and activation generation where status is `pending OR succeeded` prevents a second provider call during/after success; failed/discarded rows release it. Reuse additionally verifies the stored resolved model exactly; an upgrade changes requested model/pack and every activation/reactivation increments generation.
  - `oracle_decision_query_origins`: short-lived request-envelope records for query-derived calls, with `id`, origin kind (`mcp_request|chat|worker_source|synthetic`), optional `requesting_employee_id` FK, random per-request nonce for machine-to-machine MCP, `expires_at`, and created timestamp. Store no query text or query hash here. The decision separately links **every** contributing source message/chunk as subject rows, not only the latest message; MCP creates an origin that expires no later than 24 hours because its static bearer token cannot identify an employee; synthetic probes use `synthetic` and public data only. Deleting/expiring an origin or any contributing source invokes the same source-erasure invalidation. A query-derived company-data decision without an origin and complete contributing-source set is blocked before network access.
  - `oracle_decision_subjects`: `decision_run_id`, `effect`, and exactly one typed nullable target among FKs `query_origin_id`, `message_id`, `claim_id`, `claim_evidence_id`, `document_id`, `document_chunk_id`, `extraction_batch_id`, `extraction_candidate_id`, `extraction_candidate_evidence_id`, `entity_id`, `macro_relationship_id`, `model_run_id`, or bounded `eval_case_key` / `entity_query_key`; a check constraint requires exactly one target. Each FK deletes only its subject-link row when the source is erased. Uniqueness is `(decision_run_id, effect, target)` for each column; target lookup indexes are deliberately non-unique so one source can participate in many decisions. A decision run may have zero subject rows only for an exact repository-owned public-synthetic contract/live probe; its `decision_key` includes the fixed fixture hash.
  - Hand-written trigger `oracle_decision_subject_erasure`: when any source-bearing subject link (query origin, message, direct claim, claim evidence, document/chunk, candidate evidence, entity, relationship, or generation model run) disappears through FK cascade, atomically mark its run `discarded/source_erased`, dismiss an open review, and delete all remaining subject links—including parent/batch/entity links—so the daily orphan cleanup can remove the run. Decision-run retention cascades are exempt to avoid recursion. Deleting either claim in a multi-claim contradiction decision or any entity candidate supplied to a selection decision invalidates the whole judgment. This makes direct database source erasure safe without relying on application code.
  - `oracle_decision_adjudications`: append-only human labels for a decision run: reviewer FK `ON DELETE SET NULL`, verdict/reason code, `safety_miss`, created timestamp, and optional `supersedes_id`. A partial unique constraint permits only one child per non-null `supersedes_id`; `oracle_decision_runs.current_adjudication_id/adjudication_version` identifies the sole head. Never update an adjudication; rolling health uses only that locked head, never the comparator model alone.
  - `oracle_decision_control_events`: append-only manual/automatic mode-transition and alert record with use case, actor employee FK `ON DELETE SET NULL` or system actor, optional document FK `ON DELETE SET NULL`, event type, evidence URL/review commit/data-policy version where applicable, bounded previous/new document class sets plus classification reason code, measured numerator/denominator/threshold for health events, previous/new mode and activation generation, triggering decision/adjudication FKs `ON DELETE SET NULL`, acknowledgement state, and timestamps. Snapshot the bounded aggregate/reason so the event remains intelligible after referenced run retention; document deletion nulls its ID and retains no filename/text. Every mode/classification compare-and-set and event insert occur in one transaction.
  - `oracle_decision_canary_counters`: `(use_case,config_fingerprint,iso_week_start)` primary key plus atomically incremented negative-seen, canary-reserved, and agreement-review-reserved counts. The fingerprint hashes pack, threshold, data-policy, requested model, approved resolved model, and activation generation. It stores no source text/IDs and expires after 90 days.
  - `oracle_decision_canary_reservations`: unique `(use_case,config_fingerprint,iso_week_start,decision_key,input_hash)` plus sequence number, `is_canary`, and `agreement_review_reserved`. Counter increment and reservation insert are one transaction; conflict returns the existing reservation without incrementing. It stores only hashes/booleans and expires with its counter after 90 days.
- Enable row-level security on all nine new `oracle_decision_*` tables in the foundation migration. Follow the repository's existing intelligence-table pattern: deny anonymous access; authenticated non-admin users can neither select nor mutate; authenticated admins may select the bounded audit/control data needed by the admin UI; browser roles never insert/update/delete; trusted server/service-role paths perform validated mutations. Keep the admin check in RLS as well as in server actions so direct database access cannot bypass it.
- Extend `documents` in the same governed schema change with `decision_data_classes` (validated non-empty allowed text array, default `['unknown_restricted']`), `decision_classification_version`, `decision_classified_by` FK `ON DELETE SET NULL`, and `decision_classified_at`. Existing rows backfill only to `unknown_restricted`; never infer licensed/internal status from filename, uploader, or content.
- Add admin-only classification controls in `apps/web/app/admin/documents/page.tsx` and `_actions.ts` that select one or more allowlisted classes, require the current data-policy version and a bounded reason code, and atomically write the document plus a control event carrying its typed document FK and bounded before/after class sets/reason. Reclassification cannot make an active Jev call retroactively valid; future calls load the stored current value. Bulk auto-classification is out of scope.
- New `packages/ai/src/decisions/data-classification.ts`: derive a **set** of source classes from trusted provenance, never from a caller assertion. Initial classes are `public_synthetic`, `internal_company`, `employee_communication`, `licensed_content`, `personnel_hr`, `customer_personal`, and `unknown_restricted`; the effective class set is the union of every input/source class, and any missing/unknown provenance adds `unknown_restricted`. Only the exact repository-owned fixture builder/hash may contribute `public_synthetic`. Until a separate reviewed entity-type mapping proves a narrower rule, all registry entity values, labels, and aliases conservatively add the full possible registry union `internal_company`, `licensed_content`, `personnel_hr`, `customer_personal`, and `unknown_restricted`; the entity type or text itself cannot downgrade that set.
- New `packages/ai/src/decisions/data-policy.ts`: load the exact active policy version named by the use-case setting; before inserting a pending run, prove the pack allowlist and derived actual class set are both subsets. Record that version on the run. A revoked/missing/mismatched policy blocks before network access and executes the current path; changing policy never silently widens a previously reviewed pack.
- New `packages/ai/src/decisions/index.ts` plus `packages/ai/src/index.ts`: export only the decision API; do not expose the SDK throughout apps/workers.
- `.env.example`, `turbo.json`, `docs/configuration.md`, and `docs/deployment.md`: document `TYPESAFE_API_KEY`, pinned model override for non-production evals only, per-use-case feature flags, the 1Password location, and the two independent secret-delivery/redeploy gates. Vercel Production uses its authenticated environment-variable flow; Trigger `prod` uses the documented management API and PAT, then a worker redeploy. Keep the key server-side and verify names/presence only.
- `DECISIONS.md`: record the dated decision that Jev is a decision primitive, not a generative provider.
- `docs/architecture.md`: add the separate decision path beside `OracleAIClient` and state what may never call it.

**Required behavior**

- Empty questions, duplicate IDs, unsupported question types, invalid criteria, over-cardinality Choice, oversized state, disallowed data class, and absent key fail before network access.
- More than 100 questions, total serialized UTF-8 payload over 64,000 bytes, or state plus longest serialized question over 32,000 bytes fails before network access. Count JSON structure, IDs, criteria, options, and multi-byte text—not just state strings.
- A pack declares an allowlist of data classes. Runtime requires `actual classes ⊆ pack allowlist ⊆ active policy allowed classes` for the exact stored policy version before network access. Caller-supplied labels can only make the actual set more restrictive; they can never remove a class derived from source records.
- Hard mappings are deliberately conservative and content-independent: arbitrary MCP query text and every employee message/meeting utterance carry the full possible pasted/free-text union `internal_company`, `employee_communication`, `licensed_content`, `personnel_hr`, `customer_personal`, and `unknown_restricted`. This intentionally blocks free text unless the active policy approves every class; neither user identity nor channel provenance proves pasted content ownership. Claims inherit the union of every evidence-source class; retrieved context inherits every included claim/source class; document content is `unknown_restricted` until its stored source classification is explicitly approved. Mixed sources retain every class instead of collapsing to one enum value. Later narrowing requires a separately planned and reviewed deterministic provenance rule with fixtures that prove it cannot understate pasted content—never semantic guessing, a caller label, or an LLM classifier.
- The API key is never included in thrown errors, raw usage, telemetry, or debug logging.
- The wrapper returns normalized typed answers plus provider `typesafe`, requested model, resolved version, latency, tokens, and computed cost.
- The production default is the pinned version, not `jev-latest`.
- `typesafe-client.ts` enforces the question pack's total wall-clock deadline with `AbortController`; SDK retries share that same budget and cancellation signal. There is no unbounded background request or late result that can affect behavior.

**Verification gate**

- `pnpm --filter @oracle/ai typecheck` passes.
- New `pnpm --filter @oracle/ai verify:typesafe-decision-contract` passes with mocked transport and no real key.
- Root `package.json` exposes `verify:jev-contract`, and `.github/workflows/pr-check.yml` runs it as a network-free required step with a placeholder key that cannot reach the network.
- A repository search proves `TYPESAFE_API_KEY` appears only in env/config documentation and server-side decision code.
- Split foundation delivery into two ordered PRs/outcomes. **Step 1A (schema only):** merge the reviewed migration/schema types with no web or worker reader, run the guarded production migration from that merged SHA, verify the migration journal and all nine RLS policies on the production target, and smoke the existing admin layout before continuing. **Step 1B (dependent code):** only after Step 1A production proof, merge/deploy the decision client, controls, pages, banner, and workers; then smoke the admin layout and decision page again. Because Vercel deploys automatically from `main`, no commit that imports or queries a new decision table may merge before the production migration is verified.
- `pnpm db:generate`, migration verification, `pnpm db:check-drift` against the intended non-production target, and schema typecheck pass before Step 1A. A clean-install migration test and a current-production-snapshot rehearsal prove the schema order before the guarded production migration.
- Direct-access tests exercise anonymous, authenticated non-admin, authenticated admin, and trusted service/server roles against every new table: anon/non-admin reads and all browser mutations fail; admin bounded reads succeed; only trusted validated server paths mutate. Existing intelligence-table RLS tests remain green.
- Source-erasure tests delete each supported source type. A two-claim contradiction fixture deletes the left claim and then, in a separate fixture, the right claim; each deletion discards the run, dismisses its open review, removes every remaining subject link, and cannot affect an unrelated run.
- Before the first company-data pilot, the database has exactly one active immutable policy version matching Step 0's approved matrix/evidence, and the use-case settings name it; otherwise only `v1-public-synthetic` calls may run.
- Document-classification tests prove legacy/default rows remain blocked, non-admin and invalid/empty classes fail, an approved multi-class row records actor/version/event, policy revocation blocks it, and deleting the classifier nulls only the FK.

#### Step 2 — Integrate observability and failure behavior

**Files/functions**

- New `packages/ai/src/decisions/run-decision.ts`: derive provenance classes, serialize/hash the exact request, and snapshot all pre-call control fields including activation generation; attempt the partial-unique pending insert plus subject links before the call. Configure the pinned SDK explicitly with `maxRetries: 2` (three maximum billable attempts, matching the reviewed official SDK policy) rather than inheriting an environment/default. Lock the single active `oracle_decision_spend_epochs` row and atomically reserve **three times** the conservative per-attempt worst-case request cost (`serialized UTF-8 bytes` treated as tokens at the pinned rate) before network access. If no active epoch exists or `spent + reserved + request reservation > cap`, record `discarded/budget_blocked` and execute current behavior. On any normal finalization, atomically move the entire conservative three-attempt reservation from epoch `reserved` to permanent `spent`; record reported actual cost separately for observability but never release unprovable failed-attempt cost. If the process crashes after reservation/transport, the reservation continues to count against the cap; stale-pending reconciliation atomically converts it to spent before marking the run discarded. `spend_settled_at` makes settlement idempotent. Decision-run retention never changes epoch totals. On duplicate identity, never call TypeSafe: load an exact successful disposition or preserve current behavior while the other run is pending. Both a fresh answer and a reused disposition must pass `withDecisionActivationFence` before effect. That helper acquires the same per-use-case database advisory/setting-row lock used by control changes and, inside the final transaction, revalidates mode, activation generation, active data policy, pack, threshold, requested model, exact input hash, subjects, and resolved model; for a fresh result it computes/stores the effective fingerprint. Mismatch marks the run `discarded/control_changed` and executes current behavior. Database effects commit in that transaction; stateless callers receive a result only from a successfully fenced finalization. Failed/discarded rows leave the identity retryable. Do not copy or write generation `model_runs` records.
- New `packages/ai/src/decisions/reconcile.ts` and `retention.ts`; call both from the existing `apps/workers/src/trigger/claim-extraction-batch-drain.ts` schedule rather than adding a Trigger.dev schedule. Its current ten-minute run marks every `pending` row older than its recorded `deadline_at + 2 minutes` as `discarded/process_interrupted` in bounded indexed pages, expires query origins, and uses a database lease to run bounded retention at most once per UTC day. `runDecision` also reconciles the same versioned decision key before insert. A stale row can never be applied; a retry creates a new run linked to the same subjects. Refactor the drain's current per-batch catch: continue processing and leave transiently failed provider-batch rows retryable with their error metadata, run decision maintenance even when one batch failed, then mark the scheduled `job_runs` row failed and throw one bounded aggregate error if either drain or decision maintenance had any error. A partial failure can no longer return `{ok:true}` or a successful Trigger run.
- New `packages/ai/src/decisions/health.ts`: `reserveCanary` transaction first inserts a reservation by `(use_case,config_fingerprint,ISO week,decision_key,input_hash)`; only a successful insert locks/increments the matching fingerprinted counter and records the first-N/every-tenth result, while a conflict returns the existing reservation unchanged. `reserveAgreementReview` atomically updates that reservation/counter for the weekly agreement-review minimum. Pack, threshold, policy, requested model, approved resolved model, or activation-generation change creates a fresh fingerprint and fresh first-N cohort even midweek. The module also persists comparator results, append-only human adjudication, rolling error calculations, and fenced `active→shadow` plus control event. Never disable unrelated use cases.
- `retention.ts` performs the daily bounded cleanup from that shared schedule. Delete pending/failed/discarded runs after 30 days, successful shadow runs after 90 days, and successful active runs after 365 days; child subjects/adjudications cascade with the run. The ten-minute maintenance path expires every MCP query origin no later than 24 hours plus one schedule interval and, in the same transaction, invokes source-erasure invalidation and deletes the now-orphaned decision run, removing its decision/input hash immediately. Normally an open review pauses age-based deletion. **Source erasure takes precedence:** if its final typed subject disappears, atomically mark the review dismissed with reason `source_erased`, then delete the orphan run within 24 hours. Retain acknowledged control events for 730 days and unacknowledged events until acknowledged; their run/adjudication FKs become null while bounded snapshots remain. Retain immutable data-policy versions and spend-epoch ledgers permanently because they contain no source text and explain historical authorization/spend; decision deletion never decrements spend. Delete canary counters and matching reservations after 90 days. Deleted employee/reviewer/approver FKs become null. Store no raw source text, free-text review note, or employee ID outside typed FKs.
- Add `apps/web/app/admin/ai/decisions/page.tsx`, `apps/web/app/admin/ai/decisions/[id]/page.tsx`, and `_actions.ts`: admin-only list/detail over decision runs, default-filtered to `review_status='open'`, with bounded metadata/typed subject links and idempotent actions to mark `resolved` or `dismissed` with reviewer/timestamp/reason code. Never render raw secrets or unapproved source text. Add the page to the existing AI admin navigation so later canaries have a review destination before activation.
- `apps/web/app/admin/_components/admin-nav.tsx`: add the Decisions entry in the AI group with exact active-route behavior.
- `_actions.ts` must expose `submitDecisionAdjudication`: require the caller's expected `adjudication_version/current_adjudication_id`, lock the decision-run row `FOR UPDATE`, reject a stale head or cross-run supersession, validate an allowlisted verdict/reason/severity, insert the immutable adjudication, and atomically advance the run head/version. In that transaction recompute the use case's latest rolling human-labeled window and—if a threshold is crossed—compare-and-set only that mode to `shadow` plus insert its control event. Resolve/dismiss without an adjudication is allowed only for operational/non-canary reviews; canary reviews require this action.
- Add `apps/web/app/admin/_components/decision-health-alert-banner.tsx` beside the existing model-attempt banner. It reads unacknowledged health-type `oracle_decision_control_events`, identifies the use case and automatic `active`→`shadow` result, links to the filtered decision review page, and has an admin-only acknowledge action. Do not query or write `model_run_attempts` for Jev alerts.
- `apps/web/app/admin/layout.tsx`: mount `DecisionHealthAlertBanner` alongside `ModelAttemptAlertBanner`; tests prove the banner is actually rendered through the admin layout rather than merely existing as an unused component.
- Add redacted error taxonomy: `missing_key`, `policy_blocked`, `budget_blocked`, `invalid_request`, `timeout`, `rate_limited`, `overloaded`, `provider_error`, `invalid_response`, `process_interrupted`, `source_erased`, and `control_changed`; the last four also populate the bounded discard reason.
- Add feature-flag helpers that support `off`, `shadow`, and `active` per use case. Default every new use case to `off`; absence is never interpreted as active.
- New `packages/ai/src/decisions/config.ts` owns the exact setting keys: `jev_mcp_capability_search_mode`, `jev_entity_selection_mode`, `jev_responsibility_quote_selection_mode`, `jev_claim_extraction_prefilter_mode`, `jev_claim_support_mode`, `jev_contradiction_screen_mode`, `jev_live_recall_gate_mode`, `jev_retrieval_rerank_mode`, and `jev_chat_grounding_mode`, each seeded `off`; each also has explicit `<key>_pack_version`, `<key>_threshold_version`, `<key>_data_policy_version`, `<key>_requested_model`, `<key>_approved_resolved_model`, `<key>_activation_evidence_url`, `<key>_activation_review_commit`, and integer `<key>_activation_generation` settings. Spend comes only from the durable epoch ledger; the initial owner-approved recommendation is `5000000` microusd ($5), and no seeded active epoch means network calls stay blocked. Raising the cap or starting a new epoch is an admin-only, owner-authorized ledger/control event—never automatic refill. Unknown values, missing exact requested/resolved-version/evidence metadata, no/spent epoch, or a revoked/non-active data policy resolves effectively to `off`/current behavior before network access.
- Seed those settings in the foundation migration. Add an admin-only “Jev decision controls” section under `apps/web/app/admin/settings/page.tsx` with a focused server action/component: `off→shadow` requires pinned requested-model/pack/threshold/active-data-policy versions; completed shadow evaluation records the exact provider-returned resolved model in the evidence artifact. `shadow→active` requires that durable `<key>_approved_resolved_model`, a committed held-out artifact URL, and approving independent-review commit all bound to the exact configuration fingerprint. Any requested/approved-resolved model, pack, threshold, or data-policy change is one locked transition that first forces `active→shadow`, clears approved-resolved-model and prior activation evidence/review fields, increments activation generation, and writes a control event; it cannot edit an active configuration in place. For every active response, the request model recorded on the run must match configured requested model and the provider-returned resolved model must match stored approved resolved model; either mismatch discards the answer and atomically demotes that use case to `shadow`. Every manual transition, automatic health fallback, emergency off, or policy-revocation demotion uses the same lock/generation/event path. Reactivation always needs new exact-fingerprint held-out/review evidence and a fresh generation; no environment-only, direct-settings, or dashboard bypass exists.
- The same admin section has a separate spend-epoch action: require the owner-approval evidence URL and integer microusd cap, close the prior epoch without altering its totals, create the replacement epoch, and write one control event in the same transaction. It cannot reset/update an existing epoch or schedule automatic replenishment.

**Required behavior**

- Shadow calls record both Jev's judgment and the unchanged current outcome.
- Shadow/current and canary comparator outcomes are written to the decision run with comparator version/status, and any generation comparator is linked by typed model-run subject. Human adjudication is append-only and is the only source for rolling safety-miss rates.
- Provider failures are visible, bounded, and non-recursive. Do not call a generative model merely to interpret a Jev error.
- Retry policy is explicitly pinned to the reviewed official SDK value `maxRetries: 2` (one initial plus at most two retries) inside the pack's total deadline; do not inherit environment changes or add a second retry loop. Any retry-policy change is a reviewed config/code change that must update the maximum-attempt spend reservation and contract tests together. Initial deadlines are 600 ms for synchronous MCP discovery and 5 seconds for asynchronous worker pilots, then may tighten from measured p95 data.
- Cost is calculated from actual input tokens, not estimated request length.
- Raw state and full response bodies are not written to general logs.
- If pending-record creation fails, do not call TypeSafe. If the provider succeeds but final audit persistence fails, discard the Jev answer, record only a redacted operational error where possible, and execute the unchanged current path. Never apply an unaudited answer.
- For stateless effects such as ranking a response, `affected_behavior=true` means the audited result is authorized and returned to the caller only after the final row update commits. For database effects such as marking messages skipped, update the decision row and business rows in one transaction; either both commit or neither does.
- Process death before finalization is treated as an unknown outcome, never success. The stale-pending reaper discards it; a retried caller follows normal idempotency/current-path rules and may issue a fresh provider request.

**Verification gate**

- Contract tests assert one success row and each failure class without leaking state/key text.
- A fake 429 and 529 produce the expected final error after bounded SDK behavior.
- A fake timeout preserves the caller's current path and records a failed attempt.
- Fault-injection tests fail pending-run insert, subject-link insert, provider completion, final decision update, and combined business-effect transaction in turn; they prove no unaudited Jev effect reaches the caller and no partial record is presented as success.
- Crash tests terminate after the pending insert and after mocked provider completion but before final update; advancing the clock runs reconciliation, atomically converts any unsettled three-attempt reservation from epoch reserved to spent exactly once, proves both rows become discarded with no effect, and proves a retry succeeds once without reusing the stale result or double-settling spend.
- Duplicate-call tests race at least 100 `runDecision` calls for one exact identity and assert one pending/success row, one transport invocation, one set of effects, and fallback/reuse for every loser; after a forced failed/discarded winner, exactly one later retry may call the provider.
- Activation-fence race tests pause a provider response, then commit emergency `off`, policy revocation, or automatic `active→shadow`; the late result must become `discarded/control_changed`, apply no skip/rerank/intervention effect, and follow current behavior. Reactivation increments generation, starts a fresh first-N canary cohort, and cannot reuse the pre-fallback decision.
- Fingerprint tests keep a human-readable decision key/version constant while changing one serialized state byte or question criterion; `input_hash` changes, the old result is not reused, and the distinct call is separately audited.
- Migration/schema verification proves the dedicated tables, constraints, indexes, and generated types match this contract.
- Retention/erasure tests delete fixture messages, document chunks, claim-evidence rows, extraction-candidate-evidence rows, claims, documents, model runs, and reviewer employees; typed links cascade or null as specified, no stale identifier/free-text survives, and unrelated evidence remains. Deleting one extraction source message or replacing one exact evidence row/chunk must fire the erasure trigger, remove surviving parent/batch subjects despite JSON/parent rows, dismiss any review, and make the run pruneable. Also prove an aged run referenced by an unacknowledged event deletes while the event survives with null FKs and its bounded snapshot.
- Admin-page tests cover open/resolved/dismissed lifecycle, append-only adjudication/supersession, rejected cross-run or stale-head supersession, allowed reason codes, canary-review enforcement, idempotent actions, redaction, typed-link disappearance, and non-admin denial. Race two writers against one expected head and prove exactly one new head while the loser receives a conflict and does not affect health. A submitted safety miss must atomically change the exact active key to `shadow` and create its control event. Banner tests seed that Jev event—not a model attempt—then prove display, link, admin-only acknowledgement, and continued visibility of unrelated unacknowledged events.
- Configuration tests enumerate every named mode/model/pack/threshold/data-policy/evidence key, prove migration defaults `off` with only `v1-public-synthetic` active, reject missing evidence/version/policy metadata and pack-policy widening, deny non-admin/direct-setting transitions, persist one control event per successful compare-and-set, prove policy revocation blocks calls and demotes dependent modes, and prove automatic fallback uses the same helper without touching another key. For each fingerprint component, change it while active and prove the transaction forces shadow, clears old evidence, increments generation, discards an in-flight/late result, and refuses reactivation until new held-out artifact plus review commit match the exact new fingerprint. Simulate resolved-model drift and prove the same fail-safe demotion.
- Spend-control tests race 100 distinct calls just below/at/above the approved cap and prove epoch-row reservations serialize at `3 × worst-case per-attempt cost`, no combination of initial calls plus two retries can exceed the cap, zero/missing/spent epoch blocks before transport, and neither day/week rollover nor process restart refills it. Mock success on attempt 1, success on attempt 3, all-retry failure, and process death after attempts 1/2/3; every path settles the full reservation to spent exactly once (immediately or by stale reaper), leaves no stranded reserved amount, and records actual reported cost separately. Delete all associated 30/90/365-day decision runs and prove the permanent epoch spent total and blocked state remain unchanged. Only a separately owner-authorized admin action may close/create a higher-cap epoch, and it writes a control event.

**Natural cuts:** Step 1A is one schema-only merge/migration/proof outcome. After that production proof, land Step 1B and Step 2 together as the client/observability outcome with no product behavior change.

### Phase B — Lowest-risk product pilot

#### Step 3 — MCP capability discovery in shadow mode, then active if accepted

**Files/functions**

- `apps/web/lib/mcp/registry.ts:67-98`: keep existing lexical/synonym scoring as fallback and comparison baseline.
- Add `apps/web/lib/mcp/decision-capability-search.ts`: build a bounded `Choice` over currently enabled capabilities plus `none`; state contains only the user's capability query and non-sensitive capability names/descriptions.
- Add `buildPublicSyntheticMcpProbe()` beside it with one fixed literal query, expected enabled-capability registry hash, and `eval_case_key='mcp-capability-public-probe-v1'`. The builder alone creates `origin_kind='synthetic'`; it verifies the exact UTF-8 bytes and registry hash before granting `public_synthetic`, sends no caller content, and refuses any extra or changed byte. Ordinary MCP requests—including a caller supplying the same words or claiming a synthetic flag—remain `mcp_request` and receive the full conservative free-text class union.
- For every MCP Jev call, create and link a short-lived `mcp_request` query origin before transport. The static bearer token cannot identify a person, so the origin and its decision/input hash are forcibly erased within 24 hours plus one existing ten-minute schedule interval; a missing origin blocks the call.
- `apps/web/lib/mcp/server-tools.ts:103-130`: in `shadow`, record Jev ranking but return lexical results; in `active`, use Jev only when confidence clears the evaluated threshold, otherwise return lexical results.
- Give a normalized exact enabled-capability name match absolute deterministic precedence before Jev ranking. Capability names are unique: pin that exact match first, and if `limit=1` return it unchanged; Jev may rank only the remaining slots and can never displace it, regardless of probability. A disabled exact match receives no privilege. For remaining slots, remove `none`, intersect with enabled capabilities, sort by probability descending, break ties with existing lexical score then stable capability ID, apply the remaining limit, and return no duplicates. If too few candidates clear their position-specific threshold, fill from lexical ranking without moving the pinned exact match.
- `apps/web/lib/mcp/__verify__/mcp-registry.ts`: add paraphrases, ambiguous queries, no-match, prompt injection, disabled-capability, non-English, and service-failure cases. Prove an intentionally wrong high-confidence Jev result cannot outrank an enabled normalized exact-name match at limits 1 and 2; prove a disabled exact match stays excluded. Prove only the exact code-owned probe fixture/hash qualifies as `public_synthetic`, while a one-byte change, appended text, caller flag, or ordinary request containing the same literal is blocked before transport under the synthetic-only policy.
- Add an eval artifact under `evals/jev/mcp-capability-search.md` containing dataset version, lexical baseline, Jev version, accuracy, confusion cases, threshold curve, p50/p95 latency, tokens, cost, and decision.
- Before the first deployed Vercel shadow/live call, run the production/infrastructure task gate and obtain the standing independent-reviewer approval for the exact Vercel project, variable-name upsert, and redeployment. Then load the `secrets-to-1password` procedure and use an authenticated Vercel CLI/API flow with protected 1Password injection to upsert `TYPESAFE_API_KEY` for project `prj_rP6Jlima7iK1paffEPhLqxlswGsC` **Production**. Never place the value in a command argument, transcript, temp file, or output. Verify only the variable name/target and encrypted presence, then trigger/verify a fresh production deployment from the merged Step 3 SHA. A pre-deploy or stale deployment does not count. Preview gets a separate synthetic-only key only if its tests require one; production credentials are never copied into Preview by assumption.

**Acceptance criteria**

- No disabled capability can be returned, regardless of Jev output.
- `none` and low-confidence results fall back to lexical behavior.
- Jev improves top-1 accuracy on the reviewed set without reducing exact-name queries.
- The sealed held-out set also measures top-k recall, ordering, and `limit=1`, `limit=2`, and full-list behavior; tuning and held-out examples are disjoint.
- Safety-tier confirmation and tool argument validation remain unchanged.
- Added p95 latency is measured and acceptable for discovery; target `<750 ms`, but accuracy and safe fallback take precedence.

**Verification gate**

- `pnpm --filter @oracle/web verify:mcp` and `pnpm run verify:vercel-guards` pass.
- The shadow eval artifact is committed.
- Vercel's production environment listing proves `TYPESAFE_API_KEY` exists without revealing its value; the post-secret production deployment ID resolves to the merged Step 3 SHA, and the exact code-owned `buildPublicSyntheticMcpProbe()` path—not an arbitrary MCP request—records the expected resolved model/cost audit. Missing-key behavior remains covered by network-free tests and fails to the lexical path.
- Active behavior, if enabled, is proven against the live MCP endpoint with a benign query and an ambiguous/no-match query.
- If code lands without live proof, open exactly one leftover-proof issue for this step before ending that session.

**Natural cut:** stop after the MCP result is either activated with proof or recorded as rejected. Do not add entity selection in the same session.

### Phase C — Bounded direct replacements

#### Step 4 — Entity selection

**Files/functions**

- `packages/ai/src/entity-planner-model.ts:55-154`: preserve current registry-candidate construction and final intersection.
- Add a question pack using one Noul per prefiltered entity candidate because more than one entity may be valid. State includes query, entity type, value, label, and aliases only.
- `packages/ai/src/retrieval-plan.ts:227-276`: in shadow, compare Jev selections to current model selections. The first active pilot may add/reorder only Jev-positive candidates within the deterministic registry shortlist while unioning every current-selector result; Jev negatives never remove a current selection. On uncertainty/failure, return the current selector unchanged.
- The current entity selector does not persist `model_runs`. Represent this use case with `oracle_decision_subjects.entity_query_key`, a hash of normalized query + registry version, a query-origin subject tied to the exact chat message, worker source message/chunk, or short-lived MCP request that produced it, **and one typed `entity_id` subject for every registry candidate actually serialized to Jev**, not only selected entities; absence or an incomplete candidate/source set blocks the call. The decision/input keys hash the ordered candidate IDs, entity types, and hashes of canonical value/display label/aliases, plus locale and pack/threshold/data-policy/requested-model versions. Mutation changes the hash and prevents reuse; deletion of any supplied entity triggers whole-run erasure. Store the current selector's bounded chosen IDs, route/model ID, attempt status, latency, and usage returned by `OracleAIClient` in the decision run's comparator fields; never claim a nonexistent model-run link.
- Extend `packages/ai/src/__verify__/entity-aware-retrieval.ts` and live fixture with aliases, homonyms, multiple entities, no entity, Chinese text, adversarial candidate text, and over-cardinality shortlist handling.
- Add `evals/jev/entity-selection.md` with current-model baseline, labeled result, threshold curve, false-negative analysis, latency, and cost.
- Use separate tuning and sealed held-out entity sets; the held-out set has at least 100 cases, including at least 30 alias, homonym, multi-entity, or explicit-name cases, and is not opened until the pack/threshold is frozen.

**Acceptance criteria**

- Jev can never invent or return an entity outside the supplied registry candidates.
- Every supplied entity candidate is linked and conservatively classified before transport; deleting or changing any candidate discards/prevents reuse of the whole decision, and unknown or unapproved entity data is blocked before network access.
- Explicitly named valid entities have 100% recall in the frozen fixture before active use.
- Low-confidence candidates preserve current behavior; no negative Jev result becomes a hard retrieval exclusion.
- Because the initial active pilot still runs the current selector, it is a quality/measurement pilot, not a cost-saving replacement. Replacing that selector requires a new STATUS row and separate plan after held-out evidence proves recall and defines a safe non-Jev fallback.
- Chinese is separately scored; if it misses the bar, `zh-CN` remains on the current path.

**Verification gate**

- `pnpm --filter @oracle/ai verify:entity-aware-retrieval` passes.
- The live fixture passes only after vendor/data approval; otherwise the step remains shadow-only.
- The Jev decision run records both the shadow selection and the current selector's bounded comparator outcome/attempt metadata under `entity_query_key`; success and failure fixtures prove this without inserting a generation `model_run`. If the current selector fails, current deterministic fallback remains authoritative and the comparator status is `failed`.

#### Step 5 — Responsibility quote-candidate selection evaluation

**Files/functions**

- Do not change `RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT`, the R2 matcher, route, budgets, or production worker.
- Add an isolated evaluator under `packages/ai/evals/` or `apps/workers/src/__verify__/` that reads the immutable responsibility fixture and offered grounded quote candidates.
- Represent each file-based call with one `oracle_decision_subjects.eval_case_key` equal to the immutable fixture version + case ID; the decision key additionally hashes the offered candidate IDs/text. No repository path or licensed quote text is stored in the subject/audit rows.
- Classify the R2 fixture as `licensed_content`; do not send it until the active data-policy version explicitly allows that class and the pack is within the same policy.
- Implement a Choice pack per responsibility with candidate IDs/text plus `no_supported_candidate`.
- Reuse the exact grounded-candidate construction and exact-quote validator; Jev only selects among candidates.
- Write `evals/jev/responsibility-quote-selection.md` with the versioned fixture, current baseline, 27/30 gate, preservation failures, latency, tokens, and cost.

**Acceptance criteria**

- Never select text not present in the offered candidate set.
- Meet or exceed the existing 27/30 acceptance bar without weakening the matcher.
- Preserve every previously correct frozen case.
- Show material cost/latency improvement against the recorded GPT-4.1 baseline.

**Verification gate**

- Existing `pnpm --filter @oracle/workers run verify:r2-responsibilities` and `verify:r2-production-replay` remain byte-identical.
- The new Jev evaluator passes without importing its outputs into the live reader.
- Advancing from evaluation to production requires a new, separately scoped plan/status row after the active R2 handoff is settled.

**Natural cut:** stop after the evaluation artifact. This plan does not authorize replacing the live R2 quote path.

### Phase D — High-volume savings and independent safety checks

#### Step 6 — Claim-extraction prefilter in shadow mode

**Files/functions**

- `apps/workers/src/trigger/claim-extraction.ts:361-468` and `claim-extraction-batch-submit.ts:150-280`: stage one `extraction_batches` owner row for **every conversation window before** the decision. Run the same shared prefilter helper in sync and batch. Shadow/canary windows continue to the current model; an active confident-negative non-canary window gets batch status `skipped_by_decision` and no provider request.
- `apps/workers/src/lib/message-extraction-status.ts`: add window-aware reconciliation. A message is `complete` if any overlapping current owner completed extraction; `skipped` only if every current owner containing it is `skipped_by_decision`; `failed` only when all current non-skipped owners failed and none completed; otherwise it remains `processing`. `replay_queued` is historical/superseded and is excluded from current-owner voting. A negative overlapping window can never overwrite a completed positive owner.
- `packages/shared/src/domains.ts`: add `skipped_by_decision` and `replay_queued` to the canonical extraction-batch status list and every derived terminal/filter list. `skipped_by_decision` is a deliberate no-model terminal owner; `replay_queued` is the old owner after its messages have been atomically returned to the normal pending queue and must not count as a current skip/failure/complete owner. Add a new hand-written migration under `packages/db/migrations/sql/` that replaces the existing `extraction_batches_status_check` from migration 13 with the expanded allowlist; never edit the applied migration.
- In that migration/schema change, add nullable `extraction_batches.skip_decision_run_id` (`ON DELETE SET NULL`), `skip_question_pack_id`, `skip_question_pack_version`, `skip_threshold_policy_version`, `skip_data_policy_version`, `skip_decision_key`, and `skip_decided_at`. The bounded version/key snapshot survives decision-run retention and contains no source text; a check constraint requires the complete snapshot exactly while status is `skipped_by_decision` and requires every snapshot field null when status is `replay_queued`.
- Update status consumers in `apps/web/app/admin/ai/candidates/page.tsx` and `apps/web/app/admin/ai/runs/[id]/page.tsx` to label/filter deliberate skips and replay-queued historical owners distinctly from failures and completed extraction. Update any batch-status exhaustive switches/tests found by the required repository search.
- In `claim-extraction-batch-submit.ts`, track `skippedBatchIds` separately from `submitted/stagedBatchIds`. Pre-provider and post-provider failure cleanup may delete/reset only pending submitted owners/messages; it must retain committed `skipped_by_decision` owners and then run shared message reconciliation. An all-skipped selection completes successfully without creating a provider batch job; it is not reported as “user-message-free.”
- Link the decision to its window-owner `extraction_batch_id` **and** every source `message_id` with effect `source_message`; this retains window ownership while making deletion of any source message trigger full decision erasure instead of leaving a batch/JSON-only link. Commit the successful decision outcome, all subject links, `skipped_by_decision` batch status, and reconciled message statuses in one transaction. The versioned decision key is the ordered window message IDs plus their content hash; a changed window cannot reuse an old skip.
- Add `scripts/replay-jev-extraction-skips.ts`: dry-run by default; select `skipped_by_decision` owner windows by their durable batch snapshot for an explicit pack/threshold/data-policy version or UTC window, using the decision link when still retained but never requiring it; show exact window/message IDs in a protected artifact. With `APPLY=1`, one transaction locks the owner/messages, verifies each target message is still reconciled `skipped`, changes the old owner from `skipped_by_decision` to `replay_queued`, clears its skip snapshot, and changes only eligible messages to `pending`; never reset a message already `complete`, `processing`, or unlinked. The normal extractor then creates a new owner batch. A crash before commit leaves the complete skip snapshot/status replayable; a crash after commit leaves explicit `replay_queued` plus pending messages, never an ambiguous skipped owner without metadata.
- Create a pack with independent Nouls for operational fact, decision, rule/exception, metric, and process/handoff detail. Code combines them into `worth_extraction`; one broad question is not sufficient.
- Do not initially change `apps/workers/src/trigger/document-ingestion.ts`; document uploads are denser and higher stakes.
- Add settings/flags: `jev_claim_extraction_prefilter_mode` (`off|shadow|active`) and a versioned threshold policy. Seed/default must be `off`; add any setting row through the repository's governed migration path.
- Add `apps/workers/src/__verify__/jev-extraction-prefilter.ts` and `evals/jev/claim-extraction-prefilter.md`.
- Before the first deployed Trigger.dev shadow call, run the production/infrastructure task gate and obtain the standing independent-reviewer approval for the exact Trigger project/environment, variable-name upsert, and redeployment. Then load the `secrets-to-1password` procedure and use 1Password-protected injection for both the TypeSafe key and the Trigger management PAT to upsert `TYPESAFE_API_KEY` in project `proj_wgpzsvhmsopqhvwqaycn` environment `prod` through the documented management API. Verify with the names-only environment listing, never a value. Redeploy workers from the merged Step 6 SHA and record the Trigger deployment/version. Vercel's variable does not satisfy this worker gate; the two environments are independently proven.

**Ground truth and acceptance**

- Build a reviewed dataset containing greetings/boilerplate, implicit rules, negation, exceptions, direct capture requests, short but valuable facts, long irrelevant chatter, and sensitive content.
- A segment with any approved/reviewed operational claim is positive even if the old extractor returned zero; do not use old model output alone as ground truth.
- Require 100% recall on the frozen high-value positive set before active skipping.
- Require a meaningful confident-negative rate (initial target at least 30% of true negatives) or reject the pilot as not worth the complexity.
- In active mode, atomic weekly reservation sends the first 50 confident negatives (or all when fewer exist), then every tenth later unique negative through the current extractor as canaries. All canary disagreements are queued for admin review; any missed high-value claim or more than 1% adjudicated false negatives over the latest 100 canaries atomically changes this use case to `shadow` and raises the existing admin alert.
- Persist the canary extractor's model run as a typed subject, link any produced extraction candidates, and write a bounded comparator version/outcome/agreement to the decision run. Human labels append `oracle_decision_adjudications`; health calculations use those final labels and remain reproducible after restart.
- Direct uploads, explicit capture requests, low confidence, unsupported language, provider failure, and missing key always continue to the current extractor.
- The tuning set and sealed held-out set are disjoint. The held-out set contains at least 200 segments and 50 administrator-confirmed high-value positives; 20% is independently double-labeled and disagreements are adjudicated before activation scoring.

**Verification gate**

- `pnpm --filter @oracle/workers typecheck` and the new verifier pass.
- Trigger.dev's production names-only listing proves `TYPESAFE_API_KEY` exists without exposing it; the post-secret worker deployment is healthy and tied to the merged Step 6 SHA, and one public-synthetic shadow task records the expected resolved model/cost audit before any approved company-data window is attempted.
- The verifier runs the same cases through sync and batch policy helpers and proves identical shadow/active/fallback decisions, message status, and audit behavior.
- Overlap fixtures cover negative→positive, positive→negative, all-negative, skipped+failed, and three-window chains in both dispatch modes; reconciliation must match the owner rules above and never mark an extracted message skipped.
- Batch failure fixtures cover mixed skipped/submitted failure before provider acceptance, failure after provider acceptance, and all-skipped input; committed skip owners survive, pending owners follow the existing tracked-batch recovery rules, message statuses reconcile correctly, and the drain never receives a skipped owner as a provider `customId`.
- A recovery fixture creates false-negative window skips in both dispatch modes, deletes/ages out the linked decision run past 365 days, proves the durable batch snapshot still selects the exact dry-run window, applies the bounded replay, verifies the old owner is `replay_queued` with null skip fields and excluded from reconciliation, verifies only messages still skipped across all current linked owners return to `pending`, and then proves the existing extractor creates a new owner and processes them. Crash-before/after-commit fixtures prove neither an invalid constraint state nor a lost replay occurs.
- Shadow telemetry covers enough real approved data to calculate false negatives without storing raw employee text in logs.
- The active switch is a separate PR/session with independent review and a worker deployment/live proof.

#### Step 7 — Semantic claim support and auto-approval veto

**Files/functions**

- After deterministic exact-quote validation in `claim-extraction.ts` and `document-ingestion.ts`, ask whether the validated quote/context supports the proposed claim summary and whether it contradicts or omits a material qualification. The document path remains off for any source whose durable document classification is absent, `unknown_restricted`, wider than the pack, or outside the active data policy.
- Link each decision to the exact `extraction_candidate_id`, every `extraction_candidate_evidence_id`, and each evidence `message_id` or `document_chunk_id` actually supplied; after promotion, claim checks similarly link `claim_id`, every supplied `claim_evidence_id`, and its exact message/chunk source. The decision/input key includes candidate/claim and evidence row/content hashes, so replacing or deleting evidence invalidates and erases the judgment even if the parent candidate/claim survives.
- `apps/workers/src/lib/document-claim-auto-approval.ts:26-76`: Jev may veto auto-approval or route to review; it may not make an otherwise ineligible claim approvable.
- This step asks only support/contradiction/qualification questions for veto-or-review. Claim kind, semantic role, impact, domain, and sensitivity classification are explicitly out of scope and get no hidden secondary output from this pack.
- Keep all existing schema, taxonomy, evidence, entity, sensitivity-positive, and promotion rules authoritative.
- Add `apps/workers/src/__verify__/jev-claim-support.ts`, adversarial claim/quote fixtures, and `evals/jev/claim-support.md`.

**Acceptance criteria**

- No Jev result bypasses an existing rejection/quarantine/review rule.
- Existing sensitivity-positive results are OR'd with Jev; Jev cannot clear them.
- Unsupported/contradicted high-confidence cases are held for review, not destroyed.
- Low-confidence and failure preserve current review status.
- Thresholds are calibrated against administrator-reviewed claims, with false-support errors weighted more heavily than extra review.

**Verification gate**

- Existing extraction, R5 quote-validator, promotion, and document auto-approval verifiers stay green.
- The new verifier demonstrates supported, unsupported, contradicted, qualified, negated, and prompt-injected source cases.
- Production activation, if accepted, is proven on one bounded claim flow and gets exactly one live-proof issue if not completed in the landing session.

**Natural cut:** extraction prefilter and claim-support activation are separate sessions and separate live outcomes.

### Phase E — Runtime gates

#### Step 8A — Contradiction negative-path screening

**Files/functions**

- `apps/workers/src/trigger/contradiction-watcher.ts:155-232,450-452`: keep vector shortlist; batch Jev Choice questions over pair categories `contradiction`, `compatible_exception`, `refinement`, `different_scope`, `unrelated`, plus severity Score if useful.
- In shadow, compare with current adjudicator. In active, only confidently negative pairs skip the generative call. Possible contradiction and all uncertainty continue to the existing model, which still writes explanation/question text.
- Give each claim pair a canonical order-independent `decision_key` from the two claim IDs plus their content hashes. Persist both claim IDs in `oracle_decision_subjects`. Before screening, the watcher may skip a pair only when a successful active `skip_current` negative disposition exactly matches current question-pack, threshold-policy, data-policy, requested-model, and resolved-model versions; any changed/revoked policy, model, pack, threshold, or claim hash deliberately reevaluates.
- Update the watcher selection/query helper so a durable current-version negative disposition counts as processed without creating a fake contradiction row. Add indexes/query-plan proof so the scheduled sweep does not repeatedly rescreen the same negative pair.
- Preserve `packages/oracle-engines/src/interjection.ts` decision thresholds, cooldowns, caps, and status rules.
- Add `apps/workers/src/__verify__/jev-contradiction-screen.ts` and `evals/jev/contradiction-screen.md`.

**Acceptance and verification**

- Require 100% recall on severe/material frozen contradictions and separately report conditional, temporal, scope, exception, and negation cases.
- Prove reduced generative calls on true negatives without changing created contradiction records.
- Prove a second scheduled sweep makes zero provider calls for current-version durable negatives, while a pack/threshold version bump or changed claim hash reevaluates them exactly once.
- The same reuse fixture changes data-policy version, revokes the old policy, changes requested/resolved Jev version, and proves each invalidates the old disposition; no lookup may reactivate an older-policy/model result.
- Atomically reserve the first 50 confident-negative pairs each ISO week (or all when fewer exist), then every tenth later unique pair through the current adjudicator. Human-review every disagreement; one missed material contradiction or more than 1% adjudicated false negatives over the latest 100 canaries changes only this gate to `shadow`, alerts admins, and makes subsequent sweeps ignore its negative dispositions.
- Link the canary adjudicator's model run and both claims, persist its versioned category/severity as the bounded comparator outcome, then append the human verdict; do not infer rolling error from a transient log or recompute it from a moving model.
- Run worker typecheck and existing contradiction/interjection tests.
- Deploy/prove this outcome alone.

#### Step 8B — Live Teams intervention screening

**Files/functions**

- `apps/workers/src/trigger/teams-live-recall-utterance.ts:292-318,450-558,756-900`: replace or supplement the keyword/length pre-gate with Noul `worth_intervention` and Choice `contradiction|gap|direct_question|none`.
- Link each decision to the already-persisted utterance `message_id`; its decision key combines message ID, content hash, meeting/session ID hash, and pack/threshold versions. If message persistence fails, do not call Jev.
- Direct mentions, force-test paths, kill switches, confidence thresholds, cooldowns, and rate caps remain deterministic.
- A positive/uncertain result invokes the current generative model to draft; Jev never writes the Teams message.
- Atomically reserve the first 20 `none` decisions each ISO week (or all when fewer exist), then every tenth later unique decision through the existing analyzer as non-posting canaries. The current model's draft/interjection recommendation is captured for comparison but cannot post from the canary path; disagreements enter admin review.
- Link the analyzer model run, persist a bounded versioned recommendation comparator, and append human adjudication for disagreements plus the required random agreement sample. No message text or draft is copied into the decision tables.
- Add `apps/workers/src/__verify__/jev-live-recall-gate.ts` and `evals/jev/live-recall-gate.md` using scrubbed/synthetic utterances before any live meeting.

**Acceptance and verification**

- Direct mention always reaches current behavior.
- Timeout/low confidence fails open to the current model, not to posting.
- No extra message can be posted from Jev output alone.
- One human-confirmed missed direct question, material contradiction, or intervention-worthy gap—or more than 2% adjudicated false negatives over the latest 100 canaries—changes only the live gate to `shadow` and raises the existing admin alert before further negative suppression.
- The live test uses the existing bounded test controls, then restores the production clamp and verifies no post-clamp messages.
- This is a distinct session from contradiction screening and requires independent reviewer approval before the technical production action.

### Phase F — Quality/advisory pilots

#### Step 9A — Retrieval reranking

- `packages/ai/src/retrieval.ts:276-423`: replace the positional locale argument with a required `RetrievalCallerContext` containing `caller` (`chat_answer|mcp_knowledge|contradiction|live_recall|test`), locale, permission-scope hash, and optional complete query-origin/source IDs. Update every production caller explicitly: `apps/web/app/api/chat/route.ts`, `apps/web/lib/mcp/capabilities.ts`, `apps/workers/src/trigger/contradiction-watcher.ts`, and `apps/workers/src/trigger/teams-live-recall-utterance.ts`, plus all direct fixtures. Unknown/missing callers fail typecheck/runtime validation; no implicit default exists.
- This pilot enables Jev reranking **only** for `chat_answer` under `jev_retrieval_rerank_mode` and its chat-specific pack. `mcp_knowledge`, `contradiction`, `live_recall`, and `test` deterministically bypass this reranker and preserve their exact current ordering until each has a separate STATUS row/pack/acceptance plan. A shared mode can never affect all callers.
- Refactor both the vector path and `_searchFallbackTsvector` branch to return the same deterministically eligible over-fetched candidate shape, then call one post-retrieval reranker. It uses per-candidate relevance Noul or Score, initially reorders only, and never hard-filters. Tests force both branches and prove identical caller isolation, subject linkage, limits, and fallback.
- For `chat_answer`, create one query origin and link **every** contributing user message used by `buildConversationRetrievalQuery` (currently up to three), every ranked `claim_id`, every supplied `claim_evidence_id` and its source `message_id`/`document_chunk_id`, and every admitted `macro_relationship_id` as typed subjects. Absence/incompleteness of the origin/source set blocks the call. The decision key hashes the caller-specific pack ID, normalized query, ordered contributing-message/candidate/evidence/relationship IDs and content hashes, locale, permission-scope hash, and pack/threshold versions; deleting any earlier message or evidence invalidates the whole rerank even if the latest message/claim survives.
- Preserve `apps/web/lib/business-answer-retrieval.ts` domain-search budgets/coverage outputs and `business-answer-context.ts` atomic claim/relationship admission. Rerank only within each deterministically eligible candidate set; never erase an explicitly requested domain, relationship premise, omission flag, or citation membership.
- Keep embeddings/BM25/RRF as candidate generation and fallback.
- Keep the pack registry keyed by caller even though only `chat_answer` is enabled here; chat-answer relevance is not contradiction/live/MCP relevance and pack lookup for any bypassed caller must fail closed rather than borrow the chat pack.
- Add `packages/ai/src/__verify__/jev-retrieval-rerank.ts` and `evals/jev/retrieval-rerank.md` with vector/fallback parity, an invocation matrix for all five callers, multi-message erasure, recall@k, precision@k, downstream answer support, latency, tokens, and cost.
- Activate only if relevant-context quality improves without losing approved evidence recall.

#### Step 9B-1/9B-2 — Chat generation audit schema, then grounding verification

- **Step 9B-1 is schema-only:** add nullable `model_runs.output_hash` / Drizzle `outputHash` through a new journaled migration, list the hand-written file in `packages/db/migrations/sql/README.md` if one is needed, merge it without dependent web code, run/verify the guarded production migration, and prove existing chat/admin behavior still loads. No Step 9B-2 code that writes `output_hash` may merge before this production proof.
- `apps/web/app/api/chat/route.ts:223-315,515-663`: after generation and `assertKnownBusinessCitations`, but before assistant-message persistence, evaluate bounded support/responsiveness/language questions against the exact `answerContext` claims/relationships actually supplied. The retry reuses the same bounded context/coverage metadata and must pass `business-answer-policy.ts` again; Jev cannot broaden retrieval or suppress honest omission warnings.
- Extract `apps/web/lib/chat-generation-attempt.ts` from the route's current one-call logging path. Persist the first draft and one allowed retry as separate `model_runs`, each with its own context pack, attempts, usage, token/cost/latency, route/model, input hash, and the new output hash. Create one query origin and link **every** user message contributing to `buildConversationRetrievalQuery`/the generated answer (currently up to three), not only the latest message. Create **two** Jev decision runs: decision 1 links that origin, all contributing messages, the first model run (`draft_evaluated`), plus every supplied claim/claim-evidence/source-message-or-chunk and macro relationship; if outcome `retry`, persist the retry model run, then transactionally create decision 2 with `parent_decision_run_id=decision1.id`, link the same complete query/evidence set and the retry model run (`retry_evaluated`) before its Jev call. Decision 2 alone authorizes `continue_current|refuse`. Decision keys/input hashes include parent ID where applicable, generation output hash, exact serialized Jev request, ordered contributing-message/evidence/relationship IDs+content hashes, locale, permission-scope hash, and config fingerprint. Deleting any earlier contributing message invalidates both decisions. The first draft is never inserted as an assistant message when discarded.
- Lock the active policy before implementation: a high-confidence unsupported, materially incomplete, or wrong-language result discards the first draft and permits exactly one retry through the current generative route with the same approved evidence plus a grounding correction. Re-evaluate that retry once; if it still fails, return a deterministic “I do not have enough supported Oracle evidence to answer that reliably” response and queue the run for admin review. Jev cannot repair prose, add evidence, or cause more than one retry.
- Use the foundation's admin decision-review list/detail/actions; grounding failures set `review_status='open'` with a bounded reason code and typed links to the relevant generation runs.
- Start shadow-only because this adds latency and duplicates sensitive context externally.
- Add `apps/web/lib/__verify__/jev-chat-grounding.ts` and `evals/jev/chat-grounding.md` with supported, partially supported, fabricated, wrong-language, irrelevant-gap, and injection cases.
- On the **first** Jev check, timeout, malformed response, audit-persistence failure, low confidence, or provider failure preserves the original current answer path because no unsafe verdict exists. Once a successfully audited first check rejects that draft, the draft is permanently discarded: retry-generation failure or any second-check timeout, malformed response, low confidence, provider error, or audit-write failure returns the deterministic refusal. Where possible, mark the first decision review `open` with reason `grounding_recheck_unavailable`; inability to write that review never permits either draft to escape.
- If the retry generation itself fails, keep the first draft discarded, return the deterministic refusal, and open the decision review item. Dashboards and eval artifacts report total request cost as first generation + first Jev check + retry generation + second Jev check, not only the final attempt.
- Use at least 150 sealed held-out cases, including at least 50 unsupported/partial/wrong-language cases. Require 100% blocking after retry for the frozen high-risk unsupported set, at least 99% preservation of supported answers, zero evidence/permission bypasses, and report added p50/p95 latency and retry rate before activation.
- Live verification is one bounded synthetic/public query per supported, retry-success, and refusal outcome; company-data proof waits for the vendor/data approval. If the policy is not activated in the landing session, open exactly one leftover-proof issue for this step.
- Do not begin Step 9A or 9B while issue #15's connected-answer live proof remains open unless that owner explicitly hands the proof to this workstream; one session may not own both unproven outcomes.
- The verifier proves only a twice-failed, successfully audited grounding decision—or a failed/unavailable retry check after a successfully audited first rejection—opens review; resolution/dismissal is admin-only and idempotent; a **first-check** Jev provider/audit failure does not create a false review item; page/detail permission tests remain green.
- The verifier also proves one supported response records one generation run/one decision; a corrected response records two distinct generation runs and two parent-linked decisions, each with its own generation subject and the same complete query/evidence subjects; deleting the first, middle, or latest contributing message invalidates the result; a refused response retains both attempt audits/decisions but persists only the refusal message; broken/mismatched parent or subject linkage cannot authorize output; and aggregate usage/cost includes every attempt.
- Explicit refusal fixtures cover second-check timeout, malformed response, provider error, low confidence, and final decision-audit write failure; none may persist or return the retry text.

#### Step 9C — Dispose of future advisory ideas without bundling them

- Do not implement claim kind/role/impact/domain/sensitivity classification, claims advice, entity-proposal advice, extraction A/B judging, meeting ranking, translation verification, or reviewer-group suggestions under this plan. They have different data, safety, UI, and acceptance contracts and violate the one-outcome-per-session rule when bundled.
- At closeout, record each idea on issue #14 as rejected or deferred. Any idea Albert retains gets its own issue and implementation-plan-writer plan with exact files, dataset, thresholds, commands, data-class approval, rollback, and one STATUS row before code begins.
- Until then: no claim auto-approval, entity auto-merge, meeting auto-ingest/dismiss, translation acceptance, individual profiling, or reviewer assignment may depend on Jev.

**Verification gate:** issue #14 has one explicit disposition/link per idea and repository search shows no unplanned Jev advisory call sites.

### Phase G — Reconcile and retire

#### Step 10 — Documentation and closeout

- Update `docs/architecture.md`, `docs/configuration.md`, `docs/deployment.md`, and `DECISIONS.md` with only behavior that actually landed.
- Update this STATUS table after every step; preserve rejected pilot results and threshold rationales.
- Update the admin settings/job-brief documentation only for active controls.
- Verify decision-run/cost dashboards include TypeSafe decisions beside, but never mislabelled as, generation model runs.
- Close or explicitly defer every issue #14 scope item. If a use case is rejected, record why and remove dead flags/code.
- The successor session that completes the next step retires the previous handoff under the repository successor rule. Delete this plan only after all retained scope is complete, deployed/proven as applicable, and issue #14 closes.

**Verification gate**

- Current main, CI, Vercel, and Trigger deployment SHAs/IDs are recorded.
- No stale open feature flag or unowned proof issue remains.
- The linked handoff is retired by the successor rule, and the router no longer points to a completed plan.

### Trust-boundary adversarial-cases table

Every row names a required automated test. This table applies before any production activation.

| External input / boundary | Hostile or failure case | Required proof |
| --- | --- | --- |
| TypeSafe API key | Missing, malformed, revoked, or accidentally included in an error | `typesafe-decision-contract`: preflight/failure is redacted; fallback runs; no key substring in logs |
| TypeSafe response | Wrong answer type, missing question ID, probability outside 0–1, probabilities not summing acceptably | Contract test rejects response as `invalid_response`; caller preserves current behavior |
| Model alias/version | `jev-latest` moves or response reports unexpected resolved version | Contract test requires pinned request and logs resolved version; version mismatch prevents active effect |
| Service availability | Timeout, connection reset, 429, 529 | Mocked transport test proves bounded behavior, visible failure record, and current-path fallback |
| Cancellation/deadline | SDK retries or a late response outlive the caller's latency budget | Fake-clock test proves one total deadline aborts transport/retries and a late result cannot affect behavior |
| Request size/count | State+longest question or complete serialized request exceeds conservative byte caps, or question/option counts exceed app limits | Boundary/multi-byte/JSON-overhead tests refuse before network call and record `policy_blocked` |
| Choice cardinality | More than 255 candidates | Builder test shortlists deterministically or refuses; it never truncates silently |
| Prompt injection in state | Source text says to ignore criteria or choose a specific answer | Per-pack injection fixtures; result cannot bypass deterministic candidate/permission gates |
| Adversarial option text | Candidate label contains instructions, HTML, or control text | Pack encodes candidates as data with stable IDs; verifier proves only supplied IDs can return |
| No valid option | None of the candidates applies | Every Choice pack that can miss includes `none/no_supported_candidate`; test proves fallback |
| Ambiguity | Two near-equal candidates or diffuse probability | Threshold test routes to fallback/review; no forced autonomous choice |
| Negation and qualification | “Not required”, “except seasonal”, conditional/temporal scopes | Domain-specific fixtures prove the pack distinguishes support, contradiction, exception, and unrelated |
| Arithmetic/date content | Exact counts, deadlines, date order, rate caps | Test proves arithmetic/date/limit logic remains code-only and is not sourced from Jev Score |
| Unsupported language | Chinese or mixed-language input below evaluated support | Language-policy test keeps current path; no hard exclusion or skip |
| Sensitive/HR content | Employee complaint, private HR matter, personnel name | Data-class gate blocks network unless explicitly approved; sensitivity-positive current gate remains authoritative |
| Licensed source | R2 or uploaded licensed text sent before vendor approval | Data-class test blocks call; synthetic fixture path still works |
| Duplicate/replayed result | Same request retried or late response arrives after state changes | State/input hash test prevents applying stale judgment to changed state; duplicates remain auditable |
| Stale disposition identity | Policy is revoked or model/pack/threshold/source version changes | Lookup test requires exact policy, requested/resolved model, pack, threshold, decision-key, and source hashes; old disposition never reactivates |
| Logging | Raw employee/source text or full response appears in general logs | Log-capture test asserts redaction; decision tables keep hashes, bounded answers, subject links, and policy metadata—not raw state |
| Audit persistence | Pending run, subject-link, final decision, or combined business-effect write fails before/after provider success | Fault-injection test proves Jev effect is discarded, current behavior runs, and no partial record is labeled successful |
| Data-class downgrade/policy drift | Caller labels employee/licensed/mixed content as public, omits provenance, uses a pack wider than policy, or references a revoked policy | Provenance/policy test recomputes the union, adds `unknown_restricted` when incomplete, requires `actual ⊆ pack ⊆ active version`, records that version, and blocks before network access |
| Pasted free-text provenance | Employee/MCP text embeds licensed, internal, HR, or customer material that its channel identity cannot prove | Content-independent mapping applies the full possible union plus `unknown_restricted`; calls remain blocked unless every class is approved, and any future narrowing needs its own reviewed deterministic plan |
| Process crash | Worker/web process dies after pending insert or provider response | Fake-clock/restart test discards stale pending rows, applies no effect, and permits one clean retry |
| Overlapping extraction windows | One window is Jev-negative while another owner extracts or fails | Owner-reconciliation matrix proves a completed owner wins and only all-negative ownership becomes skipped |
| Production drift | New business language makes a formerly safe negative gate miss valuable content | Deterministic canary/human-label test crosses the limit, atomically changes only that flag to `shadow`, and alerts admins |
| Source erasure/retention | Query origin, message, either claim in a multi-claim decision, claim evidence, document/chunk, candidate evidence, any supplied entity candidate, relationship, model run, or reviewer employee is deleted or retention expires | Typed-FK, erasure-trigger, query-origin expiry, and retention tests discard/delete the affected run, remove/null links, and preserve unrelated audit records without raw text |
| Long-lived extraction skip | Decision audit expires while a `skipped_by_decision` batch/message still needs recovery | Batch-level version/key snapshot survives run retention; replay test deletes the run first and still restores only the exact eligible window |
| Direct database access | Anonymous or authenticated non-admin client queries/mutates a decision table directly | RLS integration tests deny every new table; admin gets bounded reads only and trusted server/service paths own mutations |
| Release ordering | Auto-deployed web code queries decision tables before production migration | Two-PR Step 1A/1B gate proves schema migration and RLS in production before any dependent import/query merges; pre/post admin-layout smoke tests pass |
| Runtime secret drift | Key exists only in 1Password or one host, or a deployment predates the env update | Separate Vercel Production and Trigger `prod` names-only checks, post-update redeploy IDs tied to merged SHAs, and one public-synthetic target-path probe each |
| Trigger capacity | Decision maintenance accidentally adds one or more schedules to the existing 9/10 project | Static export-count test proves no new `schedules.task()` and the worker deployment proves the project remains at 9/10 schedules with its reserved headroom |
| Spend cap | Parallel/restarted calls or run retention race past or silently refill the approved balance | Permanent spend-epoch row serializes reservations; tests delete all child runs and prove the microusd cap remains spent/blocked until an owner-authorized replacement epoch |
| Active config drift | Model/pack/threshold/policy changes while a use case remains active | Locked change forces shadow, clears old evidence, increments generation, discards in-flight results, and requires new exact-fingerprint held-out/review approval |
| Shared scheduler failure | One transient provider batch fails but the ten-minute Trigger run reports success | Mixed healthy/failing fixture preserves retryable state, completes healthy work and decision maintenance, marks the job failed, and rejects the scheduled run |
| Cost calculation | Missing token usage or changed price | Test records cost unknown rather than zero; pricing constant/version is explicit and documented |
| Feature flag | Missing, malformed, or unexpected value | Config test defaults to `off`; active behavior requires exact `active` |
| Deterministic gate conflict | Jev says approve/match but exact evidence, permission, status, or type check fails | Integration test proves deterministic rejection wins every time |
| Live Teams direct mention | Jev says “none” on an explicit Oracle invocation | Live-gate test proves direct mention bypasses Jev suppression |
| MCP disabled capability | Jev selects a disabled or unauthorized tool | Registry intersection test removes it and falls back safely |
| MCP exact-name regression | Jev assigns higher probability to a different tool than an enabled exact-name query | Deterministic preflight pins the exact enabled match first; limit-1/limit-2 tests prove Jev cannot displace it |
| Synthetic probe spoofing | An arbitrary MCP caller copies the probe text or supplies a synthetic flag to bypass the data policy | Only the code-owned builder plus exact fixture/registry hashes can create the synthetic origin/class; near-matches and caller assertions are blocked before transport |
| Entity metadata provenance | Labels/aliases are sent without linking, classification, or invalidation when the registry changes | Every serialized candidate has a typed entity subject and conservative class union; mutation changes input identity and deletion discards the whole decision |
| Retrieval false negative | Jev rates valid approved evidence low | Shadow/rerank-only test proves candidate remains available until recall acceptance is met |

## 10. Tests required

### New foundation tests

- `packages/ai/src/__verify__/typesafe-decision-contract.ts`
  - validates all three primitives and normalized responses;
  - rejects malformed answers/cardinality/state/data-class violations, mixed unapproved classes, unknown provenance, and caller downgrade attempts;
  - tests 100/101-question boundaries, 255/256 Choice options, Score levels 1/2/10/11 (only 2–10 pass), exact serialized 32,000/64,000-byte edges, JSON overhead, many short questions, and multi-byte Chinese text before any mocked transport call;
  - verifies redaction, pinned model, resolved version, tokens/cost/latency, and failure taxonomy;
  - uses an injectable fake transport and requires no live key.
- `packages/db` migration/schema tests verify the dedicated decision tables, constraints, indexes, RLS, immutable successful outcomes, query-origin/subject links, and current-version disposition lookup; migration catalog verification proves every new hand-written SQL file is listed in `packages/db/migrations/sql/README.md`.
- `packages/ai/src/__verify__/typesafe-decision-live.ts`
  - opt-in only; uses a synthetic public fixture;
  - exits non-zero on provider failure or contract drift;
  - prints only summary metrics, never key/state bodies.
- Add scripts `verify:typesafe-decision-contract` and `verify:typesafe-decision-live` to `packages/ai/package.json`; only the no-key contract verifier belongs in routine CI initially.
- Add root `verify:jev-contract` to `package.json` and an explicit network-free “Jev decision contract” step to `.github/workflows/pr-check.yml`. When claim support/contradiction/live gates land, also add named CI steps for existing `@oracle/engines verify:r5` and `verify:r11.1`; they are mandatory safety regressions and are not currently CI-wired. Every later network-free verifier is wired into the affected package's existing required suite or added as its own named PR-check step in the same PR; an eval script that CI never calls is unfinished.

### Per-use-case tests

- MCP: extend `apps/web/lib/mcp/__verify__/mcp-registry.ts`.
- Entity selection: extend `packages/ai/src/__verify__/entity-aware-retrieval.ts`; live fixture remains opt-in.
- Responsibility selection: add isolated verifier without editing the live R2 prompt/contract.
- Extraction prefilter: `apps/workers/src/__verify__/jev-extraction-prefilter.ts`.
- Claim support: `apps/workers/src/__verify__/jev-claim-support.ts` plus existing R5/promotion/auto-approval suites.
- Contradiction: `apps/workers/src/__verify__/jev-contradiction-screen.ts` plus existing interjection tests.
- Live Recall: `apps/workers/src/__verify__/jev-live-recall-gate.ts`.
- Retrieval reranking: `packages/ai/src/__verify__/jev-retrieval-rerank.ts`.
- Chat grounding: `apps/web/lib/__verify__/jev-chat-grounding.ts`.
- Chat audit schema: Step 9B-1 migration tests prove nullable `model_runs.output_hash` on fresh and current-snapshot databases; Step 9B-2 tests prove each attempt writes the hash of its exact generated bytes and decision identity uses that same value.
- Extraction recovery: the prefilter verifier exercises dry-run and applied `scripts/replay-jev-extraction-skips.ts` against isolated fixture rows in both dispatch modes.
- Decision review lifecycle: add an admin-page verifier for open/resolved/dismissed states, idempotent actions, redaction, and non-admin denial.
- Decision health: add a fake-clock/database verifier that races at least 100 parallel calls for the **same** identity and 100 distinct keys; prove one reservation/counter increment for the duplicate race, exact first-N weekly minimum (or all lower traffic), every-tenth post-minimum sampling, atomic agreement-review quota, rolling denominators, human-adjudication updates, fenced `active`→`shadow`, alert emission, and isolation from unrelated flags. Change each fingerprint component midweek and prove every new configuration starts its own first-N cohort.
- Pending reconciliation/retention: export `runDecisionAuditMaintenanceOnce` for a fake-clock fixture that seeds unrelated stale keys, invokes the shared ten-minute drain hook, proves all deadline+grace rows discard in bounded pages, proves fresh rows remain, and covers query-origin expiry plus every retention/erasure age boundary and orphan cleanup.
- Schedule-capacity/failure verification counts `schedules.task()` exports before/after, requires the total to remain nine, and proves `claim-extraction-batch-drain` invokes decision maintenance without weakening its original drain. A fixture injects one transient provider-batch failure plus one healthy batch: the healthy batch completes, the failed row remains retryable with error metadata, decision maintenance still runs, the scheduled `job_runs` row is failed, and the task rejects/non-zero; a separate decision-maintenance failure produces the same visible failure without corrupting batch state. Record a successful worker deployment/capacity result before completion.
- Each accepted pilot adds a versioned Markdown result under `evals/jev/` with dataset provenance, exact command, model version, question-pack version, threshold curve, errors, latency, tokens, total cost, and cost per correct decision.
- Every activation artifact identifies disjoint tuning and sealed held-out dataset versions, predeclared sample/class counts, label rubric, independent 20% label-agreement result for material gates, threshold chosen from tuning only, and one untouched held-out score. Re-running after a failed held-out gate requires a newly versioned held-out set; never tune against the failed acceptance cases and call the rerun independent.

### Existing commands that must stay green

- `pnpm --filter @oracle/ai typecheck`
- `pnpm --filter @oracle/workers typecheck`
- `pnpm --filter @oracle/web typecheck`
- `pnpm --filter @oracle/ai verify:r2`
- `pnpm --filter @oracle/ai verify:entity-aware-retrieval`
- `pnpm --filter @oracle/ai verify:retrieval-filter-parity`
- `pnpm --filter @oracle/ai verify:chinese-retrieval`
- `pnpm --filter @oracle/engines verify:r5` for claim-support/evidence-validator changes
- `pnpm --filter @oracle/engines verify:r11.1` for contradiction/live-interjection changes
- `pnpm --filter @oracle/workers run verify:r2-responsibilities` when any responsibility fixture/helper is touched
- `pnpm --filter @oracle/workers run verify:r2-production-replay` when any responsibility reader/helper is touched
- `pnpm --filter @oracle/web verify:mcp` when MCP code is touched
- `pnpm run verify:vercel-guards` for web/retrieval changes
- `pnpm typecheck`
- `pnpm build:vercel` before web shipment
- `git diff --check`

Tests must be quiet on success and must report exact failing cases on failure. Live tests are never routine CI until credentials, rate limits, and data classification are settled.

## 11. Constraints, standing rules, and gotchas

- Start every implementation step in its own current-upstream worktree and declare its task class with `ai-task-gates`.
- One session owns one unproven live behavior. Do not bundle MCP, extraction, contradiction, or Teams production proofs.
- Never push directly to `main`; open, review, and merge the PR. Documentation-only PRs may use the documented owner override after verifying every changed file is prose.
- Before first commit, verify `Albert Hazan <u2giants@users.noreply.github.com>` with `git var GIT_COMMITTER_IDENT`.
- Stage only owned files. Do not touch the dirty shared checkout or active R2 worktree.
- Secrets live only in 1Password vault `vibe_coding`; use `secrets-to-1password` for creation/update and never expose values.
- `TYPESAFE_API_KEY` is server-side only. Never put it in client bundles, browser env, logs, issue/PR text, or command arguments.
- Keep TypeSafe SDK logging at warning/error; debug request bodies can expose state.
- Jev accepts text only. Images/audio/video must follow existing transcription/parsing paths before any bounded text judgment.
- Pin `jev-1.13.0`; upgrades require rerunning every active pack's evaluation and thresholds.
- Keep arithmetic, dates, counts, limits, price calculation, lifecycle, permissions, and exact matching in code.
- Use `none` outcomes and uncertainty fallbacks. Never force a choice from incomplete candidates.
- Do not infer multilingual safety from English results. Evaluate `zh-CN` separately or leave it on the current path.
- Existing provider batch behavior is unrelated. Do not route Jev through generative Batch APIs or the model catalog.
- The active R2 handoff remains open. Do not alter its prompt/production behavior while doing the isolated Jev quote-selection evaluation.
- No shared-database structural change is planned. If one emerges, stop and route it through the applicable database governance instead of improvising.
- Before any production trigger or deployment action, run the required task-gate check and obtain independent reviewer approval where the standing production rule requires it.
- Scheduled/worker calls must fail visibly in telemetry; a Jev outage may preserve current product behavior but must not look like a successful Jev decision.

## 12. Access and environment

- Machine: `916-alien`, Windows 11, PowerShell 7.
- Canonical local checkout: `D:\repos\oracle` (landing-only; currently contains unrelated uncommitted work and must not be edited by implementation sessions).
- GitHub CLI is authenticated for `u2giants`.
- Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`; production URL `https://oracle.designflow.app`.
- Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`; authenticated management/deploy access is described in `docs/configuration.md` and `docs/deployment.md`.
- Supabase project `eqccjfbyrywsqkxxpjvg`; application data belongs to this application.
- Secrets vault: 1Password `vibe_coding`. Planned item: `TypeSafe AI - The Oracle`; it does not exist until Step 0 creates it.
- Local setup: Node 20+ and pnpm 9.5. Run `pnpm install --frozen-lockfile` in a fresh worktree.
- Local web: `pnpm dev`; workers: `pnpm workers:dev`.
- Official TypeSafe references:
  - [System One overview](https://docs.typesafe.ai/concepts/system-one)
  - [How to build](https://docs.typesafe.ai/concepts/how-to-build-with-system-one)
  - [JavaScript SDK](https://docs.typesafe.ai/sdk/javascript)
  - [API](https://docs.typesafe.ai/api)
  - [Models/pricing/limits](https://docs.typesafe.ai/models)
  - [Confidence](https://docs.typesafe.ai/confidence)
  - [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13)
  - [Citation verification pattern](https://docs.typesafe.ai/cookbooks/citation_check)
  - [Data processing addendum](https://typesafe.ai/legal/data-processing)

## 13. Definition of done, risks, rollback, and open questions

### Definition of done

- [ ] Vendor/data decision is recorded, and credentials/data classes match it.
- [ ] One immutable active runtime data-policy version enforces the approved matrix; decision runs record it, revocation blocks calls/demotes dependent modes, and documents remain blocked until durably classified.
- [ ] Separate decision client exists with pinned model, redaction, normalized results, and no generation-adapter contamination.
- [ ] Every call has one dedicated decision run with derived class set, subjects, bounded answer, usage, cost, latency, resolved model, pack/threshold versions, status, policy outcome, and behavior-effect audit fields.
- [ ] Foundation and adversarial contract tests pass.
- [ ] Each retained use case has its own fixture, shadow artifact, thresholds, acceptance/rejection decision, feature flag, PR, CI evidence, and live proof where activated.
- [ ] Every active hard-negative gate has sampled current-model canaries, an owned human-review queue, measured rolling error, alerting, and tested automatic fallback to `shadow`.
- [ ] Every use case has its named mode/pack/threshold settings seeded `off`, an audited authorized transition path, and no environment-only activation bypass.
- [ ] Activation generations fence every final effect; emergency off, policy revocation, auto-shadow, or reactivation invalidates in-flight/old results and starts a fresh fingerprinted canary cohort.
- [ ] Pending-run crash recovery, bounded retention, typed-link source erasure, extraction overlap reconciliation, and skip replay are proven on isolated fixtures.
- [ ] Every extraction skip keeps a bounded replay snapshot on its owner batch until replay/re-extraction commits, even after its decision audit ages out.
- [ ] All nine decision tables have tested RLS, and the schema-only production migration is proven before any dependent web/worker code merges or deploys.
- [ ] Decision maintenance reuses the existing ten-minute drain schedule, the project remains at 9/10 schedules after deployment, and no reserved headroom is consumed.
- [ ] Query-derived decisions have an exact erasable origin; static-token MCP origins and their hashes are deleted within 24 hours plus one schedule interval.
- [ ] The owner-approved evaluation cap is atomically enforced by a permanent spend-epoch ledger before transport, survives all decision-run retention, never auto-refills, and only an authorized control event can replace it.
- [ ] Free-form employee/MCP text receives the full conservative possible-class union; only exact repository-owned fixture builders may grant `public_synthetic`, and no caller or semantic guess can downgrade pasted content.
- [ ] Every entity candidate serialized to Jev has a typed subject link, conservative registry-data classification, content-hashed input identity, and tested whole-run invalidation on mutation/deletion.
- [ ] Enabled normalized exact capability-name matches are deterministically pinned ahead of Jev ranking and cannot be displaced at any result limit.
- [ ] Any model/pack/threshold/data-policy change forces shadow and requires new exact-fingerprint held-out/reviewer evidence before reactivation.
- [ ] `TYPESAFE_API_KEY` is delivered without exposure and independently proven in Vercel Production and Trigger `prod`; each target is redeployed afterward from the applicable merged SHA and passes one public-synthetic target-path probe before its first pilot.
- [ ] Deterministic evidence, permissions, status, approval, auth, direct-mention, cooldown, rate-cap, and transaction tests remain green.
- [ ] English and Chinese behavior are explicitly separated where relevant.
- [ ] Every production change is merged through GitHub, deployed from the merged SHA, and verified on the correct Vercel/Trigger target.
- [ ] Code that lands without live proof has exactly one owned leftover-proof issue for that outcome.
- [ ] Documentation and this STATUS table reflect reality; rejected pilots and dead ends remain recorded.
- [ ] Issue #14 is closed only when all accepted scope is complete and remaining ideas are explicitly deferred/removed.
- [ ] The handoff/router links are retired when the workstream is genuinely complete.

### Rollback

- Every use case has `off|shadow|active`; first set the affected use case to `off` and redeploy only if code-path changes require it.
- A Jev service failure before any audited active outcome preserves the pre-Jev behavior. Active negative gates can create durable dispositions, so rollback must reconcile those records rather than claim that no repair is needed.
- Extraction rollback runs `scripts/replay-jev-extraction-skips.ts` in dry-run, reviews the exact durable batch pack/threshold/data-policy snapshot, window, and linked message IDs, then applies the bounded reset to `pending` and verifies the existing extractor completes them. Retained decision rows remain immutable audit evidence, but replay never depends on their surviving the 365-day retention window.
- Contradiction rollback turns the gate off; the watcher ignores Jev negative dispositions when mode is off. A pack/threshold version change naturally reconsiders pairs because only a matching current-version disposition suppresses repeat evaluation.
- The foundation migration is additive. Removing Jev code does not drop its audit tables; table removal, if ever desired after retention review, is a separate migration.
- If an active pilot causes quality regression, capture the failing request hash/question-pack version/result, turn only that pilot off, and preserve the evidence for evaluation. Do not disable unrelated Oracle capabilities.

### Principal risks

- Vendor retention/residency/subprocessor terms may not be acceptable for employee or licensed data.
- False-negative extraction/contradiction gates could silently suppress knowledge or intervention.
- Confidence may be well calibrated in aggregate but wrong on a specific Oracle subdomain.
- Jev is primarily English; Chinese and mixed-language content may underperform.
- Prompt injection or adversarial source text can influence the decision.
- Large/noisy state can cause context rot and erase the expected quality advantage.
- Provider launch pricing, limits, model behavior, and availability may change.
- A cheap additional verifier can still increase total latency if placed on synchronous chat paths.
- Too many small packs/flags can become maintenance burden; reject low-value pilots instead of keeping permanent experiments.

### Open questions and decision criteria

1. **Will TypeSafe provide enterprise ZDR and acceptable DPA/security terms?** If no, restrict the integration to synthetic/public/low-sensitivity state or stop the company-data pilots.
2. **Does a $5 capped evaluation prove real value?** Continue only when cost per correct decision and total workflow cost improve without missing the quality gate.
3. **Which pilots survive?** Acceptance is per use case, not ideological. A pilot that fails accuracy, privacy, latency, or maintenance value is documented and removed.
4. **Should Jev ever make a hard negative decision?** Only after its use-case-specific frozen fixture proves required recall and an uncertainty/failure fallback exists. Until then, rerank, veto, or shadow only.

## Mandatory plan self-audit

1. **Could a brand-new AI session execute this plan without asking a question? — Yes.** Sections 1–4 define the business outcome, application, trigger, and boundaries; §5–§8 carry the current state, evidence, rejected approaches, locked/open decisions; §9 gives ordered file/function-level steps and verification gates; §§10–13 specify tests, rules, access, landing, risks, rollback, and owner decisions.
2. **Does the plan carry the investigation's background, nuance, and rejected approaches? — Yes.** Sections 5–7 preserve the audited code seams, active R2 collision risk, privacy boundary, model limitations, and every important rejected architecture. The adversarial table converts trust-boundary risks into named tests.
3. **Is the ultimate goal clear enough to steer a correct judgment if a step is wrong? — Yes.** Section 1 makes cost reduction subordinate to knowledge recall, evidence quality, privacy, and employee trust, and explicitly says the goal overrides a conflicting step.

Checklist result: all 13 required sections are present; the plan is self-contained; every build step names concrete files/functions and a verification gate; trust-boundary cases name tests; locked/open decisions and out-of-scope items are explicit; test commands, secrets locations, deployment/proof requirements, and plan/handoff backlinks are present. **Self-audit passed on 2026-09-20.**
