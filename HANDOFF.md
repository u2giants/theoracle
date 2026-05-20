# HANDOFF — The Oracle

Live in-flight state. A new contributor (human or AI) should be able to read this and pick up exactly where the previous session left off — no need to scrape conversation history.

**Snapshot date:** 2026-05-21
**Latest meaningful commit on `main`:** the doc-update commit that introduces this file.
**Repo:** https://github.com/u2giants/theoracle (**PUBLIC** — never commit secrets)
**Local checkout:** `D:\repos\oracle` on Windows 11, NTFS volume

---

## TL;DR

Phases 1–3 are coded; **Phase 1 is fully wet-tested**. Phase 2 needs a second real loginable employee to test cross-channel RLS. Phase 3 is ready for a one-shot smoke test (`@oracle ...` in a channel). Phases 4–6 are scaffolds with spec workflows as comments.

There are no blockers right now — Google OAuth + Microsoft 365 SSO are live, magic-link via Brevo works as a fallback, the database is fully migrated with the multi-identity refactor applied, and the dev server runs cleanly on `pnpm --filter @oracle/web dev`.

The next concrete action is one of:
1. **Wet-test Phase 3** — post `@oracle …` in a channel, confirm an assistant message appears and `model_runs` gets a row.
2. **Wet-test Phase 2 RLS** — requires fixing the `test-employee@oracle.local` mailbox first.
3. **Implement Phase 4** — claim extraction worker (see `apps/workers/src/trigger/claim-extraction.ts` for the scaffold).

---

## Why each phase is where it is

### Done

- **Phase 0 — Bootstrap.** Repo init, `.gitignore`, Vercel link, `.env.local` populated from Vercel via `npx vercel@latest env pull`.
- **Phase 1 — Foundation.** Drizzle schema, raw SQL (CHECK constraint, RLS helpers, RLS policies, admin views), seed (settings + admin + test-employee), first-login linker (now multi-identity), `/auth/callback`, `/auth/signout`, `/denied`. **Wet-tested end-to-end**: Albert can sign in via Google as `u2giants@gmail.com` or Microsoft 365 as `albert@popcre.com` — both land on `/admin` as the same employee row. Non-allowlisted emails are denied.
- **Multi-identity refactor (DECISIONS.md D2.multi-identity).** New `employee_identities` table. The linker resolves a session by `(auth_provider, auth_user_id)` first; on miss it bootstraps by matching either `employees.email` or any existing `employee_identities.email`. The deprecated `auth_user_id` / `auth_provider` / `auth_provider_subject` columns on `employees` are kept nullable for a transitional period and are NULL-filled. **Wet-tested** with both Google and M365 on Albert's single employee row.
- **Logout flow.** POST `/auth/signout` route + `<form action="/auth/signout">` button in both `admin/layout.tsx` and `channels/layout.tsx`.
- **Brevo SMTP integration.** Magic-link emails go through Brevo (Supabase Dashboard → Authentication → SMTP Settings). Supabase's built-in SMTP is rate-limited to ~3-4 emails per hour per project; Brevo's free tier is 300/day.
- **Next.js 16 upgrade.** Bumped from 15.1.4 (CVE-2025-66478) to 16.2.6. `next.config.ts` updated for Next 16's `serverExternalPackages` location and removal of the `eslint` config block.
- **Docs.** README, AGENTS, CLAUDE, DECISIONS, docs/architecture, docs/development, docs/configuration, docs/deployment, and `packages/db/migrations/sql/README.md` are all current as of this snapshot.

### Partially done

- **Phase 2 — Realtime + admin dashboard.** Code is complete (chat UI, channels sidebar, document upload component, Supabase Realtime subscriptions, admin employees tab with identity-provider list). **NOT wet-tested** because the seeded `test-employee@oracle.local` is not a real mailbox — there's only one signable account in the system right now. To unblock: either update `test-employee@oracle.local` to a real email (Gmail `+`-alias works: `u2giants+test@gmail.com`), or seed a second real employee.

- **Phase 3 — Oracle chat route.** Code complete: `POST /api/chat` builds the retrieval bundle (recent N messages, employee profile, top open gaps, top vector-similar approved claims) and calls OpenRouter via the Vercel AI SDK with the spec Part 10 prompt + two tools (`search_company_knowledge`, `check_open_gaps`). **Not yet wet-tested** — no one has posted `@oracle` in a channel in the live UI yet.

### Not started

- **Phase 4 — Trigger.dev workers.** Scaffolds exist in `apps/workers/src/trigger/`:
    - `claim-extraction.ts` — picks pending messages, calls extraction LLM, inserts `claims`/`claim_domains`/`claim_evidence`, marks messages complete/failed/skipped.
    - `document-ingestion.ts` — chunks uploaded files, embeds, extracts claims from chunks.
    - `contradiction-watcher.ts` — vector retrieval against approved claims on new messages; creates `contradictions` rows; sometimes a gap; rarely a live interjection.
    - `brain-synthesis.ts` — per-section synthesis with the structured-output validator from spec 9.8.
    - Each file has the full spec workflow as a JSDoc comment. None of them call a real LLM yet.

- **Phase 5 — Admin review dashboards.** Placeholder pages exist under `apps/web/app/admin/{claims,gaps,contradictions,brain}/page.tsx`. They render "Phase 5 — pending" until built. The data they will consume is documented in `packages/db/migrations/sql/30_admin_views.sql`.

- **Phase 6 — Interjection engine.** Empty module at `packages/oracle-engines/src/interjection.ts` with the spec 5.1 rules captured as JSDoc. Implementation requires Phase 4 (claims must exist) and at least one wet-tested chat channel.

---

## Recent in-flight decisions (this session)

- **Go with Path A** for the multi-identity problem (proper schema refactor) rather than parking it. Rationale: doing it tired is how bugs are introduced, but the existing identity model was actively wrong (two Albert rows), and the rest of the system depends on `employee_id` referential integrity. Documented in DECISIONS.md D2.
- **Keep the deprecated `auth_*` columns on `employees`** (nullable, NULL-filled) instead of dropping them in the same commit as the schema change. A clean follow-up commit will drop them after a soak period. Rationale: avoid a forced Drizzle column-drop migration in the middle of an active session where consumers might still hold references.
- **Use Gmail `+`-alias to provision a second test employee** (recommendation, not yet executed). Rationale: a real mailbox is needed for any real Phase 2 RLS test, and a `+`-alias is the lowest-friction way to get one without provisioning a second Google account.
- **Microsoft 365 SSO scope must include `email` explicitly.** Documented in DECISIONS.md / AGENTS.md §11 — Entra accounts without an Exchange mailbox return empty `mail` from Microsoft Graph; the `email` OIDC scope forces an email claim into the ID token.

## Dead ends / things we tried that didn't work

- **`node-linker=hoisted` in `.npmrc`.** Doesn't fix workspace symlink failures on Windows — only hoists external deps, leaves the `@oracle/*` workspace packages requiring symlinks. Removed from the repo.
- **Setting Vercel env vars on the Development environment for Sensitive-marked secrets.** Vercel refuses. Either convert to Encrypted type, or paste into `.env.local` manually from source dashboards.
- **The `db.<ref>.supabase.co` direct Postgres hostname.** IPv6-only on new Supabase projects — fails with `getaddrinfo ENOENT` on IPv4 networks. Switched to the pooler URLs (`aws-0-<region>.pooler.supabase.com`). Both `DATABASE_URL` and `DIRECT_URL` must use the pooler form with the "Use IPv4 connection (Shared Pooler)" toggle ON in the Supabase dashboard.
- **Supabase's built-in magic-link SMTP.** Rate-limited to ~3-4 emails per hour per project regardless of paid tier. Replaced with Brevo.
- **Reading `.env.local` from each workspace's CWD.** Migration runner, seed, and `apps/web` all explicitly load `.env.local` from the monorepo root now via `dotenv.config({ path: resolve(__dirname, '..', '..', '.env.local') })`. Trusting framework defaults wasted >an hour during initial setup.
- **The Windows pnpm install saga** — initial repo dir was on an exFAT-formatted drive. exFAT doesn't support symlinks, so `pnpm install` failed with cryptic `ENOENT` errors that looked like permission/AV issues. The real fix was reformatting the drive to NTFS. Recovery recipe in `docs/development.md` covers the post-NTFS edge cases.

---

## Open items the next contributor will hit

Pulled from `AGENTS.md` §15. Ranked roughly by friction-cost-to-unblock.

1. **No second loginable employee** — blocks Phase 2 wet-test. Fix by `UPDATE employees SET email = '<your-gmail+test>@gmail.com' WHERE email = 'test-employee@oracle.local';` then signing in once via Google.
2. **No CI** — typecheck/build only run locally. Adding `.github/workflows/pr-check.yml` is in pending work.
3. **Vector indexes (`99_vector_indexes.sql`) are opt-in** — fine while there's no real embedding data, but the retrieval path in `packages/ai/src/retrieval.ts` will fall back to slow sequential scans until they're enabled. Run with `ORACLE_RUN_VECTOR_INDEXES=1 pnpm db:migrate` when ready.
4. **Storage bucket `company_documents`** — must exist in Supabase. If it isn't there, create it in the Supabase Dashboard → Storage → New bucket → private. (Confirmed created during this session, but if a future contributor sets up a new Supabase project, this is the first thing they'll need.)
5. **Vercel token rotation** — the token pasted into the overnight setup transcript is still valid. Rotate at https://vercel.com/account/tokens.
6. **Authentik OIDC integration** — required by the spec, deferred. Not blocking anything until an internal-only employee shows up.

---

## Risks and unknowns

- The Phase 3 chat route has never actually called OpenRouter end-to-end against the live channel infrastructure. The retrieval path has not been tested with real claims because the claim extraction worker hasn't run. First wet-test may surface integration issues we haven't anticipated.
- The deprecated `auth_user_id` columns on `employees` are still in the schema as nullable fields. Any new code that reads them will get `null` and may silently do the wrong thing. AGENTS.md §11 calls this out, but it's a footgun until those columns are dropped.
- The Trigger.dev project is configured in Vercel env (`TRIGGER_SECRET_KEY`) but **no tasks have been deployed**. Deployment requires `pnpm --filter @oracle/workers deploy` which we haven't run.
- We've never deployed to the Vercel production URL. The web app is configured for auto-deploy on push to `main`, but nobody has loaded the production URL to verify. Worst case, an env var is set differently on Production vs the local-dev shape and the deployed app fails fast.

---

## Credentials / accounts (where things live)

| Item | Where | Notes |
|---|---|---|
| GitHub | `u2giants/theoracle` (PUBLIC) | `gh` CLI authed locally via SSH |
| Vercel project | `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | Web app auto-deploys from `main` |
| Supabase project | URL in Vercel env (`NEXT_PUBLIC_SUPABASE_URL`) | Database/Auth/Storage/Realtime |
| Supabase Storage bucket | `company_documents` | Private |
| Brevo (SMTP) | Account on file | Configured in Supabase → Authentication → SMTP Settings |
| Google OAuth client | Google Cloud Console (Albert's account) | Authorized redirect URI: `https://<supabase>.supabase.co/auth/v1/callback` |
| Microsoft Entra app registration | popcre tenant | Single-tenant only; `email` Graph permission with admin consent |
| Trigger.dev project | Secret in Vercel env (`TRIGGER_SECRET_KEY`) | Workers — not yet deployed |
| OpenRouter | Key in Vercel env (`OPENROUTER_API_KEY`) | Default models in `settings` table |
| OpenAI | Key in Vercel env (`OPENAI_API_KEY`) | Embeddings only |
| Admin employee | `u2giants@gmail.com` / Albert H. / Lead Architect / Executive / `is_admin=true` | Linked to Google + Microsoft identities |
| Test employee (for RLS gate) | `test-employee@oracle.local` | **Not a real mailbox.** Replace with a real address before testing Phase 2 RLS. |

---

## Resume — what to do next

```bash
# (only if cloning fresh on a new machine)
git clone git@github.com:u2giants/theoracle.git oracle
cd oracle
pnpm install
npx vercel@latest link --project prj_rP6Jlima7iK1paffEPhLqxlswGsC --yes
npx vercel@latest env pull .env.local --environment=development --yes
pnpm db:migrate

# Always
pnpm --filter @oracle/web dev
```

Then pick one of:

- **Wet-test Phase 3 (smallest scope, biggest signal):** in any channel where you're a participant, post `@oracle what do you know about our licensing process?`. An assistant message should arrive within a few seconds. Verify a `model_runs` row was inserted via `SELECT * FROM model_runs ORDER BY created_at DESC LIMIT 1`.
- **Wet-test Phase 2 RLS:** update `test-employee@oracle.local` to a real Gmail `+`-alias, sign in once to provision its identity, then exercise the cross-channel isolation tests in `docs/development.md` → "Verifying Phase acceptance gates locally".
- **Begin Phase 4:** open `apps/workers/src/trigger/claim-extraction.ts` and start replacing the JSDoc spec workflow with real code. Use `packages/ai/src/openrouter.ts` for the model call and `packages/ai/src/embeddings.ts` for embeddings. Every job must write a row to `job_runs`; every LLM call must write a row to `model_runs`. Spec Part 9.4 for the precise auto-approval triage rules.

---

## Resume a Claude Code session from a fresh terminal

```
I'm continuing work on The Oracle. Read HANDOFF.md, then AGENTS.md, then DECISIONS.md, then oracle_master_spec.md. Phase 1 is wet-tested; Phases 4–6 are scaffolds. My next move is [wet-test Phase 3 / wet-test Phase 2 RLS / start Phase 4 / something else]. Walk me through it.
```

Delete this file once the work it describes is complete — when Phases 4–6 are landed and all the pending items in AGENTS.md §15 are either done or migrated to a real backlog elsewhere.
