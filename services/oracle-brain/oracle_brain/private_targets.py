"""Public target commitments; packaged workers never read local private metadata."""
import hashlib,json,os,re,stat,subprocess
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit,unquote

TARGET_PINS=MappingProxyType({'legacy_trigger_project': 'fea89e37d060c6e49e41fe96e1b526a1dfe47eb2dafff368a32eb4ac0c7563e5', 'native_trigger_project': '580419cdce24974ddddeac0a2dff52e4db4b5b48a2cf01fa5c00ad59bf52970e', 'oracle_supabase_project': '9190ea2866aa7bf92e2806946d58e5728957851544cade4e900fa8436872652d', 'native_supabase_project': '620b6d5ddc335d4bd407f56c4e534cd8141fbcb6772483488a0180abbec651dd', 'coolify_api_base_url': '208ba8dd3931fe4a0638e12862634386e96412b6cf6a02fe26a1ef2e42036c3c'})

def is_pinned_target(key,value):
    return type(value) is str and key in TARGET_PINS and hashlib.sha256(value.encode()).hexdigest()==TARGET_PINS[key]

def database_tenant(username,role):
    login=unquote(username or '')
    prefix=role+'.'
    tenant=login[len(prefix):] if login.startswith(prefix) else ''
    if not re.fullmatch('[a-z]{20}',tenant) or not is_pinned_target('native_supabase_project',tenant):
        raise PermissionError('exact isolated database identity required')
    return tenant

def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise PermissionError('duplicate private target field')
        result[key]=value
    return result

def read_private_target(key,profile_path=None):
    """Offline tooling only; same default profile and public pins as Node tooling."""
    selected=profile_path if profile_path is not None else os.environ.get('ORACLE_TARGET_PROFILE_PATH')
    path=Path(selected) if selected is not None else Path.home()/'.config/oracle/targets.json'
    if not path.is_absolute():raise PermissionError('absolute private profile required')
    # Windows uses the existing Node reader, including its Windows ACL validator.
    if os.name=='nt':
        helper=Path(__file__).resolve().parents[3]/'dev/oracle2/private-target-profile.mjs'
        result=subprocess.run(['node','--input-type=module','--eval',
            'const m=await import(process.argv[1]);process.stdout.write(m.readPrivateTarget(process.argv[2],process.argv[3]));',
            helper.as_uri(),key,str(path)],capture_output=True,check=True,timeout=15,
            env={k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','WINDIR','USERPROFILE','HOME','PATHEXT')})
        value=result.stdout.decode()
        if not is_pinned_target(key,value):raise PermissionError('private target differs')
        return value
    for item in (path.parent,path):
        info=item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
            raise PermissionError('protected private profile required')
    if not stat.S_ISDIR(path.parent.lstat().st_mode):raise PermissionError('private parent required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.getuid() or info.st_mode&0o077 or not 0<info.st_size<=16384:
            raise PermissionError('protected bounded private profile required')
        raw=os.read(fd,16385)
    finally:os.close(fd)
    body=json.loads(raw,object_pairs_hook=_unique)
    if type(body) is not dict or set(body)!={'schema_version','targets'} or type(body['schema_version']) is not int or body['schema_version']!=1 or type(body['targets']) is not dict or set(body['targets'])!=set(TARGET_PINS):
        raise PermissionError('exact private target population required')
    for name,value in body['targets'].items():
        if not is_pinned_target(name,value):raise PermissionError('private target differs')
        if name=='coolify_api_base_url':
            u=urlsplit(value)
            if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query or u.fragment or u.path!='/api/v1':raise PermissionError('strict target URL required')
        elif not re.fullmatch('proj_[a-z0-9]+' if name.endswith('trigger_project') else '[a-z]{20}',value):raise PermissionError('typed project required')
    return body['targets'][key]
