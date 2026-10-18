"""Invented metadata protocol fixtures; no runtime/issuer/provider authority."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import SourceRef
from oracle_brain.operating_model.purpose_journey import PurposeWorkerJobV2
from oracle_brain.hosting.purpose_journey_v2 import PurposeJourneyJournalV2


NOW=datetime.now(timezone.utc)
ACTOR=uuid4()


@pytest.fixture(autouse=True)
def fresh_fixture_horizon(monkeypatch):
    # Collection time confers no runtime authority; each independent test starts
    # its existing two/three-minute invented window when actually executed.
    monkeypatch.setitem(globals(),'NOW',datetime.now(timezone.utc))

def job(*, phase='census', journey=None, refs=None, parent=None, prior=None, source_id=None, allocation='a'*64):
    now=NOW
    refs=refs or tuple(SourceRef(workspace_id=(w:=uuid4()) if i==0 else w,source_id=uuid4(),revision=1,
        original_sha256=str(i+1)*64,reading_sha256=str(i+4)*64,parser_id='fixture') for i in range(3))
    return PurposeWorkerJobV2(job_id=uuid4(),journey_id=journey or uuid4(),workspace_id=refs[0].workspace_id,
        actor_id=ACTOR,phase=phase,source_refs=refs,source_id=source_id,allocation_hash=allocation,
        parent_journal_hash=parent,prior_receipt_hash=prior,nonce=uuid4().hex,runtime_hash='b'*64,
        admission_hash='c'*64,dispatch_id=uuid4(),request_hash='d'*64,phase_registry_sha256='e'*64,
        expires_at=now+timedelta(minutes=2),original_horizon=now+timedelta(minutes=3))


def test_phase_awaiting_and_no_retry_or_allocation_reset(tmp_path):
    j=PurposeJourneyJournalV2(tmp_path)
    first=job(); claimed=j.claim(first,now=datetime.now(timezone.utc))
    assert claimed['state']=='attempt-started'
    with pytest.raises(PermissionError):j.claim(first,now=datetime.now(timezone.utc))
    complete=j.commit(first,receipt_hash='f'*64,native_receipt_hash='0'*64,now=datetime.now(timezone.utc))
    assert complete['state']=='awaiting-external-phase-admission'
    assert j.read(first.journey_id)[-1]['receipt_hash']=='f'*64
    wrong=job(phase='extraction',journey=first.journey_id,refs=first.source_refs,
        source_id=first.source_refs[0].source_id,parent=complete['journal_hash'],prior='f'*64,allocation='9'*64)
    with pytest.raises(PermissionError):j.claim(wrong,now=datetime.now(timezone.utc))


def test_census_barrier_parallel_extractions_and_assembly_all_refs(tmp_path):
    j=PurposeJourneyJournalV2(tmp_path);first=job();j.claim(first,now=datetime.now(timezone.utc))
    barrier=j.commit(first,receipt_hash='f'*64,native_receipt_hash='0'*64,now=datetime.now(timezone.utc))
    extracts=[]
    for ref in first.source_refs:
        x=job(phase='extraction',journey=first.journey_id,refs=first.source_refs,source_id=ref.source_id,
            parent=barrier['journal_hash'],prior='f'*64)
        j.claim(x,now=datetime.now(timezone.utc));extracts.append(x)
    head=j.commit(extracts[0],receipt_hash='1'*64,native_receipt_hash='2'*64,now=datetime.now(timezone.utc))
    premature=job(phase='assembly',journey=first.journey_id,refs=first.source_refs,parent=head['journal_hash'],prior='1'*64)
    with pytest.raises(PermissionError):j.claim(premature,now=datetime.now(timezone.utc))
    for i,x in enumerate(extracts[1:]):head=j.commit(x,receipt_hash=str(i+3)*64,native_receipt_hash='2'*64,now=datetime.now(timezone.utc))
    assembly=job(phase='assembly',journey=first.journey_id,refs=first.source_refs,parent=head['journal_hash'],prior=head['receipt_hash'])
    j.claim(assembly,now=datetime.now(timezone.utc))
    alias=extracts[0].model_copy(update={'job_id':uuid4(),'nonce':uuid4().hex})
    with pytest.raises(PermissionError):j.claim(alias,now=datetime.now(timezone.utc))


def test_future_output_appointment_requires_exact_producer_attempt_without_placeholder(tmp_path):
    from oracle_brain.hosting.purpose_journey_v2 import CompilerPhaseCustodyFileV2
    from pydantic import ValidationError
    base=dict(kind='raw_wire',path=str(tmp_path/'exact.wire'),dispatch_id=uuid4(),
        native_job_hash='a'*64,request_hash='b'*64,producer_runtime_hash='c'*64)
    admitted=CompilerPhaseCustodyFileV2(**base)
    assert admitted.sha256 is None # future bytes have no invented hash
    for field in ('dispatch_id','native_job_hash','request_hash','producer_runtime_hash'):
        with pytest.raises((PermissionError,ValidationError)):
            CompilerPhaseCustodyFileV2(**{k:v for k,v in base.items() if k!=field})
    for kind in ('native_job','assembly_context','extraction_qualification'):
        with pytest.raises(PermissionError):CompilerPhaseCustodyFileV2(**{**base,'kind':kind})


def test_protected_worker_functions_refuse_boolean_dictionary_and_callable():
    from oracle_brain.hosting.purpose_journey_v2 import (
        run_purpose_worker_once_v2,build_purpose_compiler_ledger_v3)
    for invalid in (True,{},object(),lambda:True):
        with pytest.raises(PermissionError):run_purpose_worker_once_v2(invalid)
        with pytest.raises(PermissionError):build_purpose_compiler_ledger_v3(invalid,job())


def test_journal_expired_phase_and_truncated_append_cannot_retry(tmp_path):
    j=PurposeJourneyJournalV2(tmp_path);first=job()
    with pytest.raises(PermissionError):j.claim(first,now=first.expires_at)
    j.claim(first,now=datetime.now(timezone.utc))
    path=j._path(first.journey_id)
    with path.open('ab') as stream:stream.write(b'{')
    with pytest.raises(PermissionError):j.read(first.journey_id)
    with pytest.raises(PermissionError):j.claim(first,now=datetime.now(timezone.utc))


def test_compile_consumer_requires_actual_settings_and_distinct_paid_phases():
    from oracle_brain.hosting.purpose_journey_v2 import PurposeCompileInputsV2,compile_purpose_worker_result_v3
    target=uuid4()
    with pytest.raises(PermissionError):
        PurposeCompileInputsV2(artifact_id=uuid4(),artifact_version=1,census_dispatch_id=target,
            assembly_dispatch_id=target,assessment_dispatch_id=uuid4())
    for invalid in ({},True,lambda:True):
        with pytest.raises(PermissionError):compile_purpose_worker_result_v3(invalid,job())


def test_awaiting_custody_does_not_create_success_barrier_or_retry(tmp_path):
    j=PurposeJourneyJournalV2(tmp_path);first=job();j.claim(first,now=datetime.now(timezone.utc))
    waiting=j.awaiting_custody(first,now=datetime.now(timezone.utc))
    assert waiting['state']=='awaiting-external-custody'
    assert j.awaiting_custody(first,now=datetime.now(timezone.utc))==waiting
    with pytest.raises(PermissionError):j.claim(first,now=datetime.now(timezone.utc))
    child=job(phase='extraction',journey=first.journey_id,refs=first.source_refs,source_id=first.source_refs[0].source_id,
        parent=waiting['journal_hash'],prior='f'*64)
    with pytest.raises(PermissionError):j.claim(child,now=datetime.now(timezone.utc))
    completed=j.commit(first,receipt_hash='f'*64,native_receipt_hash='0'*64,now=datetime.now(timezone.utc))
    assert completed['state']=='awaiting-external-phase-admission'
    with pytest.raises(PermissionError):j.awaiting_custody(first,now=datetime.now(timezone.utc))


def test_independently_admitted_consume_can_observe_original_attempt_without_renewal(tmp_path):
    j=PurposeJourneyJournalV2(tmp_path);first=job();j.claim(first,now=NOW)
    waiting=j.awaiting_custody(first,now=NOW)
    consumer=PurposeWorkerJobV2.model_validate(first.model_copy(update=dict(job_id=uuid4(),nonce=uuid4().hex,
        admission_hash='9'*64,operation='consume',consume_of_job_id=first.job_id,
        resume_journal_hash=waiting['journal_hash'],expires_at=first.original_horizon)).model_dump(mode='python'))
    later=first.expires_at+timedelta(seconds=1)
    with pytest.raises(PermissionError):j.claim(consumer,now=later)
    bad=consumer.model_copy(update={'allocation_hash':'8'*64})
    with pytest.raises(PermissionError):j.commit(first,receipt_hash='f'*64,native_receipt_hash='0'*64,now=later,consumer=bad)
    row=j.commit(first,receipt_hash='f'*64,native_receipt_hash='0'*64,now=later,consumer=consumer)
    assert row['allocation_hash']==first.allocation_hash and row['original_horizon']==first.original_horizon.isoformat()
    assert row['state']=='awaiting-external-phase-admission' and row['consumed_by_job_hash']
    with pytest.raises(PermissionError):j.commit(first,receipt_hash='f'*64,native_receipt_hash='0'*64,now=later,consumer=consumer)


from test_purpose_qualification_v3 import qualified_v3,context

def test_actual_schema3_admission_json_uses_strict_worker_parser(qualified_v3):
    from oracle_brain.hosting.purpose_journey_v2 import _worker_parse
    from oracle_brain.operating_model.contracts import canonical_bytes
    from oracle_brain.operating_model.purpose_qualification_v3 import PurposeSemanticAdmissionV3
    admission=qualified_v3['admission']
    value=admission.model_dump(mode='json')
    assert _worker_parse(canonical_bytes(value),PurposeSemanticAdmissionV3)==admission
    for change in ({'workspace_id':'not-a-uuid'}, {'expires_at':'2026-10-16T03:00:00'},
                   {'expires_at':True}, {'compiler_actor':12}, {'schema_version':True},
                   {'unexpected_field':'denied'}, {'expires_at':{'future':'date'}}):
        with pytest.raises(Exception):
            _worker_parse(canonical_bytes({**value,**change}),PurposeSemanticAdmissionV3)
    missing=dict(value);del missing['issuer_actor']
    with pytest.raises(Exception):_worker_parse(canonical_bytes(missing),PurposeSemanticAdmissionV3)
