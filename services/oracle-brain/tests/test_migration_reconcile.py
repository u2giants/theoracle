"""Pure identity-complete mapping proposals. No private data, stores or network."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from oracle_brain.migration.inventory import (
    LegacyInventory, LegacyPermission, LegacyRelationship, LegacySourceRecord,
    TranslationLineage,
)
from oracle_brain.migration.legacy_mapping import (
    LegacyMappingEntry, MappingManifest, MappingTarget, build_manifest,
)
from oracle_brain.migration.reconcile import (
    ShadowManifest, ShadowMigrationCounts, check_fidelity, permission_digest,
    reconcile_counts, reconcile_manifest,
)


def record(legacy_id='original', **updates):
    fields = dict(legacy_id=legacy_id, kind='document', content_sha256='a' * 64,
                  permissions=(LegacyPermission(principal_id='reader', kind='read'),),
                  review_state='confirmed', relationships=(), translation_lineage=(),
                  is_ai_summary=False, has_original=True)
    fields.update(updates)
    return LegacySourceRecord(**fields)


def inventory(*records):
    return LegacyInventory(inventory_id=uuid4(), captured_at=datetime.now(timezone.utc),
                           records=tuple(records))


def manifest_for(inv, mapping, **updates):
    buckets = {'accepted': [], 'quarantined': [], 'intentionally_excluded': [], 'failed': []}
    for entry in mapping.entries:
        bucket = ('accepted' if entry.decision == 'accepted_original' else
                  'quarantined' if entry.decision == 'quarantined' else 'intentionally_excluded')
        buckets[bucket].append(entry.legacy_id)
    fields = dict(manifest_id='shadow-invented', inventory_digest=inv.content_digest(),
                  mapping_digest=mapping.content_digest(),
                  counts=ShadowMigrationCounts(**{key: len(value) for key, value in buckets.items()}),
                  **{f'{key}_legacy_ids': tuple(value) for key, value in buckets.items()})
    fields.update(updates)
    return ShadowManifest(**fields)


def test_exact_inventory_mapping_and_manifest_population_is_complete():
    inv = inventory(record(), record('summary', kind='summary', is_ai_summary=True),
                    record('unconfirmed', review_state='pending'), record('missing', has_original=False),
                    record('quarantine'))
    mapping = build_manifest(inv, mapping_id=uuid4(), quarantine={'quarantine': 'ambiguous identity'})
    report = reconcile_manifest(inv, mapping, manifest_for(inv, mapping))
    assert report.complete is True and report.inventory_size == 5 and report.manifest_total == 5
    assert mapping.entries[0].target.attribution_legacy_id == 'original'
    assert mapping.entries[1].decision == 'excluded_ai_summary'


def test_ghost_accepted_id_cannot_replace_an_actual_original_at_equal_count():
    inv = inventory(record())
    mapping = build_manifest(inv, mapping_id=uuid4())
    with pytest.raises(ValueError, match='accepted ids do not match'):
        reconcile_manifest(inv, mapping, manifest_for(inv, mapping, accepted_legacy_ids=('ghost',)))


def test_same_count_swapped_accepted_and_excluded_ids_fail():
    inv = inventory(record(), record('summary', kind='summary', is_ai_summary=True))
    mapping = build_manifest(inv, mapping_id=uuid4())
    tampered = manifest_for(inv, mapping, accepted_legacy_ids=('summary',),
                            intentionally_excluded_legacy_ids=('original',))
    with pytest.raises(ValueError, match='ids do not match mapping decisions'):
        reconcile_manifest(inv, mapping, tampered)


@pytest.mark.parametrize('mode', ['omitted', 'extra', 'same-count-foreign'])
def test_mapping_entries_must_cover_exact_inventory(mode):
    inv = inventory(record())
    entries = build_manifest(inv, mapping_id=uuid4()).entries
    foreign = build_manifest(inventory(record('ghost')), mapping_id=uuid4()).entries
    chosen = {'omitted': (), 'extra': entries + foreign, 'same-count-foreign': foreign}[mode]
    mapping = MappingManifest(mapping_id=uuid4(), inventory_digest=inv.content_digest(), entries=chosen)
    with pytest.raises(ValueError, match='mapping ids must exactly cover inventory'):
        reconcile_manifest(inv, mapping, manifest_for(inv, mapping))


def test_mapping_cannot_belong_to_a_foreign_inventory_even_with_identical_ids():
    inv = inventory(record())
    foreign = inventory(record(content_sha256='b' * 64))
    mapping = build_manifest(foreign, mapping_id=uuid4())
    with pytest.raises(ValueError, match='mapping is not bound to this inventory'):
        reconcile_manifest(inv, mapping, manifest_for(inv, mapping))


@pytest.mark.parametrize('changed', ['inventory_digest', 'mapping_digest'])
def test_shadow_digest_cannot_be_substituted(changed):
    inv = inventory(record())
    mapping = build_manifest(inv, mapping_id=uuid4())
    with pytest.raises(ValueError, match='not bound to this'):
        reconcile_manifest(inv, mapping, manifest_for(inv, mapping, **{changed: 'f' * 64}))


@pytest.mark.parametrize('updates', [dict(kind='summary', is_ai_summary=True),
    dict(review_state='unreviewed'), dict(review_state='withdrawn'), dict(has_original=False)])
def test_manual_accepted_entry_cannot_bypass_original_eligibility(updates):
    inv = inventory(record(**updates))
    entry = LegacyMappingEntry(legacy_id='original', decision='accepted_original', reason='fabricated',
        target=MappingTarget(target_kind='source', attribution_legacy_id='original'))
    mapping = MappingManifest(mapping_id=uuid4(), inventory_digest=inv.content_digest(), entries=(entry,))
    with pytest.raises(ValueError, match='incompatible with inventoried record'):
        reconcile_manifest(inv, mapping, manifest_for(inv, mapping))


def test_incorrect_attribution_is_rejected_before_reconciliation():
    with pytest.raises(ValueError, match='original attribution'):
        LegacyMappingEntry(legacy_id='original', decision='accepted_original', reason='invented',
            target=MappingTarget(target_kind='source', attribution_legacy_id='other'))


def test_a_document_cannot_be_reclassified_as_a_claim_by_a_manual_mapping():
    inv = inventory(record())
    entry = LegacyMappingEntry(legacy_id='original', decision='accepted_original', reason='invented',
        target=MappingTarget(target_kind='claim', attribution_legacy_id='original'))
    mapping = MappingManifest(mapping_id=uuid4(), inventory_digest=inv.content_digest(), entries=(entry,))
    with pytest.raises(ValueError, match='target kind is incompatible'):
        reconcile_manifest(inv, mapping, manifest_for(inv, mapping))


def test_quarantined_mapping_retains_the_original_attribution():
    with pytest.raises(ValueError, match='original attribution'):
        LegacyMappingEntry(legacy_id='original', decision='quarantined', reason='ambiguous',
            target=MappingTarget(target_kind='quarantine', attribution_legacy_id='other'))


def test_fidelity_requires_exact_original_identity_permissions_and_attribution():
    before = record()
    assert check_fidelity(legacy_id='original', before=before, after_attribution='original',
                          after_permission_digest=permission_digest(before)).legacy_id == 'original'
    with pytest.raises(ValueError, match='identity does not match'):
        check_fidelity(legacy_id='other', before=before, after_attribution='other',
                       after_permission_digest=permission_digest(before))
    with pytest.raises(ValueError, match='permission fidelity degraded'):
        check_fidelity(legacy_id='original', before=before, after_attribution='original',
                       after_permission_digest='b' * 64)
    with pytest.raises(ValueError, match='attribution fidelity degraded'):
        check_fidelity(legacy_id='original', before=before, after_attribution='other',
                       after_permission_digest=permission_digest(before))


@pytest.mark.parametrize('kind', ['permission', 'relationship', 'translation'])
def test_duplicate_inventory_relationship_or_permission_is_refused(kind):
    item = {'permission': LegacyPermission(principal_id='reader', kind='read'),
            'relationship': LegacyRelationship(relation='cites', target_legacy_id='source'),
            'translation': TranslationLineage(source_legacy_id='source', source_language='en', target_language='zh')}[kind]
    field = {'permission': 'permissions', 'relationship': 'relationships',
             'translation': 'translation_lineage'}[kind]
    with pytest.raises(ValueError, match=f'duplicate {field}'):
        record(**{field: (item, item)})


@pytest.mark.parametrize('constructor', [
    lambda: record('   '),
    lambda: LegacyPermission(principal_id='\t', kind='read'),
    lambda: LegacyRelationship(relation='cites', target_legacy_id=' '),
    lambda: TranslationLineage(source_legacy_id=' ', source_language='en', target_language='zh'),
    lambda: MappingTarget(target_kind='source', attribution_legacy_id=' '),
    lambda: MappingTarget(target_kind='source', attribution_legacy_id='ok', redirect_legacy_id=' '),
    lambda: LegacyMappingEntry(legacy_id=' ', decision='quarantined', reason='reason'),
])
def test_whitespace_only_identifiers_are_refused(constructor):
    with pytest.raises(ValueError):
        constructor()


@pytest.mark.parametrize('bad', [True, 1.0, '1', -1])
def test_count_completeness_requires_a_strict_nonnegative_inventory_size(bad):
    with pytest.raises(ValueError):
        reconcile_counts(bad, ShadowMigrationCounts(accepted=1, quarantined=0, intentionally_excluded=0, failed=0))


def test_strict_immutable_contracts_reject_coercion_and_unknown_authority():
    with pytest.raises(ValueError):
        record(has_original='yes')
    with pytest.raises(ValueError):
        record(write_authorized=True)
    with pytest.raises(ValueError):
        ShadowMigrationCounts(accepted=True, quarantined=0, intentionally_excluded=0, failed=0)
