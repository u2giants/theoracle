---
issue: 255
status: OPEN
owner: teams-followup-checks-255
---

# Teams follow-through checks (#255) — part (b) done, part (a) waiting until after 2026-11-11

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

- **Nudging the 11 silent employees (recoverable-guess tier).** Eleven Teams-licensed employees have the Oracle app installed but have never opened a bot chat (list in §5). The bot may only write to someone who has messaged it first, and scheduled interviews are OFF per standing direction. Options: (a) wait — the Phase 3 interview tick (after 2026-11-11) may reach them once questions are scheduled, or (b) Albert asks them personally to say "hi" to The Oracle in Teams. Recommendation: (a) wait until the part (a) check on 2026-11-11; re-decide then. Blocks: nothing today; blocks any "reach 100% of employees" goal.
- **Already settled — do NOT re-ask:** interviews stay OFF until Albert turns them on (standing direction); canonical employee emails are @popcre.com (owner ruling 2026-11-02); OpenRouter cap $25/day (2026-10-30).

Put any new business question to the owner in ONE message, before starting work.

## 1. What this application is

The Oracle (https://github.com/u2giants/theoracle) is POP Creations' internal knowledge system: a Microsoft Teams bot interviews employees and a company-map "brain" turns their answers and meeting transcripts into a queryable map of the business. Owner: Albert Hazan (POP Creations). Stack: Next.js web app on Vercel (https://oracle.designflow.app), FastAPI brain on Coolify (app `oracle-brain` on the hetz host, http://hetz:8000/api/v1), production database = Supabase project "theoracle" (us-east-1), FalkorDB graph next to the brain. Tracking issue for the Teams build-out: https://github.com/u2giants/theoracle/issues/255

## 2. What we set out to do this session, and why

Handoff §6 Task 5 (Teams follow-through checks on #255), assigned to this nested session by the coordinator. Part (b), this round's done-when: the phase-4 install report said 7 Teams-enabled employees have no bot chat; re-run the install dry-run and check those users' installed apps, and post on #255 so each has a stored conversation or a known cause. Part (a) — check the interview tick log for Phase 3 done-when (scheduled questions sent to at least 3 employees in a week and at least one answer becoming a source) — is calendar-gated: only after 2026-11-11. Task is READ-ONLY: no brain deploy, no writes to prod.

## 3. Current state — what is true right now

- **Part (b) is DONE.** Findings posted on #255 at 10:04 PM EST 2026-11-04: https://github.com/u2giants/theoracle/issues/255#issuecomment-6648547659 — every account without a bot chat has a known cause (11 + 7 = 18 = 51 − 33), and all 51 accounts are verified to have the Oracle Teams app installed.
- **Install dry-run re-run** (~10:20 PM EST 2026-11-04, `dryRun: true` = counts only): `users: 51, installed: 0 (needed), already: 51, failed: 0`.
- **Live tenant split** (Graph + prod DB, same evening): 51 enabled @popcre.com accounts; 40 with a Teams license; 33 stored conversations in `cmap.teams_conversation`.
- **Part (a) is NOT started** — waiting on the calendar. Check only after 2026-11-11 (EST).
- **Code:** no application files changed. This handoff file is the only repo change; it ships on branch `teams-followup-checks-255` in a docs-only PR linked from issue #255 (see the issue timeline for the PR URL; do not assume it is merged — verify).
- Session progress notes (private, not in repo): `tasks/T2/progress.md` in this session's memory dir.

## 4. Everything we tried that did NOT work

1. **Vercel REST `GET /v9/projects/{id}/envs` (and v1/v2/v10 variants)** — HTTP 404 with both the Personal Access Token (1Password "Vercel Personal Access Token") and the CLI auth token, even though `GET /v9/projects/{id}` returns 200. Project envs are not readable this way.
2. **`vercel env pull` (CLI v65.11.0 and v33.2.0 on edge-dev3)** — writes `"[SENSITIVE]"` placeholders for 14 values: `AZURE_TENANT_ID`, `AZURE_GRAPH_CLIENT_ID`, `AZURE_GRAPH_CLIENT_SECRET`, `MICROSOFT_BOT_APP_ID`, `MICROSOFT_BOT_APP_PASSWORD`, `MICROSOFT_BOT_TENANT_ID`, `POSTGRES_PASSWORD/PRISMA_URL/URL/URL_NON_POOLING`, `RECALL_BASE_URL`, `RECALL_REALTIME_WEBHOOK_URL`, `SUPABASE_JWT_SECRET`, `SUPABASE_SECRET_KEY`. Vercel sensitive env values are effectively write-only. Real values DID come through for `DATABASE_URL`, `DIRECT_URL`, `BRAIN_SHARED_TOKEN`, `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`.
3. **Trigger.dev management API** with the admin PAT (1Password "Trigger.dev Personal Access Token (management)"): `GET /api/v2/whoami` 200, but `GET /api/v1/projects` empty and the Oracle workers project envvars endpoint → 404 "Project not found" (project ref is in that item's notes). Could not read worker env vars there.
4. **Azure CLI with the mailbox service-principal certificate** (app `07b6902d-741a-4897-9dc1-4f685faa550f`, 1Password "Azure CLI mailbox read — Albert"): login succeeds, but `GET /v1.0/users` → 403 `Authorization_RequestDenied` — that app is scoped to one mailbox and cannot list users or installed apps.
5. **`az rest` on edge-dev3** (there `az account show` is a delegated login as `Albert@popcre.com`, subscription "paygo for teams Oracle bot"): `GET /users?$select=...assignedPlans` works (that is how the Teams-license split was produced), but `GET /users/{id}/teamwork/installedApps` → 403 "Missing scope permissions" — the az CLI app has no TeamsAppInstallation scope. So per-user installed apps cannot be read via az; only the web app's own app-only token (TheOracle Entra app) can.
6. **`POST https://oracle.designflow.app/api/admin/teams/install`** — 404 on production: the route was deleted from the web app by the Oracle-2 cut refactor (PR #402, merged 11:51 AM EST 2026-11-04). The dry-run had to be re-run against an older deployment.
7. **The old #384 deployment** (`theoracle-axwjtbum9-popcre.vercel.app`) returns 401 "Protected by Vercel Authentication" without the project's automation-bypass header (`x-vercel-protection-bypass`, 1Password "Vercel automation bypass - theoracle S03 preview proof"). With it, the dry-run works.

## 5. Root causes and key findings

- **The phase-4 "7" was an arithmetic artifact.** The phase-4 comment computed 51 − 33 − 11 = 7 ("the other 7 have no conversation"), assuming all 33 conversations belonged to the 40 Teams-licensed accounts. Actually 4 unlicensed accounts also hold install-time greetings (all stored 10:52–10:53 AM EST Nov 4: Marcela Arboleda `marboleda@popcre.com`, Mauricio Casagrande `mcasagrande@popcre.com`, Vaibhav Barot `vbarot@popcre.com`, Zarit Calderon `zcalderon@popcre.com`). The true split of the 18 accounts with no bot chat:
  - **11 Teams-licensed, silent** (this is the "Teams-enabled employees have no bot chat" group): Andre Manoel `amanoel@popcre.com`, Catalina Arroyo `carroyo@popcre.com`, Claudia Cadena `ccadena@popcre.com`, Fabiola Tello `ftello@popcre.com`, Juan Lopez `jlopez@popcre.com`, João Melhorance `jmelho@popcre.com`, Jack Safdieh `jsafdieh@popcre.com`, Luis Herrera `lherrera@popcre.com`, Maria Williams `mwilliams@popcre.com`, Sergio Cortés `scortes@popcre.com`, Violette Avouac `vavouac@popcre.com`. Cause (same for each): Oracle app installed (verified per-account), Teams license present, accounts created June–October 2026 (before the install wave), yet the install-time conversationUpdate never stored a conversation and they have never messaged the bot. Zero errors were logged in the greeting path (32 of the 33 greetings landed in one minute).
  - **7 never-reachable** (no Teams license at all): Beckett Schiaparelli `bschiap@popcre.com`, Doug Hurt `dhurt@popcre.com`, Heather McGee `hmcgee@popcre.com`, Melissia Cartwright `mcartwright@popcre.com` (all four: deactivated accounts, all licenses removed); POP Design `design@popcre.com`, Hello POP `hello@popcre.com`, Jamielynn shared `jseguine@popcre.com` (shared/service mailboxes). Cause: no Teams client exists for them; the bot can never be reached.
- **How "Teams-enabled" is determined:** Graph `GET /users?$select=assignedPlans`, keep accounts where some plan has `service == 'TeamspaceAPI'` and `capabilityStatus == 'Enabled'` (this exact check yields 40, matching phase 4).
- **What "check those users' installed apps" means in practice:** the install route's dry-run iterates `GET /users/{id}/teamwork/installedApps?$expand=teamsApp,teamsAppDefinition($expand=bot)` for every enabled @popcre.com user and matches the bot id (`MICROSOFT_BOT_APP_ID`). `already: 51` on the re-run is the per-account app check — none of the 11 or the 7 is missing the app.
- **Where each credential lives** (values never in chat or repo): Vercel project env (AZURE_*, MICROSOFT_BOT_*, BRAIN_SHARED_TOKEN, DB URLs — but sensitive ones are write-only there), 1Password `vibe_coding` vault (BRAIN_SHARED_TOKEN item, Supabase direct-URL item, Vercel PAT, Vercel automation bypass, Coolify tokens, Trigger.dev PAT), and edge-dev3's az CLI delegated session for directory reads.

## 6. Exact next steps

1. **After 2026-11-11 (EST) — the part (a) check.** Verify the interview tick log for the Phase 3 done-when: at least 3 scheduled questions sent to employees within one week AND at least one answer became a source. How: read the prod DB (`cmap.open_question` where `state`/`asked_at` shows sends in the last 7 days; `cmap.interview_send` has per-employee sends; an answer that became a source is an `open_question` row with `answer_source_id` set and a matching `cmap.source` row), or call the brain's admin `GET /interview/overview` with the service token plus an admin `x-user-id`. Post the result as a comment on https://github.com/u2giants/theoracle/issues/255 signed `Posted by MiMo chat <session id> on <machine>`. You'll know it worked when the #255 comment states the counts and pass/fail against both thresholds.
2. **If the owner (see §0) chooses to nudge the 11 silent employees:** each must first say "hi" (or any message) to The Oracle bot in Teams — that stores the conversation reference and unlocks proactive replies. Interviews remain OFF unless the owner turns them on. You'll know it worked when `cmap.teams_conversation` count rises from 33 and the new rows cover the nudged emails.

## 7. Constraints and gotchas in force

- **READ-ONLY for this task.** No brain deploy, no prod writes. Also: never redeploy the brain while `cmap.job` has rows in `('running','queued')` (any future task that deploys must check `select kind,state from cmap.job where state in ('running','queued')` first).
- **Public repo hygiene** (u2giants/theoracle): no secrets, no LAN IPs, no internal project references in code, commits, issues or PRs. Employee work emails and first/last names are already the established style in this repo's docs and issues.
- **Never push to `main`.** Branch + PR + `gh pr merge --squash --admin`. Docs-only PRs must pass `bin/ai-doc-safety` on the exact head before merge.
- **Interviews stay OFF** (standing owner direction). The outbound ask tick gates itself; nothing here turns it on.
- **Sign every GitHub post** with `Posted by MiMo chat ses_ffe5e5693ac50ffeNneop6UCvq on edge-dev` (or the actual session/machine of the future session).
- **All human-facing times in EST** (America/New_York).
- **OpenRouter:** this session made zero LLM calls; the $5 floor rule (stop under $5 remaining) was not approached.

## 8. Access and environment

- `gh` authenticated as `u2giants` (from edge-dev and edge-dev3).
- **edge-dev3** (`ssh edge-dev3`, Linux, user `ahazan`): its `az` CLI holds a **delegated login as `Albert@popcre.com`** — good for Graph directory reads (`/users`, `assignedPlans`) but NOT for `teamwork/installedApps` (scope 403) and not a service account; if it expires, a re-login is needed and that is a `Blocked —` item to report (never ask Albert to click; report it).
- **Vercel CLI auth** on edge-dev3: `~/.local/share/com.vercel.cli/auth.json`; refresh it with `npx --yes vercel@latest whoami` in a directory whose `.vercel/project.json` points at the theoracle Vercel project (ids are in the 1Password "Vercel CLI auth" and "Vercel Personal Access Token" items). Useful for `vercel env pull` (non-sensitive values only) and deployments listing via REST with the PAT.
- **1Password vault `vibe_coding`** (via MCP `op_run` with `op://` refs, never raw values): "Oracle Brain shared token - The Oracle (BRAIN_SHARED_TOKEN)", "Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle)" (the `password` field IS the connection string), "Vercel Personal Access Token", "Vercel automation bypass - theoracle S03 preview proof", "Coolify API token - Oracle read-only observer", "Trigger.dev Personal Access Token (management)", "Azure CLI mailbox read — Albert" (mailbox-scoped cert, not usable for user reads).
- **Coolify API** `http://hetz:8000/api/v1` (reachable from edge-dev and edge-dev3): app `oracle-brain` (uuid in the Coolify token item notes / coordinator brief); brain logs are on that app.
- **Prod DB**: Supabase "theoracle" via the direct URL from 1Password (read-only queries only for this task).

## 9. Open questions and risks

- **(2026-11-04) Why did 11 licensed users get no conversationUpdate?** The install route stores a conversation reference for every personal-scope "bot added" event; 33 arrived in one minute, these 11 produced none, and no errors were logged. Likely Teams-side delivery/propagation (users not signed into Teams since provisioning), but unproven. If they stay silent after Phase 3 questions start, this becomes a real gap.
- **(2026-11-04) The 4 unlicensed-but-connected accounts** hold conversations although their assignedPlans show zero enabled services today. Either their licenses changed after Nov 4 or conversationUpdate delivery does not require a license. Harmless either way; noted so a later session does not "fix" it.
- **(2026-11-04) The prod install route is gone** (cut by #402 along with `apps/web/lib/teams-proactive-install.ts`). If tenant-wide re-install is ever needed again, it must either be restored in code or done per-user via Graph with the TheOracle app's credential. The old #384 deployment URL will not live forever.
- **(2026-11-04) Part (a) outcome unknown** — by design; the tick log check happens after 2026-11-11 and its result (pass or fail) must be posted on #255.

---

Self-audit (handoff-writer gate): all 10 sections present (§0 has the one owner decision and the settled list; §4 lists 7 dead ends with why; §5 has the corrected split with names/emails and the Teams-enabled definition; §6 has 2 numbered steps with verification gates; §8 lists every access path by vault item/location, no values; every file/URL reference is a GitHub or public URL — no machine-local paths). The four audit answers are preserved in the closing report.
