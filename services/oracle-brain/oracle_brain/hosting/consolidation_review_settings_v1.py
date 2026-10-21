"""Uninstalled exact two-role model-review consumer; no appointment issuance."""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import UUID
import os,stat,hashlib
from pydantic import AwareDatetime,Field,model_validator
from cryptography import x509
from oracle_brain.operating_model.contracts import StrictRecord
from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationBindingV1,ConsolidationAuthorityV1
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from .original_intake_v1 import ProtectedInputV1,_pinned,_parse

HASH=r'^[a-f0-9]{64}$'
def _with_identity(path,seal):
    def identity():
        info=Path(path).lstat()
        return (info.st_dev,info.st_ino,info.st_uid,info.st_mode,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
    before=identity();raw=_pinned(path,seal)
    if identity()!=before:raise PermissionError('review input identity changed')
    return raw,before

class ReviewConsumerV1(StrictRecord):
    appointment_id:UUID;principal_id:UUID;workspace_id:UUID;model_id:UUID
    session_login:str;expected_owner:str;operation:Literal['history-read','business-review']
    runtime_hash:str=Field(pattern=HASH);registry_hash:str=Field(pattern=HASH);config_hash:str=Field(pattern=HASH)
    ca_path:str;ca_sha256:str=Field(pattern=HASH);original_horizon:AwareDatetime
    retained_semantic_admissions:tuple[str,...]=Field(min_length=1,max_length=64)
    capability_body_hashes:tuple[tuple[str,str],...]
    database_url:ProtectedInputV1
    def authority(self):
        values=self.model_dump(mode='python');values.pop('schema_version');url=values.pop('database_url')
        values['retained_semantic_admissions']=frozenset(values['retained_semantic_admissions'])
        binding=ConsolidationBindingV1(**values)
        return ConsolidationAuthorityV1(_pinned(url['path'],url['sha256'],16384).decode('utf8').strip(),binding=binding)

class ModelReviewConfigV1(StrictRecord):
    schema_version:Literal[1];purpose:Literal['qualified-model-review-v1']
    principal_id:UUID;workspace_id:UUID;model_id:UUID
    history:ReviewConsumerV1;business:ReviewConsumerV1
    decision_kind:Literal['employee-account','process-policy','company-policy']
    storage_root:str;storage_device:int=Field(strict=True,ge=0);storage_inode:int=Field(strict=True,gt=0);storage_uid:int=Field(strict=True,ge=0)
    storage_profile_hash:str=Field(pattern=HASH)
    original_horizon:AwareDatetime;expires_at:AwareDatetime
    @model_validator(mode='after')
    def exact_pair(self):
        h,b=self.history,self.business
        if (h.operation!='history-read' or b.operation!='business-review' or h.session_login==b.session_login
            or h.appointment_id==b.appointment_id or not self.expires_at<=self.original_horizon
            or any((c.principal_id,c.workspace_id,c.model_id)!=(self.principal_id,self.workspace_id,self.model_id) for c in (h,b))
            or any(self.original_horizon>c.original_horizon for c in (h,b))):raise ValueError('two separately appointed exact own-role consumers required')
        return self

class ModelReviewPeerV1(StrictRecord):
    schema_version:Literal[1];purpose:Literal['qualified-model-review-peer-v1']
    config_sha256:str=Field(pattern=HASH)
    principal_id:UUID;workspace_id:UUID;model_id:UUID
    history_appointment_id:UUID;business_appointment_id:UUID
    issuer_actor:UUID;reviewer_actor:UUID
    client_certificate_sha256:str=Field(pattern=HASH);client_uri:str=Field(pattern=r'^spiffe://oracle/[a-zA-Z0-9/_-]+$')
    client_ca:ProtectedInputV1;server_certificate:ProtectedInputV1;server_key:ProtectedInputV1
    listen_host:Literal['127.0.0.1','::1'];listen_port:int=Field(strict=True,ge=0,le=65535)
    valid_from:AwareDatetime;expires_at:AwareDatetime;original_horizon:AwareDatetime
    @model_validator(mode='after')
    def independent(self):
        if len({self.principal_id,self.issuer_actor,self.reviewer_actor})!=3 or not self.valid_from<self.expires_at<=self.original_horizon:raise ValueError('independent finite review peer required')
        return self

@dataclass(frozen=True)
class ModelReviewSettingsV1:
    config_path:str;config_sha256:str;peer_path:str;peer_sha256:str
    expected_issuer_actor:UUID;expected_reviewer_actor:UUID
    config:ModelReviewConfigV1;peer:ModelReviewPeerV1
    file_identities:tuple
    protected_identities:tuple
    @classmethod
    def load(cls,*,config_path,config_sha256,peer_path,peer_sha256,expected_issuer_actor,expected_reviewer_actor):
        raw,ci=_with_identity(config_path,config_sha256);other,pi=_with_identity(peer_path,peer_sha256)
        config=_parse(ModelReviewConfigV1,raw);peer=_parse(ModelReviewPeerV1,other)
        obj=cls(config_path,config_sha256,peer_path,peer_sha256,expected_issuer_actor,expected_reviewer_actor,config,peer,(ci,pi),cls._identities(config,peer))
        obj.current();return obj
    @staticmethod
    def _identities(config,peer):
        inputs=(peer.client_ca,peer.server_certificate,peer.server_key,config.history.database_url,config.business.database_url,
            ProtectedInputV1(path=config.history.ca_path,sha256=config.history.ca_sha256),ProtectedInputV1(path=config.business.ca_path,sha256=config.business.ca_sha256))
        return tuple((item.path,item.sha256,_with_identity(item.path,item.sha256)[1]) for item in inputs)
    def current(self):
        config,peer=self.config,self.peer
        raw,ci=_with_identity(self.config_path,self.config_sha256);other,pi=_with_identity(self.peer_path,self.peer_sha256)
        if (ci,pi)!=self.file_identities or _parse(ModelReviewConfigV1,raw)!=config or _parse(ModelReviewPeerV1,other)!=peer:raise PermissionError('review protected installation changed')
        if (peer.config_sha256!=self.config_sha256 or (peer.principal_id,peer.workspace_id,peer.model_id)!=(config.principal_id,config.workspace_id,config.model_id)
            or (peer.history_appointment_id,peer.business_appointment_id)!=(config.history.appointment_id,config.business.appointment_id)
            or (peer.issuer_actor,peer.reviewer_actor)!=(self.expected_issuer_actor,self.expected_reviewer_actor)
            or self.expected_issuer_actor==self.expected_reviewer_actor):raise PermissionError('review installation appointment differs')
        if self._identities(config,peer)!=self.protected_identities:raise PermissionError('review protected dependency changed')
        now=datetime.now(timezone.utc);end=min(peer.expires_at,peer.original_horizon,config.expires_at,config.original_horizon)
        if not peer.valid_from<=now<end:raise PermissionError('original review appointment expired')
        for item in (peer.client_ca,peer.server_certificate,peer.server_key):_pinned(item.path,item.sha256)
        cert=x509.load_pem_x509_certificate(_pinned(peer.server_certificate.path,peer.server_certificate.sha256))
        if not cert.not_valid_before_utc<=now<cert.not_valid_after_utc:raise PermissionError('review server certificate expired')
        path=Path(config.storage_root)
        if not path.is_absolute() or str(path.resolve(strict=True))!=str(path):raise PermissionError('review root must be exact installed path')
        info=path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_mode&0o077 or (info.st_dev,info.st_ino,info.st_uid)!=(config.storage_device,config.storage_inode,config.storage_uid) or info.st_uid!=os.getuid():raise PermissionError('review private root changed')
        # Each exact SQL consumer independently rechecks pinned CA and URL.
        config.history.authority();config.business.authority()
        return min(end,cert.not_valid_after_utc)
    def consumers(self):
        self.current()
        return self.config.history.authority(),self.config.business.authority(),FileBlobStore(Path(self.config.storage_root))
