"""Knowledge-level authority: draft correction and transactional scoped confirmation."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from ..authz import has_authority


def correct_draft(database_url: str, *, draft_id: UUID, workspace_id: UUID,
                  actor_id: UUID, connections: list[dict],
                  process_name: str | None = None) -> UUID:
    """Authenticated draft correction. Requires review scope in the workspace."""
    review_id = uuid4()
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            connection.execute(
                """SELECT pg_advisory_xact_lock(
                     hashtext('oracle2-authz:' || %s::text || ':' || %s::text))""",
                (str(workspace_id), str(actor_id)),
            )
            if not has_authority(database_url, workspace_id=workspace_id,
                                 actor_id=actor_id, scope="review"):
                raise PermissionError("actor lacks review authority for draft correction")
            row = connection.execute(
                "SELECT status FROM oracle2.drafts WHERE draft_id=%s AND workspace_id=%s",
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
    review_id = uuid4()
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            connection.execute(
                """SELECT pg_advisory_xact_lock(
                     hashtext('oracle2-authz:' || %s::text || ':' || %s::text))""",
                (str(workspace_id), str(actor_id)),
            )
            if not has_authority(database_url, workspace_id=workspace_id,
                                 actor_id=actor_id, scope="confirm"):
                raise PermissionError("actor lacks confirm authority for scoped confirmation")
            row = connection.execute(
                "SELECT status FROM oracle2.drafts WHERE draft_id=%s AND workspace_id=%s",
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
    if not has_authority(database_url, workspace_id=workspace_id,
                         actor_id=revoked_by, scope="root"):
        raise PermissionError("only root authority can revoke appointments")
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            # Same advisory lock key as the web pilot mutations.
            connection.execute(
                """SELECT pg_advisory_xact_lock(
                     hashtext('oracle2-authz:' || %s::text))""",
                (str(workspace_id),),
            )
            connection.execute(
                """UPDATE oracle2.appointments SET revoked_at=now()
                   WHERE appointment_id=%s AND workspace_id=%s""",
                (appointment_id, workspace_id),
            )
