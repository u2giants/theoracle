# S07 Create-child fresh invented proof plan (runner packet)

Prepared only. No database, provider, native, or production effect is authorized by this file.
Root release after independent exact SOURCE + one resource-plan assessment is required before any run.
Business-acceptance hold remains in force.

Revision note: this packet answers Muse plan-review `20261023T210410-633252-7795` findings
H-A..H-E, M-A..M-K, L-A..L-E against head `9132df58`. Every identifier below is taken from
sealed source in this worktree, not from prior plan prose. It supersedes the previous
revision's selector, hashing, runner, artifact-index, error-chain, env, role-count,
decision-rule, and upgrade-target claims.

## Exact inputs (M-A, H-B)

| Input | Value |
|---|---|
| Plan-document head under this revision | the commit that lands this file (not `a693d210`, which is the PR base and is not a packet head) |
| Historical reviewed heads (NOT run targets) | `a693d210` (base of PR #207), `9132df58` (prior plan-only revision) — recorded history only |
| Run-time head rule | The review receipt that gates the run must bind the exact HEAD **after** the diagnostic upgrades below land. At execution, `git rev-parse HEAD` must equal that receipt head. A receipt taken before upgrades land cannot gate a post-upgrade run; re-resolve and re-review. Never follow a stale pin. |
| Source-before/after (H-B) | Before gate and after run, snapshot the worktree by walking every regular file under the worktree root and recording, per relative path: `sha256` of file **contents** and `st_mode & 0o777`. Write `source-before.json` / `source-after.json` as canonical JSON (no NUL bytes). Exclude `.git/` and treat `.pytest_cache/`, `__pycache__/`, `node_modules/`, `apps/web/.next/`, `.turbo/` as **must-be-absent or must-match**: run with `-p no:cacheprovider` and `PYTHONDONTWRITEBYTECODE=1`, and if any of those trees appear, their files are hashed too (a new cache dir is a difference). Unstaged edits, unstaged chmods, and untracked-file contents all count. This is file-content hashing, not `git ls-files` names or index blobs. |
| Diagnostic evidence note | `docs/verification/oracle2/s07-create-child-fixture-diagnostics.md` — line pins in that note are historical; this packet requires the note to be updated when the upgrades land (L-C). Trust sealed snapshot, not the note's line numbers. |
| Failing historical run | 39760061151 (5370 cases, 1 failure) |
| Known child signal | exit 2, `stage:exchange`, `state:UNKNOWN`, protected channel refused `http-headers` then `closed-wire` (stderr of the child) |
| Working hypothesis | second `current_v1` inside `beforeWrite` during `exchange_provider_v1` gets 503 from the protected create-worker service |

## What this run can and cannot discriminate (H-E, honest limits)

Production erases the inner rejection before any fixture can see it. State this as fact, not as a capture requirement:

- `RecallWireClientV1.within()` in `packages/shared/src/protected-node-https.ts` (the private method used on `beforeWrite()` before request bytes) rejects with a **fixed** `new Error('Installed Recall operation unavailable')`, discarding the inner error.
- The outer `catch` of `exchange` wraps everything in `RecallWireUncertaintyV1` (`packages/shared/src/protected-node-https.ts`, constructor around the `Installed Recall operation unavailable` message). That constructor sets **no** `cause`.
- Therefore the driver catch on the working-hypothesis path sees `error_type == "RecallWireUncertaintyV1"`, **never** `"Error"`, with `error_cause_type` absent and a fixed identical `error_message`.
- The protected-service path (`packages/shared/src/protected-service-channel.ts`) throws a fixed `Error('Replacement control unavailable')` via its `failure()` helper; that path also has a fixed identical message.
- Fixture-only code cannot recover what production erased. Capturing `error_message` / `error_cause_type` "if present" yields nothing discriminating for the working-hypothesis path. Do not treat `error_type=="RecallWireUncertaintyV1"` or `error_type=="Error"` as cause identification.

Therefore the first fresh instance is a **diagnostic-capture run**. Success at this stage is a complete artifact packet that either (a) names the exact cause from new discriminating evidence that is **not** the erased exception chain (server raise-site tag, SQL state, wire/ordering, deadlines), or (b) records remaining UNKNOWN naming the impossibility above and the exact missing predicate. A green instance is handled in the decision rule below. **The first run outcome may legitimately be UNKNOWN that names this cause-erasure impossibility**; that is a complete result, not a failed plan.

## Required diagnostic upgrades before the one fresh instance

These are fixture-only / test-only source changes. No guard, no retry, no fallback, no production public error leak.
Named upgrade target files (L-C): `services/oracle-brain/tests/test_meeting_unattended_sql.py`,
`services/oracle-brain/tests/fixtures/meeting-unattended-driver.mts`, and the fixture-only wrap in
the unattended fixture (which already monkeypatches `RequestHandlerClass` methods). Do **not**
edit `services/oracle-brain/oracle_brain/hosting/_protected_control_listener_v1.py` or any
`packages/shared/src/**` file. Also update `docs/verification/oracle2/s07-create-child-fixture-diagnostics.md`
in the same change so its line pins and claims match the post-upgrade source.

### 1. Server-side raise-site tag (H3 / prior, M-J, L-D)

The create-worker server runs **in-process** (`test_meeting_unattended_sql.py` `start_server` /
`RequesterServer`). The existing fixture wrap intercepts only `send_response` / `send_header` /
`end_headers`, which see status and headers only — not the POST body and not the exception.

Fixture-only interception inventory (L-D), to be listed in the upgrade PR and in
`create-child-diagnostics.json` so the later SOURCE check can verify minimality:

| Interception point | What it can see | Used? |
|---|---|---|
| `Handler.send_response` / `send_header` / `end_headers` (already wrapped) | status, header pairs | yes — existing jsonl |
| `Handler.do_POST` wrap (fixture-only) | exception class/`type(error).__name__` at the `except` that calls `_deny()`, and the request body bytes already read | yes — raise-site tag + operation name |
| `factory.execute_v1` wrap | factory entry, command name | optional, only if `do_POST` wrap cannot name the site |
| `settings.current()` wrap | which `current()` call refused | optional, last resort |
| Production `_deny` / listener source | refusal shape | **never touch** |

Record per request: monotonic timestamp (`time.monotonic()` at wrap entry), request sequence index,
`operation` **from the POST body JSON `operation` field** (not from the fixture, not from the route):
the wire operations are `prepare`, `claim`, `current`, `observe`, `status` — there is **no**
`repeated-claim` wire operation; that string is a **test phase** name only. The repeated-claim
request's wire `operation` is `claim`. And a fixture-only `raise_site` tag = `type(error).__name__`
plus the Python frame's code name if available without reading production secrets.
If a raise-site tag cannot be added without touching production refusal shape, record
`raise_site: UNKNOWN` and say so — do not invent one. Keep production response bytes identical
(still `503` / empty body / `Cache-Control: no-store`).

### 2. Error chain capture (H-E)

In the driver catch (`meeting-unattended-driver.mts`), record `error_type`, `error_message`,
and `error_cause_type` **if present**, plus the stage and the deadlines in §3. Still do not infer
cause from `"Error"` or `"RecallWireUncertaintyV1"` alone. `error_message` is subject to the
redaction rule in §5.

### 3. Deadline capture owner (M-C, M-D)

Three distinct deadlines exist in sealed source and each needs a named owner upgrade:

| Deadline | Sealed source | Owner upgrade |
|---|---|---|
| Driver `original_deadline_v1` | `packages/shared/src/protected-meeting-worker.ts` constructor (`this.original_deadline_v1=canonicalInstantV1(Math.floor(this.window.end))`) | driver catch + success stdout already has it; **failure stdout must add it** |
| Request-body `caller_deadline` | same file, `control()` builds `caller_deadline:this.original_deadline_v1` per request | already identical to `original_deadline_v1` on the wire; record it from the request body in the server wrap (§1) |
| Remaining-at-exchange (TS window) | `protected-node-https.ts` `remaining(window)` uses `wallDeadline`/`monotonicDeadline`; `exchange_provider_v1` passes `wallDeadline:this.window.end, monotonicDeadline:this.window.proxyMonoEnd` | driver must snapshot `Date.now()` and `process.hrtime.bigint()` immediately before `exchange_provider_v1` and again in the catch; record both and the delta |
| SQL `claim_original_deadline` | `services/oracle-brain/oracle_brain/hosting/meeting_capture_worker_v1.py` `observe_v1` reads `prior.claim_original_deadline` | claim-state upgrade (§4) selects it |

No other upgrade may claim to capture deadlines; these four rows are the full ownership.

### 4. Richer claim-time state (M-D) — exact tables

The claim query must select, with exact table and column names from sealed source
(`test_meeting_unattended_sql.py` teardown and asserts already use these):

| Fact | Table / source | Columns |
|---|---|---|
| Claim rows | `oracle2.meeting_capture_worker_claims_v1` | `claim_id`, `state`, `created_at`, `effect`, `stage` |
| Receipts count + wires | `oracle2.meeting_capture_worker_receipts_v1` JOIN `oracle2.meeting_capture_worker_claims_v1` USING(`claim_id`) | `count(*)`, `wire_object_key`, `wire_sha256`, `wire_byte_count`, `receipt_id`, `observation` |
| Latest event | `oracle2.meeting_capture_events_v1` | `action`, `payload`, `created_at` (order by `created_at` desc limit 1) |
| Head state | `oracle2.meeting_capture_heads_v1` | `state`, `capture_open`, `stop_state` |
| Admission state | `oracle2.meeting_capture_admissions_v1` | `admission_id`, `admission_sha256`, `role_name`, `actions`, `capture_until`, `stop_until`, `original_horizon`, `expires_at` |
| Supervision scope | **in-memory only** — `u['scope']` is a `MeetingSupervisorScopeV1` instance in the fixture | pin `scope.model_dump(mode='json')` to `tmp_path/supervision-scope.json` **before** teardown deletes scratch |
| Replay spool | scratch dir `short/'replay'` (`meeting-create-init.json`, `meeting-create-state.json`, `meeting-create-lock`) | copy to `tmp_path/replay-spool/` **before** `private.cleanup()`; record copy source path, copy monotonic time, and a redaction note that the spool holds nonce-sequence state and appointment hashes only (no secrets) |

"Original deadline" is ambiguous in prose; the implementation must label each field with the
four-row table in §3 (`original_deadline_v1`, `caller_deadline`, `exchange_remaining_ms`,
`claim_original_deadline`).

### 5. Redaction rule (M-E)

`error_message` is a new field class outside the evidence note's nonsecret list. Deterministic rule:

- **Allow:** exception class name; fixed production refusal strings that already appear in sealed
  source (`Installed Recall operation unavailable`, `Replacement control unavailable`); stage
  names from the driver (`prepare`/`claim`/`current`/`exchange`/`observe`); integer counts;
  UUIDs already written by the test (claim_id, operation_id, admission_id); ISO-8601 timestamps.
- **Deny:** anything matching a filesystem path under `/tmp`, `/home`, `/proc`, the worktree root,
  or a Windows drive letter; hostnames other than `localhost.localdomain`; connection strings;
  passwords; certificate/key bytes; Authorization header values; raw request/response bodies;
  free-form exception text that is not one of the allow-listed fixed strings.
- Implementation: if `error_message` is not exactly one of the allow-listed fixed strings, write
  `error_message: "REDACTED"` and `error_message_kind: "unlisted"`. Never ship a deny-rule miss.

### 6. Always-on diagnostics and try/finally scope (M-I)

Exact scope, matching sealed source line groups in `test_meeting_unattended_sql.py`:

- **Pre-child block** (queue diagnostic, cycle diagnostic, warm-up queue reads, refused `prepare`
  requests, SQL zero-asserts, child spawn + `ready` wait): wrap in `try/finally` so that on any
  failure the packet still contains whatever was already written, plus a `pre-child-failure.json`
  naming the failing step and exception type.
- **Child wait:** `actual.wait(timeout=12)` stays at 12 (do not raise). On `TimeoutExpired`,
  record `stage: "wait"`, `error_type: "TimeoutExpired"`, and then **SIGKILL** the child
  (`os.kill(actual.pid, signal.SIGKILL)` then `actual.wait(timeout=5)`). The existing
  `terminate`/`p.wait(timeout=5)` helper is not enough on a hung child; the kill path must still
  restore the `stop_runtime` chmod recorded in §9 (L-A).
- **Early asserts after child wait** (outcome parse, witness, claim_time, the
  `returncode==0` assert): all inside the same `try/finally` so `create-child-diagnostics.json`,
  the jsonl copy, stderr, and provider-routes are written even when the assert fails.
- **Teardown raise must not eat evidence:** the `unattended` fixture `finally` already writes
  `actual-selected-state.json`, `actual-provider-routes.json`, observer files, then
  `stack.close()`, then `owned-process-cleanup.json`, then `private.cleanup()`. If any step in
  that `finally` raises, subsequent steps must still run (nested try/finally per step) so
  `private.cleanup()` and the artifact index (§7) are not skipped. The hung-child path is the
  highest-value case and must not skip capture.

### 7. Artifact index written in teardown AFTER close (H-D)

The artifact index is **not** written in the test body and is **not** a field of
`create-child-diagnostics.json`. It is a separate `tmp_path/artifact-index.json` written in the
fixture `finally` **after** `stack.close()` (so the create-server jsonl file is closed) and
**after** `private.cleanup()` is armed (spool copy already taken in §4). Order:

1. copy spool → `tmp_path/replay-spool/` (if not already done)
2. `stack.close()` (closes servers and children; `close_provider`)
3. **close-then-copy** `create-server-responses.jsonl` from `short/` to `tmp_path/`
4. write `owned-process-cleanup.json`
5. `private.cleanup()`
6. write `artifact-index.json`

`artifact-index.json` must list every packet member with relative path and sha256:

- `actual-create-child.stdout` (holds `stage` / `error_type` / `state` on failure)
- `actual-create-child.stderr` (holds `Oracle protected channel refused …` lines)
- `create-child-diagnostics.json`
- `create-server-responses.jsonl`
- `actual-provider-routes.json`
- `actual-observer-refusals.json` (and `actual-observer-process-observations.json` if present)
- `owned-process-cleanup.json`
- `actual-selected-state.json`
- `queue-diagnostic.stdout`, `queue-diagnostic.stderr`, `cycle-diagnostic.stdout`, `cycle-diagnostic.stderr`
- `scheduler-actual-queue.json`, `stop-actual-queue.json` (warm-up queue reads)
- `warmup-refusals.json` (if present; see §10 on overwrite)
- `post-create-current-queue.json` or `post-create-current-queue-refusal.json`
- `actual-repeated-claim.wire` (if the test reached that step)
- `actual-unattended-outcome.json` (only on success — index marks `present: false` otherwise)
- `source-before.json`, `source-after.json`
- `supervision-scope.json`, `replay-spool/` (directory, listed recursively)
- `pre-child-failure.json` (if present)

"Read the diagnostics" means read `artifact-index.json` first, then the packets it names.

### 8. Locked jsonl append + reader (L1 / prior, M-K)

- **Lock placement:** one module-level `threading.Lock` in `test_meeting_unattended_sql.py`
  (shared across all `Handler` instances of the same server — `ThreadingHTTPServer` creates one
  `Handler` class per server, so a class attribute or module global is required; an instance
  attribute is not sufficient).
- **Reader:** the test currently copies the jsonl while the server still serves. Replace with
  close-then-copy in the fixture `finally` (§7 step 3). If any interim read is needed for the
  in-test diagnostics, take the same lock and drop a trailing partial line (a line that does not
  parse as JSON is omitted and counted as `partial_tail_lines`).

## Constraints (unchanged)

- Do not suppress strict framing/currentness
- Do not refresh the original window
- Do not resend an uncertain claim
- Keep UNKNOWN/no-resend semantics
- Keep all meaningful positives and negatives
- No production public error leak
- No guard change, no retry, no fallback

## Gate before one fresh invented instance

1. Independent exact SOURCE assessment of the diagnostic delta (existing PR196-style diagnostic bytes **plus** the upgrades above) + this plan
2. Independent ONE resource-plan assessment (fresh PG + owned graph, canonical once, owned phase)
3. True database gate with a review receipt binding the exact run-time HEAD (post-upgrade; see M-A)
4. Root one-fresh release decision
5. Execute one fresh invented instance under original limits (runner packet below)
6. Read `artifact-index.json`, then the packets it names. Either name the exact cause from discriminating evidence, or record remaining UNKNOWN naming the exact missing predicate (including the H-E erasure impossibility where it applies)
7. Only then author a permanent fix; a rerun with no cause is not a repair

## Concrete runner packet (H-A, H-C, M-F, M-G, L-A, L-B)

| Item | Value |
|---|---|
| Exact selector (H-A) | `pytest services/oracle-brain/tests/test_meeting_unattended_sql.py::test_actual_independent_V2_processes_Create_to_unattended_STOP_terminal_receipt -q --tb=short` — this is the real test node at `services/oracle-brain/tests/test_meeting_unattended_sql.py:282`. The second node `test_actual_producer_death_refuses_Create_before_any_provider_HTTP` (`:409`) is the producer-death **negative** and is **not** the S07 target. `capture_seconds` is an **indirect `meeting_sql` param** (50 for `:282`, 40 for `:408`/`:409`), not a `capture_seconds` fixture kwarg. Do not invent a `test_meeting_unattended_create_child_actual` symbol; it does not exist. Run this one node only; "do not cut cases" applies to W10, not to this single-node diagnostic. |
| Runner path (H-C) | `/tmp/oracle-parent24-wy02uT/s07-fresh-invented-runner.py` on `edge-dev3`. That script, not a shell one-liner, owns: source-before snapshot → owned Compose project up → **`bootstrap_canonical_test_schema(admin_url, container_id=..., receipt_path=...)`** → export env → run the exact selector → source-after snapshot → artifact-index check → cleanup proof. S07 does **not** use the `admin_url` pytest fixture (`services/oracle-brain/tests/conftest.py`), which is the only place that calls `bootstrap_canonical_test_schema` today; the runner **must** call it explicitly or the run errors before any child or diagnostic exists (this is exactly the S08 21-error failure mode). |
| Real environment (M-F) | `ORACLE2_TEST_ADMIN_URL` (owned DB, `sslmode=verify-full`), `ORACLE2_SYNTHETIC_POSTGRES_CONTAINER` (owned container id), `ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT` + `ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT_SHA256` (from `bootstrap_canonical_test_schema`), `COMPOSE_PROJECT_NAME=oracle2-synthetic-p24s07fresh-<UUID>` (must match `oracle2-(?:ci\|synthetic)-[a-z0-9-]{1,80}` per `dev/oracle2/test_worker_postgres_fixture.py`), `PYTHONDONTWRITEBYTECODE=1`, `PYTHONHOME` (the interpreter prefix the fixture already sets for children). **There is no `ORACLE2_WORKER_CONTAINER_ID`** — that name has zero consumers repo-wide; do not invent it. `ORACLE2_INVENTED_PROVIDER_PORT`, `ORACLE2_MEETING_*_WORKER_BINDING_*`, `ORACLE2_INVENTED_DRIVER_PRELOAD`, `ORACLE2_INVENTED_READY_FILE`, `ORACLE2_INVENTED_QUEUE_DIAGNOSTIC`, `ORACLE2_INVENTED_CYCLE_DIAGNOSTIC`, `ORACLE2_INVENTED_OBSERVER_CONFIG_*` are set by the fixture itself; the runner does not set them. |
| Interpreter / toolchain pins (M-F) | Linux-only (`test_meeting_unattended_sql.py` reads `/proc/<pid>/stat`, `os.getuid()`; `conftest.py` has a Windows FileBlobStore workaround that is **not** sufficient for this test). Python = the venv/site-packages that already import `oracle_brain`, `psycopg`, `cryptography`, `pytest`. Node = `/usr/bin/node` (hardcoded in the test) with `tsx` importable via `--import tsx`. `openssl` CLI required (`certs` fixture runs `openssl req`/`x509`). Record `python -V`, `node -v`, `openssl version`, and `python -c 'import sys; print(sys.prefix, sys.path)'` in `runner-environment.json`. |
| Resource plan | ONE fresh invented Create-child instance. Synthetic fixture universe only. Owned Compose project/containers/networks/volumes only (`dev/oracle2/compose.yaml`: `postgres:16.10-alpine@sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297`, `mem_limit: 1g`, `cpus: 1.0`, loopback `127.0.0.1:${ORACLE2_POSTGRES_PORT:-55432}:5432`; the worker fixture forces `ORACLE2_POSTGRES_PORT=0` for an ephemeral host port). TLS fixture: the test's own `certs` fixture generates an invented CA + leaf certs via `openssl` subprocess into `tmp_path/tls` (there are no "certificate issuer containers"). No company originals, no real meetings, no paid provider, no host OS changes. |
| Limits | Child wait remains `timeout=12` in the case (do not raise). Surrounding W10 120s / per-request ≤30 / ten workers is **not** this run. This run is one diagnostic-capture instance. |
| Cache hygiene (L-A) | `pytest -p no:cacheprovider`. `PYTHONDONTWRITEBYTECODE=1` for the runner **and** inherited by children (the fixture already sets it via `env`). If `node`/`tsx` writes a cache under the worktree, it must appear in source-after (or be pre-excluded by hashing). The `stop_runtime` chmod (`apps/workers/src/services/oracle2-meeting-stop-process.ts` mode 0o600 → restore) must be restored on **every** exit path including SIGKILL; the kill path in §6 owns that restore. |
| Cleanup proof (L-B, M-G) | After run: `docker ps -aq --filter label=com.docker.compose.project=<project>`, `docker network ls -q --filter label=com.docker.compose.project=<project>`, `docker volume ls -q --filter label=com.docker.compose.project=<project>` — all empty (or the project was brought down with `docker compose -p <project> down --volumes`, which is what `worker_postgres_fixture` already does). **Nine** LOGIN roles are created by the fixture stack: three in `test_meeting_capture_sql.py` `meeting_sql` (`employee-control`, `provider-ingress`, `worker` channel roles) and six in `test_meeting_unattended_sql.py` `role()` (`scheduler`, `stop`, `observer`, `create`, `pre`, `post`). Cleanup must either `DROP ROLE` those nine or prove they live only inside the dropped test database and are gone with it (cluster-level roles survive a database drop — if the runner uses `owned_phase_database`, the nine roles are cluster-wide and must be dropped explicitly). Also prove: no leftover child processes (`owned-process-cleanup.json` `remaining_pids: []`), unix sockets absent (`scheduler.sock`, `stop.sock`), scratch `short/` deleted (`private.cleanup()` assert), `.pytest_cache` absent. Workspace rows retained by design (`oracle2.meeting_capture_*` history inside the dropped DB) are called out as `dropped_with_database: true`, not hidden as "retained". Record `absence_proven: true` only when all of the above are true. |
| Failure retention | On any non-zero exit or timeout: artifacts already written by the `try/finally` and the artifact index; never retry under a weaker class; never delete the packet. |

## Competing hypotheses (M-C) — enumerate, do not lock in

Deadline ownership is the §3 table; these hypotheses stay in scope only while those fields are captured:

1. Second `current_v1` in `beforeWrite` during `exchange_provider_v1` → protected service 503 (working hypothesis). Discriminators: server `raise_site` tag, `operation: current` on the jsonl entry that returned 503, ordering of jsonl vs child stage.
2. `_check` 30s bound / worker startup timing (`meeting_capture_worker_v1.py` `_check` raises `PermissionError('unchanged original worker deadline required')` when `(deadline-now).total_seconds()>30`). Discriminators: `original_deadline_v1` vs wall clock at each stage.
3. Peer pin / observer TLS failure. Discriminators: `actual-observer-refusals.json`, `warmup-refusals.json`.
4. `settings.current()` / original-end / framing refusal (`_protected_control_listener_v1.py` raise sites: framing, peer pin, window expired, deadline elapsed, reply expired, bounded metadata). Discriminators: `raise_site` tag.
5. Nonce-sequence or `max_age_seconds=2` staleness on supervisor `current()` (`MeetingSupervisorAdmissionV2.minimum_sequence`/`max_age_seconds=2`). Discriminators: `replay-spool/` copy (`meeting-create-state.json` sequence) vs `MeetingSupervisorAdmissionV2` pin.

A run that only "passes" the post-hoc `observe_supervisor_process_v2` witness does not select among these.

## Decision rule (M-H)

| Outcome | Action |
|---|---|
| Fail + discriminating evidence names one hypothesis | Name the cause; author a permanent repair on a branch; keep negatives; then full W10. |
| Fail + packet is complete but predicates remain indistinguishable (including the H-E erasure case) | Record UNKNOWN naming the exact missing discriminator (or naming the production cause-erasure impossibility). Design the next fixture-only diagnostic. Do **not** retry this same instance. |
| `TimeoutExpired` on `actual.wait` (no stage/type beyond `wait`/`TimeoutExpired`) | This is a distinct row. Record UNKNOWN-cause-hung-child with the full packet (SIGKILL path, §6). Do not merge into "fail + evidence". Do not retry. |
| Infra failure before any child (bootstrap, compose up, node/openssl missing, schema receipt mismatch) | Record `infra_failed` with `runner-environment.json` and the exact error. This is **not** a diagnostic UNKNOWN and does not consume the one-fresh budget; fix the runner and re-gate. Do not call it a product failure. |
| Green, including green with warm-up refusals that were overwritten (`warmup-refusals.json` is rewritten on each retry attempt at `test_meeting_unattended_sql.py` warm-up loop) | Not a repair. Record as "did not reproduce" **and** copy every intermediate `warmup-refusals` write (upgrade: write `warmup-refusals-attempt-N.json`, never overwrite). Strengthen timing/load capture (§3) or, if the team chooses to accept the flake, the **owner of that acceptance is Albert Hazan** — an AI session may not silently accept it. Then require **two clean full W10 runs on the same HEAD** before treating Create-child as stable (L-E). Do not claim the 39760061151 cause is fixed. |
| Two W10 runs (L-E) | Both runs must execute at the **same** `git rev-parse HEAD`, same population (the W10 verifier's registered case list — do not cut to 5370 and do not follow a drifting main), same resource plan. Gate: 0 F/E/S and all ten workers under 120s. Release: only after both runs are green at that one head may Create-child be called stable for that head. Resource plan: owned Compose project per run, torn down between runs. |

## Success check

- **This packet's gate:** `artifact-index.json` complete (every §7 member present or explicitly `present:false` with reason); source-before equals source-after (content + mode bits, § Exact inputs); owned resources absent (§ Cleanup); either exact cause named from a non-erased discriminator, or UNKNOWN with the missing predicate named (including naming the H-E erasure impossibility when it is the limit).
- **Program success (later):** exact cause found and permanently repaired while the same capabilities, strict framing, currentness, UNKNOWN and no-resend retain meaningful positives and negatives, and full W10 is clean with 0 F/E/S and all ten workers under 120s at one head (two clean same-head W10 runs, L-E). Create-child stability after a historical flake requires those two runs.

## Honest limits that cannot be true of this run

- This run cannot recover the inner exception of the working-hypothesis path; production erases it (H-E). `error_type` will be `RecallWireUncertaintyV1` there, with a fixed message and no cause.
- A passing post-hoc supervisor witness does not exonerate the in-exchange `_fresh_supervision` branch (H4 from the prior revision, unchanged).
- A green run does not prove the 39760061151 cause is fixed; it only fails to reproduce.
- Fixture-only diagnostics cannot change production refusal shape, cannot add a guard, retry, or fallback, and cannot make the UNKNOWN state resend-authorized.

Posted by MiMo chat on edge-dev. Parent #24. Business-acceptance hold remains in force.
