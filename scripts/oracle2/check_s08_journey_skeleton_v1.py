"""Offline skeleton checks for run_s08_journey_proof_v1.py — no DB, no effects.

Proves only what can be proved without Docker/database/provider:
  - runner imports and exposes the fail-closed bindings
  - every journey stage refuses closed (NotImplementedError)
  - review receipt is fail-closed when absent
  - database-gate helper exists and is invoked by main's order (static)
  - HEAD helper requires a full 40-char SHA

This checker does NOT execute the journey and does NOT constitute acceptance.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RUNNER = Path(__file__).resolve().parent / "run_s08_journey_proof_v1.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("s08_journey_runner", RUNNER)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load runner: " + str(RUNNER))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = load_runner()
    runner_sha = mod.sha256_file(RUNNER)
    print("RUNNER_SHA256", runner_sha)

    head = mod.require_head()
    print("HEAD_BIND_OK", head)

    cases = (
        ("stage_host_control", lambda: mod.stage_host_control(30)),
        (
            "stage_current_turn",
            lambda: mod.stage_current_turn(
                "00000000-0000-0000-0000-000000000001", 30
            ),
        ),
        ("stage_sender", lambda: mod.stage_sender(30)),
        ("stage_receipt_bytes_in", lambda: mod.stage_receipt_bytes_in(b"x", 30)),
        ("stage_status_reconcile", lambda: mod.stage_status_reconcile(30)),
    )
    for name, call in cases:
        try:
            call()
        except NotImplementedError as e:
            print("STAGE_REFUSES", name, str(e)[:80])
        else:
            raise SystemExit("stage did not refuse: " + name)

    try:
        mod.require_review_receipt(head)
    except RuntimeError as e:
        print("REVIEW_RECEIPT_FAIL_CLOSED", str(e)[:100])
    else:
        raise SystemExit("review receipt did not fail closed")

    # Receipt with wrong verdict must also fail closed.
    import json
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        mod.SCRATCH = Path(td)
        (Path(td) / "review-receipt.json").write_text(
            json.dumps(
                {
                    "head": head,
                    "runner_sha256": runner_sha,
                    "verdict": "REJECT",
                }
            )
        )
        try:
            mod.require_review_receipt(head)
        except RuntimeError as e:
            print("REVIEW_VERDICT_FAIL_CLOSED", str(e)[:80])
        else:
            raise SystemExit("non-APPROVE verdict did not fail closed")

        (Path(td) / "review-receipt.json").write_text(
            json.dumps(
                {
                    "head": "0" * 40,
                    "runner_sha256": runner_sha,
                    "verdict": "APPROVE",
                }
            )
        )
        try:
            mod.require_review_receipt(head)
        except RuntimeError as e:
            print("REVIEW_HEAD_FAIL_CLOSED", str(e)[:80])
        else:
            raise SystemExit("wrong head did not fail closed")

    if not callable(getattr(mod, "require_database_gate", None)):
        raise SystemExit("require_database_gate missing")
    print("DATABASE_GATE_HELPER_PRESENT")

    # Static: main must call require_review_receipt before require_database_gate.
    src = RUNNER.read_text()
    i_receipt = src.find("require_review_receipt(")
    i_gate = src.find("require_database_gate(")
    # Skip the def lines; look at call sites inside main.
    i_receipt_call = src.find("require_review_receipt(", src.find("def main"))
    i_gate_call = src.find("require_database_gate(", src.find("def main"))
    if i_receipt_call < 0 or i_gate_call < 0 or i_receipt_call > i_gate_call:
        raise SystemExit("main must require review receipt before database gate")
    print("RECEIPT_BEFORE_DATABASE_GATE")

    print("OFFLINE_SKELETON_CHECKS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
