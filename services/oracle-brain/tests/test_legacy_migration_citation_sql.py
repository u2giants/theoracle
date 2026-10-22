"""Actual current migration citations, reusing the same owned SQL fixture."""
from pathlib import Path
from uuid import UUID,uuid4
import hashlib,os
import psycopg
from psycopg import sql
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.legacy_migration_v1 import LegacyMigrationFactoryV1
from test_legacy_migration_sql import (
    migration_sql,requester,certificates,invented_capture_peer_v1,
    owned_admin,known_head_v1,operation_window,
)


@pytest.mark.parametrize('migration_sql',['pdf'],indirect=True)
@pytest.mark.parametrize('fault',['current','read-revoked','withdrawn','withdraw-after-bytes'])
def test_actual_imported_citation_requires_current_independent_viewer(migration_sql,tmp_path,certificates,monkeypatch,fault):
    from oracle_brain.hosting.original_view_v1 import OriginalViewerFactoryV1,OriginalViewerUnavailable
    from oracle_brain.hosting.original_view_settings_v1 import load_original_viewer_settings_v1
    from test_original_view_settings_v1 import configured_viewer,pinned
    f=migration_sql;window,end=operation_window()
    with window:
        registered=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
        inventory=UUID(registered['inventory_id'])
        f.factory.import_batch_v1(inventory,known_head_v1(f,registered,end),uuid4(),caller_deadline=end)
    login='migration_view_'+uuid4().hex[:12];grant=uuid4();password='invented-current-viewer-only'
    with owned_admin(f.x) as c:
        source,revision,original_sha,count,media,key,seal=c.execute(
            "SELECT o.source_id,o.revision,o.original_sha256,o.byte_count,o.media_type,o.private_object_key,o.custody_locator_seal_sha256 FROM oracle2.migration_source_bindings_v1 b JOIN oracle2.source_original_revisions o ON o.workspace_id=b.workspace_id AND o.source_id=b.target_source_uuid WHERE b.workspace_id=%s AND b.legacy_kind='document' AND b.legacy_id=%s",(f.x['workspace'],f.document)).fetchone()
        owner=c.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2'").fetchone()[0]
        c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal(password)))
        c.execute(sql.SQL('GRANT oracle2_source_original_viewer TO {}').format(sql.Identifier(login)))
        c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,f.x['runtime'],f.x['registry'],f.until))
        c.execute('INSERT INTO oracle2.hosting_original_source_admissions VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (login,f.x['workspace'],source,revision,f.x['actor'],original_sha,'source-original-view',f.x['runtime'],f.x['registry'],None,f.until))
        c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
            (grant,f.x['workspace'],f.x['actor'],'source-read:'+str(source),f.x['owner'],f.x['root'],f.until))
    try:
        directory=tmp_path/'independent-viewer';directory.mkdir(mode=0o700)
        target=psycopg.conninfo.conninfo_to_dict(psycopg.conninfo.make_conninfo(f.x['admin'],user=login,password=password))
        original=dict(source_id=str(source),revision=revision,original_sha256=original_sha,byte_count=count,media_type=media,
            reservation_id=key.rsplit('/',1)[1],custody_seal_sha256=seal)
        horizon=dict(expires_at=f.until.isoformat(),original_horizon=f.until.isoformat())
        view=configured_viewer(directory,certificates,data=f.document_bytes,original=original,sql_target=target,owner=owner,login=login,
            principal=f.x['actor'],workspace=f.x['workspace'],runtime=f.x['runtime'],registry=f.x['registry'],storage_root=f.intake.settings.config.storage_root,
            config_changes=dict(horizon,storage_profile_hash=f.intake.settings.config.storage_profile_hash),peer_changes=horizon,appointment_changes=horizon)
        config=view.settings.config
        ca=pinned(Path(config.database_ca.path),Path(os.environ['ORACLE2_TEST_TLS_ROOT']).read_bytes())
        db=pinned(Path(config.database_url.path),psycopg.conninfo.make_conninfo(**(target|{'sslrootcert':ca['path']})).encode())
        config=config.model_copy(update=dict(database_url=type(config.database_url)(**db),database_ca=type(config.database_ca)(**ca)))
        ci=pinned(Path(view.args[0]),canonical_bytes(config.model_dump(mode='json')))
        peer=view.settings.peer.model_copy(update=dict(config_sha256=ci['sha256']));pi=pinned(Path(view.args[4]),canonical_bytes(peer.model_dump(mode='json')))
        appointment=view.settings.appointment.model_copy(update=dict(config_sha256=ci['sha256'],peer_profile_sha256=pi['sha256']))
        ai=pinned(Path(view.args[2]),canonical_bytes(appointment.model_dump(mode='json')))
        settings=load_original_viewer_settings_v1(ci['path'],ci['sha256'],ai['path'],ai['sha256'],pi['path'],pi['sha256'],issuer_actor=view.issuer,reviewer_actor=view.reviewer)
        factory=LegacyMigrationFactoryV1(**dict(zip(('register','prepare','observe','read','reconcile','citation'),f.consumers)),
            source=f.source,intake=f.intake,viewer=OriginalViewerFactoryV1(settings))
        def withdraw():
            with owned_admin(f.x) as c:
                c.execute('INSERT INTO oracle2.source_original_withdrawals_v1(event_id,workspace_id,source_id,revision,original_sha256,principal_id,session_role,runtime_hash,reason,idempotency_key,request_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (uuid4(),f.x['workspace'],source,revision,original_sha,f.x['actor'],login,f.x['runtime'],'Invented current citation withdrawal',uuid4(),'e'*64))
        reads=[];actual=OriginalViewerFactoryV1._private
        def observed_private(self,*args):
            data=actual(self,*args);reads.append(data)
            if fault=='withdraw-after-bytes':withdraw()
            return data
        monkeypatch.setattr(OriginalViewerFactoryV1,'_private',observed_private)
        if fault=='read-revoked':
            with owned_admin(f.x) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(grant,))
        elif fault=='withdrawn':withdraw()
        window,end=operation_window()
        with window:
            if fault=='current':
                result=factory.resolve_citation_v1(inventory,'document:'+str(f.document),caller_deadline=end)
                assert result['href']==f'/consultant/replacement/originals/{source}/{revision}'
                assert result['qualification'] is False and result['company_acceptance'] is False
                assert reads==[f.document_bytes] and hashlib.sha256(reads[0]).hexdigest()==original_sha
                assert 'data' not in result and 'body' not in result
            else:
                with pytest.raises((PermissionError,OriginalViewerUnavailable,psycopg.errors.InsufficientPrivilege)):
                    factory.resolve_citation_v1(inventory,'document:'+str(f.document),caller_deadline=end)
                assert reads==([f.document_bytes] if fault=='withdraw-after-bytes' else [])
                metadata=f.consumers[-1].citation_metadata_v1(inventory,'document:'+str(f.document),caller_deadline=end)
                if fault in ('withdrawn','withdraw-after-bytes'):
                    assert metadata['redacted'] is True
                    assert all(metadata[k] is None for k in ('source_id','revision','original_sha256'))
        with owned_admin(f.x) as c:
            assert c.execute('SELECT count(*),count(finalized_at) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(2,2)
            assert c.execute('SELECT count(*) FROM oracle2.operating_model_source_receipts WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(0,)
    finally:
        with owned_admin(f.x) as c:
            c.execute('DELETE FROM oracle2.hosting_original_source_admissions WHERE role_name=%s',(login,))
            c.execute('DELETE FROM oracle2.hosting_role_runtime_admissions WHERE role_name=%s',(login,))
            c.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(login)))

