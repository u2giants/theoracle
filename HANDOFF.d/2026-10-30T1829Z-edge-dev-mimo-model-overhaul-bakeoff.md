---
issue: 255
status: OPEN
owner: mimo/model-overhaul-2026-10-30 (edge-dev, session ses_ffe5e72d1f0cbffeX3dv5QYOOh)
---

# Company Map model overhaul: eval provenance, dedupe fix, job brief, leak repair — baton

Written 2026-10-30, 2:30 PM EDT (1829Z), edge-dev, MiMo. Program: parent
https://github.com/u2giants/theoracle/issues/240 ; step-14 issue
https://github.com/u2giants/theoracle/issues/255 ; model-split issue
https://github.com/u2giants/theoracle/issues/294 (CLOSED — its code landed in
PR #295). Spec: https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md
(read STATUS first). Predecessor batons: the step-14/model-split baton
https://github.com/u2giants/theoracle/blob/docs/handoff-step14-modelsplit/HANDOFF.d/2026-10-30T1442Z-edge-dev3-claude-step14-model-split.md
(PR #296, still open at this writing) and the step-9 baton
https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-29T2340Z-edge-dev-mimo-company-map-step9-paused.md
(keep it until step 14 closes — it holds the reviewer dispatch recipe).

## 0. ⚠️ Business decisions only the owner can make

Put ALL of these to Albert in ONE message before starting work.

Blocking step-14 acceptance:
1. **Albert and Ilona write the 20 evaluation questions** on the Map's eval page
   (each question must need three or more sources). Until then the real-corpus
   eval can only run the five seed questions. Recommendation: this week.
2. **Albert messages the Teams bot from his own account** ("hi") after the
   hosted Map is confirmed — the step-12 manual proof carried into step 14.
   Interviews to real employees stay OFF (`BRAIN_INTERVIEW_ENABLED=false`).
3. **Albert and Ilona spend 30 minutes marking wrong items on the first Map**
   (plan step 14 item 8); record their verbatim verdict in the plan STATUS row.
4. **The remaining corpus.** Only 8 new Oracle-1 files are ingested (26 bucket
   objects: 8 new, 18 duplicates of already-ingested files). The "hundreds of
   documents, diagrams and transcripts" are not uploaded yet. Recommendation:
   Albert drops them on the Map → Sources upload page, or names a folder the AI
   can copy into the import volume.

A wrong guess is recoverable (spend):
5. **OpenRouter $25/day cap** (shared key). Recommendation: keep it — the
   cheaper heavy-work model (the bake-off below) should cut spend by roughly
   10x so the cap stops binding.
6. **The public-repo leak history question.** The Supabase project ref and two
   test-host LAN addresses sat in committed handoffs on the PUBLIC repo; the
   tree content is redacted (PR #300, merged), but git history still holds the
   old bytes. The ref is an identifier, not a credential — no keys leaked.
   Recommendation: accept the residual history exposure (a history rewrite is
   destructive and your call); no rotation is indicated.

Already settled — do NOT re-ask: model split with Haiku 5.5 as the only Claude
model for human conversation (Albert, 2026-10-30); reviews are advisory and
never block merges (owner ruling 2026-10-29); FalkorDB stays; no permission
system beyond login + `is_admin`; the plan's env-only model-id rule stands.

## 1. What this application is

The Oracle (https://github.com/u2giants/theoracle) is POP Creations'
evidence-backed company adviser. The current program is the Company Map: it
reads company documents, diagrams and employee transcripts and shows how work
actually flows — where hand-offs break — plus answers that cite many sources.
`apps/brain` is a Python FastAPI service + worker loop doing all AI and graph
work; Postgres (Supabase project `theoracle`, project ref redacted — see PR
#300; schema `cmap`) is the durable store; FalkorDB holds graph `company`.
`apps/web` is Next.js on Vercel (production https://oracle.designflow.app)
proxying `/api/brain/*` to the brain. The brain is hosted on Coolify (hetz
VPS) as compose app `oracle-brain` at https://oracle-brain.designflow.app
(`/health` → `{"ok":true,"db":true,"graph":true}`).

## 2. What we set out to do this session, and why

Albert (2026-10-30, his chat): finish step 14's real-corpus confirmation, fix
step-13's duplicate recommendations, move heavy work to a cheap non-Claude
picked with the step-11 eval with Claude Haiku 5.5 as the separate
conversation model — and then four numbered items: (1) make eval runs record
their models, (2) run a NEW model bake-off for every stage (the seated models
are several generations old), (3) reorganize the admin model page (better
layout, less white space, list the NEW Company Map stages) and deep-investigate
the code to write a new in-depth job brief in the same methodology as the old
"Copy job brief" texts, (4) answer which direct provider keys exist and
whether a Xiaomi MiMo API key can ride Albert's subscription. The app crashed
twice mid-session; this baton closes the session.

## 3. Current state — what is true right now

Landed on `main` (verified MERGED via gh):
- **PR #297** https://github.com/u2giants/theoracle/pull/297 — eval runs now
  record their models: `cmap.eval_run.models` jsonb (migration
  https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/004_eval_models.sql),
  manifest in
  https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/eval/run.py
  (`model_manifest`: resolved answer/grade models via the PR-295 split helpers
  plus chat/eval/frontier/vision/embed raw slots + `extraction_models` row
  counts), and `GET /eval/runs` returns it. Tests: `test_eval_fixture.py`
  (122 passed on edge-dev3 test services before merge).
- **PR #299** https://github.com/u2giants/theoracle/pull/299 — duplicate
  recommendations fix: `prompts/recommend.md` now receives a numbered list of
  already-recommended problems and answers `duplicate_of`; `recommend.py`
  drops model-flagged duplicates before the cosine ≥0.9 gate. Tests:
  `test_model_marked_duplicate_skipped`, `test_duplicate_index_accepts_only_valid_numbers`.
- **PR #300** https://github.com/u2giants/theoracle/pull/300 — public-repo
  leak redaction in the step-4/step-9 batons (Supabase refs →
  PRIVATE_REFERENCE_SHA256 placeholders, LAN/Tailscale IPs → host-alias
  wording). doc-safety passed on its head before merge.
- PR #295 (another session) already landed the model split: `BRAIN_CHAT_MODEL`
  (answers), `BRAIN_EVAL_MODEL` (grader), both falling back to
  `BRAIN_FRONTIER_MODEL`; helpers `chat_model()`/`eval_model()` in
  https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/config.py.

Open PRs at this writing:
- **PR #296** https://github.com/u2giants/theoracle/pull/296 — the step-14
  model-split baton (edge-dev3 session). Rebased onto redacted main and its
  own Supabase-ref redaction pushed. Awaiting `bin/ai-doc-safety` pass on its
  exact head, then prose merge (`gh pr merge --squash --admin`).
- **PR #298** https://github.com/u2giants/theoracle/pull/298 — the model-stage
  job brief (this session's main artifact):
  https://github.com/u2giants/theoracle/blob/docs/model-stage-job-brief/docs/company-map/model-stage-job-brief.md
  — nine stage role briefs in the old "Copy job brief" methodology (measured
  benchmarks + HOW TO EVALUATE), the bake-off protocol (grader frozen;
  fixture micro-evals first; $25/day budget rules; results table), and the
  model-page rework spec (§6 of that doc). Rebased onto redacted main;
  awaiting doc-safety, then prose merge.
- **PR #302** https://github.com/u2giants/theoracle/pull/302 — the model page
  rework (sub-agent, completed after this baton was drafted): nine Company Map
  stage cards (max-w-5xl 2-col grid, seat chips, Copy-job-brief buttons wired
  to the brief's §4 texts), legacy model routes collapsed below, pool-page
  layout fixes (shared sticky filter header, overflow wrapper, compact
  Copy-from menu), and a new `require_service`-guarded `GET /models` brain
  endpoint (env-only, split-aware). Verified: brain suite 128 passed, ruff
  clean, `pnpm -w typecheck` and `lint` clean, Playwright screenshots of
  `/admin/settings` and `/admin/settings/model-pool` visually reviewed via the
  fake-auth harness. Opened, NOT merged at baton close — merge it per the code
  lane when its CI is green.

Not started / not done:
- **Prod migration 004 is NOT applied** (see dead end 1 — the task-gates class
  escalation forbids `database` this session). It must run
  (`python -m brain.migrate`) before any eval run on a deployed build.
- **Step-14 real-corpus run is IN PROGRESS, not finished.** Brain live and
  healthy; 8 sources / 97 chunks / 289 extractions / 2045 mentions / 977
  entities / 862 relations; resolve + project done; the `communities` job has
  been RUNNING since 2026-10-30 07:12 UTC (371 L0 communities and counting,
  ~2-4 min per report, zero failed jobs; no L1/L2 or company report yet);
  `recommend` chains after it. Eval questions: 0. Eval runs: 0.
- `docs/verification/company-map/first-run.md`, plan STATUS row 14, the Teams
  self-test, the owner review: all pending (they need §0 items).
- The bake-off runs themselves (the brief is the playbook; no winner seated).
- Haiku 5.5 is NOT seated as the conversation model (its empty-content bug,
  dead end 4, must be fixed first).

## 4. Everything we tried that did NOT work

1. **ai-task-gates class escalation trap (cost: the prod migration).** The
   gate's recorded base (`24c3ce77f63d`) predates the merged hosting PRs, so
   every `check` observes `.github/workflows/*`, `apps/brain/Dockerfile`,
   `apps/web/package.json` as "my" change set and escalates to the protected
   `deployment` class — where `check --before database` is FORBIDDEN with no
   acknowledge path. Redeclaring `--class code` re-escalates the same way
   ("take these files out of the change set" is impossible — they are main's).
   Do not waste time re-declaring; the migration goes through whatever path
   the policy owners open, or a later session with a clean base runs it.
2. **`ai-doc-safety` is slow and easy to lose.** It takes ~15-25 minutes in
   git-bash (fork-heavy `git ls-files` loop + per-hit greps); a detached
   `Start-Process` with a complex `-lc` one-liner dies silently with empty
   logs. What works: write a small wrapper `.sh` (export PATH with a Python
   dir so the version-span filter runs), launch it detached with
   `Start-Process bash <wrapper.sh>`, poll the log file. The two invariants:
   public-boundary + local markdown links; the allowlist is
   `tools/public-boundary-allowlist.txt` INSIDE THE REPO BEING CHECKED.
3. **Stale `origin/main` after the crash hid PR #295.** This session spent a
   while treating the model split as unbuilt work; `git fetch origin main`
   first would have shown `1b4f350e` already merged it. Always fetch before
   judging another session's state.
4. **Haiku 5.5 empty content (from the step-14 baton, re-confirmed as open).**
   `anthropic/claude-haiku-5.5` as `BRAIN_CHAT_MODEL` returned empty message
   content on 2 of 5 eval answers (3 retries each). It must be fixed (likely
   reasoning-vs-max_tokens or a content-shape issue) before it seats as the
   conversation model. Cheap candidates `deepseek/deepseek-v4.1-flash` and
   `qwen/qwen3.8-flash` crash the relations stage with "frontier relations
   message content is not text" — reasoning tiers spend `max_tokens` on
   thinking and return empty content in JSON mode; the two eval scores that
   came from those runs (0.47 / 0.40) were computed on an empty graph and are
   INVALID. Avoid reasoning-flagged tiers for the JSON stages.
5. **PowerShell will not run extensionless bash scripts in a pipeline**
   ("Cannot run a document in the middle of a pipeline"). Invoke via
   `& "C:\Program Files\Git\bin\bash.exe" -lc <script-file>` or a wrapper file.
   `bash` alone resolves to WSL (no distro installed) — always use Git's bash.
6. **Supabase direct-URL DNS failure from edge-dev.** The `password` field of
   the prod-connection item (direct URL) resolves IPv6-only and psycopg fails
   ("getaddrinfo failed"); the `oracle_session_pooler` field works.
7. **Recommend test parser brittleness (fixed in #299).** `test_no_numbers_...`
   split the prompt on the first `<<<` block; adding the EXISTING PROBLEMS DATA
   block broke it. The parser now splits on the `DATA:\n<<<\n` marker.

## 5. Root causes and key findings

- **Why step 13 duplicated recommendations (root cause, measured):** each
  qualifying finding was recommended in isolation; the 5 resulting problem
  statements were paraphrases of one licensing stall but scored below the
  plan's 0.9 cosine gate (recorded in
  https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/step13-recommendations.md).
  The fix is causal, not a threshold tweak: the generation prompt now sees the
  problems already written and flags `duplicate_of`. Keep the cosine gate as
  the safety net.
- **Public-boundary rules (learned the hard way):** the checker flags (a) any
  exactly-20-lowercase-letter word (Supabase project refs are exactly 20
  letters — `modelcontextprotocol` survives only via the repo allowlist),
  (b) RFC1918 + Tailscale-range IPs (100.64/10), (c) `https?://<bare-IP>`
  authorities, (d) credential-shaped strings. Dependency versions that LOOK
  like private IPs (e.g. the nvidia-curand version string) are filtered by
  `tools/public-boundary-version-spans.py` but ONLY when Python is on the bash
  PATH — and a bare quoted version in prose is NOT a proven version span, so
  never quote one literally in a doc. The repo under check carries its own
  `tools/public-boundary-allowlist.txt` for the exactly-20-letter words.
- **eval provenance is now the bake-off's audit trail:** `cmap.eval_run.models`
  records the resolved answer/grade models (post-#295 split) + raw slots +
  per-model extraction row counts. The bake-off results table in the job brief
  accepts only numbers backed by an eval_run id (PR #297's commit message and
  the brief §5 say so).
- **Model seats live in Coolify env (plan §11 "env only"):** verified live
  2026-10-30 — `BRAIN_FRONTIER_MODEL=anthropic/claude-sonnet-4.5`,
  `BRAIN_VISION_MODEL=openai/gpt-4.1`,
  `BRAIN_EMBED_MODEL=openai/text-embedding-3-large` (dims 1024),
  `BRAIN_SCALEDOWN_ENABLED=true`, `BRAIN_MAX_FRONTIER_CALLS_PER_JOB=3000`,
  `BRAIN_IMAGE_TAG` pinned to a main SHA (so merges do NOT auto-deploy).
  `BRAIN_CHAT_MODEL`/`BRAIN_EVAL_MODEL` are unset in prod (both fall back to
  the frontier model). The job brief §6 specs a `GET /models` brain endpoint
  for the page to display these; it must NOT introduce a second config store.
- **Communities reporting is the cost center and the step-14 bottleneck** —
  one frontier call per Leiden community with 12k-token contexts, ~2-4 min
  each serial-ish (6 workers); the real-corpus run has been on it for hours.
- **The old admin model page** (settings cards + model-pool checkbox grid) is
  legacy-app machinery (`default_*_route` settings + `model_capabilities`
  catalog); the page rework must keep it working in a collapsed section while
  the new stage cards go primary (spec: job brief §6).
- **Keys inventory (answer to Albert's question 4):** the brain uses ONE
  OpenRouter key (1Password `vibe_coding` item `62ieeyycs4ierflalbbbt5pq5i`,
  $25/day cap) for every model, plus ScaleDown (`epna47xmzcnbdc6eb3tjpx6phm`)
  and the shared token (`4lm6bpl7bc25lqne4meumwcd2a`). Direct provider keys
  exist and are unused by the brain: OpenAI, Google/Gemini, DeepSeek, Qwen
  (Alibaba), GLM (z.ai), StepFun, Meta Muse — see the vault items titled
  "openai API key for designflow", "ai provider api keys openai deepseek
  chatgpt qwen", "Google AI (Gemini) API Key...", "deepseek API key for
  reviewer only", "qwen coder alibaba token plan api key", "GLM z.ai API",
  "stepfun step5 ai api key". The old (frozen) app uses several of them via
  its own adapters. A "Xiaomi MiMo API key riding the subscription" is
  MiMoCode's capability API (`mimo llm-server issue` mints scoped OpenAI-
  compatible tokens over the instance's configured models) — but it is
  loopback-only per session, dies with the process, serves chat only (no
  /embeddings), and REFUSES `response_format`, which the brain's JSON mode
  requires; it is not a drop-in OpenRouter replacement for the hosted brain.

## 6. Exact next steps

1. **Finish the doc merges.** Poll `doc-safety-296b.log` / `doc-safety-298b.log`
   (wrapper scripts on edge-dev machine temp; if gone, rerun
   `ai-doc-safety` per dead end 2 on the PR head worktrees). When a log ends
   `EXIT=0`, merge that PR with `gh pr merge <n> --squash --admin` (prose
   lane). You'll know it worked when `gh pr view <n> --json state` says
   MERGED and the step-14 baton + job brief are on `main`.
2. **Merge PR #302** (model page rework) once its CI is green —
   `gh pr view 302 --json state` then the code lane. Its verification is
   already green locally (128 brain tests, typecheck, lint, Playwright
   screenshots). You'll know it worked when `/admin/settings` shows the nine
   Company Map stage cards (max-w-5xl grid) with Copy-job-brief buttons and
   the legacy section collapsed.
3. **Apply migration 004 to prod** before any eval run: `python -m
   brain.migrate` against the prod Supabase (see §8 for the connection item).
   Blocked for the previous session by the gate (dead end 1) — if the gate
   still forbids `database`, report `Blocked —` and leave the PR comment
   https://github.com/u2giants/theoracle/pull/297#issuecomment-6529702219 as
   the standing warning. You'll know it worked when
   `information_schema.columns` shows `cmap.eval_run.models`.
4. **Fix Haiku 5.5 empty content** in the answer path (dead end 4), then set
   `BRAIN_CHAT_MODEL=anthropic/claude-haiku-5.5` in the Coolify env. Gate:
   5/5 seed-eval answers return non-empty content.
5. **Run the bake-off** per the job brief §5: pull the live OpenRouter catalog
   (never a stale list), fixture micro-evals first (the brief's per-stage
   recipes), then stage swaps measured by the step-11 eval with the GRADER
   FROZEN. Watch the $25/day cap; heavy smokes right after the midnight-UTC
   reset. Fill the brief's results table with eval_run ids. Avoid
   reasoning-flagged tiers for the JSON stages (dead end 4).
6. **When the `communities` job finishes**, let `recommend` run (it chains),
   then run the eval on the seed questions (the 20 owner questions need §0),
   and write `docs/verification/company-map/first-run.md` with counts, eval
   mean, and the owner verdict. Then the plan STATUS row 14 and the step-14
   issue checkboxes (the landing checklist is in the step-14 baton).
7. **Put §0 to Albert in ONE message** before any of the above touches his
   workflow.

## 7. Constraints and gotchas in force

- Never push to protected `main`; branch + PR; reviews are advisory and never
  gate a merge (owner ruling 2026-10-29). Sign GitHub posts with
  `Posted by MiMo chat <id> on <machine>`.
- Model ids: env only (plan §11). Never hard-code them.
- All source text to models inside a delimited DATA block
  (`tests/test_prompts.py::test_source_text_is_data` guards it).
- The pytest suite TRUNCATEs `cmap.*` on the shared test DB — never run it
  mid-smoke (the step-9 baton §4 has the incident).
- Test services on edge-dev3 (Postgres 16 + pgvector + FalkorDB) are SHARED
  with candidate evals — never run pytest and a candidate eval at the same
  time (one FalkorDB graph name).
- HANDOFF.d discipline: do not edit another session's file (the PR-300
  redactions were a privacy-precedence exception, minimal spans only);
  delete a predecessor's file only under the successor rule (all three
  conditions) — the step-9 baton stays until step 14 closes.
- The repo is PUBLIC. Anything in it is world-readable. Private-reference
  placeholders (`PRIVATE_REFERENCE_SHA256_<sha256 of the value>`) are the
  convention; machine addresses stay in the machine atlas.

## 8. Access and environment

- Machine: edge-dev (Windows coordinator). No Docker here — brain tests run
  against services on edge-dev3 over the LAN (Postgres 16 + pgvector,
  `brain_test` db, port 56789; FalkorDB port 56791; user oracle/oracle).
  Connection strings are in the step-9 baton §"Test services" (IPs redacted
  in docs; the machine atlas or `ipconfig`/SSH config on edge-dev resolves
  them).
- `gh` is authenticated as `u2giants` (HTTPS). Commit identity:
  `Albert Hazan <u2giants@users.noreply.github.com>` (verified this session).
- SSH to github.com works (the `id_ed25519` key); transient
  "Permission denied (publickey)" is GitHub throttling — retry after a pause.
- 1Password MCP (`op_run`, vault `vibe_coding`): OpenRouter
  `62ieeyycs4ierflalbbbt5pq5i`/`OPENROUTER_API_KEY` ($25/day); ScaleDown
  `epna47xmzcnbdc6eb3tjpx6phm`/`SCALEDOWN_API_KEY`; shared token
  `4lm6bpl7bc25lqne4meumwcd2a`/`BRAIN_SHARED_TOKEN`; Supabase prod
  connections `qcuyabwseaptvuzvtjejffi2ou` (field `password` = direct URL —
  IPv6-only from this host; field `oracle_session_pooler` = the one that
  works); Coolify read/write `u3aqw63jqnkmnziip3gp5hwb5m`/`credential` (API
  base `http://<hetz tailnet ip>:8000/api/v1` — tailnet path, never the
  public IP for tokens); Anthropic reviewer key
  `5uq6z66ibusmypkvnl276ta22e`/`credential`. Values move only via `op://`
  refs in `op_run` env — never chat, argv, or commits.
- Coolify app `oracle-brain` (uuid `uge6pfm4qapktivto4981mtg`), status
  running:healthy, health URL https://oracle-brain.designflow.app/health .
  Model seats are its env vars (§5).
- Brain API auth: `x-brain-token` (BRAIN_SHARED_TOKEN) + `x-user-id`
  (Supabase auth user) for user endpoints; `require_service` for
  server-to-server. `GET /health` is open.
- Python: uv venv per worktree (`uv sync`, `uv run pytest`, `uv run ruff
  check .`); MIMO_PYTHON is available for standalone scripts.

## 9. Open questions and risks

- Whether ANY cheap non-Claude candidate can hold relations recall (the JSON
  stages choke on reasoning tiers — dead end 4). The bake-off answers this;
  do not seat on price alone (the old extraction brief's measured 10x recall
  spread is the cautionary tale).
- Community-reports slot: heavy AND human-read. The brief says the step-11
  eval decides between the cheap seat and the conversation seat; Albert reads
  these summaries, so a quality drop there is business-visible.
- The step-14 baton (PR #296) and this one both assume the `communities` job
  finishes cleanly; a crash restarts reports (stored-report reuse keyed by
  level+entity set limits the damage — step-9 baton).
- Git history of this public repo retains the redacted identifiers (§0 item
  6).
- The `ai-shared-db-closeout-check` receipt this session: zero blocking
  claims and zero blocking stages, but `ok:false` because its GitHub request
  timed out (the tool's own network blip). No popcre/shared-db object was
  ever claimed by this session; a successor may re-run the checker for a
  clean receipt.

---

## Part (b) — sub-agent blocks (this session dispatched sub-agents)

**explore-1 — brain stage model-call inventory (finished, read-only).** Asked
for an evidence-based inventory of every AI call site in `apps/brain`. Delivered
a complete per-stage report (call sites with file:line, input/output contracts,
volumes, JSON-mode/max_tokens facts, prompt list, recorded-fixture mechanism)
that became §3/§4 of the job brief (PR #298). Notable finds: no RECORD=1
re-record harness exists in this repo (fixtures are checked-in JSON), interview
makes no model calls, and the exact per-stage max_tokens/JSON-mode matrix.
No files touched.

**explore-2 — admin model page layout inventory (finished, read-only).** Asked
for the current model-UI structure. Delivered the settings-card grammar
(`max-w-2xl` cards leaving half the screen empty), the model-pool 23-column
sparse grid (2 files, 762/716 lines), the full legacy stage list with settings
keys, and the Tailwind/shadcn conventions. That report shaped the job brief §6
page spec. No files touched.

**general-1 — model page rework implementation (COMPLETED).** Asked to
implement the job brief §6 spec on branch `web/model-page-new-stages`: new
`GET /models` brain endpoint, nine stage cards with clipboard job briefs,
collapsed legacy section, pool-page layout fixes; verify with brain tests +
typecheck + lint; open a PR, do not merge. After one app crash and a resume it
delivered PR https://github.com/u2giants/theoracle/pull/302 (8 files) with
128 brain tests passing, ruff/typecheck/lint clean, and Playwright screenshots
of both pages visually reviewed via the fake-auth harness. Notes it flagged:
`BRAIN_CHAT_MODEL`/`BRAIN_EVAL_MODEL` were unset in its screenshot run
(fallback shown); pool catalog refresh was partial (Google parse error; 85
models displayed); the brief §6 header link was omitted because the brief was
not on `main` at its build time (it is now — a successor may add the link).
Findings worth keeping: the map e2e harness
(`apps/web/tests/map/fake-supabase-auth.mjs` + `map_seed.py` +
`playwright.map.config.ts`) bootstraps any authenticated admin UI screenshot
without production credentials, but the target DB needs `packages/db`
migrations plus an `auth.uid()` stub applied manually (the
`prepare-fresh-supabase-test-db.ts` script refuses non-loopback hosts by
design), and `map_seed.py`'s `employee_identities` INSERT omits
`auth_provider` (NOT NULL on the web schema) — set a column default on the
throwaway DB rather than editing the seed. Its worktree
(`theoracle-model-page`, edge-dev machine temp) is machine-local; the PR is
the artifact.

---

## Self-audit (handoff-writer gate)

1. *Could a brand-new developer pick up and not skip a beat?* Yes — §1 orients
   the app, §3 pins every artifact with GitHub URLs, §6 gives ordered next
   steps with verification gates, §8 hands over access without values.
2. *Could they continue as effectively as me right now?* Yes — §4 carries the
   gate/tooling dead ends that cost this session hours (task-gates escalation,
   doc-safety mechanics, stale-main trap), §5 carries the measured root causes
   (duplicate mechanism, boundary-checker rules, env-seat facts, key
   inventory incl. the MiMo answer).
3. *Every relevant detail included?* Background (§1-2), outcome (§3), failures
   (§4), findings (§5), actions (§6), constraints (§7), access (§8), risks
   (§9), sub-agent outcomes (part b), owner decisions (§0).
4. *Does §0 hold every owner decision and no technical approval?* Yes — the
   six business items (20 questions, Teams proof, map review, corpus upload,
   cap, leak history) are all owner-meaning; the technical items (migration
   gate, Haiku bug, bake-off execution) are §6/`Blocked —` items, not asks.

