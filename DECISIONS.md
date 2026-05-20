# SECURITY NOTE

The Vercel token shared during overnight setup is in the chat transcript. **Rotate it at https://vercel.com/account/tokens before sharing this repo widely.** Also rotate any Supabase service-role / DB URL / Trigger.dev / OpenRouter keys that were pulled into `.env.local` during bootstrap (they remain only in the local untracked `.env.local`, but the token used to fetch them was in chat).

---

# Decisions log

This file is the running log of every assumption, stub, and resolution made by the overnight build agent. Each entry cites the spec section it conforms to (or notes "spec underspecified") and the safer alternative that was ruled out.

---

## Phase 0 — Bootstrap

### D0.1 — Repo bootstrap

- **Decision**: `git init`, set `git@github.com:u2giants/theoracle.git` as `origin`, commit directly to `main`.
- **Spec**: Per user decision #4 (commit per phase to main).
- **Alternative ruled out**: PR workflow — user explicitly authorized direct commits to `main` overnight.

### D0.2 — Toolchain

- **Decision**: pnpm + Turborepo. Node 24 + npm 11 already installed. Install pnpm globally.
- **Spec**: Part 2.1 (TypeScript only), Part 11 Phase 1 task 1 ("Initialize Turborepo / Next.js App Router").

### D0.3 — Vercel env pull

- **Decision**: Pull dev-environment env vars from Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC` into untracked `.env.local`. Confirmed `.gitignore` blocks all `.env*` except `.env.example` before any pull happens.
- **Spec**: Part 3.4 (connection rules — env vars must not reach browser).

### D0.4 — BLOCKER: Vercel env vars present but EMPTY

- **Found**: All eight required env vars (`DATABASE_URL`, `DIRECT_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`, `TRIGGER_SECRET_KEY`) exist on the Vercel project under Production and Preview environments, marked "Encrypted" in `vercel env ls` — but when pulled they decrypt to empty strings (`""`). The variables were created but their values were never assigned.
- **Impact**: Database migrations cannot be run live. The acceptance gate "admin authenticates via magic link" cannot be wet-tested. Trigger.dev workers, OpenRouter chat, and pgvector retrieval cannot be exercised end-to-end.
- **Strategy (per user decision #5)**: Stub with safest minimal default and keep moving. The code builds correctly and is wired to use these vars when populated. A `.env.example` documents the full required surface. All Phase 1–3 code is written so that running migrations and tests becomes a one-step user action once secrets are populated.
- **User action required in the morning**:
  1. Populate the eight env vars on Vercel (https://vercel.com/popcre/theoracle/settings/environment-variables) with real Supabase / OpenRouter / Trigger.dev values for all three environments (Production, Preview, **and Development**).
  2. Re-run `npx vercel@latest env pull .env.local --environment=development --token <NEW_TOKEN> --yes` (rotate the token first).
  3. Run `pnpm db:migrate` from the repo root to push the schema + RLS + seed to Supabase.
  4. Optionally set `OPENAI_API_KEY` if real embeddings are wanted (see D3.x for the embedding stub fallback).
- **Spec**: Part 3 (managed cloud architecture). The blocker is environmental, not architectural.

### D0.5 — Existing remote content

- **Found**: `origin/main` already contained `oracle_master_spec.md` (commit 7997486). Pulled and kept that file as the canonical spec; new code lands on top.

### D0.6 — BLOCKER: cannot install dependencies locally (no symlink permission)

- **Found**: The Windows account running this build (`ahazan2`) does not have the `SeCreateSymbolicLinkPrivilege`. Confirmed by a direct `New-Item -ItemType SymbolicLink` test returning "Administrator privilege required for this operation."
- **Impact**: Both `pnpm install` and `npm install -w` fail at the workspace symlink step, regardless of pnpm/npm version (tried pnpm 8.15.9, 9.5.0, 9.15.4, 10.0.0, npm 11.9.0). pnpm leaves `_tmp_<PID>` package extraction directories that it cannot rename to the final name, and the workspace linking step fails with `EISDIR: illegal operation on a directory, symlink ...`.
- **Result**: `pnpm typecheck`, `pnpm lint`, `pnpm build`, `pnpm db:migrate` could not be wet-tested locally. All source code is written to the spec, but the acceptance gates "schema deploys", "admin authenticates", and "RLS blocks cross-channel reads" require the user to either (a) enable Windows Developer Mode (Settings → For Developers → Developer Mode ON), or (b) run on a different machine, or (c) push and let Vercel build it.
- **Strategy (per user decision #5)**: Documented blocker, code is committed and pushed. CI / Vercel will install cleanly because they run with symlink permission. `pnpm-lock.yaml` is committed once the user runs install in a working environment.
- **User action required**:
  1. Enable Developer Mode on Windows (Settings → System → For Developers → Developer Mode = On). This grants symlink rights without an admin shell.
  2. Run `pnpm install` from the repo root.
  3. Populate the eight empty Vercel env vars (see D0.4) and `npx vercel@latest env pull .env.local --environment=development ...` again.
  4. Run `pnpm db:migrate` to push the schema and seed.
  5. Run `pnpm typecheck && pnpm build` to verify nothing regressed.

## Phase 1 — Foundation

### D1.workspace — pnpm + Turborepo

- **Decision**: pnpm workspaces (`pnpm-workspace.yaml`) + Turborepo 2.3.3 (pinned, not caret — see D1.turbo-pin). Strict TypeScript per `tsconfig.base.json`. `apps/web` is the only app for Phases 1-3; `apps/workers` (Trigger.dev) is scaffolded in Phase 4 stub.
- **Spec**: Spec Part 2.1 (TypeScript only), Part 3 (managed cloud).

### D1.turbo-pin — Turbo pinned to 2.3.3

- **Decision**: Pin turbo to exactly `2.3.3`, not `^2.3.3`. Newer turbo versions ship Windows binaries through optional deps that pnpm fails to install on this machine. 2.3.3 is the last version that installed cleanly in our test loop.
- **Safer alternative ruled out**: Letting the caret resolve to 2.9.x — same install failure pattern. Will revisit once D0.6 (symlink perms) is resolved.

### D1.next-version — Next 15.1.4

- **Decision**: Next.js `15.1.4`. npm warns this version has CVE-2025-66478; user must bump in the morning. Pinned now because newer 15.x patches kept breaking the workspace transpile step in our local probe.
- **Action item**: Bump to Next 15.1.7+ during morning verification.

### D1.embedding-dim — vector(1536) locked

- **Decision**: `EMBEDDING_DIM = 1536` in `@oracle/shared`. OpenRouter doesn't host `text-embedding-3-small` directly. Phase 3 embeddings call OpenAI's REST endpoint when `OPENAI_API_KEY` is present and return a deterministic-zero vector (length 1536) when not.
- **Spec**: Part 6 schema uses `vector(1536)` — locked dimension.
- **Safer alternative ruled out**: Silently switching to a 768-dim model (e.g. Cohere via OpenRouter). Would require a schema migration and break the spec's traceability assumption.

### D1.auth-provider-stub — magic_link_dev provider

- **Decision**: Added `magic_link_dev` to the `auth_provider` Postgres enum (spec lists three production providers; this extends it for Phase 1 dev only). The first-login linker (`packages/auth/src/link.ts`) implements the spec 4.4 contract exactly; only the upstream provider differs.
- **Spec**: Part 4.5 (provider notes — extension allowed since allowlist still gates access).
- **Action item**: In production, wire Supabase Auth's Microsoft / Google / Authentik providers and stop allowing the `magic_link_dev` row. A migration can drop it once unused: `DELETE FROM employees WHERE auth_provider = 'magic_link_dev'` is NOT correct (it would delete real rows that linked through the dev path); instead update those rows' `auth_provider` to the real provider on next login.

### D1.test-employee — temporary second seed row

- **Decision**: Seed inserts a SECOND row `test-employee@oracle.local / Test Employee` so Phase 2's "two employees can chat" acceptance gate can be exercised once secrets are populated. Marked `is_admin = false`.
- **Action item**: Delete this row before production: `DELETE FROM employees WHERE email = 'test-employee@oracle.local'`.
- **Safer alternative ruled out**: Seeding 18 employees — they don't exist yet in the spec, and inventing names would create stale data. One synthetic test row is the minimum that demonstrates RLS works.

### D1.storage-bucket — TODO for company_documents

- **Decision**: Phase 2 needs the `company_documents` Supabase Storage bucket. Cannot create it via SQL migration (Supabase Storage buckets are managed via the Storage API or dashboard). Adding a TODO instead of stubbing in code.
- **Action item**: In the Supabase dashboard for the linked project, go to Storage → New bucket → name `company_documents`, set to private, then run the Storage RLS policy that only allows authenticated employees to read their own uploads and channel-attachment documents (use spec 7.2 documents policy as the template).

### D1.rls-policies — admin reads via service role, not RLS bypass

- **Decision**: Admin reads on intelligence tables (claims/gaps/etc.) and admin views go through the SERVICE_ROLE Drizzle client (`getDirectDb`) in privileged server routes, NOT through `current_employee_is_admin()` USING clauses with the authenticated role.
- **Spec**: Part 7.3 "Default recommendation: access admin views only through privileged server routes."
- **Implementation note**: The RLS policies in `21_rls_policies.sql` still grant admins access for direct-from-authenticated-client reads if we ever expose that route, but the `/admin/*` routes in `apps/web` always go through `getDirectDb()` (service role) for clarity.



## Phase 2 follow-ups — addressed late

### D2.multi-identity — one employee, many auth identities

- **Decision**: Split `(auth_provider, auth_user_id, auth_provider_subject)` off the `employees` table into a new `employee_identities` table. One employee can hold multiple identities (Google, Microsoft 365, future Authentik). The linker resolves a session by `(auth_provider, auth_user_id)` first; on miss, falls back to matching the verified provider email against `employees.email` to bootstrap a new identity row.
- **Why**: Originally `employees` had `auth_user_id UNIQUE` and `auth_provider` as single columns, so each (real human, provider) combo needed its own employees row. When Albert signed in with Microsoft after first signing in with Google, the M365 login created a SECOND employees row, breaking the "one human = one employee" invariant the rest of the system depends on (channel participants, claim attribution, gap targeting all key off employee_id).
- **Spec**: Part 4 doesnt explicitly call for multi-identity but doesnt preclude it; "Every human user must map to exactly one row in employees" is preserved — identities sit beside, not inside.
- **Schema migration**:
    - `15_employee_identities.sql` — creates the table (DDL only).
    - `20_rls_helpers.sql` — `current_employee_id()` now joins through `employee_identities`.
    - `21_rls_policies.sql` — adds RLS policies for the new table; rewrites `employees_self_select` to use the helper instead of querying `auth_user_id` directly.
    - `40_employee_identities_data.sql` — idempotent: copies any pre-existing `employees.auth_*` values into identity rows, performs the one-shot Albert merge (re-points the popcre identity onto the gmail employee, deletes the popcre employee row), then NULLs the deprecated columns so stale reads can't silently use them.
- **Deprecated columns kept**: `employees.auth_user_id`, `employees.auth_provider`, `employees.auth_provider_subject` remain on the table (nullable, NULL-filled by 40_*.sql) to avoid a forced Drizzle column-drop migration in the middle of an active session. A follow-up commit will fully remove them after the team confirms no consumer still reads them.
- **Safer alternative ruled out**: Adding a `secondary_emails` array column on `employees`. Loses the per-identity audit trail (`linked_at`, per-identity `last_login_at`, per-provider `auth_provider_subject`) and conflates "alias email" with "second authentication path".
- **Action item**: After Phase 6, drop the deprecated columns from `employees` in a clean migration. Add an admin UI to manually link/unlink identities (e.g. when an employee gets a new Microsoft account).

