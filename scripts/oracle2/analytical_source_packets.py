"""Inert public-source multipart mechanics, not product/delivery admission.

No route or downloader. Only a trusted server-owned independent current resolver
may provide permission. The default resolver is absent and denies before bytes.
The OS owner/cache custody remains trusted; fixtures issue no real permission.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import secrets
import time

_spec=importlib.util.spec_from_file_location('analytical_packet_validator',Path(__file__).with_name('validate_analytical_packet.py'))
validator=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(validator)


def require(ok,message):
    if not ok:raise ValueError(message)

def sha(value):return hashlib.sha256(value).hexdigest()
def seal(value):return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None

def decode(raw):
    def pairs(rows):
        result={}
        for k,v in rows:require(k not in result,'duplicate manifest field');result[k]=v
        return result
    return json.loads(raw,object_pairs_hook=pairs)

@dataclass(frozen=True)
class ProductBinding:
    manifest_sha256: str
    source_revision: str
    image_digest: str
    def validate(self):
        require(seal(self.manifest_sha256) and isinstance(self.source_revision,str) and re.fullmatch('[0-9a-f]{40}',self.source_revision) is not None
                and isinstance(self.image_digest,str) and re.fullmatch('sha256:[0-9a-f]{64}',self.image_digest) is not None,'exact typed product binding required')

@dataclass(frozen=True)
class DeliveryGrant:
    binding: ProductBinding
    principal: str
    permissions_revision: str
    issuer: str
    reviewer: str
    product_review_sha256: str
    notice_review_sha256: str
    delivery_review_sha256: str
    expires_at: int
    rights: frozenset

class CurrentProductDeliveryAuthority(ABC):
    """Trusted integration dependency; never populated from request JSON.

No implementation/registry is installed by this module. A future root-reviewed
integration must establish authentic independent product/notice/delivery receipts
and current permissions. Subclassing is a server trust decision, not a grant.
"""
    @abstractmethod
    def current(self,principal,binding):raise NotImplementedError

@dataclass(frozen=True)
class ChunkRequest:
    binding: ProductBinding
    principal: str
    artifact_id: str
    chunk_index: int
    start: int
    end: int


def stat_record(info):
    return (info.st_dev,info.st_ino,info.st_uid,info.st_mode,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)

def directory_fd(path):
    path=Path(path);require(path.is_absolute() and '..' not in path.parts,'fixed absolute custody root required')
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=new
        info=os.fstat(fd);require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'owned private directory required')
        return fd
    except Exception:os.close(fd);raise

class SourcePacketStore:
    """Fixed local artifact inventory. No caller path/URL/filename is accepted."""
    def __init__(self,manifest_bytes,lock_bytes,recipe_bytes,context_bytes,binding,source_root,cache_root,*,authority=None,clock=time.time):
        require(type(binding) is ProductBinding,'typed server product binding required');binding.validate()
        require(type(manifest_bytes) is bytes and len(manifest_bytes)<=1024*1024 and sha(manifest_bytes)==binding.manifest_sha256,'whole source manifest differs')
        packet=decode(manifest_bytes)
        self.diagnostics=validator.inspect_packet(packet,lock_bytes,recipe_bytes,context_bytes)
        require(all(type(a.get('notices')) is dict and bool(a['notices']) for a in packet['artifacts']),'complete fixed notice inventory required')
        require(packet['source_revision'] in (None,binding.source_revision) and packet['image_digest'] in (None,binding.image_digest),'manifest product identity differs')
        require(authority is None or isinstance(authority,CurrentProductDeliveryAuthority),'trusted independent resolver required; caller callback/bool/hash refused')
        self.binding=binding;self.authority=authority;self.clock=clock
        self.artifacts={a['id']:a for a in packet['artifacts']};self.verified={}
        self.source_root=Path(source_root);self.cache_root=Path(cache_root)
        # Source/cache directories are examined lazily AFTER current permission.
    def _grant(self,principal):
        require(isinstance(principal,str) and bool(principal),'current principal required')
        require(self.authority is not None,'independent current product-delivery resolver unavailable')
        grant=self.authority.current(principal,self.binding)
        require(type(grant) is DeliveryGrant and type(grant.binding) is ProductBinding and grant.binding==self.binding and grant.principal==principal,'current product delivery denied')
        require(type(grant.permissions_revision) is str and bool(grant.permissions_revision) and isinstance(grant.issuer,str) and bool(grant.issuer)
                and isinstance(grant.reviewer,str) and bool(grant.reviewer) and grant.issuer!=grant.reviewer and grant.issuer!=principal and grant.reviewer!=principal,'independent current permission provenance required')
        require(all(seal(v) for v in (grant.product_review_sha256,grant.notice_review_sha256,grant.delivery_review_sha256)),'independent product/notice/delivery receipts required')
        require(type(grant.expires_at) is int and self.clock()<grant.expires_at and type(grant.rights) is frozenset and grant.rights==frozenset({'source_delivery'}),'current exact source-delivery permission required')
        return grant
    def _recheck(self,principal,grant):require(self._grant(principal)==grant,'permission/product binding moved during delivery')
    def _verify_artifact(self,identity,principal,grant):
        if identity in self.verified:return self.verified[identity]
        artifact=self.artifacts[identity]
        self._recheck(principal,grant)
        source_fd=directory_fd(self.source_root)
        try:cache_fd=directory_fd(self.cache_root)
        except Exception:os.close(source_fd);raise
        fd=None;temporary=None;temporary_fd=None;temporary_identity=None
        try:
            fd=os.open(artifact['filename'],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=source_fd);before=os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_nlink==1 and not stat.S_IMODE(before.st_mode)&0o077 and before.st_size==artifact['bytes'],'fixed protected artifact size/custody differs')
            candidate='.verification-'+secrets.token_hex(16)
            temporary_fd=os.open(candidate,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=cache_fd)
            temporary=candidate
            initial=os.fstat(temporary_fd);temporary_identity=(initial.st_dev,initial.st_ino)
            require(stat.S_ISREG(initial.st_mode) and initial.st_uid==os.getuid() and initial.st_nlink==1 and stat.S_IMODE(initial.st_mode)==0o600,'owned exclusive verification leaf required')
            hasher=hashlib.sha256();actual=0
            while True:
                self._recheck(principal,grant)
                chunk=os.read(fd,min(validator.CHUNK,artifact['bytes']-actual+1))
                if not chunk:break
                actual+=len(chunk);require(actual<=artifact['bytes'] and actual<=validator.LIMIT,'actual intact archive exceeds bound')
                hasher.update(chunk)
                pending=memoryview(chunk)
                while pending:
                    written=os.write(temporary_fd,pending);require(written>0,'verification write incomplete');pending=pending[written:]
            require(actual==artifact['bytes'] and hasher.hexdigest()==artifact['sha256'] and stat_record(os.fstat(fd))==stat_record(before),'full actual archive integrity differs')
            self._recheck(principal,grant);os.fchmod(temporary_fd,0o400);os.fsync(temporary_fd)
            held=os.fstat(temporary_fd);leaf=os.stat(temporary,dir_fd=cache_fd,follow_symlinks=False)
            require((held.st_dev,held.st_ino)==temporary_identity and stat.S_ISREG(held.st_mode) and held.st_uid==os.getuid() and stat.S_IMODE(held.st_mode)==0o400 and held.st_nlink==1 and held.st_size==artifact['bytes'] and stat_record(leaf)==stat_record(held),'held verification inode changed')
            # Both names resolve only within the already held cache directory.
            # An existing published hash is never overwritten or reused.
            filename=artifact['sha256']+'.archive'
            os.link(temporary,filename,src_dir_fd=cache_fd,dst_dir_fd=cache_fd,follow_symlinks=False)
            linked=os.stat(filename,dir_fd=cache_fd,follow_symlinks=False);held=os.fstat(temporary_fd)
            require((held.st_dev,held.st_ino)==temporary_identity and held.st_nlink==2 and stat.S_IMODE(held.st_mode)==0o400 and held.st_uid==os.getuid() and stat_record(linked)==stat_record(held),'published verification inode differs')
            os.unlink(temporary,dir_fd=cache_fd);temporary=None
            os.fsync(cache_fd)
            held=os.fstat(temporary_fd);cached=os.stat(filename,dir_fd=cache_fd,follow_symlinks=False)
            require((held.st_dev,held.st_ino)==temporary_identity and held.st_nlink==1 and stat.S_IMODE(held.st_mode)==0o400 and held.st_uid==os.getuid() and stat_record(cached)==stat_record(held),'immutable published cache custody differs')
            self.verified[identity]=(filename,stat_record(cached))
            return self.verified[identity]
        finally:
            # Only our exclusively created leaf under the held directory may be
            # removed. A replaced/colliding foreign leaf is preserved on refusal.
            try:
                if temporary is not None:
                    try:
                        leaf=os.stat(temporary,dir_fd=cache_fd,follow_symlinks=False)
                        if (leaf.st_dev,leaf.st_ino)==temporary_identity:os.unlink(temporary,dir_fd=cache_fd)
                    except FileNotFoundError:pass
            finally:
                if temporary_fd is not None:os.close(temporary_fd)
                if fd is not None:os.close(fd)
                os.close(source_fd);os.close(cache_fd)
    def serve(self,request):
        require(type(request) is ChunkRequest and type(request.binding) is ProductBinding and request.binding==self.binding,'request whole manifest/revision/image differs')
        grant=self._grant(request.principal) # BEFORE source/cache byte opens
        require(request.artifact_id in self.artifacts,'unknown fixed artifact identity')
        artifact=self.artifacts[request.artifact_id];size=artifact['bytes']
        require(type(request.chunk_index) is int and request.chunk_index>=0 and type(request.start) is int and type(request.end) is int,'exact typed chunk/range required')
        start=request.chunk_index*validator.CHUNK;end=min(start+validator.CHUNK,size)
        require(0<=start<end<=size and (request.start,request.end)==(start,end),'exact bounded chunk/range required')
        filename,expected=self._verify_artifact(request.artifact_id,request.principal,grant)
        self._recheck(request.principal,grant);cache_fd=directory_fd(self.cache_root)
        try:
            fd=os.open(filename,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=cache_fd)
            try:
                info=os.fstat(fd);require(stat_record(info)==expected and stat.S_IMODE(info.st_mode)==0o400 and info.st_nlink==1,'immutable verified cache moved')
                payload=os.pread(fd,end-start,start)
                require(len(payload)==end-start and stat_record(os.fstat(fd))==expected,'verified chunk changed')
                self._recheck(request.principal,grant)
            finally:os.close(fd)
        finally:os.close(cache_fd)
        return {'binding':self.binding,'artifact_id':request.artifact_id,'artifact_sha256':artifact['sha256'],'artifact_bytes':size,
            'chunk_index':request.chunk_index,'start':start,'end':end,'chunk_sha256':sha(payload),'payload':payload,
            'product_admission':False,'delivery_decision_issued':False}

def reconstruction_proof(binding,artifact_id,expected_sha256,expected_bytes,chunks):
    """Client integrity proof only; never an admission/permission receipt."""
    require(type(binding) is ProductBinding,'typed exact product binding required');binding.validate()
    require(seal(expected_sha256) and type(expected_bytes) is int and 0<expected_bytes<=validator.LIMIT,'fixed archive reconstruction identity required')
    count=(expected_bytes+validator.CHUNK-1)//validator.CHUNK;require(type(chunks) is list and len(chunks)==count,'complete chunk population required')
    assembled=bytearray()
    for index,chunk in enumerate(chunks):
        start=index*validator.CHUNK;end=min(start+validator.CHUNK,expected_bytes)
        require(chunk['binding']==binding and chunk['artifact_id']==artifact_id and chunk['artifact_sha256']==expected_sha256 and chunk['artifact_bytes']==expected_bytes
                and chunk['chunk_index']==index and chunk['start']==start and chunk['end']==end and type(chunk['payload']) is bytes
                and len(chunk['payload'])==end-start and sha(chunk['payload'])==chunk['chunk_sha256'],'cross-artifact/product/order/range/chunk integrity differs')
        assembled.extend(chunk['payload'])
    require(len(assembled)==expected_bytes and sha(assembled)==expected_sha256,'intact reconstructed archive differs')
    return {'kind':'source-archive-reconstruction-integrity-only','manifest_sha256':binding.manifest_sha256,'source_revision':binding.source_revision,
        'image_digest':binding.image_digest,'artifact_id':artifact_id,'bytes':expected_bytes,'sha256':expected_sha256,'product_admission':False,'delivery_decision_issued':False}
