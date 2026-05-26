# CLAUDE.md — Claude Code Notes

**Read `AGENTS.md` first.** Everything substantive about repo operation lives there. This file adds Claude Code-specific instructions and points Claude to the current AI buildout addenda.

## Current priority

The next major implementation work is **not** Phase 6 proactive interjection. Treat `HANDOFF.md` as the authoritative phase-status table.

Retrofit progress as of 2026-05-25:

- ✅ R0 — Documentation reset
- ✅ R1 — Curated Oracle model route catalog (`packages/ai/src/routes/`)
- ✅ R2 — OracleAIClient + ContextCompiler + ModelRouter + provider adapter stubs (`packages/ai/src/{client,context,routing,providers,usage,validation}/`)
- ✅ R3 — Observability schema (`oracle_context_packs`, `model_run_usage_details`, `provider_cached_content`)
- ✅ R3.5 — Three-layer knowledge taxonomy schema (15 tables, boundary rules, `licensor` first-class)
- ✅ R4 — Candidate-before-claim staging schema (4 tables, 13 CHECK constraints)
- ✅ R5 — Quote validator + promotion decision (pure functions in `packages/oracle-engines/src/extraction/`; 33-assertion smoke)
- ✅ R5.5 — Entity resolver + taxonomy validator + extended decision shape (45-assertion smoke)
- ✅ R6 — Claim extraction worker refactored through staging pipeline + circuit breaker + executor (30-assertion smoke)
- ✅ R7 — Document ingestion worker refactored + `claims.candidate_hash` + cache profitability/lifecycle + race-safe executor (19-assertion smoke)
- ✅ R8 — Chat route refactored through `OracleAIClient` with `providerOptions` escape hatch for tools/multi-turn
- ✅ R9 — Synthesis worker refactored + `validateSynthesisDiff` (claim ID + unsupported-named-entity check) + rejected-version preservation (21-assertion smoke)
- ✅ R10 — Admin AI observability dashboards under `/admin/ai`
- ✅ R10.5 — Taxonomy governance dashboard under `/admin/taxonomy` + re-evaluation worker scaffold
- ⬜ **R11 — Resume interjection engine** — gated on wet-test (apply migrations → real extraction run → review claims → THEN R11). Code path is the original Phase 6 scaffold at `packages/oracle-engines/src/interjection.ts`.

The retrofit packet supersedes any older guidance that says Phase 6 interjection is next.

Authoritative addenda for the retrofit:

1. `docs/oracle/00-buildout-index.md` — index + reading order
2. `docs/oracle/01-model-roles-and-routes.md` — roles + curated route catalog
3. `docs/oracle/02-provider-native-ai-architecture.md` — `OracleAIClient` pipeline + hybrid retrieval + cache lifecycle
4. `docs/oracle/03-candidate-before-claim-validation.md` — staging → validation → promotion
5. `docs/oracle/04-context-packs-observability.md` — context packs + dashboards
6. `docs/oracle/05-ai-retrofit-phase-packet.md` — implementation order
7. `docs/oracle/06-evaluation-framework.md` — CLI evals + phase gates
8. `docs/oracle/07-knowledge-segmentation.md` — three-layer taxonomy + boundary rules

Do not extend the old OpenRouter-centered architecture for production extraction, document ingestion, synthesis, or cache-sensitive AI work. OpenRouter may remain temporarily as legacy fallback while the retrofit is in progress; the target architecture is Big 3 direct-provider adapters (Anthropic / Vertex / OpenAI).

## Memory

This project does not currently use Claude Code persistent memory. If you start, document the memory key naming convention here.

## Context loading protocol

Do not bulk-read documentation with wildcard commands such as:

```bash
cat docs/oracle/*
cat *.md
```

Do not load all docs into context just because they exist.

Instead:

1. Read `HANDOFF.md` first to determine the current objective.
2. Read `AGENTS.md` for repo conventions.
3. Read `oracle_master_spec.md` for product/business intent.
4. Read `DECISIONS.md` for historical decisions that may affect the task.
5. Read `docs/oracle/00-buildout-index.md`.
6. Read only the specific `docs/oracle/` files required for the active task.

If the task touches AI architecture generally, read all `docs/oracle/` files one by one in the order listed by `00-buildout-index.md`. Do not use wildcard reads.

If the task is narrow, use this routing:

- model routes/settings: read `01-model-roles-and-routes.md`;
- provider adapters/caching: read `02-provider-native-ai-architecture.md`;
- extraction validation/staging: read `03-candidate-before-claim-validation.md`;
- model runs/context packs/cost dashboards: read `04-context-packs-observability.md`;
- implementation order: read `05-ai-retrofit-phase-packet.md`.

Before coding, write a short implementation plan in your response or commit notes that names exactly which spec docs were read and why.

## Context management

Do not re-read `pnpm-lock.yaml`, `node_modules/`, `apps/web/.next/`, or generated Drizzle SQL. They are listed in `.claudeignore`.

When in doubt about behavior, read:

- `packages/db/src/schema.ts`
- `packages/db/migrations/sql/*.sql`
- `packages/ai/src/prompts/oracle-system.ts`
- `docs/oracle/00-buildout-index.md`

The hand-written SQL migration ordering is documented in `packages/db/migrations/sql/README.md`.

## `.claudeignore`

Already at the repo root. If you add new build artifacts or large generated dirs, update both `.claudeignore` and `.cursorignore` in the same commit so other AI tools stay in sync.

## Operations / permissions

Allowed:

- read/write anything under `apps/`, `packages/`, `docs/`, and root markdown files;
- run `pnpm install`, `pnpm db:generate`, `pnpm db:migrate`, `pnpm typecheck`, `pnpm build`, `pnpm lint`, `pnpm dev`;
- run git locally;
- use GitHub CLI or GitHub tools for read/write repo operations.

Allowed with care:

- `pnpm db:seed` — idempotent but writes to the real Supabase DB;
- direct pushes to `main` only when explicitly requested by Albert;
- migrations that add schema are allowed, but destructive migrations need explicit approval.

Not allowed:

- broad `Stop-Process -Force` on `node`;
- destructive git such as `reset --hard`, `push --force`, or deleting branches without explicit approval;
- committing `.env*` files except `.env.example`;
- committing secrets, Vercel tokens, Supabase service role keys, provider API keys, or Trigger.dev secrets.

## APIs Claude may call

- GitHub — read/edit files, create branches/commits/PRs.
- Vercel — link project, pull env vars, list deployments. Do not manually deploy; Vercel auto-deploys on push.
- Supabase — server-side only, using documented helpers and service role where justified.
- Anthropic / Google Vertex AI / OpenAI — only through the future `OracleAIClient` provider adapters once implemented.
- OpenRouter — legacy path only. Do not add new production OpenRouter usage.

## AI architecture rules

All new model calls must go through the target architecture:

```text
OracleAIClient
  -> ContextCompiler
  -> ModelRouter
  -> Provider Adapter
  -> UsageLogger / CostTracker / ContextPack
```

Do not call provider SDKs directly from:

- Next.js route handlers;
- Trigger.dev task files;
- admin UI components;
- random helper files.

Provider SDK calls belong inside provider adapters under `packages/ai`.

## Model-role split

The app has three primary model roles:

1. Interview model — human-facing Oracle conversation.
2. Extraction model — claim candidate extraction from messages/documents.
3. Synthesis model — Brain section synthesis and high-level operational reasoning.

Cost-aware default target routes:

```ts
interview: 'anthropic_claude_haiku_4_5_interview_primary'
extraction: 'vertex_gemini_flash_lite_extraction_primary'
synthesis: 'vertex_gemini_flash_synthesis_primary'
```

Balanced alternate target routes if evals show quality is too low:

```ts
interview: 'anthropic_claude_haiku_4_5_interview_primary'
extraction: 'vertex_gemini_flash_extraction_primary'
synthesis: 'anthropic_claude_haiku_synthesis_primary'
```

Frontier models such as Claude Sonnet/Opus, Gemini Pro, or OpenAI frontier models are escalation/manual-review routes only. Do not run frontier models across routine cron jobs or ordinary chat by default.

Do not expose arbitrary model catalogs as production choices. Use curated `OracleModelRoute.routeId` selections.

## Candidate-before-claim rule

Never write AI-extracted operational truth directly into permanent claim tables.

The correct pipeline is:

```text
model output
  -> extraction_batches
  -> extraction_candidates
  -> extraction_candidate_evidence
  -> deterministic validation
  -> transactional promotion
  -> claims / claim_domains / claim_evidence
```

If a worker writes directly from model output into `claims`, that worker must be refactored.

## Commit style

- Conventional commits: `feat(...)`, `fix(...)`, `chore(...)`, `docs(...)`.
- Reference the phase or retrofit packet when relevant: `feat(ai-r2): ...`, `docs(ai-retrofit): ...`.
- HEREDOC for multi-line commit messages.
- Never commit secrets.

## Tool preferences

- File ops: use Claude Code file tools rather than shell text surgery when possible.
- Search: use code-aware search tools.
- Long-running scaffolds: spawn an Agent/background task rather than blocking the main session.
- Multi-step research: use a Plan agent.
- Open-ended exploration: use an Explore agent.

## Behaviors to enable

- Always update `DECISIONS.md` when making an assumption not directly specified.
- Always update the relevant `docs/oracle/*.md` file when AI architecture behavior changes.
- Update `HANDOFF.md` at the end of every session.
- Run typecheck/build before declaring code complete.

## Behaviors to suppress

- Do not write speculative tests before the behavior is stable unless Albert asks.
- Do not refactor outside the immediate task scope without raising it as a separate item first.
- Do not introduce new dependencies without a one-line justification in the commit message and docs/configuration updates.
- Do not continue building proactive interjection until the AI retrofit and validation pipeline are in place.
