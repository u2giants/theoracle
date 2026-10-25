# S08 participation one-shot journey proof plan (sealed)

Recorded: 2026-10-25 EDT. Branch `parent24-s08-compose-81742134`, PR #200.
Status: **PLAN + SEALED RUNNER + CHECKER ONLY.** No journey execution, no
database, no provider, no browser acceptance in this seal.

Python floor: **≥3.11** (the runner uses `Exception.add_note` in cleanup
paths; on 3.10 the finally handler itself raises and masks the original
exception). edge-dev3 runs 3.14; the Linux-host interpreter must meet this
floor.

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
| `docs/verification/oracle2/s08-compose-81742134-evidence.md` | composition evidence note |

Backend source of truth this journey binds (already sealed on the head):

- `services/oracle-brain/sql/021_meeting_participation.sql` (deadline/admission enforcement)
- `services/oracle-brain/tests/test_meeting_participation_sql.py`
- `services/oracle-brain/oracle_brain/meetings/participation_authority_v1.py`
- `services/oracle-brain/oracle_brain/meetings/participation_control_contracts_v1.py`
- `services/oracle-brain/oracle_brain/meetings/participation_runtime_v1.py`
- `services/oracle-brain/oracle_brain/meetings/participation_wire_v1.py`
- `services/oracle-brain/oracle_brain/meetings/participant_epoch.py`
- `services/oracle-brain/oracle_brain/hosting/meeting_participation_v1.py`
- `services/oracle-brain/oracle_brain/hosting/meeting_participation_service_v1.py`
- `services/oracle-brain/oracle_brain/hosting/meeting_capture_v1.py`
- `services/oracle-brain/oracle_brain/hosting/original_intake_v1.py`
- `services/oracle-brain/oracle_brain/operating_model/protected_sql_connection_v1.py`
- `services/oracle-brain/oracle_brain/operating_model/request_deadline_v1.py`
- `services/oracle-brain/oracle_brain/operating_model/artifact_storage.py`
- `services/oracle-brain/tests/conftest.py`
- `services/oracle-brain/tests/test_hosting_boundary.py`
- `dev/oracle2/test_worker_postgres_fixture.py`
- `dev/oracle2/test_canonical_schema.py`
- `scripts/oracle2/verify_workflow_integrity.py`
- `scripts/oracle2/verify_phase.py`
- `apps/workers/src/lib/recall.ts`
- `apps/workers/src/lib/meeting-participation.ts`
- `packages/shared/src/protected-meeting-worker.ts` (owner of `exchange_provider_v1`)

Harness deps: `openssl` (mTLS peer-file re-sign), `docker compose`
(`dev/oracle2/compose.yaml`), `pytest` (21 SQL runner). (H9: the prior list
omitted `021_meeting_participation.sql`, `participant_epoch.py`,
`original_intake_v1`, `protected_sql_connection_v1`, `request_deadline_v1`,
`artifact_storage`, `participation_control_contracts_v1.py`,
`participation_runtime_v1`, `participation_wire_v1`, `meeting_capture_v1`,
the `@oracle/shared/protected-meeting-worker` owner, `conftest.py`,
`test_hosting_boundary`, and `openssl` — all load-bearing for the cited
stages.)

## Exact journey stages the eventual one-shot must prove (invented data only)

The journey is **provision-capture-admission → observe-audience →
host-control → current-turn → sender → bytes-in receipt → status/reconcile**.
There is no Next browser stage in this one-shot.

**C5 — SHA churn:** any edit to the runner file churns the receipt-bound
SHA-256 and requires a new independent review and a new receipt. There is no
"no SHA churn" guarantee. Stage signatures carry the plan's bindings (H-D) so
that an implementer has a contract, but the whole-file SHA is still bound.

Each stage pins its **call layer** (H10):

| Stage | Call layer | Owner |
|---|---|---|
| 0a provision-capture-admission | **factory** | `MeetingCaptureFactoryV1.transition_v1` / `retain_ingress_v1` |
| 0b observe-audience | **authority** | `observe_audience_v1` |
| 1 host-control | **service → authority** | mTLS HTTP `/v1/.../control` → `control_v1` |
| 2 current-turn | **factory** | `read_current_participant_turn_v1` |
| 3 sender | **factory** | `prepare_v1` / `claim_v1` (never raw SQL) |
| 4 bytes-in receipt | **factory** | `receipt_v1` (bytes-in / artifact-out) |
| 5 status/reconcile | **factory + authority** | `status_v1` + read-only reconcile |

Only the factory layer enforces turn freshness, bot identity, body
composition, and post-commit currentness
(`meeting_participation_v1.py:212-272`). Raw SQL at the sender layer is
forbidden.

### Stage 0a — capture / admission provisioning (precondition)

Cites the SQL fixture construction at
`test_meeting_participation_sql.py:68-133`: appointments, capture admissions,
roles/grants, **invite → retain_ingress** (exactly TWO capture calls —
`transition_v1(action='invite')` at line 114 and `retain_ingress_v1` at line
117; there is **no finalize method** — C4), and the host/sender/observer
participation admissions (`meeting_participation_admissions_v1`). Whoever runs
the journey must mint these first. Without stage 0a there is no admission
linkage for any later stage. This is a real stage, not an implicit fixture
assumption.

### Stage 0b — observer / audience observation (precondition for enable)

`observe_audience_v1` / `invent_observation` pattern from
`test_meeting_participation_sql.py:136-144`. Enabling the host requires an
`observation_id` (`participation_authority_v1.py:458`); the factory derives it
from current SQL status (`meeting_participation_v1.py:202`), which only exists
after this observation. Observation expiry ≤30s
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

**H8 — mTLS prerequisites deferred.** The peer-file minting, seals, `openssl`
re-sign, `certificates`/`WORKER` fixtures
(`test_hosting_boundary.py:18,28`), closed-denial matrix (bad identity/path/
body/headers → 404/503), and peer-tamper → 503 case
(`test_meeting_participation_sql.py:428,436`) are **not carried** by this
runner. They are an explicit named remaining gate. Stage 1 cannot execute
until that gate is discharged. See Remaining gates #9.

### Stage 2 — Current-turn

S07 `MeetingCaptureFactoryV1.read_current_participant_turn_v1` / SQL
`meeting_capture_current_turn_v1`. **Bindings:** exact finalized ingress event
UUID, epoch, raw/normalized SHA binding. Unknown/Oracle speaker never produces
a turn.

### Stage 3 — Sender

`meeting_participation_prepare_v1` then `meeting_participation_claim_v1` under
CURRENT enabled generation, via the **factory** layer
(`meeting_participation_v1.py:212,243`). **Bindings:** CAS `expected_revision`,
intent_id, operation UUIDs, SAME-admission linkage. One executable body only
after commit+close+fresh own current status. No transparent retry. Lost claim
= UNKNOWN (routes to stage 5 — see H5).

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

`meeting_participation_status_v1` readback (`meeting_participation_v1.py:164`),
forensic receipt, read-only reconciliation after ambiguity. ACK never equals
visible message or provider idempotency.

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
  leave **UNKNOWN** semantics.
- **UNKNOWN routing (H5/M1):** UNKNOWN from claim commit ACK loss / response
  drop / worker restart / readback-loss (`sender`, `receipt_bytes_in`)
  proceeds to **stage 5** `status_reconcile` (read-only reconcile of the
  OUTCOME) and then **ends the stage sequence** — the linear `STAGE_ORDER`
  loop is never resumed. Concretely: a `sender` UNKNOWN does **not** inject
  wire bytes afterwards (`receipt_bytes_in` is skipped — consistent with the
  sealed ACK-loss / no-resend rule) and does **not** double-run any stage
  (`status_reconcile` runs exactly once, as the routing target). A
  `receipt_bytes_in` UNKNOWN likewise runs `status_reconcile` exactly once
  and stops. UNKNOWN from any earlier stage (provision, observe, host-control,
  current-turn) **ends the journey at that stage**. **Mechanism (M1):** a
  stage raises `JourneyUnknown(JourneyRefusal)` for routable UNKNOWN; the
  main stage loop catches `JourneyUnknown` separately from plain
  `JourneyRefusal` (which is always fatal STOP) and applies
  `_route_unknown(stage)` — `("status_reconcile",)` for the claim/readback
  stages, `()` (STOP) for every other stage — then returns from
  `_run_stage_order` so the linear loop is never resumed. This is how an
  implementer distinguishes routable UNKNOWN from fatal refusal. The checker
  exercises `_route_unknown` offline, asserts `except JourneyUnknown` is
  present in the main loop, and runs a **main-loop flow test** against
  `_run_stage_order` (fake stages) proving that a `sender` UNKNOWN runs
  `status_reconcile` exactly once and never `receipt_bytes_in`, and that a
  `receipt_bytes_in` UNKNOWN does not double-run `status_reconcile`.
- **"No re-read" scope (H5):** the journey layer never re-reads a failing
  stage's inputs to retry. Factory-internal fresh readbacks
  (`meeting_participation_v1.py:201-210,231-240,256-269`) are the tested
  factory behaviour and are **outside** this scope. Stage 5's `status_v1` is a
  read-only reconcile of the outcome, not a re-read of stage inputs.
- The shared **120s** monotonic budget covers journey stages only.
  Fixture/bootstrap setup sits **outside** that budget, matching
  `verify_workflow_integrity.py:384-386`; the budget is armed only **after**
  `worker_postgres` + `bootstrap_canonical_test_schema` + 21 SQL green,
  matching `:407` (C9). The runner enforces the budget with a ContextVar
  monotonic fence that requires finite floats and performs entry + exit
  remaining checks (H1). Note: `request_deadline_v1._request_fence_v1`
  (request_deadline_v1.py:26-35) is entry-check-only; the runner adds an
  exit remaining check and is therefore STRICTER than that source.
- Per-request ceiling **≤30s**. The runner validates each stage's `deadline_s`
  is an int in `(0, 30]` and refuses otherwise (M5). The shared 120s budget
  is a total ceiling for all seven stages; there is no per-stage allocation
  mechanism — a stage may consume the whole remaining budget. The fence
  refuses only when the budget is fully elapsed (`remaining > 0` check).

## Release workflow for the review receipt (C3)

A unique per-run SCRATCH **cannot** hold a pre-minted receipt. The release
workflow is:

1. The operator mints `review-receipt.json` at a known path **OUTSIDE** any
   SCRATCH directory.
2. The operator sets `ORACLE2_S08_JOURNEY_RECEIPT` to that path.
3. The runner mints a unique per-run SCRATCH (uuid directory), then **copies**
   the receipt into it and verifies the copy.

The runner never manufactures a receipt. The `ORACLE2_S08_JOURNEY_SCRATCH`
override exists only for offline checker isolation and is not the release
workflow. The fixture's `mkdir(exist_ok=False)` for the worker subdirectory is
avoided by using a unique per-run worker subdirectory name (C3).

## Migration inventory (C5 correction — actual sealed fact)

There is **no contiguous `001..014` chain**. The sealed inventory is
`SYNTHETIC_MIGRATIONS` in `scripts/oracle2/verify_workflow_integrity.py:112-117`:

`001, 002, 004, 006, 007, 008, 009, 010, 011, 012, 013, 014, 017, 018, 019, 020, 021, 022, 023, 027`

(20 entries; **omits `003` and `005`; includes `017/018/019/022/023/027`**). The
canonical inventory is derived from that tuple
(`dev/oracle2/test_canonical_schema.py:27-43`) and the sealed bootstrap executes
all of it (`dev/oracle2/test_canonical_schema.py:157-160`). **The journey uses the
sealed bootstrap** and the runner **asserts** inventory digest against a
**sealed review-time constant** (H3/C2) — `SEALED_INVENTORY_DIGEST` — using
**git-blob bytes** (`git show HEAD:services/oracle-brain/sql/<name>`) so the
constant is host-independent (LF, not CRLF-fragile worktree bytes). The exact
constant is `7eb6085c3535175ac304b8ccd1db283aa64087042af52b2934a9065fd371be99`.
Mint command (run on any host with git):

```bash
python -c "
import hashlib, subprocess
names = (
    '001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql',
    '006_hosting_gateway_authority.sql','007_hosting_candidate_permissions.sql',
    '008_hosting_runtime_permissions.sql','009_hosting_result_permissions.sql',
    '010_hosting_job_permissions.sql','011_hosting_source_processing_permissions.sql',
    '012_processing_compiler_capabilities.sql','013_processing_purpose_permissions.sql',
    '014_replacement_source_custody.sql','017_processing_model_history.sql',
    '018_original_review_reading_input.sql','019_employee_conversations.sql',
    '020_meeting_capture.sql','021_meeting_participation.sql',
    '022_consolidated_answer_delivery.sql','023_maintained_research.sql',
    '027_legacy_migration.sql',
)
parts = []
for n in names:
    raw = subprocess.check_output(['git','show',f'HEAD:services/oracle-brain/sql/{n}'])
    parts.append(n.encode()+b'\\0'+hashlib.sha256(raw).digest())
print(hashlib.sha256(b''.join(parts)).hexdigest())
"
```

The catalog digest is **recorded, not golden** (C3 option-a): `SEALED_CATALOG_DIGEST`
is written to evidence but never compared against a sealed constant and there
is no refuse-on-empty. Filling it later would churn the receipt-bound runner
SHA and demand re-review (C5); the plan therefore does not require a fill.
It does not claim a
custom `001..014+020+021` chain, and it does not claim "no 17/18/19 union" —
those files are in the sealed inventory.

## Resource and budget contract

- ONE fresh owned synthetic Postgres via `dev/oracle2/test_worker_postgres_fixture.worker_postgres`.
  Project class `oracle2-synthetic-p24s08-journey-<hex>` (required regex
  `oracle2-(?:ci|synthetic)-[a-z0-9-]{1,80}`); worker label `documentary-01`
  (required regex `(?:documentary-[0-9]{2}|event)`).
- **Unique project name per run** and **unique SCRATCH per run**. SCRATCH must
  never live inside the repository worktree (it would dirty the tree the
  source snapshot cannot see) — this is behavioral: setting
  `ORACLE2_S08_JOURNEY_SCRATCH` to an in-repo path raises a tagged
  `JourneyRefusal` and creates no directory (M3). SCRATCH parent must not be
  group/other-writable
  unless the sticky bit is set (standard `/tmp` mode 1777 is allowed — L2).
  If the parent does not exist, the nearest existing ancestor is checked;
  after mkdir the parent is re-checked to close the stat-then-mkdir TOCTOU (L9).
  **SCRATCH reuse (L3):** a reused `ORACLE2_S08_JOURNEY_SCRATCH` directory
  must be **empty after marker cleanup** (`refusal.json` / `journey-evidence.json`
  are unlinked first). Any other residue — e.g. a leftover
  `ops-schema-receipt.json` — raises a tagged `JourneyRefusal` naming the
  residue, never a raw `FileExistsError` from the schema-receipt `O_EXCL`
  write further downstream.
- Owned cleanup: after `finally`, **always** read back
  `docker ps|network ls|volume ls`. Once identity is established, the filter
  uses the **real suffixed project name** (`identity['project']`, e.g.
  `base+'-w'+12hex`) — exact-match on the base name alone is vacuous (C2).
  Before identity, the readback is **prefix-aware** (client-side filter on
  project label `startswith(base)`), because docker label filters are
  exact-match. NOTE: the pre-identity path uses a unique per-run random base,
  so it can never match residue from a prior run — it is vacuous as an absence
  proof for prior leaks and is kept for cleanup-contract uniformity only.
  Absence must be proven. Never broad cleanup. Docker probes use
  a 60s timeout (matching the fixture). cleanup.json is an **ops artifact**
  (labeled `ops: true` / `non_evidence: true`) — never forensic evidence (C8).
- Budgets: shared **120s** monotonic ceiling for journey stages (bootstrap +
  21 SQL green outside; budget armed only after both — C9); **per-request
  ≤30s** validated per stage (M5); 0 F/E/S/timeout/launch/cleanup. Skips are
  recorded in a skip-disposition note but do **not** count as F/E/S failures
  (L8): a `test_outbound_replay` skip is a skip, not a failure. No case
  cuts, no budget raises. **W10 SAME worker-fit for the participation suites
  is asserted, not measured** — they are appended to DOCUMENTARY/EVENT without
  the `_place_suites` measurement other families receive
  (`verify_workflow_integrity.py:104-122` vs `:201-242`). This one-shot does
  **not** prove W10 SAME.
- `ai-task-gates check --before database` must print a **precise ALLOW line**
  (`^ALLOW$` or `^gate: ALLOW$` per line — never a substring match) and must
  **not** print any `^DENIED$` / `^gate: DENIED$` line (M1). The sealed runner
  invokes it and refuses on non-ALLOW or on any DENIED. **Exit-code contract
  (M4, pinned):** a zero exit with a precise ALLOW line and no DENIED line is
  the only pass. A nonzero exit or timeout is **always** a refusal — the
  runner captures stdout/stderr, writes `ops-database-gate.txt` **even on
  nonzero exit**, searches the captured output for DENIED lines so the
  refusal names the gate's own denial when present, and raises a tagged
  **M4/M7** refusal with the output tail. A raw `CalledProcessError` must
  never escape `require_database_gate`. The **zero-exit** refusal branches
  are tagged **M4/M7** too (H1): zero-exit-with-DENIED refuses naming DENIED,
  zero-exit-without-ALLOW refuses naming ALLOW — a mutation deleting those
  branches must fail the checker's zero-exit mock cases. An `OSError`
  (missing/unexecutable gate binary) is caught and raised as a tagged
  **M4/M7** `JourneyRefusal`, never an untagged escape (L6). The pytest
  identity preflight (`sys.executable -m pytest --version`) follows the same
  contract: nonzero exit or timeout is a tagged **M4/M7** preflight refusal,
  never a raw `CalledProcessError`. Each tool uses its own working identity
  command (C1):
  `git --version`, `docker --version`, `ai-task-gates version` (subcommand —
  `--version` does not exist and would refuse every run), `openssl version`
  (not `--version`), and `pytest` (via `sys.executable -m pytest --version`)
  are resolved to absolute paths and their version identity is recorded in
  evidence; a missing version is a **refusal**, not a recorded gap (M7).
  Every gate/preflight/git subprocess is bounded by a **60s** timeout (M5) so
  a hang cannot outlast the one-shot run. The `docker compose` plugin is
  also preflighted (`docker compose version`) — a missing plugin is a
  preflight refusal, not a late fixture failure (M8).
- Review receipt required before release: exact full 40-char HEAD + runner
  SHA-256 + plan SHA-256 + checker SHA-256 + evidence SHA-256 + verdict
  `APPROVE`. All four SHA bindings use **git-blob semantics**
  (`git show HEAD:path | sha256sum`) so CRLF checkouts cannot diverge (H6).
  The sealed runner refuses without the receipt and never manufactures one.
  File checks follow `test_canonical_schema.py:96-114`
  (`O_NOFOLLOW`, regular file, nlink=1, mode bits & 0o077 == 0 — i.e. no
  group/other permission bits, not a literal 0600 — size ≤4096, stable stat,
  lstat cross-check) where the host supports them; the payload is read via
  the **same O_NOFOLLOW fd** (H7 — no TOCTOU). On Windows `os.getuid` is
  absent, POSIX mode bits and nlink==1 cannot be enforced, and those checks
  degrade honestly (`mode_check: unavailable-on-windows`) without failing the
  positive path (H1). `o_nofollow` records actual `O_NOFOLLOW` availability (H6).
  Stop, do not bypass.
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

**All receipt SHA bindings (H6)** — runner, plan, checker, evidence — likewise
use git-blob semantics (`git show HEAD:path | sha256sum`), not working-tree
bytes. A receipt minted on Windows will verify on the mandated Linux rerun.

**Source snapshot of the runner (H-F/M2)** hashes **worktree file CONTENTS**
(sha256 of bytes + mode) for `.py/.ts/.tsx/.js/.mjs/.cjs/.mts/.sql/.json/.md/
.yaml/.yml/.toml/.sh/.bash/.ps1/.dockerignore` plus `Dockerfile` and its
variants (`Dockerfile.web`, `api.Dockerfile`), `requirements*.txt`,
`.dockerignore`, `compose.yaml` / `compose.yml` / `docker-compose.*` and
lockfiles (`pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`, `poetry.lock`,
`uv.lock`, `Cargo.lock`, `go.sum`) — uses `lstat` so symlink swaps are
visible (M2). Sealed blob pins stay git-blob; the snapshot is for mutation
detection only. (L10: JS module extensions and Dockerfile/requirements
variants included — `dev/oracle2` ships `.mjs/.mts` files.)

## Test figures (H1 correction — no 230/256 mixing)

| Figure | Source | Status |
|---|---|---|
| Windows control suite (`test_meeting_participation_control_v1.py`) | clean | sealed evidence note (this host) |
| Windows wire suite (`test_meeting_participation_wire_v1.py`) | 2 errors (env-var length on one huge parametrized id) | sealed evidence note (this host) |
| Windows v1 suite (`test_meeting_participation_v1.py`) | 31 passed / 57 failed / 2 errors (`os.getuid()` absent on Windows) | sealed evidence note (this host) |
| SQL module (`test_meeting_participation_sql.py`) | 21 cases collected, **NOT executed** | sealed evidence note (this host) |
| `test_meeting_participation.py` | **not measured on this host** | collect-only count to be measured on the Linux rerun |
| `test_outbound_replay.py` | **not measured on this host**; **expected to RUN** on Linux — `oracle_brain.meetings.delivery` exists at this head and base (`delivery.py` exports `DELIVERY_ACTION_PURPOSE` / `SenderCredentialProof`), so `find_spec` succeeds and the module collects/runs. The real skip condition (delivery absent, `test_outbound_replay.py:11-20`) does **not** hold. | collect/run disposition (not skip) to be measured on the Linux rerun |
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

All six must be reported. `test_outbound_replay.py:11-20` **module-skips** only
when `oracle_brain.meetings.delivery` is absent. That module **exists at this
head and base** (`services/oracle-brain/oracle_brain/meetings/delivery.py`
exports `DELIVERY_ACTION_PURPOSE` and `SenderCredentialProof`), so on Linux
`importlib.util.find_spec` succeeds and `test_outbound_replay.py` is
**expected to RUN** (collect and execute) — not skip. Under the "skips fail"
verifier (`verify_workflow_integrity.py:2`) a skip would be a **disposition to
report, not a silent pass**, and a skip is not a green case; the Linux rerun
must record the actual disposition (**expected: run**). The two unreported
modules (`test_meeting_participation.py`, `test_outbound_replay.py`) are named
above so the Linux rerun has a target to reconcile against.

## Sequencing — the 21 SQL must go green first (M-E/H4)

**Failure attribution rule:** the 21 SQL cases
(`test_meeting_participation_sql.py`) must go green against an owned synthetic
database under the sealed bootstrap **before** the journey one-shot runs. If a
journey stage fails while the 21 SQL are red, the failure is attributed to the
backend, not the journey. If the 21 SQL are green and a journey stage fails,
the failure is attributed to the journey adapter. This order is mandatory.

**Runner enforcement (H4/L1):** the runner **invokes** the 21 SQL module via
pytest against the bootstrapped database after `bootstrap_canonical_test_schema`
and refuses unless **exactly `21 passed`** is observed in the output **with
no `failed`/`error`/`skipped`/`xfailed`/`xpassed`/`deselected` count**. The
green state is **exactly 21 collected / 21 passed / 0 skipped**: when pytest
prints a `collected N items` line, `N` must be exactly 21, and a
`21 passed, 1 skipped` summary (22 collected) is **not** green. The pytest
timeout bound is **180s** (`SHARED_BUDGET_S + 60`). `TimeoutExpired` is
handled — `ops-sql-green.txt` is still written and the run refuses with an
H4 attribution and a bounded output tail (as does the nonzero-exit refusal).
The runner passes `-p no:cacheprovider` and sets `PYTHONDONTWRITEBYTECODE=1`
so the tree stays clean post-bind. This is not merely procedural — it is a
hard gate inside the runner.

The SQL module reads `ORACLE2_TEST_ADMIN_URL` directly (see C7 correction
below) and does **not** bootstrap via conftest. The journey runner provides the
externally bootstrapped admin URL. A standalone fresh-DB run of the SQL module
needs the runner's bootstrap first.

**Import-mode note (L10):** the 21 SQL module imports `certificates` from
`test_hosting_boundary` via pytest's default prepend import mode
(`test_meeting_participation_sql.py:34`). This works under the default
`--import-mode=prepend` but breaks under `--import-mode=importlib`. The runner
does not pass `--import-mode`; if collection fails after such a change, the
failure is fail-closed (H4 attribution), not silent.

## Privilege-typing note (M1)

The head commit's semantic change (typed write-time privilege refusals;
post-commit denials stay UNKNOWN) is present on this head
(`participation_authority_v1.py`: `InsufficientPrivilege` re-raised only when
`write_returned` is False; `mutation_attempted` set at `:417` before the
guarded send at `:418`). It is exercised by the 21 SQL tests **when those run**.
Pure tests use fakes and do **not** prove the real-DB path. Do not overclaim
pure coverage of it.

## Negative cases — split (H4/M3)

### Backend-covered (the 21 SQL module, when executed) — NON-EXHAUSTIVE (M3)

The list below is the subset the journey plan maps to journey stages. The 21
SQL module covers additional behaviours not enumerated here; this map is
**not exhaustive** and must not be read as a complete inventory of what the
SQL tests prove.

Mapped to journey stages:

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

Additional backend-covered behaviours **not mapped** to journey stages (M3 —
previously omitted): wrong-login/TLS/owner fail-closed
(`test_meeting_participation_sql.py:266-284`); runtime-login private-helper
denials (`:340-353`); bot-identity immutability (`:515-529`); foreign receipt
(`:508-513`); window-expiry forensic (`:532-542`); short-observation clip
(`:494-506`); late-wire orphan (`:475-492`).

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
   `test_outbound_replay.py` unreported). No historical pure total is demanded
   or claimed. **The offline skeleton checker must also be rerun on Linux**
   (M6) so the H4 mode/nlink/O_NOFOLLOW file negatives that skip on the
   sealing Windows host (`H4_MODE_SKIP`, `H4_NLINK_SKIP`, `H4_SYMLINK_SKIP`)
   actually execute — only the size negative fires where the seal was minted.
3. Actual 21 SQL against an owned synthetic database under the **sealed bootstrap**
   inventory (not a contiguous 001..014 claim). **The 21 SQL must go green
   before the journey runs** (see Sequencing; enforced in the runner, H4).
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
9. **mTLS stage-1 prerequisites (H8).** Peer-file minting, seals, `openssl`
   re-sign, `certificates`/`WORKER` fixtures
   (`test_hosting_boundary.py:18,28`), closed-denial matrix (bad identity/path/
   body/headers → 404/503), and peer-tamper → 503
   (`test_meeting_participation_sql.py:428,436`). Named remaining gate; stage 1
   cannot execute until discharged.

## Fail-closed bindings enforced in the sealed runner

`scripts/oracle2/run_s08_journey_proof_v1.py` refuses unless **all** hold:

1. No `RECALL_*` environment variable is present (forbidden network path guard).
2. `git rev-parse HEAD` is a full 40-char hex SHA and the worktree is clean.
3. The sealed migration inventory matches `canonical_synthetic_migrations()`
   exactly (20 entries).
4. A review receipt exists at the `ORACLE2_S08_JOURNEY_RECEIPT` release path
   (C3), whose `head` equals that exact 40-char HEAD, whose `runner_sha256` /
   `plan_sha256` / `checker_sha256` / `evidence_sha256` match the git-blob
   hashes of the files on disk (H6), and whose `verdict` is `APPROVE`. The
   runner never manufactures a receipt. File checks follow
   `test_canonical_schema.py:96-114` (same-fd payload read, H7) where the host
   supports them.
5. `ai-task-gates check --before database` prints a precise ALLOW line
   (`^ALLOW$` or `^gate: ALLOW$`) and **no** DENIED line (M1).
6. Source snapshot (worktree bytes + mode, including Dockerfile/.dockerignore/
   pyproject.toml/shell/compose/lockfiles, lstat not follow — M2) before the
   gate equals source snapshot after the gate.
7. After bootstrap the live inventory digest matches the **sealed review-time
   constant** (H3/C2): `SEALED_INVENTORY_DIGEST` over **git-blob bytes**
   (`git show HEAD:services/oracle-brain/sql/<name>` — host-independent LF).
   The catalog digest is **recorded, not golden** (C3 option-a): it is written
   to evidence but never compared against a sealed constant and there is no
   refuse-on-empty. Filling `SEALED_CATALOG_DIGEST` later would churn the
   receipt-bound runner SHA and demand re-review (C5).
8. The 21 SQL module runs green against the bootstrapped DB before any journey
   stage (H4).
9. After the run, exact owned synthetic containers/networks/volumes for the
   **real suffixed project** (`identity['project']`) are absent (readback
   **always**, including pre-identity refusals with prefix-aware listing — C2),
   else STOP when identity was established.
10. Each stage's `deadline_s` is validated as an int in `(0, 30]` (M5).
11. Stage binding dicts include all required keys per `STAGE_BINDING_SCHEMAS`
    (M9). The main loop passes `SKELETON_STAGE_BINDINGS` — valid-shaped
    placeholders — so a fresh skeleton run reaches the UNPROVEN refusal after
    binding validation, never M9 missing-keys (L14). An implementer replaces
    those placeholders with real journey bindings at the call sites when
    stages are released (C5 SHA churn applies).
12. Per-tool identity is established via each tool's working command (C1):
    `git --version`, `docker --version`, `ai-task-gates version` (subcommand,
    NOT `--version` which does not exist), `openssl version` (not `--version`),
    and `pytest` via `sys.executable -m pytest --version` (L16). A missing
    identity command is a refusal (M7).

**C8 — refusal/evidence exclusivity:** refused runs write only `refusal.json`
with `refused: true` / `non_evidence: true` and **never** `journey-evidence.json`.
Success runs write `journey-evidence.json` and **never** `refusal.json`. Always-
allowed ops artifacts (`cleanup.json`, `ops-database-gate.txt`,
`ops-source-after-gate.json`, `ops-schema-receipt.json`, `ops-sql-green.txt`)
are labeled `ops: true` / `non_evidence: true` via inline keys (cleanup.json)
or **sibling `.ops.json` markers** (the other four, which are text- or
externally-written formats). They are never journey evidence.
SCRATCH reuse unlinks the opposite marker (`refusal.json` ↔ `journey-evidence.json`)
on each path so a reused directory cannot hold both.
**L4 — interrupted runs:** the refusal path catches `BaseException` (including
`KeyboardInterrupt` and `SystemExit`), writes a tagged `refusal.json`, and
re-raises — an interrupted run must never leave `cleanup.json` with neither a
refusal nor an evidence marker. The `finally` cleanup readback still runs.
Stages that are not implemented raise `JourneyRefusal` and refuse. The runner
is a one-shot journey runner: it binds the exact head + review receipt and must
not be reused across heads without a new receipt.

**M10 — snapshot-vs-clean-tree ordering:** operator review output under
`.ai/reviews/` must be committed or gitignored **before** the journey run binds
the clean head. The source snapshot excludes `.ai/reviews/packets/`; the dirty
check does not. Commit packet output or add it to `.gitignore` before running.
