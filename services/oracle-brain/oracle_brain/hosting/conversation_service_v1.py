"""Fixed separately installed conversation mTLS ingress, reusing shared lifecycle.

No fixture/auth fallback, role/session issuance, employee contact or implicit
provider dispatch. Original monotonic/wall window never renews after auth/SQL.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from uuid import UUID
import json
from cryptography import x509
from pydantic import AwareDatetime,Field,model_validator,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes
from .original_intake_v1 import OriginalIntakeSettingsV1,OriginalIntakeFactoryV1
from oracle_brain.operating_model.protected_inputs_v1 import _pinned,_parse,parse_canonical_object_v1
from .conversation_control_v1 import ConversationSettingsV1,ConversationControlV1,PUBLIC_OPERATIONS,ConversationDenied,ConversationConflict
from .replacement_request_service_v1 import RequesterPeerProfileV1
from ._protected_control_listener_v1 import _protected_control_listener_v1

HASH=r'^[0-9a-f]{64}$';PATH='/v1/employee/conversation'
class _ConversationRecordV1(StrictRecord):
    @field_validator('schema_version',mode='before',check_fields=False)
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact integer conversation version required')
        return value

class ConversationPeerProfileV1(_ConversationRecordV1):
    purpose:Literal['employee-conversation-peer-v1']='employee-conversation-peer-v1'
    conversation_config_sha256:str=Field(pattern=HASH)
    conversation_appointment_sha256:str=Field(pattern=HASH)
    principal_id:UUID;workspace_id:UUID
    runtime_hash:str=Field(pattern=HASH);registry_hash:str=Field(pattern=HASH)
    client_uri:str=Field(pattern=r'^spiffe://oracle/[a-zA-Z0-9/_-]+$')
    client_certificate_sha256:str=Field(pattern=HASH)
    listen_host:str;listen_port:int=Field(ge=0,le=65535)
    server_hostname:str=Field(pattern=r'^[a-zA-Z0-9.-]{1,253}$')
    server_certificate_file:str;server_certificate_sha256:str=Field(pattern=HASH)
    server_key_file:str;server_key_sha256:str=Field(pattern=HASH)
    client_ca_file:str;client_ca_sha256:str=Field(pattern=HASH)
    issuer_actor:UUID;reviewer_actor:UUID
    valid_from:AwareDatetime;expires_at:AwareDatetime;original_horizon:AwareDatetime
    @model_validator(mode='after')
    def same_fixed_tls_rules(self):
        # Pure TLS/path/finite-window validation from the existing peer owner;
        # it supplies no intake settings/operation or identity authorization.
        RequesterPeerProfileV1.closed(self)
        return self

@dataclass(frozen=True)
class _ConversationPeerSettings:
    conversation:ConversationSettingsV1
    profile:ConversationPeerProfileV1
    path:str;sha256:str
    def current(self):
        s=self.conversation;c=s.config;p=self.profile;bound=s.current()
        if _parse(ConversationPeerProfileV1,_pinned(self.path,self.sha256))!=p:raise PermissionError('conversation peer changed')
        if (p.conversation_config_sha256,p.conversation_appointment_sha256,p.principal_id,p.workspace_id,p.runtime_hash,p.registry_hash,
            p.issuer_actor,p.reviewer_actor,p.original_horizon)!=(s.config_sha256,s.appointment_sha256,c.principal_id,c.workspace_id,c.runtime_hash,c.registry_hash,
            s.expected_issuer_actor,s.expected_reviewer_actor,c.original_horizon):raise PermissionError('independent conversation peer appointment differs')
        now=datetime.now(timezone.utc)
        if not p.valid_from<=now<p.expires_at<=bound:raise PermissionError('conversation peer expired or excessive')
        cert=_pinned(p.server_certificate_file,p.server_certificate_sha256,131072)
        _pinned(p.server_key_file,p.server_key_sha256,131072);_pinned(p.client_ca_file,p.client_ca_sha256,131072)
        leaf=x509.load_pem_x509_certificate(cert)
        names=leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
        if p.server_hostname not in names or not leaf.not_valid_before_utc<=now<leaf.not_valid_after_utc:raise PermissionError('actual conversation server certificate differs')
        return min(bound,p.expires_at)

def parse_conversation_request_v1(raw):
    q=parse_canonical_object_v1(raw)
    if type(q.get('schema_version')) is not int or q['schema_version']!=1:raise ValueError('canonical conversation request required')
    deadline=q.get('caller_deadline')
    if not isinstance(deadline,str):raise ValueError('exact conversation deadline required')
    stamp=datetime.fromisoformat(deadline)
    if stamp.tzinfo is None or stamp.utcoffset() is None:raise ValueError('aware conversation deadline required')
    op=q.get('operation')
    if op is not None and op not in PUBLIC_OPERATIONS|{'snapshot','status','list'}:raise PermissionError('closed employee control operation required')
    if op in ('snapshot','status','list'):
        fields={'schema_version','caller_deadline','operation'}|({'thread_id'} if op=='snapshot' else {'command_id'} if op=='status' else set())
        if set(q)!=fields:raise ValueError('closed conversation observation required')
        if op!='list':UUID(q['thread_id'] if op=='snapshot' else q['command_id'])
    return SimpleNamespace(caller_deadline=stamp,value=q)

class _ConversationIngress:
    def __init__(self,control,intake=None,answering=None):self.control=control;self.intake=intake;self.answering=answering
    def execute_v1(self,raw):
        try:return self._execute_v1(raw)
        except ConversationDenied:return dict(schema_version=1,state='DENIED',resend_authorized=False)
        except ConversationConflict:return dict(schema_version=1,state='CONFLICT',resend_authorized=False)
    def _execute_v1(self,raw):
        q=parse_conversation_request_v1(raw).value;op=q.get('operation')
        if op=='snapshot':
            from oracle_brain.workflows.interview import present
            return present(self.control.snapshot_v1(UUID(q['thread_id'])))
        if op=='status':return self.control.command_status_v1(UUID(q['command_id']))
        if op=='list':return self.control.list_v1()
        from oracle_brain.workflows.interview import present
        snapshot=self.control.execute_v1(raw)
        if self.intake is not None and op in ('employee_turn','correct'):
            from oracle_brain.workflows.interview import InterviewWorkflowV1
            event=next((e for e in snapshot['recap']['events'] if e['turn_id']==q['turn_id'] and e['origin']=='employee'),None)
            if event is None:raise PermissionError('actual committed employee original unavailable')
            snapshot=InterviewWorkflowV1(self.control).register_original_v1(UUID(snapshot['thread_id']),UUID(event['event_id']),self.intake)
        if self.answering is not None and op in ('employee_turn','correct'):
            return self.answering.present_turn_v1(snapshot,q['turn_id'])
        return present(snapshot)

def protected_conversation_server_v1(conversation,peer_profile_path,peer_profile_sha256,*,original_intake=None,answering=None,question_effects=None):
    if type(conversation) is not ConversationSettingsV1:raise TypeError('exact separate conversation settings required')
    profile=_parse(ConversationPeerProfileV1,_pinned(peer_profile_path,peer_profile_sha256))
    settings=_ConversationPeerSettings(conversation,profile,str(peer_profile_path),peer_profile_sha256);settings.current()
    intake=None
    if original_intake is not None:
        if type(original_intake) is not OriginalIntakeSettingsV1:raise TypeError('separately protected existing original intake required')
        c=conversation.config;i=original_intake.config
        if (c.original_intake_config_sha256,c.original_intake_appointment_sha256,c.principal_id,c.workspace_id)!=(original_intake.config_sha256,original_intake.appointment_sha256,i.principal_id,i.workspace_id):raise PermissionError('existing original intake installation not bound to conversation')
        original_intake.current();intake=OriginalIntakeFactoryV1(original_intake)
    control=ConversationControlV1(conversation);answer_owner=None
    if question_effects is not None and answering is None:raise PermissionError('question effects require separately appointed actual employee answer recipient')
    if answering is not None:
        from .conversation_answer_v1 import ConversationAnswerV1
        answer_owner=ConversationAnswerV1(control,answering,effects=question_effects)
    factory=_ConversationIngress(control,intake,answer_owner)
    def encode(value):
        if not isinstance(value,dict) or value.get('schema_version')!=1:raise PermissionError('closed actual conversation response required')
        if 'state' not in value or value['state'] not in ('committed','UNKNOWN','DENIED','CONFLICT'):
            if value.get('principal_id')!=str(conversation.config.principal_id) or value.get('workspace_id')!=str(conversation.config.workspace_id) or value.get('company_policy_confirmed') is not False:raise PermissionError('actual own conversation response differs')
        return canonical_bytes(value)
    try:
        server=_protected_control_listener_v1(settings,factory,path=PATH,parse_request=parse_conversation_request_v1,encode_response=encode,maximum_response_bytes=4194304)
        if answer_owner is not None:
            original_close=server.server_close
            def close():
                original_close();answer_owner.close()
            server.server_close=close
        return server
    except BaseException:
        if answer_owner is not None:answer_owner.close()
        raise
