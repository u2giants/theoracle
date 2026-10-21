from uuid import uuid4

import psycopg
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from oracle_brain.authz import appoint_owner, delegate, has_authority


def test_admin_cannot_self_grant_root_without_owner_appointment(admin_url, monkeypatch):
    workspace, admin, owner = uuid4(), uuid4(), uuid4()
    owner_key = Ed25519PrivateKey.generate()
    public_key = owner_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    monkeypatch.setenv("ORACLE2_OWNER_PUBLIC_KEY", public_key)
    appointment = uuid4()
    with pytest.raises(PermissionError):
        appoint_owner(admin_url, workspace_id=workspace, owner_id=admin,
                      appointed_by=admin, appointment_id=appointment,
                      owner_signature_hex="00" * 64)
    with pytest.raises(PermissionError):
        delegate(admin_url, workspace_id=workspace, grantor_id=admin,
                 actor_id=admin, scope="root")
    assert not has_authority(admin_url, workspace_id=workspace, actor_id=admin,
                             scope="root")
    message = f"oracle2-owner-appointment-v1:{workspace}:{owner}:{appointment}".encode()
    appoint_owner(admin_url, workspace_id=workspace, owner_id=owner,
                  appointed_by=admin, appointment_id=appointment,
                  owner_signature_hex=owner_key.sign(message).hex())
    assert has_authority(admin_url, workspace_id=workspace, actor_id=owner,
                         scope="root")
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=admin, scope="review")
    assert has_authority(admin_url, workspace_id=workspace, actor_id=admin,
                         scope="review")
    assert not has_authority(admin_url, workspace_id=workspace, actor_id=admin,
                             scope="root")


def test_delegation_chooses_a_valid_complete_lineage(admin_url, monkeypatch):
    workspace, owner, grantor, recipient, recording_admin = (
        uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    )
    owner_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("ORACLE2_OWNER_PUBLIC_KEY", owner_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex())

    def appoint():
        appointment = uuid4()
        message = f"oracle2-owner-appointment-v1:{workspace}:{owner}:{appointment}".encode()
        appoint_owner(admin_url, workspace_id=workspace, owner_id=owner,
                      appointed_by=recording_admin, appointment_id=appointment,
                      owner_signature_hex=owner_key.sign(message).hex())
        return appointment

    stale_root = appoint()
    stale_review = delegate(admin_url, workspace_id=workspace, grantor_id=owner,
                            actor_id=grantor, scope="review")
    with psycopg.connect(admin_url) as connection:
        connection.execute("UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s",
                           (stale_root,))
    fresh_root = appoint()
    fresh_review = delegate(admin_url, workspace_id=workspace, grantor_id=owner,
                            actor_id=grantor, scope="review")
    assert fresh_root != stale_root and fresh_review != stale_review
    assert has_authority(admin_url, workspace_id=workspace, actor_id=grantor,
                         scope="review")
    delegated = delegate(admin_url, workspace_id=workspace, grantor_id=grantor,
                         actor_id=recipient, scope="review")
    with psycopg.connect(admin_url) as connection:
        parent = connection.execute(
            "SELECT parent_id FROM oracle2.appointments WHERE appointment_id=%s",
            (delegated,),
        ).fetchone()[0]
    assert parent == fresh_review
    assert has_authority(admin_url, workspace_id=workspace, actor_id=recipient,
                         scope="review")


def test_forged_actor_cannot_obtain_authority(admin_url, monkeypatch):
    workspace, owner, forger = uuid4(), uuid4(), uuid4()
    owner_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("ORACLE2_OWNER_PUBLIC_KEY", owner_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex())
    appointment = uuid4()
    message = f"oracle2-owner-appointment-v1:{workspace}:{owner}:{appointment}".encode()
    # Forger signs with wrong key
    wrong_key = Ed25519PrivateKey.generate()
    with pytest.raises(PermissionError):
        appoint_owner(admin_url, workspace_id=workspace, owner_id=forger,
                      appointed_by=uuid4(), appointment_id=appointment,
                      owner_signature_hex=wrong_key.sign(message).hex())
    assert not has_authority(admin_url, workspace_id=workspace, actor_id=forger,
                             scope="root")
    assert not has_authority(admin_url, workspace_id=workspace, actor_id=forger,
                             scope="review")


def test_out_of_scope_grant_is_denied(admin_url, monkeypatch):
    workspace, owner, grantee = uuid4(), uuid4(), uuid4()
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
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=grantee, scope="review")
    # Grantee has review but not confirm/intake/root
    assert has_authority(admin_url, workspace_id=workspace, actor_id=grantee,
                         scope="review")
    assert not has_authority(admin_url, workspace_id=workspace, actor_id=grantee,
                             scope="confirm")
    assert not has_authority(admin_url, workspace_id=workspace, actor_id=grantee,
                             scope="intake")
    assert not has_authority(admin_url, workspace_id=workspace, actor_id=grantee,
                             scope="root")


def test_expired_delegate_loses_authority(admin_url, monkeypatch):
    from datetime import datetime, timedelta, timezone

    workspace, owner, delegatee = uuid4(), uuid4(), uuid4()
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
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=delegatee, scope="review", expires_at=past)
    assert not has_authority(admin_url, workspace_id=workspace, actor_id=delegatee,
                             scope="review")
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    delegate(admin_url, workspace_id=workspace, grantor_id=owner,
             actor_id=delegatee, scope="review", expires_at=future)
    assert has_authority(admin_url, workspace_id=workspace, actor_id=delegatee,
                         scope="review")


def test_revoked_parent_invalidates_child(admin_url, monkeypatch):
    workspace, owner, mid, leaf = uuid4(), uuid4(), uuid4(), uuid4()
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
    mid_grant = delegate(admin_url, workspace_id=workspace, grantor_id=owner,
                         actor_id=mid, scope="review")
    delegate(admin_url, workspace_id=workspace, grantor_id=mid,
             actor_id=leaf, scope="review")
    assert has_authority(admin_url, workspace_id=workspace, actor_id=leaf,
                         scope="review")
    with psycopg.connect(admin_url) as connection:
        connection.execute(
            "UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s",
            (mid_grant,),
        )
    assert not has_authority(admin_url, workspace_id=workspace, actor_id=leaf,
                             scope="review")


def test_forged_issuer_link_chain_is_denied(admin_url, monkeypatch):
    """A child whose granted_by does not match its claimed parent's actor_id
    must be rejected — mirrors the TS contract denied-case for forged chains."""
    workspace, owner, attacker = uuid4(), uuid4(), uuid4()
    owner_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("ORACLE2_OWNER_PUBLIC_KEY", owner_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex())
    root = uuid4()
    message = f"oracle2-owner-appointment-v1:{workspace}:{owner}:{root}".encode()
    appoint_owner(admin_url, workspace_id=workspace, owner_id=owner,
                  appointed_by=uuid4(), appointment_id=root,
                  owner_signature_hex=owner_key.sign(message).hex())
    # Forged grant: attacker points parent_id at the owner's root but
    # granted_by is NOT the root's actor.
    forged = uuid4()
    with psycopg.connect(admin_url) as connection:
        connection.execute(
            """INSERT INTO oracle2.appointments
               (appointment_id,workspace_id,actor_id,scope,granted_by,parent_id)
               VALUES (%s,%s,%s,'confirm',%s,%s)""",
            (forged, workspace, attacker, uuid4(), root),
        )
    assert not has_authority(admin_url, workspace_id=workspace, actor_id=attacker,
                             scope="confirm")


def test_unrelated_root_chain_is_denied(admin_url, monkeypatch):
    """A chain through a root whose actor is unrelated to the child's issuer
    must be denied — mirrors the TS contract unrelated-root case."""
    workspace, owner, outsider, attacker = uuid4(), uuid4(), uuid4(), uuid4()
    owner_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("ORACLE2_OWNER_PUBLIC_KEY", owner_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex())
    root = uuid4()
    message = f"oracle2-owner-appointment-v1:{workspace}:{owner}:{root}".encode()
    appoint_owner(admin_url, workspace_id=workspace, owner_id=owner,
                  appointed_by=uuid4(), appointment_id=root,
                  owner_signature_hex=owner_key.sign(message).hex())
    # Unrelated root belonging to a different actor.
    outsider_root = uuid4()
    with psycopg.connect(admin_url) as connection:
        connection.execute(
            """INSERT INTO oracle2.appointments
               (appointment_id,workspace_id,actor_id,scope,granted_by)
               VALUES (%s,%s,%s,'root',%s)""",
            (outsider_root, workspace, outsider, uuid4()),
        )
        # Forged grant pointing at the unrelated root with a broken issuer link.
        connection.execute(
            """INSERT INTO oracle2.appointments
               (appointment_id,workspace_id,actor_id,scope,granted_by,parent_id)
               VALUES (%s,%s,%s,'confirm',%s,%s)""",
            (uuid4(), workspace, attacker, uuid4(), outsider_root),
        )
    assert not has_authority(admin_url, workspace_id=workspace, actor_id=attacker,
                             scope="confirm")


def test_broken_issuer_link_in_multi_step_chain_is_denied(admin_url, monkeypatch):
    """Breaking the issuer link on any step of a multi-step chain invalidates
    the leaf — mirrors the TS multi-step broken-issuer case."""
    workspace, owner, mid, leaf = uuid4(), uuid4(), uuid4(), uuid4()
    owner_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("ORACLE2_OWNER_PUBLIC_KEY", owner_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex())
    root = uuid4()
    message = f"oracle2-owner-appointment-v1:{workspace}:{owner}:{root}".encode()
    appoint_owner(admin_url, workspace_id=workspace, owner_id=owner,
                  appointed_by=uuid4(), appointment_id=root,
                  owner_signature_hex=owner_key.sign(message).hex())
    mid_grant = delegate(admin_url, workspace_id=workspace, grantor_id=owner,
                         actor_id=mid, scope="review")
    # Leaf claims mid as parent but pretends the owner issued it.
    leaf_grant = uuid4()
    with psycopg.connect(admin_url) as connection:
        connection.execute(
            """INSERT INTO oracle2.appointments
               (appointment_id,workspace_id,actor_id,scope,granted_by,parent_id)
               VALUES (%s,%s,%s,'review',%s,%s)""",
            (leaf_grant, workspace, leaf, owner, mid_grant),
        )
    assert not has_authority(admin_url, workspace_id=workspace, actor_id=leaf,
                             scope="review")


def test_confirm_through_review_parent_is_denied(admin_url, monkeypatch):
    """A child cannot hold a scope its parent did not hold: confirm granted
    under a review-only parent is denied even though the chain reaches root."""
    workspace, owner, mid, leaf = uuid4(), uuid4(), uuid4(), uuid4()
    owner_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("ORACLE2_OWNER_PUBLIC_KEY", owner_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex())
    root = uuid4()
    message = f"oracle2-owner-appointment-v1:{workspace}:{owner}:{root}".encode()
    appoint_owner(admin_url, workspace_id=workspace, owner_id=owner,
                  appointed_by=uuid4(), appointment_id=root,
                  owner_signature_hex=owner_key.sign(message).hex())
    mid_grant = delegate(admin_url, workspace_id=workspace, grantor_id=owner,
                         actor_id=mid, scope="review")
    # Escalation: mid issues a confirm grant to leaf. Parent only holds review.
    leaf_grant = uuid4()
    with psycopg.connect(admin_url) as connection:
        connection.execute(
            """INSERT INTO oracle2.appointments
               (appointment_id,workspace_id,actor_id,scope,granted_by,parent_id)
               VALUES (%s,%s,%s,'confirm',%s,%s)""",
            (leaf_grant, workspace, leaf, mid, mid_grant),
        )
    assert not has_authority(admin_url, workspace_id=workspace, actor_id=leaf,
                             scope="confirm")
    # Same chain shape is valid for review (child scope equals parent scope).
    leaf_review = uuid4()
    with psycopg.connect(admin_url) as connection:
        connection.execute(
            """INSERT INTO oracle2.appointments
               (appointment_id,workspace_id,actor_id,scope,granted_by,parent_id)
               VALUES (%s,%s,%s,'review',%s,%s)""",
            (leaf_review, workspace, leaf, mid, mid_grant),
        )
    assert has_authority(admin_url, workspace_id=workspace, actor_id=leaf,
                         scope="review")
