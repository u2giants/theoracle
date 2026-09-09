---
issue: 4
status: BLOCKED
owner: codex/r2-canonicalization-flat
---

# R2 source-bound canonicalization shipped but production remained 23/30

## 0. Decisions only the owner can make

Blocking another production attempt: authorize a new, separately bounded correction cycle only after
read-only evidence identifies a different lever for rows 5, 14, 15 and 23. Recommendation: do not fund
another run of source-bound canonicalization; production proved it does not move the score.

Deferred security decision: the exposed DesignFlow MCP and NAS MCP bearer tokens still need rotation.
Recommendation: authorize both rotations, update their configured references, verify both services, and
retire the old values.

Already settled — do not re-ask: no retry for the 2026-09-09 cycle; frozen answer key
`licensed-team-responsibilities-v1`, matcher `field-aware-v3`, 27/30 threshold, controls 16/24/26,
route, budgets, disabled business-model flags, map preservation, and no migrations remain unchanged.
The next session must put the two open decisions above to Albert in one message before another production
attempt; read-only diagnosis does not need new approval.

## 1. What this application is

The Oracle is POP Creations' evidence-backed operational knowledge system. The monorepo is
`u2giants/theoracle`; the web app runs on Vercel, workers run in Trigger.dev project
`proj_wgpzsvhmsopqhvwqaycn`, and production data is in Supabase project `eqccjfbyrywsqkxxpjvg`.
R2 measures whether the licensed team-responsibility document becomes complete, source-faithful records.

## 2. What this session set out to do, and why

After production stayed at 23/30, rows 5/14/15/23 were diagnosed as source-faithful records whose
action/object wording failed the frozen matcher. PR #8 added a source-bound final-record correction that
canonicalizes only fidelity-passing completion records to the exact action and bounded object in their own
single-duty span, then requires the unchanged validator to pass. Albert authorized one deployment and one
production map run to test whether that correction reached 27/30 without regressions.

## 3. Current state — what is true right now

PR #8 merged as `53ca432bf594a4c040cf3a11e48cdae54d6be829`; exact-head CI run `34296070736`
passed. Current main at deployment was `28e8eb75f74387ded651e7fcad2dd73638e111e9`; its intervening PR #9
only added task-gate infrastructure and did not change worker behavior.

All frozen gates passed on current main. Deployment `hfnvqrvg` promoted production worker `20260909.1`
with SDK `4.5.15` and 25 tasks. Exactly one run executed with `maxAttempts: 1`:
`run_06g8eqkikc4ch8d54v8ek1jj01`. It completed and created active degraded map
`339ca8b1-e412-4447-8336-7586f08bd746`.

The frozen scorer returned 23/30. All 19 protected baseline rows survived; recovered rows were
17/19/20/29; controls 16/24/26 stayed unmatched. This tied the previous active map
`905e0626-d9a2-4014-a6a3-97e572214896`, so the regression-only rollback did not apply. The new map is
active. All 16 post-score gates passed. Issue #4 is open. No retry, second run, tuning, migration,
rollback, or map deletion occurred.

## 4. Everything tried that did not work

The source-bound canonicalization seemed appropriate because all four stored records passed fidelity but
missed the frozen matcher. Production disproved it as the closing lever: the score and matched-row set were
identical to the preceding 23/30 map. Row 15 reports the correction accepted, including action and object
canonicalization, but still misses. Rows 5, 14 and 23 report `no_strict_improvement`, so the corrector did
not change their selected records. Do not repeat this correction or another production run unchanged.

One local `pnpm install` attempt used unsupported `--no-progress`; rerunning without that option completed.
This was tooling-only and did not affect code or production.

## 5. Root causes and key findings

Read-only `verify:r2-missed-row-diagnosis` against map `339ca8b1-...` again classifies rows 5/14/15/23 as
`RECORD_PASSES_FIDELITY_BUT_FAILS_THE_MATCHER`. Row 5 has four supporting seeds but only two have stored
records; row 14 has one stored record missing one expected object token; row 15 remains two expected object
tokens short even after accepted canonicalization; row 23 still has an action mismatch and a much broader
object. Therefore the remaining gap is not simply paraphrase versus exact bounded-source wording. The next
diagnosis must inspect seed selection, record selection, and the difference between pinned inventory support
and the final bounded record, without changing the frozen evaluation contract.

## 6. Exact next steps

1. Start from current `origin/main` in a new isolated worktree and confirm issue #4 is open. Success:
   branch and SHA match current upstream and no unrelated changes exist.
2. Run the SELECT-only missed-row diagnosis on active map `339ca8b1-...` for rows 5/14/15/23. Success:
   the cause and seed/record counts reproduce without licensed text or row data being printed.
3. Trace, locally, why pinned inventory says each row is supported while the final selected record misses:
   compare seed-to-record selection, bounded-object derivation, and dedup/merge choice using only counts,
   hashes, token deltas, and reason codes. Success: one named pipeline decision explains each miss.
4. Design the smallest correction at that decision point. Do not change the answer key, matcher, threshold,
   fidelity validator, prompt contract, budgets, or controls. Success: deterministic tests reproduce each
   defect before the fix and pass after it.
5. Run all 16 gates, pinned inventory, SELECT-only replay, and the eight-seed live contract probe. Success:
   zero protected-row or record regression, controls unchanged, and 8 requested / 8 returned / zero failures.
6. Merge through PR checks and exact-head main CI. Request a new bounded production authorization only if
   the evidence identifies a genuinely different lever. Close issue #4 only after a production map reaches
   at least 27/30 and every frozen acceptance condition is proven.

## 7. Constraints and gotchas in force

Never print licensed source text, model responses, secrets, or production rows. Never delete a map or run a
migration. Use exactly one production deployment and run only when newly authorized, with
`maxAttempts: 1` and no retry. Restore the named prior active map only on a proven regression. Worker deploys
use the repository-pinned Trigger.dev `4.5.15` CLI; a dry run may precede deployment but is not production.
Read `C:\repos\ai-devops\docs\cloud-build-prod-trigger-incident-2026-07-20.md` before production work.

## 8. Access and environment

Host: `al8960ofc`, Windows PowerShell. GitHub and Trigger.dev are authenticated to the POP account and
Oracle project. Secrets are in 1Password vault `vibe_coding`; production DB reads use item
`qcuyabwseaptvuzvtjejffi2ou`, field `oracle_session_pooler`, and the live probe uses OpenAI item
`3onekcbg3dxnazpnt36d4yzfcq`, field `openai_chatGPT_Oracle`. Use protected `op_run`; never reveal values.
Licensed fixture location is recorded in `plan_r2_fresh_production_gate.md` section 10.

## 9. Open questions and risks

The four-point production gap remains and the current active map is degraded at 23/30. The strongest open
question is why the pinned inventory can support rows that the exact source-bound final records do not match;
answering that incorrectly risks another flat production run. The two MCP bearer tokens remain exposed until
rotated. No other owner decision or production action is hidden outside section 0.

## Handoff self-audit

1. Yes. Sections 1–3 give a new developer the application, purpose, exact commits, CI, deployment, run, map,
   score, active state, and issue state.
2. Yes. Sections 4–5 preserve the failed canonicalization hypothesis, tooling dead end, and the evidence that
   redirects the next diagnosis.
3. Yes. Sections 0–9 cover background, goal, current state, failures, findings, decisions, exact gated steps,
   constraints, access, and risks without exposing secrets or licensed content.
4. Yes. A line-by-line owner-decision sweep found only a future production-cycle authorization and the two
   bearer-token rotations; both are consolidated in section 0 with recommendations and consequences.
