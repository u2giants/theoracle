"""One reviewed fresh graph population; writer credential NEVER enters Trigger.

Reads only the new invented fixed fixture and its new source-role admission.
The durable SQL projection claim is spent before the first graph query.
"""
import argparse,asyncio,base64,json,os,sys,tempfile,time
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,quote
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'services/oracle-brain'))
from oracle_brain.hosting.native_trigger_v1 import decode_bundle,database_url,tls_config,SCENARIO,require,NativeSourceRoleBindingV1
from oracle_brain.private_targets import database_tenant
from oracle_brain.hosting.synthetic_fixture import fixture,NATIVE_TRIGGER_SCENARIO
from oracle_brain.operating_model.contracts import digest


async def project(body,files,root):
 import psycopg
 from oracle_brain.operating_model.source_binding import SourceRoleBinding
 from oracle_brain.operating_model.authority_adapter import PostgresSources
 from oracle_brain.operating_model.artifact_storage import FileBlobStore
 from oracle_brain.operating_model.ledger import Ledger
 from oracle_brain.operating_model.sdk_projection import NativeInventedTLSProjectionV1
 from oracle_brain.hosting.job_authority import PostgresJobAuthority
 paths={}
 for name,value in files.items():
  p=root/name;p.write_bytes(value);p.chmod(0o600);paths[name]=p
 url=database_url(files['database_url'],paths['database_ca'],role='projector')
 graph,config=tls_config(files['graph_url'],paths,projector=True)
 _,_,payload,manifest,release=fixture(body['runtime_hash'],body['review_hash'],NATIVE_TRIGGER_SCENARIO)
 binding=NativeSourceRoleBindingV1(body['runtime_hash'],body['source_role_registry_hash'],synthetic=True,expected_login='oracle_synthetic_projector')
 binding.check_url(url)
 authority=PostgresJobAuthority(url,runtime_hash=body['runtime_hash'],synthetic=True,allowed_release_hashes=frozenset((release.content_hash(),)))
 row=authority.resolve(str(SCENARIO.run),body['runtime_hash'],release.documentary_gate_hash)
 require(row['expires_at']==body['expires_at'],'actual fresh projector permission differs')
 with psycopg.connect(url) as c:c.execute('SELECT oracle2.native_trigger_projection(%s,false)',(SCENARIO.run,))
 authority(row);binding.check_url(url)
 sources=PostgresSources(url,source_binding=binding,synthetic=True)
 blobs=FileBlobStore(root/'blobs');key,seal=blobs.put(SCENARIO.workspace,payload)
 require(key==manifest.private_object_key and seal==manifest.content_hash,'fixed new projection input differs')
 ledger=Ledger(url,blobs,principal=SCENARIO.actor,can_read=sources.can_read,current_source=sources.current)
 projection=NativeInventedTLSProjectionV1(graph,connection_config=config,read_only=False)
 try:
  built=await projection.build(ledger,SCENARIO.workspace,SCENARIO.artifact,1)
  records=projection.records(payload)
  require(isinstance(built,dict) and set(built)=={'graph_name','content_hash','record_digest','sdk_version','finalized'}
      and (built['graph_name'],built['content_hash'],built['record_digest'],built['sdk_version'])==(
          projection.graph_name,manifest.content_hash,digest({'records':records}),'1.4.0')
      and isinstance(built['finalized'],dict),'native SDK build result differs from sealed projection')
  await projection.verify(payload);authority(row);binding.check_url(url)
  require(time.time()<body['expires_at'],'new projection permission expired')
  with psycopg.connect(url) as c:c.execute('SELECT oracle2.native_trigger_projection(%s,true)',(SCENARIO.run,))
  return {'state':'completed','job_id':str(SCENARIO.run),'graph_name':projection.graph_name,'artifact_hash':manifest.content_hash,'records':len(records),'sdk_version':'1.4.0'}
 finally:await projection.close()


def main():
 p=argparse.ArgumentParser();p.add_argument('--directory',required=True);a=p.parse_args();d=Path(a.directory)
 body,files=decode_bundle((d/'worker-bundle.json').read_bytes(),json.loads((d/'permission-receipt.json').read_text())['worker_bundle_sha256'])
 passwords=json.loads((d/'passwords.json').read_text())
 database_url(files['database_url'],d/'database_ca')
 tenant=database_tenant(urlsplit(files['database_url'].decode().strip()).username,'oracle_synthetic_executor')
 files['database_url']=('postgresql://oracle_synthetic_projector.'+tenant+':'+passwords['projector']+'@aws-0-us-east-1.pooler.supabase.com:5432/oracle_native_proof_v1').encode()
 files['graph_url']=('rediss://oracle_native_proof_projector_v1:'+quote(os.environ['ORACLE_NATIVE_GRAPH_PROJECTOR_PASSWORD'],safe='')+'@oracle-graph.designflow.app:16391').encode()
 try:
  with tempfile.TemporaryDirectory(prefix='oracle-native-projection-') as root:result=asyncio.run(asyncio.wait_for(project(body,files,Path(root)),timeout=115))
  print(json.dumps(result))
 except BaseException:
  print('{"state":"denied","attempt":"spent-or-unknown"}');raise SystemExit(1)

if __name__=='__main__':main()
