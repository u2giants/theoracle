# S07 Create-child fixture-only diagnostic metadata

**Date**: 2026-10-22
**Branch**: `codex/parent24-s07-create-diag`
**Base**: `bf788080` (origin/main)

## Exact cause hypothesis with evidence lines

The S07 actual Create child fails at `stage:exchange` with exit 2. Child stdout:
`{"state":"UNKNOWN","remote_stop_proven":false,"stage":"exchange"}`.
Stderr: `"Oracle protected channel refused http-headers"` then
`"Oracle protected channel refused closed-wire"`.

**Evidence chain** (file:line on base):

1. `services/oracle-brain/tests/fixtures/meeting-unattended-driver.mts:35`
   — the driver's `stage` variable is `'exchange'` when the exception fires,
   meaning `prepare_v1`, `claim_v1`, and the first `current_v1` all succeeded.
2. `packages/shared/src/protected-meeting-worker.ts:91-101`
   — `exchange_provider_v1` calls `this.provider.exchange(operation, window,
   beforeWrite)` where `beforeWrite` is
   `async()=>{await this.current_v1(claim);this.check();}`.
3. `packages/shared/src/protected-node-https.ts:80-101`
   — inside `provider.exchange`, after TLS `secureConnect`, the code runs
   `await this.within(beforeWrite(), window)` before sending HTTP bytes.
   This is the "after provider TLS, before provider HTTP bytes" point.
4. `beforeWrite` calls `current_v1` → `control('current')` →
   `openProtectedChannelV1` (`packages/shared/src/protected-service-channel.ts:33`).
5. `packages/shared/src/protected-service-channel.ts:90` — the `http-headers`
   refusal fires when `statusCode !== 200` or content-type/connection headers
   fail the strict check. Line 88 then fires `closed-wire` on socket close.
6. The protected SERVICE response is produced by
   `services/oracle-brain/oracle_brain/hosting/_protected_control_listener_v1.py`.
   On any exception before `started = True`, `_deny()` sends HTTP 503 with
   `Content-Length: 0` and no `Connection: close` header (lines 52-59).
   The TS client's check at line 90 rejects `statusCode !== 200`.
7. The second `current_v1` (inside `beforeWrite`) calls
   `CaptureWorkerFactoryV1.current_v1` (`meeting_capture_worker_v1.py:127-133`)
   which calls `_fresh_supervision()` → `_unattended_supervisor.current()`.
   This contacts the supervisor observer. If the supervisor witness, nonce
   sequence, or observer TLS fails, the server returns 503 and the TS client
   refuses at `http-headers`.

**Root cause status**: The exact private predicate that causes the server to
return 503 on the second `current` remains UNKNOWN. The first `current_v1`
(at driver stage `'current'`) succeeds, so the server can serve the operation.
The failure is specific to the call inside `beforeWrite` during exchange.

## What diagnostics were added

### 1. Driver exception type (`meeting-unattended-driver.mts:36`)

The catch block now writes `error_type` (exception constructor name) alongside
the existing `state`/`remote_stop_proven`/`stage`. This is nonsecret — just the
class name (e.g. `"Error"`, `"PermissionError"` equivalent).

### 2. Server response status/header log (`test_meeting_unattended_sql.py`)

The create worker server's `RequestHandlerClass` is wrapped to log every
response's status code and header key/value pairs to
`create-server-responses.jsonl` (fixture-only, no production code change).
When the test runs and the child fails, this file shows exactly what status
and headers the protected SERVICE sent.

### 3. Supervisor witness + claim-time diagnostics (`test_meeting_unattended_sql.py`)

Before the assertion, the test captures:
- `supervisor_witness`: per-profile `observe_supervisor_process_v2` result
  (ok/error_type)
- `claim_time`: database rows from `meeting_capture_worker_claims_v1`
  (claim_id, state, created_at)
- `stage` and `error_type` from the child's stdout
- The server response log (copied to tmp_path)

All written to `create-child-diagnostics.json` in tmp_path.

## What was deliberately NOT changed

- No production code (packages/shared/src/**) modified.
- No guard suppression: strict framing/currentness checks untouched.
- No window refresh, no resend, no retry, no fallback.
- UNKNOWN/no-resend semantics preserved (driver still writes
  `state:'UNKNOWN', remote_stop_proven:false` on catch).
- All existing meaningful positives and negatives retained (assertions at
  lines 299+, 363, etc. unchanged in behavior).
- No production public error leak: only nonsecret fields (status, header
  names/values, exception class name, claim IDs/timestamps) are logged.

## Test results

| Test | Result |
|---|---|
| `test_contract_parity.py` | 3 passed |
| `test_meeting_request_fence.py` | 5 passed, 5 pre-existing failures (assertion mismatch on `'two-second connection bound'` vs `'protected SQL cannot consume PG environment defaults'` — unrelated to this change) |
| Python syntax check of `test_meeting_unattended_driver.mts` | pass (loads, fails at expected `invented provider absent`) |
| Python syntax check of `test_meeting_unattended_sql.py` | pass |
| Full SQL/actual tests | Not run (require Linux, PostgreSQL, OpenSSL — not available in this environment) |

## Remaining gate

Fresh invented proof after independent source+resource review and root release.
The diagnostics added here will capture the exact status/headers/exception on
the next actual run, enabling a precise root-cause fix. This commit is source
preservation only — not acceptance.
