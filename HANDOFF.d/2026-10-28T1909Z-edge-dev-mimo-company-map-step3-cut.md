---
issue: 240
status: OPEN
owner: mimo/company-map-step3-cut
---

# Handoff — Company Map program: Step 3 implemented and open for review; next is the review relay, then Step 4

Written 2026-10-28, 3:09 PM EDT, edge-dev, MiMo. This file is the **program baton** for the Company Map work (parent issue https://github.com/u2giants/theoracle/issues/240 ). It replaces `HANDOFF.d/2026-10-28T1517Z-edge-dev-mimo-company-map-program-baton.md`, retired in the same commit under the successor rule (conditions checked in §9).

## 0. ⚠️ Business decisions only the owner can make

- **None — nothing in this workstream needs a business decision from Albert right now.** Step 3 needs no new ruling; its only open interpretation points are listed for the reviewer in the PR body (technical, routed to the AI reviewer — not to Albert).
- The only owner action is the supervision relay, which is ordinary process and not a decision: paste issue #244's "Review prompt (copy everything in the box)" into a **fresh Claude Opus or Fable** session on this repository so it reviews PR #267. After it merges, open a fresh implementer session for Step 4. Recommendation: do the relay now — nothing else is blocking.
- **Already settled — do NOT re-ask (owner rulings 2026-10-27/28, recorded in the plan):** the program builds the big picture from noisy data (no atomic-claim evaluation); no permission system beyond login + `is_admin`; FalkorDB stays; corpus is hundreds of documents/diagrams and tens of thousands of transcript lines plus interviews; human grading "within reason"; treat this as brand new (no comparison with the old Oracle); supervision is **Claude Opus or Fable only** for reviews (GPT/GLM never review), implementer opens the PR and never merges it, Albert pastes the child issue's review prompt into a fresh Opus/Fable session. Full text: the plan's STATUS area — https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md

## 1. What this application is

POP Creations / Spruce Line (high-volume home decor company, owner Albert Hazan) is building "The Oracle" — an evidence-backed company adviser. The current program is the **Company Map**: read hundreds of procedure documents, flowcharts/diagrams and tens of thousands of lines of employee transcripts, then show how work actually flows across departments, where hand-offs break, and answer questions citing many sources at once.

- Repository: `u2giants/theoracle` on GitHub, default branch `main` (pnpm + turbo monorepo).
- Durable program spec: https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md — **always read its STATUS table first**; do not re-derive or re-plan. "Fresh session starts at: the first row marked ⬜ open, in order."
- Program tracking: parent https://github.com/u2giants/theoracle/issues/240 with children #241–#255 (one per step 0–14). #241/#242 closed; #243's review landed its STATUS row but the issue is still open; #244 is the live one; #245–#255 untouched.
- New component: `apps/brain/` — one Python 3.12 service (FastAPI + worker loop) owning all reading, extraction, graph and answering logic. `apps/web/` (Next.js) keeps login and renders, proxying to `apps/brain`. Supabase Postgres is the durable store (schema `cmap`); FalkorDB is the graph from step 7 on.

## 2. What we set out to do this session, and why

Albert asked (2026-10-28): read issue #240, and complete **Step 3** (issue https://github.com/u2giants/theoracle/issues/244 ) — reading (text extraction, page images), chunking and embeddings, so uploaded sources actually become indexed chunks. It is the pipeline every later step consumes: nothing can be classified, extracted, graphed or answered until sources are read. Step 3 is now **implemented and awaiting its Claude Opus/Fable review** (see §3).

## 3. Current state — what is true right now

**Done and accepted (verified):**

- **Step 0** (issue #241, PR #260): old program frozen, `apps/brain` skeleton, CI workflow. Plan STATUS `✅ done`.
- **Step 1** (issue #242, PR #261): `cmap` schema + `python -m brain.migrate` + tests. Merged 2026-10-28; reviewed `VERDICT: APPROVE` (comment https://github.com/u2giants/theoracle/issues/242#issuecomment-6472574847 ). Production Supabase already holds the schema.
- **Step 2** (issue #243, PR #264): source intake (upload, bucket/folder import, transcripts, kind detection, the five fixtures). Plan STATUS `✅ done` with CI + reviewer rerun evidence. Issue #243 is still open with one deferred checkbox — the page-level "five rows queued → read" walkthrough; this session covered that proof at the API/handler level (below) and the deployment-level walkthrough is step-14 work.

**Step 3 — implemented, pushed, NOT merged (by design):**

- Branch `brain/step03-reading`, PR **https://github.com/u2giants/theoracle/pull/267** (opened 2026-10-28, base `main`, head commit includes the implementation and this handoff).
- What landed (all under `apps/brain/`):
  - `brain/read/pdf.py` — pypdfium2 page text; pages under 200 characters of native text render to PNG at 150 dpi and go to the vision model (`brain/read/vision.py`, prompt `brain/prompts/read_visual.md`); chunk locator gains `visual: true`.
  - `brain/read/office.py` — the OOXML parser copied from `services/oracle-brain/oracle_brain/ingest/binary_documents.py` (same safety checks), emitting DOCX paragraph-range chunks, XLSX sheet row-range chunks (real sheet row numbers), PPTX per-slide chunks; PPTX pictures go through the vision reader.
  - `brain/read/image.py` — raster diagrams via vision; SVG text nodes read directly (no rasteriser bundled).
  - `brain/read/transcript.py` — VTT / Teams-style JSON / Recall.ai final JSON / plain `Speaker: text` lines normalised to `{speaker, t0, text}` turns; consecutive same-speaker turns merge into one chunk up to 400 tokens, longer turns split at sentence boundaries; locator `{"turn", "speaker", "t0"}`.
  - `brain/read/chunk.py` — `tiktoken` `cl100k_base`; 400-token windows with 60-token overlap, never crossing page/slide/sheet boundaries.
  - `brain/embed.py` — 64 texts per OpenRouter embeddings call; `cmap.chunk.embedding` written as `vector(1024)`; wrong dimensions refused.
  - `brain/read/pipeline.py` (registered in `brain/worker.py`) — job `read_source`: download → read → chunk → embed → `read_state='read'` → enqueue `classify_extract`; failures set `read_state='failed'` with the error; model usage logged to `cmap.job.payload.usage` (plan §11).
- Verification: **32 passed** locally (uv, Python 3.12) against Postgres 16 + pgvector on the step-2 test container; `ruff check` clean; workspace typecheck/lint clean (no TS files touched). Named gate tests all green: `test_pdf_yields_page_chunks`, `test_blank_pdf_page_uses_vision`, `test_image_flowchart_renders_edges`, `test_transcript_turn_chunks`, `test_five_fixtures_reach_read_state` (the deferred step-2 read proof: five fixtures through the page's endpoints → five `read` rows), plus per-format tests and `tests/test_embed.py`. Full list in the PR body.
- **Gate arithmetic the reviewer must see (PR "Interpretation notes" #1):** the step text's rule (one turn per chunk, merge consecutive same-speaker turns up to 400 tokens) applied to the step-2 fixture (300 single-line turns) yields **246** turn chunks, not the done-when's "~60" (which counted on multi-line turns). The rule was not redesigned; `test_transcript_turn_chunks` asserts 246 with the arithmetic in its docstring. The other two counts hold exactly (PDF = 3 page chunks; flowchart PNG = 1 chunk with `->` edges naming "Licensor" and "Jessica").

**Not started:** steps 4–14 (ScaleDown extraction, relations, entity resolution, FalkorDB projection, communities, QA, map page, evaluation, interviews, recommendations, hosting/first real run).

**Nothing of this program is deployed to Coolify/Vercel yet** (step 14 does hosting). `apps/brain` runs from source and in CI only.

**Known red checks that are NOT ours:** `Oracle offline suites` / `oracle2-offline` fail on `main` itself in `dev/oracle2/test_ci_trust_boundary.py::test_no_private_runner_before_trust_proof` (KeyError `'uses'`). Ignore on this program's PRs — step gates are `brain tests` / each step's named pytest. Recorded in `docs/agents/15-pending-work.md`.

## 4. Everything we tried that did NOT work (dead ends — do not repeat)

Carried forward from the retired baton (still true, still worth not repeating):

1. **A multi-statement SQL splitter for `run_sql` is unnecessary.** psycopg 3 with no parameters falls back to the simple query protocol and runs a whole SQL file in one `cur.execute(sql)`. Do not add a splitter.
2. **No pgvector on the edge-dev Windows box.** Local scoop PostgreSQL 18.6 lacks `CREATE EXTENSION vector`; no Docker engine there (CLI only), WSL has no distro, no MSVC to build one. **What works:** SSH to the Linux dev box `edge-dev3` (address in the private machine atlas — `ai-private-config`; Docker 29.x) using **Git's `ssh.exe`** (Windows OpenSSH through tool calls breaks with ConPTY 255), run a `pgvector/pgvector:pg16` container there, and point `DATABASE_URL` at its published port from Windows. The step-2 test container (`brain2-test-pg`, port 56789, user `oracle`/`oracle`, db `brain_test`) was still up when this session checked and was reused; start a fresh one if it is gone and pick another host port if taken.
3. **`ai-task-gates` classifies any `*.sql` under `**/migrations/**` or `**/*.sql` as `shared-db`.** A `cmap` migration file therefore needs `--class shared-db` before `check --before database`; class `code` is refused for database actions. Procedure: `docs/agents/11-intentional-quirks.md`. (No SQL in step 3 — this returns at the next migration.)
4. **Direct-host Supabase connection from Windows is unreliable** — use the 1Password item's `oracle_session_pooler` field for migrations.

New this session:

5. **The plan's done-when "~60 transcript turn chunks" cannot be produced by the plan's own chunking rule on the step-2 fixture.** 300 single-line turns → 246 same-speaker runs → 246 chunks. Forcing ~60 would require a chunker the step text does not describe. Do not "fix" the count by redesigning the chunker — it is flagged for the reviewer in PR #267 (interpretation note 1).
6. **PowerShell on edge-dev hides some env vars in tool shells** (`$env:ProgramFiles` came back empty) — use literal paths for Git's `ssh.exe` (`C:\Program Files\Git\usr\bin\ssh.exe`) and never build such paths by string-concatenating `$env:` variables (PowerShell parses `$env:ProgramFiles\Git` as one variable name).
7. **Test-expectation arithmetic should be measured, not guessed.** Four first-run test failures came from asserting assumed counts (docx paragraphs, xlsx rows, blank-page text length) instead of measured ones. Compute fixture counts with a one-off `uv run python` probe against the fixture files before writing assertions.

## 5. Root causes and key findings

- **Review mechanics (unchanged, proven again):** implementer PR (never self-merged) → `Ready for review: PR #<n>` comment with artifacts on the child issue → Albert relays into Opus/Fable → `VERDICT: APPROVE` + STATUS update + merge + checkboxes. Implementer sessions **never edit plan STATUS rows**.
- **Recorded model responses live in `apps/brain/tests/fixtures/recorded/`** and are replayed through the client's HTTP seam (`brain/read/vision.py::_post_chat`, `brain/embed.py::_post_embeddings`) so parsing stays under test. The step-3 recordings are **hand-authored to match the fixture images exactly** (the fixture PNG's real box/diamond/lane labels); they contain no model ids or secrets. Refreshing them against live OpenRouter (RECORD-style) is step-4 smoke-test work, not CI work.
- **Transcript chunks carry `Speaker: ` in their text** (e.g. `Ilona: Which approval do you mean?`) so later text-based steps see who spoke — the same reason the plan renders diagrams as `->` lines. The locator still carries `speaker`/`t0` separately. Rationale recorded in PR #267 interpretation note 2.
- **`prompts/read_visual.md`** keeps the plan's wording but fences the JSON output shape, because `tests/test_prompts.py::test_source_text_is_data` (guarding all prompts from step 3 on) requires a fenced block in every prompt file. PR note 3.
- **Task-gates classification** (central `ai-devops/config/task-gates.json` vs repo `.ai-devops/task-gates.json`): strongest class per path wins; `.github/workflows/**`, `vercel.json`, `apps/*/package.json` classify as `deployment`. Details: `docs/agents/11-intentional-quirks.md`.
- **Supabase production project for this app:** `theoracle` (PG 17.6, pgvector 0.8.0). Connection strings in 1Password vault `vibe_coding`, item "Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, …)", field `oracle_session_pooler` for migrations from Windows. Never print values — use the 1Password MCP `op_run` runner with `op://` refs in env.
- **GitHub sign-off:** `Posted by MiMo chat <id> on edge-dev` (`$MIMO_SESSION_ID` empty ⇒ `unknown`). Commits use `Albert Hazan <u2giants@users.noreply.github.com>` (verify with `git var GIT_COMMITTER_IDENT` before the first commit in a worktree).

## 6. Exact next steps

1. **Review relay for Step 3** (owner action, ordinary process): Albert pastes the "Review prompt (copy everything in the box)" box from https://github.com/u2giants/theoracle/issues/244 into a fresh **Claude Opus/Fable** session. That session reviews PR https://github.com/u2giants/theoracle/pull/267 , posts `VERDICT: APPROVE` or `VERDICT: FIX` on #244, and on APPROVE merges the PR, ticks the issue checkboxes and updates the plan STATUS row. The same prompt asks for the **drift note on #240** (this is a drift checkpoint: steps 3/6/9/11). You'll know it worked when the plan STATUS row for Step 3 reads `✅ done` and #244 is closed.
2. **If the verdict is FIX:** a fresh implementer session continues from the numbered fix list in the verdict comment (same branch `brain/step03-reading`), reruns the gate, and re-posts `Ready for review`. If a fix would touch a Locked §8 decision or redesign the step, stop and post the question on #244 instead (plan §11 triggers).
3. **Before Step 4** (not before — do not create early): create 1Password items in vault `vibe_coding` — `SCALEDOWN_API_KEY` (title "ScaleDown API Key - The Oracle") and `BRAIN_SHARED_TOKEN` ("Oracle Brain shared token", random 32 bytes), per skill `secrets-to-1password`. **Carried forward from the retired baton (§6.3) — this is the open obligation that file named.** Blocks Step 4's pipeline (plan §8).
4. **Start Step 4** (issue https://github.com/u2giants/theoracle/issues/245 ) in a fresh implementer session: passage classification + flat extraction via ScaleDown with a frontier fallback (`brain/extract/flat.py`, job `classify_extract`, recorded responses in `tests/fixtures/recorded/scaledown/`). Read the plan's Part 1 and the Step 4 text first. You'll know it worked when `tests/test_flat.py` is green, CI `brain tests` is green on the step's PR, and `Ready for review: PR #<n>` is posted on #245.
5. **If a future step adds SQL:** `python -m brain.migrate` + `brain/sql/NNN_*.sql` (idempotent, additive only — production already holds the Step 1 schema), with the task-gates `shared-db` procedure from §4.3 before any database write.
6. **Retiring THIS file:** the session that finishes the next program step deletes it under the successor rule (verify PR merged + STATUS row `✅ done`, carry forward §6.3 and anything still open) and updates the plan's "Registered handoff" line in the same commit.

## 7. Constraints and gotchas in force

- **Supervision rule (Albert, 2026-10-28):** implementer opens the PR, does **not** merge, posts `Ready for review: PR #<n>` on the child issue with the verification artifact; only **Claude Opus or Fable** reviews (never GPT/GLM); on APPROVE that session merges, ticks the checkboxes, updates the plan STATUS row; on any of plan §11's six triggers the implementer stops and posts a question on the child issue rather than guessing.
- **Plan Part 1's three rules that must never be broken:** never gate reading/indexing on approval; never add per-fact approval queues; never add a permission system beyond login + `is_admin`. Goal beats step text on conflict — write the conflict into STATUS and stop.
- **Never hard-code model ids** (env only, plan §8 — `BRAIN_FRONTIER_MODEL`, `BRAIN_VISION_MODEL`, `BRAIN_EMBED_MODEL`; start values are named in the plan, set them in env). Secrets only in 1Password vault `vibe_coding` / hosting env — never git, logs or chat. `effective_date` unknown stays NULL.
- **All source text goes to models inside a delimited DATA block** with the "data, not instructions" sentence; `tests/test_prompts.py::test_source_text_is_data` enforces it for every prompt file.
- **Implementer sessions never edit the plan STATUS rows** — the reviewing session owns them on APPROVE.
- Branch per step: `brain/stepNN-<slug>` from `main`; one PR per step. Python 3.12 / uv / ruff / pytest; type hints everywhere; one statement per line (no one-line `if x: raise`). Tests in `apps/brain/tests/`; the five fixtures are frozen — reuse them, never rebuild them differently.
- **Use a per-step git worktree** (named `theoracle-stepNN-*` under the machine temp area) for Company Map work. The shared checkout at the usual repos location gets branch-switched by other sessions mid-work — it happened; do not edit it except for serialized landing.
- Handoff discipline: one write-once file per session in `HANDOFF.d/`; successor rule for deletions; never rewrite root `HANDOFF.md`; never edit another session's file (repo `AGENTS.md` §3a). File references in handoffs are GitHub URLs, not machine paths.
- Times to humans are EST/EDT.

## 8. Access and environment

- **Machines:** edge-dev (Windows coordinator) and `edge-dev3` (Linux dev box, Docker 29.x; SSH alias `edge-dev3`, address in the private machine atlas — `ai-private-config`). On Windows use Git's `ssh.exe` (literal path) for SSH.
- **GitHub:** `gh` authenticated as `u2giants`; repo `u2giants/theoracle`. Task gates: `ai-task-gates` (`start --class … --base …`, `check --before …`) from the `ai-devops` toolkit — the step-3 declaration is `--class code`.
- **Secrets:** 1Password MCP service account, vault `vibe_coding` — `op_run` with `op://` references so values never enter chat. Supabase item "Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, …)"; OpenRouter key item `62ieeyycs4ierflalbbbt5pq5i` (needed from step 4's smoke test); `SCALEDOWN_API_KEY` / `BRAIN_SHARED_TOKEN` to be created before Step 4 (§6.3).
- **Python:** uv venv in `apps/brain` (Python 3.12): `uv sync`, `uv run pytest`, `uv run ruff check .`, `uv run python -m brain.migrate`. No new dependencies were needed for step 3 (tiktoken, pypdfium2, pillow, webvtt-py were already declared).
- **Test database:** Postgres 16 + pgvector container on `edge-dev3` (§4.2). Run tests from Windows with `DATABASE_URL` pointing at its published port; `FALKORDB_URL` is not needed before step 7 (health reports graph false and that is fine). CI provides both services itself (`.github/workflows/brain-ci.yml`).
- **Nothing deployed** to Coolify/Vercel for this program yet (step 14).

## 9. Open questions and risks

- **The step-3 gate's "~60 transcript chunks" vs the rule's 246** (§3, §4.5) is flagged for the Claude reviewer in PR #267. If the verdict is FIX on this point, the implementer must **ask** on #244 (plan §11 trigger 1/2) rather than invent a chunker — the plan text and the step-2 fixture are simply inconsistent on this number.
- **Recorded vision responses are hand-authored** (§5). They are exact to the fixture images and exercise the full parse/render path, but they are not live-model output. The step-4 smoke test (`brain.smoke --live`, plan §10) is the first live-model moment; refresh recordings then if desired.
- **Task-gates `**/*.sql` → `shared-db`** will recur on every future `cmap` migration (§4.3). If `check --before database` demands artifacts that genuinely belong to `popcre/shared-db` (claim-first in that repo), that contradicts the plan's "shared-db rules do not apply" — stop and post the question on the current child issue (plan §11 trigger), do not guess.
- **The two red checks (`Oracle offline suites` / `oracle2-offline`) are pre-existing on `main`** (§3). They may make external gate bots look red even when a step's own gate is green — the reviewing session owns merge policy; do not "fix" the old suite inside this program (plan §10).
- **Future schema changes** to `cmap` are additive idempotent migrations (`brain/sql/002_*.sql`), never destructive recreates — production already holds the Step 1 schema.
- **Successor-rule retirement of the 2026-10-28T1517Z program baton is done in the commit carrying this file.** All three conditions hold: (1) its status line's work (steps 0–1) is committed, pushed and verified on `main` (PRs #260/#261, plus #264 for step 2 and #263 for the baton itself); (2) its open obligations are carried here — §6.3's two 1Password items (this file §6.3), the task-gates SQL procedure (§4.3), the Supabase pooler note (§4.4/§5); (3) its decisions and dead ends live in the plan's STATUS area and in §4/§5 above. Its own text said the session finishing the next program step would retire it; the step-2 session did not, so this session did. Git history keeps the text. The plan's "Registered handoff" line is updated in the same commit.

---

## Self-audit (mandatory completeness gate, run before sending)

1. **Could a brand-new developer with no project knowledge pick up here and not skip a beat?** Yes — §1 defines the application and entry points, §3 states exactly what is done/open with URLs and test names, §6 gives numbered next actions each with a "you'll know it worked when" gate, §8 covers access end to end.
2. **As effectively as I can right now?** Yes — §4 records every dead end with its fix (including this session's gate-arithmetic and PowerShell findings), §5 the non-obvious discoveries (recorded-response seams, transcript prefix rationale, prompt fence), §7 the binding constraints including supervision and STATUS-row ownership.
3. **Every relevant detail for flawless execution?** Yes — background/goals (§2), current state incl. deploy status and the 246-vs-~60 caveat (§3), failures (§4), decisions (§0 + §5 + §9), constraints (§7), risks (§9), exact next actions with gates (§6), verification evidence (§3: 32 passed locally, PR #267, named gate tests).
4. **If Albert read only §0, would he see every business decision and no technical approval?** Yes — §0 states explicitly that no business decisions are pending and lists the only owner action (the supervision relay) as ordinary process, plus the settled do-not-re-ask list. Every technical item (gate arithmetic, recorded fixtures, task-gates SQL, red checks, secrets creation) is routed to §3–§9 as technical, never as an ask.
