"""Single pure protected-byte and strict-record owner; no runtime authority.

Hosting APIs forward these same objects. File ownership/custody and canonical
bytes remain mandatory; these primitives never appoint a principal or operation.
"""
from pathlib import Path
import hashlib,json,os,stat
from pydantic import Field
from .contracts import StrictRecord,canonical_bytes

class ProtectedInputV1(StrictRecord):
    path:str;sha256:str=Field(pattern=r'^[a-f0-9]{64}$')

def protected_file(path, *, limit=1_000_000):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise PermissionError('protected operator file required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        if os.fstat(stream.fileno()).st_mode & 0o077:
            raise PermissionError('protected operator file required')
        raw=stream.read(limit+1)
    if len(raw)>limit:raise PermissionError('operator file exceeds bound')
    return raw


def _pinned(path,seal,limit=65536):
    p=Path(path)
    if not p.is_absolute() or p.resolve()!=p:raise PermissionError('canonical protected input required')
    before=p.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or before.st_nlink!=1 or before.st_mode&0o077:raise PermissionError('private owned input required')
    raw=protected_file(p,limit=limit);after=p.lstat()
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) or hashlib.sha256(raw).hexdigest()!=seal:raise PermissionError('protected input changed')
    return raw

def parse_canonical_object_v1(raw,*,limit=65536):
    if type(raw) is not bytes or not 1<=len(raw)<=limit:
        raise ValueError('bounded canonical object bytes required')
    def unique(pairs):
        out={}
        for key,value in pairs:
            if key in out:raise ValueError('duplicate canonical field')
            out[key]=value
        return out
    def constant(_):raise ValueError('nonfinite canonical field')
    value=json.loads(raw,object_pairs_hook=unique,parse_constant=constant)
    if type(value) is not dict or canonical_bytes(value)!=raw:
        raise ValueError('exact canonical object required')
    return value

def _parse(cls,raw):
    parse_canonical_object_v1(raw,limit=max(65536,len(raw)))
    value=cls.model_validate_json(raw)
    if canonical_bytes(value.model_dump(mode='json'))!=raw:
        raise ValueError('canonical protected record required')
    return value
