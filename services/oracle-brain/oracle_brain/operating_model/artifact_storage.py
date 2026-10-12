"""Write-once private artifacts. A blob alone never confers serving authority."""
import hashlib
import os
from pathlib import Path
from uuid import UUID
from .contracts import canonical_bytes

class FileBlobStore:
    """Local/restore implementation; production uses the same sealed-blob protocol."""
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.stat().st_mode & 0o077:
            raise PermissionError('blob root must be private')

    def put(self, workspace_id: UUID, payload: dict) -> tuple[str, str]:
        data = canonical_bytes(payload)
        seal = hashlib.sha256(data).hexdigest()
        key = f'operating-model/{workspace_id}/{seal}.json'
        path = self._path(key)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            if self.read(key, seal) != data:
                raise ValueError('same immutable key has different bytes')
        else:
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                path.unlink(missing_ok=True)
                raise
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
