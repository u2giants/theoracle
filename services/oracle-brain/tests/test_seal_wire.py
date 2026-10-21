"""Canonical seal messages preserve field boundaries and reject objects."""
from datetime import datetime, timezone
import json

import pytest

from oracle_brain.seal_wire import seal_payload, wire_fields


def test_delimiter_bearing_fields_have_distinct_payloads():
    purpose = 'delivery-action:v1'
    assert seal_payload(purpose, 'a|b', 'c') != seal_payload(purpose, 'a', 'b|c')
    assert seal_payload(purpose, 'a', '') != seal_payload(purpose, 'a')
    assert seal_payload(purpose, '["x"]', '雪\\"') != seal_payload(purpose, 'x', '雪\\"')
    assert json.loads(seal_payload(purpose, 'a|b', 'c')) == [purpose, ['a|b', 'c']]


def test_normalized_fields_have_identical_signer_and_verifier_payloads():
    fields = ('id', datetime(2026, 1, 1, tzinfo=timezone.utc), 3, True, None, 1.5)
    assert seal_payload('delivery-action:v1', *fields) == seal_payload(
        'delivery-action:v1', *wire_fields(*fields))


def test_signature_cannot_move_delimiter_between_fields():
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key = Ed25519PrivateKey.generate()
    signed = seal_payload('delivery-action:v1', 'a|b', 'sent', 'now')
    forged = seal_payload('delivery-action:v1', 'a', 'b|sent', 'now')
    signature = private_key.sign(signed)
    private_key.public_key().verify(signature, signed)
    with pytest.raises(InvalidSignature):
        private_key.public_key().verify(signature, forged)


def test_arbitrary_conversion_hooks_are_not_called():
    class Impostor:
        def isoformat(self):
            pytest.fail('arbitrary isoformat hook ran')

        def __str__(self):
            pytest.fail('arbitrary string hook ran')

    with pytest.raises(TypeError):
        wire_fields(Impostor())


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_fields_are_denied(value):
    with pytest.raises(ValueError):
        wire_fields(value)


def test_unknown_purpose_is_denied_before_encoding():
    with pytest.raises(PermissionError):
        seal_payload('unknown', 'a')
