"""Explicit V2 phase capture protocol; never reinterprets legacy observations."""
from datetime import datetime,timezone
import hashlib
from typing import Literal
from uuid import UUID
from pydantic import Field,AwareDatetime
from .contracts import StrictRecord,digest
from .captured_assembly import (
    AssemblyObserverContext,ObservedAssemblyCustodian,_observed_model_content)
from .purpose_assembly_v2 import AssemblyJobContextV2,ConsolidationAssemblyJobContextV1
from .semantic_acceptance import sealed
from .purpose_context import HASH


class ObservedAssemblyProtocolV2(StrictRecord):
    protocol: Literal['observed-assembly-candidate-v2']='observed-assembly-candidate-v2'
    context_schema: Literal['purpose-assembly-context-v2']='purpose-assembly-context-v2'
    candidate_schema: Literal['purpose-captured-assembly-v2']='purpose-captured-assembly-v2'
    candidate_created_at_basis: Literal['complete-wire-before-local-consumer-v2']='complete-wire-before-local-consumer-v2'
    provider_creation_claim: Literal[False]=False
    historical_earliest_claim: Literal[False]=False


class AssemblyObserverContextV2(AssemblyObserverContext):
    schema_version: Literal[2]=2
    assembly_context_hash: str=Field(pattern=HASH)
    handoff_hash: str=Field(pattern=HASH)


class ObservedAssemblyWireV2(StrictRecord):
    schema_version: Literal[2]=2
    time_basis: Literal['complete-wire-before-local-consumer-v2']='complete-wire-before-local-consumer-v2'
    observer_context_hash: str=Field(pattern=HASH)
    assembly_context_hash: str=Field(pattern=HASH)
    handoff_hash: str=Field(pattern=HASH)
    dispatch_id: UUID
    reservation_id: UUID
    job_hash: str=Field(pattern=HASH)
    request_hash: str=Field(pattern=HASH)
    raw_sha256: str=Field(pattern=HASH)
    captured_bytes: int=Field(strict=True,gt=0,le=16*1024*1024)
    observed_at: AwareDatetime


class CapturedAssemblyCandidateV2(StrictRecord):
    schema_version: Literal[2]=2
    candidate_schema: Literal['purpose-captured-assembly-v2']='purpose-captured-assembly-v2'
    context_hash: str=Field(pattern=HASH)
    handoff_hash: str=Field(pattern=HASH)
    observed_wire: ObservedAssemblyWireV2
    candidate: dict
    candidate_hash: str=Field(pattern=HASH)
    object_evidence_hash: str=Field(pattern=HASH)


class ObservedConsolidationProtocolV1(ObservedAssemblyProtocolV2):
    protocol: Literal['observed-consolidation-candidate-v1']='observed-consolidation-candidate-v1'
    context_schema: Literal['purpose-consolidation-context-v1']='purpose-consolidation-context-v1'
    candidate_schema: Literal['purpose-captured-consolidation-v1']='purpose-captured-consolidation-v1'


class CapturedConsolidationCandidateV1(CapturedAssemblyCandidateV2):
    candidate_schema: Literal['purpose-captured-consolidation-v1']='purpose-captured-consolidation-v1'


def _capture_types(context,protocol):
    return ((type(context) is AssemblyJobContextV2 and type(protocol) is ObservedAssemblyProtocolV2)
        or (type(context) is ConsolidationAssemblyJobContextV1 and type(protocol) is ObservedConsolidationProtocolV1))


class ObservedAssemblyCustodianV2(ObservedAssemblyCustodian):
    def _check_identity(self):
        c=self.context
        if (type(c) is not AssemblyObserverContextV2 or sealed(c)!=self.expected_context_hash
                or type(self.protocol) not in {ObservedAssemblyProtocolV2,ObservedConsolidationProtocolV1}
                or sealed(self.protocol)!=self.expected_protocol_hash or c.protocol_hash!=self.expected_protocol_hash
                or self._identity!=(c.custodian_id,c.custodian_config_hash,c.custodian_session_hash,c.runtime_hash)):
            raise PermissionError('actual V2 protected custodian/session/protocol differs')

    def observe(self,job,raw,reservation_id,*,key_fingerprint,ledger_identity_hash):
        observed_at=datetime.now(timezone.utc)
        self.validate_job(job,key_fingerprint=key_fingerprint,ledger_identity_hash=ledger_identity_hash,now=observed_at)
        return ObservedAssemblyWireV2(observer_context_hash=self.expected_context_hash,
            assembly_context_hash=self.context.assembly_context_hash,handoff_hash=self.context.handoff_hash,
            dispatch_id=job.dispatch_id,reservation_id=reservation_id,job_hash=sealed(job),request_hash=job.request_hash,
            raw_sha256=hashlib.sha256(raw).hexdigest(),captured_bytes=len(raw),observed_at=observed_at)


def captured_assembly_candidate_v2(*,context,observer,expected_observer_context_hash,
        protocol,expected_protocol_hash,observed,raw,now):
    if (not _capture_types(context,protocol) or type(observer) is not AssemblyObserverContextV2 or type(observed) is not ObservedAssemblyWireV2
            or now.tzinfo is None or now.utcoffset() is None or now>=min(context.expires_at,observer.expires_at)
            or sealed(observer)!=expected_observer_context_hash or sealed(protocol)!=expected_protocol_hash
            or observer.protocol_hash!=expected_protocol_hash or observer.runtime_hash!=context.runtime_hash
            or observer.census_hash!=sealed(context.census)
            or observer.assembly_context_hash!=sealed(context) or observer.handoff_hash!=sealed(context.handoff)
            or observed.assembly_context_hash!=sealed(context) or observed.handoff_hash!=sealed(context.handoff)
            or observer.dispatch_id!=context.job.dispatch_id or observer.job_hash!=sealed(context.job)
            or observer.request_hash!=context.job.request_hash or observed.observer_context_hash!=expected_observer_context_hash
            or observed.dispatch_id!=observer.dispatch_id or observed.job_hash!=observer.job_hash
            or observed.request_hash!=observer.request_hash
            or not context.census.frozen_at<observed.observed_at<=now
            or observed.observed_at>=min(observer.expires_at,context.expires_at)
            or type(raw) is not bytes or len(raw)!=observed.captured_bytes
            or hashlib.sha256(raw).hexdigest()!=observed.raw_sha256):
        raise PermissionError('complete V2 wire/context/handoff differs from external qualification')
    payload,evidence=context.validate_candidate(_observed_model_content(raw,context.job.request['model']),now=now)
    payload['assembly_capture']={'candidate_schema':protocol.candidate_schema,'context_schema':protocol.context_schema,
        'observer_context_hash':expected_observer_context_hash,'protocol':protocol.model_dump(mode='json'),
        'protocol_hash':expected_protocol_hash,'observed_wire':observed.model_dump(mode='json'),
        'assembly_context_hash':sealed(context),'handoff_hash':sealed(context.handoff),
        'compiler_digest':context.compiler_digest,
        'extractions':[{k:e.manifest.model_dump(mode='json')[k] for k in (
            'artifact_id','version','content_hash','input_digest','source_digest','permission_digest','compiler_digest')}
            |{'manifest_hash':sealed(e.manifest)} for e in context.extractions]}
    captured_type=CapturedConsolidationCandidateV1 if type(context) is ConsolidationAssemblyJobContextV1 else CapturedAssemblyCandidateV2
    return captured_type(context_hash=sealed(context),handoff_hash=sealed(context.handoff),
        observed_wire=observed,candidate=payload,candidate_hash=digest(payload),
        object_evidence_hash=digest({k:[e.model_dump(mode='json') for e in v] for k,v in evidence.items()})),evidence


from .native_factory import _ObservedAssemblyBrokerBase


class ObservedPurposeAssemblyBrokerEgress(_ObservedAssemblyBrokerBase):
    """Exact V2 startup protocol; retained paid-wire capture precedes parsing."""
    @staticmethod
    def _validate_context_types(context,observer):
        if (type(observer) is not ObservedAssemblyCustodianV2 or not _capture_types(context,observer.protocol)
                or observer.context.assembly_context_hash!=sealed(context)
                or observer.context.handoff_hash!=sealed(context.handoff)):
            raise PermissionError('exact separately admitted V2 assembly/custodian context required')
