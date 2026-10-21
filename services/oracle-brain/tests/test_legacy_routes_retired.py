"""Canonical retirement gate and independently admitted descriptive extension."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.retirement import verify_retirement
from oracle_brain.operating_model.release_manifest import ReleaseManifest
from oracle_brain.operating_model.source_receipts import SourceRef
from oracle_brain.operating_model.retirement_checklist import (
    CitationBinding, CitationInventoryPacket, FreshRestorePacket, RestoredCitation,
    RetentionClearancePacket, verify_retirement_checklist,
)

NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)


def inputs():
    """Pure canonical release fixture; no SDK imports, services or operations."""
    workspace = uuid4()
    source = SourceRef(workspace_id=workspace, source_id=uuid4(), revision=1,
        original_sha256='1' * 64, reading_sha256='2' * 64, parser_id='invented-parser')
    manifest = ReleaseManifest(release_id=uuid4(), workspace_id=workspace,
        artifact_id=uuid4(), artifact_version=1, artifact_content_hash='a' * 64,
        runtime_digest='b' * 64, permission_digest='c' * 64, source_refs=(source,),
        graph_generation=uuid4(), graph_name='oracle_operating_model_v1_' + workspace.hex,
        graph_record_digest='d' * 64, acceptance_state='admitted_hosted',
        independent_review_hash='e' * 64, documentary_gate_hash='f' * 64,
        restricted_hosting_hash='1' * 64, restore_proof_hash='2' * 64,
        source_inventory_hash='0' * 64, ledger_watermark=0)
    release_hash = manifest.content_hash()
    census = dict(release_hash=release_hash, files={'packages/old.py': dict(
        replaced=True, references=[], retention_required=False, capabilities=['source retrieval'])},
        new_legacy_writers=[], fallback_dispatches=[])
    equivalents = dict(release_hash=release_hash, capabilities={'source retrieval': dict(
        passed=True, evidence_hash='3' * 64, release_hash=release_hash)})
    return manifest, census, equivalents


def packet_inputs():
    m, census, equivalents = inputs()
    citation = CitationBinding(legacy_citation_id='legacy-1', target_id='current-1',
        source_ref=m.source_refs[0], permission_digest='4' * 64, tombstoned=False)
    inventory = CitationInventoryPacket(release_hash=m.content_hash(),
        source_inventory_hash=m.source_inventory_hash, permission_digest=m.permission_digest,
        citations=(citation,))
    restore = FreshRestorePacket(release_hash=m.content_hash(),
        source_inventory_hash=m.source_inventory_hash, permission_digest=m.permission_digest,
        citation_inventory_hash=digest(inventory.model_dump(mode='json')),
        fresh_instance_id='invented-new-instance', backup_hash='5' * 64,
        completed_at=NOW - timedelta(minutes=5), observed_at=NOW, expires_at=NOW + timedelta(minutes=5),
        citations=(RestoredCitation(**citation.model_dump(), resolution_state='available'),),
        available_target_ids=('current-1',))
    retention = RetentionClearancePacket(release_hash=m.content_hash(),
        census_hash=digest(census), equivalence_hash=digest(equivalents),
        citation_inventory_hash=digest(inventory.model_dump(mode='json')),
        restore_packet_hash=digest(restore.model_dump(mode='json')),
        rollback_rehearsal_hash='6' * 64, required_window_seconds=2 * 86400,
        stable_primary_at=NOW - timedelta(days=3), observed_at=NOW)
    return dict(manifest=m, census=census, proposed_paths=('packages/old.py',),
        preserved_capabilities=equivalents, accepted_release_hashes=frozenset({m.content_hash()}),
        admitted_census_hashes=frozenset({digest(census)}),
        admitted_equivalence_hashes=frozenset({digest(equivalents)}),
        citation_inventory=inventory, restore_packet=restore, retention_packet=retention,
        admitted_citation_inventory_hashes=frozenset({digest(inventory.model_dump(mode='json'))}),
        admitted_restore_hashes=frozenset({digest(restore.model_dump(mode='json'))}),
        admitted_retention_hashes=frozenset({digest(retention.model_dump(mode='json'))}), observed_at=NOW)


def reseal(args, *, inventory=None, restore=None, retention=None):
    """Invented independent admission fixture; never a runtime issuer."""
    result = dict(args)
    if inventory is not None:
        result['citation_inventory'] = inventory
        result['admitted_citation_inventory_hashes'] = frozenset({digest(inventory.model_dump(mode='json'))})
    if restore is not None:
        result['restore_packet'] = restore
        result['admitted_restore_hashes'] = frozenset({digest(restore.model_dump(mode='json'))})
    if retention is not None:
        result['retention_packet'] = retention
        result['admitted_retention_hashes'] = frozenset({digest(retention.model_dump(mode='json'))})
    return result


def test_extension_calls_canonical_gate_and_preserves_all_no_action_flags(monkeypatch):
    import oracle_brain.operating_model.retirement_checklist as extension
    called = []
    canonical = extension.verify_retirement
    def check(*args, **kwargs):
        called.append(True)
        return canonical(*args, **kwargs)
    monkeypatch.setattr(extension, 'verify_retirement', check)
    report = extension.verify_retirement_checklist(**packet_inputs())
    assert called == [True]
    assert report['deletion_authorized'] is False
    assert report['reviewed_retirement_pr_required'] is True
    assert report['live_proof_still_required'] is True
    assert report['observed_retention_seconds'] == 3 * 86400
    assert 'write_authorized' not in report


@pytest.mark.parametrize('path', ['', ' ', '.', './', './old.py', 'packages//old.py',
    'packages/old.py/', 'packages/../old.py', '/packages/old.py', 'C:/old.py',
    'packages/old\x00.py', 'packages/old\n.py', 'packages/old\x7f.py',
    'C:old.py', 'packages/old:stream', 'packages\\old.py', None, 1, True, []])
def test_canonical_gate_rejects_noncanonical_exact_retirement_targets(path):
    m, census, equivalents = inputs()
    with pytest.raises(ValueError, match='canonical repository relative'):
        verify_retirement(m, census, proposed_paths=(path,), preserved_capabilities=equivalents,
            accepted_release_hashes=frozenset({m.content_hash()}),
            admitted_census_hashes=frozenset({digest(census)}),
            admitted_equivalence_hashes=frozenset({digest(equivalents)}))


@pytest.mark.parametrize('field', ['accepted_release_hashes', 'admitted_census_hashes',
    'admitted_equivalence_hashes', 'admitted_citation_inventory_hashes',
    'admitted_restore_hashes', 'admitted_retention_hashes'])
def test_every_exact_independent_admission_remains_mandatory(field):
    args = packet_inputs()
    args[field] = frozenset()
    with pytest.raises(PermissionError):
        verify_retirement_checklist(**args)


@pytest.mark.parametrize('mutation', ['reference', 'retention', 'capability', 'fallback', 'writer'])
def test_extension_never_overrides_existing_dependency_capability_or_writer_refusal(mutation):
    args = packet_inputs()
    census = deepcopy(args['census'])
    equivalents = deepcopy(args['preserved_capabilities'])
    if mutation == 'reference':
        census['files']['packages/old.py']['references'] = ['active-caller']
    elif mutation == 'retention':
        census['files']['packages/old.py']['retention_required'] = True
    elif mutation == 'capability':
        equivalents['capabilities']['source retrieval']['passed'] = False
    elif mutation == 'fallback':
        census['fallback_dispatches'] = ['live-route']
    else:
        census['new_legacy_writers'] = ['old-writer']
    args.update(census=census, preserved_capabilities=equivalents,
        admitted_census_hashes=frozenset({digest(census)}),
        admitted_equivalence_hashes=frozenset({digest(equivalents)}))
    with pytest.raises(PermissionError):
        verify_retirement_checklist(**args)


@pytest.mark.parametrize('field', ['citation_inventory', 'restore_packet', 'retention_packet'])
def test_independently_hashed_cross_release_packets_still_refuse(field):
    args = packet_inputs()
    packet = args[field].model_copy(update={'release_hash': 'f' * 64})
    key = {'citation_inventory': 'inventory', 'restore_packet': 'restore', 'retention_packet': 'retention'}[field]
    with pytest.raises(PermissionError, match='different accepted release'):
        verify_retirement_checklist(**reseal(args, **{key: packet}))


@pytest.mark.parametrize('field', ['source_inventory_hash', 'permission_digest'])
@pytest.mark.parametrize('packet_key', ['citation_inventory', 'restore_packet'])
def test_changed_source_or_permission_snapshot_refuses_even_with_exact_packet_admission(field, packet_key):
    args = packet_inputs()
    changed = args[packet_key].model_copy(update={field: 'f' * 64})
    key = 'inventory' if packet_key == 'citation_inventory' else 'restore'
    with pytest.raises(PermissionError, match='snapshot differs'):
        verify_retirement_checklist(**reseal(args, **{key: changed}))


@pytest.mark.parametrize('field', ['census_hash', 'equivalence_hash', 'citation_inventory_hash', 'restore_packet_hash'])
def test_retention_packet_binds_exact_canonical_inputs(field):
    args = packet_inputs()
    changed = args['retention_packet'].model_copy(update={field: 'f' * 64})
    with pytest.raises(PermissionError, match='exact canonical inputs'):
        verify_retirement_checklist(**reseal(args, retention=changed))


def test_bool_or_short_elapsed_window_never_clears_retention():
    fields = packet_inputs()['retention_packet'].model_dump()
    with pytest.raises(ValueError):
        RetentionClearancePacket(**{**fields, 'required_window_seconds': True})
    with pytest.raises(ValueError, match='has not elapsed'):
        RetentionClearancePacket(**{**fields, 'required_window_seconds': 4 * 86400})
    with pytest.raises(ValueError, match='precedes stable'):
        RetentionClearancePacket(**{**fields, 'stable_primary_at': NOW + timedelta(days=1)})


def test_no_hardcoded_thirty_day_rule_substitutes_for_exact_admitted_window():
    args = packet_inputs()
    assert args['retention_packet'].required_window_seconds == 2 * 86400
    assert verify_retirement_checklist(**args)['deletion_authorized'] is False


def test_stale_restore_retention_and_clock_observation_are_refused():
    args = packet_inputs()
    with pytest.raises(PermissionError, match='stale'):
        verify_retirement_checklist(**{**args, 'observed_at': NOW + timedelta(minutes=10)})
    old = args['retention_packet'].model_copy(update={'observed_at': NOW - timedelta(hours=1)})
    with pytest.raises(PermissionError, match='current admitted observation'):
        verify_retirement_checklist(**reseal(args, retention=old))
    with pytest.raises(ValueError, match='aware datetime'):
        verify_retirement_checklist(**{**args, 'observed_at': NOW.replace(tzinfo=None)})


def test_unvalidated_model_copy_cannot_fake_elapsed_retention():
    args = packet_inputs()
    bad = args['retention_packet'].model_copy(update={'stable_primary_at': NOW})
    with pytest.raises(ValueError, match='has not elapsed'):
        verify_retirement_checklist(**reseal(args, retention=bad))
