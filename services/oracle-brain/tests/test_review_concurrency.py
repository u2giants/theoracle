"""S03 review concurrency: concurrent confirms and revocation racing confirmation."""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest

from oracle_brain.authz import delegate
from oracle_brain.knowledge.authority import confirm_draft, revoke_review_authority
from oracle_brain.workflows.pilot import create_draft, upload_source


def _bootstrap(admin_url, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from oracle_brain.authz import appoint_owner

    workspace, owner = uuid4(), uuid4()
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
    return workspace, owner


def test_second_confirm_on_same_draft_fails(admin_url, monkeypatch):
    workspace, owner = _bootstrap(admin_url, monkeypatch)
    reviewer = uuid4()
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=reviewer, scope="confirm")

    source_id, _ = upload_source(
        admin_url, workspace_id=workspace, actor_id=reviewer,
        filename="a.txt", content_type="text/plain", text="Step one leads to step two.",
    )
    draft_id = create_draft(
        admin_url, source_id=source_id, workspace_id=workspace,
        actor_id=reviewer, process_name="P", connections=[],
    )
    confirm_draft(admin_url, draft_id=draft_id, workspace_id=workspace,
                  actor_id=reviewer, scope="process-map")
    with pytest.raises((ValueError, psycopg.errors.UniqueViolation)):
        confirm_draft(admin_url, draft_id=draft_id, workspace_id=workspace,
                      actor_id=reviewer, scope="process-map")


def test_revocation_racing_confirmation(admin_url, monkeypatch):
    """If authority is revoked before confirmation, confirmation must fail."""
    workspace, owner = _bootstrap(admin_url, monkeypatch)
    reviewer = uuid4()
    review_grant = delegate(admin_url, workspace_id=workspace, grantor_id=owner,
                            actor_id=reviewer, scope="confirm")

    source_id, _ = upload_source(
        admin_url, workspace_id=workspace, actor_id=reviewer,
        filename="b.txt", content_type="text/plain", text="A handoff occurs here.",
    )
    draft_id = create_draft(
        admin_url, source_id=source_id, workspace_id=workspace,
        actor_id=reviewer, process_name="P2", connections=[],
    )
    revoke_review_authority(admin_url, appointment_id=review_grant,
                            workspace_id=workspace, revoked_by=owner)
    with pytest.raises(PermissionError):
        confirm_draft(admin_url, draft_id=draft_id, workspace_id=workspace,
                      actor_id=reviewer, scope="process-map")


def test_concurrent_confirmation_collision(admin_url, monkeypatch):
    """Two concurrent confirms: exactly one succeeds."""
    import threading

    workspace, owner = _bootstrap(admin_url, monkeypatch)
    reviewer = uuid4()
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=reviewer, scope="confirm")
    source_id, _ = upload_source(
        admin_url, workspace_id=workspace, actor_id=reviewer,
        filename="c.txt", content_type="text/plain", text="Step one leads to step two.",
    )
    draft_id = create_draft(
        admin_url, source_id=source_id, workspace_id=workspace,
        actor_id=reviewer, process_name="P", connections=[],
    )
    results: list[str] = []

    def attempt() -> None:
        try:
            confirm_draft(admin_url, draft_id=draft_id, workspace_id=workspace,
                          actor_id=reviewer, scope="process-map")
            results.append("ok")
        except Exception as exc:  # noqa: BLE001
            results.append(type(exc).__name__)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 1, results
    assert len(results) == 2
