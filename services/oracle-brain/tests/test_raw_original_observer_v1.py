"""New raw protocol with invented independent fixture keys, no actual issuer."""
import base64,hashlib,json,threading
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler
from uuid import uuid4
import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.original_qualification_v1 import RawOriginalPopulationV1
from oracle_brain.hosting.raw_original_observer_v1 import (
    DOMAIN,PURPOSE,RawOriginalObserverAdmissionV1,RawOriginalCurrentnessWitnessV1,
    RawOriginalObserverClientV1,RawOriginalCurrentnessConsumerV1,verify_raw_original_currentness_v1)
from oracle_brain.hosting.gateway import MutualTLSServer,GatewayDenied
from oracle_brain.hosting.custody import DurableNonceSequenceV2
from test_original_qualification_v1 import row
from test_parent_observer_v2 import provision
from test_purpose_transport import bound_tls,certificates,WORKER,SERVER


def case():
    now=datetime.now(timezone.utc);base=row()['raw_ref'];refs=[]
    for i in range(3):refs.append({**base,'source_id':str(uuid4()),'filename':f'invented-{i}.txt'})
    population=RawOriginalPopulationV1.model_validate_json(json.dumps(dict(population_id=str(uuid4()),
        workspace_id=base['workspace_id'],original_root_hash='1'*64,operation_registry_hash='2'*64,
        runtime_hash='3'*64,source_registry_hash='4'*64,raw_refs=refs,population_digest=digest({'raw_refs':refs}),
        issuer_actor=str(uuid4()),reviewer_actor=str(uuid4()),expires_at=(now+timedelta(seconds=60)).isoformat())))
    key=Ed25519PrivateKey.generate();public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    a=RawOriginalObserverAdmissionV1(purpose=PURPOSE,population=population,principal_id=uuid4(),
        observer_uri=SERVER,client_uri=WORKER,signing_public_key=public.hex(),signing_key_fingerprint=hashlib.sha256(public).hexdigest(),
        issuer_actor=uuid4(),reviewer_actor=uuid4(),minimum_sequence=12,max_age_seconds=5,expires_at=population.expires_at)
    w=RawOriginalCurrentnessWitnessV1(purpose=PURPOSE,admission_hash=digest(a.model_dump(mode='json')),
        challenge='a'*64,sequence=13,population=population,principal_id=a.principal_id,observer_uri=SERVER,client_uri=WORKER,
        checked_at=now,expires_at=now+timedelta(seconds=4),revoked=False)
    return key,a,w,now


def signed(key,w,domain=DOMAIN):
    body=w.model_dump(mode='json')
    return canonical_bytes({'witness':body,'signature':base64.b64encode(key.sign(domain+canonical_bytes(body))).decode()})


def check(key,a,w,baseline_now,**changes):
    args=dict(admission=a,trusted_admission_hash=digest(a.model_dump(mode='json')),expected_population=a.population,
        challenge='a'*64,previous_sequence=12,started_at=baseline_now,now=baseline_now+timedelta(milliseconds=10),elapsed_seconds=.01)
    args.update(changes);return verify_raw_original_currentness_v1(signed(key,w),**args)


def test_exact_byte_only_three_original_population_signature():
    k,a,w,now=case();result=check(k,a,w,now)
    assert len(result.population.raw_refs)==3 and not hasattr(result.population,'source_refs')
    assert b'"reading_sha256"' not in signed(k,w)

@pytest.mark.parametrize('damage',['key','domain','challenge','replay','stale','future','root','population_id','operation_registry',
    'runtime','omitted_third','reorder','principal','uri','revoked','overlong','schema_bool'])
def test_raw_observer_rejects_cross_operation_scope_freshness_and_qualified_domain(damage):
    k,a,w,now=case();args={}
    if damage=='key':k=Ed25519PrivateKey.generate()
    elif damage=='domain':
        from oracle_brain.hosting.parent_observer_v2 import DOMAIN as OLD
        with pytest.raises(InvalidSignature):verify_raw_original_currentness_v1(signed(k,w,OLD),admission=a,
            trusted_admission_hash=digest(a.model_dump(mode='json')),expected_population=a.population,challenge='a'*64,
            previous_sequence=12,started_at=now,now=now+timedelta(milliseconds=10),elapsed_seconds=.01)
        return
    elif damage=='challenge':args['challenge']='b'*64
    elif damage=='replay':args['previous_sequence']=13
    elif damage=='stale':args.update(now=now+timedelta(seconds=6),elapsed_seconds=6)
    elif damage=='future':w=w.model_copy(update={'checked_at':now+timedelta(seconds=1)})
    elif damage in {'root','population_id','operation_registry','runtime','omitted_third','reorder'}:
        key={'root':'original_root_hash','operation_registry':'operation_registry_hash','runtime':'runtime_hash'}.get(damage,damage)
        value=uuid4() if damage=='population_id' else 'f'*64
        if damage=='omitted_third':key,value='raw_refs',w.population.raw_refs[:-1]
        if damage=='reorder':key,value='raw_refs',tuple(reversed(w.population.raw_refs))
        w=w.model_copy(update={'population':w.population.model_copy(update={key:value})})
    elif damage=='principal':w=w.model_copy(update={'principal_id':uuid4()})
    elif damage=='uri':w=w.model_copy(update={'client_uri':'spiffe://oracle/foreign'})
    elif damage=='revoked':w=w.model_copy(update={'revoked':True})
    elif damage=='overlong':w=w.model_copy(update={'expires_at':now+timedelta(seconds=6)})
    else:w=w.model_copy(update={'schema_version':True})
    with pytest.raises((PermissionError,ValueError,InvalidSignature)):check(k,a,w,now,**args)


def test_actual_raw_mtls_challenge_and_restart_replay(bound_tls,tmp_path):
    tls,binding=bound_tls;k,a,_,now=case();seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            uris=[v for kind,v in self.connection.getpeercert().get('subjectAltName',()) if kind=='URI']
            if uris!=[WORKER]:self.send_error(403);return
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert self.path=='/v1/originals/parent/current' and set(request)=={'schema_version','purpose','challenge'}
            assert request['purpose']==PURPOSE and type(request['schema_version']) is int and request['schema_version']==1
            seen.append(request);at=datetime.now(timezone.utc)
            w=RawOriginalCurrentnessWitnessV1(purpose=PURPOSE,admission_hash=digest(a.model_dump(mode='json')),
                challenge=request['challenge'],sequence=13,population=a.population,principal_id=a.principal_id,
                observer_uri=SERVER,client_uri=WORKER,checked_at=at,expires_at=min(at+timedelta(seconds=4),a.expires_at),revoked=False)
            raw=signed(k,w);self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=MutualTLSServer(('127.0.0.1',0),Handler,tls=tls)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    spool=tmp_path/'raw-replay';spool.mkdir(mode=0o700)
    replay,pins=provision(spool,a,namespace='raw-original-v1')
    try:
        client=RawOriginalObserverClientV1(binding(server.server_port))
        c=RawOriginalCurrentnessConsumerV1(admission=a,trusted_admission_hash=pins['appointment_hash'],transport=client,replay=replay)
        assert c.current(a.population).sequence==13
        assert len(seen)==1 and replay._read()['sequence']==13
        c.replay=DurableNonceSequenceV2(spool,**pins)
        with pytest.raises(PermissionError):c.current(a.population)
        assert len(seen)==2 and len(list(spool.glob('raw-original-v1-nonce-*')))==2
        with pytest.raises(GatewayDenied):RawOriginalObserverClientV1(binding(server.server_port,uri='spiffe://oracle/wrong')).fetch_current('a'*64)
        assert len(seen)==2
        with pytest.raises(GatewayDenied):RawOriginalObserverClientV1(binding(server.server_port,client='other')).fetch_current('b'*64)
        assert len(seen)==2
    finally:server.shutdown();server.server_close();thread.join(2)


@pytest.fixture
def observed_exchange(bound_tls,tmp_path):
    """Actual invented TLS/signature/replay; no SQL or original bytes."""
    import fcntl,os
    tls,binding=bound_tls;k,a,_,_=case()
    from test_raw_original_views_v1 import pdf_fixture
    _,pdf_ref=pdf_fixture()
    refs=tuple(pdf_ref.model_copy(update={'workspace_id':a.population.workspace_id,'source_id':ref.source_id,
        'filename':f'invented-observed-{index}.pdf'}) for index,ref in enumerate(a.population.raw_refs))
    population=a.population.model_copy(update={'raw_refs':refs,
        'population_digest':digest({'raw_refs':[ref.model_dump(mode='json') for ref in refs]})})
    a=RawOriginalObserverAdmissionV1.model_validate(a.model_dump(mode='python')|{'population':population})
    state={'raw':[],'requests':[],'damage':None,'network_hook':lambda:None}
    spool=tmp_path/'observed-raw-replay';spool.mkdir(mode=0o700)
    replay,pins=provision(spool,a,namespace='raw-evidence-v1')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            assert self.path=='/v1/originals/parent/current'
            assert [v for kind,v in self.connection.getpeercert().get('subjectAltName',()) if kind=='URI']==[WORKER]
            # Acquiring the ACTUAL replay lock in the server proves it isn't
            # held across the client TLS exchange.
            fd=os.open(replay.lock_path,os.O_RDWR)
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            finally:os.close(fd)
            state['network_hook']()
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])));state['requests'].append(request)
            at=datetime.now(timezone.utc);sequence=12+len(state['requests'])
            witness=RawOriginalCurrentnessWitnessV1(purpose=PURPOSE,admission_hash=pins['appointment_hash'],
                challenge=request['challenge'],sequence=sequence,population=a.population,principal_id=a.principal_id,
                observer_uri=SERVER,client_uri=WORKER,checked_at=at,
                expires_at=min(at+timedelta(seconds=4),a.expires_at),revoked=False)
            if state['damage']=='revoked':witness=witness.model_copy(update={'revoked':True})
            elif state['damage']=='expired':witness=witness.model_copy(update={'expires_at':at-timedelta(seconds=1)})
            elif state['damage']=='foreign':witness=witness.model_copy(update={'principal_id':uuid4()})
            elif state['damage']=='replay':witness=witness.model_copy(update={'sequence':12})
            raw=b' \n'+signed(k,witness)+b'\n'  # Preserve original noncanonical envelope bytes.
            state['raw'].append(raw);self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=MutualTLSServer(('127.0.0.1',0),Handler,tls=tls)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    client=RawOriginalObserverClientV1(binding(server.server_port))
    consumer=RawOriginalCurrentnessConsumerV1(admission=a,trusted_admission_hash=pins['appointment_hash'],transport=client,replay=replay)
    try:yield consumer,state,pins
    finally:server.shutdown();server.server_close();thread.join(2)


def test_observed_actual_signed_tls_envelope_is_exact_and_follows_durable_advance(observed_exchange):
    from dataclasses import FrozenInstanceError
    c,state,pins=observed_exchange
    observed=c.observed_current(c.admission.population)
    assert observed.raw_envelope==state['raw'][0] and observed.raw_envelope.startswith(b' \n')
    assert observed.challenge==state['requests'][0]['challenge']==observed.witness.challenge
    assert observed.previous_sequence==12 and observed.witness.sequence==13
    assert observed.started_at<=observed.witness.checked_at<=observed.observed_at<observed.witness.expires_at
    assert type(observed.elapsed_seconds) is float and 0<=observed.elapsed_seconds<=5
    assert observed.envelope_sha256==hashlib.sha256(state['raw'][0]).hexdigest()
    assert observed.witness_bytes==canonical_bytes(json.loads(state['raw'][0])['witness'])
    assert c.replay._read()['sequence']==13
    with pytest.raises(FrozenInstanceError):observed.raw_envelope=b'changed'
    # Old current() interface still delegates and returns only the witness.
    assert c.current(c.admission.population).sequence==14


@pytest.mark.parametrize('damage',['revoked','expired','foreign','replay'])
def test_observed_tls_refusal_never_exposes_evidence_or_advances_highwater(observed_exchange,damage):
    c,state,_=observed_exchange;state['damage']=damage
    with pytest.raises(PermissionError):c.observed_current(c.admission.population)
    assert len(state['requests'])==1 and c.replay._read()['sequence']==12


def test_observed_evidence_not_returned_if_replay_commit_reports_failure(observed_exchange,monkeypatch):
    c,state,_=observed_exchange;original=c.replay.advance
    def failed(challenge,sequence,*,verify):
        original(challenge,sequence,verify=verify)
        raise PermissionError('invented uncertain replay acknowledgement')
    monkeypatch.setattr(c.replay,'advance',failed)
    with pytest.raises(PermissionError,match='uncertain replay'):c.observed_current(c.admission.population)
    assert c.replay._read()['sequence']==13 and len(state['requests'])==1


def test_observed_exchange_revalidates_current_pins_after_network(observed_exchange):
    c,state,_=observed_exchange
    state['network_hook']=lambda:setattr(c,'admission_hash','0'*64)
    with pytest.raises(PermissionError):c.observed_current(c.admission.population)
    assert len(state['requests'])==1 and c.replay._read()['sequence']==13


def test_observed_immutable_record_rejects_bytes_signature_and_observation_tampering(observed_exchange):
    from dataclasses import replace
    c,state,_=observed_exchange;observed=c.observed_current(c.admission.population)
    bad=json.loads(observed.raw_envelope);bad['signature']=base64.b64encode(b'x'*64).decode()
    for changes in ({'raw_envelope':canonical_bytes(bad)},{'raw_envelope':b''},
        {'challenge':'b'*64},{'previous_sequence':True},{'previous_sequence':13},
        {'elapsed_seconds':float('nan')},{'elapsed_seconds':True},{'elapsed_seconds':6.},
        {'started_at':observed.started_at.replace(tzinfo=None)},
        {'observed_at':observed.started_at-timedelta(seconds=1)},
        {'witness':observed.witness.model_copy(update={'principal_id':uuid4()})}):
        with pytest.raises((PermissionError,ValueError,InvalidSignature)):replace(observed,**changes)


def test_replay_advance_delay_cannot_return_now_expired_evidence(observed_exchange,monkeypatch):
    c,state,_=observed_exchange;advance=c.replay.advance;finished=[]
    def committed(challenge,sequence,*,verify):
        advance(challenge,sequence,verify=verify);finished.append(True)
    monkeypatch.setattr(c.replay,'advance',committed)
    c.clock=lambda:datetime.now(timezone.utc)+(timedelta(seconds=10) if finished else timedelta(0))
    with pytest.raises(PermissionError,match='expired before return'):c.observed_current(c.admission.population)
    assert c.replay._read()['sequence']==13 and len(state['requests'])==1
