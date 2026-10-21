"""Scoped sealed replay proposals; no source feed, target store or actual replay."""
from uuid import UUID, uuid4

import pytest

from oracle_brain.migration.backfill import (
    BackfillBatch, DeltaAdapter, ReplayState, SealedChange, replay_batch,
)
from oracle_brain.migration.inventory import LegacyChange, LegacyPermission, LegacySourceRecord

SCOPE = dict(workspace_id=UUID('11111111-1111-4111-8111-111111111111'),
             inventory_id=UUID('22222222-2222-4222-8222-222222222222'),
             inventory_digest='a' * 64, feed_id='invented-feed')


def record(legacy_id='original', **updates):
    data = dict(legacy_id=legacy_id, kind='document', content_sha256='b' * 64,
        permissions=(LegacyPermission(principal_id='reader', kind='read'),),
        review_state='confirmed', relationships=(), translation_lineage=(), has_original=True)
    data.update(updates)
    return LegacySourceRecord(**data)


def change(mark=1, key='event-1', kind='insert', legacy_id='original', **updates):
    data = dict(**SCOPE, watermark=mark, change_id=key, kind=kind, legacy_id=legacy_id,
                record=None if kind == 'delete' else record(legacy_id))
    data.update(updates)
    return LegacyChange(**data)


def state(**updates):
    return ReplayState(**{**SCOPE, **updates})


def test_exact_repeat_is_noop_and_preserves_one_proposed_application():
    event = change()
    first = replay_batch(state(), (event, event))
    assert len(first.applications) == 1
    again = replay_batch(first.cursor_after, (event,))
    assert again.applications == () and again.cursor_after == first.cursor_after
    assert again.outcomes[0].action == 'duplicate'


@pytest.mark.parametrize('kind', ['delete', 'permission', 'approval'])
def test_same_id_with_changed_operation_refuses_even_after_prior_application(kind):
    old = change()
    cursor = replay_batch(state(), (old,)).cursor_after
    with pytest.raises(ValueError, match='identity collision'):
        replay_batch(cursor, (change(kind=kind),))


@pytest.mark.parametrize('updates', [dict(watermark=9), dict(legacy_id='other', record=record('other')),
    dict(record=record(content_sha256='c' * 64)),
    dict(record=record(permissions=(LegacyPermission(principal_id='other', kind='read'),))),
    dict(record=record(review_state='withdrawn'))])
def test_same_id_cannot_change_subject_payload_permissions_approval_or_watermark(updates):
    cursor = replay_batch(state(), (change(),)).cursor_after
    with pytest.raises(ValueError, match='identity collision'):
        replay_batch(cursor, (change(**updates),))


def test_same_id_collision_inside_one_batch_refuses_before_any_transition():
    before = state()
    with pytest.raises(ValueError, match='identity collision'):
        replay_batch(before, (change(), change(kind='delete')))
    assert before.read_watermark == -1 and before.applied_events == ()


@pytest.mark.parametrize('scope_update', [dict(workspace_id=uuid4()), dict(inventory_id=uuid4()),
    dict(inventory_digest='f' * 64), dict(feed_id='other-feed')])
def test_foreign_event_scope_or_cursor_is_refused(scope_update):
    event = change(**scope_update)
    with pytest.raises(ValueError, match='foreign replay event scope'):
        replay_batch(state(), (event,))
    with pytest.raises(ValueError, match='foreign replay event scope'):
        replay_batch(state(**scope_update), (change(),))


def test_numeric_watermark_gaps_are_allowed_but_unseen_order_must_be_strict():
    events = (change(3, 'a'), change(7, 'b', 'update'), change(20, 'c', 'delete'))
    batch = replay_batch(state(), events)
    assert batch.cursor_after.read_watermark == batch.cursor_after.applied_watermark == 20
    assert [item.change.watermark for item in batch.applications] == [3, 7, 20]
    for invalid in ((events[1], events[0]), (events[0], change(3, 'other'))):
        with pytest.raises(ValueError, match='strictly ascending'):
            replay_batch(state(), invalid)


def test_duplicates_cannot_hide_out_of_order_unseen_events():
    before = replay_batch(state(), (change(),)).cursor_after
    with pytest.raises(ValueError, match='strictly ascending'):
        replay_batch(before, (change(9, 'later'), change(), change(3, 'middle')))
    assert before.applied_watermark == 1


def test_unseen_at_or_below_read_watermark_is_refused_not_silently_skipped():
    before = replay_batch(state(), (change(8),)).cursor_after
    with pytest.raises(ValueError, match='strictly ascending'):
        replay_batch(before, (change(5, 'late'),))


@pytest.mark.parametrize('bad', [True, False, 0, -1, 1001, 1.0, '1'])
def test_batch_limit_must_be_a_bounded_positive_actual_integer(bad):
    with pytest.raises(ValueError, match='positive bounded integer'):
        replay_batch(state(), (change(),), batch_limit=bad)


def test_batch_limit_bounds_every_supplied_delivery_including_duplicates():
    with pytest.raises(ValueError, match='exceeds its limit'):
        replay_batch(state(), (change(), change()), batch_limit=1)


@pytest.mark.parametrize('bad', [True, False, float('nan'), float('inf'), -float('inf'), -1, '1', 10 ** 1000])
def test_pause_duration_refuses_nonfinite_boolean_negative_and_untyped_values(bad):
    with pytest.raises(ValueError, match='finite and nonnegative'):
        DeltaAdapter(mechanism='write_pause_snapshot', pause_seconds=bad)


def test_pause_duration_requires_measured_value_only_for_pause_mechanism():
    assert DeltaAdapter(mechanism='write_pause_snapshot', pause_seconds=0).pause_seconds == 0.0
    assert DeltaAdapter(mechanism='write_pause_snapshot', pause_seconds=1.25).pause_seconds == 1.25
    with pytest.raises(ValueError, match='requires measured'):
        DeltaAdapter(mechanism='write_pause_snapshot')
    with pytest.raises(ValueError, match='no write pause'):
        DeltaAdapter(mechanism='change_feed', pause_seconds=1.0)


@pytest.mark.parametrize('updates', [dict(feed_id='   '), dict(inventory_digest='bad'),
    dict(workspace_id=str(SCOPE['workspace_id'])), dict(read_watermark=True)])
def test_scope_and_cursor_types_are_strict(updates):
    with pytest.raises(ValueError):
        state(**updates)


def test_exact_event_seal_cannot_be_substituted():
    with pytest.raises(ValueError, match='payload digest mismatch'):
        SealedChange(change=change(), payload_digest='f' * 64)
