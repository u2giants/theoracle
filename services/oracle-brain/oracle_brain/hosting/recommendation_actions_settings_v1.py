"""Uninstalled fixed advice read/feedback/measurement consumers, not appointments."""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from uuid import UUID
import os,stat
from pydantic import AwareDatetime,Field,model_validator
from cryptography import x509
from ..operating_model.contracts import StrictRecord
from ..operating_model.consultant.recommendation_authority_v1 import RecommendationBindingV1,RecommendationAuthorityV1
from .original_intake_v1 import ProtectedInputV1,_pinned,_parse
from .consolidation_review_settings_v1 import _with_identity

HASH=r'^[a-f0-9]{64}$'
class RecommendationConsumerV1(StrictRecord):
    appointment_id:UUID;principal_id:UUID;workspace_id:UUID;model_id:UUID
    operation:Literal['read','feedback','measurement'];session_login:str;expected_owner:str
    runtime_hash:str=Field(pattern=HASH);registry_hash:str=Field(pattern=HASH);config_hash:str=Field(pattern=HASH)
    ca_path:str;ca_sha256:str=Field(pattern=HASH);original_horizon:AwareDatetime
    capability_fingerprints:tuple[tuple[str,str,str],...]
    database_url:ProtectedInputV1
    def authority(self):
        values=self.model_dump(mode='python');values.pop('schema_version');url=values.pop('database_url')
        return RecommendationAuthorityV1(_pinned(url['path'],url['sha256'],16384).decode('utf8').strip(),binding=RecommendationBindingV1(**values))

class RecommendationConfigV1(StrictRecord):
    purpose:Literal['qualified-recommendation-actions-v1']
    principal_id:UUID;workspace_id:UUID;model_id:UUID
    read:RecommendationConsumerV1;feedback:RecommendationConsumerV1;measurement:RecommendationConsumerV1
    storage_root:str;storage_device:int=Field(strict=True,ge=0);storage_inode:int=Field(strict=True,gt=0);storage_uid:int=Field(strict=True,ge=0)
    storage_profile_hash:str=Field(pattern=HASH)
    original_horizon:AwareDatetime;expires_at:AwareDatetime
    @model_validator(mode='after')
    def distinct_consumers(self):
        consumers=(self.read,self.feedback,self.measurement)
        if (tuple(c.operation for c in consumers)!=('read','feedback','measurement')
                or len({c.session_login for c in consumers})!=3 or len({c.appointment_id for c in consumers})!=3
                or any((c.principal_id,c.workspace_id,c.model_id)!=(self.principal_id,self.workspace_id,self.model_id) for c in consumers)
                or not self.expires_at<=self.original_horizon or any(self.original_horizon>c.original_horizon for c in consumers)):
            raise ValueError('three independently installed exact advice consumers required')
        return self

class RecommendationPeerV1(StrictRecord):
    purpose:Literal['qualified-recommendation-actions-peer-v1'];config_sha256:str=Field(pattern=HASH)
    principal_id:UUID;workspace_id:UUID;model_id:UUID
    read_appointment_id:UUID;feedback_appointment_id:UUID;measurement_appointment_id:UUID
    issuer_actor:UUID;reviewer_actor:UUID
    client_certificate_sha256:str=Field(pattern=HASH);client_uri:str=Field(pattern=r'^spiffe://oracle/[a-zA-Z0-9/_-]+$')
    client_ca:ProtectedInputV1;server_certificate:ProtectedInputV1;server_key:ProtectedInputV1
    listen_host:Literal['127.0.0.1','::1'];listen_port:int=Field(strict=True,ge=0,le=65535)
    valid_from:AwareDatetime;expires_at:AwareDatetime;original_horizon:AwareDatetime
    @model_validator(mode='after')
    def independent(self):
        if len({self.principal_id,self.issuer_actor,self.reviewer_actor})!=3 or not self.valid_from<self.expires_at<=self.original_horizon:raise ValueError('independent finite advice peer required')
        return self

@dataclass(frozen=True)
class RecommendationSettingsV1:
    config_path:str;config_sha256:str;peer_path:str;peer_sha256:str
    expected_issuer_actor:UUID;expected_reviewer_actor:UUID
    config:RecommendationConfigV1;peer:RecommendationPeerV1
    file_identities:tuple;protected_identities:tuple
    @classmethod
    def load(cls,*,config_path,config_sha256,peer_path,peer_sha256,expected_issuer_actor,expected_reviewer_actor):
        raw,ci=_with_identity(config_path,config_sha256);other,pi=_with_identity(peer_path,peer_sha256)
        config=_parse(RecommendationConfigV1,raw);peer=_parse(RecommendationPeerV1,other)
        obj=cls(config_path,config_sha256,peer_path,peer_sha256,expected_issuer_actor,expected_reviewer_actor,config,peer,(ci,pi),cls._identities(config,peer))
        obj.current();return obj
    @staticmethod
    def _identities(config,peer):
        inputs=(peer.client_ca,peer.server_certificate,peer.server_key,
            *(c.database_url for c in (config.read,config.feedback,config.measurement)),
            *(ProtectedInputV1(path=c.ca_path,sha256=c.ca_sha256) for c in (config.read,config.feedback,config.measurement)))
        return tuple((i.path,i.sha256,_with_identity(i.path,i.sha256)[1]) for i in inputs)
    @property
    def profile(self):
        p=self.peer
        return SimpleNamespace(client_uri=p.client_uri,client_certificate_sha256=p.client_certificate_sha256,
            client_ca_file=p.client_ca.path,server_certificate_file=p.server_certificate.path,
            server_key_file=p.server_key.path,listen_host=p.listen_host,listen_port=p.listen_port)
    def current(self):
        c,p=self.config,self.peer
        raw,ci=_with_identity(self.config_path,self.config_sha256);other,pi=_with_identity(self.peer_path,self.peer_sha256)
        if ((ci,pi)!=self.file_identities or _parse(RecommendationConfigV1,raw)!=c or _parse(RecommendationPeerV1,other)!=p
                or self._identities(c,p)!=self.protected_identities):raise PermissionError('protected advice installation changed')
        if (p.config_sha256!=self.config_sha256 or (p.principal_id,p.workspace_id,p.model_id)!=(c.principal_id,c.workspace_id,c.model_id)
                or (p.read_appointment_id,p.feedback_appointment_id,p.measurement_appointment_id)!=(c.read.appointment_id,c.feedback.appointment_id,c.measurement.appointment_id)
                or (p.issuer_actor,p.reviewer_actor)!=(self.expected_issuer_actor,self.expected_reviewer_actor)):
            raise PermissionError('independent advice appointments differ')
        now=datetime.now(timezone.utc);end=min(c.expires_at,c.original_horizon,p.expires_at,p.original_horizon)
        if not p.valid_from<=now<end:raise PermissionError('original advice installation expired')
        cert=x509.load_pem_x509_certificate(_pinned(p.server_certificate.path,p.server_certificate.sha256))
        if not cert.not_valid_before_utc<=now<cert.not_valid_after_utc:raise PermissionError('advice certificate expired')
        root=Path(c.storage_root)
        if not root.is_absolute() or str(root.resolve(strict=True))!=str(root):raise PermissionError('exact private advice root required')
        info=root.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_mode&0o077 or info.st_uid!=os.getuid()
                or (info.st_dev,info.st_ino,info.st_uid)!=(c.storage_device,c.storage_inode,c.storage_uid)):
            raise PermissionError('private advice root changed')
        consumers=tuple(item.authority() for item in (c.read,c.feedback,c.measurement))
        targets={(a.params['host'],a.params.get('hostaddr'),a.params['port'],a.params['dbname'],a.binding.expected_owner) for a in consumers}
        if len(targets)!=1:raise PermissionError('three advice consumers must share exact installed store')
        return min(end,cert.not_valid_after_utc)
    def consumers(self):
        self.current()
        return tuple(item.authority() for item in (self.config.read,self.config.feedback,self.config.measurement))
