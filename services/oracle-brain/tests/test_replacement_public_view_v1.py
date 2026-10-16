"""Shared public transport vectors, never runtime admission or browser acceptance."""
import json
from pathlib import Path
import pytest
from oracle_brain.hosting.replacement_public_view_v1 import validate_public_snapshot_v1
ROOT=Path(__file__).resolve().parents[3]
VECTORS=json.loads((ROOT/'apps/web/lib/replacement-contract-schema/vectors-v1.json').read_text())
@pytest.mark.parametrize('vector',VECTORS,ids=lambda v:v['name'])
def test_shared_public_vectors(vector):
    if vector['valid']:
        parsed=validate_public_snapshot_v1(vector['value'])
        assert parsed.model_dump(mode='json',by_alias=True)==vector['value']
    else:
        with pytest.raises(ValueError):validate_public_snapshot_v1(vector['value'])

def test_native_qualified_projection_is_explicit_bounded_and_not_authority():
    from oracle_brain.operating_model.model import BusinessOperatingModel
    from oracle_brain.operating_model.observations import Observation
    from oracle_brain.hosting.replacement_public_view_v1 import qualified_map_view_v1
    raw=VECTORS[0]['value'];source=raw['sources'][0]
    ref=dict(workspace_id=source['workspaceId'],source_id=source['sourceId'],revision=source['revision'],original_sha256=source['originalSha256'],reading_sha256=source['readingSha256'],parser_id=source['parserId'])
    def parse(cls,value):return cls.model_validate_json(json.dumps(value))
    observation=parse(Observation,dict(observation_id='o',ref=ref,occurrence_key='o',kind='step',scope='review',value='Review',evidence=[dict(ref=ref,start=0,end=1,quote='😀')]))
    model=parse(BusinessOperatingModel,dict(model_id=raw['model']['modelId'],version=1,workspace_id=source['workspaceId'],source_refs=[ref],declared_population='invented',processes=[dict(process_id='p',label='Review',scope='review',source_ids=[source['sourceId']],observation_ids=['o'],workflow_ids=['w'],completeness='partial')],objects=[],interfaces=[],assembly_decisions=[],workflows=[dict(workflow_id='w',version=1,workspace_id=source['workspaceId'],process_id='p',scope='review',source_refs=[ref],completeness='partial',steps=[dict(step_id='s',label='Review',kind='activity',support=dict(observation_ids=['o']))],coverage_digest='a'*64)],finding_ids=[],completeness='partial'))
    view=qualified_map_view_v1(model,workflow_id='w',observations=(observation,),findings=())
    assert view.observations[0].evidence[0].quote=='😀'
    assert 'role_id' not in view.model_dump(mode='json')['workflow']['steps'][0]
    with pytest.raises(ValueError):qualified_map_view_v1(model,workflow_id='w',observations=(),findings=())
    with pytest.raises(TypeError):qualified_map_view_v1(model.model_dump(),workflow_id='w',observations=(observation,),findings=())
    with pytest.raises(ValueError):qualified_map_view_v1(model,workflow_id='other',observations=(observation,),findings=())

def test_public_declared_object_shapes_match_generated_zod_schema():
    from oracle_brain.hosting.replacement_public_view_v1 import ReplacementSnapshotV1
    ts=json.loads((ROOT/'apps/web/lib/replacement-contract-schema/snapshot-v1.json').read_text())
    py=ReplacementSnapshotV1.model_json_schema()
    def resolved(node,root):
        while '$ref' in node:
            parts=node['$ref'].split('/')[1:];node=root
            for part in parts:node=node[part]
        return node
    def compare(a,b):
        a=resolved(a,ts);b=resolved(b,py)
        if 'anyOf' in a:
            aa=[x for x in a['anyOf'] if x.get('type')!='null'];bb=[x for x in b.get('anyOf',[]) if x.get('type')!='null']
            assert len(aa)==len(bb)==1;return compare(aa[0],bb[0])
        if 'anyOf' in b: # Python optional fields serialize absent, never nullable on input.
            b=resolved(next(x for x in b['anyOf'] if x.get('type')!='null'),py)
        if a.get('type')=='object':
            assert a['additionalProperties'] is b['additionalProperties'] is False
            assert set(a['properties'])==set(b['properties'])
            assert set(a.get('required',[]))==set(b.get('required',[]))
            for key in a['properties']:compare(a['properties'][key],b['properties'][key])
        elif a.get('type')=='array':
            assert a.get('minItems')==b.get('minItems') and a.get('maxItems')==b.get('maxItems')
            compare(a['items'],b['items'])
        if 'enum' in a:assert set(a['enum'])==set(b['enum'])
    compare(ts,py)
