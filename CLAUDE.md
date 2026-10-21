<!-- Privacy rendering: infrastructure references are non-executable publication placeholders. Original Git blob 9f1337301fa2ad7ca3c537e308183c9f26986434 at ab73ef791ad48f187fa5d2998428aec99ce6bd82; exact originals are retained in the #27 private custody archive. No obligations, authority, timing or acceptance are changed. -->
# CLAUDE.md

Read `AGENTS.md` first. It is the canonical operating guide for this repo.

This file contains Claude Code-specific notes only. If guidance applies to all developers or all AI agents, put it in `AGENTS.md` instead.

## Claude Code context

- `.claudeignore` is the Claude Code ignore file. Keep it aligned with `AGENTS.md` "What to ignore" and the other AI ignore files.
- Do not bulk-read `docs/oracle/`, root historical specs, generated Drizzle SQL, `pnpm-lock.yaml`, or build artifacts. Load only the docs named by the AGENTS documentation map for the task.
- `HANDOFF.d/` is required reading at session start: list it, read the open files newest-first, and apply the successor-delete rule in `AGENTS.md` §3a. Root `HANDOFF.md` is a static pointer — never rewrite it.

## Claude-specific tools

- Supabase MCP may be used for reads and for applying hand-written idempotent SQL migrations. Do not use it for generated Drizzle `packages/db/migrations/0*.sql`.
- Vercel MCP is read-only in this environment; use the Vercel dashboard or REST API for env-var writes.
- Trigger.dev MCP can inspect/trigger/deploy workers for project `proj_PRIVATE_REFERENCE_SHA256_9f596b7f49dd981243eda05436fe11207bc7a91b39b7806c41a831504c04bb01`.
- `gh` is available for GitHub operations.

## Operations

- Commit directly to `main` only when Albert explicitly asks to push.
- Prefer `git add <specific-paths>` over `git add -A`.
- Never commit secrets, `.env.local`, cert private keys, provider keys, Vercel/Trigger/Supabase tokens, or Google service-account JSON.
- SSH is not part of the normal deployment path for this repo.

## Commit style

- Use concise conventional commits when practical, for example `docs(agents): update repo guide`.
- Include a `Co-Authored-By` trailer for Claude-authored commits when the user has not requested otherwise.
