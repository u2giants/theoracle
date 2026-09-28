#!/usr/bin/env python3
"""Fail-closed phase gate; always run exact tests and write sanitized evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "services" / "oracle-brain"
S02_TESTS = [
    "test_contract_parity.py", "test_graph_adapter.py", "test_outbox.py",
    "test_checkpoint_scope.py", "test_dependency_bundle.py",
    "test_runtime_identity.py", "test_provider_policy.py", "test_authority.py",
    "test_preview_settings.py", "test_worker_guard_parity.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["S02"])
    parser.add_argument("--mode", choices=["offline", "live"], required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--result", type=Path,
                        default=ROOT / "out" / "oracle2" / "S02-result.json")
    args = parser.parse_args()
    if args.mode != "offline":
        parser.error("S02 live gate requires a separately reviewed preview target")
    if args.manifest:
        parser.error("offline gate cannot use a private manifest")
    missing = [name for name in S02_TESTS if not (SERVICE / "tests" / name).is_file()]
    if missing:
        parser.error(f"missing required tests: {', '.join(missing)}")
    if not os.getenv("ORACLE2_TEST_ADMIN_URL") or not os.getenv("ORACLE2_TEST_CONFIRMED_URL"):
        parser.error("real isolated Postgres and FalkorDB test URLs required")
    python = SERVICE / ".venv" / "bin" / "python"
    if not python.exists():
        parser.error("frozen Python environment missing; run uv sync --frozen --extra test")
    tests = [str(SERVICE / "tests" / name) for name in S02_TESTS]
    completed = subprocess.run([str(python), "-m", "pytest", "-q", *tests], cwd=ROOT,
                               capture_output=True, text=True, check=False)
    # No test output enters a public artifact; raw logs remain in local CI job.
    lock_hash = hashlib.sha256((SERVICE / "uv.lock").read_bytes()).hexdigest()
    result = {
        "phase": args.phase, "mode": args.mode,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "lock_sha256": lock_hash,
        "required_test_files": S02_TESTS,
        "test_exit_code": completed.returncode,
        "passed": completed.returncode == 0,
        "live_accepted": False,
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2) + "\n")
    if completed.stdout:
        print(completed.stdout[-4000:])
    if completed.stderr:
        print(completed.stderr[-2000:], file=sys.stderr)
    print(f"sanitized result: {args.result}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
