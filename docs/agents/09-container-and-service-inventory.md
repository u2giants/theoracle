---
summary: "AGENTS.md section 9: every runtime service (Vercel functions, MCP endpoint, brain on Coolify, Supabase) with owner, id and image source."
kind: living
status: current
read-when: asking what runs where, or adding or changing a runtime service
---

<!-- Privacy rendering: infrastructure references are non-executable publication placeholders. Original Git blob 54e0d84ebd77240e6a923d120260e36033d21121 at ab73ef791ad48f187fa5d2998428aec99ce6bd82; exact originals are retained in the #27 private custody archive. No obligations, authority, timing or acceptance are changed. -->
<!-- Moved verbatim from AGENTS.md (issue #22). AGENTS.md is the router. -->

## 9. Container and service inventory

Oracle 2 and the old workers were removed in #398 (2026-11-04); rows that pointed at the deleted code were removed.

Production runtime: Vercel (web), Supabase (database/auth/storage), and the
Company Map brain service on Coolify (service `oracle-brain`, image
`ghcr.io/u2giants/theoracle-brain`, built from `apps/brain`).

| Container/service | Purpose | Managed by | App/project ID | Image/source |
|---|---|---|---|---|
| Vercel Functions | Next.js web app and API routes | Vercel | `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | `apps/web` build via `vercel.json` |
| Oracle MCP server | Read-only MCP endpoint exposing approved business knowledge (claims, Brain sections, domain taxonomy) to external AI agents. Streamable HTTP at `/api/mcp/mcp`, bearer-token auth (`ORACLE_MCP_TOKEN`). | Vercel (in-app route) | same web project | `apps/web/app/api/mcp/[transport]/route.ts` + `apps/web/lib/mcp/` |
| Supabase Postgres | Primary database | Supabase | configured by env | managed Postgres + pgvector |
| Supabase Auth | Login and session identity | Supabase | same project | managed Auth |
| Supabase Storage | Uploaded documents | Supabase | bucket `company_documents` | managed object storage |
| Supabase Realtime | Chat/message live updates | Supabase | same project | managed Realtime |
| Brevo SMTP | Magic-link email delivery through Supabase Auth | Brevo + Supabase | external account | SMTP relay |
| Anthropic API | Interview-model inference | Anthropic | external account | `@anthropic-ai/sdk` |
| Vertex AI | Extraction/synthesis inference and explicit context caches | Google Cloud | `vertex-ai-497120` via env/ADC | `@google/genai` + optional GCS bucket |
| OpenAI API | Fallback inference and embeddings | OpenAI | external account | `openai` SDK |
| DeepSeek API | Optional inference provider | DeepSeek | external account | `openai` SDK against `api.deepseek.com` |
| DashScope | Optional Qwen inference provider | Alibaba | external account | `openai` SDK against `dashscope-us.aliyuncs.com/compatible-mode/v1` |
| Azure Bot Service | Teams Bot Framework message ingress for `@The Oracle join`. | Azure | subscription `37077c95-ea53-4a19-8380-f3f48f0cc75d`; resource `theoracle-popcre-teams-bot` | Free `F0` Bot Service registration; Teams channel routes signed Bot Framework turns to `/api/teams/bot/messages`. |
| Teams tenant app store | Makes The Oracle addable/searchable inside Teams. | Microsoft Teams Admin Center / Teams PowerShell | Teams app id `17ccd7a1-b90b-428c-9966-33e7fb832923` | Organization/private-catalog app package built from `apps/web/teams-app/oracle/manifest.template.json`. |

