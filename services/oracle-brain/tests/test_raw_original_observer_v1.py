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
