# R2 correction: F0, F1, F2 and F2b are built and green. UNCOMMITTED. F3 is next.

Status: **OPEN. Albert authorized local implementation (2026-08-12) and the bounded-object design
change (2026-08-13). All local gates are green. The work is UNCOMMITTED and at risk. Production hard
stop is unchanged: no deploy, no second gate, no database change, no push.**

Plan: [`../plan_r2_source_bound_final_record_correction.md`](../plan_r2_source_bound_final_record_correction.md) — read its `## Drift log` first, it is the live record.

## 0. Decisions only Albert can make

### Blocking

Two questions were asked at the end of the session and **were not answered**. Ask them again in one
message before doing anything else:

1. Commit the current work locally to `main`, unpushed? Recommendation: **yes.** Roughly 500 lines of
   verified, green work currently exist only in the working tree. A local commit is reversible and
   reaches nobody. Leaving it uncommitted is the larger risk.
2. Add `.ai/reviews/` to `.gitignore`? Recommendation: **yes.** ~300 untracked AI review artifacts sit
   there now, including files that quote source. One `git add -A` commits them. The Grok wrapper also
   refuses to save reviews while that path is committable.

### Already settled, do not re-ask

- 2026-08-12: local implementation of the whole plan is authorized.
- 2026-08-13: correcting the **expected-object boundary** inside
  `validateResponsibilityFieldFidelity` to the plan's locked section 8 rule is authorized, and is
  classified as a correction rather than a forbidden weakening. Everything else in that validator
  stays frozen.
- Standing: no deploy, no second production gate, no bake-off, no DB/schema/secret change, no push,
  no change to the frozen matcher, answer key, threshold, budgets, model, route, or fail-safe flags.
- Rows 16, 24 and 26 are honest negative controls and must stay failing.
- Landing (commit + push + CI) is a separate owner decision that comes after F6.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed business knowledge system. Employees
upload company documents and ask questions. Trigger.dev workers cut each document into chunks, then
into "source duty spans" (seeds), show each seed's exact snippet to a model, have the model fill in
role / action / object / trigger, validate every field against that snippet, and save a reviewable
source map. Business-model merge, apply and serving are separately gated and are OFF.

- Repo `u2giants/theoracle`; checkout `C:\repos\oracle`; branch `main`.
- TypeScript, pnpm, Turbo, Next.js 16, Trigger.dev, Drizzle, Supabase. Node 24.
- Web `https://oracle.designflow.app`; workers `proj_wgpzsvhmsopqhvwqaycn`; DB `eqccjfbyrywsqkxxpjvg`.
- Rules and validators: `apps/workers/src/lib/responsibility-reader.ts`.
- Orchestration: `apps/workers/src/lib/source-workflow-read.ts`.
- Test suite being extended: `apps/workers/src/__verify__/r2-responsibility-reader.ts`.
- **Never edit:** `apps/workers/src/lib/responsibility-answer-key.ts` and
  `apps/workers/src/__fixtures__/licensed-team-responsibilities-v1.json`.

## 2. What we set out to do, and why

The one authorized production run on 2026-08-11 scored **19/30** against a frozen 27/30 gate. A
separate verifier shows the exact snippets support 28/30, so the duties are visible; the failures are
in the final stored field wording. Eight rows were judged correctable (5, 14, 15, 17, 19, 20, 23, 29)
and three are negative controls (16, 24, 26). 19 + 8 = 27, exactly the gate. This session executed
F0, F1, F2 and a new phase F2b.

## 3. Current state

**Green, all verified this session by running them:**

- `pnpm --filter @oracle/workers typecheck`, `@oracle/ai typecheck`, `@oracle/engines typecheck`.
- `verify:r2-responsibilities` → prints `19/30 reproduced under field-aware-v3` and
  `R2 final-record correction contract: 16/16 cases passed`.
- `verify:r2-pinned-inventory` → still 28/30, unsupported rows 16 and 26.
- `verify:source-workflow-read`, `verify:r0-reader-validator`,
  `verify:document-ingestion-fallback`, `@oracle/ai verify:r2`, `@oracle/ai verify:workflow-read`,
  `@oracle/engines verify:macro`, `verify:macro-first`, `verify:r1-cross-shape`,
  `verify:r2-responsibilities` — all pass. `git diff --check` clean.

**What was built:**

- **F0** freezes the production residual at 19/30 inside the suite, pins the eleven misses, the eight
  eligible rows and the three negative controls, and freezes the fixture SHA, answer-key version,
  matcher version, threshold, reader and post-pass budget defaults, and the three fail-safe flags.
- **F1** is now 16 invented-source cases defining the correction contract.
- **F2** is `correctResponsibilityFinalRecord` in `responsibility-reader.ts`, handling inflected
  actions, absorbed conditions, dropped named tokens and over-wide objects, with loud refusals.
- **F2b** is `boundedSourceObject` in the same file: the single definition of where a duty's object
  ends, now used by the fidelity qualifier-loss check, `deterministicInventoryRecord`, and the
  corrector. It returns the cut text and labels it `condition` or `clause`. A cut **condition** must
  appear verbatim in `trigger` or fidelity fails with `condition_not_preserved_in_trigger`. A cut
  **clause** belongs to a different seed and is deliberately not demanded.

**Not done:** F3, F4, F5, F6.

**Git:** branch `main`, one local commit ahead of origin (`f68bd36`, F0 + F1, deliberately unpushed).
Three files are modified and **uncommitted**: `apps/workers/src/lib/responsibility-reader.ts`,
`apps/workers/src/__verify__/r2-responsibility-reader.ts`, and the plan. Preserve the large untracked
`.ai/`, `.playwright-cli/`, `detail-current.png` and `rfq-before.png` set; it predates this session.

## 4. Everything we tried that did NOT work

1. **Delegating F2, F3 and F4 to GLM 5.2 in one job.** It ran 41 minutes, hit its turn deadline, and
   produced ZERO changes (`timed-out-no-changes`). Cause: too much scope and a brief that invited it
   to read the plan and handoff first. A re-scoped single-function brief with "start writing within
   10 minutes" succeeded. **Lesson: give a delegate one file and one function, and point it at the
   tests as the spec.**
2. **GLM's first F2 draft contained an acceptance-rule bypass.** It accepted a correction whenever a
   condition had been moved to `trigger`, even when fidelity regressed. Removed. It would only have
   moved the failure to `validateResponsibilityRead` downstream.
3. **GLM reported the suite was blocked by a pre-existing failure. It was not, on this machine.** The
   real cause was line endings: `core.autocrlf=true` with no blanket `text eol=lf`, so a FRESH clone
   on Windows gets CRLF and every multi-line source-text literal silently stops matching. That
   aborted GLM's run at the pre-existing frozen-budget guard. Both that guard and the F0 guard now
   normalize line endings. **CI never caught this because Linux checkouts are LF.**
4. **My own "record-level completeness" proposal was wrong and was rejected after review.** It would
   have replaced "nothing missing from `object`" with "object + trigger + audit jointly cover the
   span". Grok 4.6 refuted it: `A ⊆ object` is strictly STRONGER than `A ⊆ (object ∪ trigger ∪
   audit)`, so it was a weakening described as a broadening, and it was gameable because the frozen
   matcher never reads `trigger`. Do not revive it.
5. **My claim that row 5 shares row 17's cause was wrong.** Row 5's object carries a different duty's
   nouns and misses a required token. Only row 17 was affected by the boundary conflict.
6. **My F1 case 13 asserted the opposite of reality** and had to be rewritten. It assumed the
   absorbed-condition shape failed fidelity. It passed. GLM found this.
7. Everything earlier sessions rejected still stands: hidden source-prefix owner lookup, borrowing
   headings or neighbouring duties, matcher aliases, weaker negation, higher budgets, prompt-only
   cleanup, a general English lemmatizer, and another production gate.

## 5. Root causes and key findings

- **The core finding.** The span was doing two jobs. It is the right unit of EVIDENCE, but
  `sourceObjectText` also made it the definition of the ANSWER: the expected `object` was everything
  from the first duty verb to the end of the span. That contradicted the plan's own goal (smallest
  complete record, conditions in `trigger`) and its own locked section 8 boundary rule. F2b corrects
  it. The same helper also BUILT objects at `deterministicInventoryRecord`, so the wrong definition
  was stored as well as enforced.
- **The `condition` versus `clause` distinction is load-bearing.** A condition belongs to this duty
  and is required in `trigger`. A neighbouring duty belongs to another seed and must never be pushed
  into this record's `trigger`. Collapsing them recreates the junk-drawer failure that sank the
  record-level alternative. F1 case 16 pins this.
- **Anti-invention is untouched** and still measures against the FULL span, so narrowing the expected
  object cannot let invented words through.
- `validateResponsibilityFieldFidelity` already stems the returned action, so an inflected action
  passes fidelity and is rejected only by the frozen matcher. Acceptance is therefore "fidelity does
  not regress AND the named defect is gone", never "fidelity now passes".

## 6. Exact next steps

1. **Ask Albert the two unanswered questions in section 0.** Success: both answered before any other
   action.
2. **Build the 19/19 production-replay harness. This is the hard gate and it has NOT been run.** No
   local replay of the 93 stored production records exists. Suites passing is supporting evidence,
   not proof. Success: a check that replays the recorded production records through the current code
   and shows all 19 previously-matching rows still match under the unchanged matcher. **If any of the
   19 regress, STOP and report. Do not tune the boundary rule to suit them.**
3. **Then F3**, the late-completion acceptance seam. Keep `lateResidualResponsibilitySeeds` and
   `runLateResponsibilityCompletion` as the only late path; insert F2 between each returned late
   candidate and the existing `validateResponsibilityRead` call at
   `source-workflow-read.ts:3449-3470`. Success: no new dispatch, reservation, model call or retry
   appears anywhere in the diff.
4. **Then F4, F5, F6** as written in the plan. F6 must specifically audit F2b: only the
   expected-object boundary moved; anti-invention, polarity, owner and action-family checks are
   byte-for-byte unchanged; exactly one boundary helper exists; a cut tail missing from `trigger` is
   rejected; no acceptance-rule exemption was reintroduced.
5. **Row 5 is the live unknown.** A boundary fix cannot invent its missing token. If it turns out not
   to be honestly recoverable, the ceiling is 26/30 — that is a stop-and-ask, not a reason to loosen
   anything.
6. **At the end of every phase**, append drift to the plan's `## Drift log`. Several entries already
   exist; follow that format.

## 7. Constraints and gotchas in force

- Local only. No deploy, second gate, bake-off, Vercel action, DB, schema, migration or secret change.
- Never edit the frozen matcher, the answer-key fixture, the 27/30 threshold, the budgets
  (40 / 500,000 / $10 / 1 / 4 and post-pass 1 / 5 / 1), the model, the route, or the three
  `business_model_*_enabled` flags. F0 asserts all of these; breaking F0 means a rule was broken.
- Only the expected-object BOUNDARY inside fidelity may change, and only to the section 8 rule.
  Anti-invention, polarity, owner match, action family and multi-verb rejection stay frozen.
- Every new test uses INVENTED source text. Copy the F1 style (`Fleet Office`, `Depot Lead`,
  `route packets`, `QA1 photos`). Never put a licensed-document or answer-key term in a test or in
  production code.
- `main` only. Stage exact paths, never `git add -A` — the untracked `.ai/` pile would come with it.
- Before any commit, confirm `git var GIT_COMMITTER_IDENT` is
  `Albert Hazan <u2giants@users.noreply.github.com>`.
- **`HANDOFF.d/` holds 12 open files, far above the limit of 5.** Do not delete or edit another
  session's file. A dedicated retention cleanup is overdue.

## 8. Access and environment

- Windows 11 host `al8960ofc`; PowerShell 7; repo `C:\repos\oracle`; branch `main`.
- This session ran from the worktree `C:\repos\oracle-worktrees\repo-handoff-docs-c87db2` but made
  every edit in the primary checkout `C:\repos\oracle`, which the plan requires.
- pnpm and Node 24 work. `gh` is authenticated, needed only for a later landing.
- Licensed pinned fixture: `Z:/Documentation/company process - Oracle/Licensed Team Responsibilities 2 - tagged.txt`,
  overridable with `R2_PINNED_FIXTURE_PATH`. Reachable on this machine. Never copy its contents into
  the repo, a commit message, an issue, or any outside model. `verify:r2-responsibilities` does not
  need it; `verify:r2-pinned-inventory` does.
- Delegates: `ai-glm` (Windows shim on PATH) for GLM 5.2;
  `bash /c/repos/ai-devops/bin/ai-grok-review` with `HOME=/c/Users/ahazan2` for Grok — it is NOT on
  PATH on this machine and must be called by full path. `AI_GROK_MODEL=grok-4.6` selects 4.6; the
  wrapper otherwise pins 4.5.
- Secrets live only in 1Password vault `vibe_coding`. None were needed or handled this session.

## 9. Open questions and risks

- **Largest risk: the 19/19 preservation gate has not been run.** F2b changed the deterministic
  builder that helped produce those rows. Treat the change as unproven until that replay exists.
- **Second risk: the work is uncommitted.** A crash or a careless `git checkout` loses it.
- Row 5 may not be honestly recoverable, which would cap the score at 26/30.
- Watch for anyone reintroducing an acceptance-rule exemption, or widening the condition-cue list
  beyond the locked section 8 cues, to make a stubborn row pass.
- Local gates prove source-bound correctness, not live readiness. Any future production run needs a
  new written plan and a new explicit owner authorization.

## Handoff self-audit

Passed. A developer with zero knowledge of this app, this chat, or the R2 history can act on this
file alone. Section 1 names the system and every file that matters, including the two that must never
be edited. Section 3 states exactly what is green (with the commands actually run), what was built,
and what is uncommitted. Section 4 records all seven things that failed this session, including two
of my own errors and one delegation that produced nothing, with their causes, so none is repeated.
Section 5 carries the core finding and the one distinction a future session is most likely to
collapse. Section 6 gives ordered next steps, each with a success test and an explicit stop rule, and
names the gate that has NOT been run so nobody mistakes green suites for proof. Section 0 isolates the
two unanswered owner questions and marks everything already settled so nobody re-asks. Sections 7 to 9
carry the frozen limits, the exact delegate invocations, the licensed-data rule, and the honest risks.
No sentence in sections 1 to 9 needs Albert's judgment unless it also appears in section 0.
