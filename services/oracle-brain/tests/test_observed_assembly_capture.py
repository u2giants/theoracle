"""Actual local wire-custody path with invented HTTP bytes; no provider calls."""
from datetime import timedelta
import json
from uuid import uuid4

import pytest
from test_assembly_context import context, wire_case
from oracle_brain.operating_model.captured_assembly import ObservedAssemblyCustodian, captured_assembly_candidate
from oracle_brain.operating_model.native_factory import ObservedAssemblyBrokerEgress
from oracle_brain.operating_model.native_provider import NativeOpenRouter


def custodian(case, **updates):
    c=case['observer']
    kwargs=dict(context=c,expected_context_hash=case['expected_observer_context_hash'],
        protocol=case['protocol'],expected_protocol_hash=case['expected_protocol_hash'],
        actual_custodian_id=c.custodian_id,actual_config_hash=c.custodian_config_hash,
        actual_session_hash=c.custodian_session_hash,actual_runtime_hash=c.runtime_hash)
    return ObservedAssemblyCustodian(**{**kwargs,**updates})


def capture_broker(tmp_path,case):
    broker=ObservedAssemblyBrokerEgress.__new__(ObservedAssemblyBrokerEgress)
    broker._assembly_observer=custodian(case)
    broker._key_fingerprint=case['observer'].key_fingerprint
    broker._registry_hash=case['observer'].ledger_identity_hash
    broker._receipts=tmp_path/'private';broker._receipts.mkdir(mode=0o700)
    return broker


@pytest.mark.parametrize('field',('expected_context_hash','actual_session_hash','actual_config_hash','actual_runtime_hash'))
def test_observer_rejects_forged_startup_identity(context,field):
    with pytest.raises(PermissionError):custodian(wire_case(context),**{field:'f'*64})


def test_observer_requires_explicit_protocol_and_current_context(context):
    case=wire_case(context)
    with pytest.raises(PermissionError):custodian(case,expected_protocol_hash='f'*64)
    observer=custodian(case)
    with pytest.raises(PermissionError):
        observer.validate_job(case['context'].job,key_fingerprint=case['observer'].key_fingerprint,
            ledger_identity_hash=case['observer'].ledger_identity_hash,now=case['now']+timedelta(minutes=1))
    with pytest.raises(PermissionError):
        captured_assembly_candidate(**{**case,'expected_protocol_hash':'f'*64})


def test_malformed_response_is_observed_and_retained_before_native_json_parse(context,tmp_path,monkeypatch):
    import urllib.request
    case=wire_case(context);broker=capture_broker(tmp_path,case);reservation=uuid4()
    malformed=b'{malformed full provider response'
    class Response:
        def read(self,limit):return malformed
        def __enter__(self):return self
        def __exit__(self,*args):pass
    class Opener:
        def open(self,*args,**kwargs):return Response()
    monkeypatch.setattr(urllib.request,'build_opener',lambda *_:Opener())
    native=NativeOpenRouter('invented-only',coverage_receipt=lambda:None,
        trusted_coverage_hash='a'*64,ledger_identity_hash='b'*64,
        paid_wire_receiver=lambda raw,**kw:broker._capture_wire(case['context'].job,raw,reservation,**kw))
    with pytest.raises(RuntimeError,match="fixed admitted provider request failed"):native._request('/chat/completions',{})
    path=broker._receipts/(str(case['context'].job.dispatch_id)+'.observed-wire.json')
    assert path.exists() and json.loads(path.read_bytes())['time_basis']=='complete-wire-before-local-consumer-v1'
    assert (broker._receipts/(str(case['context'].job.dispatch_id)+'.wire')).read_bytes()==malformed
    assert path.stat().st_mode&0o777==0o600
    with pytest.raises(FileExistsError):broker._capture_wire(case['context'].job,malformed,reservation,complete=True)


def test_observer_expiry_during_response_retains_wire_but_cannot_qualify(context,tmp_path):
    case=wire_case(context);broker=capture_broker(tmp_path,case)
    broker._assembly_observer.context=case['observer'].model_copy(update={'expires_at':case['now']-timedelta(seconds=1)})
    with pytest.raises(PermissionError,match='wire retained'):
        broker._capture_wire(case['context'].job,case['raw'],uuid4(),complete=True)
    assert (broker._receipts/(str(case['context'].job.dispatch_id)+'.wire')).read_bytes()==case['raw']
    assert not (broker._receipts/(str(case['context'].job.dispatch_id)+'.observed-wire.json')).exists()


def test_incomplete_wire_never_receives_complete_observation(context,tmp_path):
    case=wire_case(context);broker=capture_broker(tmp_path,case)
    broker._capture_wire(case['context'].job,b'{partial',uuid4(),complete=False)
    assert not (broker._receipts/(str(case['context'].job.dispatch_id)+'.observed-wire.json')).exists()
