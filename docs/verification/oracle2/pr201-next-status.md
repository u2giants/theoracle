# PR201 S11 Next/multiemployee + setup-savings status (sealed)

Machine: edge-dev3 (Linux proofs only). Windows host cannot honestly run Next/SQL suites.
Task class: `deployment` (pre-existing). No production, company originals, paid providers, real meetings.

This file is sealed source. It replaces the /tmp-only status Muse REJECT found unsealed.

## Exact head

- PR #201 branch `codex/parent24-s11-compose-01a16013`
- Authoring parent `ac1a848edaa3570070abaeef5627b8d33cfd3685`
- The reviewed seal SHA is the full 40-char HEAD of the commit that contains this file. The Muse receipt must carry that same SHA. The runner asserts `receipt.head == git rev-parse HEAD`.
- PR stays open; branch is not deleted; nothing merges to protected `main`.

## Sealed artifacts (in-repo, Muse-readable at this head)

| Path | Role |
|---|---|
| `scripts/oracle2/run-s11-next-multiemployee-proof-01.py` | one-shot runner (fail-closed gates) |
| `scripts/oracle2/measure-s11-setup-batch-01.py` | setup-batch measurement script |
| `docs/verification/oracle2/s11-actual-next-proof-plan.md` | ONE plan (budget, resources, remaining gates) |
| `docs/verification/oracle2/s11-next-dist-lock-note.md` | shared Next dist lock note |
| `docs/verification/oracle2/s11-setup-batch-measurement-01.json` | measurement JSON (test-setup only) |
| `services/oracle-brain/tests/test_s11_next_database_fixture_order.py` | offline fixture-order proof |
| `docs/verification/oracle2/pr201-next-status.md` | this file |

## Fail-closed claims (now inspectable in the sealed runner)

- **exact-head pin** — `receipt.head == git rev-parse HEAD` of the execution worktree
- **clean-tree check** — `git status --porcelain` must be empty; uncommitted edits refuse (H1)
- **receipt fields** — `head`, `verdict=APPROVE`, `reviewer`, `reviewed_at`; receipt is **procedural/operator-minted** unsigned `/tmp` JSON (M3); sealed-file digests bound into `result.json`
- **STOP exit 2** — every pre/post-gate failure prints a reason and exits 2 (M1/M6); no bare asserts; no traceback exits
- **owned cleanup** — compose-project absence proof (containers/networks/volumes) + name/port/lock post-run scan (H4: broader tokens + `ss`/`lsof` port inspection)
- **source-before/after equality** — sha256 over **all git-tracked files** (content+mode) must match after the run (M4)
- **JUnit totals** — tests>0, failures==0, errors==0, skipped==0; missing XML reports returncode/timeout/stderr tail (H2)
- **timeout handler** — `start_new_session=True` + `os.killpg` on timeout; writes `result.json` with `timeout: true`; still runs post-scan and cleanup (H3)
- **resource preflight** — executable `preflight_resources()` checks DNS/::1, Chromium, pnpm/tsx, openssl, docker, git, ps, venv path with psycopg/pytest (H5)
- **stale-lock** — detects **live process holder**, not mere directory existence (C3)
- **FalkorDB** — runner provisions `falkor-candidate` and exports `ORACLE2_OPERATING_TEST_GRAPH_URL` (C2)
- **label** — `event` (legal for `worker_postgres` allowlist) (C1)

## Prior session (retained, not re-run)

- Actual 45 SQL (`test_recommendation_actions_sql.py`) **45/45 PASS** on edge-dev3 (runner `run-s11-recommendation-sql-01.py`, project `oracle2-synthetic-p24s11-mimo`, wall 97.74s). SQL already green — not double-bootstrapped this seal session.

## Offline pure results (sealed claims)

- `test_recommendation_setup_batch_v1.py` — **13/13 PASS** (offline).
- `test_s11_next_database_fixture_order.py` — **2/2 PASS** (offline pure only; no socket/DB/Next). File is real and sealed at `services/oracle-brain/tests/test_s11_next_database_fixture_order.py`.

## Next/multiemployee actual — NOT executed

Prepared runner: `scripts/oracle2/run-s11-next-multiemployee-proof-01.py` (sealed).

- Gate proven live earlier: **STOP: review receipt required before execution** (exit 2).
- Scope when authorized: `test_workspace_next_recipients_sql_v1.py` (two invented employees, multiemployee) + `test_recommendation_next_auth_browser_v1.py` (actual Next/Auth/employee SQL), as **two separate one-shot invocations**.
- Budget: `ONE_SHOT_WALL_S = 300` per invocation, labeled **test-setup-only** and **NOT the W10 120s budget**. Do not claim W10 SAME fit.
- Invented fixtures only, one fresh PG + FalkorDB graph stores + TLS fixtures + openssl + pnpm/tsx + Chromium + localhost.localdomain DNS, owned cleanup, no production/company effect.

## Setup-batch measurement — TEST SETUP only

Artifacts: `docs/verification/oracle2/s11-setup-batch-measurement-01.json`, `scripts/oracle2/measure-s11-setup-batch-01.py`.

| Path | admin contexts | pins calls | admissions | authorities | offline wall median |
|---|---|---|---|---|---|
| sequential install×4 + repin | 5 | 5 | 4 | 4 | 0.000120s |
| one-admin batch | 1 | 1 | 4 | 4 | 0.000107s |
| delta | **4** | **4** | 0 | 0 | 1.3e-05s |

- Label: **TEST SETUP measurement only — UNPROVED for business/realized savings.**
- Static reduction 5→1 is real in code. Live-DB install wall-time saving remains unmeasured and is **not** claimed.

## Shared Next dist lock — documented, UNPROVED under W10

See `docs/verification/oracle2/s11-next-dist-lock-note.md`. Three drivers share `apps/web/.next/dev`. Dist-lock under full W10 parallel remains **UNPROVED** (named remaining gate). Contention observation set includes `test_consolidation_next_auth_browser_v1.py`. No source/config edit; guards unchanged.

## Known gaps named (not fixed in this seal)

1. Drivers' `ppid == child.pid` cleanup proof misses reparented grandchildren. Runner adds name/port scans (with `ss`/`lsof`) and live-lock pre-check; closing the driver-level gap remains open.
2. `pg_stat_activity` sampling can miss fast queries. Fail-closed flake risk, named. JWT-240s is a **non-risk** under sealed bounds (45s startup + 110s communicate, mint at driver start) (L1).
3. Invented LOGIN roles are cluster-global and accumulate; containment is whole-project `down --volumes`.
4. `/proc` probing is Linux-only (runner refuses elsewhere).
5. Chromium unpinned in CI; record the version in the receipt/evidence.
6. `__wrapped__` access on pytest fixtures is pytest-version-sensitive; no pytest version is pinned (L3). Note in `test_s11_next_database_fixture_order.py` docstring.

## What remains

1. Next/multiemployee actual proof — runner sealed and receipt-gated; needs exact-head APPROVE receipt, then the one-shot on edge-dev3.
2. Live-DB one-admin setup wall-time measurement on same source/deps.
3. Shared Next dist lock legitimate isolation (per-proof `distDir` or same-owner integration) — documented, not implemented; **UNPROVED under W10**.
4. Full integrated W10 (120s / ten workers / per-request ≤30 / full population / 0 F/E/S/timeout/launch/cleanup) and whole-product post-main clean — root owns.
5. Business/company acceptance remains separate hold.

## Constraints observed

- No company originals, production, paid providers, real meetings.
- No push to protected `main`. No open PR branch deleted. No merge.
- No invented business saving. No case cuts, budget raises, or guard weakening.
- Commit identity: `Albert Hazan <u2giants@users.noreply.github.com>`.
