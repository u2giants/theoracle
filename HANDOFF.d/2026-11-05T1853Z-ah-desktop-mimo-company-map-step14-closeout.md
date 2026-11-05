---
issue: 255
status: OPEN
owner: mimo/step14-wrapup-coordinator (ah-desktop)
---

# Company Map step 14: wrap-up baton — owner gates remain

Written 2026-11-05, 2:53 PM EST, ah-desktop, MiMo (coordinator, session wrap-up).
Program parent https://github.com/u2giants/theoracle/issues/240 ; step 14
https://github.com/u2giants/theoracle/issues/255 ; spec
https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md .
Executed baton (KEEP until #255 closes — it holds the original task texts):
https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0812Z-ah-desktop-mimo-company-map-remaining.md

This file is the successor baton for what REMAINS of step 14 after the
2026-11-05 day-round. Everything AI-executable is done and independently
verified (§3); what is left is owner-gated (§0), calendar-gated (§6.5), or
`Blocked —` on a credential scope (§6.4). A successor is a coordinator only if
it starts per-task sessions; a single worker may also take any one task
directly. Do no unrelated work.

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

Put ALL open items below to Albert in ONE message before starting work.

1. **30-minute Map review: mark wrong items.** The marking tool is LIVE and
   proven (§3): on the Map, an admin flags an entity / arrow / community as
   wrong with a note; `/map/review` collects them; resolving works. Albert
   attempted the review 2026-11-05 morning and could not find a marking
   control (it did not exist yet); the control was built for him today.
   Blocks: closing #255 (task 8) — this is the last gate on the program.
   Recommendation: do it today while the map is at graph version 27.
2. **Ilona's review of the 20 eval questions** on the Claude artifact page
   (https://claude.ai/artifact/1dw8ZoafmchL3HZ9mW26KX, shared with her as
   Contributor by Albert 2026-11-05 morning). As of 10:25 AM EST the page read
   "20 questions · 0 kept · 0 dropped · 20 not decided yet" — she has not
   started. Blocks: task 6 (#367), the only real quality score for step-14
   acceptance. Also decide: should the bot nudge Ilona to start (same friendly
   mechanism as the 11-employee nudge), or does Albert chase her himself?
   Recommendation: bot nudge today.
3. **The 405 evidence-less entities on the map — keep or hide.** Earlier
   source deletions orphaned 405 entities that now have zero evidence rows
   (root cause §5). The community fix folds linked entities but leaves these
   isolates. Keep them on the map folded into communities (recommended —
   hiding loses structure Albert may want back) or hide them until evidence
   returns? Blocks: the map-content policy and whether a one-time count
   backfill runs. Recommendation: keep, no backfill. Record the answer on #255.
4. **Send the rest of the company documents.** The plan expects hundreds of
   sources; the Map has ~31. Intake is the site itself: log in to
   https://oracle.designflow.app and bulk-upload at **Map → Sources**
   (drag-and-drop, admin). Recommendation: drop them in as they are ready;
   corpus growth also continues through Teams conversations.

Already settled. Do NOT re-ask:
- 2026-11-05 Albert, verbatim "yes" — he ordered the Oracle 2 no-backup
  deletion (93 tables dropped). Record settled on issue #398.
- 2026-11-05 Albert: "nudge" the 11 silent Teams employees — DONE and proven
  (44/44 conversations carry refs; named table on #255).
- 2026-11-05 Albert, verbatim "any questions you have must be on the oracle
  site. we won't be shuttling text documents back and forth" — standing rule:
  questions go on the Oracle site's own question surfaces, never via chat
  files or markdown shuttling.
- 2026-11-05 Albert shared the question page with Ilona (his part of the
  share step is done).
- Vision seat `anthropic/claude-sonnet-5.5`; relations seat Muse direct
  (`meta-model-api/muse-spark-1.3-contributor`, live and verified); Albert
  2026-11-04 verbatim "i want the brain to use the Muse direct API key" (DONE);
  the `z-ai/glm-5.3` OpenRouter relations stopgap is superseded.
- Predecessor settled lists: tenant emails @popcre.com; interview questions
  stay OFF until Albert turns them on; $25/day OpenRouter cap; reviews are
  advice only; FalkorDB stays; permissions are login + `is_admin` only;
  public-repo history exposure accepted.

## 1. What this application is

The Oracle is POP Creations' evidence-backed company adviser. The Company Map
reads company documents, diagrams and employee transcripts and shows how work
flows. `apps/brain` (Python FastAPI + worker) runs on Coolify as `oracle-brain`
(https://oracle-brain.designflow.app), web https://oracle.designflow.app on
Vercel, Postgres schema `cmap` on Supabase project "theoracle", FalkorDB graph
`company`. The repo is PUBLIC — no LAN IPs, no Supabase project refs, no
secrets in any commit, issue or PR. Employee names in issues follow the
established @popcre.com style.

## 2. What we set out to do this session, and why

Execute the wrap-up coordinator baton named in the header. Albert's authority,
verbatim: "Goal: finish the Company Map model work and close step 14." and
"get everything that can be moving, moving." The coordinator dispatched one
MiMo actor subagent per ready task (nine in total, part (b)), verified every
report against GitHub and the live brain/DB itself, sequenced the deploys, and
applied the day's owner answers (§0 settled list). Mid-day Albert added one UI
ask (taller text boxes — done). `/wrap-up` was invoked ~2:50 PM EST with the
owner-gated tasks still open; this file is that close-out.

## 3. Current state — what is true right now

DONE this round and independently verified by the coordinator (evidence
re-checked against GitHub and the live brain/DB, not just child claims):

| Item | Outcome | Proof |
|---|---|---|
| 6.6 task-4 follow-ups | drift notes folded into #240; task4 handoff retired | comment https://github.com/u2giants/theoracle/issues/240#issuecomment-6661335266 (mentions debounced per-source chain + `run_after` claim filter); PR https://github.com/u2giants/theoracle/pull/447 merged `73a19090`; file absent from HANDOFF.d on main |
| 6.7 #437 community sizes | fold fix merged, live-proven in stored rows | PR https://github.com/u2giants/theoracle/pull/451 merged `5783e7ec`; proof https://github.com/u2giants/theoracle/issues/437#issuecomment-6664715774 — graph_version 27: L0 34 groups (3–102), L1 26 groups (3–149), zero below 3 / above 150 (coordinator re-ran the query itself: exact match); proof box ticked; handoff retired via PR https://github.com/u2giants/theoracle/pull/453 |
| Nudge 11 silent Teams employees | all 11 nudged, chats opened | https://github.com/u2giants/theoracle/issues/255#issuecomment-6661939779 ; coordinator verified `cmap.teams_conversation` = 44 rows, all 44 with non-null `conversation_ref` |
| #398 governance record | Albert's "yes" recorded | https://github.com/u2giants/theoracle/issues/398#issuecomment-6661798509 |
| Mark-as-wrong on the Map | built, deployed, live-proven | PR https://github.com/u2giants/theoracle/pull/449 merged `523d8a5`; migration `010_review_flags` applied; proof https://github.com/u2giants/theoracle/issues/255#issuecomment-6664266352 (entity + relation flagged, survived reload, resolved; prod left clean — coordinator re-queried: `review_flag` 2 rows, 0 open) |
| Taller text boxes | shared 10rem rule live | PR https://github.com/u2giants/theoracle/pull/448 merged; coordinator found `textarea{min-height:10rem}` in the live prod CSS chunk |
| Orphan-entity hygiene | `delete_source` no longer orphans entities | PR https://github.com/u2giants/theoracle/pull/454 merged `a3975710`, 217/217 tests; deployed and live 2026-11-05 ~1:50 PM EST (deployment `fkrdsqb5tcdltfnpmkif1rlp`, `/health` `{"ok":true,"db":true,"graph":true}`) |

Deploy state: brain image pin `BRAIN_IMAGE_TAG` (prod Coolify env) is
`a3975710e890ddb1c798b398ed4afebe126483d0` — the sha whose "Brain image" CI
run succeeded — deployed, healthy. Web is Vercel-auto-deployed from main.
Migration 010 (`cmap.review_flag`) is applied on prod.

NOT started / NOT done:
- Task 6 (stage-7 rerun on the final 20 questions, #367) — owner-gated (§0.2).
- Task 8 (close step 14: STATUS row 14 + close #255 + final drift note on
  #240) — owner-gated (§0.1).
- Container image deletion of `theoracle-native` / `theoracle-native-browser`
  — `Blocked —` (§6.4).
- November 11 tick-log check — calendar-gated (§6.5).
- The 405-orphan keep/hide decision and any follow-up backfill — owner-gated
  (§0.3).

## 4. Everything we tried that did NOT work

1. **`ai-task-gates check --before deploy` STOPs on a stale base.** Declaring
   `start --class code` on the (behind) canonical checkout made the change set
   include old landed files (`apps/web/app/admin/transcripts/*`,
   `evals/oracle2/synthetic-cases.jsonl` from PRs #402/#406) and trip
   `never-open-raw-transcript-archives`. WORKING PATH: `git fetch`, then
   `ai-task-gates start --class production --base origin/main`, then
   `check --before deploy`. The production class then demands
   `--acknowledge "<Albert's exact words>"` — supply the authority quote; the
   gate logs it and allows.
2. **`--before deployment` is not a valid action verb** — the tool answers
   `unknown action: deployment`. Use `--before deploy`.
3. **`BRAIN_IMAGE_TAG` stale-pin no-op deploy (the expensive one).** A
   `POST /deploy` that reports `finished` in ~10 s can still serve the OLD
   image if the pin predates the new code (the `/flags` route 404'd after a
   "successful" deploy). WORKING PATH: confirm the "Brain image" CI run for
   the target main sha succeeded, PATCH the prod env entry
   (`PATCH /api/v1/applications/<uuid>/envs`, single-object form
   `{key,value,is_preview,is_multiline,is_literal}`, `is_preview:false`) to
   that full sha, THEN `POST /deploy`, then probe a route the old image lacks.
   The envs listing also holds a stale PREVIEW entry with an ancient sha — it
   is `is_preview:true` and harmless, but PowerShell array-joins the two
   values when listing, which looks like corruption.
4. **`ai-shared-db-closeout-check` still hangs** (>90 s, reproduced again
   2026-11-05; likely in its `ai-gh` launcher). Substitute check used:
   `gh search issues --repo popcre/shared-db '<session id>'` → 0 matches = no
   owned claims. Re-run the real tool once ai-devops repairs it.
5. **Claude artifact pages are not readable by fetch** (returns only a
   "user-generated content" stub) and playwright/Edge profiles have no
   claude.ai session; Chrome's Cookies DB is hard-locked while Chrome runs.
   WORKING READ PATH (from the Ilona-check child): `chrome.exe <url>` opens a
   tab in the owner's running signed-in Chrome, then a PowerShell UIA
   (AutomationElement) walk extracts the rendered text and input values with
   no clicks. Read-only mandate: do not press page buttons.
6. **`ai-housekeeping` hangs when routed through `bin/ai-gh`.** WORKING PATH:
   `AI_HOUSEKEEPING_GH=gh AI_HOUSEKEEPING_GH_TIMEOUT_SECONDS=15` — completes
   in seconds (found by the 6.6 child).
7. **The no-redeploy-while-jobs rule repeatedly closed the deploy window** —
   the corpus is actively growing (chains fired continuously; a nudge reply
   chain and recommend tails kept the queue non-empty). WORKING PATH: one
   bounded wait (~4 min) then re-poll; deploy in the first quiet gap. Never
   loop on sleeps.
8. Carried from the predecessor batons: `mcp__ccd_session__start_session` does
   not exist on MiMo (use actor general subagents and say so); Supabase direct
   URL is IPv6-unusable (use `oracle_session_pooler`); PowerShell quoting
   through `ssh host "python3 -c …"` collapses (scp a script, pipe the secret
   on stdin); pip on edge-dev3 is PEP 668-locked (`--target /tmp/pylibs`);
   GLM invalid-JSON flakes (re-queue); Coolify `GET /applications/<uuid>/envs`
   echoes secrets — never print the body; deploy before an env PATCH
   redeploys the OLD image.

## 5. Root causes and key findings

- **The 405 evidence-less entities (§0.3):** `cmap.mention` cascades when
  chunks/sources are deleted, but `cmap.entity` has no such link, so
  `DELETE /sources/{id}` orphaned entities (405 of them in prod, from
  deletions before this round). PR #454 fixes the FUTURE path: `delete_source`
  now removes entities left with zero mentions, scoped to the deleted source's
  own entities — deliberately NOT the global smoke-cleanup statement, which
  would have purged the 405 on the next delete and pre-empted Albert's
  keep/hide decision. Historical count drift on those 405 (`mention_count` /
  `source_count` claim evidence that no longer exists) is uncorrected; a
  backfill is a data change and follows §0.3.
- **Community sizes (#437) root cause:** the L0 merge loop only reaches a
  neighbour through an edge or source; the 405 no-mention isolates had
  neither, so they stayed singletons (408 of 442 groups were ≤2 entities).
  PR #451 adds a fold pass; stored membership at graph_version 27 is all in
  [3,150] at L0/L1 (L2 is the single whole-company group by design).
- **`POST /map/rebuild`** (brain, admin auth) is the canonical re-cluster
  trigger: `resolve` → `project` (bumps `cmap.graph_version`) → `communities`
  → `recommend`. An unresolved-mention-free `resolve` is a ~2 s no-op.
  `run_communities` reuses reports keyed by (level, entity set) across graph
  versions and re-tags `graph_version` — read `created_at` to tell new rows
  from reused ones (this round's proof: 32 of 61 L0/L1 rows new).
- **`POST /api/teams/bot/proactive` accepts free-form text and is NOT gated on
  `BRAIN_INTERVIEW_ENABLED`** — anyone holding the shared brain token can open
  a chat with any employee and say anything. Fine for the sanctioned nudges;
  a standing risk otherwise (interviews OFF is convention for this route).
  Candidate for an issue by the successor (§9).
- **The11-silent-employee nudge mechanism** (PR #440): the bot opens the 1:1
  chat itself via `createConversationAsync` when no conversation reference
  exists; `POST /api/teams/bot/proactive` triggers it. All 11 refs stored.
- **GitHub merges auto-close referenced issues** — #437 was closed by the #451
  merge at 11:16 AM EST before its live proof landed; check `state:` before
  assuming an issue still needs closing.
- **theoracle has no `bin/ai-doc-safety`** — use the ai-devops toolkit copy;
  the prose lane `ai-doc-safety --changed origin/main` is the correct gate for
  docs-only PRs (whole-tree mode fails on pre-existing debt).
- **Git bash `TZ=America/New_York` is broken** (prints GMT labelled EST) —
  compute EST in PowerShell only. Windows cp1252 cannot print `→` in proof
  scripts — set `PYTHONIOENCODING=utf-8`.
- **Brain API auth** needs BOTH `x-brain-token` (1Password item
  `4lm6bpl7bc25lqne4meumwcd2a` field `BRAIN_SHARED_TOKEN`) and `x-user-id`
  (an admin Supabase auth user mapped to an active `is_admin` employee;
  `e0968007-7276-46fb-8abd-25baa108f112` verified working).
- **Eval manifests:** authoritative seats are `models.stages.*` inside
  `cmap.eval_run.models`, not the legacy top-level keys (predecessor finding,
  still true). The seed-eval mean 0.2 is NOT a quality number (fixture
  questions); the real instrument is the 20 owner questions (task 6).

## 6. Exact next steps

1. **Put §0 to Albert in ONE message** (all four open items), then wait for his
   answers. You'll know it worked when he answers in chat and the Map verdict /
   orphan decision are recorded on #255.
2. **Task 8 — close step 14** (only after the Map review verdict, §0.1).
   Verbatim from the predecessor baton: "Record Albert's verbatim Map verdict
   in plan STATUS row 14, close #255, and post a final drift note on #240 (the
   full drift report is already there). Done when: #255 closed." In the drift
   note also carry: the task-4 follow-up is already folded (link
   https://github.com/u2giants/theoracle/issues/240#issuecomment-6661335266),
   the §0.3 orphan outcome, and the proactive-endpoint risk (§5). You'll know
   it worked when #255 is closed and STATUS row 14 holds Albert's verbatim
   words.
3. **Task 6 — stage-7 rerun on the final 20 questions (#367)** (only after
   Ilona approves, §0.2). Verbatim from the predecessor baton: "On artifact
   `05282281-8fc8-4d2f-a61e-4760a9bdb45e` (the question page), run `db_get`
   review/status, then `db_list` the questions collection, enter the questions
   on the eval page, and rerun answers (local and global mode) on a cloned DB.
   The page buttons are untested in a signed-in browser. Done when: #367 is
   closed with a rerun report in the bake-off folder." Use a cloned DB; never
   point the eval at prod for scoring.
4. **Container image deletion — `Blocked —` (unowned until a token exists).**
   Delete `theoracle-native` and `theoracle-native-browser` from GitHub
   Packages. Needs a `delete:packages` token; the gh token on these machines
   has `gist, read:org, repo, workflow` and the vault packages item only
   `read:packages`. GitHub does not allow PAT creation via API — route to a
   session with the u2giants account's authenticated browser (never ask
   Albert to type it). Details:
   https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0258Z-edge-dev-mimo-task7-ghcr-images-leftover.md
   Done when both package names 404 for a read:packages-capable token and the
   live-proof box on #431 is ticked.
5. **2026-11-11 or later — interview tick-log check.** Verify Phase-3
   done-when: ≥3 scheduled questions sent to employees within one week AND ≥1
   answer became a source. Query `cmap.open_question` / `cmap.interview_send`
   / `cmap.source` (pooler path) or `GET /interview/overview` with the service
   token + admin x-user-id. Post counts and pass/fail on #255 signed.
   Recipe: https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0307Z-edge-dev-mimo-teams-followup-255.md §6.
6. **Unowned smalls (any session may take):** file or fix the
   proactive-endpoint gating risk (§5); the #450 review-fixer lane item
   (`test_review_flags_unit.py`) is the auto-fixer's; the 405-orphan count
   backfill waits on §0.3.

You'll know each step worked when its stated done-when fires.

## 7. Constraints and gotchas in force

- Never push to protected `main`: branch + PR + `gh pr merge --squash --admin`.
  Docs-only PRs need `ai-doc-safety --changed origin/main` (the ai-devops
  toolkit copy) on the exact head before merge.
- Public repo hygiene: no secrets, no LAN IPs, no Supabase project refs in
  code, commits, issues or PRs. Employee names/emails follow the @popcre.com
  style used in this repo's issues.
- Times in EST (America/New_York) in every human-facing message; compute them
  in PowerShell.
- Task gates: `ai-task-gates start --class production --base origin/main` on a
  FRESH fetch before risky steps (the stale-base trap is §4.1); `check --before
  deploy|database --acknowledge "<Albert's exact words>"`. Migration files
  (`**/*.sql`) are classified `shared-db` by the gate.
- Never redeploy the brain while `cmap.job` has rows in ('running','queued');
  only ONE session deploys at a time; env PATCH (pin!) BEFORE the deploy;
  verify a route the old image lacked after the deploy.
- Interview questions stay OFF (standing owner direction) until Albert enables
  them — and see the proactive-endpoint risk (§5).
- Sign every GitHub post: `Posted by MiMo chat <session id> on <machine>`.
- OpenRouter: check `limit_remaining` before spend; stop under $5 of the
  $25/day cap.
- HANDOFF.d discipline: never edit another session's file; retire only under
  the successor rule (issue closed + landed verified + obligations carried).
  Do not rewrite the root `HANDOFF.md`. The predecessor baton (0812Z) stays
  until #255 closes.
- Each nested task session: own worktree from fresh main, own test DB clone
  and FalkorDB container on edge-dev3 (never `brain2-test-*`), background PR
  waiter, never end a turn on "waiting", never spawn its own children without
  coordinator approval.

## 8. Access and environment

- Machines: ah-desktop (Windows; this coordinator) and edge-dev3 (Linux test
  services host over ssh). Canonical checkout and worktree layout live in the
  machine atlas: https://github.com/popcre/ai-devops/blob/main/templates/system/machine-atlas.md
  — resolve paths from it on any machine (this session's own worktree is
  removed; nothing of ours is left open on disk).
- `gh` authenticated as `u2giants` (scopes `gist, read:org, repo, workflow` —
  NO `delete:packages`, see §6.4). Commit identity:
  `Albert Hazan <u2giants@users.noreply.github.com>` (`git var GIT_COMMITTER_IDENT`).
- 1Password MCP (`1password_op_run`, vault `vibe_coding`, item-ID form of
  op:// refs): shared token item `4lm6bpl7bc25lqne4meumwcd2a` field
  `BRAIN_SHARED_TOKEN`; Supabase item `qcuyabwseaptvuzvtjejffi2ou` field
  `oracle_session_pooler` (WORKING — the field named `password` is an
  IPv6-only direct URL, unusable); Muse/Meta key item `czggiabkpo7dt7ojep4btdvq5i`;
  Coolify item `u3aqw63jqnkmnziip3gp5hwb5m` field `credential`. Never print
  values; never pass them in argv; pipe the pooler URL on stdin to edge-dev3
  scripts.
- Prod DB: psycopg from edge-dev3 (`python3 -m pip install --target /tmp/pylibs
  'psycopg[binary]'`, then `PYTHONPATH=/tmp/pylibs python3 <scp'd script>`,
  URL piped on stdin). psql is not installed there.
- Brain API https://oracle-brain.designflow.app — `/health` free; everything
  else needs both auth headers (§5). Coolify API `http://hetz:8000/api/v1`
  from ah-desktop; app uuid `uge6pfm4qapktivto4981mtg`; deploy
  `POST /api/v1/deploy?uuid=uge6pfm4qapktivto4981mtg`.
- Cmap migrations run via `python -m brain.migrate` (applies every file in
  `apps/brain/brain/sql/` in order; idempotent) — a deploy does NOT apply
  them by itself.

## 9. Open questions and risks

- **(2026-11-05) `POST /api/teams/bot/proactive` is a free-form messaging
  channel gated only by the shared brain token** (§5). No incident; candidate
  for an issue + a gate tying the route to `BRAIN_INTERVIEW_ENABLED` or an
  admin allowlist.
- **(2026-11-05) The 405 orphans and their stale counts** wait on §0.3; until
  then the map shows isolates folded per the community fix.
- **(2026-11-05) Two proof transcripts remain in the prod corpus** ("Debounce
  proof 2026-11-05 (a)/(b)"), clearly labeled. Deleting re-triggers the chain
  by design. Remove only on owner request.
- **(2026-11-05) One `interview_tick` job failed** earlier in the day (single
  failure, rest healthy) — re-queue if a content gap appears. The seed-eval
  mean of 0.2 is fixture noise (§5).
- **(2026-11-05) Coolify env listing echoes secrets** — filter to one key;
  never print the body. One earlier child saw a local-only echo of an
  existing value; per standing rule it stays unrotated (exposed only on that
  machine) and was never written to a file.
- **(2026-11-05) `ai-shared-db-closeout-check` is broken (hangs)** and
  `ai-housekeeping`'s GitHub routing reports UNKNOWN (§4.4, §4.6) — repair
  these in ai-devops; do not remove them. Housekeeping inventory at wrap-up:
  38 open handoffs (0 successor-review, 6 unattributed), 3 active plans,
  17 live worktrees — report-only.

---

## Part (b) — nested sessions (this coordinator dispatched nine)

All were MiMo `actor` general subagents (this client's equivalent of
`mcp__ccd_session__start_session`), each in its own worktree from fresh main,
briefed with the task text verbatim plus the standard addendum ("commit to your
own branch, open a PR, prove done-when live, then run wrap-up"). None spawned
children of their own. None holds a worktree, branch or claim at close-out.

- **6.6 task-4 follow-ups (general-1)** — folded the task4 drift notes into
  #240 and retired the task4 handoff via PR #447. Found the `ai-doc-safety`
  prose-lane form and the `ai-housekeeping` env workaround (§4.6). Worktree
  removed.
- **6.7 #437 community sizes (general-2)** — root-caused the isolates, PR
  #451 (fold pass, 209 tests), read-only live distribution proof on #437;
  its live re-cluster was finished by general-8. It also PATCHed
  `BRAIN_IMAGE_TAG` to `5783e7ec` at 11:34 AM EST after its own stale-pin
  deploy ran old code (the lesson in §4.3) and wrote the live-proof handoff
  (retired by general-8 via PR #452→#453). Worktree removed. It asked one
  owner question (the 405 orphans) — promoted to §0.3.
- **Ilona question-page check (general-3, read-only)** — read the artifact in
  Albert's signed-in Chrome via UIA: "20 questions · 0 kept · 0 dropped · 20
  not decided yet", Done unpressed. Discovered the Chrome/claude.ai read path
  (§4.5). Changed nothing.
- **Mark-as-wrong on the Map (general-4)** — PR #449 (migration 010,
  `brain/api/flags.py`, web `/map/review`, Playwright screenshots), then
  live-proved flagging/persistence/resolution on the deployed brain and left
  prod clean (2 resolved / 0 open — coordinator re-verified). Answered that it
  triggered no jobs; confirmed the t4-*/task9-* container cleanup on
  edge-dev3. Worktree and branches removed.
- **#398 governance record (general-5)** — one comment with Albert's verbatim
  "yes"; no repo changes. Verified live.
- **Nudge the 11 silent employees (general-6)** — `POST /api/teams/bot/proactive`
  to each of the 11 named accounts (list in the #255 comment), all 11 refs
  stored; interviews untouched. Coordinator re-verified 44/44 refs in
  `cmap.teams_conversation`. No repo changes.
- **Taller text boxes (general-7)** — one shared `textarea{min-height:10rem}`
  rule in `apps/web/app/globals.css`, PR #448 merged, verified live in the
  deployed CSS chunk. Noted Vercel previews sit behind SSO (login needed for
  page-level screenshots). Worktree removed.
- **#437 live proof (general-8)** — ran the real re-cluster (`POST /map/rebuild`
  12:14 PM EST; project wrote graph_version 27; communities clean in ~7 min),
  posted the stored-row distribution on #437 and ticked its proof box,
  retired the live-proof handoff via PR #453. Coordinator re-ran its query
  against prod: exact match. Worktree removed.
- **Orphan-entity hygiene (general-9)** — PR #454 (`delete_source` removes
  mention-less entities, scoped to the deleted source; counts repair; 217
  tests incl. the two required proof tests). Deliberately did NOT touch the
  405 existing orphans (owner decision, §0.3) and did NOT deploy. Its deploy
  was sequenced by the coordinator and verified live (§3). Worktree removed.

## Self-audit (handoff-writer gate)

1. *Could a brand-new developer pick up and not skip a beat?* Yes — §1
   orients the app, §3 pins every completed item with PR/issue/DB evidence,
   §6 gives ordered next steps with done-when gates, §8 gives every access
   path (vault item ids only).
2. *Could they continue as effectively as me right now?* Yes — §4 carries this
   round's dead ends (stale-base gate STOP, stale-pin no-op deploy, hanging
   closeout-check, the Chrome/claude.ai read path, the housekeeping env
   workaround), §5 the root causes (orphan cascade, community isolates,
   report reuse by entity set, the proactive-endpoint risk).
3. *Every relevant detail included?* Background (§1–2), outcomes (§3),
   failures (§4), findings (§5), actions (§6), constraints (§7), access (§8),
   risks (§9), owner decisions (§0), per-subagent records (part (b)). Commit
   SHAs and GitHub URLs throughout; no machine-local file paths (machine
   identity goes through the machine-atlas link).
4. *Does §0 hold every owner decision and no technical approval?* Yes — the
   sweep found four owner items (Map review verdict, Ilona's question review
   + nudge call, the 405-orphan keep/hide call, more documents) and every
   technical item is either done, `Blocked —` (the packages token — routed to
   a browser session, never to Albert), or calendar-gated. The settled list
   prevents re-asking.

