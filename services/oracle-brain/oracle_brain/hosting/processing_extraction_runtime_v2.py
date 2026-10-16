"""Opt-in original extraction runtime; V1 refusal/defaults are unchanged.

The operation companion is an externally reviewed canonical-JSON receipt, not a
new issuer. Compiler custody appointments and promotion belong to the R5 worker.
Pure paid-wire validation below issues no read/compile/serving authority.
"""
from datetime import datetime,timezone
from typing import Literal
from uuid import UUID
import hashlib,json
from pydantic import AwareDatetime,Field,model_validator

from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.purpose_context import HASH,LOGIN,WORKER,ParentPopulationAdmissionV2,source_population_digest
from oracle_brain.operating_model.purpose_receipts_v2 import PhaseResponseCommitV2
from oracle_brain.operating_model.source_receipts import SourceRef
from oracle_brain.operating_model.semantic_acceptance import sealed
from .provider_runtime import JobContext


class ExtractionTargetV2(StrictRecord):
    dispatch_id: UUID
    artifact_id: UUID
    artifact_version: int=Field(strict=True,ge=1)
    source_ref: SourceRef
    native_job_hash: str=Field(pattern=HASH)
    context_hash: str=Field(pattern=HASH)


class ExtractionOperationQualificationV2(StrictRecord):
    schema_version: Literal[2]=2
    qualification_purpose: Literal['source-extraction-operation-qualification-v2']='source-extraction-operation-qualification-v2'
    purpose: Literal['source-extraction']='source-extraction'
    operation: Literal['chat']='chat'
    model: Literal['openai/gpt-6.1-sol']='openai/gpt-6.1-sol'
    workspace_id: UUID
    actor_id: UUID
    provider_login: str=Field(pattern=LOGIN)
    worker_uri: str=Field(pattern=WORKER)
    runtime_hash: str=Field(pattern=HASH)
    source_registry_hash: str=Field(pattern=HASH)
    parent_registry_sha256: str=Field(pattern=HASH)
    envelope_sha256: str=Field(pattern=HASH)
    source_qualification_sha256: str=Field(pattern=HASH)
    descriptor_sha256: str=Field(pattern=HASH)
    projection_sha256: str=Field(pattern=HASH)
    population_admission_sha256: str=Field(pattern=HASH)
    budget_allocation_projection_sha256: str=Field(pattern=HASH)
    source_refs: tuple[SourceRef,...]=Field(min_length=1)
    population_digest: str=Field(pattern=HASH)
    targets: tuple[ExtractionTargetV2,...]=Field(min_length=1)
    issuer_actor: UUID
    reviewer_actor: UUID
    expires_at: AwareDatetime

    @model_validator(mode='after')
    def exact_new_original_extraction(self):
        if (len({self.actor_id,self.issuer_actor,self.reviewer_actor})!=3
                or any(r.workspace_id!=self.workspace_id for r in self.source_refs)
                or len({r.source_id for r in self.source_refs})!=len(self.source_refs)
                or self.population_digest!=source_population_digest(self.source_refs)
                or len(self.targets)!=len(self.source_refs)
                or len({t.source_ref for t in self.targets})!=len(self.targets)
                or set(t.source_ref for t in self.targets)!=set(self.source_refs)
                or len({t.dispatch_id for t in self.targets})!=len(self.targets)
                or len({(t.artifact_id,t.artifact_version) for t in self.targets})!=len(self.targets)):
            raise PermissionError('independently qualified exact ordered extraction population required')
        return self

    def target(self,dispatch_id):
        matches=[t for t in self.targets if t.dispatch_id==dispatch_id]
        if len(matches)!=1:raise PermissionError('exact qualified extraction target required')
        return matches[0]


class ExtractionResponseCommitV2(PhaseResponseCommitV2):
    purpose: Literal['observed-authorized-extraction-response-commit-v2']='observed-authorized-extraction-response-commit-v2'
    phase: Literal['extraction']='extraction'
    extraction_source_ref: SourceRef
    model_content_hash: str=Field(pattern=HASH)

    @model_validator(mode='after')
    def actual_single_original(self):
        if self.extraction_source_ref not in self.source_refs:
            raise PermissionError('extraction cannot borrow another dispatch source')
        return self


class VerifiedExtractionWitnessV2(StrictRecord):
    """Pure immutable consistency witness; never an appointment or compiler grant."""
    schema_version: Literal[2]=2
    workspace_id: UUID
    source_ref: SourceRef
    artifact_id: UUID
    artifact_version: int=Field(strict=True,ge=1)
    native_dispatch_id: UUID
    native_job_hash: str=Field(pattern=HASH)
    parent_registry_hash: str=Field(pattern=HASH)
    envelope_hash: str=Field(pattern=HASH)
    descriptor_hash: str=Field(pattern=HASH)
    extraction_qualification_hash: str=Field(pattern=HASH)
    raw_wire_hash: str=Field(pattern=HASH)
    model_content_hash: str=Field(pattern=HASH)
    phase_commit_hash: str=Field(pattern=HASH)
    native_custody_receipt_hash: str=Field(pattern=HASH)
    population_digest: str=Field(pattern=HASH)
    source_refs: tuple[SourceRef,...]


def verify_extraction_paid_wire_v2(context,commit,raw,qualification,population,*,
        expected_qualification_hash,artifact_version):
    """Pure exact paid-content validator; actual compiler/custody checks are R5.

    Qualification's protocol mandates canonical JSON bytes, so its canonical
    hash is also the independently pinned operation receipt's byte SHA. Neither
    that hash nor this returned witness creates authority to read or persist.
    """
    from oracle_brain.operating_model.captured_assembly import _observed_model_content
    from oracle_brain.operating_model.extraction import validate_response
    from oracle_brain.operating_model.pipeline import extraction_messages
    from oracle_brain.provider_policy import authorize
    if (type(context) is not JobContext or type(commit) is not ExtractionResponseCommitV2
            or type(qualification) is not ExtractionOperationQualificationV2
            or type(population) is not ParentPopulationAdmissionV2
            or type(raw) is not bytes or len(raw)>16*1024*1024
            or sealed(qualification)!=expected_qualification_hash):
        raise PermissionError('exact externally qualified extraction paid-custody inputs required')
    qualification=ExtractionOperationQualificationV2.model_validate(qualification.model_dump(mode='python'))
    commit=ExtractionResponseCommitV2.model_validate(commit.model_dump(mode='python'))
    job=context.job;target=qualification.target(job.dispatch_id)
    if (commit.operation_approval_hash!=expected_qualification_hash
            or commit.descriptor_hash!=qualification.descriptor_sha256
            or commit.parent_registry_hash!=qualification.parent_registry_sha256
            or population.workspace_id!=qualification.workspace_id
            or population.runtime_hash!=qualification.runtime_hash
            or population.source_registry_hash!=qualification.source_registry_hash
            or commit.budget_identity_hash!=qualification.budget_allocation_projection_sha256
            or population.parent_registry_sha256!=qualification.parent_registry_sha256
            or sealed(population)!=qualification.population_admission_sha256
            or population.source_refs!=qualification.source_refs or commit.source_refs!=qualification.source_refs
            or commit.population_digest!=qualification.population_digest
            or commit.actor_id!=qualification.actor_id or context.actor_id!=qualification.actor_id
            or commit.provider_login!=qualification.provider_login or commit.runtime_hash!=qualification.runtime_hash
            or commit.dispatch_id!=job.dispatch_id or target.artifact_id!=job.artifact_id
            or target.artifact_version!=artifact_version or target.source_ref!=context.receipt.ref
            or commit.extraction_source_ref!=target.source_ref
            or target.native_job_hash!=sealed(job) or commit.job_hash!=sealed(job)
            or context.job_hash!=sealed(job) or target.context_hash!=sealed(context)
            or commit.context_hash!=target.context_hash or job.request_hash!=digest(job.request)
            or context.permission_hash!=job.permission_hash or commit.permission_hash!=job.permission_hash
            or commit.request_hash!=job.request_hash or job.workspace_id!=qualification.workspace_id
            or commit.workspace_id!=qualification.workspace_id
            or job.purpose!='source-extraction' or job.processing_request.purpose!='source-extraction'
            or job.processing_request.provider!='openrouter'
            or job.processing_request.endpoint!='https://openrouter.ai/api/v1'
            or not job.processing_request.account.startswith('key-sha256:') or job.processing_request.fallback
            or job.request.get('model')!=qualification.model or commit.model!=qualification.model
            or job.pricing.model!=qualification.model or job.pricing.admitted_register_hash!=job.register_hash
            or commit.account_policy_hash!=digest({k:v for k,v in job.processing_request.model_dump(mode='json').items() if k!='terms_hash'})
            or job.request.get('messages')!=extraction_messages(context.receipt)
            or set(job.request)!={'model','messages','max_tokens','response_format','store','stream','provider'}
            or hashlib.sha256(raw).hexdigest()!=commit.raw_response_hash
            or commit.committed_at>=min(qualification.expires_at,population.expires_at)):
        raise PermissionError('paid extraction/context/target/source/population differs from qualified operation')
    authorize(job.processing_request,list(job.approvals),now=commit.committed_at)
    if commit.committed_at>=job.pricing.expires_at:
        raise PermissionError('extraction committed after original actual pricing horizon')
    content=_observed_model_content(raw,qualification.model)
    content_hash=hashlib.sha256(content.encode()).hexdigest()
    if content_hash!=commit.model_content_hash:
        raise PermissionError('model-only extraction content differs from actual paid wire')
    witness=VerifiedExtractionWitnessV2(workspace_id=qualification.workspace_id,source_ref=context.receipt.ref,
        artifact_id=target.artifact_id,artifact_version=artifact_version,native_dispatch_id=job.dispatch_id,
        native_job_hash=sealed(job),parent_registry_hash=qualification.parent_registry_sha256,
        envelope_hash=qualification.envelope_sha256,descriptor_hash=qualification.descriptor_sha256,
        extraction_qualification_hash=expected_qualification_hash,raw_wire_hash=commit.raw_response_hash,
        model_content_hash=content_hash,phase_commit_hash=sealed(commit),native_custody_receipt_hash=commit.native_custody_receipt_hash,
        population_digest=qualification.population_digest,source_refs=qualification.source_refs)
    return content,witness


def verify_extraction_paid_response_v2(context,commit,raw,qualification,population,*,expected_qualification_hash,artifact_version):
    from oracle_brain.operating_model.extraction import validate_response
    content,witness=verify_extraction_paid_wire_v2(context,commit,raw,qualification,population,
        expected_qualification_hash=expected_qualification_hash,artifact_version=artifact_version)
    response,_=validate_response(context.receipt,content,inventories=context.inventories)
    return response,witness

# These are separate opt-in startup schemas; the V1 schemas and refusal are not
# widened. Provider-only parent paths never occur in the metadata schema.
from contextlib import contextmanager,ExitStack
from dataclasses import dataclass
from pathlib import Path
from .purpose_runtime import PurposeCommonConfigV2,PurposeProviderConfigV2,PurposeMetadataConfigV2,_typed
from oracle_brain.operating_model.processing_context import ProcessingPins,ProcessingProjection
from oracle_brain.operating_model.authority_adapter import BoundProcessingSourceResolver
from .processing_profile import ProcessingCurrentJobs


class ExtractionProviderConfigV2(PurposeCommonConfigV2):
    phase: Literal['extraction']='extraction'
    role: Literal['provider']='provider'
    extraction_qualification_file: str
    extraction_qualification_sha256: str=Field(pattern=HASH)
    parent_registry_file: str
    envelope_file: str
    source_qualification_file: str
    provider_key_file: str
    ledger_url_file: str
    ledger_registry_file: str
    ledger_registry_hash: str=Field(pattern=HASH)
    coverage_admission_file: str
    coverage_admission_hash: str=Field(pattern=HASH)
    coverage_witness_file: str
    coverage_observer_public_key: str=Field(pattern=HASH)
    private_receipts: str


class ExtractionMetadataConfigV2(PurposeMetadataConfigV2):
    phase: Literal['extraction']='extraction'
    extraction_qualification_file: str
    extraction_qualification_sha256: str=Field(pattern=HASH)


@dataclass(frozen=True)
class ExtractionRuntimeSettingsV2:
    config: ExtractionProviderConfigV2|ExtractionMetadataConfigV2
    pins: ProcessingPins
    population: ParentPopulationAdmissionV2
    projection: ProcessingProjection
    qualification: ExtractionOperationQualificationV2
    resolver: BoundProcessingSourceResolver
    observer: object
    config_path: Path
    config_sha256: str

    @property
    def phase(self):return 'extraction'
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


def _current_extraction_records_v2(settings,*,now):
    from .provider_runtime import pinned
    from oracle_brain.operating_model.purpose_context import BudgetAllocationPinsV2
    s=settings;c=s.config;q=s.qualification;d=s.projection.descriptor
    pinned(s.config_path,s.config_sha256)
    if (_typed(c.pins_file,c.pins_sha256,ProcessingPins)!=s.pins
            or _typed(c.projection_file,q.projection_sha256,ProcessingProjection)!=s.projection
            or _typed(c.population_file,q.population_admission_sha256,ParentPopulationAdmissionV2)!=s.population):
        raise PermissionError('current extraction protected metadata changed')
    raw=pinned(c.extraction_qualification_file,c.extraction_qualification_sha256)
    if raw!=canonical_bytes(q.model_dump(mode='json')):
        raise PermissionError('exact canonical independently qualified extraction operation changed')
    if _typed(c.parent_observer_admission_file,c.parent_observer_admission_hash,type(s.observer.admission))!=s.observer.admission:
        raise PermissionError('separately appointed extraction parent observer changed')
    allocation=_typed(c.budget_allocation_projection_file,q.budget_allocation_projection_sha256,BudgetAllocationPinsV2)
    if (now>=min(q.expires_at,d.expires_at,s.population.expires_at,c.source_expires_at,
                 allocation.original_expires_at,s.observer.admission.expires_at)
            or allocation.ledger_registry_hash!=d.ledger_registry_hash or allocation.key_coverage_hash!=d.key_coverage_hash):
        raise PermissionError('extraction operation/source/allocation appointment expired or changed')
    return allocation


@contextmanager
def _extraction_population_hold_v2(settings,dispatch):
    """Every source before any body, one real connection, no network inside."""
    s=settings;d=s.projection.descriptor
    with s.resolver._connection(None) as conn:
        # Metadata-only identity getters first. A missing last grant prevents the
        # first private parent/source byte, rather than partial population reads.
        for ref in d.source_refs:
            if s.resolver.identity(d.workspace_id,ref.source_id,connection=conn)!=ref:
                raise PermissionError('complete extraction source population changed')
        with ExitStack() as stack:
            proofs=tuple(stack.enter_context(s.resolver.hold(d,j,connection=conn)) for j in d.dispatches)
            proof=proofs[d.dispatches.index(dispatch)]
            # Narrow the actual selected-source proof to every admitted source's
            # finite SQL horizon; never stretch one source over another grant.
            proof=proof.model_copy(update={'expires_at':min(p.expires_at for p in proofs)})
            if datetime.now(timezone.utc)>=proof.expires_at:
                raise PermissionError('complete extraction source horizon expired')
            _current_extraction_records_v2(s,now=datetime.now(timezone.utc))
            yield proof,conn
            _current_extraction_records_v2(s,now=datetime.now(timezone.utc))


class SourceExtractionJobsV2:
    """Actual opt-in source SQL admission; V1 authorize continues to refuse."""
    def __init__(self,settings):
        if (type(settings) is not ExtractionRuntimeSettingsV2
                or type(settings.resolver) is not BoundProcessingSourceResolver):
            raise PermissionError('fixed extraction startup and actual SQL binding required')
        self.settings=settings

    def metadata(self,dispatch_id):
        s=self.settings;d=s.projection.descriptor
        matches=[j for j in d.dispatches if j.dispatch_id==dispatch_id]
        if len(matches)!=1:raise PermissionError('unique exact extraction dispatch required')
        j=matches[0]
        _current_extraction_records_v2(s,now=datetime.now(timezone.utc))
        witness=s.observer.current(s.population)
        with _extraction_population_hold_v2(s,j):pass
        return d,j,witness

    def context(self,dispatch_id):
        s=self.settings;c=s.config
        if type(c) is not ExtractionProviderConfigV2:
            raise PermissionError('metadata extraction worker cannot open private parent')
        d,j,witness=self.metadata(dispatch_id)
        from .provider_runtime import CurrentJobs
        with _extraction_population_hold_v2(s,j) as (proof,conn):
            parent=CurrentJobs({'job_registry_file':c.parent_registry_file,
                'job_registry_hash':s.pins.parent_registry_sha256,'runtime_hash':s.pins.runtime_hash})
            jobs=ProcessingCurrentJobs(parent,envelope_path=c.envelope_file,
                qualification_path=c.source_qualification_file,pins=s.pins)
            registry,projection=jobs.snapshot()
            if projection!=s.projection:
                raise PermissionError('private extraction parent differs from admitted complete projection')
            matches=[x for x in registry.contexts if x.job.dispatch_id==dispatch_id]
            if len(matches)!=1:raise PermissionError('unique original extraction dispatch required')
            ctx=matches[0];q=s.qualification;target=q.target(dispatch_id)
            actual=s.resolver.current_for_processing(d.workspace_id,ctx.receipt.ref.source_id,connection=conn)
            allocation=_current_extraction_records_v2(s,now=datetime.now(timezone.utc))
            from oracle_brain.operating_model.pipeline import extraction_messages
            policy=ctx.job.processing_request.model_dump(mode='json')
            if (ctx.receipt!=actual or ctx.actor_id!=q.actor_id or target.source_ref!=actual.ref
                    or target.native_job_hash!=sealed(ctx.job) or target.context_hash!=sealed(ctx)
                    or target.artifact_id!=ctx.job.artifact_id or ctx.job.request.get('model')!=q.model
                    or ctx.job.request.get('messages')!=extraction_messages(actual)
                    or ctx.job.batch_id!=allocation.original_batch_id
                    or digest({k:policy[k] for k in ('provider','account','endpoint')})!=allocation.account_identity_hash):
                raise PermissionError('actual original/native request differs from independently qualified extraction')
            # Parent V1 envelope retains exact original allocation authority.
            from oracle_brain.operating_model.processing_context import ProcessingEnvelope
            envelope=_typed(c.envelope_file,s.pins.envelope_sha256,ProcessingEnvelope)
            if (envelope.budget_allocation_hash!=allocation.allocation_hash
                    or envelope.budget_receipt_hash!=allocation.original_receipt_hash
                    or envelope.budget_ceiling_usd!=allocation.original_ceiling_usd
                    or envelope.budget_expires_at!=allocation.original_expires_at):
                raise PermissionError('extraction cannot replace or renew original shared allocation')
        # Observer is outside SQL locks, followed by a fresh actual all-source
        # hold. The old witness is never stretched over a paid model operation.
        witness=s.observer.current(s.population)
        with _extraction_population_hold_v2(s,j) as (proof,conn):
            from .provider_runtime import pinned
            pinned(c.parent_registry_file,s.pins.parent_registry_sha256)
            if datetime.now(timezone.utc)>=min(witness.expires_at,proof.expires_at):
                raise PermissionError('extraction currentness expired before dispatch')
        return ctx

    def resolve(self,dispatch_id):return self.context(dispatch_id).job
    def authorize(self,job):
        if self.resolve(job.dispatch_id)!=job:raise PermissionError('actual current extraction job changed')
        return True
    def validate(self,job,response):
        from oracle_brain.operating_model.extraction import validate_response
        ctx=self.context(job.dispatch_id)
        if ctx.job!=job:raise PermissionError('paid extraction job changed before validation')
        validate_response(ctx.receipt,response,inventories=ctx.inventories)
        self.authorize(job)


def load_extraction_runtime_settings_v2(config_path,trusted_config_sha256,*,expected_role):
    """Fixed protected extraction startup; metadata loader never opens parent."""
    from .provider_runtime import pinned,tls_url
    from .gateway import unique_object
    from .purpose_transport import PurposeTLSBindingV2,ParentObserverClientV2
    from .parent_observer_v2 import ParentObserverAdmissionV2,ParentCurrentnessConsumerV2
    from .custody import DurableNonceSequenceV2
    from oracle_brain.operating_model.authority_adapter import ProcessingSourceBinding,ProcessingRunBinding
    if expected_role not in {'provider','metadata'}:
        raise PermissionError('fixed extraction role required')
    raw=pinned(config_path,trusted_config_sha256)
    model=ExtractionProviderConfigV2 if expected_role=='provider' else ExtractionMetadataConfigV2
    c=model.model_validate_json(canonical_bytes(json.loads(raw,object_pairs_hook=unique_object)))
    if c.role!=expected_role:raise PermissionError('protected extraction role differs')
    qraw=pinned(c.extraction_qualification_file,c.extraction_qualification_sha256)
    q=ExtractionOperationQualificationV2.model_validate_json(qraw)
    if qraw!=canonical_bytes(q.model_dump(mode='json')):
        raise PermissionError('independently qualified extraction companion requires exact canonical bytes')
    pins=_typed(c.pins_file,c.pins_sha256,ProcessingPins)
    pop=_typed(c.population_file,q.population_admission_sha256,ParentPopulationAdmissionV2)
    projection=_typed(c.projection_file,q.projection_sha256,ProcessingProjection);d=projection.descriptor
    if (sealed(q)!=c.extraction_qualification_sha256 or c.worker_uri!=q.worker_uri or pins.worker_uri!=q.worker_uri
            or pins.runtime_hash!=q.runtime_hash or pins.source_registry_hash!=q.source_registry_hash
            or pins.parent_registry_sha256!=q.parent_registry_sha256 or pins.envelope_sha256!=q.envelope_sha256
            or pins.qualification_sha256!=q.source_qualification_sha256 or pins.descriptor_sha256!=q.descriptor_sha256
            or pins.projection_sha256!=q.projection_sha256 or projection.descriptor_sha256!=q.descriptor_sha256
            or d.actor_id!=q.actor_id or d.workspace_id!=q.workspace_id or d.source_refs!=q.source_refs
            or pop.source_refs!=q.source_refs or pop.runtime_hash!=q.runtime_hash or pop.source_registry_hash!=q.source_registry_hash
            or pop.workspace_id!=q.workspace_id or pop.parent_registry_sha256!=q.parent_registry_sha256
            or tuple(t.dispatch_id for t in q.targets)!=tuple(j.dispatch_id for j in d.dispatches)
            or any(t.source_ref!=j.source_ref or t.native_job_hash!=j.job_hash for t,j in zip(q.targets,d.dispatches))
            or (c.role=='provider' and c.expected_session_role!=q.provider_login)):
        raise PermissionError('external extraction operation/parent/population/startup pins differ')
    admission=_typed(c.parent_observer_admission_file,c.parent_observer_admission_hash,ParentObserverAdmissionV2)
    if (admission.population!=pop or admission.principal_id!=q.actor_id
            or admission.observer_uri!=c.observer_server_uri or admission.client_uri!=c.observer_client_uri):
        raise PermissionError('separately admitted extraction observer identity differs')
    horizon=min(q.expires_at,d.expires_at,pop.expires_at,c.source_expires_at,admission.expires_at)
    if datetime.now(timezone.utc)>=horizon:raise PermissionError('extraction startup authority expired')
    binding=ProcessingSourceBinding(runtime_hash=q.runtime_hash,source_registry_hash=q.source_registry_hash,
        expected_owner_role=c.expected_owner_role,expected_session_role=c.expected_session_role,
        principal=q.actor_id,profile='source-reader' if c.role=='provider' else 'gateway-metadata',expires_at=horizon)
    resolver=BoundProcessingSourceResolver(tls_url(c.source_url_file),run_binding=ProcessingRunBinding(binding,
        q.descriptor_sha256,q.parent_registry_sha256,q.envelope_sha256))
    transport=ParentObserverClientV2(PurposeTLSBindingV2(hostname=c.observer_hostname,port=c.observer_port,
        server_uri=c.observer_server_uri,client_uri=c.observer_client_uri,ca_file=Path(c.observer_ca),
        certificate_file=Path(c.observer_certificate),key_file=Path(c.observer_key),timeout=c.observer_timeout_seconds))
    replay=DurableNonceSequenceV2(c.observer_spool,namespace=c.observer_namespace,
        appointment_hash=c.parent_observer_admission_hash,minimum_sequence=admission.minimum_sequence,
        initialization_receipt_hash=c.observer_initialization_hash)
    observer=ParentCurrentnessConsumerV2(admission=admission,trusted_admission_hash=c.parent_observer_admission_hash,
        transport=transport,replay=replay)
    settings=ExtractionRuntimeSettingsV2(c,pins,pop,projection,q,resolver,observer,Path(config_path),trusted_config_sha256)
    _current_extraction_records_v2(settings,now=datetime.now(timezone.utc))
    return settings


def _extraction_broker_v2(settings,jobs,context):
    from .provider_runtime import tls_url,signed_coverage
    from .runtime import protected_file
    from oracle_brain.operating_model.native_factory import LedgerRegistry,NativeBrokerEgress
    from oracle_brain.operating_model.key_coverage import KeyCoverageAdmission
    from oracle_brain.operating_model.provider_adapter import AdmittedAllocationLimitV2
    s=settings;c=s.config;d=s.projection.descriptor
    registry=_typed(c.ledger_registry_file,c.ledger_registry_hash,LedgerRegistry)
    coverage_admission=_typed(c.coverage_admission_file,c.coverage_admission_hash,KeyCoverageAdmission)
    if (registry.transport!='verify-full-tls' or sealed(registry)!=d.ledger_registry_hash
            or sealed(coverage_admission)!=d.key_coverage_hash):
        raise PermissionError('same externally qualified central TLS ledger/key coverage required')
    allocation=_current_extraction_records_v2(s,now=datetime.now(timezone.utc))
    # Actual context validation checks original batch/account/receipt mapping;
    # no V1 budget digest is coerced into the V2 projection identity.
    for dispatch in d.dispatches:jobs.resolve(dispatch.dispatch_id)
    key=protected_file(c.provider_key_file,limit=8192).decode().strip()
    fingerprint=hashlib.sha256(key.encode()).hexdigest()
    def coverage():
        if (_typed(c.ledger_registry_file,c.ledger_registry_hash,LedgerRegistry)!=registry
                or _typed(c.coverage_admission_file,c.coverage_admission_hash,KeyCoverageAdmission)!=coverage_admission):
            raise PermissionError('current extraction central ledger/key admission changed')
        _current_extraction_records_v2(s,now=datetime.now(timezone.utc))
        for dispatch in d.dispatches:jobs.resolve(dispatch.dispatch_id)
        return signed_coverage(c.coverage_witness_file,public_key=c.coverage_observer_public_key,
            admission=coverage_admission,admission_hash=sealed(coverage_admission),key_fingerprint=fingerprint,
            now=datetime.now(timezone.utc))
    cap=AdmittedAllocationLimitV2(batch_id=allocation.original_batch_id,allocation_hash=allocation.allocation_hash,
        original_receipt_hash=allocation.original_receipt_hash,ceiling_usd=allocation.original_ceiling_usd,
        expires_at=allocation.original_expires_at)
    return NativeBrokerEgress(admitted_allocation=cap,api_key=key,ledger_url=tls_url(c.ledger_url_file),
        registry=registry,trusted_registry_hash=sealed(registry),coverage_receipt=coverage,
        trusted_coverage_hash=sealed(coverage_admission),resolve_job=jobs.resolve,
        authorize_current_job=jobs.authorize,validate_response=jobs.validate,private_receipts=Path(c.private_receipts))


def _commit_extraction_response_v2(settings,context,record):
    """Actual source-guarded commit observation; paid wire/cost remain on denial."""
    import os
    from uuid import uuid4
    from .custody import _durable_nonce,_sync_spool
    from .provider_runtime import pinned
    from oracle_brain.operating_model.captured_assembly import _observed_model_content
    s=settings;q=s.qualification;d=s.projection.descriptor
    j=next(j for j in d.dispatches if j.dispatch_id==context.job.dispatch_id)
    witness=s.observer.current(s.population) # never under SQL locks
    directory=Path(s.config.private_receipts)
    pending=directory/(str(j.dispatch_id)+'.phase-pending-'+uuid4().hex+'.json')
    success=directory/(str(j.dispatch_id)+'.phase-commit.json');created=False;owned_inode=None
    raw=record.get('raw_response')
    if not isinstance(raw,str):raise PermissionError('actual complete native extraction response required')
    wire=raw.encode();content=_observed_model_content(wire,q.model)
    if hashlib.sha256(wire).hexdigest()!=record['raw_response_hash']:
        raise PermissionError('native extraction wire seal differs')
    try:
        with _extraction_population_hold_v2(s,j) as (proof,conn):
            now=datetime.now(timezone.utc);allocation=_current_extraction_records_v2(s,now=now)
            pinned(s.config.parent_registry_file,s.pins.parent_registry_sha256)
            until=min(proof.expires_at,witness.expires_at,q.expires_at,d.expires_at,
                s.population.expires_at,s.config.source_expires_at,allocation.original_expires_at)
            committed=ExtractionResponseCommitV2(phase='extraction',operation='chat',processing_purpose='source-extraction',
                dispatch_id=j.dispatch_id,workspace_id=d.workspace_id,actor_id=d.actor_id,provider_login=q.provider_login,
                actual_caller_login=s.config.expected_session_role,runtime_hash=d.runtime_hash,descriptor_hash=q.descriptor_sha256,
                operation_approval_hash=s.config.extraction_qualification_sha256,population_digest=q.population_digest,
                source_refs=q.source_refs,extraction_source_ref=j.source_ref,model_content_hash=hashlib.sha256(content.encode()).hexdigest(),
                context_hash=sealed(context),parent_registry_hash=d.parent_registry_sha256,current_proof_hash=sealed(proof),
                parent_witness_hash=sealed(witness),account_policy_hash=j.account_policy_hash,model=q.model,valid_until=until,
                job_hash=j.job_hash,request_hash=j.request_hash,permission_hash=j.permission_hash,
                budget_identity_hash=q.budget_allocation_projection_sha256,raw_response_hash=record['raw_response_hash'],
                native_custody_receipt_hash=digest(record),committed_at=now)
            verify_extraction_paid_response_v2(context,committed,wire,q,s.population,
                expected_qualification_hash=s.config.extraction_qualification_sha256,
                artifact_version=q.target(j.dispatch_id).artifact_version)
            _durable_nonce(directory,pending.name,canonical_bytes(committed.model_dump(mode='json')))
            info=pending.lstat();owned_inode=(info.st_dev,info.st_ino)
            if datetime.now(timezone.utc)>=until:raise PermissionError('extraction authorization expired before commit')
            os.link(pending,success,follow_symlinks=False);created=True;_sync_spool(directory)
            _current_extraction_records_v2(s,now=datetime.now(timezone.utc))
            pinned(s.config.parent_registry_file,s.pins.parent_registry_sha256)
        if datetime.now(timezone.utc)>=until:raise PermissionError('extraction authorization expired before handoff')
        pending.unlink();_sync_spool(directory)
        return committed
    except BaseException:
        if created and success.exists() and (success.lstat().st_dev,success.lstat().st_ino)==owned_inode:
            os.unlink(success);_sync_spool(directory)
        raise


class ExtractionBrokerIngressV2:
    def __init__(self,settings):
        if type(settings) is not ExtractionRuntimeSettingsV2 or type(settings.config) is not ExtractionProviderConfigV2:
            raise PermissionError('fixed extraction provider startup required')
        self.settings=settings;self.jobs=SourceExtractionJobsV2(settings)
    def dispatch(self,peer_uri,request):
        from .runtime import protected_file
        from .gateway import unique_object
        s=self.settings
        if (peer_uri!=s.worker_uri or type(request) is not dict
                or set(request)!={'dispatch_id','request_hash','extraction_qualification_sha256'}
                or request['extraction_qualification_sha256']!=s.config.extraction_qualification_sha256
                or not isinstance(request['dispatch_id'],str) or str(UUID(request['dispatch_id']))!=request['dispatch_id']):
            raise PermissionError('fixed extraction peer and opaque operation required')
        ctx=self.jobs.context(UUID(request['dispatch_id']))
        if request['request_hash']!=ctx.job.request_hash:raise PermissionError('qualified extraction request differs')
        broker=_extraction_broker_v2(s,self.jobs,ctx)
        broker.dispatch(canonical_bytes({'dispatch_id':request['dispatch_id'],'request_hash':request['request_hash'],'request':ctx.job.request}))
        self.jobs.authorize(ctx.job)
        record=json.loads(protected_file(Path(s.config.private_receipts)/(request['dispatch_id']+'.json'),limit=20*1024*1024),object_pairs_hook=unique_object)
        if record.get('failed') is not False or record.get('job_hash')!=sealed(ctx.job) or record.get('request_hash')!=ctx.job.request_hash:
            raise PermissionError('successful current native extraction receipt required')
        commit=_commit_extraction_response_v2(s,ctx,record)
        return {**request,'raw_response_hash':record['raw_response_hash'],'receipt_hash':sealed(commit)}


class ExtractionMetadataIngressV2:
    def __init__(self,settings):
        if type(settings) is not ExtractionRuntimeSettingsV2 or type(settings.config) is not ExtractionMetadataConfigV2:
            raise PermissionError('fixed metadata extraction startup required')
        from .purpose_transport import PurposeTLSBindingV2,ExtractionProviderClientV2
        s=settings;c=s.config;self.settings=s;self.jobs=SourceExtractionJobsV2(s)
        self.client=ExtractionProviderClientV2(PurposeTLSBindingV2(hostname=c.provider_hostname,port=c.provider_port,
            server_uri=c.provider_server_uri,client_uri=c.provider_client_uri,ca_file=Path(c.provider_ca),
            certificate_file=Path(c.provider_certificate),key_file=Path(c.provider_key),timeout=c.provider_rpc_timeout_seconds))
    def dispatch(self,peer_uri,request):
        s=self.settings
        if peer_uri!=s.worker_uri or type(request) is not dict or set(request)!={'dispatch_id','request_hash','extraction_qualification_sha256'}:
            raise PermissionError('opaque extraction metadata worker required')
        d,j,witness=self.jobs.metadata(UUID(request['dispatch_id']))
        if request['request_hash']!=j.request_hash or request['extraction_qualification_sha256']!=s.config.extraction_qualification_sha256:
            raise PermissionError('qualified metadata extraction differs')
        with _extraction_population_hold_v2(s,j) as (proof,conn):
            allocation=_current_extraction_records_v2(s,now=datetime.now(timezone.utc))
            deadline=min(proof.expires_at,s.qualification.expires_at,d.expires_at,s.population.expires_at,
                s.config.source_expires_at,allocation.original_expires_at,s.observer.admission.expires_at)
        if datetime.now(timezone.utc)>=witness.expires_at:raise PermissionError('extraction observer expired before POST')
        result=self.client.dispatch(j.dispatch_id,j.request_hash,s.config.extraction_qualification_sha256,deadline=deadline)
        self.jobs.metadata(j.dispatch_id)
        return result


def build_extraction_broker_v2(settings):return ExtractionBrokerIngressV2(settings)
def build_extraction_metadata_v2(settings):return ExtractionMetadataIngressV2(settings)


class FailedPaidResponseCustodyWitnessV2(StrictRecord):
    """Failed paid custody consistency; never successful response/phase authority."""
    schema_version: Literal[2]=2
    purpose: Literal['failed-native-extraction-custody-v2']='failed-native-extraction-custody-v2'
    workspace_id: UUID
    artifact_id: UUID
    artifact_version: int=Field(strict=True,ge=1)
    source_ref: SourceRef
    source_refs: tuple[SourceRef,...]
    population_digest: str=Field(pattern=HASH)
    native_dispatch_id: UUID
    reservation_id: UUID
    native_job_hash: str=Field(pattern=HASH)
    request_hash: str=Field(pattern=HASH)
    permission_hash: str=Field(pattern=HASH)
    expected_model: Literal['openai/gpt-6.1-sol']='openai/gpt-6.1-sol'
    account_policy_hash: str=Field(pattern=HASH)
    account_identity_hash: str=Field(pattern=HASH)
    budget_projection_hash: str=Field(pattern=HASH)
    extraction_qualification_hash: str=Field(pattern=HASH)
    native_receipt_hash: str=Field(pattern=HASH)
    wire_metadata_hash: str=Field(pattern=HASH)
    raw_wire_hash: str=Field(pattern=HASH)
    key_fingerprint: str=Field(pattern=HASH)
    ledger_identity_hash: str=Field(pattern=HASH)
    complete_wire: bool=Field(strict=True)
    failure_class: Literal['incomplete-wire','malformed-envelope','rejected-extraction','native-failure-after-response']


def verify_extraction_failed_paid_wire_v2(context,record,raw,wire_metadata,qualification,population,*,
        expected_qualification_hash,expected_ledger_hash,artifact_version,now):
    """Pure failed custody check. Caller authenticates exact files/current SQL.

    Failed native records have no trusted historical commit observation. This
    consumer conservatively requires current operation/population horizons; it
    cannot mint or imitate a successful ExtractionResponseCommitV2.
    """
    from oracle_brain.operating_model.captured_assembly import _observed_model_content
    from oracle_brain.operating_model.extraction import validate_response
    from oracle_brain.operating_model.pipeline import extraction_messages
    from oracle_brain.provider_policy import authorize
    if (type(context) is not JobContext or type(record) is not dict or type(wire_metadata) is not dict
            or type(raw) is not bytes or not raw or len(raw)>16*1024*1024
            or type(qualification) is not ExtractionOperationQualificationV2
            or type(population) is not ParentPopulationAdmissionV2
            or type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None
            or sealed(qualification)!=expected_qualification_hash):
        raise PermissionError('exact current qualified failed paid custody required')
    q=ExtractionOperationQualificationV2.model_validate(qualification.model_dump(mode='python'))
    pop=ParentPopulationAdmissionV2.model_validate(population.model_dump(mode='python'))
    job=context.job;target=q.target(job.dispatch_id);policy=job.processing_request.model_dump(mode='json')
    key=job.processing_request.account.removeprefix('key-sha256:');wire_hash=hashlib.sha256(raw).hexdigest()
    record_fields={'dispatch_id','reservation_id','failed','raw_response','request_hash','permission_hash','job_hash',
        'register_hash','pricing_hash','key_fingerprint','ledger_identity_hash','raw_response_hash','wire_custody'}
    wire_fields={'dispatch_id','reservation_id','request_hash','permission_hash','job_hash','key_fingerprint',
        'ledger_identity_hash','raw_sha256','captured_bytes','complete','truncated'}
    if (set(record)!=record_fields or set(wire_metadata)!=wire_fields or record['failed'] is not True
            or record['wire_custody']!=wire_metadata or type(wire_metadata['complete']) is not bool
            or wire_metadata['truncated'] is not (not wire_metadata['complete'])
            or type(wire_metadata['captured_bytes']) is not int or wire_metadata['captured_bytes']!=len(raw)
            or wire_metadata['raw_sha256']!=wire_hash
            or any(record[k]!=wire_metadata[k] for k in ('dispatch_id','reservation_id','request_hash','permission_hash','job_hash','key_fingerprint','ledger_identity_hash'))
            or record['dispatch_id']!=str(job.dispatch_id) or record['job_hash']!=sealed(job)
            or record['request_hash']!=job.request_hash or record['permission_hash']!=job.permission_hash
            or record['register_hash']!=job.register_hash or record['pricing_hash']!=sealed(job.pricing)
            or record['key_fingerprint']!=key or record['ledger_identity_hash']!=expected_ledger_hash
            or now>=min(q.expires_at,pop.expires_at,job.pricing.expires_at)
            or sealed(pop)!=q.population_admission_sha256 or pop.source_refs!=q.source_refs
            or pop.parent_registry_sha256!=q.parent_registry_sha256 or pop.runtime_hash!=q.runtime_hash
            or pop.source_registry_hash!=q.source_registry_hash or pop.workspace_id!=q.workspace_id
            or context.actor_id!=q.actor_id or job.workspace_id!=q.workspace_id
            or target.source_ref!=context.receipt.ref or target.artifact_id!=job.artifact_id
            or target.artifact_version!=artifact_version or target.native_job_hash!=sealed(job)
            or target.context_hash!=sealed(context) or context.job_hash!=sealed(job)
            or context.permission_hash!=job.permission_hash or job.request_hash!=digest(job.request)
            or job.purpose!='source-extraction' or job.processing_request.purpose!='source-extraction'
            or job.processing_request.provider!='openrouter'
            or job.processing_request.endpoint!='https://openrouter.ai/api/v1'
            or not job.processing_request.account.startswith('key-sha256:') or job.processing_request.fallback
            or job.request.get('model')!=q.model or job.pricing.model!=q.model
            or job.pricing.admitted_register_hash!=job.register_hash
            or job.request.get('messages')!=extraction_messages(context.receipt)):
        raise PermissionError('failed native custody differs from qualified extraction/actual paid wire')
    reservation=UUID(record['reservation_id'])
    if str(reservation)!=record['reservation_id']:raise PermissionError('actual canonical reservation required')
    authorize(job.processing_request,list(job.approvals),now=now)
    if record['raw_response'] is None:
        if record['raw_response_hash'] is not None:raise PermissionError('absent decoded wire cannot claim a decoded hash')
    elif (not isinstance(record['raw_response'],str) or record['raw_response'].encode()!=raw
            or record['raw_response_hash']!=wire_hash):
        raise PermissionError('decoded failed receipt differs from captured bytes')
    if not wire_metadata['complete']:
        failure='incomplete-wire'
    else:
        try:content=_observed_model_content(raw,q.model)
        except Exception:failure='malformed-envelope'
        else:
            try:validate_response(context.receipt,content,inventories=context.inventories)
            except Exception:failure='rejected-extraction'
            else:failure='native-failure-after-response'
    return FailedPaidResponseCustodyWitnessV2(workspace_id=q.workspace_id,artifact_id=target.artifact_id,
        artifact_version=artifact_version,source_ref=context.receipt.ref,source_refs=q.source_refs,population_digest=q.population_digest,
        native_dispatch_id=job.dispatch_id,reservation_id=reservation,native_job_hash=sealed(job),request_hash=job.request_hash,
        permission_hash=job.permission_hash,account_policy_hash=digest({k:v for k,v in policy.items() if k!='terms_hash'}),
        account_identity_hash=digest({k:policy[k] for k in ('provider','account','endpoint')}),
        budget_projection_hash=q.budget_allocation_projection_sha256,extraction_qualification_hash=expected_qualification_hash,
        native_receipt_hash=digest(record),wire_metadata_hash=digest(wire_metadata),raw_wire_hash=wire_hash,
        key_fingerprint=key,ledger_identity_hash=expected_ledger_hash,complete_wire=wire_metadata['complete'],failure_class=failure)
