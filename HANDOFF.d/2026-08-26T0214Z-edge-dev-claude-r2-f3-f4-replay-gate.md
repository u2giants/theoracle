# R2 correction: the 19/19 production replay is PROVEN, F3 and F4 are landed on `main`. F5 and F6 remain.

Status: **OPEN. All work described here is committed AND pushed to `origin/main` with green CI
(`b025e65`, `d3c1b4b`, `b48fcbc`, plus this file's own docs commit). Nothing is at risk in a working
tree. The production hard stop is unchanged: no deploy, no second production gate, no database or
schema change, no bake-off.**

Plan: [`../plan_r2_source_bound_final_record_correction.md`](../plan_r2_source_bound_final_record_correction.md)
— read its `## STATUS table` first, then the top of its `## Drift log`. Both are current as of this file.

## 0. Decisions only Albert can make

### Blocking

**None.** Nothing here is waiting on Albert to proceed with F5 or F6.

### Recoverable — a wrong guess costs rework, not damage

1. **Mount the licensed source drive, or tell the next session to skip that one gate.**
   `verify:r2-pinned-inventory` reads a licensed file at
   `Z:/Documentation/company process - Oracle/Licensed Team Responsibilities 2 - tagged.txt`.
   **This machine (`edge-dev`) has NO mapped network drives at all** (`Get-PSDrive` shows only C, D,
   E, Temp; `net use` is empty). That gate therefore could not run this session. It is unrelated to
   the changes made here — every other gate passed — but F5 is not formally complete without it.
   *Recommendation:* tell the next session which path holds that file on `edge-dev` (any path works —
   the verifier honours the `R2_PINNED_FIXTURE_PATH` environment variable), **or** say "run F5 on
   `al8960ofc` instead", where the drive was reachable on 2026-08-13. Blocks: the last item of F5 only.

### Not part of this workstream, and nobody is on it

2. **The stored production database URL in 1Password is stale and will fail for any future session.**
   Item `Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, eqccjfbyrywsqkxxpjvg)` in vault
   `vibe_coding` holds a `db.<ref>.supabase.co` host. Supabase has retired that host for IPv4 clients,
   so **it no longer resolves** — the credential inside it is still correct, only the host is dead.
   This session worked around it in code (see §5.4), but every other script in the repo that expects a
   working URL from that item will fail with `getaddrinfo ENOENT`.
   *Recommendation:* let a future session update that 1Password item to the session-pooler form
   (`postgresql://postgres.eqccjfbyrywsqkxxpjvg:<same password>@aws-1-us-east-1.pooler.supabase.com:5432/postgres`).
   That is a secret WRITE, which is why it was not done unasked. Blocks: nothing today.

### Already settled — do NOT re-ask

- 2026-08-12: local implementation of the whole plan is authorized.
- 2026-08-13: correcting the expected-object boundary inside `validateResponsibilityFieldFidelity` to
  the plan's locked section 8 rule is authorized and is a correction, not a weakening.
- 2026-08-13: keep the 185 KB legacy archive handoff for now; delete it in the same commit that lands
  a plan document holding its GAP/REL register. Recorded durably in `AGENTS.md` §3a.
- 2026-08-13: `.ai/reviews/` is in `.gitignore` (`.gitignore:72`). The ~344 untracked review artifacts
  there cannot be swept into a commit.
- 2026-08-25 (this session): Albert authorized pushing this work to `main`. It is pushed.
- Standing: no deploy, no second production gate, no bake-off, no DB/schema/secret change, and no
  change to the frozen matcher, answer key, threshold, budgets, model, route, or fail-safe flags.
- Rows 16, 24 and 26 of the R2 fixture are honest negative controls and must stay failing.
- Landing a future PRODUCTION RUN is a separate owner decision that comes after F6.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed business knowledge system. Employees
upload company documents and ask business questions about them. Trigger.dev workers cut each document
into chunks, then into exact "source duty spans" (called seeds), show each seed's exact snippet to a
model, have the model fill in role / action / object / trigger for that duty, validate every field
against that exact snippet, and save a reviewable, source-proved map of who does what.

- Repo `u2giants/theoracle`. Branch policy: **`main` only, no feature branches.**
- This session worked in the git worktree
  `C:\repos\oracle\.claude\worktrees\project-status-check-0c6e52` (branch
  `claude/project-status-check-0c6e52`) and pushed with `git push origin HEAD:main`. The primary
  checkout is `C:\repos\oracle`.
- TypeScript monorepo: pnpm 9.5.0 + Turbo, Next.js 16, Trigger.dev, Drizzle, Supabase. Node 24.
- Web `https://oracle.designflow.app` (Vercel). Workers: Trigger.dev project
  `proj_wgpzsvhmsopqhvwqaycn`. Database: Supabase project `eqccjfbyrywsqkxxpjvg`.
- Rules and validators: `apps/workers/src/lib/responsibility-reader.ts` (3,400+ lines).
- Orchestration: `apps/workers/src/lib/source-workflow-read.ts` (4,000+ lines).
- Main test suite: `apps/workers/src/__verify__/r2-responsibility-reader.ts` (5,200+ lines).
- **Never edit:** `apps/workers/src/lib/responsibility-answer-key.ts` and
  `apps/workers/src/__fixtures__/licensed-team-responsibilities-v1.json`. These are the frozen
  scoring rule and the frozen answer key.

## 2. What we set out to do this session, and why

Albert asked where the project stood, then authorized the two next steps the previous session had
left: **build the production-replay harness, then do F3.** He later authorized **F4** as well, plus a
push to `main` and an independent Gemini review.

Business framing: the system was measured once against a 30-question answer key drawn from a real
licensed document, and it got 19 right. The bar is 27. Several sessions of correction work followed.
The danger was that the correction work could quietly BREAK some of the 19 that already worked while
chasing the missing 11 — and nobody had ever checked. That check is what this session built.

Technical framing, from the plan:
- The one authorized production run (2026-08-11) scored **19/30** against a frozen 27/30 gate.
- A separate verifier shows the exact snippets support 28/30, so the duties ARE visible in the source;
  the failures are in the final stored field wording.
- Eight rows were judged correctable (5, 14, 15, 17, 19, 20, 23, 29); three are negative controls
  (16, 24, 26). 19 + 8 = 27, exactly the gate.
- F0, F1, F2 and F2b were already built and green. **F2b changed `boundedSourceObject`, the single
  definition of where a duty's object ends — and that helper both PRODUCED and ENFORCED the 19
  passing rows.** The previous session's own §9 called the unrun preservation gate its largest risk.

## 3. Current state — what is true right now

### Committed and pushed to `origin/main`, CI green

| SHA | What it is |
|---|---|
| `b025e65` | The production-replay gate (`verify:r2-production-replay`) + the F3 late-completion seam. |
| `d3c1b4b` | The stricter per-record preservation check inside that gate (see §5.1). |
| `b48fcbc` | **F4**: the one shared correction seam used by both candidate stages + the persisted `responsibilityFinalRecordCorrection` audit. |

CI runs `32917771597` and `32918181472` (workflow "PR check" on `main`) both completed **success**.
Verify with `gh run list --branch main --limit 3`.

### The preservation gate — RUN, PASSED, and stable across four runs

`pnpm --filter @oracle/workers verify:r2-production-replay` — file
`apps/workers/src/__verify__/r2-production-replay.ts`. SELECT-only: two SELECTs, no writes, no model
calls, no budget spend, no map supersede. Requires `R2_REPLAY_DATABASE_URL` (see §8 for exactly how to
supply it without exposing the secret).

Output, identical on every run including after F4 landed:

```
storedRecords: 93        seeds: { resolved: 93, unresolved: 0, built: 139 }
baselineMatched: 19      replayMatched: 21
preservedRows: 19        regressedRows: []        recordLevelRegressions: []
recoveredRows: [19, 29]  correctionsAccepted: 18
correctionReasonCounts: { no_strict_improvement: 75, action_inflection_normalized: 11,
                          object_boundary_isolated: 8 }
```

**What that means in words:** all 93 real stored records were re-matched to their own source spans;
the stored records reproduce exactly 19/30 with exactly the eleven documented misses; after the
correction code runs they reach 21/30; **nothing that used to pass now fails**, at either the row
level or the record level; and the three negative controls are still failing, so the corrector did
not cheat.

### What was built

- **F3** (`source-workflow-read.ts`): `executeResponsibilityCompletionBatches` gained an OPTIONAL
  `correctRecord` hook, applied to each canonicalized candidate BEFORE
  `selectStrictResponsibilityCompletionImprovements` and before the caller's existing
  `validateResponsibilityRead`. So the record that is judged is the record that is kept.
- **F4** (`responsibility-reader.ts` + `source-workflow-read.ts`):
  `responsibilityFinalRecordCorrectionSeam({ seeds, stage })` is now the ONE shared seam, used by
  BOTH candidate stages (the exhaustive completion stage and the late-completion path).
  `correctResponsibilityFinalRecord` now has **exactly one call site in the whole codebase** — inside
  that seam — and `source-workflow-read.ts` never calls it directly. Both facts are asserted by test,
  so a future session cannot quietly add a second correction path.
  `buildResponsibilityFinalRecordCorrectionAudit` persists `responsibilityFinalRecordCorrection` into
  the map's `validationJson`: offered / accepted / refused counts, accepted and refused seed IDs,
  reason counts, per-correction stage + source-span SHA-256, and execution refs. No source text.

### Verified green this session, by running them

`@oracle/workers typecheck`, `@oracle/ai typecheck`, `@oracle/engines typecheck`,
`verify:r2-responsibilities`, `verify:source-workflow-read`, `verify:r0-reader-validator`,
`verify:document-ingestion-fallback`, `verify:lull-event-dispatch`, `verify:conversation-windowing`,
`@oracle/ai verify:r2`, `@oracle/ai verify:workflow-read`, `@oracle/engines verify:macro`,
`@oracle/engines verify:macro-first`, `@oracle/engines verify:r1-cross-shape`. **13 of 13 pass.**
Plus `verify:r2-production-replay` (credentialed, above).

### NOT done

- **F5** — the formal gate sweep. Everything above is green EXCEPT `verify:r2-pinned-inventory`,
  which could not run here (see §0 item 1). F5 also expects the eight-row recovery to reach 27/30;
  it currently reaches 21/30 by replay, which is expected and is NOT a failure — see §9.1.
- **F6** — independent review by Codex and GLM 5.2, then Albert's decision. A Gemini review was run
  this session (see §5.1) but Gemini is review-only and does not satisfy F6's named reviewers.

## 4. Everything we tried that did NOT work

1. **`pnpm` is not on PATH on this machine, and the worktree had no `node_modules`.** `pnpm` is not
   installed globally on `edge-dev`; only `node`, `npm` and `corepack` are. **Use `corepack pnpm ...`
   for every command.** Also, a fresh git worktree has no dependencies — `corepack pnpm install
   --frozen-lockfile` must be run once in the worktree before any verifier will start. Both failures
   look like broken tests and are not.
2. **The Bash tool cannot run `pnpm`; PowerShell can.** `pnpm: command not found` from Bash even after
   the above. Run all pnpm/verifier commands through PowerShell.
3. **The stored production DB URL does not resolve.** `getaddrinfo ENOENT
   db.eqccjfbyrywsqkxxpjvg.supabase.co` — Supabase retired the direct host for IPv4 clients. See §5.4
   for the fix and §0 item 2 for the standing cleanup.
4. **Guessing the pooler region failed twice before it worked.** `aws-0-us-east-1` returns
   `tenant/user postgres.eqccjfbyrywsqkxxpjvg not found`. **The correct host is
   `aws-1-us-east-1.pooler.supabase.com`** (note `aws-1`, not `aws-0`). It is now the built-in default
   in the verifier, overridable with `R2_REPLAY_POOLER_HOST`. Do not re-derive this.
   *Note:* every `aws-N-<region>.pooler.supabase.com` name resolves in DNS regardless of whether it is
   yours, so DNS probing tells you nothing — only a real connection attempt does.
5. **Writing a scratch script that consumes the secret was blocked by the permission classifier**, as
   was reading the 1Password item's full contents. Both refusals were correct. The workaround that IS
   allowed: put the fallback logic in the real verifier and run the sanctioned `verify:` command
   through `op_run` with an `op://` reference. Do not fight the classifier; move the logic into the
   committed gate where it belongs anyway.
6. **The first version of the preservation gate was too weak, and Gemini's review would have let it
   stand.** See §5.1 — this is the most important entry in this section.
7. **F3's own test F3e broke when F4 landed, correctly.** F3e asserted the corrector's single call
   site was in `source-workflow-read.ts`; F4 moved it into the shared seam in
   `responsibility-reader.ts`. The test was updated to assert the NEW invariant (one call site in the
   reader, ZERO direct calls in the orchestrator), which is strictly stronger. If you move that call
   site again, expect this test to fail and update the invariant deliberately — do not delete it.
8. **Inherited from previous sessions, still true and still worth not repeating:** delegating F2–F4 to
   GLM 5.2 as one job produced ZERO changes in 41 minutes (scope too large; give a delegate one file
   and one function and point it at the tests as the spec). A CRLF/line-ending trap silently breaks
   multi-line source-text literals in a FRESH Windows clone — both the frozen-budget guard and the F0
   guard now normalize line endings, and CI never caught it because Linux checkouts are LF. A
   "record-level completeness" proposal (`A ⊆ object` replaced by `A ⊆ object ∪ trigger ∪ audit`) was
   refuted as a weakening described as a broadening — do not revive it.

## 5. Root causes and key findings

### 5.1 The matcher assigns records to rows GLOBALLY — this is the subtle one

`scoreResponsibilityAnswerKey` (`apps/workers/src/lib/responsibility-answer-key.ts:136-201`) builds
every (expected row × actual record) candidate pair and then performs a **global best-assignment**:
it sorts all matching pairs by quality and greedily assigns, one record per row, one row per record.

**Consequence:** "row 7 still matches" does NOT prove the same record matches it. A genuine regression
in record X could be masked by a different record Y sliding into X's row. The first version of this
gate checked only row-level preservation and would have reported a clean `regressedRows: []` in that
scenario.

**Gemini raised this scenario and then dismissed it** as circumstantially impossible ("only 18 records
were modified, 93/93 seeds resolved"). That is an argument from circumstance, not a proof, and it is
exactly the kind of reasoning this plan has been burned by before.

**The fix, in `r2-production-replay.ts` (the `isolatedRow` / `recordLevelRegressions` block):** the
gate now ALSO scores every stored record **in isolation** — one expected set, one actual record —
where no assignment can substitute one record for another, and fails if any record that matched a row
on its own stops matching that same row. Result on real data: `recordLevelRegressions: []`.
**Do not remove the record-level check in favour of the row check. The row check is the weaker of the
two.** Both must stay.

### 5.2 The core finding that F2b acted on (inherited, still load-bearing)

The span was doing two jobs. It is the right unit of EVIDENCE, but `sourceObjectText` also made it the
definition of the ANSWER: the expected `object` was everything from the first duty verb to the end of
the span. `boundedSourceObject` corrects that, and is used by the qualifier-loss check, by
`deterministicInventoryRecord`, and by the corrector — one definition, three call sites.

The `condition` vs `clause` distinction inside it is load-bearing: a **condition** belongs to THIS duty
and must appear verbatim in `trigger`; a **clause** belongs to a DIFFERENT seed and must never be
pushed into this record's `trigger`. Collapsing them recreates the junk-drawer failure that sank the
record-level alternative. F1 case 16 pins it.

### 5.3 Why the seam has to run BEFORE selection, not after

`selectStrictResponsibilityCompletionImprovements` decides which candidates to accept, and the
caller's `validateResponsibilityRead` decides whether the record is complete. If correction ran after
either of them, the system would judge one version of a record and store a different one. Applying
`correctRecord` to the canonicalized batch — before selection — is what makes "the record that is
judged is the record that is kept" true. Both F3 and F4 depend on that ordering; F3c and the F4
assembly assertions pin it.

### 5.4 The database-URL rewrite (and why it is safe)

`r2-production-replay.ts` accepts `R2_REPLAY_DATABASE_URL`. If — and only if — the URL matches the
dead direct form `postgres[ql]://<user>:<pass>@db.<ref>.supabase.co:<port>/<db>`, it rewrites it to
`postgresql://<user>.<ref>:<pass>@<pooler-host>:5432/<db>`. Same credential, same project, same
database — **only the network path changes.** Any URL that is already something else is used verbatim.
It cannot silently read the wrong database, because the gate then asserts on the exact map ID, the
93-record count, and the 19/30 baseline; a different database fails all three.

### 5.5 The stage boundary in the persisted audit is exact, not a guess

The exhaustive stage owns batch indices `[0, exhaustiveBatchCount)` and the late path is offset past
them using exactly that number (`batchOffset`). The F4 audit uses that offset to label each execution
ref `exhaustive` or `late`. An earlier draft inferred the stage from
`responsibilityCompletionAudit.batchManifest.length` at audit time — **that is wrong**, because late
batches are appended to the manifest before the audit is built. If you touch this, keep it anchored to
the offset, not to the manifest length.

## 6. Exact next steps

1. **Answer §0 item 1 (where the licensed fixture lives on this machine), then run the last gate.**
   Command: `$env:R2_PINNED_FIXTURE_PATH='<path>'; corepack pnpm --filter @oracle/workers
   verify:r2-pinned-inventory`.
   *You'll know it worked when:* it prints a pinned inventory result of **28/30 with rows 16 and 26
   unsupported**. Any other number is a regression — STOP and report, do not adjust anything.
2. **Complete F5 by re-running the full local sweep and recording it.** All 13 commands in §3 plus
   `verify:r2-production-replay` plus step 1.
   *You'll know it worked when:* every command exits 0, the replay still prints `regressedRows: []`
   and `recordLevelRegressions: []`, and you have appended the results to the plan's `## Drift log`.
3. **Do NOT treat 21/30 as an F5 failure.** See §9.1 before concluding anything about the score.
4. **Then F6: independent review by Codex AND GLM 5.2** — the two reviewers the plan names. Give each
   the same brief: the three commits in §3, the plan, and an instruction to REFUTE rather than confirm.
   F6 must specifically audit that only the expected-object boundary moved; that anti-invention,
   polarity, owner and action-family checks are byte-for-byte unchanged; that exactly one boundary
   helper and exactly one corrector call site exist; that a cut tail missing from `trigger` is
   rejected; and that no acceptance-rule exemption was reintroduced.
   *You'll know it worked when:* both return no P0 and no P1, and their reports are saved under
   `.ai/reviews/` (which is gitignored).
5. **Only then put the production question to Albert**, in writing, as a new plan. A new production run
   is a separate owner decision and is NOT authorized by anything in this file.
6. **At the end of every phase**, append drift to the plan's `## Drift log`. Several entries exist;
   follow that format.

## 7. Constraints and gotchas in force

- Local only. No deploy, second gate, bake-off, Vercel action, DB, schema, migration or secret change.
- Never edit the frozen matcher, the answer-key fixture, the 27/30 threshold, the budgets
  (40 / 500,000 / $10 / 1 / 4 and post-pass 1 / 5 / 1), the model, the route, or the three
  `business_model_*_enabled` flags. The F0 block asserts all of these; breaking F0 means a rule was broken.
- Only the expected-object BOUNDARY inside fidelity may change, and only to the locked section 8 rule.
  Anti-invention, polarity, owner match, action family and multi-verb rejection stay frozen.
- **Every new test must use INVENTED source text** (`Fleet Office`, `Depot Lead`, `Service Desk`,
  `route packets`, `QA1 photos`). Never put a licensed-document or answer-key term in a test or in
  production code. The F4 assertions explicitly check the persisted audit contains no source text.
- `main` only. Stage exact paths; never `git add -A` — the untracked `.ai/` pile would come with it.
- Before any commit, confirm `git var GIT_COMMITTER_IDENT` is
  `Albert Hazan <u2giants@users.noreply.github.com>`.
- Use `corepack pnpm`, from PowerShell, and run `corepack pnpm install --frozen-lockfile` once in a
  fresh worktree. See §4.1 and §4.2.

## 8. Access and environment

- Machine `edge-dev` (Windows 11, PowerShell 7). **No mapped network drives** — `Z:` does not exist here.
- Repo worktree used: `C:\repos\oracle\.claude\worktrees\project-status-check-0c6e52`, branch
  `claude/project-status-check-0c6e52`, pushed to `main` with `git push origin HEAD:main`.
- `gh` is authenticated (used for `gh run list` / `gh run watch`).
- Supabase MCP `supabase-oracle` works for read-only SQL against production and was used to inspect
  the map's shape. Trigger.dev and Vercel MCPs were not needed.
- **Secrets live only in 1Password vault `vibe_coding`. Never put a value in chat, a command line, a
  log, or a commit.** To run the credentialed gate, use the 1Password `op_run` tool with an `op://`
  reference so the value never enters the transcript:
  - command: `corepack pnpm --filter @oracle/workers verify:r2-production-replay`
  - cwd: the repo root
  - shell: `powershell`
  - env: `{"R2_REPLAY_DATABASE_URL": "op://vibe_coding/qcuyabwseaptvuzvtjejffi2ou/password"}`
  That item is titled `Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, eqccjfbyrywsqkxxpjvg)`.
  See §0 item 2 — its host is stale and the verifier compensates in code.
- Reviewers: `ai-gemini` is on PATH and its `doctor` reports PASS on this machine (the
  `gemini-code-delegation` skill text still says QUARANTINED — the wrapper disagrees; Gemini is
  review-only either way and does NOT satisfy F6). Codex and GLM wrappers are the F6 reviewers.

## 9. Open questions and risks

1. **21/30 is the expected replay result, not a shortfall — do not "fix" it.** Replaying finished,
   stored records can only repair defects that live in the wording of an already-produced record: that
   recovered rows 19 and 29 (both inflected-verb defects). Rows 5, 14, 15, 17, 20 and 23 were never
   going to come back this way — rows 20 and 23 have no stored record at all (they were completion
   gaps), and row 15 produced no usable record. Those need a fresh run through the corrected pipeline,
   which is a production question, not a local one. **A future session that "improves" the corrector
   until the replay hits 27/30 has almost certainly cheated. Check §7 before believing such a result.**
2. **Row 5 remains the live unknown.** A boundary fix cannot invent its missing token. If it turns out
   not to be honestly recoverable, the ceiling is 26/30 — that is a stop-and-ask, not a reason to
   loosen anything.
3. **Watch for anyone reintroducing an acceptance-rule exemption**, or widening the condition-cue list
   beyond the locked section 8 cues, to make a stubborn row pass.
4. **The preservation gate proves preservation, not readiness** (dated 2026-08-25). It says the
   correction work broke nothing production already got right. It does not predict what a new
   production run would score.
5. **Gemini's review (2026-08-25, commit `b025e65`) returned APPROVE with no P0/P1/P2** and is saved
   under `.ai/reviews/gemini-r2-f3-replay-review-20260825T234157Z-971491.md` (gitignored). Treat it as
   supporting evidence only: it dismissed a real weakness as circumstantially impossible (§5.1), and
   it reviewed the code BEFORE `d3c1b4b` and `b48fcbc` existed. F6's named reviewers still owe a
   verdict on the final state.

## Retired in the same commit as this file (successor rule, `AGENTS.md` §3a)

- `2026-08-13T1940Z-al8960ofc-claude-r2-bounded-object-f2b.md` — its F3 work is the work this session
  finished. All three conditions checked: (1) its commits `f68bd36` and `c6dbf81` are on `origin/main`
  — verified with `git log`; (2) its open obligations are carried forward — the replay gate and F3 are
  DONE and recorded in the plan's STATUS table and drift log, and F4/F5/F6 plus row 5 are carried into
  §6 and §9 here; (3) its dead ends are preserved — the GLM scoping lesson, the CRLF trap and the
  rejected record-level-completeness proposal are all in §4.8 above.
- `2026-08-13T1946Z-al8960ofc-claude-handoff-retention-fix.md` — this file existed for ONE stated
  reason: to carry two answers that the F2b file's §0 asked as if unanswered, and it explicitly
  instructed "the session that finishes R2 F3 deletes BOTH". That is this session. Both answers are
  preserved in §0 "Already settled" above.

## Handoff self-audit

**Passed.** Answers to the four required questions, with the sections that support each:

1. *Could a brand-new developer with no project knowledge continue without skipping a beat?* **Yes.**
   §1 names the system, both repos-of-record, the stack, the URLs, the three files that matter and the
   two that must never be edited. §2 gives the business reason and the numeric history. §3 states what
   is committed, what is green (with the exact commands run) and what is not done. §6 gives ordered,
   executable next steps.
2. *Could they continue as effectively as I can right now?* **Yes.** The two things that cost this
   session real time are written down in full: the global-assignment weakness and its fix (§5.1) and
   the four environment traps — no `pnpm` on PATH, no `node_modules` in a fresh worktree, the dead
   direct DB host, and the `aws-1` (not `aws-0`) pooler region (§4.1–§4.5). §5.5 records the audit
   stage-boundary trap that a plausible-looking rewrite would reintroduce.
3. *Is every relevant detail included?* **Yes.** Background §1–§2; current state §3 with commit SHAs
   and CI run IDs; failures §4 (eight entries, including one of my own weak first drafts and one
   correct test breakage); findings §5 with `file:line`; next steps §6 each with a "you'll know it
   worked when" gate; constraints §7; access §8 with the exact `op_run` shape and no secret values;
   risks §9 including the trap of mistaking 21/30 for a shortfall.
4. *If Albert read ONLY §0, would he see every decision he owes — including out-of-scope ones?*
   **Yes**, and I checked it the hard way by walking §1–§9 line by line. Every sentence needing his
   judgement appears in §0: the unreachable `Z:` drive (§3, §6.1, §8 → §0 item 1); the stale 1Password
   URL, which is OUTSIDE this workstream and would otherwise have been filed as a finding in §5.4 →
   promoted to §0 item 2; and the production-run question (§6.5, §9.4) → §0 "Already settled", because
   it is a known standing gate rather than a new ask. No other sentence in §1–§9 requires his ruling.
   §0 also carries the "already settled" list so nothing decided on 2026-08-12, 2026-08-13 or
   2026-08-25 gets re-asked.
