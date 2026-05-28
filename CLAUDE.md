# CLAUDE.md

Read `AGENTS.md` first.

Claude Code-specific notes:

- Respect `.claudeignore`. Keep it in sync with `.cursorignore` and `.copilotignore`.
- Prefer repo files and configured tools over memory or assumptions.
- SSH is not part of the normal deployment path for this repo.
- Allowed routine operations: edit repo-owned code/docs, run `pnpm install`, `pnpm typecheck`, `pnpm --filter @oracle/web build`, worker/typecheck scripts, and repo-local git commands.
- Use MCP/connected tools when they provide a cleaner path than shell commands, but do not bypass the repo’s documented deployment or migration flow.
- Commit style: conventional commits such as `feat(...)`, `fix(...)`, `docs(...)`, `refactor(...)`.
- Do not duplicate project-wide architecture or workflow guidance here; keep `AGENTS.md` as the source of truth.
