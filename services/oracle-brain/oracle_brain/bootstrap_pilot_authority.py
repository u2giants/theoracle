"""Bootstrap pilot authority on an isolated oracle2 store (not production).

Usage (after 001_foundation.sql + grants):
  export ORACLE2_DATABASE_URL=postgresql://oracle2_pilot_web:...@127.0.0.1:55432/oracle2
  export ORACLE2_OWNER_PUBLIC_KEY=<owner ed25519 raw hex>
  python -m oracle_brain.bootstrap_pilot_authority \\
    --workspace 00000000-0000-4000-8000-000000000002 \\
    --owner <owner-uuid> \\
    --appointed-by <bootstrap-principal-uuid != owner> \\
    --appointment-id <appointment-uuid> \\
    --actor 00000000-0000-4000-8000-000000000003 \\
    --owner-signature-hex <sig of oracle2-owner-appointment-v1:ws:owner:appointment_id>

Actor default for the web pilot is
`00000000-0000-4000-8000-000000000003` (ORACLE2_PILOT_ACTOR).
All three writes run in one transaction.
"""

from __future__ import annotations

import argparse
import os
from uuid import UUID

import psycopg

from oracle_brain.authz import has_authority


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--appointed-by", required=True,
                        help="bootstrap principal UUID; must differ from --owner")
    parser.add_argument("--appointment-id", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--owner-signature-hex", required=True)
    args = parser.parse_args()

    url = args.database_url or os.environ.get("ORACLE2_DATABASE_URL")
    if not url:
        raise SystemExit("ORACLE2_DATABASE_URL is required")
    workspace = UUID(args.workspace)
    owner = UUID(args.owner)
    appointed_by = UUID(args.appointed_by)
    appointment = UUID(args.appointment_id)
    actor = UUID(args.actor)
    if owner == appointed_by:
        raise SystemExit("appointed-by must differ from owner (appointments CHECK)")
    if actor == owner:
        raise SystemExit("actor must differ from owner (delegate CHECK)")

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    key_hex = os.environ.get("ORACLE2_OWNER_PUBLIC_KEY", "")
    if not key_hex:
        raise SystemExit("ORACLE2_OWNER_PUBLIC_KEY is required")
    message = f"oracle2-owner-appointment-v1:{workspace}:{owner}:{appointment}".encode()
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex)).verify(
        bytes.fromhex(args.owner_signature_hex), message
    )

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

    if not has_authority(url, workspace_id=workspace, actor_id=actor, scope="review"):
        raise SystemExit("review authority missing after bootstrap")
    if not has_authority(url, workspace_id=workspace, actor_id=actor, scope="confirm"):
        raise SystemExit("confirm authority missing after bootstrap")
    print("pilot authority ready", actor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
