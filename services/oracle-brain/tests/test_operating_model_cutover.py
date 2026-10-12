from uuid import uuid4
import pytest
from oracle_brain.operating_model.release_manifest import ReleaseManifest

def manifest(**changes):
    w=uuid4(); s=uuid4(); base=dict(release_id=uuid4(),workspace_id=w,artifact_id=uuid4(),artifact_version=1,artifact_content_hash='a'*64,runtime_digest='b'*64,permission_digest='c'*64,source_refs=(),graph_generation=uuid4(),graph_name='oracle_operating_model_v1_'+w.hex,graph_record_digest='d'*64,acceptance_state='synthetic',independent_review_hash='e'*64,documentary_gate_hash='f'*64,source_inventory_hash='0'*64,ledger_watermark=0)
    from oracle_brain.operating_model.source_receipts import SourceRef
    base['source_refs']=(SourceRef(workspace_id=w,source_id=s,revision=1,original_sha256='1'*64,reading_sha256='2'*64,parser_id='p'),); base.update(changes); return ReleaseManifest(**base)

def test_exact_synthetic_release_has_stable_hash():
    m=manifest(); assert len(m.content_hash())==64 and m.content_hash()==m.content_hash()

def test_unreviewed_release_is_not_admitted():
    m=manifest(); assert m.content_hash() not in frozenset()

def test_source_population_is_bound_to_workspace_and_revision():
    m=manifest(); ref=m.source_refs[0]; assert ref.workspace_id==m.workspace_id and ref.revision==1
    with pytest.raises(ValueError,match='cross-workspace'):
        manifest(source_refs=(ref.model_copy(update={'workspace_id':uuid4()}),))

def test_hosted_release_requires_restricted_gate_and_restore_proof():
    with pytest.raises(ValueError,match='restricted hosting'):
        manifest(acceptance_state='hosted_preview')
    with pytest.raises(ValueError,match='restore proof'):
        manifest(acceptance_state='admitted_hosted',restricted_hosting_hash='1'*64)

def test_analytical_release_requires_qualification():
    with pytest.raises(ValueError,match='analytical qualification'):
        manifest(analytical_capability=True)

from test_operating_model_sdk import projection_inputs,make_projection
import asyncio
import psycopg
from oracle_brain.operating_model.cutover import activate,selected,watermark
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.source_receipts import SourceRef


def test_real_atomic_selector_sdk_and_stale_rollback_denial(projection_inputs):
    async def proof():
        graph,ledger,w,artifact,payload=projection_inputs
        generation=uuid4();projection=make_projection(graph,w,artifact,generation)
        built=await projection.build(ledger,w,artifact,1)
        with psycopg.connect(ledger.url) as conn:mark=watermark(conn,w)
        m=ReleaseManifest(release_id=uuid4(),workspace_id=w,artifact_id=artifact,artifact_version=1,
          artifact_content_hash=digest(payload),runtime_digest='b'*64,permission_digest='c'*64,
          source_refs=tuple(SourceRef.model_validate_json(__import__('json').dumps(r)) for r in payload['source_refs']),
          graph_generation=generation,graph_name=built['graph_name'],graph_record_digest=built['record_digest'],
          acceptance_state='synthetic',independent_review_hash='e'*64,documentary_gate_hash='f'*64,
          source_inventory_hash='0'*64,ledger_watermark=mark)
        def verify(manifest,data):assert manifest.graph_record_digest==digest({'records':projection.records(data)})
        kwargs=dict(expected_generation=0,ledger=ledger,verify_projection=verify,runtime_digest='b'*64,synthetic=True)
        with pytest.raises(PermissionError,match='independent admission'):activate(ledger.url,m,reviewed_release_hashes=frozenset(),**kwargs)
        assert activate(ledger.url,m,reviewed_release_hashes=frozenset({m.content_hash()}),**kwargs)==1
        assert selected(ledger.url,w)==m
        with pytest.raises(ValueError,match='moved concurrently'):activate(ledger.url,m,reviewed_release_hashes=frozenset({m.content_hash()}),**kwargs)
        with psycopg.connect(ledger.url) as conn:conn.execute("INSERT INTO oracle2.operating_model_change_log(workspace_id,object_kind,object_id) VALUES(%s,'source','new-revision')",(w,))
        with pytest.raises(PermissionError,match='replay'):selected(ledger.url,w)
        ledger.can_read=lambda *_:False
        with pytest.raises(PermissionError):activate(ledger.url,m,reviewed_release_hashes=frozenset({m.content_hash()}),**{**kwargs,'expected_generation':1})
        with psycopg.connect(ledger.url) as conn:assert conn.execute('SELECT count(*) FROM oracle2.operating_release_manifests WHERE workspace_id=%s',(w,)).fetchone()[0]==1
        await projection.close()
    asyncio.run(proof())
