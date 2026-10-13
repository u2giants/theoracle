"""Executable command boundaries; public fake transports never touch a host."""
import hashlib,io,json,tarfile
from datetime import datetime,timedelta,timezone
import pytest
from oracle_brain.hosting.forward_recovery import ForwardRecovery,unpack,pack,ROLES
from oracle_brain.hosting.synthetic_seed import compile_restore_roles,compile_seed
from oracle_brain.hosting.synthetic_fixture import fixed_scenario,fixture,FORWARD_SCENARIO
from oracle_brain.operating_model.contracts import digest,canonical_bytes
from test_hosting_synthetic_fixture import parameters
from test_hosting_restore_receipts import bundle,services,changed


def forward_params():
    p=parameters();s=fixed_scenario(FORWARD_SCENARIO)
    p.update(synthetic_scenario=s.scenario_id,synthetic_scenario_seal=s.seal())
    return p


def test_restore_roles_only_never_seed_or_requeue():
    result=compile_restore_roles(forward_params())
    assert result.startswith('BEGIN;') and result.endswith('COMMIT;\n')
    assert 'CREATE ROLE oracle2_gateway_metadata NOLOGIN' in result
    assert 'LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS' in result
    for word in ('INSERT','UPDATE','DELETE','TRUNCATE','source_blocks','operating_view_runs','appointments'):
        assert word not in result
    with pytest.raises(PermissionError):compile_restore_roles(parameters())


@pytest.mark.parametrize('field,value',[('expires_at','2000-01-01T00:00:00+00:00'),('synthetic_scenario_seal','0'*64),('gateway_scram',"'; DROP SCHEMA oracle2 CASCADE; --")])
def test_restore_compiler_rejects_expired_or_hostile_input(field,value):
    p=forward_params();p[field]=value
    with pytest.raises(PermissionError):compile_restore_roles(p)


def test_tar_corpus_preserves_bytes_and_rejects_path_and_link():
    data={'nonce-public':b'invented','job.claimed':b'public'}
    assert unpack(pack(data))==data
    for name,kind in [('../foreign',tarfile.REGTYPE),('link',tarfile.SYMTYPE),('/absolute',tarfile.REGTYPE)]:
        out=io.BytesIO()
        with tarfile.open(fileobj=out,mode='w') as archive:
            item=tarfile.TarInfo(name);item.type=kind;item.uid=10001;item.mode=0o600;archive.addfile(item)
        with pytest.raises(PermissionError):unpack(out.getvalue())


def fake_inspection(b,role,quiesced=True):
    service=b.services[role];instance=b.instance
    mounts={'ledger':[(instance.ledger_volume,'/var/lib/postgresql/data')],
      'candidate':[(instance.candidate_volume,'/var/lib/falkordb/data')],
      'confirmed':[(instance.confirmed_volume,'/var/lib/falkordb/data')],
      'gateway':[(instance.spool_volume,'/run/oracle-jobs')],
      'executor':[(instance.spool_volume,'/run/oracle-jobs'),(instance.blob_volume,'/run/oracle-blobs')],
      'synthetic-project':[(instance.blob_volume,'/run/oracle-blobs')]}
    return {'id':service.container_id,'name':'/'+instance.project+'-'+role+'-1','application':instance.application,'project':instance.project,'role':role,'image':service.image,
      'state':'exited' if quiesced and role in {'gateway','executor'} and service.state=='running' else service.state,'networks':instance.networks[ROLES.index(role)%6]+' ',
      'mounts':' '.join('volume:'+name+':'+path for name,path in mounts.get(role,[]))}


def test_actual_identity_precedes_mutation_and_foreign_mount_refuses(bundle):
    _,backup,_=bundle;calls=[]
    def runner(args,**kw):
        calls.append(args);role=next(k for k,v in backup.services.items() if v.container_id==args[-1])
        row=fake_inspection(backup,role)
        if role=='ledger':row['mounts']='volume:foreign_ledger:/var/lib/postgresql/data'
        return canonical_bytes(row)
    operator=ForwardRecovery(backup,runner=runner,clock=lambda:1000)
    with pytest.raises(PermissionError):operator.prove_namespace(backup.instance,backup.services,quiesced=True)
    assert all(args[0]=='inspect' for args in calls)


def test_same_instance_restore_never_writes(bundle):
    root,b,_=bundle;calls=[]
    def runner(args,**kw):
        calls.append(args)
        if args[0]=='exec':return b'-s SIG -k SECS'
        role=next(k for k,v in b.services.items() if v.container_id==args[-1]);return canonical_bytes(fake_inspection(b,role))
    operator=ForwardRecovery(b,runner=runner,clock=lambda:1000)
    with pytest.raises(PermissionError):operator.restore(root,b.instance,b.services,operation_receipt_sha256='f'*64)
    assert all(a[0]=='inspect' for a in calls)


def test_expired_authority_denies_before_any_command(bundle):
    _,b,_=bundle
    def runner(*args,**kwargs):pytest.fail('expired action dispatched')
    operator=ForwardRecovery(b,runner=runner,clock=lambda:b.authority.expires_at)
    with pytest.raises(PermissionError):operator.prove_namespace(b.instance,b.services)


def test_fresh_rebuild_only_starts_pinned_new_projector(bundle):
    _,b,r=bundle;calls=[]
    pending={k:({**v.model_dump(),'state':'created'} if k in {'ledger-init','synthetic-project','gateway','executor'} else v.model_dump()) for k,v in r.services.items()}
    target=changed(b,instance=r.instance.model_dump(),services=pending)
    expected=fixture(b.runtime_hash,b.review_hash,FORWARD_SCENARIO)
    def runner(args,**kw):
        calls.append(args)
        if args[0]=='inspect':
            role=next(k for k,v in target.services.items() if v.container_id==args[-1]);return canonical_bytes(fake_inspection(target,role))
        if args[0]=='exec':return b'-s SIG -k SECS'
        assert args==['start','-a',target.services['synthetic-project'].container_id]
        return canonical_bytes({'finalized':True,'artifact_hash':expected[3].content_hash,'record_digest':expected[4].graph_record_digest})
    out=ForwardRecovery(b,runner=runner,clock=lambda:1000).rebuild(r.instance,target.services)
    assert out['serving_accepted'] is False
    assert calls[-1][0]=='start' and b.services['synthetic-project'].container_id not in calls[-1]


def test_executable_capture_and_empty_restore_full_command_sequence(bundle,tmp_path,monkeypatch):
    import time
    root,b,r=bundle;now=int(time.time());p=forward_params()
    p['expires_at']=datetime.fromtimestamp(now+3590,timezone.utc).isoformat()
    p['source_role_registry_hash']='d'*64
    rolebytes=canonical_bytes(p)
    opaque=b.nonces[0].request.model_dump();opaque['expires_at']=now+100
    nonce={'purpose':'admit','consumed_at':now-2,'request':opaque}
    files={k:v.model_dump() for k,v in b.files.items()};files['roles.bundle']['sha256']=hashlib.sha256(rolebytes).hexdigest();files['roles.bundle']['size']=len(rolebytes)
    b=changed(b,captured_at=now,authority={**b.authority.model_dump(),'issued_at':now-10,'expires_at':now+3590},files=files,nonces=[nonce])
    sources=json.loads((root/'sources.json').read_bytes())['receipts'];result=(root/'result.json').read_bytes()
    spool={k.removeprefix('spool/'):(root/k).read_bytes() for k in b.files if k.startswith('spool/')}
    spool[b.job_id+'.claimed']=canonical_bytes(opaque)
    spool['nonce-'+opaque['nonce']]=hashlib.sha256(json.dumps(opaque,sort_keys=True).encode()).hexdigest().encode()
    blobs={k.removeprefix('blobs/'):(root/k).read_bytes() for k in b.files if k.startswith('blobs/')}
    def source_tar(data):
        out=io.BytesIO()
        with tarfile.open(fileobj=out,mode='w') as archive:
            for name,raw in data.items():
                item=tarfile.TarInfo(name);item.size=len(raw);item.uid=item.gid=10001;item.mode=0o600;item.mtime=now-2
                archive.addfile(item,io.BytesIO(raw))
        return out.getvalue()
    calls=[]
    def capture_run(args,**kw):
        calls.append((args,kw))
        if args[0]=='inspect':
            role=next(k for k,v in b.services.items() if v.container_id==args[-1]);return canonical_bytes(fake_inspection(b,role))
        if 'timeout' in args and '--help' in args:return b'-s SIG -k SECS'
        if 'pg_dump' in args:return b'PGDMP-actual-command-public-test'
        if 'pg_restore' in args:return '\n'.join(' TABLE oracle2 '+name+' oracle_bootstrap' for name in json.loads((root/'ledger.toc.json').read_bytes())['required_table_names']).encode()
        if args[0]=='cp':return source_tar(spool if '/run/oracle-jobs' in args[1] else blobs)
        if b'synthetic_hosting_marker' in kw['data']:return b't\n'
        return canonical_bytes({'state':'completed','watermark':11,'result_hex':result.hex(),'sources':sources})
    monkeypatch.setenv('TMPDIR',str(tmp_path))
    dest=tmp_path/'oracle-forward-capture-test'
    actual,checked=ForwardRecovery(b,runner=capture_run,clock=lambda:now+1).capture(dest,rolebytes,operation_receipt_sha256=b.backup_operation_receipt_sha256)
    assert checked['validated_file_count']==len(b.files) and checked['hosted_accepted'] is False
    assert actual.files['ledger.dump'].sha256!=b.files['ledger.dump'].sha256
    pending={k:({**v.model_dump(),'state':'created'} if k in {'ledger-init','synthetic-project','gateway','executor'} else v.model_dump()) for k,v in r.services.items()}
    target=changed(actual,instance=r.instance.model_dump(),services=pending)
    restored={'spool':{'.custody-lock':b''},'blobs':{}}
    restore_calls=[]
    def restore_run(args,**kw):
        restore_calls.append((args,kw))
        if args[0]=='inspect':
            role=next(k for k,v in target.services.items() if v.container_id==args[-1]);return canonical_bytes(fake_inspection(target,role))
        if 'timeout' in args and '--help' in args:return b'-s SIG -k SECS'
        if args[0]=='cp':
            category='spool' if '/run/oracle-jobs' in args[-1] or '/run/oracle-jobs' in args[1] else 'blobs'
            if args[1]=='-a':restored[category]=unpack(kw['data']);return b''
            return pack(restored[category])
        if 'pg_restore' in args:
            assert '--single-transaction' in args and kw['data'].startswith(b'PGDMP');return b''
        query=kw['data']
        if query.startswith(b'BEGIN;'):
            assert b'INSERT' not in query and b'operating_view_runs' not in query;return b''
        if b'current_database()' in query:return b't\n'
        return canonical_bytes({'state':'completed','result_hex':result.hex()})
    out=ForwardRecovery(actual,runner=restore_run,clock=lambda:now+2).restore(dest,r.instance,target.services,operation_receipt_sha256='f'*64)
    assert out['fresh_restore_bytes_verified'] and out['serving_accepted'] is False
    assert any('pg_restore' in args for args,_ in restore_calls)
    assert restored['spool']==spool and restored['blobs']==blobs


@pytest.mark.parametrize('kind',['foreign','symlink_parent','existing_leaf','existing_manifest','public_parent'])
def test_capture_parent_safety_precedes_all_commands(bundle,tmp_path,monkeypatch,kind):
    import os
    _,b,_=bundle;parent=tmp_path/'owned';parent.mkdir(mode=0o700)
    monkeypatch.setenv('TMPDIR',str(parent));root=parent/'oracle-forward-capture-test'
    if kind=='foreign':root=tmp_path/'oracle-forward-capture-foreign'
    elif kind=='symlink_parent':
        link=tmp_path/'link';link.symlink_to(parent,target_is_directory=True);monkeypatch.setenv('TMPDIR',str(link));root=link/root.name
    elif kind=='existing_leaf':root.mkdir(mode=0o700)
    elif kind=='existing_manifest':(parent/(root.name+'.manifest.json')).write_bytes(b'public')
    else:parent.chmod(0o755)
    before=parent.stat().st_mode
    def runner(*args,**kwargs):pytest.fail('unsafe output reached a Docker command')
    with pytest.raises((PermissionError,OSError)):ForwardRecovery(b,runner=runner,clock=lambda:1000).capture(root,b'public',operation_receipt_sha256=b.backup_operation_receipt_sha256)
    assert parent.stat().st_mode==before


def test_near_expiry_budget_denies_before_any_command(bundle):
    _,b,_=bundle
    def runner(*args,**kwargs):pytest.fail('near-expiry command dispatched')
    operator=ForwardRecovery(b,runner=runner,clock=lambda:b.authority.expires_at-20)
    with pytest.raises(PermissionError):operator.checked(['exec',b.instance.ledger_container,'pg_dump'],timeout=60)



def test_native_budget_uses_unchanged_policy_and_os_deadline(tmp_path,monkeypatch):
    from oracle_brain.hosting.forward_recovery import arm_native_budget
    from test_hosting_forward_fixture import config
    import time,signal
    c=config();now=int(time.time())
    policy={'worker_uri':c['worker_uri'],'runtime_hash':c['runtime_hash'],'active':True,'expires_at':now+3600,'allowed_release_hashes':c['allowed_release_hashes']}
    path=tmp_path/'registry';path.write_bytes(canonical_bytes(policy));path.chmod(0o600)
    c.update(registry=str(path),registry_hash=digest(policy))
    calls=[];monkeypatch.setattr(signal,'signal',lambda *a:calls.append(('handler',a)))
    monkeypatch.setattr(signal,'alarm',lambda n:calls.append(('alarm',n)))
    arm_native_budget(c,seconds=80)
    assert ('alarm',80) in calls
    calls.clear();policy['expires_at']=now+30;path.write_bytes(canonical_bytes(policy));c['registry_hash']=digest(policy)
    with pytest.raises(PermissionError):arm_native_budget(c,seconds=80)
    assert not calls
