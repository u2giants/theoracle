"""Public invented receipt fixtures never assert real hosted restore acceptance."""
import copy,hashlib,json,os
from pathlib import Path
import pytest
from pydantic import ValidationError
from oracle_brain.hosting.restore_receipts import (Backup,Restore,ROLES,RUNNING,validate_backup,
 verify_bundle,validate_restore)
from oracle_brain.hosting.synthetic_fixture import fixture,fixed_scenario,FORWARD_SCENARIO
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.retrieval import build_pack,QueryPlan


def sha(raw):return hashlib.sha256(raw).hexdigest()


def instance(app,seed):
    project='oracle-native-'+app
    return {'application':app,'project':project,'ledger_container':format(seed+ROLES.index('ledger'),'064x'),
      'ledger_volume':project+'_ledger-data','spool_volume':project+'_job-spool','blob_volume':project+'_executor-blobs','candidate_volume':project+'_candidate-data','confirmed_volume':project+'_confirmed-data',
      'networks':[format(seed+100+i,'064x') for i in range(5)],'isolation_receipt_sha256':'b'*64}


def services(image,seed):
    vendor={'ledger':'postgres:16.10-alpine@sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297',
      'candidate':'falkordb/falkordb:v4.20.7@sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d',
      'confirmed':'falkordb/falkordb:v4.20.7@sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d'}
    return {role:{'container_id':format(seed+i,'064x'),'image':vendor.get(role,image),
      'state':'running' if role in RUNNING else 'exited','exit_code':0} for i,role in enumerate(ROLES)}


@pytest.fixture
def bundle(tmp_path):
    root=tmp_path/'backup';root.mkdir(mode=0o700)
    scenario=fixed_scenario(FORWARD_SCENARIO)
    receipts,_,payload,manifest,release=fixture('a'*64,'c'*64,FORWARD_SCENARIO)
    opaque={'job_id':str(scenario.run),'runtime_hash':'a'*64,'admission_hash':release.documentary_gate_hash,
       'nonce':'12345678-1234-4234-8234-123456789012','expires_at':2000}
    result=build_pack(payload,QueryPlan(view='company_overview',question='invented amber parcel',max_bytes=16384,page=0,page_size=25));result['sdk_candidate_count']=2
    corpus={'ledger.dump':b'PGDMP-public-invented-format-fixture','roles.bundle':b'PUBLIC-INVENTED-NONAUTHORIZING-ROLE-CUSTODY-FIXTURE',
      'sources.json':canonical_bytes({'receipts':[r.model_dump(mode='json') for r in receipts]}),
      'blobs/'+manifest.private_object_key:canonical_bytes(payload),'result.json':canonical_bytes(result),
      'spool/'+str(scenario.run)+'.claimed':canonical_bytes(opaque),'spool/.custody-lock':b'',
      'spool/nonce-'+opaque['nonce']:sha(json.dumps(opaque,sort_keys=True).encode()).encode()}
    toc={'schema':'oracle-forward-dump-toc/v1','archive_sha256':sha(corpus['ledger.dump']),'format':'custom','server_major':16,'database':'oracle_synthetic',
      'required_table_names':['appointments','artifact_dependencies','artifact_manifests','drafts','hosting_role_runtime_admissions','hosting_role_source_admissions','operating_model_change_log','operating_model_source_receipts','operating_release_manifests','operating_release_selectors','operating_view_pack_receipts','operating_view_runs','source_blocks','sources','synthetic_hosting_marker']}
    corpus['ledger.toc.json']=canonical_bytes(toc)
    role={'schema':'oracle-forward-role-bootstrap/v1','source_head':'f'*40,'runtime_hash':'a'*64,
      'source_registry_sha256':'d'*64,'dump_toc_sha256':sha(corpus['ledger.toc.json']),'role_bundle_sha256':sha(corpus['roles.bundle']),
      'roles':{'oracle_synthetic_gateway':'oracle2_gateway_metadata','oracle_synthetic_executor':'oracle2_documentary_executor','oracle_synthetic_projector':'oracle2_documentary_executor'},
      'login_privileges':'NOINHERIT,NOSUPERUSER,NOCREATEDB,NOCREATEROLE,NOBYPASSRLS'}
    corpus['roles-bootstrap.json']=canonical_bytes(role)
    seals={}
    for name,raw in corpus.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        for parent in path.parents:
            if not parent.is_relative_to(root):break
            parent.chmod(0o700)
        path.write_bytes(raw);path.chmod(0o600)
        seals[name]={'sha256':sha(raw),'size':len(raw),'runtime_uid':10001 if name.startswith(('blobs/','spool/')) else 0,'runtime_mode':0o600}
    image='ghcr.io/u2giants/theoracle-native@sha256:'+'e'*64
    authority={'worker_uri':scenario.worker_uri,'source_registry_sha256':'d'*64,'worker_registry_sha256':'e'*64,
      'issued_at':900,'expires_at':2200,'certificate_sha256':'f'*64,'source_permission_receipt_sha256':'1'*64}
    backup=Backup.model_validate({'schema':'oracle-forward-backup/v1','scenario':FORWARD_SCENARIO,'scenario_seal':scenario.seal(),
      'source_head':'f'*40,'image':image,'runtime_hash':'a'*64,'review_hash':'c'*64,'release_hash':release.content_hash(),'captured_at':1000,
      'instance':instance('inventedforwardnamespace2',100),'services':services(image,100),'authority':authority,'job_id':str(scenario.run),
      'job_state':'completed','pending_jobs':0,'ledger_watermark':11,'files':seals,'nonces':[{'purpose':'admit','consumed_at':950,'request':opaque}],
      'dump_toc_sha256':sha(corpus['ledger.toc.json']),'role_bootstrap_sha256':sha(corpus['roles-bootstrap.json']),
      'result_sha256':sha(corpus['result.json']),'backup_operation_receipt_sha256':'2'*64})
    restore=Restore.model_validate({'schema':'oracle-forward-restore/v1','backup_manifest_sha256':digest(backup.model_dump()),'restored_at':1100,
      'instance':instance('inventedrestorenamespace2',500),'services':services(image,500),'authority':authority,'files':seals,
      'originally_empty_receipt_sha256':'3'*64,'original_instance_routes_denied_receipt_sha256':'4'*64,'restore_operation_receipt_sha256':'5'*64,
      'source_permission_receipt_sha256':'d'*64,'source_permission_contract_sha256':'1'*64,'pending_jobs':0,'job_state':'completed','job_id':str(scenario.run),'result_sha256':sha(corpus['result.json']),
      'sdk_version':'1.4.0','sdk_graph_name':release.graph_name,'sdk_record_digest':release.graph_record_digest,'sdk_artifact_digest':manifest.content_hash,
      'sdk_rebuild_receipt_sha256':'6'*64,'sdk_reload_receipt_sha256':'7'*64,'sdk_was_empty_receipt_sha256':'8'*64,'old_job_denied_receipt_sha256':'9'*64,
      'spent_admit_denied_receipt_sha256':'a'*64,'wrong_actor_source_denied_receipt_sha256':'b'*64,'result_delivery_receipt_sha256':'c'*64})
    return root,backup,restore


def changed(model,**updates):return type(model).model_validate({**model.model_dump(),**updates})


def test_complete_public_receipts_validate_without_live_acceptance(bundle):
    root,backup,restore=bundle
    checked=verify_bundle(root,backup)
    assert checked['validated_file_count']==len(backup.files)
    assert not checked['hosted_accepted'] and not checked['business_accepted']
    checked=validate_restore(backup,restore)
    assert checked['fresh_instance_metadata_consistent'] and not checked['hosted_accepted'] and not checked['business_accepted']


@pytest.mark.parametrize('mutation',['old_job','old_app','expired','renewal','missing_file','pending','unknown_field','shared_namespace','missing_role','wrong_image','nonce_replay'])
def test_backup_or_restore_boundary_refusals(bundle,mutation):
    root,b,r=bundle
    with pytest.raises((PermissionError,ValidationError)):
        if mutation=='old_job':validate_backup(changed(b,job_id=str(fixed_scenario().run)))
        elif mutation=='old_app':validate_backup(changed(b,instance={**b.instance.model_dump(),'application':'vhmcdkdk23dgvjvcvhyhcjzd','project':'oracle-native-vhmcdkdk23dgvjvcvhyhcjzd'}))
        elif mutation=='expired':validate_restore(b,changed(r,restored_at=b.authority.expires_at))
        elif mutation=='renewal':validate_restore(b,changed(r,authority={**r.authority.model_dump(),'expires_at':2300}))
        elif mutation=='missing_file':validate_backup(changed(b,files={k:v.model_dump() for k,v in b.files.items() if k!='result.json'}))
        elif mutation=='pending':changed(b,pending_jobs=1)
        elif mutation=='unknown_field':changed(b,raw_environment={'injected':'value'})
        elif mutation=='shared_namespace':validate_restore(b,changed(r,instance=b.instance.model_dump()))
        elif mutation=='missing_role':validate_backup(changed(b,services={k:v.model_dump() for k,v in b.services.items() if k!='gateway-files'}))
        elif mutation=='wrong_image':validate_backup(changed(b,services={k:({**v.model_dump(),'image':b.image} if k=='ledger' else v.model_dump()) for k,v in b.services.items()}))
        else:validate_backup(changed(b,nonces=[n.model_dump() for n in b.nonces]*2))


@pytest.mark.parametrize('mutation',['byte_corruption','extra_file','link','mode','source_receipt','role_privilege','nonce_bytes','dump_format','fifo','extra_dir','directory_mode'])
def test_corpus_integrity_refusals(bundle,mutation):
    root,b,_=bundle
    if mutation=='fifo':os.mkfifo(root/'unexpected')
    elif mutation=='extra_dir':(root/'unexpected').mkdir(mode=0o700)
    elif mutation=='directory_mode':(root/'spool').chmod(0o755)
    elif mutation=='extra_file':(root/'unexpected').write_text('invented')
    elif mutation=='link':
        p=root/'result.json';p.unlink();p.symlink_to(root/'sources.json')
    elif mutation=='mode':(root/'result.json').chmod(0o644)
    else:
        name={'byte_corruption':'result.json','source_receipt':'sources.json','role_privilege':'roles-bootstrap.json','nonce_bytes':'spool/nonce-'+b.nonces[0].request.nonce,'dump_format':'ledger.dump'}[mutation]
        (root/name).write_bytes(b'invented-mutation')
    with pytest.raises((PermissionError,OSError)):verify_bundle(root,b)


@pytest.mark.parametrize('field',['source_permission_contract_sha256','sdk_record_digest','sdk_artifact_digest','result_sha256','sdk_rebuild_receipt_sha256'])
def test_restore_permission_result_and_sdk_refusals(bundle,field):
    _,b,r=bundle
    value=r.sdk_reload_receipt_sha256 if field=='sdk_rebuild_receipt_sha256' else '0'*64
    with pytest.raises(PermissionError):validate_restore(b,changed(r,**{field:value}))


def test_spent_expired_envelope_is_preserved_without_replay(bundle):
    _,backup,restored=bundle
    # A spent envelope may expire while the distinct original worker/source
    # authority remains active. It is immutable recovery evidence, not renewed.
    backup=changed(backup,captured_at=2100)
    restored=changed(restored,backup_manifest_sha256=digest(backup.model_dump()),restored_at=2150)
    validate_backup(backup)
    assert validate_restore(backup,restored)['serving_accepted'] is False
