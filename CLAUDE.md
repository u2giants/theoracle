# CLAUDE.md

Read `AGENTS.md` first. Everything substantive about repo operation, architecture, and conventions lives there. This file only adds Claude Code-specific notes.

## MCP servers available in this environment

Prefer MCP tools over shell commands when applicable:

- **Supabase MCP** (`mcp__supabase__*`) — direct SQL execution, `apply_migration` for schema changes, `list_tables` / `list_migrations` / `get_advisors`.
- **Vercel MCP** (`mcp__vercel__*`) — read-only: deployment list, build/runtime logs, project info. **Does NOT support env-var writes.** For writes, use the Vercel REST API directly via PowerShell (pattern documented in `docs/deployment.md`).
- **gh CLI** — installed and authenticated. Use through Bash for PR/issue/release operations.
- **gcloud CLI** — installed under `%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\`. Two configurations: `default` (lithe-breaker-323913, unrelated) and `oracle` (vertex-ai-497120, the production GCP project). Use `--project=vertex-ai-497120` or switch configs explicitly.

## Context loading protocol

Read order for an unfamiliar task:

1. `AGENTS.md` — repo conventions, what to touch, what not to touch.
2. `oracle_master_spec.md` — product/business intent.
3. `DECISIONS.md` — historical decisions that may bind this task.
4. `docs/architecture.md` for system shape, `docs/configuration.md` for env vars, `docs/development.md` for run/test workflow, `docs/deployment.md` for deploy mechanics.
5. `docs/oracle/00-buildout-index.md` if the task touches the AI retrofit.
6. Only the specific `docs/oracle/0N-*.md` files the task needs — never bulk-read.

Do NOT bulk-read with `cat docs/oracle/*` or `cat *.md`. Each retrofit doc is large.

Before coding on a non-trivial task, write a short implementation plan in your response naming exactly which spec docs you read and why.

## Context management

Do not re-read `pnpm-lock.yaml`, `node_modules/`, `apps/web/.next/`, generated Drizzle SQL (`packages/db/migrations/0*.sql`). They're in `.claudeignore`.

When in doubt about AI behavior, read:

- `packages/ai/src/providers/*-adapter.ts` (one file per provider — each is ~150–250 lines)
- `packages/ai/src/client/standard-adapters.ts` (the `buildStandardAdapters()` helper used by every caller)
- `packages/ai/src/routes/{catalog,defaults,resolve,from-settings,types}.ts`
- `packages/ai/src/model-capabilities/` (provider model-list sources + OpenRouter enrichment + quality filters)
- `apps/web/lib/stage-requirements.ts` (single source of truth for per-stage capability requirements)
- `packages/ai/src/prompts/{oracle-system,extraction-system}.ts`

When in doubt about DB behavior, read:

- `packages/db/src/schema.ts`
- `packages/db/migrations/sql/*.sql` (hand-written) and the README in that folder

## Operations / permissions

Allowed without asking:

- Read/write under `apps/`, `packages/`, `docs/`, root markdown files.
- Run `pnpm install`, `pnpm db:generate`, `pnpm typecheck`, `pnpm build`, `pnpm lint`, `pnpm dev`.
- Run smoke tests and evals (`verify:*`, `eval:*`).
- Run the catalog helpers: `tsx scripts/verify-catalog.ts` (read-only) and `tsx scripts/refresh-catalog.ts` (writes to the production DB — same as clicking Refresh in the admin UI).
- Run git locally (status / diff / log / add / commit; push to `main` when Albert asks).
- Use Supabase MCP for reads and `apply_migration`.
- Use Vercel MCP for read operations.
- Call Vercel REST API for env-var writes when needed (use a session-scoped token; never commit it).
- Use `gh` for repo read/write.

Allowed with care:

- Writing to `extraction_*` / `claims` / `claim_*` tables is fine via the worker code path; never bypass the candidate-before-claim pipeline via direct `INSERT INTO claims`.
- `pnpm db:seed` is idempotent but writes to real Supabase — explicit ok needed for first run.
- Direct push to `main` only when Albert explicitly says push.
- **Branch policy: `main` only.** This is a single-branch repo with no promotion model. Do not create feature/staging/release branches or open routine PRs — commit directly to `main`. See AGENTS.md §12 "Release & CI/CD policy".
- Adding deps requires a one-line justification in the commit message.

Not allowed without explicit approval:

- `git reset --hard`, `git push --force`, deleting branches.
- Destructive Supabase operations (DROP TABLE, TRUNCATE on populated tables).
- Broad `Stop-Process -Force` on `node`.
- Committing `.env*` files except `.env.example`.
- Committing secrets — provider API keys, Supabase service-role keys, Vercel/Trigger.dev tokens, Vercel API tokens, Google SA JSON files.

## Commit style

- Conventional commits: `feat(...)`, `fix(...)`, `chore(...)`, `docs(...)`, `refactor(...)`.
- Reference the affected area when relevant: `feat(admin/model-pool): ...`, `fix(qwen): ...`.
- Multi-line commit messages: use a HEREDOC via `git commit -m "$(cat <<'EOF' … EOF)"` to avoid Windows shell mangling.
- Always include the Co-Authored-By trailer for AI-authored commits.
- Never commit secrets — `.env.local` and similar are gitignored, do not work around that.

## Git-add hygiene

Prefer `git add <specific-paths>` over `git add -A` when the working tree has unrelated uncommitted changes. One past incident: a `git add -A` swept in a Drizzle migration that hadn't been applied to production, leading to a 500-error storm on auth callback. When in doubt, run `git status` first and stage explicitly.

## Drizzle journal hygiene

The Drizzle `__drizzle_migrations` table in production tracks which generated `packages/db/migrations/0NNN_*.sql` files have been applied. It MUST stay in sync with what has actually run, or `pnpm db:migrate` will error out on Step 2 trying to re-create existing tables.

Rules to keep it in sync:

- **Drizzle-generated migrations** (`packages/db/migrations/0NNN_*.sql`) ship ONLY through `pnpm db:migrate` (or its workspace alias `pnpm -w run db:migrate`). The runner writes the journal row as part of applying the file.
- **Hand-written idempotent SQL** (`packages/db/migrations/sql/*.sql`) MAY be applied directly via Supabase MCP `apply_migration` — those files are not journaled by Drizzle and re-apply on every boot anyway.
- **Never** apply a generated `0NNN_*.sql` via Supabase MCP, the Supabase dashboard SQL editor, `psql`, or `drizzle-kit push`. All of those bypass the journal and create the same drift that was reconciled on 2026-05-28.
- If drift is suspected, compare `SELECT hash FROM drizzle.__drizzle_migrations ORDER BY created_at` against `sha256` of each on-disk `0NNN_*.sql`. Missing rows can be back-filled by INSERTing the correct hash; never DROP the table or TRUNCATE it (that would tell Drizzle every migration is unapplied and replay them all against a populated DB).

## Behaviors to enable

- Update `DECISIONS.md` when making an assumption not directly specified.
- Update the relevant `docs/oracle/*.md` file when AI architecture behavior changes.
- Update `docs/architecture.md` when catalog filtering or provider adapter behavior changes.
- Run `pnpm -r typecheck` before declaring code complete.
- When adding a new provider adapter: register it in `buildStandardAdapters()`, add the prefix mapping in `routes/resolve.ts`'s `OR_PROVIDER_MAP`, add the cache strategy to the `CacheStrategy` enum, and update `docs/architecture.md`'s adapter table.

## Behaviors to suppress

- Do not write speculative tests before the behavior is stable unless Albert asks.
- Do not refactor outside the immediate task scope without raising it as a separate item first.
- Do not re-introduce the Vercel AI SDK or OpenRouter into the production AI path — DECISIONS.md D6 and D9 explicitly rule them out.
- Do not revert the OpenAI model source from blocklist to allowlist — DECISIONS.md D13 records why the allowlist was abandoned.
- Do not hand-type model capability tables. The model list comes from the 5 direct provider APIs; pricing and capability flags come from OpenRouter enrichment. Both are persisted to the `model_capabilities` table.
- SSH is not part of the normal deployment path for this repo.
- Do not duplicate project-wide architecture or workflow guidance here; keep `AGENTS.md` as the source of truth.
