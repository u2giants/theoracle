"""Once-only meeting text custody, not source-reading or qualification authority.

Every admitted installation is independent. A spent intake claim is never
redispatched; explicit recovery can only observe the existing intake owner.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib, json
from pathlib import Path
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, model_validator, field_validator
from oracle_brain.operating_model.contracts import StrictRecord, digest
from .meeting_capture_v1 import MeetingCaptureSettingsV1, MeetingCaptureFactoryV1
from .original_intake_v1 import (OriginalIntakeSettingsV1, OriginalIntakeFactoryV1,
    RequesterContextV1, _pinned, _parse, _context_horizon)
from ._protected_control_listener_v1 import request_remaining_v1

HASH = r'^[a-f0-9]{64}$'


class MeetingNormalizationConfigV1(StrictRecord):
    schema_version: Literal[1]
    purpose: Literal['meeting-normalization-consumer-v1']
    capture_config_sha256: str = Field(pattern=HASH)
    intake_config_sha256: str = Field(pattern=HASH)
    intake_appointment_sha256: str = Field(pattern=HASH)
    intake_issuer_actor: UUID
    intake_reviewer_actor: UUID
    issuer_actor: UUID
    reviewer_actor: UUID
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    original_processing_horizon: AwareDatetime

    @field_validator('schema_version', mode='before')
    @classmethod
    def integer_schema(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('actual integer normalization schema required')
        return value

    @model_validator(mode='after')
    def independent(self):
        if (self.issuer_actor == self.reviewer_actor
                or self.intake_issuer_actor == self.intake_reviewer_actor
                or not self.valid_from < self.expires_at <= self.original_processing_horizon):
            raise ValueError('independent original finite normalization installation required')
        return self


@dataclass(frozen=True)
class MeetingNormalizationSettingsV1:
    capture: MeetingCaptureSettingsV1
    intake: OriginalIntakeSettingsV1
    config: MeetingNormalizationConfigV1
    config_path: Path
    config_sha256: str
    expected_issuer_actor: UUID
    expected_reviewer_actor: UUID

    def current(self):
        # Installation-only reads are valid at startup. Operational methods
        # separately require the actual original listener fence before effects.
        request_remaining_v1(required=False)
        c = self.config
        if (_parse(MeetingNormalizationConfigV1, _pinned(self.config_path, self.config_sha256)) != c
                or c.capture_config_sha256 != self.capture.config_sha256
                or c.intake_config_sha256 != self.intake.config_sha256
                or c.intake_appointment_sha256 != self.intake.appointment_sha256
                or c.intake_issuer_actor != self.intake.expected_issuer_actor
                or c.intake_reviewer_actor != self.intake.expected_reviewer_actor
                or c.issuer_actor != self.expected_issuer_actor
                or c.reviewer_actor != self.expected_reviewer_actor):
            raise PermissionError('normalization installation changed')
        principals = {self.capture.host.config.principal_id, self.intake.config.principal_id}
        if (principals & {c.issuer_actor, c.reviewer_actor}
                or self.capture.host.config.workspace_id != self.intake.config.workspace_id
                or 'text/plain' not in self.intake.appointment.media_types
                or 'create' not in self.intake.appointment.operations):
            raise PermissionError('independently appointed same-workspace text intake required')
        end = min(self.capture.current(), self.intake.current(), c.expires_at, c.original_processing_horizon)
        if not c.valid_from <= datetime.now(timezone.utc) < end:
            raise PermissionError('original normalization window elapsed')
        return end


def load_meeting_normalization_settings_v1(capture, intake, path, sha256, issuer, reviewer):
    if type(capture) is not MeetingCaptureSettingsV1 or type(intake) is not OriginalIntakeSettingsV1:
        raise TypeError('exact independently installed existing owner settings required')
    settings = MeetingNormalizationSettingsV1(capture, intake,
        _parse(MeetingNormalizationConfigV1, _pinned(path, sha256)), Path(path), sha256, issuer, reviewer)
    settings.current()
    return settings


def normalization_idempotency_key_v1(workspace, meeting, ingress):
    if any(type(x) is not UUID for x in (workspace, meeting, ingress)):
        raise TypeError('exact normalization scope UUIDs required')
    return UUID(bytes=hashlib.sha256(
        f'oracle2-meeting-normalization-v1/{workspace}/{meeting}/{ingress}'.encode()).digest()[:16])


class NormalizationSourceBindingV1(StrictRecord):
    workspace_id: UUID
    source_id: UUID
    revision: int = Field(ge=1)
    original_sha256: str = Field(pattern=HASH)
    byte_count: int = Field(ge=1, le=1048576)
    custody_seal_sha256: str = Field(pattern=HASH)
    qualification: Literal[False]
    source_read_permission: Literal[False]

    @field_validator('qualification', 'source_read_permission', mode='before')
    @classmethod
    def literal_observation(cls, value):
        if type(value) is not bool or value is not False:
            raise ValueError('literal unqualified observation required')
        return value


class NormalizationSQLV1(StrictRecord):
    meeting_id: UUID
    capture_until: AwareDatetime
    valid_until: AwareDatetime
    context: RequesterContextV1
    claim_id: UUID
    ingress_event_id: UUID
    state: Literal['intake_claimed', 'UNKNOWN', 'awaiting_independently_installed_exact_reading_review', 'source_unavailable']
    fresh_intake_claim: bool
    binding: dict
    original_effect_deadline: AwareDatetime
    original_processing_horizon: AwareDatetime
    source_binding: NormalizationSourceBindingV1 | None


@dataclass(frozen=True)
class ProcessedMeetingIngressV1:
    # Descriptive correlation to the ORIGINAL actual ingress. The final-event
    # relationship lives only in the existing operational SQL owner.
    ingress_event_id: UUID
    state: str
    valid_until: AwareDatetime
    source_binding: NormalizationSourceBindingV1 | None


class MeetingNormalizationFactoryV1:
    def __init__(self, settings):
        if type(settings) is not MeetingNormalizationSettingsV1:
            raise TypeError('exact fixed normalization installation required')
        settings.current()
        self.settings = settings
        self.capture = MeetingCaptureFactoryV1(settings.capture)
        self.intake = OriginalIntakeFactoryV1(settings.intake)

    def _call(self, command, event, deadline, *, binding=None, receipt=None):
        request_remaining_v1(required=True)
        from psycopg.conninfo import conninfo_to_dict
        from oracle_brain.operating_model.protected_sql_connection_v1 import _connection_v1
        from oracle_brain.operating_model.request_deadline_v1 import sql_execute_v1
        s = self.settings; c = s.capture.host.config
        if command not in ('claim', 'status', 'record_intake') or type(event) is not UUID:
            raise ValueError('closed normalization operation required')
        if not datetime.now(timezone.utc) < deadline <= s.current():
            raise PermissionError('original normalization deadline required')
        raw = _pinned(c.database_url.path, c.database_url.sha256, 16384).decode('utf-8')
        _pinned(c.database_ca.path, c.database_ca.sha256, 131072)
        target = conninfo_to_dict(raw)
        if target.get('sslrootcert') != c.database_ca.path or target.get('user') != c.expected_session_role:
            raise PermissionError('fixed normalization SQL target differs')
        with _connection_v1(raw, deadline) as conn:
            def execute(statement, args=None):
                s.current()
                return sql_execute_v1(conn, deadline, statement, args)
            actual = conn.info
            if (not conn.pgconn.ssl_in_use or actual.host != target['host']
                    or actual.dbname != target['dbname'] or actual.user != target['user']
                    or actual.port != int(target['port'])
                    or target.get('hostaddr') and actual.hostaddr != target['hostaddr']):
                raise PermissionError('actual normalization SQL target differs')
            if execute("SELECT SESSION_USER::text,CURRENT_USER::text,(SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2')").fetchone() != (c.expected_session_role, c.expected_session_role, c.expected_owner_role):
                raise PermissionError('actual normalization SQL role differs')
            name = 'oracle2.meeting_capture_normalization_v1(uuid,text,text,uuid,jsonb,jsonb,timestamptz)'
            if execute('SELECT pg_get_userbyid(proowner),prosecdef FROM pg_proc WHERE oid=to_regprocedure(%s)', (name,)).fetchone() != (c.expected_owner_role, True):
                raise PermissionError('actual normalization function owner differs')
            value = execute('SELECT oracle2.meeting_capture_normalization_v1(%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)',
                (s.capture.config.admission_id, s.capture.config.admission_sha256, command, event,
                 json.dumps(binding, allow_nan=False) if binding is not None else None,
                 json.dumps(receipt, allow_nan=False) if receipt is not None else None, deadline)).fetchone()[0]
            result = NormalizationSQLV1.model_validate_json(json.dumps(value))
            _context_horizon(s.capture.host, result.context)
            if (result.meeting_id != s.capture.config.meeting_id or result.ingress_event_id != event
                    or result.capture_until != s.capture.config.capture_until
                    or result.original_processing_horizon != s.config.original_processing_horizon
                    or not datetime.now(timezone.utc) < result.valid_until <= deadline
                    or result.source_binding is not None and result.source_binding.workspace_id != c.workspace_id):
                raise PermissionError('actual normalization scope differs')
            s.current()
        s.current(); _context_horizon(s.capture.host, result.context)
        return result

    def status_v1(self, ingress_event_id, *, caller_deadline):
        return self._call('status', ingress_event_id, caller_deadline)

    def process_ingress_v1(self, ingress_event_id, *, caller_deadline):
        """Closed actual raw→selected whole-final→once intake operation.

        Status/repeated delivery never grants another fetch or intake window.
        Missing independent descriptor/observation remains visible pending.
        Old direct actual-final normalization remains compatible.
        """
        request_remaining_v1(required=True);self.settings.current()
        if type(ingress_event_id) is not UUID:raise ValueError('exact opaque ingress identity required')
        receipt=self.capture.receipt_v1(ingress_event_id,caller_deadline=caller_deadline)
        if receipt.action=='final_artifact':return self.normalize_v1(ingress_event_id,caller_deadline=caller_deadline)
        if receipt.action!='ingress' or receipt.payload is None:raise PermissionError('actual own original ingress required')
        processing=self.capture.process_ingress_binding_v1('claim_fetch',ingress_event_id,caller_deadline=caller_deadline)
        if processing.original_processing_horizon!=self.settings.config.original_processing_horizon:
            raise PermissionError('same original independently installed processing horizon required')
        def visible(state,source=None):
            request_remaining_v1(required=True);end=min(caller_deadline,processing.valid_until,self.settings.current())
            if datetime.now(timezone.utc)>=end:raise PermissionError('original ingress operation elapsed')
            return ProcessedMeetingIngressV1(ingress_event_id,state,end,source)
        if processing.state=='final_artifact_pending':return visible('final_artifact_pending')
        if processing.observation_only:raise PermissionError('observation-only purpose never normalizes')
        original_end=processing.original_effect_deadline
        if original_end is None:return visible('UNKNOWN')
        final=processing.final_event_id
        if final is None and datetime.now(timezone.utc)<original_end:
            lease=min(caller_deadline,original_end,self.settings.current())
            if processing.fresh_fetch_claim:
                # The global SQL claim committed before any external byte read.
                # Existing exact final-artifact owner alone fetches and retains.
                final=self.capture.fetch_final_artifact_v1(caller_deadline=lease)
            else:
                # Lost reply can observe ONLY the actual existing canonical
                # final operation. It never repeats GET or guesses a new UUID.
                retained=self.capture.receipt_v1(processing.final_operation_id,caller_deadline=lease)
                if retained.action=='final_artifact' and retained.payload is not None:final=retained.event_id
            if final is not None:
                # Reopen actual current protected custody before linking. No
                # SQL is held over bytes; the owner checks again on return.
                self.capture.reopen_raw_v1(final,caller_deadline=lease)
                processing=self.capture.process_ingress_binding_v1('record_final',ingress_event_id,returned_final=final,caller_deadline=lease)
                if processing.state!='final_linked' or processing.final_event_id!=final:raise PermissionError('actual exact final relationship required')
        if final is None:return visible('UNKNOWN')
        if datetime.now(timezone.utc)>=original_end:
            # Expired original effect may expose existing current status only.
            # No automatic downstream first intake or fetch under a new window.
            try:result=self.status_v1(final,caller_deadline=caller_deadline)
            except PermissionError:raise
            except Exception as error:
                # Only the owner's exact closed absence means no first intake
                # happened. Revocation/currentness/connection errors still deny.
                import psycopg
                if not isinstance(error,psycopg.errors.InsufficientPrivilege) or error.diag.message_primary!='existing normalization claim required':raise
                return visible('UNKNOWN')
        else:result=self.normalize_v1(final,caller_deadline=min(caller_deadline,original_end))
        return visible(result.state,result.source_binding)

    def normalize_v1(self, ingress_event_id, *, caller_deadline):
        request_remaining_v1(required=True)
        s = self.settings; s.current()
        text, derivation = self.capture.prepare_reported_text_v1(ingress_event_id, caller_deadline=caller_deadline)
        if type(text) is not bytes or not 1 <= len(text) <= 1048576:
            raise ValueError('bounded exact independently attributed text required')
        text.decode('utf-8', errors='strict')
        from oracle_brain.meetings.final_mapping import FinalWorkspaceSpeakerMappingV1
        m = _parse(FinalWorkspaceSpeakerMappingV1,
                   _pinned(s.capture.config.speaker_mapping_file, s.capture.config.speaker_mapping_sha256))
        key = normalization_idempotency_key_v1(s.capture.host.config.workspace_id, s.capture.config.meeting_id, ingress_event_id)
        binding = dict(raw_sha256=derivation.raw.original_sha256, mapping_id=str(m.mapping_id),
            mapping_revision=m.mapping_revision, mapping_sha256=m.sha256,
            derivation_sha256=digest(derivation.model_dump(mode='json')), original_sha256=hashlib.sha256(text).hexdigest(),
            byte_count=len(text), create_selector=None, idempotency_key=str(key),
            intake_principal_id=str(s.intake.config.principal_id), intake_config_sha256=s.intake.config_sha256,
            intake_appointment_sha256=s.intake.appointment_sha256)
        claimed = self._call('claim', ingress_event_id, caller_deadline, binding=binding)
        if not claimed.fresh_intake_claim:
            return claimed
        # No network or SQL transaction survives the claim. A failure here
        # leaves the durable global claim spent; only explicit read-only
        # reconciliation may later recover an actual committed receipt.
        s.current()
        snapshot = self.intake.intake_text_v1(source_id=None, expected_head=0, idempotency_key=key,
            filename='meeting-transcript.txt', original_sha256=binding['original_sha256'], data=text,
            caller_deadline=min(caller_deadline, claimed.original_effect_deadline))
        return self._record(ingress_event_id, snapshot, caller_deadline)

    def _record(self, event, snapshot, deadline):
        if snapshot.mediaType != 'text/plain':
            raise PermissionError('actual original text intake receipt required')
        return self._call('record_intake', event, deadline, receipt=dict(source_id=str(snapshot.sourceId),
            revision=snapshot.revision, original_sha256=snapshot.originalSha256, byte_count=snapshot.byteCount))

    def reconcile_v1(self, ingress_event_id, *, caller_deadline):
        retained = self.status_v1(ingress_event_id, caller_deadline=caller_deadline)
        if retained.source_binding is not None or retained.state == 'source_unavailable':
            return retained
        key = normalization_idempotency_key_v1(self.settings.capture.host.config.workspace_id,
            self.settings.capture.config.meeting_id, ingress_event_id)
        actual = self.intake.reconcile_intake_v1(key, caller_deadline=caller_deadline)
        if actual.status != 'finalized':
            return retained
        return self._record(ingress_event_id, actual.snapshot, caller_deadline)
