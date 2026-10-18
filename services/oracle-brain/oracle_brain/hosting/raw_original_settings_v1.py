"""Fixed raw PDF startup and currentness; never creates a grant or provider key."""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import UUID
import os,re

from pydantic import AwareDatetime,Field,field_validator,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.original_qualification_v1 import RawOriginalPopulationV1
from oracle_brain.operating_model.original_source_authority_v1 import OriginalSourceBindingV1,OriginalSourceResolverV1
from oracle_brain.operating_model.raw_original_context_v1 import RawOriginalPhaseContextV1
from oracle_brain.operating_model.raw_vision_policy_v1 import RawVisionTokenPolicyV1
from .purpose_journey_v2 import _worker_file,_worker_json,_require
from .purpose_transport import PurposeTLSBindingV2
from .custody import DurableNonceSequenceV2
from .raw_original_observer_v1 import RawOriginalObserverAdmissionV1,RawOriginalObserverClientV1,RawOriginalCurrentnessConsumerV1

HASH=r'^[0-9a-f]{64}$'

class RawPrivateFileV1(StrictRecord):
    path:str
    sha256:str=Field(pattern=HASH)

class RawObserverTLSV1(StrictRecord):
    hostname:str
    port:int=Field(strict=True,ge=1,le=65535)
    server_uri:str
    client_uri:str
    ca:RawPrivateFileV1
    certificate:RawPrivateFileV1
    key:RawPrivateFileV1

class RawOriginalProviderConfigV1(StrictRecord):
    schema_version:Literal[1]=1
    purpose:Literal['raw-original-provider-startup-v1']='raw-original-provider-startup-v1'
    population:RawOriginalPopulationV1
    actor_id:UUID
    phase_purpose:Literal['source-original-reading','source-original-review']
    expected_owner_role:str
    expected_session_role:str
    original_allocation_hash:str=Field(pattern=HASH)
    original_horizon:AwareDatetime
    database_url:RawPrivateFileV1
    database_ca:RawPrivateFileV1
    database_hostname:str
    database_port:int=Field(strict=True,ge=1,le=65535)
    database_name:str
    context:RawPrivateFileV1
    observer_admission:RawPrivateFileV1
    observer_tls:RawObserverTLSV1
    observer_spool:str
    observer_namespace:str
    observer_initialization_hash:str=Field(pattern=HASH)
    original_root:str
    original_root_identity:tuple[int,int,int]
    storage_profile_hash:str=Field(pattern=HASH)
    vision_policy:RawPrivateFileV1
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime

    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,v):
        if type(v) is not int or v!=1:raise ValueError('exact raw startup version required')
        return v

    @model_validator(mode='after')
    def finite_independent_startup(self):
        if (len({self.actor_id,self.issuer_actor,self.reviewer_actor})!=3
            or not self.valid_from<self.expires_at<=self.population.expires_at<=self.original_horizon
            or self.original_root_identity[2]!=os.getuid()
            or any(v<0 for v in self.original_root_identity)):
            raise ValueError('independent bounded raw startup required')
        return self

class RawOriginalProviderAppointmentV1(StrictRecord):
    schema_version:Literal[1]=1
    purpose:Literal['raw-original-provider-appointment-v1']='raw-original-provider-appointment-v1'
    config_sha256:str=Field(pattern=HASH)
    context_sha256:str=Field(pattern=HASH)
    population:RawOriginalPopulationV1
    actor_id:UUID
    expected_session_role:str
    original_allocation_hash:str=Field(pattern=HASH)
    original_horizon:AwareDatetime
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime

    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,v):
        if type(v) is not int or v!=1:raise ValueError('exact raw appointment version required')
        return v

@dataclass(frozen=True)
class RawOriginalAuthorityWindowV1:
    current_until:datetime
    operation_horizon:datetime
    sql_receipt_hash:str
    observer_witness_hash:str

    def __post_init__(self):
        if (any(type(v) is not datetime or v.tzinfo is None or v.utcoffset() is None
                for v in (self.current_until,self.operation_horizon))
            or self.current_until>self.operation_horizon
            or any(type(v) is not str or re.fullmatch(HASH,v) is None
                for v in (self.sql_receipt_hash,self.observer_witness_hash))):
            raise PermissionError('finite exact raw authorization window required')

@dataclass(frozen=True)
class RawOriginalProviderSettingsV1:
    config:RawOriginalProviderConfigV1
    config_path:Path
    config_sha256:str
    appointment_path:Path
    appointment_sha256:str
    appointment:RawOriginalProviderAppointmentV1
    resolver:OriginalSourceResolverV1
    observer:RawOriginalCurrentnessConsumerV1
    context:RawOriginalPhaseContextV1
    vision_policy:RawVisionTokenPolicyV1

    def current_window(self):
        c=self.config;now=datetime.now(timezone.utc)
        _require(_worker_json(self.config_path,self.config_sha256,RawOriginalProviderConfigV1)==c
            and _worker_json(self.appointment_path,self.appointment_sha256,RawOriginalProviderAppointmentV1)==self.appointment,
            'raw startup metadata changed')
        _require(type(self) is RawOriginalProviderSettingsV1 and type(self.resolver) is OriginalSourceResolverV1
            and type(self.observer) is RawOriginalCurrentnessConsumerV1
            and c.valid_from<=now<min(c.expires_at,self.appointment.expires_at,self.context.phase_expires_at),
            'actual current protected raw settings required')
        return _current_window(c,self.resolver,self.observer,min(self.context.phase_expires_at,
            self.vision_policy.expires_at,self.appointment.expires_at))

    def read_pdf_views(self):
        from oracle_brain.operating_model.artifact_storage import FileBlobStore,OriginalObjectRefV1,ReservationOriginalObjectRefV1
        from .raw_original_views_v1 import render_raw_pdf_views_v1
        self.current_window()
        c=self.config;r=self.context.job.raw_ref
        capability=self.resolver.original_revision_access_v1(r.source_id,r.revision)
        reservation=UUID(capability['private_object_key'].split('/')[-1])
        ref=ReservationOriginalObjectRefV1(OriginalObjectRefV1(r.workspace_id,r.source_id,r.revision,
            r.original_sha256,r.byte_count,r.media_type,c.storage_profile_hash),reservation)
        _require(ref.key==capability['private_object_key'],'exact actual original storage key required')
        store=FileBlobStore._from_provisioned_original_root(Path(c.original_root),c.original_root_identity)
        observation=canonical_bytes({'schema_version':1,'purpose':'original-intake-byte-custody-v1',
            'reservation_id':str(reservation),'source_id':str(r.source_id),'workspace_id':str(r.workspace_id),
            'revision':r.revision,'private_object_key':ref.key,'original_sha256':r.original_sha256,
            'byte_count':r.byte_count,'storage_profile_hash':c.storage_profile_hash})
        self.current_window()
        actual=_worker_file(Path(c.original_root)/'intake-observations'/str(reservation)/'custody.json',r.custody_locator_seal_sha256)
        _require(actual==observation,'actual intake original custody differs')
        self.current_window()  # Fresh complete population immediately before original bytes.
        raw=store._read_original_bytes(ref)
        rendered=render_raw_pdf_views_v1(raw,r,expected_view_policy_hash=self.context.view_policy_hash)
        self.current_window()
        return rendered

def _current_window(c,resolver,observer,phase_horizon):
    before=resolver.original_population_current_v1(c.population.population_id)
    witness=observer.current(c.population)
    after=resolver.original_population_current_v1(c.population.population_id)
    now=datetime.now(timezone.utc)
    _require(before.population==after.population==c.population
        and before.actual_principal_id==after.actual_principal_id==c.actor_id
        and before.session_role==after.session_role==c.expected_session_role
        and before.original_allocation_hash==after.original_allocation_hash==c.original_allocation_hash
        and before.original_horizon==after.original_horizon==c.original_horizon,
        'actual complete raw population changed')
    horizon=min(before.valid_until,after.valid_until,c.expires_at,c.original_horizon,phase_horizon,observer.admission.expires_at)
    current=min(horizon,witness.expires_at)
    _require(now<current,'raw authorization expired at final current boundary')
    return RawOriginalAuthorityWindowV1(current,horizon,digest(after.model_dump(mode='json')),
        digest(witness.model_dump(mode='json')))

def load_raw_original_provider_settings_v1(config_path,expected_config_sha256,*,appointment_path,
        expected_appointment_sha256,issuer_actor,reviewer_actor):
    _require(type(issuer_actor) is UUID and type(reviewer_actor) is UUID
        and all(type(h) is str and re.fullmatch(HASH,h) for h in (expected_config_sha256,expected_appointment_sha256)),
        'external raw startup pins required')
    c=_worker_json(config_path,expected_config_sha256,RawOriginalProviderConfigV1)
    a=_worker_json(appointment_path,expected_appointment_sha256,RawOriginalProviderAppointmentV1)
    now=datetime.now(timezone.utc)
    _require(a.config_sha256==expected_config_sha256 and a.context_sha256==c.context.sha256
        and a.issuer_actor==c.issuer_actor==issuer_actor and a.reviewer_actor==c.reviewer_actor==reviewer_actor
        and c.valid_from<=now<c.expires_at<=a.expires_at<=c.original_horizon and a.valid_from<=now,
        'independently appointed raw startup required')
    for name in ('population','actor_id','expected_session_role','original_allocation_hash','original_horizon'):
        _require(getattr(c,name)==getattr(a,name),'raw appointment/config differs')
    # Explicit appointment permits only own SQL URL/CA bootstrap reads.
    raw=_worker_file(c.database_url.path,c.database_url.sha256,limit=8192)
    _worker_file(c.database_ca.path,c.database_ca.sha256)
    from psycopg.conninfo import conninfo_to_dict
    try:
        url=raw.decode().strip();p=conninfo_to_dict(url);port=int(p.get('port') or 5432)
    except Exception:raise PermissionError('invalid protected raw SQL credential shape') from None
    _require(p.get('host')==c.database_hostname and port==c.database_port and p.get('dbname')==c.database_name
        and p.get('user')==c.expected_session_role and p.get('sslmode')=='verify-full'
        and p.get('sslrootcert')==c.database_ca.path,'exact own raw TLS SQL target required')
    binding=OriginalSourceBindingV1(c.population,c.actor_id,c.phase_purpose,c.expected_owner_role,
        c.expected_session_role,c.original_allocation_hash,c.original_horizon,c.expires_at)
    resolver=OriginalSourceResolverV1(url,binding=binding)
    resolver.original_population_current_v1(c.population.population_id)
    admission=_worker_json(c.observer_admission.path,c.observer_admission.sha256,RawOriginalObserverAdmissionV1)
    _require(admission.population==c.population and admission.principal_id==c.actor_id
        and admission.client_uri==c.observer_tls.client_uri and admission.observer_uri==c.observer_tls.server_uri,
        'independent raw observer subject/target differs')
    t=c.observer_tls
    for f in (t.ca,t.certificate,t.key):_worker_file(f.path,f.sha256)
    tls=PurposeTLSBindingV2(t.hostname,t.port,t.server_uri,t.client_uri,Path(t.ca.path),Path(t.certificate.path),Path(t.key.path),timeout=5)
    replay=DurableNonceSequenceV2(c.observer_spool,namespace=c.observer_namespace,
        appointment_hash=c.observer_admission.sha256,minimum_sequence=admission.minimum_sequence,
        initialization_receipt_hash=c.observer_initialization_hash)
    observer=RawOriginalCurrentnessConsumerV1(admission=admission,trusted_admission_hash=c.observer_admission.sha256,
        transport=RawOriginalObserverClientV1(tls),replay=replay)
    _current_window(c,resolver,observer,c.expires_at)
    context=_worker_json(c.context.path,c.context.sha256,RawOriginalPhaseContextV1)
    policy=_worker_json(c.vision_policy.path,c.vision_policy.sha256,RawVisionTokenPolicyV1)
    _require(context.population==c.population and context.actor_id==c.actor_id
        and context.expected_session_role==c.expected_session_role and context.job.purpose==c.phase_purpose
        and context.original_allocation_hash==c.original_allocation_hash and context.original_horizon==c.original_horizon
        and context.vision_token_policy_hash==c.vision_policy.sha256,'actual raw context/startup differs')
    settings=RawOriginalProviderSettingsV1(c,Path(config_path),expected_config_sha256,Path(appointment_path),
        expected_appointment_sha256,a,resolver,observer,context,policy)
    settings.current_window()
    return settings
