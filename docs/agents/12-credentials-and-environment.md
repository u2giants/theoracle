<!-- Moved verbatim from AGENTS.md (issue #22). AGENTS.md is the router. -->

## 12. Credentials and environment

| Variable | Purpose | Stored where | Required in dev | Required in prod |
|---|---|---|---|---|
| `DATABASE_URL` | app DB access via Supabase transaction pooler | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `DIRECT_URL` | migrations/admin DB access via session pooler | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `NEXT_PUBLIC_SUPABASE_URL` | browser Supabase URL | `.env.local`, Vercel | yes | yes |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | browser anon key | `.env.local`, Vercel | yes | yes |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | browser publishable key | `.env.local`, Vercel | yes | yes |
| `SUPABASE_SERVICE_ROLE_KEY` | server-side privileged Supabase access | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `ANTHROPIC_API_KEY` | Anthropic adapter | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `OPENAI_API_KEY` | OpenAI adapter + embeddings | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `OPENAI_ORG_ID` | Optional OpenAI organization passed to the OpenAI SDK | `.env.local`, Vercel, Trigger.dev | optional | optional |
| `GOOGLE_CLOUD_PROJECT` | Vertex adapter project | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `GOOGLE_CLOUD_LOCATION` | Vertex region | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | service-account JSON content for Vertex ADC bootstrapping | Vercel/Trigger.dev secret, optional local | no | yes |
| `GOOGLE_GEMINI_REQUEST_TIMEOUT_MS` | Optional timeout override for the direct Google Gemini adapter | `.env.local`, Vercel, Trigger.dev | optional | optional |
| `GEMINI_API_KEY` | Optional direct Gemini API key for `google/*` routes; `GoogleGeminiAdapter` falls back to `GOOGLE_APPLICATION_CREDENTIALS_JSON` OAuth when unset | `.env.local`, Vercel/Trigger.dev secret if used | no | no |
| `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` | temp GCS bucket for oversized file-backed Vertex caches | env/secret | optional | recommended |
| `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_PREFIX` | temp GCS prefix for those uploads | env/secret | optional | optional |
| `GOOGLE_VERTEX_BATCH_GCS_BUCKET` | GCS bucket for Vertex Batch Prediction JSONL I/O (D14) | env/secret | optional | required if batch mode + Vertex |
| `GOOGLE_VERTEX_BATCH_GCS_PREFIX` | Object prefix inside the batch bucket | env/secret | optional | optional |
| `DEEPSEEK_API_KEY` | DeepSeek adapter | `.env.local`, Vercel, Trigger.dev | optional | optional |
| `DASHSCOPE_API_KEY` | Qwen adapter | `.env.local`, Vercel, Trigger.dev | optional | optional (set in prod 2026-06-25 for the Qwen vision model) |
| `DASHSCOPE_BASE_URL` | Qwen adapter region override (default `dashscope-us`; set to the `dashscope-intl` compat endpoint in prod) | `.env.local`, Trigger.dev | optional | recommended when using `qwen/*` models served only on intl |
| `OPENROUTER_API_KEY` | model catalog enrichment only | `.env.local`, Vercel if desired | optional | optional |
| `ORACLE_MCP_TOKEN` | Static bearer token for the remote MCP knowledge endpoint (`/api/mcp/mcp`). External AI agents present it to query approved business knowledge. If unset, the endpoint rejects all requests. | `.env.local`, Vercel | optional | yes for MCP access |
| `ORACLE_MCP_ENABLED_TOOLS` | Optional CSV allowlist for remote MCP capabilities | Vercel/local env if used | optional | optional |
| `ORACLE_MCP_DISABLED_TOOLS` | Optional CSV denylist for remote MCP capabilities; overrides enabled list | Vercel/local env if used | optional | optional |
| `TRIGGER_SECRET_KEY` | Trigger.dev auth | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `PROD_DIRECT_URL` | Used by the CI drift-check step to reach production Postgres | GitHub Actions repo secret (`gh secret list`) | no | yes (CI) |
| `TRIGGER_PROJECT_REF` | Trigger.dev project selector | `.env.local`, Vercel | optional | optional |
| `ORACLE_RUN_VECTOR_INDEXES` | Opt-in switch for expensive `99_vector_indexes.sql` migration step | shell/env when intentionally running vector index creation | optional | optional |
| `NEXT_PUBLIC_GIT_SHA` | Build metadata injected by `apps/web/next.config.ts` for admin display | generated at build time | no | no |
| `NEXT_PUBLIC_GIT_TIMESTAMP` | Build timestamp injected by `apps/web/next.config.ts` for admin display | generated at build time | no | no |
| `NODE_ENV`, `VERCEL`, `VERCEL_ENV` | Runtime/build environment metadata used by frameworks/tooling and Turbo cache keys | platform/tooling | no | yes |
| `AZURE_TENANT_ID` | Entra ID tenant GUID for the Graph backend tenant directory pull | `.env.local`, Vercel | optional | optional |
| `AZURE_GRAPH_CLIENT_ID` | Entra app (Application) ID — same `TheOracle` app as SSO | `.env.local`, Vercel | optional | optional |
| `AZURE_GRAPH_CLIENT_SECRET` | Client secret for app-only Graph client_credentials calls. Distinct from the SSO secret (which lives in Supabase). | `.env.local`, Vercel | optional | optional |
| `TEAMS_NOTIFICATION_PRIVATE_KEY` | PEM key the webhook uses to decrypt Graph transcript notifications | Vercel (webhook) | optional | yes for Teams ingestion |
| `TEAMS_WEBHOOK_CLIENT_STATE` | Shared secret on every notification (webhook verifies, worker sets) | Vercel + Trigger.dev | optional | yes for Teams ingestion |
| `TEAMS_NOTIFICATION_URL` | Public webhook URL the worker registers as the subscription target | Trigger.dev | optional | yes for Teams ingestion |
| `TEAMS_NOTIFICATION_PUBLIC_CERT` | Base64 DER public cert Graph encrypts notifications with | Trigger.dev | optional | yes for Teams ingestion |
| `TEAMS_NOTIFICATION_CERT_ID` | Identifier for the cert above (`oracle-teams-adhoc-1`) | Trigger.dev | optional | yes for Teams ingestion |
| `RECALL_API_KEY` | Recall.ai API key — creates Teams meeting bots and sends bot chat messages | Vercel + Trigger.dev | optional | yes for live Teams participation |
| `RECALL_WEBHOOK_SECRET` | `whsec_…` signature secret — verifies real-time `transcript.data` webhooks from Recall | Vercel | optional | yes for live Teams participation |
| `RECALL_BASE_URL` | Recall.ai region endpoint. POP Creations workspace is `https://us-east-1.recall.ai` | Vercel + Trigger.dev | optional | yes for live Teams participation |
| `RECALL_REALTIME_WEBHOOK_URL` | Public URL Recall calls for `transcript.data` events (set per-bot at create time) | Vercel | optional | yes for live Teams participation |
| `MICROSOFT_BOT_APP_ID` | Azure Bot Framework app ID — enables `@The Oracle join` command from inside Teams | Vercel | optional | required for Teams-native bot |
| `MICROSOFT_BOT_APP_PASSWORD` | Bot Framework client secret | Vercel | optional | required for Teams-native bot |
| `MICROSOFT_BOT_TENANT_ID` | Tenant ID for single-tenant Bot Framework auth; omit for multi-tenant | Vercel | optional | optional |

The Teams transcript app also needs the Graph **Application** permissions `OnlineMeetingTranscript.Read.All` + `CallTranscripts.Read.All` (tenant admin consent) and a Teams application access policy. For exact sources and setup notes, read `docs/configuration.md`.

