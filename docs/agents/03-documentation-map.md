<!-- Moved verbatim from AGENTS.md (issue #22). AGENTS.md is the router. -->

## 3. Documentation map: what to read for each task

Always start with:

- `AGENTS.md`

Then load additional docs only when relevant — do not bulk-read every `.md` file.

| Task / question | Read these docs | Usually do not need |
|---|---|---|
| Quick repo orientation | `README.md`, `AGENTS.md` | Deep docs under `docs/` unless task requires them |
| Modify app behavior or project-owned code | `AGENTS.md`, relevant folder-level `README.md` if present, `docs/architecture.md` if system design is affected | `docs/deployment.md` unless deploy behavior changes |
| Add or change AI provider adapter or model catalog | `AGENTS.md`, `docs/architecture.md` (adapter table + data flow), provider files under `packages/ai/src/providers/`, `DECISIONS.md`; `fix_adapter_quirks.md` when strict/deep schema eligibility or adapter request safety is involved; run/update `packages/ai/src/__verify__/adapter-request-shapes.ts` when request-shaping, strict-schema eligibility, or usage normalization changes | Worker or webhook code |
| Integrate or evaluate TypeSafe Jev decision models | `plan_typesafe_jev_decision_layer.md` (read STATUS first), newest linked handoff, `docs/architecture.md`, `docs/configuration.md`, the affected runtime/eval files | Generative provider adapters, model catalog, or active R2 prompt/production work unless the plan step explicitly requires them |
| Add or change configuration, env vars, feature flags, secrets | `AGENTS.md` §12, `docs/configuration.md`, `docs/deployment.md` if prod/runtime env is affected | Unrelated architecture docs |
| Pull secrets from 1Password via the MCP server or `op` CLI | `AGENTS.md`, `docs/1password.md` | Unrelated architecture docs |
| Change local setup, dev scripts, test/lint/debug workflow, package scripts, or tooling | `AGENTS.md`, `docs/development.md`, relevant package/config files | `docs/deployment.md` unless CI/CD changes |
| Change task classification or its Phase 3 pilot | `AGENTS.md`, `docs/verification/phase-3-task-gates-pilot.md`, `.ai-devops/task-gates.json`, `scripts/test-task-gates.sh` | Product, model, and production docs |
| Change deployment, Docker, CI/CD, hosting, release flow, rollback, or runtime environment | `AGENTS.md` §13, `docs/deployment.md`, `docs/configuration.md`, relevant workflow/deployment files | Local-only development docs unless needed |
| Change database schema, migrations, models, external IDs, or data flow | `AGENTS.md`, `docs/architecture.md`, `docs/configuration.md` if env/config is affected, `packages/db/src/schema.ts`, relevant migration/model docs | Deployment docs unless rollout/deploy behavior changes |
| Add or change a worker task | `AGENTS.md` §7 task-to-file, `apps/workers/src/trigger/`, `docs/architecture.md` if data flow changes | Front-end app code unless there is a matching UI/API hook |
| Change Teams transcript ingestion (Graph path) | `AGENTS.md` §7 + §11 quirks, `docs/architecture.md` §"Teams transcript ingestion" | Recall docs unless both paths are affected |
| Change Recall.ai live bot path | `AGENTS.md` §7 + §11 quirks, `docs/architecture.md` §"Teams live participation (Recall.ai)" | Microsoft Graph Teams ingestion docs |
| Investigate a bug or incident | `AGENTS.md` §14 (critical incidents), docs for the affected area, `HANDOFF.md` if present | Unrelated folder-level READMEs |
| Continue unfinished work | `AGENTS.md`, `HANDOFF.md`, docs named inside `HANDOFF.md` | Docs unrelated to the handoff scope |
| Work in a subfolder with its own README | `AGENTS.md`, that folder-level `README.md`, and only broader docs referenced there | Other folder-level READMEs |
| Change the remote MCP knowledge endpoint (tools agents query) | `AGENTS.md` §11 MCP quirk, `apps/web/lib/mcp/README.md`, `apps/web/lib/mcp/*`, `apps/web/app/api/mcp/[transport]/route.ts` | Unrelated chat/worker code |
| China bilingual claim layer / claim translation / asking China-team members to verify a claim | `AGENTS.md` §8–§11, `china_imp.md` (design + resolved decisions), `packages/ai/src/retrieval.ts`, `apps/workers/src/trigger/claim-translation.ts`, `apps/web/app/admin/claims/*` (verification reuses main's `claim_review_question` + review-groups) | Teams/Recall docs; provider-adapter internals |
| Claude Code session | `CLAUDE.md`, then `AGENTS.md` | Other docs unless task requires them |
| Documentation-only cleanup | `AGENTS.md`, `README.md`, affected docs under `docs/`, folder-level READMEs only where relevant, `HANDOFF.md` if present | Source files except as needed to verify accuracy |
| Product/spec contract or AI-retrofit provenance | `AGENTS.md`, `oracle_master_spec.md`, relevant `docs/oracle/*` file, `oracle_ai_architecture_prompt caching.md` only if prompt-cache retrofit history is directly relevant | Current deployment/config docs unless operations are affected |
| Macro-first redesign / shape-aware reader / business model layer / workflow maps / source outlines / cross-claim process relationships | `MACRO_FIRST_IMPLEMENTATION_PLAN.md` (canonical forward plan), `plan_r2_source_span_inventory_reader.md` (completed release + 19/30 hard stop), `plan_r2_source_bound_final_record_correction.md` (current local-only plan; read STATUS first), `plan_r2_local_owner_context_correction.md` and `plan_r2_numbered_inner_actor_correction.md` (completed local corrections), `plan_r2_deeper_responsibility_architecture.md` (completed predecessor + failed gate/bake-off history), `SHAPE_AWARE_READER_DESIGN.md` and `MACRO_FIRST_REDESIGN.md` (supporting design/history), `MODEL_BAKEOFF_SPEC.md` for model selection history, `evals/{shape-aware-stage2,macro-first-battery}.md` for stage-gate results, `evals/r2-responsibilities.md` for the R2 answer-key history including the 19/30 production gate and the production-replay preservation gate, `fix_enhancement.md` §1–§6 as diagnosis record + ground truth only, `AGENTS.md`, `docs/architecture.md`, `DECISIONS.md` when changing provenance or routing rules | `docs/macro-understanding-implementation-plan.md` (pre-redesign plan, historical), deployment docs unless worker schedules/env/deploy behavior changes |
| Execute the owner-authorized fresh R2 production gate | `plan_r2_fresh_production_gate.md` (read STATUS first), `plan_r2_source_bound_final_record_correction.md`, newest R2 handoff, `evals/r2-responsibilities.md`, `docs/deployment.md`, `docs/configuration.md` | Any matcher, fixture, schema, model, route, budget, or feature-flag change; any second run |
| Known runtime failure, stale verification code, migration drift, missing production proof, or release automation | `plan_repo_reliability_and_release_gaps.md` (read its STATUS table first), `AGENT_ERROR_LOG.md`, affected code, `docs/deployment.md` when release behavior changes | Historical handoff blocks except for evidence |
| Deferred product or infrastructure gap: taxonomy apply, entity-aware retrieval, Authentik, China review/search, attachment cache, Vertex GCS, eval UI, provider batch, secret rotation, identity cleanup | `plan_deferred_product_and_infrastructure_gaps.md` (read its STATUS table first), the affected topic doc and source files | Macro-first supporting history unless the gap changes macro evidence or serving |

Rules:
- MUST be task-based.
- MUST NOT become a flat list of every Markdown file.
- Read `HANDOFF.md` whenever it exists. It is a static pointer: the real handoffs are the files in `HANDOFF.d/`. Read them newest-first and follow the retention rules in §3a.
- Update this documentation map when documentation files are added, removed, renamed, or repurposed.
- `docs/oracle/` — deeper AI-retrofit reference material; only read when the task touches the AI-retrofit spec directly.
- `oracle_master_spec.md` and `oracle_ai_architecture_prompt caching.md` are historical/spec reference files, not default orientation docs.

