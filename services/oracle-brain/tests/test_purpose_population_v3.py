"""Versioned pure population contracts, never source/custody admission."""
from uuid import UUID
import hashlib,json
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.purpose_journey import PurposeWorkerJobV2,PurposeWorkerJobV3


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
