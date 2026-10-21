"""Host-only signer, never invoked by the verification-only application.

Installation must provide /etc/oracle2/seal-signer.json owned by root and
not writable by group/others. It pins distinct signer/application Unix UIDs,
a private key owned exclusively by the signer, and a separate grant authority
public key. Every request needs that authority's unexpired signature over the
exact purpose/payload digest. Offline tests do not establish host installation.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
import stat
import sys
import time
from oracle_brain.seal_wire import require_allowed_purpose, seal_payload

CONFIG_PATH = '/etc/oracle2/seal-signer.json'
__all__ = ('CONFIG_PATH',)


def _parse_sign_request(raw: str) -> tuple[bytes, dict, str]:
    request = json.loads(raw or '{}')
    if not isinstance(request, dict):
        raise PermissionError('seal signer request must be JSON object')
    if 'payload_hex' in request or 'payload' in request:
        raise PermissionError('seal signer refuses free-form payload bytes')
    purpose = request.get('purpose')
    require_allowed_purpose(purpose)
    fields = request.get('fields')
    if not isinstance(fields, list) or not all(isinstance(v, str) for v in fields):
        raise PermissionError('seal signer fields must be strings')
    grant, signature = request.get('grant'), request.get('grant_signature')
    if not isinstance(grant, dict) or not isinstance(signature, str):
        raise PermissionError('independent exact-payload authorization grant required')
    return seal_payload(purpose, *fields), grant, signature


if __name__ == '__main__':
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

    def main() -> int:
        try:
            payload, grant, grant_signature = _parse_sign_request(sys.stdin.read())
            config_fd = os.open(CONFIG_PATH, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(config_fd, encoding='utf-8') as handle:
                config_stat = os.fstat(handle.fileno())
                if not stat.S_ISREG(config_stat.st_mode) or config_stat.st_uid != 0 or config_stat.st_mode & 0o022:
                    raise PermissionError('host signer configuration ownership invalid')
                config = json.load(handle)
            uid = os.geteuid()
            if uid != config['signer_uid'] or uid == config['application_uid']:
                raise PermissionError('signer requires a separate host identity')
            if (grant.get('audience') != 'oracle2-host-seal-v1'
                    or grant.get('payload_sha256') != hashlib.sha256(payload).hexdigest()
                    or not isinstance(grant.get('expires_at'), (int, float))
                    or isinstance(grant.get('expires_at'), bool)
                    or not math.isfinite(grant['expires_at'])
                    or grant['expires_at'] <= time.time()):
                raise PermissionError('host grant mismatch or expired')
            grant_bytes = json.dumps(grant, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(config['grant_public_key'])).verify(bytes.fromhex(grant_signature), grant_bytes)
            key_fd = os.open(config['key_file'], os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(key_fd, encoding='ascii') as handle:
                key_stat = os.fstat(handle.fileno())
                if (not stat.S_ISREG(key_stat.st_mode) or key_stat.st_uid != uid
                        or key_stat.st_mode & 0o077):
                    raise PermissionError('signer key must be exclusive to host signer identity')
                key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(handle.read().strip()))
            if key.public_key().public_bytes_raw().hex() == config['grant_public_key']:
                raise PermissionError('grant authority must differ from signing identity')
            signature = key.sign(payload).hex()
            sys.stdout.write(json.dumps({'signature': signature}))
            return 0
        except Exception:
            sys.stdout.write(json.dumps({'error': 'host signer authorization refused'}))
            return 1

    raise SystemExit(main())
