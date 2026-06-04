# The Oracle

The Oracle is an evidence-backed enterprise knowledge graph for POP Creations / Spruce Line. Employees talk to it in chat and upload documents; workers extract operational claims with quote-level evidence; deterministic validators gate promotion; synthesis workers maintain Brain sections; admin screens review the resulting knowledge and AI runs.

Start here:

- `AGENTS.md` — primary developer and AI-session operating guide
- `docs/architecture.md` — current system design and data flow
- `docs/development.md` — local setup and verification workflow
- `docs/configuration.md` — env vars and runtime config
- `docs/deployment.md` — release/deploy process
- `DECISIONS.md` — architectural decisions and constraints
- `oracle_master_spec.md` — product contract

## Repo map

- `apps/web/` — Next.js 16 web app, admin UI, chat route, Teams transcript webhook (`/api/teams/notifications`), Recall live Teams webhook (`/api/teams/live/recall`)
- `apps/workers/` — Trigger.dev workers (claim extraction, doc ingestion, synthesis, contradiction watcher, Teams transcript ingestion + subscription manager, Recall live Teams utterance processor)
- `packages/ai/` — `OracleAIClient`, retrieval, prompts, provider adapters
- `packages/db/` — Drizzle schema, migrations, seed, DB client
- `packages/oracle-engines/` — deterministic validation/promotion/synthesis logic
- `packages/auth/` — auth linking helpers
- `packages/shared/` — shared types/constants

## Current runtime shape

- Web app: Vercel via `vercel.json`
- Workers: Trigger.dev Cloud via `apps/workers/trigger.config.ts`
- Database/Auth/Storage/Realtime: Supabase Cloud
- AI inference: direct provider adapters only
  - Anthropic via `@anthropic-ai/sdk`
  - Vertex via `@google/genai`
  - OpenAI via `openai`
  - DeepSeek via `openai` against `api.deepseek.com`
  - Qwen via `openai` against DashScope OpenAI-compatible endpoints
- OpenRouter is enrichment-only for the model catalog, not inference

## Fast start

```bash
pnpm install
pnpm typecheck
pnpm --filter @oracle/web build
pnpm dev
```

For a real local setup you also need `.env.local`, Supabase access, and Vertex ADC. Use `docs/development.md` and `docs/configuration.md` for the exact steps.

## Notes

- `HANDOFF.md` should exist only when work is unfinished. If it is missing, there is no active handoff file.
- `AGENTS.md` is the canonical guide for future sessions. Keep it current when behavior or operations change.
