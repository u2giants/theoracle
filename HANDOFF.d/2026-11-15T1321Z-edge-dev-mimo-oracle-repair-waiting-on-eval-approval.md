---
issue: 520
status: OPEN
owner: mimo/ses_ffe5e2fbaeeadffecgSD4KM8fh
---

# Handoff — Oracle repair/consultant plan: owner questions delivered, gate + C4 + C5 still pending (session close 2026-11-15)

For the program issue [u2giants/theoracle#520](https://github.com/u2giants/theoracle/issues/520).
The live ledger is the STATUS table at the top of
[plan_oracle_repair_and_consultant_upgrade.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_repair_and_consultant_upgrade.md) —
read it first; do not re-derive or re-plan. Full program context and
environment mechanics live in the sibling open handoff
[2026-11-12T1414Z-edge-dev-mimo-oracle-repair-continuation.md](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-12T1414Z-edge-dev-mimo-oracle-repair-continuation.md);
this file records what changed since and exactly where to resume.

Session that wrote this file: MiMo on `edge-dev`, 2026-11-15, roughly
8:00–8:30 AM EST. It did no code work: it read the ledger, verified live
state, delivered the five owner business questions to Albert in one chat
message, and closed on wrap-up before he answered. Everything below is a
state verification from this session, a pointer to the standing plan, or the
exact resume point.

---

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

**Put this whole list to Albert in ONE message before starting work.** (It
was delivered once, 2026-11-15 ~8:15 AM EST, and he invoked wrap-up without
answering — check whether he answered since, then deliver it again.) Each
item needs a business judgement only; every technical step is done by the AI
itself. Recommendations are one word so he can answer fast.

**Blocking:**

1. **Approve the draft evaluation questions on the site.** The 30 drafts live
   on the Oracle's eval page
   ([https://oracle.designflow.app/map/eval](https://oracle.designflow.app/map/eval))
   with per-question recommendations; admin can approve, edit or retire each.
   *Recommendation: approve as written (edit anything that reads wrong).*
   *Blocks:* the live quality gate turning green (it is red by design — issue
   [#546](https://github.com/u2giants/theoracle/issues/546), still OPEN
   2026-11-15 8:20 AM EST; the nightly gate failed `no eval questions` on runs
   [43476059273](https://github.com/u2giants/theoracle/actions/runs/43476059273)
   (2026-11-13 12:54 PM EST) and
   [43616599901](https://github.com/u2giants/theoracle/actions/runs/43616599901)
   (2026-11-14 11:37 AM EST)); Phase B's business acceptance; and every
   score-based live check (the C4 before/after eval, the B3 accepted baseline,
   Phase C acceptance).

**Recoverable if guessed wrong:**

2. **Which operational numbers come first** (plan step J1). *Recommendation:
   order-to-ship lead times and late shipments.* *Blocks:* only J1 onward.
3. **"Possibly out of date" horizon** (step D4). *Recommendation: 18 months
   for who-does-what, 36 months for rules.* *Blocks:* only D4.
4. **Who receives the Monday briefing** (step I4). *Recommendation: Albert
   only.* *Blocks:* only I4's send list.

**Not part of this workstream, nobody on it:**

5. **Who is the licensing team** (carried from issue
   [#474](https://github.com/u2giants/theoracle/issues/474)). *Recommendation:
   derive from the directory and documents; it only speeds the first
   interviews.* *Blocks:* nothing (F3 routes without it).

**Also coming, not yet due:** Owner look #2 on the site after step C5 lands
(plan business-acceptance point). He will be told when it is ready.

**Already settled — do NOT re-ask** (with dates): the document corpus is
complete (2026-11-08); the interview bot stays OFF until issue
[#518](https://github.com/u2giants/theoracle/issues/518) (plan rule); the
weekly interview cap stays (2026-11-10); questions for the owner live on the
Oracle site, never in .md files (2026-11-05); no per-fact approval queues, no
permissions beyond login+admin (2026-10-27); domains are by part/function of
the company (2026-11-11); the 13 business functions were seeded and the owner
can rename/merge them any time on
[https://oracle.designflow.app/map/functions](https://oracle.designflow.app/map/functions);
stored interview questions are English-only (owner ruling 2026-11-13, landed
in [#581](https://github.com/u2giants/theoracle/pull/581)).

## 1. What this application is

The Oracle is POP Creations / Spruce Line's company adviser: it reads every
company document and meeting transcript into a knowledge map, answers employee
questions from that map with source citations, and interviews employees over
Teams to fill gaps. Owner goal: an all-knowing business consultant that says
what is broken, why, and what to change.

- Repo: [u2giants/theoracle](https://github.com/u2giants/theoracle) (PUBLIC —
  no secrets, no employee-private content, no LAN addresses in it).
- Web: Next.js on Vercel, [https://oracle.designflow.app](https://oracle.designflow.app)
  (Company Map pages under
  [apps/web/app/map/](https://github.com/u2giants/theoracle/tree/main/apps/web/app/map)).
- Brain: Python 3.12 FastAPI + one background worker on Coolify,
  [https://oracle-brain.designflow.app](https://oracle-brain.designflow.app)
  (image `ghcr.io/u2giants/theoracle-brain`).
- Data: the Oracle's own Supabase Postgres project (schema `cmap`; NOT the
  shared company database — shared-db rules do not apply to `cmap`) plus a
  FalkorDB graph rebuilt from Postgres.
- Pipeline jobs (`cmap.job`,
  [apps/brain/brain/worker.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/worker.py)):
  read_source → classify_extract (flat) → relations → resolve → project →
  process_pass → contradictions → function_assign → communities → recommend.
  Answers:
  [apps/brain/brain/answer/answer.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/answer/answer.py).
  Eval self-test:
  [apps/brain/brain/eval/run.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/eval/run.py).

## 2. What we set out to do this session, and why

Albert's instruction (2026-11-15): continue the Oracle repair program —
finish
[plan_oracle_repair_and_consultant_upgrade.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_repair_and_consultant_upgrade.md)
using its STATUS table as the live ledger. Exact next actions he gave, in
order: (1) put the predecessor handoff's §0 business questions to him in one
message (the unblocking one: approve the 30 draft eval questions on
[https://oracle.designflow.app/map/eval](https://oracle.designflow.app/map/eval));
(2) once approved, dispatch the "Brain quality gate" workflow, confirm gate
PASS, confirm the run becomes the accepted baseline, close issue
[#546](https://github.com/u2giants/theoracle/issues/546) with the run link,
and record the run id in the B3 STATUS row; (3) record C4's live check (eval
mean + context tokens before/after) in `docs/verification/repair/C4.md`
(intended URL once created:
https://github.com/u2giants/theoracle/blob/main/docs/verification/repair/C4.md);
(4) then start step C5 (Map page organised by function — the Owner-look #2
point), working as the predecessor session did.

This session completed step (1) only: the five questions went to Albert in one
chat message at ~8:15 AM EST 2026-11-15. He invoked wrap-up without answering,
so steps (2)–(4) are untouched and the questions must be re-put first.

## 3. Current state — what is true right now

- **17 plan steps are merged and were live** as of the predecessor handoff
  (2026-11-12 9:20 AM EST, commit
  [faf381c4](https://github.com/u2giants/theoracle/commit/faf381c4354ed060826556fb2b98910b834941ab)):
  B1–B4, C1–C4, D1–D3, E1/E2/E4, F4, G1–G2, H1. Their gate tests, PRs and live
  proofs are in the STATUS rows and under
  [docs/verification/repair/](https://github.com/u2giants/theoracle/tree/main/docs/verification/repair).
- **Since then other sessions landed** (Chinese-integration workstream, not
  repair): [db042840](https://github.com/u2giants/theoracle/commit/db042840)
  (#578), [2a48b9f6](https://github.com/u2giants/theoracle/commit/2a48b9f6)
  (#580), [1fec1ec4](https://github.com/u2giants/theoracle/commit/1fec1ec4)
  (#581, stored interview questions English-only per owner 2026-11-13),
  [3d9d1004](https://github.com/u2giants/theoracle/commit/3d9d1004) (#583,
  docs). Branch repair work from fresh `origin/main`, not from a 1414Z-era sha.
- **Live now (verified this session, 2026-11-15 8:22 AM EST):**
  `https://oracle.designflow.app/version.json` →
  `git_sha=1fec1ec445c008b2f44e57d9e08d135e57d85d08`;
  `https://oracle-brain.designflow.app/health` →
  `{"ok":true,"db":true,"graph":true}`.
- **The five owner decisions (§0) are unanswered.** Issue
  [#546](https://github.com/u2giants/theoracle/issues/546) is OPEN (latest
  activity: github-actions comments 2026-11-13 and 2026-11-14, both `gate
  FAIL: eval job failed: no eval questions`). The nightly `Brain quality gate`
  keeps failing on that line; nothing else is wrong with it.
- **Plan rows B3 / C4 are ✅ done but missing their post-approval evidence:**
  B3's row needs its accepted-baseline run id (it still names the two
  pre-approval runs
  [43163303981](https://github.com/u2giants/theoracle/actions/runs/43163303981)
  and
  [43165847107](https://github.com/u2giants/theoracle/actions/runs/43165847107));
  C4's row needs `docs/verification/repair/C4.md` (does not exist yet) with
  eval mean + `context_tokens` before/after. **C5 is ⬜ open.**
- **This session shipped nothing**: no code changes, no PRs, no deploys. The
  only repo write is this handoff file.
- Worktrees named `zh-docs`, `zh-docs2`, `zh-routing`, `zh-routing2` (visible
  in `git worktree list`) belong to other sessions — leave them alone. This
  session created no worktree.

## 4. Everything we tried that did NOT work

- **The interactive question tool for the §0 questions** (this session) —
  Albert aborted it mid-call. *Fix that works:* put the questions as a plain
  chat message (that is what landed at ~8:15 AM EST). If a question tool call
  is aborted, fall back to text; do not retry the identical call.
- **`ai-shared-db-closeout-check`** (this session) — runs but queues for
  minutes per API call ("waiting for admission"; one call took 271.8s). Two
  foreground runs hit the tool timeout; detaching via `Start-Process` crashed
  the harness with `ChildProcess.kill` (same failure mode as `ai-pr-wait` in
  the 1414Z handoff §4). *Fix:* run it in one foreground call with a very long
  timeout (20+ minutes), or accept a partially-progressing log and report
  honestly. Its purpose here is only a zero-claims receipt — this session holds
  no shared-db claims by construction (no shared-db work performed).
- **PowerShell time syntax** (this session): `TZ=America/New_York date` and
  `date -u` are bash, not pwsh. *Fix:*
  `[System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow,'Eastern Standard Time')`
  and `(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHHmm')+'Z'`.
- **`gh issue view N --comments -q ...`** (this session) — rejected without
  `--json comments`; the jq inside that call also rejects `[0..240]` — use
  `[0:240]`.
- Everything in the predecessor handoff's §4 still stands (no local Docker;
  test stores on `edge-dev3`; the Supabase direct host resolves IPv6-only from
  this machine — use the `oracle_session_pooler` field; `op read` needs item
  IDs for titles containing parentheses; `ai-pr-wait` crashes the harness —
  use `gh pr checks <pr> --watch --fail-fast` / `gh run watch <id>
  --exit-status`; landed SQL migrations stay pristine — widenings go in new
  files; one shared snake_case contradiction-kind vocabulary; re-run the FULL
  suite after resolving merge conflicts; order-dependent tests must seed their
  own settings and `get_settings.cache_clear()`; `tests/map_seed.py` contracts
  break the browser suite when community identity changes; Playwright map runs
  need a throwaway `BRAIN_E2E_DATABASE_URL`; fresh worktrees need root `pnpm
  install` and `uv run python -m brain.migrate` before the first pytest).
  **Read it before doing C5.**

## 5. Root causes and key findings

- The gate is red **only** because the owner has not approved the B1 draft
  questions (re-verified 2026-11-15 via the two latest failing runs named in
  §0 — both die at "no eval questions"). Everything else about the gate
  machinery works.
- With **lean required checks**, a red advisory check does not block a merge —
  the C4-era `map_seed.py` breakage landed exactly that way (predecessor
  handoff §4). Watch EVERY CI check before merging anyway.
- Program root causes (stale summaries, silent content loss, too little
  cross-source joining) and per-step technical findings live in the STATUS
  rows and the 1414Z handoff §5 — do not re-derive.
- The repair plan and the Chinese-integration plan are separate ledgers, and
  other sessions edit this repo concurrently. Expect STATUS-row merge
  conflicts in `plan_oracle_repair_and_consultant_upgrade.md` if two sessions
  land rows at once — merge `origin/main`, keep both rows, run the full suite.

## 6. Exact next steps

1. **Put §0's five business questions to Albert in ONE message** (delivered
   2026-11-15 ~8:15 AM EST, unanswered at wrap-up — check first whether he has
   answered since: `select count(*) from cmap.eval_question where approved_at
   is not null`, or the eval page shows "Approved"). *You'll know it worked
   when* that count is > 0.
2. **Run the live eval and arm the gate.** Dispatch `Brain quality gate`
   (`gh workflow run "Brain quality gate"`), watch the run to completion.
   *You'll know it worked when* the run reports `gate PASS`, its mean becomes
   the accepted baseline (`cmap.eval_run.accepted` via
   `POST /eval/runs/{id}/accept`), and
   [#546](https://github.com/u2giants/theoracle/issues/546) is closed with the
   run link. Then record the run id in the B3 STATUS row of
   [plan_oracle_repair_and_consultant_upgrade.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_repair_and_consultant_upgrade.md).
3. **C4's live check.** Record eval mean + average `context_tokens`
   before/after in `docs/verification/repair/C4.md` (create it; intended URL
   https://github.com/u2giants/theoracle/blob/main/docs/verification/repair/C4.md).
   *You'll know it worked when* the file is on `main` and the C4 STATUS row
   links it.
4. **C5 — Map page organised by function** (STATUS row: needs C3 ✅; it is the
   Owner-look #2 point). Working pattern the predecessor session proved: one
   worktree + one `edge-dev3` Postgres/FalkorDB container pair per step
   (distinct high ports — run `docker ps` first), one PR per step, re-run the
   named gate tests yourself, watch EVERY CI check before merging (lean
   required checks let red advisory tests merge), deploy in batches, file live
   proofs under
   [docs/verification/repair/](https://github.com/u2giants/theoracle/tree/main/docs/verification/repair).
   *You'll know it worked when* the step's named gate tests are green locally
   AND in CI, the PR is merged, and the plan STATUS row is updated with
   evidence.
5. **Owner look #2** after C5 lands (plan business acceptance): point Albert
   at the site.
6. Then continue in STATUS order: E3, E5, F1, F3, G3, G4, H3, H4, H5, then
   the chained ones (F2→F5/F6, D4, H2, I4, J1–J3; J1 also needs §0 item 2) —
   the full order is in the 1414Z handoff §6 step 4.

## 7. Constraints and gotchas in force

- Never push to `main`; branch + PR; the AI merges its own PR (Albert does not
  merge); reviews are advisory and never block; lean required checks — a red
  advisory check still needs fixing, it just will not stop the merge.
- One worktree per write-capable task; the canonical checkout is landing-only.
- `cmap` changes are new **idempotent** `B/sql/0NN_*.sql` files applied by
  `B/migrate.py` at start-up (next free number: **036**; 019–035 are used or
  retired). Landed files stay pristine. Never route `cmap` through
  `popcre/shared-db`; never hand-edit `packages/db/migrations`.
- No model ids in code (env/seat settings only — `B/seats.py`, `B/config.py`);
  new prompts live in `B/prompts/` and must appear in `T/test_prompts.py`.
- Repair, never remove: never disable ScaleDown, the weekly interview cap,
  quote validation, or any guard to make a test pass. Verbatim-quote
  validation and H1's support marks are locked.
- Locked owner rules: no per-fact approval queues; no permissions beyond login
  + admin; corrections always win over extraction and survive rebuilds;
  interview bot stays OFF until issue
  [#518](https://github.com/u2giants/theoracle/issues/518).
- The repo is PUBLIC: no secrets, employee-private content, or LAN addresses
  in fixtures, tests, docs, or plan rows. Fixtures use the synthetic company
  in
  [T/fixtures/](https://github.com/u2giants/theoracle/tree/main/apps/brain/tests/fixtures).
- Times shown to people are New York, labelled EST/EDT.
- Sign everything posted to GitHub: `Posted by MiMo chat <id> on <machine>`
  (`$MIMO_SESSION_ID`, or `unknown` when empty).
- Handoff files: one write-once file per session under `HANDOFF.d/`; never
  edit another session's file; never rewrite the root
  [HANDOFF.md](https://github.com/u2giants/theoracle/blob/main/HANDOFF.md) —
  it is the static pointer.

## 8. Access and environment

- `gh` authenticated as `u2giants`. Repo
  [u2giants/theoracle](https://github.com/u2giants/theoracle). This machine is
  `edge-dev` (Windows, pwsh 7; no working local Docker).
- 1Password vault `vibe_coding` (values only via `op://` references and
  `op run`/`op read` pipes — never in chat, argv, logs or commits). Relevant
  items (by title): `Coolify API token - Oracle deploy - release sessions only
  (theoracle)` (the ONLY key allowed to deploy oracle-brain), `Supabase DB
  Direct URL - The Oracle (CURRENT PROD, theoracle,
  eqccjfbyrywsqkxxpjvg)` (fields `password` = direct URL,
  `oracle_session_pooler` = the IPv4-reachable pooler), `Oracle Brain shared
  token - The Oracle (BRAIN_SHARED_TOKEN)` (the `x-brain-token` for
  admin/service API calls).
- Admin API calls need `x-brain-token` + `x-user-id` (an employee
  `auth_user_id` with `is_admin` — find via the pooler, read-only).
- `edge-dev3` reachable by `ssh edge-dev3` for test-store containers: one
  Postgres + FalkorDB pair per task on distinct high ports (6390, 5433, 6380
  taken — `docker ps` first), then `DATABASE_URL`/`FALKORDB_URL` at
  `edge-dev3:<port>`.
- Prod DB from this machine: use the `oracle_session_pooler` field (the direct
  host resolves IPv6-only and this machine has no IPv6 route).
- Local tooling: `uv`, `pnpm`, node, `gh`, `op` CLI 2.39, git-bash (for
  `sha256sum`). `ai-task-gates`, `ai-housekeeping`,
  `ai-shared-db-closeout-check` installed (the last queues behind slow
  admission — see §4). `bin/ai-doc-safety` does not exist in this repo —
  prose PRs merge with plain `gh pr merge`.
- GitHub Actions secrets: `BRAIN_SHARED_TOKEN` exists.

## 9. Open questions and risks

- The five §0 owner decisions (delivered 2026-11-15, unanswered at wrap-up) —
  item 1 blocks the gate, B3's baseline row, C4's eval numbers, and the start
  of C5 in Albert's prescribed order.
- C4's tuning values (similarity floor 0.25, function weight floor 0.2,
  routing cut 0.5) are flagged "tune on eval" in its PR — re-tune after the
  approved question set exists.
- `score_legacy`/`mean_score_legacy` must be retired after the third
  eval-bearing run (B2's three-run promise).
- Concurrent sessions (Chinese integration) are active in this repo —
  STATUS-row conflicts are possible; the `zh-*` worktrees are theirs.
- This session's wrap-up could not complete `ai-shared-db-closeout-check`
  inside tool timeouts (§4). The session holds no shared-db claims by
  construction (no shared-db work performed, no claims issued); rerun the
  checker with a long timeout if a proof receipt is wanted.

---

## Self-audit (handoff-writer gate, 2026-11-15)

1. **Comprehensive for a brand-new developer?** Yes — §1 defines the app and
   stack; §3 gives verified live state with SHAs; §6 gives ordered steps each
   with a "you'll know it worked when" gate; §8 gives every access fact.
2. **Detailed enough to continue as well as this session?** Yes — §2 records
   Albert's exact four-step instruction and which step is done; §4 records
   this session's dead ends (question tool abort, closeout-check admission
   queue, pwsh time syntax) plus the pointer to the predecessor §4 failures;
   §5 records the re-verified gate root cause.
3. **Every relevant detail included?** Yes — background (§1), goals (§2),
   current state with deploy status (§3), failures (§4), findings (§5),
   exact next actions + verification (§6), constraints (§7), access (§8),
   risks (§9). File and commit references are GitHub URLs; `C4.md` is
   uncreated and named by intended URL.
4. **If the owner read only §0, would he see every business decision and no
   technical approval?** Yes — sweep performed: the only owner-judgement
   sentences anywhere are the five questions (§0 items 1–5) and the Owner
   look #2 timing note (noted in §0 as "not yet due"). C4 re-tuning and
   `score_legacy` retirement (§9) are technical and stay with the AI; the
   closeout-check receipt (§9) is technical tooling, not an owner ask.
