# HANDOFF — Teams transcript ingestion (built, not yet live)

Last updated: 2026-06-04. Delete this file once the feature is wired live and verified.

## What was being built, and why

Ingest Microsoft Teams **call transcripts** into the Oracle so operational knowledge spoken in meetings becomes evidence-backed claims, the same as chat messages and documents. POP's meetings are **100% ad-hoc "Meet Now" calls, never scheduled** — that constraint shaped the whole design.

End-to-end: a transcribed Teams call → Microsoft Graph change-notification subscription (`communications/adhocCalls/getAllTranscripts`, beta) → our webhook on Vercel → ingestion worker → one `messages` row per speaker turn (in a per-call channel, `extraction_status='pending'`) → the existing `claim-extraction` cron runs candidate-before-claim. Full design: `docs/architecture.md` § "Teams transcript ingestion".

## Fully done

- **Code (all typecheck-clean):**
  - Webhook: `apps/web/app/api/teams/notifications/route.ts` + `apps/web/lib/graph-notification-crypto.ts` (RSA-OAEP → HMAC → AES-256-CBC decryption). Subscription/transcript helpers added to `apps/web/lib/microsoft-graph.ts`. (commit `a988b4e`)
  - Renewal cron + ingestion worker: `apps/workers/src/trigger/teams-subscription-manager.ts`, `apps/workers/src/trigger/teams-transcript-ingestion.ts`, shared `apps/workers/src/lib/graph-transcripts.ts`. (commit `3b1c24c`)
  - PowerShell tooling: `scripts/test-teams-transcript-access.ps1`, `scripts/diagnose-transcripts.ps1`, `scripts/create-adhoc-subscription.ps1`.
- **Microsoft tenant setup (admin, one-time) — DONE:** App `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc` granted `OnlineMeetingTranscript.Read.All` + `CallTranscripts.Read.All` (admin-consented), and a Teams application access policy `Oracle-Transcripts` granted `-Global` for that app id.
- **Webhook deployed + validated:** live at `https://oracle.designflow.app/api/teams/notifications`; passes Graph's `?validationToken` handshake.
- **Vercel secrets set (Production):** `TEAMS_NOTIFICATION_PRIVATE_KEY`, `TEAMS_WEBHOOK_CLIENT_STATE`.
- **Proven once end-to-end at the subscription layer:** the `adhocCalls/getAllTranscripts` subscription was created successfully on the beta endpoint (id `80aef001-…` at the time) — confirming the beta resource works in this tenant. It has since lapsed (no renewal running yet).

## Partially done / not started

- **Workers NOT deployed to Trigger.dev** (`pnpm --filter @oracle/workers run deploy` not run).
- **Trigger.dev env NOT set.** The workers need: `AZURE_TENANT_ID`, `AZURE_GRAPH_CLIENT_ID`, `AZURE_GRAPH_CLIENT_SECRET`, `TEAMS_NOTIFICATION_URL=https://oracle.designflow.app/api/teams/notifications`, `TEAMS_NOTIFICATION_PUBLIC_CERT` (base64 DER), `TEAMS_NOTIFICATION_CERT_ID=oracle-teams-adhoc-1`, `TEAMS_WEBHOOK_CLIENT_STATE` (same value as Vercel).
- **Web NOT redeployed** since the secrets were set → the webhook can't decrypt yet (env vars activate on next deploy).
- **No live subscription right now** (lapsed; the renewal cron isn't deployed).
- **Never tested end-to-end with a real call.**
- **Speaker→employee resolution is display-name-only (v1)** — VTT carries display names, not emails/AAD ids; unmatched speakers get `employeeId=null`. AAD-id resolution is a TODO.

## Decisions made this session (and why)

- **Utterance = `messages` row, not `document_chunk`** — preserves speaker attribution + verbatim quotes (the evidence shape the pipeline needs). Document chunks have no speaker.
- **After-the-fact only; no live participation** — Graph exposes no live-transcript API and Teams doesn't pipe spoken words into chat. Live would require a media bot (always-on audio infra), rejected against the no-VPS/containers posture.
- **Subscription, not polling** — per-organizer `getAllTranscripts` only returns *scheduled* meetings; ad-hoc calls only surface via the subscription, and only on **beta** (v1.0 returns "not supported in V1").
- **Graph helper duplicated** in `apps/web/lib` and `apps/workers/src/lib` — separate processes, no cross-app imports; web copy is the reference.

## Dead ends / gotchas hit

- `next lint` is **removed in Next 16**; ESLint 9 needs flat config. `FlatCompat` + `eslint-config-next` v16 throws `Converting circular structure to JSON` → fixed by importing `eslint-config-next/core-web-vitals` natively (`apps/web/eslint.config.mjs`).
- `az ad app permission admin-consent` **raced** the `permission add` the first time (consented the old set). Re-running consent after the add persisted fixed it. Verify with the SP's `appRoleAssignments`, not just exit code.
- The v1.0 subscriptions endpoint rejects this resource; the beta endpoint is required.
- A "recap" email arriving does NOT mean the developer transcript API can see the call — ad-hoc Meet-Now calls don't appear in `getAllTranscripts` at all (only the subscription catches them).

## Exact next action (ordered)

1. **Rotate the leaked secrets** (both were pasted into chat this session): the Azure app client secret (Entra → app → Certificates & secrets) and the Vercel API token used for env writes. Update `AZURE_GRAPH_CLIENT_SECRET` everywhere after rotating.
2. **Push** is already done for docs + webhook + lint; confirm `3b1c24c` (workers) is on `main`.
3. **Set the 6 Trigger.dev env vars** listed above. The cert material was generated into a local temp dir `oracle-teams-cert` (`private.pem`, `cert.b64.txt`, `clientState.txt` = `cb3cf30d-56a8-4c40-a832-da9f22867c0a`, `certId.txt` = `oracle-teams-adhoc-1`). If that temp dir is gone, regenerate the keypair (see `.env.example` openssl commands) and re-set both the Vercel private key and the worker public cert from the new pair.
4. **Deploy workers:** `pnpm --filter @oracle/workers run deploy`. The `teams-subscription-renew` cron will create the subscription within 30 min (or trigger `teams-subscription-manager` once to do it immediately).
5. **Redeploy `apps/web`** so the two Vercel secrets activate (any push to `main`, or a Vercel redeploy).
6. **End-to-end test:** start a Teams Meet-Now call **after** the subscription exists, turn transcription **ON**, talk briefly, end it. Watch the webhook receive the notification (Vercel runtime logs) → ingestion worker → new channel + `messages` → claim-extraction picks them up.

## Risks / unknowns

- **Beta resource reliability** — `adhocCalls/getAllTranscripts` is preview/flighted; behavior may vary or change.
- **Subscription lapse = lost calls** — if the renewal cron stops, any call during the gap is unrecoverable (no backfill). Monitor `job_runs` for `teams-subscription-*`.
- **Transcript publish lag vs window** — transcripts publish minutes after a call ends; the subscription must still be alive then (renewal handles this in steady state).
- **Speaker resolution fragility** — display-name mismatches → null attribution; claims from unidentified speakers are weaker evidence.
- **`TEAMS_WEBHOOK_CLIENT_STATE` must match** in Vercel and Trigger.dev, and the webhook's loaded cert (`TEAMS_NOTIFICATION_PRIVATE_KEY`) must be the private half of `TEAMS_NOTIFICATION_PUBLIC_CERT`, or decryption fails silently (logged).
