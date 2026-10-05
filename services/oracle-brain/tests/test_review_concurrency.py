"""S03 review concurrency: concurrent confirms and revocation racing confirmation."""

from __future__ import annotations

import threading
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


def _draft_for(admin_url, workspace, reviewer, filename, process_name):
    source_id, _ = upload_source(
        admin_url, workspace_id=workspace, actor_id=reviewer,
        filename=filename, content_type="text/plain",
        text="Step one leads to step two. A handoff occurs here.",
    )
    return create_draft(
        admin_url, source_id=source_id, workspace_id=workspace,
        actor_id=reviewer, process_name=process_name, connections=[],
    )


def test_second_confirm_on_same_draft_fails(admin_url, monkeypatch):
    workspace, owner = _bootstrap(admin_url, monkeypatch)
    reviewer = uuid4()
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=reviewer, scope="confirm")

    draft_id = _draft_for(admin_url, workspace, reviewer, "a.txt", "P")
    confirm_draft(admin_url, draft_id=draft_id, workspace_id=workspace,
                  actor_id=reviewer, scope="process-map")
    with pytest.raises((ValueError, psycopg.errors.UniqueViolation)):
        confirm_draft(admin_url, draft_id=draft_id, workspace_id=workspace,
                      actor_id=reviewer, scope="process-map")


def test_revoked_authority_cannot_confirm(admin_url, monkeypatch):
    """Deterministic revoke-then-confirm: confirmation must fail and leave no state."""
    workspace, owner = _bootstrap(admin_url, monkeypatch)
    reviewer = uuid4()
    review_grant = delegate(admin_url, workspace_id=workspace, grantor_id=owner,
                            actor_id=reviewer, scope="confirm")
    draft_id = _draft_for(admin_url, workspace, reviewer, "b.txt", "P2")

    revoke_errors: list[str] = []

    def do_revoke() -> None:
        try:
            revoke_review_authority(
                admin_url, appointment_id=review_grant,
                workspace_id=workspace, revoked_by=owner,
            )
        except Exception as exc:  # noqa: BLE001
            revoke_errors.append(repr(exc))

    do_revoke()
    assert revoke_errors == [], revoke_errors

    with pytest.raises(PermissionError, match="confirm authority"):
        confirm_draft(admin_url, draft_id=draft_id, workspace_id=workspace,
                      actor_id=reviewer, scope="process-map")

    with psycopg.connect(admin_url) as connection:
        status = connection.execute(
            "SELECT status FROM oracle2.drafts WHERE draft_id=%s",
            (draft_id,),
        ).fetchone()[0]
        confirms = connection.execute(
            "SELECT count(*) FROM oracle2.reviews WHERE draft_id=%s AND action='confirm'",
            (draft_id,),
        ).fetchone()[0]
    assert status == "draft", status
    assert confirms == 0, confirms


def test_revocation_racing_confirmation_is_safe(admin_url, monkeypatch):
    """Concurrent revoke vs confirm: whichever wins, the loser fails cleanly."""
    workspace, owner = _bootstrap(admin_url, monkeypatch)
    reviewer = uuid4()
    review_grant = delegate(admin_url, workspace_id=workspace, grantor_id=owner,
                            actor_id=reviewer, scope="confirm")
    draft_id = _draft_for(admin_url, workspace, reviewer, "b2.txt", "P3")

    revoke_errors: list[str] = []
    confirm_result: list[str] = []

    def do_revoke() -> None:
        try:
            revoke_review_authority(
                admin_url, appointment_id=review_grant,
                workspace_id=workspace, revoked_by=owner,
            )
        except Exception as exc:  # noqa: BLE001
            revoke_errors.append(repr(exc))

    def do_confirm() -> None:
        try:
            confirm_draft(admin_url, draft_id=draft_id, workspace_id=workspace,
                          actor_id=reviewer, scope="process-map")
            confirm_result.append("ok")
        except PermissionError as exc:
            confirm_result.append(f"denied:{exc}")
        except Exception as exc:  # noqa: BLE001
            confirm_result.append(type(exc).__name__)

    t1 = threading.Thread(target=do_revoke)
    t2 = threading.Thread(target=do_confirm)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert revoke_errors == [], revoke_errors
    assert len(confirm_result) == 1, confirm_result
    # Either confirm won before revoke, or it was denied by authority after.
    assert confirm_result[0] == "ok" or confirm_result[0].startswith("denied:"), confirm_result
    if confirm_result[0] != "ok":
        with psycopg.connect(admin_url) as connection:
            status = connection.execute(
                "SELECT status FROM oracle2.drafts WHERE draft_id=%s",
                (draft_id,),
            ).fetchone()[0]
        assert status == "draft", status


def test_concurrent_confirmation_collision(admin_url, monkeypatch):
    """Two concurrent confirms: exactly one succeeds."""
    workspace, owner = _bootstrap(admin_url, monkeypatch)
    reviewer = uuid4()
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=reviewer, scope="confirm")
    draft_id = _draft_for(admin_url, workspace, reviewer, "c.txt", "P")
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

