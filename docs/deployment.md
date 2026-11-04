<!-- Privacy rendering: infrastructure references are non-executable publication placeholders. Original Git blob 6c7f33f50901b0f10bd7ce5b9c91a27161707487 at ab73ef791ad48f187fa5d2998428aec99ce6bd82; exact originals are retained in the #27 private custody archive. No obligations, authority, timing or acceptance are changed. -->
# Deployment

This file describes the current deploy and release path that exists in the repo today.

## Runtime targets

| Target | What runs there | Source of truth |
|---|---|---|
| Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | `apps/web` | `vercel.json`, GitHub integration |
| Coolify service `oracle-brain` | `apps/brain` (Company Map brain), image `ghcr.io/u2giants/theoracle-brain` | `.github/workflows/brain-image.yml`, Coolify `BRAIN_IMAGE_TAG` |
| Supabase project `PRIVATE_REFERENCE_SHA256_9190ea2866aa7bf92e2806946d58e5728957851544cade4e900fa8436872652d` (`theoracle`, N. Virginia) | Postgres, Auth, Storage, Realtime | `.env.local` / runtime env + Supabase dashboard |

## Current release flow

### Web app

1. Push to `main`.
2. GitHub Actions runs `.github/workflows/pr-check.yml` (build + verify guards + migration-drift check) for visibility.
3. Vercel builds using `vercel.json`. The `buildCommand` runs the static verify guards **before** the web build, so a guard failure (or a build failure) fails the Vercel build and **blocks the deploy** — the previous production deployment stays live. This is the hard deploy gate; it lives in Vercel's own build, not in a separate CI deploy step.
4. Vercel deploys the Next.js app only if that build succeeds.

`vercel.json` is part of the deploy contract:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": "nextjs",
  "buildCommand": "pnpm run build:vercel",
  "installCommand": "pnpm install --frozen-lockfile=false",
  "outputDirectory": "apps/web/.next"
}
```

`build:vercel` runs the production web build. Keeping `vercel.json` short is required because Vercel rejects `buildCommand` values over 256
characters. `verify:vercel-contract` enforces that limit and the delegation in CI.

### Brain service

Every `apps/brain` change merged to `main` publishes `ghcr.io/u2giants/theoracle-brain:<sha>` and `:latest`
via `brain-image.yml`. Coolify deploys the tag named in its `BRAIN_IMAGE_TAG` variable; that deploy is a
separate action. Oracle 2 and the old Trigger.dev workers were removed in #398 (2026-11-04).

### Database

Database migrations are also manual today:

```bash
pnpm db:migrate
```

Run migrations before pushing code that depends on them.

To keep `pnpm db:migrate` reliable, **never apply a generated
`packages/db/migrations/0NNN_*.sql` outside this runner** (no Supabase MCP
`apply_migration`, no SQL editor, no `drizzle-kit push`). Doing so creates a
journal-vs-reality drift that makes the runner refuse to start. See
`CLAUDE.md` → "Drizzle journal hygiene" for the rule and reconciliation steps
if drift is ever suspected. One such drift was reconciled on 2026-05-28
(migration `0006_magical_revanche` had been applied without a journal row).

Another drift was reconciled on 2026-06-26 for
`0007_tricky_charles_xavier.sql`. Production already had the generated schema
objects (`claim_translations`, `claims.source_lang`, and `employees.locale`),
but the journal hash did not match the checkout hash used by CI. The journal row
was updated only after verifying those objects existed in current prod. If this
recurs, verify schema reality first, then reconcile the journal to the hash
reported by `pnpm db:check-drift`; do not blindly replay generated migrations
against prod.

Local `C:\repos\oracle\.env.local` was still confirmed on 2026-06-26 to point
at `oracle.old` (`PRIVATE_REFERENCE_SHA256_653f9df957f0c83b86b981047af863c26ed0d6834d758d4d335113fdba99c74b`). For current prod migrations from a
local shell, override `DIRECT_URL`/`DATABASE_URL` with the 1Password item
`Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle,
PRIVATE_REFERENCE_SHA256_9190ea2866aa7bf92e2806946d58e5728957851544cade4e900fa8436872652d)` field `oracle_session_pooler` before running:

```powershell
$env:DIRECT_URL = op read "op://vibe_coding/qcuyabwseaptvuzvtjejffi2ou/oracle_session_pooler"
$env:DATABASE_URL = $env:DIRECT_URL
corepack pnpm --filter @oracle/db migrate
```

Use `corepack pnpm --filter @oracle/db migrate` rather than root
`corepack pnpm db:migrate` if the elevated/local environment lacks a plain
`pnpm` binary on `PATH`; the root script delegates to bare `pnpm`.

## CI workflows that currently exist

None of these deploys:

- `pr-check.yml` — Vercel contract guard, production `@oracle/web` build, DB guards, fresh-database
  migration gate, and the advisory Drizzle journal drift check (`PROD_DIRECT_URL`; skips if absent).
- `task-gates.yml` — task-classification policy gate.
- `brain-ci.yml` — brain service tests.
- `brain-image.yml` — builds the brain image on PRs; publishes to GHCR on `main`.
- `ai-review.yml`, `review-fixer.yml` — advisory AI review and its fixer.

There is no checked-in workflow for DB migrations.

## Environment management

Runtime env vars currently live in:

- Vercel project environment settings
- Coolify service environment (brain)
- local `.env.local`

Use `docs/configuration.md` for the exact variable list.

### Supabase project cutover checklist

The production Supabase project moved on 2026-06-20 from Ohio project `PRIVATE_REFERENCE_SHA256_653f9df957f0c83b86b981047af863c26ed0d6834d758d4d335113fdba99c74b` (`oracle.old`) to N. Virginia project `PRIVATE_REFERENCE_SHA256_9190ea2866aa7bf92e2806946d58e5728957851544cade4e900fa8436872652d` (`theoracle`). For any future Supabase project move, verify all of these surfaces before declaring the cutover complete:

1. Runtime envs: `.env.local`, Vercel Production/Preview/Development, the Coolify brain service, and GitHub Actions secret `PROD_DIRECT_URL` all point at the new Supabase ref/pooler and use new anon/service-role keys.
2. Supabase Auth: site URL, redirect allow list, Google provider, Azure provider, and SMTP config are present on the new project. For Microsoft SSO, add the new `https://<ref>.supabase.co/auth/v1/callback` redirect URI in Entra and create/update only the Supabase-specific client secret with `az ad app credential reset --append`.
3. Supabase Storage: copy both Storage metadata rows and object bytes for `company_documents`, then verify downloads from the new project.
4. Platform integrations: move the Supabase.com Vercel integration and Supabase.com GitHub integration to the new Supabase project in the Supabase dashboard. The Vercel Marketplace integration may inject `SUPABASE_*` and `POSTGRES_*` variables, but this app still reads `NEXT_PUBLIC_SUPABASE_*`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, and `DIRECT_URL`.
5. Brain service: confirm the Coolify `oracle-brain` env references the new project.
6. Recall.ai: dashboard webhooks are not expected for live transcripts; realtime endpoints are configured per bot at create time. Still verify Vercel has `RECALL_API_KEY`, `RECALL_WEBHOOK_SECRET`, `RECALL_BASE_URL=https://us-east-1.recall.ai`, and `RECALL_REALTIME_WEBHOOK_URL=https://oracle.designflow.app/api/teams/live/recall`.
7. Deploy/redeploy: Vercel env changes require a new production deployment. Coolify env changes require a brain redeploy.

Unknowns to verify through dashboards when CLI/API cannot expose them: the Supabase.com Vercel integration attachment, Supabase.com GitHub integration settings, and GitHub App installation state.

## Rollback

### Web

- Use the Vercel dashboard to promote a previous deployment.

### Brain

- Set Coolify `BRAIN_IMAGE_TAG` back to the previous image SHA and redeploy.

### FalkorDB graph stores (hetz / Coolify)

- Follow `docs/implementation/falkordb-coolify-deploy-plan.md` §10 (stop, then delete each role's service with volumes kept).
- [ ] **Remove DNS record `oracle-graph.designflow.app`** (DNS-only `A` → hetz, Cloudflare record id
  `32019fc3aeb47e529ba7287cb0c84b2e`) — only when BOTH roles are being removed, because the record is shared.
  Pass: `dig +short oracle-graph.designflow.app` returns nothing. Tick the matching rollback item on
  u2giants/theoracle#27.

### Database

- There is no automatic rollback.
- Ship a compensating migration if a schema/data change must be reversed.
- **Source workflow maps are versioned, not overwritten.** A new run supersedes the previous map for a
  document; nothing is deleted and every version stays addressable by id. To make an older map active
  again, set the current one to `status = 'superseded'` FIRST, then clear the older one's
  `superseded_by_map_id` and restore its status. The partial unique index
  `source_workflow_maps_active_source_hash_unique` allows only ONE non-superseded map per document and
  source content hash, so promoting before demoting is rejected. Do the swap in one transaction, check
  preconditions inside it, and assert exactly one active map before committing. This is a production
  data write: it needs the owner to name the exact map and action.

## Teams transcript ingestion (Microsoft Graph)

The Graph transcript webhook and its workers were removed in #398 (2026-11-04). Meeting transcripts
now reach the Company Map through Recall (below).

## Teams live participation (Recall.ai)

Live meetings use a Recall.ai meeting bot.

Deploy pieces:

1. **Recall dashboard (one-time):** obtain `RECALL_API_KEY` from the workspace API keys page. Create a workspace verification secret if one does not yet exist; the value starts with `whsec_`. POP Creations workspace is US East (N. Virginia) — use `https://us-east-1.recall.ai` as the base URL.
2. **Vercel env:** `RECALL_API_KEY`, `RECALL_BASE_URL`, `RECALL_WEBHOOK_SECRET`, `RECALL_REALTIME_WEBHOOK_URL=https://oracle.designflow.app/api/teams/live/recall`.
3. Deploy web. An admin can then `POST /api/teams/live/start` with `{ "meetingUrl": "...", "provider": "elevenlabs_streaming" }` (fallback provider `"assembly_ai_v3_streaming"`).

`/api/teams/live/recall` verifies the Recall signature and, when Recall reports a finished transcript
(`transcript.done` or `bot.done`), records it in the Company Map as a `transcript` source.

### Add Oracle from Teams

To make this feel native in Teams, use the Microsoft Bot Framework wrapper at `apps/web/app/api/teams/bot/messages/route.ts` and the Teams app manifest template at `apps/web/teams-app/oracle/manifest.template.json`.

Current production state (2026-06-09):

- Azure subscription: `37077c95-ea53-4a19-8380-f3f48f0cc75d` (`paygo for teams Oracle bot`)
- Resource group: `rg-oracle-teams-bot`
- Azure Bot resource: `theoracle-popcre-teams-bot`, SKU `F0`, `msaAppType=SingleTenant`
- Messaging endpoint: `https://oracle.designflow.app/api/teams/bot/messages`
- Teams channel: enabled
- Teams organization app: `The Oracle`, Teams app id `17ccd7a1-b90b-428c-9966-33e7fb832923`, external id `850b2963-3583-4af9-bf18-84985ecbcf03`
- App availability: everyone; installed for Albert on 2026-06-09

If rebuilding from scratch:

1. **Azure Bot registration:** create a single-tenant bot whose Messaging endpoint is `https://oracle.designflow.app/api/teams/bot/messages`, then enable the Microsoft Teams channel.
2. **Vercel env:** set `MICROSOFT_BOT_APP_ID`, `MICROSOFT_BOT_APP_PASSWORD`, and optionally `MICROSOFT_BOT_TENANT_ID`.
3. **Teams app package:** copy `manifest.template.json`, replace `REPLACE_WITH_MICROSOFT_BOT_APP_ID` and `REPLACE_WITH_TEAMS_APP_ID`, add Teams PNG icons (`outline.png`, `color.png`), zip the three files, then upload/approve it in Teams Admin Center.
4. **App availability/install:** verify `Get-M365TeamsApp -Id 17ccd7a1-b90b-428c-9966-33e7fb832923` shows `IsBlocked=false` and `AvailableTo.AssignmentType=Everyone`. Install for a user/group with `Update-M365TeamsApp` if it does not appear in the user's Apps view after propagation.
5. **User flow:** in Teams, add **The Oracle** to the meeting/chat. Type `@The Oracle join <Teams meeting link>`. In meeting scope, plain `@The Oracle join` may work if Teams exposes the join URL through meeting context; otherwise the bot asks for the link.

## Operational notes

- SSH is not part of the normal release workflow.
