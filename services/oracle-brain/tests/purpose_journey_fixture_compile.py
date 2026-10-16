"""Late synthetic external qualification consumes only actual same-journey outputs.

No production issuer, assessment quality claim, source grant or paid call lives here.
"""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.semantic_acceptance import IndependentAssessment,sealed
from oracle_brain.operating_model.acceptance_profiles import AssessmentPayload,validate_payload
from oracle_brain.operating_model.purpose_receipts_v2 import PhaseResponseCommitV2
from oracle_brain.operating_model.purpose_qualification_v3 import PurposeSemanticAdmissionV3,purpose_qualified_content_core_v3
from oracle_brain.operating_model.purpose_journey import PurposeWorkerJobV2
from oracle_brain.hosting.purpose_journey_v2 import (
    CompilerPhaseCustodyFileV2,CompilerPhaseCustodyAppointmentV2,PurposeCompileInputsV2,load_purpose_worker_settings_v2)
from test_purpose_worker_startup import make_next_compiler_worker_v2


def admit_compile_fixture(*,original,initial_settings,initial_job,extraction_settings,extraction_jobs,
        assembly,assessment,prior_settings,prior_job,prior_row,captured,evidence,root):
    root.mkdir(mode=0o700)
    def store(name,record):
        raw=canonical_bytes(record.model_dump(mode='json')) if hasattr(record,'model_dump') else canonical_bytes(record)
        path=root/name;path.write_bytes(raw);path.chmod(0o600)
        return path,hashlib.sha256(raw).hexdigest()
    def commit(phase):
        return PhaseResponseCommitV2.model_validate_json((phase['custody']/(str(phase['job'].dispatch_id)+'.phase-commit.json')).read_bytes())
    census_commit=commit(original);assembly_commit=commit(assembly);assessment_commit=commit(assessment)
    raw=(assessment['custody']/(str(assessment['job'].dispatch_id)+'.wire')).read_bytes()
    content=json.loads(raw)['choices'][0]['message']['content'];ctx=assessment['private'].assessment
    validate_payload(ctx,assessment['job'].request,content,trusted_context_hash=sealed(ctx),runtime_hash=ctx.runtime_hash,
        permission_hash=ctx.permission_hash,now=assessment_commit.committed_at)
    reported=AssessmentPayload.model_validate_json(content)
    report=IndependentAssessment(workspace_id=initial_job.workspace_id,census_hash=sealed(ctx.census),candidate_hash=captured.candidate_hash,
        permission_hash=ctx.permission_hash,protocol_hash=ctx.protocol_hash,assessor_actor=ctx.actor_id,assessor_model=ctx.model,
        assessed_at=assessment_commit.committed_at,dispatch_receipt_hash=sealed(assessment_commit),raw_response_hash=hashlib.sha256(raw).hexdigest(),
        coverage=reported.coverage,criteria=reported.criteria,detail_gap_ids=reported.detail_gap_ids,detail_gap_owners=reported.detail_gap_owners)
    commits=(census_commit,assembly_commit,assessment_commit)
    core=purpose_qualified_content_core_v3(captured,census=ctx.census,assessment=report,phase_commits=commits)
    cfg=prior_settings.config;ac=assembly['assembly'];now=datetime.now(timezone.utc);end=min(cfg.source_expires_at,initial_job.original_horizon)
    admission=PurposeSemanticAdmissionV3(workspace_id=initial_job.workspace_id,issuer_actor=cfg.semantic_issuer_actor,reviewer_actor=cfg.semantic_reviewer_actor,
        protocol_hash=sealed(assembly['assembly_protocol']),runtime_hash=cfg.runtime_hash,
        source_region_register_hash=digest({'regions':[r.model_dump(mode='json') for r in ctx.census.regions]}),
        census_hash=sealed(ctx.census),assessment_hash=sealed(report),candidate_hash=captured.candidate_hash,permission_hash=ctx.permission_hash,
        reviewer_report_hash=hashlib.sha256(raw).hexdigest(),object_evidence_hash=captured.object_evidence_hash,candidate_created_at=captured.observed_wire.observed_at,
        implementer_actor=ac.actor_id,assessor_actor=ctx.actor_id,candidate_model=ac.job.request['model'],purpose='independent-source-semantic-acceptance',
        expires_at=end,final_envelope_hash=digest(core),context_hash=sealed(ac),handoff_hash=sealed(ac.handoff),compiler_actor=cfg.actor_id,
        compiler_login=cfg.expected_session_role,compiler_permission_hash=digest({'actor':str(cfg.actor_id),'runtime':cfg.runtime_hash,'population':prior_settings.population.population_digest}),
        assembly_permission_hash=ac.job.permission_hash,assembly_runtime_hash=ac.runtime_hash,assessment_runtime_hash=ctx.runtime_hash,
        census_commit_hash=sealed(census_commit),assembly_commit_hash=sealed(assembly_commit),assessment_commit_hash=sealed(assessment_commit))
    inputs=PurposeCompileInputsV2(artifact_id=ac.model_id,artifact_version=ac.model_version,census_dispatch_id=original['job'].dispatch_id,
        assembly_dispatch_id=ac.job.dispatch_id,assessment_dispatch_id=assessment['job'].dispatch_id)
    job=PurposeWorkerJobV2(job_id=uuid4(),journey_id=initial_job.journey_id,workspace_id=initial_job.workspace_id,actor_id=initial_job.actor_id,
        phase='compile',source_refs=initial_job.source_refs,allocation_hash=initial_job.allocation_hash,parent_journal_hash=prior_row['journal_hash'],
        prior_receipt_hash=prior_row['receipt_hash'],nonce=uuid4().hex,runtime_hash=cfg.runtime_hash,admission_hash=sealed(admission),expires_at=end,original_horizon=initial_job.original_horizon)
    files=[]
    def appointed(kind,path,**selectors):
        path=Path(path);files.append(CompilerPhaseCustodyFileV2(kind=kind,path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),**selectors))
    for kind,record in [('compile_inputs',inputs),('semantic_admission',admission),('assessment',report),('assembly_context',ac),
            ('assembly_observer',assembly['assembly_observer']),('assembly_protocol',assembly['assembly_protocol'])]:
        path,_=store(kind+'.json',record)
        selectors={} if kind in {'compile_inputs','semantic_admission'} else {'dispatch_id':assessment['job'].dispatch_id if kind=='assessment' else ac.job.dispatch_id}
        appointed(kind,path,**selectors)
    appointed('assembly_observed',assembly['custody']/(str(ac.job.dispatch_id)+'.observed-wire.json'),dispatch_id=ac.job.dispatch_id)
    appointed('census_context',original['context_file'],dispatch_id=original['job'].dispatch_id)
    appointed('assessment_context',assessment['context_file'],dispatch_id=assessment['job'].dispatch_id)
    for phase in (original,assembly,assessment):
        dispatch=phase['job'].dispatch_id
        appointed('phase_commit',phase['custody']/(str(dispatch)+'.phase-commit.json'),dispatch_id=dispatch)
        appointed(phase['mode']+'_wire',phase['custody']/(str(dispatch)+'.wire'),dispatch_id=dispatch)
    # Full immutable extraction custody is explicitly reappointed to this current
    # compiler job, not borrowed from another journey or another actor's grants.
    extraction_custody=CompilerPhaseCustodyAppointmentV2.model_validate_json(Path(extraction_settings.config.custody_appointment_file).read_bytes())
    files.extend(extraction_custody.files[extraction_jobs[-1].job_id])
    settings,_=make_next_compiler_worker_v2(assessment,root/'worker',prior_settings=prior_settings,jobs=(job,),custody_files={job.job_id:tuple(files)})
    registry=json.loads(Path(cfg.semantic_registry_file).read_bytes())
    scope={k:registry[k] for k in ('qualification_purpose','workspace_id','runtime_hash','compiler_profile','issuer_actor','reviewer_actor')}
    record={**scope,'schema_version':3,'admission_hash':sealed(admission),'valid_from':datetime.now(timezone.utc).isoformat(),'expires_at':end.isoformat(),'revoked':False}
    record['record_seal']=digest(record);registry['admissions']=[record]
    registry_file,registry_hash=store('semantic-registry.json',registry)
    config=settings.config.model_copy(update={'semantic_registry_file':str(registry_file),'semantic_registry_sha256':registry_hash})
    config_file,config_hash=store('compiler-settings.json',config)
    settings=load_purpose_worker_settings_v2(str(config_file),config_hash)
    return settings,job,admission,report
