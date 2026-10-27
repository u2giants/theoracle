# W10-SAME-WORKER-FIT — accepted standing gap (test population only)

This record belongs to parent #24. It is a named, accepted test-budget gap
record so the W10 SAME worker-fit shortfall survives on main when PR214's real
cuts land. It does not close any S/U/W gate, weaken any W10 assertion, grant an
operation, or satisfy business acceptance.

## Named gap

`W10-SAME-WORKER-FIT` — the W10 SAME test population does not fit the shared
120-second worker budget after all honest wall-time cuts. Status: **ACCEPTED AS
STANDING** (decision 2026-10-27 by the parent #24 coordinator on Albert's
instruction to decide the gap; recorded at
https://github.com/u2giants/theoracle/pull/214#issuecomment-6445113793 with
rationale). No factory-path optimization project is funded at this time. Albert
may override by funding the optimization.

## Measured figures — synthetic test/exercise only

**These are test-exercise wall-clock figures from the invented synthetic
population. They are NOT production RTO/RPO and must never be quoted as
production figures.** (S13 production RPO/RTO remain separate and unproven.)

- W10 population after all cuts on PR214's branch: **~1357 s** vs the **1200 s**
  shared test capacity (10 workers × 120 s) → shortfall **~157 s**.
- Bound: factory-call latency (~250 ms × 7 factory calls per test:
  `prepare_latest_v1`, `claim_v1`, `receipt_v1`, `status_v1`, `control_v1`,
  `observe_audience_v1`, each ~14 SQL queries incl. 4× `_check` full
  capability-catalog validation).
- Per-suite (test-exercise): 8 doc workers ~902 s total (all fit); event-01 and
  event-02 exceed 120 s. Raw measurement note:
  https://github.com/u2giants/theoracle/pull/214#issuecomment-6431856709.

## Why it cannot fit (2026-10-27)

Cannot fit W10 SAME without weakening assertions, adding workers, or raising
the 120 s budget — all three forbidden. One production-code optimization was
attempted and reverted: factory CA-hash + catalog-validation caching (4e00d9ed)
made doc workers slower (+2–6 s each); reverted (e6fef461). A blind cache is the
wrong layer. The deeper fix (the `_check` 4× catalog join) is production-code
surgery with regression risk right after PR200 landed meeting-participation
source composition — wrong trade for a test-budget-only benefit.

## Constraints kept (non-negotiable)

W10 SAME shared 120 s / ten workers / per-request ≤30 s / full mandatory
population / 0 F/E/S/timeout/launch/cleanup. No case cuts, no budget raises, no
added workers, no weakened assertions. The gap stays visible; it is not a silent
skip.

## Revisit triggers (any one)

1. W10 SAME becomes a release blocker for a real release gate.
2. Production factory call latency is measured as a real business problem.
3. A factory-path optimization is proposed that does not repeat the reverted
   caching approach (target the 4× catalog join in `_check` itself) and carries
   its own before/after measurement on doc workers too.

Real cuts kept with this gap (genuine test-wall-time reductions, assertions
preserved): fixture batching + `owned_worker_database` cache
(`dcc6bb8d`), sleep shortening to minimum valid + `capture_seconds` default
reduction (`4a6d2019`), `event-XX` worker labels (`2dfdbd9c`), W10 rebalance to
ten workers with event-01/event-02 split (`8cb09224`).

Posted by MiMo chat ses_ffe5e817fbf44ffe18jWbn2i1z on edge-dev.
