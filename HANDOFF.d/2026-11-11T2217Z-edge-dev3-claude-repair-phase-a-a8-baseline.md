---
issue: 520
status: OPEN
owner: claude/repair-a8-handoff
---

# Handoff — Oracle repair Phase A is live; A8 rebuild is running, baseline score not yet recorded (2026-11-11)

Written 2026-11-11, 5:20 PM EST, edge-dev3, Claude (Fable 5.2).
Plan (read its STATUS table first; do not re-derive or re-plan):
[plan_oracle_repair_and_consultant_upgrade.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_repair_and_consultant_upgrade.md).
Program issue: https://github.com/u2giants/theoracle/issues/520.
This file replaces the predecessor baton `HANDOFF.d/2026-11-11T1247Z-edge-dev3-claude-oracle-repair-plan.md` (retired in the same commit under the successor rule; its text is in git history at https://github.com/u2giants/theoracle/blob/58a3cb0d/HANDOFF.d/2026-11-11T1247Z-edge-dev3-claude-oracle-repair-plan.md).

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

Albert was shown this list on 2026-11-11 and has not answered; work is proceeding on the recommended defaults. Put the whole list to him again in ONE message only if a step needs a different answer. Nothing here blocks Phase A or B.

**A wrong guess is recoverable (work proceeds on the default):**
- **The list of business functions the Oracle sorts knowledge into** (step C1). Recommendation: accept the 13 proposed in the plan; he renames or merges them on the site.
- **Who is on the licensing team** (from issue #474). Recommendation: let the Oracle derive it from the staff directory and documents.
- **Who receives the Monday briefing** (step I4). Recommendation: Albert only.
- **How old a fact must be before it is marked "possibly out of date"** (step D4). Recommendation: 18 months for who-does-what, 36 months for rules.
- **Approve the test questions on the Oracle site's eval page** (step B1). Recommendation: approve the drafts as written.

**Blocks one step (J1 only):**
- **Which business numbers the Oracle should read first, and from which system.** Recommendation: order-to-ship lead times and late shipments.

**Already settled — do NOT re-ask:** everything in the plan's §8 "Locked" list (2026-10-27 no per-fact approval / no extra permissions / graph database stays; 2026-10-30 model seats; 2026-11-10 weekly interview quota stays and eval questions are approved on the site; 2026-11-11 knowledge is segmented by business function). The interview bot stays off until issue https://github.com/u2giants/theoracle/issues/518 says otherwise. On 2026-11-11 Albert's words "Done for this session when Phase A is merged, deployed, and the A8 baseline score is recorded" were used as the authorization for the production actions listed in §3.

## 1. What this application is

**The Oracle** — POP Creations' company adviser. It reads company documents, diagrams and meeting transcripts, interviews employees over Microsoft Teams, builds a Company Map of how work flows, answers questions with sources, and recommends changes. Web: https://oracle.designflow.app (Vercel, `apps/web`). Brain: https://oracle-brain.designflow.app (Coolify application `oracle-brain`, uuid `uge6pfm4qapktivto4981mtg`, Python, `apps/brain`). Repo https://github.com/u2giants/theoracle (public). Data: the Oracle's own Supabase project, schema `cmap`; the FalkorDB graph `company` is rebuilt from it. Vocabulary is in the plan §2 (source, chunk/passage, mention, entity, relation, community, graph_version).

## 2. What we set out to do this session, and why

Albert: "Goal: repair the Oracle and build the consultant upgrade … execute the plan starting at step A1 … Done for this session when Phase A is merged, deployed, and the A8 baseline score is recorded; tick issue #520 only with live proof." Phase A ("stop the bleeding") fixes the confirmed causes of the 0.38 self-test score: stale summaries fed to answers, silently lost reading, a passage splitter that dropped text.

## 3. Current state — what is true right now

**Merged to `main` and deployed (web verified at its version path; brain pinned in Coolify and healthy):**
- https://github.com/u2giants/theoracle/pull/523 — A1 (answers read only the current map version; old summaries pruned) + Markdown-only pull requests skip the web build, the AI review and the Vercel build.
- https://github.com/u2giants/theoracle/pull/524 — A2–A7 and the code half of A8.
- https://github.com/u2giants/theoracle/pull/528 — the brain applies its `cmap` schema at start-up; the empty-reply rescue retry no longer sends OpenRouter's `reasoning` parameter to Meta's API.
- Brain image tag live: `7ae581aa49fcff67a6babb4dadca6d6d11d3e622` (Coolify env `BRAIN_IMAGE_TAG`; previous good tag for rollback `3c7e2e39d318aebfd080a3d65512cb68edf00ec2`). Coolify deployment `aq0lbrd1mugnmcndbrgwme1m` finished; `/health` returned `{"ok":true,"db":true,"graph":true}` at 12:07 PM EST.
- SQL files `016_read_states.sql`, `017_source_read_notes.sql`, `018_answer_source_set_null.sql` are applied to production (by `python -m brain.migrate` through the session pooler at 11:04 AM EST; verified by reading the constraint and columns).

**Production actions taken through the deployed brain API (11:04 AM EST):** `POST /eval/run`, `POST /jobs/retry-failed` (7 old failed jobs requeued), `POST /sources/reread-all` (57 sources).

**A8 rebuild — IN PROGRESS, not finished.** Numbers read from production (Supabase MCP, read-only):

| | Before (10:42 AM EST) | Latest (4:22–5:07 PM EST) |
|---|---|---|
| Sources | 57, all `read` | 58 (one new source arrived mid-run): 57 `read`, 1 `extracting` |
| Passages (chunks) | 303 | 314 (after re-read of the 57) |
| Mentions | 4,832 | 4,994 |
| Entities | 2,070 | being rebuilt by `resolve` (1,586 at 5:07 PM, 1,427 mentions still unresolved) |
| Relations | 2,311 | 2,771 |
| Stored summaries level 0 / 1 / 2 | 1,417 / 1,178 / 23 | 113 / 107 / 12 after the first pruned build (11:22 AM); current version has 39 / 32 / 1 |
| Failed jobs | 7 | 0 |
| Failed passages (`cmap.extraction.error`) | n/a | 0 (13 appeared before #528 was deployed, all cleared by the re-read) |
| Self-test mean | 0.378 (graph v32, 2026-11-10) | 0.422 (graph v35, 12:03 PM EST — after A1 and one rebuild, BEFORE the re-read; this is not the A8 baseline) |

At 5:07 PM EST the job queue held: `resolve` running; queued `classify_extract` (the new 58th source), `recommend`, `directory_sync`, 2 `interview_tick` (no-ops, bot off), 2 `ensure_chain`. After `resolve` come `project` then `communities` then `recommend`, each queued by the one before.

**Not done:** the two self-test runs after the rebuild; `docs/verification/repair/A8-baseline.md` (does not exist yet); STATUS rows A1–A8 are 🟡 not ✅; issue #520 Phase A box is unticked.

**Branches:** everything is on `main`. No unmerged work. Local test containers `repairA-pg` / `repairA-fk` on edge-dev3 are disposable.

## 4. Everything we tried that did NOT work

- **Assuming the brain applies SQL at start-up (the plan said so).** It did not: the Phase A image went live at 11:03 AM EST without SQL 016–018; a re-read would have violated the old `read_state` check. Caught one minute later by reading the constraint; applied by hand; fixed for good in #528.
- **Requeueing the 7 old failed jobs before the re-read.** Their older `created_at` put them at the front of the single worker's queue, so an old full `communities` build and five old `relations` jobs ran first (~70 minutes), and those relations jobs hit the Meta `reasoning` 400 fault on the old build, leaving 3–4 sources `partial` until the re-read replaced them. Harmless in the end, but it delayed the baseline. Next time call `reread-all` only.
- **Waiting on the browser check in CI on 2026-11-11.** GitHub's runners could not resolve `security.ubuntu.com` while installing the browser, so `company map browser test` failed on #523 and #524 before running any test. The same suite passed locally (6 passed) and passed in CI on #528. Not a code fault.
- **`ai-task-gates check --before database` under class `deployment`** is refused outright; the production step needs class `production` and `--acknowledge` with the owner's exact words. A hand-written `for` loop around `gh pr` is blocked by a hook; use `ai-pr-wait <pr> --timeout-minutes 9 --fit-tool-call`.
- **A 9-minute foreground wait inside the 1Password `op_run` tool** times out the tool. Use a background timer and check progress with a read-only SQL query instead.
- Dead ends inherited from earlier sessions are in the plan §7 (removing the weekly question cap, model bake-offs, whole-document prompts, atomic-claim approval, delete-and-rebuild).

## 5. Root causes and key findings

1. A reused summary IS re-stamped with the new version (`run_communities`, https://github.com/u2giants/theoracle/blob/7ae581aa/apps/brain/brain/graph/communities.py), so "current" = every summary the latest build selected. Answers, the map API and recommendations share https://github.com/u2giants/theoracle/blob/7ae581aa/apps/brain/brain/graph/version.py.
2. Reading state now follows the chain: `queued → reading → extracting → read | partial | failed` (https://github.com/u2giants/theoracle/blob/7ae581aa/apps/brain/brain/read/state.py). `read` is set only by the relations job. A failed passage is a row in `cmap.extraction` with `prompt_hash='failed'` and `error` text.
3. Failed jobs retry twice (5 min, 20 min) before `failed` (https://github.com/u2giants/theoracle/blob/7ae581aa/apps/brain/brain/worker.py). The hourly `ensure_chain` job heals stalled work (https://github.com/u2giants/theoracle/blob/7ae581aa/apps/brain/brain/chain.py).
4. A re-read deletes a source's chunks, and with them its mentions, relations, and any entity left with no mention — so **entity ids change on a full re-read** (entities are re-created by `resolve`). Anything keyed on an entity row id (review flags, `open_question.entity_ids`, community `entity_ids`) does not survive a re-read. This matters for plan steps C3 and G1 (see drift notes in the plan).
5. CSV/TSV files are stored as kind `text` and routed to the table reader at read time by `detect.read_kind` (the `cmap.source.kind` check was not widened).
6. Flat extraction on the current flat seat spends about 30–36 thousand tokens per ~400-token passage (e.g. 30 passages → 1,083,846 tokens, 17 minutes). The whole re-read took about five hours. This is model behaviour that predates this work; it is the cost driver for any future full re-read and for H5's spend cap.
7. The Meta direct API rejects OpenRouter's `reasoning` parameter with HTTP 400 (https://github.com/u2giants/theoracle/blob/7ae581aa/apps/brain/brain/llm.py); tracked and closed by another session on https://github.com/u2giants/theoracle/issues/526.
8. Office size cap: 50 MB expanded, one constant in `detect.py`. DOCX/PPTX picture failures become a noted gap, not a failed file. Unreadable regions are stored in `cmap.source.read_notes` and shown on the source page.

## 6. Exact next steps

1. **Confirm the rebuild finished.** Supabase MCP `supabase-oracle`, read-only: `select state, kind, count(*) from cmap.job where state in ('queued','running','failed') group by 1,2;` and `select read_state, count(*) from cmap.source group by 1;` and `select max(version) from cmap.graph_version;` vs `select max(graph_version) from cmap.community;`. You'll know it worked when no `read_source`/`classify_extract`/`relations`/`resolve`/`project`/`communities` job is queued or running, zero jobs are `failed`, every source is `read`, `select count(*) from cmap.mention where entity_id is null` is 0, and the newest community version equals the newest graph version. If the chain stalled, wait for the hourly `ensure_chain` or call `POST /map/rebuild`.
2. **Run the self-test twice.** `POST https://oracle-brain.designflow.app/eval/run` with headers `x-brain-token` (1Password, §8) and `x-user-id` of an admin (`select ei.auth_user_id from public.employee_identities ei join public.employees e on e.id = ei.employee_id where e.is_admin and e.disabled_at is null`). Wait for the `evaluate` job to finish, then call it again. You'll know it worked when `select mean_score, graph_version, created_at from cmap.eval_run order by created_at desc limit 2` shows two new rows on the new graph version.
3. **Write `docs/verification/repair/A8-baseline.md`** with the before/after table from §3 (refresh the "after" column from production: sources, chunks, mentions, entities, relations, summaries per level, failed jobs, failed passages, sources `read` with zero mentions) and both scores, the image tag and deployment id, and the times in EST. You'll know it worked when the file is on `main`.
4. **Update the plan STATUS**: rows A1–A8 to ✅ with that file as evidence (A1's live gate = summary counts + score; A2's = zero failed jobs and no `read` source with zero mentions). Same PR as step 3. Markdown-only PRs now finish their checks in under a minute.
5. **Tick the Phase A box on issue #520** with a signed comment linking the baseline file. Do not tick anything else.
6. **Retire this handoff** in the PR of step 3/4 (successor rule) unless Phase B starts in a new session that needs it; the plan STATUS is the durable record.
7. **At the end of Phase A (now) and of every later phase: re-read every downstream phase of the plan to its end and record any drift** in the plan's "Drift log" (added by this session under STATUS). Then start Phase B at B1 in a fresh session (plan cut point).

## 7. Constraints and gotchas in force

Plan §11 in full. The ones that bit this session: never push to `main` (branch + PR, the AI merges); `ai-task-gates start --class <class>` before editing and re-declare when the change set escalates (workflow files and `vercel.json` are class `deployment`; production actions are class `production` with the owner's exact words); the brain deploy is manual — pin `BRAIN_IMAGE_TAG` to the full commit SHA through the Coolify API at `https://coolify.designflow.app/api/v1` (PATCH `/applications/{uuid}/envs`, then POST `/deploy?uuid=`), never `latest`; a brain restart orphans the running job, which is requeued after 180 seconds; the interview bot is OFF and must stay off; the repo is public; no model ids in code; sign GitHub posts with `$AI_GH_SIGNATURE`; times to people in EST. Next free SQL file number is **019**.

## 8. Access and environment

- GitHub: `gh` as `u2giants`.
- Database reads: Supabase MCP server `supabase-oracle` (read-only here).
- 1Password vault `vibe_coding` (locations only; use `op_run` with `op://` references, never print): "Coolify API token - Oracle deploy - release sessions only (theoracle)" field `credential`; "Oracle Brain shared token - The Oracle (BRAIN_SHARED_TOKEN)" field `BRAIN_SHARED_TOKEN`; "Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, eqccjfbyrywsqkxxpjvg)" field `password` (the direct host is IPv6-only; use the session pooler host `aws-1-us-east-1.pooler.supabase.com`, user `postgres.eqccjfbyrywsqkxxpjvg`). The Coolify envs endpoint returns plaintext values: select only the keys you need.
- Local tests: Postgres (pgvector/pgvector:pg16) + FalkorDB v4.20.7 containers; `cd apps/brain && uv sync && DATABASE_URL=… FALKORDB_URL=… uv run pytest` (338 passed at `7ae581aa`); browser suite `cd apps/web && BRAIN_E2E_DATABASE_URL=… BRAIN_E2E_FALKORDB_URL=… pnpm exec playwright test --config playwright.map.config.ts` (6 passed).

## 9. Open questions and risks

- (2026-11-11) Unknown until step 2: whether Phase A alone reaches the 0.6 target. A1 alone moved 0.378 → 0.422. Do Phase B regardless (plan).
- (2026-11-11) Recommendations and review flags created before the re-read point at entity/summary ids that no longer exist or were kept only because they are referenced; step G1 migrates flags to content-based keys. Until then old flags may show as orphans on the review page — not verified in the browser.
- (2026-11-11) The sources page's new buttons (Retry, Retry failed jobs, Re-read everything) and the "Parts that could not be read" list were type-checked and covered by the existing browser suite passing, but were not looked at in a live browser.
- (2026-11-11) The start-up schema apply re-runs `DROP/ADD CONSTRAINT` in 016 and 018 on every start; fine at today's table sizes.
- (2026-11-11) A 58th source arrived during the re-read (uploaded or an interview/meeting intake by someone else); it is processed normally and will be in the "after" counts.

## Self-audit

1. Newcomer can pick up without a question: yes — §1 what it is, §3 exact live state with numbers and tags, §6 steps with the queries and gates, §8 access. 2. As effectively as the author: yes — §4 the five things that cost time, §5 the eight findings with links, including the entity-id consequence and the per-passage token cost. 3. Every detail for flawless execution: yes — goal §2, state §3, failures §4, findings §5, steps and gates §6, rules §7, access §8, risks §9. 4. §0 sweep: walked §1–§9; the only owner items are the six in §0 (unchanged from the predecessor, still unanswered, all defaulted); the production authorization quote is recorded as settled; no technical approval is asked of him.
