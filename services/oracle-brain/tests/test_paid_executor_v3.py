"""Protected executor metadata refusals; native positive uses the sole coherent fixture."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from oracle_brain.hosting.paid_executor_v3 import PaidExecutorConfigV3,load_paid_executor_settings_v3,build_paid_executor_projection_v3
from oracle_brain.operating_model.source_receipts import SourceRef

def executor_config():
    workspace,artifact,generation=uuid4(),uuid4(),uuid4();now=datetime.now(timezone.utc)
    actors=[uuid4() for _ in range(6)]
    ref=SourceRef(workspace_id=workspace,source_id=uuid4(),revision=1,original_sha256='a'*64,reading_sha256='b'*64,parser_id='fixture')
    c=dict(workspace_id=workspace,actor_id=actors[0],expected_owner_role='fixture_owner',expected_session_role='fixture_executor',
        runtime_hash='a'*64,source_registry_hash='b'*64,source_refs=(ref,),original_root_hash='c'*64,
        semantic_admission_hash='7'*64,semantic_context_hash='8'*64,original_horizon=now+timedelta(seconds=90),source_expires_at=now+timedelta(seconds=90),database_hostname='fixture.invalid',
        database_port=5432,database_name='fixture',artifact_id=artifact,artifact_version=1,content_hash='d'*64,
        projection_digest='e'*64,receipt_body_hash='f'*64,receipt_signature='1'*64,source_digest='2'*64,permission_digest='3'*64,
        generation=generation,graph_name=f'oracle_processing_v1_{workspace.hex}_{artifact.hex}_1_{generation.hex}',blob_root='/fixture/qualified',
        graph_hostname='fixture.invalid',graph_port=6379,graph_username='fixture_reader',tls_client_uri='spiffe://fixture/executor',
        tls_server_uri='spiffe://fixture/graph',compiler_actor=actors[1],compiler_login='fixture_compiler',compiler_runtime_hash='4'*64,
        compiler_permission_hash='5'*64,semantic_issuer_actor=actors[2],semantic_reviewer_actor=actors[3],
        semantic_valid_from=now,semantic_expires_at=now+timedelta(seconds=90),issuer_actor=actors[4],reviewer_actor=actors[5],
        valid_from=now,expires_at=now+timedelta(seconds=60))
    for name in ('database_url','database_ca','graph_url','tls_ca','tls_certificate','tls_key','semantic_registry'):
        c[name+'_file']='/fixture/'+name;c[name+'_sha256']='6'*64
    return c

def test_executor_exact_metadata_never_accepts_compiler_or_writer_credentials():
    c=executor_config();assert PaidExecutorConfigV3.model_validate(c).actor_id==c['actor_id']
    for update in ({'actor_id':c['compiler_actor']},{'expected_session_role':c['compiler_login']},
        {'source_refs':()},{'source_refs':c['source_refs']*2},{'graph_name':'other'},
        {'expires_at':c['original_horizon']+timedelta(seconds=1)},{'database_port':True},
        {'tls_client_uri':c['tls_server_uri']},{'blob_root':'relative'},
        {'receipt_key_file':'/fixture/forbidden'},{'paid_wire_file':'/fixture/forbidden'}):
        with pytest.raises(Exception):PaidExecutorConfigV3.model_validate({**c,**update})

def test_executor_foreign_pins_and_settings_deny_before_any_file_or_network():
    for h in (None,'','placeholder',True):
        with pytest.raises(PermissionError,match='external protected executor pins required'):
            load_paid_executor_settings_v3('/absent',h,appointment_path='/absent',expected_appointment_sha256='a'*64,
                issuer_actor=uuid4(),reviewer_actor=uuid4())
    for supplied in (None,True,{},object()):
        with pytest.raises(PermissionError,match='actual protected executor settings required'):
            build_paid_executor_projection_v3(supplied)


def test_external_appointment_root_and_admission_cross_substitution_denies():
    from oracle_brain.hosting.paid_executor_v3 import PaidExecutorAppointmentV3,_appointment
    c=PaidExecutorConfigV3.model_validate(executor_config())
    fields=PaidExecutorAppointmentV3.model_fields
    values={k:getattr(c,k) for k in fields if hasattr(c,k)}
    values['config_sha256']='a'*64
    a=PaidExecutorAppointmentV3.model_validate(values)
    _appointment(c,a,'a'*64,c.issuer_actor,c.reviewer_actor,datetime.now(timezone.utc))
    for name,value in [('original_root_hash','0'*64),('semantic_admission_hash','0'*64),
                       ('semantic_context_hash','0'*64),('content_hash','0'*64),('receipt_body_hash','0'*64)]:
        changed=a.model_copy(update={name:value})
        with pytest.raises(PermissionError,match='appointment/config differs'):
            _appointment(c,changed,'a'*64,c.issuer_actor,c.reviewer_actor,datetime.now(timezone.utc))


def test_summary_targets_require_exact_parent_kind_and_independent_appointment():
    from oracle_brain.hosting.paid_executor_v3 import ExecutorSummaryTargetV3,PaidExecutorAppointmentV3,_appointment
    c=executor_config()
    target=dict(artifact_id=uuid4(),artifact_version=1,content_hash='9'*64,qualified_parent_id=c['artifact_id'],
        qualified_parent_version=c['artifact_version'],qualified_parent_content_hash=c['content_hash'])
    parsed=PaidExecutorConfigV3.model_validate({**c,'summary_targets':(target,)})
    for update in ({'kind':'processing_extraction_v1'},{'qualified_parent_id':uuid4()},
        {'qualified_parent_version':2},{'qualified_parent_content_hash':'0'*64},{'artifact_id':c['artifact_id']}):
        with pytest.raises(Exception):PaidExecutorConfigV3.model_validate({**c,'summary_targets':({**target,**update},)})
    with pytest.raises(Exception):PaidExecutorConfigV3.model_validate({**c,'summary_targets':(target,target)})
    values={k:getattr(parsed,k) for k in PaidExecutorAppointmentV3.model_fields if hasattr(parsed,k)}
    values['config_sha256']='a'*64;values['summary_targets']=()
    a=PaidExecutorAppointmentV3.model_validate(values)
    with pytest.raises(PermissionError,match='appointment/config differs'):
        _appointment(parsed,a,'a'*64,parsed.issuer_actor,parsed.reviewer_actor,datetime.now(timezone.utc))


def make_paid_executor_fixture_settings_v3(worker,job,root,*,executor_binding,database_url_file,database_ca_file,
        graph_url_file,tls_ca_file,tls_certificate_file,tls_key_file,tls_client_uri,tls_server_uri,
        qualified_manifest,qualified_payload,delivery_seal,qualified_blob_root,summary_targets=()):
    """TEST ONLY metadata authoring; all roles, bytes, ACK and TLS already exist."""
    import hashlib,json
    from pathlib import Path
    from datetime import datetime,timezone
    from urllib.parse import urlsplit,unquote
    from psycopg.conninfo import conninfo_to_dict
    from oracle_brain.hosting.paid_executor_v3 import (PaidExecutorConfigV3,PaidExecutorAppointmentV3,
        load_paid_executor_settings_v3)
    from oracle_brain.hosting.purpose_journey_v2 import CompilerWorkerSettingsV2,_require
    from oracle_brain.operating_model.authority_adapter import ProcessingSourceBinding
    from oracle_brain.operating_model.contracts import canonical_bytes,digest,ProcessingProjectionDeliverySealV3
    from oracle_brain.operating_model.purpose_qualification_v3 import PurposeSemanticAdmissionV3
    _require(type(worker) is CompilerWorkerSettingsV2 and type(executor_binding) is ProcessingSourceBinding
        and executor_binding.profile=='documentary-executor' and executor_binding.principal!=worker.config.actor_id
        and type(delivery_seal) is ProcessingProjectionDeliverySealV3,'actual separate executor metadata required')
    worker.authorize(job);worker.semantic.current(datetime.now(timezone.utc))
    admission=PurposeSemanticAdmissionV3.model_validate_json(canonical_bytes(qualified_payload['assembly_qualification']['admission']))
    _require(digest(qualified_payload)==qualified_manifest.content_hash
        and (delivery_seal.artifact_id,delivery_seal.version,delivery_seal.content_hash)==
            (qualified_manifest.artifact_id,qualified_manifest.version,qualified_manifest.content_hash),
        'actual qualified model/SQL delivery target differs')
    _require(executor_binding.source_registry_hash==worker.config.source_registry_hash
        and executor_binding.expected_session_role!=worker.config.expected_session_role,
        'separate executor and unchanged original source registry required')
    # These are fixture-owned exact existing credentials; helper issues none.
    sql=conninfo_to_dict(Path(database_url_file).read_text().strip())
    graph=urlsplit(Path(graph_url_file).read_text().strip())
    now=datetime.now(timezone.utc);end=min(job.original_horizon,job.expires_at,worker.population.expires_at,
        worker.allocation.original_expires_at,executor_binding.expires_at,worker.semantic.valid_until(now),admission.expires_at)
    c=dict(workspace_id=job.workspace_id,actor_id=executor_binding.principal,
        expected_owner_role=executor_binding.expected_owner_role,expected_session_role=executor_binding.expected_session_role,
        runtime_hash=executor_binding.runtime_hash,source_registry_hash=executor_binding.source_registry_hash,
        source_refs=job.source_refs,original_root_hash=worker.population.parent_registry_sha256,
        semantic_admission_hash=digest(admission.model_dump(mode='json')),semantic_context_hash=admission.context_hash,
        original_horizon=job.original_horizon,source_expires_at=end,database_hostname=sql['host'],
        database_port=int(sql.get('port') or 5432),database_name=sql['dbname'],
        artifact_id=qualified_manifest.artifact_id,artifact_version=qualified_manifest.version,
        content_hash=qualified_manifest.content_hash,source_digest=qualified_manifest.source_digest,
        permission_digest=qualified_manifest.permission_digest,projection_digest=delivery_seal.projection_digest,
        receipt_body_hash=delivery_seal.receipt_body_hash,receipt_signature=delivery_seal.signature,
        generation=__import__('uuid').UUID(delivery_seal.graph_name.rsplit('_',1)[1]),graph_name=delivery_seal.graph_name,
        blob_root=str(qualified_blob_root),graph_hostname=graph.hostname,graph_port=graph.port or 6379,
        graph_username=unquote(graph.username),tls_server_uri=tls_server_uri,tls_client_uri=tls_client_uri,
        compiler_actor=admission.compiler_actor,compiler_login=admission.compiler_login,compiler_runtime_hash=admission.runtime_hash,
        compiler_permission_hash=admission.compiler_permission_hash,semantic_issuer_actor=worker.config.semantic_issuer_actor,
        semantic_reviewer_actor=worker.config.semantic_reviewer_actor,semantic_valid_from=worker.config.semantic_valid_from,
        semantic_expires_at=worker.config.semantic_expires_at,issuer_actor=worker.config.custody_issuer_actor,
        reviewer_actor=worker.config.custody_reviewer_actor,valid_from=now,expires_at=end,summary_targets=summary_targets)
    files=dict(database_url=database_url_file,database_ca=database_ca_file,graph_url=graph_url_file,
        tls_ca=tls_ca_file,tls_certificate=tls_certificate_file,tls_key=tls_key_file,
        semantic_registry=worker.config.semantic_registry_file)
    for name,path in files.items():
        c[name+'_file']=str(path);c[name+'_sha256']=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    config=PaidExecutorConfigV3.model_validate(c)
    root=Path(root);root.mkdir(mode=0o700)  # New immutable appointment, never overwrite a live one.
    config_path=root/'executor.json';config_path.write_bytes(canonical_bytes(config.model_dump(mode='json')));config_path.chmod(0o600)
    config_hash=hashlib.sha256(config_path.read_bytes()).hexdigest()
    fields=PaidExecutorAppointmentV3.model_fields
    appointment=PaidExecutorAppointmentV3.model_validate({**{k:getattr(config,k) for k in fields if hasattr(config,k)},'config_sha256':config_hash})
    appointment_path=root/'executor-appointment.json';appointment_path.write_bytes(canonical_bytes(appointment.model_dump(mode='json')));appointment_path.chmod(0o600)
    return load_paid_executor_settings_v3(config_path,config_hash,appointment_path=appointment_path,
        expected_appointment_sha256=hashlib.sha256(appointment_path.read_bytes()).hexdigest(),
        issuer_actor=config.issuer_actor,reviewer_actor=config.reviewer_actor)


def test_executor_blob_reader_never_creates_or_writes_and_limits_exact_hash_keys(tmp_path):
    from oracle_brain.hosting.paid_executor_v3 import _ExecutorQualifiedBlobsV3
    from oracle_brain.operating_model.contracts import canonical_bytes
    import hashlib
    c=executor_config();raw=canonical_bytes({'invented':'qualified'});seal=hashlib.sha256(raw).hexdigest()
    root=tmp_path/'preexisting';c.update(blob_root=str(root),content_hash=seal)
    config=PaidExecutorConfigV3.model_validate(c)
    with pytest.raises(FileNotFoundError):_ExecutorQualifiedBlobsV3(config)
    assert not root.exists()
    root.mkdir(mode=0o700);namespace=root/'operating-model'/str(c['workspace_id']);namespace.mkdir(parents=True,mode=0o700)
    (root/'operating-model').chmod(0o700)
    path=namespace/(seal+'.json');path.write_bytes(raw);path.chmod(0o600)
    reader=_ExecutorQualifiedBlobsV3(config);key=f"operating-model/{c['workspace_id']}/{seal}.json"
    assert reader.read(key,seal)==raw
    with pytest.raises(PermissionError):reader.put(c['workspace_id'],{'unadmitted':'bytes'})
    with pytest.raises(PermissionError):reader.read(key,'0'*64)
    with pytest.raises(PermissionError):reader.read(f"operating-model/{c['workspace_id']}/"+'0'*64+'.json','0'*64)
    path.unlink();path.symlink_to(tmp_path/'outside')
    with pytest.raises(Exception):reader.read(key,seal)
