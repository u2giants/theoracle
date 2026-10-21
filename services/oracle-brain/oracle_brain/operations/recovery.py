"""Nonauthorizing recovery reconciliation; no dump, restore, send or serving.

Snapshots describe supplied evidence. They do not authenticate accepted events,
current permissions, receipt custody or an actual backup. Configured adapters
remain responsible for those facts. Hosted/durable integration stays separate.
"""
from __future__ import annotations

from typing import Callable, Literal
from uuid import UUID

from pydantic import Field

from ..operating_model.contracts import StrictRecord, digest
from ..sources.withdrawal import DERIVED_STORES, DerivedStore, Tombstone, WithdrawalRegistry

HEX = r'^[0-9a-f]{64}$'
MAX_EVENTS = 4096


class AcceptedEvent(StrictRecord):
    workspace_id: UUID
    event_id: UUID
    source_id: UUID
    sequence: int = Field(ge=1)
    revision: int = Field(ge=1)
    operation: Literal['project', 'withdraw']
    payload_digest: str = Field(pattern=HEX)
    acknowledged: Literal[True] = True


class RecoverySnapshot(StrictRecord):
    workspace_id: UUID
    backup_id: UUID
    events: tuple[AcceptedEvent, ...] = Field(max_length=MAX_EVENTS)
    event_packet_digest: str = Field(pattern=HEX)


def packet_digest(events: tuple[AcceptedEvent, ...]) -> str:
    return digest({'events': [event.model_dump(mode='json') for event in events]})


class RetainedDeliveryReceipt(StrictRecord):
    workspace_id: UUID
    effect_id: UUID
    intent_digest: str = Field(pattern=HEX)
    receipt_id: str = Field(min_length=1, max_length=200)
    status: Literal['sent'] = 'sent'


class DeliveryObservation(StrictRecord):
    workspace_id: UUID
    effect_id: UUID
    intent_digest: str = Field(pattern=HEX)
    state: Literal['sent', 'recorded', 'pending', 'failed', 'uncertain']
    receipt: RetainedDeliveryReceipt | None = None


class EffectDisposition(StrictRecord):
    effect_id: UUID
    state: Literal['preserve', 'UNKNOWN', 'blocked']


class RecoveryResult(StrictRecord):
    workspace_id: UUID
    backup_id: UUID
    event_packet_digest: str = Field(pattern=HEX)
    applied: tuple[UUID, ...]
    duplicates: tuple[UUID, ...]
    blocked: tuple[UUID, ...]
    accounted_events: tuple[AcceptedEvent, ...]
    serving_authorized: Literal[False] = False
    live_proof_required: Literal[True] = True


def _events(events, workspace):
    if type(events) is not tuple or len(events) > MAX_EVENTS:
        raise ValueError('bounded immutable event packet required')
    by_id = {}
    revisions = {}
    last_sequence = 0
    for event in events:
        # Revalidate even frozen objects: their internals are not authority.
        if type(event) is not AcceptedEvent:
            raise TypeError('exact accepted event required')
        AcceptedEvent.model_validate(event.model_dump(mode='python'))
        if event.workspace_id != workspace or event.acknowledged is not True:
            raise PermissionError('foreign or unacknowledged event')
        prior = by_id.get(event.event_id)
        if prior is not None:
            if prior != event:
                raise ValueError('conflicting event identity')
            continue
        if event.sequence <= last_sequence:
            raise ValueError('event sequence out of order')
        # Withdrawals target a source revision, not a new content revision.
        # Only projects advance the latest projected content version.
        if event.operation == 'project':
            if event.revision <= revisions.get(event.source_id, 0):
                raise ValueError('source revision out of order')
            revisions[event.source_id] = event.revision
        last_sequence = event.sequence
        by_id[event.event_id] = event
    return by_id


def _tombstones(backup, current):
    combined = {}
    for packet in (backup, current):
        if type(packet) is not tuple or len(packet) > MAX_EVENTS:
            raise ValueError('bounded canonical tombstones required')
        for tomb in packet:
            if (type(tomb) is not Tombstone or type(tomb.source_id) is not str
                    or not 0 < len(tomb.source_id) <= 200
                    or (tomb.revision is not None and
                        (type(tomb.revision) is not int or tomb.revision < 1))):
                raise ValueError('invalid canonical tombstone')
            # This packet uses UUID source identities: alternate spellings must
            # never miss a withdrawal while comparing to an event's UUID.
            try:canonical_source = str(UUID(tomb.source_id))
            except (ValueError, AttributeError) as exc:
                raise ValueError('tombstone source must match canonical event identity') from exc
            if canonical_source != tomb.source_id:
                raise ValueError('tombstone source must match canonical event identity')
            combined[(tomb.source_id, tomb.revision)] = tomb
    whole = {source for source, revision in combined if revision is None}
    return tuple(combined[key] for key in sorted(combined, key=lambda k: (k[0], k[1] or 0))
                 if key[1] is None or key[0] not in whole)


def replay(snapshot: RecoverySnapshot, *, expected_workspace_id: UUID,
           stores: dict[str, DerivedStore], backup_tombstones: tuple[Tombstone, ...],
           current_tombstones: tuple[Tombstone, ...], prior_events: tuple[AcceptedEvent, ...],
           current_can_read: Callable[[AcceptedEvent], bool],
           project: Callable[[AcceptedEvent], None]) -> RecoveryResult:
    """Reconcile a supplied packet through configured projection-only adapters.

    No callback opens reads. Tombstones are installed in every derived store
    before a projection callback. A partial adapter failure aborts this operation;
    its effects remain quarantined and must be independently reconciled.
    """
    if type(snapshot) is not RecoverySnapshot or type(expected_workspace_id) is not UUID:
        raise TypeError('exact recovery snapshot/workspace required')
    RecoverySnapshot.model_validate(snapshot.model_dump(mode='python'))
    if snapshot.workspace_id != expected_workspace_id:
        raise PermissionError('snapshot workspace differs')
    if snapshot.event_packet_digest != packet_digest(snapshot.events):
        raise ValueError('accepted event packet changed')
    incoming = _events(snapshot.events, expected_workspace_id)
    prior = _events(prior_events, expected_workspace_id)
    # Validate every collision/order before any derived-store mutation.
    all_events = tuple(prior.values()) + tuple(event for key, event in incoming.items() if key not in prior)
    for key, event in incoming.items():
        if key in prior and prior[key] != event:
            raise ValueError('conflicting previously applied event')
    _events(all_events, expected_workspace_id)
    # Deletion precedes every projection and cannot depend on retaining read
    # permission to the withdrawn material. Prior withdrawals remain effective.
    event_tombs = tuple(Tombstone(str(event.source_id), event.revision)
        for event in all_events if event.operation == 'withdraw')
    supplied_tombs = _tombstones(backup_tombstones, current_tombstones)
    tombs = _tombstones(supplied_tombs, event_tombs)
    if set(stores) != set(DERIVED_STORES):
        raise ValueError('exact six derived stores required')
    if any(not callable(getattr(store, 'purge', None)) for store in stores.values()):
        raise TypeError('derived store purge adapter required')
    if not callable(current_can_read) or not callable(project):
        raise TypeError('configured current-read/projection adapters required')
    registry = WithdrawalRegistry(stores)
    # Existing restore requires an after-purge callback; this is a local no-op,
    # never a caller-supplied ready callback or serving transition.
    registry.restore(stores, tombs, lambda: None)
    applied, duplicates, blocked = [], [], []
    applied_ids = set(prior)
    for event in snapshot.events:
        if event.operation == 'withdraw':
            # Already purged across all stores before any projection. This
            # branch accounts it even when source reads are currently denied.
            if event.event_id in applied_ids:
                duplicates.append(event.event_id)
            else:
                applied_ids.add(event.event_id)
                applied.append(event.event_id)
            continue
        if (not registry.is_servable(str(event.source_id), event.revision)
                or current_can_read(event) is not True):
            blocked.append(event.event_id)
            continue
        if event.event_id in applied_ids:
            duplicates.append(event.event_id)
            continue
        project(event)
        if current_can_read(event) is not True:
            raise PermissionError('source revoked during projection; remains quarantined')
        applied_ids.add(event.event_id)
        applied.append(event.event_id)
    return RecoveryResult(workspace_id=snapshot.workspace_id, backup_id=snapshot.backup_id,
        event_packet_digest=snapshot.event_packet_digest, applied=tuple(applied),
        duplicates=tuple(duplicates), blocked=tuple(blocked), accounted_events=tuple(incoming.values()))


def rebuild(snapshot: RecoverySnapshot, **configured_adapters) -> RecoveryResult:
    """Same reconciliation path; actual SDK/durable restore is not implied."""
    return replay(snapshot, **configured_adapters)


def resume(observations: tuple[DeliveryObservation, ...], *, expected_workspace_id: UUID,
           current_allowed: Callable[[DeliveryObservation], bool], host_enabled: bool,
           validate_retained_receipt: Callable[[DeliveryObservation], bool]) -> tuple[EffectDisposition, ...]:
    """Classify observed effects only. No sending/retrying capability is accepted.

    A retained receipt's current validity/custody is checked by a configured
    observer. Even a valid sent receipt only permits preservation, never resend.
    Uncertain/not-sent observations stay UNKNOWN without durable integration.
    """
    if type(observations) is not tuple or len(observations) > MAX_EVENTS or type(host_enabled) is not bool:
        raise ValueError('bounded observations and exact host state required')
    if not callable(current_allowed) or not callable(validate_retained_receipt):
        raise TypeError('configured current delivery observers required')
    seen = set()
    for observation in observations:
        if type(observation) is not DeliveryObservation:
            raise TypeError('exact observed delivery required')
        DeliveryObservation.model_validate(observation.model_dump(mode='python'))
        if observation.workspace_id != expected_workspace_id or observation.effect_id in seen:
            raise PermissionError('foreign or duplicate delivery observation')
        seen.add(observation.effect_id)
        receipt = observation.receipt
        if receipt is not None and (receipt.workspace_id != observation.workspace_id
                or receipt.effect_id != observation.effect_id or receipt.intent_digest != observation.intent_digest):
            raise ValueError('retained delivery receipt identity differs')
    result = []
    for observation in observations:
        state = 'UNKNOWN'
        if not host_enabled or current_allowed(observation) is not True:
            state = 'blocked'
        elif (observation.state == 'sent' and observation.receipt is not None
              and validate_retained_receipt(observation) is True):
            state = 'preserve'
        result.append(EffectDisposition(effect_id=observation.effect_id, state=state))
    return tuple(result)
