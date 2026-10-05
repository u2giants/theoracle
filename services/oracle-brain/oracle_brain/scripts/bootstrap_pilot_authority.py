"""Bootstrap pilot authority on an isolated oracle2 store (not production).

Usage:
  ORACLE2_DATABASE_URL=... ORACLE2_OWNER_PUBLIC_KEY=... \
    python -m oracle_brain.scripts.bootstrap_pilot_authority \
      --workspace 00000000-0000-4000-8000-000000000002 \
      --owner <owner-uuid> --actor <pilot-uuid> \
      --owner-signature-hex <sig>

Requires a signed owner appointment message:
  oracle2-owner-appointment-v1:<workspace>:<owner>:<appointment_id>
"""

from __future__ import annotations

import argparse
from uuid import UUID

from oracle_brain.authz import appoint_owner, delegate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--appointment-id", required=True)
    parser.add_argument("--owner-signature-hex", required=True)
    args = parser.parse_args()
    import os

    url = args.database_url or os.environ.get("ORACLE2_DATABASE_URL")
    if not url:
        raise SystemExit("ORACLE2_DATABASE_URL is required")
    workspace = UUID(args.workspace)
    owner = UUID(args.owner)
    actor = UUID(args.actor)
    appointment = UUID(args.appointment_id)
    appoint_owner(
        url,
        workspace_id=workspace,
        owner_id=owner,
        appointed_by=owner,
        appointment_id=appointment,
        owner_signature_hex=args.owner_signature_hex,
    )
    delegate(url, workspace_id=workspace, grantor_id=owner, actor_id=actor, scope="review")
    delegate(url, workspace_id=workspace, grantor_id=owner, actor_id=actor, scope="confirm")
    print("pilot authority ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
