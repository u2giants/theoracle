# Development

Local setup, day-to-day workflow, and the gotchas that have already bitten us.

## Prerequisites

- **Node.js ≥ 20** (we develop on 24). `node -v` should print something ≥ 20.0.
- **pnpm ≥ 9** (`npm install -g pnpm` or via Corepack: `corepack enable && corepack prepare pnpm@latest --activate`).
- **Git** with SSH keys configured for `github.com/u2giants`.
- A populated `.env.local` (see `docs/configuration.md`).

## Windows-specific setup

This monorepo uses pnpm workspaces, which need symlinks. Windows is awkward about that. Do all of the following before your first `pnpm install`:

1. **Enable Developer Mode** — Settings → For Developers → Developer Mode → On. **Then sign out and back in, or restart**. The privilege grant is stamped into your session token at logon.
2. **Run PowerShell as Administrator** for the first install. Administrator accounts have `SeCreateSymbolicLinkPrivilege` enabled in their token. Subsequent installs from a non-admin shell will usually work once the workspace is populated.
3. **Add Windows Defender exclusions** (the install will be much faster and won't trip on file-rename races):
   ```powershell
   Add-MpPreference -ExclusionPath "D:\repos\oracle"        # adjust path
   Add-MpPreference -ExclusionPath "$env:LOCALAPPDATA\pnpm"
   Add-MpPreference -ExclusionProcess "pnpm.exe"
   Add-MpPreference -ExclusionProcess "node.exe"
   ```
4. **No `.npmrc` workaround is checked in** — we tested `node-linker=hoisted` and it doesn't fix workspace symlinks (only external deps). The real fixes are the three steps above. If you find yourself reaching for `.npmrc`, first verify Dev Mode is actually active and try an Admin shell install. See `AGENTS.md` §11.

If you hit `ENOENT: no such file or directory ... .pnpm\...\@types+node\...\undici-types`, see the "When pnpm install hangs or ENOENTs on Windows" recipe below.

## First-time setup

```bash
git clone git@github.com:u2giants/theoracle.git oracle
cd oracle
pnpm install

# Pull env from Vercel (requires the project's token; ask Albert)
npx vercel@latest link --project prj_rP6Jlima7iK1paffEPhLqxlswGsC --token <token> --yes
npx vercel@latest env pull .env.local --environment=development --yes

# If Vercel's Development env vars are empty (sensitive vars can't live there),
# paste values manually from Supabase / OpenRouter / Trigger.dev dashboards.

# Run migrations + seed
pnpm db:migrate
pnpm db:seed
```

You should now have:
- A populated Supabase database with the full schema, RLS, views, and the admin row for `u2giants@gmail.com`.
- A `.env.local` with real secret values.

## Run / build / typecheck / lint

```bash
pnpm dev         # turbo dev — runs `next dev` (web) and `trigger dev` (workers) in parallel
pnpm build       # turbo build — runs every workspace's build
pnpm typecheck   # turbo typecheck — runs tsc --noEmit everywhere
pnpm lint        # turbo lint — ESLint for web, tsc-as-lint for packages
pnpm format      # prettier write
```

Filter to a single workspace:

```bash
pnpm --filter @oracle/web dev
pnpm --filter @oracle/workers dev
pnpm --filter @oracle/db generate     # drizzle-kit generate (after schema.ts changes)
pnpm --filter @oracle/db migrate
pnpm --filter @oracle/db seed
```

## Adding a database change

1. Edit `packages/db/src/schema.ts`.
2. `pnpm db:generate` → produces a new `packages/db/migrations/0NNN_*.sql` file. **Do not hand-edit** it.
3. If you need constraints, RLS, helper functions, or views: add `packages/db/migrations/sql/NN_<topic>.sql` with the next free numeric prefix (current files use 01/10/20/21/30/99).
4. `pnpm db:migrate` applies everything in order. The runner (`packages/db/src/migrate.ts`) is idempotent.
5. Update `docs/architecture.md`'s data-model table if you added a new top-level entity.

## Adding a new package

1. `mkdir packages/<name>` with `package.json` (`"name": "@oracle/<name>"`, `"private": true`, `"type": "module"`, `"main": "./src/index.ts"`, `"types": "./src/index.ts"`).
2. Add `tsconfig.json` extending `../../tsconfig.base.json`.
3. Reference it from another workspace via `"@oracle/<name>": "workspace:*"`.
4. `pnpm install` to wire the workspace symlinks.

## Tests

We don't have a test framework wired yet. When we do, the convention will be Vitest at the package level (`packages/<x>/src/__tests__/*.test.ts`). Don't write speculative tests before then — the spec calls for evaluation gates over real transcripts, not unit coverage on schemas.

## When pnpm install hangs or ENOENTs on Windows

Symptom: install stalls at "Progress: resolved N, reused N, downloaded 0, added 0" for >5 minutes, or errors with `ENOENT: no such file or directory, rename '...\@types+node@22.10.5\node_modules\undici-types' -> '...\.ignored_undici-types'`.

Recovery (in elevated PowerShell):

```powershell
# 1. Kill any lingering pnpm processes (NEVER blanket-kill node — kills MCP servers + IDEs)
Get-Process pnpm -ErrorAction SilentlyContinue | Stop-Process -Force

# 2. Robocopy-nuke node_modules everywhere (handles broken junctions Remove-Item can't)
$empty = New-Item -ItemType Directory -Path "$env:TEMP\empty-$([guid]::NewGuid())" -Force
Get-ChildItem -Path D:\repos\oracle -Filter node_modules -Recurse -Force -Directory | ForEach-Object {
    robocopy $empty.FullName $_.FullName /MIR /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
    Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
}
Remove-Item $empty.FullName -Force -ErrorAction SilentlyContinue

# 3. Optionally prune pnpm's store cache
pnpm store prune

# 4. Reinstall
pnpm install
```

If the lockfile itself was generated under the broken-symlink era, regenerate it:

```powershell
Remove-Item pnpm-lock.yaml -Force
pnpm install
```

…then commit the new lockfile.

## Verifying Phase acceptance gates locally

Once `pnpm db:migrate && pnpm db:seed && pnpm dev` is green, manually verify the three phase gates:

**Phase 1 (foundation):**
- Hit `http://localhost:3000/` → enter `u2giants@gmail.com` → magic link in email → land on `/admin`.
- Repeat with a random Gmail → should land on `/denied?reason=not_approved`.

**Phase 2 (realtime):**
- Two browsers (one as Albert, one logged in as `test-employee@oracle.local`).
- Insert a `channels` row + two `channel_participants` rows (admin + test-employee) via the admin dashboard or SQL.
- Send a message from each browser; both should see both messages live.
- A third browser logged in as a third employee NOT in the channel must get 0 rows when querying that channel.
- Upload a document; verify the `documents` row and storage object both exist.

**Phase 3 (Oracle chat):**
- In a channel, send `@oracle what do you know about our licensing process?`.
- An assistant message should stream in, asking ONE question.
- Verify a `model_runs` row was inserted (latency, cost, token counts populated).

## Quick commit recipe

```bash
git add -A
git commit -m "$(cat <<'EOF'
feat(scope): short message

Longer explanation if needed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```
