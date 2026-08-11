# R2 Source-Bound Final Record Correction Plan

Status: **PLAN ONLY. LOCAL IMPLEMENTATION NOT AUTHORIZED. PRODUCTION HARD STOP REMAINS.**

Created: 2026-08-11

Parent: [`plan_r2_source_span_inventory_reader.md`](plan_r2_source_span_inventory_reader.md)
Evidence: [`evals/r2-responsibilities.md`](evals/r2-responsibilities.md)
Handoff: [`HANDOFF.d/2026-08-11T1810Z-al8960ofc-codex-r2-final-record-plan.md`](HANDOFF.d/2026-08-11T1810Z-al8960ofc-codex-r2-final-record-plan.md)

## STATUS table

| Step | Status | Evidence / next gate |
|---|---|---|
| F0. Freeze the 19/30 evidence and correction boundary | ⬜ open | Re-score saved map `37a8fc62-23e4-46b7-8464-d1c784dc73cd` read-only; freeze eight eligible rows and three negative controls. |
| F1. Add generic failing final-record tests | ⬜ open | Invented cases reproduce inflected actions, condition leakage, wide objects, and incomplete exact-span duties. |
| F2. Add source-bound action and object normalization | ⬜ open | One pure helper returns source-supported canonical fields or fails loudly. |
| F3. Repair the existing late-completion acceptance seam | ⬜ open | Existing late candidates pass through F2 before existing validation; no new pass, dispatch, reservation, call, or retry is added. |
| F4. Integrate before final validation and assembly | ⬜ open | The production seam stays complete-only, source-ordered, one-to-one, and fully audited. |
| F5. Run unchanged local gates and residual replay | ⬜ open | All suites pass; the pinned source-support verifier stays 28/30 with rows 16/26 unsupported; a separate final-record replay keeps row 24 unsupported and recovers all 8/8 eligible shapes to reach the frozen 27/30 minimum. |
| F6. Independent review and owner decision | ⬜ open | Codex and GLM 5.2 approve with no P0/P1 before Albert decides on local landing. |

Fresh-session starting point: **read this file in full, then stop**. Albert must separately authorize
implementation before F0 or any application edit.

## 1. Ultimate goal

The Oracle must turn clear duties in company documents into short, accurate responsibility records
that preserve who does what, to which business object, under which condition, with exact source
proof. It must not lose a key word, attach an exception to the wrong field, or reject a duty because
the source used `provides` instead of `provide`.

The immediate goal is the smallest complete record supported by each exact source span, with an
honest refusal when that span is insufficient. Success is not making the score pass by any means.
If a step conflicts with this goal, the goal wins. Stop and flag the conflict.

## 2. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
upload business documents and ask questions. Trigger.dev workers segment documents, inventory
duties, complete missing fields with a configured model, validate evidence, and save reviewable
source maps. Later business-model merge and apply stages are separately guarded.

- Repo: `u2giants/theoracle`; checkout `C:\repos\oracle`; branch `main` only.
- Stack: TypeScript, pnpm, Turbo, Next.js 16, Trigger.dev, Drizzle, Supabase.
- Web: `https://oracle.designflow.app`; workers: `proj_wgpzsvhmsopqhvwqaycn`.
- Database: Supabase `eqccjfbyrywsqkxxpjvg`.
- Rules: `apps/workers/src/lib/responsibility-reader.ts`.
- Orchestration: `apps/workers/src/lib/source-workflow-read.ts`.
- Model contract: `packages/ai/src/prompts/workflow-read.ts`.
- Verifier: `apps/workers/src/__verify__/r2-responsibility-reader.ts`.
- Frozen matcher: `apps/workers/src/lib/responsibility-answer-key.ts`.

No UI, schema, deployment, or production operation is needed.

## 3. What triggered this work

The source-span reader passed local source support at 28/30. Albert authorized exactly one production
gate. Commit `62330bdb0b477abb373fa1d155b104cee45a8b66` shipped as worker `20260811.1`,
deployment `725f1ru9`. Run `run_06fv3keiq77bp0gpum352rls01` produced map
`37a8fc62-23e4-46b7-8464-d1c784dc73cd`, which scored **19/30** with unchanged
`field-aware-v3`. That is a binding hard stop.

| Row | Short duty | Exact production-visible reason | Status |
|---:|---|---|---|
| 5 | submit concepts into systems | Record exists, but object omits `concepts` and absorbs unrelated details; another exact compact seed was not represented correctly. | eligible |
| 14 | download PPS photos | Record exists but drops `PPS`, leaving 5/6 required object tokens. | eligible |
| 15 | rename PPS files by SKU | Inventory exposes the rename duty, but no usable rename record survives. | eligible |
| 16 | Licensed Team reviews PPS against tech pack | Completion child says `Lic Coordinator` and only `Review PPS photos`; required owner and object are not both visible. | **ineligible** |
| 17 | submit PPS photos in portals | Correct duty absorbs an exception sentence; its `do not` creates a false negation conflict. | eligible |
| 19 | fill out Letter of Guarantee | Correct record is `Fills out LOG...`; final fields keep the inflected action. | eligible |
| 20 | request sample exemption | Exact span contains the duty, but seed remains a final `completion_gap`. | eligible |
| 23 | request audits before expiration | Exact span contains role, action, object, and timing, but remains a `completion_gap`. | eligible |
| 24 | download style guides to server | Exact span says Licensed Team assists Design Team in downloading. Treating assistance as direct download changes the action family and may misstate the duty. | **ineligible** |
| 26 | submit quarterly royalty reports | Visible span says only that forecast reports are quarterly; no owner or submit action. | **ineligible** |
| 29 | provide assets to partners | Correct record uses `provides`; base action is not retained. | eligible |

Production used 21/40 calls, 63,015/500,000 input tokens, 1/1 general repair, and
$0.350742/$10. This was not budget exhaustion. Merge, apply, and serving stayed false; all protected
business-model tables remained empty.

## 4. Scope

### In scope

- Reduce ordinary source duty-verb inflections to the existing base duty verb.
- Select the smallest complete object supported by the exact completion-visible span.
- Keep explicit conditions and exceptions in `trigger` or audit, not in the affirmative object.
- Preserve a required named artifact token when present in the exact span.
- Route candidates already produced by the existing late-completion path through the same source-bound
  canonicalizer before its existing validation. Do not add another opportunity or dispatch.
- Persist before/after fields, reasons, accepted/rejected status, seed ID, and source-span hash.
- Add generic tests and verifier-only replay of the production failure shapes.

### Out of scope

- Recovering rows 16, 24, or 26 under the current source-span contract.
- Earlier headings, nearby duties, source prefixes, answer-key aliases, or fixture terms as context.
- Matcher, key, threshold, model, route, pool, cache, concurrency, or budget changes.
- New call or retry allowances; segmentation/owner redesign; DB; UI; chat; merge/apply/serving.
- Deployment, production, bake-off, or another live gate.
- Arbitrary noun stemming or broad language rewriting.

## 5. Current state of the code

- `responsibilityCompletionRequest` at `responsibility-reader.ts:201` exposes only the exact seed span,
  quote, offsets, and mutable fields. Keep it unchanged.
- `validateResponsibilityFieldFidelity` at `responsibility-reader.ts:573` checks exact-span field
  support but does not create a compact final record.
- Existing `stemDutyVerb` use near `responsibility-reader.ts:1145` and `:1352` already supplies a
  narrow verb-family mechanism. Do not add a second general stemmer.
- `canonicalizeForcedResponsibilityOutput` at `responsibility-reader.ts:1602` protects IDs and source
  binding for omission work. It is not a general final-field normalizer.
- `validateResponsibilityRead` at `responsibility-reader.ts:2603` owns final validation and complete
  element selection.
- Orchestration builds inventory near `source-workflow-read.ts:2930`, exhaustive completion near
  `:3055`, late completion near `:3401`, and complete-only assembly near `:3774`.
- Audit persistence is near `source-workflow-read.ts:3899`.
- The matcher at `responsibility-answer-key.ts:49-178` stays unchanged.
- Existing code is committed, pushed, deployed, and tested. This plan has no implementation.

## 6. Key findings and root cause

1. Source discovery is not the only problem. Several misses already have complete or near-complete
   records; their final fields cause rejection.
2. A model object may copy a whole sentence or list. Fidelity can accept source words even when a
   separate exception changes the object's apparent polarity.
3. Verb handling differs by stage. Deterministic parsing stems verbs; accepted model fields may keep
   `provides` or `Fills out`.
4. Exact seeds can remain incomplete despite ample total budget. The current late completion already
   reaches those seeds; its candidates need the same final-field correction before existing validation.
5. Object minimality differs from evidence minimality. Evidence remains verbatim; normalized fields
   should isolate the duty while retaining conditions in structured audit/trigger data.
6. Rows 16, 24, and 26 are honest refusals and required negative controls.
7. This plan's honest target is 27/30. Eight eligible recoveries plus 19 current matches equals the
   frozen passing minimum. The broader source-support ceiling remains 28/30.

## 7. Approaches considered and rejected

1. Restore hidden source-prefix owner lookup. Rejected because it exposes text outside the request.
2. Borrow headings or nearby duties. Rejected for the same honesty reason.
3. Add matcher aliases or weaken negation checks. Rejected because this hides bad stored fields.
4. Raise budgets, retries, or model cost. Rejected because production left large capacity unused.
5. Prompt-only cleanup. Rejected because prior prompt/model changes stayed near 11-19/30 and cannot
   own deterministic acceptance.
6. General English lemmatizer. Rejected because it adds broad behavior and may change business nouns.
7. Delete all extra object words. Rejected because qualifiers can be essential.
8. Recover rows 16/24/26. Rejected because their visible spans do not support the expected action,
   owner, and object combination without changing meaning or borrowing context.
9. Run another gate. Rejected because the parent plan consumed its one gate and hard-stopped.

## 8. Design decisions

### Locked, 2026-08-11

1. `responsibilityCompletionRequest(seed).sourceSpan` is the only semantic source.
2. Quote, chunk, offsets, seed ID, and source hash are immutable.
3. Correction occurs before final validation and complete-only assembly.
4. Action normalization reuses the existing duty-verb parser and cannot change action family.
5. A separate condition may leave `object` only when retained in `trigger` and durable audit. This is
   safe for the frozen score because `field-aware-v3` checks negation only in `action + object` at
   `responsibility-answer-key.ts:62-73`; a generic test must prove the condition remains visible in
   `trigger` while the affirmative object no longer carries its negation.
6. Required named source tokens cannot be silently lost.
7. Rows 16, 24, and 26 remain unsupported negative controls.
8. Matcher, key, threshold, route, model, budgets, DB, merge/apply/serving, deployment, and production
   stay untouched.
9. Ambiguity fails loudly and leaves the seed incomplete.

### Open judgments

- Exact helper name.
- Exact helper and audit field names, provided the locked field rules below remain unchanged.
- Whether the existing `trigger` needs an additional audit-only condition field. `trigger` retention
  itself is mandatory.

### Locked field-boundary rule

1. Find the one source duty verb whose family matches the candidate action. Start the normalized
   object immediately after that verb, excluding a grammatical subject or helper verb.
2. End the object at the first explicit boundary after a complete object: terminal punctuation;
   newline/list marker starting a new clause; a coordinating conjunction followed by a different
   duty verb; or a separate exception/condition cue such as `except`, `unless`, `only if`, `if`,
   `does not`, or `do not` after the affirmative duty is complete.
3. Before ending, retain named artifacts, acronyms, destinations, systems, timing, cadence, and
   direction attached to that duty. Never copy a token from another seed or clause.
4. Put a separated condition or exception into `trigger` verbatim and record its source offsets/hash
   in the correction audit. If the boundary is ambiguous, reject the correction.
5. For compound list text, isolate only a clause that contains its own actor or inherited seed owner,
   duty verb, and object. A later sibling clause cannot complete an earlier clause.

## 9. Implementation plan

### Phase A: Freeze evidence and tests

#### F0. Freeze the residual boundary

Files: `apps/workers/src/__verify__/r2-responsibility-reader.ts`.

Actions: add verifier-only production-shaped actual records; assert 19/30 with unchanged matcher;
freeze eligible rows 5,14,15,17,19,20,23,29 and negative controls 16/24/26; assert fixture SHA,
matcher version, threshold, budgets, and false safety defaults. Do not put fixture terms in production.

Dependency: none.

Verification gate: `pnpm --filter @oracle/workers run verify:r2-responsibilities` reproduces 19/30
and refuses rows 16/26 as targets.

#### F1. Add generic failing tests

File: `apps/workers/src/__verify__/r2-responsibility-reader.ts`.

Add invented cases for regular and multi-word verb inflection; noun non-stemming; negative exception
separation; over-wide list object; omitted named artifact; final incomplete seed retry; atomic bad
batch rejection; ambiguous object refusal; missing owner/action refusal; polarity; immutable source
binding; stable order and audit.

Dependency: F0.

Verification gate: new cases fail for intended current-code reasons before production edits and all
existing cases stay green.

### Context cut point A

Start a fresh implementation session. Re-read sections 6-11 and confirm the diff has tests only.

### Phase B: Pure correction and incomplete-seed handling

#### F2. Add one pure source-bound canonicalizer

Files: `apps/workers/src/lib/responsibility-reader.ts` and its verifier.

Actions:

1. Accept one immutable seed and one candidate, with no surrounding source.
2. Canonicalize action only when exactly one compatible source verb family explains it.
3. Isolate an object using explicit clause boundaries while preserving artifact, destination, timing,
   cadence, and direction.
4. Move a separate condition to trigger/audit; never discard or hide polarity.
5. Re-run existing fidelity validation. Accept only strict improvement.
6. Return typed audit with seed/hash, original/proposed fields, accepted flag, and reason codes.
7. Keep source binding and non-mutable fields immutable.

Dependency: F1.

Verification gate: all F1 tests pass and the production file contains no answer-key terms.

#### F3. Repair the existing late-completion acceptance seam

Files: `apps/workers/src/lib/source-workflow-read.ts`, optionally a pure queue helper in
`responsibility-reader.ts`, and verifier.

Actions: keep `lateResidualResponsibilitySeeds` and `runLateResponsibilityCompletion` at
`source-workflow-read.ts:3401-3540` as the only late path. Insert F2 between each returned late
candidate and the existing `validateResponsibilityRead` call at `:3449-3470`. Do not add a new seed
queue, completion stage, dispatch, budget reservation, call, or retry. If a candidate still fails,
persist the existing incomplete outcome and new F2 reasons. Preserve existing atomic batch rejection,
strict-improvement selection, execution audit, budget accounting, and stable order.

Dependency: F2.

Verification gate: a generic 40-seed stub proves each residual seed is dispatched by the existing late
path at most once; F2 can make an existing returned candidate pass without any new call; malformed,
ambiguous, or over-budget seeds remain incomplete; reversed async timing does not change order.

### Phase C: Production seam and audit

#### F4. Integrate before final assembly

Files: `apps/workers/src/lib/source-workflow-read.ts`, `responsibility-reader.ts`, verifier.

Actions: use one shared F2 seam for candidate stages before final validation; revalidate combined
state once; preserve source order and one-to-one assembly; persist a
`responsibilityFinalRecordCorrection` audit with counts, IDs, reasons, hashes, and execution refs;
keep incomplete status degraded and all safety flags off.

Dependency: F2/F3.

Verification gate: production-used orchestration test covers base, deterministic, exhaustive, final
correction, rejection, audit, assembly, and degraded status without a test-only copy.

### Context cut point B

Start a fresh verification session. Re-read the plan and audit every production hunk for hidden
context, matcher bypass, or fixture leakage.

### Phase D: Local gates and reviews

#### F5. Run unchanged local gates

```powershell
pnpm --filter @oracle/workers typecheck
pnpm --filter @oracle/ai typecheck
pnpm --filter @oracle/engines typecheck
pnpm --filter @oracle/workers run verify:r2-responsibilities
pnpm --filter @oracle/workers run verify:r2-pinned-inventory
pnpm --filter @oracle/workers run verify:source-workflow-read
pnpm --filter @oracle/workers run verify:r0-reader-validator
pnpm --filter @oracle/workers run verify:document-ingestion-fallback
pnpm --filter @oracle/ai run verify:r2
pnpm --filter @oracle/ai run verify:workflow-read
pnpm --filter @oracle/engines run verify:macro
pnpm --filter @oracle/engines run verify:macro-first
pnpm --filter @oracle/engines run verify:r1-cross-shape
pnpm --filter @oracle/engines run verify:r2-responsibilities
git diff --check
```

Also require unchanged pinned support 28/30 with rows 16/24/26 unsupported under this correction;
verifier-only recovery of all 8/8 eligible shapes, because 19 + 8 = the frozen 27/30 minimum;
preservation of 19/19 prior matches; anti-leak pass; and no changes to
limits, model, matcher, answer key, threshold, flags, schema, migrations, or deploy files.

Stop on fewer than 8 recoveries, any regression, hidden support for 16/26, or any failed command.

Verification gate: all commands and added gates pass in one fail-fast run.

#### F6. Independent review and owner decision

Run fresh read-only Codex review; continue the existing GLM 5.2 R2 session; require row-by-row honesty,
locked-decision audit, and `APPROVED FOR LOCAL LANDING REVIEW` or `CHANGES REQUIRED`; fix findings;
rerun F5; then ask Albert only whether to authorize local landing. Deployment and production are a
separate future decision.

Dependency: F5.

Verification gate: both reviews have no P0/P1, F5 remains green, and Albert receives measured results.

## 10. Tests required

Pure tests: verb inflection; no noun stemming; source-token provenance; minimal object with named
artifact; separate positive duty/negative condition; ambiguous boundary refusal; missing required
fields; immutable binding; strict improvement; stable audit reasons.

Orchestration tests: each eligible seed queued once; unchanged budget/concurrency/order; no new retry;
atomic batch rejection; full revalidation; rejected seed remains visible; complete-only one-to-one
assembly; audit persistence; rows 16/24/26 analogues stay rejected; residual replay recovers all 8/8
eligible shapes and preserves 19/19 with unchanged matcher.

Run every F5 suite. None may be skipped. The unchanged pinned verifier continues to measure source
support only and must remain 28/30 with rows 16/26 unsupported. The separate final-record replay is
the check that must keep row 24 unsupported while proving the eight eligible final records.

## 11. Constraints and gotchas

1. `main` only. Implementation is not authorized by plan creation.
2. Use `apply_patch`; preserve unrelated untracked/concurrent work.
3. Before commit, identity must be `Albert Hazan <u2giants@users.noreply.github.com>`.
4. No DB change or app-repo migration.
5. No production read is needed; saved evidence is sufficient.
6. No second gate, bake-off, deployment, or Vercel action.
7. Do not weaken evidence, field fidelity, polarity, matcher, key, or threshold.
8. Use only `responsibilityCompletionRequest(seed).sourceSpan`.
9. No headings, prefixes, siblings, nearby duties, aliases, or fixture terms.
10. Frozen limits stay 40/500k/$10 and 1/5/1; no new allowance.
11. Merge, apply, serving remain false; incomplete inventory is audit-only.
12. No silent fallback; no hard-coded model/provider; no UI work.

## 12. Access and environment

- Windows 11 `al8960ofc`; PowerShell; `C:\repos\oracle`; branch `main`.
- pnpm/Node are installed. `gh` is authenticated only for later landing.
- GLM uses `ai-glm` with `AI_GLM_CALLER=codex`; continue an existing R2 session.
- Production credentials are not needed. Any later secrets remain in 1Password vault `vibe_coding`
  and values must never be printed or committed.
- Supabase and Trigger.dev stay unused under this plan.

## 13. Definition of done, risks, rollback, and open questions

Done means: pure helper and tests; one shared production seam; existing-budget incomplete handling;
all 8/8 eligible recoveries; 19/19 prior matches; rows 16/24/26 still unsupported; all F5 gates and
reviews green; docs/handoff current; exact diff committed/pushed with green CI only after separate
owner approval; and zero deploy/production/merge/apply/serving action.

Risks: over-normalization, hidden negation, lost qualifiers, budget exhaustion, fixture tuning, and
mistaking local replay for live proof. Mitigate with exact-span tokens, strict improvement, condition
audit, qualifier tests, existing budget refusal, invented fixtures, and honest local-only reporting.

Rollback: before landing, remove only reviewed hunks. After a later approved landing, revert the
single correction commit. No data rollback exists. Never use `git reset --hard`.

Open questions: whether the locked compact-object rule safely covers rows 5/14/17 and whether larger
documents fit the remaining frozen budget. Tests decide. Row 24 is no longer an open target. If any
of the eight eligible shapes fails, stop and ask Albert. Do not lower the eight-row gate.

## Implementation-plan self-audit

1. A new session can execute without questions. Sections 1-4 define goal, app, evidence, rows, and
   scope. Sections 5-8 give exact code state, root cause, dead ends, and locked/open decisions,
   including the exact object/condition boundary rule and existing late-completion seam.
   Sections 9-13 give files, dependencies, gates, commands, access, stop rules, landing, and rollback.
2. All current nuance is carried. Sections 3, 6, and 7 distinguish 28/30 local support from 19/30
   production, record all 11 reasons, unused budget, hidden-context failure, and rejected shortcuts.
3. The goal is decisive. Section 1 requires the smallest complete exact-source record and honest
   refusal, and makes that goal override any conflicting step.

All 13 required sections, explicit scope, rejected approaches, locked/open decisions, named tests,
file/function targets, per-step gates, secret locations, commit/push/CI boundary, explicit no-deploy
rule, and plan/handoff links are present. The implementation-plan-writer self-audit passes.
