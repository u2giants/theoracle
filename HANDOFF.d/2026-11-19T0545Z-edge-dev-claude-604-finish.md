# Handoff — finish #604 (interview bot): live proof, staff sittings, restore settings

Written 2026-11-19 4:12 AM EST by the #604 delivery session (Claude, edge-dev). Issue:
https://github.com/u2giants/theoracle/issues/604. Plans (read STATUS first, do not re-plan):
[plan_interview_agent.md](../plan_interview_agent.md) (row 6 open) and
[plan_interview_conversation_rebuild.md](../plan_interview_conversation_rebuild.md) (row 11 open).
Successor rule: delete this file once both plans' STATUS rows are all ✅ and #604 is closed with evidence.
Replaces `2026-11-19T0200Z-edge-dev-claude-interview-agent.md` (deleted in the same commit).

## 1. Goal
Albert (owner, POP Creations, not a programmer) interviews staff through the Oracle's Teams bot so the
Company Map learns how the business works. The bot is now a serial conversation that understands replies
and can hand a question to a colleague ("ask Jen"). Done = the referral proven live, one sitting each for
Ilona Kereki, Jennifer Chaffier, Carlos Corral, Jessica Cortazar, test-mode settings restored, signed
evidence on #604, issue closed.

## 2. Current state (verified 2026-11-19 ~4:10 AM EST)
- Production brain runs merge `b6d7e03855384bab6a5003100e28029bd7a40a9d` (PR #634, Coolify app
  `uge6pfm4qapktivto4981mtg`, deployment `poafeox7bkzwamkj08t8ewxb` finished). Rollback tag:
  `cd269a6781aabf2774fa0377ebc6d7a44a0f1cee`.
- Albert's live conversation `dcb04ba8-f347-4e81-97c6-e0c184527f82` (employee
  `5925c3b6-2c37-4f3a-956c-7fa5c9ded951`) is `awaiting_answer` on a new question sent 2026-11-18
  7:43 PM EST. Albert was told he may answer by pointing to a colleague.
- TEST MODE still in force (must be undone, §4):
  1. Every employee except Albert has `cmap.employee_flags.interviews_paused = true`. Before the test only
     these three were paused: `2f0e8dc2-07bd-4955-829a-039200021935`, `371c0e6e-fc6c-4a86-8fec-f4606d1269a2`,
     `89236607-3a97-42ba-967d-0339701fdc46`.
  2. Coolify env `BRAIN_INTERVIEW_WEEKLY_CAP` was raised for testing; normal value is `2`.
  3. Three `cmap.open_question` rows had `target_employee_id` set to Albert to aim them at him (the
     ones he has been asked). Clear `target_employee_id` on any still-`open` question aimed at Albert
     that he has not been asked, unless a referral set it (`why` contains `[referred by`).
- Directory data issue: duplicate rows "Jen Chaffier" (`b39804d0-4b99-451c-8c65-0808a8efa42e`, not in
  Teams) and "Jennifer Chaffier" (`f8d54192-9da5-40db-a141-768b584bcacc`, Creative Director, in Teams).
  Report on #604; merging is out of scope.

## 3. Key findings this session
- Haiku-class chat model spends ~400 reasoning tokens; `CONVERSE_MAX_TOKENS` is now 1500 (500 truncated JSON).
- Follow-up turns carry no `question_id`; `converse.discussed_question` now walks back to the last question.
- The name guard flagged words from the Oracle's own earlier messages ("SOP"); they are now allowed.
- `find_person` matches name prefixes (Jen→Jennifer) and returns Teams-reachable people first.

## 4. Remaining steps, in order
1. **Live referral proof.** Read Albert's conversation turns. If he named a colleague, confirm in the DB:
   the question's `target_employee_id` = that colleague, `skipped_by` contains Albert, `why` has
   `[referred by Albert …]`, and an `out` turn told him who will be asked. The colleague's opening only
   goes out when they are unpaused (step 3). If he answered normally, that is not a failure — record it and
   prove the referral during a staff sitting instead. Update plan_interview_agent row 6.
2. **Staff sittings**, one at a time: unpause one person (`interviews_paused = false`), queue an
   `interview_tick` job (`INSERT INTO cmap.job (kind, payload, lane) VALUES ('interview_tick','{}','main')`),
   watch their conversation to a natural close, note problems. Order: Ilona Kereki, Jennifer Chaffier
   (the Teams record), Carlos Corral, Jessica Cortazar. Do not message staff yourself.
3. **Restore**: pause flags back to exactly the three ids in §2 (everyone else `false`), set
   `BRAIN_INTERVIEW_WEEKLY_CAP=2` via Coolify API (PATCH `/api/v1/applications/<uuid>/envs`, then
   `POST /api/v1/deploy?uuid=<uuid>`), verify the deployment finishes, clear aimed questions (§2.3).
4. Update both plans' STATUS with evidence, post signed evidence on #604 (sign with `$AI_GH_SIGNATURE`),
   close #604, delete this handoff, PR + merge yourself.
At the end of each step, re-read the remaining steps and both plans to plan-end and note any drift here.

## 5. Access (locations only)
1Password vault `vibe_coding` via `op_run` env refs: DB `op://vibe_coding/qcuyabwseaptvuzvtjejffi2ou/oracle_session_pooler`;
Coolify token `op://vibe_coding/u3aqw63jqnkmnziip3gp5hwb5m/credential` (API `https://coolify.designflow.app/api/v1`,
send a `User-Agent` header); OpenRouter `op://vibe_coding/62ieeyycs4ierflalbbbt5pq5i/OPENROUTER_API_KEY`.
Tests: `DATABASE_URL=postgresql://oracle:oracle@localhost:5433/brain_test uv run pytest tests/test_interview*.py`
in `apps/brain` (110 passed at `b6d7e038`).

## 6. Rules in force
Production is read-only except the restore/test-mode settings above and deploys; no human approval
gates; never push main (branch, PR, merge yourself); stage only owned files; no hard-coded model names;
new user strings in en + zh-CN; preserve line endings; never use Entire; replies to Albert ≤120 words,
plain words, plus a "Still open" block; times in EST.

## 7. Rejected / do not redo
Keyword rules for "ask X" (Albert rejected static rules); provider-native tool calling; letting the
model write questions to colleagues (they only get the stored question). See plan_interview_agent §7.

## Self-audit
1. A fresh session can finish without asking: state §2, steps §4, access §5. Yes.
2. Background carried: findings §3, rejected §7, test-mode residue §2. Yes.
3. Goal clear enough to steer: §1. Yes.

## Drift log
- 2026-11-18 11:45 PM EST (Claude, edge-dev, session "finish #604"):
  - Step 1: no referral happened. Albert replied (seq 10, 7:43 PM EST) "i'm not sure, as Adam Dweck or
    Jack Safdieh" (likely a typo for "ask") to a follow-up. The bot logged it as an answer and moved on to the
    next question; no question was re-aimed. Treat it as a bot miss: a "not sure + name" reply to a follow-up
    should hand the question over. Prove the referral in a staff sitting, and look at this case.
  - Step 2 started: Ilona Kereki (`0afd45f8-5ee1-4d41-a43c-36bcd59f4102`) unpaused at 11:23 PM EST; tick job
    `05afee28-51cc-4153-9c6a-b632f2c4a3ec` finished at 11:35 PM EST with no message, because the bot does not
    message anyone 8 PM–8 AM or on weekends. The hourly tick will open her sitting from 8 AM EST Thursday
    2026-11-19. Next session: check her turns after 8 AM, then go on with the order in §4.
  - Write access: the Supabase MCP is read-only; use `op_run` with the DB ref in §5 and `psql` for writes.
- 2026-11-19 1:00 AM EST: the missed referral is fixed (PR #640, merge `293f33e2776ba7bc6bbac26d22457b9aa2009733`,
  Coolify deployment `qwgxudkeesuufyjzerzz8hrh` finished, worker processed a job at 12:58 AM EST). Causes: the
  question was already `answered`, so the referral update matched nothing; with two names the model sometimes
  moved on. Rollback tag `b6d7e03855384bab6a5003100e28029bd7a40a9d`. Live proof of a referral is still owed (step 1).
- 2026-11-19 11:45 AM EST (cutover to a fresh session): Ilona Kereki's sitting opened at 8:02 AM EST
  (question sent, no reply yet). Albert's chat unchanged since 7:43 PM EST Nov 18. Production runs `293f33e2`.
  Still to do, unchanged order: §4 steps 1–4 (live referral proof, sittings Ilona → Jennifer → Carlos →
  Jessica one at a time, restore test-mode settings incl. `BRAIN_INTERVIEW_WEEKLY_CAP=2` (now 3), plans +
  #604 evidence + close). Bot is silent 8 PM–8 AM and weekends; do not wait on it then.
