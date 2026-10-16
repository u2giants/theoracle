"""Explicit source-extraction profile; documentary defaults remain untouched.

No startup, SQL authority, source grant, provider spending or live admission is
issued here. Metadata workers never load the raw parent/provider registry.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from uuid import UUID

from oracle_brain.operating_model.contracts import canonical_bytes, digest
from oracle_brain.operating_model.processing_context import (
    ProcessingEnvelope, ProcessingPins, ProcessingProjection,
    QualifiedProcessingSources, ProcessingAuthorityProof, derive_processing_descriptor,
)
from .provider_runtime import CurrentJobs, pinned
from .gateway import OpaqueGateway, unique_object
from .custody import FileCustody


def _typed(path, seal, model):
    raw = pinned(path, seal)
    value = json.loads(raw, object_pairs_hook=unique_object,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite processing input')))
    return model.model_validate_json(json.dumps(value))


class ProcessingCurrentJobs(CurrentJobs):
    """Provider-side only: reuse unchanged parent context/resolve validation."""
    def __init__(self, parent: CurrentJobs, *, envelope_path, qualification_path,
                 pins: ProcessingPins, clock=lambda: datetime.now(timezone.utc)):
        if not isinstance(parent, CurrentJobs) or type(pins) is not ProcessingPins:
            raise PermissionError('trusted parent and externally reviewed startup pins required')
        super().__init__(dict(parent.config))
        self.parent, self.envelope_path, self.qualification_path = parent, envelope_path, qualification_path
        self.pins, self.clock = pins, clock

    def snapshot(self):
        pins = self.pins
        if (self.parent.config.get('job_registry_hash') != pins.parent_registry_sha256
                or self.parent.config.get('runtime_hash') != pins.runtime_hash):
            raise PermissionError('parent configuration differs from external pins')
        raw_parent = pinned(self.parent.config['job_registry_file'], pins.parent_registry_sha256)
        json.loads(raw_parent, object_pairs_hook=unique_object,
                   parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite parent input')))
        parent = self.parent.registry()
        envelope = _typed(self.envelope_path, pins.envelope_sha256, ProcessingEnvelope)
        qualification = _typed(self.qualification_path, pins.qualification_sha256, QualifiedProcessingSources)
        descriptor = derive_processing_descriptor(parent, envelope, qualification, pins=pins, now=self.clock())
        projection = ProcessingProjection(descriptor=descriptor,
                                          descriptor_sha256=digest(descriptor.model_dump(mode='json')))
        if (projection.descriptor_sha256 != pins.descriptor_sha256
                or digest(projection.model_dump(mode='json')) != pins.projection_sha256):
            raise PermissionError('descriptor/projection differs from independent startup pins')
        # Re-read exact parent bytes after all derivation, closing local mutation.
        pinned(self.parent.config['job_registry_file'], pins.parent_registry_sha256)
        return parent, projection

    def registry(self):
        return self.snapshot()[0]

    def projection_bytes(self):
        return canonical_bytes(self.snapshot()[1].model_dump(mode='json'))

    def authorize(self, _job):
        raise PermissionError('processing source SQL/budget broker admission is not installed by this profile')


@dataclass(frozen=True)
class ProcessingLease:
    projection: ProcessingProjection
    dispatch_id: UUID
    lease_expires_at: int

    @property
    def descriptor(self):
        return self.projection.descriptor

    @property
    def dispatch(self):
        return next(d for d in self.descriptor.dispatches if d.dispatch_id == self.dispatch_id)


class ProcessingMetadataJobs:
    """Gateway-side metadata only; live authority/parent observer are mandatory.

    current_parent_seal must resolve the current protected parent hash through a
    separately admitted observer. live_authority.hold must use actual bound SQL
    role/dual-grant checks. No default observer or SQL-authorization fallback.
    """
    def __init__(self, *, projection_path, pins: ProcessingPins, current_parent_seal,
                 live_authority, clock=lambda: datetime.now(timezone.utc)):
        if (type(pins) is not ProcessingPins or not callable(current_parent_seal)
                or not callable(getattr(live_authority, 'hold', None))):
            raise PermissionError('independent pins, parent observer and live processing authority required')
        self.projection_path, self.pins = projection_path, pins
        self.current_parent_seal, self.live_authority, self.clock = current_parent_seal, live_authority, clock

    def _local_projection(self):
        p = _typed(self.projection_path, self.pins.projection_sha256, ProcessingProjection)
        d = p.descriptor
        now = self.clock()
        if (p.descriptor_sha256 != self.pins.descriptor_sha256
                or d.runtime_hash != self.pins.runtime_hash or d.worker_uri != self.pins.worker_uri
                or d.source_registry_hash != self.pins.source_registry_hash
                or d.parent_registry_sha256 != self.pins.parent_registry_sha256
                or d.envelope_sha256 != self.pins.envelope_sha256
                or d.ledger_registry_hash != self.pins.ledger_registry_hash
                or d.key_coverage_hash != self.pins.key_coverage_hash
                or d.expires_at <= now):
            raise PermissionError('current parent/metadata processing admission denied')
        return p

    def projection(self):
        p = self._local_projection()
        if self.current_parent_seal() != self.pins.parent_registry_sha256:
            raise PermissionError('current parent registry revoked')
        return p

    def resolve(self, identity, runtime_hash, admission_hash, *, expires_at):
        p = self.projection()
        if runtime_hash != self.pins.runtime_hash or admission_hash != self.pins.projection_sha256:
            raise PermissionError('opaque processing envelope pins mismatch')
        identity = UUID(identity)
        matches = [d for d in p.descriptor.dispatches if d.dispatch_id == identity]
        now = self.clock().timestamp()
        if (len(matches) != 1 or type(expires_at) is not int
                or not now < expires_at <= min(p.descriptor.expires_at.timestamp(), now + 120)):
            raise PermissionError('exact current processing dispatch and bounded lease required')
        return ProcessingLease(p, identity, expires_at)

    @contextmanager
    def hold(self, lease):
        if type(lease) is not ProcessingLease:
            raise PermissionError('typed processing lease required')
        def recheck():
            current = self.resolve(str(lease.dispatch_id), self.pins.runtime_hash,
                                   self.pins.projection_sha256, expires_at=lease.lease_expires_at)
            if current != lease:
                raise PermissionError('processing lease changed')
        recheck()
        with self.live_authority.hold(lease.descriptor, lease.dispatch) as proof:
            d = lease.descriptor
            now = self.clock()
            # Five seconds matches the existing bounded response lease. The SQL
            # adapter must bound expires_at by its actual current grant/admission
            # minima; these comparisons cannot manufacture that SQL authority.
            if (type(proof) is not ProcessingAuthorityProof
                    or proof.workspace_id != d.workspace_id or proof.actor_id != d.actor_id
                    or proof.source_ref != lease.dispatch.source_ref
                    or proof.runtime_hash != d.runtime_hash or proof.source_registry_hash != d.source_registry_hash
                    or proof.descriptor_sha256 != lease.projection.descriptor_sha256
                    or proof.parent_registry_sha256 != d.parent_registry_sha256
                    or proof.envelope_sha256 != d.envelope_sha256
                    or proof.profile != 'gateway-metadata' or proof.purpose != d.purpose
                    or proof.checked_at > now or (now - proof.checked_at).total_seconds() > 5
                    or not now < proof.expires_at <= d.expires_at):
                raise PermissionError('fresh exact trusted SQL processing proof required')
            # Do not invoke a parent observer (potentially a network operation)
            # while the trusted authority holds its SQL locks.
            if (self._local_projection() != lease.projection
                    or self.clock().timestamp() >= lease.lease_expires_at):
                raise PermissionError('local processing lease revoked')
            yield
        # Cross-domain parent state is rechecked after SQL locks are released;
        # a refusal retains opaque queue evidence and is never acknowledged.
        recheck()


class ProcessingCustody(FileCustody):
    """Reuse the existing durable nonce/spool implementation, separate resolver."""
    def __init__(self, *, metadata: ProcessingMetadataJobs, spool):
        if type(metadata) is not ProcessingMetadataJobs:
            raise PermissionError('explicit metadata-only processing profile required')
        self.metadata = metadata
        super().__init__(registry=metadata.projection_path, spool=spool,
                         trusted_registry_hash=metadata.pins.projection_sha256,
                         runtime_hash=metadata.pins.runtime_hash, worker_uri=metadata.pins.worker_uri,
                         job_authority=metadata, clock=lambda: metadata.clock().timestamp())

    def resolve(self, job, worker_uri, *, result=False):
        if result or worker_uri != self.worker_uri:
            raise PermissionError('processing result or foreign worker denied')
        return self.metadata.resolve(job.job_id, job.runtime_hash, job.admission_hash,
                                     expires_at=job.expires_at)

    @contextmanager
    def result(self, *_args):
        raise PermissionError('processing result delivery is not installed')
        yield


def processing_gateway(address, *, tls, signing_key, custody: ProcessingCustody):
    """Explicit selection reuses exact mTLS peer/SAN and HMAC code unchanged."""
    if type(custody) is not ProcessingCustody:
        raise PermissionError('explicit processing custody required')
    return OpaqueGateway(address, tls=tls, signing_key=signing_key, worker_uri=custody.worker_uri,
                         admit=custody.admit, result=None, clock=custody.clock)
