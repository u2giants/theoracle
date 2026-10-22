"""Installed participation owner composed with SAME protected S07 byte reader.

No provider call, observation producer, employee permission or appointment issuer.
The public caller supplies opaque event/intent selectors only, never turn bytes.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID,uuid5

from pydantic import AwareDatetime, Field, model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes
from oracle_brain.meetings.participation_authority_v1 import (
    ParticipationAuthorityV1, ParticipationSQLBindingV1, ParticipationOutcomeUnknown,
    participation_operation_policy_sha256_v1,
)
from oracle_brain.meetings.participation_runtime_v1 import compose_current_turn_v1,is_addressed_current_turn_v1,ParticipationDeclined
from .original_intake_v1 import _pinned, _parse

HASH = r'^[a-f0-9]{64}$'
_INTENT_NAMESPACE=UUID('8f8c7230-02bd-568f-914b-e8530a4b72e1')
_PREPARE_NAMESPACE=UUID('bd7c8cf4-e868-585d-9588-78f939cdd9b6')


class MeetingParticipationConfigV1(StrictRecord):
    schema_version: Literal[1]
    purpose: Literal['meeting-participation-factory-v1']
    host_config_sha256: str = Field(pattern=HASH)
    host_appointment_sha256: str = Field(pattern=HASH)
    capture_config_sha256: str = Field(pattern=HASH)
    admission_id: UUID
    admission_sha256: str = Field(pattern=HASH)
    principal_id: UUID
    workspace_id: UUID
    meeting_id: UUID
    kind: Literal['host','sender','observer']
    runtime_hash: str = Field(pattern=HASH)
    registry_hash: str = Field(pattern=HASH)
    composer_sha256: str = Field(pattern=HASH)
    observation_owner_sha256: str = Field(pattern=HASH)
    capability_hashes: tuple[tuple[str,str], ...]
    issuer_actor: UUID
    reviewer_actor: UUID
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    original_horizon: AwareDatetime

    @model_validator(mode='after')
    def independent(self):
        if (self.issuer_actor == self.reviewer_actor or self.principal_id in (self.issuer_actor,self.reviewer_actor)
                or not self.valid_from < self.expires_at <= self.original_horizon):
            raise ValueError('independent finite participation installation required')
        return self


@dataclass(frozen=True)
class MeetingParticipationSettingsV1:
    capture_settings: object
    config: MeetingParticipationConfigV1
    config_path: Path
    config_sha256: str
    expected_issuer_actor: UUID
    expected_reviewer_actor: UUID

    def current(self):
        from .meeting_capture_v1 import MeetingCaptureSettingsV1
        from ._protected_control_listener_v1 import request_remaining_v1
        request_remaining_v1(required=False)
        if type(self.capture_settings) is not MeetingCaptureSettingsV1:
            raise PermissionError('same actual installed capture settings required')
        current = _parse(MeetingParticipationConfigV1,_pinned(self.config_path,self.config_sha256))
        c = self.config; s = self.capture_settings; h = s.host
        if (current != c or c.issuer_actor != self.expected_issuer_actor or c.reviewer_actor != self.expected_reviewer_actor
                or c.host_config_sha256 != h.config_sha256 or c.host_appointment_sha256 != h.appointment_sha256
                or c.capture_config_sha256 != s.config_sha256):
            raise PermissionError('exact installed participation/capture pins changed')
        for key in ('principal_id','workspace_id','runtime_hash','registry_hash'):
            if getattr(c,key) != getattr(h.config,key):
                raise PermissionError('same actual participation principal/workspace required')
        if c.meeting_id != s.config.meeting_id:
            raise PermissionError('exact installed meeting required')
        # Source bytes pin the single deterministic implementation. Configuration
        # cannot select another composer, model, provider, role or transport.
        from oracle_brain.meetings import participation_runtime_v1
        source = Path(participation_runtime_v1.__file__).read_bytes()
        if sha256(source).hexdigest() != c.composer_sha256:
            raise PermissionError('fixed deterministic composer source changed')
        until = min(s.current(),c.expires_at,c.original_horizon)
        if not c.valid_from <= datetime.now(timezone.utc) < until:
            raise PermissionError('original participation installation elapsed')
        return until


def load_meeting_participation_settings_v1(capture_settings,path,expected_sha256,expected_issuer_actor,expected_reviewer_actor):
    config = _parse(MeetingParticipationConfigV1,_pinned(path,expected_sha256))
    settings = MeetingParticipationSettingsV1(capture_settings,config,Path(path),expected_sha256,
        expected_issuer_actor,expected_reviewer_actor)
    settings.current()
    return settings


class MeetingParticipationFactoryV1:
    def __init__(self, settings, capture_factory):
        from .meeting_capture_v1 import MeetingCaptureFactoryV1
        if type(settings) is not MeetingParticipationSettingsV1 or type(capture_factory) is not MeetingCaptureFactoryV1:
            raise PermissionError('exact installed participation and source owners required')
        if capture_factory.settings is not settings.capture_settings:
            raise PermissionError('same fixed protected capture owner required')
        self.settings = settings
        self._capture = capture_factory
        settings.current()
        s = settings.capture_settings.host; c = settings.config
        # Same protected descriptor ownership and URL/CA pins as the actual S07
        # appointment. No request-supplied role/URL/credential/storage selector.
        url = _pinned(s.config.database_url.path,s.config.database_url.sha256).decode('utf8')
        binding = ParticipationSQLBindingV1(c.admission_id,c.admission_sha256,c.principal_id,c.workspace_id,c.meeting_id,
            s.config.expected_session_role,s.config.expected_owner_role,c.kind,c.runtime_hash,c.registry_hash,
            s.config.database_ca.path,s.config.database_ca.sha256,min(c.original_horizon,s.config.original_horizon),c.capability_hashes)
        self._authority = ParticipationAuthorityV1(url,binding=binding,_runtime_recheck=settings.current)

    @property
    def operation_policy_sha256(self):
        self.settings.current()
        c=self.settings.config
        return participation_operation_policy_sha256_v1(c.composer_sha256,c.capability_hashes)

    def _deadline(self, value):
        from ._protected_control_listener_v1 import request_remaining_v1
        request_remaining_v1(required=True)
        self._authority._deadline(value)
        if value > self.settings.current():
            raise PermissionError('caller original deadline exceeds installed capture horizon')
        return value

    @staticmethod
    def _frame(turn):
        from .meeting_capture_v1 import MeetingCurrentParticipantTurnV1
        if type(turn) is not MeetingCurrentParticipantTurnV1:
            raise PermissionError('actual protected current participant turn required')
        if (turn.purpose != 'meeting-only-current-participant-turn-v1' or turn.attribution != 'workspace_actor'
                or turn.reported_only is not True or turn.qualification is not False
                or turn.shared_source_permission is not False or turn.employee_identity_verified is not False
                or sha256(turn.text.encode('utf8')).hexdigest() != turn.normalized_sha256):
            raise PermissionError('exact reported-only current turn required')
        c = turn.capture
        return dict(capture_event_id=str(c.capture_event_id),capture_event_sha256=c.capture_event_sha256,
            capture_revision=c.capture_revision,raw_sha256=turn.raw_sha256,normalized_sha256=turn.normalized_sha256,
            participant_epoch_id=str(turn.participant_epoch_id),participant_epoch_revision=turn.participant_epoch_revision,
            participant_epoch_sha256=turn.participant_epoch_sha256,participant_set_sha256=turn.participant_set_sha256,
            provider_speaker_id=turn.provider_speaker_id,actor_id=str(turn.actor_id))

    def _turn(self, event_id, deadline):
        self._deadline(deadline)
        turn = self._capture.read_current_participant_turn_v1(event_id,caller_deadline=deadline)
        frame = self._frame(turn)
        if frame['capture_event_id'] != str(event_id):
            raise PermissionError('actual own current event selector changed')
        if datetime.now(timezone.utc) >= min(turn.valid_until,deadline,self.settings.current()):
            raise PermissionError('current normalized turn expired')
        return turn,frame

    def status_v1(self, intent_id=None, *, caller_deadline):
        self._deadline(caller_deadline)
        result = self._authority.status_v1(intent_id,deadline=caller_deadline)
        self._deadline(caller_deadline)
        return result

    def status_latest_v1(self, *, caller_deadline):
        self._deadline(caller_deadline)
        result=self._authority.status_latest_v1(deadline=caller_deadline)
        self._deadline(caller_deadline)
        return result

    def prepare_latest_v1(self, *, caller_deadline):
        """Fixed dynamic composer, no caller text/event/body or authority mint.

        UUIDs identify the SAME actual turn forever; they are not provider keys
        or grants. Existing intent/UNKNOWN/observed facts only reconcile.
        """
        self._deadline(caller_deadline)
        binding,proactive_enabled=self._authority._latest_prepare_binding_v1(deadline=caller_deadline)
        if binding['existing_intent_id'] is not None:
            return self.status_v1(UUID(binding['existing_intent_id']),caller_deadline=caller_deadline)
        event_id=UUID(binding['capture_event_id'])
        turn,frame=self._turn(event_id,caller_deadline)
        proactive=not is_addressed_current_turn_v1(turn.text)
        if proactive and not proactive_enabled:
            raise ParticipationDeclined('explicit address absent and proactive participation is off')
        c=self.settings.config
        name=f'{c.workspace_id}/{c.meeting_id}/{event_id}'
        return self.prepare_v1(event_id,expected_head=binding['head_revision'],operation=uuid5(_PREPARE_NAMESPACE,name),
            intent_id=uuid5(_INTENT_NAMESPACE,name),proactive=proactive,caller_deadline=caller_deadline)

    def control_v1(self, *, expected_head, operation, enabled, proactive_enabled=False,
                   cooldown_seconds=120,max_proactive=3,caller_deadline):
        self._deadline(caller_deadline)
        # Observation identity is derived from actual own SQL, never a host
        # declaration of platform/chat/current recipients.
        current = self._authority.status_v1(None,deadline=caller_deadline)
        observation = UUID(current['observation_id']) if enabled and current['observation_id'] else None
        result = self._authority.control_v1(expected_head=expected_head,operation=operation,enabled=enabled,
            proactive_enabled=proactive_enabled,cooldown_seconds=cooldown_seconds,max_proactive=max_proactive,
            observation_id=observation,deadline=caller_deadline)
        try:
            self._deadline(caller_deadline)
        except Exception:
            raise ParticipationOutcomeUnknown('host control outcome UNKNOWN; read-only reconciliation only') from None
        return result

    def prepare_v1(self, event_id, *, expected_head, operation, intent_id, proactive=False,caller_deadline):
        if type(event_id) is not UUID:
            raise PermissionError('opaque actual current event selector required')
        self._deadline(caller_deadline)
        before,_=self._authority._latest_prepare_binding_v1(deadline=caller_deadline)
        if before['capture_event_id']!=str(event_id) or before['head_revision']!=expected_head:
            raise PermissionError('actual latest eligible turn/head changed before bytes')
        turn,frame = self._turn(event_id,caller_deadline)
        compose_current_turn_v1(turn.text,proactive=proactive)
        after,_=self._authority._latest_prepare_binding_v1(deadline=caller_deadline)
        if {k:v for k,v in before.items() if k!='valid_until'}!={k:v for k,v in after.items() if k!='valid_until'}:
            raise PermissionError('actual host/source/turn preparation changed during bytes')
        current = self._authority.status_v1(None,deadline=caller_deadline)
        if current['observation_id'] is None:
            raise PermissionError('independent current chat observation unavailable')
        result = self._authority._prepare_current_turn_v1(expected_head=expected_head,operation=operation,intent_id=intent_id,
            frame=frame,text=turn.text,proactive=proactive,observation_id=UUID(current['observation_id']),
            composer_sha256=self.settings.config.composer_sha256,deadline=caller_deadline)
        try:
            fresh,fresh_frame = self._turn(event_id,caller_deadline)
            if fresh_frame != frame or fresh.text != turn.text:
                raise PermissionError('actual turn changed after committed intent')
            final,_=self._authority._latest_prepare_binding_v1(deadline=caller_deadline)
            if (final['capture_event_id']!=str(event_id) or final['existing_intent_id']!=str(intent_id)
                    or final['generation']!=before['generation'] or final['head_revision']!=expected_head+1):
                raise PermissionError('actual host/source/composer changed after committed intent')
            self._deadline(caller_deadline)
        except Exception:
            raise ParticipationOutcomeUnknown('reply intent outcome UNKNOWN; read-only reconciliation only, no resend') from None
        return result

    def claim_v1(self, intent_id, *, expected_revision, operation,caller_deadline):
        self._deadline(caller_deadline)
        current=self._authority.status_v1(intent_id,deadline=caller_deadline)
        if current['state']!='intent':
            # A terminal or uncertain repeat can reconcile but never reopen
            # private turn bytes or obtain another provider body.
            return self._authority.claim_v1(intent_id=intent_id,expected_revision=expected_revision,operation=operation,deadline=caller_deadline)
        frame,proactive,_ = self._authority._current_turn_binding_v1(intent_id,deadline=caller_deadline)
        turn,actual = self._turn(UUID(frame['capture_event_id']),caller_deadline)
        if actual != frame:
            raise PermissionError('immutable current intent source changed before claim')
        result = self._authority.claim_v1(intent_id=intent_id,expected_revision=expected_revision,operation=operation,deadline=caller_deadline)
        try:
            fresh,fresh_frame = self._turn(UUID(frame['capture_event_id']),caller_deadline)
            if fresh_frame != frame or fresh.text != turn.text:
                raise PermissionError('actual turn changed after once-only claim')
            if result.body is not None and (str(result.bot_id) != str(turn.capture.bot_id) or str(result.bot_id) != str(fresh.capture.bot_id)):
                raise PermissionError('actual current captured bot differs from committed claim')
            if result.body is not None:
                composed=compose_current_turn_v1(fresh.text,proactive=proactive)
                if result.body != canonical_bytes({'to':'everyone','message':composed.message}):
                    raise PermissionError('committed provider body differs from same current protected turn')
                final=self._authority.status_v1(intent_id,deadline=caller_deadline)
                if (final['claim_current'] is not True or final['claim_event_id']!=result.metadata['claim_event_id']
                        or final['request_sha256']!=result.metadata['request_sha256']):
                    raise PermissionError('current exact host/source/claim changed after bytes')
            self._deadline(caller_deadline)
        except Exception:
            raise ParticipationOutcomeUnknown('send claim outcome UNKNOWN; no provider bytes, no resend') from None
        return result

    def current_claim_v1(self, intent_id, claim_event_id, request_sha256, *, caller_deadline):
        self._deadline(caller_deadline)
        frame,_,_ = self._authority._current_turn_binding_v1(intent_id,deadline=caller_deadline)
        _,actual = self._turn(UUID(frame['capture_event_id']),caller_deadline)
        current = self._authority.status_v1(intent_id,deadline=caller_deadline)
        if (actual != frame or current['claim_current'] is not True
                or current['claim_event_id'] != str(claim_event_id) or current['request_sha256'] != request_sha256):
            raise PermissionError('same actual current source and own inflight claim required')
        self._deadline(caller_deadline)
        return current

    def receipt_identity_v1(self,intent_id,claim_event_id,*,caller_deadline):
        self._deadline(caller_deadline)
        identity=self._authority.receipt_identity_v1(intent_id,claim_event_id,deadline=caller_deadline)
        self._deadline(caller_deadline)
        return identity

    def receipt_v1(self, intent_id, *, claim_event_id, operation, raw_wire,error=None,caller_deadline):
        # Forensic completion deliberately does not require host/source-current
        # serving authority. Own finite receipt/root/context remains mandatory.
        if any(type(v) is not UUID for v in (intent_id,claim_event_id,operation)):
            raise PermissionError('exact own immutable receipt selectors required')
        self._deadline(caller_deadline)
        from oracle_brain.meetings.participation_wire_v1 import observed_participation_wire_v1
        from oracle_brain.operating_model.artifact_storage import _write_private_at
        wire=observed_participation_wire_v1(raw_wire,error=error)
        request_hash,_=self._authority._current_receipt_binding_v1(intent_id,claim_event_id,deadline=caller_deadline)
        c=self.settings.config;h=self.settings.capture_settings.host.config
        key=f'meeting-participation/{c.workspace_id}/{c.meeting_id}/{intent_id}/{claim_event_id}/provider-response.wire'
        wire.update(request_sha256=request_hash,response_object_key=key)
        # No SQL transaction is held over private bytes. Slow/failed filesystem
        # work never permits later SQL/finalization/success; exact own orphan is
        # retained for read-only reconciliation, never a new send.
        try:
            self._deadline(caller_deadline)
            _write_private_at(Path(h.storage_root),key.split('/'),raw_wire,
                expected_root=(h.storage_device,h.storage_inode,h.storage_uid))
            self._deadline(caller_deadline)
            fresh_hash,_=self._authority._current_receipt_binding_v1(intent_id,claim_event_id,deadline=caller_deadline)
            if fresh_hash!=request_hash:
                raise PermissionError('own committed claim changed during wire custody')
        except Exception:
            raise ParticipationOutcomeUnknown('forensic custody outcome UNKNOWN; preserve own receipt, no resend') from None
        result = self._authority.receipt_v1(intent_id=intent_id,claim_event_id=claim_event_id,operation=operation,
            wire=wire,deadline=caller_deadline)
        try:
            self._deadline(caller_deadline)
        except Exception:
            raise ParticipationOutcomeUnknown('receipt outcome UNKNOWN; read-only reconciliation only, no resend') from None
        return result
