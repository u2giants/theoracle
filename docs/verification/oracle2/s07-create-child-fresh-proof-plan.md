# S07 Create-child fresh invented proof plan (runner packet)

Prepared only. No database, provider, native, or production effect is authorized by this file.
Root release after independent exact source + one resource-plan assessment is required before any run.

Revision note: this packet answers Muse plan-review `20261023T205451-611312-10659` findings H1–H7, M1–M6, L1–L3 on head `a693d210`. It supersedes the earlier pin/diagnostic claims that Muse rejected.

## Exact inputs (H1 — re-resolved at run time)

| Input | Value |
|---|---|
| Reviewed head for this packet | `a693d210c3555a565c0b753c5f175aa88ce931a8` |
| Historical pins (NOT run targets) | `e9531f98` (PR196 diagnostics), `81f9f6d9` (handoff PR #204) — recorded history only |
| Run-time head rule | At execution, `git rev-parse HEAD` must equal the exact head named in the review receipt. If main has moved, re-resolve and re-review; never follow a stale pin. |
| Source-before/after (H1, L2) | Before gate: `git ls-files -co --exclude-standard -z` hashed (mode bits via `git ls-files -s`) written to `source-before.json`. After: same command to `source-after.json`. Must match. Mode-bit residue from any chmod counts as a difference. |
| Diagnostic evidence note | `docs/verification/oracle2/s07-create-child-fixture-diagnostics.md` (line pins in that note are historical; trust sealed snapshot, not the note's line numbers — M6) |
| Failing historical run | 39760061151 (5370 cases, 1 failure) |
| Known child signal | exit 2, `stage:exchange`, `state:UNKNOWN`, protected channel refused `http-headers` then `closed-wire` |
| Working hypothesis | second `current_v1` inside `beforeWrite` during `exchange_provider_v1` gets 503 from protected service |

## What this run can and cannot discriminate (H2–H4)

Honest limits of the current PR196 diagnostic delta, restated so the run does not over-claim:

- **H2:** `error_type` is the exception constructor name only. In-exchange failures surface as generic `Error` because `protected-node-https.ts` erases the inner rejection and `protected-service-channel.ts.failure()` throws a fixed-message `Error`. Do **not** treat `error_type=="Error"` as cause identification.
- **H3:** `create-server-responses.jsonl` currently records status + header pairs only. The protected control listener answers the same `503` + `Content-Length: 0` + `Cache-Control: no-store` for every pre-`started` exception (dozens of raise sites: fence, framing, peer pin, `settings.current()`, original-end, metadata, worker `_check`, supervision, delivery, body hash). Status/headers alone cannot name the cause.
- **H4:** `observe_supervisor_process_v2` is a post-hoc unix-socket process-identity probe with a fresh challenge/deadline. It is not a reproduction of the in-exchange `_fresh_supervision` → supervisor `current()` path (observer mTLS + durable nonce sequence + `max_age_seconds=2`). A passing witness does not exonerate that branch; a failing one does not convict it.

Therefore the first fresh instance is a **diagnostic-capture run**. Success at this stage is a complete artifact packet that either (a) names the exact cause from new discriminating evidence, or (b) records remaining UNKNOWN with the exact missing predicate named. A green instance is handled in the decision rule below.

## Required diagnostic upgrades before the one fresh instance (H2, H3, H5, H6, L1, M1, M4)

These are fixture-only / test-only source changes. No guard, no retry, no fallback, no production public error leak.

1. **Server-side raise-site tag (H3, M1).** Extend the create-server handler capture to record, per request: monotonic timestamp, operation name (prepare/claim/current/observe/repeated-claim), a fixture-only `raise_site` or exception-class tag if available without weakening production refusal shape, and the request sequence index. Keep production response bytes identical (still `503`/empty/no-store). If a raise-site tag cannot be added without touching production refusal, record `raise_site: UNKNOWN` and say so — do not invent one.
2. **Error chain capture (H2).** In the driver catch, record `error_type`, `error_message` (redacted), and if present `error_cause_type` / nested name. Still do not infer cause from `"Error"` alone.
3. **Always-on diagnostics (H5).** Wrap child wait and all early asserts in `try/finally` so `create-child-diagnostics.json`, the jsonl, stderr, and provider-routes are written even on timeout, pre-child failure, or assertion abort. Hung child is the highest-value case and must not skip capture.
4. **Richer claim-time state (H6).** The claim query must select claim_id/state/created_at **plus** receipts count, latest event, head state, admission state, original deadline, and supervision scope if present. Preserve the replay spool (`short/'replay'`) into `tmp_path` before scratch deletion — it holds the nonce-sequence state for one hypothesis.
5. **Locked jsonl append (L1).** Serialize diagnostic jsonl writes (threading lock or queue) so concurrent handler threads cannot interleave lines.
6. **Artifact index (M4).** `create-child-diagnostics.json` must list every packet member: diagnostics.json, create-server-responses.jsonl, child stderr, provider routes, observer refusals, outcome json, source-before/after, replay-spool copy. "Read the diagnostics" means read this index first.

## Constraints (unchanged)

- Do not suppress strict framing/currentness
- Do not refresh the original window
- Do not resend an uncertain claim
- Keep UNKNOWN/no-resend semantics
- Keep all meaningful positives and negatives
- No production public error leak
- No guard change, no retry, no fallback

## Gate before one fresh invented instance

1. Independent exact SOURCE assessment of the diagnostic delta (PR196 bytes **plus** the upgrades above) + this plan
2. Independent ONE resource-plan assessment (fresh PG + owned graph, canonical once, owned phase)
3. True database gate with a review receipt binding the exact run-time HEAD
4. Root one-fresh release decision
5. Execute one fresh invented instance under original limits (runner packet below)
6. Read the artifact index, then the packets it names. Either name the exact cause from discriminating evidence, or record remaining UNKNOWN naming the exact missing predicate
7. Only then author a permanent fix; a rerun with no cause is not a repair

## Concrete runner packet (H7, M3, L3)

| Item | Value |
|---|---|
| Exact selector | `pytest services/oracle-brain/tests/test_meeting_unattended_sql.py::test_meeting_unattended_create_child_actual -q --tb=short` (parametrization `capture_seconds` stays at the case's existing value; do not cut cases) |
| Environment | `ORACLE2_TEST_ADMIN_URL` (fresh owned DB), `ORACLE2_SYNTHETIC_POSTGRES_CONTAINER`, `ORACLE2_WORKER_CONTAINER_ID`, `COMPOSE_PROJECT_NAME=oracle2-synthetic-p24s07fresh-<UUID>`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH` = brain package + tests + repo root |
| Resource plan | ONE fresh invented Create-child instance. Synthetic fixture universe only. Owned Compose project/containers/networks/volumes only. Pinned PostgreSQL 16.10, 1GiB/1CPU, loopback ephemeral port. TLS fixture: labelled disposable networkless/read-only certificate issuer containers only. No company originals, no real meetings, no paid provider, no host OS changes. |
| Limits | Child wait remains `timeout=12` in the case (do not raise). Surrounding W10 120s / per-request ≤30 / ten workers is **not** this run. This run is one diagnostic-capture instance. |
| Cleanup proof | After run: `docker ps -aq --filter label=com.docker.compose.project=<project>`, same for networks and volumes; all empty. Drop the six LOGIN roles the fixture created (or prove they are inside the dropped test DB and gone with it). Record `absence_proven: true` only when all of the above are true. Workspace rows retained by design are called out, not hidden. |
| Failure retention | On any non-zero exit or timeout: artifacts already written by the `try/finally`; never retry under a weaker class; never delete the packet. |

## Competing hypotheses (M3) — enumerate, do not lock in

Capture deadline/window values (`original_deadline_v1`, caller deadline, remaining time at exchange) so these stay in scope:

1. Second `current_v1` in `beforeWrite` during `exchange_provider_v1` → protected service 503 (working hypothesis)
2. `_check` 30s bound / worker startup timing
3. Peer pin / observer TLS failure
4. `settings.current()` / original-end / framing refusal
5. Nonce-sequence or `max_age_seconds=2` staleness on supervisor `current()`

A run that only "passes" the post-hoc witness does not select among these.

## Decision rule (M2)

| Outcome | Action |
|---|---|
| Fail + discriminating evidence names one hypothesis | Name the cause; author a permanent repair on a branch; keep negatives; then full W10. |
| Fail + packet is complete but predicates remain indistinguishable | Record UNKNOWN naming the exact missing discriminator. Design the next fixture-only diagnostic. Do **not** retry this same instance. |
| Green (including a single green rerun) | Not a repair. Record as "did not reproduce." Strengthen timing/load capture (M3) or accept the flake with UNKNOWN cause on the historical failure. Then require **two** clean full W10 runs on current main before treating Create-child as stable. Do not claim the 39760061151 cause is fixed. |

## Success check

- **This packet's gate:** artifact index complete; source-before equals source-after (including mode bits); owned resources absent; either exact cause named or UNKNOWN with the missing predicate named.
- **Program success (later):** exact cause found and permanently repaired while the same capabilities, strict framing, currentness, UNKNOWN and no-resend retain meaningful positives and negatives, and full current-main W10 is clean with 0 F/E/S and all ten workers under 120s (population = whatever current main registers; do not cut to 5370). Create-child stability after a historical flake requires two clean full W10 runs (L3).

Posted by MiMo chat on edge-dev. Parent #24. Business-acceptance hold remains in force.
