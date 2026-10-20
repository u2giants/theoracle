# S03 U3–U5 replacement browser journey — offline verification stub

**Status: Not accepted.** Browser journey offline ≠ native acceptance. This
record covers the offline replacement UI/API surface and its fixture-backed
Playwright/contract coverage only. No native pipeline, hosted preview, paid
provider, real original, or business acceptance is claimed here.

Date: 2026-11-16 (America/New_York, EST). Worktree `impl-u35`, branch
`mimo/u3-u5-browser`, base `origin/main @ f809258`. Synthetic/invented data
only — no company data, no employees.

## What landed

| Surface | Path |
|---|---|
| Journey workspace page | `apps/web/app/consultant/replacement/page.tsx` |
| Original viewer page (PNG parts) | `apps/web/app/consultant/replacement/originals/[sourceId]/[revision]/page.tsx` |
| Workspace UI | `apps/web/components/consultant/replacement-workspace.tsx` |
| Wire contract (State 13 + snapshot invariants) | `apps/web/lib/replacement-contract.ts` |
| Offline fixture store (CAS/attempts/cancel) | `apps/web/lib/replacement-store.ts` |
| API: sources | `apps/web/app/api/consultant/replacement/v1/sources/route.ts` |
| API: journeys create/list | `apps/web/app/api/consultant/replacement/v1/journeys/route.ts` |
| API: journey get | `apps/web/app/api/consultant/replacement/v1/journeys/[id]/route.ts` |
| API: CAS advance | `.../journeys/[id]/advance/route.ts` |
| API: cancel | `.../journeys/[id]/cancel/route.ts` |
| API: corrections (U4 DTO) | `.../journeys/[id]/corrections/route.ts` |
| API: confirmations (U5 DTO) | `.../journeys/[id]/confirmations/route.ts` |
| API: answers | `.../journeys/[id]/answers/route.ts` |
| API: attempts (native1..N) | `.../journeys/[id]/attempts/route.ts` |
| API: original viewer PNG | `.../originals/[sourceId]/[revision]/route.ts` |
| Contract unit tests | `apps/web/lib/replacement-contract.test.ts` |
| Playwright journey spec | `apps/web/tests/oracle2/replacement-journey.spec.ts` |

The legacy pilot path (`apps/web/lib/oracle2-store.ts` `correctDraft` /
`confirmDraft`) is untouched; the replacement family sits beside it.

## Contract rules enforced (TypeScript mirror of Python wire)

- Every replacement v1 API route requires a fail-closed auth gate
  (`apps/web/lib/replacement-auth.ts`): unauthenticated callers get 401,
  out-of-scope workspace/role principals get 403, and actor/workspace are
  server-derived from the authorized principal — never a hard-coded implicit
  caller. Bounds mirror the replacement-contract workspace+role limit.
- State 13 literals only (`uploading` … `evidence_missing`); unknown states fail
  closed — never coerced to `ready`.
- Snapshot invariants mirror `ReplacementSnapshotV1`: map requires model; model
  only in `draft_ready`/`confirmed_for_scope`/`answer_ready`; `confirmed_for_scope`
  requires a current confirmation; `answer_ready` requires model+answer; answer
  only in `answer_ready`; foreign evidence/citations rejected; current
  confirmation must match model version/hash.
- Correction is append-only original review evidence → genuinely new model
  revision (same artifact UUID, version+1). No body editing. Journey enters
  `revision_pending` and current map/answer/badge clear.
- Cancel preserves spent attempt liability (never "not sent"/refunded), reaches
  `cancelled`, and forbids replay of spent attempts or further promotion.
- native1..N: each dispatch is a new attempt; spend is one-way; replay refuses.
- Invalidation clears current map/answer/badge; metadata alone never yields ready.
- Stale seeded model/graph-evidence metadata is stored separately and is never
  the current serving output.

## Playwright coverage (`replacement-journey.spec.ts`)

No skip stub. Named env gate: `ORACLE2_PREVIEW_URL` (default
`http://localhost:3000`) only — the standard oracle2 preview target. A missing
page/endpoint is a test failure, not a skip.

1. `journey states render and transition through the State 13 machine`
2. `correction produces a new revision without body edit`
3. `control/cancel preserves liability, shows cancelled, and forbids replay`
4. `native1..N attempt visibility: attempt 1 spent, attempt 2 new, never replay`
5. `actual_native_pipeline_after_refresh` — hostile case from plan §10: real
   binary upload + backend-stale seed; after refresh the current native
   pipeline output wins and stale seed is never current; invalidation then
   clears map/answer/badge across reload
6. `original viewer serves PNG page parts from the fixture`
7. `unknown fields and unsupported intents fail closed`

### How to run

```bash
pnpm --filter @oracle/web dev            # local preview on :3000
pnpm --filter @oracle/web exec playwright install chromium
pnpm --filter @oracle/web test:oracle2   # or with ORACLE2_PREVIEW_URL set
pnpm --filter @oracle/web exec tsx --test lib/replacement-contract.test.ts
```

## Results (this session)

| Check | Result |
|---|---|
| `tsx --test lib/replacement-contract.test.ts` | **11/11 pass** (state literals, snapshot fail-closed rules, CAS transitions, correction→new revision, cancel liability/no-replay, native1..N attempts, invalidation clears current, stale seed never current, stale confirmation refused, answer requires confirmation). Registered in `.github/workflows/oracle2-contracts.yml`. |
| `tsc --noEmit` (`@oracle/web` typecheck) | **clean** |
| Playwright `replacement-journey.spec.ts` | **7/7 pass** (12.9s) against local `next dev` on :3000 — State 13 render/transition, correction→new revision (no body edit), control/cancel liability+no-replay, native1..N visibility, `actual_native_pipeline_after_refresh`, original viewer PNG, unknown-field fail-closed. No skips. |

## Explicitly out of scope / still open

- Native acceptance, hosted preview, mTLS protected result, paid provider,
  real PDF original reader/reviewer, Q2b target owner/caller/TLS proof.
- Live browser screenshots (desktop/mobile/keyboard/error states) and
  current-role denied-route evidence remain OPEN (U5).
- Real browser cancellation/lost-reply/restart/late-completion/abstention
  tests (U6) remain OPEN.
- Python `hosting/replacement_*_v1.py` services are not wired into this web
  app; the TypeScript contract layer mirrors their rules and is tested here.
  Wiring the actual Python executor is a separate admitted step.
- Playwright here is offline browser-journey evidence only — it is **not** a
  native-acceptance proof path and does not flip any acceptance gate.

## Registration note

TS unit tests follow the repo pattern
`pnpm --filter @oracle/web exec tsx --test <files>` registered in
`.github/workflows/oracle2-contracts.yml`. `lib/replacement-contract.test.ts`
is registered there under step "Verify replacement journey contract and
fixture store". Playwright specs self-register via
`playwright.oracle2.config.ts` (`testMatch: '**/*.spec.ts'`).
