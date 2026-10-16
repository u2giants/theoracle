"""Invented metadata protocol fixtures; no runtime/issuer/provider authority."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import SourceRef
from oracle_brain.operating_model.purpose_journey import PurposeWorkerJobV2, PurposeJourneyJournalV2


NOW=datetime.now(timezone.utc)
ACTOR=uuid4()

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
