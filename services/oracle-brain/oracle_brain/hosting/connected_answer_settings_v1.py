"""Protected own-recipient connected answer startup; consumes no caller authority."""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import UUID
import os,stat
from pydantic import AwareDatetime,Field,model_validator
from cryptography import x509
from oracle_brain.operating_model.contracts import StrictRecord
from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationAuthorityV1,ConsolidationBindingV1
from oracle_brain.operating_model.protected_inputs_v1 import ProtectedInputV1,_pinned,_parse,parse_canonical_object_v1
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.request_deadline_v1 import request_remaining_v1
from .consolidation_review_settings_v1 import ReviewConsumerV1,_with_identity
HASH=r'^[a-f0-9]{64}$'

class AnswerConsumerV1(ReviewConsumerV1):
    operation:Literal['history-read']='history-read'
    delivery_capability_body_hashes:tuple[tuple[str,str],...]
    def authority(self):
        values=self.model_dump(mode='python');values.pop('schema_version');url=values.pop('database_url');pins=values.pop('delivery_capability_body_hashes')
        values['retained_semantic_admissions']=frozenset(values['retained_semantic_admissions'])
        return ConsolidationAuthorityV1(_pinned(url['path'],url['sha256'],16384).decode('utf8'),binding=ConsolidationBindingV1(**values),delivery_capability_body_hashes=pins)

class AnswerProjectionV1(StrictRecord):
    version:int=Field(ge=1);generation:UUID
    graph_url:ProtectedInputV1

class ConnectedAnswerConfigV1(StrictRecord):
    purpose:Literal['qualified-connected-answer-v1']='qualified-connected-answer-v1'
    principal_id:UUID;workspace_id:UUID;model_id:UUID
    history:AnswerConsumerV1
    projections:tuple[AnswerProjectionV1,...]=Field(min_length=1,max_length=64)
    graph_ca:ProtectedInputV1;graph_certificate:ProtectedInputV1;graph_key:ProtectedInputV1
    graph_client_uri:str=Field(pattern=r'^spiffe://oracle/[a-zA-Z0-9/_-]+$')
    graph_server_uri:str=Field(pattern=r'^spiffe://oracle/[a-zA-Z0-9/_-]+$')
    storage_root:str;storage_device:int=Field(ge=0);storage_inode:int=Field(gt=0);storage_uid:int=Field(ge=0)
    storage_profile_hash:str=Field(pattern=HASH)
    original_horizon:AwareDatetime;expires_at:AwareDatetime
    @model_validator(mode='after')
    def exact_recipient(self):
        if ((self.history.principal_id,self.history.workspace_id,self.history.model_id)!=(self.principal_id,self.workspace_id,self.model_id)
            or not self.expires_at<=self.original_horizon<=self.history.original_horizon
            or len({p.version for p in self.projections})!=len(self.projections)
            or len({p.generation for p in self.projections})!=len(self.projections)
            or self.graph_client_uri==self.graph_server_uri):
            raise ValueError('exact separately appointed history recipient/projection population required')
        return self


class ConnectedIndustryAnswerConfigV1(ConnectedAnswerConfigV1):
    """A distinct independently installed profile; original v1 bytes stay valid."""
    purpose:Literal['qualified-connected-industry-answer-v1']='qualified-connected-industry-answer-v1'
    industry_readers:tuple[ProtectedInputV1,...]=Field(min_length=1,max_length=32)


def _answer_config_v1(raw):
    purpose=parse_canonical_object_v1(raw,limit=max(65536,len(raw))).get('purpose')
    cls={'qualified-connected-answer-v1':ConnectedAnswerConfigV1,
         'qualified-connected-industry-answer-v1':ConnectedIndustryAnswerConfigV1}.get(purpose)
    if cls is None:raise PermissionError('fixed independently installed answer purpose required')
    return _parse(cls,raw)


class ConnectedAnswerPeerV1(StrictRecord):
    purpose:Literal['qualified-connected-answer-peer-v1']='qualified-connected-answer-peer-v1'
    config_sha256:str=Field(pattern=HASH)
    principal_id:UUID;workspace_id:UUID;model_id:UUID;history_appointment_id:UUID
    channel:Literal['web','mcp']
    issuer_actor:UUID;reviewer_actor:UUID
    client_certificate_sha256:str=Field(pattern=HASH);client_uri:str=Field(pattern=r'^spiffe://oracle/[a-zA-Z0-9/_-]+$')
    client_ca:ProtectedInputV1;server_certificate:ProtectedInputV1;server_key:ProtectedInputV1
    listen_host:Literal['127.0.0.1','::1'];listen_port:int=Field(ge=0,le=65535)
    valid_from:AwareDatetime;expires_at:AwareDatetime;original_horizon:AwareDatetime
    @model_validator(mode='after')
    def independent(self):
        if len({self.principal_id,self.issuer_actor,self.reviewer_actor})!=3 or not self.valid_from<self.expires_at<=self.original_horizon:
            raise ValueError('independent finite answer peer required')
        return self

@dataclass(frozen=True)
class ConnectedAnswerSettingsV1:
    config_path:str;config_sha256:str;peer_path:str;peer_sha256:str
    expected_issuer_actor:UUID;expected_reviewer_actor:UUID
    config:ConnectedAnswerConfigV1|ConnectedIndustryAnswerConfigV1;peer:ConnectedAnswerPeerV1
    file_identities:tuple;protected_identities:tuple
    @classmethod
    def load(cls,*,config_path,config_sha256,peer_path,peer_sha256,expected_issuer_actor,expected_reviewer_actor):
        raw,ci=_with_identity(config_path,config_sha256);other,pi=_with_identity(peer_path,peer_sha256)
        c=_answer_config_v1(raw);p=_parse(ConnectedAnswerPeerV1,other)
        result=cls(str(config_path),config_sha256,str(peer_path),peer_sha256,expected_issuer_actor,expected_reviewer_actor,c,p,(ci,pi),cls._identities(c,p))
        result.current();return result
    @staticmethod
    def _identities(c,p):
        inputs=(c.history.database_url,ProtectedInputV1(path=c.history.ca_path,sha256=c.history.ca_sha256),c.graph_ca,c.graph_certificate,c.graph_key,p.client_ca,p.server_certificate,p.server_key,*(t.graph_url for t in c.projections),*(c.industry_readers if type(c) is ConnectedIndustryAnswerConfigV1 else ()))
        return tuple((v.path,v.sha256,_with_identity(v.path,v.sha256)[1]) for v in inputs)
    def current(self):
        request_remaining_v1(required=False)
        c,p=self.config,self.peer
        raw,ci=_with_identity(self.config_path,self.config_sha256);other,pi=_with_identity(self.peer_path,self.peer_sha256)
        if (ci,pi)!=self.file_identities or _answer_config_v1(raw)!=c or _parse(ConnectedAnswerPeerV1,other)!=p:
            raise PermissionError('protected answer installation changed')
        if (p.config_sha256!=self.config_sha256 or (p.principal_id,p.workspace_id,p.model_id,p.history_appointment_id)!=(c.principal_id,c.workspace_id,c.model_id,c.history.appointment_id)
            or (p.issuer_actor,p.reviewer_actor)!=(self.expected_issuer_actor,self.expected_reviewer_actor)
            or self._identities(c,p)!=self.protected_identities):raise PermissionError('answer current installation binding differs')
        now=datetime.now(timezone.utc);end=min(c.expires_at,c.original_horizon,p.expires_at,p.original_horizon)
        if not p.valid_from<=now<end:raise PermissionError('original answer appointment expired')
        for item in (p.server_certificate,c.graph_certificate):
            cert=x509.load_pem_x509_certificate(_pinned(item.path,item.sha256))
            if not cert.not_valid_before_utc<=now<cert.not_valid_after_utc:raise PermissionError('answer TLS certificate expired')
            end=min(end,cert.not_valid_after_utc)
        client=x509.load_pem_x509_certificate(_pinned(c.graph_certificate.path,c.graph_certificate.sha256))
        uris=client.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.UniformResourceIdentifier)
        if uris!=[c.graph_client_uri]:raise PermissionError('actual installed graph client identity differs')
        path=Path(c.storage_root);info=path.lstat()
        if (not path.is_absolute() or str(path.resolve(strict=True))!=str(path) or not stat.S_ISDIR(info.st_mode)
            or info.st_mode&0o077 or (info.st_dev,info.st_ino,info.st_uid)!=(c.storage_device,c.storage_inode,c.storage_uid)
            or info.st_uid!=os.getuid()):raise PermissionError('answer private root changed')
        c.history.authority();request_remaining_v1(required=False)
        return end
    def consumer(self):
        self.current();return self.config.history.authority(),FileBlobStore(Path(self.config.storage_root))
    def reference_readers_v1(self):
        """Use separately installed research READ appointments, never fetch roles."""
        from ..research.durable_authority_v1 import load_research_settings_v1,ResearchAuthorityV1
        from ..research.maintained_read_v1 import MaintainedResearchReaderV1
        self.current();request_remaining_v1();readers=[]
        if type(self.config) is not ConnectedIndustryAnswerConfigV1:raise PermissionError('independent reference read installation unavailable')
        for pin in self.config.industry_readers:
            settings=load_research_settings_v1(pin.path,pin.sha256);c=settings.config
            if c.operation!='read' or (c.principal_id,c.workspace_id)!=(self.config.principal_id,self.config.workspace_id):
                raise PermissionError('independently installed own reference reader required')
            readers.append(MaintainedResearchReaderV1(ResearchAuthorityV1(settings)))
        self.current();return tuple(readers)
    def projection(self,version,*,deadline,valid_at=None,known_at=None):
        from graphrag_sdk import ConnectionConfig
        from oracle_brain.operating_model.sdk_projection import ConsolidatedMetadataSDKProjectionV1
        self.current();request_remaining_v1();c=self.config
        targets=[p for p in c.projections if p.version==version]
        if len(targets)!=1:raise PermissionError('selected retained graph has no independently installed readonly target')
        target=targets[0];url=_pinned(target.graph_url.path,target.graph_url.sha256,16384).decode('utf8')
        from urllib.parse import urlsplit
        import socket,ssl
        parsed=urlsplit(url)
        if (parsed.scheme!='rediss' or not parsed.hostname or not parsed.port or not parsed.username or not parsed.password
                or parsed.path not in ('','/') or parsed.query or parsed.fragment):raise PermissionError('fixed mutual TLS readonly graph URL required')
        context=ssl.create_default_context(cadata=_pinned(c.graph_ca.path,c.graph_ca.sha256).decode('utf8'))
        context.load_cert_chain(c.graph_certificate.path,c.graph_key.path)
        remaining=min(request_remaining_v1(),(deadline-datetime.now(timezone.utc)).total_seconds())
        if remaining<=0:raise PermissionError('original graph window expired')
        with socket.create_connection((parsed.hostname,parsed.port),timeout=min(3,remaining)) as sock:
            sock.settimeout(min(3,request_remaining_v1(),(deadline-datetime.now(timezone.utc)).total_seconds()))
            with context.wrap_socket(sock,server_hostname=parsed.hostname) as actual:
                if [v for k,v in actual.getpeercert().get('subjectAltName',()) if k=='URI']!=[c.graph_server_uri]:
                    raise PermissionError('actual fixed graph server identity differs')
        self.current();request_remaining_v1()
        name=f'oracle_processing_v1_{c.workspace_id.hex}_{c.model_id.hex}_{version}_{target.generation.hex}'
        connection=ConnectionConfig.from_url(url,graph_name=name,ssl=True,ssl_check_hostname=True,ssl_cert_reqs='required',ssl_ca_certs=c.graph_ca.path,ssl_certfile=c.graph_certificate.path,ssl_keyfile=c.graph_key.path,query_timeout_ms=3000,retry_count=1,pool_timeout=1)
        authority,blobs=self.consumer()
        result=ConsolidatedMetadataSDKProjectionV1(url,authority=authority,blobs=blobs,model_id=c.model_id,version=version,generation=target.generation,connection_config=connection,deadline=deadline,valid_at=valid_at,known_at=known_at)
        self.current();return result
