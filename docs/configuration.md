# Configuration

Every environment variable, where it comes from, and what fails when it's missing.

## Environment variables

| Variable | Purpose | Source | Required (dev) | Required (prod) | Notes |
|---|---|---|---|---|---|
| `DATABASE_URL` | Supabase Postgres — **Transaction pooler** (port 6543, IPv4) — used by Drizzle for application queries from Vercel Functions | Supabase → Project Settings → Database → Connection string → **Transaction pooler** (toggle "Use IPv4 connection (Shared Pooler)" ON) | yes | yes | When using Drizzle through a transaction pooler, prepared statements must be off. The client in `packages/db/src/client.ts` already handles this. |
| `DIRECT_URL` | Supabase Postgres — **Session pooler** (port 5432, IPv4) — used by `drizzle-kit` and the migration runner | Supabase → Project Settings → Database → Connection string → **Session pooler** | yes | yes | Migrations need a non-transaction-pooler connection. Do NOT use the Direct connection — it's IPv6-only on new Supabase projects and will fail on IPv4 networks with `getaddrinfo ENOENT`. |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL, exposed to the browser | Supabase → Project Settings → API → Project URL | yes | yes | Public by design. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key for browser client | Supabase → Project Settings → API → Project API keys → `anon` `public` | yes | yes | Public by design. RLS protects everything; never bypass it from the browser. |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Newer alias of the anon key. Some Supabase clients prefer this name. | Supabase → Project Settings → API | yes | yes | Same value as anon key. |
| `SUPABASE_SERVICE_ROLE_KEY` | Bypasses RLS. Server-side only — never in any file that ships to the browser. | Supabase → Project Settings → API → Project API keys → `service_role` `secret` | yes | yes | Treat like a database password. |
| `OPENROUTER_API_KEY` | LLM provider for chat, extraction, synthesis. Used through the Vercel AI SDK. | https://openrouter.ai/keys | yes | yes | Routes to anthropic/google/etc. via OpenRouter. |
| `OPENAI_API_KEY` | Embeddings only — `text-embedding-3-small` (1536-dim) | https://platform.openai.com/api-keys | optional | yes | If unset, embeddings fall back to a deterministic zero vector. Vector similarity is meaningless without real embeddings, but the schema is preserved. |
| `TRIGGER_SECRET_KEY` | Trigger.dev v3 server-side key | Trigger.dev dashboard → project → API keys | yes | yes | Used by `apps/web` to trigger tasks, and by `apps/workers` for self-registration. |
| `TRIGGER_PROJECT_REF` | Trigger.dev project identifier — read by `apps/workers/trigger.config.ts` | Trigger.dev dashboard → project settings | yes | yes | Production value: `proj_wgpzsvhmsopqhvwqaycn`. Without this, the workers deploy command has no target and the CLI falls back to the placeholder string `TODO_set_trigger_project_ref`. |

`.env.local` lives at the **monorepo root**. Next.js, the migration runner, and the seed all explicitly load it from there (via `dotenv` with a resolved path) — Next.js's default behavior of reading `.env.local` only from the app directory is overridden in `apps/web/next.config.ts`.

## How env vars are managed

- **Source of truth: Vercel project Environment Variables tab.** Set them for Production and Preview. They're injected at build/runtime for the deployed app.
- **Local dev: `.env.local`.** Gitignored. Populated by:
  - `npx vercel@latest env pull .env.local --environment=development --yes`, OR
  - Manual paste from the source dashboards (Supabase / OpenRouter / Trigger.dev).
- **Vercel quirk:** "Sensitive" env vars in Vercel cannot be added to the Development environment. Either:
  - Convert them to "Encrypted" type so `env pull` works, or
  - Skip Vercel's Development env and paste manually into `.env.local`.

## Supabase Postgres — pooler vs direct

Supabase exposes three connection modes from the dashboard:

| Mode | Host | Port | Use for | Notes |
|---|---|---|---|---|
| Direct connection | `db.<ref>.supabase.co` | 5432 | Nothing in this project | **IPv6-only on new projects.** Requires the paid IPv4 add-on to work on IPv4 networks. Avoid. |
| Transaction pooler (shared, IPv4) | `aws-0-<region>.pooler.supabase.com` | 6543 | Application queries (`DATABASE_URL`) | Best for short-lived Vercel Function invocations. Prepared statements off. |
| Session pooler (shared, IPv4) | `aws-0-<region>.pooler.supabase.com` | 5432 | Migrations + admin SQL (`DIRECT_URL`) | Holds the session for the duration of the connection — required for Drizzle migrations. |

When copying URLs from Supabase, **toggle "Use IPv4 connection (Shared Pooler)" ON** on the connection page; otherwise Supabase still shows the IPv6-only URL.

## Supabase Auth providers

Configured in **Supabase Dashboard → Authentication → Providers**:

- **Google** — enabled. Client ID + secret from Google Cloud Console → APIs & Services → Credentials → OAuth Client ID (Web application). Authorized redirect URI must include `https://<supabase-project>.supabase.co/auth/v1/callback`. Authorized JavaScript origins must include `http://localhost:3000` (dev) and any deployed Vercel URLs.
- **Azure / Microsoft 365** — enabled. App registration in Entra ID for the popcre tenant only (`Accounts in this organizational directory only`). Required Microsoft Graph delegated permissions: `openid`, `profile`, `email`, `User.Read`. Admin consent must be granted. The Supabase "Azure URL" or "Tenant ID" field must be tenant-specific (`https://login.microsoftonline.com/<tenant-id>`), not `/common`.
- **Authentik OIDC** — TODO (not yet wired).
- **Email magic-link** — enabled as a fallback path. Delivery is via Brevo SMTP (see below).

The login UI (`apps/web/app/_components/login-form.tsx`) requests the `email` scope explicitly for both OAuth providers. **Do not remove that scope** — Microsoft Entra returns an empty `mail` field for accounts without an Exchange mailbox, which makes Supabase deny with "Error getting user email from external provider".

## Supabase Auth SMTP — Brevo

Magic-link delivery uses Brevo (formerly Sendinblue) as the SMTP provider:

| Setting | Value |
|---|---|
| Host | `smtp-relay.brevo.com` |
| Port | `587` (STARTTLS) |
| Username | A Brevo-issued `XXXXXX@smtp-brevo.com` address (Brevo → SMTP & API → SMTP tab) |
| Password | A Brevo SMTP key (NOT the API key — separate field on the same page) |
| Sender email | A Brevo-verified sender (e.g. `noreply@popcre.com`) |

Configured under **Supabase Dashboard → Authentication → SMTP Settings**. Without custom SMTP, Supabase's built-in email is rate-limited to ~3-4 emails per hour per project, which trips during basic local testing.

Brevo's free tier (300 emails/day) is plenty for development.

## Settings table (runtime config)

Not all configuration lives in env vars. Operational settings the Oracle reads at runtime live in the `settings` Postgres table. Each row is `(key, value::jsonb, description, updated_at)`. Seeded in `packages/db/src/seed.ts`.

| Key | Default | Purpose |
|---|---|---|
| `lull_window_seconds` | `60` | How many seconds of silence before the Oracle may consider a "lull" interjection. |
| `oracle_cooldown_minutes` | `10` | Minimum minutes between Oracle interjections in the same channel. |
| `max_oracle_interjections_per_hour` | `3` | Hard cap per channel per hour. |
| `default_interview_model` | `deepseek/deepseek-v4-pro` | **Legacy — OpenRouter model id.** Used by `/api/chat`. Configurable via Admin → Settings → OpenRouter catalog picker. R1 of the AI retrofit (`docs/oracle/05-ai-retrofit-phase-packet.md`) replaces this with `default_interview_route` keyed to curated `OracleModelRoute.routeId` values (cost-aware target: `anthropic_claude_haiku_4_5_interview_primary`). The legacy key stays during migration. |
| `default_extraction_model` | `google/gemini-2.5-flash` | **Legacy — OpenRouter model id.** Used by the claim extraction worker. R1 target: `default_extraction_route` = `vertex_gemini_flash_lite_extraction_primary`. |
| `default_synthesis_model` | `anthropic/claude-sonnet-4.6` | **Legacy — OpenRouter model id.** Used by the brain synthesis worker. R1 target: `default_synthesis_route` = `vertex_gemini_flash_synthesis_primary`. |
| `enable_live_contradiction_interjections` | `false` | If false, contradictions are queued silently instead of interjected. Default off is correct (spec 5.1). |
| `enable_group_chat_lull_questions` | `true` | If false, the Oracle never speaks proactively in group chats. |

Change a setting:

```sql
UPDATE settings
SET value = '"anthropic/claude-opus-4.6"'::jsonb, updated_at = now()
WHERE key = 'default_interview_model';
```

(The value is JSON, so strings need their own quotes inside the JSON.)

## Feature flags

We don't have a feature-flag service. Boolean settings in the `settings` table fill that role for now (`enable_live_contradiction_interjections`, `enable_group_chat_lull_questions`). If we add a real flag service, document it here.

## Files that read configuration

- `apps/web/next.config.ts` — explicitly loads `.env.local` from the monorepo root before Next reads anything.
- `apps/web/lib/supabase/server.ts` — `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.
- `packages/db/src/client.ts` — `DATABASE_URL`.
- `packages/db/drizzle.config.ts` — `DIRECT_URL`.
- `packages/db/src/migrate.ts` — `DIRECT_URL` (loads `.env.local` from monorepo root explicitly).
- `packages/db/src/seed.ts` — `DIRECT_URL` (same monorepo-root load pattern).
- `packages/ai/src/openrouter.ts` — `OPENROUTER_API_KEY`.
- `packages/ai/src/embeddings.ts` — `OPENAI_API_KEY` (optional).
- `apps/workers/trigger.config.ts` — `TRIGGER_SECRET_KEY`, `TRIGGER_PROJECT_REF`.
- `apps/web/app/api/chat/route.ts` — reads model id from `settings.default_interview_model`.
- `apps/workers/src/trigger/claim-extraction.ts` — reads model id from `settings.default_extraction_model`.
- `apps/workers/src/trigger/brain-synthesis.ts` — reads model id from `settings.default_synthesis_model`.
- `apps/web/app/api/admin/models/route.ts` — `OPENROUTER_API_KEY` (proxies OpenRouter `/models` to populate the Admin → Settings model picker).

If you add a new env var, update:
1. `.env.example`
2. `turbo.json` → `globalEnv` array (so Turbo doesn't cache across env changes)
3. This table
4. The relevant `packages/<x>` README if behavior depends on it

## Future env vars — added during R1–R2 retrofit

These are not yet wired but are reserved by `docs/oracle/02-provider-native-ai-architecture.md`. Add them to `.env.example` and Vercel only when the corresponding adapter lands; do not add empty values prematurely.

| Variable | Purpose | Added in phase |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic direct provider adapter | R2 |
| `GOOGLE_CLOUD_PROJECT` | Vertex / Gemini direct | R2 + R7 |
| `GOOGLE_CLOUD_LOCATION` | Vertex region (default `us-central1`) | R2 + R7 |
| `GOOGLE_CLIENT_EMAIL` | Vertex service-account email | R2 + R7 |
| `GOOGLE_PRIVATE_KEY` | Vertex service-account key (`\\n` → real newlines in memory; never written to disk in Trigger.dev) | R2 + R7 |
| `ORACLE_ENABLE_OPENROUTER_FALLBACK` | Default `false`. When the retrofit is complete, this is the only escape hatch back to the legacy OpenRouter path. | R2 |

`OPENAI_API_KEY` is already wired for embeddings and will be reused by the OpenAI direct adapter — no new key needed for that provider.
