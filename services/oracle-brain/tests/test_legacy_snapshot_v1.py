"""Metadata preparation only: no database, files, grants or invented producer."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from pydantic import ValidationError
from oracle_brain.migration.inventory import LegacyInventory, LegacySourceRecord, LegacyPermission
from oracle_brain.migration.legacy_snapshot_v1 import (
    LegacySnapshotDescriptorV1, build_metadata_snapshot_v1, stable_origin_key_v1,
    observed_metadata_version_v1, recheck_metadata_snapshot_v1, require_original_access_v1,
)

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)

def setup():
    descriptor = LegacySnapshotDescriptorV1(purpose='legacy-metadata-snapshot-preparation-v1',
        origin_system='oracle_legacy', workspace_id=uuid4(), principal_id=uuid4(), source_database_identity=uuid4(),
        snapshot_program_sha256='a'*64, source_profile_sha256='b'*64, permission_producer_kind='unavailable',
        max_records=2, max_metadata_bytes=10000, valid_from=NOW-timedelta(seconds=5),
        expires_at=NOW+timedelta(seconds=20), original_horizon=NOW+timedelta(seconds=30))
    row = LegacySourceRecord(legacy_id='doc1',kind='document',content_sha256='c'*64,
        permissions=(LegacyPermission(principal_id='old-admin',kind='admin'),),review_state='confirmed',
        relationships=(),translation_lineage=(),has_original=True)
    inventory = LegacyInventory(inventory_id=uuid4(),captured_at=NOW,records=(row,))
    return descriptor, row, inventory


def test_confirmed_admin_original_metadata_still_quarantined_no_private_access():
    d,r,i=setup();s=build_metadata_snapshot_v1(d,i,declared_source_count=1,now=NOW)
    assert s.quarantine_legacy_ids==('doc1',)
    assert not any((s.actual_source_snapshot_proven,s.current_source_permission_proven,
        s.original_bytes_observed,s.target_import_authorized,s.consistent_boundary_proven,s.company_acceptance))
    with pytest.raises(PermissionError,match='producer unavailable'):require_original_access_v1(s)


@pytest.mark.parametrize('change',[{'content_sha256':'d'*64},{'review_state':'withdrawn'}, {'permissions':()}])
def test_version_changes_keep_stable_origin_and_cannot_pass_current_recheck(change):
    d,r,i=setup();changed=LegacySourceRecord.model_validate_json(r.model_copy(update=change).model_dump_json())
    assert stable_origin_key_v1(d,r)==stable_origin_key_v1(d,changed)
    assert observed_metadata_version_v1(r)!=observed_metadata_version_v1(changed)
    before=build_metadata_snapshot_v1(d,i,declared_source_count=1,now=NOW)
    current=build_metadata_snapshot_v1(d,i.model_copy(update={'records':(changed,)}),declared_source_count=1,now=NOW)
    with pytest.raises(PermissionError,match='permission changed'):recheck_metadata_snapshot_v1(before,current,now=NOW)


def test_new_installation_does_not_change_origin_identity_and_no_source_hash_identity():
    d,r,i=setup();other=d.model_copy(update={'source_profile_sha256':'f'*64,'principal_id':uuid4()})
    assert stable_origin_key_v1(d,r)==stable_origin_key_v1(other,r)
    assert stable_origin_key_v1(d,r)!=stable_origin_key_v1(d,r.model_copy(update={'legacy_id':'other'}))
    assert stable_origin_key_v1(d,r)!=stable_origin_key_v1(d.model_copy(update={'workspace_id':uuid4()}),r)


@pytest.mark.parametrize('count',[0,2,True,-1,10001])
def test_no_false_finite_coverage(count):
    d,r,i=setup()
    with pytest.raises((ValueError,ValidationError)):build_metadata_snapshot_v1(d,i,declared_source_count=count,now=NOW)


@pytest.mark.parametrize('change',[{'max_records':True},{'max_records':10001},{'max_metadata_bytes':0},
    {'permission_producer_kind':'admin'},{'expires_at':NOW+timedelta(seconds=31)}, {'new_grant':True}])
def test_copied_descriptor_cannot_invent_producer_extend_window_or_unknown_fields(change):
    d,r,i=setup()
    with pytest.raises((ValueError,ValidationError)):build_metadata_snapshot_v1(d.model_copy(update=change),i,declared_source_count=1,now=NOW)


def test_overflow_and_duplicate_population_fail_without_partial_snapshot():
    d,r,i=setup()
    with pytest.raises(ValueError,match='byte bound'):build_metadata_snapshot_v1(d.model_copy(update={'max_metadata_bytes':1}),i,declared_source_count=1,now=NOW)
    with pytest.raises(ValueError,match='unique'):build_metadata_snapshot_v1(d,i.model_copy(update={'records':(r,r)}),declared_source_count=2,now=NOW)
    with pytest.raises(ValueError,match='record bound'):build_metadata_snapshot_v1(d.model_copy(update={'max_records':1}),i.model_copy(update={'records':(r,r.model_copy(update={'legacy_id':'2'}))}),declared_source_count=2,now=NOW)


def test_current_snapshot_membership_and_installation_are_exact():
    d,r,i=setup();before=build_metadata_snapshot_v1(d,i,declared_source_count=1,now=NOW)
    current=build_metadata_snapshot_v1(d,i.model_copy(update={'inventory_id':uuid4(),'captured_at':NOW+timedelta(seconds=1)}),declared_source_count=1,now=NOW+timedelta(seconds=1))
    assert recheck_metadata_snapshot_v1(before,current,now=NOW+timedelta(seconds=1)) is None
    missing=build_metadata_snapshot_v1(d,i.model_copy(update={'records':()}),declared_source_count=0,now=NOW)
    with pytest.raises(PermissionError):recheck_metadata_snapshot_v1(before,missing,now=NOW)
    swapped=build_metadata_snapshot_v1(d.model_copy(update={'principal_id':uuid4()}),i,declared_source_count=1,now=NOW)
    with pytest.raises(PermissionError,match='identity'):recheck_metadata_snapshot_v1(before,swapped,now=NOW)
    with pytest.raises(PermissionError):recheck_metadata_snapshot_v1(before,current,now=NOW+timedelta(seconds=20))


def test_no_copied_success_or_seal_bypass():
    d,r,i=setup();s=build_metadata_snapshot_v1(d,i,declared_source_count=1,now=NOW)
    for change in ({'target_import_authorized':True},{'metadata_sha256':'f'*64},{'quarantine_legacy_ids':()}):
        with pytest.raises(ValueError):require_original_access_v1(s.model_copy(update=change))
    with pytest.raises(PermissionError):build_metadata_snapshot_v1(d,i.model_copy(update={'captured_at':NOW+timedelta(seconds=1)}),declared_source_count=1,now=NOW)
    with pytest.raises(ValueError):build_metadata_snapshot_v1(d,i,declared_source_count=1,now=NOW.replace(tzinfo=None))


def test_input_order_is_canonical_and_nested_copied_extra_or_boolean_is_rejected():
    d,r,i=setup();other=r.model_copy(update={'legacy_id':'another'})
    a=build_metadata_snapshot_v1(d,i.model_copy(update={'records':(r,other)}),declared_source_count=2,now=NOW)
    b=build_metadata_snapshot_v1(d,i.model_copy(update={'records':(other,r)}),declared_source_count=2,now=NOW)
    assert a==b and a.quarantine_legacy_ids==('another','doc1')
    for bad in (r.model_copy(update={'has_original':1}), r.model_copy(update={'scope_grant':True})):
        with pytest.raises(ValueError):build_metadata_snapshot_v1(d,i.model_copy(update={'records':(bad,)}),declared_source_count=1,now=NOW)
