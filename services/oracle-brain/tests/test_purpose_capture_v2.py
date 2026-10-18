"""Invented actual wire envelope; source protocol proof, not admitted model quality."""
import hashlib,json
from datetime import timedelta
from uuid import uuid4
import pytest
from test_assembly_context import context
from test_purpose_assembly_v2 import make_v2
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.semantic_acceptance import sealed
from oracle_brain.operating_model.captured_assembly import captured_assembly_candidate,ObservedAssemblyProtocol
from oracle_brain.operating_model.purpose_capture_v2 import (
    ObservedAssemblyProtocolV2,AssemblyObserverContextV2,ObservedAssemblyWireV2,captured_assembly_candidate_v2)


def wire_v2(context):
    ctx,model,now=make_v2(context);protocol=ObservedAssemblyProtocolV2()
    raw=canonical_bytes({'model':ctx.job.request['model'],'choices':[{'index':0,'finish_reason':'stop',
        'message':{'role':'assistant','content':model.model_dump_json()}}]})
    observer=AssemblyObserverContextV2(custodian_id=uuid4(),custodian_config_hash='a'*64,custodian_session_hash='b'*64,
        runtime_hash=ctx.runtime_hash,census_hash=sealed(ctx.census),protocol_hash=sealed(protocol),
        dispatch_id=ctx.job.dispatch_id,job_hash=sealed(ctx.job),request_hash=ctx.job.request_hash,
        key_fingerprint='c'*64,ledger_identity_hash='d'*64,expires_at=ctx.expires_at,
        assembly_context_hash=sealed(ctx),handoff_hash=sealed(ctx.handoff))
    observed=ObservedAssemblyWireV2(observer_context_hash=sealed(observer),assembly_context_hash=sealed(ctx),
        handoff_hash=sealed(ctx.handoff),dispatch_id=ctx.job.dispatch_id,reservation_id=uuid4(),
        job_hash=sealed(ctx.job),request_hash=ctx.job.request_hash,raw_sha256=hashlib.sha256(raw).hexdigest(),
        captured_bytes=len(raw),observed_at=now)
    return dict(context=ctx,observer=observer,expected_observer_context_hash=sealed(observer),protocol=protocol,
        expected_protocol_hash=sealed(protocol),observed=observed,raw=raw,now=now+timedelta(seconds=1))


def test_v2_capture_binds_current_phase_and_historical_handoff_without_reinterpreting_v1(context):
    args=wire_v2(context);captured,_=captured_assembly_candidate_v2(**args)
    assert captured.handoff_hash==sealed(args['context'].handoff)
    assert captured.candidate['assembly_capture']['candidate_schema']=='purpose-captured-assembly-v2'
    with pytest.raises(PermissionError):captured_assembly_candidate(**args)


@pytest.mark.parametrize('damage',('legacy-protocol','context','handoff','wire-handoff','wire-context','hash','raw','future','expired'))
def test_new_capture_protocol_refuses_legacy_or_substituted_context(context,damage):
    args=wire_v2(context)
    if damage=='legacy-protocol':args['protocol']=ObservedAssemblyProtocol()
    elif damage=='context':args['observer']=args['observer'].model_copy(update={'assembly_context_hash':'f'*64})
    elif damage=='handoff':args['observer']=args['observer'].model_copy(update={'handoff_hash':'f'*64})
    elif damage=='wire-handoff':args['observed']=args['observed'].model_copy(update={'handoff_hash':'f'*64})
    elif damage=='wire-context':args['observed']=args['observed'].model_copy(update={'assembly_context_hash':'f'*64})
    elif damage=='hash':args['expected_protocol_hash']='f'*64
    elif damage=='raw':args['raw']+=b' '
    elif damage=='future':args['observed']=args['observed'].model_copy(update={'observed_at':args['now']+timedelta(seconds=1)})
    elif damage=='expired':args['now']=args['context'].expires_at
    with pytest.raises((PermissionError,ValueError)):captured_assembly_candidate_v2(**args)
