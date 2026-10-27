# S07 Create-child fixture-only diagnostic metadata

**Date**: 2026-10-25 (upgraded per plan v5 §1–§8 and Muse APPROVE
`20261025T132905-2852654-12398` build-instruction hardening; REJECT
`20261025T140952-2951761-15922` leftovers fixed in this revision)
**Branch**: `codex/parent24-s07-diag-upgrades`
**Base**: `4e365535f294c28a804827bd9293885bd09b9e6c` (origin/main at branch creation)

Line pins below refer to the post-upgrade source in this branch. The sealed
snapshot at run time is authoritative; these pins are orientation only.

## Exact cause hypothesis with evidence chain (unchanged)

The S07 actual Create child fails at `stage:exchange` with exit 2. Child stdout:
`{"state":"UNKNOWN","remote_stop_proven":false,"stage":"exchange"}`.
Stderr: `"Oracle protected channel refused http-headers"` then
`"Oracle protected channel refused closed-wire"`.

**Evidence chain** (file:line on base):

1. `services/oracle-brain/tests/fixtures/meeting-unattended-driver.mts` —
   the driver's `stage` variable is `'exchange'` when the exception fires,
   meaning `prepare_v1`, `claim_v1`, and the first `current_v1` all succeeded.
2. `packages/shared/src/protected-meeting-worker.ts:91-101` —
   `exchange_provider_v1` calls `this.provider.exchange(operation, window,
   beforeWrite)` where `beforeWrite` is
   `async()=>{await this.current_v1(claim);this.check();}`.
3. `packages/shared/src/protected-node-https.ts:80-101` —
   inside `provider.exchange`, after TLS `secureConnect`, the code runs
   `await this.within(beforeWrite(), window)` before sending HTTP bytes.
4. `beforeWrite` calls `current_v1` → `control('current')` →
   `openProtectedChannelV1` (`packages/shared/src/protected-service-channel.ts:33`).
5. `packages/shared/src/protected-service-channel.ts:90` — the `http-headers`
   refusal fires when `statusCode !== 200` or content-type/connection headers
   fail the strict check. Line 88 then fires `closed-wire` on socket close.
6. The protected SERVICE response is produced by
   `services/oracle-brain/oracle_brain/hosting/_protected_control_listener_v1.py`.
   On any exception before `started = True`, `_deny()` sends HTTP 503 with
   `Content-Length: 0` and `Cache-Control: no-store` (still unchanged).
7. The second `current_v1` (inside `beforeWrite`) calls
   `CaptureWorkerFactoryV1.current_v1` which calls `_fresh_supervision()` →
   `_unattended_supervisor.current()`.

**Root cause status**: The exact private predicate that causes the server to
return 503 on the second `current` remains UNKNOWN. Production erases the inner
rejection (H-E); see honest limits.

## What diagnostics exist after this upgrade

### 1. Server-side raise-site tag (§1)

Fixture-only wraps (no production file is edited):

| Wrap | Target | Notes |
|---|---|---|
| `execute_v1` | `_CaptureWorkerAdapter.execute_v1` | PRIMARY. Records `operation` from POST body JSON `operation` field (wire ops: `prepare`/`claim`/`current`/`observe`/`status` — there is **no** `repeated-claim` wire operation; that is a test phase name only), `caller_deadline`, every exception that propagates to `_deny`. |
| `settings.current` | `_CaptureWorkerSettings.current` | Records which `current()` call refused (entry/exit) and the `PermissionError`. |
| `_parse` | `meeting_worker_service_v1._parse` | Covers `parse_request` at listener body-read **and** the same `_parse` inside `execute_v1`. **Double-parse correlation note:** each request parses twice through this same wrapped `_parse`, so `wrap_trace` holds **paired entries per request** (one for `parse_request`, one for `execute_v1`). Pair them by `request_id`; the earlier pair member is the `parse_request` call site. |
| `peer_der_v1` | listener module binding | Called twice in `do_POST` (before body read, and after `factory.execute_v1`). |
| `fixed_request_length_v1` | listener module binding | Framing. |
| `read_request_body_v1` | listener module binding | Body read. |
| `_request_fence_v1` | listener module binding (import at `_protected_control_listener_v1.py` **line 12**, not 11) | Context-manager wrap: re-yields and re-raises; records fence entry refusal and exit around `execute_v1`. |

Every recording wrap re-raises / returns-through unchanged. Production response
bytes are unchanged (still `503` / empty body / `Cache-Control: no-store`).

**Wrap installation timing (Muse):** after `start_unattended()` returns, before
the first `worker_request` — this covers the refused-`prepare` warmup requests
and does **not** record config-load `_parse` calls. `install_wraps(server)`
also owns the create-server `RequestHandlerClass` response-logging monkeypatch
and restores it (plus every module wrap) on uninstall and on partial install
failure, so a full-file two-node run cannot double-wrap. `execute_v1` records
`ok`/`exit` **after** the wrapped call (same as its siblings).

Per-request record (locked jsonl, §8): `kind`, `request_id` (the request
sequence), `operation`, `caller_deadline`, `raise_site`, `outcome`,
`wrap_trace`. There is **no** top-level `seq` on the request record; `seq`
appears on each `wrap_trace` entry and on `response` records.
Each `wrap_trace` entry has `wrap`, `event` (`enter`/`exit`/`error`), `seq`,
`mono` (`time.monotonic()`), and on error `error_type` + `raise_site`.
`raise_site` = `type(error).__name__` + the raise-site frame code name when
available, else `UNKNOWN`. `outcome` is `ok` / `error` from the wraps, or
`response` / `refused` from `_logged_end_headers` (non-200, e.g. the inline
503 path, flushes as `refused`). `_WRAP.flush` on a thread that never began a
wrap returns `None` (no AttributeError).

**Sites that remain UNKNOWN (exact reason).** These are inline `raise
PermissionError(...)` statements inside `do_POST` itself with no callable seam.
A delegating `do_POST` wrap cannot see them (bare `except Exception` swallows
and calls `_deny()`). The ordered `wrap_trace` narrows the window but does not
uniquely identify which inline raise fired. `raise_site: "UNKNOWN"` for:

- framing: `self.server.closing or self.headers.get_all('Content-Encoding', []) != []`
- window expiry: `not datetime.now(timezone.utc) < request.caller_deadline <= min(...)`
- deadline elapsed: `self.server.closing or time.monotonic() >= original_end`
- reply expiry (inside `_request_fence_v1`, after `factory.execute_v1`)
- bounded metadata: `type(encoded) is not bytes or not 0<len(encoded)<=maximum_response_bytes`

### 2. Error chain capture (§2)

Driver catch records: `error_type`, `error_message` (allow-listed fixed
production refusal strings only, else `"REDACTED"`), `error_cause_type` if
present (bare class name only), plus `wire_byte_count` and `wire_sha256` when
`error instanceof RecallWireUncertaintyV1` (non-erased metadata; raw wire bytes
are **never** written). Do not infer cause from `"Error"` or
`"RecallWireUncertaintyV1"` alone — production erases the inner rejection.

### 3. Deadline capture owners (§3) — four rows

| Deadline | Owner field |
|---|---|
| Driver `original_deadline_v1` | `deadline` on **both** success and failure stdout |
| Request-body `caller_deadline` | `caller_deadline` in the `execute_v1` wrap record |
| Remaining-at-exchange (elapsed-proxy) | `exchange_elapsed_wall_ms` (integer `Date.now()` delta), `exchange_elapsed_mono_ms` (`Number(end-start)/1e6` — bigint/number division throws, so the plan's bare `/1e6` is corrected here), `wall_remaining_at_exchange_ms` / `wall_remaining_at_catch_ms` computed from `original_deadline_v1` |
| SQL `claim_original_deadline` | `claim_time[].original_deadline` from `meeting_capture_worker_claims_v1` |

Private `window.end` / `window.proxyMonoEnd` are not fixture-visible.

### 4. Richer claim-time state (§4)

`create-child-diagnostics.json` now selects **existing** claim columns:
`claim_id`, `original_deadline`, `created_at`, `effect`, `stage` (plus
recommended `operation_id`, `request_sha256`, `bot_id`, `worker_id`).
**Do not select `state` — it does not exist** on
`oracle2.meeting_capture_worker_claims_v1`.
Receipts: two SELECTs (count + per-row) or `json_agg` equivalent, over
`meeting_capture_worker_receipts_v1` JOIN `meeting_capture_worker_claims_v1`.
Also recorded: latest event (`action`, `payload`, `created_at`), head state
(`state`, `capture_open`, `stop_state`), admission rows
(`admission_id`, `admission_sha256`, `role_name`, `actions`, `capture_until`,
`stop_until`, `original_horizon`, `expires_at`).

Each of the five query groups has its own try/except + `rollback()`
(`claim_time`, `receipts`, `latest_event`, `head_state`, `admission_state`),
so one bad expression cannot leave the shared connection in a failed
transaction or wipe the other four; per-group failures land as
`<group>_error`. If `admin()` itself fails, all five groups are recorded as
failed (`<group>_error`), never silently absent.

Supervision scope: `scope.model_dump(mode='json')` pinned to
`tmp_path/supervision-scope.json` before teardown deletes scratch.
Replay spool: copied to `tmp_path/replay-spool/` before `private.cleanup()`,
with `replay-spool-manifest.json` (nonce-sequence state and appointment hashes
only; no secrets).

### 5. Redaction rule (§5)

One function `redact_record(record) -> dict` in
`services/oracle-brain/tests/meeting_unattended_redact.py` (imported by the
test module). Walks every value; anything not matched by the allow-list
becomes `"REDACTED"` and the parallel key `"<field>_kind": "unlisted"` is
set. A list field sets `"<field>_kind": "unlisted"` when **any** member is
redacted. Tuples (fetchall/fetchone rows) are walked like lists and become
lists so `actual-selected-state.json` and the outcome `head` survive. A dict
returns flagged=True when any leaf under it was redacted, so a list of dicts
gets its parent marker too. Applied to **every** jsonl append and **every**
JSON artifact write (via `_write_json_artifact`).
Postgres `timestamptz::text` values (space separator, short zone — e.g.
`2026-10-25 14:09:52.123456+00`) are accepted alongside the ISO-T form so
`claim_original_deadline` / `created_at` / `capture_until` evidence is kept.
Supervisor purpose strings (`meeting-scheduler-process-v1`,
`meeting-stop-worker-process-v1` and siblings) and provider request lines
(`POST /api/v1/bot/ HTTP/1.1`) are allow-listed. Raise sites with non-ident
code names (`PermissionError:<lambda>`) keep the error type.

Allow-list keeps the packet's fixed hyphenated tokens (Muse M1 fix), mirrored
on the `_EFFECT_NAMES` pattern:

- pre-child step names: `install-wraps`, `queue-diagnostic`, `cycle-diagnostic`,
  `warmup-queue-reads`, `refused-prepare-warmup`, `sql-zero-asserts`,
  `child-spawn-ready`, `warmup-observations`, `child-wait`, `stdout-redact`,
  `collect-diagnostics`, `returncode-assert`, `outcome-parse`, `repeated-claim`,
  `post-create-current-queue`, `terminal-loop`, `terminal-asserts`,
  `unattended-outcome` (plus `start_unattended`, a bare ident)
- teardown step names (§7): `supervision-scope`, `replay-spool-copy`,
  `selected-state`, `provider-routes`, `observer-files`, `stack-close`,
  `jsonl-close-then-copy`, `owned-process-cleanup`, `private-cleanup`
- claim/receipt stages (`020_meeting_capture.sql:664`): `-`,
  `pre-stop-consistency`, `post-stop-terminal`
- observation kinds (`020_meeting_capture.sql:806`): `create-observed`,
  `leave-observed`, `metadata-observed`
- header keywords the wrap logs: `Content-Length`, `Cache-Control`,
  `Connection`, `Content-Type`, `Server`, `Date`, plus fixed values
  `no-store`, `close`, `application/json`, digit strings (Content-Length),
  HTTP-date and `BaseHTTP/x Python/x.y.z` (Server)
- the literal `-` stage placeholder

Deny rules for paths/hosts/secrets are unchanged (`_PATHY_RE`, free-form
strings, bytes). Offline unit tests in
`services/oracle-brain/tests/test_meeting_unattended_redact.py` cover the
allow-list and the deny rule.

Exhaustive writer list for this packet: `create-child-diagnostics.json`,
`supervision-scope.json`, `replay-spool-manifest.json`, deadline snapshot
fields inside `create-child-diagnostics.json`, `warmup-refusals*.json` message
fields, `post-create-current-queue-refusal.json`, `pre-child-failure.json`,
`actual-create-child.stdout`, `teardown-steps.json`,
`*-actual-queue.json`, `post-create-current-queue.json`,
`actual-selected-state.json`, `actual-provider-routes.json`,
`owned-process-cleanup.json`, `actual-unattended-outcome.json`,
`actual-observer-refusals.json`, `actual-observer-process-observations.json`,
and every `create-server-responses.jsonl` append (kind `request` / `response`).
Raw streams `actual-create-child.stderr`, `queue-diagnostic.*`,
`cycle-diagnostic.*` are captured as-is and are **not** re-parsed or
redacted; they sit outside the JSON allow-list contract (the previous
"free-form text stops the run" claim is dropped — node diagnostics routinely
contain paths and the packet needs them).

**Node-written stdout owners (M11).** The child writes
`tmp_path/actual-create-child.stdout` directly via `child()`. Two owners:
1. **Driver-side allow-list (primary):** only enumerated keys are emitted
   (`state`, `remote_stop_proven`, `stage`, `error_type`, `error_message`,
   `error_cause_type`, `wire_byte_count`, `wire_sha256`, `deadline`, and the
   success keys already present plus the §3 elapsed-proxy fields). Before the
   catch write, `error_message` is replaced with `"REDACTED"` unless it is
   exactly one of the allow-listed fixed production refusal strings;
   `error_cause_type` is written only when it is a bare class name.
2. **Fixture post-pass (enforcement):** **after** `actual.wait(timeout=12)` (or
   the SIGKILL path) the fixture reads the stdout file, parses the JSON line,
   runs `redact_record`, and rewrites it (`_redact_child_stdout`). This is a
   post-wait read/redact/rewrite — there is no staging-file copy step and no
   early/racing copy that could destroy the only stdout evidence. A line that
   does not parse is written as
   `{"state":"UNKNOWN","stage":"UNKNOWN","error_type":"UnparsedStdout","raw_kind":"unlisted"}`
   (`stage` is `"UNKNOWN"`, never an unbound template key); the raw bytes are
   not kept.

### 6. Always-on diagnostics and try/finally scope (§6)

Named try/finally covers from `start_unattended()` through the early asserts.
Pre-child steps (each named in `pre-child-failure.json` on failure):
`start_unattended`, `install-wraps`, `queue-diagnostic`, `cycle-diagnostic`,
`warmup-queue-reads`, `refused-prepare-warmup`, `sql-zero-asserts`,
`child-spawn-ready`, **`warmup-observations`** (the warmup loop is inside the
named try/finally — Muse m5), `child-wait`, `stdout-redact`,
`collect-diagnostics`, `returncode-assert`, `outcome-parse`, `repeated-claim`,
`post-create-current-queue`, `terminal-loop`, `terminal-asserts`,
`unattended-outcome`.
Child wait stays `timeout=12`. On `TimeoutExpired`: record
`stage:"wait"`, `error_type:"TimeoutExpired"`, SIGKILL
(`os.kill(actual.pid, signal.SIGKILL)` then `actual.wait(timeout=5)`), and
restore the `stop_runtime` chmod; diagnostics are still collected before the
assert (`UNKNOWN-cause-hung-child`).
Teardown uses nested try/finally per step so a raise cannot eat evidence;
order is §7 write order (spool copy before close; jsonl close-then-copy after
`stack.close()`; then `owned-process-cleanup.json`; then `private.cleanup()`).

### 7. Artifact index written by the RUNNER after pytest (§7)

Design (a): the **runner** writes `artifact-index.json` after pytest exits,
covering all fixture-written members plus `source-after.json`,
`source-before.json`, and `runner-environment.json`. The fixture still writes
the members. Runner script:
`scripts/oracle2/s07_create_child_fresh_runner.py` (fail-closed; writes
`infra-failed.json` on infra failure and does not consume the one-fresh budget).

Relative-path root is the runner-owned packet directory `RUNNER_DIR`. Fixture
members land under `RUNNER_DIR/pytest-tmp/<pytest-generated-subdir>/` because
pytest is invoked with `--basetemp=RUNNER_DIR/pytest-tmp`; the runner
**enumerates** pytest-generated subdirs and does **not** assume testid names.

Each index member is
`{"path","sha256","mode","present","note"}` with `members` sorted by `path`.
`warmup-refusals-attempt-N.json` are **cumulative snapshots** (attempt N
contains every refusal observed through attempt N), not deltas; the final
`warmup-refusals.json` equals the last attempt file and is written on **both**
the clean first-try success path and the refusal path. Attempt files carry
note `cumulative snapshot` in the index.

Exact selector (M6 / Muse Low): **`sys.executable -m pytest`** with
`--basetemp=RUNNER_DIR/pytest-tmp` and `-p no:cacheprovider` in the same
invocation — never bare `pytest`. cwd = worktree root;
`PYTHONPATH="<WORKTREE_ROOT>:<WORKTREE_ROOT>/services/oracle-brain"`;
`PYTHONDONTWRITEBYTECODE=1`. **`PYTHONHOME` is not exported** to the venv
pytest invocation (it can skew stdlib/site resolution). All pins are recorded
in `runner-environment.json`.

The pytest subprocess is bounded by `PYTEST_TIMEOUT_SECONDS=600` and its
stdout/stderr are captured into `pytest-output.stdout` /
`pytest-output.stderr` (index members) with the returncode recorded in
`pytest-returncode.json`. Path tokens in that captured output are redacted
(`redact_text`) before the files are written. The recorded
`pytest_invocation` is the full command including the selector and the
`--basetemp` / `-p no:cacheprovider` pins. `PYTHONHOME` is explicitly
popped from the child env (never inherited) so `pythonhome_exported: False`
is guaranteed. The runner pins HEAD first: it refuses a dirty
worktree and an `EXPECTED_HEAD` mismatch (optional 4th argument) before the
one-fresh budget is consumed. `infra-failed.json` error strings go through
`redact_record`.

### 8. Locked jsonl append + reader (§8)

One module-level `threading.Lock` (`_JSONL_LOCK`) guards every jsonl append
**and** the per-request sequence counter. Handler threads share it. The reader
is close-then-copy in fixture teardown (after `stack.close()`), not an interim
read while the server still serves. There is no `partial_tail_lines`
mechanism; the only reader is close-then-copy.

## What was deliberately NOT changed

- No production code (`packages/shared/src/**`,
  `oracle_brain/hosting/_protected_control_listener_v1.py`) modified.
- No guard suppression: strict framing/currentness checks untouched.
- No window refresh, no resend, no retry, no fallback.
- UNKNOWN/no-resend semantics preserved (driver still writes
  `state:'UNKNOWN', remote_stop_proven:false` on catch).
- All existing meaningful positives and negatives retained. In particular the
  post-create current-queue read **records and continues** on refusal
  (`post-create-current-queue-refusal.json`) — the base diagnostic behavior —
  so a queue-read refusal is not a new failure mode.
- No production public error leak: only allow-listed nonsecret fields.
- Production response bytes identical (503 / empty body / no-store).

## Offline test results (Windows, this branch)

| Check | Result |
|---|---|
| `python -m py_compile` of `test_meeting_unattended_sql.py` | pass |
| `python -m py_compile` of `meeting_unattended_redact.py` | pass |
| `python -m py_compile` of `test_meeting_unattended_redact.py` | pass |
| `python -m py_compile` of `scripts/oracle2/s07_create_child_fresh_runner.py` | pass |
| `python -m pytest services/oracle-brain/tests/test_meeting_unattended_redact.py` (31 offline unit tests: hyphenated tokens, Postgres timestamptz text, tuples/rows, purpose strings, provider routes, dict-member markers, lambda raise sites, spool manifest, path-text redaction) | pass |
| Full SQL/actual tests | **Not run** (require Linux, PostgreSQL, OpenSSL, Docker — `edge-dev3` is the run host) |

## Remaining gate / UNKNOWN

Fresh invented proof after independent source+resource review and root release
(plan v5 gate). By-design UNKNOWNs that cannot be true of the run:

- Inner exception of the working-hypothesis path is erased by production
  (`RecallWireUncertaintyV1` fixed message, no cause). `wire_byte_count` /
  `wire_sha256` may still discriminate other paths.
- Inline `do_POST` raise sites (framing, window expiry, deadline elapsed,
  reply expiry, bounded metadata) have `raise_site: "UNKNOWN"` unless
  wrap-trace ordering narrows the window.
- A green run does not prove the 39760061151 cause is fixed; it only fails to
  reproduce. Two clean same-head full W10 runs are required before Create-child
  is called stable (L-E).

**Plan-text leftovers not edited here** (plan lives on
`codex/parent24-s07-plan-muse-h1h7`; this branch does not touch that branch):
historical reviewed heads row should also list v4 head
`8cbf4487b02674521facc5016760552e51b5c746`; the plan's bold selector text
still shows `python -m pytest` without `--basetemp`/`-p no:cacheprovider`
(corrected in the runner and this note); the plan's `--basetemp` layout
schematic `pytest-tmp/<testid>/<file>` is replaced by enumerate-don't-assume
in the runner.
