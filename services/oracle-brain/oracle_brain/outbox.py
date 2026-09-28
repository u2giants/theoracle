"""Transactional acceptance, replayable projection and authenticated receipts."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from .contracts import ProjectionReceipt
from .models import ProjectionEvent


def enqueue_accepted(database_url: str, *, workspace_id: UUID, assertion_id: UUID,
                     revision: int, payload: dict, operation: str = "project") -> UUID:
    """Accept the revision and enqueue its projection in one Postgres commit."""
    if revision < 1 or operation not in {"project", "withdraw"}:
        raise ValueError("invalid revision or operation")
    event_id = uuid4()
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            # Serialize even the first revision, when no accepted row exists yet.
            # A hash collision only serializes unrelated assertions.
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"{workspace_id}:{assertion_id}",),
            )
            row = connection.execute(
                """SELECT revision FROM oracle2.accepted
                   WHERE workspace_id=%s AND assertion_id=%s FOR UPDATE""",
                (workspace_id, assertion_id),
            ).fetchone()
            if row and row[0] >= revision:
                if row[0] == revision:
                    prior = connection.execute(
                        """SELECT event_id,operation,payload FROM oracle2.outbox
                           WHERE workspace_id=%s AND assertion_id=%s AND revision=%s""",
                        (workspace_id, assertion_id, revision),
                    ).fetchone()
                    if prior:
                        if prior[1] != operation or prior[2] != payload:
                            raise ValueError("same revision has different accepted content")
                        return prior[0]
                raise ValueError("revision must increase")
            connection.execute(
                """INSERT INTO oracle2.accepted(workspace_id,assertion_id,revision,status,payload)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT(workspace_id,assertion_id) DO UPDATE
                   SET revision=EXCLUDED.revision,status=EXCLUDED.status,payload=EXCLUDED.payload""",
                (workspace_id, assertion_id, revision,
                 "active" if operation == "project" else "withdrawn", Jsonb(payload)),
            )
            connection.execute(
                """INSERT INTO oracle2.outbox
                   (event_id,workspace_id,assertion_id,revision,operation,payload)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (event_id, workspace_id, assertion_id, revision, operation, Jsonb(payload)),
            )
    return event_id


# Events that fail this many leases stop being leased (dead-lettered) and need
# operator attention instead of being retried forever.
MAX_ATTEMPTS = 10


def lease_next(database_url: str, *, lease_seconds: int = 60,
               allowed_workspaces: frozenset[str] | None = None) -> ProjectionEvent | None:
    if allowed_workspaces is not None and not allowed_workspaces:
        return None
    scope_clause = (" AND workspace_id = ANY(%s::uuid[])"
                    if allowed_workspaces is not None else "")
    params = ((MAX_ATTEMPTS, [UUID(value) for value in allowed_workspaces], lease_seconds)
              if allowed_workspaces is not None else (MAX_ATTEMPTS, lease_seconds))
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            f"""WITH next AS (
                 SELECT event_id FROM oracle2.outbox
                 WHERE delivered_at IS NULL AND (lease_until IS NULL OR lease_until<now())
                 AND attempts < %s
                 {scope_clause}
                 ORDER BY revision,event_id FOR UPDATE SKIP LOCKED LIMIT 1
               )
               UPDATE oracle2.outbox o SET attempts=attempts+1,
                 lease_until=now()+(%s * interval '1 second')
               FROM next WHERE o.event_id=next.event_id
               RETURNING o.event_id,o.workspace_id,o.assertion_id,o.revision,
                         o.operation,o.payload,o.attempts""",
            params,
        ).fetchone()
    return ProjectionEvent(*row) if row else None


def receipt_signature(secret: bytes, *, event_id: UUID, workspace_id: UUID,
                      assertion_id: UUID, revision: int, operation: str,
                      projector_id: str, applied_at: datetime) -> str:
    canonical = json.dumps([str(event_id), str(workspace_id), str(assertion_id),
                            revision, operation, projector_id,
                            applied_at.isoformat()], separators=(",", ":"))
    return hmac.new(secret, canonical.encode(), hashlib.sha256).hexdigest()


def mark_delivered(database_url: str, *, event_id: UUID, receipt: ProjectionReceipt,
                   secret: bytes) -> None:
    """Reject forged, stale or mismatched receipts; receipt and delivery are atomic."""
    if len(secret) < 32:
        raise ValueError("projection signing key must have at least 32 bytes")
    expected = receipt_signature(secret, event_id=event_id,
                                 workspace_id=receipt.workspace_id,
                                 assertion_id=receipt.assertion_id,
                                 revision=receipt.revision,
                                 operation=receipt.operation,
                                 projector_id=receipt.projector_id,
                                 applied_at=receipt.applied_at)
    if not hmac.compare_digest(expected, receipt.signature):
        raise PermissionError("forged projection receipt")
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            row = connection.execute(
                """SELECT workspace_id,assertion_id,revision,operation,delivered_at
                   FROM oracle2.outbox WHERE event_id=%s FOR UPDATE""",
                (event_id,),
            ).fetchone()
            if row is None or row[:4] != (receipt.workspace_id, receipt.assertion_id,
                                           receipt.revision, receipt.operation):
                raise PermissionError("receipt does not match outbox event")
            latest = connection.execute(
                """SELECT revision FROM oracle2.accepted
                   WHERE workspace_id=%s AND assertion_id=%s""",
                (receipt.workspace_id, receipt.assertion_id),
            ).fetchone()
            if latest is None or receipt.revision > latest[0]:
                raise PermissionError("receipt revision exceeds accepted revision")
            connection.execute(
                """INSERT INTO oracle2.projection_receipts
                   (event_id,workspace_id,assertion_id,revision,operation,
                    projector_id,signature,applied_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (event_id, receipt.workspace_id, receipt.assertion_id,
                 receipt.revision, receipt.operation, receipt.projector_id,
                 receipt.signature, receipt.applied_at),
            )
            connection.execute(
                "UPDATE oracle2.outbox SET delivered_at=now(),lease_until=NULL WHERE event_id=%s",
                (event_id,),
            )


def make_receipt(event: ProjectionEvent, secret: bytes, projector_id: str) -> ProjectionReceipt:
    applied_at = datetime.now(timezone.utc)
    return ProjectionReceipt(
        contract_version=1,
        workspace_id=event.workspace_id, assertion_id=event.assertion_id,
        revision=event.revision, operation=event.operation, projector_id=projector_id,
        applied_at=applied_at,
        signature=receipt_signature(secret, event_id=event.event_id,
                                    workspace_id=event.workspace_id,
                                    assertion_id=event.assertion_id,
                                    revision=event.revision,
                                    operation=event.operation,
                                    projector_id=projector_id,
                                    applied_at=applied_at),
    )
