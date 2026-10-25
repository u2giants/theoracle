# S11 actual Next / real Auth-protocol / employee-SQL proof — ONE plan (v2)

Owner: journey; coordinator retains schema/security/installation/release/acceptance judgment. This file is sealed source for PR #201. It is source preparation, not execution or a completed proof. It supersedes the /tmp-only plan that Muse REJECT found unsealed.

Sealed companion artifacts (in-repo, inspectable at this head):

- `scripts/oracle2/run-s11-next-multiemployee-proof-01.py` — one-shot runner (fail-closed gates inspectable)
- `scripts/oracle2/measure-s11-setup-batch-01.py` — setup-batch measurement script
- `docs/verification/oracle2/s11-next-dist-lock-note.md` — shared Next dist lock note
- `docs/verification/oracle2/s11-setup-batch-measurement-01.json` — measurement JSON
- `services/oracle-brain/tests/test_s11_next_database_fixture_order.py` — offline fixture-order proof (real file; sealed from edge-dev3)
- `docs/verification/oracle2/pr201-next-status.md` — status / receipt requirements

## Required natural unblock — procedural / operator-minted (M2, M3)

Root first integrates and lands the exact complete consumer source, SQL025, SAME shared transport/purpose and canonical migration inventory on main under required review/release gates. Then journey creates a NEW current-upstream test worktree, captures every executed web/backend/SQL/test source hash, declares the actual task class and runs the actual database preflight. No database resource, employee-SQL read, Next database-using process or browser claim starts unless that complete source declaration returns ALLOW. If effective class remains deployment, preserve STOP; no B+C partition, dropping protected files, ancestry laundering or target reuse.

**These preconditions are procedural / operator-minted.** The runner records them in `result.json` (`natural_unblock` object) but does not independently re-verify main-landed source, worktree freshness, or ALLOW — the reviewer who mints the receipt is assumed to have confirmed them. The runner does enforce a **clean-tree check**: `git status --porcelain` must be empty before any DB/Next work (uncommitted edits refuse with STOP exit 2).

The one-shot additionally requires a review receipt at `/tmp/oracle-parent24-wy02uT/s11-next-multiemployee-review-receipt.json` with fields `head` (full 40-char, equal to checked-out HEAD), `verdict=APPROVE`, `reviewer`, `reviewed_at`. Missing receipt is STOP exit 2 before any DB/Next work.

**Receipt honesty (M3):** the receipt is an operator-minted, unsigned `/tmp` JSON file. It is a procedural gate, not an integrity-bound signature. The runner binds the sealed-set file content digests (plan, note, JSON, status, measure script, plus all git-tracked files via whole-worktree content+mode sha256) into `result.json` so a reviewer can verify the sealed set matches the reviewed head.

## Budget honesty (Muse REJECT Critical 2) — this is NOT a W10 120s pair

These two proofs are **not** a W10 120s sequential pair:

- `test_connected_answer_sdk_sql_v1` is not in this one-shot's pytest invocation; the multiemployee claim is covered by `test_workspace_next_recipients_sql_v1` (two invented employees) plus `test_recommendation_next_auth_browser_v1` (actual Next/Auth/employee SQL).
- Each Next tail allows up to 110s communicate and up to 45s Next startup. Two Next startups alone can be ~90s.
- W10 placement already puts `workspace_next_recipients_sql_v1` and `recommendation_next_auth_browser_v1` in **different parallel workers** (`scripts/oracle2/verify_workflow_integrity.py`). Running them sequentially under one 120s clock is facially infeasible.

**The one plan:** run them as **two separate one-shot invocations** inside one owned worker cluster. Each invocation gets an explicit larger wall clock (`ONE_SHOT_WALL_S = 300` in the sealed runner). That clock is labeled **test-setup-only** and is **NOT the W10 budget**.

- Do **not** claim W10 SAME fit from this run.
- Do **not** claim the one-shot proves W10 Next stability.
- Provisioning (compose up, TLS fixture, FalkorDB graph stores) and cleanup (`down --volumes`) sit **outside** each invocation wall clock, matching W10's exclusion of setup from the 120s test budget.

## Dist-lock honesty (Muse REJECT Critical 3)

Shared `apps/web/.next/dev` lock under full W10 parallel remains **UNPROVED** and is a **named remaining gate**. The ONE scope excludes the third driver, so a green ONE run proves nothing about contention it sidesteps.

Contention observation plan (documentation, not a fix):

1. Name all three actual-Next drivers: `recommendation-next-auth-proof.ts`, `workspace-next-recipients-proof.ts`, `model-review-next-auth-proof.ts`.
2. Include `test_consolidation_next_auth_browser_v1.py` (the third auth-browser driver) in the contention observation set so the observation at least sees the suite W10 places beside `recommendation_next_auth_browser_v1`.
3. Keep the symptom and legitimate fix surface in `docs/verification/oracle2/s11-next-dist-lock-note.md` (in-repo).
4. Remaining gate: dist-lock under full W10 parallel is **UNPROVED** until either per-proof owned `distDir` or same-owner sequential integration is implemented and observed under W10. Explicitly rejected: blanket serialization beyond 120s, mocks, skips, larger W10 budgets.

## Resource plan and pre-flight (Muse REJECT Critical 4)

"One fresh PG" is incomplete. Required stores and setup:

| Requirement | Why | Where |
|---|---|---|
| Fresh PG (compose worker_postgres) | owned child DB `oracle_operating_model_test_<32hex>` | `dev/oracle2/test_worker_postgres_fixture.py` |
| FalkorDB graph stores | multiemployee / connected-answer journey | compose worker stack (`falkor-candidate` service) |
| TLS fixtures (`verify-full` + `sslrootcert`) | every DB entry point | `test_worker_postgres_fixture.py` |
| `openssl` | auth-browser cert fixtures | PATH |
| `pnpm` / `tsx` | TS proof drivers | `apps/web` |
| Chromium | browser proof (CI installs **unpinned**) | `.github/workflows/oracle2-contracts.yml` |
| `localhost.localdomain` DNS + `::1` | invented auth issuer and Next origins | host resolver |
| `docker` | compose provisioning / cleanup | PATH (hard runner dep) |
| `git` | exact-head pin + clean-tree check + source digest | PATH (hard runner dep) |
| `ps` | post-run leak scan | PATH (hard runner dep) |
| Fixed venv `/tmp/pglast-venv-20261023` with `psycopg` + `pytest` | runner imports + pytest invocation | hard runner dep |
| Compose file `dev/oracle2/compose.yaml` | service definitions for postgres + falkor-candidate | repo |

All of the above are checked by the runner's executable `preflight_resources()` before any DB/Next work. Failure is STOP exit 2 with a named reason.

Pre-flight checklist (runner enforces what is executable; items marked *procedural* are operator-confirmed):

- [x] Linux host (edge-dev3). `/proc` exists. Sealed drivers' `/proc` probing is Linux-only. *(runner enforces)*
- [x] `openssl`, `pnpm`, `tsx`, Chromium present (Chromium version unpinned — record it in the receipt). *(runner `preflight_resources()` enforces)*
- [x] `localhost.localdomain` resolves; `::1` serves the invented auth issuer and Next. *(runner `preflight_resources()` enforces)*
- [x] FalkorDB graph stores up in the owned compose project (`falkor-candidate` service). *(runner provisions at runtime)*
- [x] TLS fixture path + `sslrootcert` present and `verify-full` capable. *(verified by `worker_postgres`)*
- [x] No LIVE process holds the `apps/web/.next/dev` lock (stale-lock pre-check; runner checks for live processes, not mere directory existence — the cache dir persists after clean exit).
- [x] Review receipt exists with `head`/`verdict=APPROVE`/`reviewer`/`reviewed_at`. *(runner enforces; receipt is procedural/operator-minted)*
- [x] Clean tree: `git status --porcelain` empty. *(runner enforces)*
- [x] Fresh compose project: `worker_postgres` appends `-w<12hex>` to the base project name and refuses if any container with that exact project label already exists. *(enforced by `worker_postgres`; a separate "project unused" check is meaningless because the suffixed project name is always unique)*
- *procedural* — main-landed source, new worktree, complete source declaration/ALLOW (see "Required natural unblock")

Provisioning and cleanup are **outside** the per-invocation wall clock.

## Minimal source scope for root ratification

1. `services/oracle-brain/tests/test_recommendation_next_auth_browser_v1.py`: exact canonical qualified measurement fixture → existing V3 compiler/canonical SQL025 registration → actual protected_recommendation_web_server_v1. Distinct real own-role read/feedback/measurement consumers, SAME independently invented principal/workspace/model binding and protected private bytes. Root-current complete migration inventory runs ONCE through the canonical fixture; this test consumes/asserts SQL025 catalog, never replays 022/025 over current schema.
2. `apps/web/tests/oracle2/recommendation-next-auth-proof.ts`: real Next dev process (same existing supported flags), browser /consultant/recommendations → actual getUser HTTP → current real employee join → fixed same-origin route/proxy → actual mTLS → actual SQL/private bytes. No registerHooks, production auth import replacement, fixture Maps, synthetic RSC route, clock-domain weakening or arbitrary auth adapter.
3. Reuse SAME existing `apps/web/tests/oracle2/invented-auth-service.ts` unchanged. The narrow invented employee/identity SQL helper is `services/oracle-brain/tests/invented_next_employee_fixture_v1.py`. No production schema/role/registry change.

The existing authenticated employee source imports, real auth library, shared private-file loader, service channel and pid:performance.timeOrigin guard remain byte-identical. No package/workflow/platform source is changed by this proof task. Root separately owns eventual mandatory registrations, preserving original budgets and no skips.

## One concrete actual positive journey

Use qualified_two_source_fixture_v1 plus the existing measurement_advice/assertion factory BEFORE complete capture/census/assessment. Actual retained original bodies contain the entire invented explicit 12.5 baseline and 10 follow-up unit/currency/period/population/window/completeness facts. This remains host-prepared synthetic qualification, not native generation/company evidence. Current source and read roles are independent of the invented web employee row.

Create one fresh canonical TLS/SCRAM worker service/UUID database under an unused project/worker namespace. Canonical ownership checks precede every admin schema/fixture mutation. Existing-shape public employees/employee_identities/auth_provider exist only in that owned fresh database. A generated LOGIN gets SELECT only, exact-row RLS, no write/admin/advice authority. Independently prove actual TLS, SESSION_USER/database, one permitted identity, zero INSERT/UPDATE/DELETE.

Launch the existing owned invented HTTPS Auth service and actual SDK setSession to seed test cookies; record seed request count. Launch actual Next in a bounded owned child process group with no production/provider credentials. Trust only the owned fixture CA bundle; actual backend mTLS still verifies its exact CA/SAN/DER/URI and protected files. No environment/native-build escape or auth module hook is permitted.

Browser loads current list, selects the documented recommendation without UUID entry, reads support/unknown/no-change/three lenses, chooses a real option, records one personal acceptance and then selects an actual qualified baseline record without numeric input. Independent actual SQL must show exactly one feedback and one baseline event, actual stored command hashes/sequence, false company-policy/effect/causal-savings flags. Actual private callback observers must see zero retained SQL sockets; fresh own SQL/current-source passes follow private bytes. Browser displays recorded history and documentary measurement, never realized/causal savings.

## Actual negative boundaries and evidence

- Independently revoke current source permission after those records. Explicit inspect of the already-permitted selector must return permitted redacted forensic history only; page hides reasons/values/quotes/options. New list must refuse rather than leak source labels. No inherited feedback or requalification occurs.
- Revoked/foreign/no-cookie Auth responses and disabled actual employee deny protected API and page access before advice effects. Employee monitor records actual TLS SELECT/join query hashes under the exact fixture LOGIN, never credentials or payload logs.
- Unknown write path remains no-resend; source backend45 and actual client18/component proof already cover these mechanics. The new real Next journey must independently assert no unexpected command/event count and never retry a possible write.
- Record actual Next/proxy/route processes and unchanged original clock-domain guard. A framework/process split refusal is an exact blocker, not permission to bridge clocks or count a 503 as success.

Save real Auth HTTP counts above seed, actual employee SQL/TLS observations, browser HTTP statuses, actual backend call/effect counts, source hashes before/after, JUnit and actual page PNGs. Inspect those images. No screenshot/pytest exit alone establishes the full chain.

## Cleanup honesty (Muse High cleanup) — known gap named

All three drivers assert no remaining processes via `ppid == child.pid` only. Grandchildren reparent to init and pass that assertion while still holding `.next/dev` or a port. This is a **named known gap**.

Mitigations in the sealed runner (additive, not a replacement of the drivers' proof):

1. **Stale-lock pre-check** before each Next invocation: refuses only when a **live process** holds the `.next/dev` lock (process name/args scan). Directory existence alone is NOT a lock — any clean Next run creates `apps/web/.next/dev` and leaves it behind. Between invocations the runner does not need to delete the cache dir; the check detects live holders only.
2. **Post-run scan** after each invocation and after cleanup: process name/args scan for `next dev` / `next-server` / `turbopack` / `playwright` / `chromium` / `tsx` / `headless_shell` / `chrome` / proof-TS basenames, **plus port/socket inspection** (`ss -tlnp` with `lsof` fallback). Recorded in `scans.json` (written AFTER the post-cleanup scan).
3. **Timeout handler (H3):** `subprocess.Popen` with `start_new_session=True`; on `TimeoutExpired` the runner kills the process group (`os.killpg`), writes `result.json` with `timeout: true`, still runs the post-scan and full cleanup. No Next/Chromium leak is tolerated.

The drivers themselves are not edited in this seal. Closing the ppid gap inside the drivers (recursive `psutil` trees, as `verify_workflow_integrity.py` already uses) remains a **named remaining risk**.

## Flake honesty (Muse High flake) — named, fail-closed

- `pg_stat_activity` sampling (50–100ms) can miss fast `employee_identities` queries. `assert observations` then fails a correct run. Fail-closed; **named flake risk**. The sealed runner does not widen sampling (that lives in the sealed drivers).
- **JWT-240s expiry (L1):** under the sealed bounds (45s Next startup + 110s `communicate` cap per driver, token minted at driver start) the 240s expiry **cannot fire** within a single driver invocation. This is a **non-risk** under sealed bounds; the expiry path was not separately traced. Keep as non-risk; do not present as a flake.
- No retry is permitted on this one-shot. A flake is a fail, not a re-run.

## Medium notes (Muse Medium)

- **Invented login roles are cluster-global** (`invented_web_*`, `advice_*`). Child-database drops remove tables, not roles; repeated runs accumulate. Containment requires whole-project `down --volumes`. The runner records this in `cleanup.json`.
- **`/proc` probing is Linux-only.** The sealed runner refuses on non-Linux (exit 2) and is intended only for edge-dev3. Table/type creation without `IF NOT EXISTS` fails closed on re-entry (safe, not idempotent).
- **Chromium unpinned in CI.** The one-shot must record the Chromium version in its receipt/evidence. Next is pinned (16.x); `--turbopack` / `--experimental-https*` flags are unchanged.

## Setup-batch measurement labeling (fixed)

The static 5→1 setup reduction is real in code (4× `install` + `repin` versus one batched context). The measurement JSON and script are now sealed:

- `docs/verification/oracle2/s11-setup-batch-measurement-01.json`
- `scripts/oracle2/measure-s11-setup-batch-01.py`

Label on both: **TEST SETUP measurement only — UNPROVED for business/realized savings.** Recording-harness wall time is not production install cost. Never a business claim.

## Fixture-order proof (Muse Critical 5)

`services/oracle-brain/tests/test_s11_next_database_fixture_order.py` is a real file (sealed from edge-dev3). Offline only: no socket, Docker, DB or actual Next. It proved 2/2 PASS offline (phase-binding precedes qualification; env restored on both success and failure paths). That 2/2 is an **offline pure** result, not a Next/DB result.

## Bounds and cleanup

Original request windows remain 30s or narrower, original SQL startup/statement/lock/close guards remain active. Preserve current outer test/worker budgets; no skip/timeout inflation. Child Next/browser/Auth/backend resources close in finally. Kill only the exact owned child process group; prove no active descendants **and** run the sealed runner's name/port/lock scan (see known gap above). Canonical worker helper performs exact namespace cleanup, then independently prove labeled containers/networks/volumes absent. Do not create a new shared runner, reuse an old target or clean foreign resources.

## What remains UNPROVED after a green one-shot

1. **W10 dist lock under full parallel** — named remaining gate (see dist-lock note).
2. **W10 SAME fit / W10 Next stability** — explicitly not claimed; suites sit in different W10 workers.
3. **Business / realized savings** from setup batching — test-setup only.
4. **Full integrated W10** (120s / ten workers / per-request ≤30 / full population / 0 F/E/S/timeout/launch/cleanup) — root-owned.
5. **Live proof and business/company acceptance** — separate holds.

No provider/meeting/company action, actual appointments/installation, employee/company acceptance or original-D generation claim is authorized or inferred. Passing this synthetic full framework proof would still leave live proof and business acceptance separate on the existing issue.
