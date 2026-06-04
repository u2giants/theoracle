# Deployment

This file describes the current deploy and release path that exists in the repo today.

## Runtime targets

| Target | What runs there | Source of truth |
|---|---|---|
| Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | `apps/web` | `vercel.json`, GitHub integration |
| Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn` | `apps/workers` | `apps/workers/trigger.config.ts` |
| Supabase project from env | Postgres, Auth, Storage, Realtime | `.env.local` / runtime env |

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
  "buildCommand": "pnpm --filter @oracle/ai verify:retrieval-filter-parity && pnpm --filter @oracle/ai verify:vertex-file-cache && pnpm --filter @oracle/web build",
  "installCommand": "pnpm install --frozen-lockfile=false",
  "outputDirectory": "apps/web/.next"
}
```

The verify guards are DB-free and network-free (the Vertex guard stubs its clients), so they run inside the Vercel build with no extra secrets. The migration-drift check is intentionally NOT in the Vercel build — it needs prod DB credentials and stays in `pr-check.yml` as an advisory check.

### Workers

Workers are not deployed automatically by CI today.

Current deploy command:

```bash
pnpm --filter @oracle/workers run deploy
```

The `run` keyword is required: pnpm reserves the bare `pnpm deploy` form for its own
package-deployment subcommand, so `pnpm --filter @oracle/workers deploy` fails with
`ERR_PNPM_INVALID_DEPLOY_TARGET`. The script under the hood is
`npx trigger.dev@latest deploy` against the checked-in `apps/workers/trigger.config.ts`.

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

## CI workflow that currently exists

Only one workflow is present: `.github/workflows/pr-check.yml`

What it does (in order):

1. Checks out the repo, installs pnpm 9.5.0, uses Node 24, runs `pnpm install --frozen-lockfile=false`.
2. **Build gate** — `pnpm --filter @oracle/web build`. This is a full production Next.js build (Turbopack); it is the only command that catches Next.js-specific type errors that `pnpm typecheck` alone misses.
3. **Retrieval filter-parity guard** — `pnpm --filter @oracle/ai verify:retrieval-filter-parity`. DB-free static check that every filter key from `buildPlanMetadataFilters()` is interpolated into both the hybrid and tsvector-fallback SQL branches in `retrieval.ts`.
4. **Vertex file-cache multi-turn guard** — `pnpm --filter @oracle/ai verify:vertex-file-cache`. DB-free, network-free (clients stubbed). Asserts the file-backed cache path preserves the full conversation as live contents rather than collapsing to a single turn.
5. **Drizzle journal drift check** — `pnpm -w run db:check-drift`. Compares on-disk migration hashes against `drizzle.__drizzle_migrations` in production. Requires the `PROD_DIRECT_URL` repo secret; skips gracefully if absent.

There is no checked-in workflow for DB migrations or worker deploys.

## Environment management

Runtime env vars currently live in:

- Vercel project environment settings
- Trigger.dev project env/secrets
- local `.env.local`

Use `docs/configuration.md` for the exact variable list.

## Rollback

### Web

- Use the Vercel dashboard to promote a previous deployment.

### Workers

- Redeploy from a previous commit or use Trigger.dev version rollback tools.

### Database

- There is no automatic rollback.
- Ship a compensating migration if a schema/data change must be reversed.

## Teams transcript ingestion (Microsoft Graph)

The webhook (`apps/web/app/api/teams/notifications`) ships with the normal `apps/web` Vercel deploy — no separate step. The two workers (`teams-subscription-manager`, `teams-transcript-ingestion`) ship with the normal `pnpm --filter @oracle/workers run deploy`. To make the feature live (it is built but not yet wired live — see HANDOFF.md / AGENTS.md §14):

1. **Entra permissions (one-time, admin):** grant the app `OnlineMeetingTranscript.Read.All` + `CallTranscripts.Read.All` (Application) and admin-consent. `CallTranscripts.Read.All` is **tenant-wide read of all call transcripts** — a deliberate privacy footprint; it's what the "capture every ad-hoc call" model requires.
2. **Teams application access policy (one-time, admin, Teams PowerShell):** `New-CsApplicationAccessPolicy -Identity Oracle-Transcripts -AppIds <AZURE_GRAPH_CLIENT_ID>` then `Grant-CsApplicationAccessPolicy -PolicyName Oracle-Transcripts -Global`.
3. **Vercel env:** `TEAMS_NOTIFICATION_PRIVATE_KEY`, `TEAMS_WEBHOOK_CLIENT_STATE` (Production). Redeploy `apps/web` so the functions pick them up.
4. **Trigger.dev env:** `AZURE_*`, `TEAMS_NOTIFICATION_URL`, `TEAMS_NOTIFICATION_PUBLIC_CERT`, `TEAMS_NOTIFICATION_CERT_ID`, `TEAMS_WEBHOOK_CLIENT_STATE`. Deploy the workers.
5. The subscription **cannot be created before the webhook is publicly live** — Graph validates the `notificationUrl` synchronously at create time. Once the worker is deployed, `teams-subscription-manager` creates + renews it automatically (the resource max-lifetime is ~1h; the `*/30` cron keeps it alive — no human re-auth).

Env-var writes to Vercel are done via the Vercel dashboard or the Vercel REST API (the Vercel MCP server is read-only). The Vercel CLI is not installed in this repo's tooling by default.

## Teams live participation (Recall.ai)

This is separate from the Microsoft Graph transcript subscription above. Graph remains the post-call evidence/backfill path. Live spoken participation uses a Recall.ai meeting bot because Graph does not expose live Teams caption/transcript streams.

Deploy pieces:

1. **Recall dashboard:** create `RECALL_API_KEY`, add the ElevenLabs key for `elevenlabs_streaming` first, and create a workspace verification secret (`RECALL_WEBHOOK_SECRET`).
2. **Vercel env:** `RECALL_API_KEY`, `RECALL_BASE_URL`, `RECALL_WEBHOOK_SECRET`, `RECALL_REALTIME_WEBHOOK_URL=https://oracle.designflow.app/api/teams/live/recall`.
3. **Trigger.dev env:** `RECALL_API_KEY`, `RECALL_BASE_URL`.
4. Deploy web and workers. Then an admin can `POST /api/teams/live/start` with `{ "meetingUrl": "...", "provider": "elevenlabs_streaming" }`. Use `"assembly_ai_v3_streaming"` as the fallback provider if ElevenLabs quality or integration is not acceptable.

Recall sends finalized `transcript.data` utterances to `/api/teams/live/recall`; that route verifies the Recall signature and triggers `teams-live-recall-utterance`. The worker persists each utterance as a `messages` row (`source='teams_live_recall'`) and only calls the interview model when a cheap keyword gate says the utterance might contain operational knowledge. Oracle questions are rate-limited by the existing interjection settings and posted back with Recall's `send_chat_message` endpoint.

### Add Oracle from Teams

To make this feel native in Teams, register a Microsoft Bot Framework bot and upload the Teams app manifest template at `apps/web/teams-app/oracle/manifest.template.json`.

1. **Azure Bot registration:** create a bot whose Messaging endpoint is `https://oracle.designflow.app/api/teams/bot/messages`.
2. **Vercel env:** set `MICROSOFT_BOT_APP_ID`, `MICROSOFT_BOT_APP_PASSWORD`, and optionally `MICROSOFT_BOT_TENANT_ID`.
3. **Teams app package:** copy `manifest.template.json`, replace `REPLACE_WITH_MICROSOFT_BOT_APP_ID` and `REPLACE_WITH_TEAMS_APP_ID`, add Teams PNG icons (`outline.png`, `color.png`), zip the three files, then upload/approve it in Teams Admin Center.
4. **User flow:** in Teams, add **The Oracle** to the meeting/chat. Type `@The Oracle join <Teams meeting link>`. In meeting scope, plain `@The Oracle join` may work if Teams exposes the join URL through meeting context; otherwise the bot asks for the link.

## Operational notes

- SSH is not part of the normal release workflow.
- No Docker, Compose, Coolify, or VPS deployment path exists in this repo.
- If oversized Vertex file-backed caches are needed in production, provision `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` and related access before expecting that path to activate.
- If Vertex Batch Prediction is enabled (D14), provision `GOOGLE_VERTEX_BATCH_GCS_BUCKET` in the same region as the Vertex endpoint and grant the worker service account `roles/storage.objectAdmin`. OpenAI and Anthropic batch routes need no extra infrastructure — the provider hosts the input + results. The two-phase worker (`claim-extraction-batch-submit` + `claim-extraction-batch-drain`) is enabled by flipping `extraction_dispatch_mode` to `'batch'` in `/admin/settings`.
