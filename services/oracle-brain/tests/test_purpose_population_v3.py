"""Versioned pure population contracts, never source/custody admission."""
from uuid import UUID
import hashlib,json
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.purpose_journey import (
    PurposeWorkerJobV2, PurposeWorkerJobV3, WORKER_JOB_TYPES, is_worker_job, parse_worker_job,
)


def raw(n):
    return {'job_id':str(UUID(int=10)),'journey_id':str(UUID(int=11)),'workspace_id':str(UUID(int=1)),
        'actor_id':str(UUID(int=2)),'phase':'census','source_refs':[{'workspace_id':str(UUID(int=1)),
        'source_id':str(UUID(int=20+i)),'revision':1,'original_sha256':'1'*64,'reading_sha256':'2'*64,
        'parser_id':'fixture'} for i in range(n)],'allocation_hash':'3'*64,'nonce':'4'*32,
        'runtime_hash':'5'*64,'admission_hash':'6'*64,'dispatch_id':str(UUID(int=12)),
        'request_hash':'7'*64,'phase_registry_sha256':'8'*64,'expires_at':'2026-10-16T09:00:00Z',
        'original_horizon':'2026-10-16T09:01:00Z'}


def test_v2_original_serialized_bytes_unchanged():
    v=PurposeWorkerJobV2.model_validate_json(json.dumps(raw(3)))
    assert hashlib.sha256(canonical_bytes(v.model_dump(mode='json'))).hexdigest()=='5e91bfce2c284cecb5e947069e0d611078c3b6f0a9af9f1448282d4ec09d87bc'

@pytest.mark.parametrize('n',[1,2])
def test_v2_still_rejects_fewer_than_three(n):
    with pytest.raises(PermissionError):PurposeWorkerJobV2.model_validate_json(json.dumps(raw(n)))

@pytest.mark.parametrize('n',[1,2,3])
def test_v3_explicit_complete_nonempty_population(n):
    v=PurposeWorkerJobV3.model_validate_json(json.dumps(raw(n)))
    assert len(v.source_refs)==n and v.schema_version==3 and v.purpose=='replacement-documentary-journey-v3'
    with pytest.raises(ValueError):PurposeWorkerJobV2.model_validate_json(v.model_dump_json())

@pytest.mark.parametrize('damage',['zero','duplicate','foreign','expiry','future','version'])
def test_v3_retains_population_scope_predecessor_and_horizon(damage):
    r=raw(3)
    if damage=='zero':r['source_refs']=[]
    elif damage=='duplicate':r['source_refs'][2]=r['source_refs'][0]
    elif damage=='foreign':r['source_refs'][2]['workspace_id']=str(UUID(int=99))
    elif damage=='expiry':r['expires_at']='2026-10-16T09:02:00Z'
    elif damage=='future':r.update(phase='assembly',parent_journal_hash=None,prior_receipt_hash=None)
    else:r['schema_version']=2
    with pytest.raises((PermissionError,ValueError)):PurposeWorkerJobV3.model_validate_json(json.dumps(r))

@pytest.mark.parametrize('bad',[True,False,3.0,'3'])
def test_v3_version_is_exact_integer_not_literal_coercion(bad):
    r=raw(1);r['schema_version']=bad
    with pytest.raises(ValueError):PurposeWorkerJobV3.model_validate_json(json.dumps(r))


# --- Real worker-job propagation kernel: exact V2/V3 dispatch, never widening. ---

@pytest.mark.parametrize('n',[1,2,3,4095,4096])
def test_parse_worker_job_dispatches_exact_v3_for_complete_population(n):
    r=raw(n);r['schema_version']=3
    job=parse_worker_job(json.dumps(r))
    assert type(job) is PurposeWorkerJobV3 and job.schema_version==3 and len(job.source_refs)==n
    assert is_worker_job(job)


@pytest.mark.parametrize('n',[3,4,4096])
def test_parse_worker_job_dispatches_exact_v2_and_keeps_minimum_three(n):
    r=raw(n);r['schema_version']=2
    job=parse_worker_job(json.dumps(r))
    assert type(job) is PurposeWorkerJobV2 and job.schema_version==2 and len(job.source_refs)==n


@pytest.mark.parametrize('n',[0,4097])
def test_parse_worker_job_rejects_out_of_v3_population_bounds(n):
    r=raw(n);r['schema_version']=3
    with pytest.raises((PermissionError,ValueError)):
        parse_worker_job(json.dumps(r))


@pytest.mark.parametrize('n',[1,2])
def test_parse_worker_job_still_rejects_v2_below_three(n):
    r=raw(n);r['schema_version']=2
    with pytest.raises(PermissionError):
        parse_worker_job(json.dumps(r))


@pytest.mark.parametrize('bad',[True,3.0,'3',None,1,4])
def test_parse_worker_job_rejects_unsupported_version(bad):
    r=raw(1);r['schema_version']=bad
    with pytest.raises(ValueError):
        parse_worker_job(json.dumps(r))


def test_parse_worker_job_accepts_raw_bytes():
    r=raw(1);r['schema_version']=3
    job=parse_worker_job(json.dumps(r).encode())
    assert type(job) is PurposeWorkerJobV3


def test_is_worker_job_rejects_subclass_widening():
    class Wide(PurposeWorkerJobV3):
        pass
    base=PurposeWorkerJobV3.model_validate_json(json.dumps(raw(1)))
    assert is_worker_job(base)
    # An instance of an unregistered subclass is NOT an admitted exact class.
    assert not is_worker_job(Wide.model_validate_json(json.dumps(raw(1))))
    assert WORKER_JOB_TYPES==(PurposeWorkerJobV2,PurposeWorkerJobV3)


def test_worker_registry_shape_accepts_complete_v3_population():
    """The real worker registry field is a closed V2|V3 union; V3 1..4096 flows through."""
    from typing import Union
    from pydantic import BaseModel, ConfigDict
    class Reg(BaseModel):
        model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
        jobs: tuple[Union[PurposeWorkerJobV2,PurposeWorkerJobV3],...]
    a,b,c=raw(3),raw(1),raw(4096)
    a['schema_version']=2; b['schema_version']=3; c['schema_version']=3
    reg=Reg.model_validate_json(json.dumps({'jobs':[a,b,c]}))
    assert [type(j) for j in reg.jobs]==[PurposeWorkerJobV2,PurposeWorkerJobV3,PurposeWorkerJobV3]
    assert [len(j.source_refs) for j in reg.jobs]==[3,1,4096]
