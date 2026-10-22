"""Actual mTLS→viewer factory→fresh owned TLS worker SQL→private PDF bytes.

Fixture administrator alone creates synthetic existing-role admissions; runtime
viewer never creates grants, roles, sources, appointments or custody records.
"""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest
from dev.oracle2.test_worker_postgres_fixture import owned_worker_database
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.original_intake_v1 import OriginalIntakeFactoryV1, load_original_intake_settings_v1
from oracle_brain.hosting.original_view_v1 import OriginalViewerFactoryV1, OriginalViewerUnavailable
from test_hosting_boundary import certificates
from test_original_intake_v1 import settings as base_intake_settings
from test_replacement_source_intake_sql import requester
from test_original_view_settings_v1 import configured_viewer, pinned
from test_original_view_service_v1 import running, send, wire


@pytest.fixture
def admin_url(admin_url):
    owned_worker_database(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'], admin_url)
    assert psycopg.conninfo.conninfo_to_dict(admin_url)['dbname'].startswith('oracle_operating_model_test_')
    return admin_url


@contextmanager
def owned_admin(x):
    owned_worker_database(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'], x['admin'])
    with psycopg.connect(x['admin']) as connection:
        assert connection.pgconn.ssl_in_use
        name=psycopg.conninfo.conninfo_to_dict(x['admin'])['dbname']
        assert connection.execute('SELECT SESSION_USER,current_database()').fetchone()==('oracle2_admin',name)
        yield connection


def actual_pdf():
    import pypdfium2 as pdfium
    pdf=pdfium.PdfDocument.new();page=pdf.new_page(160,90);page.gen_content()
    output=io.BytesIO();pdf.save(output);page.close();pdf.close()
    return output.getvalue()


def actual_intake(tmp_path,x,owner):
    s=base_intake_settings(tmp_path)
    ca=pinned(tmp_path/'actual-db-ca',Path(os.environ['ORACLE2_TEST_TLS_ROOT']).read_bytes())
    db=pinned(tmp_path/'actual-db-url',psycopg.conninfo.make_conninfo(x['url'],sslrootcert=ca['path']).encode())
    updates=dict(principal_id=x['actor'],workspace_id=x['workspace'],expected_session_role=x['login'],
        expected_owner_role=owner,runtime_hash=x['runtime'],registry_hash=x['registry'],
        database_url=type(s.config.database_url)(**db),database_ca=type(s.config.database_ca)(**ca))
    c=s.config.model_copy(update=updates);raw=canonical_bytes(c.model_dump(mode='json'));s.config_path.write_bytes(raw)
    seal=hashlib.sha256(raw).hexdigest()
    keys=('principal_id','workspace_id','expected_session_role','runtime_hash','registry_hash')
    a=s.appointment.model_copy(update={**{k:getattr(c,k) for k in keys},'config_sha256':seal})
    ar=canonical_bytes(a.model_dump(mode='json'));s.appointment_path.write_bytes(ar)
    return load_original_intake_settings_v1(s.config_path,seal,s.appointment_path,hashlib.sha256(ar).hexdigest(),s.expected_issuer_actor,s.expected_reviewer_actor)


@pytest.fixture
def actual_viewer(requester,tmp_path,certificates,request):
    x=requester
    with owned_admin(x) as connection:
        owner=connection.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2'").fetchone()[0]
    intake_dir=tmp_path/'intake';intake_dir.mkdir(mode=0o700)
    intake=actual_intake(intake_dir,x,owner)
    media=getattr(request,'param','application/pdf')
    if media=='text/plain':
        data='不要未经审核就发货。仅限样品。'.encode('utf-8')
        appointment=intake.appointment.model_copy(update={'media_types':('application/pdf','text/plain')})
        raw=canonical_bytes(appointment.model_dump(mode='json'));intake.appointment_path.write_bytes(raw)
        intake=load_original_intake_settings_v1(intake.config_path,intake.config_sha256,intake.appointment_path,
            hashlib.sha256(raw).hexdigest(),intake.expected_issuer_actor,intake.expected_reviewer_actor)
        snapshot=OriginalIntakeFactoryV1(intake).intake_text_v1(source_id=None,expected_head=0,idempotency_key=uuid4(),
            filename='invented-conversation.txt',original_sha256=hashlib.sha256(data).hexdigest(),data=data)
    else:
        assert media=='application/pdf'
        data=actual_pdf()
        snapshot=OriginalIntakeFactoryV1(intake).intake_pdf_v1(source_id=None,expected_head=0,idempotency_key=uuid4(),
            filename='invented-valid.pdf',original_sha256=hashlib.sha256(data).hexdigest(),data=data)
    login='original_view_'+uuid4().hex[:12];principal=uuid4();grant=uuid4()
    with owned_admin(x) as connection:
        original=connection.execute('SELECT original_sha256,byte_count,media_type,private_object_key,custody_locator_seal_sha256 FROM oracle2.source_original_revisions WHERE workspace_id=%s AND source_id=%s AND revision=1',
            (x['workspace'],snapshot.sourceId)).fetchone()
        connection.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-viewer-only')))
        connection.execute(sql.SQL('GRANT oracle2_source_original_viewer TO {}').format(sql.Identifier(login)))
        connection.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,x['runtime'],x['registry'],x['until']))
        connection.execute('INSERT INTO oracle2.hosting_original_source_admissions VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (login,x['workspace'],snapshot.sourceId,1,principal,original[0],'source-original-view',x['runtime'],x['registry'],None,x['until']))
        connection.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
            (grant,x['workspace'],principal,'source-read:'+str(snapshot.sourceId),x['owner'],x['root'],x['until']))
    view_dir=tmp_path/'view';view_dir.mkdir(mode=0o700)
    ca=Path(os.environ['ORACLE2_TEST_TLS_ROOT'])
    target=psycopg.conninfo.conninfo_to_dict(psycopg.conninfo.make_conninfo(x['admin'],user=login,password='invented-viewer-only'))
    r=dict(source_id=str(snapshot.sourceId),revision=1,original_sha256=original[0],byte_count=original[1],media_type=original[2],
        reservation_id=original[3].rsplit('/',1)[1],custody_seal_sha256=original[4])
    f=configured_viewer(view_dir,certificates,data=data,original=r,sql_target=target,owner=owner,login=login,
        principal=principal,workspace=x['workspace'],runtime=x['runtime'],registry=x['registry'],storage_root=intake.config.storage_root)
    # SQL CA is a different synthetic CA from HTTP. Re-pin exact protected URL/CA,
    # then rebuild only these independently installed synthetic startup records.
    # configured_viewer takes the real target but its copied TLS CA is HTTP CA;
    # overwrite before externally pinning the final config/appointment here.
    c=f.settings.config
    ca_input=pinned(Path(c.database_ca.path),ca.read_bytes())
    db_input=pinned(Path(c.database_url.path),psycopg.conninfo.make_conninfo(**(target|{'sslrootcert':ca_input['path']})).encode())
    c=c.model_copy(update={'database_url':type(c.database_url)(**db_input),'database_ca':type(c.database_ca)(**ca_input)})
    ci=pinned(Path(f.args[0]),canonical_bytes(c.model_dump(mode='json')))
    peer=f.settings.peer.model_copy(update={'config_sha256':ci['sha256']});pi=pinned(Path(f.args[4]),canonical_bytes(peer.model_dump(mode='json')))
    a=f.settings.appointment.model_copy(update={'config_sha256':ci['sha256'],'peer_profile_sha256':pi['sha256']})
    ai=pinned(Path(f.args[2]),canonical_bytes(a.model_dump(mode='json')))
    from oracle_brain.hosting.original_view_settings_v1 import load_original_viewer_settings_v1
    f.settings=load_original_viewer_settings_v1(ci['path'],ci['sha256'],ai['path'],ai['sha256'],pi['path'],pi['sha256'],issuer_actor=f.issuer,reviewer_actor=f.reviewer)
    f.target=target|{'sslrootcert':ca_input['path']};f.x=x;f.login=login;f.grant=grant;f.source=snapshot.sourceId;f.intake=intake
    try:yield f
    finally:
        with owned_admin(x) as connection:
            connection.execute('DELETE FROM oracle2.hosting_original_source_admissions WHERE role_name=%s',(login,))
            connection.execute('DELETE FROM oracle2.hosting_role_runtime_admissions WHERE role_name=%s',(login,))
            connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(login)))


def test_actual_tls_sql_private_pdf_exact_and_viewer_cannot_mutate_or_borrow_roles(actual_viewer,certificates):
    f=actual_viewer
    with running(f) as server:
        status,data,headers=send(server,certificates,wire(f))
        assert status==200 and data==f.data and headers['Content-Type']=='application/pdf'
        assert headers['Connection']=='close'
        assert hashlib.sha256(data).hexdigest()==f.settings.config.sources[0].original_sha256
        assert send(server,certificates,wire(f),headers={'Range':'bytes=0-10'})[:2]==(503,b'')
    url=psycopg.conninfo.make_conninfo(**f.target)
    for query in ['SELECT * FROM oracle2.source_original_revisions','SELECT * FROM oracle2.hosting_original_source_admissions',
                  'SELECT oracle2.original_revision_read_v1(%s,1)','SELECT oracle2.original_revision_review_input_v1(%s,1)',
                  'SELECT oracle2.original_population_current_v1(%s)','SELECT oracle2.reserve_source_revision_v1(0,%s::jsonb,%s)']:
        params=(f.source,) if query.count('%s')==1 else ('{}',uuid4()) if query.count('%s')==2 else None
        with psycopg.connect(url) as conn,pytest.raises(psycopg.errors.InsufficientPrivilege):conn.execute(query,params)


def test_actual_sql_admission_narrows_authenticated_delivery_header(actual_viewer, certificates):
    f = actual_viewer
    until = datetime.now(timezone.utc) + timedelta(seconds=5)
    with owned_admin(f.x) as connection:
        connection.execute('UPDATE oracle2.hosting_original_source_admissions SET expires_at=%s WHERE role_name=%s',
            (until, f.login))
    with running(f) as server:
        status, data, headers = send(server, certificates, wire(f, seconds=10))
    assert status == 200 and data == f.data
    assert headers['X-Oracle-Original-Valid-Until'] == until.strftime('%Y-%m-%dT%H:%M:%S.%fZ')



@pytest.mark.parametrize('fault',['revoked','expired','runtime','withdrawn','historical','extra_role','owner','wrong_login','no_tls'])
def test_actual_current_permission_and_target_denials(actual_viewer,certificates,fault):
    f=actual_viewer;x=f.x;restore=None
    with owned_admin(x) as connection:
        if fault=='revoked':connection.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f.grant,))
        elif fault=='expired':connection.execute("UPDATE oracle2.hosting_original_source_admissions SET expires_at=clock_timestamp()-interval '1 second' WHERE role_name=%s",(f.login,))
        elif fault=='runtime':connection.execute('UPDATE oracle2.hosting_role_runtime_admissions SET registry_hash=%s WHERE role_name=%s',('d'*64,f.login))
        elif fault=='historical':
            connection.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                (uuid4(),x['workspace'],x['actor'],'source-read:'+str(f.source),x['owner'],x['root'],x['until']))
        elif fault=='withdrawn':
            r=f.settings.config.sources[0]
            connection.execute('INSERT INTO oracle2.source_original_withdrawals_v1(event_id,workspace_id,source_id,revision,original_sha256,principal_id,session_role,runtime_hash,reason,idempotency_key,request_sha256) VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s)',
                (uuid4(),x['workspace'],f.source,r.original_sha256,f.settings.config.principal_id,f.login,x['runtime'],'Invented withdrawal',uuid4(),'e'*64))
        elif fault=='extra_role':connection.execute(sql.SQL('GRANT oracle2_source_original_reader TO {}').format(sql.Identifier(f.login)))
        elif fault=='owner':
            role='synthetic_view_owner_'+uuid4().hex[:10]
            connection.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
            connection.execute(sql.SQL('ALTER FUNCTION oracle2.original_revision_view_v1(uuid,integer) OWNER TO {}').format(sql.Identifier(role)))
            restore=f.settings.config.expected_owner_role
    try:
        if fault=='historical':
            updated=OriginalIntakeFactoryV1(f.intake).intake_pdf_v1(source_id=f.source,expected_head=1,idempotency_key=uuid4(),
                filename='invented-valid.pdf',original_sha256=hashlib.sha256(f.data).hexdigest(),data=f.data)
            assert updated.revision==2
            with owned_admin(x) as connection:
                originals=connection.execute('SELECT revision,private_object_key FROM oracle2.source_original_revisions WHERE workspace_id=%s AND source_id=%s ORDER BY revision',(x['workspace'],f.source)).fetchall()
                assert [r[0] for r in originals]==[1,2]
                assert all((Path(f.intake.config.storage_root)/r[1]).read_bytes()==f.data for r in originals)
        if fault in {'wrong_login','no_tls'}:
            mode='disable' if fault=='no_tls' else 'verify-full'
            url=psycopg.conninfo.make_conninfo(**(f.target|{'sslmode':mode})) if fault=='no_tls' else x['url']
            if fault=='no_tls':
                with pytest.raises((psycopg.OperationalError,psycopg.errors.InsufficientPrivilege),match='no encryption|TLS replacement'):
                    with psycopg.connect(url) as conn:
                        conn.execute("SET LOCAL statement_timeout='5s'")
                        conn.execute('SELECT oracle2.original_revision_view_v1(%s,1)',(f.source,))
            else:
                with psycopg.connect(url) as conn,pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute("SET LOCAL statement_timeout='5s'")
                    conn.execute('SELECT oracle2.original_revision_view_v1(%s,1)',(f.source,))
        else:
            with running(f) as server:assert send(server,certificates,wire(f))[:2]==(503,b'')
    finally:
        if restore:
            with owned_admin(x) as connection:
                connection.execute(sql.SQL('ALTER FUNCTION oracle2.original_revision_view_v1(uuid,integer) OWNER TO {}').format(sql.Identifier(restore)))


def test_actual_revocation_after_first_connection_closes_denies_second_pass(actual_viewer,certificates,monkeypatch):
    f=actual_viewer;real_connect=psycopg.connect;calls=[]
    @contextmanager
    def observed_connect(url,*args,**kwargs):
        is_viewer=psycopg.conninfo.conninfo_to_dict(url).get('user')==f.login
        with real_connect(url,*args,**kwargs) as conn:
            if is_viewer:calls.append(conn)
            yield conn
        if is_viewer and len(calls)==1:
            assert conn.closed
            owned_worker_database(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'],f.x['admin'])
            with real_connect(f.x['admin']) as admin:
                admin.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f.grant,))
    monkeypatch.setattr('psycopg.connect',observed_connect)
    with running(f) as server:assert send(server,certificates,wire(f))[:2]==(503,b'')
    assert len(calls)==2 and all(c.closed for c in calls)


@pytest.mark.parametrize('actual_viewer',['text/plain'],indirect=True)
def test_actual_text_intake_independent_native_qualification_then_tls_view_and_current_revocation(actual_viewer,certificates,tmp_path):
    from types import SimpleNamespace
    from test_conversation_original_sql import appointed_native_original_phases_v1,reading_then_review
    f=actual_viewer
    snapshot=SimpleNamespace(sourceId=f.source,originalSha256=hashlib.sha256(f.data).hexdigest(),filename='invented-conversation.txt')
    with appointed_native_original_phases_v1(f.x,snapshot,f.data,f.intake,tmp_path) as observed:
        _,qualified=reading_then_review(observed,expire_reader=True)
        assert qualified.source_ref.source_id==f.source
        assert qualified.source_ref.original_sha256==qualified.source_ref.reading_sha256==hashlib.sha256(f.data).hexdigest()
    with running(f) as server:
        status,data,headers=send(server,certificates,wire(f))
        assert status==200 and data==f.data
        assert headers['Content-Type']=='text/plain; charset=utf-8'
        assert headers['X-Content-Type-Options']=='nosniff' and headers['Connection']=='close'
        # The viewer is a separate actual role, not the expired byte reader or
        # independently appointed reviewer. Current own source access still wins.
        with owned_admin(f.x) as connection:
            assert connection.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE source_id=%s',(f.source,)).fetchone()==(1,)
            assert connection.execute('SELECT count(*) FROM oracle2.operating_dispatch_reservations WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(0,)
            connection.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f.grant,))
        assert send(server,certificates,wire(f))[:2]==(503,b'')
