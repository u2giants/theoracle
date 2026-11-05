---
issue: 255
status: OPEN
owner: claude/close-nested-coordinator (edge-dev3)
---

# Company Map step 14: whole session tree closed, coordinator baton

Written 2026-11-04, 8:40 PM EST, edge-dev3, Claude (coordinator). Program
parent https://github.com/u2giants/theoracle/issues/240 ; step 14
https://github.com/u2giants/theoracle/issues/255 . Spec
https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md .

This file merges every open task from the coordinator and all its nested
sessions. **The successor is a coordinator only.** It starts one nested session
per open task in §6, verifies each result against GitHub and the live brain,
and does no task work itself.

## 0. Owner items (put to Albert in ONE message; none blocks §6 tasks 1–5)

1. **Share Ilona's question page** https://claude.ai/artifact/1dw8ZoafmchL3HZ9mW26KX
   with Ilona as Contributor. Only Albert can share it. Blocks task 6 (#367).
2. **Ilona (and Albert) edit and approve the 20 questions** on that page.
3. **30-minute Map review** after task 1's rebuild and eval land: mark wrong
   items. Blocks closing #255. Also look at the flowchart: it now has 75 arrows
   against 67 in the reference.
4. **Send the rest of the company documents.** The plan expects hundreds; the
   Map has about 31 sources (drift report on #240).

Settled. Do NOT re-ask:
- 2026-11-04 vision seat: coordinator chose `anthropic/claude-sonnet-5.5`
  (diagram bake-off winner, 0.99; PR #417, summary on #413).
- 2026-11-04 relations seat: Muse blocked on OpenRouter, so coordinator seated
  `z-ai/glm-5.3` (stage-4 runner-up, F1 equal to Muse).
- 2026-11-04 Albert, in the T6 session, verbatim: "i want the brain to use the
  Muse direct API key" (task 2).
- All of the predecessor baton's §0 "settled" list.

## 1. What this application is

See predecessor https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-03T2349Z-edge-dev3-claude-model-bakeoff-coordinator.md
§1 and §8 (access). Brain on Coolify as `oracle-brain`
(https://oracle-brain.designflow.app), web https://oracle.designflow.app ,
Postgres schema `cmap`, FalkorDB graph `company`. The repo is PUBLIC.

## 2. Tree closed

Every session started from the coordinator, with its final state:

| Session | Final state | Branch |
|---|---|---|
| T1 verify model page | gate passed (seats followed the switch and ended on winners) | none, no code |
| T2 #359 seat/reembed | merged #371, #359 closed | deleted |
| T3 #347 report cap | merged #383, #347 closed; also #387 (#382) | deleted |
| ↳ #382 quiet-hours test | merged #387 | deleted |
| ↳ #398 retire Oracle 2 | merged #402, #406; see task 7 | see task 7 |
| T4 #344 embedding cost | merged #391, #344 closed | deleted |
| T5 #353 resolve rules | merged #393, #353 closed (22/23 real duplicates caught) | deleted |
| T6 deploy and rebuild | handoff #427; rebuild in flight (task 1) | merged |
| T7 #345 doc safety | merged popcre/ai-devops#2335, installed, #345 closed | merged |
| T8 #358/#339 | merged #370, both closed | deleted |
| T9 job brief | merged #372 | deleted |
| T10 Teams build-out | merged #374 #378 #379 #380 #384 #388; migrations 006, 007 on prod | clean |
| T11 lessons sweep | merged #396 #400 #403 #409 #411 #417 #419 #420 #421 | merged |
| ↳ #399 name thresholds | merged #403, #399 closed | deleted |
| #410 communities | merged #412, #414, #410 closed | deleted |
| Plan drift check | report posted on #240; opened #410 | none |

## 3. Landed (verified merged on GitHub, 8:38 PM EST)

theoracle PRs 370, 371, 372, 374, 378, 379, 380, 383, 384, 387, 388, 391, 393,
396, 400, 402, 403, 406, 409, 411, 412, 414, 417, 419, 420, 421, 427; plus
popcre/ai-devops PR 2335. Closed issues: 339, 344, 345, 347, 353, 358, 359,
363–366, 368, 369, 382, 390, 399, 410, 413, 418.

Live, verified: brain image `4402117e49f8b3f6a11915e56edd93e226faa064` since
7:03 PM EST; `/health` all true; `GET /models` has vision
`anthropic/claude-sonnet-5.5`, relations `z-ai/glm-5.3`, the rest as in the
predecessor §3. Flowchart gate MET: 75 arrows, 62 labels, 0 invented, 67 of 67
reference arrows. Plan drift report:
https://github.com/u2giants/theoracle/issues/240#issuecomment-6641895758 .
Teams: tenant install for 50 employees (33 chats), 11 employees contributed
on 11/4, and every contribution is in the Map.

## 4. What did not work (new this round)

1. Muse returned 403 user_blocked ("repeated policy violations") on our
   OpenRouter key from 7:41 PM EST. All 27 relations jobs failed, and the Map had 0
   relations until the re-seat (#426).
2. Each Teams answer starts a full resolve→communities chain, so redeploy
   windows keep closing (#415). The new code made communities take minutes.
3. GLM flat sometimes returns invalid JSON: 5 sources failed on the 7 PM re-read,
   and 1 retry succeeded. Re-queue fixes it.
4. The Teams intake marks a thread failed on an ingest timeout and never
   retries (thread 53e27059, reopened by hand). See task 3.
5. Nested sessions repeatedly ended turns on "waiting" with no waiter, and
   needed nudges. Brief each child to use a run_in_background waiter.
6. Sessions spawned their own children (#382, #398, #399). Watch for scope
   creep: #398 removed Oracle 2 code without the coordinator asking.

## 5. Child handoffs (read them; never edit them)

- T6: https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0115Z-edge-dev3-claude-t6-prod-rebuild.md
- T11: https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-04T2339Z-edge-dev3-claude-t11-lessons-sweep.md
- T10 has no repo handoff; its proof is on #255 (see task 3–5 below).
- Predecessors (keep until #255 closes):
  https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-03T2349Z-edge-dev3-claude-model-bakeoff-coordinator.md ,
  https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-02T2057Z-edge-dev-mimo-model-overhaul-bakeoff-round2.md
  (Appendix A has the 20 questions).

## 6. Open tasks (one nested session each)

Rules for every child: own worktree from fresh main; own DB clone and own
FalkorDB container on edge-dev3 for tests; branch, PR, `gh pr merge --squash
--admin`; wait with `bin/ai-pr-wait <pr> --repo u2giants/theoracle` run in
the background; never end a turn on "waiting"; never redeploy the brain while
a `cmap.job` row is running (check `select kind,state from cmap.job where state
in ('running','queued')`); check OpenRouter `limit_remaining` and stop under
$5. Coolify API from edge-dev3: `http://hetz:8000/api/v1` (tailnet). Only ONE
child deploys at a time: tasks 1, 2, 3 and 7 all touch the live brain, so run
them one after another, in that order.

### Task 1. Finish the prod rebuild and seeded eval (#255)
State at 8:32 PM EST: relations re-seated to `z-ai/glm-5.3` at 7:58 PM EST. Since
then: relations 16 done, 1 running, 14 queued; classify_extract 4 done and 1
failed (GLM invalid JSON); resolve 1 queued; project and communities follow
automatically. Relations count 1057. Entities 1146 are stale until resolve runs.
OpenRouter had $22.51 left. No eval_run yet.
Next: when the queue is empty, re-queue the one failed classify_extract. Check
relations > 0, `/map/company` populated, and community sizes sensible (#410
fix: no group of 2 or fewer at L0/L1, none larger than ~150). Then `POST
/eval/run`. Read the newest `cmap.eval_run` and post its id and counts on #255.
Done when: an eval is stored whose `models` manifest shows relations
`z-ai/glm-5.3` and vision `anthropic/claude-sonnet-5.5`, and the Map is
populated. Resume: main.

### Task 2. Brain uses the Muse direct API key (#426); after task 1
Albert, verbatim: "i want the brain to use the Muse direct API key". Add a
direct Meta provider route keyed off the seat's model id. Put the key in Coolify
env from 1Password item `czggiabkpo7dt7ojep4btdvq5i` via op:// refs only. Add
tests, then PR, deploy when idle, and re-seat relations to Muse. Also find out what
triggered the OpenRouter block (needs the OpenRouter activity log) and whether
other models on the key are at risk. Remove Muse from the page's OpenRouter
candidates while it is blocked. Done when: a prod relations job succeeds on
direct Muse and `GET /models` shows it. Resume: new branch from main.

### Task 3. Teams intake auto-retry and root cause (#255 proof); after task 2
Prompt from the T10 session, kept verbatim: "Teams intake:
apps/brain/brain/interview/intake.py. Problem: close_thread() marks a thread
'failed' when ingest_bytes raises (e.g. "The read operation timed out", thread
53e27059, 2026-11-04 ~12:12 PM EST) and nothing retries, so contributions are
silently lost. Do: 1) find the root cause (brain logs on Coolify app
oracle-brain ~17:12 UTC) and fix it; 2) worker sweep retries failed threads
with transient errors (retry count, backoff, max 5), never double-ingesting;
3) tests in apps/brain/tests/test_interview.py; 4) own worktree, PR, merge,
migrate, deploy, prove live that a forced failure retries into a read source."
Open an issue for it first. Done when: that live proof is posted on the issue.

### Task 4. Debounce the per-source chain (#415); after task 3
https://github.com/u2giants/theoracle/issues/415 . Batch resolve→communities
so a burst of Teams answers runs the chain once. Done when: per the issue, and
proven live with two sources arriving close together.

### Task 5. Teams follow-through checks (#255); any time, read-only
(a) Phase 3 done-when: scheduled questions sent to at least 3 employees in a
week and at least one answer became a source. Check the interview tick log
after 2026-11-11. (b) 7 Teams-enabled employees have no bot chat: re-run the
install dry-run and check those users' installed apps. Done when: each has a
stored conversation or a known cause posted on #255.

### Task 6. Stage-7 rerun on the final 20 questions (#367); after owner items 1–2
https://github.com/u2giants/theoracle/issues/367 . On artifact
`05282281-8fc8-4d2f-a61e-4760a9bdb45e` (the question page), run `db_get`
review/status, then `db_list` the questions collection, enter the questions on
the eval page, and rerun answers (local and global mode) on a cloned DB. The page
buttons are untested in a signed-in browser. Done when: #367 is closed with a
rerun report in the bake-off folder.

### Task 7. Finish retiring Oracle 2 (#398); after task 1
Code and checks are removed (#402, #406) and the old jobs are paused. Still
owed: back up, then drop, the old Oracle 2 database tables, and remove the old
jobs' settings, per the five-phase plan on
https://github.com/u2giants/theoracle/issues/398 . This is destructive. Take a
verified backup first and load `shared-db-change` if any shared-db object is
involved. Done when: #398 closed with backup location and drop evidence.

### Task 8. Close step 14 (T12); last, after owner item 3
Record Albert's verbatim Map verdict in plan STATUS row 14, close #255, and post
a final drift note on #240 (the full drift report is already there). Done when:
#255 closed.

## 7. Constraints

Predecessor §7 applies. Public repo: no LAN IPs, project refs, or secrets.
Never push to main. Times in EST. Task gates: `ai-task-gates start --class
production --base <fresh main>`.

## Self-audit

1. A newcomer can continue: yes, §2, §3, §6 plus the predecessor §8.
2. As effective as me: yes, §4 holds the new traps.
3. Every detail: §6 tasks give state, next action and done-when; job counts
   are as of 8:32 PM EST.
4. Owner sees every decision in §0 only: yes.
