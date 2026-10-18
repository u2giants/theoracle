"""Closed seven-identifier compiler and real SDK mapping/graph-boundary regressions."""
import asyncio,hashlib,json
from pathlib import Path
import pytest
from oracle_brain.hosting.native_trigger_v2_sql import compile_v2_seed,compile_v2_migration,MIGRATIONS,ROLE_MAP
from oracle_brain.hosting.synthetic_fixture import fixture,NATIVE_TRIGGER_V2_SCENARIO,LEGACY_SCENARIO,FORWARD_SCENARIO,NATIVE_TRIGGER_SCENARIO
from oracle_brain.operating_model.native_proof_v2_identity import IDENTITY as I
from oracle_brain.operating_model.sdk_projection import SDKProjection,NativeInventedTLSProjectionV2
from oracle_brain.operating_model.contracts import digest
from test_hosting_synthetic_fixture import parameters

@pytest.mark.parametrize('bad',['../001_foundation.sql','015_native_trigger_proof.sql','016_native_trigger_proof_v2.sql','missing.sql',b'001_foundation.sql'])
def test_v2_sql_only_fixed_allowed_files(bad):
 with pytest.raises(PermissionError):compile_v2_migration(bad)

def test_v2_seven_pair_mapping_union_and_exact_seed():
 from oracle_brain.hosting.synthetic_fixture import fixed_scenario
 p=parameters();p.update(synthetic_scenario=I['purpose'],synthetic_scenario_seal=fixed_scenario(I['purpose']).seal())
 seed,manifest,payload,release=compile_v2_seed(p)
 import re
 mapped='\n'.join(compile_v2_migration(n).decode() for n in MIGRATIONS)+'\n'+seed
 assert len(ROLE_MAP)==len(set(ROLE_MAP.values()))==7
 for old,new in ROLE_MAP.items():assert not re.search(r'(?<!\w)'+old+r'(?!\w)',mapped) and re.search(r'(?<!\w)'+new+r'(?!\w)',mapped)
 assert 'invented silver envelope' in seed and 'invented amber parcel' not in seed
 for old in (LEGACY_SCENARIO,FORWARD_SCENARIO,NATIVE_TRIGGER_SCENARIO):
  prior=dict(p,synthetic_scenario=old)
  with pytest.raises(PermissionError):compile_v2_seed(prior)
 p['synthetic_scenario_seal']='0'*64
 with pytest.raises(PermissionError):compile_v2_seed(p)

def test_v2_compiler_refuses_mapping_drift(monkeypatch):
 from oracle_brain.hosting import native_trigger_v2_sql as compiler
 monkeypatch.setattr(compiler,'ROLE_MAP',{**ROLE_MAP,'oracle_synthetic_executor':'foreign_executor'})
 with pytest.raises(PermissionError):compiler.compile_v2_migration(MIGRATIONS[0])

@pytest.mark.parametrize('name,expected',[
 (LEGACY_SCENARIO,'5fa8916bd09459b95dd4ae59290d5a1448d128a4b19f1975dcc3546cd2ecd774'),
 (FORWARD_SCENARIO,'ed7042f2c0d213b639c4135a87e542d875fbd2a5345026aea518c2a2893ec17e'),
 (NATIVE_TRIGGER_SCENARIO,'1f3cec6be7fefd1a0cfea46b7c2ff75cd7668a1a67a11aa74e3423c1073ebca6')])
def test_v2_addition_preserves_frozen_prior_fixture_bytes(name,expected):
 # Hashes derived from fb94fb79's unmodified fixture population, not snapshots
 # of the newly added v2 implementation.
 def normalize(x):
  if hasattr(x,'model_dump'):return x.model_dump(mode='json')
  if isinstance(x,dict):return {k:normalize(v) for k,v in x.items()}
  if isinstance(x,(list,tuple)):return [normalize(v) for v in x]
  return x
 raw=json.dumps(normalize(fixture('a'*64,'b'*64,name)),sort_keys=True,separators=(',',':'),default=str).encode()
 assert hashlib.sha256(raw).hexdigest()==expected

@pytest.mark.parametrize('url,read_only',[
 ('rediss://oracle_native_proof_executor_v1:invented@oracle-graph.designflow.app:16391',True),
 ('rediss://oracle_native_proof_executor_v2:invented@oracle-graph.designflow.app:16390',True),
 ('redis://oracle_native_proof_executor_v2:invented@oracle-graph.designflow.app:16391',True),
 ('rediss://oracle_native_proof_projector_v2:invented@oracle-graph.designflow.app:16391',True),
 ('rediss://oracle_native_proof_executor_v2:invented@oracle-graph.designflow.app:16391',False),
 ('rediss://oracle_native_proof_executor_v2:invented@oracle-graph.designflow.app:16391?ssl=false',True)])
def test_v2_exact_graph_boundary_denies_old_foreign_or_writable_role(url,read_only):
 with pytest.raises(PermissionError):NativeInventedTLSProjectionV2(url,connection_config=object(),read_only=read_only)

def test_v2_sdk_adapter_uses_pure_fixed_ids(monkeypatch):
 captured={}
 monkeypatch.setattr(SDKProjection,'__init__',lambda self,url,**kw:captured.update(kw))
 NativeInventedTLSProjectionV2('rediss://'+I['graph_executor']+':invented@oracle-graph.designflow.app:16391',connection_config=object())
 assert tuple(str(captured[k]) for k in ('workspace_id','artifact_id','generation'))==tuple(I[k] for k in ('workspace','artifact','generation'))
 assert captured['read_only'] is True and captured['dimensions']==8


def test_v2_actual_sdk_build_result_contract(monkeypatch):
 from oracle_brain.operating_model import assembly_qualification
 _,_,payload,manifest,release=fixture('a'*64,'b'*64,NATIVE_TRIGGER_V2_SCENARIO)
 class Finalized:
  def model_dump(self,**kw):return {'indexes':{'invented':True}}
 events=[]
 class Connection:
  async def query(self,query,params):events.append(params)
 class Projection:
  records=staticmethod(SDKProjection.records);read_only=False;workspace_id=manifest.workspace_id;graph_name=I['graph_name'];qualification_guard=None;connection=Connection()
  async def _build_graph_payload(self,*args):return self.records(payload),Finalized()
  async def verify(self,actual):assert actual==payload
 projection=Projection()
 monkeypatch.setattr(assembly_qualification,'read_documentary_artifact',lambda *a,**kw:payload)
 result=asyncio.run(SDKProjection.build(projection,object(),manifest.workspace_id,manifest.artifact_id,1))
 assert result=={'graph_name':I['graph_name'],'content_hash':manifest.content_hash,'record_digest':digest({'records':projection.records(payload)}),'sdk_version':'1.4.0','finalized':{'indexes':{'invented':True}}}
 assert len(events)==1 and events[0]['seal']==manifest.content_hash and events[0]['sdk']=='1.4.0'


def test_v2_actual_sdk_constructor_preserves_tls_and_ro_boundary_without_network():
 from oracle_brain.hosting.native_trigger_v2 import tls_config
 from oracle_brain.operating_model.sdk_projection import ReadOnlyConnection
 url='rediss://'+I['graph_executor']+':invented@oracle-graph.designflow.app:16391'
 paths={k:Path('/private')/k for k in ('graph_ca','graph_cert','graph_key')}
 graph,config=tls_config(url.encode(),paths)
 projection=NativeInventedTLSProjectionV2(graph,connection_config=config,read_only=True)
 assert isinstance(projection.connection,ReadOnlyConnection)
 assert projection.graph_name==I['graph_name'] and projection.connection.config.ssl_check_hostname is True
 asyncio.run(projection.close())
