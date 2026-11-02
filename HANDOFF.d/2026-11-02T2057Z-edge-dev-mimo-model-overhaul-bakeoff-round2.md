---
issue: 255
status: OPEN
owner: mimo/model-overhaul-2026-11-02 (edge-dev, session ses_ffe5e714070b5ffe79Z9JLDYFk)
---

# Company Map model overhaul: bake-off round two, Teams tenant access, step-14 close-out — baton

Written 2026-11-02, 3:57 PM EST (2057Z), edge-dev, MiMo. Program: parent
https://github.com/u2giants/theoracle/issues/240 ; step-14 issue
https://github.com/u2giants/theoracle/issues/255 ; model-overhaul issue
https://github.com/u2giants/theoracle/issues/294 (CLOSED). Spec:
https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md
(read STATUS first). Predecessor batons (keep all until step 14 closes —
they hold reviewer recipes and dead ends):
https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-30T1829Z-edge-dev-mimo-model-overhaul-bakeoff.md
and
https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-30T1442Z-edge-dev3-claude-step14-model-split.md
and the step-9 baton
https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-29T2340Z-edge-dev-mimo-company-map-step9-paused.md
.

## 0. ⚠️ Business decisions only the owner can make

Put ALL open items below to Albert in ONE message before starting work.

Open (owner action needed):
1. **Albert and Ilona edit the 20 draft eval questions** (Appendix A of this
   file — also delivered to Albert in chat as a presented file
   `eval-questions-draft-20.md`). Each question must need 3+ sources; final
   versions go on the Map's eval page (admin). Until then the real-corpus eval
   can only run the five seed questions, whose expected answers are written
   for the invented fixture corpus (see §5 — the real-corpus mean of 0.2 is
   NOT a model-quality number). Recommendation: this week; it is the only way
   to get a real score. Blocks: step-14 acceptance and the bake-off's
   step-11 column.
2. **Albert and Ilona spend 30 minutes marking wrong items on the first Map**
   (plan step 14). Record their verbatim verdict in the plan STATUS row.
   Recommendation: after the 20 questions are in. Blocks: closing #255.
3. **Have one more employee say "hi" to the Teams bot** — the owner's own
   "hi" is proven (see §3); one colleague's message proves the tenant-wide
   auto-registration path end to end. Recommendation: one message, any
   colleague. Blocks: nothing (proof nicety for the tenant ruling).

Already settled this session — do NOT re-ask (all from Albert, 2026-11-02 and
2026-10-30, recorded verbatim where quoted):
- **Tenant identity ruling (2026-11-02, verbatim):** "all emails in the system
  should be @popcre.com emails. All empployees in our M365 tenant should be
  able to access the oracle to feed information in." Implemented (PR #318,
  #320); canonical contact emails are @popcre.com; Teams senders from the
  tenant auto-register on first message. This is identity hygiene, NOT a
  permission system (the plan allows only login + `is_admin`).
- **Eval questions:** "Draft for us first" — done (Appendix A); owner edits.
- **Teams self-test:** "Yes, I'll send 'hi' (Recommended)" — DONE, proof
  recorded (§3). Further employee messages welcome (item 3 above).
- **First Map review:** "Yes, when it's ready (Recommended)" — see open item 2.
- **Remaining corpus / feed-in direction (verbatim):** "we have to build out
  the functionality of this system talking directly to employees over Teams" —
  corpus growth comes through Teams conversations with employees; the fuller
  interview build-out (proactive conversations, not just answers to asked
  questions) is the next program item (§6 step 4).
- **OpenRouter $25/day cap:** "Keep $25/day (Recommended)" — kept.
- **Public-repo git-history exposure:** "Accept residual history
  (Recommended)" — accepted; no rotation; identifier-level only.
- **Model split with Haiku 5.5 as the only Claude conversation model**
  (2026-10-30); reviews advisory and never block merges (owner ruling
  2026-10-29); FalkorDB stays; no permission system beyond login + `is_admin`;
  plan §11 env-only model ids.

## 1. What this application is

The Oracle (https://github.com/u2giants/theoracle) is POP Creations'
evidence-backed company adviser. The current program is the Company Map: it
reads company documents, diagrams and employee transcripts and shows how work
actually flows — where hand-offs break — plus answers that cite many sources.
`apps/brain` is a Python FastAPI service + worker loop doing all AI and graph
work; Postgres (Supabase project `theoracle`, project ref redacted — see
https://github.com/u2giants/theoracle/pull/300 ; schema `cmap`) is the durable
store; FalkorDB holds graph `company`. `apps/web` is Next.js on Vercel
(production https://oracle.designflow.app) proxying `/api/brain/*` to the
brain, which is hosted on Coolify (hetz VPS) as compose app `oracle-brain` at
https://oracle-brain.designflow.app (`/health` → `{"ok":true,"db":true,"graph":true}`).
The repo is PUBLIC — world-readable; private-reference placeholders only, no
LAN addresses, no project refs (see §7).

## 2. What we set out to do this session, and why

Albert's resume brief (2026-11-02 chat): finish the model bake-off and step
14's first real run. Ordered next actions: (1) merge PR 301 after doc-safety
EXIT=0, (2) put the predecessor baton's §0 business questions to Albert in one
message, (3) apply migration 004_eval_models.sql to prod (gate-blocked for the
prior session), (4) fix the Haiku 5.5 empty-content bug and seat Haiku via
`BRAIN_CHAT_MODEL` on Coolify, (5) run the bake-off per the job brief §5 and
fill its results table with eval_run ids. Plus: reorganize the admin model
page around the new stages (already landed as PR #302 — verified), write a new
accurate job brief via deep code investigation, and answer which direct
provider keys exist and whether a Xiaomi MiMo key can ride Albert's
subscription. Mid-session the owner added the tenant identity ruling (§0) and
sent a live Teams "hi" that exposed an identity-matching bug.

## 3. Current state — what is true right now

Landed on `main` this session (all MERGED, verified via `gh pr view`):
- **PR #301** https://github.com/u2giants/theoracle/pull/301 (merge
  `cc1d5a4d`) — the predecessor model-overhaul baton. Merged after
  `bin/ai-doc-safety` EXIT=0 on head `8ca2fcc7` (the original wrapper log was
  lost; rerun per the baton dead-ends section).
- **PR #307** https://github.com/u2giants/theoracle/pull/307 (merge
  `efbead1e`) — empty-content rescue at every OpenRouter call site
  (`brain/llm.py:post_chat_with_rescue`: one retry with doubled max_tokens +
  hidden low-effort reasoning) and answer budget 4000→8000. Brain suite 133
  passed. Root cause measured: `anthropic/claude-haiku-5.5` thinks 800–1400
  tokens before content (`completion_tokens_details.reasoning_tokens` on
  OpenRouter), so max_tokens=4000 could return `content: null`.
- **Haiku seated:** `BRAIN_CHAT_MODEL=anthropic/claude-haiku-5.5` on Coolify
  (app `oracle-brain`), image tag pinned to a main SHA. `GET /models` confirms
  answer=claude-haiku-5.5, grade=claude-sonnet-4.5 (frozen grader fallback).
  **Gate: 5/5 seed answers non-empty** through the hosted brain (lengths
  759–2470 chars, 6–18 citations each).
- **Migration 004 applied to prod** (`python -m brain.migrate`): verified
  `cmap.eval_run.models` jsonb exists in `information_schema.columns`. The
  prior session's gate-block was a stale `ai-task-gates` base; re-declared
  `--class production --base <fresh main>` and checked `--before database`
  with Albert's exact authorization quote (the gate asks for exactly that).
- **PR #308** https://github.com/u2giants/theoracle/pull/308 (merge
  `421dd113`) — admin model page header links the model-stage job brief.
- **PR #309** https://github.com/u2giants/theoracle/pull/309 (merge
  `26a5cc0a`) — job brief corrected to match the code (deep audit, §5) and
  the page's clipboard brief copy synced (answer 8000 tokens, recommend
  `duplicate_of`).
- **PR #310** https://github.com/u2giants/theoracle/pull/310 (merge
  `982fd90b`) — global answers no longer crash on a non-uuid `source_id`
  (bake-off candidate cited "REPORTS"); such citations drop to `(uncited)`.
  134 brain tests.
- **PR #311** https://github.com/u2giants/theoracle/pull/311 (merge
  `abf708eb`) — bake-off fixture micro-eval results file
  https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/bake-off/2026-11-01-fixture-micro-evals.md
  and the job brief §5 results table filled with eval_run ids.
- **PR #315** https://github.com/u2giants/theoracle/pull/315 (merge
  `f994bec9`) — first real-corpus run evidence
  https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/first-run.md
  and plan STATUS row 14 → "🟨 hosted, awaiting owner review".
- **PR #318** https://github.com/u2giants/theoracle/pull/318 (merge
  `0feac3e6`) — Teams senders match on any linked identity email (the owner's
  production "hi" matched no employee because `employees.email` held a
  personal address; lookup now also matches `employee_identities.email`).
- **PR #320** https://github.com/u2giants/theoracle/pull/320 (merge
  `7b92fc15`) — tenant auto-registration: first Teams message from an unknown
  **@popcre.com** sender creates a minimal employee row (name from the Teams
  profile). Non-tenant addresses never auto-register. Deployed (brain image
  tag `7b92fc1556e0152f106d0c486c2d9d78beb386c7`, `/health` ok after deploy).
- **PR #322** https://github.com/u2giants/theoracle/pull/322 (merge
  `27bdac72`) — repaired the `task gates` verify job (red on main since
  #313): the contract tests still expected `reviewer-safety` for the paths
  #313 reclassified as `code`. Verify is green again.

Live evidence recorded:
- **Owner's Teams "hi" proof (step 12 manual proof) is in the system:**
  `cmap.teams_conversation` row "Albert H. · albert@popcre.com · updated
  2026-11-02 19:58:44 UTC" (verified via prod query).
- **Albert's employee email normalized** to `albert@popcre.com` (was a
  personal address) per the tenant ruling.
- **Real-corpus pipeline COMPLETE** (prod `cmap`, verified 2026-11-02): 8
  sources / 97 chunks / 289 extractions / 2045 mentions / 977 entities / 862
  relations / 867 communities (441 L0 + 425 L1 + 1 L2 company report) / 7
  recommendations / 4656 open questions. The `communities` job had failed
  2026-10-30 ("embeddings call failed after retries" — daily cap exhaustion)
  after 440 L0 reports; resuming via `POST /map/rebuild` completed it
  (stored-report reuse). `recommend` chained after and is done.
- **Real-corpus seed eval:** eval_run `5cd3a206-de53-4611-8732-cf047491572e`,
  mean 0.2 — read carefully: the five seed questions' expected points are
  written for the invented fixture corpus (names/systems/durations), so this
  measures question/corpus fit, not model quality. Per-question: 0.667 /
  0.333 / 0 / 0 / 0. Same five on the fixture corpus scored 0.5333 under
  identical seating (eval_run `269558df-9300-48e5-91f3-241505c257d4`).
- **Bake-off fixture micro-evals (grader frozen on claude-sonnet-4.5):** full
  matrix in
  https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/bake-off/2026-11-01-fixture-micro-evals.md
  — heavy seat: sonnet baseline 0.5333 (530 relations), glm-5.3-flash 0.6
  (495 rels, eval_run `4f88dd04-96d5-48c4-939a-490934b5a1f9`) = finalist,
  gemini-3.1-flash-lite 0.5333 (423 rels, `b21c92a6-f507-4aaf-a65d-5c056bc68814`)
  = second finalist (recall warning), qwen3.7-flash FAIL (empty content even
  after rescue — disqualified). Conversation seat on the same graph: Haiku
  0.5333, glm 0.6 (`0b732084-1c76-4c72-8a2e-82266c5d524b`), gemini 0.4
  (`eb516e0c-2fc7-4401-815f-8cfb40df058a`) — Haiku holds the assigned seat.
- **Bake-off round two (real-corpus swaps) ran but BOTH RUNS ARE INVALID** —
  see §4 dead end 8 and §6 step 1. GLM run: eval_run
  `db0d8e9d-d23e-4532-a19c-f754fe98b2dc` mean 0.0667; gemini run: eval_run
  `bea242ad-8258-44d4-9331-0512a4fec776` mean 0.0; both show `entities: 0`
  (the swap runner omitted `run_resolve()`), so the graph was empty and the
  numbers are meaningless. Rerun required (§6 step 1).
- **Keys question (owner question 4 of the predecessor baton) — answer
  delivered in chat and recorded here:** direct provider keys exist and are
  UNUSED by the brain (it uses ONE OpenRouter key, $25/day cap): OpenAI,
  Google/Gemini, DeepSeek, Qwen (Alibaba), GLM (z.ai), StepFun, Meta Muse —
  vault items titled "openai API key for designflow", "ai provider api keys
  openai deepseek chatgpt qwen", "Google AI (Gemini) API Key...", "deepseek
  API key for reviewer only", "qwen coder alibaba token plan api key", "z.ai
  GLM API key for designflow dflow plm", "stepfun step5 ai api key". A
  "Xiaomi MiMo API key riding the subscription" does not exist as a drop-in:
  this machine can mint only loopback-only, process-lifetime OpenAI-compatible
  tokens over its configured models (`mimo llm-server issue`), which serve
  chat only (no /embeddings) and REFUSE `response_format` — the brain's JSON
  mode needs it, so it cannot replace OpenRouter for the hosted brain.

Not started / not done:
- Bake-off round two rerun (with resolve) and the heavy-model seating.
- Community-reports quality pass (§4.6 of the job brief) before any reports-
  slot swap — that slot is human-read.
- The fuller Teams interview build-out (proactive conversations; current code
  only ingests answers to asked questions — see §6 step 4).
- Owner items §0 (20 questions, map review) and closing #255.
- Vision/embeddings bake-off rows (job brief §5 table rows 1-2).

## 4. Everything we tried that did NOT work

1. **ai-task-gates stale-base escalation (carried from the predecessor baton,
   still the #1 time sink).** The recorded gate base predated the merged
   hosting PRs, so every check observed main's files as "my" change set and
   escalated to `deployment`, where `check --before database` is FORBIDDEN.
   Fix that worked: `ai-task-gates start --class production --base <fresh main
   SHA> --reason ...` on a clean base, then `check --before database
   --acknowledge "<Albert's exact words>"` — the gate itself tells you the
   acknowledge form it wants. Do not re-declare repeatedly on the stale base.
2. **PowerShell double-quoted here-strings eat `$PATH`.** Generating bash
   wrappers with `@"..."@` expanded `$PATH` to empty, so the inner scripts
   lost `/usr/bin` and WinGet links (`date: command not found`, `op: command
   not found`, EXIT=127) and the whole bake-off chain "finished" in seconds
   with nothing run. Fix: write wrappers with SINGLE-quoted here-strings
   (`@'...'@`) so `$PATH` stays literal, or use `.Replace()` templating.
3. **PowerShell `git commit -m` with a multi-line message breaks** ("did not
   match any file(s) known to git", commit silently NOT created). Fix: write
   the message to a temp file and `git commit -F <file>`.
4. **`Add-Content` with a doubled relative path** (`workdir=apps/brain` +
   path `apps/brain/tests/...`) fails "Could not find a part of the path".
   Use paths relative to the workdir exactly once.
5. **`bin/ai-pr-wait` needs `--repo u2giants/theoracle`** (it cannot infer the
   repo from a bare invocation in temp); without it: "cannot determine the
   repository", EXIT=3.
6. **`ai-doc-safety` takes 15-25 minutes and the wrapper log is the only
   artifact.** The recipe that keeps working: wrapper `.sh` with PATH
   including a Python dir and Git's mingw64 bin, launched detached via
   `Start-Process bash <wrapper>`, poll the log for `EXIT=0`. The original
   `doc-safety-301e.log` from the predecessor session was gone — rerun on the
   PR head is the documented fallback and worked.
7. **qwen3.7-flash disqualified for JSON stages:** relations returned empty
   content even after the PR #307 rescue (2× max_tokens + hidden low
   reasoning) — reasoning-tier behavior. Same class as the predecessor's
   deepseek-v4.1-flash / qwen3.8-flash crashes. Keep reasoning-flagged tiers
   off the JSON seats; treat empty content as a stage failure.
8. **Bake-off round-two swap runs produced INVALID evals (my runner bug).**
   `bakeoff_swap.py` (edge-dev machine temp) copied the real corpus (8
   sources/97 chunks with embeddings) and ran classify_extract + relations +
   project + eval but **omitted `run_resolve()`**, so `entities: 0`, the graph
   was empty and the eval means (0.0667 glm / 0.0 gemini) are meaningless —
   the same "empty graph" trap the predecessor baton called out. The fixture
   micro-eval runner (`bakeoff_run.py`, edge-dev machine temp) DOES call
   `run_resolve` — copy that step. Rerun per §6 step 1.
9. **Teams "hi" matched no employee (found by Albert's live test).** Two
   stacked causes: `senderEmail` → `_find_employee` matched only
   `public.employees.email` (which held his personal address while Teams
   delivers `albert@popcre.com`), and unknown tenant employees had no row at
   all. Fixed by PR #318 (match `employee_identities.email` too) and PR #320
   (auto-register unknown @popcre.com senders). Test-stub gotcha: the
   stand-in `public.employee_identities` in
   [tests/conftest.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/conftest.py)
   needed an `email` column added to mirror the real schema.
10. **`verify` (task gates) red on main since PR #313** — the policy
    reclassified reviewer-safety paths as `code` but
    [scripts/test-task-gates.sh](https://github.com/u2giants/theoracle/blob/main/scripts/test-task-gates.sh)
    still expected `reviewer-safety` (8 failures, e.g. "uncommitted policy
    edit lost protected-path classification"). The auto-fixer deferred it
    (issue #316, labels fixer-deferred/fixer-done). Fixed in PR #322 by
    following the policy's intent. Note: the suite hangs in local git-bash on
    edge-dev (never finishes); CI runs it in ~30s and is the authoritative
    run.
11. **Global answers crashed on non-uuid citations** (`InvalidTextRepresentation`
    on the uuid column when a candidate cited source_id "REPORTS") — PR #310.
12. **`e.full_name` does not exist** on prod `public.employees` (probe error);
    the column is `name`.

## 5. Root causes and key findings

- **Haiku 5.5 empty-content root cause (measured on OpenRouter):**
  `anthropic/claude-haiku-5.5` is a reasoning-tier model — 777–1424
  `reasoning_tokens` per answer call before any content. With max_tokens=4000
  a long JSON answer could exhaust the budget and return `content: null`.
  Fixed by answer budget 8000 + the shared rescue in
  [brain/llm.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/llm.py)
  (retry once, doubled max_tokens, `reasoning: {"effort":"low","exclude":true}`
  ONLY on the rescue — first-attempt behavior is untouched so the frozen
  grader is unaffected).
- **Eval provenance is the bake-off audit trail:** `cmap.eval_run.models`
  records resolved answer/grade models + raw slots + extraction model counts
  (PR #297). No number enters the brief's results table without an eval_run
  id or a micro-eval output file under `docs/verification/company-map/bake-off/`.
- **The five seed questions are a fixture instrument.** Their expected points
  name fixture facts (Jessica / Artwork Log / "rework loop adds weeks"). On
  the real corpus the grader marks those missing — mean 0.2 despite sound
  answers. The real-corpus instrument is the 20 owner questions (Appendix A).
  Cross-candidate comparisons on the SAME corpus remain valid (that is how
  the micro-eval matrix works).
- **Communities is the cost center and the fragility center:** ~1 call per
  Leiden community with 12k contexts (441 L0 on the real corpus). A daily-cap
  exhaustion surfaced as "embeddings call failed after retries" and killed a
  15-hour job mid-flight; `POST /map/rebuild` resumes with stored-report
  reuse (keyed level+entity set) — do not restart from scratch. Never
  redeploy the brain while a job is running (job rows would orphan).
- **Teams intake chain (now working):** Teams bot route
  (`apps/web/app/api/teams/bot/messages/route.ts`) → `senderProfile`
  (TeamsInfo.getMember → email + display name) → brain
  `POST /interview/teams/inbound` (`require_service`) →
  [interview/inbound.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/interview/inbound.py)
  `_find_employee` (employees.email OR employee_identities.email) →
  `_ensure_employee` (auto-register @popcre.com senders) → store
  `cmap.teams_conversation` conversation_ref (the only way to write back
  later) → pending-question handling ("stop"/"skip"/answers become
  `cmap.source` transcripts) → anything unhandled falls through to the
  meeting-join helper ("To bring Oracle into this meeting, type join...").
  `BRAIN_INTERVIEW_ENABLED` gates only the outbound ask tick, NOT inbound.
- **Model seats live in Coolify env (plan §11 env-only):** `GET /models`
  (require_service) mirrors the env; seating a winner = update the Coolify
  env + `BRAIN_IMAGE_TAG` to a main SHA with a green `brain image` build, then
  `POST /api/v1/deploy?uuid=uge6pfm4qapktivto4981mtg`. PATCH envs via the
  Coolify API accepts `{key,value,is_preview,is_multiline,is_literal}` only —
  `is_build_time`/`is_comment` are rejected (422).
- **OpenRouter key balance:** `GET /api/v1/key` → `limit_remaining` (of the
  $25/day cap). Heavy smokes right after the midnight-UTC reset; abort runs
  when under $3 remains.
- **Fixture micro-eval matrix (2026-11-01, grader frozen, chat Haiku fixed):**
  sonnet 0.5333 / glm-5.3-flash 0.6 / gemini-3.1-flash-lite 0.5333 /
  qwen3.7-flash FAIL. Relations kept: 530 / 495 / 423. GLM truncates
  relations JSON at 2000 tokens more often (5 chunks; item-wise salvage
  kept runs clean). Conversation challengers on the sonnet graph: glm 0.6,
  gemini 0.4 — inside the 5-question noise band; Haiku keeps the assigned
  seat (report-back triggers only if it lands materially BELOW).

## 6. Exact next steps

1. **Rerun bake-off round two WITH resolve.** Take the swap runner from edge-dev
   machine temp (`bakeoff_swap.py`) and add the missing `run_resolve()` call
   between the relations loop and `run_project()` (copy the pattern from
   `bakeoff_run.py` / `brain.smoke`). Fresh databases on the test services
   (Postgres port 56789, FalkorDB port 56791 — one shared `company` graph
   name, so runs must be strictly sequential). Candidates: `z-ai/glm-5.3-flash`
   (finalist) and `google/gemini-3.1-flash-lite`, grader frozen
   `anthropic/claude-sonnet-4.5`, chat `anthropic/claude-haiku-5.5`. **You'll
   know it worked when** each RESULT line shows `entities` > 900 (the prod
   corpus has 977) and carries an eval_run id whose `models` manifest names
   the candidate as frontier.
2. **Seat the heavy model only after a relations-recall check.** Compare the
   rerun's relations count against the sonnet baseline (862 on prod; fixture
   spread was 530/495/423) and read 3 community reports for quality (the
   slot is human-read; job brief §4.6 (a)+(b)). If GLM holds, set
   `BRAIN_FRONTIER_MODEL=z-ai/glm-5.3-flash` in the Coolify env (app uuid
   `uge6pfm4qapktivto4981mtg`) + pin `BRAIN_IMAGE_TAG` to the latest green
   main SHA + redeploy. **Gate:** `/health` true, `GET /models` shows the new
   id, one seed eval run on prod scores no worse than the same-day baseline.
3. **Fill the job brief §5 "Step-11 mean" column** (file
   https://github.com/u2giants/theoracle/blob/main/docs/company-map/model-stage-job-brief.md)
   from the rerun eval_run ids; update the micro-evals file's "Provisional
   read" with the seating decision.
4. **Teams interview build-out** (owner direction, §0): today the intake only
   turns ANSWERS TO ASKED QUESTIONS into sources. "Talking directly to
   employees over Teams" needs proactive intake (an employee volunteers
   knowledge unprompted → become a source) and eventually the outbound
   question tick (`BRAIN_INTERVIEW_ENABLED=true`, weekly cap, `stop`/`skip`
   already work). Design constraint from the plan: no gates on reading, no
   permission system beyond login + `is_admin`.
5. **Owner items (§0):** collect the edited 20 questions and enter them on
   the eval page; run the 30-minute map review; record the verbatim verdict
   in the plan STATUS row 14; then close #255 and post a drift note on #240.
6. **End-of-plan drift check** (plan §14, still owed): re-read plan Part 1 vs
   what is live and post the drift report on #240.

## 7. Constraints and gotchas in force

- Never push to protected `main`; branch + PR; `gh pr merge --squash --admin`
  for this repo's prose and code lanes (reviews advisory, owner ruling
  2026-10-29). Sign GitHub posts with `Posted by MiMo chat <session-id> on
  edge-dev`. Quote times in EST/EDT (America/New_York).
- Model ids: env only (plan §11). Never hard-code them.
- The repo is PUBLIC. Private-reference placeholders only (`PRIVATE_REFERENCE_SHA256_...`);
  never LAN IPs (use "the test services host" wording), never Supabase project
  refs, never credential-shaped strings. `bin/ai-doc-safety` on the PR head is
  the merge gate for doc PRs (public-boundary + local markdown links;
  allowlist `tools/public-boundary-allowlist.txt` inside the repo).
- The pytest suite TRUNCATEs `cmap.*` on the shared test DB (Postgres port
  56789 on the test services host) — never run it mid-smoke. One FalkorDB
  graph name (`company`) is shared — never run pytest and a candidate run at
  the same time; candidate runs must be strictly sequential.
- Do not redeploy the brain while jobs are running (orphaned `running` rows).
- HANDOFF.d discipline: never edit another session's file; delete a
  predecessor's file only under the successor rule (all three conditions) —
  the three predecessor batons stay until step 14 closes.
- `ai-task-gates`: declare the class (`start --class code|production ...`)
  before risky steps and `check --before <action>`; for `database` the gate
  wants `--acknowledge "<Albert's exact authorization words>"`. The stale-base
  trap (dead end 1) is the failure mode.
- Lean required checks (owner ruling 2026-10-30): only checks that stop
  production-data damage or secret leaks block a merge. The pre-existing red
  checks (`Oracle offline suites`, `oracle2-offline`, `Entire Gates`) are
  known and non-required.

## 8. Access and environment

- Machine edge-dev (Windows coordinator). Canonical checkout is landing-only;
  this session's worktrees (all merged, to be removed after this PR) lived
  under the machine's `oracle-worktrees` directory. Test services on the
  edge-dev3 host (Postgres 16 + pgvector port 56789, FalkorDB port 56791,
  user oracle/oracle, db `brain_test`; fresh bake-off DBs `cmap_bake_1..6`).
  IPs redacted — resolve via the machine atlas / ssh config on edge-dev.
- `gh` authenticated as `u2giants`. Commit identity: `Albert Hazan
  <u2giants@users.noreply.github.com>`.
- 1Password MCP (`op_run`, vault `vibe_coding`) — values move only via `op://`
  refs: OpenRouter `62ieeyycs4ierflalbbbt5pq5i`/`OPENROUTER_API_KEY` ($25/day);
  ScaleDown `epna47xmzcnbdc6eb3tjpx6phm`/`SCALEDOWN_API_KEY`; shared token
  `4lm6bpl7bc25lqne4meumwcd2a`/`BRAIN_SHARED_TOKEN`; Supabase prod connection
  `qcuyabwseaptvuzvtjejffi2ou` (field `oracle_session_pooler` = the working
  one; field `password` = direct URL is IPv6-only from edge-dev); Coolify
  read/write `u3aqw63jqnkmnziip3gp5hwb5m`/`credential`.
- Coolify app `oracle-brain` (uuid `uge6pfm4qapktivto4981mtg`), API base via
  the hetz tailnet (never the public IP for tokens), deploy
  `POST /api/v1/deploy?uuid=...`, env PATCH `/applications/<uuid>/envs`.
  Current image tag `7b92fc1556e0152f106d0c486c2d9d78beb386c7` (includes PRs
  #318+#320). Vercel prod auto-deploys `apps/web` from main.
- Brain API auth: `x-brain-token` (BRAIN_SHARED_TOKEN) + `x-user-id` (a
  Supabase auth user id mapped to an active `is_admin` employee in
  `public.employee_identities`); `require_service` for server-to-server.
  Admin auth user id used this session: `751efc6f-b030-43cf-9f22-8e82ac389771`.
- Machine-local run artifacts on edge-dev (temp): `bakeoff_run.py` (fixture
  micro-eval runner — CORRECT, includes resolve), `bakeoff_swap.py` (real-
  corpus swap runner — BROKEN, missing resolve), `bakeoff-b1..b6.env/.sh/.log`
  and `bakeoff-s1/s2` logs (results quoted in §3/§5), `coolify-seat-*.py`,
  `gate_one_answer.py`, `prod_*.py` probes. Secrets are op:// refs inside the
  `.env` files; safe to reuse.
- Python: uv venv per worktree (`uv sync`, `uv run pytest`, `uv run ruff
  check .`); `pnpm install --frozen-lockfile` + `pnpm -w typecheck`/`lint` for
  web changes.

## 9. Open questions and risks

- The swap rerun (§6 step 1) is the gate for seating the cheap heavy model;
  until it lands, prod runs on sonnet for all heavy stages (costly).
- Relations-recall spread (fixture 530/495/423) may widen on the real corpus;
  the job brief §4.4 recall probe is the check — do not seat on price alone.
- The 5-question eval instrument is noise-level (one question = 0.2 of mean);
  the 20 owner questions are the real measure (§0 item 1).
- Community-reports quality for any cheap candidate is unproven (excluded
  from the micro-evals as the cost center). If GLM's reports read badly to
  Albert, the slot can stay on the conversation model (job brief §7 decision 2).
- Open review-fixer PRs #306/#291/#284/#280 predate this session and are not
  ours; leave them (their issues track them).
- `BRAIN_CHAT_MODEL`/`BRAIN_EVAL_MODEL` set in Coolify; `BRAIN_EVAL_MODEL`
  is unset (grader falls back to frontier = sonnet) — the "frozen grader" is
  that fallback; if `BRAIN_FRONTIER_MODEL` moves to a cheap candidate, SET
  `BRAIN_EVAL_MODEL=anthropic/claude-sonnet-4.5` explicitly in the same change
  so the grader cannot drift with the frontier seat.
- Git history of the public repo retains the redacted identifiers (accepted
  by the owner, §0).

---

## Part (b) — sub-agent blocks (this session dispatched sub-agents)

**explore-1 — job-brief accuracy audit (finished, read-only).** Asked to
verify every checkable claim in the model-stage job brief §§3–6 against
`apps/brain` and `apps/web` after PRs #295/#297/#299/#302/#307. Delivered a
discrepancy table (stale call-site ranges after `brain/llm.py`, the wrong
recommend call-site line, the communities module path, the resolve rule
numbering, the missing `duplicate_of`, the judge-band volume note, and the
page-copy staleness) and a verified-correct list (all nine role briefs'
benchmarks, prompts, thresholds, and the §6 implementation checklist). Its
findings became PR #309 in full. No files touched, no worktree kept.

---

## Appendix A — the 20 draft eval questions (for Albert and Ilona)

Delivered to Albert in chat as a presented file `eval-questions-draft-20.md`;
reproduced here so the successor can enter them without hunting. Each is
written to need 3+ sources. Sources in the Map: `business-process.md`,
`Pop_Creations_Flow_12112025.png` (swimlane flowchart),
`Licensed_Team_Responsibilities_2_-_tagged.txt`, `SOP_Mockup_Creation.pdf`,
`SOP_Packaging_creating___saving.pdf`, `Licensing_Sheet_Automation_Workflow.pdf`,
`SOP_Artwork_standards_creation_and_saving.pdf`,
`transcript-Book_report_overview.txt`.

1. Walk the path of a licensed product from first concept to the purchase
   order. Which hand-offs between Sales, Creative, Technical Design, Sourcing
   and the Licensing Team are documented the same way in the flowchart and in
   the business-process document — and which are not?
2. Where does a concept sit while it waits for licensor approval, and who is
   allowed to move it forward in the meantime? Compare what the flowchart
   shows with what the responsibilities document and the business-process
   document say.
3. When the licensor comes back with changes, which roles re-do work and in
   what order? Follow the rework loop across the flowchart, the
   business-process document and the Licensing Sheet Automation workflow.
4. Between the buyer's interest and the first sample, who touches the product
   and in which system or file does each person record their step? Cite the
   SOPs where they describe it and the transcript where practice is discussed.
5. What does "approved" mean at each of the three approval points (buyer,
   licensor, internal art/tech approval)? Where do the documents disagree
   about what approval includes?
6. The packaging SOP describes creating and saving packaging files. How does
   that official path compare with the way packaging is actually handled as
   described in the business-process document and the meeting transcript?
7. What does the artwork-standards SOP require before art files are saved and
   shared, and where do the mockup SOP and the flowchart assume those
   standards were already met?
8. Which steps in the mockup-creation SOP are confirmed by anyone outside the
   design team, and which hand-offs does the business-process document show
   that the SOP never mentions?
9. The transcript shows people discussing how work really flows. Name two
   places where that discussion contradicts a written SOP or the flowchart,
   with sources for both sides.
10. Where do files actually live at each stage (concept art, tech pack,
    packaging, licensing sheet)? Compare the SOPs' file rules with the
    flowchart and the business-process document.
11. What is the Licensing Sheet Automation workflow supposed to automate, and
    which manual steps around it are described in the business-process
    document or the Licensed Team responsibilities that the automation does
    not cover?
12. When the licensing sheet is wrong or late, what breaks downstream? Trace
    the impact through the flowchart, the automation workflow document and the
    transcript.
13. Who is supposed to create, update and verify the licensing sheet at each
    stage? Compare the automation workflow with the responsibilities document
    and the business-process document.
14. For the same job (for example preparing a licensor submission), what does
    each source say the buyer, the creative designer, the technical designer
    and the licensing team each own? Where does ownership overlap or go
    unnamed?
15. When two departments disagree about a product detail, what is the
    documented escalation path, and what does the transcript show happening
    instead?
16. Which decisions require the director's approval (art, tech packs,
    samples, buyers), and which documents mention approvals that skip that
    level?
17. What does a retail buyer need from us at each stage (concept, sample, PO),
    and where do the internal documents show we prepare it later than the
    buyer-facing flow implies?
18. When does a factory first see the product, and what do they receive?
    Compare the business-process document, the packaging/artwork SOPs and the
    flowchart's factory lanes.
19. Which licensor requirements (style guides, approvals, submission numbers)
    appear in more than one source, and where do the sources describe them
    differently?
20. If licensing approval is late, which later stages (mockup, packaging,
    artwork standards, PO) show visible effects in the sources? Name the
    stage, the effect and the evidence for at least three stages.

---

## Self-audit (handoff-writer gate)

1. *Could a brand-new developer pick up and not skip a beat?* Yes — §1
   orients the app, §3 pins every artifact with GitHub URLs and eval_run ids,
   §6 gives ordered next steps with verification gates, Appendix A carries the
   owner questions in full.
2. *Could they continue as effectively as me right now?* Yes — §4 carries
   every dead end that cost time (task-gates stale base, PowerShell
   here-string/commit traps, the swap-runner resolve omission, the Teams
   identity chain), §5 carries the measured root causes (Haiku thinking
   tokens, the fixture-vs-real question instrument, communities resume
   mechanics, the keys answer).
3. *Every relevant detail included?* Background (§1-2), outcome (§3),
   failures (§4), findings (§5), actions (§6), constraints (§7), access (§8),
   risks (§9), sub-agent outcome (part b), owner decisions (§0 + Appendix A).
4. *Does §0 hold every owner decision and no technical approval?* Yes — the
   sweep found: 20 questions (open), map review (open), colleague "hi"
   (open), plus the settled tenant ruling, Teams proof, corpus direction,
   cap, leak history, model split, advisory reviews. No technical approval
   appears in §0; the swap rerun, seating and build-out are §6 work items.
