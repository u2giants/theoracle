# Oracle AI Buildout Index

Status: mandatory implementation guidance for the AI architecture retrofit.

This directory supplements, but does not replace, the root `oracle_master_spec.md`.

The root master spec remains the product/business contract: what The Oracle is, what it is not, how evidence-backed claims work, why Postgres is the source of truth, and why employee trust matters.

These addenda define the corrected AI implementation architecture for the existing repo.

## Required reading order for AI work

Before editing `packages/ai`, `apps/workers`, model settings, extraction, synthesis, retrieval, evals, or Oracle chat behavior, read these in order:

1. `README.md` at the repo root.
2. `AGENTS.md` at the repo root.
3. `CLAUDE.md` at the repo root.
4. `HANDOFF.md` at the repo root.
5. `oracle_master_spec.md` at the repo root.
6. This file.
7. `docs/oracle/01-model-roles-and-routes.md`.
8. `docs/oracle/02-provider-native-ai-architecture.md`.
9. `docs/oracle/03-candidate-before-claim-validation.md`.
10. `docs/oracle/04-context-packs-observability.md`.
11. `docs/oracle/05-ai-retrofit-phase-packet.md`.
12. `docs/oracle/06-evaluation-framework.md` when implementing or changing evals.

Do not use wildcard reads such as `cat docs/oracle/*`. Read the index first, then read the specific files required for the active task.

## Conflict order

If files disagree, resolve conflicts in this order:

1. Product intent and non-negotiable Oracle principles in `oracle_master_spec.md`.
2. Security, RLS, Postgres source-of-truth, and evidence traceability rules.
3. Candidate-before-claim validation and deterministic evidence validation rules.
4. Provider-native Big 3 AI architecture, retrieval planning, and evaluation gates in this directory.
5. Existing OpenRouter/Vercel AI SDK implementation details in older code or docs.
6. UI details and convenience implementation notes.

The old implementation currently uses OpenRouter and Vercel AI SDK heavily. That is existing technical debt, not the desired target architecture for heavy AI workloads.

## Big decision summary

The Oracle will support three primary model roles:

1. Interview model: human-facing Oracle conversation and employee interviews.
2. Extraction model: high-volume claim candidate extraction from messages and documents.
3. Synthesis model: high-quality Brain section synthesis, contradiction reasoning, and admin-facing operational synthesis.

This split is correct and should remain the default mental model.

Do not create a separate user-exposed model picker for every tiny internal subtask at first. Instead, the three roles should drive default routes, while the `ModelRouter` can internally use subroutes later for contradiction prefiltering, admin explanation, validation repair, or retry escalation.

## Big 3 provider rule

The production AI provider surface is limited to the Big 3 direct APIs:

- Google Vertex AI / Gemini direct.
- Anthropic direct.
- OpenAI direct.

OpenRouter may remain temporarily for existing code and non-critical experiments, but it must not be the target architecture for background extraction, document processing, synthesis, or cost/caching-sensitive production workloads.

## Main engineering goal

The goal is not lowest token price.

The goal is lowest cost per validated, useful, evidence-backed result:

- cost per valid claim;
- cost per approved claim;
- cost per useful gap;
- cost per accepted Brain section update;
- cache hit rate by task/provider/model;
- validation failure rate by model route;
- retry rate and fallback rate.

## Implementation rule

No LLM output becomes official operational truth directly.

All extraction output must flow through staging, deterministic validation, and transactional promotion before it enters permanent `claims`, `claim_domains`, or `claim_evidence` tables.

## Retrieval rule

Do not retrieve by global vector search by default.

All answer generation, chat retrieval, contradiction review, extraction follow-up, and Brain synthesis must use a retrieval plan that filters by knowledge domain, source type, document class, process stage, department, system, entity, review state, and time validity before vector search.

## Evaluation rule

Do not build an evaluation web UI at first.

Evals must start as CLI-run TypeScript tests/scripts using static fixtures. See `docs/oracle/06-evaluation-framework.md`.

## Documentation ownership

When implementation changes any of these topics, update the matching document in this directory in the same commit:

- model routes or defaults -> `01-model-roles-and-routes.md`;
- provider adapters, caching, retrieval planning, hybrid search, or Supabase-to-Vertex storage bridge -> `02-provider-native-ai-architecture.md`;
- extraction validation, sensitivity gates, or promotion locking -> `03-candidate-before-claim-validation.md`;
- model logging, cost, context packs, or payload retention -> `04-context-packs-observability.md`;
- implementation order -> `05-ai-retrofit-phase-packet.md`;
- eval commands, fixtures, metrics, or phase gates -> `06-evaluation-framework.md`.
