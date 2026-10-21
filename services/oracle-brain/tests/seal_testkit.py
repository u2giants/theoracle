"""Test host stand-in: request signatures from the signer CLI entrypoint.

Tests act as the host identity service. They never load the seal private
key into the test process; signatures come from the signer child process,
which reads the key file that the parent only knows by path. This module
is test-only and is never imported by application code.

The signer only accepts structured ``{"purpose", "fields"}`` requests
with a purpose from the fixed allowlist. Free-form payload bytes are
refused. ``sign_seal`` is the only signing entrypoint tests need.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from oracle_brain.seal_wire import require_allowed_purpose, wire_fields

SEAL_SIGNER_KEY_FILE_ENV = 'ORACLE2_SEAL_SIGNER_KEY_FILE'


def _signer_env(key_path: str) -> dict:
    """Explicit clean environment for the signer child (mirrors seal.py)."""
    env = {SEAL_SIGNER_KEY_FILE_ENV: key_path}
    for name in ('SystemRoot', 'WINDIR', 'PATH', 'PATHEXT', 'COMSPEC',
                 'TMP', 'TEMP', 'HOME', 'USERPROFILE'):
        value = os.environ.get(name)
        if value is not None:
            env[name] = value
    return env


def sign_seal(purpose: str, *fields) -> str:
    """Purpose-tagged seal signature via the signer CLI (host stand-in).

    Sends a structured request: allowlisted purpose plus plain-string
    fields. Free-form payload bytes never cross this boundary.
    """
    require_allowed_purpose(purpose)
    key_path = os.environ.get(SEAL_SIGNER_KEY_FILE_ENV, '')
    if not key_path:
        raise RuntimeError(f'{SEAL_SIGNER_KEY_FILE_ENV} not configured')
    request = json.dumps({'purpose': purpose, 'fields': wire_fields(*fields)})
    child = subprocess.run(
        [sys.executable, '-m', 'oracle_brain.seal_signer'],
        input=request.encode('utf-8'),
        capture_output=True,
        check=False,
        env=_signer_env(key_path),
    )
    if child.returncode != 0:
        detail = child.stdout.decode('utf-8', 'replace')[:200]
        raise RuntimeError(f'seal signer failed: {detail}')
    response = json.loads(child.stdout.decode('utf-8') or '{}')
    signature = response.get('signature')
    if not isinstance(signature, str) or not signature:
        raise RuntimeError(f'seal signer error: {response.get("error")}')
    return signature
