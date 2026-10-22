"""Fixed read-only current queue endpoint for separately installed local loops.

No SQL grant, process liveness assertion, effect body or authority is issued.
The independent observer still verifies actual process identity and current SQL.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
from typing import Literal
from uuid import UUID
import json
from pydantic import AwareDatetime,Field,model_validator,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.protected_sql_connection_v1 import _connection_v1
from oracle_brain.operating_model.request_deadline_v1 import sql_execute_v1,request_remaining_v1
from .meeting_capture_v1 import MeetingCaptureSettingsV1,MeetingHeadV1,MeetingDueStopV1
from .meeting_supervisor_observer_v1 import supervision_queue_commitment_v1
from .parent_observer_v2 import MeetingSupervisorScopeV1
from .original_intake_v1 import _pinned,_parse,_context_horizon
from .replacement_request_service_v1 import RequesterPeerProfileV1,_load_peer_settings_v1
from ._protected_control_listener_v1 import _protected_control_listener_v1

HASH=r'^[a-f0-9]{64}$'
PROCESS=Literal['meeting-scheduler-process-v1','meeting-stop-worker-process-v1']


class MeetingSupervisionConfigV1(StrictRecord):
    purpose:Literal['meeting-supervision-queue-consumer-v1']
    capture_config_sha256:str=Field(pattern=HASH)
    process_purpose:PROCESS
    scope:MeetingSupervisorScopeV1
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    @model_validator(mode='after')
    def independently_bounded(self):
        end=self.scope.capture_until if self.process_purpose=='meeting-scheduler-process-v1' else self.scope.stop_until
        if self.issuer_actor==self.reviewer_actor or not self.scope.stop_valid_from<=self.valid_from<self.expires_at<=end:
            raise ValueError('independent original local-process queue installation required')
        return self


@dataclass(frozen=True)
class MeetingSupervisionSettingsV1:
    capture:MeetingCaptureSettingsV1
    config:MeetingSupervisionConfigV1
    path:str
    sha256:str
    def current(self):
        request_remaining_v1(required=False)
        c=self.config;s=self.capture;scope=c.scope
        if _parse(MeetingSupervisionConfigV1,_pinned(self.path,self.sha256))!=c or c.capture_config_sha256!=s.config_sha256:
            raise PermissionError('fixed supervisor queue installation changed')
        principal=scope.scheduler_id if c.process_purpose=='meeting-scheduler-process-v1' else scope.stop_owner_id
        if (s.config.channel!='worker' or s.host.config.principal_id!=principal or principal in (c.issuer_actor,c.reviewer_actor)
                or s.host.config.workspace_id!=scope.workspace_id or s.config.meeting_id!=scope.meeting_id
                or s.config.provider_account!=scope.provider_account or s.config.capture_until!=scope.capture_until
                or scope.original_horizon>s.config.original_horizon):
            raise PermissionError('independently installed exact local-process identity required')
        end=min(s.current(),c.expires_at,scope.capture_until if c.process_purpose=='meeting-scheduler-process-v1' else scope.stop_until)
        if not c.valid_from<=datetime.now(timezone.utc)<end:raise PermissionError('original local-process queue window elapsed')
        return end


def load_meeting_supervision_settings_v1(capture,path,sha256):
    if type(capture) is not MeetingCaptureSettingsV1:raise PermissionError('same current capture owner required')
    s=MeetingSupervisionSettingsV1(capture,_parse(MeetingSupervisionConfigV1,_pinned(path,sha256)),str(path),sha256)
    s.current();return s


class MeetingSupervisionRequestV1(StrictRecord):
    caller_deadline:AwareDatetime
    @field_validator('schema_version',mode='before')
    @classmethod
    def integer_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('actual queue schema required')
        return value


class MeetingSupervisionPacketV1(StrictRecord):
    purpose:Literal['meeting-supervision-current-queue-v1']
    principal_id:UUID
    workspace_id:UUID
    meeting_id:UUID
    process_purpose:PROCESS
    scope_sha256:str=Field(pattern=HASH)
    runtime_sha256:str=Field(pattern=HASH)
    config_sha256:str=Field(pattern=HASH)
    queue_observation_sha256:str=Field(pattern=HASH)
    version:int=Field(ge=1,le=16384)
    capture_until:AwareDatetime
    stop_until:AwareDatetime
    due_at:AwareDatetime
    valid_until:AwareDatetime
    observation_only:Literal[True]
    remote_stop_proven:Literal[False]
    @field_validator('observation_only','remote_stop_proven',mode='before')
    @classmethod
    def actual_boolean(cls,value):
        if type(value) is not bool:raise ValueError('literal queue observation required')
        return value


class MeetingSupervisionFactoryV1:
    def __init__(self,settings):
        if type(settings) is not MeetingSupervisionSettingsV1:raise PermissionError('same fixed local-process queue settings required')
        settings.current();self.settings=settings
    def current_queue_v1(self,*,caller_deadline):
        request_remaining_v1(required=True)
        from psycopg.conninfo import conninfo_to_dict
        s=self.settings;c=s.capture.host.config;scope=s.config.scope;deadline=caller_deadline
        if type(deadline) is not datetime or deadline.tzinfo is None or not datetime.now(timezone.utc)<deadline<=s.current():
            raise PermissionError('original supervision request window required')
        raw=_pinned(c.database_url.path,c.database_url.sha256,16384).decode('utf-8');_pinned(c.database_ca.path,c.database_ca.sha256,131072)
        target=conninfo_to_dict(raw)
        if target.get('sslrootcert')!=c.database_ca.path or target.get('user')!=c.expected_session_role:raise PermissionError('fixed current queue SQL target differs')
        with _connection_v1(raw,deadline) as conn:
            def execute(statement,args=None):
                s.current();return sql_execute_v1(conn,deadline,statement,args)
            actual=conn.info
            if (not conn.pgconn.ssl_in_use or actual.host!=target['host'] or actual.dbname!=target['dbname'] or actual.user!=target['user']
                    or actual.port!=int(target['port']) or target.get('hostaddr') and actual.hostaddr!=target['hostaddr']):
                raise PermissionError('actual current queue SQL target differs')
            if execute("SELECT SESSION_USER::text,CURRENT_USER::text,(SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2')").fetchone()!=(c.expected_session_role,c.expected_session_role,c.expected_owner_role):
                raise PermissionError('actual local-process SQL role differs')
            names=['oracle2.meeting_capture_read_v1(uuid,text,text,timestamptz)','oracle2.meeting_capture_due_stop_v1(uuid,text,timestamptz)']
            owners=execute('SELECT pg_get_userbyid(proowner),prosecdef FROM pg_proc WHERE oid=ANY(ARRAY(SELECT to_regprocedure(x) FROM unnest(%s::text[]) x))',(names,)).fetchall()
            if len(owners)!=2 or any(v!=(c.expected_owner_role,True) for v in owners):raise PermissionError('actual current queue owner differs')
            prefix=(s.capture.config.admission_id,s.capture.config.admission_sha256)
            def head():return MeetingHeadV1.model_validate_json(json.dumps(execute("SELECT oracle2.meeting_capture_read_v1(%s,%s,'supervise',%s)",(*prefix,deadline)).fetchone()[0]))
            before=head()
            due=MeetingDueStopV1.model_validate_json(json.dumps(execute('SELECT oracle2.meeting_capture_due_stop_v1(%s,%s,%s)',(*prefix,deadline)).fetchone()[0]))
            after=head()
            for record in (before,due,after):
                _context_horizon(s.capture.host,record.context)
                if record.meeting_id!=scope.meeting_id or record.capture_until!=scope.capture_until:raise PermissionError('actual queue scope differs')
            queue=supervision_queue_commitment_v1(before)
            if before.version<1 or supervision_queue_commitment_v1(after)!=queue or due.version!=before.version:
                raise PermissionError('actual current queue changed during observation')
            from oracle_brain.meetings.create_stop_relation import CreateOperationStopRelationV1
            if due.stop_relation is None:raise PermissionError('independently installed STOP relation missing')
            relation=CreateOperationStopRelationV1.model_validate_json(canonical_bytes(due.stop_relation))
            for field in ('workspace_id','meeting_id','provider_account','create_operation_id','create_request_sha256','scheduler_id','scheduler_runtime_sha256','scheduler_config_sha256','stop_owner_id','stop_runtime_sha256','stop_config_sha256','capture_until','stop_valid_from','stop_until','original_horizon'):
                if getattr(scope,field)!=getattr(relation,field):raise PermissionError('actual installed queue/process scope differs')
            for field in ('scheduler_poll_seconds','stop_request_seconds','safety_allowance_seconds','stop_margin_seconds'):
                if getattr(scope,field)!=getattr(due,field):raise PermissionError('actual preinstalled polling and STOP margin differs')
            if (relation.sha256!=due.stop_mapping_sha256 or relation.supervision_scope_sha256!=digest(scope.model_dump(mode='json'))
                    or before.supervision_binding is None or before.supervision_binding.get('scope_sha256')!=relation.supervision_scope_sha256
                    or before.supervision_binding.get('stop_relation_sha256')!=relation.sha256):
                raise PermissionError('actual queue commitment differs from current installation')
            end=min(before.valid_until,due.valid_until,after.valid_until,deadline,s.current())
        s.current();_context_horizon(s.capture.host,after.context)
        scheduler=s.config.process_purpose=='meeting-scheduler-process-v1'
        return MeetingSupervisionPacketV1(purpose='meeting-supervision-current-queue-v1',principal_id=c.principal_id,workspace_id=c.workspace_id,
            meeting_id=scope.meeting_id,process_purpose=s.config.process_purpose,scope_sha256=relation.supervision_scope_sha256,
            runtime_sha256=scope.scheduler_runtime_sha256 if scheduler else scope.stop_runtime_sha256,
            config_sha256=scope.scheduler_config_sha256 if scheduler else scope.stop_config_sha256,
            queue_observation_sha256=queue,version=after.version,capture_until=scope.capture_until,stop_until=scope.stop_until,due_at=due.due_at,
            valid_until=end,observation_only=True,remote_stop_proven=False)


class MeetingSupervisionPeerProfileV1(RequesterPeerProfileV1):
    purpose:Literal['meeting-supervision-service-peer-v1']
    process_purpose:PROCESS
    supervision_config_sha256:str=Field(pattern=HASH)
    scope_sha256:str=Field(pattern=HASH)


@dataclass(frozen=True)
class _SupervisionPeerSettings:
    supervision:MeetingSupervisionSettingsV1
    peer:object
    @property
    def profile(self):return self.peer.profile
    def current(self):
        end=min(self.supervision.current(),self.peer.current());c=self.supervision.config;p=self.profile
        if type(p) is not MeetingSupervisionPeerProfileV1 or p.process_purpose!=c.process_purpose or p.supervision_config_sha256!=self.supervision.sha256 or p.scope_sha256!=digest(c.scope.model_dump(mode='json')):
            raise PermissionError('exact independently installed local-process peer required')
        return end


class _SupervisionAdapter:
    def __init__(self,settings):
        self.settings=settings;self.factory=MeetingSupervisionFactoryV1(settings.supervision)
    def execute_v1(self,raw):
        request_remaining_v1(required=True);q=_parse(MeetingSupervisionRequestV1,raw);self.settings.current()
        result=self.factory.current_queue_v1(caller_deadline=q.caller_deadline)
        request_remaining_v1(required=True);self.settings.current();return result


def _supervision_server(settings,path,sha256,purpose):
    if type(settings) is not MeetingSupervisionSettingsV1 or settings.config.process_purpose!=purpose:raise PermissionError('fixed source-selected local-process service required')
    peer=_load_peer_settings_v1(settings.capture.host,path,sha256,MeetingSupervisionPeerProfileV1)
    fixed=_SupervisionPeerSettings(settings,peer);fixed.current()
    return _protected_control_listener_v1(fixed,_SupervisionAdapter(fixed),path='/v1/replacement/meetings/supervision',
        parse_request=lambda raw:_parse(MeetingSupervisionRequestV1,raw),encode_response=lambda value:canonical_bytes(value.model_dump(mode='json')),
        maximum_request_bytes=4096,maximum_response_bytes=4096)


def protected_meeting_scheduler_supervision_server_v1(settings,path,sha256):
    return _supervision_server(settings,path,sha256,'meeting-scheduler-process-v1')


def protected_meeting_stop_supervision_server_v1(settings,path,sha256):
    return _supervision_server(settings,path,sha256,'meeting-stop-worker-process-v1')
