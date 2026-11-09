---
issue: 255
status: OPEN
owner: mimo/step14-combined-wrapup (ah-desktop)
---

# Combined remaining-work coordinator baton — Company Map step 14 closeout + "refactor Oracle" chat remainder

Written 2026-11-09, 11:20 AM EST, ah-desktop, MiMo (session `ses_ffe5e5262b286ffeXctxMDUACu`,
the step-14 closeout chat). This file is the ONE combined successor baton Albert
ordered on 2026-11-09, verbatim: "between this chat and the mimo chat named
refactor Oracle, wrap-up (with the skill) both and make a prompt and handoff doc
encompassing what's still open in both, and have the prompt set the new session up
as a coordinator". Both predecessor chats are standing down; the fenced
coordinator prompt that starts the successor session travels with this file in
the closeout chat's final report and is reproduced at the bottom of §6.

Program parent https://github.com/u2giants/theoracle/issues/240 ; step 14
https://github.com/u2giants/theoracle/issues/255 ; spec
https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md .

Predecessor batons (BOTH STAY in HANDOFF.d until #255 closes — do not retire them):
- Executed baton holding the original step-14 task texts (incl. task-6 §6.2):
  https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0812Z-ah-desktop-mimo-company-map-remaining.md
- Wrap-up baton of the day-round (task texts §6, verified outcomes §3, dead ends §4):
  https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T1853Z-ah-desktop-mimo-company-map-step14-closeout.md
Sibling-registered plan handoffs (written by the "refactor Oracle" chat, stay with their plans):
- https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-08T1616Z-ah-desktop-mimo-chinese-integration-plan.md
- https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-08T1806Z-ah-desktop-mimo-meeting-triage-plan.md

A successor is a COORDINATOR: it starts one session/subagent per ready task,
verifies every child report against GitHub and the live services itself, and
keeps owner questions for Albert. Do no unrelated work.

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

Put the two BLOCKING items below to Albert in ONE message before starting work.

**Blocking:**

1. **Map review verdict (30 minutes, only Albert).** On the live Map he flags
   what is wrong — any entity, arrow, or community — with the mark-as-wrong
   control (built Nov 5 for him, PR #449; the control he could not find that
   morning did not exist yet). Marks collect at `/map/review`. He now knows what
   it is (the "refactor Oracle" chat explained it 2026-11-08) but has not done
   the review. Blocks: closing #255 (task 8) — the last gate on the program.
   Recommendation: do it today while the map is at graph version 27; the verdict
   is recorded verbatim either way (clean or with a marked-wrong list).
2. **Ilona's review of the 20 eval questions + the nudge sub-question.** The
   questions live on the Claude artifact page
   (https://claude.ai/artifact/1dw8ZoafmchL3HZ9mW26KX, shared with her as
   Contributor by Albert 2026-11-05). Last read 2026-11-05, 10:25 AM EST:
   "20 questions · 0 kept · 0 dropped · 20 not decided yet". Albert was asked on
   2026-11-09 whether the bot should nudge Ilona to start (same friendly
   mechanism as the 11-employee nudge) or he chases her himself — he did not
   answer. Blocks: task 6 (#367), the only real quality score for step-14
   acceptance. Recommendation: bot nudge today.

**Later, inside the two registered plans (no action until those steps are reached; the coordinator dispatches the plan work itself — implementation is already authorized by the owner specs, not an ask):**

3. Meeting-triage step 3.1 acceptance — Albert reviews real rows on
   `/map/meetings` and clicks Ingest on one; plus O4 later (after two weeks of
   Phase 1, is ad-hoc "Meet Now" worth building) and the plan's open decisions
   O1–O5 (criteria in plan §8:
   https://github.com/u2giants/theoracle/blob/main/plan_meeting_triage_pipeline.md ).
4. Chinese-integration 4.2 acceptance — pick the China-office acceptance reader
   (Emma Li suggested); plus open decisions O1–O4 (criteria in plan §8:
   https://github.com/u2giants/theoracle/blob/main/plan_chinese_integration.md ).

**Already settled — do NOT re-ask:**

- 2026-11-08, Albert, verbatim "unfortunately, i think you already have all of our
  documents." — document corpus COMPLETE; growth is meetings + Teams.
  Recorded: https://github.com/u2giants/theoracle/issues/255#issuecomment-6725102695
- 2026-11-08, Albert, verbatim "i don't know what the 405 evidence-less entities
  are, so i can't comment" — settled on the wrap-up baton's recommendation:
  KEEP the 405 orphans on the map folded into communities, NO count backfill.
  Reversible: one word hides them later. Recorded:
  https://github.com/u2giants/theoracle/issues/255#issuecomment-6725350744
- 2026-11-08: the deletions that created those orphans were OUR test/proof
  material, not Albert's 8 company documents — his docs are all present (live
  47-source list verified 2026-11-08). The delete-side leak is fixed (PR #454).
- 2026-11-05, Albert, verbatim "yes" — the Oracle 2 no-backup deletion (93 tables
  dropped). Recorded: https://github.com/u2giants/theoracle/issues/398#issuecomment-6661798509
- 2026-11-05, Albert: "nudge" the 11 silent Teams employees — DONE and proven
  (44/44 conversation refs; https://github.com/u2giants/theoracle/issues/255#issuecomment-6661939779 ).
- 2026-11-05, Albert, verbatim "any questions you have must be on the oracle
  site. we won't be shuttling text documents back and forth" — standing rule:
  questions go on the Oracle site's own question surfaces.
- 2026-11-05: Albert shared the question page with Ilona (his share step is done).
- 2026-11-04, Albert, verbatim "i want the brain to use the Muse direct API key" —
  DONE (Muse Spark 1.3 Contributor direct seat live; the GLM OpenRouter relations
  stopgap is superseded). Vision seat `anthropic/claude-sonnet-5.5`.
- Predecessor settled lists still binding: tenant emails @popcre.com; interview
  questions stay OFF until Albert turns them on; $25/day OpenRouter cap; reviews
  are advice only; FalkorDB stays; permissions are login + `is_admin` only;
  public-repo history exposure accepted.

**Not owner asks (technical, tracked in §6/§9):** GHCR image cleanup is DONE (see
§3 — note the two older batons still say "Blocked"; that is stale as of
2026-11-05); the proactive-endpoint gating risk is a fix/file item; stale draft
PRs are coordinator triage; the hanging ai-devops tools are repair items.

## 1. What this application is

The Oracle is POP Creations' evidence-backed company adviser. The Company Map
reads company documents, diagrams and employee transcripts and shows how work
flows: departments → processes → steps → hand-offs → systems → recurring pain
points, every claim traceable to its sources. `apps/brain` (Python FastAPI +
worker) runs on Coolify as `oracle-brain` (https://oracle-brain.designflow.app),
web https://oracle.designflow.app on Vercel, Postgres schema `cmap` on Supabase
project "theoracle", FalkorDB graph `company`. The repo is PUBLIC — no LAN IPs,
no Supabase project refs, no secrets in any commit, issue or PR. Employee names
in issues follow the established @popcre.com style.

Two further programs are registered and ready to implement (both merged to main,
all STATUS rows open, fresh sessions start at their STATUS row 0.1):
- Chinese (Mandarin) integration — 14 steps / 5 phases, CJK-safe text handling,
  Chinese in/out, map translations, zh eval + live proof.
  https://github.com/u2giants/theoracle/blob/main/plan_chinese_integration.md
- Meeting-transcript triage pipeline — Microsoft Graph transcript sweep →
  ScaleDown classify/summarize → admin review → ingest, `/map/meetings` page.
  https://github.com/u2giants/theoracle/blob/main/plan_meeting_triage_pipeline.md
Recall.ai (meeting-capture bots) is built and healthy but unused under the
current system: API key valid, webhook signature enforced, 7 bots from June 2026,
zero meeting transcripts have ever reached the cmap brain (verified 2026-11-08).

## 2. What we set out to do this session, and why

Continue the step-14 wrap-up baton (link in the header): put the wrap-up baton's
§0 owner questions to Albert, then close step 14 after his Map verdict. The
owner questions reached him on 2026-11-09, but instead of answering them inline
he redirected: wrap up BOTH the step-14 closeout chat and the "refactor Oracle"
chat (which had been collecting his in-the-moment rulings and registering the two
plans) into one combined handoff + a coordinator prompt for a fresh session.
Everything AI-executable that could move has moved; what remains is owner-gated
(§0), calendar-gated (§6.4) or unowned smalls (§6.6).

## 3. Current state — what is true right now

DONE and independently verified (full evidence table in the wrap-up baton §3:
https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T1853Z-ah-desktop-mimo-company-map-step14-closeout.md ):
community-size fold fix live-proven at graph_version 27 (PR #451, commit `5783e7ec`;
#437 proof comment 6664715774), mark-as-wrong control built + live-proven + prod
left clean (PR #449, migration `010_review_flag`; #255 comment 6664266352),
taller text boxes (PR #448), 11 silent employees nudged (44/44 conversation refs),
task-4 follow-ups folded into #240 and the task-4 handoff retired (PR #447,
#240 comment 6661335266), orphan-entity hygiene live (PR #454, commit
`a3975710`, deployed 2026-11-05 ~1:50 PM EST, 217/217 tests). Brain image pin
`BRAIN_IMAGE_TAG` = `a3975710e890ddb1c798b398ed4afebe126483d0` deployed and
healthy.

DONE since the wrap-up baton (this closeout chat and the "refactor Oracle" chat,
2026-11-05 → 2026-11-09):
- **GHCR image cleanup — DONE** (the wrap-up baton §6.4 "Blocked" is STALE, and so
  is item 10 of the refactor-Oracle inventory). `ghcr.io/u2giants/theoracle-native`
  and `ghcr.io/u2giants/theoracle-native-browser` were deleted 2026-11-05,
  4:47 PM EST through Albert's signed-in Chrome web UI — NO new credential was
  minted. 404-proof against the read-only packages token (control package
  `theoracle-brain` returned 200 in the same run), proof comment and the ticked
  `- [x] live proof` on https://github.com/u2giants/theoracle/issues/431#issuecomment-6670399410 .
  Done-when met: both names 404 and the #431 live-proof box is ticked.
- **Owner item 4 (documents) settled** — corpus complete (§0, comment
  6725102695).
- **Owner item 3 (405 orphans) settled** — KEEP, no backfill (§0, comment
  6725350744).
- **Two plans registered and merged** — Chinese integration (PR #471, commit
  `4db52531`) and meeting triage (PR #472, commit `dd2e4a46`), with registered
  handoffs, AGENTS.md + docs/agents/03 routing, and their own STATUS tables
  (links in §1).
- **Recall.ai baseline verified live 2026-11-08** (see §1).

NOT started / NOT done (the whole remaining job):
- Task 8 — close step 14: record Albert's verbatim Map verdict in
  `plan_oracle_company_map.md` STATUS row 14 (which still reads "🟨 hosted,
  awaiting owner review"), close #255, post the final drift note on #240.
  Owner-gated (§0.1).
- Task 6 — stage-7 rerun on the final 20 eval questions (#367). Owner-gated (§0.2).
- Interview tick-log check — calendar-gated to 2026-11-11 or later (§6.4).
- Both plan implementations (§6.5) and the unowned smalls (§6.6).

Deploy state (unchanged since 2026-11-05): brain healthy
(`{"ok":true,"db":true,"graph":true}`), web Vercel-auto-deployed from main,
migration 010 applied on prod. `plan_oracle_company_map.md` STATUS row 14 text
(starts "| 14 | Hosting on Coolify + Vercel; first full run on the real corpus |
🟨 hosted, awaiting owner review | #255; health …") is what task 8 must update.

## 4. Everything we tried that did NOT work

Carry-forward dead ends from the wrap-up baton §4 (do not re-walk them):
`ai-task-gates check --before deploy` STOPs on a stale base (WORKING PATH: fresh
`git fetch`, `start --class production --base origin/main`, `check --before
deploy`, supply the owner-quote `--acknowledge`); `--before deployment` is not a
valid verb (use `--before deploy`); a stale `BRAIN_IMAGE_TAG` makes `POST /deploy`
a no-op serving the OLD image (PATCH the pin to the new full sha BEFORE deploying,
then probe a route the old image lacked); `POST /map/rebuild` re-clusters but
`run_communities` reuses reports keyed by (level, entity set) — read `created_at`
to tell new rows; GitHub merges auto-close referenced issues (check `state:`
before assuming an issue still needs closing); Git bash `TZ=America/New_York` is
broken (compute EST in PowerShell only); Windows cp1252 cannot print `→` in proof
scripts (`PYTHONIOENCODING=utf-8`); never redeploy the brain while `cmap.job` has
rows in ('running','queued') — one bounded wait (~4 min), never a sleep loop;
the ai-devops bash tools must run under the Git for Windows bash on this host
(bare `bash` resolves to the WSL stub with no distro installed).

New in this combined wrap-up (2026-11-09):
- `ai-shared-db-closeout-check` still hangs — reproduced 2026-11-09 (stalls at
  "ai-gh call 1 (auth status) waiting for admission"). Substitute check used:
  `gh search issues --repo popcre/shared-db 'ses_ffe5e5262b286ffeXctxMDUACu'` →
  0 matches = zero owned claims. Re-run the real tool once ai-devops repairs it;
  repair belongs in ai-devops, never remove the tool.
- `ai-housekeeping` from PowerShell errors (`ChildProcess.kill`); under the Git
  for Windows bash with `AI_HOUSEKEEPING_GH=gh AI_HOUSEKEEPING_GH_TIMEOUT_SECONDS=15`
  it completes and still reports GitHub: UNKNOWN (the known §4.6 routing issue).
  Report-only; the tool changed nothing.
- `ai-task-gates start` refuses outside a git repository ("cannot classify: not
  inside a Git repository") — this wrap-up ran from the session directory first
  and had to move into a theoracle worktree.
- The owner question form on 2026-11-05 was aborted by the owner before it
  reached him (he asked "is this chat superseded?" instead); the §0 questions
  were re-asked 2026-11-09 and he answered with the combined-wrap-up redirect.
  Lesson: a chat that sits idle for days gets overtaken — put owner questions to
  him the same day or they land in a different chat.
- The OS machine name of this host is `EDGE-DEV`, but every theoracle baton and
  GitHub signature calls it `ah-desktop`. Signatures use `ah-desktop` for
  continuity with the repo's issue history.

## 5. Root causes and key findings

- **The 405 evidence-less entities** exist because `cmap.mention` cascades when
  chunks/sources are deleted but `cmap.entity` had no such link; `DELETE
  /sources/{id}` orphaned them. PR #454 fixed the FUTURE path (scoped, not the
  global smoke-cleanup statement) and deliberately left the 405 standing for the
  owner decision now settled as KEEP. Their stale `mention_count`/`source_count`
  remain uncorrected by design — a backfill is a data change and would need a
  fresh owner say-so.
- **Community sizes (#437):** the L0 merge loop only reached a neighbour through
  an edge or source; no-mention isolates stayed singletons. PR #451's fold pass
  fixed stored membership at graph_version 27 (L0 34 groups 3–102, L1 26 groups
  3–149, none outside [3,150]).
- **`POST /api/teams/bot/proactive` is a free-form messaging channel gated only
  by the shared brain token**, NOT by `BRAIN_INTERVIEW_ENABLED` — anyone holding
  the token can open a chat with any employee and say anything. Fine for the
  sanctioned nudges; a standing risk otherwise. Candidate issue + a gate tying
  the route to `BRAIN_INTERVIEW_ENABLED` or an admin allowlist (§6.6).
- **Brain API auth** needs BOTH `x-brain-token` (1Password vault `vibe_coding`,
  item `4lm6bpl7bc25lqne4meumwcd2a`, field `BRAIN_SHARED_TOKEN`) and `x-user-id`
  (admin Supabase auth user mapped to an active `is_admin` employee;
  `e0968007-7276-46fb-8abd-25baa108f112` verified working).
- **Eval manifests:** authoritative seats are `models.stages.*` inside
  `cmap.eval_run.models`, not legacy top-level keys. The seed-eval mean 0.2 is
  fixture noise, NOT a quality number — the real instrument is the 20 owner
  questions (task 6). Global mode works but is worse (quality 0.59 vs local 0.72,
  ~6× tokens, ~7 min/answer) — prefer local mode for the rerun (evidence:
  https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/bake-off/2026-11-04-bake-off-followups.md ).
- **GitHub Packages deletion needed no token at all** when done through the
  owner's signed-in browser (Package settings → Delete this package → type the
  name). UIA automation works: `chrome.exe <url>` opens a tab in the running
  signed-in Chrome; `ValuePattern.SetValue` silently no-ops on GitHub's React
  confirm inputs — use `SetFocus` + SendKeys. That is why §6.4 of the wrap-up
  baton is stale.
- **The document corpus is complete on the owner side** — the plan's "hundreds of
  sources" expectation is superseded; corpus growth is meetings + Teams, which is
  exactly what the meeting-triage plan serves.
- **Recall.ai is healthy but unused** —7 bots, none since 2026-06-23; the
  meeting-triage plan routes its captures into staging (step 1.3).
- **Supabase MCP notes (from the task-7 baton, still true):** the `supabase-oracle`
  entry runs `scripts/mcp-supabase-launch.mjs` (machine-private targets profile,
  key `oracle_supabase_project`; `ORACLE_TARGET_PROFILE_PATH` overrides); no
  project ref may ever be committed; `--read-only` is deliberate; the field named
  `password` on the Supabase 1Password item is an IPv6-only direct URL — use
  `oracle_session_pooler` instead.

## 6. Exact next steps (coordinator queue, in order)

1. **Put §0's two blocking owner questions to Albert in ONE message** (Map review
   verdict; Ilona nudge-or-you-chase). Do NOT re-ask anything in §0's settled
   list. You'll know it worked when he answers — the Map verdict may arrive as
   "clean" or as a marked-wrong list; either is the verdict to record verbatim.
2. **Task 8 — close step 14 (only after the Map verdict, §0.1).** Record
   Albert's verbatim Map verdict in `plan_oracle_company_map.md` STATUS row 14,
   close #255, and post a final drift note on #240 (the full drift report is
   already there). The drift note must also carry: the task-4 follow-up is
   already folded (https://github.com/u2giants/theoracle/issues/240#issuecomment-6661335266 ),
   the 405-orphan outcome (KEEP, no backfill, #255 comment 6725350744), and the
   proactive-endpoint risk (§5). Branch + PR + squash-admin merge for the STATUS
   edit (never push to main). You'll know it worked when #255 is closed and
   STATUS row 14 holds Albert's verbatim words.
3. **Task 6 — stage-7 rerun on the final 20 questions (#367) (only after Ilona
   approves, §0.2).** Exact text, verbatim from the executed baton §6.2: "On
   artifact `05282281-8fc8-4d2f-a61e-4760a9bdb45e` (the question page), run
   `db_get` review/status, then `db_list` the questions collection, enter the
   questions on the eval page, and rerun answers (local and global mode) on a
   cloned DB. The page buttons are untested in a signed-in browser. Done when:
   #367 is closed with a rerun report in the bake-off folder." Use a cloned DB
   (own test clone on edge-dev3, never `brain2-test-*`, never prod); prefer
   local mode per §5. Claude artifact pages are not readable by fetch — use the
   Chrome read path in the wrap-up baton §4.5.
4. **2026-11-11 or later — interview tick-log check.** Verify the Phase-3
   done-when: ≥3 scheduled questions sent to employees within one week AND ≥1
   answer became a source. Query `cmap.open_question` / `cmap.interview_send` /
   `cmap.source` (pooler path: 1Password item `qcuyabwseaptvuzvtjejffi2ou`, field
   `oracle_session_pooler`, piped on stdin to an edge-dev3 script) or
   `GET /interview/overview` with the brain shared token + admin `x-user-id`.
   Post counts and pass/fail on #255, signed. Recipe:
   https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0307Z-edge-dev-mimo-teams-followup-255.md §6.
5. **Dispatch the two registered plan implementations** (one session each, own
   worktree from fresh main, own test DB clone and FalkorDB container on
   edge-dev3). Fresh session starts at each plan's STATUS row 0.1. The meeting
   triage session opens ONE tracking issue at implementation start with
   `- [ ] live proof` (plan §13) and keeps it open until step 3.1's
   `docs/verification/meetings/live-proof.md` exists. The Chinese session works
   the phases in plan order (0.1 CJK-safe foundation first). Both plans' owner
   moments (§0.3–§0.4) are their closing gates, not startup asks. You'll know
   each worked when its own plan's STATUS table and done-when gates say so.
6. **Unowned smalls (any session may take):** file or fix the proactive-endpoint
   gating risk (§5) — a new issue is fine for this one; triage the stale draft
   PRs on the repo (#407, #377, #268, #232 — close or revive each with a dated
   note); the #450 review-fixer lane item (`test_review_flags_unit.py`) is the
   auto-fixer's, not ours; the 405-orphan count backfill stays un-done unless
   the owner asks (§0 settled); the two "Debounce proof 2026-11-05 (a)/(b)"
   transcripts in the prod corpus are clearly labelled and stay until the owner
   asks for removal (deleting re-triggers the chain by design).

You'll know each step worked when its stated done-when fires. The overall verify
for the program: **#255 closed and STATUS row 14 holds Albert's verbatim words.**

### Coordinator prompt for the fresh session (paste to start the successor)

```text
You are the COORDINATOR for the remaining POP Creations "The Oracle" work — the
u2giants/theoracle Company Map step-14 closeout plus two registered plans. Repo:
u2giants/theoracle (PUBLIC). Work from a fresh origin/main worktree; NEVER push
to main (branch + PR + `gh pr merge --squash --admin`; docs-only PRs need the
ai-devops `ai-doc-safety` copy green on the head — run it under the Git for
Windows bash). Sign every GitHub post: `Posted by MiMo chat <session id> on
ah-desktop`. All human-facing times in EST (America/New_York), computed in
PowerShell.

Read first, in this order:
1. https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-09T1620Z-ah-desktop-mimo-step14-refactor-combined-remaining.md
   (this combined baton — your queue is its §6; owner asks are its §0)
2. https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T1853Z-ah-desktop-mimo-company-map-step14-closeout.md
   (day-round outcomes, dead ends §4, task texts §6)
3. https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0812Z-ah-desktop-mimo-company-map-remaining.md
   (original task texts — KEEP this file until #255 closes)

Then, in order:
(1) Put the combined baton's §0 blocking questions (Map review verdict; Ilona's
    20-question review + bot-nudge call) to Albert in ONE message. Never re-ask
    anything in §0's settled list.
(2) After his Map review verdict: record his VERBATIM words in
    plan_oracle_company_map.md STATUS row 14, close #255, post the final drift
    note on #240 (contents named in the baton §6.2).
(3) After Ilona approves the 20 questions: the #367 stage-7 rerun (exact text in
    the baton §6.3) on a CLONED DB only, never prod.
(4) On or after 2026-11-11: the interview tick-log check (baton §6.4).
(5) Dispatch the two plan implementations (baton §6.5) as per-task sessions when
    ready: plan_chinese_integration.md and plan_meeting_triage_pipeline.md, each
    starting at its STATUS row 0.1.
(6) Unowned smalls (baton §6.6) as capacity allows.

Coordinator discipline: one subagent/session per ready task, each in its own
worktree from fresh main; verify every child report against GitHub and the live
services yourself before believing it; never delegate a decision (merge,
database, production, security); never end a turn on "waiting" — use the bounded
waiters. Public repo hygiene: no secrets, no LAN IPs, no Supabase project refs
anywhere. Secrets live in 1Password vault `vibe_coding` (item IDs in the baton
§8) and never appear in chat, argv, logs or commits. Never redeploy the brain
while `cmap.job` has running/queued rows; env-pin `BRAIN_IMAGE_TAG` before
deploy. Interviews stay OFF until Albert turns them on.

Done-when for the whole program: #255 is closed and STATUS row 14 holds Albert's
verbatim Map verdict.
```

## 7. Constraints and gotchas in force

- Never push to protected `main`: branch + PR + `gh pr merge --squash --admin`.
  Docs-only PRs run the ai-devops `ai-doc-safety` copy (whole-tree mode; a
  docs-only PR is judged by its own file appearing in ZERO failure lines of the
  whole-tree output — pre-existing debt in pnpm-lock/DECISIONS.md/legacy links is
  separate work, not a wrap-up item).
- Public repo hygiene: no secrets, no LAN IPs, no Supabase/Trigger project refs
  in code, commits, issues or PRs. Employee names/emails follow the @popcre.com
  style. File references in handoffs and prompts are GitHub URLs only — never
  machine-local paths.
- Times in EST (America/New_York) in every human-facing message; compute them in
  PowerShell (Git bash `TZ=America/New_York` is broken).
- Task gates: `ai-task-gates start --class <class>` from INSIDE a git worktree;
  `check --before deploy|database|ship` before risky steps; production class
  demands `--acknowledge "<Albert's exact words>"`. Migration files (`**/*.sql`)
  classify `shared-db`.
- Never redeploy the brain while `cmap.job` has ('running','queued') rows; only
  ONE session deploys at a time; env PATCH (pin `BRAIN_IMAGE_TAG` to the new full
  sha) BEFORE `POST /deploy`; verify a route the old image lacked afterwards;
  Coolify env listings echo secrets — filter to one key, never print the body.
- Interview questions stay OFF (standing owner direction) until Albert enables
  them — and mind the proactive-endpoint risk (§5).
- Sign every GitHub post: `Posted by MiMo chat <session id> on <machine>`
  (`ah-desktop` on this host).
- OpenRouter: check `limit_remaining` before spend; stop under $5 of the $25/day
  cap.
- HANDOFF.d discipline: never edit another session's file; never rewrite the root
  `HANDOFF.md` (it is the static pointer); retire a predecessor only under the
  successor rule (its issue closed + landed verified + every obligation carried
  forward). The 0812Z and 1853Z batons both stay until #255 closes. Never add a
  file-count cap: report SUCCESSOR REVIEW candidates by name and owner instead.
- Each task session: own worktree from fresh main, own test DB clone and FalkorDB
  container on edge-dev3 (never `brain2-test-*`), background PR waiter
  (`bin/ai-pr-wait`, 60-minute deadline), never end a turn on "waiting", never
  spawn its own children without coordinator approval.

## 8. Access and environment

- Machines: ah-desktop (Windows; OS name `EDGE-DEV`) and edge-dev3 (Linux test
  services host over ssh). Canonical checkout and worktree layout live in the
  machine atlas: https://github.com/popcre/ai-devops/blob/main/templates/system/machine-atlas.md
  — resolve paths from it on any machine. This wrap-up used its own worktree
  `wt-combined-wrapup-handoff` (branch `handoff/step14-refactor-combined`) from
  fresh origin/main; other worktrees on the host belong to other sessions — do
  not touch them.
- `gh` authenticated as `u2giants` (scopes `gist, read:org, repo, workflow` — no
  `read:packages`, no `delete:packages`). Commit identity must show
  `Albert Hazan <u2giants@users.noreply.github.com>` (`git var GIT_COMMITTER_IDENT`).
- 1Password MCP, vault `vibe_coding` (values only via pipes/protected files —
  never chat, argv, logs, commits; item-ID form of op:// refs): shared brain
  token item `4lm6bpl7bc25lqne4meumwcd2a` field `BRAIN_SHARED_TOKEN`; Supabase
  item `qcuyabwseaptvuzvtjejffi2ou` field `oracle_session_pooler` (WORKING — the
  field named `password` is an IPv6-only direct URL, unusable); Muse/Meta key
  item `czggiabkpo7dt7ojep4btdvq5i`; Coolify item `u3aqw63jqnkmnziip3gp5hwb5m`
  field `credential`; read-only packages token is the item titled "GitHub token
  with Packages read access for u2giants/backrest-wiz" (GHCR cleanup is done —
  only needed for package 404 re-checks).
- Prod DB reads: psycopg from edge-dev3 (`python3 -m pip install --target
  /tmp/pylibs 'psycopg[binary]'`, `PYTHONPATH=/tmp/pylibs python3 <scp'd script>`,
  pooler URL piped on stdin). psql is not installed there.
- Brain API https://oracle-brain.designflow.app — `/health` free; everything else
  needs `x-brain-token` + `x-user-id` (§5). Coolify API `http://hetz:8000/api/v1`
  from ah-desktop; app uuid `uge6pfm4qapktivto4981mtg`; deploy
  `POST /api/v1/deploy?uuid=uge6pfm4qapktivto4981mtg`. cmap migrations run via
  `python -m brain.migrate` (idempotent; a deploy does NOT apply them by itself).
- Meeting-triage plan (step 0.1) will need `AZURE_TENANT_ID`,
  `AZURE_GRAPH_CLIENT_ID`, `AZURE_GRAPH_CLIENT_SECRET` put into the brain Coolify
  env — values from 1Password vault `vibe_coding` (search Microsoft Graph / Azure
  items; the plan's step 0.1 owns it). Recall.ai API key is already in use and
  was verified live 2026-11-08 (its vault item title was not captured here —
  search `Recall` in the vault before use).
- ai-devops toolkit lives in its own checkout on the host; run its bash tools
  (`bin/ai-doc-safety`, `bin/ai-pr-wait`, `ai-housekeeping`) under the Git for
  Windows bash, never bare `bash`/PowerShell alone (§4).

## 9. Open questions and risks

- **`POST /api/teams/bot/proactive` free-form gating risk** (§5) — no incident;
  issue + fix is a §6.6 item. Until then the route is a standing exposure to
  anyone holding the shared brain token.
- **The 405 orphans' stale counts** stay uncorrected by the settled KEEP decision;
  if the owner ever asks to fix counts, that is a data change needing its own go.
- **Two proof transcripts remain in the prod corpus** ("Debounce proof
  2026-11-05 (a)/(b)"), clearly labelled; remove only on owner request.
- **One `interview_tick` job failed** earlier on 2026-11-05 (single failure, rest
  healthy) — re-queue if the tick-log check finds a content gap (§6.4).
- **Coolify env listing echoes secrets** — filter to one key; never print the
  body. A local-only echo of an existing value seen on 2026-11-05 stays
  unrotated per the standing rule (exposed only on that machine).
- **`ai-shared-db-closeout-check` hangs** (reproduced 2026-11-09, §4) and
  **`ai-housekeeping`'s GitHub routing reports UNKNOWN** — repair in ai-devops;
  never remove them. Housekeeping inventory at this wrap-up (2026-11-09,
  report-only): 38 open handoffs (0 successor-review, 3 unprovable, 6
  unattributed), 5 active plans, 4 unknown worktrees + 3 unknown branches on the
  host (merged-ness unknowable while GitHub routing is down).
- **Stale draft PRs** #407, #377, #268, #232 on the repo — triage candidates
  (§6.6).
- **`@latest` on `@supabase/mcp-server-supabase`** (inherited pinning gap from
  task 7) — upstream can change under us; pin later if determinism matters.
- **Stale plan expectation:** the company-map plan expects "hundreds of sources"
  from document uploads; the owner ruled the document corpus complete
  (2026-11-08). Corpus growth is meetings + Teams. Do not treat low source count
  as an unfinished owner task.
- **Both predecessor batons still describe the GHCR cleanup as Blocked** — it is
  DONE (§3). If a later session "resumes" that item, stop: read §3 first.

---

## Part (b) — sub-agent and sibling-session blocks

### Agent: general-1 (MiMo actor subagent, GHCR image cleanup — this session)
- **Asked to do:** delete `theoracle-native` and `theoracle-native-browser` from
  GitHub Packages via the u2giants signed-in browser; never ask Albert; no new
  credential unless unavoidable; prove 404; record on #431.
- **Actually did:** deleted both packages through the GitHub web UI in Albert's
  signed-in Chrome (Package settings → Delete this package → typed name to
  confirm) — no PAT minted; verified 404 for both names with the read-only
  packages token (`theoracle-brain` control returned 200 in the same run);
  posted the proof comment on #431 and ticked the closing comment's
  `- [x] live proof` box. Signature
  `Posted by MiMo chat ses_ffe5e5262b286ffeXctxMDUACu on ah-desktop`, 4:47 PM EST
  2026-11-05.
- **Found:** UIA can drive GitHub's React confirm inputs with `SetFocus` +
  SendKeys (`ValuePattern.SetValue` silently no-ops); `1password_op_run` secret
  refs resolve by item ID, not by title-with-spaces; the read-only packages token
  cleanly distinguishes deleted (404) vs live (200) packages.
- **PR / branch:** none (no repo changes; scratch scripts in the machine TEMP
  directory only, no secrets in them).
- **Worktree:** none created; finished.
- **Deliberately did NOT do, and why:** did not touch any other package
  (`theoracle-brain` and the other 21 live packages were named as untouchable);
  did not mint a `delete:packages` PAT because the web UI path sufficed; did not
  rotate anything (no secret leaked).

### Sibling session: "refactor Oracle" chat (MiMo, `ses_ffe5e4443fa74ffeHY8R68xzp4`, ah-desktop)
Not a sub-agent — a second Desktop chat whose open items are folded into §0/§3/§6
of this file at Albert's order. It stood down 2026-11-09, wrote no HANDOFF.d of
its own, and reported:
- Two registered plans merged (PRs #471/#472 — §1) with registered handoffs
  (§ header links) — implementation starts at each plan's STATUS row 0.1.
- Recall.ai baseline verified live 2026-11-08 (§1/§5).
- The 2026-11-08 owner rulings on documents and the 405 orphans (§0), and the
  clarification to Albert of what the Map review gate is.
- Its secrets sweep: one local exposure found and redacted — historical Teams
  meeting passwords (`business_meeting_password`, June-2026 meetings) from a
  Recall bot listing had landed only in a local tool-output file on ah-desktop;
  7 values redacted 2026-11-09, zero raw values remain, local-only exposure so no
  rotation per the standing rule. No credential appeared in chat text; repo docs
  reference secrets by vault title only (both PRs passed `ai-doc-safety`).
- Its observation of stale draft PRs #407/#377/#268/#232 (§6.6).

## Self-audit (handoff-writer gate, 2026-11-09)

1. *Could a brand-new developer pick up and not skip a beat?* Yes — §1 orients
   the app and both plans, §3 pins every completed item with PR/issue/commit
   evidence and flags the two stale "Blocked" lines, §6 gives the ordered queue
   with done-when gates plus the paste-ready coordinator prompt.
2. *Could they continue as effectively as me right now?* Yes — §4 carries this
   round's dead ends (hanging closeout-check + its substitute, housekeeping
   routing, gates-needs-a-repo, the idle-chat-overtaken lesson) alongside the
   predecessor's via §3/§4 links; §5 carries every root cause and live finding.
3. *Every relevant detail included?* Background (§1–2), outcomes (§3), failures
   (§4), findings (§5), actions (§6), constraints (§7), access (§8), risks (§9),
   owner decisions (§0), sub-agent + sibling blocks (part (b)). GitHub URLs
   throughout; secrets by vault/item only; deploy and merge status explicit.
4. *Does §0 hold every owner decision and no technical approval?* Yes — the
   sweep found two blocking asks (Map verdict, Ilona + nudge call) and four later
   plan-internal moments (§0.3–§0.4); everything else is either settled with
   dated verbatim quotes, technical (filed/queued in §6/§9), or `Blocked —`-free
   (the only former blocker, GHCR, is done). The settled list prevents re-asking.
