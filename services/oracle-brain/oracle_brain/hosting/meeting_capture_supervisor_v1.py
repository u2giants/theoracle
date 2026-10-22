"""Closed installed consumer of the existing independent supervisor owner.

No signer, process issuer, replay initializer, SQL connection or alternative
transport lives here. A fresh observation does not renew the original intent.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from pydantic import Field
from oracle_brain.operating_model.contracts import StrictRecord
from oracle_brain.operating_model.protected_inputs_v1 import ProtectedInputV1
from .original_intake_v1 import _pinned, _parse
from .parent_observer_v2 import (MeetingSupervisorAdmissionV2,
    MeetingSupervisorClientV2, MeetingSupervisorConsumerV2)
from .purpose_transport import PurposeTLSBindingV2
from .custody import DurableNonceSequenceV2


class SupervisorClientInstallationV1(StrictRecord):
    purpose: Literal['meeting-supervisor-client-installation-v1']
    hostname: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    server_uri: str = Field(min_length=1, max_length=512)
    client_uri: str = Field(min_length=1, max_length=512)
    ca_file: ProtectedInputV1
    certificate_file: ProtectedInputV1
    key_file: ProtectedInputV1


class SupervisorReplayInstallationV1(StrictRecord):
    purpose: Literal['meeting-supervisor-replay-installation-v1']
    spool: str = Field(min_length=1, max_length=2048)
    namespace: Literal['meeting-create']
    initialization_receipt_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


@dataclass(frozen=True)
class _InstalledCaptureSupervisorV1:
    settings: object
    admission: MeetingSupervisorAdmissionV2
    transport: SupervisorClientInstallationV1
    replay: SupervisorReplayInstallationV1
    consumer: MeetingSupervisorConsumerV2

    def _current_pins(self):
        self.settings.current()
        c = self.settings.config
        for record, ref in ((self.admission, c.supervisor_admission),
                            (self.transport, c.supervisor_transport),
                            (self.replay, c.supervisor_replay)):
            if ref is None or _parse(type(record), _pinned(ref.path, ref.sha256)) != record:
                raise PermissionError('independently installed supervisor consumer changed')
        for ref in (self.transport.ca_file, self.transport.certificate_file, self.transport.key_file):
            _pinned(ref.path, ref.sha256, 131072)

    def current(self, *, deadline):
        self._current_pins()
        result = self.consumer.current(self.admission.scope, deadline=deadline)
        self._current_pins()
        return result


def load_capture_supervisor_consumer_v1(settings):
    from .meeting_capture_worker_v1 import CaptureWorkerSettingsV1
    if type(settings) is not CaptureWorkerSettingsV1 or settings.config.effect != 'capture-create':
        raise PermissionError('fixed unattended Create installation required')
    settings.current(); c = settings.config
    if any(x is None for x in (c.supervisor_admission, c.supervisor_transport, c.supervisor_replay)):
        raise PermissionError('concrete independently installed supervisor consumer required')
    admission = _parse(MeetingSupervisorAdmissionV2, _pinned(c.supervisor_admission.path, c.supervisor_admission.sha256))
    transport = _parse(SupervisorClientInstallationV1, _pinned(c.supervisor_transport.path, c.supervisor_transport.sha256))
    replay = _parse(SupervisorReplayInstallationV1, _pinned(c.supervisor_replay.path, c.supervisor_replay.sha256))
    scope = admission.scope; capture = settings.capture; host = capture.host.config
    if (admission.max_age_seconds != 2 or scope.workspace_id != host.workspace_id
            or scope.meeting_id != capture.config.meeting_id
            or scope.provider_account != capture.config.provider_account
            or scope.capture_until != capture.config.capture_until
            or scope.create_operation_id != c.create_operation_id
            or scope.create_request_sha256 != c.create_body.sha256
            or scope.original_horizon > capture.config.original_horizon
            or host.principal_id in (admission.principal_id, admission.issuer_actor, admission.reviewer_actor)
            or admission.observer_uri != transport.server_uri or admission.client_uri != transport.client_uri):
        raise PermissionError('same exact independently supervised original Create scope required')
    spool = Path(replay.spool)
    if not spool.is_absolute() or str(spool.resolve()) != replay.spool:
        raise PermissionError('canonical independently provisioned replay spool required')
    for ref in (transport.ca_file, transport.certificate_file, transport.key_file):
        _pinned(ref.path, ref.sha256, 131072)
    binding = PurposeTLSBindingV2(hostname=transport.hostname, port=transport.port,
        server_uri=transport.server_uri, client_uri=transport.client_uri,
        ca_file=Path(transport.ca_file.path), certificate_file=Path(transport.certificate_file.path),
        key_file=Path(transport.key_file.path), timeout=2.)
    durable = DurableNonceSequenceV2(spool, namespace=replay.namespace,
        appointment_hash=c.supervisor_admission.sha256, minimum_sequence=admission.minimum_sequence,
        initialization_receipt_hash=replay.initialization_receipt_sha256)
    consumer = MeetingSupervisorConsumerV2(admission=admission,
        trusted_admission_hash=c.supervisor_admission.sha256,
        transport=MeetingSupervisorClientV2(binding), replay=durable)
    result = _InstalledCaptureSupervisorV1(settings, admission, transport, replay, consumer)
    result._current_pins()
    return result
