"""Write-once private artifacts. A blob alone never confers serving authority."""
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
from .contracts import canonical_bytes

MAX_ORIGINAL_BYTES=25*1024*1024

@dataclass(frozen=True)
class OriginalObjectRefV1:
    """Private storage identity only; never grants intake/read authority."""
    workspace_id:UUID
    source_id:UUID
    revision:int
    original_sha256:str
    byte_count:int
    content_type:str
    storage_profile_hash:str
    schema_version:int=1
    def __post_init__(self):
        if (type(self.workspace_id) is not UUID or type(self.source_id) is not UUID
            or type(self.revision) is not int or self.revision<1 or self.schema_version!=1
            or type(self.byte_count) is not int or not 0<self.byte_count<=MAX_ORIGINAL_BYTES
            or not isinstance(self.content_type,str) or not 0<len(self.content_type)<=256
            or type(self.schema_version) is not int
            or any(type(h) is not str or len(h)!=64 or any(c not in '0123456789abcdef' for c in h) for h in (self.original_sha256,self.storage_profile_hash))):
            raise ValueError('invalid private original object identity')
    @property
    def key(self):return f'source-originals/{self.workspace_id}/{self.source_id}/{self.revision}/{self.original_sha256}.bin'

@dataclass(frozen=True)
class ReservationOriginalObjectRefV1:
    """SQL-reservation identity only; no arbitrary key and no intake/read grant."""
    original:OriginalObjectRefV1
    reservation_id:UUID
    def __post_init__(self):
        if type(self.original) is not OriginalObjectRefV1 or type(self.reservation_id) is not UUID:
            raise ValueError('exact original/reservation identities required')
        self.original.__post_init__()
    @property
    def key(self):
        o=self.original
        return f'source-originals/{o.workspace_id}/{o.source_id}/{o.revision}/{self.reservation_id}'
    @property
    def byte_count(self):return self.original.byte_count
    @property
    def original_sha256(self):return self.original.original_sha256
    @property
    def content_type(self):return self.original.content_type

def _private_stat(info,*,directory=False):
    if (info.st_uid!=os.getuid() or info.st_mode&0o077
        or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink!=1)):
        raise PermissionError('immutable private storage ownership/type/link/mode differs')

def _parent_fd(root,parts,*,create,strict=True):
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        if strict:_private_stat(os.fstat(fd),directory=True)
        for part in parts:
            if not part or part in ('.','..') or '/' in part or '\\' in part:raise ValueError('invalid private path component')
            if create:
                try:os.mkdir(part,0o700,dir_fd=fd);os.fsync(fd)
                except FileExistsError:pass
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            try:
                if strict:_private_stat(os.fstat(child),directory=True)
            except BaseException:os.close(child);raise
            os.close(fd);fd=child
        return fd
    except BaseException:os.close(fd);raise

def _read_private_at(parent,name,limit,*,strict=True):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if strict:_private_stat(before)
        if before.st_size>limit:raise ValueError('private object exceeds exact bounded size')
        data=stream.read(limit+1);after=os.fstat(stream.fileno())
        if strict:_private_stat(after)
        if len(data)>limit or (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise ValueError('private object changed during read')
        return data

def _write_private_at(root,parts,data,*,strict=True):
    """Shared immutable byte primitive; no scope/authority is issued here."""
    parent=_parent_fd(root,parts[:-1],create=True,strict=strict);name=parts[-1];created=None
    try:
        try:fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
        except FileExistsError:
            if _read_private_at(parent,name,len(data),strict=strict)!=data:raise ValueError('same immutable key has different bytes')
        else:
            try:
                created=os.fstat(fd)
                if strict:_private_stat(created)
                with os.fdopen(fd,'wb') as stream:
                    stream.write(data);stream.flush();os.fsync(stream.fileno())
                os.fsync(parent)
                if _read_private_at(parent,name,len(data),strict=strict)!=data:raise ValueError('immutable write readback differs')
            except BaseException:
                # Never remove an existing idempotent object or a replaced link.
                if created is not None:
                    current=os.stat(name,dir_fd=parent,follow_symlinks=False)
                    if (current.st_dev,current.st_ino)==(created.st_dev,created.st_ino):
                        os.unlink(name,dir_fd=parent);os.fsync(parent)
                raise
    finally:os.close(parent)

def _original_bytes(ref,data):
    if type(ref) not in (OriginalObjectRefV1,ReservationOriginalObjectRefV1) or type(data) is not bytes:raise ValueError('exact private original identity/bytes required')
    ref.__post_init__()
    if len(data)!=ref.byte_count or hashlib.sha256(data).hexdigest()!=ref.original_sha256:raise ValueError('original byte seal differs')

class FileBlobStore:
    """Local/restore implementation; production uses the same sealed-blob protocol."""
    def __init__(self, root: Path):
        self._original_root_alias=root.is_symlink()
        self.root = root.resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.stat().st_mode & 0o077:
            raise PermissionError('blob root must be private')

    def put(self, workspace_id: UUID, payload: dict) -> tuple[str, str]:
        data = canonical_bytes(payload)
        seal = hashlib.sha256(data).hexdigest()
        key = f'operating-model/{workspace_id}/{seal}.json'
        self._path(key)
        # Legacy JSON namespace retains its existing directory/file permissions.
        # Only the new original namespace requires stricter ownership/link modes.
        _write_private_at(self.root,key.split('/'),data,strict=False)
        self.read(key, seal)
        return key, seal

    def _path(self, key: str) -> Path:
        parts = key.split('/')
        if len(parts) != 3 or parts[0] != 'operating-model':
            raise ValueError('invalid blob namespace')
        UUID(parts[1])
        if len(parts[2]) != 69 or not parts[2].endswith('.json') or any(c not in '0123456789abcdef' for c in parts[2][:-5]):
            raise ValueError('invalid blob key')
        candidate = self.root.joinpath(*parts)
        if not candidate.resolve().is_relative_to(self.root) or any(p.is_symlink() for p in (candidate, candidate.parent, candidate.parent.parent)):
            raise PermissionError('blob path escaped private root')
        return candidate

    def read(self, key: str, expected_hash: str) -> bytes:
        path = self._path(key)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            data = stream.read()
        if hashlib.sha256(data).hexdigest() != expected_hash or path.name != expected_hash + '.json':
            raise ValueError('artifact payload seal mismatch')
        return data

    # Deliberately private I/O primitives. There is NO admitted lifecycle
    # factory/public raw intake route; callers cannot manufacture authority.
    def _put_original_bytes(self,ref:OriginalObjectRefV1,data:bytes):
        if self._original_root_alias:raise PermissionError('private original root alias denied')
        _original_bytes(ref,data);_write_private_at(self.root,ref.key.split('/'),data)
        return ref
    def _read_original_bytes(self,ref:OriginalObjectRefV1):
        if self._original_root_alias:raise PermissionError('private original root alias denied')
        if type(ref) not in (OriginalObjectRefV1,ReservationOriginalObjectRefV1):raise ValueError('exact private original identity required')
        ref.__post_init__();parts=ref.key.split('/');parent=_parent_fd(self.root,parts[:-1],create=False)
        try:data=_read_private_at(parent,parts[-1],ref.byte_count)
        finally:os.close(parent)
        _original_bytes(ref,data);return data

class ObjectBlobStore:
    """Private admitted S3-compatible store; exact-byte seal is checked on every read."""
    def __init__(self,client,bucket:str):
        if not bucket:raise ValueError('admitted private bucket required')
        self.client,self.bucket=client,bucket
    @staticmethod
    def validate_key(key):
        parts=key.split('/')
        if len(parts)!=3 or parts[0]!='operating-model':raise ValueError('invalid blob namespace')
        UUID(parts[1])
        if len(parts[2])!=69 or not parts[2].endswith('.json') or any(c not in '0123456789abcdef' for c in parts[2][:-5]):raise ValueError('invalid blob key')
    def put(self,workspace_id:UUID,payload:dict):
        data=canonical_bytes(payload);seal=hashlib.sha256(data).hexdigest()
        key=f'operating-model/{workspace_id}/{seal}.json'
        try:
            self.client.put_object(Bucket=self.bucket,Key=key,Body=data,ContentType='application/json',IfNoneMatch='*')
        except Exception as error:
            status=getattr(error,'response',{}).get('ResponseMetadata',{}).get('HTTPStatusCode')
            if status not in (409,412):raise RuntimeError('private immutable object write failed') from None
        if self.read(key,seal)!=data:raise ValueError('object seal mismatch after write')
        return key,seal
    def read(self,key,expected_hash):
        self.validate_key(key)
        body=self.client.get_object(Bucket=self.bucket,Key=key)['Body']
        try:data=body.read()
        finally:body.close()
        if hashlib.sha256(data).hexdigest()!=expected_hash or key.rsplit('/',1)[1]!=expected_hash+'.json':raise ValueError('private object seal mismatch')
        return data

    def _put_original_bytes(self,ref:OriginalObjectRefV1,data:bytes):
        _original_bytes(ref,data)
        try:self.client.put_object(Bucket=self.bucket,Key=ref.key,Body=data,ContentType=ref.content_type,IfNoneMatch='*')
        except Exception as error:
            status=getattr(error,'response',{}).get('ResponseMetadata',{}).get('HTTPStatusCode')
            if status not in (409,412):raise RuntimeError('private immutable original write failed') from None
        if self._read_original_bytes(ref)!=data:raise ValueError('original object readback differs')
        return ref
    def _read_original_bytes(self,ref:OriginalObjectRefV1):
        if type(ref) not in (OriginalObjectRefV1,ReservationOriginalObjectRefV1):raise ValueError('exact private original identity required')
        ref.__post_init__();body=self.client.get_object(Bucket=self.bucket,Key=ref.key)['Body']
        try:data=body.read(ref.byte_count+1)
        finally:body.close()
        _original_bytes(ref,data);return data
