"""Synthetic-only worker entry point; no provider call or graph write."""

from __future__ import annotations

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from oracle_brain.config import Settings
from oracle_brain.contracts import RunRequest


def main() -> int:
    settings = Settings.from_env("extractor")
    request = RunRequest.model_validate_json(sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read())
    if request.mode != "synthetic" or settings.mode != "synthetic":
        raise PermissionError("S02 transport is synthetic only")
    if settings.workspace_allowlist and str(request.workspace_id) not in settings.workspace_allowlist:
        raise PermissionError("workspace not allowed")
    print(json.dumps({"run_id": str(request.run_id), "status": "accepted_synthetic"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
