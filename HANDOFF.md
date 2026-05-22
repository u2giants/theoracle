# HANDOFF — The Oracle

Live in-flight state for the next contributor or AI coding session.

**Snapshot date:** 2026-05-22
**Repo:** https://github.com/u2giants/theoracle
**Current priority:** AI architecture retrofit before any more proactive interjection work.

---

## Read this in order

1. `HANDOFF.md` — this file.
2. `AGENTS.md` — developer guide and repo conventions.
3. `CLAUDE.md` — Claude Code-specific instructions. This now contains the current AI retrofit priority.
4. `oracle_master_spec.md` — product/business contract.
5. `DECISIONS.md` — assumptions and historical decisions.
6. `docs/oracle/00-buildout-index.md`.
7. All other docs in `docs/oracle/`.

---

## Critical update

Older handoff text said Phase 6, the interjection engine, was next.

That is now superseded.

**Do not implement proactive interjection yet.**

The next work is the AI architecture retrofit described in `docs/oracle/05-ai-retrofit-phase-packet.md`.

Reason:

- interjection depends on trustworthy claims;
- trustworthy claims depend on candidate-before-claim validation;
- candidate validation depends on context packs, model run observability, and provider-native model routes;
- provider-native model routes require replacing the old OpenRouter-centered AI layer.

Building proactive interjection before the AI retrofit would build on the wrong foundation.

---

## Current repo reality

The repo already has useful working foundation code:

- pnpm + Turborepo TypeScript monorepo;
- Next.js app under `apps/web`;
- Trigger.dev workers under `apps/workers`;
- Supabase/Postgres/Drizzle schema under `packages/db`;
- Supabase auth helpers under `packages/auth`;
- current AI helpers under `packages/ai`;
- admin dashboards and chat UI scaffolding;
- worker scaffolds and some deployed worker logic.

Do not start over.

This is a major AI/backend retrofit, not a full rebuild.

---

## Current architectural correction

The old implementation uses:

```text
Vercel AI SDK + OpenRouter
```

That path is now legacy for production AI workloads.

Target production architecture:

```text
OracleAIClient
  -> ContextCompiler
  -> ModelRouter
  -> Provider Adapter
      -> Anthropic direct
      -> Google Vertex AI / Gemini direct
      -> OpenAI direct
  -> UsageLogger / CostTracker / ContextPack
```

OpenRouter may remain temporarily for legacy runtime compatibility or experiments, but do not extend it for production extraction, document ingestion, synthesis, or cache-sensitive AI work.

---

## Model-role decision

The app should keep three primary model roles:

1. **Interview model** — human-facing Oracle chat/interviews.
2. **Extraction model** — high-volume claim candidate extraction from messages/documents.
3. **Synthesis model** — Brain section synthesis, contradiction reasoning, and admin-facing operational synthesis.

Initial target defaults:

```ts
interview: 'anthropic_claude_sonnet_interview_primary'
extraction: 'vertex_gemini_flash_extraction_primary'
synthesis: 'anthropic_claude_sonnet_synthesis_primary'
```

Top choices for each role are defined in `docs/oracle/01-model-roles-and-routes.md`.

---

## Next build sequence

Follow `docs/oracle/05-ai-retrofit-phase-packet.md`.

Summary:

1. **R0 Documentation reset** — done in principle; verify docs point to `docs/oracle`.
2. **R1 Model route configuration** — replace arbitrary model strings with curated route IDs.
3. **R2 Provider-native OracleAIClient** — add Anthropic, Vertex/Gemini, and OpenAI adapters.
4. **R3 Context packs and usage logging schema** — add observability tables.
5. **R4 Candidate-before-claim staging schema** — add staging tables.
6. **R5 Exact quote validator and promotion service** — deterministic validation and transaction promotion.
7. **R6 Refactor claim extraction worker** — stage candidates, validate, then promote.
8. **R7 Refactor document ingestion worker** — Vertex/Gemini direct and explicit context caching when justified.
9. **R8 Refactor chat route** — route through `OracleAIClient`.
10. **R9 Refactor synthesis worker** — Anthropic direct and strict synthesis validation.
11. **R10 Admin observability dashboards** — AI runs, context packs, cache dashboard, candidate review.
12. **R11 Resume interjection engine**.

---

## Existing code that likely needs refactor

High priority:

- `packages/ai/src/openrouter.ts` — mark legacy; replace production usage with `OracleAIClient`.
- `apps/workers/src/trigger/claim-extraction.ts` — currently writes too directly to permanent claims; refactor to candidates first.
- `apps/workers/src/trigger/document-ingestion.ts` — should use Vertex/Gemini direct for document-heavy extraction.
- `apps/workers/src/trigger/brain-synthesis.ts` — should use Anthropic direct and strict validation.
- `apps/web/app/api/chat/route.ts` — should call `OracleAIClient`, not OpenRouter directly.
- Admin model picker — should select curated `OracleModelRoute.routeId`, not arbitrary OpenRouter model IDs.

Medium priority:

- add `oracle_context_packs`, `model_run_usage_details`, `provider_cached_content`;
- add `extraction_batches`, `extraction_candidates`, `extraction_candidate_evidence`, `extraction_validation_results`;
- add AI cost/cache dashboards;
- update `.env.example` and `docs/configuration.md` with Big 3 provider variables.

---

## Do not do yet

Do not build these until the AI retrofit and validation pipeline are in place:

- proactive contradiction interjection;
- lull-based Oracle questions;
- live group-chat interjection;
- aggressive automatic claim approval;
- Brain synthesis from unreviewed or weakly validated claims.

---

## Security reminders

- This repo is public. Never commit secrets.
- Rotate any Vercel token or provider API key that appeared in transcripts.
- Keep `.env.local` untracked.
- Service-role Supabase access must remain server-side only.
- Employee-facing UI must never directly expose intelligence tables.

---

## Resume prompt for Claude Code

```text
I'm continuing work on The Oracle. Read HANDOFF.md, AGENTS.md, CLAUDE.md, oracle_master_spec.md, DECISIONS.md, and all docs in docs/oracle/. Do not implement Phase 6 interjection yet. The next work is the AI architecture retrofit: model routes, OracleAIClient, Big 3 provider adapters, context packs, candidate-before-claim staging, deterministic quote validation, and worker refactors. Start with docs/oracle/05-ai-retrofit-phase-packet.md and implement the phases in order.
```
