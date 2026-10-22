"""Closed source preparation only: no source SQL/permission or import proof."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

import pytest
from oracle_brain.migration.legacy_export_reader_v1 import (
    TechnicalLegacyScopeV1, _message_metadata_v1, ExportedLegacyMessageV1,
    TechnicalLegacySnapshotV1, actual_export_program_sha256_v1,
)
from oracle_brain.migration.migration_settings_v1 import PUBLIC_SIGNATURES, PRIVATE_SIGNATURES
from oracle_brain.operating_model.contracts import canonical_bytes


def row(text):
    return (uuid4(),uuid4(),uuid4(),'user',text,len(text.encode('utf8')),
            None,None,datetime.now(timezone.utc))


@pytest.mark.parametrize('body',['invented message','双语原始消息','<>&"\\\n'*10000])
def test_actual_body_hash_and_length_bound_projection_without_reescaping_text(body):
    value=row(body)
    metadata=_message_metadata_v1(value)
    assert metadata[4]=={'observed_sha256':hashlib.sha256(body.encode()).hexdigest(),'available':True}
    assert metadata[5]==len(body.encode())
    assert len(canonical_bytes({'metadata':str(metadata)}))<1000
    changed=list(value);changed[4]=body+'x';changed[5]+=1
    assert _message_metadata_v1(changed)[4]!=metadata[4]


@pytest.mark.parametrize('change',[(4,True),(5,True),(5,-1),(5,999)])
def test_inconsistent_source_body_or_count_never_becomes_eligible(change):
    value=list(row('invented'))
    value[change[0]]=change[1]
    with pytest.raises(PermissionError):_message_metadata_v1(value)


def test_unavailable_body_stays_unavailable_without_invented_hash():
    value=list(row('original unavailable'));value[4]=None
    assert _message_metadata_v1(value)[4]=={'observed_sha256':None,'available':False}
    assert _message_metadata_v1(None) is None


@pytest.mark.parametrize('length',[0,8,10])
def test_message_shape_not_silently_reinterpreted(length):
    with pytest.raises(PermissionError):_message_metadata_v1([None]*length)


def scope(**changes):
    value=dict(schema_version=1,source_database_identity=str(uuid4()),employee_id=str(uuid4()),
        auth_user_id=str(uuid4()),auth_provider='microsoft',channel_id=str(uuid4()),message_ids=[],document_ids=[])
    value.update(changes)
    return TechnicalLegacyScopeV1.model_validate_json(json.dumps(value))


@pytest.mark.parametrize('change',[{'auth_provider':'admin'},{'workspace_id':str(uuid4())},
    {'jwt':'invented'},{'role':'postgres'},{'schema_version':True}])
def test_technical_mapping_cannot_invent_human_or_administrative_authority(change):
    with pytest.raises(ValueError):scope(**change)


def test_finite_allowlist_duplicate_and_unstable_order_refused():
    a,b=sorted([uuid4(),uuid4()],key=str)
    with pytest.raises(ValueError):scope(message_ids=[str(a),str(a)])
    with pytest.raises(ValueError):scope(message_ids=[str(b),str(a)])
    valid=scope(message_ids=[str(a),str(b)])
    assert 'schema_version' not in valid.sql_scope_v1()
    assert set(valid.sql_scope_v1())=={'source_database_identity','employee_id','auth_user_id','auth_provider','channel_id','message_ids','document_ids'}


def test_private_buffers_do_not_appear_in_snapshot_or_message_repr():
    secret=b'invented private source content'
    message=ExportedLegacyMessageV1(uuid4(),'a'*64,hashlib.sha256(secret).hexdigest(),len(secret),secret)
    snapshot=TechnicalLegacySnapshotV1(secret,(message,),'b'*64,datetime.now(timezone.utc))
    assert secret.decode() not in repr(message)+repr(snapshot)
    assert snapshot.human_auth_session_proven is False and snapshot.qualified_source is False
    assert snapshot.consistent_boundary_proven is False


def test_exact_program_and_capability_inventory_are_finite_not_runtime_selectors():
    assert len(actual_export_program_sha256_v1())==64
    assert len(PUBLIC_SIGNATURES)==7 and len(set(PUBLIC_SIGNATURES))==7
    assert len(PRIVATE_SIGNATURES)==12 and len(set(PRIVATE_SIGNATURES))==12


def test_recapture_observations_do_not_fabricate_another_original_or_currentness_change():
    from oracle_brain.migration.legacy_export_reader_v1 import stable_inventory_entries_v1
    from oracle_brain.operating_model.contracts import digest
    entry=dict(legacy_kind='document',legacy_id=str(uuid4()),metadata_sha256='a'*64,permission_sha256='b'*64,
        original_sha256='c'*64,byte_count=10,media_type='application/pdf',disposition='document-current-capture-eligible')
    first=dict(entry,capture={'capture_id':str(uuid4()),'etag':'"old-current"','observed_at':'first'})
    second=dict(entry,capture={'capture_id':str(uuid4()),'etag':'"new-current"','observed_at':'second'})
    assert digest(stable_inventory_entries_v1([first]))==digest(stable_inventory_entries_v1([second]))
    assert digest([first])!=digest([second])  # Documentary observations remain distinct.
    for key,value in [('original_sha256','d'*64),('byte_count',11),('media_type','text/plain'),('permission_sha256','e'*64)]:
        assert digest(stable_inventory_entries_v1([first]))!=digest(stable_inventory_entries_v1([second|{key:value}]))


def test_private_capture_and_document_bytes_are_not_exposed_by_snapshot_repr():
    from oracle_brain.migration.legacy_export_reader_v1 import ExportedLegacyDocumentV1
    data=b'invented confidential current document'
    doc=ExportedLegacyDocumentV1(uuid4(),'a'*64,'b'*64,len(data),data,{'private_receipt_key':'private invented key'})
    snapshot=TechnicalLegacySnapshotV1(b'private inventory',(),'c'*64,datetime.now(timezone.utc),documents=(doc,))
    assert 'confidential' not in repr(doc)+repr(snapshot)
    assert 'private invented key' not in repr(doc)+repr(snapshot)


def test_fixture_profile_uses_actual_strict_canonical_owner_without_changing_instants():
    from datetime import timedelta
    from oracle_brain.migration.legacy_export_reader_v1 import LegacyExportProfileV1
    from oracle_brain.operating_model.protected_inputs_v1 import _parse
    from test_legacy_migration_sql import canonical_fixture_record_v1
    now=datetime.now(timezone.utc);until=now+timedelta(seconds=30)
    value=dict(schema_version=1,purpose='technical-legacy-channel-export-v1',permission_producer_kind='technical-channel-v1',
        source_scope=scope().model_dump(mode='json'),database_url=dict(schema_version=1,path='/private/invented-url',sha256='a'*64),
        database_ca=dict(schema_version=1,path='/private/invented-ca',sha256='b'*64),session_role='invented_source',
        source_catalog_sha256='c'*64,source_program_sha256='d'*64,max_original_bytes=1024,
        valid_from=now.isoformat(),expires_at=until.isoformat(),original_horizon=until.isoformat())
    # This is exactly the setup02 failure: +00:00 strings and omitted optional
    # declared defaults are valid model input, not its canonical protected bytes.
    with pytest.raises(ValueError,match='canonical protected record'):_parse(LegacyExportProfileV1,canonical_bytes(value))
    raw=canonical_fixture_record_v1(LegacyExportProfileV1,value)
    parsed=_parse(LegacyExportProfileV1,raw)
    assert parsed.valid_from==now and parsed.expires_at==parsed.original_horizon==until
    assert parsed.document_capture_profile is None
    assert parsed.source_scope.sql_scope_v1()==TechnicalLegacyScopeV1.model_validate_json(canonical_bytes(value['source_scope'])).sql_scope_v1()
    missing=dict(value);del missing['database_url']
    with pytest.raises(ValueError):canonical_fixture_record_v1(LegacyExportProfileV1,missing)
    with pytest.raises(ValueError):canonical_fixture_record_v1(LegacyExportProfileV1,value|{'expires_at':(until+timedelta(seconds=1)).isoformat()})
    with pytest.raises(ValueError):canonical_fixture_record_v1(LegacyExportProfileV1,value|{'valid_from':until.isoformat()})
    with pytest.raises(ValueError):_parse(LegacyExportProfileV1,raw+b' ')


def test_fixture_serializer_does_not_revive_an_expired_consumer(tmp_path):
    from datetime import timedelta
    from oracle_brain.migration.migration_settings_v1 import MigrationConsumerConfigV1,MigrationConsumerSettingsV1,SIGNATURES,PUBLIC_NAMES
    from oracle_brain.operating_model.protected_inputs_v1 import _parse
    from test_legacy_migration_sql import canonical_fixture_record_v1
    expired=datetime.now(timezone.utc)-timedelta(seconds=1)
    role='invented_snapshot';own=str(uuid4());workspace=str(uuid4())
    roles={name:[role] for name in PUBLIC_NAMES}
    value=dict(schema_version=1,purpose='legacy-migration-consumer-v1',operation='snapshot-register',admission_id=str(uuid4()),
        principal_id=own,workspace_id=workspace,origin_system='invented_expired',session_role=role,expected_owner='invented_owner',
        runtime_sha256='a'*64,registry_sha256='b'*64,descriptor_sha256='c'*64,source_scope_sha256='d'*64,source_program_sha256='e'*64,
        intake_principal_id=own,intake_config_sha256='f'*64,database_url=dict(schema_version=1,path='/private/unread/url',sha256='a'*64),
        database_ca=dict(schema_version=1,path='/private/unread/ca',sha256='b'*64),
        capability_fingerprints=[(s.split('(')[0],'c'*64,'d'*64) for s in SIGNATURES],public_capability_roles=sorted(roles.items()),
        valid_from=(expired-timedelta(seconds=30)).isoformat(),expires_at=expired.isoformat(),original_horizon=expired.isoformat())
    raw=canonical_fixture_record_v1(MigrationConsumerConfigV1,value)
    parsed=_parse(MigrationConsumerConfigV1,raw)
    assert parsed.expires_at==parsed.original_horizon==expired
    path=tmp_path/'expired-config';path.write_bytes(raw);path.chmod(0o600)
    with pytest.raises(PermissionError,match='horizon expired'):
        MigrationConsumerSettingsV1.load(path,hashlib.sha256(raw).hexdigest())


def test_private_invented_exception_diagnostic_preserves_public_UNKNOWN_and_never_stringifies_payload(tmp_path):
    from types import SimpleNamespace
    from oracle_brain.migration.migration_authority_v1 import MigrationOutcomeUnknown
    from test_legacy_migration_sql import private_exception_stage_v1
    class InventedSQLFailure(Exception):
        sqlstate='22023'
        diag=SimpleNamespace(message_primary='invalid parameter value',context='invented SQL function line 12')
        def __str__(self):raise AssertionError('must never stringify private payload')
    hidden=InventedSQLFailure('invented private payload must remain hidden')
    public=MigrationOutcomeUnknown('Migration outcome unknown; reconcile the exact command read-only; never resend')
    public.__context__=hidden;before=str(public)
    path=tmp_path/'private-error.json';private_exception_stage_v1(path,public)
    value=json.loads(path.read_bytes())
    assert [item['error_type'] for item in value['chain']]==['MigrationOutcomeUnknown','InventedSQLFailure']
    assert value['chain'][1]['sqlstate']=='22023'
    assert 'invented private payload' not in path.read_text()
    assert str(public)==before and public.__context__ is hidden
    assert path.stat().st_mode&0o077==0
    with pytest.raises(FileExistsError):private_exception_stage_v1(path,public)


def test_SQL_etag_rewrite_preserves_exact_quoted_ASCII_language_and_bound():
    import re
    from pathlib import Path
    source=(Path(__file__).parents[1]/'sql/027_legacy_migration.sql').read_text()
    assert "OR capture->>'etag'!~'^\"[!#-~]*\"$' OR char_length(capture->>'etag')>512" in source
    original=re.compile(r'^"[!#-~]{0,510}"$')
    replacement=re.compile(r'^"[!#-~]*"$')
    values=['"'+'a'*n+'"' for n in (0,1,255,256,510,511)]
    values+=['"'+chr(n)+'"' for n in range(128)]
    values+=['"é"','"双"','"😀"','unquoted','W/"tag"','"a"b"','"a"\n']
    for value in values:
        expected=original.fullmatch(value) is not None
        actual=replacement.fullmatch(value) is not None and len(value)<=512
        assert actual==expected
    assert [original.fullmatch('"'+'a'*n+'"') is not None for n in (0,1,255,256,510,511)]==[True]*5+[False]
