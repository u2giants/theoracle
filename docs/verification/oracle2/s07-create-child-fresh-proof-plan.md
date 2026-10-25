# S07 Create-child fresh invented proof plan (runner packet)

Prepared only. No database, provider, native, or production effect is authorized by this file.
Root release after independent exact SOURCE + one resource-plan assessment is required before any run.
Business-acceptance hold remains in force.

Revision note: this packet is **v4**. It answers Muse plan-review
`20261023T213157-676022-23280` findings M1–M5, m1–m10, n1–n8 against head
`f886989ca0386139bb1c7aafa4bf3e300771a7b9`, and keeps the H-E erasure honesty
and decision-rule rows from v3 (which answered
`20261023T210410-633252-7795` H-A..H-E, M-A..M-K, L-A..L-E against
`9132df584bbb333f61d1adad1e3abc152a568d86`). Every identifier below is taken
from sealed source in this worktree. It supersedes the previous revision's
interception ranking, runner sequence, artifact-index write order, cleanup
proof, claim-state columns, deadline count, and redaction scope.

## Exact inputs (M-A, H-B)

| Input | Value |
|---|---|
| Plan-document head under this revision | the commit that lands this file (not `a693d210c3555a565c0b753c5f175aa88ce931a8`, which is the PR base and is not a packet head) |
| Historical reviewed heads (NOT run targets) | `a693d210c3555a565c0b753c5f175aa88ce931a8` (base of PR #207), `9132df584bbb333f61d1adad1e3abc152a568d86` (v2 plan-only revision), `f886989ca0386139bb1c7aafa4bf3e300771a7b9` (v3 plan-only revision) — recorded history only |
| Run-time head rule | The review receipt that gates the run must bind the exact HEAD **after** the diagnostic upgrades below land. At execution, `git rev-parse HEAD` must equal that receipt head. A receipt taken before upgrades land cannot gate a post-upgrade run; re-resolve and re-review. Never follow a stale pin. |
| Source-before/after (H-B) | Before gate and after run, snapshot the worktree by walking every regular file under the worktree root and recording, per relative path: `sha256` of file **contents** and `st_mode & 0o777`. Write `source-before.json` / `source-after.json` as canonical JSON (no NUL bytes). Exclude `.git/` from the walk. The snapshot files themselves are written to the runner-owned packet directory **outside** the worktree, so they are not members of the hashed tree and the equality gate is satisfiable. Treat `.pytest_cache/`, `__pycache__/`, `node_modules/`, `apps/web/.next/`, `.turbo/` as **must-be-absent or must-match**: run with `-p no:cacheprovider` and `PYTHONDONTWRITEBYTECODE=1`, and if any of those trees appear, their files are hashed too (a new cache dir is a difference). Unstaged edits, unstaged chmods, and untracked-file contents all count. This is file-content hashing, not `git ls-files` names or index blobs. |
| Snapshot JSON schema | Each of `source-before.json` / `source-after.json` is `{"root": "<absolute worktree path>", "files": [{"path": "<relative path>", "sha256": "<64 lowercase hex>", "mode": "<4-digit octal, e.g. 0644>"}, ...]}` with `files` sorted by `path` ascending. `mode` is `st_mode & 0o777` rendered as 4-digit octal without `0o`. Equality gate: `source-before.json`'s `files` array equals `source-after.json`'s `files` array (deep equality of the sorted lists). |
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

**Non-erased wire metadata (n3).** `RecallWireUncertaintyV1` retains bounded observed **response** bytes in a private `#retained` buffer and exposes `get wire():Buffer`, `observedBytes:number`, `wireTruncated:boolean` (`packages/shared/src/protected-node-https.ts:25-26`). The class comment states these are "Bounded observed RESPONSE bytes on refusal, never request/key material." The driver catch must record, when `error instanceof RecallWireUncertaintyV1`: `wire_byte_count` = `error.wire.length` (integer) and `wire_sha256` = SHA-256 hex of `error.wire` (64 lowercase hex). These are non-erased, nonsecret metadata and are allow-listed (§5). The raw wire bytes themselves are **not** written to any artifact (deny rule: raw response bodies). This metadata discriminates non-hypothesis-1 paths (partial/truncated wire vs full refusal) without reading production secrets.

Therefore the first fresh instance is a **diagnostic-capture run**. Success at this stage is a complete artifact packet that either (a) names the exact cause from new discriminating evidence that is **not** the erased exception chain (server raise-site tag, SQL state, wire/ordering, deadlines), or (b) records remaining UNKNOWN naming the impossibility above and the exact missing predicate. A green instance is handled in the decision rule below. **The first run outcome may legitimately be UNKNOWN that names this cause-erasure impossibility**; that is a complete result, not a failed plan.

## Required diagnostic upgrades before the one fresh instance

These are fixture-only / test-only source changes. No guard, no retry, no fallback, no production public error leak.
Named upgrade target files (L-C): `services/oracle-brain/tests/test_meeting_unattended_sql.py`,
`services/oracle-brain/tests/fixtures/meeting-unattended-driver.mts`, and the fixture-only wrap in
the unattended fixture (which already monkeypatches `RequestHandlerClass` methods). Do **not**
edit `services/oracle-brain/oracle_brain/hosting/_protected_control_listener_v1.py` or any
`packages/shared/src/**` file. Also update `docs/verification/oracle2/s07-create-child-fixture-diagnostics.md`
in the same change so its line pins and claims match the post-upgrade source.

### 1. Server-side raise-site tag (H3 / prior, M-J, L-D, M1)

The create-worker server runs **in-process** (`test_meeting_unattended_sql.py` `start_server` /
`RequesterServer`). The existing fixture wrap intercepts only `send_response` / `send_header` /
`end_headers`, which see status and headers only — not the POST body and not the exception.

**M1 correction — do_POST wrap cannot be the primary capture.** Sealed source shows `do_POST`
catches everything internally and calls `_deny()` with no propagation
(`_protected_control_listener_v1.py:46-93`, bare `except Exception` at `:91-93`), while
`raw_request` is a consumed local (`:59-60`). A delegating `do_POST` wrapper sees neither the
swallowed exception nor the body. Do **not** specify a `do_POST` wrap as the raise-site capture.

**Primary capture (promoted from "optional"):**

| Interception point | How the fixture reaches it | What it sees | Used? |
|---|---|---|---|
| `factory.execute_v1(raw)` wrap — **PRIMARY** | Class-level fixture wrap of `_CaptureWorkerAdapter.execute_v1` (`meeting_worker_service_v1.py`, the class constructed inline in `_capture_worker_server` and passed as `factory` to `_protected_control_listener_v1`). The factory is a closure variable inside the listener (`_protected_control_listener_v1.py:70`), not a server attribute; the fixture discards the constructor return's internals (`test_meeting_unattended_sql.py` `worker()` calls `protected_meeting_create_worker_server_v1` and keeps only the server). A class-level wrap on `_CaptureWorkerAdapter.execute_v1` is therefore required; it is fixture-only and does not edit production files. | Raw request bytes; `q.operation` after `_parse(MeetingWorkerRequestV1, raw)`; every exception raised inside `execute_v1` (these **propagate** to the `except Exception` that calls `_deny()` at `_protected_control_listener_v1.py:91-93`). | **yes — primary raise-site tag + operation name** |
| `settings.current()` wrap | Class-level fixture wrap of `_CaptureWorkerSettings.current` (same closure problem; the instance `fixed` is a local in `_capture_worker_server`). | Which `current()` call refused (entry/exit), and the `PermissionError` from `current()`. | **yes — when the refusal is a currentness/window check inside `current()`** |
| `Handler.send_response` / `send_header` / `end_headers` (already wrapped) | Existing wrap in `worker()` for the create server (`test_meeting_unattended_sql.py`, `_logged_send_response` / `_logged_send_header` / `_logged_end_headers`) | status, header pairs | yes — existing jsonl |
| Production `_deny` / listener source | — | refusal shape | **never touch** |

**Module-global wraps for do_POST-level sites (named, M1):** the following production functions
are called from `do_POST` **before** or **around** `factory.execute_v1` and raise with propagation
to the same swallowed `except`. A fixture-only **module-global** wrap (monkeypatch of the name
imported into `oracle_brain.hosting._protected_control_listener_v1` or of the defining module) can
record entry/exit/exception for each:

| Wrap target (module-global) | Sealed source | Covers |
|---|---|---|
| `oracle_brain.hosting.replacement_transport_v1.peer_der_v1` | called twice in `do_POST` (`_protected_control_listener_v1.py` — before body read, and after `factory.execute_v1`) | peer-pin refusal |
| `oracle_brain.hosting.replacement_transport_v1.fixed_request_length_v1` | `do_POST` framing/content-length | framing |
| `oracle_brain.hosting.replacement_transport_v1.read_request_body_v1` | `do_POST` body read | framing / body-length |

**Sites that remain UNKNOWN (exact reason).** These are **inline** `raise PermissionError(...)`
statements inside `do_POST` itself, with no callable seam. A delegating `do_POST` wrap cannot see
them (the bare `except Exception` swallows and calls `_deny()`). The module-global wraps above
never enter. The raise-site tag for these is therefore **UNKNOWN** unless an ordered wrap-trace
(which of the wraps above returned successfully, and in what order) narrows the window; the plan
records the ordered wrap-trace as `wrap_trace` and sets `raise_site: "UNKNOWN"` for:

- framing: `self.server.closing or self.headers.get_all('Content-Encoding', []) != []` → `PermissionError('fixed requester lifecycle/framing required')`
- window expiry: `not datetime.now(timezone.utc) < request.caller_deadline <= min(...)` → `PermissionError('original requester window expired or excessive')`
- deadline elapsed: `self.server.closing or time.monotonic() >= original_end` → `PermissionError('original requester deadline elapsed')`
- reply expiry (inside `_request_fence_v1`, after `factory.execute_v1`): `PermissionError('original requester reply expired')`
- bounded metadata: `type(encoded) is not bytes or not 0<len(encoded)<=maximum_response_bytes` → `PermissionError('fixed bounded protected metadata required')` (after `encode_response` returns; `encode_response` is `_encode_worker_packet` / a lambda with no fixture seam that sees the raise)

If a raise-site tag cannot be added without touching production refusal shape, record
`raise_site: UNKNOWN` and say so — do not invent one. Keep production response bytes identical
(still `503` / empty body / `Cache-Control: no-store`).

Record per request: monotonic timestamp (`time.monotonic()` at wrap entry), request sequence index,
`operation` **from the POST body JSON `operation` field** (captured in the `execute_v1` wrap from
`raw`; not from the fixture, not from the route): the wire operations are `prepare`, `claim`,
`current`, `observe`, `status` — there is **no** `repeated-claim` wire operation; that string is a
**test phase** name only. The repeated-claim request's wire `operation` is `claim`. And a
fixture-only `raise_site` tag = `type(error).__name__` plus the Python frame's code name if
available without reading production secrets (from the `execute_v1` / `settings.current()` /
module-global wraps), else `UNKNOWN` as above.

### 2. Error chain capture (H-E, n3)

In the driver catch (`meeting-unattended-driver.mts`), record `error_type`, `error_message`,
and `error_cause_type` **if present**, plus `wire_byte_count` and `wire_sha256` when
`error instanceof RecallWireUncertaintyV1` (§ non-erased wire metadata above), plus the stage and
the deadlines in §3. Still do not infer cause from `"Error"` or `"RecallWireUncertaintyV1"` alone.
`error_message` and all new fields are subject to the redaction rule in §5.

### 3. Deadline capture owner (M-C, M-D, m2, m4, m10)

**Four rows / four owners** (not "three distinct deadlines"). Each needs a named owner upgrade:

| Deadline | Sealed source | Owner upgrade |
|---|---|---|
| Driver `original_deadline_v1` | `packages/shared/src/protected-meeting-worker.ts` constructor (`this.original_deadline_v1=canonicalInstantV1(Math.floor(this.window.end))`, around `:45`) | **success stdout already has it** (`meeting-unattended-driver.mts` success write includes `deadline:w.original_deadline_v1`); **catch/failure stdout does NOT have it** (catch write is only `state`/`remote_stop_proven`/`stage`/`error_type` at the catch `canonicalJson`). Failure stdout must add `deadline:w.original_deadline_v1`. |
| Request-body `caller_deadline` | same file, `control()` builds `caller_deadline:this.original_deadline_v1` per request (around `:67`) | already identical to `original_deadline_v1` on the wire; record it from the request body in the `execute_v1` wrap (§1) as `caller_deadline` |
| Remaining-at-exchange (elapsed-proxy, **m10**) | `protected-node-https.ts` `remaining(window)` uses `wallDeadline`/`monotonicDeadline` (private method on `RecallWireClientV1`); `exchange_provider_v1` passes `wallDeadline:this.window.end, monotonicDeadline:this.window.proxyMonoEnd` (`protected-meeting-worker.ts:101`) | **label this an elapsed-proxy.** The driver snapshots `Date.now()` and `process.hrtime.bigint()` immediately before `exchange_provider_v1` and again in the catch, and records `exchange_elapsed_wall_ms` and `exchange_elapsed_mono_ms` (the deltas). These measure **elapsed** time, not `remaining()`. **Wall-remaining is computable** from `original_deadline_v1` as `Date.parse(w.original_deadline_v1) - Date.now()` at each snapshot; record that as `wall_remaining_at_exchange_ms` / `wall_remaining_at_catch_ms`. The private `window.end` / `window.proxyMonoEnd` are **not** fixture-visible without production change; do not claim to capture them. |
| SQL `claim_original_deadline` | sealed DDL: `oracle2.meeting_capture_worker_claims_v1.original_deadline timestamptz NOT NULL` (`services/oracle-brain/sql/020_meeting_capture.sql:660-669`); `meeting_capture_worker_v1.py` `observe_v1` reads `prior.claim_original_deadline` | claim-state upgrade (§4) selects `original_deadline` |

No other upgrade may claim to capture deadlines; these four rows are the full ownership.
Label every deadline field with its row name (`original_deadline_v1`, `caller_deadline`,
`wall_remaining_*_ms` / `exchange_elapsed_*_ms` as elapsed-proxy, `claim_original_deadline`).

### 4. Richer claim-time state (M5, m4) — exact tables

**M5 correction — claim-rows columns were wrong.** `oracle2.meeting_capture_worker_claims_v1`
has **no `state` column** and **does** have `original_deadline timestamptz NOT NULL`
(`services/oracle-brain/sql/020_meeting_capture.sql:660-669`). The v3 columns
`claim_id, state, created_at, effect, stage` would fail; the existing query at
`test_meeting_unattended_sql.py:345` (`SELECT claim_id::text,state,created_at::text FROM ...`)
survives only via `except` → `claim_time_error` at `:347-348`. The upgrade must select columns that
exist.

| Fact | Table / source | Columns / query |
|---|---|---|
| Claim rows | `oracle2.meeting_capture_worker_claims_v1` | **`claim_id`, `original_deadline`, `created_at`, `effect`, `stage`** (all exist at `020_meeting_capture.sql:660-669`; also available and recommended: `operation_id`, `request_sha256`, `bot_id`, `worker_id`). **Do not select `state` — it does not exist.** |
| Receipts count + wires | `oracle2.meeting_capture_worker_receipts_v1` JOIN `oracle2.meeting_capture_worker_claims_v1` USING(`claim_id`) | **Two valid SELECTs** (count plus per-row columns cannot be one SELECT): (1) `SELECT count(*) ... WHERE q.workspace_id=%s`; (2) `SELECT q.effect, q.stage, r.wire_object_key, r.wire_sha256, r.wire_byte_count, r.receipt_id, r.observation ... WHERE q.workspace_id=%s`. Alternatively one SELECT with `json_agg(...)`. Columns exist at `020_meeting_capture.sql:670-676`. |
| Latest event | `oracle2.meeting_capture_events_v1` | `action`, `payload`, `created_at` (order by `created_at` desc limit 1) |
| Head state | `oracle2.meeting_capture_heads_v1` | `state`, `capture_open`, `stop_state` |
| Admission state | `oracle2.meeting_capture_admissions_v1` | `admission_id`, `admission_sha256`, `role_name`, `actions`, `capture_until`, `stop_until`, `original_horizon`, `expires_at` — columns come from the `meeting_sql` insert list (`test_meeting_capture_sql.py`) and the admissions DDL; **do not claim this test's asserts already read them** |
| Supervision scope | **in-memory only** — `u['scope']` is a `MeetingSupervisorScopeV1` instance in the fixture | pin `scope.model_dump(mode='json')` to `tmp_path/supervision-scope.json` **before** teardown deletes scratch; apply §5 redaction to every field |
| Replay spool | scratch dir `short/'replay'` (`meeting-create-init.json`, `meeting-create-state.json`, `meeting-create-lock`) | copy to `tmp_path/replay-spool/` **before** teardown close/cleanup (see §7 numbered order); record copy source path, copy monotonic time, and a redaction note that the spool holds nonce-sequence state and appointment hashes only (no secrets); apply §5 redaction |

"Original deadline" is ambiguous in prose; the implementation must label each field with the
four-row table in §3.

### 5. Redaction rule (M-E, m8)

**m8 correction — redaction covers every new field, not only `error_message`.** New field classes
outside the evidence note's nonsecret list: `error_message` and `error_cause_type` (driver catch),
jsonl wrap fields (`raise_site`, `wrap_trace`, `operation`, `caller_deadline`, monotonic floats),
`supervision-scope.json`, the spool copy, and every deadline snapshot field
(`original_deadline_v1`, `caller_deadline`, `wall_remaining_*_ms`, `exchange_elapsed_*_ms`,
`claim_original_deadline`, `wire_byte_count`, `wire_sha256`). Deterministic rule applies to
**every** JSON artifact write and **every** jsonl append:

- **Allow:** exception class name; fixed production refusal strings that already appear in sealed
  source (`Installed Recall operation unavailable`, `Replacement control unavailable`,
  `fixed requester lifecycle/framing required`, `original requester window expired or excessive`,
  `original requester deadline elapsed`, `original requester reply expired`,
  `fixed bounded protected metadata required`); stage names from the driver
  (`prepare`/`claim`/`current`/`exchange`/`observe`/`wait`); wire operation names
  (`prepare`/`claim`/`current`/`observe`/`status`); integer counts and integer byte counts;
  **finite IEEE-754 floats** from `time.monotonic()` / `Date.now()` / `process.hrtime.bigint()/1e6`
  (monotonic/elapsed proxies — explicitly allow-listed); UUIDs already written by the test
  (claim_id, operation_id, admission_id, workspace_id, meeting_id, worker_id, actor_id,
  scope UUIDs from `MeetingSupervisorScopeV1` — explicitly allow-listed); ISO-8601 timestamps;
  64-lowercase-hex hashes (`sha256`, `wire_sha256`, `request_sha256`, `admission_sha256`);
  4-digit octal mode strings; `true`/`false`/`null`; enum strings already in sealed source
  (`effect`, `stage`, `state` head values, `error_type` class names).
- **Deny:** anything matching a filesystem path under `/tmp`, `/home`, `/proc`, the worktree root,
  or a Windows drive letter; hostnames other than `localhost.localdomain`; connection strings;
  passwords; certificate/key bytes; Authorization header values; raw request/response bodies
  (including `RecallWireUncertaintyV1.wire` bytes — capture only its byte count and sha);
  free-form exception text that is not one of the allow-listed fixed strings.
- **Implementation hook (m8):** one function `redact_record(record: dict) -> dict` in the test/
  fixture module. It walks every value; anything not matched by the allow-list becomes
  `"REDACTED"` and the parallel key `"<field>_kind": "unlisted"` is set. Apply it to every jsonl
  append and every JSON artifact write (`create-child-diagnostics.json`,
  `supervision-scope.json`, spool-copy manifest, deadline snapshot fields inside
  `create-child-diagnostics.json`, `warmup-refusals*.json` message fields,
  `post-create-current-queue-refusal.json`, `infra-failed.json`). Never ship a deny-rule miss.

### 6. Always-on diagnostics and try/finally scope (M-I, m5)

Exact scope, matching sealed source line groups in `test_meeting_unattended_sql.py`:

- **Pre-child block** — wrap **from the start of `start_unattended(unattended)` onward** (m5:
  `start_unattended()` is inside this try/finally; it can fail at server startup
  (`start_server` / `RequesterServer` bind), observer spawn (child + portfile wait), or
  `invite(x)` at its end). The try/finally covers: `start_unattended()`, queue diagnostic, cycle
  diagnostic, warm-up queue reads, refused `prepare` requests, SQL zero-asserts, child spawn +
  `ready` wait. On any failure the packet still contains whatever was already written, plus a
  `pre-child-failure.json` naming the failing step and exception type.
- **Child wait:** `actual.wait(timeout=12)` stays at 12 (do not raise). On `TimeoutExpired`,
  record `stage: "wait"`, `error_type: "TimeoutExpired"`, and then **SIGKILL** the child
  (`os.kill(actual.pid, signal.SIGKILL)` then `actual.wait(timeout=5)`). The existing
  `terminate`/`p.wait(timeout=5)` helper is not enough on a hung child; the kill path must still
  restore the `stop_runtime` chmod recorded in the runner-packet Cache-hygiene row.
- **Early asserts after child wait** (outcome parse, witness, claim_time, the
  `returncode==0` assert): all inside the same `try/finally` so `create-child-diagnostics.json`,
  the jsonl copy, stderr, and provider-routes are written even when the assert fails.
- **Teardown raise must not eat evidence:** the `unattended` fixture `finally` already writes
  `actual-selected-state.json`, `actual-provider-routes.json`, observer files, then
  `stack.close()`, then `owned-process-cleanup.json`, then `private.cleanup()`. If any step in
  that `finally` raises, subsequent steps must still run (nested try/finally per step) so
  `private.cleanup()` runs and the packet is not skipped. The hung-child path is the
  highest-value case and must not skip capture.

### 7. Artifact index written by the RUNNER after pytest (M3, m7, n7)

**M3 correction — the index cannot be written in the fixture `finally`.** `source-after.json` is
written by the runner **after** pytest exits; a fixture-written index cannot hash it. **Chosen
design (a):** the **runner** writes `artifact-index.json` after pytest exits, covering all
fixture-written members plus `source-after.json`, `source-before.json`, and
`runner-environment.json`.

**Write order (n7 — drop the vague "after `private.cleanup()` is armed"; this numbered order
carries the requirement alone):**

1. (fixture, before teardown close) copy spool → `tmp_path/replay-spool/` if not already done
2. (fixture teardown) `stack.close()` (closes servers and children; `close_provider`)
3. (fixture teardown) **close-then-copy** `create-server-responses.jsonl` from `short/` to `tmp_path/`
4. (fixture teardown) write `owned-process-cleanup.json`
5. (fixture teardown) `private.cleanup()`
6. (pytest exits)
7. (runner) write `source-after.json` to the packet directory (outside the worktree)
8. (runner) write `artifact-index.json` to the packet directory, covering every member below

**Relative-path root (unambiguous):** the **runner-owned packet directory** `RUNNER_DIR`
(e.g. `/tmp/oracle-parent24-wy02uT/s07-fresh-invented-packet/` on `edge-dev3`). All index `path`
values are relative to `RUNNER_DIR`. Fixture members land under `RUNNER_DIR/pytest-tmp/<testid>/`
because pytest is invoked with `--basetemp=RUNNER_DIR/pytest-tmp` (m6); the index lists them as
`pytest-tmp/<testid>/<file>`. `source-before.json`, `source-after.json`,
`runner-environment.json`, and `artifact-index.json` itself sit directly under `RUNNER_DIR/`.

**Snapshot placement:** `source-before.json` / `source-after.json` are written to `RUNNER_DIR/`
(outside the worktree), so the worktree hash walk never includes them; equality is the `files`
array deep-equality defined in Exact inputs.

**Snapshot / index member entry schema:** each index member is
`{"path": "<relative to RUNNER_DIR>", "sha256": "<64 lowercase hex>", "mode": "<4-digit octal>",
"present": true|false, "note": "<absent reason when present=false>"}`. `artifact-index.json` is
`{"root": "<RUNNER_DIR absolute>", "members": [ ... ]}` with `members` sorted by `path`.

**Index member list (m7 — includes `warmup-refusals-attempt-N.json`):**

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
- `warmup-refusals-attempt-N.json` (one per warm-up attempt N = 1, 2, …; **n8: cumulative**, see below)
- `warmup-refusals.json` (final cumulative list; see § Decision-rule green row)
- `post-create-current-queue.json` or `post-create-current-queue-refusal.json`
- `actual-repeated-claim.wire` (if the test reached that step)
- `actual-unattended-outcome.json` (only on success — index marks `present: false` otherwise)
- `source-before.json`, `source-after.json`
- `runner-environment.json`
- `supervision-scope.json`, `replay-spool/` (directory, listed recursively)
- `pre-child-failure.json` (if present)
- `infra-failed.json` (if present; runner-written on infra failure)

**n8 — warmup-refusals-attempt-N semantics.** Sealed source writes `warmup-refusals.json` as a
**cumulative** list on each retry attempt (the `observations` list grows across attempts and each
write serializes the whole list). Therefore `warmup-refusals-attempt-N.json` files are
**cumulative snapshots** (attempt N contains every refusal observed through attempt N), **not**
deltas. The final `warmup-refusals.json` equals `warmup-refusals-attempt-N.json` for the last N.

"Read the diagnostics" means read `artifact-index.json` first, then the packets it names.

### 8. Locked jsonl append + reader (L1 / prior, M-K)

- **Lock placement:** one module-level `threading.Lock` in `test_meeting_unattended_sql.py`
  (shared across all `Handler` instances of the same server — `ThreadingHTTPServer` creates one
  `Handler` class per server, so a class attribute or module global is required; an instance
  attribute is not sufficient).
- **Reader:** the test currently copies the jsonl while the server still serves. Replace with
  close-then-copy in the fixture teardown (§7 step 3). If any interim read is needed for the
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

## Concrete runner packet (H-A, H-C, M-F, M-G, L-A, L-B, M2, m1, m3, m6, n1, n2, n4, n5, n6, m9)

| Item | Value |
|---|---|
| Exact selector (H-A) | `pytest services/oracle-brain/tests/test_meeting_unattended_sql.py::test_actual_independent_V2_processes_Create_to_unattended_STOP_terminal_receipt -q --tb=short` — this is the real test node at `services/oracle-brain/tests/test_meeting_unattended_sql.py:282`. The second node `test_actual_producer_death_refuses_Create_before_any_provider_HTTP` (`:409`) is the producer-death **negative** and is **not** the S07 target. `capture_seconds` is an **indirect `meeting_sql` param** (50 for `:282`, 40 for `:408`/`:409`), not a `capture_seconds` fixture kwarg. Do not invent a `test_meeting_unattended_create_child_actual` symbol; it does not exist. Run this one node only; "do not cut cases" applies to W10, not to this single-node diagnostic. |
| Runner path (H-C, m9) | `/tmp/oracle-parent24-wy02uT/s07-fresh-invented-runner.py` on **`edge-dev3`** (this is the only host name in this packet). That script, not a shell one-liner, owns the sequence below. |
| Runner sequence (M2, m3, m6) | (1) write `source-before.json` to `RUNNER_DIR/`; (2) owned Compose project up (`docker compose -f dev/oracle2/compose.yaml -p <project> up -d --wait postgres` with `ORACLE2_POSTGRES_PORT=0`); (3) **TLS bootstrap** — call `dev/oracle2/test_tls_bootstrap.bootstrap(container, plain_admin_url, RUNNER_DIR/tls)` (the established helper; see `test_meeting_capture_sql.py` `admin()` → `owned_worker_database` and `test_worker_postgres_fixture.py`). This produces `ORACLE2_TEST_ADMIN_URL` with `sslmode=verify-full` + `sslrootcert`, plus `ORACLE2_TEST_TLS_ROOT` and `ORACLE2_TEST_TLS_QUALIFICATION`. **S07 cannot reuse `worker_postgres()` unchanged** because it requires a `(documentary-NN|event)` label (`test_worker_postgres_fixture.py:54-55`); the runner performs the same steps `worker_postgres` performs internally: compose up, identity checks, `bootstrap(...)` for TLS, then uses the verify-full URL. Every later DB touch goes through `admin()` → `owned_worker_database`, which refuses unless the conninfo carries `sslmode=verify-full`, `sslrootcert`, and an exact dbname (`test_worker_postgres_fixture.py:20-46`); (4) **`bootstrap_canonical_test_schema(admin_url, container_id=..., receipt_path=RUNNER_DIR/<label>-schema.json)`** exactly once, using the verify-full URL. **m3:** this is **not** the only caller — `test_owned_worker_database.py`, `scripts/oracle2/verify_workflow_integrity.py`, and `owned_phase_database` (`test_canonical_schema.py`) also call it — but the substance holds: `meeting_sql` uses `ORACLE2_TEST_ADMIN_URL` directly (`test_meeting_capture_sql.py` `admin()`), not the `admin_url` pytest fixture, so the runner **must** call bootstrap explicitly or the run errors before any child or diagnostic exists. **Double-bootstrap hazard:** if bootstrap runs twice against the same owned container, the second run must not re-apply migrations over a live schema; the runner calls it exactly once and the S07 test path does not call it. The historical "S08 21-error failure mode" (n6) is **historical handoff corroboration only**, not sealed-source specification; (5) export env; (6) run the exact selector with `--basetemp=RUNNER_DIR/pytest-tmp` (absolute, runner-owned; precedent `scripts/oracle2/verify_workflow_integrity.py` `--basetemp=`) and `-p no:cacheprovider` (m6: `-p no:cacheprovider` removes pytest last-run pointers, so `--basetemp` is the only artifact-discovery mechanism); (7) write `source-after.json` to `RUNNER_DIR/`; (8) write `artifact-index.json` to `RUNNER_DIR/` (§7); (9) cleanup proof (below). |
| Real environment (M-F, M2, n5) | `ORACLE2_TEST_ADMIN_URL` (owned DB, **`sslmode=verify-full` + `sslrootcert`**, from `test_tls_bootstrap.bootstrap`), `ORACLE2_TEST_TLS_ROOT`, `ORACLE2_TEST_TLS_QUALIFICATION` (same), `ORACLE2_SYNTHETIC_POSTGRES_CONTAINER` (owned container id), `ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT` + `ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT_SHA256` (from `bootstrap_canonical_test_schema`), `COMPOSE_PROJECT_NAME=oracle2-synthetic-p24s07fresh-<UUID>` where **`<UUID>` is lowercase** `uuid4().hex` (the regex `oracle2-(?:ci\|synthetic)-[a-z0-9-]{1,80}` at `test_worker_postgres_fixture.py` allows lowercase only; the full name is ~65 chars and fits), `PYTHONDONTWRITEBYTECODE=1` (**n1:** the fixture **propagates** it via `env={**os.environ,...}` at `test_meeting_unattended_sql.py` `env=` construction — it does not set it; the runner export covers the runner and is inherited by children), `PYTHONHOME` (the interpreter prefix the fixture already sets for children). **There is no `ORACLE2_WORKER_CONTAINER_ID`** — that name has zero consumers repo-wide; do not invent it. `ORACLE2_INVENTED_PROVIDER_PORT`, `ORACLE2_MEETING_*_WORKER_BINDING_*`, `ORACLE2_INVENTED_DRIVER_PRELOAD`, `ORACLE2_INVENTED_READY_FILE`, `ORACLE2_INVENTED_QUEUE_DIAGNOSTIC`, `ORACLE2_INVENTED_CYCLE_DIAGNOSTIC`, `ORACLE2_INVENTED_OBSERVER_CONFIG_*` are set by the fixture itself; the runner does not set them. |
| Interpreter / toolchain pins (M-F) | Linux-only (`test_meeting_unattended_sql.py` reads `/proc/<pid>/stat`, `os.getuid()`; `conftest.py` has a Windows FileBlobStore workaround that is **not** sufficient for this test). Python = the venv/site-packages that already import `oracle_brain`, `psycopg`, `cryptography`, `pytest`. Node = `/usr/bin/node` (hardcoded in the test) with `tsx` importable via `--import tsx`. `openssl` CLI required (`certs` fixture runs `openssl req`/`x509`). Record `python -V`, `node -v`, `openssl version`, and `python -c 'import sys; print(sys.prefix, sys.path)'` in `runner-environment.json`. |
| `runner-environment.json` (n4) | Written by the runner to **`RUNNER_DIR/runner-environment.json`** (relative path `runner-environment.json`). On infra failure the runner writes **`RUNNER_DIR/infra-failed.json`** (relative path `infra-failed.json`) naming the failing step and the exact error, and both files are listed in `artifact-index.json`. |
| Resource plan | ONE fresh invented Create-child instance. Synthetic fixture universe only. Owned Compose project/containers/networks/volumes only (`dev/oracle2/compose.yaml`: `postgres:16.10-alpine@sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297`, `mem_limit: 1g`, `cpus: 1.0`, loopback `127.0.0.1:${ORACLE2_POSTGRES_PORT:-55432}:5432`; the worker fixture forces `ORACLE2_POSTGRES_PORT=0` for an ephemeral host port). TLS fixture: the test's own `certs` fixture generates an invented CA + leaf certs via `openssl` subprocess into `tmp_path/tls` (there are no "certificate issuer containers"). No company originals, no real meetings, no paid provider, no host OS changes. |
| Limits | Child wait remains `timeout=12` in the case (do not raise). Surrounding W10 120s / per-request ≤30 / ten workers is **not** this run. This run is one diagnostic-capture instance. |
| Cache hygiene (L-A, n2) | `pytest -p no:cacheprovider`. `PYTHONDONTWRITEBYTECODE=1` exported by the runner **and** inherited by children (the fixture propagates it via `env={**os.environ,...}`; the runner export is what supplies it). **One rule for tsx/node caches (n2):** if `node`/`tsx` writes a cache under the worktree, it **appears in source-after and fails the equality gate**; the runner does **not** pre-exclude it and does **not** hash-ignore it. The `stop_runtime` chmod (`apps/workers/src/services/oracle2-meeting-stop-process.ts` mode 0o600 → restore) must be restored on **every** exit path including SIGKILL; the kill path in §6 owns that restore. |
| Cleanup proof (L-B, M4) | **M4 correction.** Nine LOGIN roles are created by the fixture stack: three in `test_meeting_capture_sql.py` `meeting_sql` (`employee-control`, `provider-ingress`, `worker` channel roles; `CREATE ROLE ... LOGIN` with `meeting_`+`uuid4().hex[:16]` names) and six in `test_meeting_unattended_sql.py` `role()` (`scheduler`, `stop`, `observer`, `create`, `pre`, `post`; `CREATE ROLE ... LOGIN` with `unattended_`+`uuid4().hex[:12]` names). These roles are **cluster-wide** (`CREATE ROLE ... LOGIN` at both sites; `test_worker_postgres_fixture.py` module docstring: "isolate cluster-wide roles"; `owned_phase_database` drops only the database). They have **random uuid4-hex names** and no artifact records them. **Do NOT require `DROP ROLE` of unnamed roles.** The established cleanup is **whole-project** `docker compose -p <project> down --volumes` (exactly what `worker_postgres()`'s `finally` already does at `test_worker_postgres_fixture.py`); on a fresh owned cluster this destroys the roles with the container. Prove absence afterwards with all three empty: `docker ps -aq --filter label=com.docker.compose.project=<project>`, `docker network ls -q --filter label=com.docker.compose.project=<project>`, `docker volume ls -q --filter label=com.docker.compose.project=<project>`. If role-census proof is desired, state it **only** as an optional `pg_roles` prefix census (`rolname` LIKE `'meeting_%'` OR `'unattended_%'`) on the fresh cluster **before** teardown; otherwise prove cluster teardown alone. **Remove** the impossible "live only inside the dropped test database" disjunct — cluster-level roles survive a database drop. Also prove: no leftover child processes (`owned-process-cleanup.json` `remaining_pids: []`), unix sockets absent (`scheduler.sock`, `stop.sock`), scratch `short/` deleted (`private.cleanup()` assert), `.pytest_cache` absent. Workspace rows retained by design (`oracle2.meeting_capture_*` history inside the dropped DB) are called out as `dropped_with_database: true`, not hidden as "retained". Record `absence_proven: true` only when all of the above are true. |
| Failure retention | On any non-zero exit or timeout: artifacts already written by the `try/finally` and the artifact index; never retry under a weaker class; never delete the packet. |

## Competing hypotheses (M-C) — enumerate, do not lock in

Deadline ownership is the §3 four-row table; these hypotheses stay in scope only while those fields are captured:

1. Second `current_v1` in `beforeWrite` during `exchange_provider_v1` → protected service 503 (working hypothesis). Discriminators: server `raise_site` tag from the `execute_v1` / `settings.current()` wraps, `operation: current` on the jsonl entry that returned 503, ordering of jsonl vs child stage.
2. `_check` 30s bound / worker startup timing (`meeting_capture_worker_v1.py` `_check` raises `PermissionError('unchanged original worker deadline required')` when `(deadline-now).total_seconds()>30`). Discriminators: `original_deadline_v1` vs wall clock at each stage.
3. Peer pin / observer TLS failure. Discriminators: `actual-observer-refusals.json`, `warmup-refusals*.json`.
4. `settings.current()` / original-end / framing refusal (`_protected_control_listener_v1.py` raise sites: framing, peer pin, window expired, deadline elapsed, reply expired, bounded metadata). Discriminators: `raise_site` tag where a wrap seam exists; `wrap_trace` ordering where `raise_site` is UNKNOWN.
5. Nonce-sequence or `max_age_seconds=2` staleness on supervisor `current()` (`MeetingSupervisorAdmissionV2.minimum_sequence`/`max_age_seconds=2`). Discriminators: `replay-spool/` copy (`meeting-create-state.json` sequence) vs `MeetingSupervisorAdmissionV2` pin.

A run that only "passes" the post-hoc `observe_supervisor_process_v2` witness does not select among these.

## Decision rule (M-H)

| Outcome | Action |
|---|---|
| Fail + discriminating evidence names one hypothesis | Name the cause; author a permanent repair on a branch; keep negatives; then full W10. |
| Fail + packet is complete but predicates remain indistinguishable (including the H-E erasure case) | Record UNKNOWN naming the exact missing discriminator (or naming the production cause-erasure impossibility). Design the next fixture-only diagnostic. Do **not** retry this same instance. |
| `TimeoutExpired` on `actual.wait` (no stage/type beyond `wait`/`TimeoutExpired`) | This is a distinct row. Record UNKNOWN-cause-hung-child with the full packet (SIGKILL path, §6). Do not merge into "fail + evidence". Do not retry. |
| Infra failure before any child (bootstrap, compose up, node/openssl missing, schema receipt mismatch) | Record `infra_failed` in `RUNNER_DIR/infra-failed.json` with `RUNNER_DIR/runner-environment.json` and the exact error. This is **not** a diagnostic UNKNOWN and does not consume the one-fresh budget; fix the runner and re-gate. Do not call it a product failure. |
| Green, including green with warm-up refusals (`warmup-refusals-attempt-N.json` is a cumulative snapshot each attempt; `warmup-refusals.json` is the final cumulative list) | Not a repair. Record as "did not reproduce" **and** retain every `warmup-refusals-attempt-N.json` (never overwrite — write `warmup-refusals-attempt-N.json` per attempt N; **n8: each file is cumulative**, matching sealed source's full-list rewrite). Strengthen timing/load capture (§3) or, if the team chooses to accept the flake, the **owner of that acceptance is Albert Hazan** — an AI session may not silently accept it. Then require **two clean full W10 runs on the same HEAD** before treating Create-child as stable (L-E). Do not claim the 39760061151 cause is fixed. |
| Two W10 runs (L-E) | Both runs must execute at the **same** `git rev-parse HEAD`, same population (the W10 verifier's registered case list — do not cut to 5370 and do not follow a drifting main), same resource plan. Gate: 0 F/E/S and all ten workers under 120s. Release: only after both runs are green at that one head may Create-child be called stable for that head. Resource plan: owned Compose project per run, torn down between runs. |

## Success check

- **This packet's gate:** `artifact-index.json` complete (every §7 member present or explicitly `present:false` with reason); source-before equals source-after (content + mode bits, Exact inputs schema); owned resources absent (§ Cleanup proof); either exact cause named from a non-erased discriminator, or UNKNOWN with the missing predicate named (including naming the H-E erasure impossibility when it is the limit).
- **Program success (later):** exact cause found and permanently repaired while the same capabilities, strict framing, currentness, UNKNOWN and no-resend retain meaningful positives and negatives, and full W10 is clean with 0 F/E/S and all ten workers under 120s at one head (two clean same-head W10 runs, L-E). Create-child stability after a historical flake requires those two runs.

## Honest limits that cannot be true of this run

- This run cannot recover the inner exception of the working-hypothesis path; production erases it (H-E). `error_type` will be `RecallWireUncertaintyV1` there, with a fixed message and no cause. Non-erased `wire_byte_count` / `wire_sha256` may still discriminate other paths.
- Inline `do_POST` raise sites (framing, window expiry, deadline elapsed, reply expiry, bounded metadata) have no callable seam; their `raise_site` is UNKNOWN unless wrap-trace ordering narrows it (§1).
- A passing post-hoc supervisor witness does not exonerate the in-exchange `_fresh_supervision` branch (H4 from the prior revision, unchanged).
- A green run does not prove the 39760061151 cause is fixed; it only fails to reproduce.
- Fixture-only diagnostics cannot change production refusal shape, cannot add a guard, retry, or fallback, and cannot make the UNKNOWN state resend-authorized.
- The private `window.end` / `window.proxyMonoEnd` are not fixture-visible without production change; remaining-at-exchange is an elapsed-proxy plus a wall-remaining computed from `original_deadline_v1` (§3).

Posted by MiMo chat on edge-dev3. Parent #24. Business-acceptance hold remains in force.
