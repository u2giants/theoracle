"""S03 pilot journey: upload, draft, correct, confirm, question, answer."""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest

from oracle_brain.authz import delegate
from oracle_brain.contracts import *  # noqa: F401,F403 - parity with contract tests
from oracle_brain.knowledge.authority import confirm_draft, correct_draft
from oracle_brain.workflows.pilot import (
    create_draft,
    run_question,
    upload_source,
)

SYNTHETIC_PROCESS_DOC = (
    "Step 1: Designer submits the product concept to the licensing team.\n\n"
    "Step 2: Licensing reviews the concept against brand guidelines within 5 business days.\n\n"
    "Step 3: If approved, licensing hands off to production planning.\n\n"
    "Step 4: Production planning schedules the manufacturing run.\n\n"
    "Exception: If the concept uses a new material, licensing must also obtain "
    "an environmental compliance sign-off before the handoff to production."
)


def _appoint_root(admin_url, workspace, owner, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from oracle_brain.authz import appoint_owner

    owner_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("ORACLE2_OWNER_PUBLIC_KEY", owner_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex())
    appointment = uuid4()
    message = f"oracle2-owner-appointment-v1:{workspace}:{owner}:{appointment}".encode()
    appoint_owner(admin_url, workspace_id=workspace, owner_id=owner,
                  appointed_by=uuid4(), appointment_id=appointment,
                  owner_signature_hex=owner_key.sign(message).hex())
    return owner


def test_pilot_journey_upload_draft_correct_confirm_answer(admin_url, monkeypatch):
    workspace = uuid4()
    owner = uuid4()
    pilot_user = uuid4()
    _appoint_root(admin_url, workspace, owner, monkeypatch)
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=pilot_user, scope="intake")
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=pilot_user, scope="review")
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=pilot_user, scope="confirm")

    source_id, blocks = upload_source(
        admin_url, workspace_id=workspace, actor_id=pilot_user,
        filename="process.txt", content_type="text/plain",
        text=SYNTHETIC_PROCESS_DOC,
    )
    assert source_id is not None
    assert len(blocks) >= 4

    draft_id = create_draft(
        admin_url, source_id=source_id, workspace_id=workspace,
        actor_id=pilot_user, process_name="Product approval flow",
        connections=[{"from": 0, "to": 1}, {"from": 1, "to": 2}],
    )
    assert draft_id is not None

    correct_draft(
        admin_url, draft_id=draft_id, workspace_id=workspace,
        actor_id=pilot_user,
        connections=[{"from": 0, "to": 1}, {"from": 1, "to": 3}],
    )
    confirm_draft(admin_url, draft_id=draft_id, workspace_id=workspace,
                  actor_id=pilot_user, scope="process-map")

    result = run_question(
        admin_url, workspace_id=workspace, actor_id=pilot_user,
        source_id=source_id, draft_id=draft_id,
        question="Where can the handoff between licensing and production fail?",
    )
    assert result.answer.citations, "answer must include citations"
    assert result.answer.answer_text, "answer must not be empty"
    assert result.answer.hypothetical is not None
    assert "hypothetical" in result.answer.hypothetical.label.lower()
    assert result.answer.hypothetical.missing_inputs


def test_pilot_journey_answer_without_evidence_says_so(admin_url, monkeypatch):
    workspace = uuid4()
    owner = uuid4()
    pilot_user = uuid4()
    _appoint_root(admin_url, workspace, owner, monkeypatch)
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=pilot_user, scope="intake")
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=pilot_user, scope="review")
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=pilot_user, scope="confirm")

    source_id, _ = upload_source(
        admin_url, workspace_id=workspace, actor_id=pilot_user,
        filename="empty-topic.txt", content_type="text/plain",
        text="The weather is pleasant today.",
    )
    draft_id = create_draft(
        admin_url, source_id=source_id, workspace_id=workspace,
        actor_id=pilot_user, process_name="Weather",
        connections=[],
    )
    confirm_draft(admin_url, draft_id=draft_id, workspace_id=workspace,
                  actor_id=pilot_user, scope="process-map")
    result = run_question(
        admin_url, workspace_id=workspace, actor_id=pilot_user,
        source_id=source_id, draft_id=draft_id,
        question="What is the licensing approval threshold for new materials?",
    )
    assert not result.answer.citations
    assert "no source evidence" in result.answer.answer_text.lower()
