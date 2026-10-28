---
issue: 243
status: OPEN
owner: mimo/company-map-step2-handoff
---

# Company Map Step 2 — shipped and approved; the live proof carries to step 3

Handoff written 2026-10-28 (about 2:20 PM EDT) by the MiMo implementing session
for the Oracle Company Map program, step 2 of
[plan_oracle_company_map.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md).

**One-line state:** step 2 is implemented, reviewed and **merged**
([PR #264](https://github.com/u2giants/theoracle/pull/264), VERDICT: APPROVE by
the Claude Opus reviewer); what stays open is the deferred live page proof
(tick box on
[issue #243](https://github.com/u2giants/theoracle/issues/243), carried in the
plan STATUS row as "page live upload deferred to Step 3 read proof") and one
small hardening note from the reviewer.

---

## 0. ⚠️ Business decisions only the owner can make

**None — nothing in this workstream needs the owner.** The program, its
decisions and its review mechanics are already ruled; the next owner action is
process (step 3 when he asks for it), not a judgement.

**Already settled — do NOT re-ask** (dates are EDT):

- 2026-10-27 — the program's binding decisions (scale, no per-claim grading, no
  permission system beyond login + admin flag, FalkorDB stays, treat as
  brand-new) live in the STATUS section of
  [plan_oracle_company_map.md](https://github.com/u2giants/theoracle/blob/main/plan_oracle_company_map.md).
- 2026-10-28 — supervision rule (owner ruling): only Claude Opus or Fable
  reviews this program's steps; the implementer opens the step PR and does NOT
  merge it. That rule ran exactly as designed for step 2 — see
  [issue #240](https://github.com/u2giants/theoracle/issues/240).
- 2026-10-28 (2:01 PM EST) — the step-2 interpretation question (does the admin
  gate cover plain upload?) was **accepted by the reviewer**: PR #264 gates
  every mutation on `employees.is_admin`, "exactly §8 line 90" of the plan.
  Record as settled; do not reopen.

Instruct the next session: put any business question to the owner in ONE
message before starting work. There are currently none.

## 1. What this application is

The Oracle is POP Creations / Spruce Line's evidence-backed company knowledge
graph. The current program (2026-10-27) builds the **Company Map** — a
big-picture adviser that reads hundreds of documents, diagrams and transcripts
and shows how work actually flows: departments, processes, hand-offs, recurring
pain points, each click-through to its sources.

- Repository: [u2giants/theoracle](https://github.com/u2giants/theoracle) on
  GitHub (default branch `main`, pnpm + turbo monorepo).
- New piece being built: `apps/brain` — one Python 3.12 FastAPI service with a
  background worker loop; it owns all reading, extraction, graph and answering
  work. The Next.js app (`apps/web`) renders and proxies.
- Data: Supabase Postgres (schema `cmap`), Supabase Storage bucket
  `company_documents`, FalkorDB graph from step 7.
- Program map: parent issue
  [#240](https://github.com/u2giants/theoracle/issues/240), children
  #241–#255 (one per step). Steps 0 (#241), 1 (#242) and **2 (#243
  implementation)** are done and merged; the plan STATUS row for step 2 is
  `✅ done`.

## 2. What we set out to do this session, and why

Albert asked (2026-10-28): read
[u2giants/theoracle#240](https://github.com/u2giants/theoracle/issues/240) and
complete step 2 ([#243](https://github.com/u2giants/theoracle/issues/243)) —
**source intake**: upload, bulk import, transcripts, diagrams, plus the fixture
corpus every later step reuses. Nothing downstream can run until sources land
in `cmap.source` and queue their `read_source` jobs, so this step is the
program's front door. It completed the same session, review included.

## 3. Current state — what is true right now

**Done and accepted (verified):**

- Commit
  [cded0e36](https://github.com/u2giants/theoracle/commit/cded0e3612fafd2c1af95d6989cefa8e3743c9fe)
  ("Step 2: source intake — upload, bulk import, transcripts, fixtures", 20
  files) was merged to `main` via
  [PR #264](https://github.com/u2giants/theoracle/pull/264) at **2:01 PM EST,
  2026-10-28**. Reviewer verdict:
  [VERDICT: APPROVE](https://github.com/u2giants/theoracle/issues/243#issuecomment-6476671423)
  (Claude Opus, reran the suite itself on a fresh pgvector/pg16: 16 passed).
  Issue #243's three checkboxes are ticked and the plan STATUS row is updated.
- Brain endpoints (now on `main`) —
  [`apps/brain/brain/api/sources.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/sources.py):
  `GET /sources` (L253, any logged-in employee), `POST /sources` (L264,
  multipart), `POST /sources/transcript` (L319, JSON paste),
  `POST /sources/import-bucket` (L347), `POST /sources/import-folder` (L386),
  `DELETE /sources/{id}` (L444). All mutations admin-gated (settled, §0). All
  intakes write `cmap.source` with storage key `cmap/<uuid>/<safe-filename>`
  and enqueue `read_source` with payload `{"source_id": "<uuid>"}`; delete
  cascades and enqueues `project` with `{"removed_source_id": "<uuid>"}`.
- Kind detection —
  [`apps/brain/brain/read/detect.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/read/detect.py):
  `detect_kind` (L117, extension + magic bytes, mismatch refused),
  `verify_office_zip` (L150, claimed member prefix + >100 MB uncompressed
  abort).
- Auth —
  [`apps/brain/brain/api/deps.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/deps.py)
  (`x-brain-token` + `x-user-id` → `public.employees.is_admin`), storage client
  in
  [`apps/brain/brain/storage.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/storage.py).
- Web —
  [`apps/web/app/api/brain/[...path]/route.ts`](https://github.com/u2giants/theoracle/blob/main/apps/web/app/api/brain/%5B...%5D/route.ts)
  proxy; sources page
  [`apps/web/app/map/sources/page.tsx`](https://github.com/u2giants/theoracle/blob/main/apps/web/app/map/sources/page.tsx)
  with
  [`_components/sources-client.tsx`](https://github.com/u2giants/theoracle/blob/main/apps/web/app/map/sources/_components/sources-client.tsx)
  (drag-drop multi-upload, transcript paste box, sources table with
  `read_state` badges; delete shown only to admins).
- Fixtures —
  [`apps/brain/tests/fixtures/`](https://github.com/u2giants/theoracle/tree/main/apps/brain/tests/fixtures):
  3-page `licensing-approval-procedure.pdf`, `licensing-approval-flowchart.png`
  (swimlane chart naming "Licensor approval?" and "Record sign-off (Jessica)"),
  `sample-room-checklist.docx`, `open-po-exceptions.xlsx`, 300-line
  `teams-approval-2026-03-14.txt` (Ilona: "the licensor sign-off"; Marco:
  "Jessica's approval"). Regenerate the four binaries with
  [`build_fixtures.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/fixtures/build_fixtures.py)
  (stdlib + Pillow only). These five are the corpus for every later step's
  tests — do not alter their content without re-checking the step-2..9 gates
  that quote them.
- Tests on `main` — 16 green:
  [`tests/test_intake.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_intake.py)
  (12 tests: the step gate `test_five_fixtures_produce_five_queued_rows`,
  `test_duplicate_upload_returns_same_id`, and the five named adversarial
  cases),
  [`tests/test_prompts.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_prompts.py),
  plus the step-0/1 suites. CI artifact:
  [run 40723068534](https://github.com/u2giants/theoracle/actions/runs/40723068534).
  Web `tsc --noEmit` clean (reviewer reran).

**Still open (this handoff's reason for existing):**

- **Live proof** — the unchecked `- [ ] live proof` line on
  [#243](https://github.com/u2giants/theoracle/issues/243): upload the five
  fixtures through the `/map/sources` page, show five rows `queued`, then
  `read` after step 3's reader exists. The review accepted the endpoint-level
  proof for the merge and wrote "page live upload deferred to Step 3 read
  proof" into the plan STATUS row, so step 3's session will find it.
- **Reviewer's hardening note** (from the APPROVE comment): one import error in
  `_ingest_bytes` aborts a whole bulk import; "acceptable now, worth hardening
  before Step 14's real run". Not a merge blocker; record before step 14.

**Not started:** steps 3–14.

## 4. Everything we tried that did NOT work

1. **Worked in the shared checkout, got branch-switched mid-session.** The
   canonical checkout (which another session uses concurrently) was on
   `brain/step01-schema-cmap` when this session created its branch there; a few
   minutes later the working tree had been switched out to
   `mimo/handoff-step1-cmap` at the step-0 commit and the step-1 files had
   vanished from disk. Recovery: left that checkout alone entirely and moved
   all work into a dedicated git worktree. Lesson for successors: never write
   in the shared checkout for multi-step work; `git worktree add` first.
2. **`isinstance(upload, fastapi.UploadFile)` is silently False.** FastAPI
   0.162 wraps Starlette's class, so the form-field check reported "multipart
   field 'file' is required" for every real upload even though the field was
   present. Fix: import `UploadFile` from `starlette.datastructures` (the
   object's actual class) —
   [`sources.py` L22](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/sources.py#L22).
3. **`from collections.abc import BinaryIO` raises ImportError** — `BinaryIO`
   lives in `typing`, not `collections.abc`.
4. **psycopg: "cannot insert multiple commands into a prepared statement"** —
   `conn.execute(multi_statement_sql, params)` uses the extended protocol, which
   forbids multi-statement scripts. Fix: inline literal values and run the
   script without parameters (why the test employee stubs in
   [`tests/conftest.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/conftest.py)
   embed their UUIDs).
5. **Generator/streamed multipart uploads cannot be parsed** in this stack
   (httpx 0.28 + starlette 1.10 + python-multipart 0.0.32): any `files=` body
   whose content is a generator ends in `400 "There was an error parsing the
   body"`. Real file objects or raw bytes work fine. The 200 MB-size test
   therefore uploads a real 201 MB temp file through a file handle.
6. **Ruff B008 rejects `Depends(...)` in argument defaults** (classic FastAPI
   idiom) under this repo's lint rules. Fix: `Annotated[User, Depends(...)]`
   signatures instead of defaults.
7. **PowerShell cannot chain `uv run ... && $env:X=...`** — the env assignment
   is parsed as an expression. Set env vars on their own statements.
8. **`bash` on the Windows machine (edge-dev) is WSL, which has no distro
   installed.** The ai-devops shell tools run under Git Bash instead (any
   non-WSL bash works).
9. **`ai-pr-wait` timed out** ("another GitHub call holds the throttle lock")
   because another session was hammering the GitHub client; polling `gh pr
   checks <n>` directly worked immediately.
10. **First two flowchart fixture renderings were wrong** (labels overlapping
    the "Licensor approval?" diamond text, "Compliance review" in the wrong
    swimlane). Fixed by re-routing the "no" arrow below the diamond and moving
    boxes between lanes; the shipped PNG is visually verified.
11. **Do not trust Windows PowerShell 5.1 `Get-Content`/`Add-Content` defaults
    for encoding** — used the dedicated file tools instead; all repo text
    stayed UTF-8.

## 5. Root causes and key findings

- **Test database for `apps/brain` (steps 0–2 all used it):** Postgres 16 +
  pgvector runs as Docker container `brain2-test-pg` on host `edge-dev3`
  (192.168.3.42), published port **56789**, credentials `oracle`/`oracle`,
  database `brain_test` — the same shape as
  [`apps/brain/compose.dev.yaml`](https://github.com/u2giants/theoracle/blob/main/apps/brain/compose.dev.yaml)
  and the CI service in
  [`.github/workflows/brain-ci.yml`](https://github.com/u2giants/theoracle/blob/main/.github/workflows/brain-ci.yml).
  Left **running** on purpose so step 3 can reuse it. The Windows machine has
  no Docker Desktop/WSL; Postgres lives on the Linux host.
- **Path-filtered CI:** `brain-ci.yml` only triggers for `apps/brain/**`
  changes, so a commit touching only `HANDOFF.d/` does not re-run "brain
  tests"; `pr-check.yml` re-runs on every push.
- **The legacy `oracle2-offline` check is red on every PR of this program**
  (`test_ci_trust_boundary.py` KeyError `'uses'` on a workflow step) — the same
  failure appears on merged
  [PR #261](https://github.com/u2giants/theoracle/pull/261). Pre-existing and
  out of scope; the plan leaves the old workflow as is until the old code is
  deleted. Do not chase it inside step work.
- **Supabase Storage from Python** is plain REST with the service-role key as
  Bearer (`SupabaseStorage` in
  [`storage.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/storage.py));
  tests swap the client for an in-memory fake via monkeypatch of
  `brain.storage.get_storage`, so no test touches real storage.
- **Employee/admin resolution** joins `public.employee_identities` →
  `public.employees` on the auth user id (plan §8 chose `employees.is_admin`
  because it already exists). The CI database has neither table, so
  [`tests/conftest.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/conftest.py)
  installs minimal stand-ins `IF NOT EXISTS`.
- **`effective_date` is never defaulted to the upload date** (plan §11): empty
  input stores NULL.
- **FastAPI's dependency default idiom and this repo's ruff `B` rules
  disagree**; `Annotated` is the pattern for every future brain endpoint.

## 6. Exact next steps

1. **Live proof at step 3 (issue
   [#244](https://github.com/u2giants/theoracle/issues/244) implementing
   session):** once the reader exists and flips sources to `read`, upload the
   five fixtures through `/map/sources`, capture five rows `queued` → `read`,
   and tick the live-proof line on
   [#243](https://github.com/u2giants/theoracle/issues/243). *You'll know it
   worked when* the table shows five `read` rows and the box is ticked.
2. **Before step 14's real run:** harden `_ingest_bytes` so one bad object in
   a bulk import records an error and continues instead of aborting the whole
   import (reviewer's note on #243). *You'll know it worked when* a bulk import
   containing one corrupt file still ingests the rest and lists the failure in
   its `errors` array.
3. **Step 3 (#244) when Albert asks** — reading, page images, chunking,
   embeddings. A fresh implementing session re-reads the plan Part 1 and the
   step-3 text first (the plan is written to be self-contained). It should
   also add its prompt files under `apps/brain/brain/prompts/` — the reviewer
   noted `test_source_text_is_data` passes vacuously until the first prompt
   lands.
4. **Retire this handoff** under the successor rule when #243's live-proof box
   is ticked (its `issue:` then closes): delete this file in the same commit
   that finishes it, carrying any still-open item forward first.

## 7. Constraints and gotchas in force

- **Supervision rule (owner ruling 2026-10-28):** only Claude Opus or Fable
  reviews program steps; the implementer opens the step PR and never merges
  it. It ran as designed for step 2 — keep it for steps 3+.
- **Program invariants (plan Part 1, never break):** never gate a document from
  being read; never add a per-fact approval queue; never add a permission
  system beyond login + an admin flag.
- **No hard-coded model names in code** (env only); secrets live in 1Password
  vault `vibe_coding` and platform env settings — never in Git, logs or chat.
- **Every prompt file must wrap source text in a fenced DATA block** and say
  the data is not instructions —
  [`tests/test_prompts.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_prompts.py)
  enforces it from step 3 onward.
- **Concurrent-session rules:** never write in the shared checkout while
  another session may switch branches there (it happened this session — §4.1);
  never edit another session's `HANDOFF.d/` file; never rewrite root
  `HANDOFF.md` (the static pointer is already in place).
- **This handoff file is write-once**; its successor deletes it under the rule
  in §6.4.
- `effective_date` unknown stays NULL; office zips over 100 MB uncompressed are
  aborted; uploads over 200 MB are 413; transcripts over 200,000 lines are 413
  with a message.

## 8. Access and environment

- `gh` is authenticated as `u2giants` on the writing machine; GitHub is the
  source of truth for PR/issue state.
- Step 2's work is on `main` (PR #264 merged). The writing session kept its
  work in a dedicated git worktree; a fresh clone is equivalent — worktrees are
  disposable.
- Python side: `uv sync` in `apps/brain`, then `uv run pytest` /
  `uv run ruff check .` with `DATABASE_URL` pointing at the test Postgres (§5
  container) and `BRAIN_SHARED_TOKEN` set (the suite sets its own token value
  in
  [`tests/conftest.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/conftest.py)).
  Web side: `pnpm install`, `pnpm -w typecheck`, `pnpm -w lint`.
- Credentials by location only: 1Password vault `vibe_coding` holds
  `OPENROUTER_API_KEY` (item `62ieeyycs4ierflalbbbt5pq5i`, plan §12) and will
  hold `SCALEDOWN_API_KEY` before step 4; the Supabase service-role key lives
  in the hosting platform's env settings. No secret values appeared this
  session.
- Shared-database state: **none** — this session never touched the shared
  Supabase database or `popcre/shared-db`, dispatched no sub-agents and holds
  no claims (verified with `ai-shared-db-closeout-check`).

## 9. Open questions and risks

- **Live proof is the only verification gap** (§3/§6.1): the page walkthrough
  spans into step 3; until then acceptance evidence is the endpoint-level
  tests the reviewer reran.
- **Bulk-import abort** (reviewer's note, §6.2): fine for now, must harden
  before step 14's real-corpus run.
- **Legacy `oracle2-offline` CI failure** (pre-existing, §5) shows red on PRs of
  this program; do not "fix" it inside step work.
- **Fixture immutability:** later step gates quote the fixture contents
  (Jessica, the licensor sign-off, the stall). If anyone regenerates or edits
  them, every step's tests must be re-run — treat them as frozen corpus.

---

### Self-audit gate (handoff-writer Mode A) — answers

1. **Could a brand-new developer pick this up and not skip a beat?** Yes — §1
   orients, §3 gives every artifact as a `blob/main` GitHub URL (merged state)
   plus the verdict and CI links, §6 gives numbered next actions with
   verification gates, §8 explains how to run the suites.
2. **Detailed enough to continue as well as this session could right now?**
   Yes — §4 lists every failed approach with its exact symptom and fix
   (FastAPI UploadFile identity, psycopg multi-statement, generator multipart,
   B008, the shared-checkout branch switch), §5 records the test-database
   coordinates, the CI path filter, the pre-existing red check and the frozen
   fixture rule — the four things most likely to burn a successor's hour.
3. **Every relevant detail for flawless execution?** Yes — background and
   intent (§2), verified current state incl. merge time and verdict (§3), dead
   ends (§4), findings (§5), exact actions + gates (§6), constraints (§7),
   access (§8), risks and dated settled decisions (§9); secrets referenced by
   vault location only (§8); all file, commit, PR and CI references are GitHub
   URLs.
4. **If the owner read only §0, would he see every business decision and no
   technical approval?** Yes — the sweep found no outstanding business
   judgement; the one interpretation question was settled by the reviewer and
   is listed as settled (do not reopen), the remaining items (live proof,
   hardening) are technical and live in §3/§6/§9, not in §0. No approval, key
   or manual step is asked of the owner anywhere.

All four answers are evidence-backed yeses; the checklist passes.
