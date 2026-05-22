# HANDOFF — The Oracle

Live in-flight state. A new contributor (human or AI) should be able to read this top to bottom and pick up exactly where the previous session left off — no need to scrape conversation history.

**Snapshot date:** 2026-05-21
**Latest commit on `main`:** Phase 5 dashboards commit (see commit log below)
**Latest successful Vercel production deploy:** auto-deploys on push; check https://vercel.com/popcre/theoracle for current URL
**Repo:** https://github.com/u2giants/theoracle (**PUBLIC** — never commit secrets)
**Local checkout:** `C:\repos\oracle` on Windows 11, NTFS volume
**Active branch:** `main`

---

## TL;DR

- Phases 1–4 are **complete and deployed**. Phase 5 (admin review dashboards) is the next build. Phase 6 (interjection engine) follows that.
- Workers are live on Trigger.dev (version `20260521.1`, 7 tasks). They will fire on the cron schedule once messages/documents exist. No data has been processed yet — all intelligence tables are empty.
- Admin → Settings has three role-specific model pickers (interview / extraction / synthesis) with correct capability icon detection from the OpenRouter API.
- **No active blockers.** The dev server runs cleanly. Google OAuth + Microsoft 365 SSO are live. All three worker tasks are deployed and scheduled.
- Phase 5 admin dashboards are now **live** (Claims, Gaps, Contradictions, Brain). All four pages replace their placeholders with full server-component UIs backed by `getDirectDb()`. Server actions handle approve/reject (claims), resolve/stale (gaps), confirm/dismiss (contradictions).

---

## Read this in order

1. **`HANDOFF.md` (this file)** — current state, what's done, what's next.
2. **`AGENTS.md`** — the developer guide. §11 "Idiosyncratic decisions" is the most important section.
3. **`DECISIONS.md`** — assumption log with citations.
4. **`oracle_master_spec.md`** — authoritative product spec.
5. **`docs/architecture.md`** — system diagram + data-flow.

---

## Phase status

| Phase | Status | Wet-tested? |
|---|---|---|
| 0 — Bootstrap | done | n/a |
| 1 — Foundation (schema, RLS, auth, seed) | done | **YES** — Google + M365 SSO end-to-end; denial flow verified. |
| 2 — Realtime chat + document upload + admin dashboard | code complete | **Partially.** Oracle DM chat fully wet-tested. Phase 2 RLS isolation not yet verified with a second employee. |
| 3 — Oracle chat route (`POST /api/chat`) | **done + wet-tested** | **YES** — Oracle replies end-to-end. 6.3 s latency. Oracle also fires after document uploads. Vision part stripping for text-only models. Error surfacing in UI. |
| 4 — Trigger.dev workers | **deployed** — version `20260521.1`, 7 tasks | n/a — workers will process real data on cron schedule; check `job_runs` after first run |
| 5 — Admin review dashboards (claims, gaps, contradictions, brain) | **placeholder pages only** | n/a — this is the next build |
| 6 — Interjection engine | empty module with JSDoc | n/a — depends on Phase 5 + real claims |

---

## What was built or fixed in the most recent sessions

### Session (2026-05-21) — Phase 5 admin review dashboards

1. **Claims dashboard** (`apps/web/app/admin/claims/`): Full table view of all claims with lateral join to primary evidence and employee name. Status filter tabs (Pending review / Approved / Rejected / All). Approve and Reject server actions update `claims.status` and revalidate.

2. **Gaps dashboard** (`apps/web/app/admin/gaps/`): Table of gaps with priority and status badges. Filter tabs (Open / Queued / Asked / Resolved / All). Resolve and Stale server actions.

3. **Contradictions dashboard** (`apps/web/app/admin/contradictions/`): Card-per-contradiction layout showing both claim summaries side-by-side, severity/confidence, and suggested follow-up question. Filter tabs (Possible / Open / Resolved / All). Confirm (possible→open) and Dismiss server actions.

4. **Brain dashboard** (`apps/web/app/admin/brain/`): Card-per-section layout showing title, domain, category, version number, review status badge, full markdown content in a scrollable code block, and timestamps. Read-only for now — re-synthesis trigger is Phase 6.

5. **Server actions** (`_actions.ts` files in each dashboard folder) — all use `'use server'`, `getDirectDb()`, and `revalidatePath`.

### Session (2026-05-21) — Oracle fixes + admin model picker

1. **Oracle silent after document uploads** (`ad9c182`): `DocumentUpload.onDone` now calls `fetchOracleReply`. In DMs always fires; in group chats only when caption starts with `@oracle`.

2. **Oracle failing on second message after image upload** (`0b779c8`, `e70059c`): Root cause was Supabase Storage downloads running for text-only models even though the bytes were discarded. Moved `visionCapable` detection before the attachment query; text-only models skip the Storage download entirely.

3. **Oracle errors were silent** (`0b779c8`): Added `oracleError` state and an inline red bubble in the chat UI. When `POST /api/chat` fails, the error is shown to the user.

4. **Concurrent Oracle calls (race)** (`0b779c8`): `oracleFetchingRef` ref-based lock prevents upload `onDone` and `sendMessage` from triggering simultaneous Oracle calls.

5. **Admin model picker** (`eb03b44`): Custom searchable dropdown replacing native `<select>`. Shows model ID, capability icons (vision, tools, file input, reasoning, image gen), price badges ($/1M in/out), and a selected-model detail card. Full icon legend.

6. **Three model roles in Admin → Settings** (`edba686`): Expanded settings page from one to three model pickers: interview (real-time chat), extraction (async claim extraction), synthesis (brain section synthesis). Each role has a description, requirement chips, and a `ModelPicker`.

7. **Tool use capability detection broken** — two fixes:
   - First attempt (`104c991`): Added `TOOL_CAPABLE_PATTERN` regex as fallback. Was insufficient.
   - Correct fix (`9e4c433`): OpenRouter uses `architecture.input_modalities` (array), `architecture.output_modalities` (array), and `supported_parameters` (array with `"tools"`, `"tool_choice"`, etc.) — NOT `architecture.modality` string or `supported_generation_params`. Switched proxy from `/models/user` to `/models` (user endpoint strips capability metadata).

8. **Capability icons on role cards** (`87e1f09`): Each model role card now shows which capability icons are *required* (wrench for tool use, eye for vision, etc.) — extracted to `_components/caps.tsx` shared between server page and client picker.

---

## Commit log (this session and recent prior sessions)

| Commit | What it did |
|---|---|
| _(this session)_ | feat(phase-5): claims, gaps, contradictions, brain dashboards with server actions |
| `87e1f09` | feat(admin): required capability icons on each model role card; shared caps.tsx |
| `9e4c433` | fix(admin): correct OpenRouter capability field names (`input_modalities`, `output_modalities`, `supported_parameters`); switch to `/models` endpoint |
| `104c991` | fix(admin): tool-use icon detection attempt (superseded by 9e4c433) |
| `edba686` | feat(admin): three model pickers in settings (interview, extraction, synthesis) |
| `eb03b44` | feat(admin): rich model picker with capability icons, prices, legend |
| `0b779c8` | fix(phase-3): skip Storage downloads for text-only models; surface Oracle errors; race lock |
| `ad9c182` | fix(phase-3): trigger Oracle reply after document uploads |
| `e70059c` | fix(chat): strip image/file parts for text-only models |
| _(prior)_ | feat(phase-4): Trigger.dev workers deployed (claim-extraction, document-ingestion, contradiction-watcher, brain-synthesis) |
| _(prior)_ | feat(phase-3): Oracle chat route, tools, system prompt |
| _(prior)_ | feat(phase-2): channels UI, document upload, admin dashboard skeleton |
| _(prior)_ | feat(phase-1): full schema, RLS, auth, seed |

---

## The exact next action

**Build Phase 6 — Interjection engine.**

Phase 5 dashboards are live. The next build is the interjection engine at `packages/oracle-engines/src/interjection.ts`. It needs:
- Lull detection (no messages for N minutes in a channel)
- Contradiction live-interjection (Oracle interjects when a new message triggers a known contradiction)
- Cooldown logic (don't interject too frequently)
- Should write rows to `oracle_interventions` and optionally create a `gaps` row

**Resume prompt for a fresh session:**

> I'm continuing work on The Oracle. Read HANDOFF.md at the repo root first, then AGENTS.md, then DECISIONS.md. Phases 1–5 are complete and deployed. Phase 6 (interjection engine) is next. The scaffold exists at `packages/oracle-engines/src/interjection.ts`. It hooks into the real-time chat flow and the contradiction-watcher worker. It must write rows to `oracle_interventions` and optionally create `gaps` rows.

---

## Current database state

**`employees` table** (2 rows):

| email | name | role | is_admin |
|---|---|---|---|
| `u2giants@gmail.com` | Albert H. | Lead Architect | true |
| `test-employee@oracle.local` | Test Employee | Production Coordinator | false |

**`employee_identities`** (2 rows, both Albert):

| auth_provider | identity_email | auth_user_id |
|---|---|---|
| `google` | `u2giants@gmail.com` | `e0968007-7276-46fb-8abd-25baa108f112` |
| `microsoft` | `albert@popcre.com` | `751efc6f-b030-43cf-9f22-8e82ac389771` |

**Intelligence tables** — `claims`, `claim_evidence`, `gaps`, `contradictions`, `model_runs`, `job_runs` (for workers), `brain_sections`, `brain_section_versions` — all **empty**. Workers will populate them on the cron schedule once real messages/documents exist.

**`settings`** — 8 rows seeded. Notable model defaults:
- `default_interview_model` = `deepseek/deepseek-v4-pro`
- `default_extraction_model` = `google/gemini-2.5-flash`
- `default_synthesis_model` = `anthropic/claude-sonnet-4.6`

---

## Open items

### High value, low friction

1. **Replace `test-employee@oracle.local`** with a real mailbox (e.g. `u2giants+test@gmail.com`) so Phase 2 RLS can be wet-tested with two real logins.
2. **Wet-test Phase 2 RLS** — requires item 1 first. Recipe in this file below.
3. **Rotate the Vercel token** from the overnight transcript: https://vercel.com/account/tokens
4. **Drop deprecated `auth_user_id` / `auth_provider` / `auth_provider_subject` columns** from `employees` after a soak period. New migration `42_drop_legacy_auth_columns.sql`.

### Medium value, medium friction

5. **Enable HNSW vector indexes** — `ORACLE_RUN_VECTOR_INDEXES=1 pnpm db:migrate`. Worth running once claims + document_chunks have embedding data.
6. **CI: migration job** (`migrate.yml`) gated on manual approval.
7. **CI: workers deploy** (`workers-deploy.yml`) triggered on pushes to `apps/workers/`.

### High value — the actual next work

8. **Phase 5 — Admin review dashboards** (see "exact next action" above).
9. **Phase 6 — Interjection engine** — scaffold at `packages/oracle-engines/src/interjection.ts`. Depends on Phase 5 + real approved claims.
10. **Wire Authentik OIDC** as a third login provider.
11. **Admin identity management UI** — link/unlink employee identities from the admin panel.

---

## Risks and unknowns

- **Intelligence tables are empty.** Workers are deployed but no data has flowed through the pipeline yet. First `job_runs` rows will appear after the claim-extraction cron fires (every 4 hours) once messages with `extraction_status='pending'` exist.
- **Phase 5 dashboards don't exist yet.** Claim approval is the gate for synthesis — without approving claims, brain sections can never be generated. This is the most important missing piece.
- **Deprecated auth columns still queryable.** Any code that reads `employees.auth_user_id` gets NULL and may misbehave silently. `AGENTS.md §11` calls this out. Mitigated by: no new code reads those columns.
- **`test-employee@oracle.local` is not a real mailbox.** Phase 2 RLS cross-channel isolation test is blocked until this is replaced.
- **Vercel token in build transcript.** Rotate at https://vercel.com/account/tokens before sharing repo access.

---

## Phase 2 wet-test recipe

Prerequisites: a second loginable employee.

```sql
-- In Supabase SQL Editor:
UPDATE employees
SET email = 'u2giants+test@gmail.com', name = 'Test (Albert alias)'
WHERE email = 'test-employee@oracle.local';
```

Sign in once via Google as `u2giants+test@gmail.com` to provision its identity.

```sql
-- Create a test channel that ONLY the test alias is a member of.
WITH new_channel AS (
  INSERT INTO channels (name, is_group_chat, status)
  VALUES ('rls-test-channel-alias-only', false, 'active')
  RETURNING id
)
INSERT INTO channel_participants (channel_id, employee_id)
SELECT new_channel.id, employees.id
FROM new_channel, employees
WHERE employees.email = 'u2giants+test@gmail.com';
```

Then:

1. Sign in as `u2giants@gmail.com` (admin). The new channel should **not** appear in the sidebar (admin is not a participant).
2. Open `/admin` → Channels tab. The new channel **should** appear (admin service-role reads).
3. Sign out, sign in as `u2giants+test@gmail.com`. The new channel **should** appear.
4. As the alias, post a message. As admin, sign back in — message should **not** be visible in the user-facing chat; **should** be visible in `/admin/messages`.

All four checks passing = RLS is correctly isolating.

---

## Credentials map

| Item | Where | Rotation |
|---|---|---|
| GitHub repo | `u2giants/theoracle` (PUBLIC) | SSH keys managed locally |
| Vercel project | `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | Auto-deploys from `main` |
| Vercel token | https://vercel.com/account/tokens | **Rotate** — one was exposed in overnight transcript |
| Supabase project | URL in Vercel env | Supabase → Settings → API → Reset |
| Supabase Storage bucket | `company_documents` (private) | Confirmed created |
| Brevo (SMTP) | Account on file | Brevo → SMTP & API → revoke + regenerate; update Supabase Auth SMTP |
| Google OAuth client | Google Cloud Console | Recreate; update Supabase → Auth → Providers → Google |
| Microsoft Entra app | popcre tenant | Recreate client secret in Entra; update Supabase → Auth → Providers → Azure |
| Trigger.dev project | `proj_wgpzsvhmsopqhvwqaycn` | `TRIGGER_SECRET_KEY` in Vercel + Trigger.dev dashboard |
| OpenRouter | `OPENROUTER_API_KEY` in Vercel | https://openrouter.ai/keys |
| OpenAI | `OPENAI_API_KEY` in Vercel | Optional — embeddings only |

---

## When to delete this file

Delete once **all** of these are true:

- Phases 4, 5, and 6 are landed and wet-tested.
- Deprecated `auth_*` columns on `employees` are dropped.
- CI is fully wired (pr-check + migrate + workers-deploy).
- All items in AGENTS.md §15 are resolved or moved to a real backlog.

Until then, **keep this file current** — update it at the end of every session with material progress.
