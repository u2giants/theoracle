# Configuration

Every environment variable, where it comes from, and what fails when it's missing.

## Environment variables — required

| Variable | Purpose | Source | Required (dev) | Required (prod) | Notes |
|---|---|---|---|---|---|
| `DATABASE_URL` | Supabase Postgres — **Transaction pooler** (port 6543, IPv4) — used by Drizzle for application queries from Vercel Functions | Supabase → Project Settings → Database → Connection string → **Transaction pooler** (toggle "Use IPv4 connection (Shared Pooler)" ON) | yes | yes | When using Drizzle through a transaction pooler, prepared statements must be off. The client in `packages/db/src/client.ts` handles this. |
| `DIRECT_URL` | Supabase Postgres — **Session pooler** (port 5432, IPv4) — used by `drizzle-kit` and the migration runner | Supabase → Project Settings → Database → Connection string → **Session pooler** | yes | yes | Migrations need a non-transaction-pooler connection. Do NOT use "Direct connection" — it's IPv6-only on new Supabase projects. |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL, exposed to the browser | Supabase → Project Settings → API → Project URL | yes | yes | Public by design. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key for browser client | Supabase → Project Settings → API → `anon` `public` | yes | yes | Public by design. RLS protects everything; never bypass it from the browser. |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Newer alias of the anon key | Supabase → Project Settings → API | yes | yes | Same value as anon key. |
| `SUPABASE_SERVICE_ROLE_KEY` | Bypasses RLS. Server-side only — never in any file that ships to the browser. | Supabase → Project Settings → API → `service_role` `secret` | yes | yes | Treat like a database password. |
| `ANTHROPIC_API_KEY` | Direct Anthropic API key — `AnthropicAdapter` uses it for interview chat (Claude Haiku 4.5) | https://console.anthropic.com/settings/keys | yes | yes | The SDK reads this env var automatically. Loaded by the worker / chat route's adapter constructor via `process.env.ANTHROPIC_API_KEY`. |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID for Vertex AI — `VertexGeminiAdapter` uses it for extraction (Gemini 2.5 Flash) and synthesis | The active Oracle GCP project. Currently: `vertex-ai-497120`. | yes | yes | Set the value in `.env.local`, AND ensure ADC is configured (`gcloud auth application-default login`) so the SDK can authenticate. |
| `GOOGLE_CLOUD_LOCATION` | Vertex region | Pick a region with Gemini Flash availability. Currently: `us-central1`. | yes | yes | The `VertexGeminiAdapter` defaults to `us-central1` if unset; setting it explicitly is preferred. |
| `OPENAI_API_KEY` | Direct OpenAI API key — `OpenAIAdapter` uses it for fallback / schema-repair routes (GPT-4o-mini) AND `text-embedding-3-small` (1536-dim embeddings) | https://platform.openai.com/api-keys | yes | yes | Embeddings are required for hybrid retrieval and contradiction ANN search. Without this key, embeddings fall back to a deterministic zero vector and similarity becomes meaningless. |
| `TRIGGER_SECRET_KEY` | Trigger.dev v3 server-side key | Trigger.dev dashboard → project → API keys | yes | yes | Used by `apps/web` to trigger tasks, and by `apps/workers` for self-registration. |
| `TRIGGER_PROJECT_REF` | Trigger.dev project identifier | Trigger.dev dashboard → project settings | yes | yes | Production value: `proj_wgpzsvhmsopqhvwqaycn`. Without this, the workers deploy command has no target. |

`.env.local` lives at the **monorepo root**. Next.js, the migration runner, the seed, the smoke runners, and the wet-test runner all load it explicitly via `dotenv` from there. Next.js's default behavior of reading `.env.local` only from the app directory is overridden in `apps/web/next.config.ts`.

> **`OPENROUTER_API_KEY` is no longer used.** It was removed from `.env.local` when OpenRouter was retired from the codebase (commit `b01e514`, R11.0). If your `.env.local` still has it, you can delete the line.

## Google Cloud / Vertex AI authentication

The `VertexGeminiAdapter` authenticates via **Application Default Credentials** (ADC). The SDK looks for credentials in this order:

1. `GOOGLE_APPLICATION_CREDENTIALS` env var pointing at a service-account JSON (production-style).
2. ADC from `gcloud auth application-default login` (developer-style; what we use locally).
3. Metadata server (cloud-native; Vercel / GCE / GKE).

For local development:

```powershell
gcloud config configurations create oracle      # one-time
gcloud config set project vertex-ai-497120
gcloud config set account u2giants@gmail.com
gcloud auth application-default login           # opens browser
gcloud auth application-default set-quota-project vertex-ai-497120
gcloud services enable aiplatform.googleapis.com --project=vertex-ai-497120
```

For Vercel runtime: mount a Vertex AI service-account JSON via `GOOGLE_APPLICATION_CREDENTIALS_JSON` (or equivalent secret-mounting pattern) when the production wiring lands. The current local-dev path uses your developer ADC.

## How env vars are managed

- **Source of truth: Vercel project Environment Variables tab.** Set them for Production and Preview. They're injected at build/runtime for the deployed app.
- **Local dev: `.env.local` at the repo root.** Gitignored. Populated by:
  - `npx vercel@latest env pull .env.local --environment=development --yes`, OR
  - Manual paste for the direct-provider keys (Anthropic / OpenAI) and Google Cloud variables, which are not stored in Vercel.
- **Vercel quirk:** "Sensitive" env vars in Vercel cannot be added to the Development environment. Either convert them to "Encrypted" or paste manually into `.env.local`.

## Supabase Postgres — pooler vs direct

Supabase exposes three connection modes:

| Mode | Host | Port | Use for | Notes |
|---|---|---|---|---|
| Direct connection | `db.<ref>.supabase.co` | 5432 | Nothing in this project | **IPv6-only on new projects.** Avoid. |
| Transaction pooler (shared, IPv4) | `aws-0-<region>.pooler.supabase.com` | 6543 | Application queries (`DATABASE_URL`) | Best for short-lived Vercel Function invocations. Prepared statements off. |
| Session pooler (shared, IPv4) | `aws-0-<region>.pooler.supabase.com` | 5432 | Migrations + admin SQL (`DIRECT_URL`) | Holds the session for the duration of the connection — required for Drizzle migrations. |

When copying URLs from Supabase, **toggle "Use IPv4 connection (Shared Pooler)" ON** on the connection page.

## Supabase Auth providers

Configured in **Supabase Dashboard → Authentication → Providers**:

- **Google** — enabled. Client ID + secret from Google Cloud Console → APIs & Services → Credentials → OAuth Client ID (Web application).
- **Azure / Microsoft 365** — enabled. App registration in Entra ID for the popcre tenant only. Required Microsoft Graph delegated permissions: `openid`, `profile`, `email`, `User.Read`. Admin consent must be granted.
- **Authentik OIDC** — TODO (not yet wired).
- **Email magic-link** — enabled as a fallback path. Delivery via Brevo SMTP.

The login UI (`apps/web/app/_components/login-form.tsx`) requests the `email` scope explicitly for both OAuth providers. **Do not remove that scope** — Microsoft Entra returns an empty `mail` field for accounts without an Exchange mailbox, which makes Supabase deny with "Error getting user email from external provider".

## Supabase Auth SMTP — Brevo

Magic-link delivery uses Brevo as the SMTP provider:

| Setting | Value |
|---|---|
| Host | `smtp-relay.brevo.com` |
| Port | `587` (STARTTLS) |
| Username | Brevo-issued `XXXXXX@smtp-brevo.com` |
| Password | Brevo SMTP key (NOT the API key — separate field on the same page) |
| Sender email | A Brevo-verified sender (e.g. `noreply@popcre.com`) |

Brevo's free tier (300 emails/day) is plenty for development.

## Settings table (runtime config)

Operational settings the Oracle reads at runtime live in the `settings` Postgres table. Each row is `(key, value::jsonb, description, updated_at)`. Seeded in `packages/db/src/seed.ts`.

| Key | Default | Purpose |
|---|---|---|
| `lull_window_seconds` | `60` | Seconds of silence before the Oracle may consider a "lull" interjection. |
| `oracle_cooldown_minutes` | `10` | Minimum minutes between Oracle interjections in the same channel. |
| `max_oracle_interjections_per_hour` | `3` | Hard cap per channel per hour. |
| `default_interview_route` | `anthropic_claude_haiku_4_5_interview_primary` | Read by `apps/web/app/api/chat/route.ts` (R8) to resolve a curated `OracleModelRoute` from the catalog in `packages/ai/src/routes/`. |
| `default_extraction_route` | `vertex_gemini_2_5_flash_extraction_primary` | Read by `apps/workers/src/trigger/claim-extraction.ts` (R6), `apps/workers/src/trigger/document-ingestion.ts` (R7), and `apps/workers/src/trigger/contradiction-watcher.ts` (R11.0). |
| `default_synthesis_route` | `anthropic_claude_3_5_sonnet_synthesis_primary` | Read by `apps/workers/src/trigger/brain-synthesis.ts` (R9). |
| `enable_live_contradiction_interjections` | `true` (post-R11) / `false` (pre-R11) | If false, contradictions are queued silently. R11 flips this to true on install per the live-interjection decision. |
| `enable_group_chat_lull_questions` | `true` | If false, the Oracle never speaks proactively in group chats. |

Legacy `default_*_model` keys (`default_interview_model` / `default_extraction_model` / `default_synthesis_model`) have been removed from the seed. They were the pre-retrofit OpenRouter model identifiers and are no longer read by any code path. If they appear in your live DB from an older deploy, they're inert and can be deleted in a follow-up `DELETE FROM settings` migration.

Change a setting:

```sql
UPDATE settings
SET value = '"anthropic_claude_haiku_4_5_interview_primary"'::jsonb, updated_at = now()
WHERE key = 'default_interview_route';
```

(The value is JSON, so strings need their own quotes inside.)

## Feature flags

We don't have a feature-flag service. Boolean settings in the `settings` table fill that role for now (`enable_live_contradiction_interjections`, `enable_group_chat_lull_questions`).

## Files that read configuration

- `apps/web/next.config.ts` — loads `.env.local` from the monorepo root.
- `apps/web/lib/supabase/server.ts` — `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.
- `apps/web/app/api/chat/route.ts` — reads `settings.default_interview_route`; uses `ANTHROPIC_API_KEY` + Vertex ADC + `OPENAI_API_KEY` via the three direct adapters.
- `apps/workers/src/trigger/claim-extraction.ts` — reads `settings.default_extraction_route`; same three direct adapters.
- `apps/workers/src/trigger/document-ingestion.ts` — reads `settings.default_extraction_route`; same three direct adapters.
- `apps/workers/src/trigger/brain-synthesis.ts` — reads `settings.default_synthesis_route`; same three direct adapters.
- `apps/workers/src/trigger/contradiction-watcher.ts` — reads `settings.default_extraction_route` + `settings.enable_live_contradiction_interjections`; same three direct adapters.
- `apps/workers/src/wet-test/run-claim-extraction-once.ts` — wet-test driver; validates `DATABASE_URL`/`DIRECT_URL`/`GOOGLE_CLOUD_PROJECT`/`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` before running.
- `packages/db/src/client.ts` — `DATABASE_URL`.
- `packages/db/drizzle.config.ts` — `DIRECT_URL`.
- `packages/db/src/migrate.ts` — `DIRECT_URL`.
- `packages/db/src/seed.ts` — `DIRECT_URL`.
- `packages/ai/src/providers/anthropic-adapter.ts` — `ANTHROPIC_API_KEY`.
- `packages/ai/src/providers/vertex-gemini-adapter.ts` — `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION` (ADC for auth).
- `packages/ai/src/providers/openai-adapter.ts` — `OPENAI_API_KEY` (+ optional `OPENAI_ORG_ID`).
- `packages/ai/src/embeddings.ts` — `OPENAI_API_KEY` (for `text-embedding-3-small`).
- `apps/workers/trigger.config.ts` — `TRIGGER_SECRET_KEY`, `TRIGGER_PROJECT_REF`.

If you add a new env var, update:
1. `.env.example`
2. `turbo.json` → `globalEnv` array (so Turbo doesn't cache across env changes)
3. This table
4. The relevant `packages/<x>` README if behavior depends on it

## .env.local override quirk

The Claude Code harness, some Anthropic developer tools, and certain VS Code extensions inject `ANTHROPIC_API_KEY=""` (empty string) and sometimes `OPENAI_API_KEY=""` as a credential-redaction safeguard. `dotenv.config()` by default does NOT override existing process-env values, which makes the file-provided real keys silently ignored.

The smoke runner (`packages/ai/src/__verify__/r-providers-smoke.ts`) and the wet-test runner (`apps/workers/src/wet-test/run-claim-extraction-once.ts`) both use `dotenv.config({ override: true })` on the `.env.local` load to defeat this. If you add a new runner script that reads provider keys via `dotenv`, do the same.
