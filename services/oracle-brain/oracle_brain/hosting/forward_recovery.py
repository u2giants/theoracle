"""Fixed forward-only Docker recovery actuator; exact action review is external.

Importing this module performs no operation. Root must admit each concrete
capture/restore/rebuild/result invocation. No arbitrary shell, SQL, host, path,
image, provider, credential issuance or old namespace is accepted.
"""
import argparse,asyncio,base64,hashlib,io,json,os,re,resource,ssl,stat,subprocess,tarfile,tempfile,time
from psycopg import sql as pg_sql
from pathlib import Path,PurePosixPath
from uuid import uuid4
from contextlib import contextmanager
from .restore_receipts import Backup,Instance,Service,ROLES,RUNNING,MAX_TOTAL,require,validate_instance,validate_services,verify_bundle,read_protected
from .synthetic_fixture import fixture,fixed_scenario,FORWARD_SCENARIO
from .synthetic_seed import compile_restore_roles
from .runtime import protected_file,settings,sealed_scenario
from oracle_brain.operating_model.contracts import canonical_bytes,digest

MAX_FILE=512*1024**2
META_TEMPLATE='{"id":{{json .Id}},"name":{{json .Name}},"application":{{json (index .Config.Labels "coolify.applicationUuid")}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},"role":{{json (index .Config.Labels "com.docker.compose.service")}},"image":{{json .Config.Image}},"state":{{json .State.Status}},"network_mode":{{json .HostConfig.NetworkMode}},"networks":"{{range $name,$net := .NetworkSettings.Networks}}{{$name}}:{{$net.NetworkID}} {{end}}","mounts":"{{range .Mounts}}{{.Type}}:{{.Name}}:{{.Destination}} {{end}}"}'
NETWORK_TEMPLATE='{"id":{{json .Id}},"name":{{json .Name}},"driver":{{json .Driver}},"internal":{{json .Internal}},"ipv6":{{json .EnableIPv6}}}'
NETWORK_ROLES=('ingress','jobs','ledger','candidate','confirmed')
ROLE_NETWORKS={'ledger':(2,),'candidate':(3,),'confirmed':(4,),'synthetic-project':(2,3),'executor':(1,2,3),'gateway':(0,1,2)}
def network_name(instance,index):return instance.application if index==0 else instance.project+'_'+NETWORK_ROLES[index]



class BoundedDocker:
    def __call__(self,args,*,data=None,bound=MAX_FILE,timeout=60):
        validate_docker_command(args)
        require(bound in (8192,1024*1024,MAX_FILE,MAX_TOTAL) and timeout in (5,30,60,90),'unreviewed recovery budget denied')
        return _bounded_docker_execution_v1(args,data=data,bound=bound,timeout=timeout)


def _bounded_docker_execution_v1(args,*,data,bound,timeout):
    """Private shared bounded execution body; public owners fix their grammar.

    Never writes stderr, environment, credentials or native secret bytes into
    logs. The existing BoundedDocker validates its UNCHANGED grammar/budgets
    before entering. New current-recovery operations require their own concrete
    SQL/custody owner and fixed command builders; this helper grants nothing.
    """
    with tempfile.TemporaryFile() as output:
        result=_run_bounded_docker_v1(args,data=data,output=output,bound=bound,timeout=timeout)
        require(result.returncode==0,'bounded recovery operation failed')
        output.seek(0);raw=output.read(bound+1)
        require(len(raw)<=bound,'recovery output bound exceeded')
        return raw

def _run_bounded_docker_v1(args,*,data,output,bound,timeout):
    # Single actual subprocess owner. Public old grammar and new fixed native
    # builders remain separate; no callback/argv/file descriptor is wire input.
    def limited():resource.setrlimit(resource.RLIMIT_FSIZE,(bound,bound))
    return subprocess.run(['/usr/bin/docker',*args],input=data,stdout=output,stderr=subprocess.DEVNULL,timeout=timeout,
      env={'PATH':'/usr/bin:/bin','LANG':'C'},preexec_fn=limited,start_new_session=True)


def _bounded_docker_to_retained_fd_v1(args,*,output_fd,expected_file,bound,timeout,data=None):
    """Private native staging only; incomplete actual bytes remain retained.

    The concrete producer has already exclusively created the fixed operation/
    participant file under current custody. This function never creates a file,
    selects a path, accepts an API fd, retries, unlinks, renames, or reads private
    output after expiry. Zero native exit is not backup/restore completion.
    """
    from ..operating_model.recovery_contracts_v1 import RecoveryPrivateFileV1
    from ..operating_model.request_deadline_v1 import request_remaining_v1
    require(type(expected_file) is RecoveryPrivateFileV1 and type(output_fd) is int,'exact already-created private staging handle required')
    RecoveryPrivateFileV1.model_validate(expected_file.model_dump())
    require(type(bound) is int and bound in (1024**2,MAX_FILE) and type(timeout) in (int,float) and not isinstance(timeout,bool) and 0<timeout<=min(30,request_remaining_v1()),'original bounded native output window required')
    before=os.fstat(output_fd)
    require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size==0 and os.lseek(output_fd,0,os.SEEK_CUR)==0 and (before.st_dev,before.st_ino,before.st_uid,stat.S_IMODE(before.st_mode))==(expected_file.device,expected_file.inode,expected_file.uid,expected_file.mode),'actual exclusive private native staging file differs')
    named=os.stat(expected_file.path,follow_symlinks=False)
    require(stat.S_ISREG(named.st_mode) and named.st_nlink==1 and (named.st_dev,named.st_ino,named.st_uid,stat.S_IMODE(named.st_mode))==(before.st_dev,before.st_ino,before.st_uid,stat.S_IMODE(before.st_mode)),'retained native fd differs from exact precreated pathname')
    require(expected_file.sha256==hashlib.sha256(b'').hexdigest(),'native staging starts with actual empty file')
    outcome={'transport_status':'UNKNOWN','returncode':None,'timed_out':False,'automatic_retry_allowed':False}
    with os.fdopen(os.dup(output_fd),'wb',buffering=0) as output:
        try:
            result=_run_bounded_docker_v1(args,data=data,output=output,bound=bound,timeout=timeout)
        except subprocess.TimeoutExpired:
            outcome['timed_out']=True
            return outcome
        require(type(result.returncode) is int,'actual native process result required')
        outcome['returncode']=result.returncode
        if result.returncode==0:
            try:request_remaining_v1()
            except PermissionError:return outcome
            after=os.fstat(output_fd)
            if after.st_size<=bound and after.st_nlink==1 and (after.st_dev,after.st_ino,after.st_uid,stat.S_IMODE(after.st_mode))==(expected_file.device,expected_file.inode,expected_file.uid,expected_file.mode):outcome['transport_status']='process-exited-zero'
        return outcome


def validate_docker_command(args):
    """Closed command grammar; no extra flags, commands or filesystem paths."""
    cid=lambda value: isinstance(value,str) and re.fullmatch(r'[0-9a-f]{64}',value)
    valid=False
    if args[:3]==['inspect','--format',META_TEMPLATE]:
        valid=len(args)==4 and cid(args[3])
    elif args[:4]==['inspect','--type','network','--format']:
        valid=len(args)==6 and args[4]==NETWORK_TEMPLATE and (cid(args[5]) or args[5]=='none')
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


def _observe_capture_resource_v1(root_fd,custody,descriptor):
    """Actual read-only capacity observation, not issuer/quota/memory authority.

    Caller must first authenticate original master/custody with the concrete SQL
    owner. No creation/dump is permitted merely from this descriptive result.
    """
    from ..operating_model.recovery_contracts_v1 import BackupCustodyV1,RecoveryDescriptorV1
    require(type(custody) is BackupCustodyV1 and type(descriptor) is RecoveryDescriptorV1 and type(root_fd) is int,'exact current custody/descriptor/root required')
    custody.bind_descriptive_operation(descriptor)
    require(custody.kind=='capture' and custody.physical_resource is not None,'independently installed capture physical resource profile missing')
    root=custody.root_identity;profile=custody.physical_resource
    observed=os.fstat(root_fd)
    require(stat.S_ISDIR(observed.st_mode) and (observed.st_dev,observed.st_ino,observed.st_uid,stat.S_IMODE(observed.st_mode))==(root.device,root.inode,root.uid,root.mode),'actual resource custody root differs')
    path=os.stat(root.path,follow_symlinks=False)
    require((path.st_dev,path.st_ino,path.st_uid,stat.S_IMODE(path.st_mode))==(root.device,root.inode,root.uid,root.mode),'actual resource root pathname differs')
    fs=os.fstatvfs(root_fd)
    require(fs.f_fsid==profile.filesystem_id and fs.f_frsize>0 and fs.f_bavail>=0,'actual filesystem resource identity unavailable')
    required=profile.required_bytes_v1(descriptor,root)
    available=fs.f_bavail*fs.f_frsize
    require(available>=required,'current available filesystem capacity insufficient')
    # Two retained files per participant, final triplet, op/pending directories.
    required_inodes=2*len(descriptor.databases)+5
    require(fs.f_favail>=required_inodes,'current available inode capacity insufficient')
    return {'filesystem_id':fs.f_fsid,'filesystem_device':observed.st_dev,
        'required_bytes':required,'available_bytes':available,'required_inodes':required_inodes,
        'available_inodes':fs.f_favail,'quota_verified':False,'memory_verified':False,
        'serving_authorized':False,'dispatch_authorized':False}


def _check_final_output_aggregate_v1(root_fd,custody,descriptor,additional_bytes):
    """Fixed operation's complete final triplet remains <= A, before creation."""
    from ..operating_model.request_deadline_v1 import request_remaining_v1
    request_remaining_v1()
    require(type(additional_bytes) is int and additional_bytes>=0,'exact proposed output byte count required')
    try:fd=os.open(str(custody.operation_id),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root_fd)
    except FileNotFoundError:
        require(additional_bytes<=descriptor.archive_limits.maximum_total_bytes,'final output aggregate ceiling exceeded');return
    try:
        info=os.fstat(fd)
        require(info.st_uid==custody.root_identity.uid and stat.S_IMODE(info.st_mode)==0o700,'actual operation output directory differs')
        names=os.listdir(fd)
        require(len(names)<=4 and set(names)<={'archive.tar','inventory.json','manifest.json','pending'},'unknown operation output population denied')
        total=additional_bytes
        for name in names:
            request_remaining_v1();item=os.stat(name,dir_fd=fd,follow_symlinks=False)
            if name=='pending':
                require(stat.S_ISDIR(item.st_mode) and item.st_uid==custody.root_identity.uid and stat.S_IMODE(item.st_mode)==0o700,'actual pending directory differs');continue
            require(stat.S_ISREG(item.st_mode) and item.st_nlink==1 and item.st_uid==custody.root_identity.uid and stat.S_IMODE(item.st_mode)==0o600,'actual final output file differs')
            total+=item.st_size
        require(total<=descriptor.archive_limits.maximum_total_bytes,'complete final archive/inventory/manifest aggregate ceiling exceeded')
    finally:os.close(fd)


def _unpack_private_archive_v1(raw,*,metadata=False,replacement_inventory=None):
    require(len(raw)<=MAX_TOTAL,'archive bound exceeded')
    return _read_private_archive_v1(io.BytesIO(raw),metadata=metadata,replacement_inventory=replacement_inventory)


def _read_private_archive_v1(stream,*,metadata=False,replacement_inventory=None,collect=True):
    # ONE member policy for old byte APIs and new private streaming verification.
    files={};total=0;meta={};seen_members=set();hashes={}
    expected_dirs={str(parent) for name in replacement_inventory.files for parent in PurePosixPath(name).parents if str(parent)!='.'} if replacement_inventory is not None else set()
    with tarfile.open(fileobj=stream,mode='r:' if collect else 'r|') as archive:
        for member in archive:
            name=member.name
            while name.startswith('./'):name=name[2:]
            if replacement_inventory is not None:
                require(name not in seen_members and len(seen_members)<len(replacement_inventory.files)+len(expected_dirs)+1,'replacement archive duplicate/member bound denied')
                seen_members.add(name)
            if name in ('','.'):continue
            path=PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and str(path)==name,'archive path denied')
            require(member.isdir() or member.isfile(),'archive link/device denied')
            if member.isdir():
                if replacement_inventory is not None:require(name in expected_dirs,'extra replacement archive directory denied')
                continue
            require(name not in files and len(files)<(len(replacement_inventory.files) if replacement_inventory is not None else 128) and member.size<=MAX_FILE,'archive member/count denied')
            total+=member.size;require(total<=MAX_TOTAL,'archive aggregate denied')
            if replacement_inventory is None:
                require(member.uid==10001 and member.mode in (0o600,0o644),'archive ownership/mode differs')
                require(member.mode==0o600 or name=='.custody-lock','nonprivate archive member denied')
            else:
                seal=replacement_inventory.files.get(name)
                require(seal is not None and member.uid==seal.runtime_uid and member.mode==seal.runtime_mode==0o600 and member.size==seal.size,'replacement archive custody differs')
            meta[name]={'uid':member.uid,'mode':member.mode,'consumed_at':int(member.mtime)}
            source=archive.extractfile(member)
            if collect:
                files[name]=source.read(member.size+1)
                require(len(files[name])==member.size,'archive member truncated')
                hashes[name]=hashlib.sha256(files[name]).hexdigest()
            else:
                remaining=member.size;seal_hash=hashlib.sha256()
                while remaining:
                    chunk=source.read(min(65536,remaining))
                    require(bool(chunk),'archive member truncated')
                    remaining-=len(chunk);seal_hash.update(chunk)
                require(source.read(1)==b'','archive member exceeds declared size')
                files[name]=None;hashes[name]=seal_hash.hexdigest()
    if replacement_inventory is not None:
        require(set(files)==set(replacement_inventory.files),'replacement archive population differs')
        for name in files:require(hashes[name]==replacement_inventory.files[name].sha256,'replacement archive bytes differ')
    return (files,meta) if metadata else files


def unpack(raw,*,metadata=False):
    # Exact old API/policy. New metadata cannot widen the old constructor,
    # command allowlist, authority or fixed scenario.
    return _unpack_private_archive_v1(raw,metadata=metadata)


def unpack_replacement_archive_v1(raw,inventory):
    from .restore_receipts import ReplacementArchiveInventoryV1
    require(type(inventory) is ReplacementArchiveInventoryV1,'exact descriptive replacement inventory required')
    ReplacementArchiveInventoryV1.model_validate(inventory.model_dump(mode='python'))
    require(type(raw) is bytes,'exact actual archive bytes required')
    try:return _unpack_private_archive_v1(raw,metadata=True,replacement_inventory=inventory)
    except tarfile.TarError as exc:raise PermissionError('malformed replacement archive denied') from exc


def _verify_replacement_archive_fd_v1(fd,expected_file,inventory,*,archive_bound):
    """Private fixed child mechanism: actual immutable RO fd, one TAR policy.

    No path read, SQL, original authority, payload return, mutation or dispatch.
    Parent must authenticate custody/currentness and enforced memory resources.
    """
    import fcntl
    from .restore_receipts import ReplacementArchiveInventoryV1
    from ..operating_model.recovery_contracts_v1 import RecoveryPrivateFileV1
    require(type(fd) is int and type(expected_file) is RecoveryPrivateFileV1 and type(inventory) is ReplacementArchiveInventoryV1,'exact immutable archive inputs required')
    require(type(archive_bound) is int and 1<=archive_bound<=MAX_TOTAL,'bounded descriptor archive ceiling required')
    RecoveryPrivateFileV1.model_validate(expected_file.model_dump());ReplacementArchiveInventoryV1.model_validate(inventory.model_dump())
    require(fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY,'archive verifier requires read-only input fd')
    before=os.fstat(fd)
    require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 1<=before.st_size<=archive_bound and (before.st_dev,before.st_ino,before.st_uid,stat.S_IMODE(before.st_mode))==(expected_file.device,expected_file.inode,expected_file.uid,expected_file.mode),'actual immutable archive fd differs')
    with os.fdopen(os.dup(fd),'rb') as stream:
        stream.seek(0);actual_hash=hashlib.sha256()
        while chunk:=stream.read(65536):actual_hash.update(chunk)
        require(actual_hash.hexdigest()==expected_file.sha256,'actual complete archive bytes differ')
        stream.seek(0)
        try:_,metadata=_read_private_archive_v1(stream,metadata=True,replacement_inventory=inventory,collect=False)
        except tarfile.TarError as exc:raise PermissionError('malformed replacement archive denied') from exc
    after=os.fstat(fd)
    require((after.st_dev,after.st_ino,after.st_size,after.st_uid,after.st_mode,after.st_mtime_ns,after.st_ctime_ns,after.st_nlink)==(before.st_dev,before.st_ino,before.st_size,before.st_uid,before.st_mode,before.st_mtime_ns,before.st_ctime_ns,before.st_nlink),'archive input changed during verification')
    return {'file_count':len(metadata),'total_bytes':inventory.total_bytes,'archive_sha256':actual_hash.hexdigest(),'source_authenticated':False,'serving_authorized':False,'dispatch_authorized':False}


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


def pack_replacement_archive_v1(files,inventory):
    """Pure complete archive producer; supplied bytes never prove custody.

    Uses the same TAR format/private member constraints as the retained reader.
    Actual source reads/currentness and immutable output remain concrete factory
    duties; this pure function does not choose paths, issue grants or write files.
    """
    from .restore_receipts import ReplacementArchiveInventoryV1
    require(type(inventory) is ReplacementArchiveInventoryV1 and type(files) is dict,'exact replacement byte population/inventory required')
    ReplacementArchiveInventoryV1.model_validate(inventory.model_dump(mode='python'))
    require(set(files)==set(inventory.files),'complete replacement archive population required')
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as archive:
        for name,seal in inventory.files.items():
            raw=files[name]
            require(type(raw) is bytes and len(raw)==seal.size and hashlib.sha256(raw).hexdigest()==seal.sha256,'actual replacement member bytes differ')
            _add_replacement_tar_member_v1(archive,name,seal,io.BytesIO(raw))
            require(stream.tell()<=MAX_TOTAL,'replacement archive aggregate ceiling exceeded')
    raw=stream.getvalue();require(len(raw)<=MAX_TOTAL,'replacement archive aggregate ceiling exceeded')
    unpack_replacement_archive_v1(raw,inventory)
    return raw


def _add_replacement_tar_member_v1(archive,name,seal,source):
    # Same fixed USTAR member shape for old byte and private streaming writers.
    item=tarfile.TarInfo(name);item.size=seal.size;item.mode=0o600;item.uid=item.gid=seal.runtime_uid;item.mtime=0
    try:archive.addfile(item,source)
    except (ValueError,UnicodeError) as exc:raise PermissionError('replacement TAR member cannot be represented exactly') from exc


def _write_replacement_archive_fds_v1(output_fd,files,inventory,*,archive_bound,deadline):
    """Private streaming mechanism only; caller owns actual current custody.

    Source/output FDs are already-open fixed protected files, never wire paths.
    Original fence surrounds every bounded read/write. Partial output is retained
    on any error, never removed or accepted as a completed capture.
    """
    import fcntl
    from .restore_receipts import ReplacementArchiveInventoryV1
    from ..operating_model.recovery_contracts_v1 import RecoveryPrivateFileV1
    from ..operating_model.request_deadline_v1 import request_remaining_v1,sql_remaining_v1
    def fresh():request_remaining_v1();sql_remaining_v1(deadline)
    fresh()
    require(type(output_fd) is int and type(files) is dict and type(inventory) is ReplacementArchiveInventoryV1 and type(archive_bound) is int and 1<=archive_bound<=MAX_TOTAL,'exact bounded streaming archive inputs required')
    ReplacementArchiveInventoryV1.model_validate(inventory.model_dump())
    require(set(files)==set(inventory.files),'complete streaming source population required')
    out=os.fstat(output_fd)
    require(stat.S_ISREG(out.st_mode) and out.st_nlink==1 and out.st_uid==os.getuid() and stat.S_IMODE(out.st_mode)==0o600 and out.st_size==0 and os.lseek(output_fd,0,os.SEEK_CUR)==0,'exclusive empty private archive output required')
    require(fcntl.fcntl(output_fd,fcntl.F_GETFL)&os.O_ACCMODE in (os.O_WRONLY,os.O_RDWR),'writable exclusive output required')
    identities={};native_bytes=0
    for name in inventory.files:
        fd,pin=files[name]
        require(type(fd) is int and type(pin) is RecoveryPrivateFileV1,'exact immutable member fd/pin required')
        RecoveryPrivateFileV1.model_validate(pin.model_dump());seal=inventory.files[name]
        require(fcntl.fcntl(fd,fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY,'streaming source fd must be read-only')
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and (before.st_dev,before.st_ino,before.st_uid,stat.S_IMODE(before.st_mode),before.st_size)==(pin.device,pin.inode,seal.runtime_uid,seal.runtime_mode,seal.size) and pin.uid==seal.runtime_uid and pin.mode==seal.runtime_mode and pin.sha256==seal.sha256,'actual streaming source custody differs')
        require((before.st_dev,before.st_ino)!=(out.st_dev,out.st_ino),'archive output cannot also be an input')
        identities[name]=before
        # tobuf proves representability BEFORE writing any output.
        item=tarfile.TarInfo(name);item.size=seal.size;item.mode=0o600;item.uid=item.gid=seal.runtime_uid;item.mtime=0
        try:header=item.tobuf(format=tarfile.USTAR_FORMAT)
        except (ValueError,UnicodeError) as exc:raise PermissionError('replacement TAR member cannot be represented exactly') from exc
        native_bytes+=len(header)+((seal.size+511)//512)*512
    complete_bytes=((native_bytes+1024+10239)//10240)*10240
    require(complete_bytes<=archive_bound,'complete streaming archive exceeds installed ceiling')
    class Output:
        position=0
        def write(self,raw):
            fresh();require(self.position+len(raw)<=archive_bound,'streaming archive ceiling exceeded')
            written=os.write(output_fd,raw);require(written==len(raw),'incomplete streaming archive write')
            self.position+=written;fresh();return written
        def tell(self):return self.position
    class Member:
        def __init__(self,fd):self.fd=fd;self.sha=hashlib.sha256();self.offset=0
        def read(self,count):
            fresh();require(type(count) is int and 0<=count<=65536,'bounded streaming member read required')
            raw=os.pread(self.fd,count,self.offset);self.offset+=len(raw);self.sha.update(raw);fresh();return raw
    output=Output()
    with tarfile.open(fileobj=output,mode='w|',format=tarfile.USTAR_FORMAT,bufsize=10240) as archive:
        for name in inventory.files:
            fd,pin=files[name]
            source=Member(fd);_add_replacement_tar_member_v1(archive,name,inventory.files[name],source)
            require(source.offset==inventory.files[name].size and source.sha.hexdigest()==pin.sha256,'actual streaming member bytes differ')
            before=identities[name];after=os.fstat(fd)
            require((before.st_dev,before.st_ino,before.st_size,before.st_mode,before.st_uid,before.st_nlink,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mode,after.st_uid,after.st_nlink,after.st_mtime_ns,after.st_ctime_ns),'streaming member changed')
    fresh();os.fsync(output_fd);fresh()
    require(output.position==complete_bytes,'complete actual streaming TAR size differs')
    return {'bytes':output.position,'file_count':len(files),'source_authenticated':False,'serving_authorized':False,'dispatch_authorized':False}


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


@contextmanager
def _exclusive_output_v1(root,name,*,root_fd=None,readwrite=False,deadline=None):
    # Never chmod any existing parent; every write is anchored to owned dirfds.
    def fresh():
        if readwrite:
            from ..operating_model.request_deadline_v1 import request_remaining_v1,sql_remaining_v1
            request_remaining_v1();sql_remaining_v1(deadline)
    fresh()
    path=PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and str(path)==name,'unsafe custody output denied')
    directory=os.dup(root_fd) if root_fd is not None else owned_directory(root)
    try:
        for part in path.parts[:-1]:
            fresh()
            try:os.mkdir(part,0o700,dir_fd=directory)
            except FileExistsError:pass
            fresh()
            nextfd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            info=os.fstat(nextfd)
            if not (info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700):
                os.close(nextfd);raise PermissionError('nested output custody differs')
            os.close(directory);directory=nextfd
        fresh()
        fd=os.open(path.name,(os.O_RDWR if readwrite else os.O_WRONLY)|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        try:yield fd,directory
        finally:os.close(fd)
    finally:os.close(directory)


def save(root,name,raw,*,root_fd=None):
    # Same exclusive private creator; native staging uses the private FD variant.
    with _exclusive_output_v1(root,name,root_fd=root_fd) as (fd,directory):
        with os.fdopen(os.dup(fd),'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.fsync(directory)


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
        no_network=json.loads(self.checked(['inspect','--type','network','--format',NETWORK_TEMPLATE,'none'],bound=8192,timeout=5))
        require(set(no_network)=={'id','name','driver','internal','ipv6'} and isinstance(no_network['id'],str)
            and re.fullmatch(r'[0-9a-f]{64}',no_network['id']) and no_network=={'id':no_network['id'],'name':'none','driver':'null','internal':False,'ipv6':False},'actual builtin no-network identity differs')
        seen_networks=set()
        for role in ROLES:
            row=json.loads(self.checked(['inspect','--format',META_TEMPLATE,services[role].container_id],bound=8192,timeout=5))
            networks=row.pop('networks').split();mounts=row.pop('mounts').split()
            require(all(token.count(':')==1 for token in networks),'actual role network attachment differs')
            pairs=[token.split(':',1) for token in networks]
            expected={network_name(instance,i):instance.networks[i] for i in ROLE_NETWORKS.get(role,())}
            mode=row.pop('network_mode')
            bootstrap=role not in ROLE_NETWORKS
            if bootstrap:
                require(mode=='none','bootstrap must use builtin no-network mode')
                expected={'none':no_network['id']}
            else:
                require(mode in expected,'actual role network mode differs')
            require(len(pairs)==len(expected) and len({name for name,_ in pairs})==len(pairs),'actual role network attachment differs')
            require(all(name in expected and (value==expected[name] or (services[role].state=='created' and value=='')) for name,value in pairs),'actual role network attachment differs')
            networks=[] if bootstrap else [expected[name] for name,_ in pairs]
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
        for i,identity in enumerate(instance.networks):
            observed=json.loads(self.checked(['inspect','--type','network','--format',NETWORK_TEMPLATE,identity],bound=8192,timeout=5))
            require(observed=={'id':identity,'name':network_name(instance,i),'driver':'bridge','internal':i!=0,'ipv6':i!=0},'actual core network identity differs')
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

class ReplacementForwardRecoveryV1:
    """Quarantined archive inspection, not an admitted capture/restore actuator.

    This first source slice accepts no runner, permission callback, provider,
    role, database URL or serving hook. Actual SQL026 currentness and concrete
    effect composition must be installed before any dump/restore can exist.
    """
    def __init__(self,inventory):
        from .restore_receipts import ReplacementArchiveInventoryV1
        require(type(inventory) is ReplacementArchiveInventoryV1,'exact replacement inventory required')
        ReplacementArchiveInventoryV1.model_validate(inventory.model_dump(mode='python'))
        self.inventory=inventory

    def inspect_archive_v1(self,raw):
        files,metadata=unpack_replacement_archive_v1(raw,self.inventory)
        return {'protocol':'oracle-replacement-quarantined-inspection-v1',
            'file_count':len(files),'total_bytes':sum(len(v) for v in files.values()),
            'inventory_sha256':digest(self.inventory.model_dump(mode='json')),
            'quarantine_reasons':['current-deny-plane-unproved','once-cost-tail-unproved',
                'recovery-authority-unproved','retained-vector-authority-unproved'],
            'source_authenticated':False,'dump_restore_enabled':False,
            'serving_authorized':False,'business_accepted':False}


if __name__=='__main__':raise SystemExit(main())


class ProtectedReplacementRecoveryFactoryV1:
    """Current replacement quarantine, using the original control master.

    This first connected slice imports ACTUAL current denials under a separately
    installed postrestore target role/profile. It never accepts caller census,
    authority/hash maps, runner callbacks, target selectors or positive grants.
    Capture/restore/archive inspection retain their existing owners. No dump or
    restore is invoked by this class, and no ready/serve/dispatch API exists.

    A complete SQL policy census is not complete disaster recovery: actual
    covered-key cost/once tail, private originals, retained original vector wire,
    model/license/current source scope and accepted read-only SDK census remain
    independently mandatory. Loss of the original control plane quarantines;
    there is no assumed replica or RPO claim. Old capture/provider/source/role
    permission is never renewed by a new restore/read lease.
    """
    def __init__(self,settings):
        from ..operating_model.recovery_authority_v1 import ProtectedRecoverySettingsV1
        if type(settings) is not ProtectedRecoverySettingsV1:raise TypeError('actual protected recovery installation required')
        self.settings=settings
        _,_,descriptor,_,_=settings.current_v1()
        if descriptor.kind not in ('capture','restore'):raise PermissionError('fresh independently appointed recovery operation required')

    def inspect_native_resources_v1(self,*,deadline):
        """Read-only fixed native metadata; never grants capture/restore authority."""
        _,_,descriptor,_,_=self.settings.current_v1()
        purpose='capture' if descriptor.kind=='capture' else 'deny-only-target'
        return _ReplacementNativeDockerV1(self._source(purpose),deadline=deadline).inspect_participants_v1()

    def validate_native_services_v1(self,*,deadline):
        """Fixed protected native reads only; actual physical SQL still required."""
        _,_,descriptor,_,_=self.settings.current_v1()
        purpose='capture' if descriptor.kind=='capture' else 'deny-only-target'
        return _ReplacementNativeDockerV1(self._source(purpose),deadline=deadline).validate_services_v1()

    def verify_native_physical_identities_v1(self,*,deadline):
        """Actual fixed read-only native SQL, never a dump/restore dispatch."""
        _,_,descriptor,_,_=self.settings.current_v1()
        purpose='capture' if descriptor.kind=='capture' else 'deny-only-target'
        return _ReplacementNativeDockerV1(self._source(purpose),deadline=deadline).verify_physical_identities_v1()

    def _save_capture_output_v1(self,leaf,raw,*,deadline):
        """Internal immutable producer output under ACTUAL retained master claim.

        No API accepts file bytes, paths or a claim. The eventual concrete capture
        producer supplies its own observed archive/inventory/manifest. Existing
        save owns O_EXCL/private mode/dirfd/fsync; partial/late/lost output remains
        UNKNOWN and is never removed, overwritten or automatically retried.
        """
        from datetime import datetime,timezone
        from ..operating_model.request_deadline_v1 import request_remaining_v1,sql_remaining_v1
        from ..operating_model.recovery_authority_v1 import RecoveryOutcomeUnknownV1
        request_remaining_v1();sql_remaining_v1(deadline)
        require(leaf in ('archive.tar','inventory.json','manifest.json') and type(raw) is bytes and 1<=len(raw)<=MAX_TOTAL,'fixed bounded actual capture output required')
        source=self._source('capture')
        before=source.current_v1(deadline=deadline)
        claims=[c for c in before.retained_claims if c.phase=='capture']
        require(len(claims)==1 and not claims[0].fresh,'actual retained original capture claim required')
        claim=claims[0]
        require(datetime.now(timezone.utc)<claim.original_phase_deadline,'original capture phase expired')
        _,custody=source.custody_v1(deadline=deadline)
        _,_,descriptor,_,_=self.settings.current_v1()
        require(len(raw)<=descriptor.archive_limits.maximum_total_bytes,'installed capture output bound exceeded')
        root=custody.root_identity
        fd=owned_directory(root.path)
        def exact_root():
            observed=os.fstat(fd)
            require((observed.st_dev,observed.st_ino,observed.st_uid,stat.S_IMODE(observed.st_mode))==(root.device,root.inode,root.uid,root.mode),'actual output custody root differs')
            current=os.stat(root.path,follow_symlinks=False)
            require((current.st_dev,current.st_ino,current.st_uid,stat.S_IMODE(current.st_mode))==(root.device,root.inode,root.uid,root.mode),'output custody root pathname changed')
        possible=False
        try:
            exact_root();request_remaining_v1();sql_remaining_v1(deadline)
            _observe_capture_resource_v1(fd,custody,descriptor)
            possible=True # Existing operation output may already be partial/uncertain.
            _check_final_output_aggregate_v1(fd,custody,descriptor,len(raw))
            # No caller-supplied pathname and no root creation/chmod. The one
            # operation UUID directory is private under the existing pinned root.
            name=str(custody.operation_id)+'/'+leaf
            possible=True;save(root.path,name,raw,root_fd=fd)
            request_remaining_v1();sql_remaining_v1(deadline);exact_root()
            actual=source.current_v1(deadline=deadline)
            matches=[c for c in actual.retained_claims if c.phase=='capture']
            require(matches==[claim] and datetime.now(timezone.utc)<claim.original_phase_deadline,'original master claim changed or expired after capture output')
            _,after=source.custody_v1(deadline=deadline)
            require(after==custody,'actual output custody changed after immutable write')
            return {'member':name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'serving_authorized':False,'dispatch_authorized':False,'automatic_retry_allowed':False}
        except Exception as exc:
            if possible:raise RecoveryOutcomeUnknownV1('possibly written immutable capture output; retain without retry') from exc
            raise
        finally:os.close(fd)

    def verify_native_dump_inventories_v1(self,*,deadline):
        """Fixed read-only full DDL inventory, with no caller hash/table selector."""
        _,_,descriptor,_,_=self.settings.current_v1()
        purpose='capture' if descriptor.kind=='capture' else 'deny-only-target'
        return _ReplacementNativeDockerV1(self._source(purpose),deadline=deadline).verify_dump_inventories_v1()

    def _source(self,purpose):
        from ..operating_model.recovery_authority_v1 import RecoverySQLAuthorityV1
        return RecoverySQLAuthorityV1(self.settings,purpose,target=False)

    @staticmethod
    def _stable_census(census):
        # Actual SQL returns a fresh checked/read window/snapshot. Only those
        # observational fields are excluded; every policy/operational row digest,
        # source/withdrawal/deny, full scope and exact owner identity remains.
        return digest(census.model_dump(mode='json',exclude={'checked_at','valid_until','source_snapshot'}))

    @staticmethod
    def _restore_claim(current):
        values=[c for c in current.retained_claims if c.phase=='restore']
        if len(values)!=1:raise PermissionError('actual original control restore claim required')
        return values[0]

    def import_current_denials_v1(self,*,deadline):
        from datetime import datetime,timezone
        from ..operating_model.recovery_authority_v1 import RecoverySQLAuthorityV1,RecoveryOutcomeUnknownV1
        from ..operating_model.request_deadline_v1 import request_remaining_v1,sql_remaining_v1
        from ..operating_model.recovery_contracts_v1 import RecoveryObservationV1
        request_remaining_v1();sql_remaining_v1(deadline)
        _,_,descriptor,_,profile=self.settings.current_v1()
        if profile is None:raise PermissionError('actual independently installed postrestore profile missing')
        master=self._source('deny-only-target')
        denials=self._source('current-denials')
        observer=self._source('observe')
        target=RecoverySQLAuthorityV1(self.settings,'deny-only-target',target=True)
        original=master.current_v1(deadline=deadline)
        restore_claim=self._restore_claim(original)
        profile.bind_actual_master(descriptor,restore_claim)
        census=denials.current_v1(deadline=deadline).census
        if census is None:raise PermissionError('actual complete current original-control census missing')
        target.current_v1(deadline=deadline)
        # The SAME global original master is checked immediately before claim.
        if self._restore_claim(master.current_v1(deadline=deadline))!=restore_claim:raise PermissionError('original master changed before target effect')
        claim=master._claim_v1('deny-import',deadline=deadline)
        if not claim.fresh:raise RecoveryOutcomeUnknownV1('retained deny-import claim cannot be dispatched again')
        try:
            request_remaining_v1();sql_remaining_v1(deadline)
            if datetime.now(timezone.utc)>=claim.original_phase_deadline:raise PermissionError('original deny-import phase expired')
            # No SQL transaction is held across source/target connections.
            result=target._import_actual_census_v1(census,deadline=deadline)
            census_sha=digest(census.model_dump(mode='json'))
            expected={'schema_version':1,'operation_id':str(descriptor.operation_id),'census_sha256':census_sha,
                      'quarantined':True,'serving_authorized':False,'dispatch_authorized':False,'automatic_retry_allowed':False}
            if type(result) is not dict or canonical_bytes(result)!=canonical_bytes(expected):raise PermissionError('actual target denial receipt differs')
            after=denials.current_v1(deadline=deadline).census
            if after is None or self._stable_census(after)!=self._stable_census(census):raise PermissionError('actual current original denials changed during target effect')
            if self._restore_claim(master.current_v1(deadline=deadline))!=restore_claim:raise PermissionError('actual original master changed after target effect')
            observed=target.current_v1(deadline=deadline)
            if census_sha not in observed.imported_census_sha256s:raise PermissionError('actual target denial import not retained')
            request_remaining_v1();sql_remaining_v1(deadline)
            if datetime.now(timezone.utc)>=claim.original_phase_deadline:raise PermissionError('original phase expired after target effect')
            note=RecoveryObservationV1(observation_id=uuid4(),operation_id=descriptor.operation_id,phase='deny-import',status='complete',
                original_phase_deadline=claim.original_phase_deadline,phase_started_at=claim.claimed_at,observed_at=datetime.now(timezone.utc),
                backup_manifest_sha256=descriptor.backup_manifest_sha256,source_census_sha256=census_sha,observed_result_sha256=digest(result),
                observed_file_count=None,observed_bytes=None,quarantine_reasons=('custody-incomplete','once-cost-tail-unproved','vector-custody-unproved','vector-model-license-unproved'))
            observer._observe_actual_v1(note,deadline=deadline)
            return note
        except Exception as exc:
            # The retained immutable original claim remains the recovery fence.
            # Possibly committed target/source writes are never rerun, even if
            # the current recipient/source authority has expired or been revoked.
            if isinstance(exc,RecoveryOutcomeUnknownV1):raise
            raise RecoveryOutcomeUnknownV1('recovery phase possibly effected; retain quarantine, no retry') from exc


def _active_native_participants_v1(custody):
    # Capture reads its actual source; fresh restore touches ONLY its independently
    # appointed target and retained backup. Historical source native pins never
    # require/revive expired capture credentials or an available old source DB.
    return tuple((p,'source',p.source) if custody.kind=='capture' else (p,'target',p.target) for p in custody.native_participants)


_REPLACEMENT_NATIVE_IDENTITY_SQL_V1=b"SELECT json_build_object('system_identifier',(SELECT system_identifier::text FROM pg_control_system()),'database_oid',(SELECT oid::bigint FROM pg_database WHERE datname=current_database()),'database_name',current_database(),'database_owner',(SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()),'session_role',SESSION_USER,'effective_role',current_setting('role'),'tls',(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()));\n"

_REPLACEMENT_CONTAINER_TEMPLATE_V1='{"id":{{json .Id}},"image":{{json .Image}},"name":{{json .Name}},"running":{{json .State.Running}}}'

class _ReplacementNativeDockerV1:
    """Closed actual native resource inspector under the ORIGINAL SQL owner.

    No callable/argv/container/path arrives from an API request. Settings/custody
    are reread through actual own SQL before/after every subprocess. Inspection
    exposes only fixed physical container metadata; never Config/Env or secrets.
    Dump/restore dispatch is deliberately not exposed by this read-only slice.
    """
    def __init__(self,authority,*,deadline):
        from ..operating_model.recovery_authority_v1 import RecoverySQLAuthorityV1
        require(type(authority) is RecoverySQLAuthorityV1 and not authority.target,'actual original own recovery SQL authority required')
        require(authority.purpose in ('capture','deny-only-target'),'actual native custody purpose required')
        self._authority=authority;self._deadline=deadline

    def _read_operation_v1(self,container,kind,pin=None):
        from ..operating_model.request_deadline_v1 import request_remaining_v1,sql_remaining_v1
        _,before=self._authority.custody_v1(deadline=self._deadline)
        installed=[c for _,_,c in _active_native_participants_v1(before) if c is not None]
        require(container in installed,'native container differs from actual protected custody')
        files=(container.service_file,container.native_sql_identity.database_url,container.native_sql_identity.tls_ca)
        if kind=='stat':
            paths=[v.path for v in container.native_sql_identity.ancestors]+[v.path for v in files]
            args=['exec',container.container_id,'stat','--printf','%d:%i:%u:%a:%F\n','--',*paths];bound=8192
        elif kind=='copy':
            require(pin in files,'native copy outside exact installed three-file set')
            args=['cp',container.container_id+':'+pin.path,'-'];bound=1024**2
        elif kind in ('identity','inventory'):
            if kind=='inventory':require(container.dump_inventory_sha256 is not None,'independently installed full native dump inventory pin missing')
            remaining=min(request_remaining_v1(),sql_remaining_v1(self._deadline))
            require(remaining>=7,'original window cannot fit fixed native connection/query bounds')
            args=['exec','-i',container.container_id,'env','-i','PATH=/usr/local/bin:/usr/bin:/bin','LANG=C','PGCONNECT_TIMEOUT=2','PGSERVICEFILE='+container.service_file.path,'PGOPTIONS=-c statement_timeout=5000 -c lock_timeout=2000','psql','-X','-q','-A','-t','-v','ON_ERROR_STOP=1','--dbname=service=oracle_recovery_v1'];bound=8192 if kind=='identity' else 1024**2
        else:raise PermissionError('fixed native read operation required')
        remaining=min(request_remaining_v1(),sql_remaining_v1(self._deadline))
        data=None
        if kind=='identity':data=_REPLACEMENT_NATIVE_IDENTITY_SQL_V1
        elif kind=='inventory':
            from ..operating_model.recovery_authority_v1 import _DUMP_CATALOG_SQL_V1
            data=(_DUMP_CATALOG_SQL_V1+';\n').encode('utf8')
        raw=_bounded_docker_execution_v1(args,data=data,bound=bound,timeout=min(30,remaining))
        request_remaining_v1();sql_remaining_v1(self._deadline)
        _,after=self._authority.custody_v1(deadline=self._deadline)
        require(after==before,'actual native custody changed around protected read')
        return raw

    def _stat_private_files_v1(self,container):
        raw=self._read_operation_v1(container,'stat')
        expected=[(p,'directory') for p in container.native_sql_identity.ancestors]+[(p,'regular file') for p in (container.service_file,container.native_sql_identity.database_url,container.native_sql_identity.tls_ca)]
        require(type(raw) is bytes and raw.endswith(b'\n'),'complete native protected stat required')
        try:lines=raw.decode('ascii',errors='strict').splitlines()
        except UnicodeError as exc:raise PermissionError('invalid native protected stat') from exc
        require(len(lines)==len(expected),'complete exact native file/ancestor population required')
        for line,(pin,kind) in zip(lines,expected):
            fields=line.split(':')
            require(len(fields)==5 and all(re.fullmatch(r'[0-9]+',v) for v in fields[:3]) and re.fullmatch(r'[0-7]+',fields[3]),'exact native stat shape required')
            observed=(int(fields[0]),int(fields[1]),int(fields[2]),int(fields[3],8),fields[4])
            require(observed==(pin.device,pin.inode,pin.uid,pin.mode,kind),'actual native private file/ancestor identity changed')
        return raw

    def verify_dump_inventories_v1(self):
        """Read-only exact catalog observation; not a snapshot/capture admission."""
        from ..operating_model.recovery_authority_v1 import validate_recovery_dump_catalog_v1
        self.verify_physical_identities_v1()
        _,custody=self._authority.custody_v1(deadline=self._deadline)
        result=[]
        for participant,side,container in _active_native_participants_v1(custody):
            require(container is not None,'complete actual current native target required')
            require(container.dump_inventory_sha256 is not None,'complete independently installed native inventory pin missing')
            before=self._stat_private_files_v1(container)
            raw=self._read_operation_v1(container,'inventory')
            def unique(pairs):
                value={}
                for key,item in pairs:
                    require(key not in value,'duplicate native DDL inventory field');value[key]=item
                return value
            try:value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite native DDL inventory')))
            except (ValueError,UnicodeError) as exc:raise PermissionError('complete actual native DDL inventory unavailable') from exc
            tables=validate_recovery_dump_catalog_v1(value,container.dump_inventory_sha256)
            require(self._stat_private_files_v1(container)==before,'native protected identity changed around DDL read')
            result.append({'participant_id':str(participant.participant_id),'side':side,'actual_inventory_sha256':digest(value),'actual_wire_sha256':hashlib.sha256(raw).hexdigest(),'tables':tables,'capture_snapshot_verified':False,'serving_authorized':False,'dispatch_authorized':False})
        return tuple(result)

    def verify_physical_identities_v1(self):
        self.validate_services_v1()
        _,custody=self._authority.custody_v1(deadline=self._deadline)
        result=[]
        for participant,side,container in _active_native_participants_v1(custody):
            require(container is not None,'complete actual current native target required')
            before=self._stat_private_files_v1(container)
            raw=self._read_operation_v1(container,'identity')
            def unique(pairs):
                value={}
                for key,item in pairs:
                    require(key not in value,'duplicate native SQL identity field');value[key]=item
                return value
            try:value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite native SQL identity')))
            except (ValueError,UnicodeError) as exc:raise PermissionError('fixed actual native SQL identity unavailable') from exc
            i=container.native_sql_identity
            expected={'system_identifier':i.system_identifier,'database_oid':i.database_oid,'database_name':i.database_name,'database_owner':i.database_owner,'session_role':i.session_role,'effective_role':'none','tls':True}
            require(type(value) is dict and type(value.get('database_oid')) is int and type(value.get('tls')) is bool and value==expected,'actual native physical SQL/own session/TLS differs')
            require(self._stat_private_files_v1(container)==before,'native private identity changed around actual SQL')
            result.append({'participant_id':str(participant.participant_id),'side':side,**expected,'serving_authorized':False,'dispatch_authorized':False})
        return tuple(result)

    def validate_services_v1(self):
        # No secret leaves this method. Native SQL/TLS physical readback and
        # actual capture/restore remain separate checks, not inferred here.
        self.inspect_participants_v1()
        _,custody=self._authority.custody_v1(deadline=self._deadline)
        result=[]
        for participant,side,container in _active_native_participants_v1(custody):
            require(container is not None,'complete actual current native target required')
            before=self._stat_private_files_v1(container)
            values=tuple(_container_private_file_bytes_v1(self._read_operation_v1(container,'copy',pin),pin) for pin in (container.service_file,container.native_sql_identity.database_url,container.native_sql_identity.tls_ca))
            require(self._stat_private_files_v1(container)==before,'native protected file population changed during private reads')
            checked=_validate_native_service_bytes_v1(values[0],values[1],container)
            result.append({'participant_id':str(participant.participant_id),'side':side,**checked})
        return tuple(result)

    def inspect_participants_v1(self):
        from ..operating_model.request_deadline_v1 import request_remaining_v1,sql_remaining_v1
        _,custody=self._authority.custody_v1(deadline=self._deadline)
        result=[]
        for participant,side,container in _active_native_participants_v1(custody):
            require(container is not None,'complete actual current native target required')
            _,before=self._authority.custody_v1(deadline=self._deadline)
            require(before==custody,'native custody changed before container inspection')
            remaining=min(request_remaining_v1(),sql_remaining_v1(self._deadline))
            require(remaining>0,'original recovery request expired')
            raw=_bounded_docker_execution_v1(['inspect','--format',_REPLACEMENT_CONTAINER_TEMPLATE_V1,container.container_id],data=None,bound=8192,timeout=min(30,remaining))
            # Docker format adds one newline; do not accept arbitrary trailing
            # output, duplicated objects or extra secret-bearing fields.
            require(raw.endswith(b'\n') and not raw.endswith(b'\n\n'),'complete fixed container metadata required')
            def unique(pairs):
                obj={}
                for key,value in pairs:
                    require(key not in obj,'duplicate fixed container field denied');obj[key]=value
                return obj
            try:observed=json.loads(raw[:-1],object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite fixed container field')))
            except (ValueError,UnicodeError) as exc:raise PermissionError('malformed fixed container metadata') from exc
            require(type(observed) is dict and set(observed)=={'id','image','name','running'},'fixed container metadata shape required')
            require(type(observed['running']) is bool and observed=={'id':container.container_id,'image':'sha256:'+container.image_id,'name':'/'+container.container_name,'running':True},'actual pinned native container identity/running state differs')
            request_remaining_v1();sql_remaining_v1(self._deadline)
            _,after=self._authority.custody_v1(deadline=self._deadline)
            require(after==custody,'native custody changed after container inspection')
            result.append({'participant_id':str(participant.participant_id),'side':side,'container_id':container.container_id,'image_id':container.image_id,'container_name':container.container_name,'running':True})
        return tuple(result)


def _container_private_file_bytes_v1(raw,pin):
    """One actual docker-cp file, consumed privately; never logged/returned wire."""
    from ..operating_model.recovery_contracts_v1 import RecoveryPrivateFileV1
    require(type(pin) is RecoveryPrivateFileV1 and type(raw) is bytes and 1<=len(raw)<=1024**2,'bounded actual protected container file required')
    try:
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
            members=archive.getmembers()
            require(len(members)==1,'single exact protected container member required')
            member=members[0]
            require(member.isfile() and member.name==PurePosixPath(pin.path).name and member.uid==pin.uid and member.mode==pin.mode==0o600 and 1<=member.size<=65536,'actual protected container file custody differs')
            stream=archive.extractfile(member);value=stream.read(member.size+1)
            require(len(value)==member.size and hashlib.sha256(value).hexdigest()==pin.sha256,'actual protected container file bytes changed')
            return value
    except tarfile.TarError as exc:raise PermissionError('malformed protected container file transfer') from exc


def _validate_native_service_bytes_v1(service_raw,url_raw,container):
    """Strict private comparison only; no network/auth/permission inference.

    Service/DSN secret bytes are intentionally absent from errors, receipts and
    returned metadata. Native TLS private-key authentication is not supported by
    this slice because it has no independently pinned client-key custody tuple;
    it refuses rather than importing or guessing such material.
    """
    import configparser
    from psycopg.conninfo import conninfo_to_dict,make_conninfo
    from psycopg import Error as NativeConnectionInfoError
    from ..operating_model.recovery_contracts_v1 import RecoveryNativeContainerV1
    require(type(container) is RecoveryNativeContainerV1 and type(service_raw) is bytes and type(url_raw) is bytes,'actual private native service bytes required')
    try:
        parser=configparser.ConfigParser(interpolation=None,strict=True,empty_lines_in_values=False)
        parser.read_string(service_raw.decode('utf8',errors='strict'))
        require(parser.sections()==['oracle_recovery_v1'] and not parser.defaults(),'exact one fixed native service required')
        actual=dict(parser['oracle_recovery_v1'])
        expected=conninfo_to_dict(url_raw.decode('utf8',errors='strict'))
        require(make_conninfo(**dict(sorted(expected.items()))).encode('utf8')==url_raw,'exact canonical native conninfo bytes required')
        # Complete explicit password-auth DSN; no PG* ambient/default/service,
        # options, shell values or unpinned client key/certificate is accepted.
        keys={'host','hostaddr','port','dbname','user','sslmode','sslrootcert','password'}
        require(set(actual)==keys and set(expected)==keys and actual==expected,'complete fixed native service and protected conninfo differ')
        i=container.native_sql_identity
        require({k:actual[k] for k in keys-{'password'}}=={'host':i.host,'hostaddr':i.hostaddr,'port':str(i.port),'dbname':i.database_name,'user':i.session_role,'sslmode':'verify-full','sslrootcert':i.tls_ca.path},'native TLS/target/session pins differ')
        require(all(type(v) is str and v and '\x00' not in v and '\n' not in v and '\r' not in v for v in actual.values()),'exact bounded native service values required')
    except (configparser.Error,UnicodeError,ValueError,NativeConnectionInfoError):
        raise PermissionError('invalid protected native service configuration') from None
    return {'service_validated':True,'location':'container-local','credential_material_exported':False,'source_authenticated':False}
