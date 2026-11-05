---
issue: 255
status: OPEN
owner: mimo/close-nested-coordinator (ah-desktop)
---

# Company Map step 14: coordinator baton — owner-gated tasks remain

Written 2026-11-05, 3:12 AM EST, ah-desktop, MiMo (coordinator). Program parent
https://github.com/u2giants/theoracle/issues/240 ; step 14
https://github.com/u2giants/theoracle/issues/255 . Spec:
https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md .
Executed baton:
https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0140Z-edge-dev3-claude-close-nested-company-map.md
(keep it until #255 closes — it holds the original task texts and the settled
list).

This file is the successor baton for what REMAINS of step 14. Six of the
executed baton's eight §6 tasks are done and independently verified (§3). Two
are gated on Albert (§0). One item is `Blocked —` on a credential scope (§6.4).
A successor is a coordinator only if it starts per-task sessions; a single
worker may also take any one task directly. Do no unrelated work.

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

Put ALL open items below to Albert in ONE message before starting work.

1. **Share Ilona's question page**
   https://claude.ai/artifact/1dw8ZoafmchL3HZ9mW26KX with Ilona as Contributor.
   Only Albert can share it. Blocks task 6 (#367). Recommendation: this week.
2. **Ilona (and Albert) edit and approve the 20 questions** on that page.
   Blocks task 6 (#367) and the only real quality score for step-14
   acceptance. Recommendation: this week. The draft questions are in Appendix A
   of https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-02T2057Z-edge-dev-mimo-model-overhaul-bakeoff-round2.md
   and in the file `eval-questions-draft-20.md` delivered to Albert.
3. **30-minute Map review: mark wrong items.** The rebuild and seeded eval have
   LANDED (2026-11-05, eval_run `c987534d-6c52-4d74-a6a9-4777e133f2a5`, graph
   version 15 — later 21 after the debounce proof). The review can start NOW.
   Also look at the flowchart: it now has 75 arrows against 67 in the
   reference. Blocks closing #255 and task 8. Recommendation: as soon as
   possible; it is the last gate on the program.
4. **Send the rest of the company documents.** The plan expects hundreds; the
   Map has about 31 sources (drift report on #240). Recommendation: as they
   are ready; corpus growth also comes through Teams answers.
5. **Confirm the Oracle 2 no-backup deletion was actually ordered.** The
   session that dropped 93 tables and deleted apps/projects reports Albert
   ordered deletion without a backup; no coordinator saw those words. This is
   a governance question about an irreversible act that already happened —
   answer "yes, I ordered it" or "no" so the record is accurate. Blocks:
   nothing operationally; it settles the record on #398 and its handoff
   https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0258Z-edge-dev-mimo-task7-ghcr-images-leftover.md .
6. **The 11 silent Teams employees — nudge or wait (low urgency).** Eleven
   licensed employees never opened a bot chat. A fix landed 2026-11-05
   12:34 AM EST (PR https://github.com/u2giants/theoracle/pull/440 ) so the
   bot can now open the chat itself. Recommendation: wait for the November 11
   tick-log check (§6.5) and re-decide then; interviews stay OFF until Albert
   turns them on.

Already settled. Do NOT re-ask:
- 2026-11-04 vision seat: `anthropic/claude-sonnet-5.5` (diagram bake-off
  winner). Relations seat: Muse direct (`meta-model-api/muse-spark-1.3-contributor`)
  — live and verified 2026-11-05 12:33 AM EST after task 2.
- 2026-11-04 Albert, verbatim: "i want the brain to use the Muse direct API
  key" — DONE (task 2, PR #438).
- 2026-11-04 relations re-seat to `z-ai/glm-5.3` as the OpenRouter stopgap —
  superseded by the Muse direct seat above.
- All of the predecessor batons' §0 settled lists (tenant emails @popcre.com;
  interviews OFF until Albert enables them; $25/day OpenRouter cap; reviews
  advisory; FalkorDB stays; no permission system beyond login + `is_admin`;
  public-repo history exposure accepted).

## 1. What this application is

The Oracle is POP Creations' evidence-backed company adviser. The Company Map
reads company documents, diagrams and employee transcripts and shows how work
flows. `apps/brain` (Python FastAPI + worker) runs on Coolify as `oracle-brain`
(https://oracle-brain.designflow.app), web https://oracle.designflow.app ,
Postgres schema `cmap` on Supabase project "theoracle", FalkorDB graph
`company`. The repo is PUBLIC — no LAN IPs, no Supabase project refs, no
secrets in any commit, issue or PR.

## 2. What we set out to do this session, and why

Execute the close-nested coordinator baton named in the header. Albert's
authority, verbatim: "Goal: finish the Company Map model work and close step
14." and "get everything that can be moving, moving." The coordinator's job:
start one nested session per open §6 task whose dependencies were met, verify
each report against GitHub and the live brain, re-route any child idle 30
minutes, start dependent tasks only on verified completion, then close out.
This file is that close-out: what landed, what remains, and how to continue.

## 3. Current state — what is true right now

DONE and independently verified (evidence checked against GitHub and the live
brain/DB by the coordinator, not just child claims):

| Task | Outcome | Proof |
|---|---|---|
| 1. Prod rebuild + seeded eval | eval stored with correct seats, Map populated | eval_run `c987534d-6c52-4d74-a6a9-4777e133f2a5` (models.stages.relations=`z-ai/glm-5.3`, stages.vision=`anthropic/claude-sonnet-5.5`); `/map/company` populated at graph_version 15; proof comment on #255 |
| 2. Muse direct API key (#426) | direct Meta provider route live | PR https://github.com/u2giants/theoracle/pull/438 merged `38feedef`, deployed; prod relations job `fcd93444` done on `meta-model-api/muse-spark-1.3-contributor`, 2031 rows in `cmap.relation`; `GET /models` shows it; OpenRouter block investigated |
| 3. Teams intake auto-retry + root cause | root cause found, live retry proof | issue https://github.com/u2giants/theoracle/issues/443 closed with proof (forced failure → retry → read source `1a5a8236`; organic `c0ff02f2`; victim thread `53e27059` recovered). PR #424 had already landed the code |
| 4. Debounce the per-source chain (#415) | burst runs the chain once | PR https://github.com/u2giants/theoracle/pull/444 merged `faa3482f`, deployed; proof on #415 (2 sources 5 s apart → 1 resolve + 1 project + 1 communities; graph v20→21); issue #415 closed |
| 5. Teams follow-through (part b) | every non-chatted account has a named cause | comment on #255 (11 licensed-but-silent + 7 unlicensed); install dry-run 51/51 have the app; PR https://github.com/u2giants/theoracle/pull/436 (handoff) |
| 7. Oracle 2 leftovers (b)(c) | Supabase MCP repaired, stale docs removed | PR https://github.com/u2giants/theoracle/pull/432 merged `85eaf44a`; issue #431 closed; live MCP probe 13 tools, old `settings` table confirmed gone; (a) is `Blocked —` (§6.4) |

Landed on `main` this round (all MERGED, verified via `gh pr view`): PRs 432,
435, 436, 438, 440, 442/441-closed, 444, 445 (plus the auto-fixer's lane).
Closed issues: 415, 426 (proof comment; verify closure when you arrive), 431,
437 (filed by task 1), 443.

Live, verified by the coordinator at 3:00 AM EST 2026-11-05:
`/health` `{"ok":true,"db":true,"graph":true}`; `GET /models` relations =
`meta-model-api/muse-spark-1.3-contributor` (source: page), vision
`anthropic/claude-sonnet-5.5`, embed `voyageai/voyage-4-lite`, flat
`z-ai/glm-5.3-flash`, resolve/reports/recommend/grade `openai/gpt-6-luna`,
answer `anthropic/claude-haiku-5.5`. Latest eval_run `c987534d…` (mean 0.2 on
the 5 seed questions — expected; those questions are written for the fixture
corpus, not the real one). Queue at 2:31 AM EST: all chains quiet except one
`communities` run finishing the debounce proof.

NOT started / NOT done:
- Task 6 (stage-7 rerun on the final 20 questions, #367) — owner-gated (§0.1–2).
- Task 8 (close step 14) — owner-gated (§0.3).
- Container image deletion (§6.4) — `Blocked —`.
- November 11 tick-log check (§6.5) — calendar-gated.
- #437 community-size defect (§6.7) — unowned.
- Task 4 wrap-up follow-ups (§6.6) — unowned.

## 4. Everything we tried that did NOT work

1. **`mcp__ccd_session__start_session` does not exist in MiMo Desktop.** The
   baton names the Claude desktop session tool. Per the `close-nested` skill's
   client rule ("use its equivalent, and say which you used"), nested sessions
   were MiMo `actor` general subagents with their own worktrees, tracked via
   session memory `tasks/<TID>/progress.md`. Any successor on MiMo should do
   the same; on Claude, use the named tool.
2. **The Supabase direct URL field is unusable from these machines.** 1Password
   item `qcuyabwseaptvuzvtjejffi2ou` field `password` (direct URL) resolves to
   a host that is IPv6-only; Windows cannot resolve it at all and edge-dev3
   resolves it but has no IPv6 route ("Network is unreachable"). WORKING PATH:
   same item, field `oracle_session_pooler` — psycopg from edge-dev3 connects
   in ~2 s. (Confirmed independently by task 1's child.)
3. **`ai-shared-db-closeout-check` hangs.** Invoked with
   `--session-id ses_…` it produced no output and had to be killed after both
   120 s and 300 s; the underlying `bin/ai-shared-db-closeout-check` bash+
   python script stalls, likely in its `ai-gh` launcher. Substitute check used:
   `gh search issues --repo popcre/shared-db '<session id>'` returns zero
   matches = zero owned claims. A successor should re-run the real tool once it
   is repaired (it lives in the installed ai-devops checkout).
4. **PowerShell quoting through `ssh host "python3 -c …"` collapses.** Nested
   quotes break before ssh. WORKING PATH: write the script to a local temp
   file, `scp` it to edge-dev3, and pipe the secret via stdin from
   `1password_op_run` (`$env:PGURL | ssh edge-dev3 "PYTHONPATH=/tmp/pylibs python3 /tmp/oracle-q.py"`).
   The secret never appears in argv or transcript that way.
5. **pip on edge-dev3 is PEP 668-locked and `python3 -m venv` has no ensurepip.**
   WORKING PATH: `python3 -m pip install --target /tmp/pylibs 'psycopg[binary]'`
   then `PYTHONPATH=/tmp/pylibs python3 …`. (`uv` IS present at ~/.local/bin/uv.)
6. **`ai-housekeeping` timed out** in several children (2-minute default). Run
   it detached from `C:\repos\oracle` in a fresh session if its inventory is
   needed; it is report-only.
7. Carried from the executed baton §4: nested sessions that end turns on
   "waiting" without a waiter; GLM invalid-JSON flakes (re-queue fixes);
   Vercel sensitive envs are write-only; the `GET /applications/<uuid>/envs`
   Coolify endpoint echoes secrets — never print it; sending a deploy before
   the env PATCH lands redeploys the OLD image (likely cause of past "mystery
   redeploys").

## 5. Root causes and key findings

- **OpenRouter Muse block (task 2):** Meta provider-level 403 `user_blocked`
  "repeated policy violations", triggered 2026-11-04 7:41 PM EST by bake-off
  volume (17,134 req/$11.02 on 11/01; 14,990 req/$16.74 on 11/04). The other
  36 models on the key are unblocked; key balance $19.56 of $25 at the time.
  The management API `GET /api/v1/activity` (not `/api/v1/generation`) is how
  to investigate such blocks.
- **Teams intake data loss (task 3):** `close_thread()` treated
  `httpx.ReadTimeout` from `store.upload()` as permanent failure. Root cause:
  Supabase Storage REST stalls >60 s behind Cloudflare. PR #424 raised the
  client timeout to 180 s and added the worker retry sweep (retry_count,
  next_retry_at, max 5, migration 008). Thread `53e27059` was the original
  victim and is now recovered.
- **Per-source chain churn (task 4):** coalescing on "no queued job" never
  worked because the worker claims within 2 s. The fix is a future `run_after`
  hold pushed per source (5 min quiet) capped at 15 min. Implementation:
  `apps/brain/brain/sql/009_chain_debounce.sql`, `worker.py`,
  `extract/relations.py`, `api/map.py`, `tests/test_chain_debounce.py` (PR
  #444).
- **"7 Teams-enabled employees have no bot chat" was an arithmetic artifact
  (task 5):** 51−33−11=7 assumed all 33 conversations belonged to the 40
  licensed accounts; 4 unlicensed accounts also hold install-time greetings.
  True split of the 18 without a chat: 11 licensed-but-silent (install
  `conversationUpdate` never stored a reference and they never messaged the
  bot) + 7 never-reachable (no Teams license: deactivated or shared mailbox).
  Named lists are in the #255 comment and in
  https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0307Z-edge-dev-mimo-teams-followup-255.md §5.
- **Brain API auth** needs BOTH `x-brain-token` (1Password item
  `4lm6bpl7bc25lqne4meumwcd2a` field `BRAIN_SHARED_TOKEN`) and `x-user-id` (an
  admin Supabase auth user id mapped to an active `is_admin` employee). Two ids
  verified working: `751efc6f-b030-43cf-9f22-8e82ac389771` (predecessor baton)
  and `e0968007-7276-46fb-8abd-25baa108f112` (task 1 child).
- **Eval manifests:** the authoritative seat list is `models.stages.*` inside
  `cmap.eval_run.models` (e.g. `stages.relations`), NOT the legacy top-level
  `models.vision`/`models.frontier` keys, which still carry pre-seating values.
  Verify done-when claims against `stages.*`.
- **Communities runtime:** a full L0+L1 run is ~90 minutes for ~630
  communities with report generation. One communities job also failed on GLM
  invalid JSON during the rebuild (`communities failed` = 1 in `cmap.job`);
  re-queue if a communities gap appears.

## 6. Exact next steps

1. **Put §0 to Albert in ONE message** (all six items), then wait for his
   answers before touching tasks 6 and 8. You will know it worked when Albert
   answers in chat and the Map review / question approvals are recorded on
   #255.
2. **Task 6 — stage-7 rerun on the final 20 questions (#367)** — starts only
   after §0.1–2 (Ilona shares the question page and the 20 questions are
   approved). Task text, verbatim from the executed baton §6:
   "> https://github.com/u2giants/theoracle/issues/367 . On artifact
   `05282281-8fc8-4d2f-a61e-4760a9bdb45e` (the question page), run `db_get`
   review/status, then `db_list` the questions collection, enter the questions
   on the eval page, and rerun answers (local and global mode) on a cloned DB.
   The page buttons are untested in a signed-in browser. Done when: #367 is
   closed with a rerun report in the bake-off folder."
   You'll know it worked when #367 is closed and the bake-off folder holds the
   rerun report. Use a cloned DB; never point the eval at prod for scoring.
3. **Task 8 — close step 14** — last, after Albert's Map review (§0.3).
   Verbatim: "Record Albert's verbatim Map verdict in plan STATUS row 14, close
   #255, and post a final drift note on #240 (the full drift report is already
   there). Done when: #255 closed." Include in that drift note the task-4
   follow-up (§6.6). You'll know it worked when #255 is closed and the STATUS
   row 14 holds his verbatim words.
4. **Container image deletion — `Blocked —` (unowned until a token exists).**
   Delete `theoracle-native` and `theoracle-native-browser` from GitHub's
   container registry. Needs a token with `delete:packages`; the gh token on
   this machine is `gist, read:org, repo, workflow` and the vault packages item
   has only `read:packages`. GitHub does not allow PAT creation via API — route
   to a session with the u2giants account's authenticated browser (never ask
   Albert to type it). Details and dead ends:
   https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0258Z-edge-dev-mimo-task7-ghcr-images-leftover.md
   . You'll know it worked when both package names 404 for a
   read:packages-capable token and the live-proof box on issue #431 is ticked.
5. **November 11, 2026 — interview tick-log check (task 5a).** Only AFTER
   2026-11-11 EST. Verify Phase-3 done-when: ≥3 scheduled questions sent to
   employees within one week AND ≥1 answer became a source. Query
   `cmap.open_question` / `cmap.interview_send` / `cmap.source` on prod (pooler
   path, §8) or `GET /interview/overview` with the service token + admin
   x-user-id. Post counts and pass/fail on #255 signed
   `Posted by MiMo chat <session id> on <machine>`. Exact recipe:
   https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0307Z-edge-dev-mimo-teams-followup-255.md §6.
   You'll know it worked when the #255 comment states both thresholds.
6. **Task 4 wrap-up follow-ups (small, unowned).** (a) Fold the plan-drift
   notes in §5/§6.1 of
   https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0750Z-edge-dev-mimo-task4-debounce-chain-notes.md
   (worker claim SQL + per-source chain prose) into the next drift report on
   #240 — best done inside step 3 above. (b) In the same commit, retire that
   task4 handoff file (its issue #415 is closed, its work verified; apply the
   successor rule). You'll know it worked when the #240 drift report mentions
   the debounced chain and the `run_after` claim filter, and `HANDOFF.d/` no
   longer contains the task4-debounce file.
7. **#437 community-size defect (unowned).**
   https://github.com/u2giants/theoracle/issues/437 — 607 communities with
   ≤2 entities at L0/L1 despite the #410 fix (PRs #412/#414). It predates the
   2026-11-05 rebuild and survived graph v15/v21. Any session with brain
   capacity can take it; it does not block step 14. You'll know it worked when
   #437 shows a fix whose L0/L1 groups are all ≥3 or ≤150 entities.
8. **Hygiene (low priority).** Re-run `ai-shared-db-closeout-check` once its
   hang is repaired (§4.3); run `ai-housekeeping` detached for an inventory
   (§4.6); four other sessions' handoffs are reported UNATTRIBUTED — do not
   edit them, report only.

## 7. Constraints and gotchas in force

- Never push to protected `main`: branch + PR + `gh pr merge --squash --admin`.
  Docs-only PRs need `bin/ai-doc-safety` on the exact head before merge.
- Public repo hygiene: no secrets, no LAN IPs, no Supabase project refs in
  code, commits, issues or PRs. Employee names/emails follow the established
  @popcre.com style already used in this repo's issues.
- Times in EST (America/New_York) in every human-facing message.
- Task gates: `ai-task-gates start --class production --base <fresh main>`
  before risky steps; `check --before database --acknowledge "<Albert's exact
  words>"` for database actions. The stale-base trap (repeatedly declaring on
  an old base) is in the predecessor baton §4.1.
- Never redeploy the brain while `cmap.job` has rows in
  `('running','queued')` — and note the debounce fix (task 4) exists precisely
  because bursts kept closing that window. Coolify deploy:
  `POST /api/v1/deploy?uuid=uge6pfm4qapktivto4981mtg` (or
  `POST /applications/<uuid>/start`); env PATCH is the single-object form
  `{key,value,is_preview,is_multiline,is_literal}` (list form → 422). Deploy
  AFTER the env PATCH, never before.
- Only ONE child deploys at a time. Interview questions stay OFF (standing
  direction) until Albert enables them.
- Sign every GitHub post: `Posted by MiMo chat <session id> on <machine>`.
- OpenRouter: check `limit_remaining` before spend; stop under $5 of the
  $25/day cap. It was $19.56 at 12:55 AM EST 2026-11-05.
- HANDOFF.d discipline: never edit another session's file; retire only under
  the successor rule (issue closed + landed verified + obligations carried).
  Do not rewrite the root `HANDOFF.md`.
- Each nested task session: own worktree from fresh main, own test DB clone
  and FalkorDB container on edge-dev3, background PR waiter
  (`bin/ai-pr-wait <pr> --repo u2giants/theoracle`), never end a turn on
  "waiting", never spawn its own children without coordinator approval.

## 8. Access and environment

- Machines: ah-desktop (Windows; this coordinator) and edge-dev3 (Linux test
  services host, `ssh edge-dev3`). Canonical checkout on ah-desktop is
  `C:\repos\oracle` (landing-only — never commit on its main); worktrees live
  under `D:\repos\oracle-worktrees\<name>`. This is machine-local detail —
  resolve paths via the machine atlas on other machines.
- `gh` authenticated as `u2giants` (scopes `gist, read:org, repo, workflow` —
  NO `delete:packages`, see §6.4). Commit identity:
  `Albert Hazan <u2giants@users.noreply.github.com>` (`git var GIT_COMMITTER_IDENT`).
- 1Password MCP (`op_run`, vault `vibe_coding`, item-ID form of op:// refs —
  names with spaces fail parsing): shared token `4lm6bpl7bc25lqne4meumwcd2a`
  field `BRAIN_SHARED_TOKEN`; Supabase `qcuyabwseaptvuzvtjejffi2ou` field
  `oracle_session_pooler` (WORKING) / field `password` (direct URL — IPv6-only,
  unusable, §4.2); Muse/Meta key `czggiabkpo7dt7ojep4btdvq5i`; Coolify
  `u3aqw63jqnkmnziip3gp5hwb5m` field `credential`. Never print values; never
  pass them in argv.
- Prod DB: connect with psycopg from edge-dev3 using the pooler URL piped on
  stdin (pattern in §4.4). Schema `cmap`. psql is not installed on edge-dev3.
- Brain API: https://oracle-brain.designflow.app — `/health` needs no auth;
  everything else needs `x-brain-token` + `x-user-id` (§5). Coolify API
  `http://hetz:8000/api/v1` from ah-desktop and edge-dev3 (app uuid
  `uge6pfm4qapktivto4981mtg`).
- edge-dev3 test infra: create per-session Postgres/FalkorDB containers (e.g.
  `task4-pg`/`task4-falkor` pattern) and remove them after; never reuse
  `brain2-test-pg`, `brain2-test-falkordb`.
- Python 3.13 + uv + node on Windows; `ai-task-gates` on PATH;
  `ai-shared-db-closeout-check` present but hangs (§4.3).

## 9. Open questions and risks

- **(2026-11-05) The #410 community-size fix looks incomplete** — 607
  communities with ≤2 entities survived the fix AND two rebuilds (#437). If
  Albert's Map review flags community quality, this is the likely reason.
- **(2026-11-05) The model-pool page was deleted by #402**, so "remove Muse
  from the page's OpenRouter candidates" (executed baton task 2) is moot. If
  the page is ever rebuilt, redo that removal while the OpenRouter block lasts.
- **(2026-11-05) Two proof transcripts remain in the prod corpus** ("Debounce
  proof 2026-11-05 (a)/(b)"), clearly labeled, adding no business claims.
  Deleting them re-triggers the chain by design. Remove only if the owner wants
  them gone.
- **(2026-11-05) One `communities` job failed** on GLM invalid JSON during the
  rebuild and one `interview_tick` failed; both are single failures with the
  rest healthy. Re-queue if a content gap appears.
- **(2026-11-05) The seed-eval mean of 0.2 is NOT a quality number** — the
  five seed questions expect fixture facts. The real instrument is the 20
  owner questions (task 6). Do not compare 0.2 across models or rounds.
- **(2026-11-05) Coolify env listing echoes secrets** (§4.7): never print
  `GET /applications/<uuid>/envs` output. One child observed a local-only echo
  of an existing value; per standing rule it stays unrotated (exposed only on
  that machine) and was never written to a file.

---

## Part (b) — nested sessions (this coordinator dispatched six)

All were MiMo `actor` general subagents (the equivalent of
`mcp__ccd_session__start_session` in this client), each in its own worktree
from fresh main, each briefed with the executed baton's task text verbatim.

- **Task 1 prod rebuild + eval** — finished the seeded rebuild (communities
  v14/15), re-queued the failed classify_extract, ran `POST /eval/run`, posted
  the done-when on #255. No code change, no PR. Filed #437 (community sizes)
  on request. Worktree removed. Coordinator verified the eval manifest against
  the live `/eval/runs` API and the DB before accepting.
- **Task 2 Muse direct key** — PR https://github.com/u2giants/theoracle/pull/438
  (`apps/brain/brain/llm.py` provider routing, `config.py` key setting, 40
  tests), deployed, re-seated relations to Muse, proved a prod relations job on
  the direct key, investigated the OpenRouter block via the management API.
  Worktree and branch removed. Coordinator verified job `fcd93444` done,
  `cmap.relation` count 2031, and `GET /models` before accepting.
- **Task 3 Teams intake** — opened and closed
  https://github.com/u2giants/theoracle/issues/443 with the root cause
  (Supabase Storage stalls >60 s behind Cloudflare) and live proof (forced
  failure → retry → read source, plus one organic recovery). Found PR #424 had
  already landed the code; made no duplicate change. Worktree removed.
  Coordinator verified the thread/source rows in the DB before accepting.
- **Task 4 debounce** — PR https://github.com/u2giants/theoracle/pull/444
  (migration 009 + worker/API/extract changes + 206 tests) and PR
  https://github.com/u2giants/theoracle/pull/445 (handoff notes), live proof on
  #415 (two sources 5 s apart → one chain run), issue #415 closed. Worktree and
  branches removed. Coordinator saw the same single-chain pattern in the job
  queue before the proof landed and verified the proof after.
- **Task 5 Teams follow-through** — read-only. Re-ran the install dry-run
  (against the surviving #384 deployment — the prod route was cut by #402),
  named all 18 accounts without a bot chat with causes, posted on #255, wrote
  https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-05T0307Z-edge-dev-mimo-teams-followup-255.md
  (PR #436). Part (a) recorded as calendar-gated to after 2026-11-11.
- **Task 7 Oracle 2 leftovers** — PR https://github.com/u2giants/theoracle/pull/432
  (repair `supabase-oracle` `.mcp.json` entry + remove stale seed/settings doc
  mentions) and PR https://github.com/u2giants/theoracle/pull/435 (handoff),
  issue #431 closed with (a) left as a `- [ ]` live-proof box and named.
  Part (a) `Blocked —` (§6.4). Worktree and branches removed.

None of the six spawned children of their own (the baton's scope-creep warning
was enforced). No session holds a worktree, branch or claim at close-out.

---

## Self-audit (handoff-writer gate)

1. *Could a brand-new developer pick up and not skip a beat?* Yes — §1 orients
   the app, §3 pins every completed task with its PR/issue/eval evidence, §6
   gives ordered next steps with per-step verification gates, §8 gives every
   access path (vault item ids only, never values).
2. *Could they continue as effectively as me right now?* Yes — §4 carries the
   dead ends that cost time tonight (the session tool substitution, the IPv6
   direct-URL trap and the working pooler field, the hanging closeout check,
   the PowerShell/ssh quoting trap), §5 carries each root cause with its
   evidence (OpenRouter abuse flag, Storage stalls, run_after debounce, the
   "7" arithmetic artifact, `models.stages.*` vs legacy manifest keys).
3. *Every relevant detail included?* Background (§1–2), outcomes (§3), failures
   (§4), findings (§5), actions (§6), constraints (§7), access (§8), risks
   (§9), per-subagent records (part b), owner decisions (§0). Commit SHAs and
   GitHub URLs throughout; no machine-local paths in the task text (machine
   paths appear only in §8 as labeled machine-local detail).
4. *Does §0 hold every owner decision and no technical approval?* Yes — swept
   §1–§9 and part (b): Ilona page share, 20-question approval, Map review,
   corpus documents, the no-backup deletion confirmation, the 11-silent
   nudge-or-wait. Every other item in this file is an AI-executable task, a
   dated calendar check, or a `Blocked —` credential scope — none asks Albert
   to approve technical work. The settled list prevents re-asking.
