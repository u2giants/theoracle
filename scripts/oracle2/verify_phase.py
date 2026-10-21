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
S03_TESTS = [
    "test_replacement_request_service_v1.py",
    "test_owned_worker_database.py", "test_replacement_upload_service_v1.py",
    "test_replacement_upload_sql.py",
    "test_provider_policy.py", "test_pilot_journey.py", "test_authority.py",
    "test_review_concurrency.py", "test_holistic_graphrag.py",
    "test_holistic_graphrag_integration.py",
    "test_holistic_runtime.py", "test_original_reading.py", "test_original_corpus_import.py", "test_original_corpus_read.py",
    "test_provider_transport.py",
    "test_original_pdf_image_views.py",
    "test_graph_evidence_answer.py",
    "test_replacement_original_lifecycle.py", "test_original_qualification_runtime.py",
    "test_replacement_qualification_sql.py", "test_q2b_target_catalog_v1.py",
    "test_q2b_transaction_freshness_sql.py",
    "test_seal_security.py", "test_seal_wire.py",
    "test_replacement_journey_control.py", "test_replacement_job_authority.py",
    "test_replacement_requester_v1.py", "test_replacement_requester_sql.py",
]
# S04 — complete source ingestion, revisions and withdrawal
# (plan_oracle_consultant_overhaul.md §S04 gate list).
S04_TESTS = [
    "test_binary_documents.py",
    "test_original_byte_storage.py",
    "test_document_provenance.py",
    "test_file_limits.py",
    "test_source_lifecycle.py",
]
# S05 — confirmed temporal operating model and corrections.
S05_TESTS = [
    "test_identity_resolution.py",
    "test_temporal_facts.py",
    "test_admission.py",
    "test_graphiti_isolation.py",
    "test_review_concurrency.py",
    "test_summary_invalidation.py",
]
# S06 — interviews and ordinary chat learning.
S06_TESTS = [
    "test_interview_resume.py",
    "test_question_selection.py",
    "test_chat_learning.py",
    "test_multilingual.py",
    "test_chat_proposal_contract.py",
]
# S07 — learn from explicitly invited meetings.
S07_TESTS = [
    "test_meeting_ingress.py",
    "test_meeting_dedup.py",
    "test_speaker_scope.py",
]
# S08 — bounded in-meeting participation.
S08_TESTS = [
    "test_meeting_participation.py",
    "test_outbound_replay.py",
]
# S09 — connected, historical and company-wide answers.
S09_TESTS = [
    "test_retrieval_modes.py",
    "test_query_bounds.py",
    "test_citation_entailment_contract.py",
    "test_global_scope.py",
    "test_mcp_parity.py",
]
# S10 — maintained industry expertise.
S10_TESTS = [
    "test_research_fetch.py",
    "test_research_rights.py",
    "test_applicability.py",
    "test_research_freshness.py",
    "test_research_scheduler.py",
]
# S11 — consulting recommendations and feedback.
S11_TESTS = [
    "test_recommendation_contract.py",
    "test_scenario_math.py",
    "test_operational_export.py",
    "test_experiment_outcomes.py",
]
# S12 — the plan gate names Playwright specs (workspace/accessibility/exports)
# and `verify_phase.py S12 --mode offline`. The Python side is the offline
# completeness gate; Playwright pages are still unbuilt and their specs skip
# with the named blocker (see apps/web/tests/oracle2/workspace.spec.ts).
S12_TESTS = [
    "test_s12_completeness_gate.py",
]
# S13 — operational recovery reruns S04 source-lifecycle (restored-backup
# tombstone enforcement) plus recovery primitives and ops offline checks.
# The isolated staging exercise stays in S13-recovery.md (not a Python test).
S13_TESTS = [
    "test_source_lifecycle.py",
    "test_recovery_primitives.py",
    "test_operations_recovery.py",
    "test_operations_offline.py",
]
# S14 — migrate and compare historical knowledge (pattern from
# origin/claude/s14-historical-migration; pure fixture contracts).
S14_TESTS = [
    "test_legacy_mapping.py",
    "test_migration_resume.py",
    "test_migration_delta.py",
    "test_migration_reconcile.py",
]
# S16 — retire the superseded system (pattern from s16-retire-offline;
# pure fixture tests: no store, provider or live target).
S16_TESTS = [
    "test_legacy_routes_retired.py",
    "test_legacy_citation_redirect.py",
    "test_retired_writer_denial.py",
]
# S15 (controlled production adoption) is NOT offline-registrable: its gate is
# `verify_phase.py S15 --mode live --manifest PRIVATE_PATH` under an exact
# approved release. Offline mode cannot use a private manifest, and this file
# never sets live_accepted=true. S15 stays out of PHASE_TESTS on purpose.

PHASE_TESTS = {
    "S02": S02_TESTS,
    "S03": S03_TESTS,
    "S04": S04_TESTS,
    "S05": S05_TESTS,
    "S06": S06_TESTS,
    "S07": S07_TESTS,
    "S08": S08_TESTS,
    "S09": S09_TESTS,
    "S10": S10_TESTS,
    "S11": S11_TESTS,
    "S12": S12_TESTS,
    "S13": S13_TESTS,
    "S14": S14_TESTS,
    "S16": S16_TESTS,
}
# Pure-fixture phases need no isolated Postgres/FalkorDB target.
FIXTURE_ONLY_PHASES = {"S12", "S14", "S16"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=sorted(PHASE_TESTS))
    parser.add_argument("--mode", choices=["offline", "live"], required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--result", type=Path,
                        default=None)
    args = parser.parse_args()
    if args.result is None:
        args.result = ROOT / "out" / "oracle2" / f"{args.phase}-result.json"
    if args.mode != "offline":
        parser.error(f"{args.phase} live gate requires a separately reviewed preview target")
    if args.manifest:
        parser.error("offline gate cannot use a private manifest")
    test_list = PHASE_TESTS[args.phase]
    if not test_list:
        parser.error(
            f"{args.phase} has no offline Python tests named in the phase gate; "
            "register them before running this stage"
        )
    missing = [name for name in test_list if not (SERVICE / "tests" / name).is_file()]
    if missing:
        parser.error(f"missing required tests: {', '.join(missing)}")
    if args.phase not in FIXTURE_ONLY_PHASES:
        if not os.getenv("ORACLE2_TEST_ADMIN_URL") or not os.getenv("ORACLE2_TEST_CONFIRMED_URL"):
            parser.error("real isolated Postgres and FalkorDB test URLs required")
    if args.phase == "S03" and not os.getenv("ORACLE2_TEST_FALKORDB_URL"):
        parser.error("S03 requires actual GraphRAG SDK FalkorDB integration target")
    python = SERVICE / ".venv" / "bin" / "python"
    if not python.exists():
        python = SERVICE / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        parser.error("frozen Python environment missing; run uv sync --frozen --extra test")
    tests = [str(SERVICE / "tests" / name) for name in test_list]
    completed = subprocess.run([str(python), "-m", "pytest", "-q", *tests], cwd=ROOT,
                               capture_output=True, text=True, check=False)
    # No test output enters a public artifact; raw logs remain in local CI job.
    lock_hash = hashlib.sha256((SERVICE / "uv.lock").read_bytes()).hexdigest()
    result = {
        "phase": args.phase, "mode": args.mode,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "lock_sha256": lock_hash,
        "required_test_files": test_list,
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
