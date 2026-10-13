"""Fixed invented SDK build on isolated candidate network; never private inputs."""
import asyncio,hashlib,json,os
from pathlib import Path
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.authority_adapter import PostgresSources
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.sdk_projection import SDKProjection
from oracle_brain.operating_model.runtime import NoGeneration,SyntheticEmbedding
from .runtime import settings,protected_file,sealed_scenario
from .synthetic_fixture import fixture,WORKSPACE,ACTOR,ARTIFACT,GENERATION,LEGACY_SCENARIO

async def project(config,review_hash):
    if not config['synthetic']:raise PermissionError('fixed invented projection only')
    scenario=sealed_scenario(config)
    if scenario.scenario_id!=LEGACY_SCENARIO:
        WORKSPACE,ACTOR,ARTIFACT,GENERATION=(scenario.workspace,scenario.actor,scenario.artifact,scenario.generation)
        if review_hash!=config['synthetic_review_hash']:raise PermissionError('forward scenario review differs')
    else:
        WORKSPACE,ACTOR,ARTIFACT,GENERATION=(globals()[key] for key in ('WORKSPACE','ACTOR','ARTIFACT','GENERATION'))
    receipts,_,payload,manifest,release=fixture(config['runtime_hash'],review_hash,scenario.scenario_id)
    if release.content_hash() not in config['allowed_release_hashes']:raise PermissionError('fixed fixture release not independently admitted')
    from psycopg import connect
    with connect(config['_database_url']) as conn:
        if conn.execute('SELECT oracle2.hosting_source_runtime_binding() IS NOT NULL').fetchone()[0] is not True:raise PermissionError('source role admission absent')
        runtime,registry,_=conn.execute('SELECT * FROM oracle2.hosting_source_runtime_binding()').fetchone()
        if runtime!=config['runtime_hash'] or registry!=config['source_role_registry_hash']:raise PermissionError('external source role pins differ')
    sources=PostgresSources(config['_database_url'],source_binding=config['_source_binding'])
    # The only bytes materialized by this fixed task are public invented payload.
    blobs=FileBlobStore(Path(config['blob_root']))
    key,seal=blobs.put(WORKSPACE,payload)
    if (key,seal)!=(manifest.private_object_key,manifest.content_hash):raise PermissionError('invented artifact identity differs')
    ledger=Ledger(config['_database_url'],blobs,principal=ACTOR,can_read=sources.can_read,current_source=sources.current)
    if ledger.read(WORKSPACE,ARTIFACT,1)!=payload:raise PermissionError('seed differs from fixed reviewed payload')
    projection=SDKProjection(protected_file(config['graph_url_file']).decode().strip(),workspace_id=WORKSPACE,artifact_id=ARTIFACT,artifact_version=1,generation=GENERATION,llm=NoGeneration(),embedder=SyntheticEmbedding(),dimensions=8)
    try:
        # Never rewrite an existing graph. A failed run leaves recovery evidence.
        if (await projection.connection.query('MATCH (n) RETURN count(n)')).result_set[0][0]!=0:raise PermissionError('new empty invented graph required')
        receipt=await projection.build(ledger,WORKSPACE,ARTIFACT,1)
        if receipt['graph_name']!=release.graph_name or receipt['content_hash']!=release.artifact_content_hash or receipt['record_digest']!=release.graph_record_digest:raise PermissionError('finalized invented graph differs')
        return {'synthetic':True,'sdk_version':receipt['sdk_version'],'finalized':True,'artifact_hash':seal,'record_digest':receipt['record_digest'],'source_count':len(receipts),'private_admission':False}
    finally:await projection.close()

def main():
    try:
        config=settings('executor','/run/oracle-auth/settings.json',os.environ.get('ORACLE_HOSTING_SETTINGS_SHA256',''))
        if config.get('synthetic_scenario')=='public-invented-forward-v2':
            from .forward_recovery import arm_native_budget
            arm_native_budget(config,seconds=80)
        review=protected_file('/run/oracle-auth/synthetic-review-hash').decode().strip()
        print(json.dumps(asyncio.run(project(config,review)),sort_keys=True))
    except Exception:
        print('fixed invented projection denied',file=__import__('sys').stderr);raise SystemExit(1)

if __name__=='__main__':main()
