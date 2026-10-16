"""Explicit post-paid-output custody metadata for the single native fixture."""
import hashlib,json
from contextlib import contextmanager
from pathlib import Path
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.paid_sdk_embeddings_v3 import PaidSDKEmbeddingPinsV3
from oracle_brain.operating_model.purpose_receipts_v2 import PhaseResponseCommitV2
from oracle_brain.hosting.purpose_journey_v2 import CompilerPhaseCustodyFileV2,CompilerPhaseCustodyAppointmentV2
from test_purpose_worker_startup import make_next_compiler_worker_v2


@contextmanager
def unmounted_historical_extraction_wires(extraction,root):
    """TEST ONLY recoverable absence of exactly three already-paid raw files."""
    root.mkdir(mode=0o700)
    paths=tuple(extraction['custody']/(str(c.job.dispatch_id)+'.wire') for c in extraction['contexts'])
    assert len(paths)==3 and len(set(paths))==3
    moved=[]
    try:
        for index,path in enumerate(paths):
            seal=hashlib.sha256(path.read_bytes()).hexdigest();backup=root/(str(index)+'.wire-backup')
            assert not backup.exists()
            path.rename(backup);moved.append((path,backup,seal))
        yield paths
    finally:
        for path,backup,seal in reversed(moved):
            assert not path.exists() and hashlib.sha256(backup.read_bytes()).hexdigest()==seal
            backup.rename(path)


def appoint_actual_embedding_outputs(phase,*,worker,compile_job,artifact,root):
    """No new job/spool/attempt and no call to the compilation or provider worker."""
    root.mkdir(mode=0o700);job=phase['job'];private=phase['private'];directory=phase['custody']
    commit_path=directory/(str(job.dispatch_id)+'.phase-commit.json')
    native_path=directory/(str(job.dispatch_id)+'.json');wire_path=directory/(str(job.dispatch_id)+'.wire')
    commit=PhaseResponseCommitV2.model_validate_json(commit_path.read_bytes());native=json.loads(native_path.read_bytes())
    assert commit.phase=='embedding' and commit.dispatch_id==job.dispatch_id
    assert hashlib.sha256(wire_path.read_bytes()).hexdigest()==commit.raw_response_hash
    assert digest(native)==commit.native_custody_receipt_hash
    pins=PaidSDKEmbeddingPinsV3(context_hash=digest(private.model_dump(mode='json')),commit_hash=digest(commit.model_dump(mode='json')),
        native_receipt_hash=digest(native),descriptor_hash=digest(phase['descriptor'].model_dump(mode='json')),
        operation_approval_hash=phase['operation_hash'],parent_registry_hash=worker.population.parent_registry_sha256,
        allocation_hash=worker.config.allocation_projection_sha256,population_digest=worker.population.population_digest,
        ledger_identity_hash=worker.allocation.ledger_registry_hash,key_fingerprint=phase['platform']['coverage'].key_fingerprint)
    pins_path=root/'embedding-pins.json';pins_path.write_bytes(canonical_bytes(pins.model_dump(mode='json')));pins_path.chmod(0o600)
    old=CompilerPhaseCustodyAppointmentV2.model_validate_json(Path(worker.config.custody_appointment_file).read_bytes())
    files=list(old.files[compile_job.job_id]);selector=dict(artifact_id=artifact.artifact_id,artifact_version=artifact.version,dispatch_id=job.dispatch_id)
    for kind,path in [('embedding_context',Path(phase['context_file'])),('embedding_pins',pins_path),('phase_commit',commit_path),('native_receipt',native_path),('raw_wire',wire_path)]:
        files.append(CompilerPhaseCustodyFileV2(kind=kind,path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            native_job_hash=digest(job.model_dump(mode='json')),producer_runtime_hash=phase['descriptor'].runtime_hash,request_hash=job.request_hash,**selector))
    updated,jobs=make_next_compiler_worker_v2(phase,root/'worker',prior_settings=worker,jobs=(compile_job,),custody_files={compile_job.job_id:tuple(files)})
    assert jobs==(compile_job,) and updated.config.spool==worker.config.spool
    assert updated.config.runtime_hash==worker.config.runtime_hash and updated.config.expected_session_role==worker.config.expected_session_role
    assert updated.population==worker.population and updated.allocation==worker.allocation
    assert updated.config.semantic_registry_sha256==worker.config.semantic_registry_sha256
    return updated,pins


@contextmanager
def deliver_actual_paid_graph(worker,job,*,artifact,embedding_dispatch_id,root,tls,certificates,prepared_bundle,stage):
    """ONE actual native packet through protected factory and leased outbox.

    The fixture admin provisions only a new exact writer ACL. Runtime receives
    its own named writer credentials; UNKNOWN never confirms cleanup.
    """
    import asyncio,os,secrets
    from urllib.parse import urlsplit,urlunsplit
    from uuid import uuid4
    from dev.oracle2.test_readonly_graph_fixture import processing_writer
    from dev.oracle2.test_graph_tls_fixture import owned_graph_tls,verify_graph_tls_peer
    from test_hosting_boundary import WORKER
    from test_purpose_transport import SERVER
    from test_paid_projector_v3 import make_paid_projector_fixture_settings_v3
    from oracle_brain.hosting.paid_projector_v3 import project_paid_projector_event_v3,reload_paid_projector_projection_v3
    from oracle_brain.operating_model.processing_projection import lease_processing_projection
    root.mkdir(mode=0o700)
    admin=os.environ['ORACLE2_OPERATING_TEST_GRAPH_URL'];project=os.environ['COMPOSE_PROJECT_NAME']
    container=project+'-falkor-candidate-1';generation=uuid4()
    with processing_writer(container,admin,root/'writer',workspace_id=artifact.workspace_id,
            artifact_id=artifact.artifact_id,version=artifact.version,generation=generation) as writer:
        with owned_graph_tls(container,admin,server_context=tls,expected_client_uri=WORKER) as port:
            verify_graph_tls_peer(port,ca_file=certificates/'ca.pem',certificate_file=certificates/'worker.pem',
                key_file=certificates/'worker.key',expected_server_uri=SERVER)
            parsed=urlsplit(writer.environment['ORACLE2_TEST_PROCESSING_WRITER_GRAPH_URL'])
            graph_url=urlunsplit(('rediss',parsed.netloc.rsplit('@',1)[0]+'@localhost:'+str(port),'','',''))
            url_file=root/'writer-url';url_file.write_text(graph_url);url_file.chmod(0o600)
            key_file=root/'receipt-key';key_file.write_bytes(secrets.token_bytes(32));key_file.chmod(0o600)
            settings=make_paid_projector_fixture_settings_v3(worker,job,root/'projector',graph_url_file=url_file,
                tls_ca_file=certificates/'ca.pem',tls_certificate_file=certificates/'worker.pem',
                tls_key_file=certificates/'worker.key',receipt_key_file=key_file,artifact_id=artifact.artifact_id,
                artifact_version=artifact.version,embedding_dispatch_id=embedding_dispatch_id,generation=generation,projector_id=uuid4(),
                prepared_bundle=prepared_bundle)
            stage('protected_projector_settings_loaded')
            lease=lease_processing_projection(settings.bundle.ledger,job.workspace_id)
            assert lease is not None
            async def deliver():
                signed=await project_paid_projector_event_v3(settings,lease)
                assert signed['schema_version']==3 and signed['embedding_protocol']=='paid-sdk-embedding-v3'
                stage('protected_graph_ack_committed')
                # Fresh compiler reconstruction obtains the ACTUAL SQL ACK, not
                # this local return value or an owner SELECT/cached receipt.
                fresh=reload_paid_projector_projection_v3(settings)
                try:
                    loaded=await fresh.load(settings.bundle.ledger,job.workspace_id,artifact.artifact_id,artifact.version)
                    assert loaded['qualified_lineage']['schema_version']==3
                finally:await fresh.close()
                return signed
            signed=asyncio.run(deliver())
            yield dict(signed=signed,settings=settings,container=container,admin_url=admin,generation=generation)
            writer.confirm_inactive()  # All timely awaited calls/pools closed.
