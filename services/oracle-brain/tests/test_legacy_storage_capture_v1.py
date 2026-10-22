"""Capture boundary failures; recording boundaries are not SQL/Storage rights proof."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import base64
import json
import threading

import pytest

from oracle_brain.migration.legacy_storage_capture_v1 import (
    LegacyDocumentCaptureV1, LegacyCaptureUnavailable, _CaptureWireUnknownV1,
    _json_object_v1,
)


@pytest.fixture
def interrupted(monkeypatch):
    selected=uuid4(); owner=object.__new__(LegacyDocumentCaptureV1)
    owner.profile=SimpleNamespace(workspace_id=uuid4())
    owner._slot=threading.Lock(); owner._active=None
    state=SimpleNamespace(expired=False,writes=[],checks=0)
    owner.reader=SimpleNamespace(profile=SimpleNamespace(source_scope=SimpleNamespace(document_ids=(selected,))),
        authority=SimpleNamespace(source_context_v1=lambda **_:None),
        _pass=lambda _:('projection',[],[(selected,None,None,'application/pdf','documents','a.pdf')]))
    def current(_):
        state.checks+=1
        if state.expired:raise PermissionError('original elapsed')
        return 1
    def auth(_):
        raise _CaptureWireUnknownV1(b'HTTP/1.1 200 OK\r\n')
    def put(key,data):
        state.writes.append((key,data))
        if getattr(state,'expire_during_write',False):state.expired=True
    monkeypatch.setattr(owner,'_time',current)
    monkeypatch.setattr(owner,'_auth',auth)
    monkeypatch.setattr(owner,'_put',put)
    return owner,state,selected


def test_interrupted_prefix_retained_only_inside_original_window(interrupted):
    owner,state,selected=interrupted
    with pytest.raises(LegacyCaptureUnavailable):
        owner.capture_document_v1(selected,caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=5))
    assert len(state.writes)==1 and state.writes[0][1]==b'HTTP/1.1 200 OK\r\n'
    assert state.writes[0][0].endswith('/UNKNOWN.wire')
    assert owner._active is None and owner._slot.acquire(False)
    owner._slot.release()


def test_expired_partial_response_cannot_start_private_write(interrupted,monkeypatch):
    owner,state,selected=interrupted
    def auth(_):
        state.expired=True
        raise _CaptureWireUnknownV1(b'actual partial response')
    monkeypatch.setattr(owner,'_auth',auth)
    with pytest.raises(PermissionError,match='elapsed'):
        owner.capture_document_v1(selected,caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=5))
    assert state.writes==[] and owner._active is None
    assert owner._slot.acquire(False);owner._slot.release()


def test_already_running_private_write_finishing_late_never_returns_success(interrupted):
    owner,state,selected=interrupted;state.expire_during_write=True
    with pytest.raises(PermissionError,match='elapsed'):
        owner.capture_document_v1(selected,caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=5))
    assert len(state.writes)==1 and owner._active is None


def test_actual_auth_identity_checked_before_decoding_any_token(monkeypatch):
    owner=object.__new__(LegacyDocumentCaptureV1);subject=uuid4()
    owner.profile=SimpleNamespace(auth_subject=subject)
    monkeypatch.setattr(owner,'_credentials',lambda:('malformed.token.payload','fixture-key'))
    monkeypatch.setattr(owner,'_exchange',lambda *args:dict(status=200,body=json.dumps(
        dict(id=str(uuid4()),role='authenticated',is_anonymous=False)).encode()))
    with pytest.raises(PermissionError,match='subject/role'):
        owner._auth(datetime.now(timezone.utc)+timedelta(seconds=1))


@pytest.mark.parametrize('role,anonymous',[('service_role',False),('admin',False),('anon',False),('authenticated',True),('authenticated',None)])
def test_server_role_and_nonanonymous_required(monkeypatch,role,anonymous):
    owner=object.__new__(LegacyDocumentCaptureV1);subject=uuid4()
    owner.profile=SimpleNamespace(auth_subject=subject)
    monkeypatch.setattr(owner,'_credentials',lambda:('malformed.token.payload','fixture-key'))
    monkeypatch.setattr(owner,'_exchange',lambda *args:dict(status=200,body=json.dumps(
        dict(id=str(subject),role=role,is_anonymous=anonymous)).encode()))
    with pytest.raises(PermissionError,match='subject/role'):
        owner._auth(datetime.now(timezone.utc)+timedelta(seconds=1))


def test_token_subject_and_role_never_replace_actual_server_identity(monkeypatch):
    owner=object.__new__(LegacyDocumentCaptureV1);subject=uuid4()
    owner.profile=SimpleNamespace(auth_subject=subject)
    claims=dict(sub=str(uuid4()),role='service_role',exp=int(datetime.now(timezone.utc).timestamp())+60)
    payload=base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
    monkeypatch.setattr(owner,'_credentials',lambda:('fixture.'+payload+'.fixture','fixture-key'))
    actual=dict(status=200,body=json.dumps(dict(id=str(subject),role='authenticated',is_anonymous=False)).encode())
    monkeypatch.setattr(owner,'_exchange',lambda *args:actual)
    assert owner._auth(datetime.now(timezone.utc)+timedelta(seconds=1)) is actual


@pytest.mark.parametrize('body',[b'{"id":1,"id":2}',b'{"value":NaN}',b'[]',b''])
def test_actual_auth_json_is_bounded_and_unambiguous(body):
    with pytest.raises((ValueError,PermissionError)):_json_object_v1(body,65536)

@pytest.fixture
def invented_capture_peer_v1(tmp_path,monkeypatch):
    """Owned loopback TLS peer only; source-current boundary remains recording."""
    import hashlib, socket, ssl, time
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID
    from oracle_brain.operating_model.protected_inputs_v1 import ProtectedInputV1
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    now=datetime.now(timezone.utc);key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'owned invented capture fixture')])
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('a'*20+'.supabase.co'),x509.DNSName('a'*20+'.storage.supabase.co')]),False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),False).sign(key,hashes.SHA256()))
    pem=cert.public_bytes(serialization.Encoding.PEM);ca=tmp_path/'ca';ca.write_bytes(pem);ca.chmod(0o600)
    private=tmp_path/'key';private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));private.chmod(0o600)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(ca,private)
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(4);listener.settimeout(.1)
    state=SimpleNamespace(response=b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nPDF',requests=[],errors=[],delay=0,source_checks=0,stop=False)
    def serve():
        while not state.stop:
            try:raw,_=listener.accept()
            except socket.timeout:continue
            except OSError:return
            try:
                with context.wrap_socket(raw,server_side=True) as secure:
                    secure.settimeout(2);request=bytearray()
                    while not request.endswith(b'\r\n\r\n') and len(request)<=65536:
                        chunk=secure.recv(1)
                        if not chunk:break
                        request.extend(chunk)
                    state.requests.append(bytes(request))
                    if state.delay:time.sleep(state.delay)
                    response=state.response(bytes(request)) if callable(state.response) else state.response
                    secure.sendall(response)
                    try:secure.unwrap().close()
                    except (OSError,ssl.SSLError):pass
            except (OSError,ssl.SSLError) as error:state.errors.append(type(error).__name__)
            finally:raw.close()
    thread=threading.Thread(target=serve,name='owned-current-capture-fixture');thread.start()
    owner=object.__new__(LegacyDocumentCaptureV1)
    pin=ProtectedInputV1.model_validate(dict(schema_version=1,path=str(ca),sha256=hashlib.sha256(pem).hexdigest()))
    until=now+timedelta(seconds=20)
    owner.profile=SimpleNamespace(project_ref='a'*20,auth_address='127.0.0.1',storage_address='127.0.0.1',
        auth_port=listener.getsockname()[1],storage_port=listener.getsockname()[1],auth_ca=pin,storage_ca=pin,
        auth_server_der_sha256=hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest(),
        storage_server_der_sha256=hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest(),expires_at=until,original_horizon=until)
    monkeypatch.setattr(owner,'_time',lambda deadline:owner._remaining(deadline))
    def source(deadline):state.source_checks+=1;owner._remaining(deadline)
    monkeypatch.setattr(owner,'_source_current',source)
    try:
        yield owner,state
    finally:
        state.stop=True;listener.close();thread.join(3)
        assert not thread.is_alive()


@pytest.fixture
def actual_capture_tls(invented_capture_peer_v1):
    import time
    from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
    with _request_fence_v1(time.monotonic()+10):
        yield invented_capture_peer_v1


def test_actual_tls_response_full_wire_and_source_check_before_request(actual_capture_tls):
    owner,state=actual_capture_tls
    result=owner._exchange('storage','GET','/storage/v1/s3/invented/a.pdf',{},datetime.now(timezone.utc)+timedelta(seconds=2),100)
    assert result['body']==b'PDF' and result['wire']==state.response and result['status']==200
    assert len(state.requests)==1 and state.source_checks==1
    assert state.requests[0].startswith(b'GET /storage/v1/s3/invented/a.pdf HTTP/1.1\r\n')


@pytest.mark.parametrize('response',[
    b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\nContent-Length: 3\r\n\r\nPDF',
    b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\nContent-Encoding: gzip\r\n\r\nPDF',
    b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nPD',
    b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nPDFEXTRA',
    b'HTTP/1.1 302 Found\r\nLocation: https://elsewhere.invalid/\r\n\r\n',
])
def test_actual_tls_ambiguous_truncated_encoded_or_extra_wire_no_retry(actual_capture_tls,response):
    owner,state=actual_capture_tls;state.response=response
    with pytest.raises(_CaptureWireUnknownV1):
        owner._exchange('storage','GET','/storage/v1/s3/invented/a.pdf',{},datetime.now(timezone.utc)+timedelta(seconds=2),100)
    assert len(state.requests)==1


def test_actual_tls_original_absolute_deadline_closes_socket_without_retry(actual_capture_tls):
    import time
    owner,state=actual_capture_tls;state.delay=.3;start=time.monotonic()
    with pytest.raises(_CaptureWireUnknownV1):
        owner._exchange('auth','GET','/auth/v1/user',{},datetime.now(timezone.utc)+timedelta(seconds=.1),65536)
    assert time.monotonic()-start<.6 and len(state.requests)==1
    assert not any(t.name.startswith('Thread-') and t.is_alive() and isinstance(t,threading.Timer) for t in threading.enumerate())


def test_actual_tls_wrong_der_never_transmits_http(actual_capture_tls):
    owner,state=actual_capture_tls;owner.profile.storage_server_der_sha256='0'*64
    with pytest.raises(PermissionError,match='DER'):
        owner._exchange('storage','GET','/storage/v1/s3/invented/a.pdf',{},datetime.now(timezone.utc)+timedelta(seconds=2),100)
    assert state.source_checks==0 and not any(state.requests)



def invented_s3_auth_responder_v1(*,token,anonymous,subject,data,etag,mode):
    import hashlib,hmac
    operations=[];phase=0;terminal=False
    expected=(('GET','/auth/v1/user'),('HEAD','/storage/v1/s3/invented/a%20file.pdf'),
        ('GET','/storage/v1/s3/invented/a%20file.pdf'),('HEAD','/storage/v1/s3/invented/a%20file.pdf'),('GET','/auth/v1/user'))
    def serve(request):
        nonlocal phase,terminal
        head=request.decode('ascii').split('\r\n');method,path,_=head[0].split(' ')
        headers=dict(line.split(': ',1) for line in head[1:] if line)
        assert not terminal and (method,path)==expected[phase], 'exact current capture request order required'
        operations.append((method,path))
        if path=='/auth/v1/user':
            assert headers['authorization']=='Bearer '+token and headers['apikey']==anonymous
            returned_subject=uuid4() if mode=='wrong-final-auth' and phase==4 else subject
            if phase==4:
                terminal=mode=='wrong-final-auth'
                if not terminal:phase=0  # Only a complete successful five-request cycle resets.
            else:phase+=1
            body=json.dumps(dict(id=str(returned_subject),role='authenticated',is_anonymous=False)).encode()
            return b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body
        assert path=='/storage/v1/s3/invented/a%20file.pdf'
        algorithm,raw=headers['authorization'].split(' ',1)
        values=dict(piece.split('=',1) for piece in raw.split(','));signed=values['SignedHeaders']
        assert algorithm=='AWS4-HMAC-SHA256' and headers['x-amz-security-token']==token
        canonical='\n'.join((method,path,'',''.join(k+':'+headers[k]+'\n' for k in signed.split(';')),signed,hashlib.sha256(b'').hexdigest()))
        scope=values['Credential'].split('/')[1:];key=('AWS4'+anonymous).encode()
        for value in scope:key=hmac.digest(key,value.encode(),'sha256')
        message='\n'.join((algorithm,headers['x-amz-date'],'/'.join(scope),hashlib.sha256(canonical.encode()).hexdigest()))
        assert values['Signature']==hmac.digest(key,message.encode(),'sha256').hex()
        if phase in (2,3):assert headers['if-match']==etag
        else:assert 'if-match' not in headers, 'fresh initial HEAD cannot reuse prior capture condition'
        if mode=='precondition' and method=='GET':
            terminal=True
            return b'HTTP/1.1 412 Precondition Failed\r\nContent-Length: 0\r\n\r\n'
        media=b'text/plain' if mode=='unsupported' else b'application/pdf'
        actual_etag='"changed-current"' if mode=='wrong-final-etag' and phase==3 else etag
        length=25*1024*1024+1 if mode=='overflow' else len(data)
        response=b'HTTP/1.1 200 OK\r\nContent-Type: '+media+b'\r\nETag: '+actual_etag.encode()+b'\r\nContent-Length: '+str(length).encode()+b'\r\n\r\n'
        terminal=mode in ('unsupported','overflow') or mode=='wrong-final-etag' and phase==3
        phase+=1
        return response+(data if method=='GET' else b'')
    return serve,operations


@pytest.mark.parametrize('mode',['ok','precondition','unsupported','overflow','wrong-final-etag','wrong-final-auth','source-withdraw'])
def test_actual_auth_S3_TLS_current_capture_private_readback_and_independent_signature(actual_capture_tls,tmp_path,monkeypatch,mode):
    import hashlib,hmac,os
    from oracle_brain.operating_model.protected_inputs_v1 import ProtectedInputV1
    owner,state=actual_capture_tls;document=uuid4();subject=uuid4();workspace=uuid4()
    data=b'%PDF-1.4\nActual invented current capture bytes\n%%EOF\n'
    etag='"opaque-current-object-not-body-sha"'
    now=datetime.now(timezone.utc)
    claims=base64.urlsafe_b64encode(json.dumps(dict(exp=int(now.timestamp())+60,sub='ignored-local-claim',role='ignored')).encode()).decode().rstrip('=')
    token='invented.'+claims+'.fixture';anonymous='invented.anon.fixture'
    def pin(name,value):
        path=tmp_path/name;path.write_bytes(value.encode());path.chmod(0o600)
        return ProtectedInputV1.model_validate(dict(schema_version=1,path=str(path),sha256=hashlib.sha256(value.encode()).hexdigest()))
    root=tmp_path/'private';root.mkdir(mode=0o700);info=root.stat()
    vars(owner.profile).update(workspace_id=workspace,auth_subject=subject,session_token=pin('ordinary-session',token),
        anonymous_key=pin('public-fixture-anonymous',anonymous),region='us-east-1',max_document_bytes=25*1024*1024,
        max_aggregate_bytes=64*1024*1024,storage_root=str(root),storage_device=info.st_dev,storage_inode=info.st_ino,storage_uid=os.getuid())
    owner._slot=threading.Lock();owner._active=None;owner.sha256='a'*64
    source_events=[]
    def source_pass(deadline):
        source_events.append('closed-recording-source-pass')
        return ('b'*64,[],[(document,None,None,'application/pdf','invented','a file.pdf')])
    owner.reader=SimpleNamespace(profile=SimpleNamespace(source_scope=SimpleNamespace(document_ids=(document,))),
        authority=SimpleNamespace(source_context_v1=lambda **_:source_events.append('closed-recording-root-pass')),
        _pass=source_pass)
    state.response,operations=invented_s3_auth_responder_v1(token=token,anonymous=anonymous,subject=subject,data=data,etag=etag,mode=mode)
    deadline=datetime.now(timezone.utc)+timedelta(seconds=3)
    if mode=='source-withdraw':
        def source_current(deadline):
            if len(operations)>=3:raise PermissionError('recording source withdrawal')
            state.source_checks+=1;owner._remaining(deadline)
        monkeypatch.setattr(owner,'_source_current',source_current)
    if mode!='ok':
        expected=PermissionError if mode in ('wrong-final-auth','source-withdraw') else LegacyCaptureUnavailable
        with pytest.raises(expected):owner.capture_document_v1(document,caller_deadline=deadline)
        assert not list(root.rglob('*'))  # No accepted capture/body/receipt after refusal.
        expected_requests={'precondition':3,'unsupported':2,'overflow':2,'wrong-final-etag':4,'wrong-final-auth':5,'source-withdraw':3}
        assert len(state.requests)==expected_requests[mode]
        # Direct fixture-only audit, no HTTP dispatch or capture retry: a failed
        # cycle cannot accept another initial Auth and conceal its uncertainty.
        count=len(operations)
        with pytest.raises(AssertionError,match='request order'):state.response(state.requests[0])
        assert len(operations)==count
        assert owner._active is None and owner._slot.acquire(False);owner._slot.release()
        return
    result=owner.capture_document_v1(document,caller_deadline=deadline)
    assert result.data==data and result.original_sha256==hashlib.sha256(data).hexdigest()
    assert result.historical_original_proven is False and result.qualification is False
    assert [op[0] for op in operations]==['GET','HEAD','GET','HEAD','GET']
    assert len(state.requests)==5 and state.source_checks==7  # prewrite each, pre-custody and post-custody currentness
    assert source_events and not state.errors
    assert len(result.capture['observations'])==5
    assert (root/result.capture['private_body_key']).read_bytes()==data
    receipt=(root/result.capture['private_receipt_key']).read_bytes()
    assert hashlib.sha256(receipt).hexdigest()==result.capture['receipt_sha256']
    assert len(receipt)==result.capture['receipt_byte_count']
    assert owner._active is None and owner._slot.acquire(False);owner._slot.release()
    # A second independent capture uses the SAME original test deadline. Its
    # initial HEAD has no inherited If-Match, while both conditional reads are
    # independently signature-checked by the same actual TLS responder.
    again=owner.capture_document_v1(document,caller_deadline=deadline)
    assert len(state.requests)==10 and not state.errors
    assert [op[0] for op in operations]==['GET','HEAD','GET','HEAD','GET']*2
    assert again.data==result.data and again.original_sha256==result.original_sha256
    assert again.capture['capture_id']!=result.capture['capture_id']
    assert (root/result.capture['private_receipt_key']).read_bytes()==receipt
    assert owner._active is None and owner._slot.acquire(False);owner._slot.release()


def test_invented_capture_responder_never_resets_on_wrong_order():
    responder,operations=invented_s3_auth_responder_v1(token='fixture',anonymous='fixture-public',subject=uuid4(),data=b'fixture',etag='"opaque"',mode='ok')
    with pytest.raises(AssertionError,match='request order'):
        responder(b'HEAD /storage/v1/s3/invented/a%20file.pdf HTTP/1.1\r\n\r\n')
    auth=b'GET /auth/v1/user HTTP/1.1\r\nauthorization: Bearer fixture\r\napikey: fixture-public\r\n\r\n'
    responder(auth)
    with pytest.raises(AssertionError,match='request order'):responder(auth)
    assert operations==[('GET','/auth/v1/user')]


def test_real_currentness_method_refuses_changed_source_projection_before_bytes(interrupted,monkeypatch):
    owner,state,selected=interrupted;owner._active={'source_projection':'before'}
    # Exercise the actual currentness owner, not the fixture's I/O recording.
    with pytest.raises(PermissionError,match='changed'):
        LegacyDocumentCaptureV1._source_current(owner,datetime.now(timezone.utc)+timedelta(seconds=2))
    assert state.writes==[]


def test_actual_currentness_root_refusal_cannot_become_per_document_quarantine(interrupted,monkeypatch):
    owner,state,selected=interrupted
    def withdrawn(**_):raise PermissionError('actual root withdrawn')
    owner.reader.authority.source_context_v1=withdrawn
    with pytest.raises(PermissionError,match='withdrawn'):
        owner.capture_document_v1(selected,caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=2))
    assert state.writes==[] and owner._active is None
