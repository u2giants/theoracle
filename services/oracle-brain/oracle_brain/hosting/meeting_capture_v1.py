"""Dedicated operational capture consumer. Exact external pins, never a grant.

No provider calls or learning occur in SQL transactions. Raw bytes are retained
by the existing immutable private-byte owner; native text qualification is a
separate, independently appointed S06 operation.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
import hashlib,json,time
from pathlib import Path
from typing import Literal
from uuid import UUID,uuid5,NAMESPACE_URL
from pydantic import AwareDatetime,Field,model_validator,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes
from oracle_brain.operating_model.artifact_storage import _write_private_at,_parent_fd,_read_private_at
from oracle_brain.meetings.capture_contracts import HASH,MAX_RAW
from oracle_brain.meetings.participant_epoch import LiveParticipantEpochV1
from .gateway import unique_object
from .original_intake_v1 import OriginalIntakeSettingsV1,_pinned,_parse,RequesterContextV1,_context_horizon

class MeetingCaptureConfigV1(StrictRecord):
    purpose:Literal['meeting-capture-consumer-v1']
    host_config_sha256:str=Field(pattern=HASH)
    host_appointment_sha256:str=Field(pattern=HASH)
    admission_id:UUID
    admission_sha256:str=Field(pattern=HASH)
    meeting_id:UUID
    consent_packet_sha256:str=Field(pattern=HASH)
    capture_until:AwareDatetime
    final_artifact_file:str|None=None
    final_artifact_sha256:str|None=Field(default=None,pattern=HASH)
    participant_epoch_file:str|None=None
    participant_epoch_sha256:str|None=Field(default=None,pattern=HASH)
    final_mapping_id:UUID|None=None
    speaker_mapping_file:str|None=None
    speaker_mapping_sha256:str|None=Field(default=None,pattern=HASH)
    provider:Literal['recall','graph']
    provider_account:str=Field(min_length=1,max_length=256)
    tenant_id:str=Field(min_length=1,max_length=256)
    provider_meeting_id:str=Field(min_length=1,max_length=2048)
    bot_id:str|None=Field(min_length=1,max_length=256)
    verifier_secret_sha256:str|None=Field(pattern=HASH)
    channel:Literal['employee-control','provider-ingress','worker']
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    original_horizon:AwareDatetime
    @model_validator(mode='after')
    def exact_scope(self):
        if not self.valid_from<self.capture_until<=self.original_horizon:raise ValueError('fixed original capture end required')
        if self.issuer_actor==self.reviewer_actor or not self.valid_from<self.expires_at<=self.original_horizon:raise ValueError('independent finite meeting appointment required')
        for v in (self.provider_account,self.tenant_id,self.provider_meeting_id,self.bot_id):
            if v is not None and (v!=v.strip() or any(ord(c)<32 or ord(c)==127 for c in v)):raise ValueError('canonical meeting identity required')
        if (self.final_artifact_file is None)!=(self.final_artifact_sha256 is None):raise ValueError('exact final selection file and hash required together')
        if (self.participant_epoch_file is None)!=(self.participant_epoch_sha256 is None):raise ValueError('exact live participant epoch file and hash required together')
        if len({self.speaker_mapping_file is None,self.speaker_mapping_sha256 is None,self.final_mapping_id is None})!=1:raise ValueError('exact current final mapping ID, file and hash required together')
        if self.channel=='provider-ingress' and (self.bot_id is None or self.verifier_secret_sha256 is None):raise ValueError('separate installed ingress identity required')
        return self
@dataclass(frozen=True)
class MeetingCaptureSettingsV1:
    host:OriginalIntakeSettingsV1
    config:MeetingCaptureConfigV1
    config_path:Path
    config_sha256:str
    def current(self):
        c=_parse(MeetingCaptureConfigV1,_pinned(self.config_path,self.config_sha256))
        if c!=self.config or c.host_config_sha256!=self.host.config_sha256 or c.host_appointment_sha256!=self.host.appointment_sha256:raise PermissionError('meeting installation changed')
        if self.host.config.principal_id in (c.issuer_actor,c.reviewer_actor):raise PermissionError('meeting actor cannot appoint itself')
        now=datetime.now(timezone.utc);until=min(self.host.current(),c.expires_at,c.original_horizon)
        if not c.valid_from<=now<until:raise PermissionError('meeting installation expired')
        return until

def load_meeting_capture_settings_v1(host,path,sha256):
    if type(host) is not OriginalIntakeSettingsV1:raise TypeError('exact independently installed host pins required')
    settings=MeetingCaptureSettingsV1(host,_parse(MeetingCaptureConfigV1,_pinned(path,sha256)),Path(path),sha256)
    settings.current();return settings
class MeetingMutationV1(StrictRecord):
    context:RequesterContextV1
    capture_until:AwareDatetime
    meeting_id:UUID
    event_id:UUID
    version:int=Field(ge=1,le=16384)
    state:Literal['invited','joining','pending_mapping','waiting_room','recording_permission_pending','recording_permission_denied','capturing','capture_ended','processing','final_artifact_pending','capture_status_unknown','review','failed','UNKNOWN','cancelled']
    created:bool
    valid_until:AwareDatetime
class MeetingHeadV1(StrictRecord):
    context:RequesterContextV1
    capture_until:AwareDatetime
    ingress_binding:dict|None
    supervision_binding:dict|None
    artifact_binding:dict|None
    meeting_id:UUID
    version:int=Field(ge=0,le=16384)
    state:Literal['not_invited','invited','joining','pending_mapping','waiting_room','recording_permission_pending','recording_permission_denied','capturing','capture_ended','processing','final_artifact_pending','capture_status_unknown','review','failed','UNKNOWN','cancelled']
    pending_ingress:tuple[UUID,...]=Field(max_length=4096)
    valid_until:AwareDatetime
class MeetingReceiptV1(StrictRecord):
    context:RequesterContextV1
    capture_until:AwareDatetime
    meeting_id:UUID
    event_id:UUID
    payload:dict|None
    action:Literal['ingress','final_artifact']|None
    payload_sha256:str|None=Field(pattern=HASH)
    valid_until:AwareDatetime
class MeetingCurrentFinalMappingSQLV1(StrictRecord):
    receipt:MeetingReceiptV1
    mapping:dict
    mapping_sha256:str=Field(pattern=HASH)
    valid_until:AwareDatetime
    @property
    def context(self):return self.receipt.context
    @property
    def meeting_id(self):return self.receipt.meeting_id
    @property
    def capture_until(self):return self.receipt.capture_until
class MeetingCurrentCaptureV1(StrictRecord):
    workspace_id:UUID
    meeting_id:UUID
    provider:Literal['recall','graph']
    provider_account:str
    tenant_id:str
    provider_meeting_id:str
    bot_id:str
    admission_id:UUID
    admission_sha256:str=Field(pattern=HASH)
    capture_event_id:UUID
    capture_event_sha256:str=Field(pattern=HASH)
    capture_revision:int=Field(ge=1,le=16384)
    valid_until:AwareDatetime
class MeetingCurrentTurnSQLV1(StrictRecord):
    capture:MeetingCurrentCaptureV1
    receipt:MeetingReceiptV1
    epoch:LiveParticipantEpochV1
    epoch_sha256:str=Field(pattern=HASH)
    valid_until:AwareDatetime
    @property
    def context(self):return self.receipt.context
    @property
    def meeting_id(self):return self.receipt.meeting_id
    @property
    def capture_until(self):return self.receipt.capture_until
class MeetingCurrentParticipantTurnV1(StrictRecord):
    purpose:Literal['meeting-only-current-participant-turn-v1']
    capture:MeetingCurrentCaptureV1
    raw_sha256:str=Field(pattern=HASH)
    participant_epoch_id:UUID
    participant_epoch_revision:int=Field(ge=1)
    participant_epoch_sha256:str=Field(pattern=HASH)
    participant_set_sha256:str=Field(pattern=HASH)
    valid_until:AwareDatetime
    normalized_sha256:str=Field(pattern=HASH)
    provider_speaker_id:str
    actor_id:UUID
    employee_identity_verified:Literal[False]
    attribution:Literal['workspace_actor']
    text:str=Field(min_length=1,max_length=1048576)
    language:str
    reported_only:Literal[True]
    qualification:Literal[False]
    shared_source_permission:Literal[False]
    @field_validator('reported_only','qualification','shared_source_permission','employee_identity_verified',mode='before')
    @classmethod
    def strict_observation(cls,v):
        if type(v) is not bool:raise ValueError('actual observation booleans required')
        return v

class MeetingPreStopObservationV1(StrictRecord):
    receipt_id:UUID
    claim_id:UUID
    operation_id:UUID
    bot_id:UUID
    metadata_sha256:str=Field(pattern=HASH)

class MeetingDueStopV1(StrictRecord):
    context:RequesterContextV1
    workspace_id:UUID
    meeting_id:UUID
    version:int=Field(ge=1,le=16384)
    capture_until:AwareDatetime
    stop_valid_from:AwareDatetime
    stop_until:AwareDatetime
    original_horizon:AwareDatetime
    due_at:AwareDatetime
    due:bool
    create_intent_id:UUID|None
    created_bot:dict|None
    pre_stop_observation:MeetingPreStopObservationV1|None=None
    stop_intent_id:UUID|None
    stop_observation_id:UUID|None
    stop_state:Literal['not_attempted','inflight','observed','UNKNOWN','terminal_observed']
    stop_mapping_sha256:str=Field(pattern=HASH)
    stop_relation:dict|None=None
    scheduler_poll_seconds:int=Field(ge=1,le=30)
    stop_request_seconds:int=Field(ge=1,le=30)
    safety_allowance_seconds:int=Field(ge=1,le=60)
    stop_margin_seconds:int=Field(ge=3,le=120)
    valid_until:AwareDatetime
    @model_validator(mode='after')
    def exact(self):
        from datetime import timedelta
        if (not self.stop_valid_from<self.due_at<self.capture_until<=self.stop_until<=self.original_horizon
            or self.due_at!=self.capture_until-timedelta(seconds=self.stop_margin_seconds)
            or self.stop_margin_seconds<self.scheduler_poll_seconds+self.stop_request_seconds+self.safety_allowance_seconds):raise ValueError('actual fixed STOP-only queue and full margin required')
        return self

class MeetingCaptureUnavailable(PermissionError):pass

class MeetingDeliverySQLV1(StrictRecord):
    context:RequesterContextV1
    capture_until:AwareDatetime
    meeting_id:UUID
    valid_until:AwareDatetime
    state:Literal['idle','prepared','claimed','inflight','observed','UNKNOWN']
    fresh_claim:bool
    worker_id:UUID
    operation_policy_sha256:str=Field(pattern=HASH)
    stop_mapping_sha256:str|None=Field(pattern=HASH)
    effect:Literal['capture-create','capture-leave','capture-retrieve']
    stage:Literal['-','pre-stop-consistency','post-stop-terminal']
    operation_id:UUID
    intent_event_id:UUID
    claim_id:UUID|None
    claim_admission_id:UUID|None
    claim_worker_id:UUID|None
    claim_original_deadline:AwareDatetime|None
    request_sha256:str=Field(pattern=HASH)
    bot_id:UUID|None
    receipt_id:UUID|None
    observation:dict|None
    @model_validator(mode='after')
    def exact_delivery(self):
        if self.fresh_claim!=(self.state=='claimed') or self.fresh_claim and self.claim_id is None:
            raise ValueError('exact first committed claim required')
        if (self.effect=='capture-create')!=(self.bot_id is None):raise ValueError('exact delivery bot required')
        if (self.effect=='capture-retrieve')!=(self.stage!='-'):raise ValueError('exact retrieval stage required')
        return self

class MeetingCaptureFactoryV1:
    def __init__(self,settings):
        if type(settings) is not MeetingCaptureSettingsV1:raise TypeError('fixed meeting settings required')
        settings.current();self.settings=settings;self._artifact=None;self._artifact_client=None
        if settings.config.final_artifact_file is not None:
            from oracle_brain.meetings.capture_contracts import InstalledFinalArtifactV1
            from oracle_brain.research.fetch import _InstalledArtifactGET
            c=settings.config;h=settings.host.config
            selection=_parse(InstalledFinalArtifactV1,_pinned(c.final_artifact_file,c.final_artifact_sha256))
            for key in ('meeting_id','provider','provider_account','tenant_id','provider_meeting_id','bot_id'):
                if getattr(selection,key)!=getattr(c,key):raise PermissionError('foreign installed final artifact')
            if selection.workspace_id!=h.workspace_id or selection.original_horizon>c.original_horizon:raise PermissionError('foreign final artifact horizon')
            def current_artifact():
                from ._protected_control_listener_v1 import request_remaining_v1
                request_remaining_v1(required=True);settings.current()
                if _parse(InstalledFinalArtifactV1,_pinned(c.final_artifact_file,c.final_artifact_sha256))!=selection:raise PermissionError('final artifact selection changed')
                if not selection.valid_from<=datetime.now(timezone.utc)<min(selection.expires_at,selection.original_horizon):raise PermissionError('final artifact selection expired')
            self._artifact=selection
            self._artifact_client=_InstalledArtifactGET(url=selection.download_url,expected_sha256=selection.original_sha256,byte_count=selection.byte_count,ca_file=selection.ca_file,ca_sha256=selection.ca_sha256,server_der_sha256=selection.server_der_sha256,current=current_artifact)
    def _call(self,method,args,record,deadline):
        from psycopg.conninfo import conninfo_to_dict
        s=self.settings;c=s.host.config
        from ._protected_control_listener_v1 import request_remaining_v1
        started_tick=time.monotonic();original_remaining=request_remaining_v1(required=True)
        wall=datetime.now(timezone.utc);installed_end=s.current()
        if type(deadline) is not datetime or deadline.tzinfo is None or not wall<deadline<=installed_end or (deadline-wall).total_seconds()>30:raise PermissionError('original bounded meeting deadline required')
        # Capture the caller/installation narrowing once in the same local clock
        # domain. UTC rollback or repeated current reads cannot renew that end.
        original_end=started_tick+min(original_remaining,(deadline-wall).total_seconds(),(installed_end-wall).total_seconds())
        def current():
            remaining=min(request_remaining_v1(required=True),original_end-time.monotonic(),(deadline-datetime.now(timezone.utc)).total_seconds(),(s.current()-datetime.now(timezone.utc)).total_seconds())
            if remaining<=0:raise MeetingCaptureUnavailable('meeting window elapsed')
            return max(1,int(remaining*1000))
        current()
        raw=_pinned(c.database_url.path,c.database_url.sha256,16384).decode('utf-8');_pinned(c.database_ca.path,c.database_ca.sha256,131072)
        target=conninfo_to_dict(raw)
        if set(target)-{'host','hostaddr','port','dbname','user','password','sslmode','sslrootcert','connect_timeout'} or target.get('sslmode')!='verify-full' or target.get('sslrootcert')!=c.database_ca.path or target.get('user')!=c.expected_session_role or not target.get('host') or not target.get('dbname'):raise PermissionError('fixed meeting SQL target required')
        from oracle_brain.operating_model.protected_sql_connection_v1 import _connection_v1
        from oracle_brain.operating_model.request_deadline_v1 import sql_execute_v1,_request_fence_v1
        # SAME protected socket/BEGIN/SQL/COMMIT/CLOSE owner as other actual
        # consumers. No PG* fallback, DNS, late rearm or private bytes under SQL.
        with _request_fence_v1(float(original_end)), _connection_v1(raw,deadline) as conn:
            actual=conn.info
            if not conn.pgconn.ssl_in_use or actual.host!=target['host'] or actual.dbname!=target['dbname'] or actual.user!=target['user'] or actual.port!=int(target.get('port',5432)) or (target.get('hostaddr') and actual.hostaddr!=target['hostaddr']):raise PermissionError('actual meeting SQL target differs')
            def execute(statement,arguments=None):
                current();result=sql_execute_v1(conn,deadline,statement,arguments);current();return result
            if execute('SELECT SESSION_USER::text,CURRENT_USER::text,(SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname=\'oracle2\')').fetchone()!=(c.expected_session_role,c.expected_session_role,c.expected_owner_role):raise PermissionError('actual meeting SQL role differs')
            names=['oracle2.meeting_capture_transition_v1(uuid,text,integer,uuid,text,jsonb,timestamptz)','oracle2.meeting_capture_read_v1(uuid,text,text,timestamptz)','oracle2.meeting_capture_receipt_v1(uuid,text,uuid,text,timestamptz)','oracle2.meeting_capture_current_turn_v1(uuid,text,uuid,timestamptz)','oracle2.meeting_capture_due_stop_v1(uuid,text,timestamptz)','oracle2.meeting_capture_current_final_mapping_v1(uuid,text,uuid,timestamptz)']
            if method=='enqueue':names.append('oracle2.meeting_capture_enqueue_v1(uuid,text,text,uuid,jsonb,timestamptz)')
            if method=='processing':names.append('oracle2.meeting_capture_process_ingress_v1(uuid,text,text,uuid,uuid,timestamptz)')
            if method=='worker':names.append('oracle2.meeting_capture_worker_v1(uuid,text,text,uuid,uuid,text,jsonb,timestamptz)')
            owners=execute('SELECT pg_get_userbyid(proowner),prosecdef FROM pg_proc WHERE oid=ANY(ARRAY(SELECT to_regprocedure(x) FROM unnest(%s::text[]) x))',(names,)).fetchall()
            if len(owners)!=len(names) or any(x!=(c.expected_owner_role,True) for x in owners):raise PermissionError('actual meeting function owner differs')
            prefix=(s.config.admission_id,s.config.admission_sha256)
            if method=='transition':row=execute('SELECT oracle2.meeting_capture_transition_v1(%s,%s,%s,%s,%s,%s::jsonb,%s)',(*prefix,*args,deadline))
            elif method=='read':row=execute('SELECT oracle2.meeting_capture_read_v1(%s,%s,%s,%s)',(*prefix,*args,deadline))
            elif method=='receipt':row=execute('SELECT oracle2.meeting_capture_receipt_v1(%s,%s,%s,%s,%s)',(*prefix,*args,deadline))
            elif method=='final_mapping':row=execute('SELECT oracle2.meeting_capture_current_final_mapping_v1(%s,%s,%s,%s)',(*prefix,*args,deadline))
            elif method=='due_stop':row=execute('SELECT oracle2.meeting_capture_due_stop_v1(%s,%s,%s)',(*prefix,deadline))
            elif method=='worker':row=execute('SELECT oracle2.meeting_capture_worker_v1(%s,%s,%s,%s,%s,%s,%s::jsonb,%s)',(*prefix,*args,deadline))
            elif method=='enqueue':row=execute('SELECT oracle2.meeting_capture_enqueue_v1(%s,%s,%s,%s,%s::jsonb,%s)',(*prefix,*args,deadline))
            elif method=='processing':row=execute('SELECT oracle2.meeting_capture_process_ingress_v1(%s,%s,%s,%s,%s,%s)',(*prefix,*args,deadline))
            elif method=='current_turn':row=execute('SELECT oracle2.meeting_capture_current_turn_v1(%s,%s,%s,%s)',(*prefix,*args,deadline))
            else:raise PermissionError('fixed meeting function required')
            value=record.model_validate_json(json.dumps(row.fetchone()[0]));current()
            _context_horizon(s.host,value.context)
            if value.meeting_id!=s.config.meeting_id or value.capture_until!=s.config.capture_until:raise PermissionError('actual meeting scope differs')
            if not datetime.now(timezone.utc)<value.valid_until<=deadline:raise PermissionError('actual meeting lease differs')
            current()
        current();_context_horizon(s.host,value.context)
        return value
    def _enqueue_binding_v1(self,command,ingress,*,caller_deadline,wire_receipt=None):
        from oracle_brain.meetings.queue_contracts import MeetingEnqueueSQLV1
        if command not in ('pending','claim','current','record','status') or (ingress is not None and type(ingress) is not UUID) or wire_receipt is not None and type(wire_receipt) is not dict:
            raise ValueError('closed actual queue operation required')
        result=self._call('enqueue',(command,ingress,json.dumps(wire_receipt,allow_nan=False) if wire_receipt is not None else None),MeetingEnqueueSQLV1,caller_deadline)
        if ingress is not None and result.ingress_event_id!=ingress:raise PermissionError('actual queue ingress differs')
        return result

    def process_ingress_binding_v1(self,command,ingress,*,caller_deadline,returned_final=None):
        """Same SQL owner; current metadata is not a caller-issued grant.

        Immutable startup cannot read operational SQL. The request-bound
        read-only preflight verifies the independently installed operation
        against the retained owner formula BEFORE any claim/fetch.
        """
        from oracle_brain.meetings.processing_contracts import MeetingProcessIngressSQLV1,final_population_sha256_v1
        if command not in ('claim_fetch','record_final','status') or type(ingress) is not UUID or returned_final is not None and type(returned_final) is not UUID:
            raise ValueError('closed process-ingress identity required')
        if command=='claim_fetch':
            before=self.process_ingress_binding_v1('status',ingress,caller_deadline=caller_deadline)
            if before.state=='final_artifact_pending':return before
        result=self._call('processing',(command,ingress,returned_final),MeetingProcessIngressSQLV1,caller_deadline)
        if result.original_ingress_event_id!=ingress:
            raise PermissionError('actual original process-ingress scope differs')
        if result.descriptor_sha256 is not None:
            expected=uuid5(NAMESPACE_URL,f'oracle-meeting-final:{self.settings.host.config.workspace_id}:{self.settings.config.meeting_id}:{self.settings.config.final_artifact_sha256}')
            if self._artifact is None or result.final_operation_id!=expected or result.descriptor_sha256!=self.settings.config.final_artifact_sha256 or result.population_sha256!=final_population_sha256_v1(self._artifact):
                raise PermissionError('actual independently installed final population/operation differs')
        return result

    def _worker_delivery_v1(self,command,*,operation_id=None,claim_id=None,body_sha256=None,wire=None,caller_deadline):
        if command not in ('prepare','claim','current','observe','status'):raise PermissionError('fixed worker command required')
        for value in (operation_id,claim_id):
            if value is not None and type(value) is not UUID:raise ValueError('exact opaque worker identity required')
        if wire is not None and type(wire) is not dict:raise ValueError('exact retained wire metadata required')
        return self._call('worker',(command,operation_id,claim_id,body_sha256,json.dumps(wire,allow_nan=False) if wire is not None else None),MeetingDeliverySQLV1,caller_deadline)
    def head_v1(self,*,caller_deadline,processing=False):
        return self._call('read',('process' if processing else 'status',),MeetingHeadV1,caller_deadline)
    def due_stop_v1(self,*,caller_deadline):
        return self._call('due_stop',(),MeetingDueStopV1,caller_deadline)
    def supervision_head_v1(self,*,caller_deadline):
        return self._call('read',('supervise',),MeetingHeadV1,caller_deadline)
    def transition_v1(self,*,expected_head,operation_id,action,payload,caller_deadline):
        if type(expected_head) is not int or type(operation_id) is not UUID or type(payload) is not dict:raise ValueError('exact meeting transition required')
        return self._call('transition',(expected_head,operation_id,action,json.dumps(payload,allow_nan=False)),MeetingMutationV1,caller_deadline)
    def receipt_v1(self,event_id,*,caller_deadline):
        if type(event_id) is not UUID:raise ValueError('opaque receipt identity required')
        return self._call('receipt',(event_id,'process'),MeetingReceiptV1,caller_deadline)
    def retain_ingress_v1(self,raw:bytes,*,provider_event_id,bot_id,event_kind,verifier_secret_sha256,expected_head,caller_deadline):
        s=self.settings;c=s.config;h=s.host.config
        if c.channel!='provider-ingress' or c.bot_id!=bot_id or c.verifier_secret_sha256!=verifier_secret_sha256:raise PermissionError('exact installed provider identity required')
        if type(raw) is not bytes or not 0<len(raw)<=MAX_RAW or type(provider_event_id) is not str or not 0<len(provider_event_id)<=256:raise ValueError('bounded exact provider bytes required')
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=unique_object,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite provider event')))
        if type(value) is not dict or value.get('event')!=event_kind or type(value.get('data')) is not dict or type(value['data'].get('bot')) is not dict or value['data']['bot'].get('id')!=bot_id:raise ValueError('provider raw scope differs')
        words=value['data'].get('data',{}).get('words') if type(value['data'].get('data',{})) is dict else None
        if words is not None and (type(words) is not list or len(words)>4096):raise ValueError('bounded provider words required')
        # Actual SQL permission and invitation before private persistence, then
        # transition checks again before durable acknowledgement. No SQL lock is
        # held over byte I/O. This read does not manufacture provider authority.
        observed=self._call('read',('ingress',),MeetingHeadV1,caller_deadline)
        expected={key:getattr(c,key) for key in ('provider','provider_account','tenant_id','provider_meeting_id','bot_id','verifier_secret_sha256')}
        if observed.ingress_binding!=expected or observed.version<1 or observed.state in ('UNKNOWN','cancelled'):raise PermissionError('actual current capture mapping differs')
        seal=hashlib.sha256(raw).hexdigest();parts=['meeting-raw',str(h.workspace_id),str(c.meeting_id),seal+'.bin']
        payload=dict(bot_id=bot_id,verifier_secret_sha256=verifier_secret_sha256,provider_event_id=provider_event_id,raw_sha256=seal,byte_count=len(raw),raw_object_key='/'.join(parts),event_kind=event_kind)
        operation=uuid5(NAMESPACE_URL,f'oracle-meeting-ingress:{c.provider}:{c.provider_account}:{provider_event_id}')
        retained=self._call('receipt',(operation,'ingress'),MeetingReceiptV1,caller_deadline)
        if retained.payload is not None and retained.payload!=payload:raise ValueError('provider message identity conflicts before private persistence')
        if retained.payload is None:
            from ._protected_control_listener_v1 import request_remaining_v1
            request_remaining_v1(required=True);s.current()
            _write_private_at(Path(h.storage_root),parts,raw,expected_root=(h.storage_device,h.storage_inode,h.storage_uid))
        return self.transition_v1(expected_head=expected_head,operation_id=operation,action='ingress',payload=payload,caller_deadline=caller_deadline)
    def reopen_raw_v1(self,event_id,*,caller_deadline):
        import os
        receipt=self.receipt_v1(event_id,caller_deadline=caller_deadline)
        raw=self._read_raw_receipt_bytes_v1(receipt)
        self.receipt_v1(event_id,caller_deadline=caller_deadline);return raw,receipt
    def _read_raw_receipt_bytes_v1(self,receipt):
        import os
        s=self.settings;h=s.host.config;c=s.config;p=receipt.payload
        fields={'bot_id','verifier_secret_sha256','provider_event_id','raw_sha256','byte_count','raw_object_key','event_kind'}
        if type(p) is dict and 'selection_sha256' in p:
            fields={'selection_sha256','provider_event_id','raw_sha256','byte_count','raw_object_key','event_kind'}
            if p['selection_sha256']!=c.final_artifact_sha256:raise PermissionError('stale final artifact selection')
        if type(p) is not dict or set(p)!=fields or type(p['byte_count']) is not int or not 0<p['byte_count']<=MAX_RAW:raise ValueError('retained ingress descriptor differs')
        expected=f'meeting-raw/{h.workspace_id}/{c.meeting_id}/{p["raw_sha256"]}.bin'
        if p['raw_object_key']!=expected:raise PermissionError('retained raw scope differs')
        from ._protected_control_listener_v1 import request_remaining_v1
        request_remaining_v1(required=True);s.current()
        parts=expected.split('/');fd=_parent_fd(Path(h.storage_root),parts[:-1],create=False,expected_root=(h.storage_device,h.storage_inode,h.storage_uid))
        try:raw=_read_private_at(fd,parts[-1],p['byte_count'])
        finally:os.close(fd)
        request_remaining_v1(required=True);s.current()
        if len(raw)!=p['byte_count'] or hashlib.sha256(raw).hexdigest()!=p['raw_sha256']:raise ValueError('retained provider bytes differ')
        return raw

    def read_current_participant_turn_v1(self,event_id,*,caller_deadline):
        """Current attributed workspace participant; no employee/source/send grant."""
        from ._protected_control_listener_v1 import request_remaining_v1
        from oracle_brain.meetings.capture_contracts import RawMeetingArtifactV1
        from oracle_brain.meetings.final_transcript import parse_live_recall_utterance_v1
        if type(event_id) is not UUID:raise PermissionError('exact current opaque event required')
        s=self.settings;c=s.config;h=s.host.config
        if c.channel!='worker' or c.participant_epoch_file is None:raise PermissionError('independent current participant epoch pending')
        before=self._call('current_turn',(event_id,),MeetingCurrentTurnSQLV1,caller_deadline)
        if before.capture.workspace_id!=h.workspace_id or before.capture.admission_id!=c.admission_id or before.capture.admission_sha256!=c.admission_sha256:raise PermissionError('actual current turn scope differs')
        request_remaining_v1(required=True);s.current()
        epoch=_parse(LiveParticipantEpochV1,_pinned(c.participant_epoch_file,c.participant_epoch_sha256))
        if before.epoch!=epoch or before.epoch_sha256!=c.participant_epoch_sha256 or epoch.sha256!=c.participant_epoch_sha256:raise PermissionError('independently installed current epoch differs')
        raw=self._read_raw_receipt_bytes_v1(before.receipt)
        after=self._call('current_turn',(event_id,),MeetingCurrentTurnSQLV1,caller_deadline)
        if before.capture!=after.capture or before.receipt.payload!=after.receipt.payload or after.epoch!=epoch or after.epoch_sha256!=before.epoch_sha256:raise PermissionError('current turn or participant epoch changed during private read')
        request_remaining_v1(required=True);s.current()
        if _parse(LiveParticipantEpochV1,_pinned(c.participant_epoch_file,c.participant_epoch_sha256))!=epoch:raise PermissionError('current participant epoch file changed')
        p=after.receipt.payload
        descriptor=RawMeetingArtifactV1(workspace_id=h.workspace_id,meeting_id=c.meeting_id,provider=c.provider,provider_account=c.provider_account,tenant_id=c.tenant_id,provider_meeting_id=c.provider_meeting_id,provider_artifact_id=p['provider_event_id'],provider_revision=str(after.capture.capture_revision),original_sha256=p['raw_sha256'],byte_count=p['byte_count'],media_type='application/json',final=False)
        revision=parse_live_recall_utterance_v1(raw,descriptor,revision=after.capture.capture_revision,epoch=epoch,observed_at=datetime.now(timezone.utc),expected_bot_id=after.capture.bot_id)
        if len(revision.turns)!=1:raise PermissionError('one exact current participant required')
        turn=revision.turns[0];link=next(x for x in epoch.links if x.provider_participant_id==turn.provider_speaker_id)
        if link.attribution!='workspace_actor' or link.actor_id is None:raise PermissionError('independently attributed workspace participant required')
        text=' '.join(w.text for w in turn.words)
        if len(text.encode('utf-8'))>MAX_RAW:raise ValueError('bounded original participant turn required')
        final=self._call('current_turn',(event_id,),MeetingCurrentTurnSQLV1,caller_deadline)
        if final.capture!=after.capture or final.receipt.payload!=after.receipt.payload or final.epoch!=epoch or final.epoch_sha256!=epoch.sha256:raise PermissionError('current turn or epoch changed before return')
        request_remaining_v1(required=True);s.current()
        if not epoch.valid_from<=datetime.now(timezone.utc)<min(epoch.expires_at,epoch.capture_until,final.valid_until):raise PermissionError('current participant epoch expired before return')
        if _parse(LiveParticipantEpochV1,_pinned(c.participant_epoch_file,c.participant_epoch_sha256))!=epoch:raise PermissionError('participant epoch file changed before return')
        return MeetingCurrentParticipantTurnV1(purpose='meeting-only-current-participant-turn-v1',capture=final.capture,raw_sha256=descriptor.original_sha256,participant_epoch_id=epoch.epoch_id,participant_epoch_revision=epoch.epoch_revision,participant_epoch_sha256=epoch.sha256,participant_set_sha256=epoch.participant_set_sha256,valid_until=min(final.valid_until,epoch.expires_at,epoch.capture_until,caller_deadline),normalized_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),provider_speaker_id=turn.provider_speaker_id,actor_id=link.actor_id,employee_identity_verified=False,attribution='workspace_actor',text=text,language=turn.language,reported_only=True,qualification=False,shared_source_permission=False)

    def fetch_final_artifact_v1(self,*,caller_deadline):
        """Selected whole-final bytes only; metadata discovery is not admission."""
        from ._protected_control_listener_v1 import request_remaining_v1
        c=self.settings.config;h=self.settings.host.config;selection=self._artifact
        request_remaining_v1(required=True)
        if c.channel!='worker' or selection is None:raise PermissionError('independently selected final artifact pending')
        before=self._call('read',('final_artifact',),MeetingHeadV1,caller_deadline)
        expected={key:getattr(c,key) for key in ('provider','provider_account','tenant_id','provider_meeting_id','bot_id')}
        expected['selection_sha256']=c.final_artifact_sha256
        if before.version<1 or before.artifact_binding!=expected:raise PermissionError('actual final artifact mapping differs')
        lease=min(caller_deadline,before.valid_until,selection.expires_at,selection.original_horizon)
        operation=uuid5(NAMESPACE_URL,f'oracle-meeting-final:{h.workspace_id}:{c.meeting_id}:{c.final_artifact_sha256}')
        payload=dict(selection_sha256=c.final_artifact_sha256,provider_event_id='final:'+c.final_artifact_sha256,raw_sha256=selection.original_sha256,byte_count=selection.byte_count,raw_object_key=f'meeting-raw/{h.workspace_id}/{c.meeting_id}/{selection.original_sha256}.bin',event_kind=c.provider+'.final')
        retained=self._call('receipt',(operation,'final_artifact'),MeetingReceiptV1,lease)
        if retained.payload is not None:
            if retained.payload!=payload:raise ValueError('final artifact identity conflicts')
            return retained.event_id
        raw=self._artifact_client.fetch(caller_deadline=lease)
        current=self._call('read',('final_artifact',),MeetingHeadV1,lease)
        if current.artifact_binding!=expected:raise PermissionError('current final artifact mapping differs')
        request_remaining_v1(required=True);self.settings.current()
        _write_private_at(Path(h.storage_root),payload['raw_object_key'].split('/'),raw,expected_root=(h.storage_device,h.storage_inode,h.storage_uid))
        return self.transition_v1(expected_head=current.version,operation_id=operation,action='final_artifact',payload=payload,caller_deadline=lease).event_id

    def prepare_reported_text_v1(self,event_id,*,caller_deadline):
        """Current raw and SQL-rooted workspace mapping; no employee grant."""
        from ._protected_control_listener_v1 import request_remaining_v1
        from oracle_brain.meetings.capture_contracts import RawMeetingArtifactV1,derive_reported_text_v1
        from oracle_brain.meetings.final_transcript import parse_final_recall_v1,parse_final_graph_v1
        from oracle_brain.meetings.final_mapping import FinalWorkspaceSpeakerMappingV1
        c=self.settings.config;h=self.settings.host.config;selection=self._artifact
        if c.channel!='worker' or selection is None or c.speaker_mapping_file is None or c.final_mapping_id is None:raise PermissionError('independent final attribution pending')
        before=self._call('final_mapping',(event_id,),MeetingCurrentFinalMappingSQLV1,caller_deadline)
        request_remaining_v1(required=True);self.settings.current()
        mapping=_parse(FinalWorkspaceSpeakerMappingV1,_pinned(c.speaker_mapping_file,c.speaker_mapping_sha256))
        if (mapping.mapping_id!=c.final_mapping_id or mapping.sha256!=c.speaker_mapping_sha256
            or before.mapping_sha256!=mapping.sha256 or canonical_bytes(before.mapping)!=canonical_bytes(mapping.model_dump(mode='json'))):raise PermissionError('actual current whole-final mapping differs')
        raw=self._read_raw_receipt_bytes_v1(before.receipt)
        after=self._call('final_mapping',(event_id,),MeetingCurrentFinalMappingSQLV1,caller_deadline)
        if after.mapping!=before.mapping or after.mapping_sha256!=before.mapping_sha256 or after.receipt.payload!=before.receipt.payload:raise PermissionError('whole-final mapping changed during original read')
        descriptor=RawMeetingArtifactV1(workspace_id=h.workspace_id,meeting_id=c.meeting_id,provider=c.provider,provider_account=c.provider_account,tenant_id=c.tenant_id,provider_meeting_id=c.provider_meeting_id,provider_artifact_id=selection.transcript_id,provider_revision=selection.provider_revision,original_sha256=selection.original_sha256,byte_count=selection.byte_count,media_type=selection.media_type,final=True)
        kwargs=dict(revision=mapping.mapping_revision,mapping=mapping.structural_mapping_v1(),observed_at=datetime.now(timezone.utc))
        revision=parse_final_recall_v1(raw,descriptor,**kwargs) if c.provider=='recall' else parse_final_graph_v1(raw,descriptor,language=mapping.language,**kwargs)
        text,derivation=derive_reported_text_v1(revision)
        final=self._call('final_mapping',(event_id,),MeetingCurrentFinalMappingSQLV1,caller_deadline)
        if final.mapping!=before.mapping or final.mapping_sha256!=mapping.sha256 or final.receipt.payload!=before.receipt.payload:raise PermissionError('current final attribution changed before return')
        request_remaining_v1(required=True);self.settings.current()
        if _parse(FinalWorkspaceSpeakerMappingV1,_pinned(c.speaker_mapping_file,c.speaker_mapping_sha256))!=mapping:raise PermissionError('installed final mapping changed before return')
        return text,derivation

    def execute_v1(self,raw):
        return _execute_meeting_v1(self,raw)

class MeetingControlRequestV1(StrictRecord):
    operation:Literal['invite','status','cancel','review']
    meeting_id:UUID
    expected_head:int=Field(ge=0,le=16384)
    operation_id:UUID
    payload:dict
    caller_deadline:AwareDatetime
class MeetingIngressRequestV1(StrictRecord):
    operation:Literal['ingress']
    provider_event_id:str=Field(min_length=1,max_length=256)
    bot_id:str=Field(min_length=1,max_length=256)
    event_kind:str=Field(pattern=r'^(transcript\.(data|partial_data|done|failed)|bot\.[a-z_]{1,64})$')
    verifier_secret_sha256:str=Field(pattern=HASH)
    raw_base64:str=Field(min_length=4,max_length=1398104)
    caller_deadline:AwareDatetime

def parse_meeting_control_v1(raw):return _parse(MeetingControlRequestV1,raw)
def parse_meeting_ingress_v1(raw):return _parse(MeetingIngressRequestV1,raw)

def _execute_meeting_v1(self,raw):
    """Fixed private listener entry, never caller-selected identity or config."""
    import base64,binascii
    c=self.settings.config
    if c.channel=='employee-control':
        q=parse_meeting_control_v1(raw)
        if q.meeting_id!=c.meeting_id:raise PermissionError('foreign meeting selector')
        if q.operation=='status':
            if q.payload:raise ValueError('closed status required')
            mutation=None
        else:
            payload=q.payload
            if q.operation=='invite':
                if payload!={'explicit_invitation':True,'consent_observed':True} or any(type(v) is not bool for v in payload.values()):raise ValueError('explicit current invitation observation required')
                payload={'consent_packet_sha256':c.consent_packet_sha256}
            mutation=self.transition_v1(expected_head=q.expected_head,operation_id=q.operation_id,action=q.operation,payload=payload,caller_deadline=q.caller_deadline)
        head=self.head_v1(caller_deadline=q.caller_deadline);event=mutation.event_id if mutation else None;ingress=None
    elif c.channel=='provider-ingress':
        q=parse_meeting_ingress_v1(raw)
        try:data=base64.b64decode(q.raw_base64,validate=True)
        except (ValueError,binascii.Error):raise ValueError('canonical provider original required') from None
        if base64.b64encode(data).decode()!=q.raw_base64:raise ValueError('canonical provider original required')
        value=json.loads(data.decode('utf-8'),object_pairs_hook=unique_object,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite provider event')))
        if type(value) is not dict or value.get('event')!=q.event_kind or type(value.get('data')) is not dict or type(value['data'].get('bot')) is not dict or value['data']['bot'].get('id')!=q.bot_id:raise ValueError('provider raw/envelope mismatch')
        words=value['data'].get('data',{}).get('words') if type(value['data'].get('data',{})) is dict else None
        if words is not None and (type(words) is not list or len(words)>4096):raise ValueError('bounded provider words required')
        head=self.head_v1(caller_deadline=q.caller_deadline)
        mutation=self.retain_ingress_v1(data,provider_event_id=q.provider_event_id,bot_id=q.bot_id,event_kind=q.event_kind,verifier_secret_sha256=q.verifier_secret_sha256,expected_head=head.version,caller_deadline=q.caller_deadline)
        head=self.head_v1(caller_deadline=q.caller_deadline);event=ingress=mutation.event_id
    else:raise PermissionError('fixed public meeting listener purpose required')
    return dict(schema_version=1,meeting_id=str(c.meeting_id),version=head.version,state=head.state,event_id=str(event) if event else None,ingress_id=str(ingress) if ingress else None,pending_count=len(head.pending_ingress),valid_until=min(head.valid_until,q.caller_deadline).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),qualification=False,remote_stop_proven=False,observation_only=True)
