"""Owned-fixture provider container proof; never deployment qualification.

Reuses the native census fixture and existing image/transport/runtime. Transparent
fixture-only forwarding preserves TLS bytes; no provider credentials cross it.
"""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import hashlib,json,os,pathlib,select,shutil,socket,subprocess,threading,time,uuid


def docker(*args):
    return subprocess.check_output(['docker',*args],text=True,stderr=subprocess.PIPE,timeout=90).strip()


@contextmanager
def forward(address,port,*,target_host="127.0.0.1",target_port=None):
    listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind((address,port));listener.listen(8);listener.settimeout(.1)
    stop=threading.Event();workers=[]
    def relay(client):
        with client,socket.create_connection((target_host,target_port or port),timeout=5) as upstream:
            peers=(client,upstream);deadline=time.monotonic()+90;total=0
            while not stop.is_set() and time.monotonic()<deadline:
                ready,_,_=select.select(peers,[],[],.1)
                for source in ready:
                    value=source.recv(65536)
                    if not value:return
                    total+=len(value)
                    if total>20_000_000:raise RuntimeError('owned relay byte limit')
                    (upstream if source is client else client).sendall(value)
    def serve():
        while not stop.is_set():
            try:client,_=listener.accept()
            except socket.timeout:continue
            except OSError:return
            thread=threading.Thread(target=relay,args=(client,),daemon=True);workers.append(thread);thread.start()
    thread=threading.Thread(target=serve,daemon=True);thread.start()
    try:yield listener.getsockname()[1]
    finally:
        stop.set();listener.close();thread.join(2)
        for worker in workers:worker.join(2)


def prove(x,*,fixture,image,output_root):
    """x is an actual native_census_startup fixture, never a deployed record."""
    from contextlib import ExitStack
    from oracle_brain.operating_model.contracts import canonical_bytes
    from oracle_brain.hosting.purpose_transport import PurposeProviderClientV2
    from oracle_brain.operating_model import native_provider
    cfg=x['settings'].config.model_dump(mode='json');source_root=x['settings'].config_path.parent
    output_root=pathlib.Path(output_root);private=output_root/'provider-own-phase';private.mkdir(mode=0o755)
    selected={str(x['settings'].config_path)}
    selected.update(value for value in cfg.values() if isinstance(value,str) and value.startswith('/') and pathlib.Path(value).is_file() and pathlib.Path(value).is_relative_to(source_root))
    selected.update(cfg['private_context_files'].values())
    inventory=[]
    for path in sorted(selected):
        original=pathlib.Path(path)
        assert original.is_relative_to(source_root) and not original.is_symlink()
        relative=original.relative_to(source_root);destination=private/relative
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,destination)
        if str(path) in cfg['private_context_files'].values():
            from oracle_brain.operating_model.purpose_profiles_v2 import PurposePrivateContextV2
            context=PurposePrivateContextV2.model_validate_json(original.read_bytes())
            assert context.phase=='census' and context.census is not None
            assert all(getattr(context,name,None) is None for name in ('assembly','assessment','embedding'))
            category='own-census-originals-only-context'
        elif relative.name in {'source-url','ledger-url','provider-key','server.key'}:category='own-provider-credential'
        elif relative.suffix in {'.pem','.key'}:category='own-provider-TLS'
        else:category='own-census-authority-metadata'
        inventory.append({'relative_path':str(relative),'sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'content_class':category})
    for field in ('observer_spool','private_receipts'):
        original=pathlib.Path(cfg[field]);relative=original.relative_to(source_root)
        shutil.copytree(original,private/relative)
        for item in sorted(original.rglob('*')):
            if item.is_file():
                assert not item.is_symlink()
                inventory.append({'relative_path':str(item.relative_to(source_root)),'sha256':hashlib.sha256(item.read_bytes()).hexdigest(),'content_class':'own-census-replay-metadata' if field=='observer_spool' else 'own-census-private-result'})
    # Keep absolute protected paths unchanged inside the container. Only this
    # phase's copied root is mounted, never the original fixture parent/siblings.
    forbidden=output_root/'sibling-private-credential';forbidden.write_text('INVENTED_UNMOUNTED_PARENT_AND_SIBLING')
    (private/'escape-to-sibling').symlink_to(forbidden)
    config=dict(cfg,bind_host='0.0.0.0',bind_port=8443)
    config_file=private/x['settings'].config_path.name;config_file.write_bytes(canonical_bytes(config));config_file.chmod(0o600)
    config_hash=hashlib.sha256(config_file.read_bytes()).hexdigest()
    for item in inventory:
        if item['relative_path']==str(x['settings'].config_path.relative_to(source_root)):item['sha256']=config_hash
    (output_root/'mount-input-inventory.json').write_text(json.dumps({'schema_version':1,'files':inventory,'raw_complete_parent':False,'sibling_phase':False,'candidate_or_extraction_content':False},sort_keys=True,indent=2)+'\n')
    network=fixture['network'];net=json.loads(docker('network','inspect',network))[0]
    assert net['Internal'] and net['Labels']['oracle.purpose.synthetic']=='true'
    gateway=net['IPAM']['Config'][0]['Gateway'];hosts=output_root/'hosts'
    hosts.write_text(gateway+' localhost\n::1 ip6-localhost\n');hosts.chmod(0o444)
    image_id=docker('image','inspect','--format','{{.Id}}',image)
    name='oracle-purpose-working-provider-'+uuid.uuid4().hex[:12];created=False
    credential_urls=[pathlib.Path(cfg[field]).read_text() for field in ('source_url_file','ledger_url_file')]
    import psycopg
    ca_paths={psycopg.conninfo.conninfo_to_dict(url)['sslrootcert'] for url in credential_urls}
    args=['create','--name',name,'--label','oracle.purpose.synthetic=true','--network',network,
        '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true','--user','10001:10001',
        '--pids-limit','128','--memory','1g','--tmpfs','/tmp:rw,noexec,nosuid,size=64m,mode=1777',
        '--mount',f'type=bind,src={private},dst={source_root},readonly',
        '--mount',f'type=bind,src={hosts},dst=/etc/hosts,readonly']
    states=[cfg['observer_spool'],cfg['private_receipts']]
    for path in states:
        own=private/pathlib.Path(path).relative_to(source_root)
        assert own.is_dir() and not own.is_symlink()
        args+=['--mount',f'type=bind,src={own},dst={path}']
    external_tls={cfg[field] for field in ('observer_ca','observer_certificate','observer_key',
        'server_certificate','server_key','client_ca') if not pathlib.Path(cfg[field]).is_relative_to(source_root)} | ca_paths
    tls_copy=private/'external-tls';tls_copy.mkdir()
    for path in external_tls:
        destination=tls_copy/hashlib.sha256(path.encode()).hexdigest()
        destination.write_bytes(pathlib.Path(path).read_bytes());destination.chmod(0o600)
        args+=['--mount',f'type=bind,src={destination},dst={path},readonly']
    for path in ca_paths-external_tls:
        args+=['--mount',f'type=bind,src={path},dst={path},readonly']
    # Root helper only repairs ownership of this new private copy. It receives
    # no credential environment and never touches the original fixture tree.
    docker('run','--rm','--network','none','--user','0','--mount',f'type=bind,src={private},dst=/owned',
        '--entrypoint','python',image,'-c','import os;\nfor root,dirs,files in os.walk("/owned"):\n os.chown(root,10001,10001)\n for name in files: os.chown(os.path.join(root,name),10001,10001,follow_symlinks=False)')
    code="""import sys,pathlib
from oracle_brain.operating_model import native_provider
native_provider.ENDPOINT=sys.argv[1]
from oracle_brain.hosting import purpose_runtime
real=purpose_runtime.build_purpose_broker_v2
def observed(settings):
 ingress=real(settings);actual=ingress.dispatch
 def dispatch(*args):
  try:return actual(*args)
  except Exception as error:
   (pathlib.Path(settings.config.private_receipts)/'fixture-denial.txt').write_text(type(error).__name__+': '+str(error))
   raise
 ingress.dispatch=dispatch
 return ingress
purpose_runtime.build_purpose_broker_v2=observed
from oracle_brain.hosting.purpose_transport import main
sys.argv=['purpose-provider',*sys.argv[2:]]
main()
"""
    args+=['--entrypoint','python',image,'-c',code,native_provider.ENDPOINT.replace('127.0.0.1','localhost'),'--phase','census','--role','provider',
        '--config',str(x['settings'].config_path),'--config-sha256',config_hash]
    try:
        with ExitStack() as stack:
            for port in {cfg['observer_port'],int(native_provider.ENDPOINT.rsplit(':',1)[1])}:
                stack.enter_context(forward(gateway,port))
            docker(*args);created=True;actual=json.loads(docker('inspect',name))[0]
            assert actual['Config']['User']=='10001:10001' and actual['HostConfig']['ReadonlyRootfs']
            assert not actual['HostConfig']['Privileged'] and actual['HostConfig']['PidMode']==''
            assert set(actual['NetworkSettings']['Networks'])=={network}
            assert not any('ORACLE2_TEST_ADMIN' in value or 'PASSWORD=' in value for value in actual['Config']['Env'])
            assert {m['Destination'] for m in actual['Mounts']}=={str(source_root),'/etc/hosts',*states,*ca_paths,*external_tls}
            docker('start',name)
            address=json.loads(docker('inspect',name))[0]['NetworkSettings']['Networks'][network]['IPAddress']
            port=stack.enter_context(forward('127.0.0.1',0,target_host=address,target_port=8443))
            tls=x['client'].binding
            from dataclasses import replace
            client=PurposeProviderClientV2(replace(tls,port=port))
            deadline=time.monotonic()+15
            while True:
                try:
                    with socket.create_connection((address,8443),timeout=.2):break
                except OSError:
                    if time.monotonic()>=deadline:raise TimeoutError('working provider did not listen')
                    time.sleep(.05)
            response=client.dispatch(x['job'].dispatch_id,x['job'].request_hash,x['descriptor'].phase_registry_sha256)
            assert len(response)==5 and x['state']['posts']==1
            assert b'PRIVATE_NATIVE_WIRE' not in canonical_bytes(response)
            probe='import os,pathlib,json;assert not pathlib.Path('+repr(str(forbidden))+').exists();assert not pathlib.Path('+repr(str(source_root/'escape-to-sibling'))+').exists();assert os.getuid()==10001;assert not pathlib.Path("/var/run/docker.sock").exists();assert not any("ORACLE2_TEST_ADMIN" in k for k in os.environ);assert "CapEff:\\t0000000000000000" in pathlib.Path("/proc/self/status").read_text();print("isolated")'
            assert docker('exec',name,'python','-c',probe)=='isolated'
            from decimal import Decimal
            with psycopg.connect(x['billing_admin']) as conn:
                assert conn.execute('SELECT r.purpose,s.status,s.actual_usd FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id)').fetchall()==[('source-census','completed',Decimal('.00001'))]
            commit_path=str(x['custody']/(str(x['job'].dispatch_id)+'.phase-commit.json'))
            wire_path=str(x['custody']/(str(x['job'].dispatch_id)+'.wire'))
            sealed=json.loads(docker('exec',name,'python','-c',
                'import pathlib,json,hashlib;from oracle_brain.operating_model.contracts import digest;'+
                'c=json.loads(pathlib.Path('+repr(commit_path)+').read_bytes());'+
                'print(json.dumps({"receipt":digest(c),"wire":hashlib.sha256(pathlib.Path('+repr(wire_path)+').read_bytes()).hexdigest(),"caller":c["actual_caller_login"]}))'))
            assert sealed=={'receipt':response['receipt_hash'],'wire':response['raw_response_hash'],'caller':x['f']['login']}
            # Inspect the ACTUAL mounted tree after successful wire/custody,
            # returning hashes/classes only. Unknown files are a failed proof.
            scan="""import pathlib,hashlib,json,sys
root=pathlib.Path(sys.argv[1]);result=[]
for p in sorted(root.rglob('*')):
 if p.is_symlink():continue
 if p.is_file():result.append({'relative_path':str(p.relative_to(root)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
print(json.dumps(result))
"""
            mounted=json.loads(docker('exec',name,'python','-c',scan,str(source_root)))
            selected_classes={item['relative_path']:item['content_class'] for item in inventory}
            for item in mounted:
                relative=pathlib.Path(item['relative_path'])
                if item['relative_path'] in selected_classes:item['content_class']=selected_classes[item['relative_path']]
                elif relative.parts[0]=='external-tls':item['content_class']='own-provider-TLS-or-database-CA'
                elif relative.parts[0]==pathlib.Path(cfg['observer_spool']).relative_to(source_root).parts[0]:item['content_class']='own-census-replay-metadata'
                elif relative.parts[0]==pathlib.Path(cfg['private_receipts']).relative_to(source_root).parts[0]:
                    assert relative.name.startswith(str(x['job'].dispatch_id))
                    item['content_class']='own-census-private-result'
                else:raise AssertionError('unadmitted file in actual provider mount')
            (output_root/'actual-mount-content-inventory.json').write_text(json.dumps({'schema_version':1,'files':mounted,'raw_complete_parent':False,'sibling_phase':False,'candidate_or_extraction_content':False},sort_keys=True,indent=2)+'\n')
            result={'success':True,'synthetic':True,'installation_admission':False,'network':network,
                'image_id':image_id,'container':name,'uid':10001,'read_only':True,'capabilities':[],
                'mounts':[{'destination':m['Destination'],'writable':m['RW']} for m in actual['Mounts']],
                'tls_san':'localhost','forwarding':'owned bridge gateway TCP bytes only',
                'actual_mount_inventory_sha256':hashlib.sha256((output_root/'actual-mount-content-inventory.json').read_bytes()).hexdigest(),
                'mount_input_inventory_sha256':hashlib.sha256((output_root/'mount-input-inventory.json').read_bytes()).hexdigest(),
                'source_population':len(x['descriptor'].source_refs),'paid_posts':1,'reply_fields':sorted(response)}
            (output_root/'result.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
            return result
    finally:
        if created:
            check=json.loads(docker('inspect',name))[0]
            assert check['Config']['Labels']['oracle.purpose.synthetic']=='true'
            (output_root/'provider.log').write_text(subprocess.check_output(['docker','logs',name],text=True,stderr=subprocess.STDOUT))
            docker('rm','-f',name)
        docker('run','--rm','--network','none','--user','0','--mount',f'type=bind,src={private},dst=/owned',
            '--entrypoint','python',image,'-c',f'import os;\nfor root,dirs,files in os.walk("/owned"):\n os.chown(root,{os.getuid()},{os.getgid()})\n for name in files: os.chown(os.path.join(root,name),{os.getuid()},{os.getgid()},follow_symlinks=False)')
