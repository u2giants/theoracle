"""Fixed compiler-owned paid projector startup. No issuer, provisioning or dispatch."""
from dataclasses import dataclass,field
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit,unquote
from uuid import UUID
import hashlib,ssl
from pydantic import Field,AwareDatetime,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,digest
from oracle_brain.operating_model.purpose_journey import PurposeWorkerJobV2
from .purpose_journey_v2 import CompilerWorkerSettingsV2,_worker_file,_worker_json,_require
from .paid_sdk_delivery_v3 import load_paid_sdk_bundle_v3

HASH=r'^[a-f0-9]{64}$'

class PaidProjectorAppointmentV3(StrictRecord):
    schema_version:Literal[3]=3
    purpose:Literal['replacement-documentary-projector-v3']='replacement-documentary-projector-v3'
    config_sha256:str=Field(pattern=HASH)
    worker_config_sha256:str=Field(pattern=HASH)
    job_hash:str=Field(pattern=HASH)
    workspace_id:UUID
    compiler_actor:UUID
    compiler_login:str=Field(min_length=1)
    runtime_hash:str=Field(pattern=HASH)
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    @model_validator(mode='after')
    def independent(self):
        if len({self.compiler_actor,self.issuer_actor,self.reviewer_actor})!=3 or self.valid_from>=self.expires_at:
            raise ValueError('distinct externally appointed projector scope required')
        return self

class PaidProjectorConfigV3(StrictRecord):
    schema_version:Literal[3]=3
    purpose:Literal['replacement-documentary-projector-v3']='replacement-documentary-projector-v3'
    worker_config_sha256:str=Field(pattern=HASH)
    job_hash:str=Field(pattern=HASH)
    workspace_id:UUID
    compiler_actor:UUID
    compiler_login:str=Field(min_length=1)
    runtime_hash:str=Field(pattern=HASH)
    artifact_id:UUID
    artifact_version:int=Field(strict=True,ge=1)
    content_hash:str=Field(pattern=HASH)
    projection_digest:str=Field(pattern=HASH)
    embedding_dispatch_id:UUID
    generation:UUID
    graph_name:str
    ontology_name:str
    graph_hostname:str=Field(min_length=1)
    graph_port:int=Field(strict=True,ge=1,le=65535)
    graph_username:str=Field(min_length=1)
    graph_url_file:str
    graph_url_sha256:str=Field(pattern=HASH)
    tls_ca_file:str
    tls_ca_sha256:str=Field(pattern=HASH)
    tls_certificate_file:str
    tls_certificate_sha256:str=Field(pattern=HASH)
    tls_key_file:str
    tls_key_sha256:str=Field(pattern=HASH)
    projector_id:UUID
    receipt_key_file:str
    receipt_key_sha256:str=Field(pattern=HASH)
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    @model_validator(mode='after')
    def exact_target(self):
        expected=f'oracle_processing_v1_{self.workspace_id.hex}_{self.artifact_id.hex}_{self.artifact_version}_{self.generation.hex}'
        if (self.graph_name!=expected or self.ontology_name!=expected+'__ontology'
                or len({self.compiler_actor,self.issuer_actor,self.reviewer_actor})!=3
                or self.valid_from>=self.expires_at):raise ValueError('exact bounded projector namespace required')
        paths=[self.graph_url_file,self.tls_ca_file,self.tls_certificate_file,self.tls_key_file,self.receipt_key_file]
        if len(set(paths))!=len(paths) or any(not Path(p).is_absolute() for p in paths):
            raise ValueError('distinct exact private projector paths required')
        return self

@dataclass(frozen=True)
class PaidProjectorSettingsV3:
    config:PaidProjectorConfigV3
    config_path:Path
    config_sha256:str
    appointment_path:Path
    appointment_sha256:str
    issuer_actor:UUID
    reviewer_actor:UUID
    worker:CompilerWorkerSettingsV2
    job:PurposeWorkerJobV2
    bundle:object
    valid_until:datetime
    graph_url:str=field(repr=False)
    receipt_secret:bytes=field(repr=False)
    tls_context:ssl.SSLContext=field(repr=False)

    def current(self):
        self.worker.authorize(self.job)
        now=datetime.now(timezone.utc)
        self.worker.custody_horizon(self.job);self.worker.semantic.current(now)
        config=_worker_json(self.config_path,self.config_sha256,PaidProjectorConfigV3)
        appointment=_worker_json(self.appointment_path,self.appointment_sha256,PaidProjectorAppointmentV3)
        _require(config==self.config and appointment.config_sha256==self.config_sha256
            and appointment.issuer_actor==self.issuer_actor and appointment.reviewer_actor==self.reviewer_actor
            and appointment.worker_config_sha256==self.worker.config_sha256
            and appointment.job_hash==digest(self.job.model_dump(mode='json'))
            and appointment.valid_from<=now<min(appointment.expires_at,self.valid_until),
            'current exact projector appointment/config required')
        self.bundle.qualification_guard(self.bundle.manifest,self.bundle.payload,self.job.actor_id,now)
        for path,seal in ((config.graph_url_file,config.graph_url_sha256),(config.tls_ca_file,config.tls_ca_sha256),
                         (config.tls_certificate_file,config.tls_certificate_sha256),(config.tls_key_file,config.tls_key_sha256),
                         (config.receipt_key_file,config.receipt_key_sha256)):
            _worker_file(path,seal)
        _require(datetime.now(timezone.utc)<self.valid_until,'original projector horizon expired')
        return self.valid_until


def load_paid_projector_settings_v3(config_path,expected_config_sha256,*,appointment_path,
        expected_appointment_sha256,issuer_actor,reviewer_actor,worker,job):
    """Hashes/issuer pins come from protected launcher appointment, never JSON itself."""
    _require(type(worker) is CompilerWorkerSettingsV2 and type(job) is PurposeWorkerJobV2
        and job.phase=='compile' and type(issuer_actor) is UUID and type(reviewer_actor) is UUID,
        'actual compiler worker and protected external projector pins required')
    worker.authorize(job)
    worker.custody_horizon(job)
    now=datetime.now(timezone.utc)
    worker.semantic.current(now)
    appointment=_worker_json(appointment_path,expected_appointment_sha256,PaidProjectorAppointmentV3)
    _require(appointment.config_sha256==expected_config_sha256
        and appointment.worker_config_sha256==worker.config_sha256
        and appointment.job_hash==digest(job.model_dump(mode='json'))
        and appointment.workspace_id==job.workspace_id and appointment.compiler_actor==job.actor_id
        and appointment.compiler_login==worker.config.expected_session_role
        and appointment.runtime_hash==worker.config.runtime_hash
        and appointment.issuer_actor==issuer_actor and appointment.reviewer_actor==reviewer_actor
        and appointment.valid_from<=now<appointment.expires_at<=job.original_horizon,
        'exact current independently appointed projector startup required')
    config=_worker_json(config_path,expected_config_sha256,PaidProjectorConfigV3)
    for name in ('worker_config_sha256','job_hash','workspace_id','compiler_actor','compiler_login','runtime_hash','issuer_actor','reviewer_actor'):
        _require(getattr(config,name)==getattr(appointment,name),'projector config/appointment scope differs')
    _require(config.valid_from<=now<config.expires_at<=appointment.expires_at,
        'current projector config window required')
    bundle=load_paid_sdk_bundle_v3(worker,job,artifact_id=config.artifact_id,
        artifact_version=config.artifact_version,embedding_dispatch_id=config.embedding_dispatch_id)
    _require(digest(bundle.payload)==config.content_hash
        and bundle.embedder.data.inventory.projection_digest==config.projection_digest,
        'projector target differs from current paid qualified artifact')
    horizon=min(bundle.valid_until,config.expires_at,appointment.expires_at,
        worker.authority_horizon(job),worker.custody_horizon(job),worker.semantic.valid_until(now))
    _require(datetime.now(timezone.utc)<horizon,'projector authority expired before credential read')
    # Existing exact-file protection rejects symlink parents/leaves, aliases,
    # foreign ownership, nlink !=1, nonprivate modes, mutation and oversized data.
    url=_worker_file(config.graph_url_file,config.graph_url_sha256,limit=8192).decode().strip()
    parsed=urlsplit(url)
    _require(parsed.scheme=='rediss' and parsed.hostname==config.graph_hostname
        and (parsed.port or 6379)==config.graph_port and unquote(parsed.username or '')==config.graph_username
        and parsed.password is not None and parsed.path in ('','/') and not parsed.query and not parsed.fragment,
        'exact TLS graph target and writer username required')
    ca=_worker_file(config.tls_ca_file,config.tls_ca_sha256,limit=1024*1024)
    cert=_worker_file(config.tls_certificate_file,config.tls_certificate_sha256,limit=1024*1024)
    key=_worker_file(config.tls_key_file,config.tls_key_sha256,limit=1024*1024)
    secret=_worker_file(config.receipt_key_file,config.receipt_key_sha256,limit=8192)
    _require(len(secret)>=32,'existing projector receipt key required')
    context=ssl.create_default_context(cadata=ca.decode())
    context.check_hostname=True;context.verify_mode=ssl.CERT_REQUIRED
    context.load_cert_chain(config.tls_certificate_file,config.tls_key_file)
    # Recheck exact bytes after path-based SSL loading, never trust an earlier
    # file digest after a credential/CA path substitution.
    _require(_worker_file(config.tls_certificate_file,config.tls_certificate_sha256)==cert
        and _worker_file(config.tls_key_file,config.tls_key_sha256)==key,'TLS identity changed during startup')
    worker.authorize(job);worker.custody_horizon(job);worker.semantic.current(datetime.now(timezone.utc))
    bundle.qualification_guard(bundle.manifest,bundle.payload,job.actor_id,datetime.now(timezone.utc))
    _require(datetime.now(timezone.utc)<horizon,'projector original horizon expired during credential read')
    return PaidProjectorSettingsV3(config,Path(config_path),expected_config_sha256,Path(appointment_path),
        expected_appointment_sha256,issuer_actor,reviewer_actor,worker,job,bundle,horizon,url,secret,context)


from .paid_sdk_delivery_v3 import CurrentPaidSDKGuardV3

class CurrentPaidProjectorGuardV3(CurrentPaidSDKGuardV3):
    def __init__(self,settings):
        _require(type(settings) is PaidProjectorSettingsV3,'protected projector settings required')
        self.projector=settings
        super().__init__(settings.bundle.qualification_guard.combined)
    def __call__(self,manifest,payload,principal,now):
        self.projector.current()
        return super().__call__(manifest,payload,principal,now)
    def valid_until(self,manifest,payload,principal,now):
        return min(self.projector.current(),super().valid_until(manifest,payload,principal,now))


def _paid_projector_projection_v3(settings,*,signed_receipt=None):
    from graphrag_sdk import ConnectionConfig
    from oracle_brain.operating_model.sdk_projection import PaidProcessingSDKProjectionV3
    _require(type(settings) is PaidProjectorSettingsV3,'exact protected projector settings required')
    horizon=settings.current();c=settings.config
    remaining=(horizon-datetime.now(timezone.utc)).total_seconds()
    _require(remaining>0,'projector original horizon expired')
    parsed=urlsplit(settings.graph_url)
    connection=ConnectionConfig(host=c.graph_hostname,port=c.graph_port,
        username=unquote(parsed.username),password=unquote(parsed.password),graph_name=c.graph_name,
        ssl=True,ssl_cert_reqs='required',ssl_check_hostname=True,ssl_ca_certs=c.tls_ca_file,
        ssl_certfile=c.tls_certificate_file,ssl_keyfile=c.tls_key_file,
        query_timeout_ms=max(1,min(30000,int(remaining*1000))),pool_timeout=min(30.0,remaining),retry_count=0)
    projection=PaidProcessingSDKProjectionV3(settings.graph_url,workspace_id=c.workspace_id,
        artifact_id=c.artifact_id,artifact_version=c.artifact_version,generation=c.generation,
        embedder=settings.bundle.embedder,qualification_guard=CurrentPaidProjectorGuardV3(settings),
        read_only=signed_receipt is not None,signed_receipt=signed_receipt,
        receipt_secret=settings.receipt_secret,connection_config=connection)
    settings.current()
    return projection


def build_paid_projector_projection_v3(settings):
    """Fixed initial construction; actual leased handler owns whole-await timeout/ACK."""
    return _paid_projector_projection_v3(settings)


def reload_paid_projector_projection_v3(settings):
    """Genuine committed compiler ACK only, never caller supplied receipt/cache."""
    _require(type(settings) is PaidProjectorSettingsV3,'exact protected projector settings required')
    settings.current();c=settings.config
    # This exact compiler-only SQL getter is a required dependency; absence or
    # revocation fails closed rather than opening an owner connection/fallback.
    delivered=settings.worker.resolver.projection_receipt_v3(c.workspace_id,c.artifact_id,c.artifact_version)
    receipt={**delivered.receipt.model_dump(mode='json'),'signature':delivered.signature}
    _require(receipt['graph_name']==c.graph_name and receipt['projector_id']==str(c.projector_id),
        'committed projector receipt belongs to another target/identity')
    settings.current()
    return _paid_projector_projection_v3(settings,signed_receipt=receipt)
