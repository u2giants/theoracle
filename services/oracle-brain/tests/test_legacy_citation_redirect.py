"""Original-to-target citation fidelity through an exact admitted fresh restore."""
from datetime import timedelta

import pytest

from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.retirement_checklist import (
    CitationBinding, CitationInventoryPacket, FreshRestorePacket, RestoredCitation,
    verify_retirement_checklist,
)
from test_legacy_routes_retired import NOW, packet_inputs, reseal


def chain(args, *, inventory=None, restore=None):
    """Construct coherent invented independently admitted input packets only."""
    inventory = inventory or args['citation_inventory']
    restore = restore or args['restore_packet']
    citation_hash = digest(inventory.model_dump(mode='json'))
    restore = restore.model_copy(update={'citation_inventory_hash': citation_hash})
    retention = args['retention_packet'].model_copy(update={
        'citation_inventory_hash': citation_hash,
        'restore_packet_hash': digest(restore.model_dump(mode='json'))})
    return reseal(args, inventory=inventory, restore=restore, retention=retention)


def paired_inputs():
    args = packet_inputs()
    first = args['citation_inventory'].citations[0]
    second = first.model_copy(update={'legacy_citation_id': 'legacy-2', 'target_id': 'current-2'})
    inventory = args['citation_inventory'].model_copy(update={'citations': (first, second)})
    restore = args['restore_packet'].model_copy(update={
        'citations': tuple(RestoredCitation(**item.model_dump(), resolution_state='available')
                           for item in inventory.citations),
        'available_target_ids': ('current-1', 'current-2')})
    return chain(args, inventory=inventory, restore=restore)


def test_complete_original_mapping_survives_fresh_restore_without_granting_access():
    args = paired_inputs()
    proof = verify_retirement_checklist(**args)
    assert proof['fresh_restore_hash'] == digest(args['restore_packet'].model_dump(mode='json'))
    assert proof['deletion_authorized'] is False


@pytest.mark.parametrize('mutation', ['missing', 'ghost', 'swapped-targets', 'swapped-citation-ids'])
def test_missing_ghost_or_swapped_citation_mapping_cannot_pass_equal_counts(mutation):
    args = paired_inputs()
    first, second = args['restore_packet'].citations
    if mutation == 'missing':
        rows = (first,)
    elif mutation == 'ghost':
        rows = (first, second.model_copy(update={'legacy_citation_id': 'ghost'}))
    elif mutation == 'swapped-targets':
        rows = (first.model_copy(update={'target_id': second.target_id}),
                second.model_copy(update={'target_id': first.target_id}))
    else:
        rows = (first.model_copy(update={'legacy_citation_id': second.legacy_citation_id}),
                second.model_copy(update={'legacy_citation_id': first.legacy_citation_id}))
    restore = args['restore_packet'].model_copy(update={'citations': rows})
    with pytest.raises(PermissionError):
        verify_retirement_checklist(**chain(args, restore=restore))


@pytest.mark.parametrize('mutation', ['revision', 'original-hash', 'permission', 'tombstone'])
def test_restored_source_revision_original_permission_and_tombstone_are_exact(mutation):
    args = packet_inputs()
    row = args['restore_packet'].citations[0]
    if mutation == 'revision':
        row = row.model_copy(update={'source_ref': row.source_ref.model_copy(update={'revision': 2})})
    elif mutation == 'original-hash':
        row = row.model_copy(update={'source_ref': row.source_ref.model_copy(update={'original_sha256': 'f' * 64})})
    elif mutation == 'permission':
        row = row.model_copy(update={'permission_digest': 'f' * 64})
    else:
        row = row.model_copy(update={'tombstoned': True, 'resolution_state': 'withdrawn'})
    restore = args['restore_packet'].model_copy(update={'citations': (row,)})
    with pytest.raises(PermissionError, match='original target revision permission or tombstone mismatch'):
        verify_retirement_checklist(**chain(args, restore=restore))


def test_inventory_cannot_substitute_a_source_revision_outside_the_accepted_release():
    args = packet_inputs()
    binding = args['citation_inventory'].citations[0]
    wrong = binding.model_copy(update={'source_ref': binding.source_ref.model_copy(update={'revision': 2})})
    inventory = args['citation_inventory'].model_copy(update={'citations': (wrong,)})
    restore = args['restore_packet'].model_copy(update={
        'citations': (RestoredCitation(**wrong.model_dump(), resolution_state='available'),)})
    with pytest.raises(PermissionError, match='source revision is not in accepted release'):
        verify_retirement_checklist(**chain(args, inventory=inventory, restore=restore))


@pytest.mark.parametrize('available', [(), ('ghost',), ('current-1', 'ghost')])
def test_dangling_missing_and_extra_restored_targets_are_refused(available):
    args = packet_inputs()
    restore = args['restore_packet'].model_copy(update={'available_target_ids': available})
    with pytest.raises(PermissionError, match='target population is dangling'):
        verify_retirement_checklist(**chain(args, restore=restore))


def test_duplicate_citation_id_and_duplicate_available_target_are_refused():
    args = packet_inputs()
    with pytest.raises(ValueError, match='duplicate legacy citation'):
        CitationInventoryPacket(**{**args['citation_inventory'].model_dump(),
            'citations': (args['citation_inventory'].citations[0],) * 2})
    with pytest.raises(ValueError, match='duplicate restored citation'):
        FreshRestorePacket(**{**args['restore_packet'].model_dump(),
            'citations': (args['restore_packet'].citations[0],) * 2})
    with pytest.raises(ValueError, match='unique and nonblank'):
        FreshRestorePacket(**{**args['restore_packet'].model_dump(),
            'available_target_ids': ('current-1', 'current-1')})


def test_same_target_cannot_conflate_distinct_original_or_permission_identities():
    args = packet_inputs()
    original = args['citation_inventory'].citations[0]
    changed = original.model_copy(update={'legacy_citation_id': 'other', 'permission_digest': 'f' * 64})
    with pytest.raises(ValueError, match='conflates distinct'):
        CitationInventoryPacket(**{**args['citation_inventory'].model_dump(), 'citations': (original, changed)})


def test_withdrawn_citation_retains_tombstone_without_restoring_available_content():
    args = packet_inputs()
    withdrawn = args['citation_inventory'].citations[0].model_copy(update={'tombstoned': True})
    inventory = args['citation_inventory'].model_copy(update={'citations': (withdrawn,)})
    restore = args['restore_packet'].model_copy(update={
        'citations': (RestoredCitation(**withdrawn.model_dump(), resolution_state='withdrawn'),),
        'available_target_ids': ()})
    assert verify_retirement_checklist(**chain(args, inventory=inventory, restore=restore))['deletion_authorized'] is False
    with pytest.raises(ValueError, match='contradicts tombstone'):
        RestoredCitation(**withdrawn.model_dump(), resolution_state='available')


def test_expired_fresh_restore_packet_is_refused_even_with_a_current_observation_label():
    args = packet_inputs()
    restore = args['restore_packet'].model_copy(update={
        'observed_at': NOW - timedelta(minutes=10), 'completed_at': NOW - timedelta(minutes=15),
        'expires_at': NOW - timedelta(minutes=1)})
    with pytest.raises(PermissionError, match='stale'):
        verify_retirement_checklist(**chain(args, restore=restore))


def test_unvalidated_copied_bad_tombstone_packet_cannot_bypass_field_validation():
    args = packet_inputs()
    row = args['restore_packet'].citations[0].model_copy(update={'tombstoned': True})
    restore = args['restore_packet'].model_copy(update={'citations': (row,)})
    with pytest.raises(ValueError, match='contradicts tombstone'):
        verify_retirement_checklist(**chain(args, restore=restore))
