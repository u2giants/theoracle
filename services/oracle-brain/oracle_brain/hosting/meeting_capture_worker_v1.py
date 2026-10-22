"""S07 delivery custody composed with the SAME operational capture SQL owner.

No provider client, employee adapter, installation issuer or second intent ledger.
Request bodies are independently pinned configuration and returned only after an
actual first durable SQL claim; subsequent delivery cannot expose them again.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import UUID
import hashlib,json
from pydantic import AwareDatetime,Field,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes
from oracle_brain.operating_model.protected_inputs_v1 import ProtectedInputV1
from oracle_brain.operating_model.artifact_storage import _write_private_at
from oracle_brain.meetings.capture_wire_v1 import observe_capture_wire_v1
from .original_intake_v1 import _pinned,_parse
from .meeting_capture_v1 import MeetingCaptureSettingsV1,MeetingCaptureFactoryV1
from ._protected_control_listener_v1 import request_remaining_v1
HASH=r'^[a-f0-9]{64}$'
class CaptureWorkerConfigV1(StrictRecord):
    purpose:Literal['meeting-capture-worker-consumer-v1']
    capture_config_sha256:str=Field(pattern=HASH)
    worker_id:UUID
    effect:Literal['capture-create','capture-leave','capture-retrieve']
    operation_policy_sha256:str=Field(pattern=HASH)
    create_operation_id:UUID|None
    create_body:ProtectedInputV1|None
    retrieve_stage:Literal['pre-stop-consistency','post-stop-terminal']|None
    retrieve_operation_id:UUID|None
    stop_mapping_sha256:str|None=Field(pattern=HASH)
    supervisor_admission:ProtectedInputV1|None=None
    supervisor_transport:ProtectedInputV1|None=None
    supervisor_replay:ProtectedInputV1|None=None
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    original_horizon:AwareDatetime
    @model_validator(mode='after')
    def exact(self):
        if self.issuer_actor==self.reviewer_actor or not self.valid_from<self.expires_at<=self.original_horizon:raise ValueError('independent original finite worker installation required')
        if (self.effect=='capture-create')!=(self.create_operation_id is not None and self.create_body is not None):raise ValueError('exact externally pinned create operation and body required')
        if self.effect!='capture-create' and (self.create_operation_id is not None or self.create_body is not None):raise ValueError('create body never belongs to STOP/read-only delivery')
        if (self.effect=='capture-retrieve')!=(self.retrieve_stage is not None and self.retrieve_operation_id is not None):raise ValueError('exact independently installed retrieval stage required')
        if self.effect!='capture-retrieve' and (self.retrieve_stage is not None or self.retrieve_operation_id is not None):raise ValueError('retrieval stage is not a caller selector')
        if (self.effect in ('capture-leave','capture-retrieve'))!=(self.stop_mapping_sha256 is not None):raise ValueError('exact independently installed STOP relationship required')
        pins=(self.supervisor_admission,self.supervisor_transport,self.supervisor_replay)
        if any(x is not None for x in pins) and (any(x is None for x in pins) or self.effect!='capture-create'):
            raise ValueError('complete separate supervisor pins belong only to unattended Create')
        return self
def _parse_capture_worker_config_v1(raw):
    try:return _parse(CaptureWorkerConfigV1,raw)
    except ValueError:
        # Exactly the retained pre-supervisor wire, never partial/new pins.
        fields={'supervisor_admission','supervisor_transport','supervisor_replay'}
        value=CaptureWorkerConfigV1.model_validate_json(raw)
        if fields & set(json.loads(raw)) or canonical_bytes(value.model_dump(mode='json',exclude=fields))!=raw:raise
        return value

@dataclass(frozen=True)
class CaptureWorkerSettingsV1:
    capture:MeetingCaptureSettingsV1
    config:CaptureWorkerConfigV1
    path:Path
    sha256:str
    def current(self):
        c=self.config
        if _parse_capture_worker_config_v1(_pinned(self.path,self.sha256))!=c or c.capture_config_sha256!=self.capture.config_sha256:raise PermissionError('installed worker changed')
        if self.capture.config.channel!='worker' or self.capture.host.config.principal_id in (c.issuer_actor,c.reviewer_actor):raise PermissionError('separate independent worker service required')
        now=datetime.now(timezone.utc);end=min(self.capture.current(),c.expires_at,c.original_horizon)
        if c.original_horizon>self.capture.config.original_horizon or not c.valid_from<=now<end:raise PermissionError('original worker horizon elapsed')
        return end

def load_capture_worker_settings_v1(capture,path,sha256):
    if type(capture) is not MeetingCaptureSettingsV1:raise PermissionError('same exact installed capture owner required')
    value=CaptureWorkerSettingsV1(capture,_parse_capture_worker_config_v1(_pinned(path,sha256)),Path(path),sha256);value.current();return value

class CaptureWorkerFactoryV1:
    def __init__(self,settings):
        if type(settings) is not CaptureWorkerSettingsV1:raise PermissionError('exact independent capture worker installation required')
        settings.current();self.settings=settings;self.capture=MeetingCaptureFactoryV1(settings.capture);self._unattended_supervisor=None
    @classmethod
    def from_unattended_create_v1(cls,settings):
        if cls is not CaptureWorkerFactoryV1 or type(settings) is not CaptureWorkerSettingsV1 or settings.config.effect!='capture-create':
            raise PermissionError('fixed unattended Create owner required')
        from .meeting_capture_supervisor_v1 import load_capture_supervisor_consumer_v1
        value=cls(settings);value._unattended_supervisor=load_capture_supervisor_consumer_v1(settings)
        return value
    def _fresh_supervision(self,deadline):
        if self._unattended_supervisor is not None:
            self._check(deadline);self._unattended_supervisor.current(deadline=deadline);self._check(deadline)
    def _check(self,deadline):
        request_remaining_v1(required=True);end=self.settings.current();now=datetime.now(timezone.utc)
        if type(deadline) is not datetime or deadline.tzinfo is None or not now<deadline<=end or (deadline-now).total_seconds()>30:raise PermissionError('unchanged original worker deadline required')
    def _delivery(self,command,*,operation_id=None,claim_id=None,body_sha256=None,wire=None,caller_deadline):
        self._check(caller_deadline)
        result=self.capture._worker_delivery_v1(command,operation_id=operation_id,claim_id=claim_id,body_sha256=body_sha256,wire=wire,caller_deadline=caller_deadline)
        c=self.settings.config
        if (result.worker_id!=c.worker_id or result.effect!=c.effect or result.operation_policy_sha256!=c.operation_policy_sha256
            or c.effect!='capture-create' and result.stop_mapping_sha256!=c.stop_mapping_sha256
            or result.stage!=(c.retrieve_stage or '-') or c.effect=='capture-create' and (result.operation_id!=c.create_operation_id or result.request_sha256!=c.create_body.sha256)
            or c.effect=='capture-retrieve' and result.operation_id!=c.retrieve_operation_id):raise PermissionError('actual SQL worker installation differs')
        self._check(caller_deadline);return result
    def prepare_v1(self,*,caller_deadline):
        # The fixed unattended constructor independently observes the actual
        # producer. Retained direct compatibility still requires its SQL fact.
        self._fresh_supervision(caller_deadline)
        return self._delivery('prepare',caller_deadline=caller_deadline)
    def _body(self):
        c=self.settings.config
        if c.effect!='capture-create':return b''
        body=_pinned(c.create_body.path,c.create_body.sha256,65536)
        if not body:raise PermissionError('nonempty independently pinned create body required')
        return body
    def claim_v1(self,operation_id,*,caller_deadline):
        # Fresh own SQL/root before private bytes. This read is never a grant.
        prepared=self.prepare_v1(caller_deadline=caller_deadline)
        if prepared.operation_id!=operation_id:raise PermissionError('exact actual prepared operation required')
        if prepared.state!='prepared':return prepared,None
        body=self._body();self._check(caller_deadline)
        claimed=self._delivery('claim',operation_id=operation_id,body_sha256=hashlib.sha256(body).hexdigest(),caller_deadline=caller_deadline)
        if not claimed.fresh_claim:return claimed,None
        if self._body()!=body:raise PermissionError('actual claimed private bytes changed')
        self._check(caller_deadline);return claimed,body
    def current_v1(self,operation_id,claim_id,*,caller_deadline):
        # Actual TS provider channel invokes this after its verified TLS and
        # before Authorization/body, under the unchanged original request end.
        self._fresh_supervision(caller_deadline)
        result=self._delivery('current',operation_id=operation_id,claim_id=claim_id,caller_deadline=caller_deadline)
        body=self._body()
        if hashlib.sha256(body).hexdigest()!=result.request_sha256:raise PermissionError('actual current body changed')
        return self._delivery('current',operation_id=operation_id,claim_id=claim_id,caller_deadline=caller_deadline)
    def status_v1(self,*,caller_deadline):return self._delivery('status',caller_deadline=caller_deadline)
    def observe_v1(self,operation_id,claim_id,raw,*,error=None,caller_deadline):
        prior=self.status_v1(caller_deadline=caller_deadline)
        if (prior.operation_id!=operation_id or prior.claim_id!=claim_id or prior.claim_admission_id!=self.settings.capture.config.admission_id
            or prior.claim_worker_id!=self.settings.config.worker_id or prior.claim_original_deadline is None
            or caller_deadline>prior.claim_original_deadline):raise PermissionError('exact retained own claim required')
        observed=observe_capture_wire_v1(raw,effect=self.settings.config.effect,expected_bot=prior.bot_id,error=error)
        sha=hashlib.sha256(raw).hexdigest();host=self.settings.capture.host.config
        key=f'meeting-worker/{host.workspace_id}/{self.settings.capture.config.meeting_id}/{claim_id}/{sha}.wire'
        self._check(caller_deadline)
        _write_private_at(Path(host.storage_root),key.split('/'),raw,expected_root=(host.storage_device,host.storage_inode,host.storage_uid))
        self._check(caller_deadline)
        return self._delivery('observe',operation_id=operation_id,claim_id=claim_id,
            wire=dict(wire_object_key=key,wire_sha256=sha,wire_byte_count=len(raw),observation=observed),caller_deadline=caller_deadline)
