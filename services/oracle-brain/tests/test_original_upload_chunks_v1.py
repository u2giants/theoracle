"""Actual loopback mTLS, actual intake factory/private store; recording SQL only."""
import base64,hashlib,json,os,socket,threading
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.hosting.original_intake_v1 import OriginalIntakeFactoryV1
from oracle_brain.hosting.original_upload_settings_v1 import OriginalUploadPeerV1,load_original_upload_settings_v1
from oracle_brain.hosting.original_upload_store_v1 import *
from oracle_brain.hosting.original_upload_service_v1 import protected_original_upload_chunks_server_v1,PATH
from test_hosting_boundary import certificates
from test_replacement_request_service_v1 import profile_fixture,client
from test_replacement_upload_service_v1 import recording_intake,PDF


def setup_upload(tmp_path,monkeypatch,certificates):
    f,path,seal,tls=profile_fixture(tmp_path,monkeypatch,certificates)
    recording_intake(f,monkeypatch)
    root=tmp_path/'external-spool';root.mkdir(mode=0o700);i=root.stat();p=json.loads(path.read_bytes())
    (root/'upload.lock').write_bytes(b'');(root/'upload.lock').chmod(0o600);lock=(root/'upload.lock').stat()
    initialization=dict(lock_device=lock.st_dev,lock_inode=lock.st_ino,lock_uid=lock.st_uid,schema_version=1,purpose='original-upload-spool-v1',workspace_id=p['workspace_id'],principal_id=p['principal_id'],runtime_hash=p['runtime_hash'],registry_hash=p['registry_hash'])
    raw=canonical_bytes(initialization);(root/'initialization.json').write_bytes(raw);(root/'initialization.json').chmod(0o600)
    p.update(purpose='original-upload-chunks-peer-v1',spool_root=str(root),spool_device=i.st_dev,spool_inode=i.st_ino,spool_uid=i.st_uid,spool_initialization_sha256=hashlib.sha256(raw).hexdigest())
    profile=OriginalUploadPeerV1.model_validate_json(json.dumps(p));raw=canonical_bytes(profile.model_dump(mode='json'));path.write_bytes(raw)
    settings=load_original_upload_settings_v1(f.s,path,hashlib.sha256(raw).hexdigest())
    return f,path,hashlib.sha256(raw).hexdigest(),settings


def begin(data=PDF,**patch):
    return parse_upload_request_v1(canonical_bytes(dict(schema_version=1,operation='begin',source_id=None,expected_head=0,idempotency_key=str(uuid4()),filename='invented.pdf',original_sha256=hashlib.sha256(data).hexdigest(),byte_count=len(data),caller_deadline=(now()+timedelta(seconds=7)).isoformat().replace('+00:00','Z'))|patch))


def action(b,r,operation='status',**patch):
    return parse_upload_request_v1(canonical_bytes(dict(schema_version=1,operation=operation,reservation_id=str(r.reservation_id),source_id=str(r.source_id),revision=r.revision,begin_sha256=digest(b.model_dump(mode='json')),caller_deadline=b.model_dump(mode='json')['caller_deadline'])|patch))


def chunk(b,r,data=PDF,index=0,**patch):
    return action(b,r,'chunk',chunk_index=index,offset=index*CHUNK_BYTES,chunk_sha256=hashlib.sha256(data).hexdigest(),data_base64=base64.b64encode(data).decode(),**patch)


@contextmanager
def running_chunks(tmp_path,monkeypatch,certificates):
    f,path,seal,settings=setup_upload(tmp_path,monkeypatch,certificates)
    server=protected_original_upload_chunks_server_v1(f.s,path,seal);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
    try:yield f,settings,server
    finally:
        server.shutdown();server.server_close();thread.join(2)
        assert not thread.is_alive() and not server._active and server.socket.fileno()==-1


def send(server,certificates,request,identity='worker',headers=None,path=PATH):
    c=client(server,certificates,identity);c.timeout=5
    c._create_connection=lambda address,timeout,source_address=None:socket.create_connection(('127.0.0.1',address[1]),timeout,source_address)
    try:
        c.request('POST',path,body=canonical_bytes(request.model_dump(mode='json')),headers={'Content-Type':'application/json'}|(headers or {}))
        res=c.getresponse();raw=res.read();return res.status,UploadResponseV1.model_validate_json(raw) if res.status==200 else raw
    finally:c.close()


def test_actual_tls_factory_private_bytes_custody_finalize_and_historical_status(tmp_path,monkeypatch,certificates):
    with running_chunks(tmp_path,monkeypatch,certificates) as (f,s,server):
        b=begin();status,r=send(server,certificates,b);assert status==200
        status,r=send(server,certificates,chunk(b,r));assert status==200 and r.received_bytes==len(PDF)
        status,r=send(server,certificates,action(b,r,'finalize'));assert status==200 and r.state=='committed' and r.source_snapshot.state=='awaiting_original_reading'
        assert f.visible and not r.qualification and not r.remote_stop_proven
        status,historical=send(server,certificates,action(b,r));assert status==200 and historical.state=='committed' and historical.source_snapshot is None
        assert len(set(f.deadlines))==1
        path=Path(f.s.config.storage_root)/f'source-originals/{f.s.config.workspace_id}/{f.source}/1/{f.reservation}'
        assert path.read_bytes()==PDF
        assert sum(x=='finalize' for x in f.intake_calls)==1


def test_exact25mib_thirteen_chunks_preserves_backend_limit(tmp_path,monkeypatch,certificates):
    data=PDF+b' '*(25*1024*1024-len(PDF))
    with running_chunks(tmp_path,monkeypatch,certificates) as (f,s,server):
        b=begin(data);status,r=send(server,certificates,b);assert status==200
        for i,offset in enumerate(range(0,len(data),CHUNK_BYTES)):
            part=data[offset:offset+CHUNK_BYTES];request=chunk(b,r,part,i)
            assert len(canonical_bytes(request.model_dump(mode='json')))<MAX_REQUEST
            status,r=send(server,certificates,request);assert status==200 and r.next_chunk_index==i+1
        assert r.next_chunk_index==13 and r.received_bytes==len(data)
        status,r=send(server,certificates,action(b,r,'finalize'));assert status==200 and r.state=='committed'
        assert f.visible


def test_exact_chunk_ack_conflict_and_original_begin_hash_collision(tmp_path,monkeypatch,certificates):
    f,path,seal,s=setup_upload(tmp_path,monkeypatch,certificates);store=OriginalUploadStoreV1(s,OriginalIntakeFactoryV1(f.s));b=begin();r=store.apply(b,peer_until=s.current());c=chunk(b,r)
    r=store.apply(c,peer_until=s.current());again=store.apply(c,peer_until=s.current());assert again.received_bytes==r.received_bytes
    altered=begin(original_sha256='b'*64,idempotency_key=str(b.idempotency_key),caller_deadline=b.model_dump(mode='json')['caller_deadline'])
    with pytest.raises(PermissionError):store.apply(altered,peer_until=s.current())
    with pytest.raises(PermissionError):store.apply(chunk(b,r,PDF.replace(b'Invented',b'Changed!')),peer_until=s.current())
    assert not f.visible


def test_restart_nonterminal_unknown_exact_committed_ack_only(tmp_path,monkeypatch,certificates):
    f,path,seal,s=setup_upload(tmp_path,monkeypatch,certificates);store=OriginalUploadStoreV1(s,OriginalIntakeFactoryV1(f.s));b=begin();r=store.apply(b,peer_until=s.current());c=chunk(b,r);r=store.apply(c,peer_until=s.current())
    restart=OriginalUploadStoreV1(s,OriginalIntakeFactoryV1(f.s));r=restart.apply(action(b,r),peer_until=s.current());assert r.state=='UNKNOWN'
    r=restart.apply(c,peer_until=s.current());assert r.state=='UNKNOWN' and r.received_bytes==len(PDF)
    with pytest.raises(PermissionError):restart.apply(action(b,r,'finalize'),peer_until=s.current())
    with pytest.raises(PermissionError):restart.apply(begin(),peer_until=s.current())
    assert not f.visible


@pytest.mark.parametrize('where',['chunk-receipt','finalize-close'])
def test_uncertain_write_or_sql_commit_never_redispatches(tmp_path,monkeypatch,certificates,where):
    f,path,seal,s=setup_upload(tmp_path,monkeypatch,certificates);store=OriginalUploadStoreV1(s,OriginalIntakeFactoryV1(f.s));b=begin();r=store.apply(b,peer_until=s.current())
    if where=='chunk-receipt':
        original=store._write
        def broken(parts,value):
            if parts[-1]=='chunk-0.json':raise OSError('invented disk uncertainty')
            return original(parts,value)
        monkeypatch.setattr(store,'_write',broken)
        with pytest.raises(OSError):store.apply(chunk(b,r),peer_until=s.current())
    else:
        r=store.apply(chunk(b,r),peer_until=s.current());f.finalize_close_error=True
        with pytest.raises(Exception):store.apply(action(b,r,'finalize'),peer_until=s.current())
    observed=store.apply(action(b,r),peer_until=s.current());assert observed.state=='UNKNOWN'
    attempts=sum(x=='finalize' for x in f.intake_calls)
    with pytest.raises(PermissionError):store.apply(action(b,r,'finalize'),peer_until=s.current())
    assert sum(x=='finalize' for x in f.intake_calls)==attempts


def test_cancel_out_of_order_missing_population_and_no_append_after_close(tmp_path,monkeypatch,certificates):
    f,path,seal,s=setup_upload(tmp_path,monkeypatch,certificates);store=OriginalUploadStoreV1(s,OriginalIntakeFactoryV1(f.s));b=begin();r=store.apply(b,peer_until=s.current())
    with pytest.raises(PermissionError):store.apply(action(b,r,'finalize'),peer_until=s.current())
    with pytest.raises((PermissionError,ValueError)):store.apply(chunk(b,r,index=1),peer_until=s.current())
    r=store.apply(action(b,r,'cancel'),peer_until=s.current());assert r.state=='cancelled' and not r.remote_stop_proven
    with pytest.raises(PermissionError):store.apply(chunk(b,r),peer_until=s.current())
    assert not f.visible


@pytest.mark.parametrize('patch',[{'revision':True},{'byte_count':26*1024*1024},{'schema_version':True},{'actor':'admin'},{'caller_deadline':'NaN'}])
def test_strict_closed_begin_refuses(patch):
    with pytest.raises(Exception):begin(**patch)


def test_scope_and_peer_header_refusals_have_no_byte_write(tmp_path,monkeypatch,certificates):
    with running_chunks(tmp_path,monkeypatch,certificates) as (f,s,server):
        b=begin()
        assert send(server,certificates,b,headers={'Range':'bytes=0-1'})[0]==503
        assert send(server,certificates,b,identity='other')[0]==503
        assert send(server,certificates,b,path='/v1/replacement/upload')[0]==503
        assert not (Path(s.profile.spool_root)/'uploads').exists()

def test_connection_timeouts_use_same_original_remaining_and_late_connect_cannot_proceed(tmp_path,monkeypatch,certificates):
    import time,psycopg
    f,path,seal,s=setup_upload(tmp_path,monkeypatch,certificates)
    factory=OriginalIntakeFactoryV1(f.s);b=begin();store=OriginalUploadStoreV1(s,factory)
    r=store.apply(b,peer_until=s.current());first=f.connection_options[-1]
    assert 1<=first['tcp_user_timeout']<=7000
    store.apply(chunk(b,r),peer_until=s.current())
    assert all(option['tcp_user_timeout']<=first['tcp_user_timeout'] for option in f.connection_options)
    assert len(set(f.deadlines))==1
    prior=psycopg.connect
    def late(*args,**kwargs):
        result=prior(*args,**kwargs)
        time.sleep(1.2)
        return result
    monkeypatch.setattr(psycopg,'connect',late)
    f.intake_calls.clear()
    deadline=now()+timedelta(seconds=1.1)
    with pytest.raises(PermissionError):factory.reserve_pdf_v1(store._q(b),caller_deadline=deadline)
    assert not f.intake_calls and not f.visible

def test_narrowed_sql_lease_never_renews_and_monotonic_expiry_precedes_sql(tmp_path,monkeypatch,certificates):
    import time
    f,path,seal,s=setup_upload(tmp_path,monkeypatch,certificates);store=OriginalUploadStoreV1(s,OriginalIntakeFactoryV1(f.s));b=begin();r=store.apply(b,peer_until=s.current())
    original=f.context['valid_until'];short=now()+timedelta(seconds=3);f.context['valid_until']=short.isoformat()
    narrowed=store.apply(action(b,r),peer_until=s.current());assert narrowed.valid_until<=short
    f.context['valid_until']=original
    later=store.apply(action(b,r),peer_until=s.current());assert later.valid_until==narrowed.valid_until
    store.windows[str(b.idempotency_key)]=time.monotonic()-1;calls=len(f.intake_calls)
    with pytest.raises(PermissionError):store.apply(chunk(b,r),peer_until=s.current())
    assert len(f.intake_calls)==calls


def test_protected_spool_lock_replacement_or_missing_initialization_cannot_reset_session(tmp_path,monkeypatch,certificates):
    f,path,seal,s=setup_upload(tmp_path,monkeypatch,certificates);store=OriginalUploadStoreV1(s,OriginalIntakeFactoryV1(f.s));b=begin();r=store.apply(b,peer_until=s.current())
    root=Path(s.profile.spool_root);(root/'upload.lock').rename(root/'retained-original.lock');(root/'upload.lock').write_bytes(b'');(root/'upload.lock').chmod(0o600)
    with pytest.raises(PermissionError):store.apply(action(b,r),peer_until=s.current())
    assert not f.visible


@pytest.mark.parametrize('change',[{'qualification':0},{'remote_stop_proven':0},{'observation_only':1},{'next_chunk_index':1}])
def test_public_observation_flags_and_chunk_accounting_are_strict(tmp_path,monkeypatch,certificates,change):
    f,path,seal,s=setup_upload(tmp_path,monkeypatch,certificates);store=OriginalUploadStoreV1(s,OriginalIntakeFactoryV1(f.s));r=store.apply(begin(),peer_until=s.current())
    with pytest.raises(Exception):UploadResponseV1.model_validate_json(json.dumps(r.model_dump(mode='json')|change))


def test_revoked_sql_scope_cannot_read_original_chunks_or_mark_restart_unknown(tmp_path,monkeypatch,certificates):
    f,path,seal,s=setup_upload(tmp_path,monkeypatch,certificates)
    store=OriginalUploadStoreV1(s,OriginalIntakeFactoryV1(f.s));b=begin()
    r=store.apply(b,peer_until=s.current());r=store.apply(chunk(b,r),peer_until=s.current())
    restart=OriginalUploadStoreV1(s,OriginalIntakeFactoryV1(f.s))
    original_read=restart._read_bytes
    def read(parts,limit):
        if parts[-1].endswith('.bin'):pytest.fail('revoked SQL scope reached original bytes')
        return original_read(parts,limit)
    def denied(*args,**kwargs):raise PermissionError('current SQL intake scope revoked')
    monkeypatch.setattr(restart,'_read_bytes',read)
    monkeypatch.setattr(restart.factory,'reserve_pdf_v1',denied)
    with pytest.raises(PermissionError,match='scope revoked'):
        restart.apply(action(b,r),peer_until=s.current())
    assert not (restart.root/'uploads'/str(b.idempotency_key)/'closed.json').exists()


def test_unrelated_retained_upload_inventory_never_rereads_original_bytes(tmp_path,monkeypatch,certificates):
    f,path,seal,s=setup_upload(tmp_path,monkeypatch,certificates)
    store=OriginalUploadStoreV1(s,OriginalIntakeFactoryV1(f.s));b=begin()
    r=store.apply(b,peer_until=s.current());r=store.apply(chunk(b,r),peer_until=s.current())
    store.apply(action(b,r,'cancel'),peer_until=s.current())
    original_read=store._read_bytes
    def read(parts,limit):
        if parts[-1].endswith('.bin'):pytest.fail('unrelated upload caused retained original read')
        return original_read(parts,limit)
    monkeypatch.setattr(store,'_read_bytes',read)
    fresh=store.apply(begin(),peer_until=s.current())
    assert fresh.state=='reserved' and fresh.received_bytes==0


def test_selected_original_bytes_are_bracketed_by_fresh_actual_intake_calls(tmp_path,monkeypatch,certificates):
    f,path,seal,s=setup_upload(tmp_path,monkeypatch,certificates)
    store=OriginalUploadStoreV1(s,OriginalIntakeFactoryV1(f.s));b=begin()
    r=store.apply(b,peer_until=s.current());r=store.apply(chunk(b,r),peer_until=s.current())
    initial=f.intake_calls.count('reserve');observed=[];original_read=store._read_bytes
    def read(parts,limit):
        if parts[-1].endswith('.bin'):
            observed.append(f.intake_calls.count('reserve'))
        return original_read(parts,limit)
    monkeypatch.setattr(store,'_read_bytes',read)
    result=store.apply(action(b,r),peer_until=s.current())
    assert result.received_bytes==len(PDF) and observed and min(observed)>initial
    assert f.intake_calls.count('reserve')>max(observed)
