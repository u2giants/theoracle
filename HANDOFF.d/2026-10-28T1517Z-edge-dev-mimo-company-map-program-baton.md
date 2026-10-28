---
issue: 240
status: OPEN
owner: mimo/company-map-program-baton
---

# Handoff — Company Map program: Steps 0–1 done and accepted; next is Step 2 (source intake)

Written 2026-10-28, 11:30 AM EST, edge-dev, MiMo. This file is the **program baton** for the Company Map work (parent issue #240). It replaces `HANDOFF.d/2026-10-28T0250Z-edge-dev3-claude-company-map-plan.md`, retired in the same commit under the successor rule (see §9).

## 0. ⚠️ Business decisions only the owner can make

- **None — nothing in this workstream needs a business decision from Albert right now.** The Step 1 review already happened (2026-10-28, `VERDICT: APPROVE`, PR #261 merged) and no new question arose.
- Next owner action is ordinary usage, not a decision: open a fresh session for **Step 2** whenever ready (the copy-paste prompt is in the wrap-up report / can be rebuilt from §6). Recommendation: start it after reading §6 once — nothing is blocked.
- **Already settled — do NOT re-ask (owner rulings 2026-10-27/28, recorded in the plan):** the program builds the big picture from noisy data (no atomic-claim evaluation); no permission system beyond login + `is_admin`; FalkorDB stays; corpus is hundreds of documents/diagrams and tens of thousands of transcript lines plus interviews; human grading "within reason"; treat this as brand new (no comparison with the old Oracle); supervision is **Claude Opus or Fable only** for reviews (GPT/GLM never review), implementer opens the PR and never merges it, Albert pastes the child issue's review prompt into a fresh Opus/Fable session. Full text: the plan's STATUS area — https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md

## 1. What this application is

POP Creations / Spruce Line (high-volume home decor company, owner Albert Hazan) is building "The Oracle" — an evidence-backed company adviser. The current program is the **Company Map**: read hundreds of procedure documents, flowcharts/diagrams and tens of thousands of lines of employee transcripts, then show how work actually flows across departments, where hand-offs break, and answer questions citing many sources at once.

- Repository: `u2giants/theoracle` on GitHub, default branch `main` (pnpm + turbo monorepo).
- Durable program spec: https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md — **always read its STATUS table first**; do not re-derive or re-plan. "Fresh session starts at: the first row marked ⬜ open, in order."
- Program tracking: parent issue https://github.com/u2giants/theoracle/issues/240 with children #241–#255 (one per step 0–14). #241 and #242 are closed (done); #243–#255 open.
- New component: `apps/brain/` — one Python 3.12 service (FastAPI + worker loop) owning all reading, extraction, graph and answering logic. `apps/web/` (Next.js) keeps login and renders, proxying to `apps/brain`. Supabase Postgres is the durable store (new tables in schema `cmap`); FalkorDB is the graph from step 7 on.

## 2. What we set out to do this session, and why

Albert asked (2026-10-28): pull the latest repo, read issue #240, and complete **Step 1** (issue #242) — the `cmap` Postgres schema, the `python -m brain.migrate` runner, and the step's named tests. It is the program's data foundation: nothing later can store anything without it. Step 1 is now **implemented, verified, reviewed and merged** (see §3).

## 3. Current state — what is true right now

**Done and accepted (verified):**

- **Step 0** (issue #241, PR #260): old program frozen, `apps/brain` skeleton, CI workflow. Plan STATUS `✅ done` 2026-10-28 10:15 EDT.
- **Step 1** (issue #242, PR #261): `apps/brain/brain/sql/001_cmap.sql` (15 tables + 3 indexes, all `IF NOT EXISTS`, verbatim from the plan), `apps/brain/brain/migrate.py` (`python -m brain.migrate`), `apps/brain/tests/test_schema.py` (`test_migrate_runs_twice_without_error`, `test_all_tables_exist`). Merged to `main` 2026-10-28 11:10 AM EST.
  - Independent review (Claude Opus 5.5 session): `VERDICT: APPROVE` on #242 — scope exact, gate rerun green on its own fresh pgvector container, no Part 1 / §8 violations, no later-step problems, no model names/secrets/approval scaffolding. https://github.com/u2giants/theoracle/issues/242#issuecomment-6472574847
  - Verification artifacts: CI `brain tests` green (3 passed) https://github.com/u2giants/theoracle/actions/runs/40711354399 ; same suite green locally on a fresh `pgvector/pgvector:pg16`; `python -m brain.migrate` ran twice cleanly both places.
  - **Production Supabase already has the schema** — project `theoracle` (ref `eqccjfbyrywsqkxxpjvg`, us-east-1, PG 17.6): 15 tables present, `pgvector` 0.8.0, applied idempotently twice after target identity was proven. Row-level data: none written; DDL only.
  - Plan STATUS row for Step 1: `✅ done` with evidence, updated by the review session (commit `e4a1d707`). Issue #242 checkboxes ticked; issue closed 2026-10-28 by this session after merge.
- **Next up: Step 2 — source intake** (issue #243): `POST /sources` upload, bulk folder import, transcript import (VTT / Teams JSON / Recall.ai JSON / "Speaker: text"), diagram import, `brain/read/detect.py` kind detection. See the plan's Step 2 text.

**Not started:** steps 3–14 (reading/chunking, ScaleDown extraction, relations, entity resolution, FalkorDB projection, communities, QA, the map page, evaluation, interviews, recommendations, hosting/first real run).

**Nothing of this program is deployed to Coolify/Vercel yet** (step 14 does hosting). `apps/brain` runs from source and in CI only.

**Known red checks that are NOT ours:** `Oracle offline suites` / `oracle2-offline` fail on `main` itself in `dev/oracle2/test_ci_trust_boundary.py::test_no_private_runner_before_trust_proof` (KeyError `'uses'`). Ignore on this program's PRs — step gates are `brain tests` / each step's named pytest. Recorded in `docs/agents/15-pending-work.md`.

## 4. Everything we tried that did NOT work (dead ends — do not repeat)

1. **Almost wrote a multi-statement SQL splitter for `run_sql`.** Assumed psycopg 3 `Cursor.execute()` rejects files with several statements (psycopg2 lore: "cannot insert multiple commands into a prepared statement"). Wrong here: with **no parameters**, psycopg 3.3.6 falls back to the simple query protocol (`_pgconn.send_query` in `psycopg/_cursor_base.py`, the "if we can, let's use simple query protocol" branch), which runs the whole file. `brain/db.py::run_sql` needed **no change**. Don't add a splitter.
2. **No pgvector on the edge-dev Windows box.** Local scoop PostgreSQL 18.6 lacks `CREATE EXTENSION vector`; no Docker engine there (CLI only, no Docker Desktop), WSL has no distro, scoop has no pgvector, no MSVC to build one. **What worked:** SSH to the Linux dev box `edge-dev3` (address in the private machine atlas — `ai-private-config`; it has Docker 29.x). From Windows use Git's `ssh.exe` (Windows OpenSSH through tool calls breaks with ConPTY 255). Start `pgvector/pgvector:pg16` there (`docker run -d --name brain-step1-pg -e POSTGRES_USER=oracle -e POSTGRES_PASSWORD=oracle -e POSTGRES_DB=brain_test -p 56789:5432 pgvector/pgvector:pg16`), then run tests from Windows with `DATABASE_URL` pointing at that container's host port. Container removed after use. (Pick another host port if the chosen one is already taken.)
3. **`ai-task-gates check --before database` refused twice before passing.**
   - First: the recorded base was stale (commit `9308cd89` from 2026-10-19, 255 commits back) so the change set ballooned to 932 files including workflows and Dockerfile → observed class `deployment`, refusal. Fix: `ai-task-gates start --class <c> --base <branch-point>` — a stale base is a declaration error, not a gate to route around.
   - Second: the central policy maps `**/*.sql` → class `shared-db` (protected), and class `code` forbids `database`. Fix per the tool's own message: redeclare `--class shared-db`. Details and the standing procedure: `docs/agents/11-intentional-quirks.md` ("Any `*.sql` change classifies as `shared-db` in ai-task-gates").
4. **Direct-host Supabase connection from Windows is unreliable** — the 1Password item's notes and `docs/agents/11-intentional-quirks.md` already say the prod DIRECT host is IPv6-only from local Windows; use the item's `oracle_session_pooler` field for migrations. That is what worked.

## 5. Root causes and key findings

- **Task-gates classification (took real time).** Central `ai-devops/config/task-gates.json` maps `**/*.sql` / `**/migrations/**` → `shared-db`; repo-local `.ai-devops/task-gates.json` maps only the canonical Drizzle path (`packages/db/**`) to `shared-db` and maps `.github/workflows/**`, `vercel.json`, `package.json`, `apps/*/package.json`, `apps/workers/trigger.config.ts` → `deployment`. Strongest class per path wins. Any new `cmap` SQL file ⇒ class `shared-db` ⇒ `database` writes allowed only under `shared-db`/`production` classes, with gates listed as "not checked by this tool" honored in substance (tests, target-identity proof before every write, branch+PR). Canonical write-up: https://github.com/u2giants/theoracle/blob/main/docs/agents/11-intentional-quirks.md
- **The old oracle2 CI trust test is broken on `main`** — `test_ci_trust_boundary.py` expects `oracle2-contracts.yml` job `oracle2-offline` step 1 to be `actions/checkout@v4`, but two `run:` steps precede the checkout. Red since before this program (run 40703858027 on `main`). Plan §10: leave `oracle2-contracts.yml` alone until the old code is deleted.
- **Supabase production project for this app:** `theoracle`, ref `eqccjfbyrywsqkxxpjvg` (PG 17.6, pgvector 0.8.0). Connection strings in 1Password vault `vibe_coding`, item "Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, …)", field `oracle_session_pooler` for migrations from Windows. Never print values — use the 1Password MCP `op_run` runner with `op://` refs in env.
- **psycopg 3 simple-query fallback** — a whole SQL file can go through one `cur.execute(sql)` (see §4.1).
- **GitHub sign-off:** `Posted by MiMo chat <id> on edge-dev` (`$MIMO_SESSION_ID` empty ⇒ `unknown`). Commits use `Albert Hazan <u2giants@users.noreply.github.com>` (already the machine's git identity).
- **Review mechanics worked exactly as ruled:** implementer PR (never self-merged) → `Ready for review` comment with artifacts on the child issue → Albert's relay into Opus/Fable → `VERDICT: APPROVE` + STATUS update + merge + checkboxes. Repeat unchanged for steps 2+.

## 6. Exact next steps

1. **Start Step 2** (issue https://github.com/u2giants/theoracle/issues/243 ) in a fresh implementer session (GLM 5.1 / Sol 6.1 class per the plan). First: read the plan's STATUS table and Part 1, then the Step 2 text (`brain/api/sources.py` upload/bulk/transcript endpoints, `brain/read/detect.py` kind detection, fixture documents under `apps/brain/tests/fixtures/`). You'll know it worked when the step's named tests pass, CI `brain tests` is green on the step's PR, and `Ready for review: PR #<n>` is posted on #243.
2. **Repeat the supervision loop** (§0's settled list): implementer opens the PR and stops; Albert pastes #243's review prompt into a fresh Opus/Fable session; that session verdicts and, on APPROVE, merges + ticks + updates STATUS. You'll know it worked when the plan STATUS row for Step 2 reads `✅ done`.
3. **Before Step 4** (not before — do not create early): create 1Password items `SCALEDOWN_API_KEY` (title "ScaleDown API Key - The Oracle") and `BRAIN_SHARED_TOKEN` ("Oracle Brain shared token", random 32 bytes) in vault `vibe_coding` (skill `secrets-to-1password`). Carried forward from the retired plan-landing handoff. Blocks Step 4's pipeline (§8 of the plan).
4. **If a future step adds SQL**, use `python -m brain.migrate` + `brain/sql/NNN_*.sql` (idempotent `IF NOT EXISTS`), and follow the task-gates procedure in `docs/agents/11-intentional-quirks.md` before any database write.
5. **Drift checkpoints:** after steps 3, 6, 9 and 11 the review prompt also asks for a drift note on parent #240 (plan §11).
6. **Retiring THIS file:** the session that finishes the next program step (Step 2) deletes it under the successor rule (verify PR merged + STATUS row `✅ done`, carry forward §6.3 and anything still open) and updates the plan's "Registered handoff" line in the same commit.

## 7. Constraints and gotchas in force

- **Supervision rule (Albert, 2026-10-28):** implementer opens the PR, does **not** merge, posts `Ready for review: PR #<n>` on the child issue with the verification artifact; only **Claude Opus or Fable** reviews (never GPT/GLM); on APPROVE that session merges, ticks the checkboxes, updates the plan STATUS row; on any of plan §11's six triggers the implementer stops and posts a question on the child issue rather than guessing.
- **Plan Part 1's three rules that must never be broken:** never gate reading/indexing on approval; never add per-fact approval queues; never add a permission system beyond login + `is_admin`. Goal beats step text on conflict — write the conflict into STATUS and stop.
- **Never hard-code model ids** (env only, plan §8). Secrets only in 1Password vault `vibe_coding` / hosting env — never git, logs or chat. `effective_date` unknown stays NULL.
- **Database writes:** `ai-task-gates check --before database` immediately before, with the correct `--base` and class and the exact target proven; see `docs/agents/11-intentional-quirks.md`. No reviewer APPROVE needed for a database write (owner ruling 2026-10-14), every other gate stands. `cmap` is the application's own database — the `popcre/shared-db` claim-first workflow does **not** apply (plan: Step 1 text).
- **Implementer sessions never edit the plan STATUS rows** — the reviewing session owns them on APPROVE.
- Branch per step: `brain/stepNN-<slug>` from `main`; one PR per step. Python 3.12 / uv / ruff / pytest; type hints everywhere; tests in `apps/brain/tests/`; fixtures invented-but-realistic (the plan names them).
- edge-dev (Windows) has no Docker engine, no psql, no local pgvector — use edge-dev3 containers (§4.2). Times to humans are EST/EDT.
- Handoff discipline: one write-once file per session in `HANDOFF.d/`; successor rule for deletions; never rewrite root `HANDOFF.md`; never edit another session's file (repo `AGENTS.md` §3a).

## 8. Access and environment

- **Machines:** edge-dev (Windows coordinator) and `edge-dev3` (Linux dev box with Docker 29.x; SSH alias `edge-dev3`, address in the private machine atlas — `ai-private-config`). On Windows use Git's `ssh.exe` for SSH.
- **GitHub:** `gh` authenticated as `u2giants`; repo `u2giants/theoracle`. Task gates: `ai-task-gates` (`start --class … --base …`, `check --before …`, `explain --json`) from the `ai-devops` toolkit.
- **Secrets:** 1Password MCP service account, vault `vibe_coding` — use `op_run` with `op://` references so values never enter chat. Supabase item "Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, …)"; OpenRouter key item `62ieeyycs4ierflalbbbt5pq5i` (needed from later steps); `SCALEDOWN_API_KEY` / `BRAIN_SHARED_TOKEN` to be created before Step 4 (§6.3).
- **Python:** uv venv in `apps/brain` (Python 3.12): `uv run pytest`, `uv run ruff check .`, `uv run python -m brain.migrate`.
- **Databases:** production Supabase `theoracle` (`eqccjfbyrywsqkxxpjvg`, PG 17.6, pgvector 0.8.0) — `cmap` schema applied (Step 1). CI test DB: `pgvector/pgvector:pg16` service in `.github/workflows/brain-ci.yml`.
- **Nothing deployed** to Coolify/Vercel for this program yet (step 14).

## 9. Open questions and risks

- **No open questions.** Nothing is blocked; the next step is ordinary implementation work (§6.1).
- **Task-gates `**/*.sql` → `shared-db`** will recur on every future `cmap` migration. Procedure documented (2026-10-28) in `docs/agents/11-intentional-quirks.md`. If `check --before database` ever demands artifacts that genuinely belong to `popcre/shared-db` (claim-first in that repo), that contradicts the plan's "shared-db rules do not apply" — stop and post the question on the current child issue (plan §11 trigger), do not guess.
- **The two red checks (`Oracle offline suites` / `oracle2-offline`) are pre-existing on `main`** (§5). They may make external gate bots (e.g. the `Entire Gates` PR check) look red even when a step's own gate is green — the reviewing session owns merge policy; do not "fix" the old suite inside this program (plan §10).
- **Future schema changes** to `cmap` are additive idempotent migrations (`brain/sql/002_*.sql`, `ALTER … IF NOT EXISTS`-style guards or `CREATE TABLE IF NOT EXISTS`), never destructive recreates — production already holds the Step 1 schema.
- **Successor-rule retirement done in the commit carrying this file:** `HANDOFF.d/2026-10-28T0250Z-edge-dev3-claude-company-map-plan.md` met all three conditions — (1) its status line: plan committed/pushed/merged via PRs #239/#257/#258, verified in `main` history; (2) its open obligations carried forward here (§6.3's two 1Password items; "start the plan" is done — steps 0–1 landed); (3) its decisions/dead-ends live in the plan's STATUS area and §7. Its own text said Step 0 would retire it; Step 0 did not, so this session did. Git history keeps the text. The plan's "Registered handoff" line was updated in the same commit.

---

## Self-audit (mandatory completeness gate, run before sending)

1. **Could a brand-new developer with no project knowledge pick up here and not skip a beat?** Yes — §1 defines the application and program entry points, §3 states exactly what is done/accepted/undeployed with URLs and artifacts, §6 gives numbered next actions each with a "you'll know it worked when" gate, §8 covers access end to end.
2. **As effectively as I can right now?** Yes — §4 records every dead end and its fix (psycopg, pgvector/edge-dev3, task-gates refusals), §5 the non-obvious findings with sources, §7 the binding constraints including supervision and STATUS-row ownership.
3. **Every relevant detail for flawless execution?** Yes — background/goals (§2), current state incl. deploy status (§3), failures (§4), decisions (§0 + §5 + §9 last bullet), constraints (§7), risks (§9), exact next actions + verification gates (§6), verification evidence (§3: CI run 40711354399, VERDICT comment, merge time). Secrets by vault/item only (§8).
4. **If Albert read only §0, would he see every business decision and no technical approval?** Yes — §0 states explicitly that no business decisions are pending and lists only settled rulings plus the ordinary next action; every technical item (oracle2 CI, task-gates, secrets creation, schema procedure) is routed to §4–§9 as technical. Sweep terms ("waiting on", "owner", "decide", "blocked") appear only in §0's settled list and in §6/§9 as process or technical notes — none requires Albert's judgement.
