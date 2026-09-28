"""Owner-rooted, scoped authority; application admins have no root shortcut."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from uuid import UUID, uuid4

import psycopg
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def appoint_owner(admin_url: str, *, workspace_id: UUID, owner_id: UUID,
                  appointed_by: UUID, appointment_id: UUID,
                  owner_signature_hex: str) -> UUID:
    """Bootstrap only with a signed external owner appointment."""
    message = f"oracle2-owner-appointment-v1:{workspace_id}:{owner_id}:{appointment_id}".encode()
    owner_public_key_hex = os.environ.get("ORACLE2_OWNER_PUBLIC_KEY", "")
    if not owner_public_key_hex:
        raise PermissionError("trusted owner public key not configured")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(owner_public_key_hex)).verify(
            bytes.fromhex(owner_signature_hex), message
        )
    except (ValueError, TypeError) as exc:
        raise PermissionError("owner appointment signature invalid") from exc
    except Exception as exc:
        raise PermissionError("owner appointment signature invalid") from exc
    with psycopg.connect(admin_url) as connection:
        connection.execute(
            """INSERT INTO oracle2.appointments
               (appointment_id,workspace_id,actor_id,scope,granted_by)
               VALUES (%s,%s,%s,'root',%s)""",
            (appointment_id, workspace_id, owner_id, appointed_by),
        )
    return appointment_id


def has_authority(database_url: str, *, workspace_id: UUID, actor_id: UUID,
                  scope: str, at: datetime | None = None) -> bool:
    at = at or datetime.now(timezone.utc)
    with psycopg.connect(database_url) as connection:
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
                                 (expires_at IS NULL OR expires_at>%s))
                    AND bool_or(scope='root' AND parent_id IS NULL)
               )""",
            (workspace_id, actor_id, scope, at),
        ).fetchone()
        return bool(row[0])


def delegate(database_url: str, *, workspace_id: UUID, grantor_id: UUID,
             actor_id: UUID, scope: str, expires_at: datetime | None = None) -> UUID:
    if scope == "root":
        raise PermissionError("root authority requires owner appointment")
    if not has_authority(database_url, workspace_id=workspace_id, actor_id=grantor_id,
                         scope=scope):
        raise PermissionError("grantor lacks scoped authority")
    appointment_id = uuid4()
    with psycopg.connect(database_url) as connection:
        parent = connection.execute(
            """SELECT appointment_id FROM oracle2.appointments
               WHERE workspace_id=%s AND actor_id=%s AND scope IN (%s,'root')
                 AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>now())
               ORDER BY created_at LIMIT 1 FOR UPDATE""",
            (workspace_id, grantor_id, scope),
        ).fetchone()
        if parent is None:
            raise PermissionError("no active parent appointment")
        connection.execute(
            """INSERT INTO oracle2.appointments
               (appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (appointment_id, workspace_id, actor_id, scope, grantor_id, parent[0], expires_at),
        )
    return appointment_id
