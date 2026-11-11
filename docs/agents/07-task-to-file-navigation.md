---
summary: "AGENTS.md section 7: for each common change (database field, admin page, auth, env, model picker) which files to touch and which to avoid."
kind: living
status: current
read-when: about to edit source and need to know which files a change belongs in
---

<!-- Moved verbatim from AGENTS.md (issue #22). AGENTS.md is the router. -->

## 7. Task-to-file navigation: what to edit for common changes

Oracle 2 and the old workers were removed in #398 (2026-11-04); rows that pointed at the deleted code were removed.

| Task | Files to touch | Files not to touch |
|---|---|---|
| Add a database field or table | `packages/db/src/schema.ts`, new file under `packages/db/migrations/sql/` if hand-written SQL is needed, generated Drizzle migration if schema changed. Ship through `pnpm db:migrate` only — never via Supabase MCP `apply_migration` or `drizzle-kit push`, both bypass the journal. Run `pnpm db:check-drift` if unsure of state. | previously applied migration files; `drizzle.__drizzle_migrations` directly |
| Add an admin page | `apps/web/app/admin/**`, possibly `packages/db/migrations/sql/*.sql` for a new admin view | RLS helpers unless policy changes are truly required |
| Change auth/linking behavior | `packages/auth/src/**`, `apps/web/app/auth/**`, `apps/web/app/_components/login-form.tsx` | direct edits to Supabase-managed auth tables |
| Add or change env/config | `.env.example`, `turbo.json`, `docs/configuration.md`, consuming code | `.env.local` in git |
| Add or change model picker stage requirements / job briefs | `apps/web/lib/stage-requirements.ts` (shared requirement predicates), `apps/web/app/admin/settings/page.tsx` (role descriptions + Copy job brief text), `docs/configuration.md`, `docs/architecture.md` if behavior changes | provider inference adapters unless runtime dispatch changes |
| Reorder or regroup admin nav | `apps/web/app/admin/_components/admin-nav.tsx` (GROUPS array + isActive helper). Layout wrapper stays server-rendered for auth. | `apps/web/app/admin/layout.tsx` other than the AdminNav import — auth still runs there |
| Change the meeting picker / discovery | `apps/web/app/admin/transcripts/page.tsx` + `_actions.ts` (`ingestMeetings`/`dismissMeeting`/`runDiscoveryScan`, admin-only) over the `meeting_transcripts` table (migration `77_meeting_transcripts.sql`); discovery sources = the webhook (real-time, `discovered_via='subscription'`) and `teams-transcript-discovery-scan` (past meetings, `'scan'`), both metadata-only upserts; picking → `triggerTask('teams-transcript-ingestion', {…, discoveryTranscriptId})` which flips the row to `ingested`. NOTE: the older `awaiting_approval` enum value + `raw_transcripts.approval_status` (migrations 75/76) are now DEPRECATED/unused — see DECISIONS `D-meeting-picker`. | the live Recall path (`teams-live-recall-utterance.ts`); re-introducing auto-ingest in the webhook |
| Set an employee's reader language (China group) | `apps/web/app/admin/employees/page.tsx` ("Language" column) + `_components/employee-locale-form.tsx` + `_actions.ts` (`updateEmployeeLocale`). Writes `employees.locale` (`en`/`zh-CN`, validated vs `SUPPORTED_LOCALES`). This is the single switch the whole bilingual layer keys off — editable in the UI now, not SQL-only. Forward-looking (no retroactive translation). | the auth/identity tables |
| Show which claims are out for review / to whom | `apps/web/app/admin/claims/page.tsx` — derived live from open `claim_review_question` gaps (`gaps.related_claim_ids ? claim.id`, status in `open/queued/asked`), NOT a column on `claims`. The bulk "Ask selected to evaluate" checkboxes are UI-gated to `pending_review` rows, but `assignClaimQuestionCore` has no status gate. | adding a denormalized column on `claims` (the gap rows are the source of truth) |
| Change claims grouping / checkbox range-select | `apps/web/app/admin/claims/page.tsx` — claims are grouped by specific source (channel/meeting, document, external, or manual), derived in the evidence `LATERAL` (`source_group_key/label/kind`); rows arrive newest-first so first-seen key orders groups. Shift-click range select is a pure-DOM client enhancer `_components/shift-select.tsx` keyed off `data-select-form`/`data-select-index` (ranges never cross the `bulk-evaluate`/`translate-claims` form boundary). | the form-based submission model (checkboxes stay server-rendered + `form=`-associated) |

