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
    --owner-signature-hex <sig of oracle2-owner-appointment-v1:ws:owner:appointment_id>

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
    args = parser.parse_args()

    # Credentials only via env, never CLI. Isolated host allowlist (loopback or
    # explicitly named private hosts). Broad RFC1918 ranges are not enough.
    url = os.environ.get("ORACLE2_DATABASE_URL")
    if not url:
        raise SystemExit("ORACLE2_DATABASE_URL (admin) is required via environment")
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    allow_raw = os.environ.get("ORACLE2_ISOLATED_STORE_HOSTS", "127.0.0.1,localhost,::1")
    allowed_hosts = {h.strip().lower() for h in allow_raw.split(",") if h.strip()}
    if host not in allowed_hosts:
        raise SystemExit(
            "refusing DATABASE_URL host not in ORACLE2_ISOLATED_STORE_HOSTS allowlist"
        )
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
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex)).verify(
            bytes.fromhex(args.owner_signature_hex), message
        )
    except Exception as exc:
        raise SystemExit(f"owner appointment signature invalid: {exc}") from exc

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
