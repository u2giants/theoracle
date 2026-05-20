# HANDOFF — The Oracle

Live in-flight state of the project. Treat this as a session snapshot; whoever resumes (a fresh Claude Code session, a different developer, the same person on a different machine) should be able to pick up exactly where the previous session left off.

**Snapshot date:** 2026-05-20
**Latest commit on `main`:** `4744ca3` — docs (AGENTS.md, CLAUDE.md, docs/, ignore files)
**Repo:** https://github.com/u2giants/theoracle (PUBLIC — never commit secrets)
**Local checkout (previous machine):** `D:\repos\oracle` on Windows 11

---

## TL;DR for the new session

1. **Phases 1–3 are coded and pushed.** Phases 4–6 are scaffolded with TODOs. Read `oracle_master_spec.md` for the product, then `AGENTS.md` for the dev guide, then `DECISIONS.md` for assumption history.
2. **Nothing runs yet** — we're stuck on a `pnpm install` failure on the previous Windows machine. The hope is that a fresh machine (or a non-Windows machine) installs cleanly.
3. **The next concrete action** is: clone, install, populate `.env.local`, run `pnpm db:migrate && pnpm db:seed`, then `pnpm dev`. See "Resume on a new machine" below.

---

## Where we are by phase

| Phase | Status | Commit |
|---|---|---|
| Phase 0 — Bootstrap (repo init, .gitignore, DECISIONS.md, Vercel link) | done | `10d2b77` |
| Phase 1 — Foundation (Drizzle schema, RLS, auth callback, admin seed) | code done, not yet executed against the DB | `d832f5f` |
| Phase 2 — Realtime chat UI + document upload + admin skeleton | code done | `9efd3e1` |
| Phase 3 — Oracle chat route + tools + system prompt | code done | `eec3d58` |
| Phase 4 — Trigger.dev workers | scaffolds only (4 task files with workflow comments) | `4940327` |
| Phase 5 — Admin review dashboards | placeholders only | `4940327` |
| Phase 6 — Interjection engine | empty module with spec rules as JSDoc | `4940327` |
| Docs | done — `AGENTS.md` / `CLAUDE.md` / `docs/*` / ignore files | `4744ca3` |

Nothing has been wet-tested. Migrations have not been applied. The admin row has not been seeded. The Vercel deployment exists (project ID `prj_rP6Jlima7iK1paffEPhLqxlswGsC`) but Development env vars are empty (see "Open blockers" below).

---

## Open blockers (in order of urgency)

### 1. `pnpm install` keeps failing on Windows

**Symptom:** `ENOENT: no such file or directory, rename 'D:\repos\oracle\node_modules\.pnpm\@types+node@22.10.5\node_modules\undici-types' -> '...\.ignored_undici-types'`

**What we already tried** (none fixed it):
- Enabled Developer Mode + restarted Windows
- Ran installs from Administrator PowerShell (`whoami /priv` still shows `SeCreateSymbolicLinkPrivilege` as Disabled even in admin shell — unusual but apparently OS-normal lazy activation)
- Added Windows Defender exclusions for `D:\repos\oracle`, `%LOCALAPPDATA%\pnpm`, `pnpm.exe`, `node.exe`
- `pnpm install --force`
- `pnpm store prune`
- Robocopy-mirror an empty folder over `node_modules` to wipe broken junctions
- Tried `node-linker=hoisted` via `.npmrc` (didn't help — workspace packages still get symlinked regardless; removed from repo)

**What to try next** (in order):
1. **On a non-Windows machine first** (Mac/Linux/WSL2). The codebase has zero Windows-specific assumptions; a fresh Mac/Linux install should just work. If it does → confirms it's a local Windows-environment issue, not a repo issue.
2. **On Windows with WSL2** — clone inside the WSL filesystem, install there. Avoids the Windows symlink layer entirely.
3. **On Windows native, fresh attempt**: delete `pnpm-lock.yaml`, delete all `node_modules`, then `pnpm install` from an Admin shell. The lockfile may have records from the broken-symlink era that are interfering.
4. **Last resort**: switch the monorepo to **npm workspaces** instead of pnpm. Loses pnpm's isolation but works everywhere. Would require updating `package.json` + `pnpm-workspace.yaml` → `workspaces` array in `package.json`, removing `pnpm-lock.yaml`, and running `npm install`.

The Windows symlink saga is documented in `docs/development.md` (Windows-specific setup + the robocopy recipe) and `AGENTS.md` §11 (why no `.npmrc` is checked in).

### 2. Vercel Development env vars are empty

**Symptom:** `npx vercel env pull .env.local --environment=development` returns variable names with empty values for `DATABASE_URL`, `DIRECT_URL`, `NEXT_PUBLIC_SUPABASE_*`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`, `TRIGGER_SECRET_KEY`.

**Root cause:** Vercel doesn't allow **Sensitive** env vars to be set on the Development environment. The values exist on Production/Preview but not Development.

**Fix (one of):**
- **Easiest:** open each source dashboard (Supabase / OpenRouter / Trigger.dev) and paste values directly into `.env.local`. The file is gitignored. Reference dashboard pointers are in `docs/configuration.md`.
- **Cleaner:** convert each variable in Vercel from "Sensitive" to "Encrypted" type, then re-enter values and check the "Development" environment box. Then `vercel env pull` works.

Once `.env.local` has real values, the rest of the steps can proceed.

### 3. Supabase Storage bucket `company_documents`

Probably not created yet. Create it in Supabase dashboard → Storage → New bucket → name `company_documents`, **private**.

### 4. Pending dependency bumps

```bash
pnpm --filter @oracle/web up next@latest      # CVE-2025-66478 — Next 15.1.4 → 15.1.7+
pnpm -r up tsx@latest                          # drops deprecated @esbuild-kit/* subdeps
```

These were attempted on the previous machine but got stuck behind the install issue.

### 5. Vercel token rotation

The Vercel token shared during the overnight setup is in the chat transcript. **Rotate it** at https://vercel.com/account/tokens once the new machine has its own token (or stop using a token entirely and use `vercel login`).

---

## Credentials & accounts (where things live)

| Item | Where | Notes |
|---|---|---|
| GitHub | `u2giants/theoracle` (PUBLIC) | `gh` CLI was authed on the previous machine via SSH |
| Vercel project | `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | Web app deploys auto from `main` |
| Supabase project | URL is in Vercel env (`NEXT_PUBLIC_SUPABASE_URL`) | Database/Auth/Storage/Realtime |
| Supabase Storage bucket | `company_documents` | Needs creating if not done |
| Trigger.dev project | secret in Vercel env (`TRIGGER_SECRET_KEY`) | Workers — not yet deployed |
| OpenRouter | key in Vercel env (`OPENROUTER_API_KEY`) | Default models in `settings` table |
| OpenAI | key in Vercel env (`OPENAI_API_KEY`) | Embeddings only (optional — zero-vector fallback) |
| Admin seed | `u2giants@gmail.com` / Albert H. / Lead Architect / Executive / `is_admin=true` | Single row, idempotent |
| Test employee (for RLS gate) | `test-employee@oracle.local` | Delete before production |

---

## Architectural decisions in force

Read `AGENTS.md` §11 ("Idiosyncratic decisions") and `DECISIONS.md` for the full list. Highlights:

- **Magic-link auth is a dev stub.** Real OAuth (Microsoft Entra / Google / Authentik) is deferred per overnight decision. The `auth_provider` enum has a `magic_link_dev` value for this. The employee allowlist + `auth_user_id` linking flow is the real spec-compliant logic — only the upstream provider is stubbed.
- **Embedding dimension is locked at 1536.** Don't change it without re-embedding everything.
- **Claims have no `employee_id`.** Join through `claim_evidence.asserted_by_employee_id`. Spec Part 6.6.
- **`.npmrc` is deliberately NOT checked in.** It doesn't fix the Windows install issue (only hoists external deps; workspace packages get symlinked regardless).
- **No tests yet.** The spec calls for evaluation gates over real transcripts, not unit coverage on schemas. Don't add speculative tests.

---

## Resume on a new machine

```bash
# 1. Clone
git clone git@github.com:u2giants/theoracle.git oracle
cd oracle

# 2. Install pnpm if not present
npm install -g pnpm

# 3. Install deps (this is the step that was failing on the previous Windows box)
pnpm install

# 4. Populate .env.local
#    Option A: vercel CLI (requires Vercel token + project link)
npx vercel@latest link --project prj_rP6Jlima7iK1paffEPhLqxlswGsC --yes
npx vercel@latest env pull .env.local --environment=development --yes
#    Option B: paste values from Supabase / OpenRouter / Trigger.dev dashboards directly into .env.local
#               See docs/configuration.md for the full table of what goes where.

# 5. Apply schema + seed admin row
pnpm db:migrate
pnpm db:seed

# 6. Run
pnpm dev
```

Then verify the three acceptance gates — see `docs/development.md` → "Verifying Phase acceptance gates locally".

---

## Resume the Claude Code conversation

If you want a fresh Claude Code session to pick up exactly where we left off, give it this opening prompt verbatim:

> I'm continuing work on The Oracle. Read `HANDOFF.md` at the repo root first, then `AGENTS.md`, then `DECISIONS.md`, then `oracle_master_spec.md`. The previous session got stuck on a Windows `pnpm install` failure (`ENOENT` on rename of `undici-types` → `.ignored_undici-types`). I'm now on `<describe-machine: Mac / Linux / WSL2 / fresh Windows>`. Walk me through resuming from "Resume on a new machine" in `HANDOFF.md`.

The conversation history itself doesn't transfer between machines — but every meaningful decision, blocker, and next step is already in the repo (`HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, commit history). A fresh session can pick up cleanly.

---

## Suggested first move when you resume

If the new machine is non-Windows, just run the "Resume on a new machine" steps above. The install should succeed cleanly and you'll be looking at a running dev server within ~10 minutes.

If the new machine is Windows again, **clone into WSL2** (`\\wsl$\Ubuntu\home\<user>\repos\oracle` or similar). Native Windows pnpm + symlinks has been the entire blocker; WSL2 sidesteps it. Once it's running there, the rest of the work proceeds normally.
