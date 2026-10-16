"""Fixed native job freezing only; denied before any provider/key/ledger IO."""
from uuid import uuid4
import pytest
from oracle_brain.operating_model.native_factory import RawOriginalDispatchJobV1,NativeDispatchJob,NativeBrokerEgress
from test_native_factory import job,envelope


def original_job(review=False):
    prior=job();purpose='source-original-review' if review else 'source-original-reading'
    values=prior.model_dump(mode='python');values['purpose']=purpose
    values['processing_request']=prior.processing_request.model_copy(update={'purpose':purpose})
    values['approvals']=tuple(a.model_copy(update={'purpose':purpose}) for a in prior.approvals)
    values.update(population_id=uuid4(),operation_registry_hash='f'*64,raw_ref={'workspace_id':prior.workspace_id,'source_id':uuid4(),'revision':1,
        'original_sha256':'a'*64,'byte_count':20,'media_type':'application/pdf','filename':'invented.pdf',
        'custody_locator_seal_sha256':'b'*64},view_manifest_hash='c'*64,locator_map_hash='d'*64,
        reading_commit_hash='e'*64 if review else None)
    return RawOriginalDispatchJobV1.model_validate(values)

@pytest.mark.parametrize('review',[False,True])
def test_exact_original_job_survives_native_snapshot_before_authority_denial(review):
    j=original_job(review);observed=[]
    b=object.__new__(NativeBrokerEgress);b._resolve=lambda _:j;b._allocation=None
    def deny(current):observed.append(current);return False
    b._authorize=deny
    with pytest.raises(PermissionError,match='current job authority unavailable'):b.dispatch(envelope(j))
    assert len(observed)==1 and type(observed[0]) is RawOriginalDispatchJobV1
    assert observed[0]==j and observed[0] is not j
    with pytest.raises(ValueError):NativeDispatchJob.model_validate_json(j.model_dump_json())

@pytest.mark.parametrize('damage',['review_without_reader','reading_with_future_reader','foreign','text','purpose'])
def test_original_job_requires_exact_phase_no_future_source_ref(damage):
    values=original_job().model_dump(mode='python')
    if damage=='review_without_reader':values['purpose']='source-original-review'
    elif damage=='reading_with_future_reader':values['reading_commit_hash']='a'*64
    elif damage=='foreign':values['raw_ref']['workspace_id']=uuid4()
    elif damage=='text':values['raw_ref']['media_type']='text/plain'
    else:values['purpose']='arbitrary-original-purpose'
    with pytest.raises(ValueError):RawOriginalDispatchJobV1.model_validate(values)


def test_unknown_original_job_subclass_is_not_an_admitted_native_snapshot():
    class Foreign(RawOriginalDispatchJobV1):pass
    j=Foreign.model_validate(original_job().model_dump(mode='python'))
    b=object.__new__(NativeBrokerEgress);b._resolve=lambda _:j;b._allocation=None
    b._authorize=lambda _:pytest.fail('unknown subclass reached current authority')
    with pytest.raises(PermissionError,match='immutable admitted job'):b.dispatch(envelope(j))
