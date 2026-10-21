"""Denied-case tests for the seal security boundary.

Proves: the verify path holds no private key and no sign capability,
no MAC/sign helper is importable or getattr-able from the verify module,
the parent process environment carries no private key material, the
signer entrypoint signs only as a process, the signer refuses unknown
purposes and free-form payload bytes, forged / wrong-key / tampered /
truncated seals stay denied, duck-typed catalog connections are denied,
and forged registry mutation attempts are irrelevant (no registry).
"""
from __future__ import annotations

import ast
import importlib
import inspect
import json
import os
import subprocess
import sys

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


def test_parent_env_has_no_private_key_material():
    """The parent process environment must not carry ORACLE2_SEAL_PRIVATE_KEY*.

    The parent knows only the signer key-file path string
    (ORACLE2_SEAL_SIGNER_KEY_FILE). Private key material never sits in
    the parent environment under any name.
    """
    for name in os.environ:
        assert not name.startswith('ORACLE2_SEAL_PRIVATE_KEY'), (
            f'parent environment must not hold {name}')
    assert 'ORACLE2_SEAL_PRIVATE_KEY' not in os.environ
    assert 'ORACLE2_SEAL_PRIVATE_KEY_FILE' not in os.environ


def test_seal_signer_import_yields_no_sign_capability():
    """import oracle_brain.seal_signer must not yield a usable sign().

    Signing code lives under the __main__ guard, so the import surface
    exposes no sign, no key loader and no main entrypoint.
    """
    signer = importlib.import_module('oracle_brain.seal_signer')
    for name in ('sign', 'sign_seal', 'sign_payload', 'main',
                 '_load_private_key', 'load_private_key', '_sign',
                 '_sign_impl', '_run'):
        assert not hasattr(signer, name), (
            f'seal_signer must not expose {name} on import')
    source = inspect.getsource(signer)
    assert 'if __name__' in source and "__main__" in source, (
        'signing logic must live under the __main__ guard')
    # The key loader must not be defined at module import time.
    module_defs = {
        node.name for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert 'sign' not in module_defs
    assert '_load_private_key' not in module_defs
    assert 'main' not in module_defs


def test_signer_cli_refuses_application_supplied_key(tmp_path):
    """An application key path cannot replace fixed host installation/grants."""
    fake_key = tmp_path / 'app-controlled.key'
    fake_key.write_text('00' * 32)
    child = subprocess.run(
        [sys.executable, '-m', 'oracle_brain.seal_signer'],
        input=json.dumps({'purpose': 'participation-enable:v1', 'fields': ['x'],
                          'grant': {}, 'grant_signature': '00'}).encode(),
        capture_output=True, check=False,
        env={**os.environ, 'ORACLE2_SEAL_SIGNER_KEY_FILE': str(fake_key),
             'ORACLE2_SEAL_PRIVATE_KEY_FILE': str(fake_key)})
    assert child.returncode != 0
    assert json.loads(child.stdout) == {'error': 'host signer authorization refused'}


def test_signer_refuses_unknown_purpose_and_free_form_bytes():
    """Unknown purpose, free-form payload_hex and malformed requests are refused."""
    env = {}
    for name in ('SystemRoot', 'WINDIR', 'PATH', 'PATHEXT', 'COMSPEC',
                 'TMP', 'TEMP', 'HOME', 'USERPROFILE'):
        value = os.environ.get(name)
        if value is not None:
            env[name] = value

    def _signer_request(request: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, '-m', 'oracle_brain.seal_signer'],
            input=json.dumps(request).encode('utf-8'),
            capture_output=True,
            check=False,
            env=env,
        )

    # Unknown purpose: refused.
    child = _signer_request({'purpose': 'not-a-real-purpose', 'fields': ['x']})
    assert child.returncode != 0
    assert json.loads(child.stdout) == {'error': 'host signer authorization refused'}
    # Free-form payload bytes: refused.
    child = _signer_request({'payload_hex': '00' * 32})
    assert child.returncode != 0
    assert json.loads(child.stdout) == {'error': 'host signer authorization refused'}
    # Malformed fields: refused.
    child = _signer_request({'purpose': 'participation-enable:v1', 'fields': 'not-a-list'})
    assert child.returncode != 0
    child = _signer_request({'purpose': 'participation-enable:v1', 'fields': [1, 2]})
    assert child.returncode != 0
    # Non-object JSON: refused.
    child = subprocess.run(
        [sys.executable, '-m', 'oracle_brain.seal_signer'],
        input=b'["not", "an", "object"]',
        capture_output=True, check=False, env=env,
    )
    assert child.returncode != 0


def test_verify_mac_refuses_unknown_purpose():
    """verify_mac refuses a purpose outside the fixed allowlist before any check."""
    from oracle_brain.seal import verify_mac
    from seal_testkit import sign_seal

    with pytest.raises(PermissionError, match='purpose not allowed'):
        verify_mac('not-a-real-purpose', '0' * 64, 'x')
    # Even a real signature under a known purpose cannot satisfy an unknown one.
    known = sign_seal('participation-enable:v1', 'm-1')
    with pytest.raises(PermissionError, match='purpose not allowed'):
        verify_mac('made-up-purpose-v1', known, 'm-1')


def test_verification_only_app_has_no_signer_invocation_or_key_path():
    seal = importlib.import_module('oracle_brain.seal')
    source = inspect.getsource(seal)
    assert not hasattr(seal, '_signer_child_env')
    assert 'subprocess' not in source
    assert 'ORACLE2_SEAL_SIGNER_KEY_FILE' not in source


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


def test_duck_typed_catalog_connection_denied():
    """Fake connection objects are denied before any sign."""
    from types import SimpleNamespace
    from oracle_brain.operating_model.q2b_target_catalog_v1 import (
        Q2bExpectedPins, read_target_catalog,
    )

    pins = Q2bExpectedPins(
        function_signatures=('oracle2.invented_helper_alpha(integer)',),
        expected_owner_role='invented_ledger_owner',
        expected_session_role='invented_session_role',
        expected_host='invented-target.example.test',
        expected_port=5432,
        expected_dbname='invented_db',
        expected_user='invented_user',
        expected_sslmode='verify-full',
        expected_execute_grants=(('oracle2.invented_helper_alpha(integer)', ()),),
        role_scope=('invented_ledger_owner', 'invented_session_role'),
    )
    fake = SimpleNamespace(
        info=None, pgconn=None, execute=lambda *a, **k: None)
    with pytest.raises(PermissionError, match='real DB-API connection'):
        read_target_catalog(fake, pins)


def test_no_mutable_registry_in_trust_modules():
    """No WeakSet/id-registry patterns remain; closure mutation is irrelevant."""
    for mod_name in ('oracle_brain.meetings.delivery',
                     'oracle_brain.operating_model.q2b_target_catalog_v1'):
        mod = importlib.import_module(mod_name)
        source = inspect.getsource(mod)
        assert 'WeakSet' not in source, f'{mod_name} must not use WeakSet'
        assert 'from weakref' not in source, f'{mod_name} must not import weakref'
        # Exported installers must not close over a mutable add-able registry.
        for name, obj in vars(mod).items():
            if not callable(obj) or not hasattr(obj, '__closure__'):
                continue
            for cell in (obj.__closure__ or ()):
                contents = getattr(cell, 'cell_contents', None)
                if isinstance(contents, (set, dict)):
                    try:
                        contents.add(object())
                    except AttributeError:
                        try:
                            contents[object()] = object()
                        except Exception:
                            continue
                        else:
                            raise AssertionError(
                                f'{mod_name}.{name} closes over a mutable registry')
                    else:
                        raise AssertionError(
                            f'{mod_name}.{name} closes over a mutable registry')


def test_verify_rejects_forged_wrong_key_tampered_and_truncated():
    """Denied cases: forged, wrong key, tampered payload, truncated signature.

    The good signature comes from the synthetic test host; no installation
    or host capability is established.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    from oracle_brain.seal import seal_payload, verify, verify_mac
    from seal_testkit import sign_seal

    purpose = 'participation-enable:v1'
    fields = ['field-1', 'field-2']
    payload = seal_payload(purpose, *fields)
    good = sign_seal(purpose, *fields)
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
        verify_mac(purpose, wrong_key, *fields)
    with pytest.raises(PermissionError, match='seal MAC mismatch'):
        verify_mac(purpose, good, 'field-1', 'OTHER')


@pytest.fixture
def synthetic_host_signer(monkeypatch, tmp_path):
    """Run the real signer under mocked host ownership, never install host files."""
    import hashlib
    import io
    import runpy
    import stat
    signer_file = importlib.import_module('oracle_brain.seal_signer').__file__
    from types import SimpleNamespace
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from oracle_brain.seal_wire import seal_payload

    host_key = Ed25519PrivateKey.generate()
    grant_key = Ed25519PrivateKey.generate()
    config = {'signer_uid': 8101, 'application_uid': 8102,
              'key_file': '/synthetic-host/seal-private.key',
              'grant_public_key': grant_key.public_key().public_bytes_raw().hex()}
    state = {'uid': 8101, 'config_mode': stat.S_IFREG | 0o644, 'config_uid': 0,
             'key_mode': stat.S_IFREG | 0o600, 'key_uid': 8101, 'now': 1000}
    config_file, key_file = tmp_path / 'host-config.json', tmp_path / 'host-key'
    original_open, original_fstat = os.open, os.fstat
    fd_roles = {}
    open_flags = []

    def open_file(path, flags, *args, **kwargs):
        if path == '/etc/oracle2/seal-signer.json':
            config_file.write_text(json.dumps(config))
            fd = original_open(config_file, flags, *args, **kwargs)
            fd_roles[fd] = 'config'
        elif path == config['key_file']:
            key_file.write_text(host_key.private_bytes_raw().hex())
            fd = original_open(key_file, flags, *args, **kwargs)
            fd_roles[fd] = 'key'
        else:
            return original_open(path, flags, *args, **kwargs)
        open_flags.append(flags)
        return fd

    def fstat(fd):
        role = fd_roles.get(fd)
        if role:
            return SimpleNamespace(st_mode=state[role + '_mode'], st_uid=state[role + '_uid'])
        return original_fstat(fd)

    def request():
        payload = seal_payload('participation-enable:v1', 'invented-meeting')
        grant = {'audience': 'oracle2-host-seal-v1',
                 'payload_sha256': hashlib.sha256(payload).hexdigest(),
                 'expires_at': 1100}
        signature = grant_key.sign(json.dumps(grant, sort_keys=True,
                                    separators=(',', ':')).encode()).hex()
        return {'purpose': 'participation-enable:v1', 'fields': ['invented-meeting'],
                'grant': grant, 'grant_signature': signature}

    def run(value):
        output = io.StringIO()
        with monkeypatch.context() as patch:
            patch.setattr(os, 'open', open_file)
            patch.setattr(os, 'fstat', fstat)
            patch.setattr(os, 'geteuid', lambda: state['uid'])
            import time
            patch.setattr(time, 'time', lambda: state['now'])
            patch.setattr(sys, 'stdin', io.StringIO(json.dumps(value)))
            patch.setattr(sys, 'stdout', output)
            with pytest.raises(SystemExit) as stopped:
                runpy.run_path(signer_file, run_name='__main__')
        return stopped.value.code, json.loads(output.getvalue())

    return SimpleNamespace(run=run, request=request, state=state, config=config,
                           public_key=host_key.public_key(), open_flags=open_flags, host_key=host_key,
                           grant_key=grant_key)


def test_mock_host_signer_accepts_exact_independent_grant(synthetic_host_signer):
    from oracle_brain.seal_wire import seal_payload
    host = synthetic_host_signer
    code, result = host.run(host.request())
    assert code == 0
    assert len(host.open_flags) == 2
    assert all(flags & os.O_NOFOLLOW for flags in host.open_flags)
    host.public_key.verify(bytes.fromhex(result['signature']),
                           seal_payload('participation-enable:v1', 'invented-meeting'))


@pytest.mark.parametrize('damage', ['missing', 'expired', 'payload', 'signature',
                                    'wrong_authority', 'audience', 'nan', 'bool', 'same_key'])
def test_host_signer_denies_invalid_independent_grant(synthetic_host_signer, damage):
    host = synthetic_host_signer
    request = host.request()
    if damage == 'missing':
        request.pop('grant')
    elif damage == 'expired':
        host.state['now'] = 1200
    elif damage == 'payload':
        request['fields'] = ['other-meeting']
    elif damage == 'signature':
        request['grant_signature'] = '00' * 64
    elif damage == 'wrong_authority':
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        host.config['grant_public_key'] = Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()
    elif damage == 'nan':
        request['grant']['expires_at'] = float('nan')
    elif damage == 'bool':
        request['grant']['expires_at'] = True
    elif damage == 'same_key':
        host.config['grant_public_key'] = host.public_key.public_bytes_raw().hex()
        request['grant_signature'] = host.host_key.sign(json.dumps(request['grant'], sort_keys=True, separators=(',', ':')).encode()).hex()
    else:
        request['grant']['audience'] = 'other-service'
    assert host.run(request) == (1, {'error': 'host signer authorization refused'})


@pytest.mark.parametrize(('field', 'value'), [
    ('uid', 8102), ('uid', 9000), ('config_uid', 8102),
    ('config_mode', 0o100666), ('config_mode', 0o120777),
    ('key_uid', 8102), ('key_mode', 0o100644), ('key_mode', 0o120600),
])
def test_host_signer_denies_wrong_identity_or_ownership(synthetic_host_signer, field, value):
    host = synthetic_host_signer
    host.state[field] = value
    assert host.run(host.request()) == (1, {'error': 'host signer authorization refused'})


def test_host_signer_denies_same_application_and_signer_identity(synthetic_host_signer):
    host = synthetic_host_signer
    host.config['application_uid'] = host.config['signer_uid']
    assert host.run(host.request()) == (1, {'error': 'host signer authorization refused'})


def test_request_cannot_replace_pinned_public_issuer(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from oracle_brain.seal import verify, seal_payload
    from seal_testkit import sign_seal
    payload = seal_payload('delivery-action:v1', 'intent', 'sent', 'time')
    assert verify(payload, sign_seal('delivery-action:v1', 'intent', 'sent', 'time'))
    attacker = Ed25519PrivateKey.generate()
    monkeypatch.setenv('ORACLE2_SEAL_PUBLIC_KEY', attacker.public_key().public_bytes_raw().hex())
    assert not verify(payload, attacker.sign(payload).hex())
