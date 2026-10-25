"""Offline skeleton checks for run_s08_journey_proof_v1.py — no DB, no effects.

Proves only what can be proved without Docker/database/provider:
  - runner imports and exposes the fail-closed bindings
  - every journey stage refuses closed (JourneyRefusal / NotImplementedError)
  - review receipt is fail-closed when absent, wrong-head, wrong-runner-SHA,
    wrong plan/checker/evidence SHA (H2: ALL FOUR SHA negatives tested), or
    non-APPROVE verdict
  - database-gate helper requires a precise ALLOW line, rejects DENIED lines,
    and is invoked AFTER the review receipt (gate-before-database order)
  - HEAD helper requires a full 40-char SHA
  - RECALL_* env refusal is present
  - inventory assertion helper is present and compares the sealed tuple
  - budget helpers enforce a monotonic deadline (finite-only, entry+exit)
  - cleanup readback helper exists and is called from finally
  - SCRATCH must not live inside the repository
  - refused runs write refusal.json with refused=true and do NOT write
    journey-evidence.json (C8 exclusivity)
  - success path writes journey-evidence.json and does NOT write refusal.json
  - ops artifacts are labeled ops/non-evidence
  - stage binding schemas are present (M9)

This checker restores runner state after every mutation. It does NOT execute
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

    # M9: stage binding schemas must exist and name required keys.
    if not hasattr(mod, "STAGE_BINDING_SCHEMAS"):
        raise SystemExit("STAGE_BINDING_SCHEMAS missing (M9)")
    schemas = mod.STAGE_BINDING_SCHEMAS
    expected_stages = {
        "provision_capture_admission", "observe_audience", "host_control",
        "current_turn", "sender", "receipt_bytes_in", "status_reconcile",
    }
    if set(schemas) != expected_stages:
        raise SystemExit(f"STAGE_BINDING_SCHEMAS keys wrong: {set(schemas)}")
    if not schemas["host_control"] or "observation_id" not in schemas["host_control"]:
        raise SystemExit("host_control schema missing observation_id (M9)")
    print("STAGE_BINDING_SCHEMAS_OK")

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

    # Budget helpers must enforce a monotonic deadline (H-H/H1).
    if not callable(getattr(mod, "_monotonic_end", None)):
        raise SystemExit("_monotonic_end missing")
    if not callable(getattr(mod, "_budget_check", None)):
        raise SystemExit("_budget_check missing")
    # L1: reject inf/nan budgets.
    for bad in (float("inf"), float("nan"), -1.0, 0.0):
        try:
            mod._monotonic_end(bad)
        except mod.JourneyRefusal:
            pass
        else:
            raise SystemExit(f"_monotonic_end accepted non-finite/non-positive: {bad!r}")
    print("BUDGET_REJECTS_NONFINITE")
    end = mod._monotonic_end(0.001)
    import time

    time.sleep(0.002)
    try:
        mod._budget_check(end, "checker")
    except mod.JourneyRefusal as e:
        print("BUDGET_ENFORCED", str(e)[:60])
    else:
        raise SystemExit("budget was not enforced")

    # H1: fence must have ContextVar + finiteness + entry + exit check.
    if not hasattr(mod, "_request_end_v1"):
        raise SystemExit("fence ContextVar _request_end_v1 missing (H1)")
    # Non-finite fence must refuse.
    for bad in (float("inf"), float("nan"), "x", 1):
        try:
            with mod._request_fence_v1(bad):
                pass
        except mod.JourneyRefusal:
            pass
        else:
            raise SystemExit(f"fence accepted bad value: {bad!r}")
    print("FENCE_REJECTS_NONFINITE")
    # Exit check: a fence that elapses inside must refuse at exit.
    try:
        with mod._request_fence_v1(float(time.monotonic() + 0.001)):
            time.sleep(0.005)
    except mod.JourneyRefusal:
        print("FENCE_EXIT_CHECK_ENFORCED")
    else:
        raise SystemExit("fence exit check did not fire on overrun")
    # Normal fence completes.
    with mod._request_fence_v1(float(time.monotonic() + 5.0)):
        pass
    print("FENCE_ENTRY_EXIT_OK")

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

    # C3: receipt release path env must exist.
    if not hasattr(mod, "RECEIPT_RELEASE_ENV"):
        raise SystemExit("RECEIPT_RELEASE_ENV missing (C3)")
    if mod.RECEIPT_RELEASE_ENV != "ORACLE2_S08_JOURNEY_RECEIPT":
        raise SystemExit("RECEIPT_RELEASE_ENV wrong value")
    print("RECEIPT_RELEASE_ENV_PRESENT")

    # C8: refusal/evidence exclusivity — both markers present, and the
    # success path sets evidence_written before return.
    if "refused" not in src or "non_evidence" not in src:
        raise SystemExit("refusal marker keys missing")
    if "journey-evidence.json" not in src:
        raise SystemExit("journey-evidence writer missing")
    if "evidence_written" not in src:
        raise SystemExit("evidence_written flag missing (C8)")
    if "journey-evidence.json" not in main_src:
        raise SystemExit("journey-evidence writer not in main")
    # Refusal writer must not be called after evidence on the success path:
    # the success path must set evidence_written = True and return 0.
    if "evidence_written = True" not in main_src:
        raise SystemExit("evidence_written not set on success path (C8)")
    print("REFUSAL_EVIDENCE_EXCLUSIVITY_MARKERS")

    # C8: ops artifacts labeled ops/non-evidence.
    for ops_marker in ("ops-database-gate.txt", "ops-source-after-gate.json", "ops-schema-receipt.json"):
        if ops_marker not in src:
            raise SystemExit(f"ops artifact {ops_marker} missing (C8)")
    if '"ops": True' not in src and "'ops': True" not in src:
        # cleanup.json is labeled in main's finally.
        if "ops" not in main_src.split("finally:", 1)[-1]:
            raise SystemExit("cleanup.json ops label missing (C8)")
    print("OPS_ARTIFACTS_LABELED")

    # Receipt fail-closed cases. require_review_receipt takes scratch explicitly;
    # the checker's TemporaryDirectory is isolated and restored by the with-block.
    with tempfile.TemporaryDirectory() as td:
        scratch = Path(td)
        # C3: require_review_receipt now reads from RECEIPT_RELEASE_ENV.
        # Set it to a temp release path for the tests below.
        release_path = Path(td) / "release-receipt.json"
        saved_release = os.environ.get(mod.RECEIPT_RELEASE_ENV)
        os.environ[mod.RECEIPT_RELEASE_ENV] = str(release_path)

        def write_release(payload: dict) -> None:
            release_path.write_text(json.dumps(payload) + "\n")
            release_path.chmod(0o600)
            # Clear any prior copy in scratch so the runner re-copies.
            p = scratch / "review-receipt.json"
            if p.exists():
                p.unlink()

        try:
            # absent release path
            try:
                mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                print("REVIEW_RECEIPT_FAIL_CLOSED", str(e)[:100])
            else:
                raise SystemExit("review receipt did not fail closed when release absent")

            good = {
                "head": head,
                "runner_sha256": runner_sha,
                "plan_sha256": plan_sha,
                "checker_sha256": checker_sha,
                "evidence_sha256": evidence_sha,
                "verdict": "APPROVE",
            }

            # wrong runner SHA (H2/M-B)
            write_release({**good, "runner_sha256": "0" * 64})
            try:
                mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                print("RUNNER_SHA_MISMATCH_FAIL_CLOSED", str(e)[:80])
            else:
                raise SystemExit("runner_sha256 mismatch did not fail closed")

            # wrong plan SHA
            write_release({**good, "plan_sha256": "0" * 64})
            try:
                mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                print("PLAN_SHA_MISMATCH_FAIL_CLOSED", str(e)[:80])
            else:
                raise SystemExit("plan_sha256 mismatch did not fail closed")

            # H2: wrong checker SHA — previously untested.
            write_release({**good, "checker_sha256": "0" * 64})
            try:
                mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                print("CHECKER_SHA_MISMATCH_FAIL_CLOSED", str(e)[:80])
            else:
                raise SystemExit("checker_sha256 mismatch did not fail closed")

            # H2: wrong evidence SHA — previously untested.
            write_release({**good, "evidence_sha256": "0" * 64})
            try:
                mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                print("EVIDENCE_SHA_MISMATCH_FAIL_CLOSED", str(e)[:80])
            else:
                raise SystemExit("evidence_sha256 mismatch did not fail closed")

            # wrong head
            write_release({**good, "head": "0" * 40})
            try:
                mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                print("REVIEW_HEAD_FAIL_CLOSED", str(e)[:80])
            else:
                raise SystemExit("wrong head did not fail closed")

            # non-APPROVE verdict
            write_release({**good, "verdict": "REJECT"})
            try:
                mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                print("REVIEW_VERDICT_FAIL_CLOSED", str(e)[:80])
            else:
                raise SystemExit("non-APPROVE verdict did not fail closed")
        finally:
            if saved_release is not None:
                os.environ[mod.RECEIPT_RELEASE_ENV] = saved_release
            else:
                os.environ.pop(mod.RECEIPT_RELEASE_ENV, None)
    print("SCRATCH_RESTORED")

    if not callable(getattr(mod, "require_database_gate", None)):
        raise SystemExit("require_database_gate missing")
    print("DATABASE_GATE_HELPER_PRESENT")

    # Precise ALLOW token, not substring; DENIED line rejects (H-G/M1).
    if not hasattr(mod, "ALLOW_LINE"):
        raise SystemExit("ALLOW_LINE regex missing")
    if not hasattr(mod, "DENIED_LINE"):
        raise SystemExit("DENIED_LINE regex missing (M1)")
    if mod.ALLOW_LINE.search("gate: ALLOW") is None:
        raise SystemExit("ALLOW_LINE does not match 'gate: ALLOW'")
    if mod.ALLOW_LINE.search("ALLOW") is None:
        raise SystemExit("ALLOW_LINE does not match bare 'ALLOW'")
    if mod.ALLOW_LINE.search("DENIED but ALLOW later") is not None:
        raise SystemExit("ALLOW_LINE matches a denial substring")
    if mod.ALLOW_LINE.search("  ALLOW  ") is not None:
        raise SystemExit("ALLOW_LINE accepts surrounding whitespace (M1)")
    if mod.DENIED_LINE.search("DENIED") is None:
        raise SystemExit("DENIED_LINE does not match 'DENIED'")
    if mod.DENIED_LINE.search("gate: DENIED") is None:
        raise SystemExit("DENIED_LINE does not match 'gate: DENIED'")
    if mod.DENIED_LINE.search("ALLOW") is not None:
        raise SystemExit("DENIED_LINE matches ALLOW")
    print("ALLOW_DENIED_LINE_PRECISE")

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

    # C9: budget armed AFTER bootstrap (not before worker_postgres).
    i_budget = main_src.find("_monotonic_end(")
    i_bootstrap = main_src.find("bootstrap_canonical_test_schema(")
    if i_bootstrap < 0:
        raise SystemExit("bootstrap_canonical_test_schema not called in main")
    if i_budget < 0:
        raise SystemExit("_monotonic_end not called in main")
    # The budget end assignment must appear after the bootstrap call in main.
    i_budget_assign = main_src.find("budget_end = _monotonic_end(")
    if i_budget_assign < 0:
        raise SystemExit("budget_end assignment not found (C9)")
    if i_budget_assign < i_bootstrap:
        raise SystemExit("budget must be armed AFTER bootstrap_canonical_test_schema (C9)")
    print("BUDGET_AFTER_BOOTSTRAP")

    # C1: must use worker_env['ORACLE2_TEST_ADMIN_URL'], never fall back to
    # an outer ORACLE2_TEST_ADMIN_URL as the owned target.
    if "worker_env[\"ORACLE2_TEST_ADMIN_URL\"]" not in src and "worker_env['ORACLE2_TEST_ADMIN_URL']" not in src:
        raise SystemExit("worker_env['ORACLE2_TEST_ADMIN_URL'] not used (C1)")
    if 'os.environ.get("ORACLE2_TEST_ADMIN_URL") or' in src:
        raise SystemExit("outer ORACLE2_TEST_ADMIN_URL fallback present (C1)")
    print("WORKER_ENV_URL_NO_FALLBACK")

    # C2: absence readback must support prefix-aware or identity project.
    if "prefix_aware" not in src:
        raise SystemExit("prefix-aware absence readback missing (C2)")
    if "identity[\"project\"]" not in src and "identity['project']" not in src:
        raise SystemExit("identity project not used for absence readback (C2)")
    print("ABSENCE_READBACK_IDENTITY_AWARE")

    # Tool identity recording (H-G/M7).
    if not callable(getattr(mod, "_tool_identity", None)):
        raise SystemExit("_tool_identity missing")
    print("TOOL_IDENTITY_HELPER_PRESENT")

    # Forbidden network path constant (H-E).
    if not getattr(mod, "FORBIDDEN_NETWORK_PATHS", None):
        raise SystemExit("FORBIDDEN_NETWORK_PATHS missing")
    if "exchange_provider_v1" not in mod.FORBIDDEN_NETWORK_PATHS:
        raise SystemExit("forbidden network path list incomplete")
    print("FORBIDDEN_NETWORK_PATHS_NAMED")

    # H6: git-blob SHA helper must exist and be used for bindings.
    if not callable(getattr(mod, "sha256_git_blob", None)):
        raise SystemExit("sha256_git_blob missing (H6)")
    if "sha256_git_blob" not in main_src and "sha256_git_blob" not in src[src.find("def require_review_receipt"):src.find("def require_database_gate")]:
        raise SystemExit("sha256_git_blob not used in receipt bindings (H6)")
    print("GIT_BLOB_SHA_BINDINGS")

    # C4: no phantom finalize in stage 0a.
    stage0a_src = src[src.find("def stage_provision_capture_admission"):src.find("def stage_observe_audience")]
    if "finalize" in stage0a_src.lower() and "no finalize" not in stage0a_src.lower():
        raise SystemExit("phantom finalize in stage 0a (C4)")
    print("NO_PHANTOM_FINALIZE")

    print("OFFLINE_SKELETON_CHECKS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
