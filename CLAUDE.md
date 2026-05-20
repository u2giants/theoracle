# CLAUDE.md — Claude Code Notes

**Read `AGENTS.md` first.** Everything substantive lives there. This file is just Claude Code-specific.

## Memory

This project does not currently use Claude Code persistent memory. If you start, document the memory key naming convention here.

## Context management

- The repo is small but dense. Start each session by reading **`HANDOFF.md`** (current state — done/pending/blockers), then `AGENTS.md` (15 sections), then `oracle_master_spec.md` (large but authoritative), then `DECISIONS.md`.
- Do not re-read `pnpm-lock.yaml`, `node_modules/`, `apps/web/.next/`, or generated Drizzle SQL. They're listed in `.claudeignore`.
- When in doubt about behavior, read `packages/db/src/schema.ts` and `packages/ai/src/prompts/oracle-system.ts` — those two files plus the spec define everything else.
- The hand-written SQL migration ordering is documented in `packages/db/migrations/sql/README.md` (numeric prefixes have meaning).

## `.claudeignore`

Already at the repo root. If you add new build artifacts or large generated dirs, update both `.claudeignore` and `.cursorignore` in the same commit so other AI tools stay in sync.

## Operations / permissions

- **Allowed:** read/write anything under `apps/`, `packages/`, `docs/`, root markdown files. Run `pnpm install`, `pnpm db:generate`, `pnpm db:migrate`, `pnpm typecheck`, `pnpm build`, `pnpm lint`, `pnpm dev`. Run git locally. Use `gh` CLI for read-only GitHub queries.
- **Allowed with care:** `pnpm db:seed` (idempotent but writes to the real Supabase DB), `git push` to `main` (the user has authorized direct-to-main commits for the build phase).
- **Not allowed:** `Stop-Process -Force` on `node` broadly (it kills MCP servers and IDEs). Target `pnpm` specifically. Don't run destructive git (`reset --hard`, `push --force`) without explicit per-action approval.

## APIs Claude may call

- **GitHub** (`gh` CLI) — read PRs/issues, create commits/branches/PRs.
- **Vercel** (via `npx vercel@latest` with the project's token) — link project, pull env vars, list deployments. Do not deploy from Claude — Vercel auto-deploys on push.
- **Supabase** (via the SDK using the service role key, server-side only) — DB queries, storage uploads.
- **OpenRouter / OpenAI** — only through the wrappers in `packages/ai/`.

## SSH

There are no SSH targets. The stack is fully managed cloud. If a future task seems to require SSH, that is almost certainly a sign the task is misframed — escalate to Albert before proceeding.

## Commit style

- Conventional commits: `feat(...)`, `fix(...)`, `chore(...)`, `docs(...)`.
- Reference the phase when relevant: `feat(phase-3): ...`.
- HEREDOC for multi-line messages.
- Include the `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer.
- Never commit `.env*` (except `.env.example`).
- Do not commit anything containing the Vercel token, Supabase service role key, OpenRouter key, or Trigger.dev secret.

## Tool preferences

- File ops: `Read`, `Edit`, `Write` — not `cat`/`sed`/`awk`.
- Search: `Grep` and `Glob` — not `grep`/`rg`/`find`.
- Long-running scaffolds: spawn an `Agent` (background) rather than blocking the main session.
- Multi-step research: `Plan` agent. Open-ended exploration: `Explore` agent.

## Behaviors to enable

- Always update `DECISIONS.md` when making an assumption that wasn't directly specified.
- Always update the relevant `docs/*.md` file when behavior changes — don't leave docs as a final-pass task.
- Update `AGENTS.md` "Pending work" table at the end of every session.

## Behaviors to suppress

- Do not write tests speculatively. Write tests when a behavior is stable and the user asks for coverage.
- Do not refactor outside the immediate task scope without raising it as a separate item first.
- Do not introduce new dependencies without a one-line justification in the commit message.
