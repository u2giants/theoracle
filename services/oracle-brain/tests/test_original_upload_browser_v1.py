"""Actual invented browser source path; explicit auth-import hooks, not real login.

Recording-SQL and actual-owned-SQL proofs are distinct tests. No skip/fallback.
"""
import hashlib,json,os,subprocess,threading
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from pathlib import Path
import psycopg
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.original_intake_v1 import load_original_intake_settings_v1
from oracle_brain.hosting.original_upload_settings_v1 import OriginalUploadPeerV1
from oracle_brain.hosting.original_upload_service_v1 import protected_original_upload_chunks_server_v1
from test_hosting_boundary import certificates
from test_original_upload_chunks_v1 import setup_upload
from test_replacement_source_intake_sql import requester


def run_browser(f,path,seal,certificates,tmp_path):
    """Regenerate invented dual-SAN server leaf; distinct fixture-only startup."""
    profile=json.loads(path.read_bytes());tls=Path(profile['server_certificate_file']).parent
    ext=tls/'browser-server.ext';ext.write_text('subjectAltName=DNS:localhost,DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer')
    subprocess.run(['openssl','x509','-req','-in',str(certificates/'server.csr'),'-CA',str(certificates/'ca.pem'),'-CAkey',str(certificates/'ca.key'),'-CAcreateserial','-out',profile['server_certificate_file'],'-days','1','-extfile',str(ext)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    profile.update(server_certificate_sha256=hashlib.sha256(Path(profile['server_certificate_file']).read_bytes()).hexdigest(),server_hostname='localhost.localdomain',listen_host='::1',expires_at=(f.s.config.expires_at-timedelta(seconds=1)).isoformat())
    value=OriginalUploadPeerV1.model_validate_json(json.dumps(profile));raw=canonical_bytes(value.model_dump(mode='json'));path.write_bytes(raw);seal=hashlib.sha256(raw).hexdigest()
    server=protected_original_upload_chunks_server_v1(f.s,path,seal)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
    original_apply=server.upload_store.apply
    def observed_apply(*args,**kwargs):
        result=original_apply(*args,**kwargs);(tmp_path/'last-result.json').write_bytes(canonical_bytes(result.model_dump(mode='json')));return result
    server.upload_store.apply=observed_apply
    p=value;c=f.s.config
    metadata=dict(scratch=str(tmp_path),auth_user_id=str(c.auth_user_id),employee_id=str(c.employee_id),project_url=c.auth_issuer.removesuffix('/auth/v1'),principal_id=str(c.principal_id),workspace_id=str(c.workspace_id),runtime_hash=c.runtime_hash,registry_hash=c.registry_hash,intake_config_sha256=f.s.config_sha256,intake_appointment_sha256=f.s.appointment_sha256,upload_peer_profile_sha256=seal,upload_spool_initialization_sha256=p.spool_initialization_sha256,storage_profile_hash=c.storage_profile_hash,backend_origin='https://localhost.localdomain:'+str(server.server_port),server_key_file=p.server_key_file,server_certificate_file=p.server_certificate_file,client_ca_file=p.client_ca_file,client_certificate_file=str(certificates/'worker.pem'),client_key_file=str(certificates/'worker.key'),client_uri=p.client_uri,issuer_actor=str(p.issuer_actor),reviewer_actor=str(p.reviewer_actor),valid_from=p.valid_from.isoformat(),expires_at=p.expires_at.isoformat(),original_horizon=p.original_horizon.isoformat())
    meta=tmp_path/'browser-metadata.json';meta.write_text(json.dumps(metadata));meta.chmod(0o600)
    repo=Path(__file__).resolve().parents[3]
    try:
        result=subprocess.run(['pnpm','--filter','@oracle/web','exec','tsx','tests/oracle2/original-upload-proof.ts',str(meta)],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=55)
        (tmp_path/'browser-process.txt').write_text(result.stdout)
        assert result.returncode==0,result.stdout[-6000:]
        receipt=json.loads((tmp_path/'browser-receipt.json').read_text())
        assert receipt['byte_count']==25*1024*1024 and receipt['deadline_count']==1 and len(receipt['operations'])==15
        objects=list(Path(c.storage_root).glob('source-originals/*/*/*/*'))
        assert len(objects)==1 and objects[0].is_file()
        assert objects[0].stat().st_size==receipt['byte_count'] and hashlib.sha256(objects[0].read_bytes()).hexdigest()==receipt['original_sha256']
        assert len(list(Path(c.storage_root).glob('intake-observations/*/custody.json')))==1
        return receipt
    finally:
        server.shutdown();server.server_close();thread.join(2)
        assert not thread.is_alive() and not server._active and server.socket.fileno()==-1


def test_actual_browser_recording_sql_original_upload(tmp_path,monkeypatch,certificates):
    f,path,seal,s=setup_upload(tmp_path,monkeypatch,certificates)
    receipt=run_browser(f,path,seal,certificates,tmp_path)
    assert f.visible and f.intake_calls.count('finalize')==1
    assert receipt['auth']=='invented existing-import hooks'


def test_actual_browser_owned_sql_original_upload(tmp_path,monkeypatch,certificates,requester):
    # Existing owned requester fixture provisions its existing role and scopes.
    # The protected production factory remains actual psycopg with TLS/SCRAM.
    actual_connect=psycopg.connect
    f,path,seal,s=setup_upload(tmp_path,monkeypatch,certificates)
    monkeypatch.setattr(psycopg,'connect',actual_connect)
    x=requester;target=psycopg.conninfo.conninfo_to_dict(x['url'])
    assert target['sslmode']=='verify-full' and target.get('sslrootcert')
    with actual_connect(x['admin']) as conn:
        owner=conn.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2'").fetchone()[0]
    c=f.s.config;url=Path(c.database_url.path);url.write_text(x['url']);ca=Path(target['sslrootcert'])
    updated=c.model_copy(update=dict(expected_session_role=x['login'],expected_owner_role=owner,workspace_id=x['workspace'],principal_id=x['actor'],runtime_hash=x['runtime'],registry_hash=x['registry'],database_url=type(c.database_url)(path=str(url),sha256=hashlib.sha256(url.read_bytes()).hexdigest()),database_ca=type(c.database_ca)(path=str(ca),sha256=hashlib.sha256(ca.read_bytes()).hexdigest())))
    raw=canonical_bytes(updated.model_dump(mode='json'));f.s.config_path.write_bytes(raw);config_sha=hashlib.sha256(raw).hexdigest()
    appointment=f.s.appointment.model_copy(update=dict(config_sha256=config_sha,expected_session_role=x['login'],workspace_id=x['workspace'],principal_id=x['actor'],runtime_hash=x['runtime'],registry_hash=x['registry']))
    raw=canonical_bytes(appointment.model_dump(mode='json'));f.s.appointment_path.write_bytes(raw)
    f.s=load_original_intake_settings_v1(f.s.config_path,config_sha,f.s.appointment_path,hashlib.sha256(raw).hexdigest(),f.s.expected_issuer_actor,f.s.expected_reviewer_actor)
    profile=json.loads(path.read_bytes());profile.update(intake_config_sha256=config_sha,intake_appointment_sha256=f.s.appointment_sha256,workspace_id=str(x['workspace']),principal_id=str(x['actor']),runtime_hash=x['runtime'],registry_hash=x['registry'])
    init=Path(profile['spool_root'])/'initialization.json';v=json.loads(init.read_bytes());v.update(workspace_id=str(x['workspace']),principal_id=str(x['actor']),runtime_hash=x['runtime'],registry_hash=x['registry']);raw=canonical_bytes(v);init.write_bytes(raw);profile['spool_initialization_sha256']=hashlib.sha256(raw).hexdigest();path.write_bytes(canonical_bytes(profile))
    receipt=run_browser(f,path,seal,certificates,tmp_path)
    with actual_connect(x['admin']) as conn:
        assert conn.pgconn.ssl_in_use
        rows=conn.execute('SELECT original_sha256,byte_count FROM oracle2.source_original_revisions WHERE workspace_id=%s',(x['workspace'],)).fetchall()
        assert rows==[(receipt['original_sha256'],receipt['byte_count'])]
        assert conn.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
