"""Protected own-conversation SQL consumer; source creates no runtime authority.

The sole durable owner is SQL019. No browser/caller actor, role, history,
SourceRef, question projection or provider job is accepted by this boundary.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID
import hashlib
import json

from pydantic import AwareDatetime, Field, model_validator, field_validator
from oracle_brain.operating_model.contracts import StrictRecord, canonical_bytes
from .protected_inputs_v1 import ProtectedInputV1, _pinned, _parse, parse_canonical_object_v1

HASH=r'^[a-f0-9]{64}$'
class _ConversationRecordV1(StrictRecord):
    @field_validator('schema_version',mode='before',check_fields=False)
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact integer conversation version required')
        return value

class ConversationConfigV1(_ConversationRecordV1):
    schema_version:Literal[1]
    purpose:Literal['employee-conversation-control-v1']
    auth_issuer:str; auth_project_id:str; auth_user_id:UUID; employee_id:UUID
    principal_id:UUID; workspace_id:UUID
    expected_session_role:str=Field(pattern=r'^[a-z][a-z0-9_]{0,62}$')
    expected_owner_role:str=Field(pattern=r'^[a-z][a-z0-9_]{0,62}$')
    runtime_hash:str=Field(pattern=HASH); registry_hash:str=Field(pattern=HASH)
    database_url:ProtectedInputV1; database_ca:ProtectedInputV1
    original_horizon:AwareDatetime; expires_at:AwareDatetime
    response_job:ProtectedInputV1|None=None
    billing_bounds:ProtectedInputV1|None=None
    processing_config:ProtectedInputV1|None=None
    original_intake_config_sha256:str|None=Field(default=None,pattern=HASH)
    original_intake_appointment_sha256:str|None=Field(default=None,pattern=HASH)
    @model_validator(mode='after')
    def fixed_identity(self):
        from urllib.parse import urlsplit
        u=urlsplit(self.auth_issuer)
        if self.expected_session_role==self.expected_owner_role or u.scheme!='https' or not u.hostname or u.path!='/auth/v1' or u.username or u.password or u.query or u.fragment:
            raise ValueError('fixed independent conversation identity required')
        return self

class ConversationAppointmentV1(_ConversationRecordV1):
    schema_version:Literal[1]
    purpose:Literal['employee-conversation-control-v1']
    config_sha256:str=Field(pattern=HASH)
    principal_id:UUID; workspace_id:UUID; expected_session_role:str
    runtime_hash:str=Field(pattern=HASH); registry_hash:str=Field(pattern=HASH)
    issuer_actor:UUID; reviewer_actor:UUID
    valid_from:AwareDatetime; original_horizon:AwareDatetime; expires_at:AwareDatetime
    @model_validator(mode='after')
    def independent(self):
        if self.issuer_actor==self.reviewer_actor or self.principal_id in (self.issuer_actor,self.reviewer_actor) or not self.valid_from<self.expires_at<=self.original_horizon:
            raise ValueError('independent finite conversation appointment required')
        return self

@dataclass(frozen=True)
class ConversationSettingsV1:
    config:ConversationConfigV1; appointment:ConversationAppointmentV1
    config_path:Path; config_sha256:str; appointment_path:Path; appointment_sha256:str
    expected_issuer_actor:UUID; expected_reviewer_actor:UUID
    def current(self):
        from .request_deadline_v1 import request_remaining_v1
        request_remaining_v1(required=False)
        c=_parse(ConversationConfigV1,_pinned(self.config_path,self.config_sha256))
        a=_parse(ConversationAppointmentV1,_pinned(self.appointment_path,self.appointment_sha256))
        if c!=self.config or a!=self.appointment or a.config_sha256!=self.config_sha256 or a.issuer_actor!=self.expected_issuer_actor or a.reviewer_actor!=self.expected_reviewer_actor:
            raise PermissionError('protected conversation installation changed')
        for field in ('principal_id','workspace_id','expected_session_role','runtime_hash','registry_hash','original_horizon'):
            if getattr(c,field)!=getattr(a,field):raise PermissionError('conversation appointment differs')
        _pinned(c.database_url.path,c.database_url.sha256,16384)
        _pinned(c.database_ca.path,c.database_ca.sha256,131072)
        if c.response_job is not None:_pinned(c.response_job.path,c.response_job.sha256,262144)
        if c.billing_bounds is not None:_pinned(c.billing_bounds.path,c.billing_bounds.sha256)
        if c.processing_config is not None:_pinned(c.processing_config.path,c.processing_config.sha256,262144)
        until=min(c.expires_at,c.original_horizon,a.expires_at,a.original_horizon)
        if not a.valid_from<=datetime.now(timezone.utc)<until:raise PermissionError('conversation appointment expired')
        request_remaining_v1(required=False)
        return until

def load_conversation_settings_v1(config_path,config_sha256,appointment_path,appointment_sha256,issuer_actor,reviewer_actor):
    s=ConversationSettingsV1(_parse(ConversationConfigV1,_pinned(config_path,config_sha256)),
        _parse(ConversationAppointmentV1,_pinned(appointment_path,appointment_sha256)),Path(config_path),config_sha256,
        Path(appointment_path),appointment_sha256,issuer_actor,reviewer_actor)
    s.current();return s

class ConversationConflict(ValueError):pass
class ConversationDenied(PermissionError):pass
class ConversationUnknown(PermissionError):
    """Possibly committed operation: observe command status, never automatically resend."""

SIGNATURES=('create_conversation_v1(bytea)','apply_conversation_command_v1(bytea)',
 'conversation_snapshot_v1(uuid,bigint,timestamptz)','conversation_command_status_v1(uuid,timestamptz)')
PUBLIC_OPERATIONS=frozenset({'employee_turn','correct','skip','unknown','referral','pause','resume','stop','review_recap'})

class ConversationControlV1:
    def __init__(self,settings):
        if type(settings) is not ConversationSettingsV1:raise TypeError('actual protected conversation settings required')
        settings.current();self.settings=settings
    def _call(self,name,args):
        from .request_deadline_v1 import request_remaining_v1
        request_remaining_v1()
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        s=self.settings;c=s.config;deadline=s.current()
        if name in ('create','apply'):
            caller=datetime.fromisoformat(json.loads(args[0])['caller_deadline'])
            if caller.tzinfo is None or caller.utcoffset() is None:raise ValueError('aware original caller deadline required')
            deadline=min(deadline,caller)
            if datetime.now(timezone.utc)>=deadline:raise ConversationDenied('Original conversation window expired')
        url=_pinned(c.database_url.path,c.database_url.sha256,16384).decode('utf-8');target=conninfo_to_dict(url)
        if set(target)-{'host','hostaddr','port','dbname','user','password','sslmode','sslrootcert','connect_timeout'} or target.get('sslmode')!='verify-full' or target.get('sslrootcert')!=c.database_ca.path or target.get('user')!=c.expected_session_role or not target.get('host') or not target.get('dbname'):
            raise PermissionError('fixed conversation TLS target required')
        try:
            request_remaining_v1()
            with psycopg.connect(url,connect_timeout=5) as conn:
                request_remaining_v1()
                def execute(statement,parameters=None):
                    request_remaining_v1()
                    observed=conn.execute(statement,parameters)
                    request_remaining_v1()
                    return observed
                actual=conn.info
                if not conn.pgconn.ssl_in_use or actual.host!=target['host'] or actual.dbname!=target['dbname'] or actual.user!=target['user'] or actual.port!=int(target.get('port',5432)) or (target.get('hostaddr') and actual.hostaddr!=target['hostaddr']):raise PermissionError('actual conversation target differs')
                execute("SELECT set_config('statement_timeout','5000',true),set_config('lock_timeout','2000',true)")
                row=execute("SELECT SESSION_USER::text,CURRENT_USER::text,(SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2')").fetchone()
                if row!=(c.expected_session_role,c.expected_session_role,c.expected_owner_role):raise PermissionError('actual conversation SQL role differs')
                for signature in SIGNATURES:
                    row=execute("SELECT pg_get_userbyid(proowner),prosecdef,provolatile,proconfig,has_function_privilege(SESSION_USER,oid,'EXECUTE') FROM pg_proc WHERE oid=to_regprocedure(%s)",('oracle2.'+signature,)).fetchone()
                    if row is None or row[:3]!=(c.expected_owner_role,True,'v') or row[3]!=['search_path=pg_catalog, oracle2'] or row[4] is not True:raise PermissionError('actual conversation capability catalog differs')
                    grants=execute("SELECT coalesce(r.rolname,'PUBLIC'),x.is_grantable FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x LEFT JOIN pg_roles r ON r.oid=x.grantee WHERE p.oid=to_regprocedure(%s) AND x.privilege_type='EXECUTE' AND x.grantee<>p.proowner",('oracle2.'+signature,)).fetchall()
                    if grants!=[('oracle2_replacement_requester',False)]:raise PermissionError('actual conversation function ACL differs')
                s.current()
                if name=='create':query='SELECT oracle2.create_conversation_v1(%s)'
                elif name=='apply':query='SELECT oracle2.apply_conversation_command_v1(%s)'
                elif name=='snapshot':query='SELECT oracle2.conversation_snapshot_v1(%s,%s,%s)'
                elif name=='status':query='SELECT oracle2.conversation_command_status_v1(%s,%s)'
                else:raise PermissionError('fixed conversation capability required')
                request_remaining_v1()
                result=execute(query,args).fetchone()[0]
                request_remaining_v1()
                if not isinstance(result,dict):raise PermissionError('closed conversation response required')
                if name!='status' and (result.get('principal_id')!=str(c.principal_id) or result.get('workspace_id')!=str(c.workspace_id) or result.get('company_policy_confirmed') is not False or result.get('source_qualified') is not False):raise PermissionError('actual own conversation response differs')
                s.current()
                if datetime.now(timezone.utc)>=deadline:raise PermissionError('original conversation deadline elapsed')
                request_remaining_v1()
                conn.commit()
                request_remaining_v1()
            s.current()
            if datetime.now(timezone.utc)>=deadline:raise PermissionError('original conversation deadline elapsed')
            return result
        except BaseException as error:
            if getattr(error,'sqlstate',None) in ('40001','23505'):raise ConversationConflict('Refresh current conversation before a new command') from None
            if getattr(error,'sqlstate',None) in ('42501','22023','55000'):raise ConversationDenied('Current conversation control denied; no mutation committed') from None
            raise ConversationUnknown('Conversation outcome UNKNOWN; observe exact command status; no automatic resend') from None
    def execute_v1(self,raw:bytes):
        q=parse_canonical_object_v1(raw)
        operation=q.get('operation')
        if operation is not None and operation not in PUBLIC_OPERATIONS:raise PermissionError('employee control operation required')
        return self._call('create' if operation is None else 'apply',(raw,))
    def list_v1(self):
        return self._call('snapshot',(None,0,self.settings.current()))
    def snapshot_v1(self,thread_id,*,after_sequence=0):
        if type(thread_id) is not UUID or type(after_sequence) is not int or after_sequence<0:raise ValueError('exact bounded thread selector required')
        return self._call('snapshot',(thread_id,after_sequence,self.settings.current()))
    def command_status_v1(self,command_id):
        if type(command_id) is not UUID:raise ValueError('exact command selector required')
        return self._call('status',(command_id,self.settings.current()))
