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
| `GEMINI_API_KEY` | Optional direct Gemini Developer API key for `GoogleGeminiAdapter`. If unset, the adapter uses `GOOGLE_APPLICATION_CREDENTIALS_JSON` to mint an OAuth token for the Gemini API. | Google AI Studio / Gemini API keys | optional | optional | `google/*` routes need either this key or `GOOGLE_APPLICATION_CREDENTIALS_JSON`. This does not replace Vertex credentials for existing `vertex/*` routes. |
| `GOOGLE_GEMINI_REQUEST_TIMEOUT_MS` | Per-request timeout (ms) for `GoogleGeminiAdapter` `generateContent` calls (both the API-key SDK path and the service-account OAuth/REST path). | A positive integer in ms | optional | optional | Defaults to **180000** (3 min). Replaced a hard-coded 60s that aborted dense `google/gemini-2.5-flash` extraction on image-derived transcripts at ~60.1s (2026-06-26 bug fix). Only lower it deliberately — dense diagram extraction legitimately runs ~60s+. |
| `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` | Temporary GCS bucket used by `VertexGeminiAdapter` when it needs to build a file-backed explicit cache from a large local artifact | A bucket in the same GCP project/region as Vertex when possible | optional | recommended for large-document workloads | Required only for the oversized file-backed cache path. If unset, the adapter falls back to text-prefix caching only. |
| `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_PREFIX` | Object prefix inside the temporary cache bucket | Any short prefix, e.g. `oracle-context-cache` | optional | optional | Defaults to `oracle-context-cache`. Keeps temporary uploaded cache-source objects grouped for cleanup. |
| `GOOGLE_VERTEX_BATCH_GCS_BUCKET` | GCS bucket used by `VertexGeminiAdapter.submitBatch` for JSONL input/output of Vertex Batch Prediction jobs (D14, ~50% off) | A regional bucket in the same region as your Vertex deployment, with the SA granted `roles/storage.objectAdmin` | optional | required to use batch mode | Required only when `extraction_dispatch_mode = 'batch'` and the chosen route's provider is `vertex`. Throws a clear error at `submitBatch` if missing. |
| `GOOGLE_VERTEX_BATCH_GCS_PREFIX` | Object prefix inside the batch GCS bucket | Any short prefix, e.g. `oracle-batch` | optional | optional | If set, batch I/O lives under `gs://$BUCKET/$PREFIX/oracle-batch-<uuid>/`. If unset, lives under `gs://$BUCKET/oracle-batch-<uuid>/`. |
| `OPENAI_API_KEY` | Direct OpenAI API key — `OpenAIAdapter` uses it for fallback / schema-repair routes (GPT-4o-mini) AND `text-embedding-3-small` (1536-dim embeddings) | https://platform.openai.com/api-keys | yes | yes | Embeddings are required for hybrid retrieval and contradiction ANN search. Without this key, embeddings fall back to a deterministic zero vector and similarity becomes meaningless. |
| `OPENAI_ORG_ID` | Optional OpenAI organization passed to the OpenAI SDK. | OpenAI organization settings | optional | optional | Only needed for accounts that require selecting an org. The adapter omits it when unset. |
| `DEEPSEEK_API_KEY` | Direct DeepSeek API key — `DeepSeekAdapter` uses `api.deepseek.com` (OpenAI-compatible). | https://platform.deepseek.com/api_keys | optional | recommended | Without it, the DeepSeek adapter is silently omitted from `buildStandardAdapters()` and any worker / chat request routed to a `deepseek/*` model will fail with "no adapter registered for provider deepseek". Add only if you have models selected in any stage's pool that start with `deepseek/`. |
| `DASHSCOPE_API_KEY` | Alibaba DashScope key — `QwenAdapter` uses `dashscope-us.aliyuncs.com/compatible-mode/v1` (OpenAI-compatible). | https://bailian.console.alibabacloud.com → API Key (International region) | optional | recommended | Same omitted-when-missing behavior as DeepSeek above. Only required if any `qwen/*` model is selected in a stage's pool. **Region matters — set `DASHSCOPE_BASE_URL` accordingly.** `dashscope-intl.aliyuncs.com/compatible-mode/v1` IS the OpenAI-compatible endpoint for the INTL region (CONFIRMED 2026-06-25: it serves `qwen3-vl-235b-a22b-thinking` and the org key authenticates there; `dashscope-us` returned 401 for that same key). Set `DASHSCOPE_BASE_URL` to point the adapter at the region that serves your selected model — prod uses the intl endpoint. |
| `DASHSCOPE_BASE_URL` | Overrides the QwenAdapter base URL (default `https://dashscope-us.aliyuncs.com/compatible-mode/v1`). | n/a — set to `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` for the intl region. | optional | recommended (intl) | Read at runtime by `qwen-adapter.ts` via `process.env.DASHSCOPE_BASE_URL`. Must match the region your `DASHSCOPE_API_KEY` + selected `qwen/*` model live in. Applies to ALL Qwen calls (vision, extraction, translation). |
| `TRIGGER_SECRET_KEY` | Trigger.dev v3 server-side key | Trigger.dev dashboard → project → API keys | yes | yes | Used by `apps/web` to trigger tasks, and by `apps/workers` for self-registration. **In Vercel Production this MUST be the PROD-environment key** (`tr_prod_…`). The SDK dispatches a trigger to whatever environment the key belongs to; a dev key silently routes production work to the dev env where no worker runs and the run expires (TTL 10m). Cost us a silently-lost Teams transcript — see AGENTS.md §13 incident 2026-06-04. |
| `TRIGGER_PROJECT_REF` | Trigger.dev project identifier | Trigger.dev dashboard → project settings | yes | yes | Production value: `proj_wgpzsvhmsopqhvwqaycn`. Without this, the workers deploy command has no target. |
| `ORACLE_RUN_VECTOR_INDEXES` | Opt-in flag for expensive vector index migration file `packages/db/migrations/sql/99_vector_indexes.sql`. | Shell/env only when intentionally creating HNSW indexes | optional | optional | Set to `1` when you want the migration runner to execute the opt-in vector-index file. Omit for normal migration runs. |
| `NEXT_PUBLIC_GIT_SHA` | Build commit SHA displayed in admin surfaces. | Generated by `apps/web/next.config.ts` at build time | no | no | Do not set manually; `next.config.ts` injects it from `git rev-parse HEAD`. |
| `NEXT_PUBLIC_GIT_TIMESTAMP` | Build commit timestamp displayed in admin surfaces. | Generated by `apps/web/next.config.ts` at build time | no | no | Do not set manually; `next.config.ts` injects it from `git show -s --format=%ct HEAD`. |
| `NODE_ENV`, `VERCEL`, `VERCEL_ENV` | Runtime/build environment metadata used by framework/platform tooling and Turbo cache keys. | Node/Vercel/Turbo | no | yes | Listed in `turbo.json` so cache keys account for platform/runtime mode. |
| `AZURE_TENANT_ID` | Entra ID tenant GUID. Used by the admin "M365 users not yet in Oracle" card to mint app-only Graph tokens. | Entra ID → Overview → Tenant ID | optional | optional | Production value: `1caeb1c0-a087-4cb9-b046-a5e22404f971`. All three `AZURE_*` vars must be set together; missing any one renders the M365 card as "not configured." |
| `AZURE_GRAPH_CLIENT_ID` | Entra app registration (Application/Client) ID. Same `TheOracle` app that owns the user-facing SSO; the Graph backend uses it with a separate client secret. | Entra ID → App registrations → TheOracle → Overview | optional | optional | Production value: `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc`. App needs the Graph `User.Read.All` **Application** permission (directory pull) and, for Teams transcript ingestion, `OnlineMeetingTranscript.Read.All` + `CallTranscripts.Read.All` (tenant-wide) — all with tenant admin consent. Transcripts also need a Teams application access policy (see deployment.md). |
| `AZURE_GRAPH_CLIENT_SECRET` | Client secret for the backend Graph client. Distinct from the SSO secret stored in Supabase. | Entra app → Certificates & secrets → New client secret (name `oracle-graph-backend`) | optional | optional | Rotate independently of the SSO secret. Long-lived (2y) — calendar the expiry. |
| `TEAMS_NOTIFICATION_PRIVATE_KEY` | PEM private key the webhook (`apps/web/app/api/teams/notifications`) uses to decrypt Graph's encrypted transcript notifications (`graph-notification-crypto.ts`). | openssl-generated keypair (see `.env.example`). PRIVATE half. | optional | required for Teams ingestion | Set in **Vercel** (the webhook runs there). The public half goes into `TEAMS_NOTIFICATION_PUBLIC_CERT`. |
| `TEAMS_WEBHOOK_CLIENT_STATE` | Shared secret echoed on every Graph notification; the webhook rejects mismatches, the worker sets it at subscription-create time. | Any random string (a GUID is fine). | optional | required for Teams ingestion | Set in **both** Vercel (webhook) and Trigger.dev (worker). Must be identical in both places. |
| `TEAMS_NOTIFICATION_URL` | Public HTTPS URL of the webhook; the worker registers it as the subscription `notificationUrl`/`lifecycleNotificationUrl`. | `https://oracle.designflow.app/api/teams/notifications` | optional | required for Teams ingestion | Set in **Trigger.dev** (read by the subscription-manager worker). |
| `TEAMS_NOTIFICATION_PUBLIC_CERT` | Base64 DER of the public cert Graph uses to encrypt notification payloads. | `openssl x509 -outform DER \| base64 -w0` of the cert. | optional | required for Teams ingestion | Set in **Trigger.dev** (the worker passes it as `encryptionCertificate` on create). |
| `TEAMS_NOTIFICATION_CERT_ID` | Identifier for the cert above; echoed back on each notification. | Any short string. Production: `oracle-teams-adhoc-1`. | optional | required for Teams ingestion | Set in **Trigger.dev**. Must match the cert actually loaded by the webhook. |
| `RECALL_API_KEY` | Recall.ai API key for creating Teams meeting bots and sending bot chat messages. | Recall.ai dashboard | optional | required for live Teams participation | Set in **Vercel** for `/api/teams/live/start` and **Trigger.dev** for `teams-live-recall-utterance`. |
| `RECALL_BASE_URL` | Recall.ai region base URL. | Recall.ai region/workspace | optional | required for live Teams participation | Defaults to `https://us-east-1.recall.ai` when unset (POP Creations workspace is US East, N. Virginia). Keep Vercel + Trigger.dev aligned. Using the wrong region causes 403/404 on every bot create or chat-message call. |
| `RECALL_WEBHOOK_SECRET` | Recall workspace verification secret (`whsec_...`) used to verify real-time transcript webhooks. | Recall.ai dashboard → API keys/secrets | optional | required for live Teams participation | Set in **Vercel**. The webhook rejects unsigned/invalid requests before triggering workers. |
| `RECALL_REALTIME_WEBHOOK_URL` | Public URL Recall should call for `transcript.data` events. | `https://oracle.designflow.app/api/teams/live/recall` | optional | required for live Teams participation | Used by `/api/teams/live/start` when creating a bot. |
| `MICROSOFT_BOT_APP_ID` | Azure Bot / Teams app bot App ID. | Azure Bot registration | optional | required to add Oracle from Teams | Set in **Vercel**. The Azure Bot messaging endpoint is `/api/teams/bot/messages`. |
| `MICROSOFT_BOT_APP_PASSWORD` | Bot client secret/password used by Bot Framework auth. | Azure Bot registration / app registration secret | optional | required to add Oracle from Teams | Set in **Vercel** only. Never expose to the browser. |
| `MICROSOFT_BOT_TENANT_ID` | Tenant ID for single-tenant Bot Framework auth. | Entra tenant ID | optional | optional | If unset, the bot auth is configured as multi-tenant. |
| `ORACLE_MCP_TOKEN` | Static bearer token external AI agents present to the remote MCP knowledge endpoint (`/api/mcp/mcp`). Verified in constant time by `apps/web/app/api/mcp/[transport]/route.ts`. | Any long random value (e.g. `openssl rand -hex 32`) | optional | required for MCP access | Set in **Vercel**. If unset, the endpoint rejects every request (fail-closed). Machine-to-machine only — not a Supabase user session. Rotate by changing the env var. |
| `ORACLE_MCP_ENABLED_TOOLS` | Optional CSV allowlist of MCP capability names. If set, ONLY these capabilities are discoverable/invocable. | CSV of capability names (e.g. `search_business_knowledge`) | optional | optional | Omit to enable all. Resolved in `apps/web/lib/mcp/registry.ts`; disabled overrides enabled. |
| `ORACLE_MCP_DISABLED_TOOLS` | Optional CSV denylist of MCP capability names; always disabled even if also listed as enabled. | CSV of capability names | optional | optional | Disabled wins over enabled. Hides the capability from `tool_search`/`list_capabilities` and makes `invoke_tool` reject it. |

`.env.local` lives at the **monorepo root**. Next.js, the migration runner, the seed, the smoke runners, and the wet-test runner all load it explicitly via `dotenv` from there. Next.js's default behavior of reading `.env.local` only from the app directory is overridden in `apps/web/next.config.ts`.

> `OPENROUTER_API_KEY` is optional — `packages/ai/src/model-capabilities/sources/openrouter.ts` sends it as a Bearer token when present to avoid rate limits on OpenRouter's public `/v1/models` endpoint (used for model capability and pricing enrichment). If unset, the endpoint is called unauthenticated. It is NOT read by any inference code path. The variable from `.env.example` documents it as optional.

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

**For Vercel runtime (set 2026-05-27):** the `VertexGeminiAdapter` looks for `GOOGLE_APPLICATION_CREDENTIALS_JSON` (raw JSON content of a service-account key) FIRST, and if present writes it to a deterministic temp file then points `GOOGLE_APPLICATION_CREDENTIALS` at it before delegating to the standard ADC flow. The production Vercel env has all three set:

- `GOOGLE_APPLICATION_CREDENTIALS_JSON` — the JSON content of an SA key for `oracle-trigger-worker@vertex-ai-497120`
- `GOOGLE_CLOUD_PROJECT` = `vertex-ai-497120`
- `GOOGLE_CLOUD_LOCATION` = `us-central1`

If you enable the oversized file-backed explicit-cache path, also set:

- `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` — writable by the same ADC/service account
- `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_PREFIX` — optional grouping prefix for temporary uploaded objects

To rotate the SA key:

```powershell
$gcloud = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
& $gcloud iam service-accounts keys create $env:TEMP\new-key.json `
  --iam-account=oracle-trigger-worker@vertex-ai-497120.iam.gserviceaccount.com `
  --project=vertex-ai-497120
# upload the file content as GOOGLE_APPLICATION_CREDENTIALS_JSON in Vercel
# then revoke the old key:
& $gcloud iam service-accounts keys delete <OLD_KEY_ID> `
  --iam-account=oracle-trigger-worker@vertex-ai-497120.iam.gserviceaccount.com
Remove-Item $env:TEMP\new-key.json -Force
```

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
| Transaction pooler (shared, IPv4) | Copy exact host from Supabase, e.g. `aws-1-us-east-1.pooler.supabase.com` | 6543 | Application queries (`DATABASE_URL`) | Best for short-lived Vercel Function invocations. Prepared statements off. Do not assume the host prefix is always `aws-0`. |
| Session pooler (shared, IPv4) | Copy exact host from Supabase, e.g. `aws-1-us-east-1.pooler.supabase.com` | 5432 | Migrations + admin SQL (`DIRECT_URL`) | Holds the session for the duration of the connection — required for Drizzle migrations. Do not assume the host prefix is always `aws-0`. |

When copying URLs from Supabase, **toggle "Use IPv4 connection (Shared Pooler)" ON** on the connection page and use the host Supabase shows for that project. The current production project is in N. Virginia and uses `aws-1-us-east-1.pooler.supabase.com`.

## Supabase Auth providers

Configured in **Supabase Dashboard → Authentication → Providers**:

- **Google** — enabled. Client ID + secret from Google Cloud Console → APIs & Services → Credentials → OAuth Client ID (Web application).
- **Azure / Microsoft 365** — enabled. App registration in Entra ID for the popcre tenant only. Required Microsoft Graph delegated permissions: `openid`, `profile`, `email`, `User.Read`. Admin consent must be granted. Provider URL must be `https://login.microsoftonline.com/1caeb1c0-a087-4cb9-b046-a5e22404f971` with **no** trailing `/v2.0`; Supabase appends `/oauth2/v2.0/authorize` itself.
- **Authentik OIDC** — TODO (not yet wired).
- **Email magic-link** — enabled as a fallback path. Delivery via Brevo SMTP.

The login UI (`apps/web/app/_components/login-form.tsx`) requests the `email` scope explicitly for both OAuth providers. **Do not remove that scope** — Microsoft Entra returns an empty `mail` field for accounts without an Exchange mailbox, which makes Supabase deny with "Error getting user email from external provider".

Client-secret rotation note: the Entra app `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc` is shared by Supabase Microsoft SSO, the app-only Graph backend, and the Teams Bot Framework registration. Use `az ad app credential reset --append --display-name <purpose> ...` when creating a new secret for one consumer. Running the command without `--append` removes the other consumers' secrets and breaks sign-in/Graph/Bot auth.

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
| `teams_live_recall_min_confidence_to_post` | `70` | Minimum model confidence required before the Recall live worker posts an Oracle question. Set to `101` to clamp live posting off without a deploy. |
| `teams_live_recall_force_model_pass` | `false` | Test-only override that sends every live Recall utterance through the model gate. Keep false outside controlled debugging. |
| `teams_live_recall_force_post` | `false` | Test-only override that posts utterances beginning with `Oracle test...` through Recall chat. Keep false outside controlled debugging. |
| `teams_live_recall_disable_posting_limits` | `false` | Test-only override that bypasses live Recall cooldown and hourly caps. Keep false outside controlled debugging. |
| `default_interview_route` | `anthropic_claude_haiku_4_5_interview_primary` | Read by `apps/web/app/api/chat/route.ts` (R8) to resolve a curated `OracleModelRoute` from the catalog in `packages/ai/src/routes/`. |
| `default_extraction_route` | `vertex_gemini_2_5_flash_extraction_primary` | Read by `apps/workers/src/trigger/claim-extraction.ts` (R6), `apps/workers/src/trigger/document-ingestion.ts` (R7), and `apps/workers/src/trigger/contradiction-watcher.ts` (R11.0). |
| `default_synthesis_route` | `anthropic_claude_3_5_sonnet_synthesis_primary` | Read by `apps/workers/src/trigger/brain-synthesis.ts` (R9). The route-ID name is **legacy** — it resolves at runtime to `anthropic/claude-sonnet-4-6` (see catalog `modelId`). Do not rename the route to "fix" the name; saved DB rows reference this exact string. |
| `enable_live_contradiction_interjections` | `true` (post-R11) / `false` (pre-R11) | If false, contradictions are queued silently. R11 flips this to true on install per the live-interjection decision. |
| `enable_group_chat_lull_questions` | `true` | If false, the Oracle never speaks proactively in group chats. |
| `model_pool` | `[]` (empty array) | **Deprecated 2026-05-27** — replaced by the three per-stage keys below. Left in the DB if it exists; no code path reads it. |
| `model_pool_interview` | `['anthropic/claude-haiku-4-5']` | Admin-curated approved chain for Interview. Pipeline dispatch tries the configured primary first, then the remaining pool entries in order. Empty is a runtime configuration error for pipeline callers. Interview filters to tools + structured output + vision + context >100K. |
| `model_pool_extraction` | `['google/gemini-2.5-flash']` | Same, for Extraction. Extraction filters to structured output + context >100K; it intentionally does **not** require vision because uploaded images are first transcribed by `default_vision_route`, then Extraction receives text. Empty is a runtime configuration error. |
| `model_pool_synthesis` | `['anthropic/claude-sonnet-4-6']` | Same, for Synthesis. Synthesis filters to context >400K + structured output + reasoning + output-cap support. Empty is a runtime configuration error. |
| `enforce_model_capabilities` | `true` | When true, runtime route resolution rejects configured models that do not meet the slot requirements. Set false only for controlled debugging. |
| `default_general_purpose_route` | `vertex_gemini_2_5_flash_extraction_primary` | Required auxiliary model id/route for internal utility jobs such as taxonomy cluster naming. Auxiliary models are single-pick: unset means fail loud, not fallback. |
| `default_macro_route` | `openai/gpt-4.1-mini` | Reserved model for later inferential macro passes. The old `source-outline`, `macro-relationship-extraction`, and `source-coverage-audit` workers were deleted in Stage 3; workflow read and model merge use their own slots. |
| `model_pool_macro` | `["openai/gpt-4.1-mini","openai/gpt-4.1","google/gemini-2.5-pro"]` | Reserved fallback chain for later inferential macro passes. Keep OpenAI first until the future Stage 7 schema is tested against real candidates. |
| `default_workflow_read_route` | `openai/gpt-4.1` | Macro-first source workflow reader. `document-ingestion` awaits this pass before extraction, and the standalone Trigger task id is `source-workflow-read`. The output schema is flat nodes/edges/lanes/paths and is persisted to `source_workflow_maps`. OpenAI is primary because the 2026-07-07 Stage 2 gate proved this slot needs strict schema and because Gemini rejected the schema as too complex. Anthropic temperature request-shaping has since been fixed, but OpenAI remains the known-good primary for this gate. |
| `model_pool_workflow_read` | `["openai/gpt-4.1","anthropic/claude-sonnet-5","google/gemini-2.5-pro"]` | Ordered fallback chain for the workflow-read slot. Stage gates require a bake-off before treating broader candidate quality as final. Runtime capability enforcement rejects Qwen/DeepSeek for missing strict JSON Schema enforcement and rejects Gemini for the complex workflow schema even if a stale pool setting includes it. |
| `workflow_read_max_estimated_input_tokens` | `150000` | Estimated-token threshold above which the workflow reader processes chunks in sequential windows rather than truncating the source. |
| `workflow_map_max_dropped_ratio` | `0.2` | If deterministic validation drops more than this fraction of map elements, the map is stored as `degraded` and document macro health is degraded. |
| `require_workflow_map_for_ingestion` | `false` | When false, document ingestion falls back to blind claim extraction if every `workflow_read` candidate fails; the failed map remains visible through `macro_health='map_failed'` and the document gets a degraded processing note. When true, reader failure fails the document. |
| `map_directed_extraction_enabled` | `true` | When true, document ingestion runs the source workflow reader before extraction, injects the map into every extraction window, and dedups map-referenced candidates by `(documentId, mapElementRef)`. When false, document ingestion uses the old blind document extraction path as an emergency comparison/fallback until Stage 5 retires it. |
| `default_vision_route` | `vertex_gemini_2_5_flash_extraction_primary` | Vision model used by `apps/workers/src/trigger/document-ingestion.ts` to transcribe uploaded images to text (Pass 1) before claim extraction. An **auxiliary model** chosen at `/admin/settings` → "Image vision model" (picker filtered to vision-capable models). Inference is provider-direct, never OpenRouter. **Pick a vision (image-reading) model, NOT an image-generation model.** |
| `default_translation_route` | `anthropic_claude_3_5_sonnet_synthesis_primary` | Required auxiliary model id/route for bilingual claim rendering and Chinese review-question translation. Unset means fail loud, not English fallback. |
| `default_vision_reasoning_effort` | _(unset)_ | Reasoning effort for the image-vision model. Most vision models ignore it; leave `off`/unset. Same `'off'\|'low'\|'medium'\|'high'` semantics as the stage effort keys. |
| `default_interview_reasoning_effort` | _(unset)_ | One of `'off' \| 'low' \| 'medium' \| 'high'`. Unified across providers; each adapter translates to its native form (Anthropic `thinking.budget_tokens`, OpenAI `reasoning_effort`, Vertex `thinkingConfig.thinkingBudget`, Qwen `enable_thinking + thinking_budget`, DeepSeek: logged but not forwarded). Set in `/admin/settings` via the dropdown next to the model picker when the selected model has reasoning capability. See `docs/architecture.md` § "AI model adapters" for the per-provider translation table. |
| `default_extraction_reasoning_effort` | _(unset)_ | Same, for the Extraction stage. |
| `default_synthesis_reasoning_effort` | _(unset)_ | Same, for the Synthesis stage. |
| `extraction_char_budget` | `24000` | Approximate max active conversation characters selected per claim-extraction run. The selector stops at a conversation boundary; if one conversation exceeds the budget it is processed whole and logged rather than truncated. |
| `extraction_carry_in_count` | `12` | Number of prior complete/skipped same-channel messages included as non-quotable context for message extraction. Carry-in helps interpret continued conversations but cannot be cited as evidence. |
| `extraction_dispatch_mode` | `'sync'` | `'sync'` \| `'batch'`. When `'batch'`, the `claim-extraction-batch-submit` cron task gathers pending messages and submits them through the provider Batch API (OpenAI, Vertex, or Anthropic; D14) at ~50% off pricing with a 24-hour SLA; the always-on `claim-extraction-batch-drain` cron (every 10 minutes) polls in-flight `provider_batch_jobs` rows and runs the existing validation + promotion pipeline (`processSegmentOutput`) on completed batches. The legacy sync `claim-extraction` task bails early when this flag is `'batch'`. **Flip via the UI**: `/admin/settings` → "Extraction dispatch mode" card (DispatchModeToggle component). Or by SQL: `UPDATE settings SET value = '"batch"'::jsonb WHERE key = 'extraction_dispatch_mode';`. Read every cron tick, no redeploy needed. Vertex routes additionally need `GOOGLE_VERTEX_BATCH_GCS_BUCKET` provisioned; OpenAI and Anthropic batch routes need no extra infrastructure. |

Legacy `default_*_model` keys (`default_interview_model` / `default_extraction_model` / `default_synthesis_model`) have been removed from the seed. They were the pre-retrofit OpenRouter model identifiers and are no longer read by any code path. If they appear in your live DB from an older deploy, they're inert and can be deleted in a follow-up `DELETE FROM settings` migration.

### Route-ID values vs. model-ID values in `default_*_route` (2026-06-18)

The canonical shape for all three `default_*_route` settings is a **curated route ID** (e.g. `anthropic_claude_3_5_sonnet_synthesis_primary`). A bare `provider/modelId` (e.g. `anthropic/claude-sonnet-4-6`) is also accepted — `resolveModelRoute()` (`packages/ai/src/routes/resolve.ts`) looks up the catalog by provider+modelId+role and lands on an equivalent `OracleModelRoute`.

Two things future sessions should know:

- **Seed reconcile.** `packages/db/src/seed.ts` previously seeded `default_synthesis_route` with the model-ID `anthropic/claude-sonnet-4-6` while the interview/extraction rows (and `defaults.ts`) used route IDs. That drift is fixed — synthesis now seeds the route ID to match. The seed is idempotent and won't rewrite an existing row, so live DBs are unchanged.
- **Admin picker resolves route IDs.** The `/admin/settings` model picker (`apps/web/app/admin/settings/_components/model-picker.tsx`) lists concrete pool model IDs, so a saved route ID never matched directly and used to raise a (harmless) amber "not in the approved model pool" warning. The picker now resolves the route ID to its concrete model via the parent-computed `currentResolvedModel`, selects that model in the dropdown, and shows a calm note instead. Saving **without changing the model preserves the route ID** rather than flattening it to a bare model ID; explicitly picking a different model writes that model ID.

Change a setting:

```sql
UPDATE settings
SET value = '"anthropic_claude_haiku_4_5_interview_primary"'::jsonb, updated_at = now()
WHERE key = 'default_interview_route';
```

(The value is JSON, so strings need their own quotes inside.)

## Feature flags

We don't have a feature-flag service. Boolean settings in the `settings` table fill that role for now (`enable_live_contradiction_interjections`, `enable_group_chat_lull_questions`, and the `teams_live_recall_*` test overrides). Numeric settings can also act as safety clamps; for example `teams_live_recall_min_confidence_to_post=101` disables live Recall posting.

Macro lens fan-out was deleted in macro-first Stage 3. Migration `89_map_directed_extraction_cleanup.sql` removes `macro_lenses_enabled`, the `macro_max_lens_*` settings, and `macro_outline_injection_enabled`.

Macro validation tuning rows from `82_macro_validation_tuning_settings.sql` may still exist for historical compatibility, but the deleted lens and LLM macro writer paths no longer read the lens-dedup settings.

## Files that read configuration

- `apps/web/next.config.ts` — loads `.env.local` from the monorepo root.
- `apps/web/lib/supabase/server.ts` — `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.
- `apps/web/app/api/chat/route.ts` — reads `settings.default_interview_route`; uses `ANTHROPIC_API_KEY` + Vertex ADC + `OPENAI_API_KEY` via the three direct adapters, and persists Qwen Responses session state in `provider_response_sessions`.
- `apps/web/app/admin/settings/model-pool/` — reads and writes `settings.model_pool_{interview,extraction,synthesis,macro}` (per-stage pools plus the macro fallback pool).
- `apps/web/app/api/admin/model-catalog/route.ts` — `GET` reads the persisted `model_capabilities` table; `POST` calls `refreshModelCatalog(db)` which fetches models from the direct provider APIs (Anthropic, OpenAI, Google Gemini, DeepSeek, Qwen) and enriches with OpenRouter pricing/caps, then upserts. Non-fatal per-source errors are returned in `errors[]`. Admin-triggered via the "Refresh catalog" button.
- `apps/workers/src/trigger/model-catalog-refresh.ts` — nightly Trigger.dev refresh of the same `model_capabilities` table (`model-catalog-refresh-nightly`, cron `15 7 * * *`). Uses the worker production env; missing optional provider keys surface as partial-refresh errors.
- `apps/web/app/api/admin/models/route.ts` — `?stage=<interview|extraction|synthesis|auxiliary-id>` returns the pool's models from `model_capabilities` for pipeline stages; auxiliary ids such as `vision` and `general` ignore stage pools and return the full catalog for client-side auxiliary filtering.
- `packages/ai/src/model-capabilities/sources/openrouter.ts` — OpenRouter enrichment source only. Returns a `Map<modelId, OpenRouterEnrichment>` keyed by `provider/modelId`. Capability flags come from `architecture.input_modalities` + `supported_parameters`; pricing from `pricing.{prompt,completion}` (×1M); context from `top_provider.context_length` / `max_completion_tokens`. Called by `refreshModelCatalog` after the model list is built from direct provider APIs.
- `apps/workers/src/trigger/claim-extraction.ts` — reads `settings.default_extraction_route`; uses the standard provider-adapter registry.
- `apps/workers/src/trigger/document-ingestion.ts` — reads `settings.default_extraction_route`; uses the standard provider-adapter registry.
- `apps/workers/src/trigger/brain-synthesis.ts` — reads `settings.default_synthesis_route`; uses the standard provider-adapter registry.
- `apps/workers/src/trigger/contradiction-watcher.ts` — reads `settings.default_extraction_route` + `settings.enable_live_contradiction_interjections`; uses the standard provider-adapter registry.
- `apps/web/app/api/teams/notifications/route.ts` — `TEAMS_WEBHOOK_CLIENT_STATE`, `TEAMS_NOTIFICATION_PRIVATE_KEY` (Teams transcript webhook; runs on Vercel).
- `apps/web/app/api/teams/live/start/route.ts` — `RECALL_API_KEY`, `RECALL_BASE_URL`, `RECALL_REALTIME_WEBHOOK_URL` (admin-only helper to send a Recall bot into a Teams meeting).
- `apps/web/app/api/teams/live/recall/route.ts` — `RECALL_WEBHOOK_SECRET` (signed Recall real-time transcript webhook; runs on Vercel and triggers the worker).
- `apps/web/app/api/teams/bot/messages/route.ts` — `MICROSOFT_BOT_APP_ID`, `MICROSOFT_BOT_APP_PASSWORD`, `MICROSOFT_BOT_TENANT_ID`, `RECALL_API_KEY`, `RECALL_BASE_URL`, `RECALL_REALTIME_WEBHOOK_URL` (Teams-native bot command wrapper; `@The Oracle join <meeting link>` summons the Recall listener).
- `apps/workers/src/lib/graph-transcripts.ts` — `AZURE_TENANT_ID` / `AZURE_GRAPH_CLIENT_ID` / `AZURE_GRAPH_CLIENT_SECRET`, `TEAMS_NOTIFICATION_URL`, `TEAMS_NOTIFICATION_PUBLIC_CERT`, `TEAMS_NOTIFICATION_CERT_ID`, `TEAMS_WEBHOOK_CLIENT_STATE` (subscription create/renew; read by the `teams-subscription-*` + `teams-transcript-ingestion` tasks on Trigger.dev).
- `apps/workers/src/lib/recall.ts` + `apps/workers/src/trigger/teams-live-recall-utterance.ts` — `RECALL_API_KEY`, `RECALL_BASE_URL`; live Recall posting also reads `settings.oracle_cooldown_minutes`, `settings.max_oracle_interjections_per_hour`, and the `settings.teams_live_recall_*` test/safety overrides.
- `apps/web/lib/microsoft-graph.ts` — `AZURE_*` (directory pull + the web-side subscription/transcript helpers).
- `apps/web/app/api/mcp/[transport]/route.ts` — `ORACLE_MCP_TOKEN` (bearer auth for the remote MCP knowledge endpoint; runs on Vercel). Capability enablement is read from `ORACLE_MCP_ENABLED_TOOLS` / `ORACLE_MCP_DISABLED_TOOLS` in `apps/web/lib/mcp/registry.ts`. Tool/capability detail lives in `apps/web/lib/mcp/README.md`.
- `apps/workers/src/wet-test/run-claim-extraction-once.ts` — wet-test driver; validates `DATABASE_URL`/`DIRECT_URL`/`GOOGLE_CLOUD_PROJECT`/`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` before running.
- `packages/db/src/client.ts` — `DATABASE_URL`.
- `packages/db/drizzle.config.ts` — `DIRECT_URL`.
- `packages/db/src/migrate.ts` — `DIRECT_URL` and optional `ORACLE_RUN_VECTOR_INDEXES=1`.
- `packages/db/src/seed.ts` — `DIRECT_URL`.
- `packages/ai/src/providers/anthropic-adapter.ts` — `ANTHROPIC_API_KEY`.
- `packages/ai/src/providers/vertex-gemini-adapter.ts` — `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION` (ADC for auth) and optional `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` / `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_PREFIX` for file-backed explicit caches.
- `packages/ai/src/providers/openai-adapter.ts` — `OPENAI_API_KEY` (+ optional `OPENAI_ORG_ID`).
- `packages/ai/src/providers/deepseek-adapter.ts` — `DEEPSEEK_API_KEY` (+ optional `baseURL` override).
- `packages/ai/src/providers/qwen-adapter.ts` — `DASHSCOPE_API_KEY` + `DASHSCOPE_BASE_URL` env override (default `dashscope-us.aliyuncs.com/compatible-mode/v1`; prod is set to the `dashscope-intl` compat endpoint).
- `packages/ai/src/client/standard-adapters.ts` — calls all 5 adapter constructors with `tryAdd()`; failures (missing env) log in non-prod and are silently omitted in prod.
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
