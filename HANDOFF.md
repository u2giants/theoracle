# HANDOFF — The Oracle

Live in-flight state. A new contributor (human or AI) should be able to read this top to bottom and pick up exactly where the previous session left off — no need to scrape conversation history.

**Snapshot date:** 2026-05-21
**Latest commit on `main`:** `42a04e5` — docs: document the Vercel monorepo + production-tsc gotchas
**Latest successful Vercel production deploy:** `theoracle-7c5ryvwxm-popcre.vercel.app` (commit `c8fca10`)
**Uncommitted (this session):** `.github/workflows/pr-check.yml` + AGENTS.md / docs/deployment.md / HANDOFF.md sync — adds the `pnpm --filter @oracle/web build` CI gate on PRs and pushes to `main`. Verified locally: build succeeds with placeholder env vars (all auth-gated pages are dynamic).
**Repo:** https://github.com/u2giants/theoracle (**PUBLIC** — never commit secrets)
**Local checkout:** `D:\repos\oracle` on Windows 11, NTFS volume
**Active branch:** `main`

---

## TL;DR

- The project is a **TypeScript pnpm + Turborepo monorepo** that implements "The Oracle" — an AI knowledge graph for POP Creations / Spruce Line (see `oracle_master_spec.md` for the product vision).
- **Phases 1–3 are code-complete**. Phase 1 is **fully wet-tested**. Phase 2 has UI built but RLS hasn't been wet-tested. Phase 3 (Oracle chat route) hasn't been wet-tested yet either.
- **Phases 4–6 are scaffolds only** — files exist with the spec workflow as JSDoc comments. Nothing actually calls an LLM yet.
- **No active blockers.** The dev server runs cleanly. Google OAuth + Microsoft 365 SSO are live. Brevo SMTP handles magic-link email delivery. The multi-identity refactor (`employee_identities` table) is in and verified.
- The natural next step is **one of**: wet-test Phase 3 (5 min), wet-test Phase 2 RLS (needs a second mailbox first), or start implementing Phase 4 (Trigger.dev workers — the longest-running, highest-value work).

---

## Read this in order

1. **`HANDOFF.md` (this file)** — current state, what's done, what's next.
2. **`AGENTS.md`** — the developer guide. §11 "Idiosyncratic decisions" is the most important section; do not undo those without reading the cited spec section.
3. **`DECISIONS.md`** — assumption log with citations. D2.multi-identity is the biggest entry from this session.
4. **`oracle_master_spec.md`** — authoritative product spec. Large but every paragraph is load-bearing.
5. **`docs/architecture.md`** — system diagram + data-flow + identity-model.

If you only have time for two: read `HANDOFF.md` and `AGENTS.md`.

---

## What this project is — one paragraph

The Oracle is an AI-powered Enterprise Knowledge Graph for **POP Creations / Spruce Line** — a Brooklyn-based home decor company (~1,500 SKUs, ~18 employees across US/China/Brazil/Colombia, sells into Burlington, TJX, Ross, Hobby Lobby, Walmart, etc.). The company's actual operating reality lives in employees' heads ("dark matter"): informal rules, undocumented workarounds, contradictions in how work moves between departments. The Oracle observes conversations, ingests documents, interviews employees, extracts evidence-backed *claims* about how the business actually works, and synthesizes a versioned "Brain" the lead architect (Albert) can query — every answer backed by traceable evidence (specific messages, specific document chunks, specific employees on specific dates). **It is not** a project manager, task tracker, or ticket system. If any code in this repo looks like that, it is a bug. See `oracle_master_spec.md` Part 1.3.

---

## Current dev workflow

```bash
# Start dev server (web only — workers aren't wired yet)
pnpm --filter @oracle/web dev

# Run migrations (idempotent — runs seed at the end too)
pnpm db:migrate

# After changing schema.ts
pnpm db:generate    # creates a new Drizzle migration file
pnpm db:migrate     # applies it

# Inspect identity state
pnpm --filter @oracle/db exec tsx src/verify-identities.ts
pnpm --filter @oracle/db exec tsx src/inspect-auth-users.ts

# Lint / typecheck / build
pnpm typecheck
pnpm build
pnpm lint

# Pull fresh env from Vercel
npx vercel@latest env pull .env.local --environment=development --yes
```

The migrations apply to the **live Supabase project** referenced by `DIRECT_URL` — there is no staging DB. Be deliberate.

---

## Commit history of this session

| Commit | What it did |
|---|---|
| `10d2b77` | Bootstrap — `.gitignore`, `.env.example`, `DECISIONS.md` skeleton, Vercel link. |
| `d832f5f` | **Phase 1** — Drizzle schema (the whole thing), raw SQL migrations (extensions, constraints, RLS helpers, RLS policies, admin views, vector indexes), magic-link auth, `/auth/callback`, `/denied`, admin seed. |
| `9efd3e1` | **Phase 2** — channels UI, chat composer, document upload, Supabase Realtime, admin dashboard skeleton. |
| `eec3d58` | **Phase 3** — `POST /api/chat`, OpenRouter via Vercel AI SDK, two tools (`search_company_knowledge`, `check_open_gaps`), Part 10 system prompt verbatim. |
| `4940327` | Phase 4–6 scaffolds — Trigger.dev task files with workflow as JSDoc, admin tab placeholders, empty interjection engine. |
| `4744ca3` | Initial AGENTS / CLAUDE / docs / `.claudeignore` / `.cursorignore`. |
| `0bcc3dc` | Original HANDOFF (cross-machine framing — superseded by this rewrite). |
| `37893b5` | `pnpm-lock.yaml` committed after clean install on NTFS. |
| `d676494` | `.env.local` loading + Windows direct-run check in `migrate.ts` / `seed.ts`. |
| `16fe0f4` | Migrate runner treats missing `_journal.json` as "no generated migrations". |
| `f921041` | Generated Drizzle migrations + lockfile after first successful migrate. |
| `4527430` | Workers `dev` script switched to `npx trigger.dev@latest` (no global install). |
| `382190e` | `apps/web/next.config.ts` loads `.env.local` from monorepo root. |
| `7412a4f` | **Google + Microsoft 365 SSO buttons** in login form (callback already handled them). |
| `53249aa` | Unwrapped `redirect()` from try/catch; added OAuth-callback error logging. |
| `592d6c9` | OAuth `email` scope added (fixes Microsoft "Error getting user email"). |
| `fc7d362` | **Multi-identity refactor** — new `employee_identities` table, linker rewrite, RLS updates, idempotent data migration + Albert merge. |
| `7cb48de` | Silence Next 16 config warnings (`serverExternalPackages`, eslint block removal). |
| `ff08333` | **Logout button** + comprehensive doc refresh. |
| `5cc4bc7` | HANDOFF.md expanded into self-contained session-resume guide. |
| `d27f1fd` | **Unblock Vercel production builds** — fix `OracleDb` vs `Db` typecheck error in retrieval helpers + implicit-any in `@supabase/ssr` cookie adapter. Production tsc had been failing every deploy for ~an hour while dev was green. |
| `c8fca10` | **`vercel.json`** — point Vercel at `apps/web/.next` so the monorepo finalize step finds the build output. Production deploy went green on this commit. |
| `42a04e5` | Docs: capture the Vercel monorepo + production-tsc gotchas in `docs/deployment.md`, AGENTS.md §11, `docs/development.md`. |

---

## Phase status

| Phase | Status | Wet-tested? |
|---|---|---|
| 0 — Bootstrap | done | n/a |
| 1 — Foundation (schema, RLS, auth, seed) | done | **YES** — both Google + M365 SSO end-to-end; denial flow with non-allowlisted email. |
| 2 — Realtime chat + document upload + admin dashboard | code complete | **No.** Needs a second loginable employee. |
| 3 — Oracle chat route (`POST /api/chat`) | code complete | **No.** Never posted `@oracle` in a live channel yet. |
| 4 — Trigger.dev workers (claim extraction, ingestion, contradiction watcher, brain synthesis) | **scaffolds only** | n/a |
| 5 — Admin review dashboards (claims, gaps, contradictions, brain) | placeholders | n/a |
| 6 — Interjection engine | empty module with JSDoc | n/a |
| Docs (AGENTS / DECISIONS / docs/* / HANDOFF / migrations README) | current as of this snapshot | n/a |

---

## The architectural mental model

### Request flow (from a user click in the browser)

```
Browser
   │  cookie: sb-<project>-auth-token  ←  set by Supabase OAuth/magic-link callback
   ↓
apps/web/lib/supabase/server.ts → createServerClient (anon key + cookies)
   │
   ↓
apps/web/lib/auth-guard.ts → getCurrentEmployee()
   │  joins employees ⨝ employee_identities on auth.uid()
   ↓
Server Component / Route Handler
   │  for DB writes that need to bypass RLS:
   │     packages/db/src/client.ts → getDirectDb() — postgres-js with SERVICE_ROLE
   │  for queries that should respect RLS:
   │     the Supabase client above (anon key, RLS enforced)
   ↓
Postgres
   │  every privileged read goes through service_role
   │  every employee-scoped read goes through the helper functions
   │  in 20_rls_helpers.sql which read auth.uid() ⨝ employee_identities
   ↓
Response (Server Component HTML, or JSON from a route handler)
```

### Identity model — read this carefully

**One human → one `employees` row → many `employee_identities` rows.**

- `employees.email` is the **primary contact / display email**. It is also the bootstrap target for first-login linking — when a verified provider email arrives at the callback and no `employee_identities` row matches, the linker tries to find an `employees` row by this email.
- `employee_identities.(auth_provider, auth_user_id)` is the **authoritative identity**. Once linked, all subsequent logins resolve via this tuple — email matching is only a fallback.
- `auth.uid()` returns the **Supabase auth.users.id** (a uuid). That maps to **`employee_identities.auth_user_id`** in our schema.
- The RLS helper `public.current_employee_id()` does the join — it never reads `employees.auth_user_id` (those columns are deprecated; see below).
- Supabase auth.users deduplicates by email — if a single email signs in via magic-link first and then Google, Supabase returns the **same** `auth.users.id` and adds Google to its internal `providers` array. So one of Albert's `employee_identities` rows can correspond to two upstream auth providers (magic-link + Google) sharing one `auth_user_id`.
- **The deprecated columns** `employees.auth_user_id`, `employees.auth_provider`, `employees.auth_provider_subject` are still in the schema but **nullable and NULL-filled** by `40_employee_identities_data.sql`. They will be dropped in a follow-up migration after a soak period. **Do not read or write to them in new code.**

### RLS

- `service_role` (the connection from `getDirectDb()`) **bypasses RLS** entirely. Admin-only routes use it.
- `authenticated` (the SSR client with the user's cookie + anon key) is subject to all the policies in `21_rls_policies.sql`.
- Two helper functions in `20_rls_helpers.sql` (`current_employee_id`, `current_employee_is_admin`) are `SECURITY DEFINER` so they can read `employees` + `employee_identities` even while RLS is enabled on those tables. Both are STABLE so the planner calls them at most once per statement.
- The intelligence tables (`claims`, `claim_evidence`, `brain_sections`, `brain_section_versions`, `section_claims`, `gaps`, `contradictions`, `model_runs`, `job_runs`, `oracle_interventions`) are **admin-only via RLS**, but the application reads them through `getDirectDb()` so admin reads never actually hit the RLS path. Per `DECISIONS.md` D1.rls-policies: the policies are there for defense in depth.

### Retrieval bundle (Phase 3 — `POST /api/chat`)

When `@oracle` is mentioned in a channel, the route in `apps/web/app/api/chat/route.ts` builds this bundle (spec 9.1 constraint: never load the full Brain):

- `recentMessages` — last N messages from the channel (default 30). Source: `packages/ai/src/retrieval.ts` → `getRecentMessages`.
- `employeeProfile` — the requester's `employees` row.
- `openGaps` — top open `gaps` rows filtered to this employee / their department / this channel context (default 5). Source: `getRelevantOpenGaps` and `getOpenGapsForChannel`.
- `relevantClaims` — top semantically-similar approved `claims` rows via pgvector cosine (default 5). Source: `searchApprovedClaims`.
- **Not loaded:** any `brain_sections` content. The retrieval is per-turn and lean.

The route then calls `generateText` from the Vercel AI SDK with the spec Part 10 system prompt + two tools (`search_company_knowledge`, `check_open_gaps`), persists the assistant response as a message with `role='assistant'` (via service-role so RLS doesn't block), and writes a `model_runs` row with cost/latency/tokens.

### Document ingestion flow (Phase 4 — scaffold only)

```
upload → Supabase Storage bucket "company_documents"
       → documents row (status='pending_processing')
       → message_attachments row
       ↓
       (Trigger.dev cron, every N minutes)
       ↓
apps/workers/src/trigger/document-ingestion.ts
       ├─ chunk by page/sheet/row, store in document_chunks
       ├─ embed each chunk via packages/ai/src/embeddings.ts (1536-dim)
       └─ call extraction workflow (claim-extraction.ts) over the chunks
       ↓
claims + claim_domains + claim_evidence rows
       (claim_evidence.source_type='document_chunk',
        source_document_chunk_id = the chunk that yielded it)
```

---

## File-by-file map

Each entry is "where does the logic for X live."

### Auth & Identity

| Concern | File |
|---|---|
| Magic-link / OAuth callback (exchange code for session, run linker, redirect) | `apps/web/app/auth/callback/route.ts` |
| Logout (POST → clear cookies → redirect) | `apps/web/app/auth/signout/route.ts` |
| Linker — resolve Supabase session to employee row, create identity rows | `packages/auth/src/link.ts` |
| Provider → enum mapping (`google`/`azure`/`authentik`/`magic_link_dev`) | `packages/auth/src/server.ts` → `resolveAuthProvider` |
| Login UI (Google + Microsoft buttons + magic-link form) | `apps/web/app/_components/login-form.tsx` |
| Logout button | `apps/web/app/_components/logout-button.tsx` |
| Server-side employee resolution helpers (`getCurrentEmployee`, `requireEmployee`, `requireAdmin`) | `apps/web/lib/auth-guard.ts` |
| Server-side Supabase clients (SSR + service role) | `apps/web/lib/supabase/server.ts`, `packages/auth/src/server.ts` |
| Browser Supabase client | `packages/auth/src/client.ts` |
| Denied page (off-allowlist landing) | `apps/web/app/denied/page.tsx` |
| Identity tables in schema | `packages/db/src/schema.ts` → `employees`, `employeeIdentities` |
| Identity DDL | `packages/db/migrations/sql/15_employee_identities.sql` |
| RLS helpers (used by all policies) | `packages/db/migrations/sql/20_rls_helpers.sql` |
| RLS policies (per table) | `packages/db/migrations/sql/21_rls_policies.sql` |

### Database

| Concern | File |
|---|---|
| Drizzle schema (all 25+ tables, all enums) | `packages/db/src/schema.ts` |
| Auto-generated Drizzle migrations | `packages/db/migrations/0NNN_*.sql` (do not hand-edit) |
| Hand-written SQL (extensions, constraints, RLS, views, data migrations) | `packages/db/migrations/sql/` (see README in that folder) |
| Migration runner | `packages/db/src/migrate.ts` |
| Seed (settings + admin + test-employee) | `packages/db/src/seed.ts` |
| Drizzle clients (`getDirectDb` for service role, transaction-pool aware) | `packages/db/src/client.ts` |
| drizzle-kit config | `packages/db/drizzle.config.ts` |
| Inspection scripts (debug-only) | `packages/db/src/verify-identities.ts`, `packages/db/src/inspect-auth-users.ts` |

### AI / Chat

| Concern | File |
|---|---|
| Spec Part 10 system prompt (verbatim) | `packages/ai/src/prompts/oracle-system.ts` |
| OpenRouter provider wrapper | `packages/ai/src/openrouter.ts` |
| Embeddings (OpenAI `text-embedding-3-small`, 1536-dim, with zero-vector fallback) | `packages/ai/src/embeddings.ts` |
| Retrieval bundle helpers | `packages/ai/src/retrieval.ts` (`getRecentMessages`, `getRelevantOpenGaps`, `searchApprovedClaims`, `getOpenGapsForChannel`, `getBrainSectionSnippets`) |
| Oracle chat route | `apps/web/app/api/chat/route.ts` |

### Chat UI

| Concern | File |
|---|---|
| Channels sidebar layout | `apps/web/app/channels/layout.tsx` |
| Channel page (server-rendered initial messages) | `apps/web/app/channels/[channelId]/page.tsx` |
| Live chat client component (Realtime, optimistic insert, `@oracle` detection) | `apps/web/app/channels/[channelId]/_components/channel-chat.tsx` |
| Document upload component | `apps/web/app/channels/[channelId]/_components/document-upload.tsx` (or equivalent) |
| Admin dashboard layout (header + nav tabs + logout) | `apps/web/app/admin/layout.tsx` |
| Admin employees tab (shows identity provider list per employee) | `apps/web/app/admin/page.tsx` |
| Admin placeholder tabs (Phase 5) | `apps/web/app/admin/{channels,messages,documents,claims,gaps,contradictions,brain}/page.tsx` |

### Workers (Phase 4 scaffolds)

| Concern | File |
|---|---|
| Trigger.dev v3 config | `apps/workers/trigger.config.ts` |
| Claim extraction task scaffold | `apps/workers/src/trigger/claim-extraction.ts` |
| Document ingestion task scaffold | `apps/workers/src/trigger/document-ingestion.ts` |
| Contradiction watcher task scaffold | `apps/workers/src/trigger/contradiction-watcher.ts` |
| Brain synthesis task scaffold | `apps/workers/src/trigger/brain-synthesis.ts` |

### Engines (Phase 6 scaffolds)

| Concern | File |
|---|---|
| Interjection engine (lull / cooldown / contradiction-live-interject rules as JSDoc) | `packages/oracle-engines/src/interjection.ts` |

---

## Current database state

Verified by `pnpm --filter @oracle/db exec tsx src/verify-identities.ts` at the end of this session:

**`employees` table** (2 rows):

| email | name | role | department | is_admin | deprecated auth columns |
|---|---|---|---|---|---|
| `u2giants@gmail.com` | Albert H. | Lead Architect | Executive | true | all NULL ✓ |
| `test-employee@oracle.local` | Test Employee | Production Coordinator | Production | false | all NULL ✓ |

**`employee_identities` table** (2 rows, both attached to Albert):

| auth_provider | identity_email | auth_user_id | linked_at | last_login_at |
|---|---|---|---|---|
| `google` | `u2giants@gmail.com` | `e0968007-7276-46fb-8abd-25baa108f112` | 2026-05-20 22:56:30 | 2026-05-20 22:56:30 |
| `microsoft` | `albert@popcre.com` | `751efc6f-b030-43cf-9f22-8e82ac389771` | 2026-05-20 23:33:34 | 2026-05-20 23:33:34 |

**Supabase `auth.users`** (out of our schema's control, but for reference):

| email | id | linked providers |
|---|---|---|
| `u2giants@gmail.com` | `e0968007-7276-46fb-8abd-25baa108f112` | `["email", "google"]` |
| `albert@popcre.com` | `751efc6f-b030-43cf-9f22-8e82ac389771` | `["email", "azure"]` |

**Other tables** — `channels`, `channel_participants`, `messages`, `documents`, `document_chunks`, `claims`, `claim_evidence`, `gaps`, `contradictions`, `model_runs`, `job_runs`, `oracle_interventions`, `brain_sections`, `brain_section_versions` — all empty. `settings` is populated with the 8 defaults from spec 6.2.

---

## Decisions made this session (and why)

### Multi-identity refactor (Path A)

When Albert signed in via Microsoft after first signing in via Google, the linker created a **second** `employees` row keyed on `albert@popcre.com`. That violated the "one human = one employee" invariant the rest of the system relies on (channel participants, claim attribution, gap targeting all key off `employee_id`).

Two paths considered:
- **Path A** (chosen): split identities off into a new `employee_identities` table. One employee, many identities. ~45 minutes of work.
- **Path B** (rejected): manual SQL merge for now, document as a known limitation, fix later.

Chose A because the bug was active and the rest of the system depends on referential integrity. The full schema map is in `DECISIONS.md` D2.multi-identity. The deprecated columns on `employees` were left in place (nullable, NULL-filled) rather than dropped in the same commit, to avoid forcing a Drizzle column-drop mid-session — they'll be dropped in a follow-up.

### Keep magic-link auth as a fallback after OAuth went live

When Google and Microsoft 365 went live, the magic-link path could have been removed. We kept it because:
- It works without a configured OAuth provider (useful for future Authentik provisioning).
- Brevo SMTP is already wired and rate-limit-friendly.
- The `auth_provider` enum already has the `magic_link_dev` value.
- The Phase 1 "deny non-allowlisted email" flow is identical regardless of which provider sent the email.

### Brevo SMTP over Supabase's built-in

Supabase's built-in magic-link SMTP is rate-limited to ~3-4 emails per hour per project across all paid tiers. Brevo's free tier (300/day) removes the limit and is configured in 5 minutes (Supabase → Authentication → SMTP Settings).

### Microsoft 365 OAuth requires the `email` scope explicitly

Microsoft Entra accounts without an Exchange mailbox return an empty `mail` field from Microsoft Graph; Supabase reads `mail` first and bails with "Error getting user email from external provider". The login form (`apps/web/app/_components/login-form.tsx`) now sends `scopes: 'openid profile email User.Read'` for Azure. **Removing this scope re-introduces the denial.**

### Use Supabase pooler URLs, never the direct hostname

New Supabase projects expose `db.<ref>.supabase.co` as IPv6-only. Most consumer ISPs and CI environments are IPv4-only and get `getaddrinfo ENOENT`. Switched both `DATABASE_URL` (transaction pooler, port 6543) and `DIRECT_URL` (session pooler, port 5432) to the `aws-0-<region>.pooler.supabase.com` form. The Supabase dashboard has a "Use IPv4 connection (Shared Pooler)" toggle that must be ON to show those URLs.

### `.env.local` lives at the monorepo root; consumers explicitly load it from there

Next.js's default behavior is to read `.env.local` only from the app directory. `packages/db/src/migrate.ts`, `packages/db/src/seed.ts`, and `apps/web/next.config.ts` all explicitly `loadEnv({ path: resolve(repoRoot, '.env.local') })`. One source of truth for secrets across all workspaces.

### Logout via server POST route, not client-side `signOut()`

Client-only `signOut()` leaves SSR-rendered pages thinking the session is still valid for the JWT cache lifetime. The POST form to `/auth/signout` clears cookies server-side via the same `@supabase/ssr` cookie adapter the callback uses. POST also blocks accidental sign-outs from URL prefetchers and link-preview crawlers.

### `redirect()` must not be inside a try/catch

Next.js implements `redirect()` by throwing a special `NEXT_REDIRECT` exception that the framework catches at the request boundary. Wrapping `redirect()` in a try/catch swallows the throw and surfaces the exception to the dev overlay instead of redirecting. Both `apps/web/app/page.tsx` and `apps/web/lib/auth-guard.ts` were refactored to do the DB lookup inside try/catch and the redirect outside.

### `node-linker=hoisted` does NOT fix Windows pnpm install issues

We tried `node-linker=hoisted` in `.npmrc` when the install kept failing. It doesn't help — it only flattens external deps; workspace packages get symlinked regardless. The real root cause was that `D:\` was formatted exFAT, which doesn't support symlinks. Reformatting to NTFS fixed it. The `.npmrc` was removed; `docs/development.md` documents the NTFS-vs-exFAT root cause.

---

## Dead ends / approaches we tried and abandoned

1. **`node-linker=hoisted` in `.npmrc`** — see above.
2. **Setting Sensitive Vercel env vars on the Development environment** — Vercel refuses. Either convert to Encrypted, or paste manually into `.env.local`.
3. **The `db.<ref>.supabase.co` direct Postgres hostname** — IPv6-only, fails on IPv4 networks.
4. **Supabase's built-in SMTP** — too rate-limited for repeated testing.
5. **Trusting Next.js to find `.env.local` automatically in a monorepo** — only finds it in the app's own directory.
6. **`Stop-Process -Force` on `node` broadly** — killed Claude Desktop's MCP servers and any Electron-based IDEs. Always target `pnpm` specifically.
7. **Wrapping `redirect()` in try/catch** — swallows `NEXT_REDIRECT` and breaks the redirect silently.
8. **Pre-checking employee allowlist before sending magic-link** — would leak which emails are approved (enumeration risk). Spec / current behavior is to send the email always and reject at the callback.
9. **A single-row-per-identity layout on `employees`** — created two Albert rows. Replaced by the multi-identity refactor.
10. **`drizzle-kit push` instead of our custom `migrate.ts` runner** — skips the hand-written `migrations/sql/*.sql` files entirely (RLS, constraints, views, data migrations). Don't use it.

---

## Open items

Ranked roughly by friction-cost vs payoff.

### High value, low friction

1. **Wet-test Phase 3** — post `@oracle ...` in a channel and confirm response. ~5 min once a channel exists.
2. **Replace `test-employee@oracle.local` with a real mailbox** — Gmail `+`-alias works: `UPDATE employees SET email = 'u2giants+test@gmail.com' WHERE email = 'test-employee@oracle.local';`. Then sign in once to provision the identity.
3. **Wet-test Phase 2 RLS** — requires #2 first. Recipe below.
4. **Rotate the Vercel token** from the overnight transcript at https://vercel.com/account/tokens.
5. **Drop the deprecated `auth_user_id` / `auth_provider` / `auth_provider_subject` columns** from `employees` once a few days of soak confirm nothing reads them. New migration `42_drop_legacy_auth_columns.sql`.

### Medium value, medium friction

6. ~~Wire CI~~ — **done** in this session (`.github/workflows/pr-check.yml`). Runs `pnpm install && pnpm --filter @oracle/web build` on PRs + pushes to `main`. Verified locally with placeholder env vars; build is clean and all auth-gated routes are dynamic so secrets aren't needed at build time. Still **open**: a migration CI job (`pnpm db:migrate`) gated on manual approval.
8. **Enable HNSW vector indexes** — `ORACLE_RUN_VECTOR_INDEXES=1 pnpm db:migrate` runs `99_vector_indexes.sql`. Worth doing once there's enough embedding data to benefit; until then the planner falls back to seq scan which is fine on small data.

### High value, high friction — the actual work

9. **Implement Phase 4 — Trigger.dev workers.** See the dedicated guide below.
10. **Implement Phase 5 — Admin review dashboards.** Each placeholder under `apps/web/app/admin/*` needs to be built. The data they read is documented in `packages/db/migrations/sql/30_admin_views.sql`.
11. **Implement Phase 6 — Interjection engine.** Depends on Phase 4 (claims must exist) and at least one wet-tested channel.
12. **Wire Authentik OIDC** as a third login provider. Spec requires it for internal-only accounts. Not blocking anything until such an account exists.

---

## Risks and unknowns

- **Phase 3 chat route has never run against the live retrieval path.** It was unit-clean as written but no integration test exists. First wet-test may surface issues with the OpenRouter wrapper, the Zod tool schemas, or the way the assistant message gets inserted (the route writes with service-role; verify the realtime feed picks it up).
- **The deprecated `auth_*` columns on `employees` are still queryable.** Any new code that does `SELECT auth_user_id FROM employees WHERE ...` will get NULL and may silently misbehave. `AGENTS.md` §11 calls this out, but it's a footgun until those columns are dropped.
- **No tasks have been deployed to Trigger.dev** despite the project being configured. Running `pnpm --filter @oracle/workers deploy` for the first time may surface auth/permissions issues we haven't seen.
- **Production Vercel deploy is now green** (deploy `theoracle-7c5ryvwxm-popcre.vercel.app`, commit `c8fca10`). The deployed URL hasn't been browsed yet — first real visit may surface env-var-shape mismatches between Production and the local-dev `.env.local`.
- **Spec compliance for Phase 4 worker output is strict** (spec 9.8 — structured output with `supportingClaimIds`, etc.). The synthesis validator must reject paragraphs that don't map to approved claim IDs. Writing this correctly the first time is non-trivial.

---

## Credentials map (where things live, where to rotate)

| Item | Where | Rotation |
|---|---|---|
| GitHub repo | `u2giants/theoracle` (PUBLIC) | `gh` CLI authed locally via SSH |
| Vercel project | `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | Auto-deploys from `main` |
| Vercel token | https://vercel.com/account/tokens | **Rotate** — one was pasted in overnight transcript |
| Supabase project | URL in Vercel env | API keys: Supabase → Settings → API → Reset |
| Supabase Storage bucket | `company_documents` (private) | Confirmed created |
| Supabase DB password | Used inside `DATABASE_URL` / `DIRECT_URL` | Reset: Supabase → Settings → Database → Reset Database Password (one-time display) |
| Brevo (SMTP) | Account on file | Brevo → SMTP & API → SMTP → revoke + regenerate; update Supabase Auth SMTP Settings |
| Google OAuth client | Google Cloud Console (Albert's account) | Recreate; update Supabase → Authentication → Providers → Google |
| Microsoft Entra app registration | popcre tenant (single-tenant only) | Recreate client secret in Entra; update Supabase → Authentication → Providers → Azure |
| Trigger.dev project | secret in Vercel env (`TRIGGER_SECRET_KEY`) | Workers — not yet deployed |
| OpenRouter | key in Vercel env (`OPENROUTER_API_KEY`) | https://openrouter.ai/keys → revoke + recreate |
| OpenAI | key in Vercel env (`OPENAI_API_KEY`) | Optional — embeddings only. Falls back to zero vector if unset. |

---

## Phase 4 implementation guide

This is the natural next big piece of work. Start here.

### What the scaffolds give you

Each file under `apps/workers/src/trigger/` already has the spec workflow captured as JSDoc. Read each one before starting — the workflow is precise.

### Patterns to follow

- **Every job MUST insert a row into `job_runs`** before doing work and update it on completion. Non-negotiable per spec Part 9.
- **Every LLM call MUST insert a row into `model_runs`** with `model`, `provider='openrouter'` (or `'openai'` for embeddings), `prompt_version`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `success`. Use the OpenRouter wrapper (`packages/ai/src/openrouter.ts`) and embeddings helper (`packages/ai/src/embeddings.ts`).
- **All worker DB writes go through `getDirectDb()`** — workers bypass RLS by design.
- **Use Zod schemas** for the structured output from each LLM call. The synthesis worker's output schema (spec 9.8) is the most elaborate.
- **Exact-quote validation** — when an extraction LLM returns a claim with an `exact_quote`, verify it is a substring of the source message or chunk before inserting. Reject claims with invalid quotes. Spec Part 9.4.
- **Idempotency** — workers can be retried. Use `(source_message_id, claim_summary_hash)` or similar de-dup keys so a retry doesn't double-insert.

### Order to implement

1. **`claim-extraction.ts`** — simplest workflow. Picks `messages WHERE extraction_status='pending' AND role='user'`, calls the LLM in batches, inserts `claims` + `claim_domains` + `claim_evidence` (with `source_type='message'`), marks messages `complete`/`failed`/`skipped`. Triage rules (auto-approve vs `pending_review`) are in spec 9.4.
2. **`document-ingestion.ts`** — picks `documents WHERE status='pending_processing'`, chunks the file (PDF / xlsx / docx via appropriate parsers), embeds chunks (1536-dim), inserts `document_chunks` rows, then calls the same extraction workflow over each chunk (claim_evidence with `source_type='document_chunk'`).
3. **`contradiction-watcher.ts`** — triggered by new user messages. Runs cheap vector retrieval against approved claims; if a similar-but-misaligned claim exists, inserts a `contradictions` row with `status='possible'`. Decides whether to: silently queue, create a `gaps` row, request admin review, or live-interject. **Most decisions should NOT live-interject** — that lives in Phase 6's interjection engine. The watcher just records.
4. **`brain-synthesis.ts`** — most complex. Per-section synthesis with the structured output validator from spec 9.8. Each material paragraph must map to approved claim IDs. Section creation is the two-step transaction from spec 6.7 (insert section with `current_version_id=NULL`, insert version, update section).

### Wiring Trigger.dev

- `apps/workers/trigger.config.ts` reads `TRIGGER_PROJECT_REF` from env. Set this in Vercel + Trigger.dev dashboards once the Trigger.dev project is created.
- First deploy: `pnpm --filter @oracle/workers deploy`. The script invokes `npx trigger.dev@latest deploy`.
- For local development of tasks, use `pnpm --filter @oracle/workers dev` (runs `trigger.dev dev` which tunnels back to the cloud).

### Testing

The spec calls for evaluation gates over real transcripts (spec Part 12), not unit tests. Don't write speculative tests. Once Phase 4 has real workers running, build the gold-standard transcript suite per spec Part 12.

---

## Phase 2 wet-test recipe

Prerequisites: a second loginable employee. Set this up first.

```sql
-- In Supabase SQL Editor:
UPDATE employees
SET email = 'u2giants+test@gmail.com', name = 'Test (Albert alias)'
WHERE email = 'test-employee@oracle.local';
```

Sign in once via Google as `u2giants+test@gmail.com` to provision its identity. Mail arrives in the same inbox as `u2giants@gmail.com`; Supabase Auth treats it as a distinct user.

Now the test itself:

```sql
-- Create a test channel that ONLY the test alias is a member of.
WITH new_channel AS (
  INSERT INTO channels (name, is_group_chat, status)
  VALUES ('rls-test-channel-alias-only', false, 'active')
  RETURNING id
)
INSERT INTO channel_participants (channel_id, employee_id)
SELECT new_channel.id, employees.id
FROM new_channel, employees
WHERE employees.email = 'u2giants+test@gmail.com';
```

Then:

1. Sign in as `u2giants@gmail.com` (admin). Open the channels sidebar. The new channel should **not** appear (admin uses the same user-facing chat UI, gated by `channel_participants` — RLS-enforced).
2. Open `/admin` → Channels tab. The new channel **should** appear (admin reads via service-role).
3. Sign out, sign in as `u2giants+test@gmail.com`. The new channel **should** appear in the sidebar.
4. As the alias, post a message. As admin, sign back in — message should **not** be visible via the user-facing chat (admin isn't a participant); should **be** visible in `/admin/messages`.

If RLS is correctly isolating, all four checks pass.

---

## Phase 3 wet-test recipe

Prerequisites: at least one channel with the admin as a participant.

```sql
WITH new_channel AS (
  INSERT INTO channels (name, is_group_chat, status)
  VALUES ('oracle-smoke-test', false, 'active')
  RETURNING id
)
INSERT INTO channel_participants (channel_id, employee_id)
SELECT new_channel.id, employees.id
FROM new_channel, employees
WHERE employees.email = 'u2giants@gmail.com';
```

Then:

1. Sign in as `u2giants@gmail.com`.
2. Open the new channel from the sidebar.
3. Send: `@oracle what do you know about our licensing process?`
4. Within ~5 seconds, an assistant message should appear (Oracle responding).
5. Verify:
   ```sql
   SELECT id, task_type, model, success, cost_usd, latency_ms, created_at
   FROM model_runs ORDER BY created_at DESC LIMIT 1;
   ```
   Should show one new row with `task_type='oracle_chat'`, `model='anthropic/claude-sonnet-4.6'` (or whatever `settings.default_interview_model` says), `success=true`.

Expected behavior from the Oracle in a cold channel with no prior claims:

- Asks **one** tightly-scoped question (spec Part 10 output constraint).
- Does NOT load a giant brain context (spec 9.1).
- Tone is "curious COO," not "task manager" (spec Part 10 personality).

If the message never arrives, the most likely failure modes are: missing `OPENROUTER_API_KEY`, the AI SDK version mismatch with the OpenRouter provider package, or the assistant insert failing due to RLS (it shouldn't — the route uses service-role — but verify).

---

## Suggested first-move flowchart

```
Are you here to keep building?
│
├── Yes, smallest scope first
│      └── Wet-test Phase 3 (5 min — see recipe above)
│
├── Yes, prove RLS works
│      └── Provision second employee → wet-test Phase 2 RLS
│
├── Yes, biggest piece next
│      └── Phase 4 — start with claim-extraction.ts
│
└── No, just need to fix something specific
       └── Read the relevant section of AGENTS.md §6 (Decision tree) +
           §7 (Task-to-file map). They cover the common modification paths.
```

---

## Verbatim resume prompt for a fresh Claude Code session

> I'm continuing work on The Oracle. Read HANDOFF.md at the repo root first, then AGENTS.md, then DECISIONS.md, then `oracle_master_spec.md`. Phase 1 is fully wet-tested (Google OAuth + Microsoft 365 SSO both land on the same Albert employee row via the multi-identity refactor). Phase 2 and 3 are code-complete but not wet-tested. Phases 4–6 are scaffolds. My next move is [pick: wet-test Phase 3 / wet-test Phase 2 RLS / implement Phase 4 claim-extraction / fix the two pre-existing typecheck errors / something else]. Walk me through it and start executing.

---

## When to delete this file

Delete `HANDOFF.md` once **all** of these are true:

- Phases 4, 5, and 6 are landed.
- The deprecated `auth_user_id` / `auth_provider` / `auth_provider_subject` columns on `employees` are dropped.
- The two pre-existing typecheck errors are fixed and `pnpm typecheck` is green.
- CI is wired (`.github/workflows/pr-check.yml` + migration workflow).
- The remaining items in `AGENTS.md` §15 are either done or migrated to a real backlog elsewhere (GitHub Issues, Linear, etc.).

Until then, **keep this file current** — update it whenever a session ends with material progress or a meaningful change in state. A stale HANDOFF is worse than no HANDOFF.
