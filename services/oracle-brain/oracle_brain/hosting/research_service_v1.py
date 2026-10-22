"""Fixed uninstalled research mTLS service, one independently installed purpose.

No role, source rights, peer identity, schedule or fetch permission is created.
The shared protected listener owns framing, peer proof and original lifecycle.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import UUID
import ipaddress,json
from cryptography import x509
from pydantic import AwareDatetime,Field,field_validator,model_validator
from ..operating_model.contracts import StrictRecord,canonical_bytes
from ..operating_model.protected_inputs_v1 import _pinned,_parse
from ..research.durable_authority_v1 import ResearchAuthorityV1,ResearchSettingsV1
from ..research.maintained_fetch_v1 import MaintainedResearchFetcherV1
from ..research.maintained_read_v1 import MaintainedResearchReaderV1
from ._protected_control_listener_v1 import _protected_control_listener_v1

PATH='/v1/replacement/research'
HASH=r'^[a-f0-9]{64}$'

class ResearchPeerV1(StrictRecord):
    purpose:Literal['maintained-research-service-peer-v1']
    operation:Literal['schedule','fetch','read']
    research_config_sha256:str=Field(pattern=HASH)
    principal_id:UUID;workspace_id:UUID;source_id:UUID
    source_revision:int=Field(strict=True,ge=1)
    runtime_hash:str=Field(pattern=HASH);registry_hash:str=Field(pattern=HASH)
    client_uri:str=Field(pattern=r'^spiffe://oracle/research/(schedule|fetch|read)/[a-zA-Z0-9_-]+$')
    client_certificate_sha256:str=Field(pattern=HASH)
    listen_host:str
    listen_port:int=Field(strict=True,ge=0,le=65535)
    server_hostname:str=Field(pattern=r'^[a-zA-Z0-9.-]{1,253}$')
    server_certificate_file:str;server_certificate_sha256:str=Field(pattern=HASH)
    server_key_file:str;server_key_sha256:str=Field(pattern=HASH)
    client_ca_file:str;client_ca_sha256:str=Field(pattern=HASH)
    issuer_actor:UUID;reviewer_actor:UUID
    valid_from:AwareDatetime;expires_at:AwareDatetime;original_horizon:AwareDatetime

    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact research peer version required')
        return value

    @model_validator(mode='after')
    def fixed_purpose(self):
        ipaddress.ip_address(self.listen_host)
        if (not self.valid_from<self.expires_at<=self.original_horizon
                or len({self.principal_id,self.issuer_actor,self.reviewer_actor})!=3
                or not self.client_uri.startswith('spiffe://oracle/research/'+self.operation+'/')):
            raise ValueError('distinct finite research purpose peer required')
        paths=(self.server_certificate_file,self.server_key_file,self.client_ca_file)
        if len(set(paths))!=3 or any(not Path(p).is_absolute() or str(Path(p))!=p for p in paths):
            raise ValueError('separate exact research TLS files required')
        return self

@dataclass(frozen=True)
class _ResearchPeerSettingsV1:
    settings:ResearchSettingsV1
    profile:ResearchPeerV1
    path:str
    sha256:str
    def current(self):
        p=_parse(ResearchPeerV1,_pinned(self.path,self.sha256));s=self.settings;c=s.config
        if p!=self.profile or _parse(type(c),_pinned(s.config_path,s.config_sha256))!=c:
            raise PermissionError('installed research service inputs changed')
        if (p.research_config_sha256!=s.config_sha256
                or any(getattr(p,k)!=getattr(c,k) for k in ('operation','principal_id','workspace_id','source_id','source_revision','runtime_hash','registry_hash','issuer_actor','reviewer_actor','original_horizon'))):
            raise PermissionError('research service purpose or appointment differs')
        now=datetime.now(timezone.utc)
        if not p.valid_from<=now<min(p.expires_at,c.expires_at,c.original_horizon):
            raise PermissionError('original research service installation expired')
        cert=_pinned(p.server_certificate_file,p.server_certificate_sha256,131072)
        _pinned(p.server_key_file,p.server_key_sha256,131072);_pinned(p.client_ca_file,p.client_ca_sha256,131072)
        _pinned(c.database_ca.path,c.database_ca.sha256,131072)
        leaf=x509.load_pem_x509_certificate(cert)
        names=leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
        if p.server_hostname not in names or not leaf.not_valid_before_utc<=now<leaf.not_valid_after_utc:
            raise PermissionError('current research server certificate differs')
        return min(p.expires_at,c.expires_at,c.original_horizon,leaf.not_valid_after_utc)

class ResearchRequestV1(StrictRecord):
    operation:Literal['tick','force','pending','fetch','reconcile','status','reference']
    run_id:UUID|None
    caller_deadline:AwareDatetime
    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact research wire version required')
        return value
    @model_validator(mode='after')
    def opaque_only(self):
        if (self.operation in ('fetch','reconcile'))!=(self.run_id is not None):
            raise ValueError('only once-claimed operations select opaque research runs')
        return self


def parse_research_request_v1(raw):
    if type(raw) is not bytes or not 1<=len(raw)<=4096:raise PermissionError('bounded research request required')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate research field')
            result[key]=value
        return result
    value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('finite research wire required')))
    if (type(value) is not dict or set(value)!={'schema_version','operation','run_id','caller_deadline'}
            or canonical_bytes(value)!=raw):raise PermissionError('closed canonical research wire required')
    # Preserve ORIGINAL canonical request bytes; datetime normalization is not
    # a protected-settings parser and cannot manufacture a fresh deadline.
    return ResearchRequestV1.model_validate_json(raw)

class _ResearchServiceFactoryV1:
    def __init__(self,authority):
        if type(authority) is not ResearchAuthorityV1:raise TypeError('exact installed research SQL owner required')
        self.authority=authority;operation=authority.settings.config.operation
        self.fetcher=MaintainedResearchFetcherV1(authority) if operation=='fetch' else None
        self.reader=MaintainedResearchReaderV1(authority) if operation=='read' else None
    def execute_v1(self,raw):
        q=parse_research_request_v1(raw);a=self.authority;operation=a.settings.config.operation
        allowed={'schedule':('tick','force','pending'),'fetch':('fetch','reconcile'),'read':('status','reference')}
        if q.operation not in allowed[operation]:raise PermissionError('separately installed research service purpose required')
        if q.operation=='tick':return a.schedule_due_v1(deadline=q.caller_deadline)
        if q.operation=='force':return a.force_due_v1(deadline=q.caller_deadline)
        if q.operation=='pending':return a.pending_queue_v1(deadline=q.caller_deadline)
        if q.operation=='fetch':return self.fetcher.execute_v1(q.run_id,deadline=q.caller_deadline)
        if q.operation=='reconcile':return self.fetcher.reconcile_retained_v1(q.run_id,deadline=q.caller_deadline)
        if q.operation=='status':return a.status_v1(deadline=q.caller_deadline)
        return self.reader.latest_v1(deadline=q.caller_deadline)


def protected_research_server_v1(settings,peer_path,peer_sha256):
    if type(settings) is not ResearchSettingsV1:raise TypeError('exact installed research settings required')
    profile=_parse(ResearchPeerV1,_pinned(peer_path,peer_sha256))
    peer=_ResearchPeerSettingsV1(settings,profile,str(peer_path),peer_sha256);peer.current()
    factory=_ResearchServiceFactoryV1(ResearchAuthorityV1(settings));peer.current()
    return _protected_control_listener_v1(peer,factory,path=PATH,parse_request=parse_research_request_v1,
        encode_response=canonical_bytes,maximum_request_bytes=4096,maximum_response_bytes=7340032)
