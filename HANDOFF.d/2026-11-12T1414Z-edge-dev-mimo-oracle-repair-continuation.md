---
issue: 520
status: OPEN
owner: mimo/ses_ffe5e324c88ccffe4UKUXvdj04
---

# Handoff — Oracle repair/consultant plan: execution from B1 (session close 2026-11-12)

For the program issue [u2giants/theoracle#520](https://github.com/u2giants/theoracle/issues/520).
The live ledger is the STATUS table at the top of
[plan_oracle_repair_and_consultant_upgrade.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_repair_and_consultant_upgrade.md) —
read it first; do not re-derive or re-plan. This file carries the session
context that the plan cannot: what was tried and failed, the environment
mechanics, and exactly where to resume.

Final state of this session: brain and web both live on commit
[`faf381c4`](https://github.com/u2giants/theoracle/commit/faf381c4354ed060826556fb2b98910b834941ab)
(2026-11-12, 9:20 AM EST). 17 plan steps landed and deployed in one sitting.

---

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

**Put this whole list to Albert in ONE message before starting work.** Each
item needs a business judgement only; every technical step is done by the AI
itself. Recommendations are one word so he can answer fast.

**Blocking:**

1. **Approve the draft evaluation questions on the site.** The 30 drafts live
   on the Oracle's eval page
   ([https://oracle.designflow.app/map/eval](https://oracle.designflow.app/map/eval))
   with per-question recommendations; admin can approve, edit or retire each.
   *Recommendation: approve as written (edit anything that reads wrong).*
   *Blocks:* the live quality gate turning green (it is currently red by
   design — see issue [#546](https://github.com/u2giants/theoracle/issues/546));
   Phase B's business acceptance; and every score-based live check (the C4
   before/after eval, the B3 accepted baseline, Phase C acceptance).

**Recoverable if guessed wrong:**

2. **Which operational numbers come first** (plan step J1). *Recommendation:
   order-to-ship lead times and late shipments.* *Blocks:* only J1 onward.
3. **"Possibly out of date" horizon** (step D4). *Recommendation: 18 months
   for who-does-what, 36 months for rules.* *Blocks:* only D4.
4. **Who receives the Monday briefing** (step I4). *Recommendation: Albert
   only.* *Blocks:* only I4's send list.

**Not part of this workstream, nobody on it:**

5. **Who is the licensing team** (carried from issue #474). *Recommendation:
   derive from the directory and documents; it only speeds the first
   interviews.* *Blocks:* nothing (F3 routes without it).

**Also coming, not yet due:** Owner look #2 on the site after step C5 lands
(plan business-acceptance point). He will be told when it is ready.

**Already settled — do NOT re-ask** (with dates): the document corpus is
complete (2026-11-08); the interview bot stays OFF until issue #518 (plan
rule); the weekly interview cap stays (2026-11-10); questions for the owner
live on the Oracle site, never in .md files (2026-11-05); no per-fact approval
queues, no permissions beyond login+admin (2026-10-27); domains are by
part/function of the company (2026-11-11); the 13 business functions were
seeded and the owner can rename/merge them any time on
[https://oracle.designflow.app/map/functions](https://oracle.designflow.app/map/functions).

---

## 1. What this application is

The Oracle is POP Creations / Spruce Line's company adviser: it reads every
company document and meeting transcript into a knowledge map, answers
employee questions from that map with source citations, and interviews
employees over Teams to fill gaps. Owner goal: an all-knowing business
consultant that says what is broken, why, and what to change.

- Repo: [u2giants/theoracle](https://github.com/u2giants/theoracle) (PUBLIC —
  no secrets, no employee-private content, no LAN addresses in it).
- Web: Next.js on Vercel, [https://oracle.designflow.app](https://oracle.designflow.app)
  (Company Map pages under `apps/web/app/map/`).
- Brain: Python 3.12 FastAPI + one background worker on Coolify,
  [https://oracle-brain.designflow.app](https://oracle-brain.designflow.app)
  (image `ghcr.io/u2giants/theoracle-brain`).
- Data: the Oracle's own Supabase Postgres project (schema `cmap`; NOT the
  shared company database — shared-db rules do not apply to `cmap`) plus a
  FalkorDB graph rebuilt from Postgres.
- Pipeline jobs (`cmap.job`, `apps/brain/brain/worker.py`): read_source →
  classify_extract (flat) → relations → resolve → project → process_pass →
  contradictions → function_assign → communities → recommend. Answers:
  `apps/brain/brain/answer/answer.py`. Eval self-test: `apps/brain/brain/eval/run.py`.

## 2. What we set out to do this session, and why

Albert's instruction (2026-11-12): read the plan's STATUS and drift log, then
**execute from step B1**, acting as coordinator and spinning up subagents for
all the work, maximally parallel, double-checking everything. Phase A
(stop-the-bleeding repairs) was already done; the session started at Phase B
(quality bar) and was to continue through the plan as far as possible.

## 3. Current state — what is true right now

**Everything below is merged to `main`, deployed, and live at commit
[`faf381c4`](https://github.com/u2giants/theoracle/commit/faf381c4354ed060826556fb2b98910b834941ab)
(verified: `GET /health` → `{"ok":true,"db":true,"graph":true}`;
`https://oracle.designflow.app/version.json` → `git_sha=faf381c4`).**

Landed this session (step → PR):

- B1 question approvals + 30 drafts — [#543](https://github.com/u2giants/theoracle/pull/543)
- B2 eval scoring (0.6 points / 0.2 sources / 0.2 supported-share) — [#536](https://github.com/u2giants/theoracle/pull/536)
- B3 live quality gate workflow — [#544](https://github.com/u2giants/theoracle/pull/544) + gate fix [#545](https://github.com/u2giants/theoracle/pull/545)
- B4 pipeline health panel — [#538](https://github.com/u2giants/theoracle/pull/538)
- C1 curated 13 business functions — [#548](https://github.com/u2giants/theoracle/pull/548)
- C2 function assignment for sources/chunks/entities — [#552](https://github.com/u2giants/theoracle/pull/552)
- C3 function reports + stable cluster ids — [#560](https://github.com/u2giants/theoracle/pull/560)
- C4 function-scoped answering + hard token budget — [#575](https://github.com/u2giants/theoracle/pull/575)
- D1 every source has a date — [#554](https://github.com/u2giants/theoracle/pull/554)
- D2 source supersession — [#558](https://github.com/u2giants/theoracle/pull/558)
- D3 cross-source contradictions — [#569](https://github.com/u2giants/theoracle/pull/569)
- E1 relations across neighbouring passages — [#564](https://github.com/u2giants/theoracle/pull/564)
- E2 whole-document process flows — [#571](https://github.com/u2giants/theoracle/pull/571)
- E4 hand-offs in reports + company matrix — [#572](https://github.com/u2giants/theoracle/pull/572)
- F4 reply matching + chat safety — [#550](https://github.com/u2giants/theoracle/pull/550)
- G1 content-keyed corrections — [#555](https://github.com/u2giants/theoracle/pull/555)
- G2 entity merge/split/rename admin — [#562](https://github.com/u2giants/theoracle/pull/562)
- H1 every sentence supported or marked — [#563](https://github.com/u2giants/theoracle/pull/563)

Close-outs and docs: Phase B close-out [#547](https://github.com/u2giants/theoracle/pull/547),
C2/D1 live proof [#557](https://github.com/u2giants/theoracle/pull/557),
E1 live proof [#568](https://github.com/u2giants/theoracle/pull/568),
session learnings [#574](https://github.com/u2giants/theoracle/pull/574),
map-seed hotfix [#576](https://github.com/u2giants/theoracle/pull/576).

**Live proofs filed** under
[`docs/verification/repair/`](https://github.com/u2giants/theoracle/tree/main/docs/verification/repair):
B1.md (45 eval questions = 15 existing + 30 drafts, 0 approved), B3.md (gate
runs 43163303981 / 43165847107, issue #546), C2.md (0 sources without a
function; per-function counts), D1.md (zero NULL dates), E1.md (relation
yield 289→402 on the book-report transcript).

**Half-done / not started:** nothing of the dispatched work is half-done —
all 17 steps are merged with green CI. The remaining plan steps (C5, D4, E3,
E5, F1–F3, F5–F6, G3–G4, H2–H5, I1–I7, J1–J3) are **not started**. The live
quality gate ([brain-quality.yml](https://github.com/u2giants/theoracle/blob/main/.github/workflows/brain-quality.yml))
runs nightly at 5:17 AM EST and on dispatch; it is **red until the owner
approves the draft questions** (by design — the eval refuses to score an
empty approved set; issue #546 tracks it and closes when a run passes).

## 4. Everything we tried that did NOT work

- **Local Docker for brain tests.** The Windows machine (`edge-dev`) has the
  Docker CLI (scoop) but no daemon: dockerd fails ("Containers feature is not
  installed", no admin to enable). *Failed:* every `docker run` locally.
  *Fix that works:* test stores on `edge-dev3` over TCP (reachable via
  `ssh edge-dev3`) — one Postgres + FalkorDB container pair per task on
  distinct high ports, then `DATABASE_URL`/`FALKORDB_URL` point at
  `edge-dev3:<port>`. Ports 6390 and 5433/6380 were already taken on that
  host — always check `docker ps` before choosing.
- **Direct Supabase host from this machine.** `db.eqccjfbyrywsqkxxpjvg.supabase.co`
  resolves IPv6-only and this machine has no IPv6 route (TCP 5432 fails).
  *Fix:* the session pooler (`aws-1-us-east-1.pooler.supabase.com`, field
  `oracle_session_pooler` on the vault item) works over IPv4.
- **`op read "op://vibe_coding/<title>/..."` with a title containing
  parentheses** — rejected ("invalid character in secret reference").
  *Fix:* reference the item **ID** instead. Also `sha256sum` is absent in
  pwsh (use git-bash for fingerprints); PowerShell pipelines append a newline
  to piped secrets.
- **`ai-pr-wait`** crashed the tool harness twice ("ChildProcess.kill").
  *Fix:* `gh pr checks <pr> --watch --fail-fast` / `gh run watch <id>
  --exit-status` as the bounded waiter.
- **GHCR package listing** (`gh api /users/u2giants/packages/...`) — 403, no
  `read:packages` scope. *Fix:* a successful `brain-image.yml` run on the
  exact commit is the publish proof.
- **Editing an already-shipped SQL migration** (agent for D3 widened a CHECK
  inside `B/sql/024_function_assignment.sql`). *Why it's wrong:* landed
  migrations must stay pristine so each PR is independently revertable. *Worse
  trap discovered there:* migrate re-runs files in order every boot and
  `ADD CONSTRAINT` validates existing rows — a later file can leave rows an
  earlier file's re-assertion rejects and **the service fails to boot**
  (reproduced: `CheckViolation: extraction_stage_check`). *Fix:* widening
  lives in the new file (DROP IF EXISTS + ADD with the wider vocabulary).
- **Kind-vocabulary mismatch** (E2 wrote contradiction kind `"true
  contradiction"`, D3's CHECK allows `true_contradiction`) — the merge of the
  two parallel steps produced a runtime CheckViolation in E2's gate test.
  *Fix:* one shared snake_case vocabulary (`true_contradiction`,
  `policy_vs_practice`, `precedes_cycle`, `changed_over_time`, `same`,
  `refinement`).
- **Constant rename miss in a merge** (E4 renamed `CLUSTER_EDGE_KIND_WEIGHTS`
  → `EDGE_KIND_WEIGHTS`; C4's branch still imported the old name) — 16
  collection ImportErrors after merge. *Fix:* rename in the merge commit;
  always re-run the FULL suite after resolving conflicts, not just the step's
  own tests.
- **Order-dependent tests riding warm caches.** Two of E2's gate tests passed
  only because earlier tests left `get_settings` warm; D3's cache hygiene in
  the merge exposed them. *Fix:* each test seeds its own
  `BRAIN_FRONTIER_MODEL` + `get_settings.cache_clear()`.
- **`map_seed.py` broke after C4 merged** (its broken-pipeline wrap lambda
  pinned the old 3-arg `_finalize_local`; C4 added an `evidence` argument) —
  the map browser suite failed on C4's PR and the squash-merge landed before
  the red advisory check was noticed. *Fix:* hotfix
  [#576](https://github.com/u2giants/theoracle/pull/576). **Lesson: with lean
  required checks a red advisory map test does NOT block the merge — watch
  every check before merging anyway.**
- **First quality-gate run burned its 20-minute poll** (issue #546's first
  entry): the eval job failed "no eval questions" but A2's retry logic re-queued
  it as `state=queued` with the error text kept, so the gate's
  `state=='failed'` bail never fired. *Fix:* [#545](https://github.com/u2giants/theoracle/pull/545) —
  fail on any job error regardless of retry state.
- **Parallel step conflicts** (expected, resolved by the coordinator each
  time): `map.spec.ts` EOF test appends, `test_schema.py` EXPECTED_TABLES,
  `chain.py` heal lists, `eval-client.tsx`, the plan STATUS rows. Pattern:
  merge `origin/main` into the branch, keep both features, run the FULL suite.
- **PowerShell gotchas:** `${{` inside a double-quoted here-string gets
  interpolated (use `@'...'@`); `docker run` prints "Run 'docker run --help'"
  as part of ANY daemon error (the real error is the line above — e.g. "port
  is already allocated"); multi-line Edit-tool replacements fail on files with
  mixed line endings (normalize, or use single-line anchors).
- **Fresh worktrees** need root `pnpm install` before web lint/typecheck, and
  `uv run python -m brain.migrate` against an empty test DB before the first
  pytest run.

## 5. Root causes and key findings

- The plan's own root-cause analysis stands (audit
  [docs/audit-2026-11-11-oracle-goals.md](https://github.com/u2giants/theoracle/blob/main/docs/audit-2026-11-11-oracle-goals.md)):
  stale summaries, silent content loss, and too little cross-source joining.
  Phase A fixed the first two; this session's C/E/D waves attack the third.
- `T/test_schema.py::test_all_tables_exist` is an exact set match — every new
  `cmap` table needs its entry or the suite goes red.
- `conftest._clean_cmap` TRUNCATEs `cmap.function` CASCADE — anything
  exercising function vocabulary must seed functions per test.
- `tests/map_seed.py` drives both Playwright and some brain tests; its
  contracts (e.g. `licensing_community_id`) break the browser suite when
  community identity changes.
- Playwright map runs need a **throwaway** `BRAIN_E2E_DATABASE_URL` (a
  `brain_e2e` DB on the same edge-dev3 instance works) — never the brain
  pytest DB (conftest stubs poison `map_seed`'s DDL). Runs also rewrite every
  committed screenshot and `next-env.ts` — restore unrelated churn.
- With `conftest.fake_embeddings` all vectors are parallel (cosine 1.0) —
  similarity gates trip on unrelated fixtures unless titles differ.
- `ai-task-gates`: `check --before ship|deploy|pr-wait|database|...` (valid
  actions: review, code-only-review, pr-wait, ship, deploy, database,
  database-read, infrastructure, production). Any `B/sql/` file escalates the
  class to `shared-db` (this repo's canonical migration-path gates — NOT
  popcre/shared-db): re-declare `--class shared-db` and the ship check passes.
- Deploy mechanics (verified): image tag = **bare full sha**;
  `PATCH /applications/<uuid>/envs` accepts only key/value/is_preview/
  is_multiline/is_literal; then `POST /deploy?uuid=...`; verify `/health` and
  probe a route the release added. Never redeploy with queued/running
  `cmap.job` rows. (Now in
  [docs/deployment.md](https://github.com/u2giants/theoracle/blob/main/docs/deployment.md).)
- The eval answers now carry `supported_share` (H1) and the eval page shows
  `functions_consulted` + `context_tokens` (C4). `score_legacy` /
  `mean_score_legacy` are a three-run continuity aid (B2) — retire them after
  the third eval-bearing run.

## 6. Exact next steps

1. **Get the owner's answers to §0** (one message, all items). His approval of
   the 30 drafts is the unblocking one. *You'll know it worked when*
   `select count(*) from cmap.eval_question where approved_at is not null`
   shows > 0 (or the eval page shows "Approved").
2. **Run the live eval and arm the gate.** Dispatch `Brain quality gate`
   (`gh workflow run "Brain quality gate"`), watch run `43165847107`'s
   successors. *You'll know it worked when* the run reports `gate PASS`, its
   mean becomes the `accepted` baseline (`cmap.eval_run.accepted`), and issue
   [#546](https://github.com/u2giants/theoracle/issues/546) is closed with
   the run link. Record the run id in the B3 STATUS row (it currently names
   the two pre-approval runs).
3. **C4's live check (plan row: eval re-run; mean and average context tokens
   before/after).** After step 2, record mean + `context_tokens` in
   `docs/verification/repair/C4.md` (file does not exist yet). *You'll know it
   worked when* the file exists and the C4 STATUS row links it.
4. **Continue the plan in STATUS order.** First row marked ⬜ open whose
   "needs" are all ✅: **C5** (Map page organised by function — needs C3 ✅;
   it is the Owner-look #2 point). Then E3 (needs E1 ✅), E5 (needs E2 ✅), F1
   (needs C2+E2 ✅), F3 (needs C2 ✅), G3 (needs G2 ✅), G4 (needs G1 ✅), H3
   (needs C4 ✅), H4, H5 (needs A2 ✅), I1/I2/I5/I6/I7 (needs ✅), I3, then
   the chained ones (F2→F5/F6, D4, H2, I4, J1–J3; J1 also needs §0 item 2).
   Working pattern that this session proved: one worktree + one `edge-dev3`
   Postgres/FalkorDB container pair per step, one PR per step, coordinator
   re-runs the named gate tests and watches every CI check before merging,
   then deploys in batches and files live proofs under
   `docs/verification/repair/`.
5. **Owner look #2** after C5 lands (plan business acceptance): point Albert
   at the site.

## 7. Constraints and gotchas in force

- Never push to `main`; branch + PR; the AI merges its own PR (Albert does
  not merge); reviews are advisory and never block; lean required checks
  (only data-damage/secret checks may block) — so a red advisory check still
  needs fixing, it just won't stop the merge.
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
- Locked owner rules: no per-fact approval queues; no permissions beyond
  login + admin; corrections always win over extraction and survive rebuilds;
  interview bot stays OFF until issue #518.
- The repo is PUBLIC: no secrets, employee-private content, or LAN addresses
  in fixtures, tests, docs, or plan rows. Fixtures use the synthetic company
  in `T/fixtures/`.
- Times shown to people are New York, labelled EST/EDT.
- Sign everything posted to GitHub: `Posted by MiMo chat <id> on <machine>`.

## 8. Access and environment

- `gh` authenticated as `u2giants`. Repo `u2giants/theoracle`.
- 1Password vault `vibe_coding` (values only via `op://` references and
  `op run`/`op read` pipes — never in chat, argv, logs or commits). Relevant
  items (by title): `Coolify API token - Oracle deploy - release sessions only
  (theoracle)` (the ONLY key allowed to deploy oracle-brain),
  `Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle,
  eqccjfbyrywsqkxxpjvg)` (fields `password` = direct URL, `oracle_session_pooler`
  = the IPv4-reachable pooler), `Oracle Brain shared token - The Oracle
  (BRAIN_SHARED_TOKEN)` (the `x-brain-token` for admin/service API calls).
- Admin API calls need `x-brain-token` + `x-user-id` (an employee
  `auth_user_id` with `is_admin` — find via the pooler, read-only).
- `edge-dev3` reachable by `ssh edge-dev3` for test-store containers and the
  FalkorDB/Postgres test instances (see §4).
- Local tooling: `uv`, `pnpm`, node, `gh`, `op` CLI 2.39 (works), git-bash
  (for `sha256sum`). No working local Docker.
- GitHub Actions secrets: `BRAIN_SHARED_TOKEN` exists (added for B3).

## 9. Open questions and risks

- The live gate is red purely because the owner has not approved drafts (§0.1).
  Nothing else is wrong with it; both dispatch runs exercised the machinery.
- C4's tuning values (similarity floor 0.25, function weight floor 0.2,
  routing cut 0.5) are flagged "tune on eval" in its PR — re-tune after the
  approved set exists.
- `score_legacy`/`mean_score_legacy` must be retired after the third
  eval-bearing run (B2's three-run promise).
- Two older Chinese negative seed questions are abstention-style but still
  `abstention=false` (flag them when touching question rows — noted in the
  plan drift log).
- The live Recall webhook capture posts transcript bodies without meeting
  metadata, so those meetings date to `upload_time` until the capture passes
  `effective_date` (D1's PR body; a web-route change, unowned).
- `flow_step`/`process_flow` have no `updated_at` (E2 hashes content instead);
  G2's same-name split corrections are inert across rebuilds (G3 owns
  same-name identity).
- `(verifying)` sentence marks (H1) have no async fill-in job.

---

## Part (b) — sub-agent workstreams this session (18 dispatched, all finished)

Each block: task → what it did → PR → status. All merged unless noted.

- **B1 eval approvals + drafts** → SQL 019 + admin approve/edit/retire +
  30 drafts + approved-only bar + Playwright approve-flow →
  [#543](https://github.com/u2giants/theoracle/pull/543) → merged (coordinator
  resolved B2/B4 conflicts in the merge commit; agent hung after push and was
  cancelled — work was complete on the branch).
- **B2 eval scoring** → 0.6/0.2/0.2 formula + error-fails-run + abstention
  judging + legacy carry → [#536](https://github.com/u2giants/theoracle/pull/536)
  → merged after a Playwright repair round (its web change broke the
  `eval-mean` assertion).
- **B4 health panel** → `GET /sources/health` + admin panel + seeded-failure
  Playwright test + office-fixture zip fix →
  [#538](https://github.com/u2giants/theoracle/pull/538) → merged.
- **B3 quality gate** → `brain-quality.yml` + `B/eval/gate.py` + `accepted`
  baseline + `POST /eval/runs/{id}/accept` (coordinator review caught the
  missing live-accept round-trip; agent fixed it) →
  [#544](https://github.com/u2giants/theoracle/pull/544) → merged (+ gate
  fix [#545](https://github.com/u2giants/theoracle/pull/545) by the
  coordinator).
- **C1 function list** → `cmap.function` seeded with 13 evidence-mapped
  functions + admin page → [#548](https://github.com/u2giants/theoracle/pull/548)
  → merged.
- **C2 assignment** → `source/chunk/entity_function` tables + assignment job +
  admin rows that survive reruns + `eval_question.function` backfill →
  [#552](https://github.com/u2giants/theoracle/pull/552) → merged.
- **C3 clusters/reports** → function reports (id = function id), Jaccard
  level-0 ids, content-hash regeneration, map-reduce →
  [#560](https://github.com/u2giants/theoracle/pull/560) → merged.
- **C4 scoped answering** → routing + budget + hybrid mode + W/map/ask
  display → [#575](https://github.com/u2giants/theoracle/pull/575) → merged
  (coordinator resolved E4 conflicts + the `EDGE_KIND_WEIGHTS` rename; map-seed
  hotfix [#576](https://github.com/u2giants/theoracle/pull/576) followed).
- **D1 dates** → precedence resolver + `date_origin` + backfill action →
  [#554](https://github.com/u2giants/theoracle/pull/554) → merged (coordinator
  resolved C2 conflicts; live proof zero NULL dates).
- **D2 supersession** → `source_version` + guarded `relation.status` + upload
  detection + history reach → [#558](https://github.com/u2giants/theoracle/pull/558)
  → merged.
- **D3 contradictions** → `cmap.contradiction` + compare job + interview
  trigger + PRECEDES cycle + gap rows for F1 →
  [#569](https://github.com/u2giants/theoracle/pull/569) → merged (coordinator
  corrected its edit of landed SQL 024 first).
- **E1 relation windows** → window-2 extraction + exchange/page windows +
  dedupe + drop counts → [#564](https://github.com/u2giants/theoracle/pull/564)
  → merged (live proof: 289→402 relations on one transcript).
- **E2 process flows** → `process_flow`/`flow_step` + grounded steps +
  cross-source merge → [#571](https://github.com/u2giants/theoracle/pull/571)
  → merged (coordinator resolved D3 conflicts incl. the kind vocabulary fix).
- **E4 handoff matrix** → boundary edges in reports + company matrix +
  kind-weight edge caps → [#572](https://github.com/u2giants/theoracle/pull/572)
  → merged.
- **F4 reply matching** → personal-chat refs only + unified 7-day window +
  judge-based matching/profile/stop-resume →
  [#550](https://github.com/u2giants/theoracle/pull/550) → merged.
- **G1 corrections** → content-keyed `cmap.correction` applied at
  resolve/project/answer + review-flag migration →
  [#555](https://github.com/u2giants/theoracle/pull/555) → merged.
- **G2 entity admin** → merge/split/rename/never-merge actions writing
  corrections + targeted re-projection →
  [#562](https://github.com/u2giants/theoracle/pull/562) → merged.
- **H1 sentence support** → per-sentence check/rewrite/mark + `supported_share`
  seam swapped into B2's eval → [#563](https://github.com/u2giants/theoracle/pull/563)
  → merged.

Sub-agent findings worth keeping are folded into §4–§5 above.

---

## Self-audit (mandatory gate, 2026-11-12 9:20 AM EST)

1. *Could a brand-new developer with no project knowledge pick up here without
   asking a question?* **Yes** — §1 defines the app and URLs; §3 lists every
   landed step with its PR; §6 gives the ordered next actions with
   "you'll know it worked when" gates; §8 names every credential by vault
   item; §0 tells them exactly what to ask the owner first.
2. *Could they continue as effectively as this session could?* **Yes** —
   §4 catalogs every dead end with its working fix (Docker, IPv6, op://
   titles, migration trap, kind vocabulary, cache-dependent tests, merge
   patterns); §5 the non-obvious repo traps (EXPECTED_TABLES, conftest
   CASCADE, map_seed contracts, Playwright throwaway DB); §7 the standing
   rules; part (b) maps every sub-agent's PR so nothing is re-done.
3. *Every relevant detail — background, goals, state, failures, decisions,
   constraints, risks, next actions, verification?* **Yes** — each has its own
   section (§2 goals; §3 state + verification evidence with live-proof links;
   §4 failures; §5 findings; §6 actions; §7 constraints; §9 risks/decisions).
   Every file and PR reference is a GitHub URL; deploy status is explicit
   (`faf381c4`, both tiers verified live).
4. *If the owner read only §0, would he see every business decision — and no
   technical approval?* **Yes** — the sweep of §1–§9 found: draft approval
   (§3/§6 blocking), J1 numbers (§6.4), D4 horizon (§9→§0.3), briefing
   audience (plan I4→§0.4), licensing-team identity (§0.5). All five are in
   §0 with recommendations; no technical approval is asked anywhere (secrets,
   deploys, merges are all AI-side and named in §8/§7).

