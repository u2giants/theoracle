"""Separate-current-actor assembly inputs; historical extraction seals stay exact.

Handoff records do not appoint their compiler. A protected independently reviewed
phase registry must bind their exact hashes after actual compiler-role reads.
Legacy AssemblyJobContext and extraction permission semantics are unchanged.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,model_validator

from .assembly_context import SealedAssemblyExtraction,assembly_messages
from .contracts import StrictRecord,digest
from .native_factory import NativeDispatchJob
from .pipeline import assembly_inputs,assembly_candidate_payload
from .purpose_context import HASH,LOGIN
from .semantic_acceptance import FrozenCensus,sealed
from .source_receipts import SourceReceipt,SourceRef


class CompilerExtractionHandoffV2(StrictRecord):
    schema_version: Literal[2]=2
    purpose: Literal['compiler-extraction-handoff-v2']='compiler-extraction-handoff-v2'
    workspace_id: UUID
    compiler_actor: UUID
    compiler_login: str=Field(pattern=LOGIN)
    compiler_runtime_hash: str=Field(pattern=HASH)
    compiler_authority_receipt_hash: str=Field(pattern=HASH)
    source_registry_hash: str=Field(pattern=HASH)
    source_refs: tuple[SourceRef,...]=Field(min_length=2)
    extractions: tuple[SealedAssemblyExtraction,...]=Field(min_length=2)
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode='after')
    def exact_historical_seals(self):
        refs,_,_=assembly_inputs(tuple(e.payload for e in self.extractions),enforce_unique_sources=True)
        if (tuple(refs)!=self.source_refs or len({r.source_id for r in refs})!=len(refs)
                or any(r.workspace_id!=self.workspace_id for r in refs)
                or any(e.manifest.kind!='processing_extraction_v1' for e in self.extractions)
                or len({(e.manifest.artifact_id,e.manifest.version) for e in self.extractions})!=len(self.extractions)
                or self.issued_at>=self.expires_at):
            raise PermissionError('exact current compiler handoff of immutable reported extractions required')
        return self


def compiler_extraction_handoff_v2(ledger,*,workspace_id,extraction_ids,source_refs,
        compiler_authority_receipt_hash,now,expires_at):
    """Read under actual existing compiler authority, never issue an appointment.

    The resulting exact record must subsequently be independently bound by the
    external assembly phase registry; accepting the dataclass alone is forbidden.
    No provider work or SQL lock spans private blob reads.
    """
    import psycopg
    from .processing_ledger import require_explicit_compiler_ledger_v3
    require_explicit_compiler_ledger_v3(ledger)
    resolver=ledger.processing_sources;binding=resolver.binding
    if binding.profile!='candidate-compiler' or ledger.principal!=binding.principal:
        raise PermissionError('current compiler principal/profile required')
    pairs=[]
    for artifact_id,version in extraction_ids:
        manifest,payload=ledger.read_with_manifest(workspace_id,artifact_id,version)
        pairs.append(SealedAssemblyExtraction(manifest=manifest,payload=payload))
    # Re-read each current artifact's metadata after ALL private reads.
    for extraction in pairs:
        current,refs=resolver.artifact_metadata(workspace_id,extraction.manifest.artifact_id,extraction.manifest.version)
        if current!=extraction.manifest:
            raise PermissionError('compiler extraction changed during handoff')
    with psycopg.connect(ledger.url) as conn:
        resolver._check(conn)
        actual=conn.execute('SELECT session_user,clock_timestamp()').fetchone()
        if actual[0]!=binding.expected_session_role or actual[1]>=min(binding.expires_at,expires_at):
            raise PermissionError('compiler actual login or current handoff horizon unavailable')
    return CompilerExtractionHandoffV2(workspace_id=workspace_id,compiler_actor=ledger.principal,
        compiler_login=actual[0],compiler_runtime_hash=binding.runtime_hash,
        compiler_authority_receipt_hash=compiler_authority_receipt_hash,
        source_registry_hash=binding.source_registry_hash,source_refs=source_refs,
        extractions=tuple(pairs),issued_at=actual[1],expires_at=min(expires_at,binding.expires_at))


class AssemblyJobContextV2(StrictRecord):
    schema_version: Literal[2]=2
    context_schema: Literal['purpose-assembly-context-v2']='purpose-assembly-context-v2'
    actor_id: UUID
    provider_login: str=Field(pattern=LOGIN)
    runtime_hash: str=Field(pattern=HASH)
    source_registry_hash: str=Field(pattern=HASH)
    compiler_digest: str=Field(pattern=HASH)
    parent_registry_hash: str=Field(pattern=HASH)
    expected_handoff_hash: str=Field(pattern=HASH)
    job: NativeDispatchJob
    receipts: tuple[SourceReceipt,...]=Field(min_length=2)
    handoff: CompilerExtractionHandoffV2
    census: FrozenCensus
    reviewed_inventories: dict
    model_id: UUID
    model_version: int=Field(strict=True,ge=1)
    expires_at: AwareDatetime

    @property
    def extractions(self):return self.handoff.extractions

    @model_validator(mode='after')
    def separated_authority(self):
        import json
        refs=tuple(r.ref for r in self.receipts)
        if (sealed(self.handoff)!=self.expected_handoff_hash
                or self.handoff.source_refs!=refs or self.census.source_refs!=refs
                or self.handoff.workspace_id!=self.job.workspace_id
                or self.handoff.source_registry_hash!=self.source_registry_hash
                or self.job.artifact_id!=self.model_id or self.job.purpose!='operating-audit'
                or self.job.processing_request.purpose!='operating-audit'
                or self.job.request.get('model')!='openai/gpt-6.1-sol'
                or self.job.pricing.model!='openai/gpt-6.1-sol'
                or self.job.pricing.provider!=self.job.processing_request.provider
                or self.job.pricing.admitted_register_hash!=self.job.register_hash
                or set(self.job.request)!={'model','messages','max_tokens','response_format','store','stream','provider'}
                or self.expires_at>self.handoff.expires_at
                or any(e.manifest.artifact_id==self.model_id for e in self.extractions)):
            raise PermissionError('separately qualified current assembly and historical compiler handoff required')
        expected=assembly_messages(receipts=self.receipts,extractions=self.extractions,
            census=self.census,model_id=self.model_id,version=self.model_version)
        if self.job.request.get('messages')!=expected or digest(self.job.request)!=self.job.request_hash:
            raise PermissionError('assembly V2 request differs from complete immutable source inputs')
        # Historical extraction permission hashes are immutable evidence. They
        # deliberately need not equal this different current actor's permission.
        return self

    def validate_candidate(self,raw,*,now:datetime):
        from oracle_brain.provider_policy import authorize
        type(self).model_validate(self.model_dump(mode='python'))
        approval=authorize(self.job.processing_request,list(self.job.approvals),now=now)
        if (now.tzinfo is None or now.utcoffset() is None or now>=self.expires_at
                or self.expires_at>min(approval.expires_at,self.job.pricing.expires_at)):
            raise PermissionError('current independent assembly phase qualification required')
        refs,observations,findings=assembly_inputs(tuple(e.payload for e in self.extractions),enforce_unique_sources=True)
        payload,evidence=assembly_candidate_payload(raw,workspace_id=self.job.workspace_id,
            refs=refs,observations=observations,findings=findings)
        model=payload['operating_models'][0]
        if model['model_id']!=str(self.model_id) or model['version']!=self.model_version:
            raise PermissionError('V2 assembly output identity differs from sealed new model intent')
        return payload,evidence
