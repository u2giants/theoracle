"""Single-principal result startup. Consumes appointments; never issues them."""
from dataclasses import dataclass,field
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import UUID
import os,stat
from pydantic import AwareDatetime,Field,field_validator,model_validator
from oracle_brain.operating_model.contracts import StrictRecord
from oracle_brain.operating_model.contracts import ReplacementExecutorTargetV1
from .paid_executor_v3 import PaidExecutorSettingsV3,load_paid_executor_settings_v3,_executor_bootstrap_v3
from .purpose_journey_v2 import _worker_json,_require
HASH=r'^[a-f0-9]{64}$'

class ProtectedReplacementResultConfigV1(StrictRecord):
    schema_version:Literal[1]
    purpose:Literal['replacement-protected-result-v1']
    principal_id:UUID
    workspace_id:UUID
    journey_id:UUID
    population_sha256:str=Field(pattern=HASH)
    original_root_hash:str=Field(pattern=HASH)
    executor_config_file:str
    executor_config_sha256:str=Field(pattern=HASH)
    executor_appointment_file:str
    executor_appointment_sha256:str=Field(pattern=HASH)
    executor_issuer_actor:UUID
    executor_reviewer_actor:UUID
    executor_login:str=Field(min_length=1,max_length=63)
    executor_runtime_hash:str=Field(pattern=HASH)
    model_id:UUID
    model_version:int=Field(ge=1)
    model_content_hash:str=Field(pattern=HASH)
    projection_digest:str=Field(pattern=HASH)
    ack_event_id:UUID
    summary_artifact_id:UUID
    summary_version:int=Field(ge=1)
    summary_content_hash:str=Field(pattern=HASH)
    workflow_id:str=Field(min_length=1,max_length=200)
    listen_host:str
    listen_port:int=Field(ge=1,le=65535)
    client_uri:str=Field(pattern=r'^spiffe://oracle/')
    client_certificate_sha256:str=Field(pattern=HASH)
    server_uri:str=Field(pattern=r'^spiffe://oracle/')
    server_certificate_file:str
    server_certificate_sha256:str=Field(pattern=HASH)
    server_key_file:str
    server_key_sha256:str=Field(pattern=HASH)
    client_ca_file:str
    client_ca_sha256:str=Field(pattern=HASH)
    nonce_root:str
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    original_horizon:AwareDatetime

    @field_validator('schema_version',mode='before')
    @classmethod
    def version(cls,v):
        if type(v) is not int or v!=1:raise ValueError('exact result startup version required')
        return v

    @model_validator(mode='after')
    def closed(self):
        if (not self.valid_from<self.expires_at<=self.original_horizon
                or len({self.principal_id,self.issuer_actor,self.reviewer_actor})!=3
                or self.client_uri==self.server_uri):
            raise ValueError('separate finite result appointment required')
        import ipaddress
        ipaddress.ip_address(self.listen_host)
        paths=[self.executor_config_file,self.executor_appointment_file,self.server_certificate_file,
            self.server_key_file,self.client_ca_file,self.nonce_root]
        if any(not p.startswith('/') or '..' in Path(p).parts for p in paths) or len(set(paths))!=len(paths):
            raise ValueError('exact separate result startup paths required')
        return self

class ProtectedReplacementResultAppointmentV1(StrictRecord):
    schema_version:Literal[1]
    purpose:Literal['replacement-protected-result-v1']
    config_sha256:str=Field(pattern=HASH)
    principal_id:UUID
    workspace_id:UUID
    journey_id:UUID
    executor_config_sha256:str=Field(pattern=HASH)
    executor_appointment_sha256:str=Field(pattern=HASH)
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    @field_validator('schema_version',mode='before')
    @classmethod
    def version(cls,v):return ProtectedReplacementResultConfigV1.version(v)


def _appointment(c,a,config_hash,issuer,reviewer,now):
    _require(type(c) is ProtectedReplacementResultConfigV1 and type(a) is ProtectedReplacementResultAppointmentV1,
        'actual fixed result startup records required')
    _require(a.config_sha256==config_hash and (c.issuer_actor,c.reviewer_actor)==(issuer,reviewer)
        and all(getattr(a,k)==getattr(c,k) for k in ('principal_id','workspace_id','journey_id',
            'executor_config_sha256','executor_appointment_sha256','issuer_actor','reviewer_actor'))
        and max(c.valid_from,a.valid_from)<=now<min(c.expires_at,a.expires_at,c.original_horizon)
        and a.expires_at<=c.original_horizon,'current independent result appointment differs')


def _current_registered_target(c,e,resolver,semantic):
    now=datetime.now(timezone.utc)
    _require(c.executor_runtime_hash==e.runtime_hash and c.executor_login==e.expected_session_role
        and c.principal_id==e.actor_id and c.workspace_id==e.workspace_id
        and c.original_root_hash==e.original_root_hash and c.original_horizon==e.original_horizon,
        'exact result executor identity differs')
    _require(e.semantic_admission_hash in semantic.current(now),'current result semantic admission required')
    # This fixed own-role getter is independently admitted in SQL. Missing
    # rollout is a refusal, never config or browser tuple authority.
    method=getattr(resolver,'replacement_executor_target_v1',None)
    _require(callable(method),'current executor run authority unavailable')
    target=method(c.journey_id)
    _require(type(target) is ReplacementExecutorTargetV1,'actual current executor run metadata required')
    _require((target.run_id,target.requester_principal_id,target.workspace_id,target.population_sha256)==
        (c.journey_id,c.principal_id,c.workspace_id,c.population_sha256)
        and (target.model_id,target.model_version,target.model_content_hash,target.projection_digest,target.ack_event_id)==
        (c.model_id,c.model_version,c.model_content_hash,c.projection_digest,c.ack_event_id)
        and len(target.source_refs)==len(e.source_refs) and set(target.source_refs)==set(e.source_refs),
        'current independently admitted result target differs')
    summaries=[t for t in target.summary_targets if (t.summary_artifact_id,t.summary_version,t.summary_content_hash)==
        (c.summary_artifact_id,c.summary_version,c.summary_content_hash)]
    appointed=[t for t in e.summary_targets if (t.artifact_id,t.artifact_version,t.content_hash)==
        (c.summary_artifact_id,c.summary_version,c.summary_content_hash)]
    _require(len(appointed)==1,'exact executor-appointed summary required before private bytes')
    _require(len(summaries)==1 and (summaries[0].qualified_parent_id,summaries[0].qualified_parent_version,
        summaries[0].qualified_parent_content_hash)==(c.model_id,c.model_version,c.model_content_hash),
        'current independently registered summary differs')
    _require(target.state=='delivered' and not target.answer_hold and not target.cancelled,
        'current result is unavailable')
    _require(target.checked_at<=datetime.now(timezone.utc)<min(target.valid_until,semantic.valid_until(datetime.now(timezone.utc))),'current result target expired')
    return target


@dataclass(frozen=True)
class ProtectedReplacementResultSettingsV1:
    config:ProtectedReplacementResultConfigV1
    config_path:Path
    config_sha256:str
    appointment_path:Path
    appointment_sha256:str
    issuer_actor:UUID
    reviewer_actor:UUID
    executor:PaidExecutorSettingsV3=field(repr=False)
    nonce_identity:tuple

    def current_target(self):
        c=self.config;now=datetime.now(timezone.utc)
        _require(type(self.executor) is PaidExecutorSettingsV3,'actual own executor required')
        _require(_worker_json(self.config_path,self.config_sha256,ProtectedReplacementResultConfigV1)==c,
            'result startup changed')
        a=_worker_json(self.appointment_path,self.appointment_sha256,ProtectedReplacementResultAppointmentV1)
        _appointment(c,a,self.config_sha256,self.issuer_actor,self.reviewer_actor,now)
        e=self.executor.config
        _require((e.actor_id,e.workspace_id,e.expected_session_role,e.runtime_hash,e.original_root_hash)==
            (c.principal_id,c.workspace_id,c.executor_login,c.executor_runtime_hash,c.original_root_hash)
            and self.executor.config_sha256==c.executor_config_sha256
            and self.executor.appointment_sha256==c.executor_appointment_sha256,'exact independently appointed executor differs')
        current_until=self.executor.authorize_current()
        target=_current_registered_target(c,e,self.executor.resolver,self.executor.semantic)
        root=Path(c.nonce_root);info=root.lstat()
        _require(root.resolve()==root and stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid()
            and not info.st_mode&0o077 and (info.st_dev,info.st_ino,info.st_uid,info.st_mode)==self.nonce_identity,
            'preexisting exact result nonce custody changed')
        horizon=min(current_until,target.valid_until,c.expires_at,a.expires_at,c.original_horizon)
        _require(datetime.now(timezone.utc)<horizon,'current result authority expired')
        return target,horizon


def load_protected_replacement_result_settings_v1(config_path,expected_config_sha256,*,appointment_path,
        expected_appointment_sha256,issuer_actor,reviewer_actor):
    import re
    _require(all(type(v) is str and re.fullmatch(HASH,v) for v in (expected_config_sha256,expected_appointment_sha256))
        and type(issuer_actor) is UUID and type(reviewer_actor) is UUID and issuer_actor!=reviewer_actor,
        'external protected result pins required')
    c=_worker_json(config_path,expected_config_sha256,ProtectedReplacementResultConfigV1)
    a=_worker_json(appointment_path,expected_appointment_sha256,ProtectedReplacementResultAppointmentV1)
    _appointment(c,a,expected_config_sha256,issuer_actor,reviewer_actor,datetime.now(timezone.utc))
    # Existing executor appointment controls its sole SQL bootstrap, then own
    # actual source/registry checks before graph credentials and qualified bytes.
    ec,_,resolver,semantic=_executor_bootstrap_v3(c.executor_config_file,c.executor_config_sha256,
        appointment_path=c.executor_appointment_file,expected_appointment_sha256=c.executor_appointment_sha256,
        issuer_actor=c.executor_issuer_actor,reviewer_actor=c.executor_reviewer_actor)
    _current_registered_target(c,ec,resolver,semantic)  # BEFORE any qualified/graph private bytes.
    executor=load_paid_executor_settings_v3(c.executor_config_file,c.executor_config_sha256,
        appointment_path=c.executor_appointment_file,expected_appointment_sha256=c.executor_appointment_sha256,
        issuer_actor=c.executor_issuer_actor,reviewer_actor=c.executor_reviewer_actor)
    root=Path(c.nonce_root);info=root.lstat()
    _require(root.resolve()==root and stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid()
        and not info.st_mode&0o077,'preexisting private result nonce root required')
    settings=ProtectedReplacementResultSettingsV1(c,Path(config_path),expected_config_sha256,
        Path(appointment_path),expected_appointment_sha256,issuer_actor,reviewer_actor,executor,
        (info.st_dev,info.st_ino,info.st_uid,info.st_mode))
    settings.current_target()
    return settings
