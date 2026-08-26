# R2 correction: F5 and F6 are both COMPLETE. Every review finding is fixed. Only the production decision remains.

Status: **OPEN, but not for review work.** F0 through F6 are done. All 15 local gates pass, both named
F6 reviewers have signed off with no P0 and no P1 outstanding, and everything is committed AND pushed
to `origin/main` (`aab134e`, `41f775b`, `58642ed`, `52b308b`). Nothing is at risk in a working tree.
**The production hard stop is unchanged: no deploy, no second production gate, no database or schema
change, no bake-off.** What is left is a single owner decision — see §0.

Plan of record: [`../plan_r2_source_bound_final_record_correction.md`](../plan_r2_source_bound_final_record_correction.md).
**Read its `## STATUS table` first, then the top four entries of its `## Drift log`** — those four
entries (F5, and F6 rounds 1, 2 and 3) are this session and are newer than the plan body.

This file supersedes and retires `2026-08-26T0214Z-edge-dev-claude-r2-f3-f4-replay-gate.md`, deleted
in the same commit that lands this file. Git history keeps its text. See the retirement note at the
end for the three-condition check.

---

## 0. ⚠️ DECISIONS ONLY ALBERT CAN MAKE

**Put this whole list to him in ONE message before starting work.**

### Blocking — this is the only real decision left in the workstream

1. **Authorize a fresh production run, or stop here?** Everything local is proven and every reviewer
   is satisfied. The one number that cannot be established locally is the real one: whether a fresh
   run through the corrected pipeline reaches the frozen **27/30** bar. Replaying the OLD stored
   records reaches 21/30 and mathematically cannot do better (see §9.1 — this is expected, not a
   shortfall). A production run costs model budget and writes a new map.
   *Recommendation:* **authorize one run**, because the entire plan exists to answer that question and
   nothing further can be learned locally. *Blocks: everything remaining. Nothing else does.*

### A wrong guess is recoverable, but rework is wasteful

2. **Delete the parked branch `al8960ofc-r2-f4-local-superseded`?** It holds this machine's separate,
   never-pushed implementation of F3/F4 from 2026-08-14, superseded by the `edge-dev` line that is now
   on `main` (see §4.1). It has already paid for itself once — its seam had ALREADY fixed the audit
   overstatement that Codex raised as a P1 here, which is how we knew our fix was the right shape.
   *Recommendation:* **keep it until after the production run**, then delete. *Blocks: nothing.*
3. **`apps/workers/src/__verify__/r2-residual-matrix-source.ts` still points at three stale map ids**
   that score 11/30 and 12/30 — the old bake-off maps, not the 2026-08-11 production gate. Inherited,
   unfixed, and still true. Any future session that trusts that file measures the wrong run.
   *Recommendation:* **repoint it at `37a8fc62-23e4-46b7-8464-d1c784dc73cd` or delete it**, since
   `verify:r2-production-replay` supersedes it. *Blocks: nothing. Risk: a future session reports a
   wrong score.*

### Not part of this work, and nobody is on it

4. **The Oracle production database has no read-only credential.** 1Password `vibe_coding` holds one
   live connection string for it, the full-privilege one. Every read-only replay gate therefore runs
   under a credential that could also drop tables. *Recommendation:* **create a read-only Postgres
   role for gates and store it as a new field on that item.** That is a production database change and
   needs his explicit say-so. *Blocks: nothing today; true for every session that ever ran a replay.*
5. **The stored production database URL in 1Password is stale.** Item
   `Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, eqccjfbyrywsqkxxpjvg)` holds a
   `db.<ref>.supabase.co` host that Supabase retired for IPv4 clients, so it no longer resolves. The
   replay gate compensates in code (§5.4), but any OTHER script expecting a working URL from that item
   fails with `getaddrinfo ENOENT`. *Recommendation:* update the item to the session-pooler form. That
   is a secret WRITE, which is why no session has done it unasked. *Blocks: nothing today.*
6. **`C:\repos\oracle` has an untracked clutter pile** — `.ai/gap*.out|err`, two `.ai/run-gap10-*.ps1`
   scripts, `.playwright-cli/`, `detail-current.png`, `rfq-before.png`. None belongs to this session.
   *Recommendation:* **leave them**; they may belong to another session. Flagged only so nobody sweeps
   them in with `git add -A`. *Blocks: nothing.*

### Already settled — do NOT re-ask

- **2026-08-12:** local implementation of this whole plan is authorized.
- **2026-08-13:** correcting the expected-object boundary inside `validateResponsibilityFieldFidelity`
  to the plan's locked section 8 rule is authorized, and is a correction, not a weakening.
- **2026-08-13:** `.ai/reviews/` is in `.gitignore` (line 72). The `ai-qwen` wrapper's warning that it
  is not ignored is WRONG. Do not "fix" the gitignore.
- **2026-08-25:** pushing this work to `main` is authorized.
- **2026-08-26 (this session):** pulling/reconciling the diverged repo, running F5 including the
  licensed `Z:` gate, proceeding to F6, and **fixing the `fieldFidelity === null` acceptance-rule
  gap** are all authorized and all DONE.
- **Standing:** no deploy, no second production gate, no bake-off, no DB/schema/secret change, and no
  change to the frozen matcher, answer key, fixture, 27/30 threshold, budgets, model, route, or the
  three `business_model_*_enabled` flags.
- **Rows 16, 24 and 26 of the fixture are honest negative controls and must stay failing.**

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed business knowledge system. Employees
upload company documents and ask business questions about them. Trigger.dev workers cut each document
into chunks, then into exact "source duty spans" (called **seeds**), show each seed's exact snippet to
a model, have the model fill in role / action / object / trigger for that duty, validate every field
against that exact snippet, and save a reviewable, source-proved map of who does what. Business-model
merge, apply and serving are separately gated and are OFF.

- Repo `u2giants/theoracle`. Branch policy: **`main` only, no feature branches.**
- Primary checkout `C:\repos\oracle`. Machine `al8960ofc`, Windows 11, PowerShell 7.
- TypeScript monorepo: pnpm + Turbo, Next.js 16, Trigger.dev, Drizzle, Supabase. Node 24.
- Web `https://oracle.designflow.app` (Vercel). Workers: Trigger.dev `proj_wgpzsvhmsopqhvwqaycn`.
  Database: Supabase project `eqccjfbyrywsqkxxpjvg`.
- Rules, validators, the corrector, the F4 seam: `apps/workers/src/lib/responsibility-reader.ts`.
- Orchestration: `apps/workers/src/lib/source-workflow-read.ts`.
- Main suite: `apps/workers/src/__verify__/r2-responsibility-reader.ts`.
- Production replay gate: `apps/workers/src/__verify__/r2-production-replay.ts`.
- **Never edit:** `apps/workers/src/lib/responsibility-answer-key.ts` and
  `apps/workers/src/__fixtures__/licensed-team-responsibilities-v1.json`.

**Terms.** *Seed* = one source duty span, the exact snippet a record must be provable from.
*Answer key* = a frozen fixture of 30 expected records used to score a run. *Frozen matcher*
(`field-aware-v3`) = the scoring function; never allowed to change. *Gate* = a run scored against the
answer key; the bar is 27 of 30. *Candidate stages* = the steps producing a record for a seed before
final validation (base read, deterministic builder, exhaustive completion, late completion).
*F0…F6* = the phases of the plan.

## 2. What we set out to do this session, and why

Albert asked to pull the latest repo, proceed to **F5**, told us the `Z:` drive is available on this
machine, then authorized **F6**, and finally authorized fixing the one blocker F6 surfaced.

Business framing: the system was measured once against a 30-question answer key drawn from a real
licensed document and got 19 right; the bar is 27. Several sessions of correction work followed. F5 is
the formal proof that all local gates pass. F6 is independent review by two other AI engines whose job
is to try to REFUTE the work before the owner is asked to spend production budget on it.

## 3. Current state — what is true right now

### Committed AND pushed to `origin/main`

| SHA | What it is |
|---|---|
| `aab134e` | F5 closed: all 15 local gates green, the licensed pinned-inventory gate finally run. |
| `41f775b` | F6 round 1: audit reconciliation + first attempt at the replay record-level fix. |
| `58642ed` | F6 round 2: that first attempt was a NO-OP; replaced with a working one. |
| `52b308b` | F6 round 3: the `fieldFidelity === null` acceptance bypass closed. |

Working tree is clean apart from other sessions' untracked clutter (§0 item 6).
**Phases F0, F1, F2, F2b, F3, F4, F5, F6: all done.**

### Every gate, run at `52b308b` on this machine

```
3 typechecks (@oracle/workers, @oracle/ai, @oracle/engines)                        PASS
verify:r2-responsibilities        19/30 reproduced; correction contract 16/16; F6 blocks pass
verify:source-workflow-read, verify:r0-reader-validator,
verify:document-ingestion-fallback, verify:lull-event-dispatch,
verify:conversation-windowing                                                      PASS
@oracle/ai verify:r2, verify:workflow-read                                         PASS
@oracle/engines verify:macro, verify:macro-first, verify:r1-cross-shape            PASS
verify:r2-pinned-inventory        28/30, rows 16 and 26 unsupported
verify:r2-production-replay       see below
```

Production replay output, identical before and after every change this session:

```
Stored records matching more than one answer-key row in isolation: 0
storedRecords 93   seeds { resolved 93, unresolved 0, built 139 }
baselineMatched 19   replayMatched 21   preservedRows 19
regressedRows []     recordLevelRegressions []     recoveredRows [19, 29]
correctionsAccepted 18
correctionReasonCounts { no_strict_improvement: 75, action_inflection_normalized: 11,
                         object_boundary_isolated: 8 }
replaySha256 013e40ca24070d22a5113b6e788e94ed55a8d1c7eae61c00ab2bc86829f4a468
```

**In words:** all 93 real stored records re-matched to their own source spans; the stored records
reproduce exactly 19/30 with the eleven documented misses; after correction 21/30; nothing that used
to pass now fails, at row level or record level; negative controls still failing.

### F6 outcome, in full

**Reviewer 1 — Codex (`gpt-5.6-terra`, read-only sandbox, reasoning effort `medium`).** Round 1:
`CHANGES REQUIRED`, two P1s. Round 2 (same session resumed): both fixes accepted, and it explicitly
endorsed the decision NOT to re-validate inside the seam. It then raised the `fieldFidelity === null`
bypass as a further P1.

**Reviewer 2 — GLM 5.3 (session `r2-f6-correction-audit`, reports in `.ai/reviews/`).** Round 1:
`APPROVED FOR LOCAL LANDING REVIEW`, one P2 and five P3s. Round 2, after being shown Codex's
counter-example: reversed to `CHANGES REQUIRED` with the finding at **P1** — *"You are right, and I
was wrong."*

**All three findings are now fixed.** No P0 and no P1 remains open from either reviewer.

### The three fixes, and what each was

1. **The persisted correction audit was overstating.** `correctResponsibilityFinalRecord` returns
   `accepted: true` whenever something changed and fidelity did not REGRESS
   (`fidelityRegressed = beforeFidelity.passed && !afterFidelity.passed`), so a record failing fidelity
   BOTH before and after was "accepted". The seam applies the correction WITHOUT re-validating, and
   `buildResponsibilityFinalRecordCorrectionAudit` copied that raw flag into `validationJson`. Stored
   `acceptedCount` therefore meant "a correction was taken", not "a corrected record passed validation"
   and not "the record was kept". Such a record could never reach `elementsJson` —
   `validateResponsibilityRead` rejects it — so this was an honesty defect in a governance artefact, not
   a persistence defect. **Fixed:** the builder takes `persistedSeedIds` and reports `accepted` only
   when the correction was taken AND the seed reached the persisted map; a taken-but-lost correction is
   reported refused with the reason `correction_not_persisted`.
2. **The replay gate's record-level check, twice.** It used `evidence.findIndex(matched)` — the FIRST
   row a record matches in isolation, not the row the global best-assignment gave it — so a record could
   lose a different row it genuinely owned while another corrected record covered that row, with both
   checks green. **The first fix was a no-op** (§4.3) and the second one works: the gate now asks one
   expected row per call and fails if a record loses ANY row it could satisfy alone.
3. **The `fieldFidelity === null` acceptance bypass.** `resolveEnclosingResponsibilityDutySpan` returns
   null when no duty span encloses the evidence quote AND the quote carries no duty verb. The rejection
   branch fires only when fidelity EXISTS and fails, so such a record was persisted having passed NO
   field check at all — a record could be stored with an object invented from nothing. **Fixed:**
   `validationSpan` now falls back to the matched inventory seed's own immutable `sourceSpan`
   (`enclosingDutySpan ?? matchedSeed?.sourceSpan ?? null`).

## 4. Everything we tried that did NOT work

Read this before repeating any of it.

1. **`git pull` could not fast-forward, and it was NOT a stale-repo problem.** `C:\repos\oracle` held
   six commits from 2026-08-14 that were never pushed — an independent implementation of F3/F4 done on
   this machine — while `edge-dev` had implemented and PUSHED the same phases. Two divergent histories
   of the same feature. **Resolution used, and it is the safe one:** `git branch
   al8960ofc-r2-f4-local-superseded <old-head>` to preserve, then `git reset --hard origin/main`.
   Nothing was destroyed. **Lesson: a handoff that says "committed but not pushed" is a live hazard,
   not a footnote.**
2. **The Bash tool's working directory is NOT reliably persistent between calls, and it silently
   reverted mid-session.** Several reads landed in the WORKTREE
   (`C:\repos\oracle-worktrees\whats-next-104c7d`, HEAD `15984f1` = the superseded implementation)
   instead of `C:\repos\oracle`, which made a reviewer's line citations look wrong and briefly made a
   function look hallucinated. **Always `cd /c/repos/oracle && …` in EVERY Bash call and print `pwd`
   before believing any file read.** This is the second session this trap has cost real time.
3. **The first version of the F6 replay fix was a complete no-op, and its "evidence" was a tautology.**
   It asked `scoreResponsibilityAnswerKey` for all 30 rows in ONE call and collected every `matched`
   row. But the scorer assigns greedily and guards with `assignedActual.has(actualIndex)`, so ONE actual
   is consumed by its greedy-best row and every other row it satisfies is forced to `matched: false`.
   The returned set could never exceed one, so the "fixed" gate was behaviourally identical to what it
   replaced, and the "0 multi-row records" it printed was structurally incapable of being anything else.
   **Caught by the reviewer, not by the gate.** The lesson is general: **a verification result that
   cannot come out any other way is not evidence.** The working form asks one expected row per call.
4. **`grep` reports `r2-production-replay.ts` as a binary file** and silently finds nothing; `grep -a`
   works. This briefly made a real function (`isolatedRow`) look invented by the reviewer. Use `grep -a`
   on that file.
5. **Writing a CRLF into a TypeScript string literal from PowerShell broke the suite** with an esbuild
   `TransformError`. Use the two-character escape `\n` inside the literal, never a real newline. This is
   the same CRLF class of trap recorded by earlier sessions.
6. **Two dead ends while constructing the F6 fidelity test** (worth minutes each):
   `resolveEnclosingResponsibilityDutySpan` matches any exact fragment CONTAINED IN a duty line, so a
   fragment of the duty sentence still resolves and proves nothing — the quote must come from text
   OUTSIDE every duty span; and a duty line needs an owner header (`[Depot Lead]`) or
   `buildResponsibilitySourceInventory` returns zero seeds.
7. **Codex's `file:line` citations were consistently off by roughly 100 lines**, in both rounds. Every
   finding was real and locatable from its prose; none of the line numbers resolved. Verify its
   citations against the file rather than trusting them — and do NOT conclude from a bad line number
   that a finding is fabricated.
8. **`ai-glm list` shows no reusable review session for this workstream in `C:/repos/oracle`** — the
   `claude`-caller rows are completed IMPLEMENTATION jobs, which `ai-glm ask` cannot resume. A new
   review session was correct here. The live one is `r2-f6-correction-audit`.
9. **Inherited and still true.** GLM sandboxes do not inherit the caller's environment, so any
   credentialed gate must be run by the owner session. `ai-glm implement` through `op_run` times out
   (10-minute cap vs 25–35 minute jobs). `ai-glm show` must run from `C:\repos\oracle`. A plausible
   "the data was always bad" story is NOT a diagnosis — trace the code. On `edge-dev` only, `pnpm` is
   not on PATH (use `corepack pnpm`); on `al8960ofc` plain `pnpm` works.

## 5. Root causes and key findings

1. **The matcher assigns records to rows GLOBALLY.** `scoreResponsibilityAnswerKey` builds every
   (expected × actual) pair and greedily assigns one record per row. Consequence: "row 7 still matches"
   does NOT prove the same record matches it. The replay gate compensates with a per-record isolation
   check — and that compensation was itself defective until this session (§3, fix 2).
2. **The same greedy guard is why a single-actual score cannot reveal a multi-row match** (§4.3). This
   is now pinned by a test using invented wording: a record that genuinely satisfies TWO expected rows
   is reported as matching only ONE by the combined call, and the per-row form recovers both.
3. **Measured, not argued: `0` stored records match more than one answer-key row in isolation.** So the
   masking scenario cannot arise on today's data — the OLD check was accidentally sufficient — and the
   new one is sufficient by construction. The count prints on every run so it cannot silently change.
4. **Tightening acceptance moved nothing.** After the fidelity-bypass fix, the F0 block still
   reproduces 19/30 with the same eligible rows and negative controls, pinned support is still 28/30
   with rows 16/26 unsupported, and the replay is byte-identical including `replaySha256`. This is the
   outcome the preservation gate exists to establish rather than assume.
5. **The seam deliberately does NOT re-validate internally, and Codex endorsed that.**
   `validateResponsibilityRead` is already the single authority that judges completeness after
   correction and before selection; a second validation inside the seam would duplicate that authority,
   which is the kind of second mechanism F4 exists to prevent. Reconciling the audit against the
   persisted ids is the narrower correct fix. **Do not "improve" this by adding validation to the seam.**
6. **The paired trigger rule is STRICTER than the plan's locked §8.5 wording, deliberately.** Fidelity
   fails when a `condition` tail is absent from `trigger` EVEN IF the condition text is still fully
   present in `object`. Locked §8.5 permits object-retention. The stricter form is what kills row 17's
   absorbed record, and the frozen matcher would score an `unless`/`except`-absorbed record as a match
   because there is no negation token — so the locked wording would silently keep junk. **A future
   session "restoring the locked wording" would re-legalize the absorbed shape and re-break row 17 with
   every gate green except the replay score.** Raised by GLM; recorded here and in the drift log.
7. **A dormant second field-rewrite path exists.** `patchCombinedResponsibilityRepairs` can rewrite all
   four duty fields outside the seam and is default-armed at `maxFieldRepairs ?? 6`. It is disabled in
   the only production wiring by the literal `maxFieldRepairs: 0`, that zero is pinned by a source
   assertion in the suite, and any repaired output is re-validated. **The one-seam invariant holds
   because of the pin, not because the path is absent. Do not re-enable it to rescue a stubborn row —
   it would bypass the correction audit by design.**
8. **One honest residual.** A record with NO matched seed AND no resolvable enclosing span still
   accepts without a fidelity check. Rejecting it would change acceptance for base reads that
   legitimately run without inventory seeds. It is now countable rather than invisible:
   `validateResponsibilityRead` returns `unprovenFieldFidelityElementIds`, unioned across base and
   retry reads. **Expected to be empty. If a future session ever sees it non-empty, that is the
   remaining tail of this bypass — bring it to Albert rather than tolerating it.**
9. **Completion-outcome reason ORDERING is asserted only set-wise** (`.some` / `.includes`), so an
   ordering change is test-invisible. Both reviewers confirmed no functional consumer parses that order.

## 6. Exact next steps

1. **Put §0 to Albert in ONE message.** *Worked when: every item has an answer, especially item 1.*
2. **If he authorizes a production run, plan it as its own document before running anything.** A run
   spends model budget and writes a new map. It is NOT authorized by anything in this file.
   *Worked when: a written plan names the document, the budget, the expected score and the abort
   condition, and Albert approves it.*
3. **After any run, re-run the full gate list in §3** plus `verify:r2-production-replay`.
   *Worked when: every command exits 0 and the replay still prints `regressedRows []` and
   `recordLevelRegressions []`. **If the new run scores below 27/30, STOP and report.** Never tune a
   rule, threshold, fixture or suite to make a number agree.*
4. **Append to the plan's `## Drift log` at the end of every phase**, newest entry directly under the
   `## Drift log` heading. Several entries exist; follow that format.
5. **Retire this handoff** when the production decision is made and executed, under the successor rule
   in `AGENTS.md` §3a.

## 7. Constraints and gotchas in force

- Local only. No deploy, no second production gate, no bake-off, no Vercel action, no database,
  schema, migration or secret change.
- Frozen and never to be edited: the matcher (`field-aware-v3`), the answer key, the fixture, the
  27/30 threshold, the budgets (40 / 500,000 / $10 / 1 / 4 and post-pass 1 / 5 / 1), the model, the
  route, and the three `business_model_*_enabled` flags. The F0 block asserts all of these; **if F0
  breaks, a rule was broken.**
- Only the expected-object BOUNDARY inside fidelity may change, and only to the locked section 8 rule.
  Anti-invention, polarity, owner match, action family and multi-verb rejection stay frozen.
- **Every new test must use INVENTED source text** in house style (`Fleet Office`, `Depot Lead`,
  `Service Desk`, `route packets`, `QA1 photos`, `Hub North`). Never put licensed-document or
  answer-key wording into code or tests. The F4 assertions check the persisted audit contains no
  source text.
- `main` only. Stage exact paths; **never `git add -A`** — other sessions' untracked files are in this
  checkout.
- Before any commit, confirm `git var GIT_COMMITTER_IDENT` reads
  `Albert Hazan <u2giants@users.noreply.github.com>`. It did this session.
- Work in `C:\repos\oracle`, not a worktree, and `cd` explicitly in every shell call (§4.2).
- Do not add validation inside the correction seam (§5.5). Do not re-enable field repair (§5.7). Do not
  relax the trigger rule to the literal §8.5 text (§5.6).

## 8. Access and environment

- Machine `al8960ofc`, Windows 11, PowerShell 7 primary. Primary checkout `C:\repos\oracle`.
  **The licensed `Z:` drive IS mapped on this machine** — this is why F5's last gate could finally run.
  It is NOT mapped on `edge-dev`.
- Authenticated and working: `gh`, `codex` (found via `where codex`, at
  `~/.codex/packages/standalone/current/bin/codex` — **do NOT hardcode the
  `…\Programs\OpenAI\Codex\bin` junction**), `ai-glm`, `ai-qwen`, 1Password MCP (vault `vibe_coding`),
  Supabase MCP, Trigger.dev MCP.
- **Secrets live only in 1Password vault `vibe_coding`. Never put a value in chat, a command line, a
  log, or a commit.** To run the credentialed replay gate, use the 1Password `op_run` tool so the value
  never enters the transcript:
  - command: `pnpm --filter @oracle/workers verify:r2-production-replay`
  - cwd: `C:\repos\oracle`, shell: `powershell`
  - env: `{"R2_REPLAY_DATABASE_URL": "op://vibe_coding/qcuyabwseaptvuzvtjejffi2ou/password"}`

  That item is `Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, eqccjfbyrywsqkxxpjvg)`.
  See §0 item 5 — its host is stale and the verifier compensates in code.
- The pinned-inventory gate needs the licensed file:
  `$env:R2_PINNED_FIXTURE_PATH='Z:\Documentation\company process - Oracle\Licensed Team Responsibilities 2 - tagged.txt'`
- Review artifacts land in `.ai/reviews/` (git-ignored). This session: two GLM reports under
  `glm-r2-f6-correction-audit-*`, and Codex output kept in the session scratchpad.

## 9. Open questions and risks

1. **21/30 on replay is EXPECTED, not a shortfall — do not "fix" it.** Replaying finished, stored
   records can only repair defects in the wording of a record that was actually produced. That
   recovered rows 19 and 29 (inflected-verb defects). Rows 20 and 23 have NO stored record at all
   (completion gaps) and row 15 produced no usable record, so they cannot come back this way. Reaching
   27/30 requires a fresh run through the corrected pipeline. **A future session that "improves" the
   corrector until a replay prints 27/30 has almost certainly cheated.**
2. **Row 5 remains the live unknown**, unchanged for several sessions. Its stored object carries a
   different duty's nouns and lacks the required `concepts` token — a wrong object or a wrong surviving
   seed, not an exception tail (established 2026-08-13 by independent review; do not re-derive). A
   boundary fix cannot invent a token missing from the source. **If row 5 is not honestly recoverable
   the ceiling is 26/30, below the gate. That is a stop-and-ask, not a reason to loosen anything.**
3. **The 27/30 arithmetic has no margin**: 19 preserved + 8 recovered = 27 exactly.
4. **The preservation gate proves preservation, not readiness** (dated 2026-08-25, still true). It says
   the correction work broke nothing production already got right. It does not predict a new run's score.
5. **Watch for anyone reintroducing an acceptance-rule exemption** or widening the condition-cue list
   beyond the locked section 8 cues to make a stubborn row pass. This has been attempted and rejected
   twice (2026-08-13 record-level completeness; the early F2 exemption).
6. **Reviewer agreement is not proof.** Gemini (2026-08-25) approved with no findings while dismissing
   a real weakness as circumstantially impossible; GLM initially did the same thing on a different
   finding this session and reversed only when shown a concrete counter-example. **When a reviewer
   dismisses a scenario as unlikely rather than impossible, push back with a counter-example.**
7. **Dated decisions, so a later session cannot unknowingly contradict them.** 2026-08-13: record-level
   completeness rejected as a weakening described as a broadening — do not revive. 2026-08-13: row 5
   does not share row 17's cause. 2026-08-14: a corrected record must reach persistence, not merely
   flip a verdict. 2026-08-26: the seam does not re-validate internally, by design; the audit is
   reconciled against persisted ids instead; the fidelity bypass is closed via the seed-span fallback
   and the no-seed residual is deliberately left accepting but counted.

---

## Retired in the same commit as this file (successor rule, `AGENTS.md` §3a)

- `2026-08-26T0214Z-edge-dev-claude-r2-f3-f4-replay-gate.md`. All three conditions checked:
  (1) its commits `b025e65`, `d3c1b4b`, `b48fcbc` and `f997f8e` are on `origin/main` — verified with
  `git log`; (2) every open obligation it carried is discharged or carried forward — its F5 was
  completed here including the `Z:` gate it could not run, its F6 is complete, and its §0 items 1 and 2
  are resolved (the drive) or carried forward verbatim (the stale 1Password URL, §0 item 5 above);
  (3) its dead ends are preserved — the `corepack pnpm` / no-`node_modules` traps, the dead direct DB
  host, the `aws-1` (not `aws-0`) pooler region, the permission-classifier workaround, the global
  best-assignment finding, and the F3e test-breakage lesson are all reproduced in §4, §5 and §8 here.

## Handoff self-audit — passed

1. **Could a brand-new developer with no project knowledge continue without skipping a beat?** Yes.
   §1 defines the app, stack, hosts, the files that matter, the two never-edit files, and every term
   (*seed*, *answer key*, *frozen matcher*, *gate*, *candidate stages*). §3 gives commit SHAs, phase
   status, the measured output of every gate, and the full F6 outcome. §6 gives ordered steps each with
   a verification gate.
2. **Could they continue as effectively as I can right now?** Yes. §4 records nine dead ends including
   the three that cost this session real time — the diverged-repo reconciliation, the Bash working
   directory silently reverting to a superseded worktree, and the no-op fix whose evidence was a
   tautology — plus the CRLF-in-literal break, the binary-grep trap, both test-construction dead ends,
   and the warning not to dismiss a reviewer finding over bad line numbers. §5 records nine findings
   including the three "do not "improve" this" traps.
3. **Is every relevant detail present?** Yes. Background §1–§2; state §3 with SHAs and measured gate
   output; failures §4; findings §5 with mechanisms; steps §6 each with a "worked when"; constraints
   §7; access §8 with the exact `op_run` shape and no secret values; risks §9 with dated decisions.
4. **Reading ONLY §0, would Albert see every decision he owes, including ones outside this
   workstream?** Yes — checked the hard way by walking §1–§9 line by line. The production run (§6.2,
   §9.1) → §0 item 1. The parked branch (§4.1) → item 2. The stale residual-matrix file → item 3. The
   missing read-only credential → item 4. The stale 1Password URL (§8, inherited) → item 5. The
   untracked clutter (§3) → item 6. Items 3–6 are all OUTSIDE this workstream and are promoted here
   precisely because that is the category that goes unraised. The "already settled" list carries nine
   prior rulings so none is re-asked.
