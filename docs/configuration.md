# Configuration

Every environment variable, where it comes from, and what fails when it's missing.

## Environment variables

| Variable | Purpose | Source | Required (dev) | Required (prod) | Notes |
|---|---|---|---|---|---|
| `DATABASE_URL` | Supabase Postgres — transaction pooler (port 6543) — used by Drizzle for application queries from Vercel Functions | Supabase → Project Settings → Database → Connection string → "Transaction" | yes | yes | When using Drizzle through a transaction pooler, prepared statements must be off. The client in `packages/db/src/client.ts` already handles this. |
| `DIRECT_URL` | Supabase Postgres — direct (port 5432) — used by `drizzle-kit` for migrations | Supabase → Project Settings → Database → Connection string → "Direct" | yes | yes | Migrations need a non-pooled connection. |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL, exposed to the browser | Supabase → Project Settings → API → Project URL | yes | yes | Public by design. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key for browser client | Supabase → Project Settings → API → Project API keys → `anon` `public` | yes | yes | Public by design. RLS protects everything; never bypass it from the browser. |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Newer alias of the anon key. Some Supabase clients prefer this name. | Supabase → Project Settings → API | yes | yes | Same value as anon key. |
| `SUPABASE_SERVICE_ROLE_KEY` | Bypasses RLS. Server-side only — never in any file that ships to the browser. | Supabase → Project Settings → API → Project API keys → `service_role` `secret` | yes | yes | Treat like a database password. |
| `OPENROUTER_API_KEY` | LLM provider for chat, extraction, synthesis. Used through the Vercel AI SDK. | https://openrouter.ai/keys | yes | yes | Routes to anthropic/google/etc. via OpenRouter. |
| `OPENAI_API_KEY` | Embeddings only — `text-embedding-3-small` (1536-dim) | https://platform.openai.com/api-keys | optional | yes | If unset, embeddings fall back to a deterministic zero vector. Vector similarity is meaningless without real embeddings, but the schema is preserved. |
| `TRIGGER_SECRET_KEY` | Trigger.dev v3 server-side key | Trigger.dev dashboard → project → API keys | yes | yes | Used by `apps/web` to trigger tasks, and by `apps/workers` for self-registration. |

## How env vars are managed

- **Source of truth: Vercel project Environment Variables tab.** Set them for Production and Preview. They're injected at build/runtime for the deployed app.
- **Local dev: `.env.local`.** Gitignored. Populated by:
  - `npx vercel@latest env pull .env.local --environment=development --yes`, OR
  - Manual paste from the source dashboards (Supabase/OpenRouter/Trigger.dev).
- **Vercel quirk:** "Sensitive" env vars in Vercel cannot be added to the Development environment. Either:
  - Convert them to "Encrypted" type so `env pull` works, or
  - Skip Vercel's Development env and paste manually into `.env.local`.

## Settings table (runtime config)

Not all configuration lives in env vars. Operational settings the Oracle reads at runtime live in the `settings` Postgres table. Each row is `(key, value::jsonb, description, updated_at)`. Seeded in `packages/db/src/seed.ts`.

| Key | Default | Purpose |
|---|---|---|
| `lull_window_seconds` | `60` | How many seconds of silence before the Oracle may consider a "lull" interjection. |
| `oracle_cooldown_minutes` | `10` | Minimum minutes between Oracle interjections in the same channel. |
| `max_oracle_interjections_per_hour` | `3` | Hard cap per channel per hour. |
| `default_interview_model` | `anthropic/claude-sonnet-4.6` | Model used by `/api/chat`. |
| `default_extraction_model` | `google/gemini-flash` | Model used by the claim extraction worker. |
| `default_synthesis_model` | `anthropic/claude-sonnet-4.6` | Model used by the brain synthesis worker. |
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

- `apps/web/lib/supabase/server.ts` — `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.
- `packages/db/src/client.ts` — `DATABASE_URL`.
- `packages/db/drizzle.config.ts` — `DIRECT_URL`.
- `packages/db/src/migrate.ts` — `DIRECT_URL`.
- `packages/ai/src/openrouter.ts` — `OPENROUTER_API_KEY`.
- `packages/ai/src/embeddings.ts` — `OPENAI_API_KEY` (optional).
- `apps/workers/trigger.config.ts` — `TRIGGER_SECRET_KEY`.
- `apps/web/app/api/chat/route.ts` — reads model id from `settings.default_interview_model`.

If you add a new env var, update:
1. `.env.example`
2. `turbo.json` → `globalEnv` array (so Turbo doesn't cache across env changes)
3. This table
4. The relevant `packages/<x>` README if behavior depends on it
