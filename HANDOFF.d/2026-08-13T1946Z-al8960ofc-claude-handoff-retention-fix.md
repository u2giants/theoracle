# HANDOFF.d retention: 9 superseded files retired, root cause fixed in AGENTS.md

Status: **DONE and pushed. This file is kept for ONE reason — see §0b.** The cleanup and the
documentation fix are complete and on `origin/main` at `fcb839d`. Nothing here is waiting on
anybody.

## 0. Decisions only Albert can make

### Blocking

None. Nothing in the Oracle product was touched.

### Recoverable

None. Both questions this file originally carried were answered by Albert on 2026-08-13:

1. Keep the 185 KB legacy archive for now — **decided, and the deletion trigger is now recorded
   durably in `AGENTS.md` §3a** as a standing exception, not here. Delete the archive in the same
   commit that lands a plan document holding its GAP/REL register.
2. Push — **done.** `origin/main` is `fcb839d`.

## 0b. Why this file still exists — read this, then retire it

The predecessor handoff `2026-08-13T1940Z-al8960ofc-claude-r2-bounded-object-f2b.md` is still OPEN
(its F3 work is unfinished), so it was correctly NOT deleted. But **its §0 asks two blocking
questions that are already answered**, and editing another session's handoff is forbidden. If this
file disappears, the next R2 session will read that stale §0 and put two settled questions to Albert
for no reason.

So this file's only remaining job is to carry those two answers, plus the retired-file index in
§3a:

1. "Commit the F0–F2b work locally?" — **already committed AND pushed.** `c6dbf81`
   ("fix(r2): bound the expected object to the locked field-boundary rule") is on `origin/main`.
   That work is not at risk in a working tree.
2. "Add `.ai/reviews/` to `.gitignore`?" — **already done.** `.gitignore:72`. 344 untracked review
   artifacts are there and cannot be swept up by `git add -A`. Ten review files were committed
   before that line was added and remain tracked; leave them, they are already in history.

**Retire this file when the F2b workstream's successor lands** — i.e. the session that finishes R2
F3 deletes BOTH the F2b file and this one in the same commit. At that point the stale §0 is gone
and nothing here is load-bearing.

### Already settled, do NOT re-ask

- The R2 production hard stop is unchanged: no deploy, no second production gate, no database or
  schema change, no bake-off. This session changed none of that.
- Rows 16, 24 and 26 of the R2 fixture remain honest negative controls.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed business knowledge system. Employees
upload company documents and ask business questions. Trigger.dev workers cut each document into
chunks and then into exact "source duty spans", have a model fill in role / action / object /
trigger for each span, validate every field against that exact snippet, and save reviewable,
source-proved business knowledge.

Repo: `C:\repos\oracle`, GitHub `u2giants/theoracle`, branch `main` (main-only, no feature
branches). TypeScript monorepo on pnpm + Turbo. Web app: `https://oracle.designflow.app` (Vercel).
Workers: Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`. Data: Supabase project
`eqccjfbyrywsqkxxpjvg`.

## 2. What we set out to do this session, and why

`HANDOFF.d/` held **12 open files against a documented limit of 5**, nine of them from Codex
sessions going back to 6 August. Albert asked for two things: clean it up, and find out why it got
that dirty so the cause could be fixed.

This matters because of how the folder is defined: **a file's presence means the workstream is
OPEN.** There is no status field and no archive folder — presence *is* the status. Twelve files
means a fresh session is told there are twelve live workstreams and must read roughly 300 KB of
nine-section essays before it may start. Nine of those twelve were the same single workstream.

## 3. Current state — what is true right now

`HANDOFF.d/` now holds **4 files**, under the limit of 5:

| File | Why it stays |
| --- | --- |
| `2026-08-06T1510Z-t16-codex-legacy-migrated-handoff.md` | Historical archive; sole full text of the open GAP/REL register. Its deletion trigger is a standing exception in `AGENTS.md` §3a. |
| `2026-08-06T1510Z-t16-codex-project-status-closeout.md` | Project-wide status and the owner-gated GAP/REL decisions. Not part of the R2 chain. |
| `2026-08-13T1940Z-al8960ofc-claude-r2-bounded-object-f2b.md` | The live R2 workstream. F0–F2b are green; **F3 is the next step.** |
| `2026-08-13T1946Z-al8960ofc-claude-handoff-retention-fix.md` | This file. |

Documentation changes made (all documentation-only, no product code):

- `AGENTS.md` — added **§3a "Handoffs — `HANDOFF.d/` and the successor rule"**. This is the fix.
- `AGENTS.md` §3 documentation-map rule and the five-minute orientation list now point at
  `HANDOFF.d/` instead of a root `HANDOFF.md`.
- `AGENTS.md` §15 "Pending work" — canonical ownership now reads `HANDOFF.d/`, not `HANDOFF.md`.
- `AGENTS.md` end-of-file line that told future sessions to "create `HANDOFF.md` at the repo root"
  — that instruction was retired months ago by the `HANDOFF.d/` migration and is now corrected.
- `CLAUDE.md` line 11 — same correction, plus a pointer to §3a.

Both commits are pushed; `origin/main` is `fcb839d` and the tracked tree is clean. Pre-existing
untracked scratch was left alone: `.playwright-cli/`, two root `.png` files, six
`.ai/gap*-*.err|.out` logs, and two `.ai/run-gap10-*.ps1` scripts. None of it is from this session
and none of it is tracked; a `.gitignore` sweep for it is a reasonable small follow-up.

Nothing was deployed. No production run, no database change, no secret used.

## 3a. The nine retired files, and how to read any of them

Deleted under the **successor rule** (see §5). Git history keeps every word. To read one:

```bash
git show <sha>:HANDOFF.d/<filename>
```

| Added in | File |
| --- | --- |
| `3eca8f9` | `2026-08-10T1744Z-al8960ofc-codex-r2-inventory-p3.md` |
| `fce082d` | `2026-08-10T1850Z-al8960ofc-codex-r2-inventory-p4.md` |
| `559dd6a` | `2026-08-10T2244Z-al8960ofc-codex-r2-p5-p6-blocker.md` |
| `0ea1180` | `2026-08-11T0147Z-al8960ofc-codex-r2-p5-honest-score.md` |
| `85dab98` | `2026-08-11T1306Z-al8960ofc-codex-r2-owner-correction-plan.md` |
| `62330bd` | `2026-08-11T1342Z-al8960ofc-codex-r2-owner-correction-stop.md` |
| `62330bd` | `2026-08-11T1522Z-al8960ofc-codex-r2-numbered-inner-actor.md` |
| `26b60cd` | `2026-08-11T1721Z-al8960ofc-codex-r2-production-hard-stop.md` |
| `8679a05` | `2026-08-11T1810Z-al8960ofc-codex-r2-final-record-plan.md` |

All nine are **one workstream**: R2, the source-span inventory reader. They are the phase-by-phase
baton for `plan_r2_source_span_inventory_reader.md` (P0–P8) and then
`plan_r2_source_bound_final_record_correction.md` (F0–F6). Each was superseded by the next.
The narrative they contain, in one line each, so nothing is lost to a reader who never opens them:

P3/P4 built the source-bound seed inventory and scheduling. P5/P6 hit a proof blocker: a verifier
fallback was searching source text *before* the model-visible span for an owner, faking 27/30. With
that removed the honest score was **16/30**. A bounded owner-context correction reached 26/30, and a
numbered-inner-actor correction reached **28/30 locally**. The single authorized production gate
then scored **19/30** — a binding hard stop — which produced the final-record correction plan that
the live F2b handoff is now executing.

Every one of the nine is cleared by the three-part successor test:

1. **Committed and pushed?** Yes. Each file's own status line names its commit, and every SHA in
   the table above is an ancestor of `origin/main` (`fcb839d`).
2. **Open obligations carried forward?** Yes. The R2 technical state lives in the two plan documents
   and in the live F2b handoff. The legacy GAP/REL decisions that the P4 file re-listed are recorded
   in full in the two kept `2026-08-06` files.
3. **Any decision or dead end that exists nowhere else?** No. The rejected approaches (verifier
   prefix lookup, answer-key aliases, wider completion spans, larger budgets, model swaps) are all
   recorded in the plan documents' locked-constraint and drift sections, which is where a fresh
   implementer actually looks.

## 4. What we tried that did NOT work

- **First instinct: just delete the oldest files by date.** Wrong, and dangerous. Age is not
  evidence. Two of the three oldest files (`2026-08-06`) are the ones that had to be KEPT — they
  hold the project-wide GAP/REL register — while much newer 11 August files were the ones safe to
  retire. Sort by *workstream and supersession*, never by timestamp.
- **Considered writing an `ARCHIVE/` subfolder or adding a `Status:` field to each file.** Rejected.
  Both re-introduce the exact failure being fixed: they let a finished file keep existing, so nobody
  ever removes anything and the folder grows forever. "Presence = OPEN" only works if presence is
  the *only* signal. Git history is already the archive.
- **Considered editing the stale §0 questions inside the F2b file** once it was clear both had been
  answered. Rejected — editing another session's handoff is the concurrency data-loss bug the whole
  `HANDOFF.d/` layout exists to prevent. The answers went in §0b of THIS file instead.
- **Considered fixing only the shared skill in `ai-devops`.** Insufficient. The rule was already
  correct there (see §5) and it still did not fire, because sessions in this repo are routed by
  `AGENTS.md` and most never load that skill.

## 5. Root cause — why it got this dirty

Two causes, and the second is the real one.

**Cause 1 (mechanical): one workstream, nine batons.** R2 was executed as an explicitly phased plan
— P0 through P8, then F0 through F6. The handoff standard says each session writes exactly one file.
So a nine-phase plan mechanically produces nine handoff files even when it is one continuous piece
of work with one owner. The standard already anticipates this and answers it with the **successor
rule**: the session that finishes the NEXT phase deletes the PREVIOUS phase's file, in the same
commit. That rule never fired here. Not once, across nine sessions.

**Cause 2 (the actual root cause): the successor rule was never visible in this repository.**

- The rule lives in `templates/system/handoff-standard.md` in `u2giants/ai-devops`, and in the
  `handoff-writer` skill.
- `AGENTS.md` is this repo's canonical router — it is the file every session is told to read first.
  Before this session, `AGENTS.md` contained **zero occurrences of the string `HANDOFF.d`**. It
  still described the retired single-file model ("create `HANDOFF.md` at the repo root and delete it
  once the work is finished"), which had been superseded by the 6 August migration.
- So a Codex session that read `AGENTS.md` (as instructed) and wrote its handoff without loading the
  `handoff-writer` skill saw the *write* half of the layout — inferred from the folder it was
  looking at — and never saw the *retention* half. It correctly refused to touch other sessions'
  files, because "never edit another session's file" is the memorable part of the rule and the
  successor exemption is the forgettable part. Every session did exactly what it was told. The
  folder still grew every time.
- **The threshold warning is only a warning, and it is only mechanical in `ai-devops`.**
  `tools/context-audit/context-audit.py` prints `open handoffs: N` — but that tool runs against the
  `ai-devops` repo, not against `theoracle`. Nothing in this repo counts the files. The count
  crossed 5 on 10 August and nobody was told for three days.

Summary in one sentence: **a rule that exists only in a shared template, and is enforced only by a
tool that does not run on this repo, is not a rule that this repo has.**

## 6. Exact next steps

1. **Resume the live R2 workstream at F3** per
   `2026-08-13T1940Z-al8960ofc-claude-r2-bounded-object-f2b.md` and the plan's `## Drift log`.
   Do NOT re-ask its two §0 questions — see §0b of this file. Success: F3 gates green.
2. **When you finish F3, delete the F2b file AND this file** in the same commit. That is the
   successor rule working, and it is what clears the stale §0 described in §0b. If it does not
   happen, the fix in §5 did not take and the mechanical check in §9 is needed.
3. **Optional, recommended:** move the GAP/REL register out of the 185 KB archive into a real plan
   document with a STATUS table, then retire the archive. Success: `HANDOFF.d/` holds only live
   session batons.

## 7. Constraints and gotchas

- **Never rewrite root `HANDOFF.md`.** It is a static pointer with a `handoff-pointer: v1` marker
  comment. Never edit another session's `HANDOFF.d/` file either — the successor rule permits
  *deleting* a proven-landed predecessor, never editing one.
- **Presence = OPEN.** Do not add a `Status:` field, an index file, or an archive folder as a way to
  keep a finished file around. Delete it; git history is the archive.
- **`git rm`, not a plain delete**, so the removal is staged in the same commit as the work.
- Prefer `git add <specific-paths>`. `.ai/reviews/` is gitignored but 344 untracked files live
  there; a careless `git add -A` is still a bad habit in this repo.
- **Worktrees are a live trap in this repo, and they cost real time in this session.** The session
  opened in `C:\repos\oracle-worktrees\handoff-file-cleanup-0e58c7`, but this repo is main-only, so
  every edit was made in the primary checkout `C:\repos\oracle`. Several verification `grep`s then
  silently ran against the WORKTREE — an older commit — and appeared to prove the edits had been
  lost. They had not. **Always `cd` to the repo you mean, and print `pwd` and `git log -1` before
  trusting verification output.** Both stale worktrees (`handoff-file-cleanup-0e58c7` and the
  abandoned `repo-handoff-docs-c87db2`) and their branches were removed at the end of this session;
  `git worktree list` now shows only `C:\repos\oracle`. Windows kept two empty directory shells
  under `C:\repos\oracle-worktrees\` because the session was running inside one; they are
  unregistered from git and safe to `rm -rf` once no session is open there.

## 8. Access needed

Nothing beyond a normal checkout of `C:\repos\oracle` and `git`. No secrets, no cloud credentials,
no database access were used or are required to repeat this work.

## 9. Risks and what to watch

- **The fix is documentation-only, so it is advisory.** §3a will work only if sessions read
  `AGENTS.md`, which they are instructed to. If `HANDOFF.d/` crosses 5 files again, escalate to a
  mechanical check: port `context-audit.py`'s `open handoffs: N` count into this repo as a CI step
  or a pre-commit warning. Do that only after the documentation fix has been given a fair trial —
  an audit that blocks a commit over paperwork teaches people to ignore audits.
- **A retired file is not a lost file, but only if the SHA is recorded.** §3a of this file is the
  index for the nine retired here. Future retirements should record the same thing in the retiring
  session's own file.
- **The R2 hard stop is unaffected by any of this.** Nothing here authorizes a deploy, a second
  production gate, or any database change.
