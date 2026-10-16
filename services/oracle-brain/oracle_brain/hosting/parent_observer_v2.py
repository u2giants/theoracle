"""Complete-parent currentness CONSUMER only; no observer, signer or admission issuer.

Workers receive only metadata. The independently appointed observer must check
actual complete parent bytes/current authority outside this process. Fixture keys
never become runtime authority through construction of these records.
"""
import base64
import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import AwareDatetime, Field, model_validator

from oracle_brain.operating_model.contracts import StrictRecord, canonical_bytes, digest
from oracle_brain.operating_model.purpose_context import HASH, WORKER, ParentPopulationAdmissionV2

PURPOSE='complete-parent-currentness-v2'
DOMAIN=b'oracle.complete-parent-currentness-v2\x00'


class ParentObserverAdmissionV2(StrictRecord):
    schema_version: Literal[2] = 2
    purpose: Literal['complete-parent-currentness-v2']
    population: ParentPopulationAdmissionV2
    principal_id: UUID
    observer_uri: str = Field(pattern=WORKER)
    client_uri: str = Field(pattern=WORKER)
    signing_public_key: str = Field(pattern=HASH)
    signing_key_fingerprint: str = Field(pattern=HASH)
    issuer_actor: UUID
    reviewer_actor: UUID
    minimum_sequence: int = Field(strict=True, ge=0)
    max_age_seconds: int = Field(strict=True, ge=1, le=5)
    expires_at: AwareDatetime

    @model_validator(mode='after')
    def appointment(self):
        if (hashlib.sha256(bytes.fromhex(self.signing_public_key)).hexdigest()!=self.signing_key_fingerprint
                or len({self.principal_id,self.issuer_actor,self.reviewer_actor})!=3
                or self.expires_at>self.population.expires_at):
            raise ValueError('independent exact complete-parent observer appointment required')
        return self


class ParentCurrentnessWitnessV2(StrictRecord):
    schema_version: Literal[2] = 2
    purpose: Literal['complete-parent-currentness-v2']
    admission_hash: str = Field(pattern=HASH)
    challenge: str = Field(pattern=HASH)
    sequence: int = Field(strict=True, ge=1)
    population: ParentPopulationAdmissionV2
    principal_id: UUID
    observer_uri: str = Field(pattern=WORKER)
    client_uri: str = Field(pattern=WORKER)
    checked_at: AwareDatetime
    expires_at: AwareDatetime
    revoked: bool


def verify_parent_currentness_v2(raw, *, admission, trusted_admission_hash,
        expected_population, challenge, previous_sequence, started_at, now,
        elapsed_seconds):
    """Pure cryptographic/freshness check. Caller consumes durable replay state.

    A signed file alone is insufficient: the fresh challenge must originate in
    this caller immediately before the bounded authenticated observer exchange.
    """
    from .gateway import unique_object
    if type(admission) is ParentObserverAdmissionV2:
        admission=ParentObserverAdmissionV2.model_validate(admission.model_dump(mode='python'))
    if (type(admission) is not ParentObserverAdmissionV2
            or digest(admission.model_dump(mode='json'))!=trusted_admission_hash
            or type(expected_population) is not ParentPopulationAdmissionV2
            or admission.population!=expected_population
            or type(previous_sequence) is not int or previous_sequence<admission.minimum_sequence
            or type(elapsed_seconds) not in (int,float)
            or not 0<=elapsed_seconds<=admission.max_age_seconds
            or now.tzinfo is None or started_at.tzinfo is None
            or now<started_at or now>=admission.expires_at):
        raise PermissionError('current separately appointed complete-parent observer required')
    if not isinstance(raw,bytes) or len(raw)>100_000:
        raise PermissionError('bounded metadata-only currentness response required')
    value=json.loads(raw,object_pairs_hook=unique_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite observer response')))
    if not isinstance(value,dict) or set(value)!={'witness','signature'}:
        raise PermissionError('exact signed complete-parent witness required')
    witness=ParentCurrentnessWitnessV2.model_validate_json(canonical_bytes(value['witness']))
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(admission.signing_public_key)).verify(
        base64.b64decode(value['signature'],validate=True),DOMAIN+canonical_bytes(value['witness']))
    if (witness.admission_hash!=trusted_admission_hash or witness.challenge!=challenge
            or witness.sequence<=previous_sequence or witness.population!=expected_population
            or witness.principal_id!=admission.principal_id
            or witness.observer_uri!=admission.observer_uri or witness.client_uri!=admission.client_uri
            or witness.revoked or not started_at<=witness.checked_at<=now<witness.expires_at
            or (now-witness.checked_at).total_seconds()>admission.max_age_seconds
            or witness.expires_at>min(admission.expires_at,expected_population.expires_at)
            or (witness.expires_at-witness.checked_at).total_seconds()>admission.max_age_seconds):
        raise PermissionError('stale, replayed, revoked or changed complete-parent witness')
    return witness


class ParentObserverTransportV2:
    """R4's fixed authenticated transport implements this; never a bool callback."""
    def fetch_current(self, challenge: str) -> bytes:
        raise PermissionError('actual independently admitted observer transport unavailable')


class ParentCurrentnessConsumerV2:
    """Fresh challenge exchange using retained custody's durable replay primitive."""
    def __init__(self,*,admission,trusted_admission_hash,transport,replay,clock=None,monotonic=None):
        import time
        from datetime import timezone
        from .custody import DurableNonceSequenceV2
        if (type(admission) is not ParentObserverAdmissionV2
                or digest(admission.model_dump(mode='json'))!=trusted_admission_hash
                or not isinstance(transport,ParentObserverTransportV2)
                or type(replay) is not DurableNonceSequenceV2
                or replay.appointment_hash!=trusted_admission_hash
                or replay.minimum_sequence!=admission.minimum_sequence):
            raise PermissionError('actual fixed observer and externally provisioned replay state required')
        self.admission,self.admission_hash=admission,trusted_admission_hash
        self.transport,self.replay=transport,replay
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.monotonic=monotonic or time.monotonic

    def current(self,expected_population):
        import secrets
        before=self.clock()
        if before>=min(self.admission.expires_at,expected_population.expires_at):
            raise PermissionError('observer appointment expired before challenge exchange')
        challenge=secrets.token_hex(32)
        self.replay.claim(challenge)
        started_at=self.clock();tick=self.monotonic()
        raw=self.transport.fetch_current(challenge)  # No replay/SQL lock during network.
        if not isinstance(raw,bytes) or len(raw)>100_000:
            raise PermissionError('bounded observer metadata response required')
        elapsed=self.monotonic()-tick;now=self.clock()
        from .gateway import unique_object
        value=json.loads(raw,object_pairs_hook=unique_object)
        # Parsing sequence conveys no trust. Full signature/currentness verification
        # occurs under the replay transaction before any highwater advancement.
        if not isinstance(value,dict) or not isinstance(value.get('witness'),dict):
            raise PermissionError('exact signed observer response required')
        witness=None
        def verify(previous):
            nonlocal witness
            witness=verify_parent_currentness_v2(raw,admission=self.admission,
                trusted_admission_hash=self.admission_hash,expected_population=expected_population,
                challenge=challenge,previous_sequence=previous,started_at=started_at,now=now,
                elapsed_seconds=elapsed)
        self.replay.advance(challenge,value['witness'].get('sequence'),verify=verify)
        return witness
