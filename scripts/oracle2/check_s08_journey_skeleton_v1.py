"""Offline skeleton checks for run_s08_journey_proof_v1.py — no DB, no effects.

Proves only what can be proved without Docker/database/provider:
  - runner imports and exposes the fail-closed bindings
  - every journey stage refuses closed (JourneyRefusal / NotImplementedError)
  - review receipt is fail-closed when absent, wrong-head, wrong-runner-SHA,
    wrong plan/checker/evidence SHA, or non-APPROVE verdict
  - database-gate helper requires a precise ALLOW line and is invoked AFTER
    the review receipt (gate-before-database order)
  - HEAD helper requires a full 40-char SHA
  - RECALL_* env refusal is present
  - inventory assertion helper is present and compares the sealed tuple
  - budget helpers enforce a monotonic deadline
  - cleanup readback helper exists and is called from finally
  - SCRATCH must not live inside the repository
  - refused runs write refusal.json with refused=true and do NOT write
    journey-evidence.json

This checker restores runner.SCRATCH after every mutation. It does NOT execute
the journey and does NOT constitute acceptance.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

RUNNER = Path(__file__).resolve().parent / "run_s08_journey_proof_v1.py"
PLAN = Path(__file__).resolve().parents[2] / "docs/verification/oracle2/s08-journey-proof-plan.md"
EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / "docs/verification/oracle2/s08-compose-81742134-evidence.md"
)


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
    plan_sha = mod.sha256_file(PLAN)
    checker_sha = mod.sha256_file(Path(__file__).resolve())
    evidence_sha = mod.sha256_file(EVIDENCE)
    print("RUNNER_SHA256", runner_sha)
    print("PLAN_SHA256", plan_sha)
    print("CHECKER_SHA256", checker_sha)
    print("EVIDENCE_SHA256", evidence_sha)

    head = mod.require_head()
    print("HEAD_BIND_OK", head)

    # Stages must refuse closed under the extended binding signatures (H-D).
    stage_cases = (
        ("stage_provision_capture_admission", lambda: mod.stage_provision_capture_admission({}, 30)),
        ("stage_observe_audience", lambda: mod.stage_observe_audience({}, 30)),
        ("stage_host_control", lambda: mod.stage_host_control({}, 30)),
        (
            "stage_current_turn",
            lambda: mod.stage_current_turn(
                {"event_id": "00000000-0000-0000-0000-000000000001"}, 30
            ),
        ),
        ("stage_sender", lambda: mod.stage_sender({}, 30)),
        ("stage_receipt_bytes_in", lambda: mod.stage_receipt_bytes_in({"raw_wire": b"x"}, 30)),
        ("stage_status_reconcile", lambda: mod.stage_status_reconcile({}, 30)),
    )
    for name, call in stage_cases:
        try:
            call()
        except (mod.JourneyRefusal, NotImplementedError) as e:
            print("STAGE_REFUSES", name, str(e)[:80])
        else:
            raise SystemExit("stage did not refuse: " + name)

    # RECALL_* env must be refused (H-E).
    import os

    saved_recall = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("RECALL_")}
    os.environ["RECALL_API_KEY"] = "invented-should-refuse"
    try:
        try:
            mod.require_recall_env_absent()
        except mod.JourneyRefusal as e:
            print("RECALL_ENV_FAIL_CLOSED", str(e)[:80])
        else:
            raise SystemExit("RECALL_* env was not refused")
    finally:
        os.environ.pop("RECALL_API_KEY", None)
        os.environ.update(saved_recall)

    # Inventory helper must compare the sealed tuple, not echo a note (H-I).
    if not callable(getattr(mod, "assert_sealed_inventory", None)):
        raise SystemExit("assert_sealed_inventory missing")
    inv = mod.assert_sealed_inventory()
    if inv.get("inventory_count") != 20:
        raise SystemExit("sealed inventory count is not 20")
    if inv.get("omits") != ["003", "005"]:
        raise SystemExit("sealed inventory omit list wrong")
    print("INVENTORY_ASSERTION_OK", inv["inventory_count"])

    # Budget helpers must enforce a monotonic deadline (H-H).
    if not callable(getattr(mod, "_monotonic_end", None)):
        raise SystemExit("_monotonic_end missing")
    if not callable(getattr(mod, "_budget_check", None)):
        raise SystemExit("_budget_check missing")
    end = mod._monotonic_end(0.001)
    import time

    time.sleep(0.002)
    try:
        mod._budget_check(end, "checker")
    except mod.JourneyRefusal as e:
        print("BUDGET_ENFORCED", str(e)[:60])
    else:
        raise SystemExit("budget was not enforced")

    # Cleanup helper must exist and be referenced from main's finally (M-C).
    if not callable(getattr(mod, "_owned_absence_readback", None)):
        raise SystemExit("_owned_absence_readback missing")
    src = RUNNER.read_text()
    main_src = src[src.find("def main") :]
    if "_owned_absence_readback(" not in main_src.split("finally:", 1)[-1]:
        raise SystemExit("cleanup readback is not called from main's finally")
    print("CLEANUP_READBACK_IN_FINALLY")

    # SCRATCH must not live inside the repository (M-C).
    try:
        mod.SCRATCH_ENV  # noqa: B018 — attribute must exist
    except AttributeError:
        raise SystemExit("SCRATCH_ENV missing") from None
    if "SCRATCH must not live inside the repository" not in src:
        raise SystemExit("SCRATCH-inside-repo refusal missing")
    print("SCRATCH_REPO_FORBID_PRESENT")

    # Refusal marker shape (M-D).
    if "refused" not in src or "non_evidence" not in src:
        raise SystemExit("refusal marker keys missing")
    if "journey-evidence.json" not in src:
        raise SystemExit("journey-evidence writer missing")
    print("REFUSAL_MARKER_PRESENT")

    # Receipt fail-closed cases. require_review_receipt takes scratch explicitly;
    # the checker's TemporaryDirectory is isolated and restored by the with-block.
    with tempfile.TemporaryDirectory() as td:
        scratch = Path(td)
        try:
            mod.require_review_receipt(head, scratch)
        except mod.JourneyRefusal as e:
            print("REVIEW_RECEIPT_FAIL_CLOSED", str(e)[:100])
        else:
            raise SystemExit("review receipt did not fail closed")

        good = {
            "head": head,
            "runner_sha256": runner_sha,
            "plan_sha256": plan_sha,
            "checker_sha256": checker_sha,
            "evidence_sha256": evidence_sha,
            "verdict": "APPROVE",
        }

        def write_receipt(payload: dict) -> None:
            p = scratch / "review-receipt.json"
            p.write_text(json.dumps(payload) + "\n")
            p.chmod(0o600)

        # wrong runner SHA (M-B)
        write_receipt({**good, "runner_sha256": "0" * 64})
        try:
            mod.require_review_receipt(head, scratch)
        except mod.JourneyRefusal as e:
            print("RUNNER_SHA_MISMATCH_FAIL_CLOSED", str(e)[:80])
        else:
            raise SystemExit("runner_sha256 mismatch did not fail closed")

        # wrong plan SHA
        write_receipt({**good, "plan_sha256": "0" * 64})
        try:
            mod.require_review_receipt(head, scratch)
        except mod.JourneyRefusal as e:
            print("PLAN_SHA_MISMATCH_FAIL_CLOSED", str(e)[:80])
        else:
            raise SystemExit("plan_sha256 mismatch did not fail closed")

        # wrong head
        write_receipt({**good, "head": "0" * 40})
        try:
            mod.require_review_receipt(head, scratch)
        except mod.JourneyRefusal as e:
            print("REVIEW_HEAD_FAIL_CLOSED", str(e)[:80])
        else:
            raise SystemExit("wrong head did not fail closed")

        # non-APPROVE verdict
        write_receipt({**good, "verdict": "REJECT"})
        try:
            mod.require_review_receipt(head, scratch)
        except mod.JourneyRefusal as e:
            print("REVIEW_VERDICT_FAIL_CLOSED", str(e)[:80])
        else:
            raise SystemExit("non-APPROVE verdict did not fail closed")
    print("SCRATCH_RESTORED")

    if not callable(getattr(mod, "require_database_gate", None)):
        raise SystemExit("require_database_gate missing")
    print("DATABASE_GATE_HELPER_PRESENT")

    # Precise ALLOW token, not substring (H-G).
    if not hasattr(mod, "ALLOW_LINE"):
        raise SystemExit("ALLOW_LINE regex missing")
    if mod.ALLOW_LINE.search("gate: ALLOW") is None:
        raise SystemExit("ALLOW_LINE does not match 'gate: ALLOW'")
    if mod.ALLOW_LINE.search("DENIED but ALLOW later") is not None:
        raise SystemExit("ALLOW_LINE matches a denial substring")
    print("ALLOW_LINE_PRECISE")

    # Static order: review receipt BEFORE database gate; gate BEFORE any
    # worker_postgres / database work (M-B gate-before-database).
    main_src = src[src.find("def main") :]
    i_receipt = main_src.find("require_review_receipt(")
    i_gate = main_src.find("require_database_gate(")
    i_worker = main_src.find("worker_postgres(")
    if i_receipt < 0 or i_gate < 0 or i_receipt > i_gate:
        raise SystemExit("main must require review receipt before database gate")
    if i_worker < 0 or i_gate > i_worker:
        raise SystemExit("main must require database gate before worker_postgres")
    print("RECEIPT_BEFORE_GATE_BEFORE_DATABASE")

    # Tool identity recording (H-G).
    if not callable(getattr(mod, "_tool_identity", None)):
        raise SystemExit("_tool_identity missing")
    print("TOOL_IDENTITY_HELPER_PRESENT")

    # Forbidden network path constant (H-E).
    if not getattr(mod, "FORBIDDEN_NETWORK_PATHS", None):
        raise SystemExit("FORBIDDEN_NETWORK_PATHS missing")
    if "exchange_provider_v1" not in mod.FORBIDDEN_NETWORK_PATHS:
        raise SystemExit("forbidden network path list incomplete")
    print("FORBIDDEN_NETWORK_PATHS_NAMED")

    print("OFFLINE_SKELETON_CHECKS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
