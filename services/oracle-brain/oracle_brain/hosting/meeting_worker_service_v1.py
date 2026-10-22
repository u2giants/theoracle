"""One fixed installed meeting-worker mTLS boundary, no employee adaptation.

Only fixed startup code chooses the actual participation owner. This adapter
translates existing own SQL operations; it has no ledger, grant or provider call.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
from typing import Literal
from uuid import UUID,uuid5,NAMESPACE_URL
from pydantic import Field
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.meetings.worker_contracts import MeetingWorkerRequestV1,MeetingWorkerPacketV1,MAX_REQUEST_BYTES
from .replacement_request_service_v1 import RequesterPeerProfileV1,_load_peer_settings_v1
from .meeting_participation_v1 import MeetingParticipationSettingsV1,MeetingParticipationFactoryV1
from .meeting_capture_v1 import MeetingCaptureFactoryV1
from .original_intake_v1 import _parse
from ._protected_control_listener_v1 import _protected_control_listener_v1,request_remaining_v1
HASH=r'^[a-f0-9]{64}$'

class ParticipationWorkerPeerProfileV1(RequesterPeerProfileV1):
    purpose:Literal['replacement-meeting-participation-worker-peer-v1']
    effect_purpose:Literal['participation-send']
    worker_id:UUID
    meeting_id:UUID
    provider_account:str=Field(min_length=1,max_length=256)
    worker_config_sha256:str=Field(pattern=HASH)
    worker_admission_sha256:str=Field(pattern=HASH)
    operation_policy_sha256:str=Field(pattern=HASH)
    composer_program_sha256:str=Field(pattern=HASH)

@dataclass(frozen=True)
class _ParticipationWorkerSettings:
    participation:MeetingParticipationSettingsV1
    factory:MeetingParticipationFactoryV1
    peer:object
    @property
    def profile(self):return self.peer.profile
    def current(self):
        end=min(self.participation.current(),self.peer.current());p=self.profile;c=self.participation.config
        if (type(p) is not ParticipationWorkerPeerProfileV1 or c.kind!='sender'
                or p.worker_config_sha256!=self.participation.config_sha256
                or p.worker_admission_sha256!=c.admission_sha256
                or p.meeting_id!=c.meeting_id
                or p.provider_account!=self.participation.capture_settings.config.provider_account
                or p.operation_policy_sha256!=self.factory.operation_policy_sha256
                or p.composer_program_sha256!=c.composer_sha256):
            raise PermissionError('exact independently installed participation worker differs')
        return end

class _ParticipationWorkerAdapter:
    def __init__(self,settings):
        if type(settings) is not _ParticipationWorkerSettings or type(settings.factory) is not MeetingParticipationFactoryV1:raise PermissionError('same installed participation owner required')
        self.settings=settings
    def _check(self,deadline):
        request_remaining_v1(required=True);end=self.settings.current();now=datetime.now(timezone.utc)
        if not now<deadline<=end or (deadline-now).total_seconds()>30:raise PermissionError('original worker window elapsed or excessive')
        return end
    def _identity(self,intent,claim,deadline):
        self._check(deadline)
        bot,metadata=self.settings.factory.receipt_identity_v1(intent,claim,caller_deadline=deadline)
        self._check(deadline)
        if type(bot) is not UUID or metadata.get('intent_id')!=str(intent) or metadata.get('claim_event_id')!=str(claim):raise PermissionError('same immutable own receipt identity required')
        return bot,metadata
    def _packet(self,metadata,deadline,*,body=None,bot=None,current=False,lease=None):
        end=self._check(deadline);p=self.settings.profile;c=self.settings.participation.config
        actual=metadata.get('state');state='claimed' if body is not None else 'inflight' if current else {'intent':'prepared','provider-response-observed':'observed','inflight':'UNKNOWN','UNKNOWN':'UNKNOWN','suppressed':'idle',None:'idle'}.get(actual)
        if state is None:raise PermissionError('closed actual participation state required')
        until=datetime.fromisoformat(metadata['valid_until'].replace('Z','+00:00'))
        value=dict(schema_version=1,state=state,effect_purpose='participation-send',principal_id=str(c.principal_id),worker_id=str(p.worker_id),workspace_id=str(c.workspace_id),meeting_id=str(c.meeting_id),provider_account=p.provider_account,
            operation_id=metadata['intent_id'],claim_event_id=metadata['claim_event_id'],request_sha256=metadata['request_sha256'],bot_id=str(bot) if bot else None,
            body_base64=__import__('base64').b64encode(body).decode() if body is not None else None,
            operation_policy_sha256=self.settings.factory.operation_policy_sha256,composer_program_sha256=c.composer_sha256,
            valid_until=min(until,end,deadline,lease or deadline).astimezone(timezone.utc).isoformat().replace('+00:00','Z'),executable=body is not None,
            qualification=False,remote_stop_proven=False,observation_only=True,resend_authorized=False)
        checked=MeetingWorkerPacketV1.model_validate_json(canonical_bytes(value));self._check(deadline)
        return checked.model_dump(mode='json')
    def execute_v1(self,raw):
        q=_parse(MeetingWorkerRequestV1,raw);self._check(q.caller_deadline);f=self.settings.factory
        if q.operation=='prepare':
            metadata=f.prepare_latest_v1(caller_deadline=q.caller_deadline);bot=None
            if metadata.get('claim_event_id') is not None:bot,metadata=self._identity(UUID(metadata['intent_id']),UUID(metadata['claim_event_id']),q.caller_deadline)
            return self._packet(metadata,q.caller_deadline,bot=bot)
        if q.operation=='claim':
            before=f.status_v1(q.operation_id,caller_deadline=q.caller_deadline)
            if before.get('intent_id')!=str(q.operation_id):raise PermissionError('same actual prepared intent required')
            operation=uuid5(NAMESPACE_URL,f'oracle-meeting-worker/participation-claim-v1/{q.operation_id}')
            claim=f.claim_v1(q.operation_id,expected_revision=before['delivery_revision'],operation=operation,caller_deadline=q.caller_deadline)
            self._check(q.caller_deadline)
            if claim.body is not None:
                bot,metadata=self._identity(q.operation_id,UUID(claim.metadata['claim_event_id']),q.caller_deadline)
                if bot!=claim.bot_id or metadata.get('claim_current') is not True or metadata['request_sha256']!=claim.metadata['request_sha256']:raise PermissionError('actual first claim identity changed')
                return self._packet(metadata,q.caller_deadline,body=claim.body,bot=bot,lease=claim.valid_until)
            bot=None;metadata=claim.metadata
            if metadata.get('claim_event_id') is not None:bot,metadata=self._identity(q.operation_id,UUID(metadata['claim_event_id']),q.caller_deadline)
            return self._packet(metadata,q.caller_deadline,bot=bot)
        if q.operation=='current':
            bot,before=self._identity(q.operation_id,q.claim_event_id,q.caller_deadline)
            fresh=f.current_claim_v1(q.operation_id,q.claim_event_id,before['request_sha256'],caller_deadline=q.caller_deadline)
            after_bot,metadata=self._identity(q.operation_id,q.claim_event_id,q.caller_deadline)
            if after_bot!=bot or fresh['request_sha256']!=metadata['request_sha256'] or fresh['claim_event_id']!=metadata['claim_event_id'] or metadata.get('claim_current') is not True:raise PermissionError('actual current claim changed')
            return self._packet(metadata,q.caller_deadline,bot=bot,current=True)
        if q.operation=='observe':
            bot,before=self._identity(q.operation_id,q.claim_event_id,q.caller_deadline)
            error={None:None,'transport_uncertain':'network','invalid_response':'framing','expired':'expired','cancelled':'unknown','local_failure':'unknown'}[q.error]
            operation=uuid5(NAMESPACE_URL,f'oracle-meeting-worker/participation-observe-v1/{q.operation_id}/{q.claim_event_id}')
            observed=f.receipt_v1(q.operation_id,claim_event_id=q.claim_event_id,operation=operation,raw_wire=q.observed_wire(),error=error,caller_deadline=q.caller_deadline)
            after_bot,metadata=self._identity(q.operation_id,q.claim_event_id,q.caller_deadline)
            if after_bot!=bot or before['request_sha256']!=metadata['request_sha256'] or observed['request_sha256']!=metadata['request_sha256']:raise PermissionError('actual retained receipt identity differs')
            return self._packet(metadata,q.caller_deadline,bot=bot)
        metadata=f.status_v1(q.operation_id,caller_deadline=q.caller_deadline) if q.operation_id else f.status_latest_v1(caller_deadline=q.caller_deadline)
        if q.operation_id is not None and metadata.get('intent_id')!=str(q.operation_id):raise PermissionError('same own historical intent required')
        bot=None
        if metadata.get('claim_event_id') is not None:
            claim=UUID(metadata['claim_event_id'])
            if q.claim_event_id is not None and q.claim_event_id!=claim:raise PermissionError('same actual historical claim required')
            bot,metadata=self._identity(UUID(metadata['intent_id']),claim,q.caller_deadline)
        elif q.claim_event_id is not None:raise PermissionError('unknown claim selector refused')
        return self._packet(metadata,q.caller_deadline,bot=bot)

def _encode_worker_packet(value):
    checked=MeetingWorkerPacketV1.model_validate_json(canonical_bytes(value))
    return canonical_bytes(checked.model_dump(mode='json'))

def protected_meeting_participation_worker_server_v1(participation_settings,capture_factory,peer_profile_path,peer_profile_sha256):
    if type(participation_settings) is not MeetingParticipationSettingsV1 or type(capture_factory) is not MeetingCaptureFactoryV1 or participation_settings.config.kind!='sender':raise PermissionError('fixed installed sender and same capture owner required')
    factory=MeetingParticipationFactoryV1(participation_settings,capture_factory)
    peer=_load_peer_settings_v1(participation_settings.capture_settings.host,peer_profile_path,peer_profile_sha256,ParticipationWorkerPeerProfileV1)
    settings=_ParticipationWorkerSettings(participation_settings,factory,peer);settings.current()
    return _protected_control_listener_v1(settings,_ParticipationWorkerAdapter(settings),path='/v1/replacement/meetings/worker',parse_request=lambda raw:_parse(MeetingWorkerRequestV1,raw),encode_response=_encode_worker_packet,maximum_request_bytes=MAX_REQUEST_BYTES,maximum_response_bytes=131072)

# SAME listener/peer lifecycle, a separately installed capture service purpose.
# Startup entry names below are closed; no HTTP field selects purpose/stage.
from .meeting_capture_worker_v1 import CaptureWorkerSettingsV1,CaptureWorkerFactoryV1
class CaptureWorkerPeerProfileV1(RequesterPeerProfileV1):
    purpose:Literal['replacement-meeting-capture-worker-peer-v1']
    effect_purpose:Literal['capture-create','capture-leave','capture-retrieve']
    retrieve_stage:Literal['pre-stop-consistency','post-stop-terminal']|None
    worker_id:UUID
    meeting_id:UUID
    provider_account:str=Field(min_length=1,max_length=256)
    worker_config_sha256:str=Field(pattern=HASH)
    worker_admission_sha256:str=Field(pattern=HASH)
    operation_policy_sha256:str=Field(pattern=HASH)

@dataclass(frozen=True)
class _CaptureWorkerSettings:
    source:CaptureWorkerSettingsV1
    factory:CaptureWorkerFactoryV1
    peer:object
    @property
    def profile(self):return self.peer.profile
    def current(self):
        end=min(self.source.current(),self.peer.current());p=self.profile;c=self.source.config;b=self.source.capture
        if (type(p) is not CaptureWorkerPeerProfileV1 or p.effect_purpose!=c.effect or p.retrieve_stage!=c.retrieve_stage
            or p.worker_id!=c.worker_id or p.meeting_id!=b.config.meeting_id or p.provider_account!=b.config.provider_account
            or p.worker_config_sha256!=self.source.sha256 or p.worker_admission_sha256!=b.config.admission_sha256
            or p.operation_policy_sha256!=c.operation_policy_sha256):raise PermissionError('exact independent capture worker installation differs')
        if c.effect=='capture-create' and self.factory._unattended_supervisor is None:
            raise PermissionError('fixed unattended Create cannot use legacy direct constructor')
        return end

class _CaptureWorkerAdapter:
    def __init__(self,settings):
        if type(settings) is not _CaptureWorkerSettings or type(settings.factory) is not CaptureWorkerFactoryV1:raise PermissionError('same actual capture delivery owner required')
        self.settings=settings
    def _packet(self,value,deadline,body=None):
        s=self.settings;s.current();request_remaining_v1(required=True);p=s.profile;b=s.source.capture.host.config
        import base64
        return MeetingWorkerPacketV1(state=value.state,effect_purpose=p.effect_purpose,principal_id=b.principal_id,
            worker_id=p.worker_id,workspace_id=b.workspace_id,meeting_id=p.meeting_id,provider_account=p.provider_account,
            operation_id=value.operation_id,claim_event_id=value.claim_id,request_sha256=value.request_sha256,
            bot_id=value.bot_id,body_base64=base64.b64encode(body).decode() if body is not None else None,
            operation_policy_sha256=p.operation_policy_sha256,composer_program_sha256=None,
            valid_until=min(value.valid_until,deadline,s.current()),executable=value.fresh_claim,
            qualification=False,remote_stop_proven=False,observation_only=True,resend_authorized=False)
    def execute_v1(self,raw):
        q=_parse(MeetingWorkerRequestV1,raw);s=self.settings;s.current();request_remaining_v1(required=True);f=s.factory;body=None
        if q.operation=='prepare':value=f.prepare_v1(caller_deadline=q.caller_deadline)
        elif q.operation=='claim':value,body=f.claim_v1(q.operation_id,caller_deadline=q.caller_deadline)
        elif q.operation=='current':value=f.current_v1(q.operation_id,q.claim_event_id,caller_deadline=q.caller_deadline)
        elif q.operation=='observe':
            error={'transport_uncertain':'network','invalid_response':'framing','expired':'expired','cancelled':'unknown','local_failure':'unknown',None:None}[q.error]
            value=f.observe_v1(q.operation_id,q.claim_event_id,q.observed_wire(),error=error,caller_deadline=q.caller_deadline)
        else:value=f.status_v1(caller_deadline=q.caller_deadline)
        return self._packet(value,q.caller_deadline,body)

def _capture_worker_server(settings,path,sha256,effect,stage):
    if type(settings) is not CaptureWorkerSettingsV1 or settings.config.effect!=effect or settings.config.retrieve_stage!=stage:raise PermissionError('fixed source-selected capture role required')
    settings.current();peer=_load_peer_settings_v1(settings.capture.host,path,sha256,CaptureWorkerPeerProfileV1)
    factory=(CaptureWorkerFactoryV1.from_unattended_create_v1(settings) if effect=='capture-create' else CaptureWorkerFactoryV1(settings))
    fixed=_CaptureWorkerSettings(settings,factory,peer);fixed.current()
    return _protected_control_listener_v1(fixed,_CaptureWorkerAdapter(fixed),path='/v1/replacement/meetings/worker',
        parse_request=lambda raw:_parse(MeetingWorkerRequestV1,raw),encode_response=lambda value:canonical_bytes(value.model_dump(mode='json')),
        maximum_request_bytes=MAX_REQUEST_BYTES,maximum_response_bytes=131072)

def protected_meeting_create_worker_server_v1(settings,path,sha256):return _capture_worker_server(settings,path,sha256,'capture-create',None)
def protected_meeting_leave_worker_server_v1(settings,path,sha256):return _capture_worker_server(settings,path,sha256,'capture-leave',None)
def protected_meeting_pre_stop_retrieve_worker_server_v1(settings,path,sha256):return _capture_worker_server(settings,path,sha256,'capture-retrieve','pre-stop-consistency')
def protected_meeting_post_stop_retrieve_worker_server_v1(settings,path,sha256):return _capture_worker_server(settings,path,sha256,'capture-retrieve','post-stop-terminal')
