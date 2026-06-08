# HANDOFF — Recall.ai wiring + extraction pipeline tuning

Last updated: 2026-06-08. Delete this file once the remaining items below are closed (secret rotation, end-to-end Recall test, synthesis demo, entity-registry seeding).

---

## What is open and needs finishing

### 1. Rotate the leaked secrets (CRITICAL — do first)

Three secrets were exposed in chat sessions and must be rotated before anything else:

| Secret | Exposed in session | Action |
|---|---|---|
| `RECALL_API_KEY` | 2026-06-06 | Regenerate in Recall dashboard → update in Vercel + Trigger.dev |
| `RECALL_WEBHOOK_SECRET` | 2026-06-06 | Regenerate in Recall dashboard (workspace verification secret) → update in Vercel |
| Azure app client secret | prior session (2026-06-05) | Entra → app `ed0b64b2` → Certificates & secrets → create new → update `AZURE_GRAPH_CLIENT_SECRET` in Vercel + Trigger.dev |
| Vercel API token | prior session (2026-06-05) | Vercel account settings → Tokens → revoke |

### 2. End-to-end Recall test (after secret rotation)

The Recall live path is now fully wired (env vars set, workers deployed, webhook confirmed responding), but has not been exercised with a real Teams meeting. To test:

```
POST https://oracle.designflow.app/api/teams/live/start
Authorization: (admin session cookie)
Content-Type: application/json
{"meetingUrl":"<your Teams join link>"}
```

Expected: Recall bot joins under "The Oracle". When someone speaks, expect a `messages` row in `source='teams_live_recall'` within a few seconds. If the utterance passes the keyword gate + cooldown + confidence threshold, Oracle posts a short question to meeting chat.

### 3. Demonstrate synthesis

4 claims are in `pending_review`. Synthesis has never been run. To unblock:

1. Approve ≥1 of the 4 `pending_review` claims (SQL: `UPDATE claims SET status='approved' WHERE status='pending_review' LIMIT 1`) or use the admin review UI.
2. Trigger `brain-synthesis` via Trigger MCP or the admin UI.
3. Confirm a `brain_section_versions` row appears + narrative looks right.

### 4. Seed entity registry + active knowledge domains

On a fresh system, almost every extraction-derived claim is **held**:
- **Entity registry is empty** → new entities ("Albert H.", "Newark warehouse", "RFQ") are unresolved → claim held, entity queued as `entity_proposals`.
- **`domain_valid` fails** when the model's proposed knowledge-domains don't map to active `knowledge_top_domains`.
- **High-impact claims (≥7)** always go to `pending_review` — by design.

This is not a bug; it's the review/safety model working as intended. Get owner sign-off before loosening.

---

## What is done (since the prior HANDOFF)

### Teams transcript ingestion — LIVE and validated (2026-06-04/05)

- Real Meet-Now call → subscription → webhook → ingestion → **95 messages**, `speakersResolved 2/2`
- Speaker resolution by email (`fbb82cd`) + bootstrap-by-email for `@popcre.com` (`e73868b`)
- 38 employees seeded (all enabled `@popcre.com` humans)
- Two latent extraction bugs fixed: `segmentSummary` cap overflow (`71fa76f`) + broken `::uuid` cast in `stageEntityProposal` (`c159732`)
- Fuzzy quote matching for spoken transcripts (`89d2fd9`, D-transcript-fuzzy-quote)
- Raw VTT persistence (`89d2fd9`, D-raw-transcripts, hand-written `62_raw_transcripts.sql`)
- Workers deployed: Trigger.dev version **20260605.1**

### Recall.ai live Teams path — wired and deployed (2026-06-06)

The code (`bfd6612`) was committed by a prior session but was untested. This session wired it live:

- **Region bug fixed** (`4219c66`): default `RECALL_BASE_URL` was `us-west-2` but POP Creations workspace is US East. Fixed in `apps/web/lib/recall.ts`, `apps/workers/src/lib/recall.ts`, `.env.example`.
- **Vercel env vars set** (manually by user after CLI scripting issues): `RECALL_API_KEY`, `RECALL_WEBHOOK_SECRET`, `RECALL_BASE_URL=https://us-east-1.recall.ai`, `RECALL_REALTIME_WEBHOOK_URL=https://oracle.designflow.app/api/teams/live/recall`.
- **Trigger.dev env vars set** (via REST API): `RECALL_API_KEY`, `RECALL_BASE_URL`.
- **Workers deployed**: version **20260606.1** (17 tasks including `teams-live-recall-utterance`).
- **Vercel build**: `4219c66` deployed to production (READY), both verify guards passed.
- **Webhook confirmed live**: `POST /api/teams/live/recall` with no signature returns `{"error":"invalid_signature"}` — proving the route is live and `RECALL_WEBHOOK_SECRET` is loaded (if secret were missing the error would be "Recall verification secret is missing or invalid").

### Design File Operations taxonomy domain applied (2026-06-08)

Commit `616cf95` added the `design_file_operations` top-level domain, retrieval-boundary guard, seed updates, entity hints, and hand-written migration `packages/db/migrations/sql/63_design_file_operations_domain.sql`.

The local shell still could not run the normal Drizzle runner because `DIRECT_URL` / `DATABASE_URL` were unavailable, but the repo was linked to Supabase project `vokucjpanhvqunimlvsp` and the hand-written SQL was applied through:

```
supabase.exe db query --linked --file packages\db\migrations\sql\63_design_file_operations_domain.sql --output table
```

Verification completed for:

- `entities.domain_hints`: `Google Drive`, `Illustrator`, `InDesign`, `Photoshop`, and `SharePoint` now include `design_file_operations`.
- `claim_top_domains`: backfill count for `design_file_operations` was `0` at verification time.

Follow-up verification queries against `knowledge_top_domains` started timing out after Supabase temporarily blocked linked CLI login attempts with `ECIRCUITBREAKER too many authentication failures`. Do not retry rapidly; let the pooler cool down before further linked CLI queries.

### Key lesson — TRIGGER_SECRET_KEY must be the prod key in Vercel

Vercel's `TRIGGER_SECRET_KEY` was initially a **dev** environment key. The webhook triggered `teams-transcript-ingestion` into the dev environment where no worker ran; the run expired (TTL 10m). Set Vercel Production `TRIGGER_SECRET_KEY` to the `tr_prod_…` key. See AGENTS.md §13 incident 2026-06-04.

---

## Recall.ai integration — how the pieces fit

| Component | File | Purpose |
|---|---|---|
| Bot creation | `apps/web/app/api/teams/live/start/route.ts` | Admin POST to join a meeting. Calls `createRecallLiveBot()` with `realtime_endpoints` pointing to the webhook URL. |
| Webhook receiver | `apps/web/app/api/teams/live/recall/route.ts` | Verifies `RECALL_WEBHOOK_SECRET` signature, triggers `teams-live-recall-utterance` worker. |
| Web helper | `apps/web/lib/recall.ts` | `createRecallLiveBot()` + `verifyRecallRequest()` |
| Worker helper | `apps/workers/src/lib/recall.ts` | `sendRecallChatMessage()` — posts Oracle question to meeting chat |
| Worker task | `apps/workers/src/trigger/teams-live-recall-utterance.ts` | Normalizes words → text, finds/creates channel, resolves speaker, inserts `messages` row, applies keyword gate + cooldown + rate cap, calls LLM, if confidence ≥ 70 sends chat message + inserts `oracle_interventions` row. |
| Teams-native bot (optional) | `apps/web/app/api/teams/bot/messages/route.ts`, `apps/web/teams-app/oracle/manifest.template.json` | Lets users type `@The Oracle join <link>` from inside Teams. Requires Azure Bot registration + `MICROSOFT_BOT_APP_ID` + `MICROSOFT_BOT_APP_PASSWORD` in Vercel. Not yet wired. |

**Important**: real-time webhook endpoints are per-bot, specified in `recording_config.realtime_endpoints` on Create Bot — NOT configurable in the Recall dashboard. The dashboard webhook section is for post-call lifecycle events only.

---

## Tooling and identifiers

- **Supabase project ref**: `vokucjpanhvqunimlvsp`. DB access: `POST https://api.supabase.com/v1/projects/vokucjpanhvqunimlvsp/database/query` with the `sbp_…` token from Windows Credential Manager (`Supabase CLI:supabase`).
- **Trigger.dev project**: `proj_wgpzsvhmsopqhvwqaycn`, prod environment. Trigger MCP (`mcp__trigger__*`) is connected.
- **Recall.ai workspace**: `f2f8cedc-6d28-4fd2-8d06-402b74d65bcc` (POP Creations), US East. Recall MCP (`mcp__recall-ai__*`) is read-only.
- **Vercel project**: `prj_rP6Jlima7iK1paffEPhLqxlswGsC`. Vercel MCP (`mcp__vercel__*`) is read-only — env-var writes go via REST API or the Vercel dashboard.
- **Trigger.dev env var REST endpoint**: `GET/POST https://api.trigger.dev/api/v1/projects/{ref}/envvars/{env}` with PAT from `claude_desktop_config.json`.

---

## Cert material (do not commit)

`oracle-teams-cert/` is gitignored. It contains `private.pem` (in Vercel as `TEAMS_NOTIFICATION_PRIVATE_KEY`), `cert.b64.txt` (Trigger.dev as `TEAMS_NOTIFICATION_PUBLIC_CERT`), `clientState.txt`, `certId.txt`. Losing `private.pem` requires regenerating the cert and re-setting both Vercel + Trigger.dev + recreating the subscription.

---

## Risks and unknowns

- **Beta resource reliability** — `communications/adhocCalls/getAllTranscripts` is preview/flighted.
- **Subscription lapse = lost calls** — the `teams-subscription-renew` cron (`*/30`) must stay healthy; monitor `job_runs` for `teams-subscription-*`.
- **Fuzzy quote matching** relaxes the verbatim-provenance guarantee for transcripts. See DECISIONS.md D-transcript-fuzzy-quote.
- **`TEAMS_WEBHOOK_CLIENT_STATE`** must match in Vercel + Trigger.dev; the private key must pair with the worker's public cert.
- **Recall creds leaked** — rotate before relying on the live path (see §1 above).
