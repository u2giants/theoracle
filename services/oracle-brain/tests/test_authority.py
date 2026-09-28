from uuid import uuid4

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
