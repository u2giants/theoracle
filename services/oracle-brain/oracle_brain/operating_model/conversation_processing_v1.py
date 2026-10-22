"""Protected actual own model-worker input, reused source/runtime admissions.

Config selects an externally installed operational admission. It contains no
future job/request/body hash and creates no grant. SQL019 derives the actual
thread/event/enduser and complete qualified population even when it is empty.
"""
from datetime import datetime,timezone
from pathlib import Path
from uuid import UUID
from typing import Literal
import hashlib
from pydantic import AwareDatetime,Field,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,SourceRef,canonical_bytes,digest
from oracle_brain.operating_model.source_receipts import SourceReceipt
from oracle_brain.operating_model.authority_adapter import ProcessingSourceBinding,ProcessingSourceResolver
from .protected_inputs_v1 import ProtectedInputV1,_pinned,_parse
HASH=r'^[0-9a-f]{64}$'
class _ConversationRecordV1(StrictRecord):
    @field_validator('schema_version',mode='before',check_fields=False)
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact integer conversation version required')
        return value

class ConversationProcessingConfigV1(_ConversationRecordV1):
    purpose:Literal['employee-conversation-processing-input-v1']='employee-conversation-processing-input-v1'
    admission_id:UUID
    worker_principal_id:UUID;workspace_id:UUID;thread_id:UUID;thread_revision:int=Field(ge=1)
    employee_event_id:UUID;enduser_principal_id:UUID
    dispatch_id:UUID
    expected_session_role:str;expected_owner_role:str
    runtime_hash:str=Field(pattern=HASH);registry_hash:str=Field(pattern=HASH)
    model_id:Literal['openai/gpt-6.1-sol','openai/gpt-6-astra']
    qualified_population:tuple[SourceRef,...]=Field(max_length=64)
    qualified_population_sha256:str=Field(pattern=HASH)
    database_url:ProtectedInputV1;database_ca:ProtectedInputV1
    original_horizon:AwareDatetime;expires_at:AwareDatetime

class ConversationProcessingInputV1(_ConversationRecordV1):
    admission_id:UUID;worker_principal_id:UUID;workspace_id:UUID;thread_id:UUID;thread_revision:int=Field(ge=1)
    employee_event_id:UUID;enduser_principal_id:UUID
    runtime_hash:str=Field(pattern=HASH);registry_hash:str=Field(pattern=HASH);config_sha256:str=Field(pattern=HASH)
    dispatch_id:UUID;model_id:Literal['openai/gpt-6.1-sol','openai/gpt-6-astra']
    qualified_population:tuple[SourceRef,...]=Field(max_length=64)
    qualified_population_sha256:str=Field(pattern=HASH)
    original_horizon:AwareDatetime;valid_until:AwareDatetime;checked_at:AwareDatetime
    qualified_readings:tuple[SourceReceipt,...]=Field(max_length=64)
    snapshot:dict

class _WorkerResolver(ProcessingSourceResolver):
    def __init__(self,url,*,binding,admission_id):
        self._conversation_admission_id=admission_id
        super().__init__(url,binding=binding)
    def _check(self,connection):
        from .request_deadline_v1 import request_remaining_v1
        request_remaining_v1()
        self._check_role_and_catalog(connection)
        request_remaining_v1()
        connection.execute("SELECT set_config('statement_timeout','5000',true),set_config('lock_timeout','2000',true)")
        row=connection.execute('SELECT oracle2.conversation_model_input_v1(%s)',(self._conversation_admission_id,)).fetchone()
        if not row:raise PermissionError('actual current conversation worker admission required')
    _signatures={**ProcessingSourceResolver._signatures,
        'oracle2.conversation_model_input_v1(uuid)':frozenset({'oracle2_source_reader'}),
        'oracle2.hosting_employee_conversation_receipt_v1(uuid,uuid,uuid,text,text)':frozenset({'oracle2_source_reader'}),
        'oracle2.hosting_employee_conversation_identity_v1(uuid,uuid,uuid,text,text)':frozenset({'oracle2_source_reader'}),
        'oracle2._purpose_source_v2(uuid,uuid,uuid,text,text,text,boolean)':frozenset()}

class ProtectedConversationProcessingV1:
    def __init__(self,pin):
        if type(pin) is not ProtectedInputV1:raise TypeError('protected existing installation pointer required')
        self.pin=pin
    def current_v1(self):
        import psycopg
        try:return self._current_v1()
        except psycopg.Error:
            raise PermissionError("actual current conversation worker/thread input denied") from None
    def _current_v1(self):
        from .request_deadline_v1 import request_remaining_v1
        request_remaining_v1()
        pin=self.pin;raw=_pinned(pin.path,pin.sha256,262144);c=_parse(ConversationProcessingConfigV1,raw)
        if (c.qualified_population_sha256!=digest({'source_refs':[r.model_dump(mode='json') for r in c.qualified_population]})
            or len({r.source_id for r in c.qualified_population})!=len(c.qualified_population)
            or any(r.workspace_id!=c.workspace_id for r in c.qualified_population)
            or not datetime.now(timezone.utc)<c.expires_at<=c.original_horizon):raise PermissionError('complete current worker input pins required')
        _pinned(c.database_ca.path,c.database_ca.sha256,131072)
        url=_pinned(c.database_url.path,c.database_url.sha256,16384).decode('utf-8')
        from psycopg.conninfo import conninfo_to_dict
        target=conninfo_to_dict(url)
        if (set(target)-{'host','hostaddr','port','dbname','user','password','sslmode','sslrootcert','connect_timeout'}
            or target.get('sslmode')!='verify-full' or target.get('sslrootcert')!=c.database_ca.path or target.get('user')!=c.expected_session_role):raise PermissionError('fixed worker TLS pins required')
        resolver=_WorkerResolver(url,binding=ProcessingSourceBinding(c.runtime_hash,c.registry_hash,c.expected_owner_role,
            c.expected_session_role,c.worker_principal_id,'source-reader',c.expires_at),admission_id=c.admission_id)
        with resolver._connection() as connection:
            resolver._check(connection)
            connection.execute("SELECT set_config('statement_timeout','5000',true),set_config('lock_timeout','2000',true)")
            observed=connection.execute('SELECT oracle2.conversation_model_input_v1(%s)',(c.admission_id,)).fetchone()
            resolver._check(connection)
        value=ConversationProcessingInputV1.model_validate_json(canonical_bytes(observed[0]))
        fields=('admission_id','worker_principal_id','workspace_id','thread_id','thread_revision','employee_event_id','enduser_principal_id',
            'runtime_hash','registry_hash','dispatch_id','model_id','qualified_population','qualified_population_sha256','original_horizon')
        if (any(getattr(value,k)!=getattr(c,k) for k in fields) or value.config_sha256!=pin.sha256
            or not value.checked_at<=datetime.now(timezone.utc)<value.valid_until<=min(c.expires_at,c.original_horizon)):
            raise PermissionError('actual own worker/thread/input binding differs')
        if tuple(x.ref for x in value.qualified_readings)!=value.qualified_population:raise PermissionError('actual complete qualified reading population differs')
        if _pinned(pin.path,pin.sha256,262144)!=raw:raise PermissionError('worker protected input changed')
        request_remaining_v1()
        return value
    def current_for_job_v1(self,job):
        from oracle_brain.operating_model.native_factory import EmployeeConversationDispatchJobV1
        if type(job) is not EmployeeConversationDispatchJobV1:raise TypeError('exact immutable conversation job required')
        actual=self.current_v1()
        if (actual.dispatch_id,actual.workspace_id,actual.thread_id,actual.thread_revision,actual.employee_event_id,actual.model_id,
            actual.qualified_population,actual.qualified_population_sha256)!=(job.dispatch_id,job.workspace_id,job.thread_id,
            job.thread_revision,job.employee_event_id,job.pricing.model,job.qualified_population,job.qualified_population_sha256):
            raise PermissionError('actual worker input differs from registered immutable job')
        matching=[e for e in actual.snapshot['recap']['events'] if e['event_id']==str(job.employee_event_id) and e['origin']=='employee']
        if len(matching)!=1 or matching[0]['original_sha256']!=job.original_sha256:
            raise PermissionError('actual employee original differs from model job')
        return actual
