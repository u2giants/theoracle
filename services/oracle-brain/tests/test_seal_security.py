"""Denied-case tests for the seal security boundary.

Proves: the verify path holds no private key and no sign capability,
no MAC/sign helper is importable or getattr-able from the seal module,
and forged / wrong-key / tampered / truncated seals stay denied.
"""
from __future__ import annotations

import importlib
import inspect

import pytest


def test_no_public_secret_installer():
    """install_seal_secret must not exist on the public surface."""
    seal = importlib.import_module('oracle_brain.seal')
    assert not hasattr(seal, 'install_seal_secret'), (
        'install_seal_secret must not be a module attribute')
    with pytest.raises(ImportError):
        exec('from oracle_brain.seal import install_seal_secret')


def test_no_mac_helper_importable_or_getattr():
    """No mint/MAC/sign helper is importable or reachable by getattr.

    Covers the historical name and every alias a forger might try.
    """
    seal = importlib.import_module('oracle_brain.seal')
    for name in ('_make_mac', 'make_mac', 'seal_mac', 'sign', 'create_mac',
                 'hmac_sign', '_mint_mac', 'mint_mac', 'mint', '_mint',
                 'mac', 'compute_mac', 'hmac_sign', 'sign_mac', 'sign_seal',
                 'sign_payload', 'private_key', '_private_key',
                 'load_private_key', '_load_private_key'):
        assert not hasattr(seal, name), (
            f'MAC/sign helper {name} must not be a module attribute')
        with pytest.raises((ImportError, AttributeError)):
            getattr(seal, name)
        with pytest.raises(ImportError):
            exec(f'from oracle_brain.seal import {name}')


def test_internal_make_mac_not_exported():
    """The internal helper is not in __all__ and not a module attribute."""
    seal = importlib.import_module('oracle_brain.seal')
    exported = getattr(seal, '__all__', None)
    if exported is not None:
        assert '_make_mac' not in exported
        assert 'seal_mac' not in exported
        assert 'sign' not in exported
    assert not hasattr(seal, '_make_mac')


def test_verify_path_has_no_sign_or_private_key():
    """The verify module/namespace has no sign capability and no private key.

    This is the R8 boundary: same-process callers cannot extract a
    signing capability from the verify path. Public-key verify cannot
    forge even when every closure is inspected.
    """
    seal = importlib.import_module('oracle_brain.seal')
    forbidden_names = {
        'sign', 'sign_seal', 'sign_payload', 'mint', 'mint_mac', 'make_mac',
        'private_key', 'private_bytes', 'SEAL_PRIVATE_KEY_ENV',
        'SEAL_PRIVATE_KEY_FILE_ENV',
    }
    for name in forbidden_names:
        assert not hasattr(seal, name), (
            f'verify path must not expose {name}')

    # No public attribute may be a private-key object or a signer callable.
    for name, value in vars(seal).items():
        if name.startswith('__'):
            continue
        assert 'private' not in name.lower(), (
            f'verify path attribute {name} looks like private key material')

    # Source of the verify module must not load a private key or sign.
    source = inspect.getsource(seal)
    assert 'from_private_bytes' not in source
    assert 'Ed25519PrivateKey' not in source
    assert '.sign(' not in source
    assert 'os.environ.get(SEAL_PRIVATE_KEY' not in source
    assert "os.environ.get('ORACLE2_SEAL_PRIVATE_KEY'" not in source
    assert 'os.environ.get(SEAL_PRIVATE_KEY_ENV' not in source


def test_verify_path_does_not_import_seal_signer():
    """The verify module must not import the isolated signing helper."""
    seal = importlib.import_module('oracle_brain.seal')
    assert 'oracle_brain.seal_signer' not in getattr(seal, '__dict__', {})
    source = inspect.getsource(seal)
    assert 'import oracle_brain.seal_signer' not in source
    assert 'from oracle_brain.seal_signer' not in source
    assert 'importlib' not in source or 'seal_signer' not in source


def test_forged_credential_mac_still_denied():
    """A seal under a wrong key never verifies at the credential boundary."""
    from oracle_brain.meetings.delivery import issue_sender_credential_proof
    from datetime import datetime, timezone

    exp = datetime(2030, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(PermissionError, match='seal MAC mismatch'):
        issue_sender_credential_proof(
            principal_id='p-1', role='delivery_sender', expires_at=exp,
            mac='0' * 64)


def test_forged_enable_mac_still_denied():
    """A forged participation enable seal is refused."""
    from oracle_brain.meetings.participation import record_settings

    with pytest.raises(PermissionError, match='seal MAC mismatch'):
        record_settings(
            meeting_id='m-1', enabled=True,
            recorded_at='2026-10-16T12:00:00Z',
            enable_proof_mac='0' * 64)


def test_forged_reader_fact_mac_still_denied():
    """A caller-built receipt with a forged fact_mac never admits."""
    from oracle_brain.operating_model.q2b_target_catalog_v1 import (
        Q2bExecuteGrant, Q2bExpectedPins, Q2bExecuteGrantsFact,
        Q2bProcOwnerFact, Q2bRoleMembershipsFact, Q2bSearchPathFact,
        Q2bSecurityDefinerFact, Q2bTargetCatalogReceipt, Q2bTargetIdentityFact,
        admit_target_catalog,
    )

    sig = 'oracle2.invented_helper_alpha(integer)'
    owner = 'invented_ledger_owner'
    session = 'invented_session_role'
    group = 'invented_reader_group'
    caller_built = Q2bTargetCatalogReceipt(
        pg_proc_owner=Q2bProcOwnerFact(values=((sig, owner),)),
        security_definer=Q2bSecurityDefinerFact(values=((sig, True),)),
        search_path=Q2bSearchPathFact(
            values=((sig, ('pg_catalog', 'public')),)),
        execute_grants=Q2bExecuteGrantsFact(
            values=((sig, (Q2bExecuteGrant(grantee=session, is_grantable=False),)),)),
        role_memberships=Q2bRoleMembershipsFact(
            session_user=session, current_user=session,
            owner_reachable_member=False, owner_reachable_set=False,
            owner_reachable_usage=False, reachable_roles=(session, group)),
        target_identity=Q2bTargetIdentityFact(
            host='invented-target.example.test', port=5432,
            dbname='invented_db', user='invented_user',
            ssl_in_use=True, sslmode='verify-full'),
        fact_mac='0' * 64,
    )
    pins = Q2bExpectedPins(
        function_signatures=(sig,),
        expected_owner_role=owner,
        expected_session_role=session,
        expected_host='invented-target.example.test',
        expected_port=5432,
        expected_dbname='invented_db',
        expected_user='invented_user',
        expected_sslmode='verify-full',
        expected_execute_grants=((sig, (session,)),),
        role_scope=(owner, session, group),
    )
    with pytest.raises(PermissionError):
        admit_target_catalog(caller_built, pins)


def test_verify_rejects_forged_wrong_key_tampered_and_truncated():
    """Denied cases: forged, wrong key, tampered payload, truncated signature."""
    import os

    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    from oracle_brain.seal import seal_payload, verify, verify_mac

    payload = seal_payload('seal-security-denied-cases', 'field-1', 'field-2')
    good = Ed25519PrivateKey.from_private_bytes(
        bytes.fromhex(os.environ['ORACLE2_SEAL_PRIVATE_KEY'])
    ).sign(payload).hex()
    assert verify(payload, good) is True

    # Forged signature (garbage bytes of the right length).
    forged = '0' * 128
    assert verify(payload, forged) is False

    # Wrong key: a real signature under a different keypair.
    wrong_key = Ed25519PrivateKey.generate().sign(payload).hex()
    assert verify(payload, wrong_key) is False

    # Tampered payload.
    assert verify(b'tampered|field-1|field-2', good) is False

    # Truncated signature.
    assert verify(payload, good[:64]) is False
    assert verify(payload, good[:-2]) is False

    with pytest.raises(PermissionError, match='seal MAC mismatch'):
        verify_mac('seal-security-denied-cases', wrong_key, 'field-1', 'field-2')
    with pytest.raises(PermissionError, match='seal MAC mismatch'):
        verify_mac('seal-security-denied-cases', good, 'field-1', 'OTHER')
