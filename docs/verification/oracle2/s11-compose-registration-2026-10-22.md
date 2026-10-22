# S11 recommendation/recipients compose + mandatory test registration

Date: 2026-10-22 2:40 PM EST. Worktree `C:/tmp/oracle-s11-compose-01a16013`,
branch `codex/parent24-s11-compose-01a16013`. Class `code` declared before writes
via `ai-task-gates start --class code`. Source preservation only: no database,
provider, production, company, or acceptance claim.

## Composition inventory

Base: current `origin/main` `adb89f6d85e467e5d847b3f48b77e09802fd2c5f`
(S12-04 brief on top of parent24 closeout `bf788080`).

Parked S11 head: `ac5392355b19a025e3371e36bfee903583773b90`
(branch `origin/codex/oracle-s11-recipient-index`), three owned commits on
genuine `c187bfc36723ca891ad7558fe202a258ee2f27f8`:

- `b0362f39` Compose complete recommendation and frozen employee origin prerequisites
- `3d71e9b8` Select recommendation profiles through the canonical employee recipient index
- `ac539235` Prove indexed recommendation denials cannot use a valid singleton

Composition method: **true-ancestor additive merge** of `ac539235` onto
`origin/main` (shared ancestor `c187bfc3`). No inverse old-head diff. The
forbidden inverse composition (149 paths / 63 deletions / 9,385 lines including
current-main S07 source) was not used.

Measured result:

- 95 net paths changed vs `origin/main` (exact match to ac539 delta path set).
- **0 deletions** of any `origin/main` file.
- Every main191/193/027/S09 source file retained (closeout handoff, five plan
  STATUS updates, docs map, S12-04 brief all present on the composed tree).
- Tracked file count 1753 (ac539's 1751 + main's handoff + S12-04 brief).
- SQL024 + SQL025 source present; S11 security/setup + S12 delta present.

## Registration changes

Handoff §3.8 / §6.6 left three existing TS suites, canonical 025, and the
recommendation mandatory population unregistered. Completed in source:

1. `.github/workflows/oracle2-contracts.yml` — registered the three existing
   TS suites into the same `tsx --test` mandatory list:
   - `lib/replacement-recipient-origin.test.ts`
   - `lib/replacement-recommendation-client.test.ts`
   - `lib/replacement-recommendation-contract.test.ts`
   (`lib/replacement-question-effect.test.ts` was already registered on ac539.)
2. `scripts/oracle2/verify_workflow_integrity.py`:
   - `SYNTHETIC_MIGRATIONS` += `025_recommendation_actions.sql` (canonical 025).
   - `DOCUMENTARY` += `RECOMMENDATION_PURE_SUITES`,
     `RECOMMENDATION_SQL_SUITES`, `RECOMMENDATION_BROWSER_SUITES` (10 existing
     Python suites: `recommendation_actions_v1`, `recommendation_presentation_v1`,
     `recommendation_setup_batch_v1`, `measurement_evidence_v1`,
     `protected_sql_connection_v1`, `workspace_workflow_fixture_v1`,
     `recommendation_actions_sql`, `workspace_next_recipients_sql_v1`,
     `recommendation_next_auth_browser_v1`, `recommendation_actions_service_v1`).
   - Placement preserves the existing `purpose_worker_startup` +
     `question_effects_sql_v1` measured pair (heavy-suite isolation assertion
     unchanged). Recommendation SQL joins the last documentary group
     (`paid_sdk_embeddings_v3` after). Ten workers and the shared 120-second
     deadline are unchanged. No cases cut, no budgets raised.
3. `services/oracle-brain/tests/test_operating_model_verifier.py` — updated
   `SYNTHETIC_MIGRATIONS` equality and tail assertions for canonical 025.

`DOCUMENTARY_BOUNDARIES` was not changed (still 8 boundaries → 9 documentary
groups + 1 event = 10 W10 groups).

## Test results on this Windows host

Host: Windows, Python 3.13.15 system / 3.12.14 venv, Node v24.19.0, pnpm 9.5.0.
`hnswlib` cannot build (no MSVC 14.0+); graphrag-sdk installed with
`--no-deps` plus its pure dependencies.

### Verifier self-tests (`test_operating_model_verifier.py`)

- **39 passed** (including `test_parallel_population_is_exact_bounded_and_heavy_native_suites_are_isolated`
  and the updated `SYNTHETIC_MIGRATIONS` assertions).
- **29 failed — all Windows host limits**, not registration defects:
  `os.O_PATH` missing (26), `os.mkfifo` missing (3 cases × params),
  WinError 1314 hardlink privilege (several). These same cases pass on the
  Linux CI runner that executed ac539.

### Recommendation pure Python (the 10 newly registered suites' pure portion)

- **90 passed / 5 failed** across
  `test_recommendation_actions_v1`, `test_recommendation_presentation_v1`,
  `test_measurement_evidence_v1`, `test_workspace_workflow_fixture_v1`,
  `test_recommendation_setup_batch_v1`.
- All 5 failures are the same Windows host limit: `Path('/invented/ca.pem').is_absolute()`
  is false on Windows (POSIX absolute path without drive letter), so
  `protected_sql_connection_v1` raises
  `PermissionError: one explicitly pinned verify-full host/address/port target required`
  before the case's intended branch. Same root cause fails 14 further cases in
  `test_protected_sql_connection_v1.py`.
- `test_protected_sql_connection_v1.py` on Windows: failures are exclusively the
  POSIX-absolute-`sslrootcert` host limit above.

### Three newly registered TS suites

- `lib/replacement-recommendation-contract.test.ts` — **8/8 passed**.
- `lib/replacement-recipient-origin.test.ts` — static-origin refusal cases pass;
  cases that call `protectedRead` / absolute-path resolve fail on Windows
  (`packages/shared/src/_protected-file.ts` requires `resolve(path)===path`,
  which rejects `/…` paths on Windows).
- `lib/replacement-recommendation-client.test.ts` — non-TLS control cases pass;
  actual loopback mTLS cases return 503 on this host (no native peer path).
- `openssl` was not on PATH; Git's `C:\Program Files\Git\usr\bin\openssl.exe`
  was used for certificate generation.

### Types and lint

- `@oracle/web` `tsc --noEmit` — **pass**.
- `@oracle/shared` `tsc --noEmit` — **pass**.
- `@oracle/workers` `tsc --noEmit` — **pass**.
- `@oracle/web` `eslint . --max-warnings 0` — **pass**.

### Not run here (named, not invented)

- Full 469-case web suite (ac539's Linux result; Windows mTLS/path limits would
  misrepresent it).
- Full 150-case pure suite (same reason; recommendation pure subset measured above).
- Clean HEAD Next build (`pnpm build:vercel` / licensing source-offer guard) —
  attempted after commit on a subsequent step if host allows; not claimed until
  observed.
- Actual 45 SQL+Next / current multiemployee proof — **not executed** (root owns).
- Full integrated W10 — **not executed** (root owns).

## One-admin setup batching = UNPROVED savings

`test_recommendation_setup_batch_v1.py` covers TEST SETUP only: four independent
roles/admissions/source/root/horizons in one existing admin transaction,
canonical installation once, final complete catalog after grants. Measured
setup-time savings remain **UNPROVED** and are **not** a realized business
benefit. No company acceptance, production authority, or adoption claim follows.

## Remaining gate (root-owned)

1. Actual current 45 SQL+Next / multiemployee proof under same owner (no new
   grant).
2. Full integrated W10 / post-main clean run under the unchanged 120-second
   shared deadline and ten workers (registration now includes the three TS
   suites, canonical 025, and the 10 recommendation Python suites).
3. Measure one-admin setup savings; solve the shared Next dist lock
   legitimately (no blanket serialization beyond 120s).
4. Business/company acceptance remains a separate hold.

## Constraints observed

- Safety gates preserved; business-acceptance hold separate.
- No company data, production, paid providers, or real observation windows.
- No realized-savings claim.
- No case cuts, no budget raises, no blanket Next-dist serialization.
- Committer `Albert Hazan <u2giants@users.noreply.github.com>`; branch only
  (never protected `main` push).
