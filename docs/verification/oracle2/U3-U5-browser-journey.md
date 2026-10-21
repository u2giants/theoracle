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

### Local fixture authentication

Browser tests require explicit development/test fixture mode, a replacement
token of at least 32 characters, and a distinct fixture session key of at least
32 characters. Missing secrets fail closed. Run the preview bound to loopback;
the browser spec logs in through the fixture-only session route. Both request
URL and Host must be local HTTP on the same port; Origin must match Host.
Production, nonlocal, cross-origin, wrong-token and expired-cookie paths deny.
Never reuse company credentials or place test secrets in committed files.

## Current offline verification

The authenticated invented-data browser journey passes all seven cases
(12.8 seconds, zero skips). This supersedes the historical unauthenticated
journey claim, which failed with HTTP 401 after R8 authentication enforcement.
The original 38 replacement-contract tests and two new fixture-authentication
tests pass (40 total, zero failures/skips). Both files are registered in
`.github/workflows/oracle2-contracts.yml`.

The local fixture's full application typecheck remains unverified because its
external minimal dependency setup lacks unrelated application dependencies and
types. No clean full-typecheck claim is made by this evidence.

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
