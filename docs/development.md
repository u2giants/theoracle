# Development

Local setup, day-to-day workflow, and the gotchas that have already bitten us.

## Prerequisites

- **Node.js ≥ 20** (we develop on 24). `node -v` should print something ≥ 20.0.
- **pnpm ≥ 9** (`npm install -g pnpm` or via Corepack: `corepack enable && corepack prepare pnpm@latest --activate`).
- **Git** with SSH keys configured for `github.com/u2giants`.
- An **NTFS** repo location on Windows (see below), or any Linux/macOS filesystem.
- A populated `.env.local` at the **monorepo root** (see `docs/configuration.md`).

## Windows-specific setup

The monorepo uses pnpm workspaces, which need symlinks. Two things have to be true on Windows for that to work:

1. **The repo directory must be on an NTFS volume.** exFAT and FAT32 do not support symlinks at all, and pnpm fails with cryptic `ENOENT: ... rename ... .ignored_*` errors that look like permission problems. Confirm with `Get-Volume D | Select-Object FileSystemType` (substitute your drive letter). If it says anything other than NTFS, **reformat to NTFS or move the repo to an NTFS drive** before doing anything else.
2. **Windows Developer Mode enabled.** Settings → For Developers → Developer Mode → On. After enabling, **sign out and back in** (or restart) — the symlink privilege is stamped into your session token at logon, so toggling it in an existing session is not enough.

After those two preconditions, `pnpm install` from a regular PowerShell should work. If anything goes wrong, the recovery recipe below covers the common cases. Running the first install from an Administrator PowerShell helps because admin tokens have `SeCreateSymbolicLinkPrivilege` enabled unconditionally.

**Recommended Defender exclusions** (not strictly required, makes installs much faster):

```powershell
Add-MpPreference -ExclusionPath "D:\repos\oracle"          # adjust path
Add-MpPreference -ExclusionPath "$env:LOCALAPPDATA\pnpm"
Add-MpPreference -ExclusionProcess "pnpm.exe"
Add-MpPreference -ExclusionProcess "node.exe"
```

**No `.npmrc` workaround is checked in.** We tried `node-linker=hoisted`; it does not help with workspace packages. See `AGENTS.md` §11.

## First-time setup

```bash
git clone git@github.com:u2giants/theoracle.git oracle
cd oracle
pnpm install

# Pull env from Vercel (one-time link, then pull)
npx vercel@latest link --project prj_rP6Jlima7iK1paffEPhLqxlswGsC --yes
npx vercel@latest env pull .env.local --environment=development --yes

# If Vercel's Development env vars are empty (sensitive vars can't live there),
# either convert them to Encrypted type in Vercel and re-pull, or paste values
# manually from Supabase / OpenRouter / Trigger.dev dashboards.
# See docs/configuration.md for the exact source for each variable.

# Apply schema + raw SQL (RLS, constraints, views, data migrations) + seed
pnpm db:migrate
```

`pnpm db:migrate` is idempotent and runs the seed at the end (admin row + test employee + settings defaults). You don't need to run `pnpm db:seed` separately on a fresh setup.

After this you should have:
- A populated Supabase database with the full schema, RLS, views, and the admin row for `u2giants@gmail.com`.
- A `.env.local` with real secret values at the monorepo root.

## Run / build / typecheck / lint

```bash
pnpm dev          # turbo dev — runs `next dev` (web) and `trigger dev` (workers) in parallel
pnpm build        # turbo build — runs every workspace's build
pnpm typecheck    # turbo typecheck — runs tsc --noEmit everywhere
pnpm lint         # turbo lint — ESLint for web, tsc-as-lint for packages
pnpm format       # prettier write
```

If you only want the web app (no Trigger.dev CLI invocation), filter:

```bash
pnpm --filter @oracle/web dev
```

Other useful filters:

```bash
pnpm --filter @oracle/db generate     # drizzle-kit generate (after schema.ts changes)
pnpm --filter @oracle/db migrate
pnpm --filter @oracle/db seed
pnpm --filter @oracle/workers dev     # requires Trigger.dev CLI; the script uses npx
```

## Adding a database change

1. Edit `packages/db/src/schema.ts`.
2. `pnpm db:generate` → produces a new `packages/db/migrations/0NNN_*.sql` file. **Do not hand-edit** it.
3. If you need constraints, RLS, helper functions, views, or data migrations: add a `packages/db/migrations/sql/NN_<topic>.sql` file with the next free numeric prefix. **See `packages/db/migrations/sql/README.md` for the ordering convention** — files run in lex order on every boot and must be idempotent.
4. `pnpm db:migrate` applies everything in order. The runner (`packages/db/src/migrate.ts`) is idempotent.
5. Update `docs/architecture.md`'s data-model table if you added a new top-level entity.

## Adding a new package

1. `mkdir packages/<name>` with `package.json` (`"name": "@oracle/<name>"`, `"private": true`, `"type": "module"`, `"main": "./src/index.ts"`, `"types": "./src/index.ts"`).
2. Add `tsconfig.json` extending `../../tsconfig.base.json`.
3. Reference it from another workspace via `"@oracle/<name>": "workspace:*"`.
4. `pnpm install` to wire the workspace symlinks.

## Tests

We don't have a test framework wired yet. When we do, the convention will be Vitest at the package level (`packages/<x>/src/__tests__/*.test.ts`). Don't write speculative tests before then — the spec calls for evaluation gates over real transcripts, not unit coverage on schemas.

## Inspection / debugging scripts

`packages/db/src/` ships two small tsx scripts useful for local debugging:

- `verify-identities.ts` — prints current `employees` rows, their `employee_identities`, and any orphan identity rows. Run with `pnpm --filter @oracle/db exec tsx src/verify-identities.ts`.
- `inspect-auth-users.ts` — prints rows from Supabase's `auth.users` schema so you can see which providers Supabase has on file for each email. Same invocation pattern.

Both load `.env.local` from the monorepo root.

## When `pnpm install` errors or hangs on Windows

If you're on Windows with an NTFS drive and Developer Mode enabled, the install should just work. If it doesn't:

Symptom 1: `ENOENT: no such file or directory, rename '...\.ignored_*'`
Symptom 2: install stalls at `Progress: resolved N, reused N, downloaded 0, added 0` for >5 minutes.

Recovery in an elevated PowerShell:

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

If the lockfile itself was generated under broken conditions, regenerate it:

```powershell
Remove-Item pnpm-lock.yaml -Force
pnpm install
```

…then commit the new lockfile.

If it still fails, **double-check the filesystem** — `Get-Volume D | Select-Object FileSystemType` must return NTFS. This is by far the most common root cause and the one we spent the longest debugging without finding it.

## Verifying Phase acceptance gates locally

**Phase 1 (foundation) — wet-tested:**
- Click "Sign in with Google" as `u2giants@gmail.com` → land on `/admin`.
- Click "Sign in with Microsoft 365" as `albert@popcre.com` → land on `/admin` (same Albert, multi-identity confirmed).
- Sign in with any non-allowlisted address → `/denied?reason=not_approved`.

**Phase 2 (realtime) — partial:**
- Requires two real loginable employees. The seeded `test-employee@oracle.local` is not deliverable; replace its email with a Gmail `+`-alias (e.g. `u2giants+test@gmail.com`) or seed a second real employee.
- Open two browsers, sign in as each, insert a `channels` row + two `channel_participants` rows via SQL (the Phase 5 admin UI isn't built yet).
- Both browsers should see new messages live.
- A third logged-in employee NOT in the channel must get 0 rows when querying that channel.
- Upload a document; verify the `documents` row and Storage object both exist.

**Phase 3 (Oracle chat) — ready to wet-test:**
- In a channel, send `@oracle what do you know about our licensing process?`.
- An assistant message should appear, asking ONE question.
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
