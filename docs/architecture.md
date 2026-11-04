# Architecture

System design for The Oracle Company Map. Current plan and status:
`plan_oracle_company_map.md` (read STATUS first). Developer map: `AGENTS.md`.

Oracle 2 and the old workers were removed in #398 (2026-11-04): the old chat,
claims review, Trigger.dev workers, provider-adapter package, deterministic
engines package and Oracle 2 Python foundation no longer exist. Older sections
of this file describing them were deleted; see git history if needed.

## Components

- `apps/web` — Next.js on Vercel. Login (Supabase Auth), `/admin/employees`,
  the Company Map pages under `/map/*`, the `/api/brain/*` proxy to the brain
  service, the Teams bot endpoints `/api/teams/bot/*`, and the Recall endpoints
  `/api/teams/live/start` and `/api/teams/live/recall`. Login lands on `/map`.
- `apps/brain` — Python FastAPI service (the Company Map "brain"): source
  reading and extraction, entity resolution, graph, answers, interviews,
  recommendations, evals and model settings. Runs on Coolify; its Coolify
  service is named `oracle-brain` and its image is
  `ghcr.io/u2giants/theoracle-brain`.
- `packages/auth` — Supabase session → employee linker.
- `packages/db` — Drizzle schema and migrations for the Supabase Postgres database.
- `packages/shared` — shared TypeScript types and helpers.

```
Browser ──> apps/web (Vercel) ──/api/brain/*──> apps/brain (Coolify)
                 │                                   │
                 └──────── Supabase Postgres ────────┘
Teams ──> Azure Bot ──> /api/teams/bot/messages ──> Recall bot
Recall ──> /api/teams/live/recall ──> finished transcript recorded as a
           Company Map `transcript` source (via the brain)
```

## Teams live meetings (Recall.ai)

An admin (`POST /api/teams/live/start`) or a Teams user (`@The Oracle join
<meeting link>`) creates a Recall.ai bot for the meeting. Recall posts signed
events to `/api/teams/live/recall`; the route verifies the signature, returns
202, and when Recall reports a finished transcript (`transcript.done` or
`bot.done`) records the final transcript in the brain as a `transcript` source.

## Teams-native command wrapper

The Recall listener itself cannot be invited from the Teams people picker as an internal employee. To let employees initiate it from Teams, The Oracle also exposes a Bot Framework endpoint:

```
Teams user adds The Oracle app to a meeting/chat
  ↓
@The Oracle join <Teams meeting link>
  ↓
Azure Bot Service -> /api/teams/bot/messages
  • verifies Bot Framework auth via MICROSOFT_BOT_APP_ID/PASSWORD
  • strips the @mention and parses join/listen/start commands
  • uses Teams meeting context for joinUrl when available
  • otherwise asks the user to include the meeting link
  • creates the Recall live bot
```

So the user-facing flow originates inside Teams, while the live audio/STT work is still performed by Recall.

Current production wiring (2026-06-09): Azure Bot resource `theoracle-popcre-teams-bot` routes the Microsoft Teams channel to `https://oracle.designflow.app/api/teams/bot/messages`; the Teams organization app `The Oracle` is uploaded with app id `17ccd7a1-b90b-428c-9966-33e7fb832923`. This does not replace Recall.ai for live audio/STT; it only provides the native Teams command surface.

## Identity model

One human → one `employees` row → many `employee_identities` rows.

- `employees.email` is the **primary contact** for the human (used for display, admin contact, and first-login bootstrap).
- `employee_identities` is the authoritative source for `(auth_provider, auth_user_id)`. Supabase Auth identifies the user; the linker maps that Supabase user to the employee row through this table.
- The linker resolves a session by `(auth_provider, auth_user_id)` first. On miss it bootstraps by matching the verified provider email against `employees.email` OR any existing `employee_identities.email` row, then creates a new identity. See `packages/auth/src/link.ts`.
- The RLS helper `current_employee_id()` joins `employees` with `employee_identities` on `auth.uid()` — RLS does not read `employees.auth_user_id` directly.
- `employee_identities` is the only identity source in the current schema and production database. Rerun-safe raw migration `98_drop_deprecated_employee_identity_columns.sql` removed the old `employees.auth_user_id`, `employees.auth_provider`, and `employees.auth_provider_subject` fields in release `30eed14` on 2026-07-29. A second full migration run and protected post-drop login both passed. The verifier supports both the all-present pre-drop state and the all-absent post-drop state, and fails loudly on partial state. See `DECISIONS.md` D2.multi-identity.
- `employees.departments text[]` (multi-value, authoritative) replaces `employees.department varchar` (single-value, nullable, deprecated). All new code reads `departments`; legacy code falls back to `department`.
- Employee removal is a soft-disable: Admin -> Employees writes `employees.disabled_at` through `updateEmployeeAccess()`. Disabled employees cannot link or continue sessions (`packages/auth/src/link.ts`, `apps/web/lib/auth-guard.ts`, and RLS helpers check `disabled_at IS NULL`), but historical references remain intact. Do not hard-delete employees from the GUI without a separate archival/reference-cleanup design.

