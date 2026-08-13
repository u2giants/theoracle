# R2 source-bound correction: F0 and F1 landed locally, F2 is next

Status: **OPEN. Albert authorized local-only implementation on 2026-08-12. F0 and F1 are complete
and verified. The working tree is UNCOMMITTED on purpose. F2 has not started. Production hard stop
is unchanged.**

Plan: [`../plan_r2_source_bound_final_record_correction.md`](../plan_r2_source_bound_final_record_correction.md)
Prior handoff: [`2026-08-11T1810Z-al8960ofc-codex-r2-final-record-plan.md`](2026-08-11T1810Z-al8960ofc-codex-r2-final-record-plan.md)

This file exists because the plan places a mandatory **Context cut point A** after F1: the next phase
must begin in a fresh session that re-reads the plan and confirms the diff is tests only. It is.

## 0. Decisions only Albert can make

### Blocking

- Nothing is blocking F2 through F5. Albert's 2026-08-12 authorization covers local implementation of
  F0 through F6. The next session should start F2 immediately without asking again.

### Already settled, do not re-ask

- 2026-08-12: local implementation of F0-F6 is authorized.
- 2026-08-12 and earlier: do NOT deploy, run a second production gate, change the database, weaken
  the verifier or the `field-aware-v3` matcher, restore hidden owner lookup, raise budgets, change
  the model or route, or enable merge/apply/serving.
- 2026-08-11: rows 16, 24 and 26 are honest negative controls and must stay unsupported. A change
  that "recovers" any of them has cheated.
- 2026-08-11: the 19/30 production result is honest and binding. No score exception was granted.
- Landing (commit + push + CI) is a SEPARATE owner decision that comes after F6. Do not commit.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed business knowledge system. Employees
upload company documents and ask questions. Trigger.dev workers segment documents, inventory duties,
complete missing fields with a configured model, validate the evidence, and save reviewable source
maps. Business-model merge and apply are separately gated and currently off.

- Repo: `u2giants/theoracle`; checkout `C:\repos\oracle`; branch `main`.
- Stack: TypeScript, pnpm, Turbo, Next.js 16, Trigger.dev, Drizzle, Supabase.
- Web `https://oracle.designflow.app`; workers `proj_wgpzsvhmsopqhvwqaycn`; DB `eqccjfbyrywsqkxxpjvg`.
- Rules: `apps/workers/src/lib/responsibility-reader.ts`.
- Orchestration: `apps/workers/src/lib/source-workflow-read.ts`.
- Verifier being edited: `apps/workers/src/__verify__/r2-responsibility-reader.ts`.
- Frozen matcher, never edit: `apps/workers/src/lib/responsibility-answer-key.ts`.
- Frozen answer key, never edit: `apps/workers/src/__fixtures__/licensed-team-responsibilities-v1.json`.

## 2. What we set out to do this session, and why

The single authorized production gate on 2026-08-11 scored 19/30 against a frozen 27/30 threshold.
A correction plan was written and independently reviewed. Albert read the handoff on 2026-08-12 and
authorized local-only implementation. This session executed the first two phases of that plan: F0
(freeze the residual boundary) and F1 (write the red tests that define the fix).

## 3. Current state

**Verified green:**

- `pnpm --filter @oracle/workers typecheck` — clean.
- `pnpm --filter @oracle/workers run verify:r2-pinned-inventory` — still 28/30, unsupported rows
  16 and 26. Unchanged by this work.
- Every pre-existing case in `verify:r2-responsibilities` still passes.

**Verified red on purpose:**

- `pnpm --filter @oracle/workers run verify:r2-responsibilities` now FAILS at the very end with
  `F1 correction contract is not satisfied: 13/13 cases failing. This is the expected state until
  F2 lands.` All 13 fail for one reason only: `correctResponsibilityFinalRecord` does not exist yet.
  This is the intended red state of a TDD phase, not a regression. Do not "fix" it by deleting tests.

**What was added, both in one file, `apps/workers/src/__verify__/r2-responsibility-reader.ts`:**

- **F0 block.** Reproduces the production residual as verifier-only records — one representative
  record per answer-key row, carrying each documented failure shape — and asserts it scores exactly
  19/30 under the unchanged matcher. Pins: the eleven missed rows; the eight correction-eligible rows
  5, 14, 15, 17, 19, 20, 23, 29; the three negative controls 16, 24, 26; the arithmetic 19 + 8 = 27;
  the frozen fixture SHA-256, answer-key version, matcher version and threshold; the reader budget
  defaults (40 calls / 500,000 tokens / $10 / 1 repair / 4 concurrency) and post-pass defaults
  (1 / 5 / 1); and the three fail-safe flags defaulting to false. It also proves each reproduced miss
  fails for its OWN documented reason by scoring each expected row against its own record in
  isolation.
- **F1 block.** 13 cases, all using invented source text, that define the F2 contract.

**Not done:** F2, F3, F4, F5, F6. No production code file has been touched at all.

**Git:** branch `main`, and the change is DELIBERATELY UNCOMMITTED. `git diff --stat` shows exactly
two files: the verifier (+686) and the plan (+41/-3). Untracked `.ai/`, `.playwright-cli/`,
`detail-current.png` and `rfq-before.png` predate this session and must be preserved.

## 4. Everything we tried that did NOT work

1. **F0's first attempt asserted per-row failure reasons off the whole-residual score.** It failed
   with `row 16 fails because the owner is not source-visible: true !== false`. Cause: when a row is
   unmatched, `scoreResponsibilityAnswerKey` reports the BEST candidate across every actual record,
   which can belong to a completely different duty. Row 16's best candidate was some other
   `Licensed Team` record, so `roleExact` was true. Fix: score each expected row against its own
   reproduced record in isolation (`r2RowFailureEvidence`). If you add row-level reason assertions
   later, use that helper — do not read `evidence[i]` from a full-set score.
2. **F1 case 13 originally asserted that the inflected record fails field fidelity today.** It does
   not. This is the most important finding of the session; see section 5.
3. **A static `import { correctResponsibilityFinalRecord }` in F1 was rejected before writing it.**
   It would break `tsc` and kill the whole suite at import time, so no pre-existing case could be
   shown green — violating F1's own gate. F1 resolves the helper with `await import` instead.
4. Everything the prior handoffs rejected still stands: hidden source-prefix owner lookup, borrowing
   headings or neighbouring duties, matcher aliases, weaker negation, higher budgets, prompt-only
   cleanup, a general English lemmatizer, and running another production gate.

## 5. Root causes and key findings

**The finding that changes F2 (also written into the plan's drift log):**
`validateResponsibilityFieldFidelity` already stems the returned action through `dutyVerbsInText`.
So a record with the inflected action `provides` **passes field fidelity today**. The inflection is
rejected only by the frozen `field-aware-v3` matcher, which compares action tokens literally
(`responsibility-answer-key.ts:81-93`). Rows 19 and 29 therefore never failed fidelity.

Consequence: the plan's section 9 wording for F2, "re-run existing fidelity validation, accept only
strict improvement", cannot be implemented as "accept when fidelity flips from fail to pass" — for
five of the eight eligible rows there is nothing to flip. **F2 must accept a correction when
fidelity does not REGRESS and the named defect is provably gone.** Only the absorbed-condition shape
(row 17) fails fidelity today. F1 case 13 pins both halves of that rule.

Other findings:

- Two of the four defect families are pure action wording (rows 19, 29), one is a lost named
  artifact token (row 14), one is an over-wide or incomplete object (rows 5, 17), and three rows
  (15, 20, 23) produced no final record at all and belong to the F3 late-completion seam.
- The frozen budgets and fail-safe flags are NOT exported constants. They are inline defaults inside
  `loadSourceReaderBudgetLimits` and `loadResponsibilityPostPassBudgetLimits` in
  `source-workflow-read.ts` and in `packages/db/src/seed.ts`. F0 freezes them by asserting their
  exact declaration text. If you refactor those functions, F0 will fail loudly by design — update
  the frozen strings, do not delete the assertion.
- `verify:r2-responsibilities` deliberately does NOT require the licensed pinned source. F0 checks
  the real file's SHA only when `R2_PINNED_FIXTURE_PATH` (or the default `Z:` path) is reachable, so
  CI stays green and no licensed text enters the repo. `verify:r2-pinned-inventory` still requires it.

## 6. Exact next steps

1. **Start F2.** Export `correctResponsibilityFinalRecord` from
   `apps/workers/src/lib/responsibility-reader.ts`. The signature and every reason code are already
   pinned by F1; read the F1 block first and treat it as the specification. Reuse the existing
   `stemDutyVerb` at `responsibility-reader.ts:430` — the plan forbids a second stemmer. Success:
   `verify:r2-responsibilities` prints
   `R2 final-record correction contract: 13/13 cases passed` and `typecheck` is clean.
2. **Then optionally switch F1 to a static import** of the helper now that it exists, and delete the
   `r2CorrectOrThrow` shim. Success: suite still 13/13.
3. **Then F3**, the late-completion acceptance seam. Insert F2 between each late candidate and the
   existing `validateResponsibilityRead` call at `source-workflow-read.ts:3449-3470`. Keep
   `lateResidualResponsibilitySeeds` and `runLateResponsibilityCompletion` as the only late path.
   Success: no new dispatch, reservation, call or retry appears anywhere in the diff.
4. **Then F4, F5, F6** exactly as written in the plan. F5's command list is verbatim in the plan and
   none of it may be skipped.
5. **At the end of every phase**, re-read all later phases and append any drift to the plan's
   `## Drift log`. Two entries already exist from this session; follow that format.
6. **Do not commit.** Landing is a separate owner decision after F6.

## 7. Constraints and gotchas in force

- Local only. No deploy, no second production gate, no bake-off, no Vercel action.
- No database, schema, migration, secret or Supabase change. No production read is needed.
- Never edit `responsibility-answer-key.ts`, the answer-key fixture, the 27/30 threshold, the
  budgets, the model route, or the fail-safe flags.
- Use only `responsibilityCompletionRequest(seed).sourceSpan` as the semantic source. No headings,
  no source prefixes, no neighbouring duties, no answer-key aliases, no fixture terms.
- Every new test must use INVENTED source text. The F1 block is the pattern; copy it.
- Merge, apply and serving stay false.
- `main` only. Stage exact paths, never `git add -A`, and preserve the untracked files listed in
  section 3.
- Before any future commit, confirm `git var GIT_COMMITTER_IDENT` is
  `Albert Hazan <u2giants@users.noreply.github.com>`.
- **There are now 12 open handoff files in `HANDOFF.d/`, well above the limit of 5.** Do not delete
  or edit another session's file. Albert should schedule a dedicated handoff-retention cleanup.

## 8. Access and environment

- Windows 11 host `al8960ofc`; PowerShell 7; repo `C:\repos\oracle`; branch `main`.
- This session ran from the git worktree `C:\repos\oracle-worktrees\repo-handoff-docs-c87db2` but
  made every edit in the primary checkout `C:\repos\oracle`, which the plan requires.
- pnpm and Node 24 are installed and working. `gh` is authenticated, needed only for later landing.
- The licensed pinned fixture is at
  `Z:/Documentation/company process - Oracle/Licensed Team Responsibilities 2 - tagged.txt`,
  overridable with `R2_PINNED_FIXTURE_PATH`. It is reachable on this machine. Never copy its
  contents into the repo, a commit message, an issue, or any outside model.
- Secrets live only in 1Password vault `vibe_coding`. None are needed for F2 through F5. Serialize
  any 1Password reads.
- Supabase and Trigger.dev stay unused under this plan.

## 9. Open questions and risks

- **Biggest risk: over-normalization.** F2 rewrites stored fields. The guard is that the object must
  be rebuilt only from the exact span and that fidelity may never regress. If a case forces you to
  loosen either guard, stop and ask Albert rather than loosening it.
- **Second risk: silently tuning to the eight eligible rows.** Every F2/F3 test uses invented text
  for exactly this reason. A reviewer in F6 will look for answer-key vocabulary in production files.
- Open question from the plan, still open: whether the locked compact-object rule in plan section 8
  safely covers rows 5, 14 and 17. The tests decide. If any of the eight eligible shapes cannot be
  recovered honestly, STOP and ask Albert. Do not lower the eight-row gate.
- Open question: whether `trigger` alone is enough to hold a separated condition or whether an
  audit-only condition field is also needed. F1 requires `trigger` retention; the extra field is
  still F2's judgment call.
- Local replay proves source-bound correctness, not live production readiness. Any future live run
  needs a new written plan and a new explicit owner authorization.

## Handoff self-audit

Passed. A developer with zero knowledge of this app, this chat, or the R2 history can act on this
file alone: section 1 identifies the system and every file that matters, section 3 states exactly
what is green, what is red on purpose, and what is uncommitted, section 4 records all three
approaches that failed this session with their causes so they are not repeated, section 5 carries
the one finding that changes the next phase's acceptance rule, and section 6 gives ordered next
steps each with a concrete success test. Section 0 isolates the only owner decisions and marks the
settled ones so nobody re-asks. Sections 7 to 9 carry the safety limits, the environment, the
licensed-data rule, and the honest risks. No sentence in sections 1 to 9 needs Albert's judgment
unless it also appears in section 0.
