"""Explicit post-paid-output custody metadata for the single native fixture."""
import hashlib,json
from pathlib import Path
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.paid_sdk_embeddings_v3 import PaidSDKEmbeddingPinsV3
from oracle_brain.operating_model.purpose_receipts_v2 import PhaseResponseCommitV2
from oracle_brain.hosting.purpose_journey_v2 import CompilerPhaseCustodyFileV2,CompilerPhaseCustodyAppointmentV2
from test_purpose_worker_startup import make_next_compiler_worker_v2


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
