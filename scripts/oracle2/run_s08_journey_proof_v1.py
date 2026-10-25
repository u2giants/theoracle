"""One-shot S08 participation journey runner — sealed on PR #200 branch.

Binds the exact full 40-char HEAD at run time and a review receipt that names
that HEAD, this file's SHA-256, the plan SHA-256, the checker SHA-256 and the
evidence SHA-256, plus verdict APPROVE. Refuses without a precise
ai-task-gates check --before database ALLOW line. One fresh owned synthetic
Postgres (oracle2-synthetic-p24s08-journey-<unique>). Owned cleanup with
absence readback always — including pre-identity refusals.

Journey stages (invented data only):
  provision-capture-admission -> observe-audience -> host-control ->
  current-turn -> sender -> bytes-in receipt -> status/reconcile

There is NO Next browser enable/control web surface on this head and NO sealed
fake-Recall HTTPS owner. HTTP 200/201/429/5xx network negatives and
"exactly ONE network invocation" are UNPROVED and are not executed here.

FORBIDDEN network path (never call; runner refuses if RECALL_* env is set):
  exchange_provider_v1 / sendRecallChatMessage / recall.ts HTTPS POST
  (apps/workers/src/lib/meeting-participation.ts:44,
   apps/workers/src/lib/recall.ts:29-63).
The only allowed bytes-in path is the factory layer
(meeting_participation_v1.py receipt_v1, bytes-in / artifact-out).

Deadline / CAS / conflict policy (H-C):
  Every SQL entry enforces a <=30s absolute deadline
  (021_meeting_participation.sql:163; participation_authority_v1.py:216-221).
  Observations expire in <=30s (021_meeting_participation.sql:259).
  control / prepare / observe / claim all take CAS revisions. On head conflict,
  expired observation, or elapsed window: STOP. No transparent retry. Record
  the failing stage and leave UNKNOWN semantics. One shared monotonic budget
  (120s) covers the journey stages only; fixture/bootstrap setup sits OUTSIDE
  that budget, matching verify_workflow_integrity.py:384-386.

Migration inventory is the sealed SYNTHETIC_MIGRATIONS bootstrap
(001,002,004,006..014,017,018,019,020,021,022,023,027) — NOT a contiguous
001..014 chain. The runner calls bootstrap_canonical_test_schema and asserts
the sealed inventory and catalog; it never merely echoes a note.

Real Teams producer stays UNQUALIFIED. Business acceptance HELD.

This is a prepared one-shot skeleton: stages refuse until implemented and
reviewed. Offline checks only until a reviewed release. Do not invent a
production effect.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

# Repository root = two levels up from scripts/oracle2/.
ROOT = Path(__file__).resolve().parents[2]
# Unique per-run scratch; override only for offline checker isolation.
# SCRATCH must never live inside the repository (H-F/M-C).
SCRATCH_ENV = "ORACLE2_S08_JOURNEY_SCRATCH"
SHARED_BUDGET_S = 120
PER_REQUEST_S = 30
DOCKER_PROBE_TIMEOUT_S = 60
COMPOSE_PROJECT_PREFIX = "oracle2-synthetic-p24s08-journey"
WORKER_LABEL = "documentary-01"
# Sealed SYNTHETIC_MIGRATIONS inventory. The runner applies the sealed
# bootstrap and asserts equality; it never a custom contiguous 001..014 chain.
SEALED_MIGRATION_INVENTORY = (
    "001_foundation.sql",
    "002_pilot.sql",
    "004_workflow_integrity.sql",
    "006_hosting_gateway_authority.sql",
    "007_hosting_candidate_permissions.sql",
    "008_hosting_runtime_permissions.sql",
    "009_hosting_result_permissions.sql",
    "010_hosting_job_permissions.sql",
    "011_hosting_source_processing_permissions.sql",
    "012_processing_compiler_capabilities.sql",
    "013_processing_purpose_permissions.sql",
    "014_replacement_source_custody.sql",
    "017_processing_model_history.sql",
    "018_original_review_reading_input.sql",
    "019_employee_conversations.sql",
    "020_meeting_capture.sql",
    "021_meeting_participation.sql",
    "022_consolidated_answer_delivery.sql",
    "023_maintained_research.sql",
    "027_legacy_migration.sql",
)
SEALED_MIGRATION_INVENTORY_NOTE = ",".join(
    name.split("_", 1)[0] for name in SEALED_MIGRATION_INVENTORY
)
FULL_SHA40 = re.compile(r"^[0-9a-f]{40}$")
# Precise ALLOW token: a whole line that is exactly ALLOW, optionally with a
# `gate: ` prefix. Substring match is forbidden (H-G).
ALLOW_LINE = re.compile(r"^\s*(?:gate:\s*)?ALLOW\s*$", re.MULTILINE)
# Worktree-content suffixes and lock/compose names the DB image depends on (H-F).
SOURCE_SUFFIXES = (".py", ".ts", ".tsx", ".sql", ".json", ".md", ".yaml", ".yml")
SOURCE_BASENAMES = frozenset(
    {
        "compose.yaml",
        "compose.yml",
        "docker-compose.yaml",
        "docker-compose.yml",
        "pnpm-lock.yaml",
        "package-lock.json",
        "yarn.lock",
        "poetry.lock",
        "uv.lock",
        "Cargo.lock",
        "go.sum",
    }
)
# Forbidden network entry points (H-E). Named so a stage implementer cannot
# reach them by accident.
FORBIDDEN_NETWORK_PATHS = (
    "exchange_provider_v1",
    "sendRecallChatMessage",
    "recall.ts HTTPS POST",
)
RECALL_ENV_PREFIX = "RECALL_"


class JourneyRefusal(RuntimeError):
    """Fail-closed refusal. Carries the failing stage for the outcome record."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scratch() -> Path:
    """Unique per-run scratch, never inside the repository (M-C)."""
    raw = os.environ.get(SCRATCH_ENV)
    if raw:
        scratch = Path(raw).resolve()
    else:
        base = Path(os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp")
        scratch = (base / f"oracle-parent24-s08-journey-{uuid4().hex}").resolve()
    try:
        scratch.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise JourneyRefusal(
            "SCRATCH must not live inside the repository worktree (M-C)"
        )
    scratch.mkdir(mode=0o700, parents=True, exist_ok=True)
    return scratch


def _monotonic_end(seconds: float) -> float:
    if type(seconds) not in (int, float) or seconds <= 0:
        raise JourneyRefusal("positive budget seconds required")
    return time.monotonic() + float(seconds)


@contextmanager
def _request_fence_v1(original_monotonic_end: float):
    """Same shape as the sealed _request_fence_v1 (H-H).

    Compares a monotonic deadline; never a wall-clock label.
    """
    if type(original_monotonic_end) is not float:
        raise JourneyRefusal("exact original monotonic fence required")
    if original_monotonic_end <= time.monotonic():
        raise JourneyRefusal("shared budget already elapsed; STOP")
    try:
        yield
    finally:
        pass


def _budget_check(end: float, stage: str) -> None:
    if time.monotonic() >= end:
        raise JourneyRefusal(f"shared monotonic budget elapsed at stage {stage}; STOP")


def require_recall_env_absent() -> None:
    """Refuse if any RECALL_* credential/env is present (H-E).

    The journey must never reach exchange_provider_v1 / sendRecallChatMessage /
    recall.ts HTTPS POST. The only allowed path is the factory bytes-in layer
    (meeting_participation_v1.py:291 receipt_v1).
    """
    present = sorted(k for k in os.environ if k.startswith(RECALL_ENV_PREFIX))
    if present:
        raise JourneyRefusal(
            "RECALL_* environment present — forbidden network path "
            f"({', '.join(FORBIDDEN_NETWORK_PATHS)}) must stay unreachable; "
            f"unset: {', '.join(present)}"
        )


def require_head() -> str:
    """Exact full 40-char clean HEAD; never a short SHA, never a dirty tree."""
    git = _tool_identity("git")
    head = subprocess.check_output(
        [git["path"], "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if not FULL_SHA40.fullmatch(head):
        raise JourneyRefusal(f"HEAD is not a full 40-char SHA: {head!r}")
    dirty = subprocess.check_output(
        [git["path"], "status", "--porcelain"], cwd=ROOT, text=True
    ).strip()
    if dirty:
        raise JourneyRefusal(f"worktree dirty at bind head:\n{dirty}")
    return head


def _tool_identity(name: str) -> dict:
    """Resolve a tool to an absolute path and record its identity (H-G)."""
    path = shutil.which(name)
    if not path:
        raise JourneyRefusal(f"required tool not on PATH: {name}")
    resolved = str(Path(path).resolve())
    version = ""
    try:
        version = subprocess.check_output(
            [resolved, "--version"], text=True, stderr=subprocess.STDOUT
        ).splitlines()[0][:200]
    except (subprocess.CalledProcessError, OSError, IndexError):
        version = "(--version unavailable)"
    return {"name": name, "path": resolved, "version": version}


def _receipt_stat_ok(path: Path) -> dict:
    """uid/mode/nlink/O_NOFOLLOW checks in the shape of test_canonical_schema.py:96-114.

    os.getuid is absent on Windows; there the uid check is skipped and the
    limit is recorded explicitly (H-J).
    """
    checks: dict[str, object] = {"o_nofollow": True, "uid_checked": False}
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        checks["is_regular"] = stat.S_ISREG(before.st_mode)
        checks["nlink_is_1"] = before.st_nlink == 1
        checks["mode_no_group_other"] = (before.st_mode & 0o077) == 0
        checks["size_le_4096"] = before.st_size <= 4096
        if hasattr(os, "getuid"):
            checks["uid_checked"] = True
            checks["uid_is_self"] = before.st_uid == os.getuid()
        else:
            checks["uid_is_self"] = None
            checks["uid_limit"] = (
                "os.getuid absent on this host (Windows); uid ownership of the "
                "procedural receipt cannot be enforced here"
            )
        raw = os.read(fd, before.st_size + 1)
        identity = lambda s: (
            s.st_dev,
            s.st_ino,
            s.st_mode,
            s.st_uid,
            s.st_nlink,
            s.st_size,
            s.st_mtime_ns,
            s.st_ctime_ns,
        )
        checks["stat_stable"] = identity(before) == identity(os.fstat(fd))
    finally:
        os.close(fd)
    checks["passed"] = bool(
        checks.get("is_regular")
        and checks.get("nlink_is_1")
        and checks.get("mode_no_group_other")
        and checks.get("size_le_4096")
        and checks.get("stat_stable")
        and (checks.get("uid_is_self") in (True, None))
    )
    return checks


def require_review_receipt(head: str, scratch: Path) -> dict:
    """Exact-head review receipt must already exist; never manufacture one.

    Procedural trust model (H-J): the receipt is an operator-minted JSON file
    under SCRATCH. It is not a cryptographic authority. It must bind the exact
    full 40-char head plus the SHA-256 of the runner, plan, checker and
    evidence artifacts, and verdict APPROVE. Any mismatch or absence fails
    closed. File-mode checks follow test_canonical_schema.py:96-114 where the
    host supports them.
    """
    receipt_path = scratch / "review-receipt.json"
    if not receipt_path.is_file():
        raise JourneyRefusal(
            "review-receipt.json absent — release requires an independent review "
            "receipt binding exact full 40-char head + runner/plan/checker/evidence "
            "SHA-256 + verdict APPROVE. STOP. Do not invent a production effect."
        )
    stat_checks = _receipt_stat_ok(receipt_path)
    if not stat_checks["passed"]:
        raise JourneyRefusal(f"review receipt file checks failed: {stat_checks}")
    receipt = json.loads(receipt_path.read_text())
    if not isinstance(receipt, dict):
        raise JourneyRefusal("review receipt must be a JSON object")
    got_head = receipt.get("head")
    if not isinstance(got_head, str) or not FULL_SHA40.fullmatch(got_head):
        raise JourneyRefusal(f"review receipt head is not a full 40-char SHA: {got_head!r}")
    if got_head != head:
        raise JourneyRefusal(
            f"review receipt head mismatch: receipt={got_head} current={head}"
        )
    bindings = {
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "plan_sha256": sha256_file(
            ROOT / "docs/verification/oracle2/s08-journey-proof-plan.md"
        ),
        "checker_sha256": sha256_file(
            ROOT / "scripts/oracle2/check_s08_journey_skeleton_v1.py"
        ),
        "evidence_sha256": sha256_file(
            ROOT / "docs/verification/oracle2/s08-compose-81742134-evidence.md"
        ),
    }
    for key, actual in bindings.items():
        if receipt.get(key) != actual:
            raise JourneyRefusal(
                f"review receipt {key} mismatch: receipt={receipt.get(key)!r} actual={actual}"
            )
    if receipt.get("verdict") != "APPROVE":
        raise JourneyRefusal(f"review verdict is {receipt.get('verdict')!r}, not APPROVE")
    return {"receipt": receipt, "stat_checks": stat_checks, "bindings": bindings}


def require_database_gate(scratch: Path, tools: dict) -> str:
    """ai-task-gates check --before database must print a precise ALLOW line (H-G)."""
    gate = tools["ai-task-gates"]
    out = subprocess.check_output(
        [gate["path"], "check", "--before", "database"],
        cwd=ROOT,
        text=True,
        stderr=subprocess.STDOUT,
    )
    if not ALLOW_LINE.search(out):
        # Persist only after the check, and never as forensic evidence (M-D).
        raise JourneyRefusal(f"database gate did not print a precise ALLOW line:\n{out}")
    (scratch / "database-gate.txt").write_text(out)
    return out


def source_snapshot() -> dict[str, str]:
    """Hash worktree file CONTENTS (sha256 of bytes) + mode (H-F).

    Not git ls-files index blobs: an edit after bind must be visible. Includes
    compose.yaml and lockfiles the DB image depends on. Sealed blob pins stay
    git-blob (git show HEAD:path | sha256sum); this snapshot is for worktree
    mutation detection only.
    """
    snap: dict[str, str] = {}
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith((".git/", "node_modules/", ".ai/reviews/packets/")):
            continue
        name = path.name
        if name not in SOURCE_BASENAMES and path.suffix not in SOURCE_SUFFIXES:
            continue
        try:
            st = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        snap[rel] = f"sha256:{digest}:mode:{st.st_mode & 0o777:o}"
    return snap


def assert_sealed_inventory() -> dict:
    """Assert the sealed SYNTHETIC_MIGRATIONS inventory without importing psycopg (H-I).

    Parses the tuple from verify_workflow_integrity.py the same way
    canonical_synthetic_migrations does. The live bootstrap assertion happens
    later inside main() via bootstrap_canonical_test_schema / _inventory_digest /
    _catalog. This helper never merely echoes SEALED_MIGRATION_INVENTORY_NOTE.
    """
    import ast

    tree = ast.parse((ROOT / "scripts/oracle2/verify_workflow_integrity.py").read_text())
    observed: tuple[str, ...] | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "SYNTHETIC_MIGRATIONS" for t in node.targets
        ):
            observed = tuple(ast.literal_eval(node.value))
            break
    if observed is None:
        raise JourneyRefusal("SYNTHETIC_MIGRATIONS tuple not found in verifier")
    expected = tuple(SEALED_MIGRATION_INVENTORY)
    if observed != expected:
        raise JourneyRefusal(
            "sealed migration inventory drift: "
            f"expected={expected!r} observed={observed!r}"
        )
    return {
        "inventory": list(observed),
        "inventory_count": len(observed),
        "omits": ["003", "005"],
        "includes_extra": ["017", "018", "019", "022", "023", "027"],
    }


# ---------------------------------------------------------------------------
# Journey stages. Signatures carry the plan's bindings (H-D) so implementation
# does not churn the receipt-bound runner SHA.
# ---------------------------------------------------------------------------


def stage_provision_capture_admission(bindings: dict, deadline_s: int) -> dict:
    """Stage 0a: capture / admission provisioning precondition (H-B).

    Cites the SQL fixture construction at
    test_meeting_participation_sql.py:69-125: appointments, capture
    admissions, roles/grants, invite -> retain_ingress -> finalize, and the
    host/sender/observer participation admissions. Without this stage the
    later stages have no admission linkage.
    """
    raise JourneyRefusal(
        "capture/admission provisioning not released; journey stage 0a UNPROVEN "
        "(invite -> retain_ingress -> finalize; host/sender/observer admissions)"
    )


def stage_observe_audience(bindings: dict, deadline_s: int) -> dict:
    """Stage 0b: observer / audience observation (H-A).

    observe_audience_v1 / invent_observation pattern from
    test_meeting_participation_sql.py:128-136. Produces the observation_id
    that stage 1 host enable requires (participation_authority_v1.py:458;
    meeting_participation_v1.py:201-202 derives it from current SQL status).
    Observation expiry <=30s (021_meeting_participation.sql:259).
    """
    raise JourneyRefusal(
        "observer/audience observation not released; journey stage 0b UNPROVEN "
        "(observe_audience_v1 / invent_observation; observation_id required by enable)"
    )


def stage_host_control(bindings: dict, deadline_s: int) -> dict:
    """Stage 1: mTLS host enable/control at /v1/replacement/meetings/participation/control.

    bindings carry: meeting selector, CAS expected_head, operation UUID,
    and the observation_id from stage 0b. Server-derived principal. No Next
    browser enable/control web surface exists on this head — that is a named
    remaining gate, not this stage. UI-only screenshots and fixture auth are
    NOT this stage. Deadline <=30s. On CAS conflict: STOP, no transparent
    retry, leave UNKNOWN.
    """
    raise JourneyRefusal(
        "host-control mTLS journey adapter not released; journey stage 1 UNPROVEN "
        "(no Next browser surface on head; see s08-journey-proof-plan.md)"
    )


def stage_current_turn(bindings: dict, deadline_s: int) -> dict:
    """Stage 2: S07 read_current_participant_turn_v1 / meeting_capture_current_turn_v1.

    bindings carry: exact finalized ingress event UUID + epoch + raw/normalized
    SHA binding. Unknown/Oracle speaker never produces a turn.
    """
    raise JourneyRefusal(
        "current-turn live consumer not released; journey stage 2 UNPROVEN"
    )


def stage_sender(bindings: dict, deadline_s: int) -> dict:
    """Stage 3: prepare_v1 + claim_v1 under CURRENT enabled generation.

    bindings carry: CAS expected_revision, intent_id, operation UUIDs, and
    SAME-admission linkage. Body only after commit+close+fresh own current
    status. No transparent retry. Lost claim = UNKNOWN.
    """
    raise JourneyRefusal(
        "sender live path not released; journey stage 3 UNPROVEN"
    )


def stage_receipt_bytes_in(bindings: dict, deadline_s: int) -> dict:
    """Stage 4: bytes-in receipt path (meeting_participation_v1.receipt_v1:291).

    bindings carry: raw wire bytes, claim_event_id, operation UUID, SAME
    admission linkage. Injects bounded raw wire bytes into the sealed receipt
    path as test_meeting_participation_sql.py does. The ONLY allowed path is
    the factory bytes-in layer. There is NO fake-Recall HTTPS owner and the
    forbidden network path (exchange_provider_v1 / sendRecallChatMessage /
    recall.ts HTTPS POST) is never called. HTTP 200/201/429/5xx network
    negatives and exactly-one-network-invocation are UNPROVED.
    """
    raise JourneyRefusal(
        "bytes-in receipt journey adapter not released; journey stage 4 UNPROVEN "
        "(factory bytes-in only; no fake-Recall HTTPS owner; network negatives UNPROVED)"
    )


def stage_status_reconcile(bindings: dict, deadline_s: int) -> dict:
    """Stage 5: status_v1 readback + forensic receipt + read-only reconcile.

    bindings carry: intent_id, claim_event_id, admission linkage. Ambiguous
    outcome UNKNOWN. Receipt never reauthorizes send. ACK is never a visible
    message or provider idempotency.
    """
    raise JourneyRefusal(
        "status/reconcile journey adapter not released; journey stage 5 UNPROVEN"
    )


def _owned_absence_readback(project: str) -> dict:
    """Always callable. Proves absence of exact owned synthetic residue (M-C)."""
    docker = _tool_identity("docker")
    remains = {}
    for kind, cmd in (
        ("containers", ["ps", "-aq"]),
        ("networks", ["network", "ls", "-q"]),
        ("volumes", ["volume", "ls", "-q"]),
    ):
        try:
            out = subprocess.check_output(
                [docker["path"], *cmd, "--filter", f"label=com.docker.compose.project={project}"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=DOCKER_PROBE_TIMEOUT_S,
            )
            remains[kind] = bool(out.strip())
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            remains[kind] = f"probe-failed:{type(exc).__name__}"
    absent = all(v is False for v in remains.values())
    return {"project": project, "remaining": remains, "absent": absent}


def _write_refusal(scratch: Path, reason: str, stage: str | None, head: str | None) -> None:
    """Refused runs write ONLY a refusal marker — never forensic evidence (M-D)."""
    payload = {
        "refused": True,
        "non_evidence": True,
        "reason": str(reason)[:2000],
        "failing_stage": stage,
        "head": head,
    }
    (scratch / "refusal.json").write_text(json.dumps(payload, sort_keys=True) + "\n")


def main() -> int:
    os.umask(0o077)
    scratch = _scratch()
    project = f"{COMPOSE_PROJECT_PREFIX}-{uuid4().hex[:8]}"  # unique per run (M-C)
    head: str | None = None
    failing_stage: str | None = None
    identity = None
    try:
        require_recall_env_absent()  # H-E: refuse before any other work
        tools = {
            name: _tool_identity(name) for name in ("git", "ai-task-gates", "docker")
        }
        head = require_head()
        inventory = assert_sealed_inventory()  # H-I before any DB
        before = source_snapshot()  # H-F worktree bytes + mode
        receipt = require_review_receipt(head, scratch)  # H-J
        require_database_gate(scratch, tools)  # H-G precise ALLOW
        if before != source_snapshot():
            raise JourneyRefusal("source changed during gate; STOP")
        (scratch / "source-after-gate.json").write_text(
            json.dumps(source_snapshot(), sort_keys=True) + "\n"
        )

        # Bootstrap sits OUTSIDE the shared 120s budget, matching
        # verify_workflow_integrity.py:384-386 (H-H). The shared budget covers
        # journey stages only.
        budget_end = _monotonic_end(SHARED_BUDGET_S)

        # One fresh owned synthetic PG via the sealed fixture. The sealed
        # bootstrap inventory is used and asserted — never a custom contiguous
        # 001..014 chain.
        sys.path.insert(0, str(ROOT))
        from dev.oracle2.test_worker_postgres_fixture import worker_postgres

        with worker_postgres(
            {**os.environ, "COMPOSE_PROJECT_NAME": project},
            scratch / "worker",
            WORKER_LABEL,
        ) as (tls, identity):
            assert identity["project"].startswith(project)
            assert identity.get("synthetic_only") is True
            # H-I: real bootstrap + inventory/catalog assertion on the live DB.
            from dev.oracle2.test_canonical_schema import (
                _catalog,
                _inventory_digest,
                bootstrap_canonical_test_schema,
                canonical_synthetic_migrations,
            )
            import psycopg

            target = os.environ.get("ORACLE2_TEST_ADMIN_URL") or tls
            schema_receipt = (scratch / "schema-receipt.json").resolve()
            bootstrap_canonical_test_schema(
                target, container_id=identity["container_id"], receipt_path=schema_receipt
            )
            files = canonical_synthetic_migrations()
            with psycopg.connect(target) as connection:
                catalog = _catalog(connection)
            if tuple(p.name for p in files) != tuple(SEALED_MIGRATION_INVENTORY):
                raise JourneyRefusal("sealed inventory names drift after bootstrap")
            if _inventory_digest(files) is None:
                raise JourneyRefusal("sealed inventory digest unavailable after bootstrap")

            stages = {
                "provision_capture_admission": "UNPROVEN",
                "observe_audience": "UNPROVEN",
                "host_control": "UNPROVEN",
                "current_turn": "UNPROVEN",
                "sender": "UNPROVEN",
                "receipt_bytes_in": "UNPROVEN",
                "status_reconcile": "UNPROVEN",
            }
            # Stages refuse until implemented; the budget fence is armed first.
            with _request_fence_v1(budget_end):
                for name, call in (
                    ("provision_capture_admission", lambda: stage_provision_capture_admission({}, PER_REQUEST_S)),
                    ("observe_audience", lambda: stage_observe_audience({}, PER_REQUEST_S)),
                    ("host_control", lambda: stage_host_control({}, PER_REQUEST_S)),
                    ("current_turn", lambda: stage_current_turn({}, PER_REQUEST_S)),
                    ("sender", lambda: stage_sender({}, PER_REQUEST_S)),
                    ("receipt_bytes_in", lambda: stage_receipt_bytes_in({"raw_wire": b""}, PER_REQUEST_S)),
                    ("status_reconcile", lambda: stage_status_reconcile({}, PER_REQUEST_S)),
                ):
                    failing_stage = name
                    _budget_check(budget_end, name)
                    call()
                    stages[name] = "PROVEN"
                    failing_stage = None

            # Success-path evidence only (M-D). Never written on refusal.
            evidence = {
                "refused": False,
                "head": head,
                "review_receipt_sha256": sha256_file(scratch / "review-receipt.json"),
                "runner_sha256": sha256_file(Path(__file__).resolve()),
                "plan_sha256": receipt["bindings"]["plan_sha256"],
                "checker_sha256": receipt["bindings"]["checker_sha256"],
                "evidence_sha256": receipt["bindings"]["evidence_sha256"],
                "sealed_migration_inventory": list(SEALED_MIGRATION_INVENTORY),
                "inventory_assertion": inventory,
                "catalog_digest": hashlib.sha256(
                    json.dumps(catalog, sort_keys=True).encode()
                ).hexdigest()
                if isinstance(catalog, (list, tuple))
                else str(catalog),
                "stages": stages,
                "tools": tools,
                "limits": {
                    "shared_budget_s": SHARED_BUDGET_S,
                    "per_request_s": PER_REQUEST_S,
                    "bootstrap_inside_shared_budget": False,
                    "budget_mechanism": "monotonic (_request_fence_v1 shape)",
                },
                "deadline_cas_policy": {
                    "max_deadline_s": 30,
                    "observation_expiry_max_s": 30,
                    "on_conflict": "STOP; record failing stage; leave UNKNOWN; no transparent retry",
                },
                "forbidden_network_paths": list(FORBIDDEN_NETWORK_PATHS),
                "unproved": [
                    "http_201_429_5xx_network_negatives",
                    "exactly_one_network_invocation_across_restart_repeat",
                    "host_disable_between_prepare_and_claim_zero_network",
                    "observation_commit_ack_loss_journey_sequence",
                    "permission_expiry_before_after_close_matrix_journey",
                    "next_browser_enable_control_web_surface",
                    "w10_same_worker_fit_measurement",
                ],
                "business_acceptance": "HELD",
                "real_teams_producer": "UNQUALIFIED",
            }
            (scratch / "journey-evidence.json").write_text(
                json.dumps(evidence, sort_keys=True) + "\n"
            )
            raise JourneyRefusal(
                "skeleton only — stage implementations absent; no journey effect performed"
            )
    except JourneyRefusal as exc:
        _write_refusal(scratch, str(exc), failing_stage, head)
        raise
    except Exception as exc:  # noqa: BLE001 — any failure is a refusal
        _write_refusal(scratch, f"{type(exc).__name__}: {exc}", failing_stage, head)
        raise
    finally:
        # Cleanup readback ALWAYS, even pre-identity (M-C). Project name is
        # generated before the try so residue can be named on every path.
        try:
            readback = _owned_absence_readback(project)
            (scratch / "cleanup.json").write_text(
                json.dumps(readback, sort_keys=True) + "\n"
            )
            if not readback["absent"] and identity is not None:
                raise JourneyRefusal(
                    "exact owned synthetic cleanup incomplete; absence not proven; STOP"
                )
        except JourneyRefusal:
            raise
        except Exception:
            # A cleanup probe failure on a pre-identity refusal is recorded but
            # must not mask the original refusal.
            pass


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
