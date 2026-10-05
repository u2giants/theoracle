"""Knowledge-level authority: draft correction and transactional scoped confirmation."""

from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb


def _lock(connection, workspace_id: UUID) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtext(%s))",
        (f"oracle2-authz:{workspace_id}",),
    )


def _has_authority_conn(connection, workspace_id: UUID, actor_id: UUID, scope: str) -> bool:
    row = connection.execute(
        """WITH RECURSIVE lineage AS (
             SELECT a.appointment_id AS start_id,a.appointment_id,a.parent_id,
                    a.revoked_at,a.expires_at,a.scope,a.actor_id,a.workspace_id,1 AS depth
             FROM oracle2.appointments a
             WHERE a.workspace_id=%s AND a.actor_id=%s
               AND a.scope IN (%s,'root')
             UNION ALL
             SELECT l.start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,
                    p.scope,p.actor_id,p.workspace_id,l.depth+1
             FROM oracle2.appointments p JOIN lineage l ON l.parent_id=p.appointment_id
             WHERE l.depth<16 AND p.workspace_id=l.workspace_id
           )
           SELECT EXISTS (
             SELECT 1 FROM lineage GROUP BY start_id
             HAVING bool_and(revoked_at IS NULL AND
                             (expires_at IS NULL OR expires_at>now()))
                AND bool_or(scope='root' AND parent_id IS NULL)
           )""",
        (workspace_id, actor_id, scope),
    ).fetchone()
    return bool(row and row[0])


def correct_draft(database_url: str, *, draft_id: UUID, workspace_id: UUID,
                  actor_id: UUID, connections: list[dict],
                  process_name: str | None = None) -> UUID:
    """Authenticated draft correction. Requires review scope in the workspace."""
    review_id = uuid4()
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            _lock(connection, workspace_id)
            if not _has_authority_conn(connection, workspace_id, actor_id, "review"):
                raise PermissionError("actor lacks review authority for draft correction")
            row = connection.execute(
                "SELECT status FROM oracle2.drafts WHERE draft_id=%s AND workspace_id=%s FOR UPDATE",
                (draft_id, workspace_id),
            ).fetchone()
            if row is None:
                raise LookupError("draft not found")
            if row[0] != "draft":
                raise ValueError("only draft-status documents can be corrected")
            connection.execute(
                """UPDATE oracle2.drafts
                   SET connections=%s,
                       process_name=COALESCE(%s, process_name),
                       updated_at=now()
                   WHERE draft_id=%s""",
                (Jsonb(connections), process_name, draft_id),
            )
            connection.execute(
                """INSERT INTO oracle2.reviews
                   (review_id,draft_id,workspace_id,actor_id,action,payload)
                   VALUES (%s,%s,%s,%s,'correct',%s)""",
                (review_id, draft_id, workspace_id, actor_id,
                 Jsonb({"connections": connections})),
            )
    return review_id


def confirm_draft(database_url: str, *, draft_id: UUID, workspace_id: UUID,
                  actor_id: UUID, scope: str) -> UUID:
    """Transactional scoped confirmation. Requires confirm scope.

    The unique partial index on reviews enforces one active confirmation per
    draft; a second concurrent confirmation fails at the database level.
    """
    if scope != "process-map":
        raise ValueError("unsupported confirmation scope")
    review_id = uuid4()
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            _lock(connection, workspace_id)
            if not _has_authority_conn(connection, workspace_id, actor_id, "confirm"):
                raise PermissionError("actor lacks confirm authority for scoped confirmation")
            row = connection.execute(
                "SELECT status FROM oracle2.drafts WHERE draft_id=%s AND workspace_id=%s FOR UPDATE",
                (draft_id, workspace_id),
            ).fetchone()
            if row is None:
                raise LookupError("draft not found")
            if row[0] == "confirmed":
                raise ValueError("draft already confirmed")
            if row[0] == "withdrawn":
                raise ValueError("withdrawn draft cannot be confirmed")
            connection.execute(
                "UPDATE oracle2.drafts SET status='confirmed', updated_at=now() WHERE draft_id=%s",
                (draft_id,),
            )
            connection.execute(
                """INSERT INTO oracle2.reviews
                   (review_id,draft_id,workspace_id,actor_id,action,payload)
                   VALUES (%s,%s,%s,%s,'confirm',%s)""",
                (review_id, draft_id, workspace_id, actor_id,
                 Jsonb({"scope": scope})),
            )
    return review_id


def revoke_review_authority(database_url: str, *, appointment_id: UUID,
                            workspace_id: UUID, revoked_by: UUID) -> None:
    """Revoke an appointment. Must be done by someone with root authority."""
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            _lock(connection, workspace_id)
            if not _has_authority_conn(connection, workspace_id, revoked_by, "root"):
                raise PermissionError("only root authority can revoke appointments")
            connection.execute(
                """UPDATE oracle2.appointments SET revoked_at=now()
                   WHERE appointment_id=%s AND workspace_id=%s""",
                (appointment_id, workspace_id),
            )
