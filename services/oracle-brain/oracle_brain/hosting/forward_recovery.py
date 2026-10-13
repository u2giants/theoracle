"""Fixed forward-only Docker recovery actuator; exact action review is external.

Importing this module performs no operation. Root must admit each concrete
capture/restore/rebuild/result invocation. No arbitrary shell, SQL, host, path,
image, provider, credential issuance or old namespace is accepted.
"""
import argparse,asyncio,base64,hashlib,io,json,os,re,resource,ssl,stat,subprocess,tarfile,tempfile,time
from psycopg import sql as pg_sql
from pathlib import Path,PurePosixPath
from uuid import uuid4
from .restore_receipts import Backup,Instance,Service,ROLES,RUNNING,MAX_TOTAL,require,validate_instance,validate_services,verify_bundle,read_protected
from .synthetic_fixture import fixture,fixed_scenario,FORWARD_SCENARIO
from .synthetic_seed import compile_restore_roles
from .runtime import protected_file,settings,sealed_scenario
from oracle_brain.operating_model.contracts import canonical_bytes,digest

MAX_FILE=512*1024**2
META_TEMPLATE='{"id":{{json .Id}},"name":{{json .Name}},"application":{{json (index .Config.Labels "coolify.applicationUuid")}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},"role":{{json (index .Config.Labels "com.docker.compose.service")}},"image":{{json .Config.Image}},"state":{{json .State.Status}},"networks":"{{range .NetworkSettings.Networks}}{{.NetworkID}} {{end}}","mounts":"{{range .Mounts}}{{.Type}}:{{.Name}}:{{.Destination}} {{end}}"}'


class BoundedDocker:
    def __call__(self,args,*,data=None,bound=MAX_FILE,timeout=60):
        validate_docker_command(args)
        require(bound in (8192,1024*1024,MAX_FILE,MAX_TOTAL) and timeout in (5,30,60,90),'unreviewed recovery budget denied')
        def limited():resource.setrlimit(resource.RLIMIT_FSIZE,(bound,bound))
        with tempfile.TemporaryFile() as output:
            result=subprocess.run(['/usr/bin/docker',*args],input=data,stdout=output,stderr=subprocess.DEVNULL,timeout=timeout,
              env={'PATH':'/usr/bin:/bin','LANG':'C'},preexec_fn=limited,start_new_session=True)
            require(result.returncode==0,'bounded recovery operation failed')
            output.seek(0);raw=output.read(bound+1)
            require(len(raw)<=bound,'recovery output bound exceeded')
            return raw

def validate_docker_command(args):
    """Closed command grammar; no extra flags, commands or filesystem paths."""
    cid=lambda value: isinstance(value,str) and re.fullmatch(r'[0-9a-f]{64}',value)
    valid=False
    if args[:3]==['inspect','--format',META_TEMPLATE]:
        valid=len(args)==4 and cid(args[3])
    elif args and args[0]=='start':
        valid=(len(args)==2 and cid(args[1])) or (len(args)==3 and args[1]=='-a' and cid(args[2]))
    elif args and args[0]=='cp':
        ref=lambda value,paths: isinstance(value,str) and ':' in value and cid(value.split(':',1)[0]) and value.split(':',1)[1] in paths
        valid=(len(args)==3 and args[2]=='-' and ref(args[1],('/run/oracle-jobs/.','/run/oracle-blobs/.')))
        valid=valid or (len(args)==4 and args[1:3]==['-a','-'] and ref(args[3],('/run/oracle-jobs','/run/oracle-blobs')))
    elif args and args[0]=='exec':
        tail=args[1:]
        if tail and tail[0]=='-i':tail=tail[1:]
        if tail[:2]==['--env','PGOPTIONS=-c statement_timeout=20000 -c lock_timeout=5000']:tail=tail[2:]
        if tail and cid(tail[0]):
            program=tail[1:]
            valid=program in [
              ['timeout','--help'],
              ['timeout','-s','TERM','-k','5','15','psql','-X','-q','-A','-t','-v','ON_ERROR_STOP=1','-U','oracle_bootstrap','-d','oracle_synthetic'],
              ['timeout','-s','TERM','-k','5','40','pg_dump','--format=custom','-U','oracle_bootstrap','-d','oracle_synthetic'],
              ['timeout','-s','TERM','-k','5','15','pg_restore','--list'],
              ['timeout','-s','TERM','-k','5','40','pg_restore','--exit-on-error','--single-transaction','-U','oracle_bootstrap','-d','oracle_synthetic'],
              ['python','-m','oracle_brain.hosting.forward_recovery','sdk-reload']]
    require(bool(valid),'unreviewed Docker command denied')

def sql_literal(value):
    return pg_sql.Literal(str(value)).as_string()


def unpack(raw,*,metadata=False):
    require(len(raw)<=MAX_TOTAL,'archive bound exceeded')
    files={};total=0;meta={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        for member in archive:
            name=member.name
            while name.startswith('./'):name=name[2:]
            if name in ('','.'):continue
            path=PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and str(path)==name,'archive path denied')
            require(member.isdir() or member.isfile(),'archive link/device denied')
            if member.isdir():continue
            require(name not in files and len(files)<128 and member.size<=MAX_FILE,'archive member/count denied')
            total+=member.size;require(total<=MAX_TOTAL,'archive aggregate denied')
            require(member.uid==10001 and member.mode in (0o600,0o644),'archive ownership/mode differs')
            require(member.mode==0o600 or name=='.custody-lock','nonprivate archive member denied')
            meta[name]={'uid':member.uid,'mode':member.mode,'consumed_at':int(member.mtime)}
            files[name]=archive.extractfile(member).read(member.size+1)
            require(len(files[name])==member.size,'archive member truncated')
    return (files,meta) if metadata else files


def pack(files,modes=None):
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as archive:
        for name,raw in sorted(files.items()):
            path=PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and str(path)==name,'restore path denied')
            item=tarfile.TarInfo(name);item.size=len(raw);item.mode=(modes or {}).get(name,0o600);require(item.mode==0o600 or (name=='.custody-lock' and item.mode==0o644),'restore mode denied');item.uid=item.gid=10001
            archive.addfile(item,io.BytesIO(raw))
    require(stream.tell()<=MAX_TOTAL,'restore archive bound exceeded')
    return stream.getvalue()


def owned_directory(path):
    path=Path(path).absolute();fd=os.open(path.anchor,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            nextfd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nextfd
        info=os.fstat(fd)
        require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'coordinator directory custody differs')
        return fd
    except BaseException:os.close(fd);raise


def capture_preflight(root):
    import re
    root=Path(root).absolute();parent=root.parent
    require(os.environ.get('TMPDIR') and parent==Path(os.environ['TMPDIR']).absolute(),'capture parent is outside coordinator custody')
    require(re.fullmatch(r'oracle-forward-capture-[a-z0-9][a-z0-9-]{0,63}',root.name),'exact forward capture leaf required')
    fd=owned_directory(parent)
    try:
        for leaf in (root.name,root.name+'.manifest.json'):
            try:os.stat(leaf,dir_fd=fd,follow_symlinks=False)
            except FileNotFoundError:continue
            raise PermissionError('existing capture or manifest leaf denied')
        info=os.fstat(fd);return (info.st_dev,info.st_ino)
    finally:os.close(fd)


def save(root,name,raw,*,root_fd=None):
    # Never chmod any existing parent; every write is anchored to owned dirfds.
    path=PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and str(path)==name,'unsafe custody output denied')
    directory=os.dup(root_fd) if root_fd is not None else owned_directory(root)
    try:
        for part in path.parts[:-1]:
            try:os.mkdir(part,0o700,dir_fd=directory)
            except FileExistsError:pass
            nextfd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            info=os.fstat(nextfd)
            if not (info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700):
                os.close(nextfd);raise PermissionError('nested output custody differs')
            os.close(directory);directory=nextfd
        fd=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.fsync(directory)
    finally:os.close(directory)


class ForwardRecovery:
    def __init__(self,backup:Backup,*,runner=None,clock=time.time):
        from .restore_receipts import validate_backup
        validate_backup(backup)
        self.backup=backup;self.run=runner or BoundedDocker();self.clock=clock
        self.scenario=fixed_scenario(FORWARD_SCENARIO)

    def fresh(self):
        require(self.backup.authority.issued_at<=self.clock()<self.backup.authority.expires_at,'original forward authority expired; no renewal')

    def checked(self,args,**kwargs):
        self.fresh();budget=kwargs.get('timeout',60)
        require(self.clock()+budget+15<self.backup.authority.expires_at,'insufficient original lifetime for bounded command')
        result=self.run(args,**kwargs);self.fresh();return result

    def prove_namespace(self,instance,services,*,quiesced=False,phase="source"):
        self.fresh();validate_instance(instance)
        require(phase in {'source','restore','rebuild','reload'},'unreviewed recovery phase denied')
        if phase=='source':validate_services(services,self.backup.image)
        else:
            require(all(services[role].state=='running' for role in ('ledger','candidate','confirmed')),'restore storage must be running')
            delayed={'ledger-init','gateway','executor','synthetic-project'}
            require(all(services[role].state=='exited' for role in ROLES if role not in RUNNING and role not in delayed),'restore bootstrap completion unproved')
            normalized={role:Service.model_validate({**value.model_dump(),'state':'running' if role in RUNNING else 'exited'}) for role,value in services.items()}
            validate_services(normalized,self.backup.image)
            require(instance.application!=self.backup.instance.application,'original mutable phase denied')
            require(services['ledger-init'].state=='created','restore seed profile must remain unstarted')
        require(instance.ledger_container==services['ledger'].container_id,'ledger binding differs')
        seen_networks=set()
        for role in ROLES:
            row=json.loads(self.checked(['inspect','--format',META_TEMPLATE,services[role].container_id],bound=8192,timeout=5))
            networks=row.pop('networks').split();mounts=row.pop('mounts').split()
            seen_networks.update(networks)
            require(set(networks)<=set(instance.networks),'actual original/foreign network denied')
            expected_mounts={'ledger':[(instance.ledger_volume,'/var/lib/postgresql/data')],'candidate':[(instance.candidate_volume,'/var/lib/falkordb/data')],'confirmed':[(instance.confirmed_volume,'/var/lib/falkordb/data')],'gateway':[(instance.spool_volume,'/run/oracle-jobs')],'executor':[(instance.spool_volume,'/run/oracle-jobs'),(instance.blob_volume,'/run/oracle-blobs')],'synthetic-project':[(instance.blob_volume,'/run/oracle-blobs')]}
            require(all(m.startswith('volume:'+instance.project+'_') for m in mounts),'actual foreign/bind mount denied')
            require(all('volume:'+name+':'+destination in mounts for name,destination in expected_mounts.get(role,[])),'actual store mount binding differs')
            state=services[role].state
            if phase=='source' and quiesced and role in {'gateway','executor'}:state='exited'
            if phase=='reload' and role=='synthetic-project':state='exited'
            if phase!='source' and role in {'gateway','executor','synthetic-project'}:
                require(services[role].state in {'created','exited'},'recovery runtime was started prematurely')
            require(row=={'id':services[role].container_id,'name':'/'+instance.project+'-'+role+'-1','application':instance.application,
              'project':instance.project,'role':role,'image':services[role].image,'state':state},'actual target namespace/image/state differs')

        require(seen_networks==set(instance.networks),'actual network closure incomplete')
        tools=self.checked(['exec',instance.ledger_container,'timeout','--help'],bound=8192,timeout=5)
        require(b'-k' in tools and b'-s' in tools,'in-container timeout capability unproved')

    def sql(self,instance,query):
        self.fresh()
        return self.checked(['exec','-i','--env','PGOPTIONS=-c statement_timeout=20000 -c lock_timeout=5000',instance.ledger_container,'timeout','-s','TERM','-k','5','15','psql','-X','-q','-A','-t','-v','ON_ERROR_STOP=1','-U','oracle_bootstrap','-d','oracle_synthetic'],data=query.encode(),bound=1024*1024,timeout=30)

    def capture(self,root,roles_bundle,*,operation_receipt_sha256):
        """Source writer quiescence must already be admitted and observed."""
        identity=capture_preflight(root)
        b=self.backup;self.prove_namespace(b.instance,b.services,quiesced=True)
        require(hashlib.sha256(roles_bundle).hexdigest()==b.files['roles.bundle'].sha256,'original protected role bundle differs')
        params=json.loads(roles_bundle);compile_restore_roles(params)
        require(params['source_role_registry_hash']==b.authority.source_registry_sha256 and params['runtime_hash']==b.runtime_hash and params['review_hash']==b.review_hash,'original role/runtime association differs')
        from datetime import datetime
        require(int(datetime.fromisoformat(params['expires_at']).timestamp())==b.authority.expires_at,'role authority expiry differs')
        inventory=self.sql(b.instance,"SELECT (SELECT marker FROM oracle2.synthetic_hosting_marker)='public-invented-remote-forward-v2' AND (SELECT count(*) FROM oracle2.sources)=2 AND (SELECT count(*) FROM oracle2.operating_view_runs)=1 AND (SELECT count(*) FROM oracle2.sources WHERE workspace_id="+sql_literal(self.scenario.workspace)+")=2 AND (SELECT status FROM oracle2.operating_view_runs WHERE run_id="+sql_literal(b.job_id)+")='completed';")
        require(inventory.strip()==b't','fixed forward-only source population unproved')
        dump=self.checked(['exec',b.instance.ledger_container,'timeout','-s','TERM','-k','5','40','pg_dump','--format=custom','-U','oracle_bootstrap','-d','oracle_synthetic'],bound=MAX_FILE,timeout=60)
        require(dump.startswith(b'PGDMP'),'custom archive missing')
        listing=self.checked(['exec','-i',b.instance.ledger_container,'timeout','-s','TERM','-k','5','15','pg_restore','--list'],data=dump,bound=1024*1024,timeout=30)
        expected_tables=['appointments','artifact_dependencies','artifact_manifests','drafts','hosting_role_runtime_admissions','hosting_role_source_admissions','operating_model_change_log','operating_model_source_receipts','operating_release_manifests','operating_release_selectors','operating_view_pack_receipts','operating_view_runs','source_blocks','sources','synthetic_hosting_marker']
        require(all((' TABLE oracle2 '+table+' ') in listing.decode() for table in expected_tables),'actual archive TOC incomplete')
        state=json.loads(self.sql(b.instance,"SELECT jsonb_build_object('state',status,'watermark',(SELECT max(sequence) FROM oracle2.operating_model_change_log),'result_hex',(SELECT encode(canonical_pack,'hex') FROM oracle2.operating_view_pack_receipts WHERE run_id="+sql_literal(b.job_id)+"),'sources',(SELECT jsonb_agg(receipt ORDER BY source_id) FROM oracle2.operating_model_source_receipts)) FROM oracle2.operating_view_runs WHERE run_id="+sql_literal(b.job_id)+";"))
        require(state['state']=='completed' and state['watermark']==11,'completed canonical ledger unavailable')
        spools,spoolmeta=unpack(self.checked(['cp',b.services['gateway'].container_id+':/run/oracle-jobs/.','-'],bound=MAX_TOTAL),metadata=True)
        blobs=unpack(self.checked(['cp',b.services['executor'].container_id+':/run/oracle-blobs/.','-'],bound=MAX_TOTAL))
        corpus={'ledger.dump':dump,'roles.bundle':roles_bundle,'sources.json':canonical_bytes({'receipts':state['sources']}),'result.json':bytes.fromhex(state['result_hex'])}
        corpus.update({'spool/'+k:v for k,v in spools.items()});corpus.update({'blobs/'+k:v for k,v in blobs.items()})
        corpus['ledger.toc.json']=canonical_bytes({'schema':'oracle-forward-dump-toc/v1','archive_sha256':hashlib.sha256(dump).hexdigest(),'format':'custom','server_major':16,'database':'oracle_synthetic','required_table_names':expected_tables})
        corpus['roles-bootstrap.json']=canonical_bytes({'schema':'oracle-forward-role-bootstrap/v1','source_head':b.source_head,'runtime_hash':b.runtime_hash,'source_registry_sha256':b.authority.source_registry_sha256,'dump_toc_sha256':hashlib.sha256(corpus['ledger.toc.json']).hexdigest(),'role_bundle_sha256':hashlib.sha256(roles_bundle).hexdigest(),
          'roles':{'oracle_synthetic_gateway':'oracle2_gateway_metadata','oracle_synthetic_executor':'oracle2_documentary_executor','oracle_synthetic_projector':'oracle2_documentary_executor'},'login_privileges':'NOINHERIT,NOSUPERUSER,NOCREATEDB,NOCREATEROLE,NOBYPASSRLS'})
        require(operation_receipt_sha256==b.backup_operation_receipt_sha256,'capture action receipt differs')
        root=Path(root).absolute();parent_fd=owned_directory(root.parent)
        output_fd=None
        try:
            parent_info=os.fstat(parent_fd)
            require((parent_info.st_dev,parent_info.st_ino)==identity,'capture parent changed after preflight')
            os.mkdir(root.name,0o700,dir_fd=parent_fd)
            output_fd=os.open(root.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent_fd)
            require(set(corpus)==set(b.files),'captured corpus population differs')
            seals={}
            for name,data in corpus.items():
                mode=spoolmeta.get(name.removeprefix('spool/'),{}).get('mode',0o600) if name.startswith('spool/') else 0o600
                seals[name]={'sha256':hashlib.sha256(data).hexdigest(),'size':len(data),'runtime_uid':10001 if name.startswith(('spool/','blobs/')) else 0,'runtime_mode':mode}
                save(root,name,data,root_fd=output_fd)
            nonces=[]
            for nonce in b.nonces:
                value=nonce.model_dump();value['consumed_at']=spoolmeta['nonce-'+nonce.request.nonce]['consumed_at'];nonces.append(value)
            actual=Backup.model_validate({**b.model_dump(),'captured_at':int(self.clock()),'files':seals,'nonces':nonces,
              'dump_toc_sha256':seals['ledger.toc.json']['sha256'],'role_bootstrap_sha256':seals['roles-bootstrap.json']['sha256'],'result_sha256':seals['result.json']['sha256']})
            checked=verify_bundle(root,actual)
            save(root.parent,root.name+'.manifest.json',canonical_bytes(actual.model_dump()),root_fd=parent_fd)
            self.backup=actual
            return actual,checked
        finally:
            if output_fd is not None:os.close(output_fd)
            os.close(parent_fd)

    def restore(self,root,target:Instance,services,*,operation_receipt_sha256):
        """Exact new empty platform instance only; no source seed/data replay."""
        b=self.backup;verify_bundle(root,b);self.prove_namespace(target,services,quiesced=True,phase="restore")
        require(target.application!=b.instance.application and target.ledger_container!=b.instance.ledger_container,'same instance denied')
        require(set(target.networks).isdisjoint(b.instance.networks),'original network denied')
        require({target.ledger_volume,target.spool_volume,target.blob_volume,target.candidate_volume,target.confirmed_volume}.isdisjoint({b.instance.ledger_volume,b.instance.spool_volume,b.instance.blob_volume,b.instance.candidate_volume,b.instance.confirmed_volume}),'original mounts denied')
        empty=self.sql(target,"SELECT current_database()='oracle_synthetic' AND current_user='oracle_bootstrap' AND NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast' AND c.relkind IN ('r','p','v','m','S')); ")
        require(empty.strip()==b't','empty dedicated restore database unproved')
        for role,path in (('gateway','/run/oracle-jobs/.'),('executor','/run/oracle-blobs/.')):
            existing=unpack(self.checked(['cp',services[role].container_id+':'+path,'-'],bound=MAX_TOTAL))
            require(not existing or (role=='gateway' and existing=={'.custody-lock':b''}),'empty target corpus unproved')
        params=json.loads(read_protected(root,'roles.bundle',b.files['roles.bundle']))
        self.sql(target,compile_restore_roles(params))
        dump=read_protected(root,'ledger.dump',b.files['ledger.dump'])
        self.fresh();self.checked(['exec','-i','--env','PGOPTIONS=-c statement_timeout=20000 -c lock_timeout=5000',target.ledger_container,'timeout','-s','TERM','-k','5','40','pg_restore','--exit-on-error','--single-transaction','-U','oracle_bootstrap','-d','oracle_synthetic'],data=dump,bound=1024*1024,timeout=60)
        for prefix,role,path in (('spool/','gateway','/run/oracle-jobs'),('blobs/','executor','/run/oracle-blobs')):
            files={name[len(prefix):]:read_protected(root,name,b.files[name]) for name in b.files if name.startswith(prefix)}
            self.fresh();self.checked(['cp','-a','-',services[role].container_id+':'+path],data=pack(files,{name[len(prefix):]:b.files[name].runtime_mode for name in b.files if name.startswith(prefix)}),bound=8192,timeout=60)
            readback,metadata=unpack(self.checked(['cp',services[role].container_id+':'+path+'/.','-'],bound=MAX_TOTAL),metadata=True)
            require(all(metadata[name]['uid']==10001 and metadata[name]['mode']==b.files[prefix+name].runtime_mode for name in files),'restored ownership/mode parity failed')
            require(readback==files,'fresh restore corpus byte parity failed')
        state=json.loads(self.sql(target,"SELECT jsonb_build_object('state',status,'result_hex',(SELECT encode(canonical_pack,'hex') FROM oracle2.operating_view_pack_receipts WHERE run_id="+sql_literal(b.job_id)+")) FROM oracle2.operating_view_runs WHERE run_id="+sql_literal(b.job_id)+";"))
        require(state['state']=='completed' and hashlib.sha256(bytes.fromhex(state['result_hex'])).hexdigest()==b.result_sha256,'restored result differs')
        return {'fresh_restore_bytes_verified':True,'operation_receipt_sha256':operation_receipt_sha256,'hosted_accepted':False,'business_accepted':False,'serving_accepted':False}

    def rebuild(self,target,services):
        """Only the NEW target's fixed one-shot projector may run; never source."""
        self.prove_namespace(target,services,quiesced=True,phase="rebuild")
        require(target.application!=self.backup.instance.application,'original projector replay denied')
        raw=self.checked(['start','-a',services['synthetic-project'].container_id],bound=8192,timeout=90)
        result=json.loads(raw)
        _,_,_,manifest,release=fixture(self.backup.runtime_hash,self.backup.review_hash,FORWARD_SCENARIO)
        require(result.get('finalized') is True and result.get('artifact_hash')==manifest.content_hash and result.get('record_digest')==release.graph_record_digest,'stock SDK fresh build differs')
        return {'sdk_rebuild_response_sha256':hashlib.sha256(raw).hexdigest(),'hosted_accepted':False,'business_accepted':False,'serving_accepted':False}

    def reload(self,target,services):
        # A separate process loads through the documentary executor's restricted
        # graph credential, never through the projector's writer credential.
        self.prove_namespace(target,services,quiesced=True,phase="reload")
        require(target.application!=self.backup.instance.application,'original runtime replay denied')
        self.fresh();self.checked(['start',services['executor'].container_id],bound=8192,timeout=30)
        self.fresh();raw=self.checked(['exec',services['executor'].container_id,'python','-m','oracle_brain.hosting.forward_recovery','sdk-reload'],bound=8192,timeout=60)
        response=json.loads(raw)
        expected=fixture(self.backup.runtime_hash,self.backup.review_hash,FORWARD_SCENARIO)
        require(response.get('reload_verified') is True and response.get('sdk_version')=='1.4.0' and response.get('artifact_hash')==expected[3].content_hash and response.get('record_digest')==expected[4].graph_record_digest,'independent stock SDK restricted reload differs')
        return {'sdk_reload_response_sha256':hashlib.sha256(raw).hexdigest(),'hosted_accepted':False,'business_accepted':False,'serving_accepted':False}


def arm_native_budget(config,*,seconds):
    import signal
    scenario=sealed_scenario(config)
    require(scenario.scenario_id==FORWARD_SCENARIO and seconds in (45,80),'fixed native budget required')
    policy=json.loads(protected_file(config['registry']))
    require(set(policy)=={'worker_uri','runtime_hash','active','expires_at','allowed_release_hashes'} and policy.get('runtime_hash')==config['runtime_hash'] and policy.get('allowed_release_hashes')==config['allowed_release_hashes'] and digest(policy)==config['registry_hash'] and policy.get('active') is True and policy.get('worker_uri')==scenario.worker_uri,'unchanged original policy required')
    require(time.time()+seconds+15<policy['expires_at'],'insufficient original native operation lifetime')
    signal.signal(signal.SIGALRM,signal.SIG_DFL);signal.alarm(seconds)


async def reload_only(config):
    """In-image separate stock SDK read-only load; never generation or job run."""
    scenario=sealed_scenario(config);require(scenario.scenario_id==FORWARD_SCENARIO,'forward reload only')
    from oracle_brain.operating_model.artifact_storage import FileBlobStore
    from oracle_brain.operating_model.authority_adapter import PostgresSources
    from oracle_brain.operating_model.ledger import Ledger
    from oracle_brain.operating_model.sdk_projection import SDKProjection
    from oracle_brain.operating_model.runtime import NoGeneration,SyntheticEmbedding
    sources=PostgresSources(config['_database_url'],source_binding=config['_source_binding'])
    ledger=Ledger(config['_database_url'],FileBlobStore(Path(config['blob_root'])),principal=scenario.actor,can_read=sources.can_read,current_source=sources.current)
    expected=fixture(config['runtime_hash'],config['synthetic_review_hash'],FORWARD_SCENARIO)
    projection=SDKProjection(protected_file(config['graph_url_file']).decode().strip(),workspace_id=scenario.workspace,artifact_id=scenario.artifact,artifact_version=1,generation=scenario.generation,llm=NoGeneration(),embedder=SyntheticEmbedding(),dimensions=8,read_only=True)
    try:
        loaded=await projection.load(ledger,scenario.workspace,scenario.artifact,1)
        require(canonical_bytes(loaded)==canonical_bytes(expected[2]),'independent SDK reload differs')
        return {'sdk_version':'1.4.0','artifact_hash':expected[3].content_hash,'record_digest':expected[4].graph_record_digest,'reload_verified':True,'hosted_accepted':False,'business_accepted':False,'serving_accepted':False}
    finally:await projection.close()


def load_verified_client_chain(context,cert,key):
    # Load the already verified bytes through immutable kernel descriptors;
    # never re-open a mutable custody path between pinning and the handshake.
    import fcntl
    descriptors=[]
    try:
        for name,raw in (('oracle-forward-client-cert',cert),('oracle-forward-client-key',key)):
            fd=os.memfd_create(name,os.MFD_CLOEXEC|os.MFD_ALLOW_SEALING);descriptors.append(fd)
            os.fchmod(fd,0o600);require(os.write(fd,raw)==len(raw),'client identity descriptor write incomplete')
            # Linux UAPI fcntl.h: BASE1024+9/+10, seal flags0x0001..0x0008.
            # Some supported Python builds omit these names; kernel sealing
            # remains mandatory and is independently read back, never skipped.
            fcntl.fcntl(fd,getattr(fcntl,'F_ADD_SEALS',1033),0x000f)
            require(fcntl.fcntl(fd,getattr(fcntl,'F_GET_SEALS',1034))==0x000f,'immutable client identity unproved')
        context.load_cert_chain('/proc/self/fd/'+str(descriptors[0]),'/proc/self/fd/'+str(descriptors[1]))
    finally:
        for fd in descriptors:os.close(fd)


def collect_native_result(backup,worker_root,*,hostname,port,expected_sha256,clock=time.time):
    """Result-only independent mTLS/HMAC delivery; never enqueue/replay a job."""
    from .gateway import signature_message
    import hmac,socket
    from cryptography import x509
    from cryptography.x509.oid import ExtensionOID
    require(backup.authority.issued_at<=clock()<backup.authority.expires_at,'original result authority expired')
    require(hostname=='gateway' and port==8443,'reviewed namespace-local result endpoint only')
    scenario=fixed_scenario(FORWARD_SCENARIO)
    root=Path(worker_root);cert=protected_file(root/'server.crt');key=protected_file(root/'server.key');ca=protected_file(root/'ca.crt');signing=protected_file(root/'hmac-key')
    certificate=x509.load_pem_x509_certificate(cert)
    uris=certificate.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value.get_values_for_type(x509.UniformResourceIdentifier)
    require(uris==[scenario.worker_uri] and hashlib.sha256(cert).hexdigest()==backup.authority.certificate_sha256,'worker certificate differs')
    require(len(signing)>=32,'fixed signing key unavailable')
    context=ssl.create_default_context(cadata=ca.decode());context.minimum_version=ssl.TLSVersion.TLSv1_3
    context.verify_mode=ssl.CERT_REQUIRED;context.check_hostname=True
    load_verified_client_chain(context,cert,key)
    expiry=min(int(clock())+30,backup.authority.expires_at-1)
    require(expiry>clock(),'fresh result envelope unavailable')
    body=canonical_bytes({'job_id':backup.job_id,'runtime_hash':backup.runtime_hash,'admission_hash':fixture(backup.runtime_hash,backup.review_hash,FORWARD_SCENARIO)[-1].documentary_gate_hash,'nonce':str(uuid4()),'expires_at':expiry})
    signature=hmac.new(signing,signature_message('POST','/v1/jobs/result',body),hashlib.sha256).hexdigest()
    request=b'POST /v1/jobs/result HTTP/1.0\r\nHost: gateway\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body)).encode()+b'\r\nX-Oracle-Job-Signature: '+signature.encode()+b'\r\n\r\n'+body
    deadline=time.monotonic()+15
    require(clock()+30+15<backup.authority.expires_at,'insufficient original result operation lifetime')
    with context.wrap_socket(socket.create_connection((hostname,port),timeout=5),server_hostname='gateway') as sock:
        sock.settimeout(5);sock.sendall(request);reply=b''
        while True:
            remaining=deadline-time.monotonic();require(remaining>0,'native result wall budget exceeded')
            sock.settimeout(min(5,remaining))
            part=sock.recv(8192)
            if not part:break
            reply+=part;require(len(reply)<=140000,'native delivery bound exceeded')
    require(clock()<backup.authority.expires_at,'original result authority expired during delivery')
    header,delivered=reply.split(b'\r\n\r\n',1)
    require(header.startswith(b'HTTP/1.0 200 ') or header.startswith(b'HTTP/1.1 200 '),'native completed result denied')
    require(hashlib.sha256(delivered).hexdigest()==expected_sha256==backup.result_sha256,'native result exact bytes differ')
    return {'result_sha256':expected_sha256,'opaque_request_sha256':hashlib.sha256(body).hexdigest(),'native_response_sha256':hashlib.sha256(reply).hexdigest(),'hosted_accepted':False,'business_accepted':False,'serving_accepted':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('capture','restore','rebuild','reload','sdk-reload','result'))
    parser.add_argument('--backup');parser.add_argument('--bundle');parser.add_argument('--roles-bundle')
    parser.add_argument('--target');parser.add_argument('--operation-receipt-sha256');parser.add_argument('--worker-root')
    args=parser.parse_args(argv)
    try:
        if args.operation=='sdk-reload':
            config=settings('executor','/run/oracle-auth/settings.json',os.environ.get('ORACLE_HOSTING_SETTINGS_SHA256',''))
            arm_native_budget(config,seconds=45)
            result=asyncio.run(reload_only(config))
        else:
            backup=Backup.model_validate_json(protected_file(args.backup))
            operator=ForwardRecovery(backup)
            if args.operation=='capture':
                capture_preflight(args.bundle)
                actual,result=operator.capture(args.bundle,protected_file(args.roles_bundle),operation_receipt_sha256=args.operation_receipt_sha256)
                result['backup_manifest_sha256']=digest(actual.model_dump())
            elif args.operation=='result':result=collect_native_result(backup,args.worker_root,hostname='gateway',port=8443,expected_sha256=backup.result_sha256)
            else:
                target=json.loads(protected_file(args.target))
                require(set(target)=={'instance','services'},'exact restore target descriptor required')
                instance=Instance.model_validate(target['instance']);services={k:Service.model_validate(v) for k,v in target['services'].items()}
                if args.operation=='restore':result=operator.restore(args.bundle,instance,services,operation_receipt_sha256=args.operation_receipt_sha256)
                elif args.operation=='rebuild':result=operator.rebuild(instance,services)
                else:result=operator.reload(instance,services)
        print(json.dumps(result,sort_keys=True));return 0
    except Exception:
        print('fixed forward recovery refused; authority unchanged',file=__import__('sys').stderr);return 3

if __name__=='__main__':raise SystemExit(main())
