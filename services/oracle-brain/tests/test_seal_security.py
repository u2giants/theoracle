"""Denied-case tests for the seal security boundary.

Proves: secret install is one-shot (second install denied), no public
general-purpose MAC maker is importable, and forged proofs stay denied.
"""
from __future__ import annotations

import importlib

import pytest


def test_second_secret_install_denied():
    """Once the seal has loaded a secret, a second install is refused."""
    from oracle_brain.seal import install_seal_secret, verify_mac

    # Trigger first use so the seal loads from env and latches _installed.
    try:
        verify_mac('test-purpose', '0' * 64, 'x')
    except PermissionError:
        pass  # MAC mismatch is expected; loading is what matters.

    with pytest.raises(PermissionError, match='already installed'):
        install_seal_secret(b'x' * 32)


def test_public_make_mac_absent_or_denied():
    """No public make_mac/sign/seal_mac is importable as a general signer."""
    seal = importlib.import_module('oracle_brain.seal')
    for name in ('seal_mac', 'make_mac', 'sign', 'create_mac', 'hmac_sign'):
        assert not hasattr(seal, name), (
            f'public MAC maker {name} must not be a module attribute')
        with pytest.raises(ImportError):
            exec(f'from oracle_brain.seal import {name}')


def test_internal_make_mac_not_exported():
    """The internal helper is underscore-prefixed and not in __all__."""
    seal = importlib.import_module('oracle_brain.seal')
    exported = getattr(seal, '__all__', None)
    if exported is not None:
        assert '_make_mac' not in exported
        assert 'seal_mac' not in exported


def test_forged_credential_mac_still_denied():
    """A MAC under a wrong secret never verifies at the credential boundary."""
    from oracle_brain.meetings.delivery import issue_sender_credential_proof
    from datetime import datetime, timezone

    exp = datetime(2030, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(PermissionError, match='seal MAC mismatch'):
        issue_sender_credential_proof(
            principal_id='p-1', role='delivery_sender', expires_at=exp,
            mac='0' * 64)


def test_forged_enable_mac_still_denied():
    """A forged participation enable MAC is refused."""
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
