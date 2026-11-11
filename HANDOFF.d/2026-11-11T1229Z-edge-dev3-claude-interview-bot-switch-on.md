---
issue: 518
status: OPEN
owner: claude/handoff-interview-switch-on
---

# Handoff — Interview bot: flood stopped, logic reworked, bot deliberately OFF (2026-11-11)

Written 2026-11-11, 7:35 AM EST, machine edge-dev3, Claude Code session
`1caa41fd-09ea-429d-8fe6-1a65276dc3f1`. Tracking issue:
https://github.com/u2giants/theoracle/issues/518 (its checklist is the definition of done).

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

Put the whole list to Albert in ONE message before starting work.

**Blocking**
1. **When to turn the question bot back on.** It is off by his instruction. Recommendation:
   turn it on during a weekday morning so the first few questions can be watched as they go out.
   Blocks next steps 2–5 (everything except step 1).

**A wrong guess is recoverable**
2. **Two waiting questions have no person or department that would know the answer.** They will
   never be sent on their own. Recommendation: leave them; Albert can assign them on the
   Company Map questions page if he cares about them.
3. **25 older questions are still marked "asked" from before the flood and were never answered.**
   Recommendation: let them lapse (they free up after 3 days) rather than chase people.

**Not part of this work and nobody is on it** — none that need a business ruling. (The failing
background job in §9 is technical and is the AI's to fix.)

**Already settled — do NOT re-ask**
- 2026-11-10: nobody should get a pile of questions; one at a time, human pace (Albert).
- 2026-11-10: do NOT dedupe new questions against old questions. Albert, verbatim: "we shouldn't
  be checking questions against previous questions. if it was answered, the data (answer) should
  be in the brain and it shouldn't have that question at all."
- 2026-11-10: questions go to someone in the relevant department, not to whoever is nearby
  (Albert: "why was it sending me questions about the licensing process if i'm not in the
  licensing department").
- 2026-11-10 "keep the bot off for now"; 2026-11-11 7:28 AM EST "Keep it off" (Albert).
- 2026-11-10: weekly cap of 2 questions per person was restored by another session (PR #508).

## 1. What this application is

The Oracle is POP Creations' internal knowledge system. Repo
https://github.com/u2giants/theoracle. Its "brain" (Python, FastAPI plus one background worker
thread; code under [apps/brain](https://github.com/u2giants/theoracle/blob/main/apps/brain)) reads uploaded company documents and
conversations, builds a "Company Map" of people, departments and how work flows, and notices
gaps. For each gap it stores an "open question" and a Teams bot (the "interview bot") asks an
employee; the reply is fed back in as knowledge. The brain runs as container image
`ghcr.io/u2giants/theoracle-brain:<commit sha>` on the Coolify app `oracle-brain`
(health: https://oracle-brain.designflow.app/health). Its database is the Oracle Supabase
project `eqccjfbyrywsqkxxpjvg`, schema `cmap`. Routing guide for the repo:
[AGENTS.md](https://github.com/u2giants/theoracle/blob/main/AGENTS.md).

Vocabulary: **tick** = the hourly job `interview_tick` that picks and sends questions.
**Vetting** = an AI check of each candidate question (already answered? how important 1–5? who
would know? which department?). **Area/community** = a cluster of related people/things that the
brain writes a report about; questions are produced per area by the `communities` job.

## 2. What we set out to do, and why

Incident: on 2026-11-10 between about 4 PM and 7:02 PM EST the bot sent roughly 1,700 questions
to 19 people. Trigger: PR #507 (another session) removed the weekly per-person cap while about
8,400 questions were waiting. Albert asked to stop it immediately, then to fix the underlying
logic: no importance judgement, replies not checked, wrong recipients, and thousands of
near-duplicate questions.

## 3. Current state — what is true right now (verified 2026-11-11 7:29 AM EST)

- **Bot is OFF two ways.** `cmap.interview_setting.enabled = false`, AND all 74 rows in
  `cmap.employee_flags` have `interviews_paused = true`. No question has been sent since
  7:02 PM EST 2026-11-10 (latest `cmap.open_question.asked_at`; zero `cmap.interview_send`
  rows after that).
- **Backups in the database:** `cmap.zz_pause_backup_20261110` (the 35 employee-flag rows as
  they were before everyone was paused — the source of truth for who was ALREADY paused);
  `cmap.zz_flood_backup_20261110` (the 1,702 flood questions before they were dismissed).
  Another session separately moved the flood's send-log rows to
  `cmap.interview_send_flood_backup_20261110` (see that session's handoff:
  [zh routing and acceptance](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-11T0048Z-ah-desktop-mimo-zh-routing-and-acceptance.md)).
- **Question counts:** open 67 (all vetted, priority 3–5), asked 25 (pre-flood, unanswered),
  answered 20, dismissed 10,074.
- **All code is merged to main and deployed.** Live image tag = commit
  [3c7e2e39](https://github.com/u2giants/theoracle/commit/3c7e2e39). Nothing unpushed. PRs:
  [#510](https://github.com/u2giants/theoracle/pull/510) pacing (one question in flight per
  person, 3 a day at most, switch re-read before every send);
  [#511](https://github.com/u2giants/theoracle/pull/511) questions only from what the brain does
  not know; [#514](https://github.com/u2giants/theoracle/pull/514) vetting, priority, routing by
  suggested person/department, reply check;
  [#516](https://github.com/u2giants/theoracle/pull/516) jobs left "running" by a restart are
  requeued 3 minutes after boot (proven live 8:56 PM EST 2026-11-10).
- **Database change applied to production:**
  [015_question_priority.sql](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/015_question_priority.sql) (columns
  `priority`, `suggested_person`, `department` on `cmap.open_question`).
- **Not verified live:** the reply check has only passed automated tests; no real Teams reply
  has gone through it because the bot is off. Sending under the new rules is likewise untested
  live.
- **Not started:** switching back on (waits on §0 item 1).

## 4. Everything we tried that did NOT work

- **Turning only the switch off.** The tick that was already running had read the switch once
  and kept sending. Fix at the time: pause every employee. Permanent fix: #510 re-reads the
  switch before every send.
- **Supabase MCP for writes.** It is read-only here. Writes need psql with the production URL
  (see §8).
- **Direct database host.** IPv6 only, unreachable from this machine; use the pooler host
  `aws-1-us-east-1.pooler.supabase.com` with user `postgres.eqccjfbyrywsqkxxpjvg`.
- **Dedupe new questions against old ones by similarity** (first version of the fix). Albert
  rejected it as backwards; removed in #511 and replaced with the knowledge check.
- **Deploying #514 before applying migration 015.** The code expected the new columns.
  Migrations are NOT run on startup; run `python -m brain.migrate` from apps/brain against
  production first.
- **Hand-written wait loops on a PR.** A hook blocks them; use `ai-pr-wait <pr>
  --timeout-minutes 9 --fit-tool-call`.
- **Another session switched the bot back on at about 7:24 PM EST 2026-11-10** while this work
  was in progress; it was switched off again. Re-check the switch before trusting it.
- **`e.department` in SQL.** The employee table differs between production and the test
  schema; the code uses `to_jsonb(e)->>'department'` so it works in both.

## 5. Root causes and key findings

- Flood: no per-person pacing once the weekly cap was removed, plus a huge backlog. Pacing now
  lives in [tick.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/interview/tick.py) (`DAILY_CAP`, `OUTSTANDING_DAYS`,
  `_busy_employees`).
- Backlog of ~8,400: every rebuild of an area re-wrote its questions in new words and never
  retired the old ones. Now each rebuild retires unasked questions of rebuilt areas and re-vets
  kept ones — [communities.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/graph/communities.py)
  (`vet_questions`, `_store_open_questions`, `_refresh_open_questions`); a question that
  could not be vetted is never stored. Prompts:
  [knowledge_check.md](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/prompts/knowledge_check.md),
  [community_report.md](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/prompts/community_report.md).
- Wrong recipients: a question's `entity_ids` are ALL members of its area, not the people the
  question is about, so "connected" people were effectively random. `select_target` in tick.py
  now uses a manual target, else the vetted suggested person, else the least-recently-asked
  reachable employee of the vetted department; an empty department means nobody.
- Replies: any reply used to be saved as the answer. Now
  [inbound.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/interview/inbound.py) `classify_reply` sorts it into
  answer / dont_know / other ([reply_check.md](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/prompts/reply_check.md));
  it fails open to "answer" if the check itself errors.
- The tick only sends questions with `priority IS NOT NULL OR target_employee_id IS NOT NULL`,
  highest priority first.
- Tests: [test_interview.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_interview.py),
  [test_communities.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_communities.py),
  [test_worker_orphans.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_worker_orphans.py). 298 pass.

## 6. Exact next steps

1. Ask Albert the §0 list in one message. Do nothing below until he says to turn the bot on.
   *Worked when:* he has answered item 1 in words.
2. Confirm state is unchanged: switch false, 74 paused, backup table has 35 rows.
   *Worked when:* three read-only queries match.
3. Restore pauses: set `interviews_paused` back to the value in
   `cmap.zz_pause_backup_20261110` for the 35 backed-up rows, and false for the rest
   (compare the backup table's columns to `cmap.employee_flags` first; write inside a
   transaction). *Worked when:* the paused count equals the count of paused rows in the backup.
4. Set `cmap.interview_setting.enabled = true` during working hours (the bot is quiet
   8 PM–8 AM ET and weekends). *Worked when:* after the next hourly tick, new
   `cmap.interview_send` rows show at most ONE row per employee, every sent question has a
   priority, and each recipient is the suggested person or in the question's department.
   If anything else appears, set the switch false at once.
5. Verify the reply check with real replies (Albert or a willing employee): a real answer →
   question becomes `answered` and a new source appears; "I don't know" → question returns to
   `open` for someone else; an unrelated message → question stays `asked`.
   *Worked when:* all three are seen in the database.
6. Drop `cmap.zz_pause_backup_20261110` and `cmap.zz_flood_backup_20261110` only after
   steps 3–5 pass; then close issue #518 and delete this file.
7. Diagnose the failing `relations` job (§9) under its own issue.

## 7. Constraints and gotchas in force

- The bot stays OFF until Albert says otherwise. Other sessions are active in this repo and
  one has flipped the switch before.
- Production is read-only by default; declare the task class with `ai-task-gates` before any
  database write and prove which database you are connected to first.
- Never push to main; branch and PR, then merge it yourself. Reviews are advice only.
- Deploy = set the Coolify app's `BRAIN_IMAGE_TAG` to the merge commit, trigger a deploy,
  confirm the health URL reports that commit.
- Never ask Albert to approve, type or click; only business questions go to him.
- Model names are never hard-coded in adapters; use the configured stage models.

## 8. Access and environment

- GitHub: `gh` authenticated as u2giants. Sign posts with `$AI_GH_SIGNATURE`.
- Database reads: Supabase MCP for project eqccjfbyrywsqkxxpjvg. Writes: the production
  connection string in 1Password vault `vibe_coding` (item id
  `qcuyabwseaptvuzvtjejffi2ou`, field `password`), used only through the 1Password
  run-with-secret tool, rewritten to the pooler host in §4. Keep each call under ~100 seconds.
- Coolify deploy token: vault `vibe_coding`, item id `u3aqw63jqnkmnziip3gp5hwb5m`, field
  `credential`. Coolify app uuid `uge6pfm4qapktivto4981mtg`.
- Local tests (apps/brain): Postgres on localhost:5433 database `brain_test`, FalkorDB on
  localhost:6380 (docker containers `zh-brain-pg`, `zh-brain-fk` on edge-dev3; elsewhere
  start equivalents), then `uv run pytest -q tests/` and `uv run ruff check brain tests`.

## 9. Open questions and risks

- 2026-11-11: **`relations` background job is failing** — 5 failed rows in `cmap.job`, latest
  9:23 PM EST 2026-11-10, error: the model provider rejects an "unknown parameter reasoning".
  Seen during wrap-up, NOT investigated or fixed (scope freeze). Effect: new relationships
  between people/things may not be extracted. Likely place to look: the relations stage call in
  apps/brain and its stage-model settings.
- Two old failed jobs are historical only: `interview_tick` 2026-11-04 (orphaned by a restart;
  the class of problem #516 fixes) and `communities` 2026-10-30 (embeddings call failed).
- Review findings on #514 are tracked in
  [#515](https://github.com/u2giants/theoracle/issues/515) (advice only; not read this session).
- Risk: the vetting model may over- or under-rate importance; the 67 waiting questions have not
  been read by a person. Risk: `classify_reply` fails open, so a provider outage would save any
  reply as an answer.
- The older handoff linked in §3 says the bot waits on a "routing fix"; that fix is #514, landed.

## Self-audit (all four: yes)

1. Newcomer can continue: §1 defines the app and terms, §3 the exact state, §6 the steps.
2. As well as the author: §4 dead ends and §5 findings carry everything learned.
3. Every detail: goals §2, state §3, failures §4, decisions §0/§9, constraints §7, access §8,
   steps with gates §6.
4. Owner decisions: swept §1–§9; the only business items (when to switch on, the 2 unrouted
   questions, the 25 stale asked questions) are all in §0; the relations failure is technical.
