# HANDOFF — Recall.ai wiring + extraction pipeline tuning

Last updated: 2026-06-09. Delete this file once the remaining items below are closed (synthesis demo, entity-registry seeding, live retrieval context).

---

## What is open and needs finishing

### 0. Current repo/deploy state from the 2026-06-09 live test

This handoff is **not** just historical notes. At the time it was updated, the working tree had uncommitted changes that matter:

- `apps/workers/src/trigger/teams-live-recall-utterance.ts`
- `HANDOFF.md`

The worker code changes in `teams-live-recall-utterance.ts` were deployed to Trigger.dev production during testing:

- `20260609.1` — live prompt allows spoken business-process questions to be captured.
- `20260609.2` — deterministic fallback for direct business-process questions when the model omits a `question`.
- `20260609.3` — strips leading direct address (`Oracle, ...`, `Hey Oracle, ...`) before business-question classification.
- `20260609.4` — fallback no longer posts exact echo; frames as `Can we clarify this process question: ...`.
- `20260609.5` — temporary `recall-live-bot-create` task added so Codex could create a fresh bot through Trigger's prod env.
- `20260609.6` — temporary create task removed; production worker surface back to 17 tasks.

Important:
- `20260609.6` is deployed and contains the `teams-live-recall-utterance.ts` behavior changes.
- The temporary `recall-live-bot-create.ts` file was deleted locally and is not present in `20260609.6`.
- The remaining source changes should be reviewed, tested as needed, committed, and pushed before considering this session closed.
- Do **not** assume the deployed worker and git history are aligned until these changes are committed.

### 1. Demonstrate synthesis

4 claims are in `pending_review`. Synthesis has never been run. To unblock:

1. Approve ≥1 of the 4 `pending_review` claims (SQL: `UPDATE claims SET status='approved' WHERE status='pending_review' LIMIT 1`) or use the admin review UI.
2. Trigger `brain-synthesis` via Trigger MCP or the admin UI.
3. Confirm a `brain_section_versions` row appears + narrative looks right.

### 2. Seed entity registry + active knowledge domains

On a fresh system, almost every extraction-derived claim is **held**:
- **Entity registry is empty** → new entities ("Albert H.", "Newark warehouse", "RFQ") are unresolved → claim held, entity queued as `entity_proposals`.
- **`domain_valid` fails** when the model's proposed knowledge-domains don't map to active `knowledge_top_domains`.
- **High-impact claims (≥7)** always go to `pending_review` — by design.

This is not a bug; it's the review/safety model working as intended. Get owner sign-off before loosening.

### 3. Add retrieval-backed context to live Oracle

The Recall live Teams path is now mechanically proven end-to-end, but it is not yet proven to be deeply knowledge-backed.

Current live worker behavior:
- Receives finalized Recall utterances.
- Stores them as `messages`.
- Uses a rolling window of recent meeting utterances.
- Applies heuristic/model/fallback logic to decide whether to post one short clarification question.

Current limitation:
- The live prompt does **not** yet retrieve approved claims, Brain sections, or older relevant messages before deciding what to ask.
- Therefore it can capture obvious process ambiguity from the live conversation, but it may not ask the most pertinent company-specific question if the relevant knowledge has not been spoken recently or synthesized yet.

Recommended next implementation:
1. In `apps/workers/src/trigger/teams-live-recall-utterance.ts`, before `decideLiveQuestion()`, run the existing retrieval/planning path against the current utterance plus recent live context.
2. Retrieve a small, bounded set of approved claims / relevant prior messages / Brain sections, with evidence metadata.
3. Add those snippets to the live decision prompt as context blocks.
4. Ask only when the live utterance conflicts with, updates, or leaves a gap against retrieved context.
5. Store evidence IDs in `oracle_interventions` or assistant-message metadata; keep Teams chat text short and citation-free unless the product later wants visible citations.

Important constraint:
- Do not let the live bot answer questions directly. It should ask clarifying questions or capture ambiguity, not behave like a full chat assistant inside the meeting.

Best first code-read for this task:
- `apps/workers/src/trigger/teams-live-recall-utterance.ts` — current live decision task, prompt, test flags, fallback logic.
- `packages/ai/src/retrieval.ts` and related retrieval-plan files — existing approved-claim retrieval path to reuse instead of inventing a second retrieval mechanism.
- `docs/architecture.md` sections for Recall live participation and retrieval/claims flow.
- `AGENTS.md` quirks on the single endorsed claim-retrieval path; keep hybrid and fallback retrieval behavior in lockstep.

Definition of done:
- A live utterance can retrieve relevant approved knowledge before deciding whether to ask.
- The worker stores which evidence influenced the interjection.
- The Teams chat post remains concise and does not answer the meeting.
- Tests or verification runs prove that generic small talk still skips, direct business questions still post, and retrieval-backed contradictions/gaps produce better questions.

---

## What is done (since the prior HANDOFF)

### Documentation maintenance audit from pasted task spec (2026-06-09)

Completed the broad Markdown audit requested from:

`C:\Users\ahazan2\.codex\attachments\0ddbc067-291d-421c-9a87-eaad3e2691a4\pasted-text.txt`

What was verified/updated:
- `AGENTS.md` remains canonical and now explicitly routes historical/spec docs without encouraging bulk-loading every Markdown file.
- `README.md` points new sessions to `HANDOFF.md` when present.
- `CLAUDE.md` was checked and left Claude-specific.
- Topic docs were aligned with the current live state: Graph post-call transcript ingestion is live, Recall live Teams participation is live, and Recall live posting is currently clamped off by runtime settings.
- `docs/configuration.md` now documents the live Recall safety/test settings.
- `docs/deployment.md` now has upsert-based SQL snippets to reopen and re-clamp live Recall tests.
- `.claudeignore`, `.cursorignore`, and `.copilotignore` were checked and already matched the project ignore policy.
- No secret values were added to docs.

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
| Teams-native bot | `apps/web/app/api/teams/bot/messages/route.ts`, `apps/web/teams-app/oracle/manifest.template.json` | Lets users type `@The Oracle join <link>` from inside Teams. Azure Bot + Teams channel + org app are wired; see current state below. |

**Important**: real-time webhook endpoints are per-bot, specified in `recording_config.realtime_endpoints` on Create Bot — NOT configurable in the Recall dashboard. The dashboard webhook section is for post-call lifecycle events only.

### Teams-native app/bot wrapper — wired (2026-06-09)

The Teams-native command wrapper is now wired on the platform side:

- Azure subscription `37077c95-ea53-4a19-8380-f3f48f0cc75d` (`paygo for teams Oracle bot`)
- Resource group `rg-oracle-teams-bot`
- Azure Bot resource `theoracle-popcre-teams-bot`, SKU `F0`, single-tenant app id `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc`
- Messaging endpoint `https://oracle.designflow.app/api/teams/bot/messages`
- Microsoft Teams channel enabled
- Teams organization app `The Oracle`: app id `17ccd7a1-b90b-428c-9966-33e7fb832923`, external id `850b2963-3583-4af9-bf18-84985ecbcf03`
- App availability is everyone; installed for Albert (`Albert@popcre.com`) on 2026-06-09

If the app does not appear in Teams immediately, check propagation and verify with:

```powershell
Get-M365TeamsApp -Id 17ccd7a1-b90b-428c-9966-33e7fb832923
```

Expected state: `IsBlocked=false`, `AvailableTo.AssignmentType=Everyone`, and Albert listed under `InstalledFor.InstallForUsers`.

### 2026-06-09 credential repair note

During Teams bot setup, an Entra secret rotation without `--append` temporarily broke Supabase Microsoft sign-in and invalidated the Graph backend secret. Recovery completed:

- Supabase Azure provider client secret was refreshed manually in the Supabase dashboard.
- Supabase Azure provider URL was corrected to `https://login.microsoftonline.com/1caeb1c0-a087-4cb9-b046-a5e22404f971` — do **not** include `/v2.0`.
- Vercel `AZURE_GRAPH_CLIENT_SECRET`, `MICROSOFT_BOT_APP_ID`, `MICROSOFT_BOT_APP_PASSWORD`, and `MICROSOFT_BOT_TENANT_ID` were refreshed and production redeployed.
- Trigger.dev prod `AZURE_GRAPH_CLIENT_SECRET` was refreshed via `POST https://api.trigger.dev/api/v1/projects/proj_wgpzsvhmsopqhvwqaycn/envvars/prod/import` using the authenticated Trigger CLI token.

Future Entra client secrets on shared app `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc` must be created with `az ad app credential reset --append --display-name <purpose> ...` unless intentionally replacing every consumer.

### Current live Recall operational state

Production settings after the final 2026-06-09 test are intentionally clamped:

| Setting | Value | Why |
|---|---:|---|
| `max_oracle_interjections_per_hour` | `0` | Disables live interjections by rate cap. |
| `teams_live_recall_min_confidence_to_post` | `101` | Disables confidence-gated posting because model confidence max is 100. |
| `teams_live_recall_force_model_pass` | `false` | Restores keyword pre-gate. |
| `teams_live_recall_force_post` | `false` | Prevents blunt test echo mode. |
| `teams_live_recall_disable_posting_limits` | `false` | Restores cooldown/hourly limit enforcement. |

To test live interjections again, intentionally reopen the gates and clamp them back off afterwards:

```sql
INSERT INTO settings (key, value, description, updated_at)
VALUES
  ('max_oracle_interjections_per_hour', '3'::jsonb, 'Hard cap per channel per hour.', now()),
  ('teams_live_recall_min_confidence_to_post', '70'::jsonb, 'Minimum live Recall model confidence required before posting.', now()),
  ('teams_live_recall_force_model_pass', 'false'::jsonb, 'Test-only: force all live Recall utterances through the model gate.', now()),
  ('teams_live_recall_force_post', 'false'::jsonb, 'Test-only: force-post Oracle test utterances.', now()),
  ('teams_live_recall_disable_posting_limits', 'false'::jsonb, 'Test-only: bypass live Recall posting cooldown and rate caps.', now())
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    description = COALESCE(settings.description, EXCLUDED.description),
    updated_at = now();
```

To clamp off:

```sql
INSERT INTO settings (key, value, description, updated_at)
VALUES
  ('max_oracle_interjections_per_hour', '0'::jsonb, 'Hard cap per channel per hour.', now()),
  ('teams_live_recall_min_confidence_to_post', '101'::jsonb, 'Minimum live Recall model confidence required before posting.', now()),
  ('teams_live_recall_force_model_pass', 'false'::jsonb, 'Test-only: force all live Recall utterances through the model gate.', now()),
  ('teams_live_recall_force_post', 'false'::jsonb, 'Test-only: force-post Oracle test utterances.', now()),
  ('teams_live_recall_disable_posting_limits', 'false'::jsonb, 'Test-only: bypass live Recall posting cooldown and rate caps.', now())
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    description = COALESCE(settings.description, EXCLUDED.description),
    updated_at = now();
```

Supabase CLI note:
- `supabase.exe db query --linked` intermittently hung during this session. If it sticks, kill `supabase*` processes and retry once:

```powershell
Get-Process | Where-Object { $_.ProcessName -like 'supabase*' } |
  Stop-Process -Force -ErrorAction SilentlyContinue
```

Do not hammer retries if the linked pooler returns authentication/circuit-breaker errors.

### Recall.ai live Teams path — end-to-end tested (2026-06-08)

Real Teams meeting test succeeded:

- Admin UI `/admin/settings` start path worked.
- ElevenLabs start failed because the Recall workspace has no ElevenLabs credentials configured.
- AssemblyAI fallback succeeded; bot `68cf8eca-459d-409e-b87d-67879615b61b` joined the Teams meeting and reached `in_call_recording`.
- Recall recording `0e591d96-e63d-4f8a-84f3-5d7f4e08f277` and transcript artifact `8256d8db-97d1-4f20-b9fd-132fe621deff` were created with `assembly_ai_v3_streaming`.
- Oracle realtime endpoint `https://oracle.designflow.app/api/teams/live/recall` was configured on the bot.
- Trigger jobs `teams-live-recall-utterance` completed successfully.
- `messages` rows were inserted with `metadata_json.source='teams_live_recall'` in channel `Teams live meeting 68cf8eca-459d-409e-b87d-67879615b61b`.

No Oracle question was posted during this test because the captured utterances were skipped by the cheap heuristic gate (`decisionReason='heuristic_skip'`), which is expected for small talk / non-operational speech.

### Temporary live Recall interjection test mode — tested, clamped OFF (2026-06-08)

Worker version **20260608.2** added temporary DB-controlled test knobs for the `teams-live-recall-utterance` task. Worker version **20260608.3** made the `force_post` override safer: it now only force-posts utterances that start with `Oracle test:`.

- `teams_live_recall_force_model_pass=true` — every non-empty live utterance is sent to the interjection decision model instead of using the cheap keyword/length pre-gate.
- `teams_live_recall_force_post=true` — posts a test question even when the model returns `shouldAsk=false`; if the model gives no question, it strips an `Oracle test:` prefix and posts the remaining utterance as the question.
- `teams_live_recall_disable_posting_limits=true` — bypasses cooldown + hourly cap for live Recall interjection tests.
- `teams_live_recall_min_confidence_to_post=0` — lowers the confidence threshold for posting when the model decides `shouldAsk=true`.

This confirms whether live utterances reach the model and whether the chat-send path can be exercised. Turn this off after testing:

Result: force-post testing succeeded with ElevenLabs bot `b2c114eb-2713-44ef-8196-f776b99d0d63`. Oracle posted the test clarification back through Recall into Teams, including:

- `Should artwork always go to China after license or approval, or is Walmart seasonal an exception?`

During the first force-post test, Oracle also echoed a few follow-up utterances because `force_post=true` was intentionally blunt in version `20260608.2`. The production settings were then hard-clamped at `2026-06-08 20:33:28`:

- `max_oracle_interjections_per_hour=0`
- `teams_live_recall_min_confidence_to_post=101`
- `teams_live_recall_force_model_pass=false`
- `teams_live_recall_force_post=false`
- `teams_live_recall_disable_posting_limits=false`

Verified after the clamp: no `teams_live_recall_interjection` assistant messages were inserted after `2026-06-08 20:33:28`.

Follow-up live test on 2026-06-09:

- Fresh Teams meeting bot `4e63dc18-a63d-4cdc-a7c7-b0e967027b20` joined and recorded successfully with ElevenLabs streaming.
- Recall recording `4c0a8a18-072f-40bc-8ae9-5cfe81f0b245` and transcript artifact `050437ce-6559-4b4f-984d-ca9e2b1b2a8b` reached `done`.
- Oracle received and stored live utterances in channel `0390c592-96af-450f-aaf9-63cecae61c92`.
- Worker versions deployed during testing:
  - `20260609.1` broadened the model prompt so business-process questions asked aloud can be captured in Teams chat.
  - `20260609.2` added deterministic fallback posting for direct business-process questions when the model recognizes the need but omits a structured `question`.
  - `20260609.3` treats leading direct address (`Oracle, ...`, `Hey Oracle, ...`) as invocation, not as meta/tool chatter, before deciding whether the remaining content is a business-process question.
- Later same-link retest bot `69b0bc21-e3a0-424c-aaa0-d75c83c40567` joined and recorded successfully with ElevenLabs streaming.
- Worker version `20260609.4` changed the deterministic direct-question fallback so Oracle no longer posts an exact echo. It frames the chat message as `Can we clarify this process question: ...`.
- The `20260609.4` path fired for: `Oracle, should artwork always go to China after licensor approval, or is Walmart a seasonal exception?`
- Oracle worker job completed with no error and `postedQuestion='Can we clarify this process question: should artwork always go to China after licensor approval, or is Walmart a seasonal exception?'`.
- Recall workspace logs independently confirmed `POST /api/v1/bot/69b0bc21-e3a0-424c-aaa0-d75c83c40567/send_chat_message/ -> 200` at `2026-06-09T17:04:09.580Z` with `to='everyone'` and the same framed message.
- Follow-up direct-send probe confirmed Recall chat delivery was visible in Teams: `direct chat probe 2026-06-09 1:13pm?`.
- After the first same-link bot stopped producing live utterance jobs, the user kicked it out and a fresh bot `5f529c48-f1de-48c2-a72b-b599b53be9c4` was created for the same meeting. It reached `in_call_recording`, recording `50a40fb6-b839-44c6-8c4a-e25126f4bf19`, transcript `afda8f7d-71ab-4579-ad97-5b024fe48f68`.
- Fresh-bot hearing test succeeded: Oracle received `Oracle hearing test, 1:28 p.m..` and skipped it correctly as a technical test.
- Final business-question test succeeded: Oracle received `Oracle, should artwork always go to China after licensor approval, or is Walmart an exception?` and posted `Can we clarify this process question: should artwork always go to China after licensor approval, or is Walmart an exception?` to Teams chat.
- During the same-link rejoin, temporary worker version `20260609.5` briefly added a `recall-live-bot-create` task so Codex could create the fresh Recall bot through Trigger's production env. The file was deleted and workers were redeployed as `20260609.6` with the normal 17 detected tasks.
- Safety state after testing: temporary settings were clamped off at `2026-06-09 17:34:23` (`max_oracle_interjections_per_hour=0`, `teams_live_recall_min_confidence_to_post=101`, all force flags `false`).

To restore normal gated live interjections later, use:

```sql
UPDATE settings
SET value = '3'::jsonb, updated_at = now()
WHERE key = 'max_oracle_interjections_per_hour';

UPDATE settings
SET value = '70'::jsonb, updated_at = now()
WHERE key = 'teams_live_recall_min_confidence_to_post';
```

To keep live interjections disabled, leave those clamp values as-is. To make sure temporary force settings are off:

```sql
UPDATE settings
SET value = 'false'::jsonb, updated_at = now()
WHERE key IN (
  'teams_live_recall_force_model_pass',
  'teams_live_recall_force_post',
  'teams_live_recall_disable_posting_limits'
);

UPDATE settings
SET value = '70'::jsonb, updated_at = now()
WHERE key = 'teams_live_recall_min_confidence_to_post';
```

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
