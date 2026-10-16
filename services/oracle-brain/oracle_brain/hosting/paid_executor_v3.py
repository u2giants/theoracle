"""Protected metadata-only Schema3 executor startup; no issuer or writer keys."""
from dataclasses import dataclass,field
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit,unquote
from uuid import UUID
import ssl,re
from pydantic import Field,AwareDatetime,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,digest,canonical_bytes
from oracle_brain.operating_model.source_receipts import SourceRef
from oracle_brain.operating_model.authority_adapter import ProcessingSourceBinding,ProcessingArtifactResolver
from oracle_brain.operating_model.semantic_registry_v3 import CurrentSemanticAdmissionsV3,SemanticRegistryAppointmentV3
from oracle_brain.operating_model.purpose_qualification_v3 import PurposeQualifiedAssemblyReadGuardV3,PurposeSemanticAdmissionV3
from .purpose_journey_v2 import _worker_file,_worker_json,_worker_parse,_require
HASH=r'^[a-f0-9]{64}$'

class ExecutorSummaryTargetV3(StrictRecord):
    kind:Literal['processing_summary_v1']='processing_summary_v1'
    artifact_id:UUID
    artifact_version:int=Field(strict=True,ge=1)
    content_hash:str=Field(pattern=HASH)
    qualified_parent_id:UUID
    qualified_parent_version:int=Field(strict=True,ge=1)
    qualified_parent_content_hash:str=Field(pattern=HASH)

class PaidExecutorConfigV3(StrictRecord):
    schema_version:Literal[3]=3
    purpose:Literal['replacement-documentary-executor-v3']='replacement-documentary-executor-v3'
    workspace_id:UUID
    actor_id:UUID
    expected_owner_role:str
    expected_session_role:str
    runtime_hash:str=Field(pattern=HASH)
    source_registry_hash:str=Field(pattern=HASH)
    source_refs:tuple[SourceRef,...]
    summary_targets:tuple[ExecutorSummaryTargetV3,...]=()
    original_root_hash:str=Field(pattern=HASH)
    semantic_admission_hash:str=Field(pattern=HASH)
    semantic_context_hash:str=Field(pattern=HASH)
    original_horizon:AwareDatetime
    source_expires_at:AwareDatetime
    database_url_file:str
    database_url_sha256:str=Field(pattern=HASH)
    database_ca_file:str
    database_ca_sha256:str=Field(pattern=HASH)
    database_hostname:str
    database_port:int=Field(strict=True,ge=1,le=65535)
    database_name:str
    artifact_id:UUID
    artifact_version:int=Field(strict=True,ge=1)
    content_hash:str=Field(pattern=HASH)
    projection_digest:str=Field(pattern=HASH)
    receipt_body_hash:str=Field(pattern=HASH)
    receipt_signature:str=Field(pattern=HASH)
    source_digest:str=Field(pattern=HASH)
    permission_digest:str=Field(pattern=HASH)
    generation:UUID
    graph_name:str
    blob_root:str
    graph_url_file:str
    graph_url_sha256:str=Field(pattern=HASH)
    graph_hostname:str
    graph_port:int=Field(strict=True,ge=1,le=65535)
    graph_username:str
    tls_ca_file:str
    tls_ca_sha256:str=Field(pattern=HASH)
    tls_certificate_file:str
    tls_certificate_sha256:str=Field(pattern=HASH)
    tls_key_file:str
    tls_key_sha256:str=Field(pattern=HASH)
    tls_server_uri:str
    tls_client_uri:str
    semantic_registry_file:str
    semantic_registry_sha256:str=Field(pattern=HASH)
    compiler_actor:UUID
    compiler_login:str
    compiler_runtime_hash:str=Field(pattern=HASH)
    compiler_permission_hash:str=Field(pattern=HASH)
    semantic_issuer_actor:UUID
    semantic_reviewer_actor:UUID
    semantic_valid_from:AwareDatetime
    semantic_expires_at:AwareDatetime
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    @model_validator(mode='after')
    def exact(self):
        _require(self.source_refs and len(set(self.source_refs))==len(self.source_refs)
            and all(r.workspace_id==self.workspace_id for r in self.source_refs),'complete unique executor source population required')
        _require(len({self.actor_id,self.compiler_actor,self.issuer_actor,self.reviewer_actor})==4
            and self.expected_session_role!=self.compiler_login,'separate executor/compiler/issuer identities required')
        _require(self.valid_from<self.expires_at<=min(self.original_horizon,self.source_expires_at,self.semantic_expires_at)
            and self.semantic_valid_from<self.semantic_expires_at,'finite original executor horizon required')
        _require(len({(t.artifact_id,t.artifact_version) for t in self.summary_targets})==len(self.summary_targets)
            and all(t.artifact_id!=self.artifact_id and (t.qualified_parent_id,t.qualified_parent_version,t.qualified_parent_content_hash)==
                (self.artifact_id,self.artifact_version,self.content_hash) for t in self.summary_targets),
            'exact unique summary targets and qualified parent required')
        expected=f'oracle_processing_v1_{self.workspace_id.hex}_{self.artifact_id.hex}_{self.artifact_version}_{self.generation.hex}'
        _require(self.graph_name==expected,'exact delivered executor graph required')
        paths=[self.database_url_file,self.database_ca_file,self.blob_root,self.graph_url_file,
            self.tls_ca_file,self.tls_certificate_file,self.tls_key_file,self.semantic_registry_file]
        _require(all(Path(p).is_absolute() for p in paths) and len(set(paths))==len(paths),'distinct exact executor paths required')
        _require(self.tls_client_uri!=self.tls_server_uri and self.tls_client_uri.startswith('spiffe://')
            and self.tls_server_uri.startswith('spiffe://'),'distinct pinned executor TLS identities required')
        return self

class PaidExecutorAppointmentV3(StrictRecord):
    schema_version:Literal[3]=3
    purpose:Literal['replacement-documentary-executor-v3']='replacement-documentary-executor-v3'
    config_sha256:str=Field(pattern=HASH)
    workspace_id:UUID
    actor_id:UUID
    expected_session_role:str
    runtime_hash:str=Field(pattern=HASH)
    source_registry_hash:str=Field(pattern=HASH)
    source_refs:tuple[SourceRef,...]
    summary_targets:tuple[ExecutorSummaryTargetV3,...]=()
    original_root_hash:str=Field(pattern=HASH)
    semantic_admission_hash:str=Field(pattern=HASH)
    semantic_context_hash:str=Field(pattern=HASH)
    original_horizon:AwareDatetime
    artifact_id:UUID
    artifact_version:int=Field(strict=True,ge=1)
    generation:UUID
    graph_name:str
    blob_root:str
    content_hash:str=Field(pattern=HASH)
    projection_digest:str=Field(pattern=HASH)
    receipt_body_hash:str=Field(pattern=HASH)
    compiler_actor:UUID
    compiler_login:str
    compiler_runtime_hash:str=Field(pattern=HASH)
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime

@dataclass(frozen=True)
class PaidExecutorSettingsV3:
    config:PaidExecutorConfigV3
    config_path:Path
    config_sha256:str
    appointment_path:Path
    appointment_sha256:str
    issuer_actor:UUID
    reviewer_actor:UUID
    resolver:ProcessingArtifactResolver
    semantic:CurrentSemanticAdmissionsV3
    ledger:object
    guard:PurposeQualifiedAssemblyReadGuardV3
    graph_url:str=field(repr=False)

    def authorize_current(self):
        c=self.config;now=datetime.now(timezone.utc)
        _require(_worker_json(self.config_path,self.config_sha256,PaidExecutorConfigV3)==c,'executor config changed')
        a=_worker_json(self.appointment_path,self.appointment_sha256,PaidExecutorAppointmentV3)
        _appointment(c,a,self.config_sha256,self.issuer_actor,self.reviewer_actor,now)
        _require(c.semantic_admission_hash in self.semantic.current(now),'exact current externally admitted model required')
        horizons=[c.expires_at,a.expires_at,c.original_horizon,c.source_expires_at,self.semantic.valid_until(now)]
        with self.resolver._connection() as conn:
            self.resolver._check(conn)
            for ref in c.source_refs:
                rows=conn.execute('SELECT * FROM oracle2.hosting_current_source_identity(%s,%s,%s,%s,%s)',self.resolver._args(ref.workspace_id,ref.source_id)).fetchall()
                _require(len(rows)==1,'unique current executor source required')
                revision,original,reading,parser,until,checked=rows[0]
                _require(SourceRef(workspace_id=ref.workspace_id,source_id=ref.source_id,revision=revision,
                    original_sha256=original,reading_sha256=reading,parser_id=parser)==ref,'current executor source changed')
                horizons.append(until)
            self.resolver._check(conn)
        until=min(horizons);_require(datetime.now(timezone.utc)<until,'current executor authority expired')
        return until

    def read_target(self):
        self.authorize_current();c=self.config
        m,p=self.ledger.read_with_manifest(c.workspace_id,c.artifact_id,c.artifact_version)
        a=_worker_parse(canonical_bytes(p['assembly_qualification']['admission']),PurposeSemanticAdmissionV3)
        _require((a.compiler_actor,a.compiler_login,a.runtime_hash,a.compiler_permission_hash)==
            (c.compiler_actor,c.compiler_login,c.compiler_runtime_hash,c.compiler_permission_hash)
            and a.workspace_id==c.workspace_id and a.context_hash==c.semantic_context_hash
            and digest(a.model_dump(mode='json'))==c.semantic_admission_hash
            and c.semantic_admission_hash in self.semantic.current(datetime.now(timezone.utc)),
            'independent schema3 historical compiler differs')
        _require((m.content_hash,m.source_digest,m.permission_digest)==(c.content_hash,c.source_digest,c.permission_digest),
            'executor exact qualified manifest differs')
        seal=self.resolver.projection_delivery_seal(c.workspace_id,c.artifact_id,c.artifact_version)
        _require((seal.receipt_body_hash,seal.signature,seal.graph_name,seal.projection_digest)==
            (c.receipt_body_hash,c.receipt_signature,c.graph_name,c.projection_digest),'executor exact delivered ACK differs')
        _require(len(seal.source_refs)==len(c.source_refs) and set(seal.source_refs)==set(c.source_refs),'executor delivery population differs')
        self.authorize_current()
        return m,p


    def read_summary(self,artifact_id,artifact_version):
        c=self.config
        targets=[t for t in c.summary_targets if (t.artifact_id,t.artifact_version)==(artifact_id,artifact_version)]
        _require(len(targets)==1,'exact independently appointed summary required')
        self.read_target()
        manifest,payload=self.ledger.read_with_manifest(c.workspace_id,artifact_id,artifact_version)
        target=targets[0]
        _require(manifest.kind==target.kind and manifest.content_hash==target.content_hash,'exact appointed summary differs')
        from oracle_brain.operating_model.summaries import DocumentarySummary
        summary=_worker_parse(canonical_bytes(payload['summary']),DocumentarySummary)
        _require((summary.pack.artifact_id,summary.pack.version)==(target.qualified_parent_id,target.qualified_parent_version),
            'summary qualified parent differs')
        self.read_target()
        return payload


def _appointment(c,a,config_hash,issuer,reviewer,now):
    _require(a.config_sha256==config_hash and a.issuer_actor==issuer and a.reviewer_actor==reviewer
        and a.valid_from<=now<a.expires_at<=c.original_horizon,'independently appointed executor startup required')
    for name in ('workspace_id','actor_id','expected_session_role','runtime_hash','source_registry_hash','source_refs',
            'summary_targets','original_root_hash','semantic_admission_hash','semantic_context_hash','original_horizon',
            'artifact_id','artifact_version','generation','graph_name','blob_root','content_hash','projection_digest','receipt_body_hash',
            'compiler_actor','compiler_login','compiler_runtime_hash','issuer_actor','reviewer_actor'):
        _require(getattr(c,name)==getattr(a,name),'executor appointment/config differs')
    _require(c.valid_from<=now<c.expires_at<=a.expires_at,'current executor config required')


def load_paid_executor_settings_v3(config_path,expected_config_sha256,*,appointment_path,
        expected_appointment_sha256,issuer_actor,reviewer_actor):
    _require(all(type(h) is str and re.fullmatch(HASH,h) for h in (expected_config_sha256,expected_appointment_sha256))
        and type(issuer_actor) is UUID and type(reviewer_actor) is UUID,'external protected executor pins required')
    c=_worker_json(config_path,expected_config_sha256,PaidExecutorConfigV3)
    a=_worker_json(appointment_path,expected_appointment_sha256,PaidExecutorAppointmentV3)
    _appointment(c,a,expected_config_sha256,issuer_actor,reviewer_actor,datetime.now(timezone.utc))
    # Bootstrap appointment permits only these own-role credential bytes.
    raw=_worker_file(c.database_url_file,c.database_url_sha256,limit=8192)
    _worker_file(c.database_ca_file,c.database_ca_sha256)
    from psycopg.conninfo import conninfo_to_dict
    url=raw.decode().strip();params=conninfo_to_dict(url)
    _require(params.get('host')==c.database_hostname and int(params.get('port') or 5432)==c.database_port
        and params.get('dbname')==c.database_name and params.get('user')==c.expected_session_role
        and params.get('sslmode')=='verify-full' and params.get('sslrootcert')==c.database_ca_file,
        'exact own executor TLS database target required')
    resolver=ProcessingArtifactResolver(url,binding=ProcessingSourceBinding(runtime_hash=c.runtime_hash,
        source_registry_hash=c.source_registry_hash,expected_owner_role=c.expected_owner_role,
        expected_session_role=c.expected_session_role,principal=c.actor_id,profile='documentary-executor',
        expires_at=c.source_expires_at,synthetic=False))
    semantic=CurrentSemanticAdmissionsV3(c.semantic_registry_file,c.semantic_registry_sha256,
        appointment=SemanticRegistryAppointmentV3(c.workspace_id,c.compiler_runtime_hash,'candidate-compiler',
            c.semantic_issuer_actor,c.semantic_reviewer_actor,c.semantic_valid_from,c.semantic_expires_at))
    holder={}
    def current():return holder['settings'].authorize_current()
    def source(workspace,principal,source_id):
        _require(workspace==c.workspace_id and principal==c.actor_id and source_id in {r.source_id for r in c.source_refs},'exact executor source target required')
        current();return resolver.identity(workspace,source_id)
    def extraction(workspace,principal,artifact,version):
        _require(workspace==c.workspace_id and principal==c.actor_id,'executor dependency principal differs')
        current();return resolver.extraction_seal(workspace,artifact,version)
    def trust():current();return semantic.current(datetime.now(timezone.utc))
    def parent(workspace,principal,artifact,version):
        _require(workspace==c.workspace_id and principal==c.actor_id,'executor qualified parent principal differs')
        _require((artifact,version)==(c.artifact_id,c.artifact_version),'exact appointed executor parent required')
        current();metadata,_=resolver.artifact_metadata(workspace,artifact,version)
        _require(metadata.kind=='processing_qualified_model_v1','executor qualified parent only')
        return holder['settings'].ledger.read_with_manifest(workspace,artifact,version)
    guard=PurposeQualifiedAssemblyReadGuardV3(trusted_admissions=trust,runtime_hash=c.compiler_runtime_hash,
        current_source_identity=source,current_extraction_seal=extraction,qualified_parent_reader=parent)
    from oracle_brain.operating_model.ledger import Ledger
    from oracle_brain.operating_model.artifact_storage import FileBlobStore
    def denied(*args):raise PermissionError('executor original/nonprocessing bytes forbidden')
    class ExactExecutorLedger(Ledger):
        def _authorize_processing_blob(self,manifest):
            current()
            model=(manifest.kind=='processing_qualified_model_v1'
                and (manifest.workspace_id,manifest.artifact_id,manifest.version,manifest.content_hash)==
                (c.workspace_id,c.artifact_id,c.artifact_version,c.content_hash))
            summary=any(manifest.kind==t.kind and (manifest.workspace_id,manifest.artifact_id,manifest.version,manifest.content_hash)==
                (c.workspace_id,t.artifact_id,t.artifact_version,t.content_hash) for t in c.summary_targets)
            _require(model or summary,'exact appointed qualified executor blob required')
    ledger=ExactExecutorLedger(url,FileBlobStore(Path(c.blob_root)),principal=c.actor_id,can_read=denied,current_source=denied,
        processing_sources=resolver,processing_read_guard=guard)
    # No graph credential has been read yet; placeholders are never returned.
    settings=PaidExecutorSettingsV3(c,Path(config_path),expected_config_sha256,Path(appointment_path),
        expected_appointment_sha256,issuer_actor,reviewer_actor,resolver,semantic,ledger,guard,'')
    holder['settings']=settings;settings.read_target()
    graph_url=_worker_file(c.graph_url_file,c.graph_url_sha256,limit=8192).decode().strip();parsed=urlsplit(graph_url)
    _require(parsed.scheme=='rediss' and parsed.hostname==c.graph_hostname and (parsed.port or 6379)==c.graph_port
        and unquote(parsed.username or'')==c.graph_username and parsed.password is not None
        and parsed.path in ('','/') and not parsed.query and not parsed.fragment,'exact readonly executor graph target required')
    ca=_worker_file(c.tls_ca_file,c.tls_ca_sha256);cert=_worker_file(c.tls_certificate_file,c.tls_certificate_sha256)
    key=_worker_file(c.tls_key_file,c.tls_key_sha256)
    context=ssl.create_default_context(cadata=ca.decode());context.load_cert_chain(c.tls_certificate_file,c.tls_key_file)
    _require(_worker_file(c.tls_certificate_file,c.tls_certificate_sha256)==cert
        and _worker_file(c.tls_key_file,c.tls_key_sha256)==key,'executor TLS identity changed')
    # Certificate URI pins are enforced before any graph connection.
    from cryptography import x509
    cert_obj=x509.load_pem_x509_certificate(cert)
    uris=cert_obj.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.UniformResourceIdentifier)
    _require(uris==[c.tls_client_uri],'executor client certificate identity differs')
    settings=PaidExecutorSettingsV3(c,Path(config_path),expected_config_sha256,Path(appointment_path),
        expected_appointment_sha256,issuer_actor,reviewer_actor,resolver,semantic,ledger,guard,graph_url)
    holder['settings']=settings;settings.read_target()
    return settings


def build_paid_executor_projection_v3(settings):
    _require(type(settings) is PaidExecutorSettingsV3,'actual protected executor settings required')
    settings.read_target();c=settings.config
    for name in ('database_url','database_ca','graph_url','tls_ca','tls_certificate','tls_key'):
        _worker_file(getattr(c,name+'_file'),getattr(c,name+'_sha256'))
    # Actual peer URI is verified on this exact TLS target before SDK use.
    import socket
    context=ssl.create_default_context(cadata=_worker_file(c.tls_ca_file,c.tls_ca_sha256).decode())
    context.load_cert_chain(c.tls_certificate_file,c.tls_key_file)
    deadline=settings.authorize_current();remaining=(deadline-datetime.now(timezone.utc)).total_seconds()
    with socket.create_connection((c.graph_hostname,c.graph_port),timeout=min(5,remaining)) as sock:
        with context.wrap_socket(sock,server_hostname=c.graph_hostname) as tls:
            uris=[v for kind,v in tls.getpeercert().get('subjectAltName',()) if kind=='URI']
            _require(uris==[c.tls_server_uri],'executor graph server identity differs')
    from oracle_brain.operating_model.sdk_projection import PaidMetadataSDKProjectionV3,paid_tls_connection_config_v3
    from graphrag_sdk import ConnectionConfig
    parsed=urlsplit(settings.graph_url)
    connection=paid_tls_connection_config_v3(settings.graph_url,c.graph_name,ConnectionConfig(
        host=c.graph_hostname,port=c.graph_port,username=unquote(parsed.username),password=unquote(parsed.password),
        graph_name=c.graph_name,ssl=True,ssl_cert_reqs='required',ssl_check_hostname=True,
        ssl_ca_certs=c.tls_ca_file,ssl_certfile=c.tls_certificate_file,ssl_keyfile=c.tls_key_file,
        query_timeout_ms=max(1,min(30000,int((deadline-datetime.now(timezone.utc)).total_seconds()*1000))),
        pool_timeout=min(5,remaining),retry_count=1))
    settings.read_target()
    projection=PaidMetadataSDKProjectionV3(settings.graph_url,workspace_id=c.workspace_id,artifact_id=c.artifact_id,
        artifact_version=c.artifact_version,generation=c.generation,resolver=settings.resolver,
        qualification_guard=settings.guard,connection_config=connection)

    settings.read_target()
    return projection
