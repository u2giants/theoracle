# R2 Completion Recovery Cycle Plan

## STATUS table

| Step | Status | Evidence |
|---|---|---|
| G0. Owner authorization of another correction cycle | DONE 2026-08-27 | Albert authorized "another correction cycle" after the 22/30 gate. |
| G1. Diagnose why each missed row is missed, read-only | DONE 2026-08-27 | `verify:r2-missed-row-diagnosis` against map `aa713247-...` splits the five real misses into two distinct causes: rows 19 and 23 `NO_RECORD_PRODUCED_ON_THE_SUPPORTING_SPAN`; rows 5, 14 and 15 `RECORD_PASSES_FIDELITY_BUT_FAILS_THE_MATCHER`. Production audit confirms 40 of 96 completion outcomes were `validation_rejected` and the late pass never ran. |
| G2. Repair the starved late completion pass | DONE 2026-08-27 | `apps/workers/src/lib/source-workflow-read.ts`: late-pass `handledIds` now come from ACCEPTED completion outcomes, not from every SCHEDULED seed. Two new deterministic cases in `verify:r2-responsibilities` lock both the helper behaviour and the production wiring. All 16 gates pass; replay hash `013e40ca...` unchanged. |
| G3. Address the object-wording misses (rows 5, 14, 15) | OPEN - NOT STARTED | Separate, riskier work. Evidence gathered but no code change attempted. See section 7. |
| G4. Measure in production | DONE 2026-08-27 - **23/30, still below the 27 threshold** | Albert authorized one run. Worker `20260827.2` (deployment `a877o1d9`), run `run_06g45qkld9p9931i6qp4quk501`, one attempt, COMPLETED, $0.0054. Map `224ca68d-82c8-4954-ac65-59b02db00546`, 95 stored records. **The repair worked mechanically**: the completion stage ran 2 batches and 2 executions instead of 1 and 1, and re-attempted 47 previously rejected seeds. **Row 19 recovered.** Row 23 did not. Score 23/30, all 19 prior rows still preserved, negative controls 16/24/26 still unmatched. All 16 gates re-pass; replay hash `013e40ca...` unchanged. |
| G5. Remaining shortfall | OPEN | Rows 5, 14, 15 (object wording) and row 23 (still no record on its span). See sections 6 and 7. |
| G6. Feed rejection reason codes into the late pass | DONE 2026-08-27, NOT YET MEASURED | Albert funded a third cycle. Each residual seed is now re-asked WITH the deterministic reason codes its previous candidate was rejected for, carried in the request payload so the packer estimates it, capped at 6 codes of 160 chars. Completion prompt moved to `responsibility-completion-v2` and explains each code without proposing an answer. Nine deterministic cases plus four source assertions lock it. All 16 gates pass; replay hash `013e40ca...` unchanged. |
| G7. Measure G6 in production | BLOCKED ON OWNER | Needs a fresh authorization for exactly one run. |

## 1. Ultimate goal

Recover the business duties the Oracle reader currently loses, without inventing facts and without
weakening any evidence rule. If a step conflicts with that goal, the goal wins: stop and flag it
rather than tuning the matcher, the answer key, the validator or the threshold.

## 2. What this application is

The Oracle turns POP Creations documents into source-grounded business knowledge. Repository
`u2giants/theoracle`, `main`, TypeScript, pnpm, Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`,
production Supabase `eqccjfbyrywsqkxxpjvg`.

## 3. What triggered this work

The one authorized production run of 2026-08-27 (`run_06g423t548pl6pc50ii4e2iv01`, worker
`20260827.1`, map `aa713247-e30f-4b0c-9b93-e02fdefd4048`) scored **22/30** against a frozen threshold
of 27/30. Preservation held completely and rows 17, 20 and 29 were recovered, but rows 5, 14, 15, 19
and 23 were still missed. Albert authorized another correction cycle. Full record:
[`plan_r2_fresh_production_gate.md`](plan_r2_fresh_production_gate.md).

## 4. Scope

In scope: read-only diagnosis of the measured misses; structural repair of the completion pipeline
where the evidence names a concrete defect; deterministic local proof; documentation.

Out of scope: any change to the answer key, the `field-aware-v3` matcher, the 27/30 threshold, the
fidelity validator's strictness, the frozen route/model, budgets, retries, concurrency, schema,
migrations, secrets, or the business-model flags. No production run without a new authorization.

## 5. Current state of the code

`main` carries the 22/30 result. This cycle adds two SELECT-only verifiers
(`verify:r2-fresh-map-score`, `verify:r2-missed-row-diagnosis`) and one production fix in
`apps/workers/src/lib/source-workflow-read.ts`. All 16 local gates pass and the SELECT-only
preservation replay is byte-identical to before the change.

## 6. Key findings and root cause

The 2026-08-27 run detected **139** source-bound duty seeds and stored only **102** records. The
production audit shows why: of **96** seeds sent to the completion stage, **56** were accepted and
**40** came back `validation_rejected`. The rejections are legitimate — 12 involve
`condition_not_preserved_in_trigger`, 11 are quote-policy failures, and the rest are
`action_family_mismatch`, `object_qualifier_loss`, `owner_mismatch` or `invented_object_content`. The
validator was doing its job.

**The defect is what happened next: nothing.** The pipeline already has a late completion pass built
to give an unresolved seed one more source-bound attempt. It was fed
`handledIds = responsibilityCompletionAudit.residualSeedIds` — every seed that had been **scheduled**,
regardless of outcome. That conflates "we asked about this seed" with "this seed is answered", so all
40 rejected seeds counted as handled, `lateResidualSeeds` was empty, and the late pass never executed.
The run finished having spent **21 of its 40 authorized model calls** and $0.36 of a $10 budget.

Answer rows 19 and 23 are two of the duties lost exactly this way. The fix builds `handledIds` from
**accepted** outcomes only. It widens which seeds the existing late pass considers; it adds no stage,
relaxes no validator, and raises no budget. Every late candidate still passes through the same
unchanged corrector, strict-improvement selection and `validateResponsibilityRead`.

## 6a. What the measurement changed

The repair did exactly what it was designed to do and it was not enough. On the second run the
completion stage ran **2 batches and 2 executions** instead of 1 and 1, and re-attempted **47**
previously rejected seeds. Row 19 came back. Row 23 did not: its candidate was rejected again, on the
same source-bound fidelity grounds. Stored records moved from 102 to 95 while the score rose from 22
to 23 — record COUNT is not the objective and must not be used as a proxy for it.

That reframes the remaining work. Of 148 completion outcomes on the second run, **95 were
validation-rejected**. Giving those candidates another identical attempt does not help, because the
model is asked the same question and returns a candidate that fails the same rule. The next lever is
not another retry: it is telling the model WHY its candidate was rejected. The rejection reasons are
already computed, already audited, and already specific — `condition_not_preserved_in_trigger`,
`object_qualifier_loss:<tokens>`, `action_family_mismatch`, `owner_mismatch`. Feeding those codes
back into the late-pass prompt is a genuinely different attempt, keeps the validator authoritative,
and invents nothing. That is the recommended next cycle, and it is NOT authorized yet.

## 7. Rejected approaches, and the open work

Rejected outright:

- Do not relax the fidelity validator to admit the 40 rejected candidates. Those rejections are the
  evidence rule working; admitting them would manufacture a score from bad records.
- Do not weaken `field-aware-v3`, the answer key, or the 27/30 threshold to close rows 5, 14 and 15.
- Do not raise budgets, retries or concurrency. The failed run used barely half its allowance; the
  constraint was never capacity.
- Do not add a second late pass or a new completion stage. The existing one was starved, not missing.

**G3, still open.** Rows 5, 14 and 15 each DO have a stored record on the correct source span that
passes fidelity, but whose object wording does not satisfy the frozen matcher. Row 14 is the sharpest
case: its object carries five of the six expected tokens and **zero** unexpected ones — a strict
subset missing one qualifier. Row 15 has two of four expected tokens and one unexpected. Row 5 has two
competing supporting spans and matches neither. Any fix here changes how objects are constructed,
which is the same seam that currently protects all 19 preserved rows, so it needs its own plan,
its own regression proof and its own review. It was deliberately not attempted in this cycle.

## 8. Locked and open decisions

Locked: answer key `licensed-team-responsibilities-v1`; matcher `field-aware-v3`; threshold 27/30;
negative controls rows 16, 24 and 26; frozen route and limits; all three `business_model_*_enabled`
false; no production run without a new explicit owner authorization.

Measured 2026-08-27: the repaired late pass is worth **one row** on this document (row 19). Row 23
did not return. The remaining shortfall is four rows and is NOT a retry-wiring problem.

## 9. Execution plan

1. **Diagnose read-only.** Done. `verify:r2-missed-row-diagnosis` names one cause per missed row.
2. **Repair the starved late pass.** Done, with the deterministic cases in section 10.
3. **Prove nothing regressed.** Done. All 16 gates pass and the SELECT-only replay is unchanged.
4. **Ship the record.** Done: this plan, the drift log, `evals/r2-responsibilities.md`, `main`, CI.
5. **Measure.** Done 2026-08-27 on Albert's authorization. The late pass ran (2 completion batches
   and 2 executions, 47 rejected seeds re-attempted) and row 19 returned. Score 23/30.
6. **Then, separately, G3 and row 23.** Now informed by the measurement in section 6a.

## 10. Tests required

The full section-10 list from [`plan_r2_fresh_production_gate.md`](plan_r2_fresh_production_gate.md)
— all 16 commands — plus the two new deterministic cases inside `verify:r2-responsibilities`:

- the pre-fix defect is reproduced: treating every scheduled seed as handled starves the late pass;
- a `validation_rejected` seed reaches the late completion pass;
- and two source assertions that pin the production wiring, so `residualSeedIds` cannot return.

`verify:r2-missed-row-diagnosis` is a diagnostic, not a gate: it needs the production database and is
run deliberately, not in CI.

## 11. Constraints and gotchas

Never print licensed source text, secrets, model responses or production rows. Never delete a map.
Never run a migration. The late pass is budget-guarded; if a future change makes it run away, the cap
is the frozen per-source budget, not this fix. `apps/workers/src/__verify__/r2-responsibility-reader.ts`
uses CRLF line endings — match them or the source assertions silently stop matching.

## 12. Access and environment

`al8960ofc`. GitHub, Trigger.dev CLI, Supabase MCP (read-only) and 1Password are authenticated. Vault
`vibe_coding` is id `pimcaogmxxzoafh7lsluj6uxkq`; `op://` refs must use item IDs, not titles. The
SELECT-only verifiers read `R2_REPLAY_DATABASE_URL` from item `qcuyabwseaptvuzvtjejffi2ou`, field
`password`. The licensed fixture is mounted at the path in the production plan's section 10.

## 13. Definition of done, risks, rollback, and open questions

This cycle is done: the defect is repaired, locked by deterministic tests, proven not to regress any
existing gate, shipped green, and measured in production at 23/30. The business goal is NOT met — the
threshold is 27/30 — and this is an honest partial gain, not a pass.

Risk: the late pass now runs where it previously did not, so a future run will spend more of its
authorized model calls. That is the intended behaviour and it stays inside the frozen budget.
Rollback is a one-line revert of the `handledIds` construction. The open question is the measured
recovery, and rows 5, 14 and 15 remain unaddressed by design.

## Self-audit

1. Yes. Sections 2-13 give a new session every identifier, cause, gate and stop condition without
   chat context.
2. Yes. Sections 3, 6, 7 and 8 preserve the measured failure, the root cause, the rejected shortcuts,
   and the work deliberately left open.
3. Yes. Section 1 states the business goal and makes it win over any conflicting step.

Cycle handoff: [`HANDOFF.d/2026-08-27T1130Z-al8960ofc-claude-r2-late-pass-measured.md`](HANDOFF.d/2026-08-27T1130Z-al8960ofc-claude-r2-late-pass-measured.md).
