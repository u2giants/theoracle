"""Offline skeleton checks for run_s08_journey_proof_v1.py — no DB, no effects.

Proves only what can be proved without Docker/database/provider:
  - runner imports and exposes the fail-closed bindings
  - every journey stage refuses closed (JourneyRefusal / NotImplementedError)
  - every journey stage with VALID bindings still refuses UNPROVEN (so
    deleting the final raise would fail this checker)
  - deadline negatives are driven with VALID bindings and assert the refusal
    message names the deadline (H5 — not a vacuous M9 refusal)
  - review receipt is fail-closed when absent, wrong-head, wrong-runner-SHA,
    wrong plan/checker/evidence SHA (H2: ALL FOUR SHA negatives tested), or
    non-APPROVE verdict
  - a CORRECT receipt (git-blob SHAs + matching head + APPROVE) is ACCEPTED
    and its returned bindings echo the four computed SHAs (L9)
  - database-gate helper requires a precise ALLOW line, rejects DENIED lines,
    and is invoked AFTER the review receipt (gate-before-database order)
  - gate exit-code contract: nonzero exit / timeout writes ops-database-gate.txt,
    searches DENIED in captured output, raises a tagged M4/M7 refusal (M4)
  - gate zero-exit contract (H1): DENIED-with-0 refuses naming DENIED,
    garbage-with-0 refuses (no precise ALLOW), clean ALLOW-with-0 returns
  - gate OSError is tagged M4/M7 (L6) — never escapes untagged
  - HEAD helper requires a full 40-char SHA
  - RECALL_* env refusal is present AND is the first substantive call in main
    (L5 order assertion)
  - inventory assertion helper is present and compares the sealed tuple,
    AND a monkeypatched drifted sealed tuple is refused (M2 drift-negative)
  - H3 sealed constants (SEALED_INVENTORY_DIGEST / SEALED_CATALOG_DIGEST)
    exist and are used instead of self-referential goldens
  - _inventory_digest_git_blob binds the exact 40-char head, not symbolic HEAD (L13)
  - budget helpers enforce a monotonic deadline (finite-only, entry+exit)
  - cleanup readback helper exists and is called from finally
  - cleanup paths use add_note to preserve the original exception (L15)
  - SCRATCH must not live inside the repository (behavioral: in-repo path
    refuses and creates no directory — M3)
  - SCRATCH reuse unlinks opposite markers (refusal.json vs journey-evidence.json)
  - SCRATCH reuse with leftover residue (e.g. ops-schema-receipt.json) raises
    a tagged JourneyRefusal (L3), never a raw FileExistsError
  - sticky-bit / parent-mode L2 ordering is behavioral where the host can
    express POSIX write bits (refuse before mkdir, no litter)
  - Python floor (M3) is behavioral via require_python_floor (a fake 3.10
    version_info refuses; 3.11+ passes) — not a static string scan (L5)
  - refused runs write refusal.json with refused=true and do NOT write
    journey-evidence.json (C8 exclusivity)
  - success path writes journey-evidence.json and does NOT write refusal.json
  - ops artifacts are labeled ops/non-evidence (sibling markers or inline)
  - stage binding schemas are present (M9) and main passes skeleton-shaped
    bindings (L14)
  - H4 pytest green-receipt logic is factored into sql_green_receipt_ok and
    behaves correctly on synthetic tails (H3/H4), including L1 skipped-count
    and collected-count pins (exactly 21 collected / 21 passed / 0 skipped)
  - openssl and pytest identities are checked (M7)
  - bare assert is not used for safety-critical checks (any indent / nesting)
  - snapshot is computed exactly twice (before + after gate), not 3×, and
    comment mentions do not count (L11)
  - SOURCE_SUFFIXES covers JS modules and Dockerfile/requirements variants (L10)
  - o_nofollow is honest both statically and behaviorally (L12)
  - JourneyUnknown routing is implemented, not just documented (M1), and the
    main-loop flow test proves a routable UNKNOWN routes to stage 5 then STOPS
    (no wire-byte injection after UNKNOWN, no double-run of stages)
  - docker compose preflight uses the argv literal ["compose","version"] (L8)

This checker restores runner state after every mutation. It does NOT execute
the journey and does NOT constitute acceptance. All SHA bindings use git-blob
semantics (sha256_git_blob), matching the runner's receipt expectations.
"""
from __future__ import annotations

import importlib.util
import json
import re
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
    # H3: use git-blob SHAs (same semantics as the runner's receipt bindings),
    # NOT worktree bytes. CRLF checkouts must not diverge from the receipt.
    runner_sha = mod.sha256_git_blob(RUNNER)
    plan_sha = mod.sha256_git_blob(PLAN)
    checker_sha = mod.sha256_git_blob(Path(__file__).resolve())
    evidence_sha = mod.sha256_git_blob(EVIDENCE)
    print("RUNNER_SHA256", runner_sha)
    print("PLAN_SHA256", plan_sha)
    print("CHECKER_SHA256", checker_sha)
    print("EVIDENCE_SHA256", evidence_sha)
    print("SHA_SEMANTICS git-blob (git show HEAD:path | sha256sum)")

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

    # UNPROVEN check: a stage with VALID bindings must still refuse UNPROVEN.
    # This catches a deleted final `raise JourneyRefusal(UNPROVEN)` — M9 binding
    # validation alone would pass with {} but a valid-binding call would not.
    valid_bindings = {
        "provision_capture_admission": {
            "workspace_id": "w-00000000-0000-0000-0000-000000000001",
            "meeting_id": "m-00000000-0000-0000-0000-000000000001",
            "owner_actor": "owner-1",
        },
        "observe_audience": {
            "meeting_id": "m-00000000-0000-0000-0000-000000000001",
            "observation_owner_sha256": "a" * 64,
        },
        "host_control": {
            "meeting_id": "m-00000000-0000-0000-0000-000000000001",
            "expected_head": "0" * 40,
            "operation_id": "op-00000000-0000-0000-0000-000000000001",
            "observation_id": "obs-00000000-0000-0000-0000-000000000001",
        },
        "current_turn": {
            "event_id": "00000000-0000-0000-0000-000000000001",
            "epoch_id": "ep-00000000-0000-0000-0000-000000000001",
            "capture_sha256": "b" * 64,
        },
        "sender": {
            "expected_revision": 1,
            "intent_id": "intent-00000000-0000-0000-0000-000000000001",
            "operation_id": "op-00000000-0000-0000-0000-000000000002",
            "admission_id": "adm-00000000-0000-0000-0000-000000000001",
        },
        "receipt_bytes_in": {
            "raw_wire": b"x",
            "claim_event_id": "00000000-0000-0000-0000-000000000002",
            "operation_id": "op-00000000-0000-0000-0000-000000000003",
            "admission_id": "adm-00000000-0000-0000-0000-000000000001",
        },
        "status_reconcile": {
            "intent_id": "intent-00000000-0000-0000-0000-000000000001",
            "claim_event_id": "00000000-0000-0000-0000-000000000002",
            "admission_id": "adm-00000000-0000-0000-0000-000000000001",
        },
    }
    unproven_cases = (
        ("stage_provision_capture_admission", lambda: mod.stage_provision_capture_admission(valid_bindings["provision_capture_admission"], 30)),
        ("stage_observe_audience", lambda: mod.stage_observe_audience(valid_bindings["observe_audience"], 30)),
        ("stage_host_control", lambda: mod.stage_host_control(valid_bindings["host_control"], 30)),
        ("stage_current_turn", lambda: mod.stage_current_turn(valid_bindings["current_turn"], 30)),
        ("stage_sender", lambda: mod.stage_sender(valid_bindings["sender"], 30)),
        ("stage_receipt_bytes_in", lambda: mod.stage_receipt_bytes_in(valid_bindings["receipt_bytes_in"], 30)),
        ("stage_status_reconcile", lambda: mod.stage_status_reconcile(valid_bindings["status_reconcile"], 30)),
    )
    for name, call in unproven_cases:
        try:
            call()
        except mod.JourneyRefusal as e:
            msg = str(e).lower()
            if "unproven" not in msg and "not released" not in msg:
                raise SystemExit(f"stage {name} refused but not UNPROVEN: {e}")
            print("STAGE_UNPROVEN_WITH_VALID_BINDINGS", name)
        else:
            raise SystemExit("stage with valid bindings did not refuse UNPROVEN: " + name)

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
    # M2: drift-negative — monkeypatch the sealed tuple to a drifted value and
    # assert refusal (a hardcoded-return mutant would pass the call above).
    original_sealed = mod.SEALED_MIGRATION_INVENTORY
    try:
        mod.SEALED_MIGRATION_INVENTORY = ("001_foundation.sql", "002_pilot.sql")
        try:
            mod.assert_sealed_inventory()
        except mod.JourneyRefusal as e:
            if "drift" not in str(e).lower():
                raise SystemExit(f"inventory drift refusal does not name drift (M2): {e}")
            print("INVENTORY_DRIFT_REFUSED", str(e)[:80])
        else:
            raise SystemExit(
                "assert_sealed_inventory accepted a drifted sealed tuple (M2)"
            )
    finally:
        mod.SEALED_MIGRATION_INVENTORY = original_sealed

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
    # M3: _scratch must be behavioral, not just a string check. Set
    # SCRATCH_ENV inside the repo and assert JourneyRefusal; assert no
    # directory was created on the refused path (no litter).
    import os as _os_m3

    saved_scratch_env = _os_m3.environ.get(mod.SCRATCH_ENV)
    in_repo_target = Path(mod.ROOT) / "scratch-inside-repo-forbidden-m3"
    try:
        _os_m3.environ[mod.SCRATCH_ENV] = str(in_repo_target)
        try:
            mod._scratch()
        except mod.JourneyRefusal as e:
            if "SCRATCH must not live inside the repository" not in str(e):
                raise SystemExit(f"scratch in-repo refusal message wrong (M3): {e}")
            print("SCRATCH_IN_REPO_REFUSED_BEHAVIORAL", str(e)[:80])
        else:
            raise SystemExit(
                "_scratch accepted a path inside the repository (M3)"
            )
        if in_repo_target.exists():
            raise SystemExit(
                "_scratch created a directory inside the repository on "
                "refusal (M3/L2 litter)"
            )
    finally:
        if saved_scratch_env is None:
            _os_m3.environ.pop(mod.SCRATCH_ENV, None)
        else:
            _os_m3.environ[mod.SCRATCH_ENV] = saved_scratch_env
    # L3: SCRATCH_ENV reuse with leftover ops-schema-receipt.json must raise
    # a tagged JourneyRefusal (not a raw FileExistsError from the schema
    # receipt O_EXCL write further downstream).
    with tempfile.TemporaryDirectory() as td:
        reuse = Path(td) / "reused-scratch"
        reuse.mkdir()
        (reuse / "ops-schema-receipt.json").write_text("{}\n")
        _os_m3.environ[mod.SCRATCH_ENV] = str(reuse)
        try:
            mod._scratch()
        except mod.JourneyRefusal as e:
            msg = str(e)
            if "L3" not in msg and "residue" not in msg.lower() and "empty" not in msg.lower():
                raise SystemExit(
                    f"SCRATCH reuse residue refusal not tagged (L3): {e}"
                )
            print("SCRATCH_REUSE_RESIDUE_REFUSED", msg[:80])
        except OSError as e:
            raise SystemExit(
                f"SCRATCH reuse raised raw OSError/FileExistsError (L3): "
                f"{type(e).__name__}: {e}"
            )
        else:
            raise SystemExit(
                "_scratch accepted reused scratch with leftover "
                "ops-schema-receipt.json (L3)"
            )
        finally:
            if saved_scratch_env is None:
                _os_m3.environ.pop(mod.SCRATCH_ENV, None)
            else:
                _os_m3.environ[mod.SCRATCH_ENV] = saved_scratch_env
    # L2: sticky-bit / parent-mode ordering behavioral — a world-writable
    # non-sticky parent must refuse BEFORE mkdir (no litter). Feasible only
    # where the host can express POSIX write bits (the runner degrades this
    # check on Windows via the same os.getuid pattern as _receipt_stat_ok).
    import stat as _stat_m3

    if not hasattr(_os_m3, "getuid"):
        print("L2_STICKY_BIT_SKIP unavailable-on-windows")
    else:
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td) / "ww-parent"
            parent.mkdir()
            try:
                parent.chmod(0o777)
            except OSError:
                print("L2_STICKY_BIT_SKIP chmod-unavailable")
            else:
                pst = parent.stat()
                # S_ISVTX is the sticky-bit mask constant (no predicate function).
                if pst.st_mode & 0o022 and not (pst.st_mode & _stat_m3.S_ISVTX):
                    child = parent / "scratch-child"
                    _os_m3.environ[mod.SCRATCH_ENV] = str(child)
                    try:
                        mod._scratch()
                    except mod.JourneyRefusal as e:
                        if "sticky" not in str(e).lower() and "L2" not in str(e):
                            raise SystemExit(f"L2 parent-mode refusal not tagged: {e}")
                        if child.exists():
                            raise SystemExit(
                                "scratch created despite L2 parent refusal (litter)"
                            )
                        print("L2_PARENT_MODE_REFUSED_BEFORE_MKDIR", str(e)[:80])
                    else:
                        raise SystemExit(
                            "_scratch accepted a world-writable non-sticky parent (L2)"
                        )
                    finally:
                        if saved_scratch_env is None:
                            _os_m3.environ.pop(mod.SCRATCH_ENV, None)
                        else:
                            _os_m3.environ[mod.SCRATCH_ENV] = saved_scratch_env
                else:
                    print("L2_STICKY_BIT_SKIP host-cannot-express-mode-bits")

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

    # C8: ops artifacts labeled ops/non-evidence (sibling markers or inline).
    for ops_marker in ("ops-database-gate.txt", "ops-source-after-gate.json", "ops-schema-receipt.json"):
        if ops_marker not in src:
            raise SystemExit(f"ops artifact {ops_marker} missing (C8)")
    if "_label_ops_artifact" not in src and '"ops": True' not in src and "'ops': True" not in src:
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

            # wrong runner SHA (H2/M-B) — assert message names the mutated key.
            write_release({**good, "runner_sha256": "0" * 64})
            try:
                mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                if "runner_sha256" not in str(e):
                    raise SystemExit(f"runner-SHA refusal does not name the key: {e}")
                print("RUNNER_SHA_MISMATCH_FAIL_CLOSED", str(e)[:80])
            else:
                raise SystemExit("runner_sha256 mismatch did not fail closed")

            # wrong plan SHA — assert message names the mutated key.
            write_release({**good, "plan_sha256": "0" * 64})
            try:
                mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                if "plan_sha256" not in str(e):
                    raise SystemExit(f"plan-SHA refusal does not name the key: {e}")
                print("PLAN_SHA_MISMATCH_FAIL_CLOSED", str(e)[:80])
            else:
                raise SystemExit("plan_sha256 mismatch did not fail closed")

            # H2: wrong checker SHA — assert message names the mutated key.
            write_release({**good, "checker_sha256": "0" * 64})
            try:
                mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                if "checker_sha256" not in str(e):
                    raise SystemExit(f"checker-SHA refusal does not name the key: {e}")
                print("CHECKER_SHA_MISMATCH_FAIL_CLOSED", str(e)[:80])
            else:
                raise SystemExit("checker_sha256 mismatch did not fail closed")

            # H2: wrong evidence SHA — assert message names the mutated key.
            write_release({**good, "evidence_sha256": "0" * 64})
            try:
                mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                if "evidence_sha256" not in str(e):
                    raise SystemExit(f"evidence-SHA refusal does not name the key: {e}")
                print("EVIDENCE_SHA_MISMATCH_FAIL_CLOSED", str(e)[:80])
            else:
                raise SystemExit("evidence_sha256 mismatch did not fail closed")

            # wrong head — assert message names head.
            write_release({**good, "head": "0" * 40})
            try:
                mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                if "head" not in str(e).lower():
                    raise SystemExit(f"head refusal does not name head: {e}")
                print("REVIEW_HEAD_FAIL_CLOSED", str(e)[:80])
            else:
                raise SystemExit("wrong head did not fail closed")

            # non-APPROVE verdict — assert message names verdict.
            write_release({**good, "verdict": "REJECT"})
            try:
                mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                if "verdict" not in str(e).lower() and "APPROVE" not in str(e):
                    raise SystemExit(f"verdict refusal does not name verdict: {e}")
                print("REVIEW_VERDICT_FAIL_CLOSED", str(e)[:80])
            else:
                raise SystemExit("non-APPROVE verdict did not fail closed")

            # Positive path: a CORRECT receipt (git-blob SHAs + matching head
            # + APPROVE) must be ACCEPTED. Without this, a runner that refuses
            # everything passes the checker.
            write_release(good)
            try:
                result = mod.require_review_receipt(head, scratch)
            except mod.JourneyRefusal as e:
                raise SystemExit(f"correct receipt was refused (positive test failed): {e}")
            else:
                if result.get("receipt", {}).get("verdict") != "APPROVE":
                    raise SystemExit("positive receipt accepted but verdict not APPROVE")
                # L9: pin the bindings echo against the four computed SHAs.
                got_bindings = result.get("bindings") or {}
                expected_bindings = {
                    "runner_sha256": runner_sha,
                    "plan_sha256": plan_sha,
                    "checker_sha256": checker_sha,
                    "evidence_sha256": evidence_sha,
                }
                if got_bindings != expected_bindings:
                    raise SystemExit(
                        f"positive receipt bindings echo mismatch (L9): "
                        f"got={got_bindings} expected={expected_bindings}"
                    )
                print("REVIEW_RECEIPT_POSITIVE_ACCEPTED")
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

    # M4: gate exit-code contract — nonzero exit must write ops-database-gate.txt,
    # search DENIED in the captured output, and raise a tagged refusal with tail.
    # A raw CalledProcessError must never escape require_database_gate.
    import subprocess as _sp
    from unittest import mock as _mock

    with tempfile.TemporaryDirectory() as td:
        gscratch = Path(td)
        gate_tools = {
            "ai-task-gates": {"path": "fake-gate", "name": "ai-task-gates", "version": "fake"}
        }
        fake_denied = "gate: DENIED\nreason: not authorized\n"
        with _mock.patch.object(
            _sp,
            "check_output",
            side_effect=_sp.CalledProcessError(2, ["fake-gate"], output=fake_denied),
        ):
            try:
                mod.require_database_gate(gscratch, gate_tools)
            except mod.JourneyRefusal as e:
                msg = str(e)
                if "DENIED" not in msg:
                    raise SystemExit(f"gate nonzero-exit refusal does not name DENIED (M4): {e}")
                if "M4" not in msg and "M7" not in msg:
                    raise SystemExit(f"gate nonzero-exit refusal not tagged M4/M7 (M4): {e}")
            except _sp.CalledProcessError:
                raise SystemExit("raw CalledProcessError escaped require_database_gate (M4)")
            else:
                raise SystemExit("gate nonzero exit was not refused (M4)")
            ops = gscratch / "ops-database-gate.txt"
            if not ops.exists():
                raise SystemExit("ops-database-gate.txt not written on nonzero exit (M4)")
            if "DENIED" not in ops.read_text(encoding="utf-8"):
                raise SystemExit("ops-database-gate.txt missing captured DENIED output (M4)")
        # Nonzero exit WITHOUT a DENIED line must still refuse with a tail.
        fake_nodeny = "something went wrong\n"
        with _mock.patch.object(
            _sp,
            "check_output",
            side_effect=_sp.CalledProcessError(2, ["fake-gate"], output=fake_nodeny),
        ):
            try:
                mod.require_database_gate(gscratch, gate_tools)
            except mod.JourneyRefusal as e:
                if "M4" not in str(e) and "M7" not in str(e):
                    raise SystemExit(f"gate nonzero-no-DENIED refusal not tagged (M4): {e}")
                if "tail" not in str(e).lower() and "exited" not in str(e).lower():
                    raise SystemExit(f"gate nonzero refusal missing tail/exit info (M4): {e}")
            else:
                raise SystemExit("gate nonzero exit without DENIED was not refused (M4)")
        # Timeout must also refuse with a tag.
        with _mock.patch.object(
            _sp,
            "check_output",
            side_effect=_sp.TimeoutExpired(cmd="fake-gate", timeout=60),
        ):
            try:
                mod.require_database_gate(gscratch, gate_tools)
            except mod.JourneyRefusal as e:
                if "M4" not in str(e) and "M5" not in str(e):
                    raise SystemExit(f"gate timeout refusal not tagged (M4): {e}")
            else:
                raise SystemExit("gate timeout was not refused (M4)")
        # H1 (round-7): zero-exit contract was vacuous — the runner's zero-exit
        # DENIED and zero-exit no-ALLOW branches had no behavioral coverage, so a
        # mutation deleting them would pass all three nonzero/timeout mock cases.
        # DENIED-with-0 must refuse naming DENIED; garbage-with-0 must refuse
        # (no precise ALLOW); clean ALLOW-with-0 must return the output.
        fake_denied0 = "gate: DENIED\nreason: not authorized\n"
        with _mock.patch.object(_sp, "check_output", return_value=fake_denied0):
            try:
                mod.require_database_gate(gscratch, gate_tools)
            except mod.JourneyRefusal as e:
                if "DENIED" not in str(e):
                    raise SystemExit(
                        f"zero-exit DENIED refusal does not name DENIED (H1): {e}"
                    )
            except _sp.CalledProcessError:
                raise SystemExit("raw CalledProcessError escaped on zero-exit DENIED (H1)")
            else:
                raise SystemExit("zero-exit DENIED was accepted as gate success (H1)")
        fake_garbage0 = "something else entirely\nnot a gate line\n"
        with _mock.patch.object(_sp, "check_output", return_value=fake_garbage0):
            try:
                mod.require_database_gate(gscratch, gate_tools)
            except mod.JourneyRefusal as e:
                if "ALLOW" not in str(e):
                    raise SystemExit(
                        f"zero-exit garbage refusal does not name ALLOW (H1): {e}"
                    )
            else:
                raise SystemExit("zero-exit garbage was accepted as gate success (H1)")
        fake_allow0 = "gate: ALLOW\n"
        with _mock.patch.object(_sp, "check_output", return_value=fake_allow0):
            try:
                out0 = mod.require_database_gate(gscratch, gate_tools)
            except mod.JourneyRefusal as e:
                raise SystemExit(f"clean ALLOW-with-0 was refused (H1): {e}")
            else:
                if "ALLOW" not in out0:
                    raise SystemExit(
                        f"clean ALLOW-with-0 did not return the gate output (H1): {out0!r}"
                    )
        # L6: OSError (missing/unexecutable gate binary) must raise a tagged
        # M4/M7 JourneyRefusal — never escape untagged to main's generic handler.
        with _mock.patch.object(
            _sp, "check_output", side_effect=FileNotFoundError(2, "no such file", "fake-gate")
        ):
            try:
                mod.require_database_gate(gscratch, gate_tools)
            except mod.JourneyRefusal as e:
                if "M4" not in str(e) and "M7" not in str(e):
                    raise SystemExit(f"gate OSError refusal not tagged M4/M7 (L6): {e}")
            except OSError:
                raise SystemExit("raw OSError escaped require_database_gate (L6)")
            else:
                raise SystemExit("gate OSError was not refused (L6)")
    print("M4_GATE_EXIT_CODE_CONTRACT")
    print("M4_ZERO_EXIT_DENIED_GARBAGE_ALLOW")
    print("L6_GATE_OSError_TAGGED")
    # M4: the pytest identity preflight must be wrapped (tagged M4/M7), not a
    # bare check_output that surfaces a raw CalledProcessError.
    if "pytest identity unavailable" not in src:
        raise SystemExit("pytest preflight tagged refusal missing (M4)")
    if "except (" not in main_src and "except subprocess.CalledProcessError" not in main_src:
        raise SystemExit("pytest preflight not wrapped in try/except (M4)")

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

    # Tool identity recording (H-G/M7) — and C1: execute _tool_identity
    # against real tools to prove the identity commands work.
    if not callable(getattr(mod, "_tool_identity", None)):
        raise SystemExit("_tool_identity missing")
    # C1: execute against real tools. ai-task-gates uses `version` subcommand.
    for tool_name in ("git", "ai-task-gates"):
        try:
            ident = mod._tool_identity(tool_name)
        except mod.JourneyRefusal as e:
            raise SystemExit(f"_tool_identity({tool_name!r}) refused: {e}")
        if not ident.get("version"):
            raise SystemExit(f"_tool_identity({tool_name!r}) returned no version")
        print(f"TOOL_IDENTITY_EXECUTED {tool_name} {ident['version'][:60]}")
    # C1: verify TOOL_VERSION_ARGS maps ai-task-gates to ("version",) not ("--version",).
    if not hasattr(mod, "TOOL_VERSION_ARGS"):
        raise SystemExit("TOOL_VERSION_ARGS missing (C1)")
    if mod.TOOL_VERSION_ARGS.get("ai-task-gates") != ("version",):
        raise SystemExit(f"ai-task-gates version args wrong: {mod.TOOL_VERSION_ARGS.get('ai-task-gates')!r} (C1)")
    if mod.TOOL_VERSION_ARGS.get("openssl") != ("version",):
        raise SystemExit(f"openssl version args wrong: {mod.TOOL_VERSION_ARGS.get('openssl')!r} (C1)")
    print("TOOL_VERSION_ARGS_OK")

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

    # L2: sticky-bit exception must exist for /tmp-style world-writable parents.
    if "S_ISVTX" not in src:
        raise SystemExit("S_ISVTX sticky-bit exception missing (L2)")
    if "mkdir" in src and src.find("parent") > src.find("mkdir"):
        pass  # parent check may be before or after; the key is S_ISVTX presence
    print("STICKY_BIT_EXCEPTION_PRESENT")

    # L2: mkdir must run AFTER the parent check (no litter on refuse).
    scratch_fn = src[src.find("def _scratch"):src.find("def _monotonic_end")]
    i_parent_check = scratch_fn.find("S_ISVTX")
    i_mkdir = scratch_fn.find("scratch.mkdir")
    if i_mkdir >= 0 and i_parent_check >= 0 and i_mkdir < i_parent_check:
        raise SystemExit("scratch.mkdir runs before parent check (L2 litter)")
    print("MKDIR_AFTER_PARENT_CHECK")

    # H3: sealed constants must exist and be used, not self-referential goldens.
    if "SEALED_INVENTORY_DIGEST" not in src:
        raise SystemExit("SEALED_INVENTORY_DIGEST missing (H3)")
    if "SEALED_CATALOG_DIGEST" not in src:
        raise SystemExit("SEALED_CATALOG_DIGEST missing (H3)")
    if "expected_inventory_digest = _inventory_digest(files)" in src:
        raise SystemExit("self-referential inventory golden still present (H3)")
    # Catalog golden must not come from the schema receipt.
    if "golden_catalog = schema_receipt_data" in src:
        raise SystemExit("catalog golden from schema-receipt (self-referential, H3)")
    # C2: recompute the inventory digest over git-blob bytes and verify the
    # constant matches. Not just a presence check. L13: pass the bound head.
    if not callable(getattr(mod, "_inventory_digest_git_blob", None)):
        raise SystemExit("_inventory_digest_git_blob missing (C2)")
    sealed_inv = mod.SEALED_INVENTORY_DIGEST
    if not isinstance(sealed_inv, str) or not __import__("re").fullmatch(r"[0-9a-f]{64}", sealed_inv):
        raise SystemExit(f"SEALED_INVENTORY_DIGEST is not 64-hex: {sealed_inv!r}")
    observed_inv = mod._inventory_digest_git_blob(mod.SEALED_MIGRATION_INVENTORY, head)
    if observed_inv != sealed_inv:
        raise SystemExit(
            f"SEALED_INVENTORY_DIGEST wrong: sealed={sealed_inv} observed={observed_inv} (C2)"
        )
    print("C2_INVENTORY_DIGEST_RECOMPUTED", observed_inv[:16])
    # L13: symbolic HEAD must be refused — only a full 40-char bound head.
    try:
        mod._inventory_digest_git_blob(mod.SEALED_MIGRATION_INVENTORY, "HEAD")
    except mod.JourneyRefusal as e:
        if "40-char" not in str(e) and "L13" not in str(e):
            raise SystemExit(f"symbolic-head refusal not tagged (L13): {e}")
    else:
        raise SystemExit("symbolic HEAD accepted by _inventory_digest_git_blob (L13)")
    # C3: catalog check must be "recorded, not golden" — no refuse-on-empty.
    # Verify the runner does NOT refuse when SEALED_CATALOG_DIGEST is empty.
    if 'raise JourneyRefusal(\n                    "SEALED_CATALOG_DIGEST is not a 64-hex' in src:
        raise SystemExit("refuse-on-empty for SEALED_CATALOG_DIGEST still present (C3)")
    if "fill it from a trusted bootstrap before release" in src:
        raise SystemExit("circular catalog fill instruction still present (C3)")
    print("C3_CATALOG_RECORDED_NOT_GOLDEN")
    print("H3_SEALED_CONSTANTS_PRESENT")

    # SCRATCH reuse: opposite markers must be unlinked.
    if "refusal.json" not in src or "journey-evidence.json" not in src:
        raise SystemExit("marker filenames missing")
    # _write_refusal must unlink journey-evidence.json
    write_refusal_src = src[src.find("def _write_refusal"):src.find("def main")]
    if "journey-evidence.json" not in write_refusal_src or "unlink" not in write_refusal_src:
        raise SystemExit("_write_refusal does not unlink stale journey-evidence.json")
    # Success path must unlink refusal.json
    if "refusal.json" not in main_src or "unlink" not in main_src:
        raise SystemExit("success path does not unlink stale refusal.json")
    print("SCRATCH_REUSE_MARKERS_UNLINKED")

    # C8: all four ops artifacts labeled via sibling markers or inline.
    for ops_name in ("ops-database-gate.txt", "ops-source-after-gate.json",
                     "ops-schema-receipt.json", "ops-sql-green.txt"):
        if ops_name not in src:
            raise SystemExit(f"ops artifact {ops_name} missing (C8)")
    if "_label_ops_artifact" not in src:
        raise SystemExit("_label_ops_artifact helper missing (C8)")
    # M5: verify each ops artifact is actually labeled — not just that the
    # helper is called N times (which counts the def line).
    for ops_name in ("ops-database-gate.txt", "ops-source-after-gate.json",
                     "ops-schema-receipt.json", "ops-sql-green.txt"):
        label_for = f'_label_ops_artifact(scratch, "{ops_name}")'
        label_for_sq = f"_label_ops_artifact(scratch, '{ops_name}')"
        if label_for not in src and label_for_sq not in src:
            raise SystemExit(f"ops artifact {ops_name} not labeled via _label_ops_artifact (M5)")
    print("OPS_ARTIFACTS_SIBLING_MARKERS")

    # H3: source snapshot must be computed exactly twice in main (before + after gate).
    # The def is outside main_src; count only calls inside main, excluding
    # comment text (L11 — a comment mentioning source_snapshot() must not count).
    snap_calls = 0
    for line in main_src.splitlines():
        code = line.split("#", 1)[0]
        snap_calls += code.count("source_snapshot()")
    if snap_calls != 2:  # exactly 2 calls in main: before gate + after gate
        raise SystemExit(f"source_snapshot called {snap_calls}× in main; expected exactly 2 (M4)")
    print("SNAPSHOT_COMPUTED_TWICE")

    # L10: SOURCE_SUFFIXES must cover JS module extensions (dev/oracle2 ships
    # .mjs/.mts), and Dockerfile variants / requirements files must be
    # snapshotted via _is_snapshotted_source.
    for ext in (".js", ".mjs", ".cjs", ".mts"):
        if ext not in mod.SOURCE_SUFFIXES:
            raise SystemExit(f"SOURCE_SUFFIXES missing {ext} (L10)")
    if not callable(getattr(mod, "_is_snapshotted_source", None)):
        raise SystemExit("_is_snapshotted_source missing (L10)")
    from pathlib import Path as _P

    if not mod._is_snapshotted_source(_P("/x/Dockerfile.web"), "Dockerfile.web"):
        raise SystemExit("Dockerfile variant not snapshotted (L10)")
    if not mod._is_snapshotted_source(_P("/x/api.Dockerfile"), "api.Dockerfile"):
        raise SystemExit(".Dockerfile suffix variant not snapshotted (L10)")
    if not mod._is_snapshotted_source(_P("/x/requirements-dev.txt"), "requirements-dev.txt"):
        raise SystemExit("requirements-*.txt not snapshotted (L10)")
    if mod._is_snapshotted_source(_P("/x/notes.txt"), "notes.txt"):
        raise SystemExit("ordinary .txt wrongly snapshotted (L10)")
    print("L10_SOURCE_SUFFIXES_EXTENDED")

    # H4: pytest regex must reject failed/error counts (and L1: skipped too).
    if (
        r"\b\d+\s+(?:failed|errors?|skipped|xfailed|xpassed|deselected)\b" not in src
        and r"\d+\s+(?:failed|errors?|skipped)" not in src
    ):
        raise SystemExit("H4/L1 regex does not reject failed/error/skipped counts")
    if "skipped" not in src:
        raise SystemExit("H4/L1 regex does not cover skipped counts")
    # TimeoutExpired must be handled.
    if "TimeoutExpired" not in src:
        raise SystemExit("TimeoutExpired not handled (H4)")
    # pytest flags: no:cacheprovider and PYTHONDONTWRITEBYTECODE.
    if "no:cacheprovider" not in src:
        raise SystemExit("-p no:cacheprovider missing (H4 tree cleanliness)")
    if "PYTHONDONTWRITEBYTECODE" not in src:
        raise SystemExit("PYTHONDONTWRITEBYTECODE missing (H4 tree cleanliness)")
    print("H4_REGEX_STRICT_AND_TIMEOUT_HANDLED")

    # H3/H4: the 21-passed / failed-error logic is factored into
    # sql_green_receipt_ok and must behave correctly on synthetic tails —
    # a static string scan cannot detect a disconnected regex (Muse H3/H4).
    if not callable(getattr(mod, "sql_green_receipt_ok", None)):
        raise SystemExit("sql_green_receipt_ok missing (H3/H4)")
    green_cases = (
        # (tail, expected_ok)
        ("21 passed in 3.0s", True),
        ("21 passed, 1 failed", False),
        ("1 failed, 20 passed", False),
        ("121 passed", False),  # boundary: 121 is NOT 21
        ("2 errors", False),
        ("21 passed", True),
        ("= 21 passed, 1 error in 1.0s =", False),
        ("21  passed", True),  # whitespace-flexible inside the count
        ("22 passed", False),
        # L1: skipped/xfailed/xpassed/deselected are non-green. "21 passed,
        # 1 skipped" (22 collected) must NOT count as green.
        ("21 passed, 1 skipped in 2.0s", False),
        ("collected 22 items\n\n21 passed, 1 skipped in 2.0s", False),
        ("21 passed, 1 xfailed", False),
        ("21 passed, 2 deselected in 1.0s", False),
        ("collected 21 items\n\n21 passed in 3.0s", True),
        ("collected 22 items\n\n21 passed in 3.0s", False),  # L1: collected pin
        ("collected 20 items\n\n21 passed in 3.0s", False),  # L1: collected pin
    )
    for tail, expected_ok in green_cases:
        ok, reason = mod.sql_green_receipt_ok(tail)
        if ok is not expected_ok:
            raise SystemExit(
                f"sql_green_receipt_ok({tail!r}) returned {ok}, expected {expected_ok} (H3/H4); reason={reason!r}"
            )
        if not ok and not reason:
            raise SystemExit(f"sql_green_receipt_ok({tail!r}) failed without a reason (H3/H4)")
    print("H3_H4_SQL_GREEN_HELPER_BEHAVIORAL_OK")

    # H3: "21 passed" positive requirement must be enforced in the runner.
    if r"\b21\s+passed\b" not in src:
        raise SystemExit("21 passed positive assertion missing from runner (H3)")
    # Meta-check: deleting the positive assertion must fail this checker.
    # We verify the regex is present AND used in a refusal path.
    if "21 SQL green receipt not observed" not in src:
        raise SystemExit("21-passed refusal message missing (H3)")
    print("H3_21_PASSED_POSITIVE_ENFORCED")

    # H4: file-check negatives — _receipt_stat_ok must reject symlink,
    # oversized file, and (on Linux) group-readable mode / nlink!=1.
    import os as _os
    import stat as _stat

    with tempfile.TemporaryDirectory() as td:
        ftd = Path(td)
        # Oversized file
        big = ftd / "big.json"
        big.write_bytes(b"x" * 5000)
        try:
            mod._receipt_stat_ok(big)
        except (mod.JourneyRefusal, OSError):
            pass
        else:
            checks_big, _ = mod._receipt_stat_ok(big)
            if checks_big.get("passed"):
                raise SystemExit("oversized receipt passed stat checks (H4)")
        print("H4_SIZE_NEGATIVE_OK")
        # Symlink to a regular file
        target = ftd / "target.json"
        target.write_text("{}\n")
        link = ftd / "link.json"
        try:
            link.symlink_to(target)
        except OSError:
            print("H4_SYMLINK_SKIP unavailable-on-windows")
        else:
            try:
                mod._receipt_stat_ok(link)
            except (mod.JourneyRefusal, OSError):
                pass
            else:
                checks_link, _ = mod._receipt_stat_ok(link)
                # On hosts without O_NOFOLLOW, symlink may be followed;
                # the lstat cross-check should still catch it.
                if checks_link.get("passed") and checks_link.get("lstat_matches"):
                    raise SystemExit("symlink receipt passed stat checks (H4)")
            print("H4_SYMLINK_NEGATIVE_OK")
        # Group-readable mode (Linux only — Windows cannot express POSIX bits)
        if hasattr(_os, "getuid"):
            gr = ftd / "group-readable.json"
            gr.write_text("{}\n")
            gr.chmod(0o644)
            checks_gr, _ = mod._receipt_stat_ok(gr)
            if checks_gr.get("passed"):
                raise SystemExit("group-readable receipt passed stat checks (H4)")
            print("H4_MODE_NEGATIVE_OK")
        else:
            print("H4_MODE_SKIP unavailable-on-windows")
        # nlink!=1 via hardlink (Linux only)
        if hasattr(_os, "getuid"):
            nlink_src = ftd / "nlink-src.json"
            nlink_src.write_text("{}\n")
            nlink_hard = ftd / "nlink-hard.json"
            try:
                _os.link(nlink_src, nlink_hard)
            except OSError:
                print("H4_NLINK_SKIP hardlink-unavailable")
            else:
                checks_nl, _ = mod._receipt_stat_ok(nlink_src)
                if checks_nl.get("passed"):
                    raise SystemExit("nlink!=1 receipt passed stat checks (H4)")
                print("H4_NLINK_NEGATIVE_OK")
        else:
            print("H4_NLINK_SKIP unavailable-on-windows")

    # H5: deadline negatives — stages must reject 0, 31, "30", None.
    # Drive with VALID bindings (valid_bindings above) so the deadline check
    # is actually reached: empty bindings refuse on M9 missing-keys first and
    # never execute the M5 line. Assert the refusal message names the deadline
    # (M5 tag or "deadline"), so a vacuous JourneyRefusal from some other
    # check cannot satisfy this test (Muse H5).
    deadline_negatives = (0, 31, "30", None)
    for bad_dl in deadline_negatives:
        for stage_name, stage_fn in (
            ("provision_capture_admission", mod.stage_provision_capture_admission),
            ("observe_audience", mod.stage_observe_audience),
            ("host_control", mod.stage_host_control),
            ("current_turn", mod.stage_current_turn),
            ("sender", mod.stage_sender),
            ("receipt_bytes_in", mod.stage_receipt_bytes_in),
            ("status_reconcile", mod.stage_status_reconcile),
        ):
            try:
                stage_fn(dict(valid_bindings[stage_name]), bad_dl)
            except mod.JourneyRefusal as e:
                msg = str(e).lower()
                if "deadline" not in msg and "m5" not in msg:
                    raise SystemExit(
                        f"stage {stage_name} refused bad deadline {bad_dl!r} "
                        f"but message does not name the deadline (H5): {e}"
                    )
            else:
                raise SystemExit(
                    f"stage {stage_name} accepted bad deadline {bad_dl!r} (H5)"
                )
    print("H5_DEADLINE_NEGATIVES_OK")

    # H6: o_nofollow must be honest (not hardcoded True).
    if '"o_nofollow": True' in src or "'o_nofollow': True" in src:
        raise SystemExit("o_nofollow hardcoded True (H6)")
    if "getattr(os, \"O_NOFOLLOW\", 0) != 0" not in src and "getattr(os, 'O_NOFOLLOW', 0) != 0" not in src:
        # Check for the variable form
        if "o_nofollow_available" not in src:
            raise SystemExit("o_nofollow honest check missing (H6)")
    print("H6_O_NOFOLLOW_HONEST")
    # L12: one-call behavioral check — the o_nofollow value in the returned
    # checks must equal real O_NOFOLLOW availability on this host.
    import os as _os_h6

    with tempfile.TemporaryDirectory() as td:
        ok_file = Path(td) / "ok.json"
        ok_file.write_text("{}\n")
        checks_ok, _ = mod._receipt_stat_ok(ok_file)
        expected_o_nofollow = getattr(_os_h6, "O_NOFOLLOW", 0) != 0
        if checks_ok.get("o_nofollow") is not expected_o_nofollow:
            raise SystemExit(
                f"o_nofollow not honest (L12): checks={checks_ok.get('o_nofollow')!r} "
                f"host={expected_o_nofollow!r}"
            )
    print("H6_O_NOFOLLOW_BEHAVIORAL_OK")

    # H1: Windows mode/nlink degradation must be present.
    if "unavailable-on-windows" not in src:
        raise SystemExit("Windows mode/nlink degradation missing (H1)")
    if "mode_check" not in src:
        raise SystemExit("mode_check degradation key missing (H1)")
    print("H1_WINDOWS_DEGRADATION_PRESENT")

    # M1: JourneyUnknown subclass must exist for routable UNKNOWN.
    if not hasattr(mod, "JourneyUnknown"):
        raise SystemExit("JourneyUnknown missing (M1)")
    if not issubclass(mod.JourneyUnknown, mod.JourneyRefusal):
        raise SystemExit("JourneyUnknown must subclass JourneyRefusal (M1)")
    print("M1_JOURNEY_UNKNOWN_SUBCLASS")
    # M1: routing must be implemented, not just documented. The main loop
    # catches JourneyUnknown separately, and _route_unknown encodes the H5
    # policy: claim/readback-loss (sender, receipt_bytes_in) -> stage 5;
    # every other stage -> empty (STOP at that stage).
    if not callable(getattr(mod, "_route_unknown", None)):
        raise SystemExit("_route_unknown missing (M1 routing stub)")
    for routed_stage in ("sender", "receipt_bytes_in"):
        onward = mod._route_unknown(routed_stage)
        if onward != ("status_reconcile",):
            raise SystemExit(
                f"_route_unknown({routed_stage!r}) must route to stage 5: {onward!r} (M1)"
            )
    for end_stage in (
        "provision_capture_admission",
        "observe_audience",
        "host_control",
        "current_turn",
        "status_reconcile",
    ):
        onward = mod._route_unknown(end_stage)
        if onward != ():
            raise SystemExit(
                f"_route_unknown({end_stage!r}) must end at that stage: {onward!r} (M1)"
            )
    # M1: the stage-loop helper (the real main-loop body) must catch
    # JourneyUnknown; main must call that helper. The catch moved into
    # _run_stage_order when the loop was extracted for the flow test.
    if "_run_stage_order(" not in main_src:
        raise SystemExit("main does not call _run_stage_order (M1 wiring)")
    run_order_src = src[src.find("def _run_stage_order") : src.find("SKELETON_STAGE_BINDINGS")]
    if "except JourneyUnknown" not in run_order_src:
        raise SystemExit("stage-order helper does not catch JourneyUnknown (M1)")
    # M1 (round-7): main-loop flow — a routable UNKNOWN must route to its
    # onward stage then END the sequence. It must NOT resume STAGE_ORDER
    # (no receipt_bytes_in wire-byte injection after an UNKNOWN sender claim,
    # no double-run of status_reconcile). This is a flow test of the real
    # stage-loop helper, not `_route_unknown` isolation.
    if not callable(getattr(mod, "_run_stage_order", None)):
        raise SystemExit("_run_stage_order missing (M1 main-loop flow stub)")

    def _fake_named(unknown_name: str):
        calls: list[str] = []

        def _make(name: str):
            def _call(bindings, deadline):
                calls.append(name)
                if name == unknown_name:
                    raise mod.JourneyUnknown(f"simulated ACK loss at {name}")
                return {"status": "OK"}

            return _call

        return calls, {n: _make(n) for n in mod.STAGE_ORDER}

    # sender UNKNOWN -> status_reconcile once, then STOP (no receipt_bytes_in).
    calls, fns = _fake_named("sender")
    stages = {n: "UNPROVEN" for n in mod.STAGE_ORDER}
    failing_cell: list = [None]
    budget_end = mod._monotonic_end(30.0)
    mod._run_stage_order(fns, stages, budget_end, failing_cell)
    expected_after_sender = [
        "provision_capture_admission",
        "observe_audience",
        "host_control",
        "current_turn",
        "sender",
        "status_reconcile",
    ]
    if calls != expected_after_sender:
        raise SystemExit(
            f"M1 main-loop flow wrong after sender UNKNOWN: {calls!r} "
            f"expected {expected_after_sender!r}"
        )
    if "receipt_bytes_in" in calls:
        raise SystemExit(
            "M1 receipt_bytes_in ran after sender UNKNOWN (wire-byte injection)"
        )
    if calls.count("status_reconcile") != 1:
        raise SystemExit("M1 status_reconcile double-ran after sender UNKNOWN")
    if stages["sender"] != "UNKNOWN->status_reconcile":
        raise SystemExit(f"M1 stages map wrong for sender: {stages['sender']!r}")
    if stages["receipt_bytes_in"] != "UNPROVEN":
        raise SystemExit("M1 receipt_bytes_in marked after sender UNKNOWN")
    print("M1_MAIN_LOOP_FLOW_SENDER_STOPS_AFTER_ROUTE")
    # receipt_bytes_in UNKNOWN -> status_reconcile once (no double-run).
    calls, fns = _fake_named("receipt_bytes_in")
    stages = {n: "UNPROVEN" for n in mod.STAGE_ORDER}
    failing_cell = [None]
    budget_end = mod._monotonic_end(30.0)
    mod._run_stage_order(fns, stages, budget_end, failing_cell)
    if calls.count("status_reconcile") != 1:
        raise SystemExit(
            f"M1 status_reconcile double-ran after receipt_bytes_in UNKNOWN: {calls!r}"
        )
    if calls[-1] != "status_reconcile":
        raise SystemExit(
            f"M1 sequence did not end at stage 5 after receipt_bytes_in UNKNOWN: {calls!r}"
        )
    if stages["receipt_bytes_in"] != "UNKNOWN->status_reconcile":
        raise SystemExit(
            f"M1 stages map wrong for receipt_bytes_in: {stages['receipt_bytes_in']!r}"
        )
    print("M1_MAIN_LOOP_FLOW_RECEIPT_STOPS_AFTER_ROUTE")
    # Earlier-stage UNKNOWN must end at that stage (no onward route).
    calls, fns = _fake_named("current_turn")
    stages = {n: "UNPROVEN" for n in mod.STAGE_ORDER}
    failing_cell = [None]
    budget_end = mod._monotonic_end(30.0)
    try:
        mod._run_stage_order(fns, stages, budget_end, failing_cell)
    except mod.JourneyRefusal as e:
        if "UNKNOWN" not in str(e) and "no onward" not in str(e):
            raise SystemExit(f"M1 earlier-UNKNOWN refusal message wrong: {e}")
    else:
        raise SystemExit("M1 earlier-stage UNKNOWN did not end the journey")
    if "sender" in calls or "receipt_bytes_in" in calls or "status_reconcile" in calls:
        raise SystemExit(
            f"M1 earlier-UNKNOWN continued the loop after STOP: {calls!r}"
        )
    print("M1_MAIN_LOOP_FLOW_EARLIER_UNKNOWN_STOPS")
    print("M1_JOURNEY_UNKNOWN_ROUTING")

    # M3/L5: Python floor must be enforced — behaviorally, not just a static
    # "sys.version_info" string scan. require_python_floor is extracted so a
    # fake old version_info drives the real comparison.
    if not callable(getattr(mod, "require_python_floor", None)):
        raise SystemExit("require_python_floor missing (M3/L5)")
    import collections as _collections
    from unittest import mock as _mock_ver

    _Ver = _collections.namedtuple("_Ver", "major minor micro")
    with _mock_ver.patch.object(sys, "version_info", _Ver(3, 10, 0)):
        try:
            mod.require_python_floor()
        except mod.JourneyRefusal as e:
            if "3.11" not in str(e) and "Python" not in str(e):
                raise SystemExit(f"M3 floor refusal does not name the floor: {e}")
            print("M3_PYTHON_FLOOR_BEHAVIORAL", str(e)[:80])
        else:
            raise SystemExit("require_python_floor accepted Python 3.10 (M3)")
    with _mock_ver.patch.object(sys, "version_info", _Ver(3, 11, 0)):
        mod.require_python_floor()  # must not raise
    with _mock_ver.patch.object(sys, "version_info", _Ver(3, 14, 0)):
        mod.require_python_floor()  # must not raise
    print("M3_PYTHON_FLOOR_ENFORCED")
    # L5: RECALL-first-order — require_recall_env_absent must be the first
    # substantive call in main() (before identity, head, inventory, gate, DB).
    i_recall = main_src.find("require_recall_env_absent(")
    if i_recall < 0:
        raise SystemExit("require_recall_env_absent not called in main (L5)")
    i_python_floor = main_src.find("require_python_floor(")
    if i_python_floor < 0:
        raise SystemExit("require_python_floor not called in main (L5)")
    for later_name, needle in (
        ("_tool_identity", "_tool_identity("),
        ("require_head", "require_head("),
        ("assert_sealed_inventory", "assert_sealed_inventory("),
        ("require_database_gate", "require_database_gate("),
        ("worker_postgres", "worker_postgres("),
    ):
        later_pos = main_src.find(needle)
        if later_pos >= 0 and i_recall > later_pos:
            raise SystemExit(
                f"require_recall_env_absent must run before {later_name} (L5 order)"
            )
    # The Python floor must also precede other work (M3 is a pre-flight).
    for later_name, needle in (
        ("_scratch", "scratch = _scratch("),
        ("_tool_identity", "_tool_identity("),
    ):
        later_pos = main_src.find(needle)
        if later_pos >= 0 and i_python_floor > later_pos:
            raise SystemExit(
                f"require_python_floor must run before {later_name} (L5 order)"
            )
    print("RECALL_ENV_FIRST_ORDER_OK")

    # M8/L8: docker compose plugin must be preflighted via the argv literal
    # ["compose", "version"] — not comment substrings. Deleting the try/except
    # while leaving the comment must fail this check.
    if '"compose", "version"' not in src and "'compose', 'version'" not in src:
        raise SystemExit("compose version argv literal missing (M8/L8)")
    if "docker compose plugin unavailable" not in src:
        raise SystemExit("compose preflight refusal message missing (M8)")
    print("M8_COMPOSE_PREFLIGHT_PRESENT")

    # M7: openssl and pytest identities must be checked.
    if "openssl" not in main_src:
        raise SystemExit("openssl identity not checked (M7)")
    if "pytest" not in main_src or "_pytest_version" not in main_src:
        raise SystemExit("pytest identity not checked (M7)")
    print("M7_TOOL_IDENTITIES_EXTENDED")

    # M6: bare assert must not be used for safety checks in main — any indent
    # level, any nesting depth, both `assert x` and `assert(x)` forms (L11).
    # Covers main() only; stages and helpers are covered by the offline
    # behavioral tests above.
    if re.search(r"(?m)^\s+assert[\s(]", main_src):
        raise SystemExit("bare assert found in main() (M6/L11)")
    print("NO_BARE_ASSERT_IN_MAIN")

    # L15: cleanup paths must preserve the original exception via add_note —
    # never a bare pass that would drop the cleanup refusal. Three add_note
    # call sites: cleanup-also-failed, cleanup-refusal, cleanup-probe-failed.
    finally_src = main_src.split("finally:", 1)[-1]
    if finally_src.count(".add_note(") < 3:
        raise SystemExit(
            f"cleanup add_note calls missing (L15): found {finally_src.count('.add_note(')}"
        )
    for m in re.finditer(r"except [^\n]+:\n(\s+)pass\b", finally_src):
        raise SystemExit(f"bare pass in cleanup except (L15): {m.group(0)!r}")
    print("L15_ADD_NOTE_IN_CLEANUP")

    # H1: citation must note runner is STRICTER (entry+exit vs entry-only).
    if "STRICTER" not in src and "entry-check-only" not in src:
        raise SystemExit("H1 citation does not note runner is stricter than request_deadline_v1")
    print("H1_CITATION_CORRECTED")

    # Dead JourneyComplete removed.
    if "JourneyComplete" in src:
        raise SystemExit("JourneyComplete still present (dead code)")
    print("JOURNEY_COMPLETE_REMOVED")

    print("OFFLINE_SKELETON_CHECKS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
