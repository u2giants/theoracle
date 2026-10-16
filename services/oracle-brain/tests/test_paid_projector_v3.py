"""Exact projector metadata refusals; no authority, key generation or graph calls."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from oracle_brain.hosting.paid_projector_v3 import PaidProjectorConfigV3,load_paid_projector_settings_v3


def config():
    workspace,artifact,generation=uuid4(),uuid4(),uuid4();now=datetime.now(timezone.utc)
    name=f'oracle_processing_v1_{workspace.hex}_{artifact.hex}_1_{generation.hex}'
    return dict(worker_config_sha256='a'*64,job_hash='b'*64,workspace_id=workspace,compiler_actor=uuid4(),compiler_login='compiler',runtime_hash='c'*64,
        artifact_id=artifact,artifact_version=1,content_hash='d'*64,projection_digest='e'*64,embedding_dispatch_id=uuid4(),generation=generation,
        graph_name=name,ontology_name=name+'__ontology',graph_hostname='owned-fixture.invalid',graph_port=6379,graph_username='oracle_projector',
        graph_url_file='/fixture/graph-url',graph_url_sha256='1'*64,tls_ca_file='/fixture/ca',tls_ca_sha256='2'*64,
        tls_certificate_file='/fixture/cert',tls_certificate_sha256='3'*64,tls_key_file='/fixture/key',tls_key_sha256='4'*64,
        projector_id=uuid4(),receipt_key_file='/fixture/receipt-key',receipt_key_sha256='5'*64,issuer_actor=uuid4(),reviewer_actor=uuid4(),
        valid_from=now,expires_at=now+timedelta(seconds=60))


def test_exact_projector_namespace_and_private_path_schema():
    value=config();assert PaidProjectorConfigV3.model_validate(value).graph_name==value['graph_name']
    for update in ({'graph_name':'other'}, {'ontology_name':value['graph_name']}, {'graph_port':True},
                   {'generation':uuid4()}, {'tls_key_file':value['receipt_key_file']},
                   {'tls_ca_file':'relative'}, {'worker_config_sha256':'placeholder'},
                   {'expires_at':value['valid_from']}, {'issuer_actor':value['compiler_actor']}):
        with pytest.raises(Exception):PaidProjectorConfigV3.model_validate({**value,**update})


def test_projector_startup_never_accepts_foreign_worker_or_caller_json():
    for worker in (None,True,{},object()):
        with pytest.raises(Exception,match='actual compiler worker'):
            load_paid_projector_settings_v3('/absent','a'*64,appointment_path='/absent',
                expected_appointment_sha256='b'*64,issuer_actor=uuid4(),reviewer_actor=uuid4(),worker=worker,job={})


def test_projector_authority_refuses_caller_objects_and_deserialized_metadata():
    from oracle_brain.hosting.paid_projector_v3 import PaidProjectorAuthorityV3
    for supplied in (None,True,{},object()):
        with pytest.raises(Exception,match='exact protected projector authority'):
            PaidProjectorAuthorityV3(supplied)


def test_projector_startup_rejects_missing_or_placeholder_external_hashes_before_files():
    for config_hash,appointment_hash in ((None,'b'*64),('a'*64,None),('placeholder','b'*64),('a'*64,'')):
        with pytest.raises(Exception,match='explicit external projector'):
            load_paid_projector_settings_v3('/absent',config_hash,appointment_path='/absent',
                expected_appointment_sha256=appointment_hash,issuer_actor=uuid4(),reviewer_actor=uuid4(),worker=None,job=None)


def test_exact_generation_attempt_nonce_survives_unknown_and_process_restart(tmp_path):
    from oracle_brain.hosting.paid_projector_v3 import _ProjectorAttemptFilesV3
    import json
    tmp_path.chmod(0o700)
    first=_ProjectorAttemptFilesV3(tmp_path,'exact-invented-graph')
    row={'attempt_id':str(uuid4()),'state':'STARTED','job_hash':'a'*64,'lease_token':str(uuid4())}
    first.begin(row)
    first.append({'attempt_id':row['attempt_id'],'state':'UNKNOWN','server_writer_inactive_proven':False})
    restarted=_ProjectorAttemptFilesV3(tmp_path,'exact-invented-graph')
    assert restarted.started()==row
    with pytest.raises(Exception,match='graph generation already attempted'):
        restarted.begin({**row,'attempt_id':str(uuid4()),'job_hash':'b'*64})
    with pytest.raises(Exception,match='projector attempt identity differs'):
        restarted.append({'attempt_id':str(uuid4()),'state':'COMPLETED'})
    assert json.loads(first.events_path.read_text())['server_writer_inactive_proven'] is False
    assert first.start_path.exists()  # No expiry-based deletion/rebuild.


def test_projector_attempt_nonce_refuses_symlink_and_foreign_permissions(tmp_path):
    from oracle_brain.hosting.paid_projector_v3 import _ProjectorAttemptFilesV3
    tmp_path.chmod(0o700)
    attempt=_ProjectorAttemptFilesV3(tmp_path,'exact-invented-graph')
    outside=tmp_path/'outside';outside.write_text('untouched')
    attempt.start_path.symlink_to(outside)
    with pytest.raises(Exception):attempt.begin({'attempt_id':str(uuid4())})
    assert outside.read_text()=='untouched'
    tmp_path.chmod(0o755)
    with pytest.raises(Exception):_ProjectorAttemptFilesV3(tmp_path,'foreign-mode')
    tmp_path.chmod(0o700)


def make_paid_projector_fixture_settings_v3(worker,job,root,*,graph_url_file,tls_ca_file,
        tls_certificate_file,tls_key_file,receipt_key_file,artifact_id,artifact_version,
        embedding_dispatch_id,generation,projector_id,prepared_bundle=None):
    """TEST ONLY external metadata authoring; creates no runtime/source/key grant.

    Caller owns the coherent invented fixture and existing exact target/keys.
    All source/provider/semantic/custody authority must ALREADY exist. This
    creates only fixture config+independent appointment bytes and calls the
    REAL protected loader; no fake bundle, role, current check or provider.
    """
    import hashlib
    from pathlib import Path
    from urllib.parse import urlsplit,unquote
    from oracle_brain.operating_model.contracts import canonical_bytes,digest
    from oracle_brain.hosting.paid_sdk_delivery_v3 import load_paid_sdk_bundle_v3
    from oracle_brain.hosting.paid_projector_v3 import PaidProjectorAppointmentV3
    from oracle_brain.hosting.purpose_journey_v2 import _worker_file
    root=Path(root);root.mkdir(mode=0o700)
    # Optional SAME-construction result supplies metadata hashes ONLY. It
    # never replaces the real protected loader's paid/current authentication.
    if prepared_bundle is None:
        bundle=load_paid_sdk_bundle_v3(worker,job,artifact_id=artifact_id,
            artifact_version=artifact_version,embedding_dispatch_id=embedding_dispatch_id)
    else:
        from oracle_brain.hosting.paid_sdk_delivery_v3 import AuthenticatedPaidSDKBundleV3
        assert type(prepared_bundle) is AuthenticatedPaidSDKBundleV3
        bundle=prepared_bundle
        assert bundle.qualification_guard.combined.settings is worker
        assert bundle.qualification_guard.combined.job==job
        worker.authorize(job);worker.custody_window_v3(job)
        worker.semantic.current(datetime.now(timezone.utc))
        metadata,refs=worker.resolver.artifact_metadata(job.workspace_id,artifact_id,artifact_version)
        assert metadata==bundle.manifest and metadata.kind=='processing_qualified_model_v1'
        assert len(set(refs))==len(refs) and set(refs)==set(job.source_refs)
        witness=bundle.embedder.data.witness
        assert (witness.dispatch_id,witness.qualified_artifact_id,witness.qualified_artifact_version)==(
            embedding_dispatch_id,artifact_id,artifact_version)
        assert digest(bundle.payload)==metadata.content_hash==witness.qualified_content_hash
    now=datetime.now(timezone.utc)
    end=min(job.expires_at,job.original_horizon,worker.config.source_expires_at,bundle.window.operation_horizon,
        worker.semantic.valid_until(now),worker.custody_window_v3(job).operation_horizon)
    assert now<end
    issuer,reviewer=uuid4(),uuid4()  # explicit invented fixture appointment only
    graph_bytes=_worker_file(graph_url_file);target=urlsplit(graph_bytes.decode().strip())
    assert target.scheme=='rediss' and target.username and target.password
    name=f'oracle_processing_v1_{job.workspace_id.hex}_{artifact_id.hex}_{artifact_version}_{generation.hex}'
    common=dict(worker_config_sha256=worker.config_sha256,job_hash=digest(job.model_dump(mode='json')),
        workspace_id=job.workspace_id,compiler_actor=job.actor_id,compiler_login=worker.config.expected_session_role,
        runtime_hash=worker.config.runtime_hash,issuer_actor=issuer,reviewer_actor=reviewer,
        valid_from=now,expires_at=end)
    files={}
    for prefix,path in (('graph_url',graph_url_file),('tls_ca',tls_ca_file),
                        ('tls_certificate',tls_certificate_file),('tls_key',tls_key_file),('receipt_key',receipt_key_file)):
        path=Path(path);files[prefix+'_file']=str(path)
        files[prefix+'_sha256']=hashlib.sha256(_worker_file(path)).hexdigest()
    value=PaidProjectorConfigV3(**common,artifact_id=artifact_id,artifact_version=artifact_version,
        content_hash=bundle.manifest.content_hash,projection_digest=bundle.embedder.data.inventory.projection_digest,
        embedding_dispatch_id=embedding_dispatch_id,generation=generation,graph_name=name,ontology_name=name+'__ontology',
        graph_hostname=target.hostname,graph_port=target.port or 6379,graph_username=unquote(target.username),
        projector_id=projector_id,**files)
    def store(name,value):
        raw=canonical_bytes(value.model_dump(mode='json'));path=root/name
        path.write_bytes(raw);path.chmod(0o600)
        return path,hashlib.sha256(raw).hexdigest()
    cfg,cfg_sha=store('projector-config.json',value)
    appointment=PaidProjectorAppointmentV3(config_sha256=cfg_sha,**common)
    appoint,appoint_sha=store('projector-appointment.json',appointment)
    return load_paid_projector_settings_v3(str(cfg),cfg_sha,appointment_path=str(appoint),
        expected_appointment_sha256=appoint_sha,issuer_actor=issuer,reviewer_actor=reviewer,worker=worker,job=job)
