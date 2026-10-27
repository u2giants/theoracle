# Shared Next dist lock — symptom and legitimate fix surface (S11 / PR201)

Sealed into PR #201. Documentation only; no source change to Next config or the three drivers. This note is the in-repo authority Muse can read at the sealed head.

## Symptom

Three actual-Next test drivers spawn `next dev --turbopack` with
`cwd: resolve('.')` (i.e. `apps/web`) and therefore share one generated Next
development output directory:

- `apps/web/tests/oracle2/recommendation-next-auth-proof.ts`
- `apps/web/tests/oracle2/workspace-next-recipients-proof.ts`
- `apps/web/tests/oracle2/model-review-next-auth-proof.ts`

Installed Next (16.x) defaults `distDir` to `.next` and in development further
joins `dev` onto it. Parallel mandatory S05/S11/S12 actual-Next drivers therefore contend on the same `apps/web/.next/dev` development lock.

There is no `distDir` in `apps/web/next.config.ts` on this head. No CLI `--distDir` flag is used by the three spawn sites.

## Third driver and W10 contention observation (Muse Critical 3)

W10 places `recommendation_next_auth_browser_v1` beside
`consolidation_next_auth_browser_v1` in one worker group, while
`workspace_next_recipients_sql_v1` sits in a different parallel worker. The ONE one-shot scope runs only the two S11 suites sequentially (as two separate one-shot invocations) and therefore **cannot** validate a dist-lock fix that excludes the third driver.

Contention observation set (named, for any future observation run):

1. `test_recommendation_next_auth_browser_v1.py` + `recommendation-next-auth-proof.ts`
2. `test_workspace_next_recipients_sql_v1.py` + `workspace-next-recipients-proof.ts`
3. `test_consolidation_next_auth_browser_v1.py` (third auth-browser driver)
4. `model-review-next-auth-proof.ts` (third spawn site)

## UNPROVED remaining gate

**Dist-lock under full W10 parallel remains UNPROVED.** The one-shot does not claim W10 Next stability. This is a named remaining gate.

Legitimate fix surface already in framework source (not yet wired):

- Next officially supports a string `distDir` in `next.config.ts`.
- Legitimate isolation directions that do **not** weaken guards: per-proof owned `distDir` under the test scratch (test-only config seam consumed by the existing official `distDir` option), or same-owner sequential integration of the three drivers.
- Explicitly rejected: blanket serialization beyond the shared 120s W10 budget, fake mocks, skips, or larger W10 budgets.

## Stale-lock and post-run scans

The sealed runner (`scripts/oracle2/run-s11-next-multiemployee-proof-01.py`) adds:

- **Stale-lock pre-check (path-scoped)** before each Next invocation: refuses only when a **live process actually binds this worktree's `apps/web` / `.next/dev`** — its cwd is under the owned `apps/web` (including `.next/dev`), an open fd points under that tree, or its argv names that absolute path (relative `apps/web` argv also counts only when cwd is under the worktree root). Host-level `node` / `chromium` / `playwright` / `claude` name-or-args scans must **NOT** count: Playwright MCP, `chrome_crashpad_handler`, `claude-headroom` and disclaimer wrappers previously matched broad tokens and false-STOPped the one-shot before any DB/Next work (`next_dev_dir_exists: False` in that STOP record). Directory existence alone is NOT a lock — any clean Next run creates `apps/web/.next/dev` and leaves it behind. Real holders (cwd under the owned `apps/web`, or `.next/dev` fds) remain fail-closed STOP. A failed `/proc` walk is also fail-closed. Contract unit-proved offline by `services/oracle-brain/tests/test_s11_live_lock_path_scope.py`.
- **Post-run scan** after each invocation and after cleanup: a broad process name/args scan **plus port/socket inspection** (`ss -tlnp` with `lsof` fallback) kept as **leak evidence only** (`name_scan_processes` / `matching_ports`) — those broad hits must never set `live_lock_present`. `live_lock_present` uses the same path-scoped holder walk. Recorded in `scans.json` (written after the post-cleanup scan).
- **Timeout handler**: `start_new_session=True` + `os.killpg` on `TimeoutExpired`, then post-scan and full cleanup.

These are additive. The drivers' own `ppid == child.pid` cleanup proof still misses reparented grandchildren; that gap stays named (see the ONE plan).

## Not done here

No Next `distDir` wiring. No process launched by this note. Guards unchanged.
