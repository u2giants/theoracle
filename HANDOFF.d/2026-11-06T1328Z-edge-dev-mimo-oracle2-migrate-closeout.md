---
issue: none
status: OPEN
owner: mimo/edge-dev-2026-11-06-wrapup
---

<!--
issue: none — the delivered work is proven by the already-closed issue
https://github.com/u2giants/theoracle/issues/431 and merged PR
https://github.com/u2giants/theoracle/pull/462 . What remains here is wrap-up
verification that a tool could not complete, plus pre-existing doc debt that no
ticket covers. No new issue was opened because this session was in its closing
scope freeze and opening one would be new work.
-->

# Handoff — Oracle 2 migrate-runner repair closeout (2026-11-06)

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

**None — nothing in this workstream needs the owner.**

Everything left is technical and can be done by an AI session on its own
authority: re-run a verification tool, and clean up broken documentation links.
No access, sign-in, key, credential, manual step, or judgement call is waiting
on Albert.

### Already settled — do NOT re-ask

- **2026-11-06 — issue #431 is complete and closed.** All three original items
  (GitHub Packages images, Supabase MCP entry, stale seed/settings docs) plus the
  follow-up migration-runner repair are done and proven live. Do not reopen.
- **2026-11-06 — `99_vector_indexes.sql` is deliberately kept.** See §5. Do not
  "tidy it up". Removing it breaks the GAP-10 identity-cleanup safety gate.
- **2026-10-14 (owner ruling) — no AI reviewer approval is required for a
  database write.** Quoted in the ai-devops standing rules.

## 1. What this application is

**The Oracle** is POP Creations' internal knowledge assistant. Employees ask it
questions about the business (customers, licensors, design and production
processes) and it answers from a curated claim base, surfacing sources. It runs
as a web app plus a background "brain" service.

- Repository: https://github.com/u2giants/theoracle
- Stack: Next.js web app, Postgres (Supabase) database, a Python background
  service ("brain") that owns the `cmap` (Company Map) schema.
- Live web: `oracle.designflow.app` (the `*.vercel.app` host sits behind Vercel
  SSO and is not directly readable).
- Live database project ref: `eqccjfbyrywsqkxxpjvg` (this is the application's
  own database, **not** the shared company Supabase).
- The old "Oracle 2" product (claims, gaps, taxonomy, extraction, macros,
  meetings) was removed earlier — issue
  https://github.com/u2giants/theoracle/issues/398 . What remains in the live
  database is five tables in `public` plus the Company Map in `cmap`.

## 2. What we set out to do this session, and why

Albert asked to **clear https://github.com/u2giants/theoracle/issues/431**.

Issue #431 tracked three leftovers from the Oracle 2 removal. Two were done and
one follow-up remained, recorded in a comment on that issue: after the 93 Oracle
2 tables were dropped from production, the database setup step
(`pnpm db:migrate`) could no longer complete — it died on hand-written SQL files
that still referenced the dropped tables. That repair was the job.

## 3. Current state — what is true right now

**The delivered work is COMPLETE, MERGED and PROVEN LIVE. Nothing about it is
half-done.**

- Merged commit: https://github.com/u2giants/theoracle/commit/78c2aabc13753b3ddde0369425c5b365a31a3704
  ("fix(db): retire Oracle 2 raw SQL so pnpm db:migrate completes again (#462)").
- PR: https://github.com/u2giants/theoracle/pull/462 — MERGED, branch deleted.
- Issue: https://github.com/u2giants/theoracle/issues/431 — CLOSED, with the
  full proof recorded in the closing comment
  https://github.com/u2giants/theoracle/issues/431#issuecomment-6677701879
- CI on `main` at that commit is green: `PR check`, `task gates`, `Verify live
  version`, `review-fixer` all `success` (checked 2026-11-06).
- Live proof was run **twice** against production — once from the PR branch and
  again from a fresh checkout of the exact merged head. Both printed
  `Migrations complete.` and exit 0. `db:check-drift` printed
  `[drift] OK — 12 on-disk migrations and 12 journal rows match exactly.`

**What is NOT complete — the reason this handoff exists:**

1. **The shared-database ownership closeout check never ran.** The installed
   `ai-shared-db-closeout-check` tool hangs with zero output and has to be killed
   (killed at 240 s and again at 420 s, exit 124). So the formal "zero owned
   claims" receipt was never produced. See §4 and §6.
2. **Pre-existing documentation-link breakage in this repo** was found but not
   fixed (it predates this session and was out of scope). See §5 and §6.

## 4. Everything we tried that did NOT work

These are the real dead ends. Do not repeat them.

1. **Running `ai-shared-db-closeout-check` normally.** Called as
   `ai-shared-db-closeout-check --session-id ses_ffe5e50e3fcc6ffe7zIUPMLZiw`.
   It printed **nothing at all** and hung. Killed by the tool harness at 180 s,
   retried, killed again at 420 s. Why it seemed reasonable: it is the documented
   mandatory final gate for wrap-up. Why it failed: unknown — it produced not
   even a partial JSON line. Not diagnosed further because repairing the
   ai-devops toolkit is new work and the session was in its closing scope freeze.

2. **Running the same tool under a hard `timeout` from Git Bash.**
   `timeout 240 /C/repos/ai-devops/bin/ai-shared-db-closeout-check …` → exit
   **124** (timeout killed it), again with zero output. Confirms the hang is in
   the tool, not in the calling shell. The launcher
   (`ai-shared-db-closeout-check.cmd`) is fine — it resolves and invokes Git Bash
   against `C:/repos/ai-devops/bin/ai-shared-db-closeout-check`, and that path
   exists.

3. **`scripts/test-task-gates.sh` run locally.** Ran it from the worktree and it
   hung (killed at 300 s). We suspected it was broken because it references
   files deleted by the Oracle 2 removal (`apps/workers/trigger.config.ts`,
   `packages/ai/package.json`). **This suspicion was WRONG** — see §5, finding
   (d). Do not re-raise it.

4. **`ai-doc-safety` invoked via WSL `bash`.** `bash` on this machine is the
   Windows Store stub and prints "Windows Subsystem for Linux has no installed
   distributions." It must be invoked as
   `"C:\Program Files\Git\bin\bash.exe" <path>/ai-doc-safety` instead.

5. **`ai-housekeeping` invoked from the session working directory.** Printed
   `ai-housekeeping: not inside a git repository — nothing to inventory.` The
   session's working directory (`D:\repos\oracle`) is a scratch folder, **not**
   a git checkout — see §8.

6. **`ai-housekeeping` and `ai-housekeeping --details` invoked from inside the
   repo worktree.** Both exit 0 and print **zero bytes** — no report body at
   all. `--help` works and prints normally. So there is no housekeeping summary
   to report; either there are no candidates or the report path is silent. Not
   diagnosed further.

7. **Early date readings were inconsistent.** Readings taken early in the session
   showed roughly 05:0x UTC / 12:0x AM EST; a later reading of the same system
   clock showed 13:2x UTC / 08:2x AM EST, and the two agreed with each other
   from that point. The timestamps written into the PR body and the issue
   comment (12:08 AM, 12:21 AM, 12:25 AM, 12:26 AM EST) came from the clock at
   the time and are internally consistent, but may be hours off. The **evidence**
   (commit SHA, PR state, live migration output, drift output) is unaffected —
   trust those, not the clock strings.

## 5. Root causes and key findings

**(a) The real defect was leftover Oracle 2 SQL, not the runner.**
https://github.com/u2giants/theoracle/commit/78c2aabc13753b3ddde0369425c5b365a31a3704
removed 61 hand-written SQL files and trimmed two. The runner itself
(https://github.com/u2giants/theoracle/blob/78c2aabc13753b3ddde0369425c5b365a31a3704/packages/db/src/migrate.ts)
was **not** changed and needed no change. It applies raw SQL in lexical filename
order in "Step 3"; `100_model_coverage_conversions.sql` sorts first and named the
dropped `gaps` table, so the run died before anything else could be tested.

**(b) `99_vector_indexes.sql` must stay. This is a trap.**
https://github.com/u2giants/theoracle/blob/78c2aabc13753b3ddde0369425c5b365a31a3704/packages/db/migrations/sql/99_vector_indexes.sql
indexes `claims.embedding` and `document_chunks.embedding` — both dropped with
Oracle 2, so the file is dead. It is still there because
https://github.com/u2giants/theoracle/blob/78c2aabc13753b3ddde0369425c5b365a31a3704/packages/db/src/verify-identity-cleanup-contract.ts#L210-L211
asserts `98_drop_deprecated_employee_identity_columns.sql` sorts **before**
`99_vector_indexes.sql`. Delete the file and that GAP-10 safety gate fails. It
is also opt-in behind `ORACLE_RUN_VECTOR_INDEXES=1` and the runner always skips
it in Step 3, so it can never block a run. Its README row says all this.

**(c) The live production catalog is exactly five `public` tables.** Measured
2026-11-06 against project `eqccjfbyrywsqkxxpjvg`:
`departments`, `employee_departments`, `employee_directory_roles`,
`employee_identities`, `employees`. Plus the 22 Company Map tables in `cmap`.
Row counts at that time: 74 employees, 130 `employee_directory_roles`,
8 `employee_identities`, 9 departments, 54 `employee_departments`. Any raw SQL
naming anything else is Oracle 2 and will kill the run.

**(d) `scripts/test-task-gates.sh` is NOT broken.** It looks stale (it names
files deleted in https://github.com/u2giants/theoracle/pull/406) but the `task
gates` workflow passes on `main` at `78c2aabc` and at `c39f7344`. It only hung
when run locally. Use the CI result as the truth.

**(e) `ai-doc-safety` fails on this repo today, for pre-existing reasons.**
Broken local Markdown links in `DECISIONS.md` (two lines naming
`packages/ai/src/providers/openai-adapter.ts` and
`packages/ai/src/providers/vertex-gemini-adapter.ts`, both deleted with Oracle 2)
and in several `HANDOFF.d/*.md` files (naming deleted `plan_*.md` and
`docs/research/*.md` files). None of these files were touched by this session's
change. This matters because the standing rule says a prose-only PR merges with
`gh pr merge --squash --admin` **once `bin/ai-doc-safety` passes on the exact
head** — so that fast path is currently unavailable in this repo. Use the normal
PR + CI path instead until the links are fixed.

**(f) Any `*.sql` change is classified `shared-db` by the task-gate policy, even
in an application's own database.** The central policy maps `**/*.sql` and
`**/migrations/**` to class `shared-db`, and resolution takes the strongest class
per changed path. The correct procedure is
`ai-task-gates start --class shared-db --base <branch-point>` then
`ai-task-gates check --before database`. Always pass `--base` explicitly. The
`popcre/shared-db` claim-first workflow does **not** apply to this repo's own
database — documented at
https://github.com/u2giants/theoracle/blob/78c2aabc13753b3ddde0369425c5b365a31a3704/docs/agents/11-intentional-quirks.md#L583
("Any `*.sql` change classifies as `shared-db` in ai-task-gates").

**(g) Migration `40_employee_identities_data.sql` contains a `DELETE FROM
employees` and is only safe because the runner skips it.** It is guarded by a
check for `employees.auth_user_id`, which
https://github.com/u2giants/theoracle/blob/78c2aabc13753b3ddde0369425c5b365a31a3704/packages/db/src/migrate.ts#L70-L86
performs before applying that one file. Confirmed absent on production before
the write, so the file was skipped. If someone ever re-adds `auth_user_id`, that
file will start running again and delete the `albert@popcre.com` employee row.

## 6. Exact next steps

1. **Prove this session owns no shared-db claim.** Run the installed
   `ai-shared-db-closeout-check` with this session's id
   `ses_ffe5e50e3fcc6ffe7zIUPMLZiw` and require its JSON receipt to show
   `ok: true` with zero `blocking_claims` and zero `blocking_stages`.
   *You'll know it worked when* the tool prints a JSON receipt and exits 0
   instead of hanging.
   - If it still hangs: that is a real bug in the ai-devops toolkit — file it
     against `popcre/ai-devops` (this session could not, being in a scope
     freeze). Then satisfy the same question the direct way: confirm no
     `popcre/shared-db` issue carries a claim from session
     `ses_ffe5e50e3fcc6ffe7zIUPMLZiw`, and confirm the session dispatched no
     sub-agents. Both are already true for this session (see §3/§9) — this is
     the formal receipt, not new information.
   - Do **not** write a substitute checker. The rule is supported reviewed
     installation, not a self-written replacement.

2. **(Optional, separate work) fix the broken documentation links** so
   `ai-doc-safety` passes on `https://github.com/u2giants/theoracle` again.
   Two categories:
   - `DECISIONS.md` — the two lines naming `packages/ai/src/providers/…`
     adapter files that no longer exist.
   - `HANDOFF.d/*.md` — several files naming deleted `plan_*.md` /
     `docs/research/*.md` targets. **Do not edit another session's handoff file
     for content.** Either fix only the dead link targets where the handoff is
     yours to retire, or leave them and say so.
   *You'll know it worked when*
   `"C:\Program Files\Git\bin\bash.exe" <repo>/../ai-devops/bin/ai-doc-safety`
   prints `public boundary and local Markdown links hold on …` and exits 0.

3. **(Optional, separate work) sweep the remaining stale Oracle 2 doc
   mentions.** Already declared out of scope on issue #431:
   `docs/agents/04-repository-structure.md` ("migrate/seed scripts") and
   `docs/agents/08-data-model-and-external-identifiers.md` (describes `settings`
   rows and `/admin/settings`, both removed).
   *You'll know it worked when* neither file mentions a table the live catalog
   does not have (§5c).

## 7. Constraints and gotchas in force

- **Never push directly to `main`.** Branch, open a PR, let checks decide.
- **Albert does not merge — the AI does**, except DesignFlow or a PR Albert says
  he will review first.
- **No AI reviewer approval is required for a database write** (owner ruling
  2026-10-14). Every other gate stands: task declaration, class escalation,
  target identity proof, branch + PR, the canonical migration runner, and live
  proof.
- **Prove which database you are pointed at immediately before every write.**
  Host, user, database name, and project ref — never the password.
- **Secrets never enter chat, arguments, output, logs, or commits.** Use
  `1password_op_run` with `op://` references in env values only.
- **Do not edit another session's `HANDOFF.d/` file**, and do not rewrite the
  root `HANDOFF.md` (it is a static pointer, `handoff-pointer: v1`).
- **Canonical checkouts are landing-only.** Do the work in your own worktree.
- **Do not `git clean` or `git checkout --` over unreviewed work.**
- **Concurrency:** other agents work these repos. Stage only your own files.
- **Any `*.sql` change escalates the task class to `shared-db`** — see §5f.

## 8. Access and environment

- **Machine:** Windows, hostname `edge-dev`. Git for Windows is at
  `C:\Program Files\Git\bin\bash.exe`. WSL is **not** installed; the bare `bash`
  command is the Windows Store stub and does nothing useful.
- **Session working directory `D:\repos\oracle` is NOT a git repository.** It is
  a scratch folder holding only `.playwright-cli/` and an eval draft. Do not run
  repo commands from there.
- **Repository checkouts:** the canonical checkout of
  https://github.com/u2giants/theoracle is `D:\repos\theoracle`. Worktrees live
  under `D:\repos\theoracle-worktrees\`. (Machine-local paths are given here
  only because the next session may need to find the checkout on this machine;
  all *file content* references above are GitHub URLs.)
- **GitHub CLI (`gh`) is authenticated** as `u2giants`.
- **1Password MCP is connected** (vault `vibe_coding`, vault id
  `pimcaogmxxzoafh7lsluj6uxkq`). Oracle production database credentials live in
  item id `qcuyabwseaptvuzvtjejffi2ou`, titled
  `Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, eqccjfbyrywsqkxxpjvg)`.
  Use field `oracle_session_pooler` as `DIRECT_URL` for migrations. **Do not**
  use item `gt537vxthxmeva64lfqku4mo6q` — that is the retired `oracle.old`
  project `vokucjpanhvqunimlvsp`. Never print either value; pass them only as
  `op://` references through `1password_op_run`.
- **Managed tool runtimes** are available via `$MIMO_PYTHON`, `$MIMO_NODE`,
  `$MIMO_RIPGREP_PATH`, etc.
- **ai-devops toolkit** is installed (launchers under
  `C:\Users\ahazan\.local\bin\`); its checkout is at `C:\repos\ai-devops` and
  `D:\repos\ai-devops`.

## 9. Open questions and risks

- **`ai-shared-db-closeout-check` hangs (2026-11-06).** Cause unknown. Risk: the
  wrap-up standard cannot produce its formal zero-claims receipt for any session
  on this machine until it is fixed. Substantively this session holds no claim —
  it never issued a single command against `popcre/shared-db`, never opened or
  claimed a shared-db issue, and dispatched **zero** sub-agents (only the `task`
  tracker was used). The gap is the receipt, not the ownership.
- **`ai-housekeeping` prints nothing (2026-11-06).** Exit 0, zero bytes, from
  inside the repo; `--help` is fine. Risk: housekeeping candidates may be
  invisible on this machine. Unknown whether there are any.
- **`ai-doc-safety` is red on this repo (2026-11-06), pre-existing.** Risk: the
  documented prose-only fast-merge path is unavailable until it is fixed (§5e).
- **Do not delete `packages/db/migrations/sql/99_vector_indexes.sql`**
  (2026-11-06 decision). See §5b. It is dead code kept for a safety gate.
- **`packages/db/migrations/sql/40_employee_identities_data.sql` becomes live
  again if `employees.auth_user_id` is ever re-added** (2026-11-06 observation).
  See §5g. It deletes an employee row.
- **Clock readings were inconsistent early in this session** (2026-11-06). See
  §4 item 7. Timestamps in the PR body and issue comment may be hours off; the
  commit/PR/live-proof evidence is sound.
