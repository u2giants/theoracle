---
summary: "AGENTS.md section 3: full table of which documents to read, and which to skip, for each kind of task."
kind: living
status: current
read-when: deciding which document to open for a task
---

<!-- Moved verbatim from AGENTS.md (issue #22). AGENTS.md is the router. -->

## 3. Documentation map: what to read for each task

Oracle 2 and the old workers were removed in #398 (2026-11-04); rows that pointed at the deleted code were removed.

Always start with:

- `AGENTS.md`

Then load additional docs only when relevant — do not bulk-read every `.md` file.

| Task / question | Read these docs | Usually do not need |
|---|---|---|
| Company Map (v3 program) model stages / model bake-off / model page / which model for which stage | [plan_oracle_company_map.md](../../plan_oracle_company_map.md) (STATUS first; parent #240), [docs/company-map/model-stage-job-brief.md](../company-map/model-stage-job-brief.md) (per-stage role briefs, bake-off protocol, model-page spec), `apps/brain/brain/config.py` and the stage call sites it names | Legacy admin model-pool internals; old provider-adapter docs |
| Chinese (Mandarin) integration: language detection, CJK-safe reading, bilingual map content, Chinese bot/answers/interviews, zh eval | [plan_chinese_integration.md](../../plan_chinese_integration.md) (STATUS table first — do not re-derive or re-plan), its registered handoff `HANDOFF.d/2026-11-08T1616Z-ah-desktop-mimo-chinese-integration-plan.md` | `china_imp.md` (retired claims-system design — principles only), GAP-4 rows in `plan_deferred_product_and_infrastructure_gaps.md` |
| Meeting-transcript triage pipeline: Graph enumeration, ScaleDown triage + summaries, `/map/meetings` review list, approved fluff-stripped ingest, Recall routing | [plan_meeting_triage_pipeline.md](../../plan_meeting_triage_pipeline.md) (STATUS table first — do not re-derive or re-plan), its registered handoff `HANDOFF.d/2026-11-08T1806Z-ah-desktop-mimo-meeting-triage-plan.md` | Old-system Recall/Trigger notes in DECISIONS.md; the interview/Teams-chat intake path (unchanged) |
| Quick repo orientation | `README.md`, `AGENTS.md` | Deep docs under `docs/` unless task requires them |
| Modify app behavior or project-owned code | `AGENTS.md`, relevant folder-level `README.md` if present, `docs/architecture.md` if system design is affected | `docs/deployment.md` unless deploy behavior changes |
| Add or change configuration, env vars, feature flags, secrets | `AGENTS.md` §12, `docs/configuration.md`, `docs/deployment.md` if prod/runtime env is affected | Unrelated architecture docs |
| Pull secrets from 1Password via the MCP server or `op` CLI | `AGENTS.md`, `docs/1password.md` | Unrelated architecture docs |
| Change local setup, dev scripts, test/lint/debug workflow, package scripts, or tooling | `AGENTS.md`, `docs/development.md`, relevant package/config files | `docs/deployment.md` unless CI/CD changes |
| Change task classification or its Phase 3 pilot | `AGENTS.md`, `docs/verification/phase-3-task-gates-pilot.md`, `.ai-devops/task-gates.json`, `scripts/test-task-gates.sh` | Product, model, and production docs |
| Change database schema, migrations, models, external IDs, or data flow | `AGENTS.md`, `docs/architecture.md`, `docs/configuration.md` if env/config is affected, `packages/db/src/schema.ts`, relevant migration/model docs | Deployment docs unless rollout/deploy behavior changes |
| Change Teams transcript ingestion (Graph path) | `AGENTS.md` §7 + §11 quirks, `docs/architecture.md` §"Teams transcript ingestion" | Recall docs unless both paths are affected |
| Change Recall.ai live bot path | `AGENTS.md` §7 + §11 quirks, `docs/architecture.md` §"Teams live participation (Recall.ai)" | Microsoft Graph Teams ingestion docs |
| Investigate a bug or incident | `AGENTS.md` §14 (critical incidents), docs for the affected area, `HANDOFF.md` if present | Unrelated folder-level READMEs |
| Continue unfinished work | `AGENTS.md`, `HANDOFF.md`, docs named inside `HANDOFF.md` | Unrelated plans |
| Work in a subfolder with its own README | `AGENTS.md`, that folder-level `README.md`, and only broader docs referenced there | Other folder-level READMEs |
| Claude Code session | `CLAUDE.md`, then `AGENTS.md` | Other docs unless task requires them |
| Documentation-only cleanup | `AGENTS.md`, `README.md`, [`docs/INDEX.md`](../INDEX.md) (generated; find documents here first), affected docs under `docs/`, folder-level READMEs only where relevant, `HANDOFF.md` if present; finish with `ai-doc-health --repo .` clean | Source files except as needed to verify accuracy |
| Known runtime failure, stale verification code, migration drift, missing production proof, or release automation | `plan_repo_reliability_and_release_gaps.md` (read its STATUS table first), `AGENT_ERROR_LOG.md`, affected code, `docs/deployment.md` when release behavior changes | Historical handoff blocks except for evidence |
| Deferred product or infrastructure gap: taxonomy apply, entity-aware retrieval, Authentik, China review/search, attachment cache, Vertex GCS, eval UI, provider batch, secret rotation, identity cleanup | `plan_deferred_product_and_infrastructure_gaps.md` (read its STATUS table first), the affected topic doc and source files | Macro-first supporting history unless the gap changes macro evidence or serving |
| Fix an Oracle quality defect or build a consultant feature: answer accuracy, data domains/business functions, source dates and versions, contradictions, relationships and ordered flows, gap finding and interviews, corrections, Teams Q&A, briefings, operational numbers | `plan_oracle_repair_and_consultant_upgrade.md` (read its STATUS table first), `docs/audit-2026-11-11-oracle-goals.md`, the affected `apps/brain/brain` files | Legacy `packages/*` claim code |

Rules:
- MUST be task-based.
- MUST NOT become a flat list of every Markdown file.
- Read `HANDOFF.md` whenever it exists. It is a static pointer: the real handoffs are the files in `HANDOFF.d/`. Read them newest-first and follow the retention rules in §3a.
- Update this documentation map when documentation files are added, removed, renamed, or repurposed.
