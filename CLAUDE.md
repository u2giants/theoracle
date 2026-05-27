# CLAUDE.md — Claude Code Notes

**Read `AGENTS.md` first.** Everything substantive about repo operation, architecture, and conventions lives there. This file adds only Claude Code-specific notes.

## Current state (2026-05-27)

Production SHA `65f250e` (Vercel). Model-pool overhaul complete:
- Live model catalog sourced from openrouter.ai, persisted to `model_capabilities` table.
- Per-stage pools (`model_pool_interview` / `_extraction` / `_synthesis`).
- Fourth `/admin/settings` card: "General-purpose model" picker.
- `/api/chat` uses lazy `OracleAIClient` init (previous module-level singleton broke Vercel builds for ~12h).

See `HANDOFF.md` for the full session log and unfinished work. See `DECISIONS.md` for the why behind the OpenRouter-as-catalog decision (D6, D9 already cover the no-Vercel-AI-SDK, no-OpenRouter-for-inference policy; OpenRouter is admin-side metadata only).

## MCP servers available in this environment

This session typically has the following MCP servers connected. Prefer them over shell commands when applicable:

- **Supabase MCP** (`mcp__supabase__*`) — direct SQL execution against the live database, `apply_migration` for schema changes, `list_tables` / `list_migrations` / `get_advisors`. If the tools appear deferred-only, run `authenticate` once.
- **Vercel MCP** (`mcp__vercel__*`) — deployment list, build/runtime logs, env reads. Does NOT support env-var writes; use the Vercel REST API directly via PowerShell when needed (see HANDOFF.md for the exact pattern).
- **gh CLI** — installed and authenticated. Use through Bash for PR/issue/release operations.
- **gcloud CLI** — installed under `%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\`. Two configurations: `default` (lithe-breaker-323913, unrelated) and `oracle` (vertex-ai-497120, the production GCP project). Use `--project=vertex-ai-497120` or switch configs explicitly.

If a tool isn't loaded, use `ToolSearch` with `select:<tool_name>` (specific) or a keyword query.

## Context loading protocol

Read order for an unfamiliar task:

1. `HANDOFF.md` — current state + unfinished work
2. `AGENTS.md` — repo conventions
3. `oracle_master_spec.md` — product/business intent
4. `DECISIONS.md` — historical decisions that may bind this task
5. `docs/architecture.md` for system shape, `docs/configuration.md` for env vars, `docs/development.md` for run/test workflow, `docs/deployment.md` for deploy mechanics
6. `docs/oracle/00-buildout-index.md` if the task touches the AI retrofit
7. Only the specific `docs/oracle/0N-*.md` files the task needs — never bulk-read

Do NOT bulk-read with `cat docs/oracle/*` or `cat *.md`. Each retrofit doc is large.

Before coding on a non-trivial task, write a short implementation plan in your response naming exactly which spec docs you read and why.

## Context management

Do not re-read `pnpm-lock.yaml`, `node_modules/`, `apps/web/.next/`, generated Drizzle SQL (`packages/db/migrations/0*.sql`). They're in `.claudeignore`.

When in doubt about behavior, read:

- `packages/db/src/schema.ts`
- `packages/db/migrations/sql/*.sql` (hand-written) and the README in that folder
- `packages/ai/src/prompts/extraction-system.ts` and `oracle-system.ts`
- `packages/ai/src/routes/catalog.ts` and `defaults.ts`
- `packages/ai/src/model-capabilities/` (the OpenRouter discovery service)
- `docs/oracle/00-buildout-index.md`

## `.claudeignore`

Lives at repo root. If you add new build artifacts or large generated dirs, update both `.claudeignore` and `.cursorignore` in the same commit.

## Operations / permissions

Allowed without asking:

- Read/write under `apps/`, `packages/`, `docs/`, root markdown files
- Run `pnpm install`, `pnpm db:generate`, `pnpm typecheck`, `pnpm build`, `pnpm lint`, `pnpm dev`
- Run smoke tests and evals (`verify:*`, `eval:*`)
- Run git locally (status / diff / log / add / commit; push to `main` when Albert asks)
- Use Supabase MCP for reads and `apply_migration`
- Use Vercel MCP for read operations
- Call Vercel REST API for env-var writes when needed (use a session-scoped token; never commit it)
- Use `gh` for repo read/write

Allowed with care:

- Writing to `extraction_*` / `claims` / `claim_*` tables is fine via the worker code path; never bypass the candidate-before-claim pipeline via direct `INSERT INTO claims`
- `pnpm db:seed` is idempotent but writes to real Supabase — explicit ok needed for first run
- Direct push to `main` only when Albert explicitly says push
- Adding deps requires a one-line justification in the commit message

Not allowed without explicit approval:

- `git reset --hard`, `git push --force`, deleting branches
- Destructive Supabase operations (DROP TABLE, TRUNCATE on populated tables)
- Broad `Stop-Process -Force` on `node`
- Committing `.env*` files except `.env.example`
- Committing secrets — provider API keys, Supabase service-role keys, Vercel/Trigger.dev tokens, Vercel API tokens, Google SA JSON files

## Commit style

- Conventional commits: `feat(...)`, `fix(...)`, `chore(...)`, `docs(...)`, `refactor(...)`
- Reference the phase or retrofit packet when relevant: `feat(ai-r11.0): ...`, `docs(ai-r-providers): ...`
- Multi-line commit messages: use a HEREDOC via `git commit -m "$(cat <<'EOF' … EOF)"` to avoid Windows shell mangling
- Always include the Co-Authored-By trailer
- Never commit secrets — `.env.local` and similar are gitignored, do not work around that

## Behaviors to enable

- Update `DECISIONS.md` when making an assumption not directly specified
- Update the relevant `docs/oracle/*.md` file when AI architecture behavior changes
- Update `HANDOFF.md` at the end of every session and when phase boundaries land
- Run `pnpm -r typecheck` before declaring code complete

## Behaviors to suppress

- Do not write speculative tests before the behavior is stable unless Albert asks
- Do not refactor outside the immediate task scope without raising it as a separate item first
- Do not re-introduce the Vercel AI SDK or OpenRouter into the production AI path — DECISIONS.md D6 and D9 explicitly rule them out. OpenRouter's `/v1/models` is used ONLY for admin-side catalog metadata via the discovery service, never for inference.
- Do not hand-type model capability tables. The capability source is the `model_capabilities` table populated from OpenRouter.
