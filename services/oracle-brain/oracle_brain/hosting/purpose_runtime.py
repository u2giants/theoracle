"""Fixed V2 purpose loading; no parent originals or sibling phase configuration.

Every currentness observation is externally appointed, every SQL capability is
bound to this caller, and every operation is qualified by protected phase bytes.
This module consumes those admissions; it never issues grants, trust or budget.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
import json
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field,AwareDatetime,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.purpose_context import (
    HASH,WORKER,LOGIN,PurposePinsV2,BudgetAllocationPinsV2,ParentPopulationAdmissionV2,PurposePhaseRegistryV2,
    PurposeMetadataProjectionV2,derive_purpose_descriptor_v2,verify_purpose_authority_proof_v2)
from oracle_brain.operating_model.purpose_profiles_v2 import PurposePrivateContextV2
from oracle_brain.operating_model.authority_adapter import (
    ProcessingSourceBinding,PurposeSourceBindingV2,PurposeSourceResolverV2)
from .parent_observer_v2 import ParentObserverAdmissionV2,ParentCurrentnessConsumerV2
from .custody import DurableNonceSequenceV2
from .provider_runtime import pinned,tls_url,signed_coverage
from .runtime import protected_file
from .gateway import unique_object


def _typed(path,seal,model):
    raw=pinned(path,seal)
    value=json.loads(raw,object_pairs_hook=unique_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite purpose input')))
    return model.model_validate_json(canonical_bytes(value))


class PurposeCommonConfigV2(StrictRecord):
    schema_version: Literal[2]=2
    phase: Literal['census','assembly','assessment','embedding']
    role: Literal['provider','metadata']
    worker_uri: str=Field(pattern=WORKER)
    pins_file: str
    budget_allocation_projection_file: str
    pins_sha256: str=Field(pattern=HASH)
    population_file: str
    projection_file: str
    source_url_file: str
    expected_owner_role: str=Field(pattern=LOGIN)
    expected_session_role: str=Field(pattern=LOGIN)
    source_expires_at: AwareDatetime
    parent_observer_admission_file: str
    parent_observer_admission_hash: str=Field(pattern=HASH)
    observer_hostname: str
    observer_port: int=Field(strict=True,ge=1,le=65535)
    observer_server_uri: str=Field(pattern=WORKER)
    observer_client_uri: str=Field(pattern=WORKER)
    observer_ca: str
    observer_certificate: str
    observer_key: str
    observer_spool: str
    observer_namespace: str
    observer_initialization_hash: str=Field(pattern=HASH)
    server_certificate: str
    server_key: str
    client_ca: str
    bind_host: Literal['127.0.0.1','0.0.0.0']
    bind_port: int=Field(strict=True,ge=1,le=65535)


class PurposeProviderConfigV2(PurposeCommonConfigV2):
    role: Literal['provider']='provider'
    phase_registry_file: str
    private_context_files: dict[UUID,str]
    provider_key_file: str
    ledger_url_file: str
    ledger_registry_file: str
    ledger_registry_hash: str=Field(pattern=HASH)
    coverage_admission_file: str
    coverage_admission_hash: str=Field(pattern=HASH)
    coverage_witness_file: str
    coverage_observer_public_key: str=Field(pattern=HASH)
    private_receipts: str
    # Assembly's preparse observer is separately admitted; never inferred.
    assembly_observer_file: str|None=None
    assembly_observer_hash: str|None=Field(default=None,pattern=HASH)
    assembly_protocol_file: str|None=None
    assembly_protocol_hash: str|None=Field(default=None,pattern=HASH)
    actual_custodian_id: UUID|None=None
    actual_custodian_config_hash: str|None=Field(default=None,pattern=HASH)
    actual_custodian_session_hash: str|None=Field(default=None,pattern=HASH)


class PurposeMetadataConfigV2(PurposeCommonConfigV2):
    role: Literal['metadata']='metadata'
    provider_hostname: str
    provider_port: int=Field(strict=True,ge=1,le=65535)
    provider_server_uri: str=Field(pattern=WORKER)
    provider_client_uri: str=Field(pattern=WORKER)
    provider_ca: str
    provider_certificate: str
    provider_key: str

    @model_validator(mode='after')
    def no_embedding_gateway(self):
        if self.phase=='embedding':
            raise PermissionError('embedding provider itself is metadata-only; no gateway impersonation')
        return self


@dataclass(frozen=True)
class PurposeRuntimeSettingsV2:
    config: PurposeProviderConfigV2|PurposeMetadataConfigV2
    pins: PurposePinsV2
    population: ParentPopulationAdmissionV2
    projection: PurposeMetadataProjectionV2
    resolver: PurposeSourceResolverV2
    observer: ParentCurrentnessConsumerV2

    @property
    def phase(self):return self.config.phase
    @property
    def role(self):return self.config.role
    @property
    def worker_uri(self):return self.config.worker_uri
    @property
    def server_certificate(self):return Path(self.config.server_certificate)
    @property
    def server_key(self):return Path(self.config.server_key)
    @property
    def client_ca(self):return Path(self.config.client_ca)
    @property
    def bind_host(self):return self.config.bind_host
    @property
    def bind_port(self):return self.config.bind_port


def load_purpose_runtime_settings_v2(config_path,trusted_config_sha256,*,expected_phase,expected_role):
    """Protected fixed startup only. No dynamic class/callback or HTTP selector."""
    from .purpose_transport import PurposeTLSBindingV2,ParentObserverClientV2
    raw=pinned(config_path,trusted_config_sha256)
    value=json.loads(raw,object_pairs_hook=unique_object)
    model=PurposeProviderConfigV2 if expected_role=='provider' else PurposeMetadataConfigV2
    if expected_role not in {'provider','metadata'}:
        raise PermissionError('fixed purpose startup role required')
    config=model.model_validate_json(canonical_bytes(value))
    if config.phase!=expected_phase or config.role!=expected_role:
        raise PermissionError('protected startup phase/role differs')
    pins=_typed(config.pins_file,config.pins_sha256,PurposePinsV2)
    population=_typed(config.population_file,pins.population_admission_sha256,ParentPopulationAdmissionV2)
    projection=_typed(config.projection_file,pins.projection_sha256,PurposeMetadataProjectionV2)
    d=projection.descriptor
    now=datetime.now(timezone.utc)
    allocation=_typed(config.budget_allocation_projection_file,
        pins.budget_allocation_projection_sha256,BudgetAllocationPinsV2)
    allocation.verify_current(trusted_projection_hash=pins.budget_allocation_projection_sha256,
        dispatches=d.dispatches,now=now)
    if now>=min(pins.expires_at,population.expires_at,d.expires_at,config.source_expires_at,
                allocation.original_expires_at):
        raise PermissionError('own operation appointment expired before observer or private access')
    if (d.phase!=config.phase or d.phase!=pins.phase or d.provider_login!=pins.provider_login
            or d.worker_uri!=pins.worker_uri or config.worker_uri!=pins.worker_uri or d.source_refs!=population.source_refs
            or d.parent_registry_sha256!=population.parent_registry_sha256
            or digest(d.model_dump(mode='json'))!=pins.descriptor_sha256
            or d.population_admission_sha256!=pins.population_admission_sha256
            or config.source_expires_at>d.expires_at):
        raise PermissionError('exact externally admitted phase metadata required')
    source=ProcessingSourceBinding(runtime_hash=d.runtime_hash,source_registry_hash=d.source_registry_hash,
        expected_owner_role=config.expected_owner_role,expected_session_role=config.expected_session_role,
        principal=d.actor_id,profile='gateway-metadata' if config.role=='metadata' or d.operation=='embedding' else 'source-reader',
        expires_at=config.source_expires_at)
    binding=PurposeSourceBindingV2(source=source,phase=d.phase,purpose=d.purpose,operation=d.operation,
        expected_provider_login=d.provider_login,caller_kind='provider' if config.role=='provider' else 'gateway',
        source_refs=d.source_refs,population_digest=d.population_digest,descriptor_sha256=pins.descriptor_sha256,
        parent_registry_sha256=d.parent_registry_sha256,population_admission_sha256=d.population_admission_sha256,
        phase_registry_sha256=d.phase_registry_sha256,projection_sha256=pins.projection_sha256)
    resolver=PurposeSourceResolverV2(tls_url(config.source_url_file),binding=binding)
    admission=_typed(config.parent_observer_admission_file,config.parent_observer_admission_hash,ParentObserverAdmissionV2)
    if (admission.population!=population or admission.principal_id!=d.actor_id
            or admission.observer_uri!=config.observer_server_uri or admission.client_uri!=config.observer_client_uri):
        raise PermissionError('separately appointed actual observer/client differs')
    transport=ParentObserverClientV2(PurposeTLSBindingV2(hostname=config.observer_hostname,port=config.observer_port,
        server_uri=config.observer_server_uri,client_uri=config.observer_client_uri,
        ca_file=Path(config.observer_ca),certificate_file=Path(config.observer_certificate),key_file=Path(config.observer_key)))
    replay=DurableNonceSequenceV2(config.observer_spool,namespace=config.observer_namespace,
        appointment_hash=config.parent_observer_admission_hash,minimum_sequence=admission.minimum_sequence,
        initialization_receipt_hash=config.observer_initialization_hash)
    observer=ParentCurrentnessConsumerV2(admission=admission,trusted_admission_hash=config.parent_observer_admission_hash,
        transport=transport,replay=replay)
    return PurposeRuntimeSettingsV2(config,pins,population,projection,resolver,observer)


class CurrentPurposeJobsV2:
    """Own phase only: no CurrentJobs parent loader, path or sibling context."""
    def __init__(self,settings):
        if type(settings) is not PurposeRuntimeSettingsV2 or type(settings.resolver) is not PurposeSourceResolverV2:
            raise PermissionError('actual fixed purpose runtime settings required')
        self.settings=settings

    def metadata(self,dispatch_id):
        s=self.settings;d=s.projection.descriptor;j=d.dispatch(dispatch_id)
        now=datetime.now(timezone.utc)
        if _typed(s.config.pins_file,s.config.pins_sha256,PurposePinsV2)!=s.pins:
            raise PermissionError('protected operation pins changed without external admission')
        allocation=_typed(s.config.budget_allocation_projection_file,
            s.pins.budget_allocation_projection_sha256,BudgetAllocationPinsV2)
        allocation.verify_current(trusted_projection_hash=s.pins.budget_allocation_projection_sha256,
            dispatches=d.dispatches,now=now)
        if now>=min(s.pins.expires_at,s.population.expires_at,d.expires_at,
                    s.config.source_expires_at,allocation.original_expires_at):
            raise PermissionError('own operation appointment expired before observer or forwarding')
        # Reload sealed metadata so a changed mount cannot inherit a cached grant.
        if (_typed(s.config.population_file,s.pins.population_admission_sha256,ParentPopulationAdmissionV2)!=s.population
                or _typed(s.config.projection_file,s.pins.projection_sha256,PurposeMetadataProjectionV2)!=s.projection):
            raise PermissionError('complete parent metadata changed')
        s.observer.current(s.population)
        return d,j

    def context(self,dispatch_id):
        s=self.settings
        if type(s.config) is not PurposeProviderConfigV2:
            raise PermissionError('metadata runtime cannot open private phase files')
        d,j=self.metadata(dispatch_id)
        with s.resolver.hold(d,j) as proof:
            verify_purpose_authority_proof_v2(proof,d,j,projection_sha256=s.pins.projection_sha256,
                actual_caller_login=s.config.expected_session_role,profile=s.resolver.binding.source.profile,
                now=datetime.now(timezone.utc))
            # ALL externally admitted sources were checked before the first body.
            registry=_typed(s.config.phase_registry_file,s.pins.phase_registry_sha256,PurposePhaseRegistryV2)
            derived=derive_purpose_descriptor_v2(registry,s.population,pins=s.pins,
                phase_registry_bytes_hash=s.pins.phase_registry_sha256,now=datetime.now(timezone.utc))
            if derived!=d or set(s.config.private_context_files)!={x.dispatch_id for x in d.dispatches}:
                raise PermissionError('private registry/dispatch population differs')
            raw=protected_file(s.config.private_context_files[dispatch_id],limit=2_000_000)
            value=json.loads(raw,object_pairs_hook=unique_object)
            ctx=PurposePrivateContextV2.model_validate_json(canonical_bytes(value))
            if digest(ctx.model_dump(mode='json'))!=j.context_hash:
                raise PermissionError('private phase context differs from operation qualification')
            ctx.validate_current(d,j,now=datetime.now(timezone.utc))
        s.observer.current(s.population)
        return ctx

    def resolve(self,dispatch_id):return self.context(dispatch_id).job

    def authorize(self,job):
        current=self.resolve(job.dispatch_id)
        if current!=job:raise PermissionError('current purpose job changed')
        return True

    def validate(self,job,response):
        ctx=self.context(job.dispatch_id);d=self.settings.projection.descriptor;j=d.dispatch(job.dispatch_id)
        if ctx.job!=job:raise PermissionError('response job differs from current exact phase')
        ctx.validate_response(response,d,j,now=datetime.now(timezone.utc))
        self.authorize(job)


class PurposeBrokerIngressV2:
    """Metadata-only mTLS ingress; existing broker keeps complete private wire."""
    def __init__(self,settings):
        if type(settings) is not PurposeRuntimeSettingsV2 or type(settings.config) is not PurposeProviderConfigV2:
            raise PermissionError('fixed private provider startup required')
        self.settings=settings;self.jobs=CurrentPurposeJobsV2(settings)

    def dispatch(self,peer_uri,request):
        s=self.settings
        if (peer_uri!=s.worker_uri or type(request) is not dict
                or set(request)!={'dispatch_id','request_hash','phase_registry_sha256'}
                or not isinstance(request['dispatch_id'],str)
                or str(UUID(request['dispatch_id']))!=request['dispatch_id']
                or request['phase_registry_sha256']!=s.pins.phase_registry_sha256):
            raise PermissionError('fixed peer and opaque phase dispatch required')
        ctx=self.jobs.context(UUID(request['dispatch_id']))
        if request['request_hash']!=ctx.job.request_hash:
            raise PermissionError('request differs from independently qualified native phase')
        broker=_native_phase_broker_v2(s,self.jobs,ctx)
        # Complete response bytes NEVER enter the gateway reply or result cache.
        broker.dispatch(canonical_bytes({'dispatch_id':request['dispatch_id'],
            'request_hash':request['request_hash'],'request':ctx.job.request}))
        self.jobs.authorize(ctx.job)
        record=json.loads(protected_file(Path(s.config.private_receipts)/(request['dispatch_id']+'.json'),
            limit=20*1024*1024),object_pairs_hook=unique_object)
        if (record.get('failed') is not False or record.get('request_hash')!=ctx.job.request_hash
                or record.get('job_hash')!=digest(ctx.job.model_dump(mode='json'))
                or not isinstance(record.get('raw_response_hash'),str)):
            raise PermissionError('exact successfully committed private phase receipt required')
        committed=_commit_phase_response_v2(s,ctx,record)
        return {**request,'raw_response_hash':record['raw_response_hash'],
                'receipt_hash':digest(committed.model_dump(mode='json'))}


def _commit_phase_response_v2(settings,context,record):
    """No network under SQL hold; failed guards leave custody, no SUCCESS record."""
    import os
    from uuid import uuid4
    from oracle_brain.operating_model.purpose_receipts_v2 import PhaseResponseCommitV2
    from .custody import _durable_nonce,_sync_spool
    s=settings;d=s.projection.descriptor;j=d.dispatch(context.job.dispatch_id)
    # Actual complete-parent fresh challenge happens before, never inside SQL.
    witness=s.observer.current(s.population)
    allocation=_typed(s.config.budget_allocation_projection_file,
        s.pins.budget_allocation_projection_sha256,BudgetAllocationPinsV2)
    allocation.verify_current(trusted_projection_hash=s.pins.budget_allocation_projection_sha256,
        dispatches=d.dispatches,now=datetime.now(timezone.utc))
    directory=Path(s.config.private_receipts)
    pending=directory/(str(j.dispatch_id)+'.phase-pending-'+uuid4().hex+'.json')
    success=directory/(str(j.dispatch_id)+'.phase-commit.json')
    created=False;owned_inode=None
    try:
        with s.resolver.hold(d,j) as proof:
            now=datetime.now(timezone.utc)
            verify_purpose_authority_proof_v2(proof,d,j,projection_sha256=s.pins.projection_sha256,
                actual_caller_login=s.config.expected_session_role,profile=s.resolver.binding.source.profile,now=now)
            until=min(proof.expires_at,witness.expires_at,allocation.original_expires_at,s.pins.expires_at,
                      s.population.expires_at,d.expires_at,s.config.source_expires_at)
            committed=PhaseResponseCommitV2(phase=d.phase,operation=d.operation,processing_purpose=d.purpose,
                dispatch_id=j.dispatch_id,workspace_id=d.workspace_id,actor_id=d.actor_id,
                provider_login=d.provider_login,actual_caller_login=proof.actual_caller_login,
                runtime_hash=d.runtime_hash,descriptor_hash=s.pins.descriptor_sha256,
                operation_approval_hash=s.pins.operation_approval_hash,population_digest=d.population_digest,
                source_refs=d.source_refs,job_hash=j.job_hash,request_hash=j.request_hash,permission_hash=j.permission_hash,
                budget_identity_hash=j.budget_identity_hash,raw_response_hash=record['raw_response_hash'],
                native_custody_receipt_hash=digest(record),committed_at=now,valid_until=until,
                context_hash=j.context_hash,parent_registry_hash=d.parent_registry_sha256,
                current_proof_hash=digest(proof.model_dump(mode='json')),
                parent_witness_hash=digest(witness.model_dump(mode='json')),
                account_policy_hash=j.account_policy_hash,model=j.model)
            _durable_nonce(directory,pending.name,canonical_bytes(committed.model_dump(mode='json')))
            info=pending.lstat();owned_inode=(info.st_dev,info.st_ino)
            if datetime.now(timezone.utc)>=until:
                raise PermissionError('phase authorization expired before bounded final commit')
            # link is exclusive: a replay never overwrites an existing success.
            os.link(pending,success,follow_symlinks=False);created=True;_sync_spool(directory)
        # SQL hold's actual current-source/role/clock recheck completed. No success
        # may escape when post-write guards refuse; preserve failed custody below.
        if datetime.now(timezone.utc)>=until:
            raise PermissionError('phase authorization expired before response handoff')
        pending.unlink();_sync_spool(directory)
        return committed
    except BaseException:
        if created and success.exists() and (success.lstat().st_dev,success.lstat().st_ino)==owned_inode:
            # Only this invocation's exclusive link, never another attempt's file.
            os.unlink(success);_sync_spool(directory)
        # Pending metadata + original wire/cost/native receipt remain diagnostic
        # custody. Their names never represent successful authorized handoff.
        raise



def _native_phase_broker_v2(settings,jobs,context):
    import hashlib
    from oracle_brain.operating_model.key_coverage import KeyCoverageAdmission
    from oracle_brain.operating_model.native_factory import LedgerRegistry,NativeBrokerEgress
    c=settings.config
    registry=_typed(c.ledger_registry_file,c.ledger_registry_hash,LedgerRegistry)
    admission=_typed(c.coverage_admission_file,c.coverage_admission_hash,KeyCoverageAdmission)
    registry_hash=digest(registry.model_dump(mode='json'));admission_hash=digest(admission.model_dump(mode='json'))
    d=settings.projection.descriptor
    if (registry.transport!='verify-full-tls'
            or any(j.ledger_registry_hash!=registry_hash or j.key_coverage_hash!=admission_hash for j in d.dispatches)):
        raise PermissionError('same actual TLS central budget/key coverage required')
    allocation=_typed(c.budget_allocation_projection_file,
        settings.pins.budget_allocation_projection_sha256,BudgetAllocationPinsV2)
    allocation.verify_current(trusted_projection_hash=settings.pins.budget_allocation_projection_sha256,
        dispatches=d.dispatches,now=datetime.now(timezone.utc))
    if d.expires_at>allocation.original_expires_at:
        raise PermissionError('phase cannot extend original allocation expiry')
    if c.phase=='embedding':
        raise PermissionError('current typed embedding eligibility capability required')
    key=protected_file(c.provider_key_file,limit=8192).decode().strip()
    fingerprint=hashlib.sha256(key.encode()).hexdigest()
    def coverage():
        # Same existing externally admitted key coverage and central Budget;
        # no per-phase reservations ledger, allowance cache or budget reset.
        allocation.verify_current(trusted_projection_hash=settings.pins.budget_allocation_projection_sha256,
            dispatches=d.dispatches,now=datetime.now(timezone.utc))
        for dispatch in d.dispatches:jobs.authorize(jobs.resolve(dispatch.dispatch_id))
        return signed_coverage(c.coverage_witness_file,public_key=c.coverage_observer_public_key,
            admission=admission,admission_hash=admission_hash,key_fingerprint=fingerprint,
            now=datetime.now(timezone.utc))
    from oracle_brain.operating_model.provider_adapter import AdmittedAllocationLimitV2
    if any(jobs.resolve(j.dispatch_id).batch_id!=allocation.original_batch_id for j in d.dispatches):
        raise PermissionError('every phase must preserve the same original allocation batch')
    cap=AdmittedAllocationLimitV2(batch_id=allocation.original_batch_id,allocation_hash=allocation.allocation_hash,
        original_receipt_hash=allocation.original_receipt_hash,ceiling_usd=allocation.original_ceiling_usd,
        expires_at=allocation.original_expires_at)
    kwargs=dict(admitted_allocation=cap,api_key=key,ledger_url=tls_url(c.ledger_url_file),registry=registry,
        trusted_registry_hash=registry_hash,coverage_receipt=coverage,trusted_coverage_hash=admission_hash,
        resolve_job=jobs.resolve,authorize_current_job=jobs.authorize,validate_response=jobs.validate,
        private_receipts=Path(c.private_receipts))
    if c.phase=='assembly':
        from oracle_brain.operating_model.purpose_capture_v2 import (
            ObservedPurposeAssemblyBrokerEgress,ObservedAssemblyProtocolV2,AssemblyObserverContextV2,
            ObservedAssemblyCustodianV2)
        if any(getattr(c,k) is None for k in ('assembly_observer_file','assembly_observer_hash',
            'assembly_protocol_file','assembly_protocol_hash','actual_custodian_id',
            'actual_custodian_config_hash','actual_custodian_session_hash')):
            raise PermissionError('separately admitted V2 assembly complete-wire custodian required')
        observer=_typed(c.assembly_observer_file,c.assembly_observer_hash,AssemblyObserverContextV2)
        protocol=_typed(c.assembly_protocol_file,c.assembly_protocol_hash,ObservedAssemblyProtocolV2)
        custodian=ObservedAssemblyCustodianV2(context=observer,expected_context_hash=digest(observer.model_dump(mode='json')),
            protocol=protocol,expected_protocol_hash=digest(protocol.model_dump(mode='json')),
            actual_custodian_id=c.actual_custodian_id,actual_config_hash=c.actual_custodian_config_hash,
            actual_session_hash=c.actual_custodian_session_hash,actual_runtime_hash=d.runtime_hash)
        return ObservedPurposeAssemblyBrokerEgress(assembly_context=context.assembly,
            expected_assembly_context_hash=digest(context.assembly.model_dump(mode='json')),
            assembly_observer=custodian,**kwargs)
    return NativeBrokerEgress(**kwargs)


class PurposeMetadataIngressV2:
    """Current own-caller metadata guard; forwards no request body or originals."""
    def __init__(self,settings):
        if type(settings) is not PurposeRuntimeSettingsV2 or type(settings.config) is not PurposeMetadataConfigV2:
            raise PermissionError('fixed metadata-only startup required')
        from .purpose_transport import PurposeTLSBindingV2,PurposeProviderClientV2
        c=settings.config
        self.settings=settings;self.jobs=CurrentPurposeJobsV2(settings)
        self.client=PurposeProviderClientV2(PurposeTLSBindingV2(hostname=c.provider_hostname,port=c.provider_port,
            server_uri=c.provider_server_uri,client_uri=c.provider_client_uri,ca_file=Path(c.provider_ca),
            certificate_file=Path(c.provider_certificate),key_file=Path(c.provider_key)))

    def dispatch(self,peer_uri,request):
        s=self.settings
        if (peer_uri!=s.worker_uri or type(request) is not dict
                or set(request)!={'dispatch_id','request_hash','phase_registry_sha256'}):
            raise PermissionError('fixed metadata worker and opaque dispatch required')
        dispatch_id=UUID(request['dispatch_id']);d,j=self.jobs.metadata(dispatch_id)
        if request['request_hash']!=j.request_hash or request['phase_registry_sha256']!=s.pins.phase_registry_sha256:
            raise PermissionError('metadata dispatch differs from independently admitted operation')
        def current_sql():
            with s.resolver.hold(d,j) as proof:
                verify_purpose_authority_proof_v2(proof,d,j,projection_sha256=s.pins.projection_sha256,
                    actual_caller_login=s.config.expected_session_role,profile='gateway-metadata',
                    now=datetime.now(timezone.utc))
        current_sql()
        receipt=self.client.dispatch(dispatch_id,j.request_hash,s.pins.phase_registry_sha256)
        self.jobs.metadata(dispatch_id);current_sql()
        return receipt


def build_purpose_broker_v2(settings):return PurposeBrokerIngressV2(settings)
def build_purpose_metadata_v2(settings):return PurposeMetadataIngressV2(settings)
