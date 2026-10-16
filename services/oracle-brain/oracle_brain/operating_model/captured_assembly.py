"""Versioned complete-wire observation and model-only candidate parsing.

Observation is local complete-wire arrival before local decoding/consumption. It
is not provider creation time or a claim about unknown historical exposure.
Constructor configuration must come from an externally sealed trusted startup;
these records do not issue authority or add a signer/trust registry.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from .assembly_context import AssemblyJobContext
from .contracts import StrictRecord, canonical_bytes, digest
from .native_factory import _unique_object, _deny_constant
from .semantic_acceptance import sealed

HASH = r'^[0-9a-f]{64}$'


class ObservedAssemblyProtocol(StrictRecord):
    protocol: Literal['observed-assembly-candidate-v1'] = 'observed-assembly-candidate-v1'
    candidate_created_at_basis: Literal['complete-wire-before-local-consumer-v1'] = 'complete-wire-before-local-consumer-v1'
    provider_creation_claim: Literal[False] = False
    historical_earliest_claim: Literal[False] = False


class AssemblyObserverContext(StrictRecord):
    custodian_id: UUID
    custodian_config_hash: str = Field(pattern=HASH)
    custodian_session_hash: str = Field(pattern=HASH)
    runtime_hash: str = Field(pattern=HASH)
    census_hash: str = Field(pattern=HASH)
    protocol_hash: str = Field(pattern=HASH)
    dispatch_id: UUID
    job_hash: str = Field(pattern=HASH)
    request_hash: str = Field(pattern=HASH)
    key_fingerprint: str = Field(pattern=HASH)
    ledger_identity_hash: str = Field(pattern=HASH)
    expires_at: AwareDatetime


class ObservedAssemblyWire(StrictRecord):
    time_basis: str = Field(pattern=r'^complete-wire-before-local-consumer-v1$')
    observer_context_hash: str = Field(pattern=HASH)
    dispatch_id: UUID
    reservation_id: UUID
    job_hash: str = Field(pattern=HASH)
    request_hash: str = Field(pattern=HASH)
    raw_sha256: str = Field(pattern=HASH)
    captured_bytes: int = Field(strict=True, gt=0, le=16*1024*1024)
    observed_at: AwareDatetime


class CapturedAssemblyCandidate(StrictRecord):
    context_hash: str = Field(pattern=HASH)
    observed_wire: ObservedAssemblyWire
    candidate: dict
    candidate_hash: str = Field(pattern=HASH)
    object_evidence_hash: str = Field(pattern=HASH)


def captured_assembly_candidate(*, context: AssemblyJobContext, observer: AssemblyObserverContext,
        expected_observer_context_hash: str, protocol: ObservedAssemblyProtocol,
        expected_protocol_hash: str, observed: ObservedAssemblyWire,
        raw: bytes, now: datetime):
    """Compile-only parse of actual retained wire; never fabricate ledger metadata."""
    if type(context) is not AssemblyJobContext or type(protocol) is not ObservedAssemblyProtocol:
        raise PermissionError('legacy assembly capture cannot consume a purpose V2 context/protocol')
    if now.tzinfo is None or now.utcoffset() is None or observer.expires_at <= now:
        raise PermissionError('current externally admitted assembly observer required')
    if (not isinstance(protocol, ObservedAssemblyProtocol)
            or sealed(protocol) != expected_protocol_hash or observer.protocol_hash != expected_protocol_hash
            or sealed(observer) != expected_observer_context_hash
            or observed.observer_context_hash != expected_observer_context_hash
            or observer.runtime_hash != context.runtime_hash
            or observer.census_hash != sealed(context.census)
            or observer.dispatch_id != context.job.dispatch_id
            or observer.job_hash != sealed(context.job)
            or observer.request_hash != context.job.request_hash
            or observed.dispatch_id != observer.dispatch_id
            or observed.job_hash != observer.job_hash
            or observed.request_hash != observer.request_hash
            or not context.census.frozen_at < observed.observed_at <= now
            or observed.observed_at >= min(observer.expires_at, context.expires_at)
            or type(raw) is not bytes or len(raw) != observed.captured_bytes
            or hashlib.sha256(raw).hexdigest() != observed.raw_sha256):
        raise PermissionError('complete observed assembly wire differs from sealed context')
    content=_observed_model_content(raw,context.job.request['model'])
    payload, evidence = context.validate_candidate(content, now=now)
    # This stable pre-assessment packet binds full wire provenance as well as
    # extracted model content. Coverage is added only after independent admission.
    payload['assembly_capture'] = {
        'observer_context_hash': expected_observer_context_hash,
        'protocol':protocol.model_dump(mode='json'),
        'protocol_hash':expected_protocol_hash,
        'observed_wire': observed.model_dump(mode='json'),
        'assembly_context_hash': sealed(context),
        'compiler_digest':context.compiler_digest,
        'extractions': [{k: e.manifest.model_dump(mode='json')[k] for k in (
            'artifact_id','version','content_hash','input_digest','source_digest',
            'permission_digest','compiler_digest')} | {'manifest_hash':sealed(e.manifest)}
            for e in context.extractions],
    }
    return CapturedAssemblyCandidate(context_hash=sealed(context), observed_wire=observed,
        candidate=payload, candidate_hash=digest(payload), object_evidence_hash=digest({
            k: [e.model_dump(mode='json') for e in v] for k,v in evidence.items()})), evidence


def _observed_model_content(raw,model):
    envelope = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                          parse_constant=_deny_constant)
    if not isinstance(envelope, dict) or envelope.get('model') != model:
        raise PermissionError('captured provider model differs from assembly context')
    choices = envelope.get('choices')
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ValueError('captured assembly requires exactly one complete choice')
    choice = choices[0]
    message = choice.get('message')
    if (choice.get('finish_reason') != 'stop' or choice.get('index') != 0
            or not isinstance(message, dict) or message.get('role') != 'assistant'
            or message.get('tool_calls') or message.get('refusal')
            or not isinstance(message.get('content'), str)):
        raise ValueError('captured assembly is incomplete or not model-only content')
    return message['content']


class ObservedAssemblyCustodian:
    """Protected-startup-only observer, not an authority issued by its fields.

    Actual identity arguments must originate in the trusted admitted runtime,
    separately from loaded context. Never accept this object/config via HTTP.
    """
    def __init__(self, *, context, expected_context_hash, protocol, expected_protocol_hash,
                 actual_custodian_id, actual_config_hash, actual_session_hash, actual_runtime_hash):
        self.context=context
        self.expected_context_hash=expected_context_hash
        self.protocol=protocol
        self.expected_protocol_hash=expected_protocol_hash
        self._identity=(actual_custodian_id,actual_config_hash,actual_session_hash,actual_runtime_hash)
        self._check_identity()

    def _check_identity(self):
        c=self.context
        if (not isinstance(c,AssemblyObserverContext) or sealed(c)!=self.expected_context_hash
                or not isinstance(self.protocol,ObservedAssemblyProtocol)
                or sealed(self.protocol)!=self.expected_protocol_hash or c.protocol_hash!=self.expected_protocol_hash
                or self._identity!=(c.custodian_id,c.custodian_config_hash,c.custodian_session_hash,c.runtime_hash)):
            raise PermissionError('actual protected-startup custodian/session/protocol differs')

    def validate_job(self, job, *, key_fingerprint, ledger_identity_hash, now):
        self._check_identity()
        c=self.context
        if (now.tzinfo is None or now.utcoffset() is None or c.expires_at<=now
                or job.purpose!='operating-audit' or c.dispatch_id!=job.dispatch_id
                or c.job_hash!=sealed(job) or c.request_hash!=job.request_hash
                or c.key_fingerprint!=key_fingerprint or c.ledger_identity_hash!=ledger_identity_hash):
            raise PermissionError('current exact assembly observation context unavailable')

    def observe(self, job, raw, reservation_id, *, key_fingerprint, ledger_identity_hash):
        # Deliberately no caller timestamp/clock parameter. This runs at the paid
        # complete-wire callback before UTF8 decoding or the model consumer.
        observed_at=datetime.now(timezone.utc)
        self.validate_job(job,key_fingerprint=key_fingerprint,ledger_identity_hash=ledger_identity_hash,now=observed_at)
        return ObservedAssemblyWire(time_basis='complete-wire-before-local-consumer-v1',
            observer_context_hash=self.expected_context_hash,dispatch_id=job.dispatch_id,
            reservation_id=reservation_id,job_hash=sealed(job),request_hash=job.request_hash,
            raw_sha256=hashlib.sha256(raw).hexdigest(),captured_bytes=len(raw),observed_at=observed_at)

    @staticmethod
    def retain(directory, observed):
        path=Path(directory)/(str(observed.dispatch_id)+'.observed-wire.json')
        data=canonical_bytes(observed.model_dump(mode='json'))
        descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        descriptor=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
        if path.read_bytes()!=data:
            raise PermissionError('durable observed assembly metadata readback failed')
