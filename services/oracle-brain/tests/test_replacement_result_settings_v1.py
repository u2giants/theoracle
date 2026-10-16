"""Metadata and controlled IO ordering only; actual SQL/mTLS proof is separate."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from oracle_brain.hosting import replacement_result_settings_v1 as m

def config():
    now=datetime.now(timezone.utc);ids=[uuid4() for _ in range(8)]
    data=dict(schema_version=1,purpose='replacement-protected-result-v1',principal_id=ids[0],workspace_id=ids[1],
        journey_id=ids[2],population_sha256='a'*64,original_root_hash='b'*64,executor_login='fixture_executor',
        executor_runtime_hash='c'*64,executor_issuer_actor=ids[3],executor_reviewer_actor=ids[4],model_id=ids[5],
        model_version=1,model_content_hash='d'*64,projection_digest='e'*64,ack_event_id=ids[6],
        summary_artifact_id=ids[7],summary_version=1,summary_content_hash='f'*64,workflow_id='fixture-workflow',
        listen_host='127.0.0.1',listen_port=8443,client_uri='spiffe://oracle/fixture/requester',client_certificate_sha256='1'*64,
        server_uri='spiffe://oracle/fixture/result',nonce_root='/fixture/nonces',issuer_actor=uuid4(),reviewer_actor=uuid4(),
        valid_from=now,expires_at=now+timedelta(seconds=60),original_horizon=now+timedelta(seconds=90))
    for name in ('executor_config','executor_appointment','server_certificate','server_key','client_ca'):
        data[name+'_file']='/fixture/'+name;data[name+'_sha256']='2'*64
    return m.ProtectedReplacementResultConfigV1.model_validate(data)

def test_fixed_result_startup_no_provider_raw_hmac_or_body_identity():
    c=config();assert c.client_uri!=c.server_uri
    for update in ({'schema_version':True},{'schema_version':1.0},{'principal_id':c.issuer_actor},
        {'reviewer_actor':c.issuer_actor},{'client_uri':c.server_uri},{'nonce_root':'relative'},
        {'server_key_file':c.executor_config_file},{'raw_context_file':'/private'},
        {'provider_key_file':'/private'},{'hmac_key_file':'/private'},
        {'expires_at':c.original_horizon+timedelta(seconds=1)}):
        with pytest.raises(Exception):m.ProtectedReplacementResultConfigV1.model_validate({**c.model_dump(),**update})

def test_missing_external_pins_refuses_before_any_file(monkeypatch):
    def deny(*a,**k):raise AssertionError('private file read before external pins')
    monkeypatch.setattr(m,'_worker_json',deny)
    for supplied in ('',None,True,'untrusted'):
        with pytest.raises(PermissionError,match='external protected result pins'):
            m.load_protected_replacement_result_settings_v1('/absent',supplied,appointment_path='/absent',
                expected_appointment_sha256='a'*64,issuer_actor=uuid4(),reviewer_actor=uuid4())

@pytest.mark.parametrize('reason',['pending','cancelled','revoked','foreign-run'])
def test_controlled_current_run_refusal_precedes_all_qualified_and_graph_bytes(monkeypatch,reason):
    c=config();a=m.ProtectedReplacementResultAppointmentV1.model_validate(dict(schema_version=1,
        purpose=c.purpose,config_sha256='a'*64,principal_id=c.principal_id,workspace_id=c.workspace_id,
        journey_id=c.journey_id,executor_config_sha256=c.executor_config_sha256,
        executor_appointment_sha256=c.executor_appointment_sha256,issuer_actor=c.issuer_actor,
        reviewer_actor=c.reviewer_actor,valid_from=c.valid_from,expires_at=c.expires_at))
    events=[]
    monkeypatch.setattr(m,'_worker_json',lambda p,h,t:c if t is type(c) else a)
    def bootstrap(*args,**kwargs):events.append('only-sql-bootstrap');return (object(),None,object(),object())
    def current(*args):events.append('actual-run-boundary');raise PermissionError(reason)
    def forbidden(*args,**kwargs):raise AssertionError('qualified/graph loader before current run')
    monkeypatch.setattr(m,'_executor_bootstrap_v3',bootstrap)
    monkeypatch.setattr(m,'_current_registered_target',current)
    monkeypatch.setattr(m,'load_paid_executor_settings_v3',forbidden)
    with pytest.raises(PermissionError,match=reason):
        m.load_protected_replacement_result_settings_v1('/fixture/config','a'*64,
            appointment_path='/fixture/appointment',expected_appointment_sha256='b'*64,
            issuer_actor=c.issuer_actor,reviewer_actor=c.reviewer_actor)
    assert events==['only-sql-bootstrap','actual-run-boundary']

def test_fixed_result_service_rejects_foreign_settings_before_private_io():
    from oracle_brain.hosting.replacement_result_service_v1 import ProtectedReplacementResultServiceV1,protected_replacement_result_server_v1
    for item in (None,True,{},object()):
        with pytest.raises(PermissionError,match='actual fixed protected result settings'):
            ProtectedReplacementResultServiceV1(item)
        with pytest.raises(PermissionError,match='actual fixed protected result settings'):
            protected_replacement_result_server_v1(item)


def test_unverified_peer_never_reaches_current_sql_or_qualified_bytes(monkeypatch,tmp_path):
    import asyncio
    from oracle_brain.hosting.replacement_result_service_v1 import ProtectedReplacementResultServiceV1
    c=config()
    # Controlled negative only: these unadmitted metadata objects must never be
    # used as authority. Actual TLS/current SQL positive remains independent.
    s=m.ProtectedReplacementResultSettingsV1(c,tmp_path/'config','a'*64,tmp_path/'appt','b'*64,
        c.issuer_actor,c.reviewer_actor,None,())
    def forbidden(*args):raise AssertionError('unauthenticated peer reached private/current authority')
    monkeypatch.setattr(m.ProtectedReplacementResultSettingsV1,'current_target',forbidden)
    for peer in (None,b'invented-wrong-der',True):
        with pytest.raises(PermissionError,match='exact authenticated result client'):
            asyncio.run(ProtectedReplacementResultServiceV1(s).handle_result_v1(peer,b'{}'))
