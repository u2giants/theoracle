---
summary: "AGENTS.md section 8: main entities and the external identifiers for Vercel, Supabase, Trigger.dev, storage buckets and related systems."
kind: living
status: current
read-when: needing a project id, bucket name, table identity or other external identifier
---

<!-- Privacy rendering: infrastructure references are non-executable publication placeholders. Original Git blob 0e294b1fe5fb26736c2fa82394f821b30de41f5d at ab73ef791ad48f187fa5d2998428aec99ce6bd82; exact originals are retained in the #27 private custody archive. No obligations, authority, timing or acceptance are changed. -->
<!-- Moved verbatim from AGENTS.md (issue #22). AGENTS.md is the router. -->

## 8. Data model and external identifiers

Oracle 2 and the old workers were removed in #398 (2026-11-04); rows that pointed at the deleted code were removed.

| Entity/System | Identifier | Where defined | Notes |
|---|---|---|---|
| Vercel project | `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | `AGENTS.md`, deployment/config docs | Web app target |
| Trigger.dev org POP | `cmpdjy8yg0107n50hqma87hjk` | Trigger dashboard | Owns legacy and Oracle 2 preview projects |
| Oracle 2 preview projects | `proj_PRIVATE_REFERENCE_SHA256_5ac719234cae50874f21f058a58195aea057b037473342b561250e996f9cbf9d` (extractor), `proj_PRIVATE_REFERENCE_SHA256_1be33553a1432811f3b085bbf640ff84aa12c5a94d7f7a822296cdc5d78f8285` (projector) | `docs/verification/oracle2/S02-dependencies.md` | Synthetic-only staging; delete when #26 closes |
| Current Supabase project | `PRIVATE_REFERENCE_SHA256_9190ea2866aa7bf92e2806946d58e5728957851544cade4e900fa8436872652d` (`theoracle`, N. Virginia / `us-east-1`) | Supabase dashboard + runtime env | Primary DB/Auth/Storage/Realtime after 2026-06-20 cutover. Previous Ohio project `PRIVATE_REFERENCE_SHA256_653f9df957f0c83b86b981047af863c26ed0d6834d758d4d335113fdba99c74b` is `oracle.old`. |
| Supabase Storage bucket | `company_documents` | `packages/shared/src/domains.ts`, `apps/brain` | Private document bucket |
| Employee identity table | `employee_identities` | `packages/db/src/schema.ts` | Canonical auth-link table |
| Entra app (Graph backend) | `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc` | Entra `TheOracle` app | App-only Graph: directory pull + Teams transcripts. Tenant `1caeb1c0-a087-4cb9-b046-a5e22404f971`. |
| Azure Bot resource | `theoracle-popcre-teams-bot` | Azure subscription `37077c95-ea53-4a19-8380-f3f48f0cc75d`, resource group `rg-oracle-teams-bot` | Free `F0` Bot Service resource. Display name `The Oracle`, endpoint `https://oracle.designflow.app/api/teams/bot/messages`, `msaAppType=SingleTenant`, Teams channel enabled. |
| Teams org app | Teams app id `17ccd7a1-b90b-428c-9966-33e7fb832923`; external id `850b2963-3583-4af9-bf18-84985ecbcf03` | Teams tenant app store, package generated from `apps/web/teams-app/oracle/manifest.template.json` | Organization/private-catalog app named `The Oracle`. Available to everyone; installed for Albert on 2026-06-09. |
| Recall.ai workspace | `f2f8cedc-6d28-4fd2-8d06-402b74d65bcc` (POP Creations) | Recall.ai dashboard | US East (N. Virginia), API v1.11, base URL `https://us-east-1.recall.ai`. Do not use the `us-west-2` endpoint — wrong region for this workspace. |
| Graph notification cert id | `oracle-teams-adhoc-1` | `TEAMS_NOTIFICATION_CERT_ID` | Self-signed RSA cert; public half encrypts notifications, private half (`TEAMS_NOTIFICATION_PRIVATE_KEY`) decrypts them. |
| Graph transcript permissions | `OnlineMeetingTranscript.Read.All`, `CallTranscripts.Read.All` | Entra app role assignments | `CallTranscripts.Read.All` (id `4cd61b6d-8692-40bf-9d90-7f38db5e5fce`) is tenant-wide; required for the ad-hoc subscription. Also needs a Teams app access policy. |

| Employee locale | `employees.locale` | `packages/db/src/schema.ts` | Reader/content language (`varchar(12)`, default `'en'`). Admin sets `'zh-CN'` to put an employee on the "China team" (Admin → Employees). |
| Supported locales | `SUPPORTED_LOCALES` (`['en','zh-CN']`) | `packages/shared/src/domains.ts` | Source of truth for supported reader locales (used by the Admin → Employees locale form); add variants here (varchar(12) columns, no migration). |

Do not casually rename or regenerate these identifiers. They are wired across code, DB, and deployment surfaces.

