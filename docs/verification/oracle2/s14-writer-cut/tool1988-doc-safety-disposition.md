# Tool1988 / doc-safety recovery disposition

**Parent:** #24 closeout ledger · **Date:** 2026-10-26 EDT · **Class:** code (docs + candidate evidence only; no toolkit install, no reviewer repair)

## Item scope

Recover/land the Tool1988 candidate matcher path, or document the exact remaining CI blocker with evidence. Do not invent a green CI.

## Candidate facts (preserved)

| Fact | Value |
|---|---|
| Candidate commit | `2634e51f422f2184697750c1f41450f1a373ed0b` |
| Branch | `origin/codex/oracle-boundary-linear-01a16013` (popcre/ai-devops) |
| PR | [popcre/ai-devops#1988](https://github.com/popcre/ai-devops/pull/1988) CLOSED/parked |
| Change | `LC_ALL=C` scoping on the tailnet matcher in `bin/ai-public-boundary-check`, plus locale-parity test in `tests/test-public-boundary-versions.py` |
| Local gates | 20 cases / full gates passed; 26-locale byte parity with original Git ERE |
| Shard4 | green |
| Successor CI | FAILED on a **separate** StepFun pacing test — not the matcher path |

## Exact remaining CI blocker (evidence)

The matcher path itself is correct and locally proved. CI still fails in
`tests/test-ai-stepfun.sh` on the pacer test `paces_before_call`:

- **Test intent:** three concurrent asks against a provider that refuses any call within 2s of the previous one. With `AI_STEPFUN_RPM=1` and `AI_STEPFUN_PACE_WINDOW=2`, the pacer must space starts ≥2s so the three calls never 429.
- **Observed failure (closeout evidence):** starts at `1792665365 / 66 / 68 / 70`; first gap is **1s instead of 2s**; **four provider calls after a 429** vs expected three.
- **Meaning:** the shared pacer's slot arithmetic (`tools/lib/stepfun-pace.sh` `_stepfun_pace_slot`) admits a start that is only 1s after the previous one under concurrent load, the stub correctly 429s, and the retry path then produces a fourth call.
- **Not caused by** the Tool1988 matcher diff. That diff touches only `bin/ai-public-boundary-check` and `tests/test-public-boundary-versions.py`.
- **Not repaired here:** no cause repaired, no rerun, no provider retry, no test suppression. Closeout constraint "no toolkit/reviewer repair on the way out" remains respected; this document records the blocker, it does not install or merge the candidate.

## Disposition

**Held — exact CI blocker documented with evidence. Landing requires a green
run of `tests/test-ai-stepfun.sh::paces_before_call` (or an independently
reviewed pacer fix) on top of candidate `2634e51f`.**

What is proven:

1. The candidate matcher path (bounded external `LC_ALL=C` grep) matches original Git ASCII tailnet behavior byte-for-byte across available locales (local 26-locale parity, 20 cases, full gates, shard4 green).
2. The remaining CI failure is isolated to StepFun pacer timing under concurrency (`paces_before_call`), not to `ai-public-boundary-check` or its tests.

What is held:

1. Merging/installing candidate `2634e51f` (PR1988 stays parked; auto-merge disabled).
2. Any toolkit/reviewer repair.
3. A claim of green CI.

## Recommended next action (for root)

1. Reproduce `paces_before_call` on a quiet machine and capture exact `burst.*.out/.err` and `pace/starts` bytes.
2. Fix the pacer slot boundary (likely `oldest + STEPFUN_PACE_WINDOW - now` rounding under concurrent `flock`) in a separately reviewed ai-devops change.
3. Re-open or re-cut PR1988 from exact `2634e51f` plus the pacer fix; land only on a green full suite.
4. Installation still needs the normal `ai-review` lifecycle APPROVE, separate installation candidate, and one-use `authorize-install` tied to the actual installed checkout/launcher — candidate source-only gate PASS does not satisfy installation.

## Boundaries preserved

- No POP shared-db claim (Tool1988 is popcre/ai-devops toolkit, not Oracle DB structure).
- No production, no company comparison, no live cutover.
- No reviewer repair during observation week.
- Candidate `2634e51f` remains remotely preserved on `origin/codex/oracle-boundary-linear-01a16013`.
