---
issue: 245
status: OPEN
owner: mimo/company-map-step4-flat
---

# Handoff — Company Map program: Step 4 implemented and open for review; next is the review relay, then Step 5

Written 2026-10-28, 4:23 PM EDT, edge-dev, MiMo. This file is the **program baton** for the Company Map work (parent issue https://github.com/u2giants/theoracle/issues/240 ). It replaces `HANDOFF.d/2026-10-28T1909Z-edge-dev-mimo-company-map-step3-cut.md`, retired in the same commit under the successor rule (conditions checked in §9).

## 0. ⚠️ Business decisions only the owner can make

- **None — nothing in this workstream needs a business decision from Albert right now.** Step 4's only judgment calls are interpretation notes in the PR body (technical, routed to the AI reviewer — not to Albert).
- The only owner action is the supervision relay, which is ordinary process and not a decision: paste issue #245's "Review prompt (copy everything in the box)" into a **fresh Claude Opus or Fable** session on this repository so it reviews the Step 4 PR. After it merges, open a fresh implementer session for Step 5. Recommendation: do the relay now — nothing else is blocking.
- **Already settled — do NOT re-ask (owner rulings 2026-10-27/28, recorded in the plan):** the program builds the big picture from noisy data (no atomic-claim evaluation); no permission system beyond login + `is_admin`; FalkorDB stays; corpus is hundreds of documents/diagrams and tens of thousands of transcript lines plus interviews; human grading "within reason"; treat this as brand new (no comparison with the old Oracle); supervision is **Claude Opus or Fable only** for reviews (GPT/GLM never review), implementer opens the PR and never merges it, Albert pastes the child issue's review prompt into a fresh Opus/Fable session. Full text: the plan's STATUS area — https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md

## 1. What this application is

POP Creations / Spruce Line (high-volume home decor company, owner Albert Hazan) is building "The Oracle" — an evidence-backed company adviser. The current program is the **Company Map**: read hundreds of procedure documents, flowcharts/diagrams and tens of thousands of lines of employee transcripts, then show how work actually flows across departments, where hand-offs break, and answer questions citing many sources at once.

- Repository: `u2giants/theoracle` on GitHub, default branch `main` (pnpm + turbo monorepo).
- Durable program spec: https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md — **always read its STATUS table first**; do not re-derive or re-plan. "Fresh session starts at: the first row marked ⬜ open, in order."
- Program tracking: parent https://github.com/u2giants/theoracle/issues/240 with children #241–#255 (one per step 0–14). #241/#242 closed; #243/#244 still open with merged work; **#245 is the live one**; #246–#255 untouched.
- New component: `apps/brain/` — one Python 3.12 service (FastAPI + worker loop) owning all reading, extraction, graph and answering logic. `apps/web/` (Next.js) keeps login and renders, proxying to `apps/brain`. Supabase Postgres is the durable store (schema `cmap`); FalkorDB is the graph from step 7 on.

## 2. What we set out to do this session, and why

Albert asked (2026-10-28): read issue #240, and complete **Step 4** (issue https://github.com/u2giants/theoracle/issues/245 ) — passage classification and flat extraction via ScaleDown, so every chunk gets a passage label and its named things (people, roles, steps, issues…) become mention rows that steps 5–6 join into the map. Step 4 is now **implemented and awaiting its Claude Opus/Fable review** (see §3).

## 3. Current state — what is true right now

**Done and accepted (verified on main):**

- **Steps 0–3** (PRs #260/#261/#264/#267): skeleton, `cmap` schema, intake + fixtures, reading/chunking/embeddings. Plan STATUS rows `✅ done` with artifacts.
- **Prerequisites for step 4 are DONE (this session closed the step-3 handoff's §6.3 obligation):** 1Password vault `vibe_coding` now holds
  - `Oracle Brain shared token - The Oracle (BRAIN_SHARED_TOKEN)` (item `4lm6bpl7bc25lqne4meumwcd2a`) — 43-char base62 (256-bit) token from the vault generator;
  - `ScaleDown API Key - The Oracle` (item `epna47xmzcnbdc6eb3tjpx6phm`) — `SCALEDOWN_API_KEY` concealed field, same provider key as `scaledown.ai API key for testing` (copied without exposure through `op` CLI + `op_run` env injection; one ScaleDown account — see the item notes).

**Step 4 — implemented, pushed, NOT merged (by design):**

- Branch `brain/step04-flat-extraction`, PR **(number in the "Ready for review" comment on #245)** — opened 2026-10-28, base `main`, worktree `C:/tmp/theoracle-step04-flat`.
- What landed (all under `apps/brain/`):
  - `brain/extract/flat.py` — job `classify_extract` (registered in `brain/worker.py`): per source, per chunk, **8 concurrent** ScaleDown calls — `POST https://api.scaledown.xyz/classify` (the plan's seven labels) and `POST /extract` (the plan's sixteen entity types). `top_label` → `chunk.passage_kind`; `chatter` at score ≥ 0.8 skips extraction; entities at confidence ≥ 0.5 become `cmap.mention` rows (span → containing-sentence quote, `normalized_name`, embedding of `surface_name — quote`). Raw responses recorded in `cmap.extraction(stage='flat')` with `model` = `scaledown/classify` | `scaledown/extract` | the frontier model id.
  - **Frontier fallback** — `BRAIN_SCALEDOWN_ENABLED=false`, missing key, or three non-200s in a row → one frontier call per chunk with `brain/prompts/flat_extract.md` (both halves of the work in one JSON). Every ScaleDown call has the fallback (plan §8/§11); the per-job frontier cap `BRAIN_MAX_FRONTIER_CALLS_PER_JOB` is enforced.
  - `brain/extract/normalize.py` — casefold, strip punctuation, collapse spaces, drop leading "the" and honorifics, singularise trailing "s" for non-Person types ("process"/"status"/"bus" keep their s).
  - `brain/smoke.py` — the plan §10 live smoke (`uv run python -m brain.smoke --live`), not in CI: ingests the five fixtures with real ScaleDown + OpenRouter calls and prints counts and cost.
  - `tests/test_flat.py` (6 tests) + recorded ScaleDown responses in `tests/fixtures/recorded/scaledown/` (`transcript.json`, `pdf.json`, `frontier_flat.json`), replayed through the HTTP seams via `fake_scaledown` / `fake_frontier` in `tests/conftest.py`.
- Verification: **38 passed** locally (uv, Python 3.12) against Postgres 16 + pgvector on the edge-dev3 test container (32 from earlier steps + 6 new); `ruff check` clean. Named gate tests green: `test_transcript_finds_jessica_role_process_and_stall_issue` (Person "Jessica", Role "licensing manager", Process containing "licens", Issue containing "bottleneck"), `test_pdf_yields_a_step_for_each_procedure_step` (six Steps, one per procedure step), `test_flat_fallback_matches_shape`, plus `test_chatter_chunks_skip_extraction`, `test_normalize_name_rules`, `test_sentence_containing_and_span_repair`. CI `brain tests` is the step gate on the PR.
- **Live smoke run (plan §10), 2026-10-28 4:20 PM EDT** (real ScaleDown + OpenRouter, ScaleDown path enabled):
  - TOTAL **253 chunks, 807 mentions, 0 edges, 0 communities** (edges/communities arrive at steps 5–8).
  - Transcript (246 chunks): 663 mentions (Person 253, Role 37, Issue 59, Process 36…); passage kinds: chatter 66, problem 52, process 37, responsibility 35, decision 28, rule 24, reference 4; **477 ScaleDown calls (1.94/chunk)**; extraction skipped on 15 chunks (the chatter ≥ 0.8 rule); embed 4,260 tokens.
  - Whole run: 253 classify + 238 extract ScaleDown calls, 1 vision call (1,682 tokens), 33,642 embedding tokens (23 batches), **0 frontier tokens**. Per-chunk cost is ScaleDown-cheap exactly as the step-3 drift note hoped — the `chatter` skip is doing part of the work, the rest is ScaleDown pricing.

**Interpretation notes the reviewer must see (also in the PR body):**
1. **Fallback JSON shape.** The plan says the frontier fallback uses "the same JSON shape as ScaleDown's `structured_result` so results are interchangeable." One JSON cannot be both a `structured_result` (no spans, no confidences) and interchangeable with the `entities[]` list that needs `[start,end)` and confidence ≥ 0.5. The fallback therefore returns **one JSON carrying both ScaleDown response shapes** — `top_label`/`scores` from `/classify` and `entities`/`structured_result` from `/extract` — and both paths feed the same mention builder. `test_flat_fallback_matches_shape` asserts the two paths yield identical mention rows for the same chunk.
2. **`brain/smoke.py` is new** beyond the step's "Change" list, because plan §10 requires the live smoke run *before each step's PR from step 4 onward* with its counts in the PR body. It is explicitly not CI.
3. **`brain/embed.py` now sends `dimensions: BRAIN_EMBED_DIMS`.** Verified live: `openai/text-embedding-3-large` (the plan's default) returns **3072** dims without it, which can never satisfy the `vector(1024)` schema; with `dimensions=1024` it returns 1024. This makes step 3's declared contract true at runtime and is required by the §10 smoke test.
4. **Prompt hashes** (`cmap.extraction.prompt_hash`): classify = hash of the label spec; extract = hash of the entity spec; frontier = hash of label spec + entity spec + `flat_extract.md` bytes. Editing a prompt file changes the hash (plan §11); reprocessing is the future `POST /sources/reprocess`.
5. **Chatter-skip resume:** a chatter chunk records its classify response but never an extract row; a re-run reuses the stored classify payload (no HTTP) and skips again. Cheap and idempotent; non-chatter chunks are skipped entirely once their extract/frontier row exists.

**Not started:** steps 5–14 (relations, entity resolution, FalkorDB projection, communities, QA, map page, evaluation, interviews, recommendations, hosting/first real run).

**Nothing of this program is deployed to Coolify/Vercel yet** (step 14 does hosting). `apps/brain` runs from source and in CI only.

**Known red checks that are NOT ours:** `Oracle offline suites` / `oracle2-offline` fail on `main` itself (`docs/agents/15-pending-work.md`). Ignore on this program's PRs — step gates are `brain tests` / each step's named pytest.

## 4. Everything we tried that did NOT work (dead ends — do not repeat)

Carried forward from the step-3 baton (still true):
1. **No pgvector on the edge-dev Windows box.** What works: the `brain2-test-pg` container (pgvector/pgvector:pg16, published port **56789**, user `oracle`/`oracle`, db `brain_test`) on `edge-dev3`, reached from Windows at `192.168.3.42:56789` (Tailscale `100.66.9.69` also works). SSH with **Git's `ssh.exe`** (`C:\Program Files\Git\usr\bin\ssh.exe`); Windows OpenSSH through tool calls breaks with ConPTY 255. Start a fresh container if it is gone.
2. **PowerShell tool shells mangle `$env:VAR=...` one-liners** (they parse as bare tokens) and **block `.ps1` files** (execution policy). What works: `cmd /c "set VAR=value&& …"` for env, and `powershell -NoProfile -ExecutionPolicy Bypass -File x.ps1` for scripts.
3. **`1password_op_run` (MCP) times out on long processes** (~60 s bridge limit) and leaves the child orphaned. For jobs over a minute, write an env file of `op://` references and run `op run --env-file file -- <command>` from the normal shell (values never enter the transcript; op CLI is signed in as the service account).
4. **`op item duplicate` does not exist** in 1Password CLI 2.39. Copying a secret between items without revealing it works via a PowerShell script fed by `op_run` env injection that pipes an item JSON template into `op item create --vault vibe_coding -` (assignment statements on argv would leak).
5. **Task-gates classifies `*.sql` as `shared-db`** (`docs/agents/11-intentional-quirks.md`) — no SQL in step 4 (the `cmap` schema already had everything; `001_cmap.sql` untouched). This returns at the next migration.
6. **Test-expectation arithmetic should be measured, not guessed** — the recorded fixtures' character spans were computed from the real chunk texts by a one-off probe, not hand-counted.

New this session:
7. **ScaleDown entity `text` may span PDF line breaks** (chunk text joins lines with `\n\n`). Prefer single-line surfaces in recorded fixtures, or probe the exact chunk text first.
8. **`zip(a, a[1:], strict=True)` is always wrong** (strict compares lengths of n and n-1) — use an index-pair loop; also ruff's B905 demands `strict=` on plain `zip`, so pairwise code is cleaner as an explicit loop.

## 5. Root causes and key findings

- **Review mechanics (unchanged, proven again):** implementer PR (never self-merged) → `Ready for review: PR #<n>` comment with artifacts on the child issue → Albert relays into Opus/Fable → `VERDICT: APPROVE` + STATUS update + merge + checkboxes. Implementer sessions **never edit plan STATUS rows**; they only repoint the plan's "Registered handoff" line when they retire a baton. The reviewing session's STATUS commit goes on the PR branch (see PR #267's third commit).
- **Recorded model responses** live in `apps/brain/tests/fixtures/recorded/` and are replayed through the HTTP seams (`brain/extract/flat.py::_post_scaledown` and `::_post_chat`). Step-4 recordings are hand-authored to the fixture texts exactly (spans computed); refreshing them against live ScaleDown is optional future work, not CI work. The live smoke already proves the real API shapes parse: 807 mentions landed from real ScaleDown responses.
- **ScaleDown responses carry `entities[]` with `text/type/confidence/start/end` plus `structured_result`** — mentions come from `entities[]`; spans are repaired by substring search when wrong (models drift); a mention that cannot be quoted (no containing sentence) is dropped, same spirit as step 5's "if you cannot quote, do not record".
- **`chatter` skip is the budget lever the drift note asked about:** on the 300-line transcript, 66 chunks labelled chatter but only 15 skipped extraction (skip needs score ≥ 0.8). Cost per chunk stayed 1.94 ScaleDown calls regardless.
- **Supabase production project for this app:** `theoracle` (PG 17.6, pgvector 0.8.0). Connection strings in 1Password item "Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, …)", field `oracle_session_pooler` for migrations from Windows. Never print values.
- **GitHub sign-off:** `Posted by MiMo chat <id> on edge-dev` (`$MIMO_SESSION_ID` empty ⇒ `unknown`). Commits use `Albert Hazan <u2giants@users.noreply.github.com>` (verify with `git var GIT_COMMITTER_IDENT` before the first commit in a worktree).

## 6. Exact next steps

1. **Review relay for Step 4** (owner action, ordinary process): Albert pastes the "Review prompt (copy everything in the box)" box from https://github.com/u2giants/theoracle/issues/245 into a fresh **Claude Opus/Fable** session. That session reviews the PR named in the latest "Ready for review" comment, posts `VERDICT: APPROVE` or `VERDICT: FIX` on #245, and on APPROVE merges the PR, ticks the issue checkboxes and updates the plan STATUS row. You'll know it worked when the plan STATUS row for Step 4 reads `✅ done`.
2. **If the verdict is FIX:** a fresh implementer session continues from the numbered fix list (same branch `brain/step04-flat-extraction`), reruns the gate, and re-posts `Ready for review`. If a fix would touch a Locked §8 decision or redesign the step, stop and post the question on #245 instead (plan §11 triggers).
3. **Start Step 5** (issue https://github.com/u2giants/theoracle/issues/246 ) in a fresh implementer session: relationship extraction via the frontier model (`brain/extract/relations.py`, job `relations`, prompt `prompts/relations.md` in the plan text). Read the plan's Part 1 and the Step 5 text first. You'll know it worked when `tests/test_relations.py` (with `test_drops_relation_with_fabricated_quote`, `test_rejects_unknown_type`, `test_resume_skips_done_chunks`) is green, CI `brain tests` is green on the step's PR, and `Ready for review: PR #<n>` is posted on #246. Step 5 reuses this step's seams: `cmap.mention` rows (already populated by `classify_extract`) are the `{{mentions_json}}` input.
4. **Before any future step adds SQL:** `python -m brain.migrate` + `brain/sql/NNN_*.sql` (idempotent, additive only), with the task-gates `shared-db` procedure from §4.5.
5. **Retiring THIS file:** the session that finishes the next program step deletes it under the successor rule (verify PR merged + STATUS row `✅ done`, carry forward anything still open) and updates the plan's "Registered handoff" line in the same commit.

## 7. Constraints and gotchas in force

- **Supervision rule (Albert, 2026-10-28):** implementer opens the PR, does **not** merge, posts `Ready for review: PR #<n>` on the child issue with the verification artifact; only **Claude Opus or Fable** reviews (never GPT/GLM); on APPROVE that session merges, ticks the checkboxes, updates the plan STATUS row; on any of plan §11's six triggers the implementer stops and posts a question on the child issue rather than guessing.
- **Plan Part 1's three rules that must never be broken:** never gate reading/indexing on approval; never add per-fact approval queues; never add a permission system beyond login + `is_admin`. Goal beats step text on conflict — write the conflict into STATUS and stop.
- **Never hard-code model ids** (env only, plan §8 — `BRAIN_FRONTIER_MODEL`, `BRAIN_VISION_MODEL`, `BRAIN_EMBED_MODEL`; start values are named in the plan and were used in the smoke run's env). Secrets only in 1Password vault `vibe_coding` / hosting env — never git, logs or chat. `effective_date` unknown stays NULL.
- **All source text goes to models inside a delimited DATA block** with the "data, not instructions" sentence; `tests/test_prompts.py::test_source_text_is_data` enforces it for every prompt file (`flat_extract.md` complies).
- **Implementer sessions never edit the plan STATUS rows** — the reviewing session owns them on APPROVE.
- Branch per step: `brain/stepNN-<slug>` from `main`; one PR per step; **per-step git worktree** named `theoracle-stepNN-*` under the machine temp area (the shared checkout gets branch-switched by other sessions). Python 3.12 / uv / ruff / pytest; type hints everywhere; one statement per line (no one-line `if x: raise`). Tests in `apps/brain/tests/`; the five fixtures are frozen — reuse them, never rebuild them differently.
- Handoff discipline: one write-once file per session in `HANDOFF.d/`; successor rule for deletions; never rewrite root `HANDOFF.md`; never edit another session's file (repo `AGENTS.md` §3a). File references in handoffs are GitHub URLs, not machine paths.
- Times to humans are EST/EDT.

## 8. Access and environment

- **Machines:** edge-dev (Windows coordinator) and `edge-dev3` (Linux dev box, Docker 29.x; SSH alias `edge-dev3`, address in the private machine atlas — `ai-private-config`). On Windows use Git's `ssh.exe` (literal path) for SSH.
- **GitHub:** `gh` authenticated as `u2giants`; repo `u2giants/theoracle`. Task gates: `ai-task-gates` (`start --class code`, `check --before …`) from the `ai-devops` toolkit.
- **Secrets (vault `vibe_coding`):** OpenRouter key item `62ieeyycs4ierflalbbbt5pq5i` (field `OPENROUTER_API_KEY`); **`ScaleDown API Key - The Oracle` item `epna47xmzcnbdc6eb3tjpx6phm` (field `SCALEDOWN_API_KEY`)**; **`Oracle Brain shared token - The Oracle (BRAIN_SHARED_TOKEN)` item `4lm6bpl7bc25lqne4meumwcd2a`**. Use `op://` references (`op run --env-file` for long jobs) so values never enter chat or logs.
- **Python:** uv venv in `apps/brain` (Python 3.12): `uv sync`, `uv run pytest`, `uv run ruff check .`. Step 4 added no new dependencies.
- **Test database:** Postgres 16 + pgvector container `brain2-test-pg` on `edge-dev3`, port 56789 (§4.1). CI provides both Postgres and FalkorDB itself (`.github/workflows/brain-ci.yml`).
- **Live smoke env** (the run in §3 used exactly these; all from 1Password except the DB URL): `DATABASE_URL` to the test container, `BRAIN_FRONTIER_MODEL=anthropic/claude-sonnet-4.5`, `BRAIN_VISION_MODEL=openai/gpt-4.1`, `BRAIN_EMBED_MODEL=openai/text-embedding-3-large`, `BRAIN_SCALEDOWN_ENABLED=true` — model ids are env-only start values (plan §8), change them in env only.
- **Nothing deployed** to Coolify/Vercel for this program yet (step 14).

## 9. Open questions and risks

- **Fallback JSON shape (interpretation note 1)** is the one place the step text is ambiguous. If the verdict is FIX and demands literal `structured_result`-only output from the fallback, the implementer must handle the missing spans/confidence somehow — if that needs a design choice the plan does not spell out, **ask** on #245 (plan §11 trigger 1) rather than inventing thresholds.
- **ScaleDown extraction quality on messy transcripts is unproven** (plan §13 risk): the smoke showed plausible mentions (663 on the transcript) but no precision/recall numbers yet. Mitigation per plan: the eval harness (step 11) compares `BRAIN_SCALEDOWN_ENABLED` true vs false on the same corpus.
- **Recorded fixtures are hand-authored to the fixture texts** (§5); the live smoke is the real-API proof. If a future step sees extraction drift, refresh recordings against live ScaleDown then.
- **`[smoke]` rows are left in the test database** after a smoke run (named `[smoke]`, deleted at the start of the next run). Harmless; tests truncate `cmap.source` anyway.
- **Task-gates `**/*.sql` → `shared-db`** will recur on every future `cmap` migration (§4.5). If `check --before database` demands artifacts that genuinely belong to `popcre/shared-db`, that contradicts the plan's "shared-db rules do not apply" — stop and post the question on the current child issue (plan §11 trigger), do not guess.
- **The two red checks (`Oracle offline suites` / `oracle2-offline`) are pre-existing on `main`** (§3); the reviewing session owns merge policy.
- **Successor-rule retirement of the 2026-10-28T1909Z step-3 cut baton is done in the commit carrying this file.** All three conditions hold: (1) its work (step 3, PR #267) is committed, pushed and verified on `main` (STATUS row `✅ done`); (2) its open obligations are carried or closed — §6.3's two 1Password items are **created this session** (§3), the task-gates SQL procedure and Supabase pooler note are restated (§4.5/§5), the recorded-response refresh note is superseded by the live smoke proof; (3) its decisions and dead ends live in §4/§5 above (including the 246-chunk arithmetic resolution: reviewer accepted 246). Git history keeps the text.

---

## Self-audit (mandatory completeness gate, run before sending)

1. **Could a brand-new developer with no project knowledge pick up here and not skip a beat?** Yes — §1 defines the application and entry points, §3 states exactly what is done/open with the smoke numbers and test names, §6 gives numbered next actions each with a "you'll know it worked when" gate, §8 covers access end to end.
2. **As effectively as I can right now?** Yes — §4 records every dead end with its fix (including this session's 1Password/CLI and long-process findings), §5 the non-obvious discoveries (recorded-response seams, fallback shape, chatter budget).
3. **Every relevant detail for flawless execution?** Yes — background/goals (§2), current state incl. deploy status and the interpretation notes (§3), failures (§4), decisions (§0 + §5 + §9), constraints (§7), risks (§9), exact next actions with gates (§6), verification evidence (§3: 38 passed, smoke counts, named gate tests).
4. **If Albert read only §0, would he see every business decision and no technical approval?** Yes — §0 states explicitly that no business decisions are pending and lists the only owner action (the supervision relay) as ordinary process, plus the settled do-not-re-ask list. Every technical item (fallback shape, embed dims, smoke scope, secrets, task-gates) is routed to §3–§9 as technical, never as an ask.
