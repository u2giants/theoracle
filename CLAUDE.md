# CLAUDE.md — Claude Code Notes

**Read `AGENTS.md` first.** Everything substantive about repo operation lives there. This file adds only Claude Code-specific notes.

## Current state (2026-05-26)

**AI retrofit complete + external review closed.** R0 → R11.4 done. All 6 external reviewer issues resolved (P1 #1–4, P2 #1–2): settings overhaul with model pool UI + `resolveModelRoute`, sensitivity flags + entity extraction prompt v2.0.0, full RetrievalPlan + hybrid pgvector/tsvector RRF, requireAdmin on intelligence actions, and honest R10.5 scaffold labels.

**Next work is operational, not architectural:** Trigger.dev redeploy of updated workers, Vertex prod credentials, key rotation, threshold tuning. See `HANDOFF.md` "What's next" for the full list.

Treat `HANDOFF.md` as the authoritative phase-status table. Treat `DECISIONS.md` as the authoritative decision log (D6 + D9 explain why no Vercel AI SDK / no OpenRouter; D10 + D11 explain the R11 live-interjection switch and lull simplifications).

## MCP servers available in this environment

This session typically has the following MCP servers connected. When relevant, prefer them over shell commands:

- **Supabase MCP** (`mcp__supabase__*`) — direct SQL execution against the live database, `apply_migration` for schema changes, `list_tables` / `list_migrations` / `get_advisors`. Authentication is per-session; if the tools appear as deferred-only, run the `authenticate` flow once and the user pastes the callback URL back.
- **Vercel MCP** (`mcp__vercel__*`) — deployment list, build logs, runtime logs, env inspection. Use these instead of shelling `vercel`.
- **gh CLI** — already installed and authenticated on Albert's machine. Use through Bash for PR/issue/release operations.
- **gcloud CLI** — installed under `%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\`. Active configuration is `oracle` pointing at project `vertex-ai-497120`, region `us-central1`. ADC is set up. Vercel project `lithe-breaker-323913` is unrelated to Oracle.

If a tool isn't loaded, use `ToolSearch` with `select:<tool_name>` (specific tools) or a keyword query like `select:mcp__supabase__list_projects,mcp__supabase__execute_sql`.

## Context loading protocol

Do not bulk-read documentation with wildcard commands such as:

```bash
cat docs/oracle/*
cat *.md
```

Read order:

1. `HANDOFF.md` — current objective and unfinished work.
2. `AGENTS.md` — repo conventions.
3. `oracle_master_spec.md` — product/business intent.
4. `DECISIONS.md` — historical decisions that may affect the task.
5. `docs/oracle/00-buildout-index.md` — index of the retrofit addenda.
6. Only the specific `docs/oracle/0N-*.md` files the task touches.

Routing for narrow tasks:

- model routes/settings → `01-model-roles-and-routes.md`
- provider adapters/caching → `02-provider-native-ai-architecture.md`
- extraction validation/staging → `03-candidate-before-claim-validation.md`
- observability/cost dashboards → `04-context-packs-observability.md`
- implementation order → `05-ai-retrofit-phase-packet.md`
- evals → `06-evaluation-framework.md`
- taxonomy → `07-knowledge-segmentation.md`

Before coding, write a short implementation plan in your response that names exactly which spec docs you read and why.

## Context management

Do not re-read `pnpm-lock.yaml`, `node_modules/`, `apps/web/.next/`, or generated Drizzle SQL. They are listed in `.claudeignore`.

When in doubt about behavior, read:

- `packages/db/src/schema.ts`
- `packages/db/migrations/sql/*.sql` (and the README in that folder for prefix conventions)
- `packages/ai/src/prompts/extraction-system.ts` and `packages/ai/src/prompts/oracle-system.ts`
- `packages/ai/src/routes/catalog.ts` (the curated routes)
- `docs/oracle/00-buildout-index.md`

## `.claudeignore`

Already at the repo root. If you add new build artifacts or large generated dirs, update both `.claudeignore` and `.cursorignore` in the same commit.

## Operations / permissions

Allowed without asking:

- read/write under `apps/`, `packages/`, `docs/`, root markdown files;
- run `pnpm install`, `pnpm db:generate`, `pnpm typecheck`, `pnpm build`, `pnpm lint`, `pnpm dev`;
- run smoke tests and evals (`verify:*`, `eval:*`);
- run git locally (status / diff / log / add / commit / push to `main` when Albert asks);
- use Supabase MCP for read queries and `apply_migration` (Albert prefers MCP over shelling `pnpm db:migrate`);
- use Vercel MCP for read operations;
- use `gh` for repo read/write.

Allowed with care:

- writing to `extraction_*` / `claims` / `claim_*` tables is fine via the worker code path; never bypass the candidate-before-claim pipeline via direct `INSERT INTO claims`;
- `pnpm db:seed` is idempotent but writes to real Supabase — explicit ok needed for first run;
- direct push to `main` only when Albert explicitly says push;
- adding deps requires a one-line justification in the commit message.

Not allowed without explicit approval:

- `git reset --hard`, `git push --force`, deleting branches;
- destructive Supabase operations (DROP TABLE, TRUNCATE on populated tables);
- broad `Stop-Process -Force` on `node`;
- committing `.env*` files except `.env.example`;
- committing secrets, Vercel tokens, Supabase service-role keys, provider API keys, or Trigger.dev secrets.

## Commit style

- Conventional commits: `feat(...)`, `fix(...)`, `chore(...)`, `docs(...)`, `refactor(...)`.
- Reference the phase or retrofit packet when relevant: `feat(ai-r11.0): ...`, `docs(ai-r-providers): ...`.
- Multi-line commit messages: write to `.commit-msg.tmp`, then `git commit -F .commit-msg.tmp && rm .commit-msg.tmp` — Windows shells mangle heredocs with backticks.
- Always include the Co-Authored-By trailer.
- Never commit secrets — `.env.local` and similar are gitignored, do not work around that.

## Behaviors to enable

- Update `DECISIONS.md` when making an assumption not directly specified.
- Update the relevant `docs/oracle/*.md` file when AI architecture behavior changes.
- Update `HANDOFF.md` at the end of every session and when phase boundaries land.
- Run `pnpm -r typecheck` before declaring code complete.

## Behaviors to suppress

- Do not write speculative tests before the behavior is stable unless Albert asks.
- Do not refactor outside the immediate task scope without raising it as a separate item first.
- Do not re-introduce the Vercel AI SDK or OpenRouter into the production AI path — DECISIONS.md D6 and D9 explicitly rule them out.
