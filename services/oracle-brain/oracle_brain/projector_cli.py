"""One projection attempt. Process supervisor retries after interruption."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from oracle_brain.config import Settings
from oracle_brain.graph.falkor import FalkorGraphStore
from oracle_brain.outbox import lease_next, make_receipt, mark_delivered


def run_once() -> bool:
    settings = Settings.from_env("projector")
    secret = os.environ["ORACLE2_PROJECTION_SIGNING_KEY"].encode()
    if len(secret) < 32:
        raise ValueError("projection signing key too short")
    event = lease_next(settings.database_url,
                       allowed_workspaces=settings.workspace_allowlist or None)
    if event is None:
        return False
    if settings.workspace_allowlist and str(event.workspace_id) not in settings.workspace_allowlist:
        raise PermissionError("projection workspace is outside runtime allowlist")
    graph = FalkorGraphStore(settings.confirmed_graph_url)
    if event.operation == "project":
        graph.project(event.workspace_id, event.assertion_id,
                      event.revision, event.payload)
    else:
        graph.withdraw(event.workspace_id, event.assertion_id, event.revision)
    receipt = make_receipt(event, secret, "oracle2-projector")
    mark_delivered(settings.database_url, event_id=event.event_id,
                   receipt=receipt, secret=secret)
    return True


def main() -> int:
    try:
        delivered = run_once()
    except Exception as exc:  # report the class only; messages may carry URLs
        print(json.dumps({"status": "failed", "error": type(exc).__name__}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "delivered" if delivered else "idle"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
