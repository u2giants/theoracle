"""Byte-only complete-parent CONSUMER; no signer/server/admission issuance.

This separate version never casts raw originals into future qualified SourceRefs.
Existing TLS and durable challenge/highwater custody primitives remain unchanged.
"""
import base64,hashlib,json,time
from datetime import datetime,timezone
from typing import Literal
from uuid import UUID
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import AwareDatetime,Field,field_validator,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.original_qualification_v1 import RawOriginalPopulationV1
from .custody import DurableNonceSequenceV2
from .gateway import unique_object
from .purpose_transport import _FixedTLSClientV2,PurposeTLSBindingV2

HASH=r'^[0-9a-f]{64}$'
URI=r'^spiffe://oracle/[A-Za-z0-9._/-]+$'
PURPOSE='complete-raw-original-currentness-v1'
DOMAIN=b'oracle.complete-raw-original-currentness-v1\x00'

class _RawObserverRecordV1(StrictRecord):
    schema_version:Literal[1]=1
    purpose:Literal['complete-raw-original-currentness-v1']

    @field_validator('schema_version',mode='before')
    @classmethod
    def version_integer(cls,value):
        if type(value) is not int or value!=1:raise ValueError('raw observer version is integer one')
        return value

class RawOriginalObserverAdmissionV1(_RawObserverRecordV1):
    population:RawOriginalPopulationV1
    principal_id:UUID
    observer_uri:str=Field(pattern=URI)
    client_uri:str=Field(pattern=URI)
    signing_public_key:str=Field(pattern=HASH)
    signing_key_fingerprint:str=Field(pattern=HASH)
    issuer_actor:UUID
    reviewer_actor:UUID
    minimum_sequence:int=Field(strict=True,ge=0)
    max_age_seconds:int=Field(strict=True,ge=1,le=5)
    expires_at:AwareDatetime

    @model_validator(mode='after')
    def independently_appointed(self):
        if (hashlib.sha256(bytes.fromhex(self.signing_public_key)).hexdigest()!=self.signing_key_fingerprint
                or len({self.principal_id,self.issuer_actor,self.reviewer_actor})!=3
                or self.expires_at>self.population.expires_at):
            raise ValueError('independent exact raw observer appointment required')
        return self

class RawOriginalCurrentnessWitnessV1(_RawObserverRecordV1):
    admission_hash:str=Field(pattern=HASH)
    challenge:str=Field(pattern=HASH)
    sequence:int=Field(strict=True,ge=1)
    population:RawOriginalPopulationV1
    principal_id:UUID
    observer_uri:str=Field(pattern=URI)
    client_uri:str=Field(pattern=URI)
    checked_at:AwareDatetime
    expires_at:AwareDatetime
    revoked:bool


def verify_raw_original_currentness_v1(raw,*,admission,trusted_admission_hash,expected_population,
        challenge,previous_sequence,started_at,now,elapsed_seconds):
    """Existing Ed25519/challenge policy, exact NEW raw domain/types only."""
    if (type(admission) is not RawOriginalObserverAdmissionV1
            or digest(admission.model_dump(mode='json'))!=trusted_admission_hash
            or type(expected_population) is not RawOriginalPopulationV1
            or admission.population!=expected_population
            or type(previous_sequence) is not int or previous_sequence<admission.minimum_sequence
            or type(elapsed_seconds) not in (int,float) or not 0<=elapsed_seconds<=admission.max_age_seconds
            or not isinstance(now,datetime) or not isinstance(started_at,datetime)
            or now.tzinfo is None or started_at.tzinfo is None or now<started_at or now>=admission.expires_at):
        raise PermissionError('current separately appointed raw population observer required')
    RawOriginalObserverAdmissionV1.model_validate(admission.model_dump(mode='python'))
    RawOriginalPopulationV1.model_validate(expected_population.model_dump(mode='python'))
    if type(raw) is not bytes or len(raw)>100_000:
        raise PermissionError('bounded raw metadata response required')
    value=json.loads(raw,object_pairs_hook=unique_object,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite observer metadata')))
    if type(value) is not dict or set(value)!={'witness','signature'}:
        raise PermissionError('exact signed raw witness required')
    witness=RawOriginalCurrentnessWitnessV1.model_validate_json(canonical_bytes(value['witness']))
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(admission.signing_public_key)).verify(
        base64.b64decode(value['signature'],validate=True),DOMAIN+canonical_bytes(value['witness']))
    if (witness.admission_hash!=trusted_admission_hash or witness.challenge!=challenge
            or witness.sequence<=previous_sequence or witness.population!=expected_population
            or witness.principal_id!=admission.principal_id or witness.observer_uri!=admission.observer_uri
            or witness.client_uri!=admission.client_uri or witness.revoked
            or not started_at<=witness.checked_at<=now<witness.expires_at
            or (now-witness.checked_at).total_seconds()>admission.max_age_seconds
            or witness.expires_at>min(admission.expires_at,expected_population.expires_at)
            or (witness.expires_at-witness.checked_at).total_seconds()>admission.max_age_seconds):
        raise PermissionError('stale replayed revoked or changed raw population witness')
    return witness

class RawOriginalObserverClientV1(_FixedTLSClientV2):
    def __init__(self,binding):
        if type(binding) is not PurposeTLSBindingV2 or binding.timeout>5:
            raise PermissionError('actual fixed raw observer TLS and total <=5s required')
        super().__init__(binding)

    def fetch_current(self,challenge):
        import re
        if type(challenge) is not str or re.fullmatch(HASH,challenge) is None:
            raise PermissionError('fresh canonical raw observer challenge required')
        raw=self._post('/v1/originals/parent/current',{'schema_version':1,'purpose':PURPOSE,'challenge':challenge},100_000)
        value=json.loads(raw,object_pairs_hook=unique_object)
        if type(value) is not dict or set(value)!={'witness','signature'}:
            raise PermissionError('exact raw observer signed envelope required')
        return raw

class RawOriginalCurrentnessConsumerV1:
    def __init__(self,*,admission,trusted_admission_hash,transport,replay,clock=None,monotonic=None):
        if (type(admission) is not RawOriginalObserverAdmissionV1
                or digest(admission.model_dump(mode='json'))!=trusted_admission_hash
                or type(transport) is not RawOriginalObserverClientV1
                or type(replay) is not DurableNonceSequenceV2
                or replay.appointment_hash!=trusted_admission_hash
                or replay.minimum_sequence!=admission.minimum_sequence):
            raise PermissionError('actual raw observer and existing appointed replay state required')
        self.admission,self.admission_hash=admission,trusted_admission_hash
        self.transport,self.replay=transport,replay
        self.clock=clock or (lambda:datetime.now(timezone.utc));self.monotonic=monotonic or time.monotonic

    def current(self,expected_population):
        import secrets
        before=self.clock()
        if type(expected_population) is not RawOriginalPopulationV1 or before>=min(self.admission.expires_at,expected_population.expires_at):
            raise PermissionError('raw observer appointment expired before exchange')
        challenge=secrets.token_hex(32)
        self.replay.claim(challenge)
        started_at=self.clock();tick=self.monotonic()
        raw=self.transport.fetch_current(challenge)  # No SQL/replay lock during network.
        elapsed=self.monotonic()-tick;now=self.clock()
        if type(raw) is not bytes or len(raw)>100_000:
            raise PermissionError('bounded raw observer metadata required')
        value=json.loads(raw,object_pairs_hook=unique_object)
        if type(value) is not dict or type(value.get('witness')) is not dict:
            raise PermissionError('exact raw witness envelope required')
        witness=None
        def verify(previous):
            nonlocal witness
            witness=verify_raw_original_currentness_v1(raw,admission=self.admission,
                trusted_admission_hash=self.admission_hash,expected_population=expected_population,
                challenge=challenge,previous_sequence=previous,started_at=started_at,now=now,elapsed_seconds=elapsed)
        self.replay.advance(challenge,value['witness'].get('sequence'),verify=verify)
        return witness
