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
from pydantic import AwareDatetime, Field, model_validator,field_validator

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

# Distinct closed meeting-supervision purpose. Existing parent populations and
# witnesses above are never reinterpreted as meeting or provider permission.
MEETING_SUPERVISOR_DOMAIN=b'oracle.meeting-supervisor-currentness-v1\x00'

class _MeetingSupervisorRecordV1(StrictRecord):
    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_schema(cls,v):
        if type(v) is not int or v!=1:raise ValueError('exact integer supervisor schema required')
        return v

class MeetingSupervisorScopeV1(_MeetingSupervisorRecordV1):
    workspace_id:UUID
    meeting_id:UUID
    provider_account:str=Field(min_length=1,max_length=256)
    create_operation_id:UUID
    create_request_sha256:str=Field(pattern=HASH)
    scheduler_id:UUID
    scheduler_runtime_sha256:str=Field(pattern=HASH)
    scheduler_config_sha256:str=Field(pattern=HASH)
    stop_owner_id:UUID
    stop_runtime_sha256:str=Field(pattern=HASH)
    stop_config_sha256:str=Field(pattern=HASH)
    capture_until:AwareDatetime
    stop_valid_from:AwareDatetime
    stop_until:AwareDatetime
    original_horizon:AwareDatetime
    scheduler_poll_seconds:int=Field(strict=True,ge=1,le=30)
    stop_request_seconds:int=Field(strict=True,ge=1,le=30)
    safety_allowance_seconds:int=Field(strict=True,ge=1,le=60)
    stop_margin_seconds:int=Field(strict=True,ge=3,le=120)
    @model_validator(mode='after')
    def original_stop_window(self):
        from datetime import timedelta
        if (not self.stop_valid_from<self.capture_until<=self.stop_until<=self.original_horizon
            or self.stop_margin_seconds<self.scheduler_poll_seconds+self.stop_request_seconds+self.safety_allowance_seconds
            or self.capture_until-timedelta(seconds=self.stop_margin_seconds)<=self.stop_valid_from):
            raise ValueError('preinstalled finite STOP-only window and full original margin required')
        return self
    @field_validator('provider_account')
    @classmethod
    def canonical_account(cls,v):
        if v!=v.strip() or any(ord(c)<32 or ord(c)==127 for c in v):raise ValueError('canonical installed provider account required')
        return v

class MeetingSupervisorAdmissionV1(_MeetingSupervisorRecordV1):
    purpose:Literal['meeting-supervisor-currentness-v1']
    scope:MeetingSupervisorScopeV1
    principal_id:UUID
    observer_uri:str=Field(pattern=WORKER)
    client_uri:str=Field(pattern=WORKER)
    signing_public_key:str=Field(pattern=HASH)
    signing_key_fingerprint:str=Field(pattern=HASH)
    issuer_actor:UUID
    reviewer_actor:UUID
    minimum_sequence:int=Field(strict=True,ge=0)
    max_age_seconds:int=Field(strict=True,ge=1,le=5)
    expires_at:AwareDatetime
    @model_validator(mode='after')
    def exact(self):
        if (hashlib.sha256(bytes.fromhex(self.signing_public_key)).hexdigest()!=self.signing_key_fingerprint
            or len({self.principal_id,self.issuer_actor,self.reviewer_actor,self.scope.scheduler_id,self.scope.stop_owner_id})!=5
            or self.expires_at>self.scope.capture_until):
            raise ValueError('independent exact meeting supervisor appointment required')
        return self

class MeetingSupervisorWitnessV1(_MeetingSupervisorRecordV1):
    purpose:Literal['meeting-supervisor-currentness-v1']
    admission_hash:str=Field(pattern=HASH)
    scope:MeetingSupervisorScopeV1
    principal_id:UUID
    observer_uri:str=Field(pattern=WORKER)
    client_uri:str=Field(pattern=WORKER)
    challenge:str=Field(pattern=HASH)
    sequence:int=Field(strict=True,ge=1)
    scheduler_observation_sha256:str=Field(pattern=HASH)
    checked_at:AwareDatetime
    expires_at:AwareDatetime

MEETING_SUPERVISOR_DOMAIN_V2=b'oracle.meeting-supervisor-currentness-v2\x00'

class MeetingSupervisorAdmissionV2(MeetingSupervisorAdmissionV1):
    schema_version:Literal[2]=2
    purpose:Literal['meeting-supervisor-currentness-v2']
    scheduler_process_sha256:str=Field(pattern=HASH)
    stop_process_sha256:str=Field(pattern=HASH)
    max_age_seconds:Literal[2]=2
    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_schema(cls,value):
        if type(value) is not int or value!=2:raise ValueError('actual v2 supervisor schema required')
        return value
    @field_validator('max_age_seconds',mode='before')
    @classmethod
    def exact_freshness(cls,value):
        if type(value) is not int or value!=2:raise ValueError('original two-second supervisor freshness required')
        return value

class MeetingSupervisorWitnessV2(MeetingSupervisorWitnessV1):
    schema_version:Literal[2]=2
    purpose:Literal['meeting-supervisor-currentness-v2']
    scheduler_process_sha256:str=Field(pattern=HASH)
    stop_process_sha256:str=Field(pattern=HASH)
    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_schema(cls,value):
        if type(value) is not int or value!=2:raise ValueError('actual v2 supervisor witness required')
        return value

def verify_meeting_supervisor_v1(raw,*,admission,trusted_admission_hash,expected_scope,challenge,previous_sequence,started_at,now,elapsed_seconds):
    if type(admission) is not MeetingSupervisorAdmissionV1:raise PermissionError('exact v1 supervisor admission required')
    return _verify_meeting_supervisor(raw,admission=admission,trusted_admission_hash=trusted_admission_hash,expected_scope=expected_scope,challenge=challenge,previous_sequence=previous_sequence,started_at=started_at,now=now,elapsed_seconds=elapsed_seconds)

def verify_meeting_supervisor_v2(raw,*,admission,trusted_admission_hash,expected_scope,challenge,previous_sequence,started_at,now,elapsed_seconds):
    if type(admission) is not MeetingSupervisorAdmissionV2:raise PermissionError('exact v2 producer profile admission required')
    return _verify_meeting_supervisor(raw,admission=admission,trusted_admission_hash=trusted_admission_hash,expected_scope=expected_scope,challenge=challenge,previous_sequence=previous_sequence,started_at=started_at,now=now,elapsed_seconds=elapsed_seconds)

def _verify_meeting_supervisor(raw,*,admission,trusted_admission_hash,expected_scope,challenge,previous_sequence,started_at,now,elapsed_seconds):
    """Same signature/replay owner, closed new domain; never old parent proof."""
    import math
    if type(admission) not in (MeetingSupervisorAdmissionV1,MeetingSupervisorAdmissionV2) or type(expected_scope) is not MeetingSupervisorScopeV1:
        raise PermissionError('exact independent supervisor scope required')
    admission=type(admission).model_validate(admission.model_dump(mode='python'))
    v2=type(admission) is MeetingSupervisorAdmissionV2
    expected_scope=MeetingSupervisorScopeV1.model_validate(expected_scope.model_dump(mode='python'))
    if (digest(admission.model_dump(mode='json'))!=trusted_admission_hash or admission.scope!=expected_scope
        or type(previous_sequence) is not int or previous_sequence<admission.minimum_sequence
        or type(elapsed_seconds) not in (int,float) or not math.isfinite(elapsed_seconds) or not 0<=elapsed_seconds<=admission.max_age_seconds
        or type(challenge) is not str or len(challenge)!=64
        or type(now) is not datetime or type(started_at) is not datetime or now.tzinfo is None or started_at.tzinfo is None
        or now<started_at or now>=min(admission.expires_at,expected_scope.capture_until)):
        raise PermissionError('current exact supervisor observation required')
    if type(raw) is not bytes or not 0<len(raw)<=16384:raise PermissionError('bounded supervisor observation required')
    from .gateway import unique_object
    value=json.loads(raw,object_pairs_hook=unique_object,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite observer response')))
    if type(value) is not dict or set(value)!={'witness','signature'}:raise PermissionError('closed signed supervisor witness required')
    witness=(MeetingSupervisorWitnessV2 if v2 else MeetingSupervisorWitnessV1).model_validate_json(canonical_bytes(value['witness']))
    signature=base64.b64decode(value['signature'],validate=True)
    if base64.b64encode(signature).decode()!=value['signature'] or len(signature)!=64:raise PermissionError('canonical supervisor signature required')
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(admission.signing_public_key)).verify(signature,(MEETING_SUPERVISOR_DOMAIN_V2 if v2 else MEETING_SUPERVISOR_DOMAIN)+canonical_bytes(value['witness']))
    if (witness.admission_hash!=trusted_admission_hash or witness.scope!=expected_scope or witness.challenge!=challenge
        or witness.principal_id!=admission.principal_id or witness.observer_uri!=admission.observer_uri or witness.client_uri!=admission.client_uri
        or witness.sequence<=previous_sequence or not started_at<=witness.checked_at<=now<witness.expires_at
        or (now-witness.checked_at).total_seconds()>admission.max_age_seconds
        or witness.expires_at>min(admission.expires_at,expected_scope.capture_until)
        or (witness.expires_at-witness.checked_at).total_seconds()>admission.max_age_seconds):
        raise PermissionError('stale foreign replayed supervisor observation')
    if v2 and (witness.scheduler_process_sha256!=admission.scheduler_process_sha256 or witness.stop_process_sha256!=admission.stop_process_sha256):
        raise PermissionError('exact independently installed v2 producer profiles required')
    return witness

class MeetingSupervisorClientV1:
    """Fixed mTLS adapter to the independently installed observer owner."""
    def __init__(self,binding):
        from .purpose_transport import PurposeTLSBindingV2,_FixedTLSClientV2
        if type(binding) is not PurposeTLSBindingV2 or binding.timeout>5:raise PermissionError('fixed supervisor observer TLS required')
        self._client=_FixedTLSClientV2(binding)
    def fetch_current(self,challenge,*,deadline):
        import re
        if type(challenge) is not str or re.fullmatch(HASH,challenge) is None:raise PermissionError('fresh supervisor nonce required')
        import time
        from datetime import timezone
        from ._protected_control_listener_v1 import request_remaining_v1
        end=time.monotonic()+request_remaining_v1(required=True)
        if type(self) not in (MeetingSupervisorClientV1,MeetingSupervisorClientV2):raise PermissionError('fixed supervisor protocol client required')
        v2=type(self) is MeetingSupervisorClientV2
        return self._client._post('/v2/meetings/supervisor/current' if v2 else '/v1/meetings/supervisor/current',{'schema_version':2 if v2 else 1,'purpose':'meeting-supervisor-currentness-v2' if v2 else 'meeting-supervisor-currentness-v1','challenge':challenge,'caller_deadline':deadline.astimezone(timezone.utc).isoformat().replace('+00:00','Z')},16384,valid_until=deadline,_absolute_monotonic_end=float(end))

class MeetingSupervisorClientV2(MeetingSupervisorClientV1):
    def __init__(self,binding):
        if binding.timeout>2:raise PermissionError('v2 supervisor observation must fit original two-second freshness')
        super().__init__(binding)

class MeetingSupervisorConsumerV1:
    def __init__(self,*,admission,trusted_admission_hash,transport,replay):
        from .custody import DurableNonceSequenceV2
        if type(self) not in (MeetingSupervisorConsumerV1,MeetingSupervisorConsumerV2):raise PermissionError('fixed supervisor consumer owner required')
        v2=type(self) is MeetingSupervisorConsumerV2
        if (type(admission) is not (MeetingSupervisorAdmissionV2 if v2 else MeetingSupervisorAdmissionV1) or digest(admission.model_dump(mode='json'))!=trusted_admission_hash
            or type(transport) is not (MeetingSupervisorClientV2 if v2 else MeetingSupervisorClientV1) or type(replay) is not DurableNonceSequenceV2
            or replay.appointment_hash!=trusted_admission_hash or replay.minimum_sequence!=admission.minimum_sequence):
            raise PermissionError('separately installed supervisor verifier and durable replay owner required')
        self.admission=admission;self.admission_hash=trusted_admission_hash;self.transport=transport;self.replay=replay
    def current(self,scope,*,deadline):
        import time,secrets
        from datetime import timezone
        from ._protected_control_listener_v1 import request_remaining_v1
        request_remaining_v1(required=True)
        if type(scope) is not MeetingSupervisorScopeV1 or scope!=self.admission.scope:raise PermissionError('exact supervisor scope required')
        challenge=secrets.token_hex(32);self.replay.claim(challenge)
        started=datetime.now(timezone.utc);tick=time.monotonic()
        raw=self.transport.fetch_current(challenge,deadline=min(deadline,self.admission.expires_at,scope.capture_until))
        request_remaining_v1(required=True);now=datetime.now(timezone.utc)
        from .gateway import unique_object
        value=json.loads(raw,object_pairs_hook=unique_object);witness=None
        if type(value) is not dict or type(value.get('witness')) is not dict:raise PermissionError('closed supervisor witness required')
        def verify(previous):
            nonlocal witness
            witness=_verify_meeting_supervisor(raw,admission=self.admission,trusted_admission_hash=self.admission_hash,expected_scope=scope,challenge=challenge,previous_sequence=previous,started_at=started,now=now,elapsed_seconds=time.monotonic()-tick)
        self.replay.advance(challenge,value['witness'].get('sequence'),verify=verify)
        request_remaining_v1(required=True)
        return witness

class MeetingSupervisorConsumerV2(MeetingSupervisorConsumerV1):
    """Same replay/transport owner, exact independently installed V2 only."""
    pass
