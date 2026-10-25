# S08 participation one-shot journey proof plan (sealed)

Recorded: 2026-10-25 EDT. Branch `parent24-s08-compose-81742134`, PR #200.
Status: **PLAN + SEALED RUNNER + CHECKER ONLY.** No journey execution, no
database, no provider, no browser acceptance in this seal.

This document replaces the edge-dev3 `/tmp` journey brief. The prior brief
claimed a Next browser enable/control web surface and a fake-Recall HTTPS owner;
both claims are withdrawn. What follows is bound only to artifacts that exist in
this branch.

## Sealed artifacts (this commit)

| Path | Role |
|---|---|
| `docs/verification/oracle2/s08-journey-proof-plan.md` | this plan |
| `scripts/oracle2/run_s08_journey_proof_v1.py` | one-shot journey runner (fail-closed; refuses without review receipt + database gate) |
| `scripts/oracle2/check_s08_journey_skeleton_v1.py` | offline skeleton checker (no DB, no effects) |
| `docs/verification/oracle2/s08-compose-81742134-evidence.md` | composition evidence note (byte-identity wording corrected) |

Backend source of truth this journey binds (already sealed on the head):

- `services/oracle-brain/tests/test_meeting_participation_sql.py`
- `services/oracle-brain/oracle_brain/meetings/participation_authority_v1.py`
- `services/oracle-brain/oracle_brain/hosting/meeting_participation_v1.py`
- `services/oracle-brain/oracle_brain/hosting/meeting_participation_service_v1.py`
- `dev/oracle2/test_worker_postgres_fixture.py`
- `dev/oracle2/test_canonical_schema.py`
- `scripts/oracle2/verify_workflow_integrity.py`
- `scripts/oracle2/verify_phase.py`
- `apps/workers/src/lib/recall.ts`
- `apps/workers/src/lib/meeting-participation.ts`

## Exact journey stages the eventual one-shot must prove (invented data only)

The journey is **provision-capture-admission → observe-audience →
host-control → current-turn → sender → bytes-in receipt → status/reconcile**.
There is no Next browser stage in this one-shot. Stage signatures on the sealed
runner already carry the bindings named below (H-D), so filling in the stage
bodies does not churn the receipt-bound runner SHA.

### Stage 0a — capture / admission provisioning (precondition)

Cites the SQL fixture construction at
`test_meeting_participation_sql.py:69-125`: appointments, capture admissions,
roles/grants, **invite → retain_ingress → finalize**, and the host/sender/
observer participation admissions (`meeting_participation_admissions_v1`).
Whoever runs the journey must mint these first. Without stage 0a there is no
admission linkage for any later stage. This is a real stage, not an implicit
fixture assumption.

### Stage 0b — observer / audience observation (precondition for enable)

`observe_audience_v1` / `invent_observation` pattern from
`test_meeting_participation_sql.py:128-136`. Enabling the host requires an
`observation_id` (`participation_authority_v1.py:458`); the factory derives it
from current SQL status (`meeting_participation_v1.py:201-202`), which only
exists after this observation. Observation expiry ≤30s
(`021_meeting_participation.sql:259`). Stage 1 enable is unsatisfiable without
stage 0b producing an `observation_id`.

### Stage 1 — Host-control

mTLS host enable/control at `/v1/replacement/meetings/participation/control`
(`meeting_participation_service_v1.py`), contracts in
`participation_control_contracts_v1.py`. **Bindings carried by the runner
signature:** exact meeting selector + CAS `expected_head` + operation UUID +
`observation_id` from stage 0b. Server-derived principal. No caller
actor/role/body/provider selectors. UI-only screenshots and fixture auth are
NOT this stage. **No Next host enable/control web surface exists on this head.**
A browser enable/control surface is a named remaining gate (see Remaining
gates), not a stage of this one-shot.

### Stage 2 — Current-turn

S07 `MeetingCaptureFactoryV1.read_current_participant_turn_v1` / SQL
`meeting_capture_current_turn_v1`. **Bindings:** exact finalized ingress event
UUID, epoch, raw/normalized SHA binding. Unknown/Oracle speaker never produces
a turn.

### Stage 3 — Sender

`meeting_participation_prepare_v1` then `meeting_participation_claim_v1` under
CURRENT enabled generation. **Bindings:** CAS `expected_revision`, intent_id,
operation UUIDs, SAME-admission linkage. One executable body only after
commit+close+fresh own current status. No transparent retry. Lost claim =
UNKNOWN.

### Stage 4 — Bytes-in receipt

`meeting_participation_observe_v1` + `meeting_participation_status_v1` on the
SAME sender admission, using the sealed receipt path
(`meeting_participation_v1.py` `receipt_v1` at line 291, bytes-in / artifact-out)
as exercised by `test_meeting_participation_sql.py`. **Bindings:** bounded raw
wire bytes, claim_event_id, operation UUID, SAME admission linkage. Ambiguous
outcome = UNKNOWN. Receipt never reauthorizes send. Forensic receipt after host
disable completes inflight only.

**There is no sealed fake-Recall HTTPS owner.** The SQL tests inject raw wire
bytes directly into the receipt path. Literal HTTP 200/201/429/5xx network
negatives and "exactly ONE network invocation across restart/repeat" are
**UNPROVED** (see UNPROVED list) unless and until a fixture that counts exactly
one network invocation is sealed and reviewed.

### Stage 5 — Status/reconcile

`meeting_participation_status_v1` readback, forensic receipt, read-only
reconciliation after ambiguity. ACK never equals visible message or provider
idempotency.

## Forbidden network path (H-E)

The following are **forbidden** for this journey and every stage of it:

- `exchange_provider_v1` (`apps/workers/src/lib/meeting-participation.ts:44`)
- `sendRecallChatMessage` (`apps/workers/src/lib/recall.ts:29-63`, real HTTPS
  POST to `https://us-east-1.recall.ai`, 15s timeout)
- any `recall.ts` HTTPS POST

The **only** allowed bytes-in path is the factory layer
(`meeting_participation_v1.py:291` `receipt_v1`, bytes-in / artifact-out).
The sealed runner refuses to start if any `RECALL_*` environment variable is
present, so the worker entrypoint cannot be reached by accident.

## Deadline / CAS / conflict policy (H-C)

- Every SQL entry enforces a **≤30s absolute deadline**
  (`021_meeting_participation.sql:163`;
  `participation_authority_v1.py:216-221` rejects deadlines beyond +30s).
- Observations expire in **≤30s** (`021_meeting_participation.sql:259`).
- `control` / `prepare` / `observe` / `claim` all take **CAS revisions**
  (`expected_head` / `expected_revision`).
- **On head conflict, expired observation, or elapsed window: STOP.**
  No transparent retry. Record the failing stage in the outcome record and
  leave **UNKNOWN** semantics. A single re-read is not authorised; the journey
  ends at the failing stage.
- The shared **120s** monotonic budget covers journey stages only.
  Fixture/bootstrap setup sits **outside** that budget, matching
  `verify_workflow_integrity.py:384-386`. The runner enforces the budget with
  a monotonic deadline helper shaped like `_request_fence_v1`
  (`request_deadline_v1.py:26-35`), never a wall-clock label.
- Per-request ceiling **≤30s**.

## Migration inventory (C5 correction — actual sealed fact)

There is **no contiguous `001..014` chain**. The sealed inventory is
`SYNTHETIC_MIGRATIONS` in `scripts/oracle2/verify_workflow_integrity.py:112-117`:

`001, 002, 004, 006, 007, 008, 009, 010, 011, 012, 013, 014, 017, 018, 019, 020, 021, 022, 023, 027`

(20 entries; **omits `003` and `005`; includes `017/018/019/022/023/027`**). The
canonical inventory is derived from that tuple
(`dev/oracle2/test_canonical_schema.py:27-43`) and the sealed bootstrap executes
all of it (`dev/oracle2/test_canonical_schema.py:157-160`). **The journey uses the
sealed bootstrap** and the runner **asserts** inventory and catalog equality via
`bootstrap_canonical_test_schema` / `_inventory_digest` / `_catalog` — it never
merely echoes a note. It does not claim a custom `001..014+020+021` chain, and
it does not claim "no 17/18/19 union" — those files are in the sealed inventory.

## Resource and budget contract

- ONE fresh owned synthetic Postgres via `dev/oracle2/test_worker_postgres_fixture.worker_postgres`.
  Project class `oracle2-synthetic-p24s08-journey-<hex>` (required regex
  `oracle2-(?:ci|synthetic)-[a-z0-9-]{1,80}`); worker label `documentary-01`
  (required regex `(?:documentary-[0-9]{2}|event)`).
- **Unique project name per run** and **unique SCRATCH per run**. SCRATCH must
  never live inside the repository worktree (it would dirty the tree the
  source snapshot cannot see).
- Owned cleanup: after `finally`, **always** read back
  `docker ps|network ls|volume ls` filtered by the exact project label —
  including pre-identity refusals — and **absence must be proven**. Never broad
  cleanup. Docker probes use a 60s timeout (matching the fixture).
- Budgets: shared **120s** monotonic ceiling for journey stages (bootstrap
  outside); **per-request ≤30s**; 0 F/E/S/timeout/launch/cleanup. No case
  cuts, no budget raises. **W10 SAME worker-fit for the participation suites
  is asserted, not measured** — they are appended to DOCUMENTARY/EVENT without
  the `_place_suites` measurement other families receive
  (`verify_workflow_integrity.py:104-122` vs `:201-242`). This one-shot does
  **not** prove W10 SAME.
- `ai-task-gates check --before database` must print a **precise ALLOW line**
  (`^ALLOW$` or `^gate: ALLOW$` per line — never a substring match) before any
  DB; the sealed runner invokes it and refuses on non-ALLOW. `git`,
  `ai-task-gates` and `docker` are resolved to absolute paths and their
  `--version` identity is recorded in evidence.
- Review receipt required before release: exact full 40-char HEAD + runner
  SHA-256 + plan SHA-256 + checker SHA-256 + evidence SHA-256 + verdict
  `APPROVE`. The sealed runner refuses without it and never manufactures one.
  The receipt under SCRATCH is **procedural** (operator-minted); it is not a
  cryptographic authority. File checks follow `test_canonical_schema.py:96-114`
  (`O_NOFOLLOW`, regular file, nlink=1, mode 0600, size ≤4096, stable stat)
  where the host supports them; on Windows `os.getuid` is absent and that limit
  is recorded. Stop, do not bypass.
- Synthetic/invented only. No company originals, production, paid providers,
  real Teams. **Real Teams producer stays UNQUALIFIED.** ACK ≠ visible message.
  Business acceptance held.

## Byte-identity pin language (H2 correction)

Byte-identity for `services/oracle-brain/sql/021_meeting_participation.sql` is
pinned on **git blob bytes**, not working-tree bytes (CRLF checkouts diverge):

```
git show HEAD:services/oracle-brain/sql/021_meeting_participation.sql | sha256sum
```

The earlier sealed note recorded `959a7755…` / 63753 B LF. A working-tree
measurement on a CRLF host is **not** a valid pin and must not be quoted as one.
Runner-SHA bindings likewise hash the runner file as checked out at receipt time;
the receipt binds that exact hash together with the exact HEAD.

**Source snapshot of the runner (H-F)** hashes **worktree file CONTENTS**
(sha256 of bytes + mode) for `.py/.ts/.tsx/.sql/.json/.md/.yaml/.yml` plus
`compose.yaml` / `compose.yml` / `docker-compose.*` and lockfiles
(`pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`, `poetry.lock`, `uv.lock`,
`Cargo.lock`, `go.sum`) — never `git ls-files` index blobs, which cannot see a
worktree edit after bind. Sealed blob pins stay git-blob; the snapshot is for
mutation detection only.

## Test figures (H1 correction — no 230/256 mixing)

| Figure | Source | Status |
|---|---|---|
| Windows control suite (`test_meeting_participation_control_v1.py`) | clean | sealed evidence note (this host) |
| Windows wire suite (`test_meeting_participation_wire_v1.py`) | 2 errors (env-var length on one huge parametrized id) | sealed evidence note (this host) |
| Windows v1 suite (`test_meeting_participation_v1.py`) | 31 passed / 57 failed / 2 errors (`os.getuid()` absent on Windows) | sealed evidence note (this host) |
| SQL module (`test_meeting_participation_sql.py`) | 21 cases collected, **NOT executed** | sealed evidence note (this host) |
| `test_meeting_participation.py` | **not measured on this host** | collect-only count to be measured on the Linux rerun |
| `test_outbound_replay.py` | **not measured on this host**; module-skips when `oracle_brain.meetings.delivery` is absent | collect-only / skip disposition to be measured on the Linux rerun |
| 21/21 SQL green on edge-dev3 | prior-session Linux run | **prior-session evidence, not current-head proof** |
| 256 pure / 21 SQL | historical Linux run | **not re-claimed** |
| 230 pure (4 suites + verifier) | edge-dev3 `/tmp` status note | **not sealed; not re-claimed here** |

This plan does not mix 230 and 256 and does **not** demand "full 256 pure".
Pure coverage on the head is whatever the sealed evidence note records for this
Windows host. **Per-suite collect-only counts for the six S08 gate modules are
to be measured on the Linux rerun**; until then no pure total is claimed. The
real-DB path is covered only by the 21 SQL when they are actually executed.

## S08 gate files (M-A — all six)

`scripts/oracle2/verify_phase.py:96-103` gates **six** modules:

1. `test_meeting_participation.py`
2. `test_meeting_participation_control_v1.py`
3. `test_meeting_participation_sql.py`
4. `test_meeting_participation_v1.py`
5. `test_meeting_participation_wire_v1.py`
6. `test_outbound_replay.py`

All six must be reported. `test_outbound_replay.py:11-20` **module-skips** when
`oracle_brain.meetings.delivery` is absent (not built on main). Under the
"skips fail" verifier (`verify_workflow_integrity.py:2`) that skip is a
**disposition to report, not a silent pass**: the Linux rerun must record
whether the module skipped or ran, and a skip is not a green case. The two
unreported modules (`test_meeting_participation.py`, `test_outbound_replay.py`)
are named above so the Linux rerun has a target to reconcile against.

## Sequencing — the 21 SQL must go green first (M-E)

**Failure attribution rule:** the 21 SQL cases
(`test_meeting_participation_sql.py`) must go green against an owned synthetic
database under the sealed bootstrap **before** the journey one-shot runs. If a
journey stage fails while the 21 SQL are red, the failure is attributed to the
backend, not the journey. If the 21 SQL are green and a journey stage fails,
the failure is attributed to the journey adapter. This order is mandatory.

## Privilege-typing note (M1)

The head commit's semantic change (typed write-time privilege refusals;
post-commit denials stay UNKNOWN) is present on this head
(`participation_authority_v1.py`: `InsufficientPrivilege` re-raised only when
`write_returned` is False; `mutation_attempted` set before the guarded send).
It is exercised by the 21 SQL tests **when those run**. Pure tests use fakes and
do **not** prove the real-DB path. Do not overclaim pure coverage of it.

## Negative cases — split (H4)

### Backend-covered (the 21 SQL module, when executed)

- Missing/off/disabled/stale generation; wrong role/account/bot/platform/channel/chat-unknown
- Broken selected root with alternate valid grant
- Capture ended/withdrawn/replaced/Oracle-origin/speaker-unknown
- Incomplete audience; body bounds/cross-selector/unknown fields
- Concurrent claims, one winner
- Proactive default-off, cooldown 120 / max 3 across toggles
- Claim commit ACK loss / response drop / worker restart → no body, no resend
- Claim readback-loss pair → UNKNOWN, no automatic retry
- Forensic receipt after host disable completes inflight only
- Deadline non-renewal; permission-expiry enforcement points at SQL 021
  (`021_meeting_participation.sql:163-168`)

### Journey-orphaned / UNPROVED by this one-shot

- HTTP 201 / 429 / 5xx / network expiry never-observed-200 (no network actor)
- Exactly ONE network invocation across restart/repeat (no network counter fixture)
- Host disable between prepare and claim implying **zero network** (no network actor)
- Observation-commit ACK loss → one event + read-only reconcile as a **journey**
  sequence (the shared `_write` path is exercised only via claim-side SQL tests)
- Full permission-expiry before/after close matrix as a journey-level enumerated
  executor (enforcement points exist; the matrix is not executed end-to-end)
- Next browser enable/control web surface (does not exist on this head)

## UNQUALIFIED

- **Real Teams chat/audience producer.** UNQUALIFIED permanently for this
  one-shot. ACK never equals visible message or provider idempotency.
- **Business acceptance / company readiness.** HELD. No acceptance claimed.

## UNPROVED / remaining gates

1. Journey one-shot execution itself (this seal is plan + runner + checker only).
2. Fresh-current complete composition review on a Linux host. **Per-suite
   collect-only counts for the six S08 gate modules are to be measured on that
   rerun** (four measured on Windows + `test_meeting_participation.py` +
   `test_outbound_replay.py` unreported). No "full 256 pure" figure is demanded
   or claimed.
3. Actual 21 SQL against an owned synthetic database under the **sealed bootstrap**
   inventory (not a contiguous 001..014 claim). **The 21 SQL must go green
   before the journey runs** (see Sequencing).
4. Next host enable/control **web** surface (named remaining gate; out of scope
   for this one-shot). Until then the journey's control stage is the mTLS
   `/v1/replacement/meetings/participation/control` path only.
5. Fake-Recall HTTPS owner and HTTP status/network negatives (need a fixture that
   counts exactly one network invocation, sealed and reviewed). The forbidden
   network path (`exchange_provider_v1` / `sendRecallChatMessage` / `recall.ts`
   HTTPS POST) stays unreachable.
6. Full installed invitation / supervision / audience-currentness proof.
7. W10 SAME worker-fit measurement for the participation suites (currently asserted).
8. Real Teams chat/audience producer remains UNQUALIFIED.

## Fail-closed bindings enforced in the sealed runner

`scripts/oracle2/run_s08_journey_proof_v1.py` refuses unless **all** hold:

1. No `RECALL_*` environment variable is present (forbidden network path guard).
2. `git rev-parse HEAD` is a full 40-char hex SHA and the worktree is clean.
3. The sealed migration inventory matches `canonical_synthetic_migrations()`
   exactly (20 entries).
4. A review receipt exists whose `head` equals that exact 40-char HEAD, whose
   `runner_sha256` / `plan_sha256` / `checker_sha256` / `evidence_sha256` match
   the files on disk, and whose `verdict` is `APPROVE`. The runner never
   manufactures a receipt. File checks follow `test_canonical_schema.py:96-114`
   where the host supports them.
5. `ai-task-gates check --before database` prints a precise ALLOW line
   (`^ALLOW$` or `^gate: ALLOW$`).
6. Source snapshot (worktree bytes + mode, including compose/lockfiles) before
   the gate equals source snapshot after the gate.
7. After bootstrap the live inventory and catalog match the sealed inventory.
8. After the run, exact owned synthetic containers/networks/volumes for the
   project are absent (readback **always**, including pre-identity refusals),
   else STOP when identity was established.

Refused runs write only `refusal.json` with `refused: true` /
`non_evidence: true` and never `journey-evidence.json`. Stages that are not
implemented raise `JourneyRefusal` and refuse. The runner is a one-shot journey
runner: it binds the exact head + review receipt and must not be reused across
heads without a new receipt.
