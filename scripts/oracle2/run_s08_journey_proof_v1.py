"""One-shot S08 participation journey runner — sealed on PR #200 branch.

Binds the exact full 40-char HEAD at run time and a review receipt that names
that HEAD, this file's SHA-256, and verdict APPROVE. Refuses without
ai-task-gates check --before database ALLOW. One fresh owned synthetic Postgres
(oracle2-synthetic-p24s08-journey-*). Owned cleanup with absence readback.

Journey stages (invented data only):
  host-control -> current-turn -> sender -> bytes-in receipt -> status/reconcile

There is NO Next browser enable/control web surface on this head and NO sealed
fake-Recall HTTPS owner. HTTP 200/201/429/5xx network negatives and
"exactly ONE network invocation" are UNPROVED and are not executed here.

Migration inventory is the sealed SYNTHETIC_MIGRATIONS bootstrap
(001,002,004,006..014,017,018,019,020,021,022,023,027) — NOT a contiguous
001..014 chain. Real Teams producer stays UNQUALIFIED. Business acceptance HELD.

This is a prepared one-shot skeleton: stages refuse until implemented and
reviewed. Offline checks only until a reviewed release. Do not invent a
production effect.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

# Repository root = two levels up from scripts/oracle2/.
ROOT = Path(__file__).resolve().parents[2]
# Default scratch; override with ORACLE2_S08_JOURNEY_SCRATCH.
SCRATCH = Path(
    os.environ.get(
        "ORACLE2_S08_JOURNEY_SCRATCH",
        "/tmp/oracle-parent24-wy02uT/pr200-s08-journey-proof-01",
    )
)
SHARED_BUDGET_S = 120
PER_REQUEST_S = 30
COMPOSE_PROJECT_PREFIX = "oracle2-synthetic-p24s08-journey"
WORKER_LABEL = "documentary-01"
# Sealed SYNTHETIC_MIGRATIONS tail after the shared prefix. The runner applies
# the sealed bootstrap, never a custom contiguous 001..014 chain.
SEALED_MIGRATION_INVENTORY_NOTE = (
    "001,002,004,006,007,008,009,010,011,012,013,014,"
    "017,018,019,020,021,022,023,027"
)
FULL_SHA40 = re.compile(r"^[0-9a-f]{40}$")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_head() -> str:
    """Exact full 40-char clean HEAD; never a short SHA, never a dirty tree."""
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if not FULL_SHA40.fullmatch(head):
        raise RuntimeError(f"HEAD is not a full 40-char SHA: {head!r}")
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).strip()
    if dirty:
        raise RuntimeError(f"worktree dirty at bind head:\n{dirty}")
    return head


def require_review_receipt(head: str) -> dict:
    """Exact-head review receipt must already exist; never manufacture one.

    Receipt must bind: exact full 40-char head + this runner's SHA-256 + verdict
    APPROVE. Any mismatch or absence fails closed.
    """
    receipt_path = SCRATCH / "review-receipt.json"
    if not receipt_path.is_file():
        raise RuntimeError(
            "review-receipt.json absent — release requires an independent review "
            "receipt binding exact full 40-char head + this runner SHA-256 + "
            "verdict APPROVE. STOP. Do not invent a production effect."
        )
    receipt = json.loads(receipt_path.read_text())
    runner_sha = sha256_file(Path(__file__).resolve())
    got_head = receipt.get("head")
    if not isinstance(got_head, str) or not FULL_SHA40.fullmatch(got_head):
        raise RuntimeError(f"review receipt head is not a full 40-char SHA: {got_head!r}")
    if got_head != head:
        raise RuntimeError(
            f"review receipt head mismatch: receipt={got_head} current={head}"
        )
    if receipt.get("runner_sha256") != runner_sha:
        raise RuntimeError(
            "review receipt runner SHA-256 mismatch: receipt="
            f"{receipt.get('runner_sha256')!r} actual={runner_sha}"
        )
    if receipt.get("verdict") != "APPROVE":
        raise RuntimeError(f"review verdict is {receipt.get('verdict')!r}, not APPROVE")
    return receipt


def require_database_gate() -> str:
    """ai-task-gates check --before database must ALLOW before any DB work."""
    out = subprocess.check_output(
        ["ai-task-gates", "check", "--before", "database"],
        cwd=ROOT,
        text=True,
        stderr=subprocess.STDOUT,
    )
    SCRATCH.mkdir(mode=0o700, parents=True, exist_ok=True)
    (SCRATCH / "database-gate.txt").write_text(out)
    if "ALLOW" not in out:
        raise RuntimeError(f"database gate did not ALLOW:\n{out}")
    return out


def source_snapshot() -> dict[str, str]:
    """Git blob-oriented snapshot of owned source suffixes.

    Uses `git ls-files -s` blob SHAs where possible so CRLF working-tree bytes
    do not diverge from the sealed blob pin (H2). Falls back to file SHA only
    for untracked files that must not appear at a clean head.
    """
    lines = subprocess.check_output(
        ["git", "ls-files", "-s"], cwd=ROOT, text=True
    ).splitlines()
    snap: dict[str, str] = {}
    for line in lines:
        # mode SP sha SP stage TAB path
        meta, _, name = line.partition("\t")
        if not name:
            continue
        if Path(name).suffix not in (".py", ".ts", ".tsx", ".sql", ".json", ".md"):
            continue
        blob = meta.split()[1] if meta.split() else ""
        snap[name] = f"blob:{blob}"
    return snap


def stage_host_control(deadline_s: int) -> dict:
    """Stage 1: mTLS host enable/control at /v1/replacement/meetings/participation/control.

    Exact meeting selector + CAS. Server-derived principal. No Next browser
    enable/control web surface exists on this head — that is a named remaining
    gate, not this stage. UI-only screenshots and fixture auth are NOT this stage.
    """
    raise NotImplementedError(
        "host-control mTLS journey adapter not released; journey stage 1 UNPROVEN "
        "(no Next browser surface on head; see s08-journey-proof-plan.md)"
    )


def stage_current_turn(event_id: str, deadline_s: int) -> dict:
    """Stage 2: S07 read_current_participant_turn_v1 / meeting_capture_current_turn_v1.

    Exact finalized ingress event UUID + epoch + raw/normalized SHA binding.
    """
    raise NotImplementedError(
        "current-turn live consumer not released; journey stage 2 UNPROVEN"
    )


def stage_sender(claim_deadline_s: int) -> dict:
    """Stage 3: prepare_v1 + claim_v1 under CURRENT enabled generation.

    Body only after commit+close+fresh own current status. No transparent retry.
    """
    raise NotImplementedError(
        "sender live path not released; journey stage 3 UNPROVEN"
    )


def stage_receipt_bytes_in(raw_wire: bytes, deadline_s: int) -> dict:
    """Stage 4: bytes-in receipt path (meeting_participation_v1.receipt_v1).

    Injects bounded raw wire bytes into the sealed receipt path as
    test_meeting_participation_sql.py does. There is NO fake-Recall HTTPS owner.
    HTTP 200/201/429/5xx network negatives and exactly-one-network-invocation
    are UNPROVED and are not performed by this stage.
    """
    raise NotImplementedError(
        "bytes-in receipt journey adapter not released; journey stage 4 UNPROVEN "
        "(no fake-Recall HTTPS owner; network negatives UNPROVED)"
    )


def stage_status_reconcile(deadline_s: int) -> dict:
    """Stage 5: status_v1 readback + forensic receipt + read-only reconcile.

    Ambiguous outcome UNKNOWN. Receipt never reauthorizes send. ACK is never a
    visible message or provider idempotency.
    """
    raise NotImplementedError(
        "status/reconcile journey adapter not released; journey stage 5 UNPROVEN"
    )


def _owned_absence_readback(project: str) -> dict:
    remains = {
        kind: bool(
            subprocess.check_output(
                cmd
                + [
                    "--filter",
                    "label=com.docker.compose.project=" + project,
                ],
                text=True,
            ).strip()
        )
        for kind, cmd in (
            ("containers", ["docker", "ps", "-aq"]),
            ("networks", ["docker", "network", "ls", "-q"]),
            ("volumes", ["docker", "volume", "ls", "-q"]),
        )
    }
    absent = not any(remains.values())
    return {"project": project, "remaining": remains, "absent": absent}


def main() -> int:
    os.umask(0o077)
    SCRATCH.mkdir(mode=0o700, exist_ok=True)
    head = require_head()
    before = source_snapshot()
    (SCRATCH / "source-before-gate.json").write_text(
        json.dumps(before, sort_keys=True) + "\n"
    )
    receipt = require_review_receipt(head)
    require_database_gate()
    if before != source_snapshot():
        raise RuntimeError("source changed during gate; STOP")
    (SCRATCH / "source-after-gate.json").write_text(
        json.dumps(source_snapshot(), sort_keys=True) + "\n"
    )
    identity = None
    try:
        # One fresh owned synthetic PG via the sealed fixture. The sealed
        # bootstrap inventory is used — never a custom contiguous 001..014 chain.
        sys.path.insert(0, str(ROOT))
        from dev.oracle2.test_worker_postgres_fixture import worker_postgres

        project = f"{COMPOSE_PROJECT_PREFIX}-{uuid4().hex[:8]}"
        with worker_postgres(
            {**os.environ, "COMPOSE_PROJECT_NAME": project},
            SCRATCH / "worker",
            WORKER_LABEL,
        ) as (tls, identity):
            assert identity["project"].startswith(project)
            assert identity.get("synthetic_only") is True
            evidence = {
                "head": head,
                "review_receipt_sha256": sha256_file(SCRATCH / "review-receipt.json"),
                "runner_sha256": sha256_file(Path(__file__).resolve()),
                "sealed_migration_inventory": SEALED_MIGRATION_INVENTORY_NOTE,
                "stages": {
                    "host_control": "UNPROVEN",
                    "current_turn": "UNPROVEN",
                    "sender": "UNPROVEN",
                    "receipt_bytes_in": "UNPROVEN",
                    "status_reconcile": "UNPROVEN",
                },
                "limits": {
                    "shared_budget_s": SHARED_BUDGET_S,
                    "per_request_s": PER_REQUEST_S,
                },
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
            (SCRATCH / "journey-evidence.json").write_text(
                json.dumps(evidence, sort_keys=True) + "\n"
            )
            raise RuntimeError(
                "skeleton only — stage implementations absent; no journey effect performed"
            )
    finally:
        if identity:
            readback = _owned_absence_readback(identity["project"])
            (SCRATCH / "cleanup.json").write_text(
                json.dumps(readback, sort_keys=True) + "\n"
            )
            if not readback["absent"]:
                raise RuntimeError(
                    "exact owned synthetic cleanup incomplete; absence not proven; STOP"
                )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
