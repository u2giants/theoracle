"""Bootstrap pilot authority on an isolated oracle2 store (not production).

The bootstrap connection must be an **admin** role that can INSERT into
`oracle2.appointments` (e.g. `oracle2_admin`). The web app later connects as
`oracle2_pilot_web` (SELECT on appointments only). Never run this against
production.

Usage (after 001_foundation.sql + grant-postgres.sql):
  export ORACLE2_DATABASE_URL=postgresql://oracle2_admin:...@127.0.0.1:55432/oracle2
  export ORACLE2_OWNER_PUBLIC_KEY=<owner ed25519 raw hex>
  python -m oracle_brain.bootstrap_pilot_authority \\
    --workspace 00000000-0000-4000-8000-000000000002 \\
    --owner <owner-uuid> \\
    --appointed-by <bootstrap-principal-uuid != owner> \\
    --appointment-id <appointment-uuid> \\
    --actor 00000000-0000-4000-8000-000000000003 \\
    --owner-signature-hex <sig of oracle2-owner-appointment-v1:ws:owner:appointment_id> \\
    --actor-signature-hex <sig of oracle2-pilot-delegate-v1:ws:owner:actor>

Required inputs (all of them):
  - --workspace / ORACLE2_PILOT_WORKSPACE_ID
  - --owner (appointed root actor UUID)
  - --appointed-by (different UUID; CHECK actor_id <> granted_by)
  - --appointment-id (UUID for the root appointment row)
  - --actor (pilot actor UUID used by ORACLE2_PILOT_ACTOR)
  - --owner-signature-hex (Ed25519 signature over the appointment message)
  - ORACLE2_OWNER_PUBLIC_KEY (raw public key hex)
  - ORACLE2_DATABASE_URL (admin URL for bootstrap only)

All three appointment writes run in one transaction.
"""

from __future__ import annotations

import argparse
import os
from uuid import UUID


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--appointed-by", required=True,
                        help="bootstrap principal UUID; must differ from --owner")
    parser.add_argument("--appointment-id", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--owner-signature-hex", required=True)
    parser.add_argument("--actor-signature-hex", required=True,
                        help="owner signature over oracle2-pilot-delegate-v1:ws:owner:actor")
    args = parser.parse_args()

    # Credentials only via env, never CLI. Isolation is hard-coded to loopback —
    # the same environment cannot redefine what counts as isolated.
    url = os.environ.get("ORACLE2_DATABASE_URL")
    if not url:
        raise SystemExit("ORACLE2_DATABASE_URL (admin) is required via environment")
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("refusing DATABASE_URL host that is not loopback isolated store")
    path = (urlparse(url).path or "").lstrip("/")
    if path and path != "oracle2":
        raise SystemExit("refusing DATABASE_URL database name other than oracle2")
    workspace = UUID(args.workspace)
    owner = UUID(args.owner)
    appointed_by = UUID(args.appointed_by)
    appointment = UUID(args.appointment_id)
    actor = UUID(args.actor)
    if owner == appointed_by:
        raise SystemExit("appointed-by must differ from owner (appointments CHECK)")
    if actor == owner:
        raise SystemExit("actor must differ from owner (delegate CHECK)")

    import psycopg

    from oracle_brain.authz import has_authority

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    key_hex = os.environ.get("ORACLE2_OWNER_PUBLIC_KEY", "")
    if not key_hex:
        raise SystemExit("ORACLE2_OWNER_PUBLIC_KEY is required")
    message = f"oracle2-owner-appointment-v1:{workspace}:{owner}:{appointment}".encode()
    delegate_message = f"oracle2-pilot-delegate-v1:{workspace}:{owner}:{actor}".encode()
    try:
        public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex))
        public.verify(bytes.fromhex(args.owner_signature_hex), message)
        public.verify(bytes.fromhex(args.actor_signature_hex), delegate_message)
    except Exception as exc:
        raise SystemExit(f"owner appointment/delegate signature invalid: {exc}") from exc

    with psycopg.connect(url) as connection:
        with connection.transaction():
            connection.execute(
                """INSERT INTO oracle2.appointments
                   (appointment_id,workspace_id,actor_id,scope,granted_by)
                   VALUES (%s,%s,%s,'root',%s)""",
                (appointment, workspace, owner, appointed_by),
            )
            connection.execute(
                """INSERT INTO oracle2.appointments
                   (appointment_id,workspace_id,actor_id,scope,granted_by,parent_id)
                   VALUES (gen_random_uuid(),%s,%s,'review',%s,%s)""",
                (workspace, actor, owner, appointment),
            )
            connection.execute(
                """INSERT INTO oracle2.appointments
                   (appointment_id,workspace_id,actor_id,scope,granted_by,parent_id)
                   VALUES (gen_random_uuid(),%s,%s,'confirm',%s,%s)""",
                (workspace, actor, owner, appointment),
            )
            # Same connection/transaction so uncommitted grants are visible.
            for scope in ("review", "confirm"):
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
                    (workspace, actor, scope),
                ).fetchone()
                if not row or not row[0]:
                    raise RuntimeError(f"{scope} authority missing after bootstrap")

    print("pilot authority ready", actor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
