"""Exact retained pending accounting and restart-safe pure replay transitions."""
from uuid import UUID, uuid4

import pytest

from oracle_brain.migration.backfill import BackfillBatch, ReplayState, replay_batch
from oracle_brain.migration.inventory import LegacyChange, LegacySourceRecord

SCOPE = dict(workspace_id=UUID('11111111-1111-4111-8111-111111111111'),
             inventory_id=UUID('22222222-2222-4222-8222-222222222222'),
             inventory_digest='a' * 64, feed_id='invented-feed')


def change(mark, key, kind='update'):
    row = LegacySourceRecord(legacy_id='source', kind='document', content_sha256='b' * 64,
        permissions=(), review_state='confirmed', relationships=(), translation_lineage=(), has_original=True)
    return LegacyChange(**SCOPE, watermark=mark, change_id=key, kind=kind, legacy_id='source',
                         record=None if kind == 'delete' else row)


def state():
    return ReplayState(**SCOPE)


def ids(events):
    return tuple(event.change.change_id for event in events)


@pytest.mark.parametrize('label', ['failed', 'quarantined'])
def test_failed_middle_retains_every_later_event_and_separates_read_safe_cursor(label):
    events = (change(1, 'a'), change(4, 'b'), change(8, 'c', 'delete'))
    batch = replay_batch(state(), events, **{f'{label}_change_ids': ('b',)})
    assert batch.cursor_after.read_watermark == 8 and batch.cursor_after.applied_watermark == 1
    assert ids(batch.applications) == ('a',)
    assert ids(tuple(item.event for item in batch.pending)) == ('b', 'c')
    assert tuple(item.reason for item in batch.pending) == (label, 'blocked')
    assert batch.cursor_after.failure_history[0].reason == label
    assert ids(batch.cursor_after.applied_events) + ids(tuple(item.event for item in batch.pending)) == ('a', 'b', 'c')


def test_duplicate_delivery_does_not_clear_a_failure_or_skip_to_later_event():
    a, b, c = change(1, 'a'), change(4, 'b'), change(8, 'c')
    before = replay_batch(state(), (a, b, c), failed_change_ids=('b',)).cursor_after
    duplicate = replay_batch(before, (b,))
    assert duplicate.cursor_after == before and duplicate.applications == ()
    extended = replay_batch(before, (change(10, 'd'),))
    assert extended.cursor_after.read_watermark == 10
    assert extended.cursor_after.applied_watermark == 1 and extended.applications == ()
    assert ids(tuple(item.event for item in extended.pending)) == ('b', 'c', 'd')


def test_explicit_exact_pending_resolution_proposes_every_retained_unblocked_event_once():
    a, b, c = change(1, 'a'), change(4, 'b'), change(8, 'c')
    before = replay_batch(state(), (a, b, c), failed_change_ids=('b',)).cursor_after
    result = replay_batch(before, (b,), resolve_pending_change_ids=('b',))
    assert ids(result.applications) == ('b', 'c') and result.pending == ()
    assert result.cursor_after.applied_watermark == result.cursor_after.read_watermark == 8
    assert result.cursor_after.failure_history == before.failure_history
    assert result.cursor_after.resolved_change_ids == ('b',)
    repeat = replay_batch(result.cursor_after, (a, b, c))
    assert repeat.applications == () and repeat.cursor_after == result.cursor_after


def test_each_independent_failure_or_quarantine_needs_its_own_resolution():
    a, b, c, d = change(1, 'a'), change(4, 'b'), change(8, 'c'), change(12, 'd')
    before = replay_batch(state(), (a, b, c, d), failed_change_ids=('b',),
                          quarantined_change_ids=('d',)).cursor_after
    first = replay_batch(before, (b,), resolve_pending_change_ids=('b',))
    assert ids(first.applications) == ('b', 'c')
    assert first.cursor_after.applied_watermark == 8
    assert ids(tuple(item.event for item in first.pending)) == ('d',)
    second = replay_batch(first.cursor_after, (d,), resolve_pending_change_ids=('d',))
    assert ids(second.applications) == ('d',) and second.pending == ()
    assert [(item.event.change.change_id, item.reason) for item in second.cursor_after.failure_history] == [
        ('b', 'failed'), ('d', 'quarantined')]


def test_resolving_later_failure_does_not_advance_around_earlier_unresolved_failure():
    a, b, c = change(1, 'a'), change(4, 'b'), change(8, 'c')
    before = replay_batch(state(), (a, b, c), failed_change_ids=('a', 'c')).cursor_after
    later = replay_batch(before, (c,), resolve_pending_change_ids=('c',))
    assert later.applications == () and later.cursor_after.applied_watermark == -1
    assert later.cursor_after.resolved_change_ids == ('c',)
    complete = replay_batch(later.cursor_after, (a,), resolve_pending_change_ids=('a',))
    assert ids(complete.applications) == ('a', 'b', 'c') and complete.pending == ()


def test_resolution_requires_same_pending_identity_payload_and_explicit_input():
    b = change(4, 'b')
    before = replay_batch(state(), (b,), failed_change_ids=('b',)).cursor_after
    with pytest.raises(ValueError, match='must appear with exact payload'):
        replay_batch(before, (), resolve_pending_change_ids=('b',))
    with pytest.raises(ValueError, match='identity collision'):
        replay_batch(before, (change(4, 'b', 'delete'),), resolve_pending_change_ids=('b',))
    with pytest.raises(ValueError, match='independently failed or quarantined'):
        replay_batch(state(), (b,), resolve_pending_change_ids=('b',))
    with pytest.raises(ValueError, match='disjoint'):
        replay_batch(before, (b,), failed_change_ids=('b',), resolve_pending_change_ids=('b',))


def test_restart_serialization_preserves_sealed_pending_and_failure_history():
    events = (change(1, 'a'), change(4, 'b'), change(8, 'c'))
    before = replay_batch(state(), events, quarantined_change_ids=('b',)).cursor_after
    restored = ReplayState.model_validate_json(before.model_dump_json())
    assert restored == before
    resumed = replay_batch(restored, (events[1],), resolve_pending_change_ids=('b',))
    assert ids(resumed.applications) == ('b', 'c') and resumed.pending == ()
    assert BackfillBatch.model_validate_json(resumed.model_dump_json()) == resumed


@pytest.mark.parametrize('field', ['read_watermark', 'applied_watermark'])
def test_direct_cursor_false_advancement_is_refused(field):
    cursor = replay_batch(state(), (change(1, 'a'),)).cursor_after
    data = cursor.model_dump()
    data[field] = 99
    with pytest.raises(ValueError, match='watermark does not match'):
        ReplayState(**data)
    copied = cursor.model_copy(update={field: 99})
    with pytest.raises(ValueError, match='watermark does not match'):
        replay_batch(copied, ())


@pytest.mark.parametrize('tamper', ['applications', 'pending', 'scope', 'cursor', 'outcomes'])
def test_caller_constructed_batch_cannot_fabricate_advancement_or_drop_accounting(tamper):
    events = (change(1, 'a'), change(4, 'b'), change(8, 'c'))
    batch = replay_batch(state(), events, failed_change_ids=('b',))
    fields = batch.model_dump()
    if tamper == 'applications':
        fields['applications'] = ()
    elif tamper == 'pending':
        fields['pending'] = ()
    elif tamper == 'scope':
        fields['cursor_after']['workspace_id'] = uuid4()
    elif tamper == 'cursor':
        fields['cursor_after']['pending_events'] = ()
        fields['cursor_after']['read_watermark'] = 1
    else:
        fields['outcomes'] = ()
    with pytest.raises(ValueError):
        BackfillBatch(**fields)


def test_state_rejects_unsealed_or_foreign_or_unresolved_applied_history():
    b = change(4, 'b')
    pending = replay_batch(state(), (b,), failed_change_ids=('b',)).cursor_after
    data = pending.model_dump()
    data['pending_events'][0]['event']['payload_digest'] = 'f' * 64
    with pytest.raises(ValueError, match='payload digest mismatch'):
        ReplayState(**data)
    data = pending.model_dump()
    data['failure_history'] = ()
    with pytest.raises(ValueError, match='unresolved history'):
        ReplayState(**data)
    data = pending.model_dump()
    data['applied_events'] = (data['pending_events'][0]['event'],)
    data['pending_events'] = ()
    data['applied_watermark'] = 4
    with pytest.raises(ValueError, match='unresolved failure'):
        ReplayState(**data)


def test_failure_markers_cannot_be_invented_duplicated_or_retroactive():
    a = change(1, 'a')
    with pytest.raises(ValueError, match='must appear'):
        replay_batch(state(), (a,), failed_change_ids=('ghost',))
    with pytest.raises(ValueError, match='unique and nonblank'):
        replay_batch(state(), (a,), failed_change_ids=('a', 'a'))
    before = replay_batch(state(), (a,)).cursor_after
    with pytest.raises(ValueError, match='cannot be relabeled'):
        replay_batch(before, (a,), quarantined_change_ids=('a',))
