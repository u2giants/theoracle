# TypeSafe Jev Decision Layer Implementation Plan

Tracking issue: [u2giants/theoracle#14](https://github.com/u2giants/theoracle/issues/14)

Session handoff: [`HANDOFF.d/2026-09-20T1411Z-916-codex-jev-integration-plan.md`](HANDOFF.d/2026-09-20T1411Z-916-codex-jev-integration-plan.md)

Plan created: 2026-09-20

Source baseline: `origin/main` at `824c1ff9f2caa47428c63df038d229a44e2db515`

## STATUS — read this first

| Step | Status | Date | Evidence / owner |
| --- | --- | --- | --- |
| 0. Vendor, privacy, and test-data boundary | ⬜ open | 2026-09-20 | Issue #14; owner decision in §8 and §13 |
| 1. Decision-client foundation | ⬜ open | 2026-09-20 | Fresh implementation session starts here after Step 0's synthetic-only boundary is accepted |
| 2. Observability, cost, and failure contract | ⬜ open | 2026-09-20 | Must land with Step 1 or the client is not usable |
| 3. Low-sensitivity MCP capability-search pilot | ⬜ open | 2026-09-20 | Separate session and live-behavior outcome |
| 4. Bounded entity-selection pilot | ⬜ open | 2026-09-20 | Separate session and live-behavior outcome |
| 5. Responsibility quote-candidate evaluation | ⬜ open | 2026-09-20 | Separate session; must not alter the active R2 reader workstream |
| 6. Extraction prefilter shadow evaluation | ⬜ open | 2026-09-20 | Separate session and worker deployment outcome |
| 7. Claim-support and auto-approval veto checks | ⬜ open | 2026-09-20 | Separate session; veto/review only |
| 8. Contradiction and live-meeting decision pilots | ⬜ open | 2026-09-20 | Two separate sessions; never combine their live proofs |
| 9A. Retrieval-reranking pilot | ⬜ open | 2026-09-20 | Separate session and acceptance evidence |
| 9B. Chat-grounding pilot | ⬜ open | 2026-09-20 | Separate session and acceptance evidence |
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
   - admin review assistance.
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
10. **Dedicated minimal audit schema.** Add `oracle_decision_runs`, `oracle_decision_subjects`, append-only `oracle_decision_adjudications`, and `oracle_decision_control_events` in the foundation migration specified below; do not overload generation-oriented `model_runs`. No business claim, contradiction, message, or permission rule moves into these tables.
11. **No autonomous governance.** Claim approval, entity merge, meeting ingest/dismiss, reviewer assignment, and translation acceptance remain human/deterministic decisions.
12. **One production outcome per session.** MCP, entity selection, extraction prefilter, contradiction gate, live Recall gate, reranking, and grounding are separate implementation/live-proof sessions.
13. **Separated tuning and acceptance evidence.** Thresholds are chosen only on a versioned tuning set. Activation is judged on a sealed held-out set that was not used to write prompts, choose thresholds, or select examples. Each pilot records its minimum sample and class counts before the held-out run; material gates double-label at least 20% of cases, report agreement, and adjudicate disagreements before scoring.
14. **Audited effects only.** A Jev result may affect behavior only after its final dedicated decision row, typed subject links, usage, bounded answers, and policy outcome commit successfully. Any audit-persistence failure discards the Jev result and preserves the current path.
15. **Hard-negative canaries never stop.** Any active Jev decision that suppresses extraction, contradiction adjudication, or live-meeting analysis must deterministically sample at least 10% of negatives and the stated first-N weekly minimum (or all negatives when traffic is lower) into the unchanged current model path. Every disagreement plus at least 10 randomly selected agreements per use case per week (or all when fewer exist) enters human review, so shared model blind spots remain measurable. A human-confirmed safety miss or rolling error threshold automatically changes only that use case from `active` to `shadow` and alerts admins. Frozen acceptance is necessary but never substitutes for production drift detection.

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
- Until approval, use only synthetic/public fixtures. Do not assume an existing `TYPESAFE_API_KEY` is approved for company data.
- Record an explicit allow/deny matrix for `public_synthetic`, `internal_company`, `employee_communication`, `licensed_content`, `personnel_hr`, `customer_personal`, and `unknown_restricted`. Approval of one class never implies another; mixed input is allowed only when every derived class is allowed. `unknown_restricted` is denied by default.
- Record the trusted provenance mappings used by `data-classification.ts`; do not rely on semantic guessing or on a caller-provided downgrade. Where a document/source lacks durable classification metadata, leave it `unknown_restricted` until a separately reviewed backfill/admin classification flow exists.

**Dependencies / parallelism**

- Synthetic client/harness work in Step 1 may proceed before vendor approval.
- Every Oracle-data pilot waits for the contract/DPA and credential note.

**Verification gate**

- Issue #14 contains the dated approval or explicit synthetic-only limitation.
- The 1Password item exists by title and field presence; no value appears in terminal output.
- Tests prove every unapproved member of the derived class set, mixed-class input, unknown provenance, and a falsified caller downgrade are refused before any network call.

**Natural cut:** end the session here if the owner/vendor decision is not complete. Do not pretend synthetic success authorizes company data.

#### Step 1 — Add the decision-client foundation

**Files/functions**

- `packages/ai/package.json`: add pinned compatible `@typesafe-ai/sdk`; update `pnpm-lock.yaml` through pnpm, never by hand.
- New `packages/ai/src/decisions/types.ts`: define `DecisionState`, question-pack metadata, Noul/Choice/Score request types, normalized answer types, resolved model, usage, latency, raw-response boundary, derived data-class set, and policy outcome.
- New `packages/ai/src/decisions/typesafe-client.ts`: wrap `TypeSafeClient.systemOne`, default to the pinned model, inject the SDK client/fetch for tests, normalize errors, and calculate input cost from the documented price.
- New `packages/ai/src/decisions/question-pack.ts`: require stable pack ID/version, an approved data-class allowlist, state-size check, expected language, complete question meanings, and a caller-approved total deadline. IDs are audit identifiers, not hidden instructions.
- `packages/db/src/schema.ts` plus a new generated Drizzle migration and, where constraints need it, one new hand-written migration under `packages/db/migrations/sql/`: add the two tables below through the repository's normal `pnpm db:generate` / `pnpm db:migrate` journaled path. Never use `drizzle-kit push` or Supabase `apply_migration`.
  - `oracle_decision_runs`: `id`; `use_case`; `question_pack_id`; `question_pack_version`; `threshold_policy_version`; `mode`; requested/resolved model; provider request ID; `input_hash`; `decision_key`; `data_classes_json`; `status` (`pending|succeeded|failed|discarded`); bounded option-ID/probability `answers_json`; `policy_outcome` (`shadow_only|fallback|continue_current|skip_current|rerank|retry|refuse|review`); `affected_behavior`; `is_canary`; token/cost/latency fields; error class/redacted error; comparator kind/version/status (`not_sampled|pending|completed|failed`), bounded comparator outcome, agreement status (`unreviewed|agree|disagree`); optional `review_status` (`open|resolved|dismissed`), reviewer FK with `ON DELETE SET NULL`, review reason code, review timestamp; created/completed timestamps. No free-text reviewer note or raw state is stored. Add indexes on `(use_case,status,created_at)` and `(use_case,decision_key,question_pack_version,threshold_policy_version)`, with a uniqueness rule preventing duplicate successful active disposition for the same versioned decision key.
  - `oracle_decision_subjects`: `decision_run_id`, `effect`, and exactly one typed nullable FK among `message_id`, `claim_id`, `document_id`, `extraction_batch_id`, `extraction_candidate_id`, and `model_run_id`; a check constraint requires exactly one target. Each FK deletes only its subject-link row when the source is erased. Uniqueness is `(decision_run_id, effect, target_id)` for each target column; target lookup indexes are deliberately non-unique so one claim/candidate/model run can participate in many decisions and contradiction pairs. A decision run may have zero subject rows only for the named subjectless use cases `mcp_capability_search` and synthetic contract/live probes; their `decision_key` is the request hash and they still obey retention.
  - `oracle_decision_adjudications`: append-only human labels for a decision run: reviewer FK `ON DELETE SET NULL`, verdict/reason code, `safety_miss`, created timestamp, and optional `supersedes_id`. Never update an adjudication; the latest non-superseded row is authoritative. Rolling health uses only final human adjudications, never the comparator model alone.
  - `oracle_decision_control_events`: append-only manual/automatic mode-transition and alert record with use case, actor employee FK `ON DELETE SET NULL` or system actor, event type, evidence URL/review commit/data-matrix version where applicable, measured numerator/denominator/threshold for health events, previous/new mode, triggering decision/adjudication IDs, acknowledgement state, and timestamps. Every mode compare-and-set and event insert occur in one transaction.
- New `packages/ai/src/decisions/data-classification.ts`: derive a **set** of source classes from trusted provenance, never from a caller assertion. Initial classes are `public_synthetic`, `internal_company`, `employee_communication`, `licensed_content`, `personnel_hr`, `customer_personal`, and `unknown_restricted`; the effective class set is the union of every input/source class, and any missing/unknown provenance adds `unknown_restricted`.
- New `packages/ai/src/decisions/index.ts` plus `packages/ai/src/index.ts`: export only the decision API; do not expose the SDK throughout apps/workers.
- `.env.example`, `turbo.json`, and `docs/configuration.md`: document `TYPESAFE_API_KEY`, pinned model override for non-production evals only, per-use-case feature flags, and the 1Password location. Keep the key server-side.
- `DECISIONS.md`: record the dated decision that Jev is a decision primitive, not a generative provider.
- `docs/architecture.md`: add the separate decision path beside `OracleAIClient` and state what may never call it.

**Required behavior**

- Empty questions, duplicate IDs, unsupported question types, invalid criteria, over-cardinality Choice, oversized state, disallowed data class, and absent key fail before network access.
- A pack declares an allowlist of data classes approved in Step 0. Central provenance derivation must prove the actual class set is a subset before network access. Caller-supplied labels can only make the set more restrictive; they can never remove a class derived from source records.
- Hard mappings are deliberately conservative and content-independent: arbitrary MCP query text and every employee message/meeting utterance carry `employee_communication`, `personnel_hr`, and `customer_personal` because free text can contain any of them; claims inherit the union of every evidence-source class; retrieved context inherits every included claim/source class; document content is `unknown_restricted` until its stored source classification is explicitly approved. Mixed sources retain every class instead of collapsing to one enum value. Later narrowing requires a separately reviewed deterministic provenance rule, never a semantic guess.
- The API key is never included in thrown errors, raw usage, telemetry, or debug logging.
- The wrapper returns normalized typed answers plus provider `typesafe`, requested model, resolved version, latency, tokens, and computed cost.
- The production default is the pinned version, not `jev-latest`.
- `typesafe-client.ts` enforces the question pack's total wall-clock deadline with `AbortController`; SDK retries share that same budget and cancellation signal. There is no unbounded background request or late result that can affect behavior.

**Verification gate**

- `pnpm --filter @oracle/ai typecheck` passes.
- New `pnpm --filter @oracle/ai verify:typesafe-decision-contract` passes with mocked transport and no real key.
- Root `package.json` exposes `verify:jev-contract`, and `.github/workflows/pr-check.yml` runs it as a network-free required step with a placeholder key that cannot reach the network.
- A repository search proves `TYPESAFE_API_KEY` appears only in env/config documentation and server-side decision code.
- `pnpm db:generate`, migration verification, `pnpm db:check-drift` against the intended non-production target, and schema typecheck pass before any application code consumes the tables. Production migration is its own guarded outcome and must land before an active/shadow deployment that writes decision rows.

#### Step 2 — Integrate observability and failure behavior

**Files/functions**

- New `packages/ai/src/decisions/run-decision.ts`: derive provenance classes, compile the minimal state/question context, insert one `oracle_decision_runs` pending row plus its subject links before the call, then atomically update that row with final status, bounded answers, usage, and policy outcome before returning a result that may affect behavior. Do not copy or write generation `model_runs` records.
- New `packages/ai/src/decisions/reconcile.ts` plus `apps/workers/src/trigger/decision-audit-maintenance.ts`: a five-minute scheduled task marks every `pending` row older than its recorded `deadline_at + 2 minutes` as `discarded/process_interrupted` in bounded indexed pages. `runDecision` also reconciles the same versioned decision key before insert. A stale row can never be applied; a retry creates a new run linked to the same subjects. The task exits non-zero on reconciliation failure.
- New `packages/ai/src/decisions/health.ts`: deterministic hash sampling for hard-negative canaries, comparator-result persistence, append-only human adjudication, rolling error calculations, and an atomic compare-and-set from `active` to `shadow` plus `oracle_decision_control_events` insert when a use case crosses its limit. Never disable unrelated use cases.
- New `apps/workers/src/trigger/decision-audit-retention.ts`: daily bounded cleanup. Delete pending/failed/discarded runs after 30 days, successful shadow runs after 90 days, and successful active runs after 365 days; child subjects/adjudications cascade with the run. Retain an open review until resolved, then apply the active-run clock. Remove an orphan run within 24 hours after all typed subject links disappear. Retain acknowledged control events for 730 days and unacknowledged events until acknowledged; deleted employee/reviewer FKs become null. Store no raw source text, free-text review note, or employee ID outside typed FKs.
- Add `apps/web/app/admin/ai/decisions/page.tsx`, `apps/web/app/admin/ai/decisions/[id]/page.tsx`, and `_actions.ts`: admin-only list/detail over decision runs, default-filtered to `review_status='open'`, with bounded metadata/typed subject links and idempotent actions to mark `resolved` or `dismissed` with reviewer/timestamp/reason code. Never render raw secrets or unapproved source text. Add the page to the existing AI admin navigation so later canaries have a review destination before activation.
- Add `apps/web/app/admin/_components/decision-health-alert-banner.tsx` beside the existing model-attempt banner. It reads unacknowledged health-type `oracle_decision_control_events`, identifies the use case and automatic `active`→`shadow` result, links to the filtered decision review page, and has an admin-only acknowledge action. Do not query or write `model_run_attempts` for Jev alerts.
- Add redacted error taxonomy: `missing_key`, `policy_blocked`, `invalid_request`, `timeout`, `rate_limited`, `overloaded`, `provider_error`, `invalid_response`.
- Add feature-flag helpers that support `off`, `shadow`, and `active` per use case. Default every new use case to `off`; absence is never interpreted as active.
- New `packages/ai/src/decisions/config.ts` owns the exact setting keys: `jev_mcp_capability_search_mode`, `jev_entity_selection_mode`, `jev_responsibility_quote_selection_mode`, `jev_claim_extraction_prefilter_mode`, `jev_claim_support_mode`, `jev_contradiction_screen_mode`, `jev_live_recall_gate_mode`, `jev_retrieval_rerank_mode`, and `jev_chat_grounding_mode`, each seeded `off`; each also has explicit `<key>_pack_version` and `<key>_threshold_version` settings. Unknown values or missing versions resolve to `off`.
- Seed those settings in the foundation migration. Add an admin-only “Jev decision controls” section under `apps/web/app/admin/settings/page.tsx` with a focused server action/component: `off→shadow` requires a pinned pack/version; `shadow→active` also requires the committed held-out artifact URL, approving independent-review commit, and approved data-class matrix version. Every transition writes `oracle_decision_control_events`. Runtime code and automatic health fallback call the same compare-and-set helper; no environment-only or dashboard-only activation exists.

**Required behavior**

- Shadow calls record both Jev's judgment and the unchanged current outcome.
- Shadow/current and canary comparator outcomes are written to the decision run with comparator version/status, and any generation comparator is linked by typed model-run subject. Human adjudication is append-only and is the only source for rolling safety-miss rates.
- Provider failures are visible, bounded, and non-recursive. Do not call a generative model merely to interpret a Jev error.
- Retries remain the official SDK's bounded defaults inside the pack's total deadline; do not add a second retry loop. Initial deadlines are 600 ms for synchronous MCP discovery and 5 seconds for asynchronous worker pilots, then may tighten from measured p95 data.
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
- Crash tests terminate after the pending insert and after mocked provider completion but before final update; advancing the clock runs reconciliation, proves both rows become discarded with no effect, and proves a retry succeeds once without reusing the stale result.
- Migration/schema verification proves the dedicated tables, constraints, indexes, and generated types match this contract.
- Retention/erasure tests delete fixture messages, claims, documents, model runs, and reviewer employees; typed links cascade or null as specified, no stale identifier/free-text survives, orphan runs are pruned, and unrelated decision evidence remains.
- Admin-page tests cover open/resolved/dismissed lifecycle, append-only adjudication/supersession, allowed reason codes, idempotent actions, redaction, typed-link disappearance, and non-admin denial. Banner tests seed a Jev health event—not a model attempt—then prove display, link, automatic mode result, admin-only acknowledgement, and continued visibility of unrelated unacknowledged events.
- Configuration tests enumerate every named mode/pack/threshold key, prove migration defaults `off`, reject missing evidence/version/data-matrix metadata for activation, deny non-admin transitions, persist one control event per successful compare-and-set, and prove automatic fallback uses the same helper without touching another key.

**Natural cut:** land Steps 1–2 together. They form one foundation outcome and must not include a product behavior change.

### Phase B — Lowest-risk product pilot

#### Step 3 — MCP capability discovery in shadow mode, then active if accepted

**Files/functions**

- `apps/web/lib/mcp/registry.ts:67-98`: keep existing lexical/synonym scoring as fallback and comparison baseline.
- Add `apps/web/lib/mcp/decision-capability-search.ts`: build a bounded `Choice` over currently enabled capabilities plus `none`; state contains only the user's capability query and non-sensitive capability names/descriptions.
- `apps/web/lib/mcp/server-tools.ts:103-130`: in `shadow`, record Jev ranking but return lexical results; in `active`, use Jev only when confidence clears the evaluated threshold, otherwise return lexical results.
- Convert the single Choice probability vector into a deterministic ranked list: remove `none`, intersect with enabled capabilities, sort by probability descending, break ties with existing lexical score then stable capability ID, apply the caller's requested `limit`, and return no duplicates. If fewer than `limit` candidates clear their position-specific threshold, fill from the lexical ranking without reordering exact-name matches.
- `apps/web/lib/mcp/__verify__/mcp-registry.ts`: add paraphrases, ambiguous queries, no-match, prompt injection, disabled-capability, non-English, and service-failure cases.
- Add an eval artifact under `evals/jev/mcp-capability-search.md` containing dataset version, lexical baseline, Jev version, accuracy, confusion cases, threshold curve, p50/p95 latency, tokens, cost, and decision.

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
- Active behavior, if enabled, is proven against the live MCP endpoint with a benign query and an ambiguous/no-match query.
- If code lands without live proof, open exactly one leftover-proof issue for this step before ending that session.

**Natural cut:** stop after the MCP result is either activated with proof or recorded as rejected. Do not add entity selection in the same session.

### Phase C — Bounded direct replacements

#### Step 4 — Entity selection

**Files/functions**

- `packages/ai/src/entity-planner-model.ts:55-154`: preserve current registry-candidate construction and final intersection.
- Add a question pack using one Noul per prefiltered entity candidate because more than one entity may be valid. State includes query, entity type, value, label, and aliases only.
- `packages/ai/src/retrieval-plan.ts:227-276`: in shadow, compare Jev selections to current model selections. The first active pilot may add/reorder only Jev-positive candidates within the deterministic registry shortlist while unioning every current-selector result; Jev negatives never remove a current selection. On uncertainty/failure, return the current selector unchanged.
- Extend `packages/ai/src/__verify__/entity-aware-retrieval.ts` and live fixture with aliases, homonyms, multiple entities, no entity, Chinese text, adversarial candidate text, and over-cardinality shortlist handling.
- Add `evals/jev/entity-selection.md` with current-model baseline, labeled result, threshold curve, false-negative analysis, latency, and cost.
- Use separate tuning and sealed held-out entity sets; the held-out set has at least 100 cases, including at least 30 alias, homonym, multi-entity, or explicit-name cases, and is not opened until the pack/threshold is frozen.

**Acceptance criteria**

- Jev can never invent or return an entity outside the supplied registry candidates.
- Explicitly named valid entities have 100% recall in the frozen fixture before active use.
- Low-confidence candidates preserve current behavior; no negative Jev result becomes a hard retrieval exclusion.
- Because the initial active pilot still runs the current selector, it is a quality/measurement pilot, not a cost-saving replacement. Replacing that selector requires a new STATUS row and separate plan after held-out evidence proves recall and defines a safe non-Jev fallback.
- Chinese is separately scored; if it misses the bar, `zh-CN` remains on the current path.

**Verification gate**

- `pnpm --filter @oracle/ai verify:entity-aware-retrieval` passes.
- The live fixture passes only after vendor/data approval; otherwise the step remains shadow-only.
- The current selector's normal `model_run` records its actual selection; a separate Jev `oracle_decision_run` records the shadow selection and links that current model run as a typed comparator subject. Neither table impersonates the other.

#### Step 5 — Responsibility quote-candidate selection evaluation

**Files/functions**

- Do not change `RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT`, the R2 matcher, route, budgets, or production worker.
- Add an isolated evaluator under `packages/ai/evals/` or `apps/workers/src/__verify__/` that reads the immutable responsibility fixture and offered grounded quote candidates.
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
- `apps/workers/src/lib/message-extraction-status.ts`: add window-aware reconciliation. A message is `complete` if any overlapping owner completed extraction; `skipped` only if every owner containing it is `skipped_by_decision`; `failed` only when all non-skipped owners failed and none completed; otherwise it remains `processing`. A negative overlapping window can never overwrite a completed positive owner.
- `packages/shared/src/domains.ts`: add `skipped_by_decision` to the canonical extraction-batch status list and every derived terminal/filter list that should include a deliberate no-model result. Add a new hand-written migration under `packages/db/migrations/sql/` that replaces the existing `extraction_batches_status_check` from migration 13 with the expanded allowlist; never edit the applied migration.
- Update status consumers in `apps/web/app/admin/ai/candidates/page.tsx` and `apps/web/app/admin/ai/runs/[id]/page.tsx` to label/filter deliberate skips distinctly from failures and completed extraction. Update any batch-status exhaustive switches/tests found by the required repository search.
- In `claim-extraction-batch-submit.ts`, track `skippedBatchIds` separately from `submitted/stagedBatchIds`. Pre-provider and post-provider failure cleanup may delete/reset only pending submitted owners/messages; it must retain committed `skipped_by_decision` owners and then run shared message reconciliation. An all-skipped selection completes successfully without creating a provider batch job; it is not reported as “user-message-free.”
- Link the decision to its `extraction_batch_id`, not directly to every repeated message. Commit the successful decision outcome, `skipped_by_decision` batch status, and reconciled message statuses in one transaction. The versioned decision key is the ordered window message IDs plus their content hash; a changed window cannot reuse an old skip.
- Add `scripts/replay-jev-extraction-skips.ts`: dry-run by default; select only `skipped_by_decision` owner windows linked to successful active decisions for an explicit pack/threshold version or UTC window; show exact window/message IDs in a protected artifact; with `APPLY=1`, reset only messages whose current reconciled status is still `skipped` to `pending` after verifying the target database. Never reset a message already `complete`, `processing`, or unlinked.
- Create a pack with independent Nouls for operational fact, decision, rule/exception, metric, and process/handoff detail. Code combines them into `worth_extraction`; one broad question is not sufficient.
- Do not initially change `apps/workers/src/trigger/document-ingestion.ts`; document uploads are denser and higher stakes.
- Add settings/flags: `jev_claim_extraction_prefilter_mode` (`off|shadow|active`) and a versioned threshold policy. Seed/default must be `off`; add any setting row through the repository's governed migration path.
- Add `apps/workers/src/__verify__/jev-extraction-prefilter.ts` and `evals/jev/claim-extraction-prefilter.md`.

**Ground truth and acceptance**

- Build a reviewed dataset containing greetings/boilerplate, implicit rules, negation, exceptions, direct capture requests, short but valuable facts, long irrelevant chatter, and sensitive content.
- A segment with any approved/reviewed operational claim is positive even if the old extractor returned zero; do not use old model output alone as ground truth.
- Require 100% recall on the frozen high-value positive set before active skipping.
- Require a meaningful confident-negative rate (initial target at least 30% of true negatives) or reject the pilot as not worth the complexity.
- In active mode, deterministic hashing sends at least 10% of confident negatives and the first 50 each rolling week (or all when fewer exist) through the current extractor as canaries. All canary disagreements are queued for admin review; any missed high-value claim or more than 1% adjudicated false negatives over the latest 100 canaries atomically changes this use case to `shadow` and raises the existing admin alert.
- Persist the canary extractor's model run as a typed subject, link any produced extraction candidates, and write a bounded comparator version/outcome/agreement to the decision run. Human labels append `oracle_decision_adjudications`; health calculations use those final labels and remain reproducible after restart.
- Direct uploads, explicit capture requests, low confidence, unsupported language, provider failure, and missing key always continue to the current extractor.
- The tuning set and sealed held-out set are disjoint. The held-out set contains at least 200 segments and 50 administrator-confirmed high-value positives; 20% is independently double-labeled and disagreements are adjudicated before activation scoring.

**Verification gate**

- `pnpm --filter @oracle/workers typecheck` and the new verifier pass.
- The verifier runs the same cases through sync and batch policy helpers and proves identical shadow/active/fallback decisions, message status, and audit behavior.
- Overlap fixtures cover negative→positive, positive→negative, all-negative, skipped+failed, and three-window chains in both dispatch modes; reconciliation must match the owner rules above and never mark an extracted message skipped.
- Batch failure fixtures cover mixed skipped/submitted failure before provider acceptance, failure after provider acceptance, and all-skipped input; committed skip owners survive, pending owners follow the existing tracked-batch recovery rules, message statuses reconcile correctly, and the drain never receives a skipped owner as a provider `customId`.
- A recovery fixture creates false-negative window skips in both dispatch modes, proves the dry-run selection, applies the bounded replay, verifies only messages still skipped across all linked owners return to `pending`, and then proves the existing extractor processes them.
- Shadow telemetry covers enough real approved data to calculate false negatives without storing raw employee text in logs.
- The active switch is a separate PR/session with independent review and a worker deployment/live proof.

#### Step 7 — Semantic claim support and auto-approval veto

**Files/functions**

- After deterministic exact-quote validation in `claim-extraction.ts` and `document-ingestion.ts`, ask whether the validated quote/context supports the proposed claim summary and whether it contradicts or omits a material qualification.
- Link each decision to the exact `extraction_candidate_id` plus its evidence message/claim/document subjects as available; the decision key includes candidate content/evidence hashes so one candidate can be rechecked by a new pack version without colliding with other candidates or contradiction pairs.
- `apps/workers/src/lib/document-claim-auto-approval.ts:26-76`: Jev may veto auto-approval or route to review; it may not make an otherwise ineligible claim approvable.
- Add optional typed classification packs for claim kind, semantic role, impact, domains, and sensitivity. Multi-label domains use one Noul each, not one Choice.
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
- Give each claim pair a canonical order-independent `decision_key` from the two claim IDs plus their content hashes. Persist both claim IDs in `oracle_decision_subjects`. Before screening, the watcher may skip a pair only when a successful active `skip_current` negative disposition exists for the exact current question-pack and threshold-policy versions; old versions or changed claim hashes are deliberately reevaluated.
- Update the watcher selection/query helper so a durable current-version negative disposition counts as processed without creating a fake contradiction row. Add indexes/query-plan proof so the scheduled sweep does not repeatedly rescreen the same negative pair.
- Preserve `packages/oracle-engines/src/interjection.ts` decision thresholds, cooldowns, caps, and status rules.
- Add `apps/workers/src/__verify__/jev-contradiction-screen.ts` and `evals/jev/contradiction-screen.md`.

**Acceptance and verification**

- Require 100% recall on severe/material frozen contradictions and separately report conditional, temporal, scope, exception, and negation cases.
- Prove reduced generative calls on true negatives without changing created contradiction records.
- Prove a second scheduled sweep makes zero provider calls for current-version durable negatives, while a pack/threshold version bump or changed claim hash reevaluates them exactly once.
- Deterministically send at least 10% of confident negatives and the first 50 pairs each rolling week (or all when fewer exist) through the current adjudicator. Human-review every disagreement; one missed material contradiction or more than 1% adjudicated false negatives over the latest 100 canaries changes only this gate to `shadow`, alerts admins, and makes subsequent sweeps ignore its negative dispositions.
- Link the canary adjudicator's model run and both claims, persist its versioned category/severity as the bounded comparator outcome, then append the human verdict; do not infer rolling error from a transient log or recompute it from a moving model.
- Run worker typecheck and existing contradiction/interjection tests.
- Deploy/prove this outcome alone.

#### Step 8B — Live Teams intervention screening

**Files/functions**

- `apps/workers/src/trigger/teams-live-recall-utterance.ts:292-318,450-558,756-900`: replace or supplement the keyword/length pre-gate with Noul `worth_intervention` and Choice `contradiction|gap|direct_question|none`.
- Direct mentions, force-test paths, kill switches, confidence thresholds, cooldowns, and rate caps remain deterministic.
- A positive/uncertain result invokes the current generative model to draft; Jev never writes the Teams message.
- At least 10% of `none` decisions and the first 20 each rolling week (or all when fewer exist) run the existing analyzer as non-posting canaries. The current model's draft/interjection recommendation is captured for comparison but cannot post from the canary path; disagreements enter admin review.
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

- `packages/ai/src/retrieval.ts:276-423`: deterministically over-fetch approved, locale-correct, permission-safe candidates; use per-candidate relevance Noul or Score; initially reorder only, never hard-filter.
- Preserve `apps/web/lib/business-answer-retrieval.ts` domain-search budgets/coverage outputs and `business-answer-context.ts` atomic claim/relationship admission. Rerank only within each deterministically eligible candidate set; never erase an explicitly requested domain, relationship premise, omission flag, or citation membership.
- Keep embeddings/BM25/RRF as candidate generation and fallback.
- Maintain caller-specific packs: chat-answer relevance is not contradiction relevance.
- Add `packages/ai/src/__verify__/jev-retrieval-rerank.ts` and `evals/jev/retrieval-rerank.md` with recall@k, precision@k, downstream answer support, latency, tokens, and cost.
- Activate only if relevant-context quality improves without losing approved evidence recall.

#### Step 9B — Chat grounding verification

- `apps/web/app/api/chat/route.ts:223-315,515-663`: after generation and `assertKnownBusinessCitations`, but before assistant-message persistence, evaluate bounded support/responsiveness/language questions against the exact `answerContext` claims/relationships actually supplied. The retry reuses the same bounded context/coverage metadata and must pass `business-answer-policy.ts` again; Jev cannot broaden retrieval or suppress honest omission warnings.
- Extract `apps/web/lib/chat-generation-attempt.ts` from the route's current one-call logging path. Persist the first draft and the one allowed retry as separate `model_runs`, each with its own context pack, attempts, usage, token/cost/latency, route/model, and input/output hashes. Link both model-run IDs to the grounding decision through typed `oracle_decision_subjects` effects `draft_evaluated` and `retry_evaluated`; the first draft is never inserted as an assistant message when discarded.
- Lock the active policy before implementation: a high-confidence unsupported, materially incomplete, or wrong-language result discards the first draft and permits exactly one retry through the current generative route with the same approved evidence plus a grounding correction. Re-evaluate that retry once; if it still fails, return a deterministic “I do not have enough supported Oracle evidence to answer that reliably” response and queue the run for admin review. Jev cannot repair prose, add evidence, or cause more than one retry.
- Use the foundation's admin decision-review list/detail/actions; grounding failures set `review_status='open'` with a bounded reason code and typed links to the relevant generation runs.
- Start shadow-only because this adds latency and duplicates sensitive context externally.
- Add `apps/web/lib/__verify__/jev-chat-grounding.ts` and `evals/jev/chat-grounding.md` with supported, partially supported, fabricated, wrong-language, irrelevant-gap, and injection cases.
- On Jev timeout, malformed response, audit-persistence failure, low confidence, or provider failure, preserve the current answer path; only a successfully audited high-confidence judgment activates the retry/refusal policy.
- If the retry generation itself fails, keep the first draft discarded, return the deterministic refusal, and open the decision review item. Dashboards and eval artifacts report total request cost as first generation + first Jev check + retry generation + second Jev check, not only the final attempt.
- Use at least 150 sealed held-out cases, including at least 50 unsupported/partial/wrong-language cases. Require 100% blocking after retry for the frozen high-risk unsupported set, at least 99% preservation of supported answers, zero evidence/permission bypasses, and report added p50/p95 latency and retry rate before activation.
- Live verification is one bounded synthetic/public query per supported, retry-success, and refusal outcome; company-data proof waits for the vendor/data approval. If the policy is not activated in the landing session, open exactly one leftover-proof issue for this step.
- Do not begin Step 9A or 9B while issue #15's connected-answer live proof remains open unless that owner explicitly hands the proof to this workstream; one session may not own both unproven outcomes.
- The verifier proves only a twice-failed, successfully audited grounding decision—or a failed retry after a successfully audited first rejection—opens review; resolution/dismissal is admin-only and idempotent; Jev provider/audit failure does not create a false review item; page/detail permission tests remain green.
- The verifier also proves one supported response records one generation run, a corrected response records two distinct generation runs and two decision checks, a refused response retains both attempt audits but persists only the refusal message, and aggregate usage/cost includes every attempt.

#### Step 9C — Dispose of future advisory ideas without bundling them

- Do not implement claims advice, entity-proposal advice, extraction A/B judging, meeting ranking, translation verification, or reviewer-group suggestions under this plan. They have different data, safety, UI, and acceptance contracts and violate the one-outcome-per-session rule when bundled.
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
| State size | State or question pack exceeds documented limit | Preflight size-budget test refuses before network call and records `policy_blocked` |
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
| Logging | Raw employee/source text or full response appears in general logs | Log-capture test asserts redaction; decision tables keep hashes, bounded answers, subject links, and policy metadata—not raw state |
| Audit persistence | Pending run, subject-link, final decision, or combined business-effect write fails before/after provider success | Fault-injection test proves Jev effect is discarded, current behavior runs, and no partial record is labeled successful |
| Data-class downgrade | Caller labels employee/licensed/mixed content as public or omits provenance | Provenance test recomputes the union, adds `unknown_restricted` when incomplete, and blocks before network access |
| Process crash | Worker/web process dies after pending insert or provider response | Fake-clock/restart test discards stale pending rows, applies no effect, and permits one clean retry |
| Overlapping extraction windows | One window is Jev-negative while another owner extracts or fails | Owner-reconciliation matrix proves a completed owner wins and only all-negative ownership becomes skipped |
| Production drift | New business language makes a formerly safe negative gate miss valuable content | Deterministic canary/human-label test crosses the limit, atomically changes only that flag to `shadow`, and alerts admins |
| Source erasure/retention | Message, claim, document, model run, or reviewer employee is deleted or retention expires | Typed-FK and retention-worker tests remove/null links, prune orphan runs, and preserve unrelated audit records without raw text |
| Cost calculation | Missing token usage or changed price | Test records cost unknown rather than zero; pricing constant/version is explicit and documented |
| Feature flag | Missing, malformed, or unexpected value | Config test defaults to `off`; active behavior requires exact `active` |
| Deterministic gate conflict | Jev says approve/match but exact evidence, permission, status, or type check fails | Integration test proves deterministic rejection wins every time |
| Live Teams direct mention | Jev says “none” on an explicit Oracle invocation | Live-gate test proves direct mention bypasses Jev suppression |
| MCP disabled capability | Jev selects a disabled or unauthorized tool | Registry intersection test removes it and falls back safely |
| Retrieval false negative | Jev rates valid approved evidence low | Shadow/rerank-only test proves candidate remains available until recall acceptance is met |

## 10. Tests required

### New foundation tests

- `packages/ai/src/__verify__/typesafe-decision-contract.ts`
  - validates all three primitives and normalized responses;
  - rejects malformed answers/cardinality/state/data-class violations, mixed unapproved classes, unknown provenance, and caller downgrade attempts;
  - verifies redaction, pinned model, resolved version, tokens/cost/latency, and failure taxonomy;
  - uses an injectable fake transport and requires no live key.
- `packages/db` migration/schema tests verify the dedicated decision tables, constraints, indexes, immutable successful outcomes, subject links, and current-version disposition lookup.
- `packages/ai/src/__verify__/typesafe-decision-live.ts`
  - opt-in only; uses a synthetic public fixture;
  - exits non-zero on provider failure or contract drift;
  - prints only summary metrics, never key/state bodies.
- Add scripts `verify:typesafe-decision-contract` and `verify:typesafe-decision-live` to `packages/ai/package.json`; only the no-key contract verifier belongs in routine CI initially.
- Add root `verify:jev-contract` to `package.json` and an explicit network-free “Jev decision contract” step to `.github/workflows/pr-check.yml`. Every later network-free verifier is wired into the affected package's existing required suite or added as its own named PR-check step in the same PR; an eval script that CI never calls is unfinished.

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
- Extraction recovery: the prefilter verifier exercises dry-run and applied `scripts/replay-jev-extraction-skips.ts` against isolated fixture rows in both dispatch modes.
- Decision review lifecycle: add an admin-page verifier for open/resolved/dismissed states, idempotent actions, redaction, and non-admin denial.
- Decision health: add a fake-clock verifier for deterministic canary selection, weekly minimums, rolling denominators, human-adjudication updates, atomic `active`→`shadow` transition, alert emission, and isolation from unrelated flags.
- Pending reconciliation/retention: export `runDecisionAuditMaintenanceOnce` for a fake-clock fixture that seeds unrelated stale keys, runs the five-minute task, proves all deadline+grace rows discard in bounded pages, proves fresh rows remain, and covers every retention/erasure age boundary and orphan cleanup.
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
- [ ] Separate decision client exists with pinned model, redaction, normalized results, and no generation-adapter contamination.
- [ ] Every call has one dedicated decision run with derived class set, subjects, bounded answer, usage, cost, latency, resolved model, pack/threshold versions, status, policy outcome, and behavior-effect audit fields.
- [ ] Foundation and adversarial contract tests pass.
- [ ] Each retained use case has its own fixture, shadow artifact, thresholds, acceptance/rejection decision, feature flag, PR, CI evidence, and live proof where activated.
- [ ] Every active hard-negative gate has sampled current-model canaries, an owned human-review queue, measured rolling error, alerting, and tested automatic fallback to `shadow`.
- [ ] Every use case has its named mode/pack/threshold settings seeded `off`, an audited authorized transition path, and no environment-only activation bypass.
- [ ] Pending-run crash recovery, bounded retention, typed-link source erasure, extraction overlap reconciliation, and skip replay are proven on isolated fixtures.
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
- Extraction rollback runs `scripts/replay-jev-extraction-skips.ts` in dry-run, reviews the exact pack/version/window and linked message IDs, then applies the bounded reset to `pending` and verifies the existing extractor completes them. The decision rows remain immutable audit evidence.
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
