"""One newly authored population for the owned synthetic native journey.

Original input custody precedes operation admission. No old paid result is adopted.
"""
import hashlib

import psycopg

from purpose_journey_fixture_models import RICH_SOURCE_TEXTS
from test_purpose_source_authority import purpose_population,context
from test_source_processing_qualification import processing


def test_rich_originals_are_sealed_before_source_admission(admin_url,purpose_population):
    f=purpose_population('census','source-reader',source_texts=RICH_SOURCE_TEXTS)
    resolver,_,_=context(f)
    receipts=resolver.read_population()
    assert tuple(receipt.reading for receipt in receipts)==RICH_SOURCE_TEXTS
    with psycopg.connect(admin_url) as connection:
        for receipt,text in zip(receipts,RICH_SOURCE_TEXTS):
            expected=hashlib.sha256(text.encode()).hexdigest()
            assert receipt.ref.reading_sha256==expected and receipt.ref.original_sha256==expected
            admitted=connection.execute(
                'SELECT reading_hash FROM oracle2.hosting_role_source_admissions '
                'WHERE role_name=%s AND workspace_id=%s AND source_id=%s',
                (f['login'],f['workspace'],receipt.ref.source_id)).fetchone()
            assert admitted==(expected,)
        assert connection.execute('SELECT DISTINCT status FROM oracle2.drafts WHERE workspace_id=%s',(f['workspace'],)).fetchall()==[('draft',)]
        assert connection.execute('SELECT count(*) FROM oracle2.reviews WHERE workspace_id=%s',(f['workspace'],)).fetchone()==(0,)


import pytest
from test_purpose_native_census_startup import native_census_startup
from test_purpose_worker_startup import compiler_worker
from test_native_factory import actual_ledger
from test_purpose_transport import bound_tls,certificates
from test_parent_observer_v2 import provision
from oracle_brain.operating_model.contracts import digest
from oracle_brain.hosting.purpose_journey_v2 import PurposeJourneyCustodyV2,run_purpose_worker_once_v2


@pytest.mark.parametrize('native_census_startup',[{'phase':'census','coherent':True}],indirect=True)
def test_coherent_native_census_uses_real_prior_input_parent(compiler_worker,admin_url,tmp_path):
    import json,time
    started=time.monotonic();timings={}
    def stage(name):
        timings[name]=round(time.monotonic()-started,3)
        path=tmp_path/'stage-timings.json';path.write_text(json.dumps(timings,sort_keys=True));path.chmod(0o600)
    x,settings,job=compiler_worker
    parent=x['input_parent']
    assert parent is not None and len(parent.contexts)==3
    assert set(c.receipt.reading for c in parent.contexts)==set(RICH_SOURCE_TEXTS)
    assert parent.runtime_hash==x['input_runtime'] and all(c.actor_id==x['input_actor'] for c in parent.contexts)
    assert settings.population.parent_registry_sha256==digest(parent.model_dump(mode='json'))
    assert {c.job.batch_id for c in parent.contexts}=={x['job'].batch_id}
    custody=PurposeJourneyCustodyV2(settings);custody.admit(job.job_id)
    try:row=run_purpose_worker_once_v2(settings)
    except Exception as error:raise AssertionError(str(x['state'].get('failure'))) from error
    assert row['state']=='awaiting-external-phase-admission' and x['state']['posts']==1
    stage('census_committed')
    assert len(custody.journal.read(job.journey_id))==2
    from purpose_journey_fixture_phases import freeze_authorized_census
    frozen=freeze_authorized_census(settings,job)
    assert len(frozen.obligations)==6 and frozen.frozen_at<=__import__('datetime').datetime.now(__import__('datetime').timezone.utc)
    assert x['state']['requests'][0]['messages']==x['job'].request['messages']
    # Original-input custody is sealed; no extraction operation registry, paid
    # result, or future phase body was manufactured to establish this barrier.
    assert not list(x['custody'].glob('*.extraction*'))
    from purpose_journey_fixture_phases import admit_extraction_phase
    extraction=admit_extraction_phase(x,admin_url=admin_url,root=tmp_path/'late-extraction',census_row=row)
    from purpose_journey_fixture_phases import extraction_worker_appointments
    current,jobs=extraction_worker_appointments(extraction,prior_settings=settings,initial_job=job,census_row=row,root=tmp_path/'extraction-worker')
    extraction_custody=PurposeJourneyCustodyV2(current)
    for admitted in jobs:
        x['observe_fixture_coverage']()
        extraction_custody.admit(admitted.job_id)
        result=run_purpose_worker_once_v2(current)
        assert result['state']=='awaiting-external-phase-admission'
    with psycopg.connect(admin_url) as connection:
        manifests=connection.execute("SELECT artifact_id,kind,state FROM oracle2.artifact_manifests WHERE workspace_id=%s",(job.workspace_id,)).fetchall()
        assert len(manifests)==3 and all(m[1:] == ('processing_extraction_v1','ready') for m in manifests)
        assert connection.execute('SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s',(job.workspace_id,)).fetchone()==(0,)
    assert x['state']['posts']==4
    stage('three_extractions_committed')
    assert extraction['settings'].population.parent_registry_sha256==settings.population.parent_registry_sha256

    from oracle_brain.hosting.purpose_journey_v2 import build_purpose_compiler_ledger_v3
    from oracle_brain.operating_model.purpose_assembly_v2 import compiler_extraction_handoff_v2
    from datetime import datetime,timezone
    compiler=build_purpose_compiler_ledger_v3(current,jobs[-1])
    handoff=compiler_extraction_handoff_v2(compiler,workspace_id=job.workspace_id,
        extraction_ids=tuple((c.job.artifact_id,1) for c in extraction['contexts']),
        source_refs=job.source_refs,compiler_authority_receipt_hash=digest(result),
        now=datetime.now(timezone.utc),expires_at=current.population.expires_at)
    assert len(handoff.extractions)==3 and handoff.source_refs==frozen.source_refs
    assert all(e.payload['observations'] and e.payload['findings'] for e in handoff.extractions)
    stage('compiler_handoff_verified')
    from purpose_journey_fixture_phases import admit_assembly_phase,phase_worker_appointment
    receipts=tuple(c.receipt for c in extraction['contexts'])
    assembly=admit_assembly_phase(x,admin_url=admin_url,root=tmp_path/'late-assembly',handoff=handoff,census=frozen,receipts=receipts)
    assembled,assembly_job=phase_worker_appointment(assembly,prior_settings=current,prior_job=jobs[-1],prior_row=result,root=tmp_path/'assembly-worker')
    x['observe_fixture_coverage']()
    PurposeJourneyCustodyV2(assembled).admit(assembly_job.job_id)
    assembly_row=run_purpose_worker_once_v2(assembled)
    assert assembly_row['state']=='awaiting-external-phase-admission' and x['state']['posts']==5
    stage('assembly_committed')
    from purpose_journey_fixture_phases import capture_actual_assembly
    captured,evidence=capture_actual_assembly(assembly)
    assert captured.handoff_hash==digest(handoff.model_dump(mode='json'))
    assessment=admit_assembly_phase(x,admin_url=admin_url,root=tmp_path/'late-assessment',handoff=handoff,census=frozen,
        receipts=receipts,phase='assessment',captured=captured,evidence=evidence)
    assessed,assessment_job=phase_worker_appointment(assessment,prior_settings=assembled,prior_job=assembly_job,
        prior_row=assembly_row,root=tmp_path/'assessment-worker')
    x['observe_fixture_coverage']()
    PurposeJourneyCustodyV2(assessed).admit(assessment_job.job_id)
    try:assessment_row=run_purpose_worker_once_v2(assessed)
    except Exception as error:raise AssertionError(str(x['state'].get('failure'))) from error
    assert assessment_row['state']=='awaiting-external-phase-admission' and x['state']['posts']==6
    stage('assessment_committed')
    assert assessment['descriptor'].actor_id!=assembly['descriptor'].actor_id
    assert assessment['descriptor'].provider_login!=assembly['descriptor'].provider_login
    assert assessment['job'].request['model']!=assembly['job'].request['model']
    from purpose_journey_fixture_compile import admit_compile_fixture
    compiled,compile_job,semantic,report=admit_compile_fixture(original=x,initial_settings=settings,initial_job=job,
        extraction_settings=current,extraction_jobs=jobs,assembly=assembly,assessment=assessment,prior_settings=assessed,
        prior_job=assessment_job,prior_row=assessment_row,captured=captured,evidence=evidence,root=tmp_path/'late-compile')
    PurposeJourneyCustodyV2(compiled).admit(compile_job.job_id)
    compile_row=run_purpose_worker_once_v2(compiled)
    assert compile_row['state']=='qualified-model-outbox-committed' and x['state']['posts']==6
    stage('qualified_model_committed')
    with psycopg.connect(admin_url) as connection:
        assert connection.execute("SELECT kind,state FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s",
            (job.workspace_id,assembly['job'].artifact_id)).fetchone()==('processing_qualified_model_v1','ready')
        assert connection.execute("SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s AND payload->>'namespace'='oracle_processing_v1'",
            (job.workspace_id,)).fetchone()==(1,)
    from oracle_brain.hosting.purpose_journey_v2 import build_purpose_qualified_reader_v3
    compiled_ledger=build_purpose_qualified_reader_v3(compiled,compile_job)
    qualified=compiled_ledger.read_with_manifest(job.workspace_id,assembly['job'].artifact_id,1)
    embedding=admit_assembly_phase(x,admin_url=admin_url,root=tmp_path/'late-embedding',handoff=handoff,census=frozen,
        receipts=receipts,phase='embedding',qualified=qualified,semantic_settings=compiled)
    x['observe_fixture_coverage']()
    try:embedding_reply=embedding['client'].dispatch(embedding['job'].dispatch_id,embedding['job'].request_hash,
        embedding['operation_hash'],deadline=embedding['descriptor'].expires_at)
    except Exception as error:raise AssertionError(str(x['state'].get('failure'))) from error
    assert x['state']['posts']==7 and set(embedding_reply)=={'dispatch_id','request_hash','phase_registry_sha256','raw_response_hash','receipt_hash'}
    stage('native_embedding_committed')
    from purpose_journey_fixture_delivery import appoint_actual_embedding_outputs
    delivered_worker,embedding_pins=appoint_actual_embedding_outputs(embedding,worker=compiled,compile_job=compile_job,
        artifact=qualified[0],root=tmp_path/'late-paid-consumer')
    stage('embedding_custody_reappointment_loaded')
    from oracle_brain.hosting.paid_sdk_delivery_v3 import load_paid_sdk_bundle_v3
    from purpose_journey_fixture_delivery import deliver_actual_paid_graph,unmounted_historical_extraction_wires
    # Summary is a compiler operation: retain all historical paid proof here.
    from oracle_brain.hosting.paid_sdk_delivery_v3 import CurrentPaidSDKGuardV3
    summary_compiler=build_purpose_qualified_reader_v3(delivered_worker,compile_job)
    summary_guard=CurrentPaidSDKGuardV3(summary_compiler.processing_read_guard)
    from oracle_brain.operating_model.retrieval import QueryPlan
    from oracle_brain.operating_model.summaries import summarize_from_ledger,persist_summary
    from uuid import uuid4
    summary=summarize_from_ledger(summary_compiler,job.workspace_id,qualified[0].artifact_id,1,
        QueryPlan(view='company_overview',question='Invented complete workflow',max_bytes=128*1024,page=0,page_size=25),
        qualification_guard=summary_guard)
    summary_manifest=persist_summary(summary_compiler,summary,summary_id=uuid4(),summary_version=1,
        permission_digest=qualified[0].permission_digest,compiler_digest=delivered_worker.config.runtime_hash,
        qualification_guard=summary_guard)
    assert summary_manifest.kind=='processing_summary_v1'
    with psycopg.connect(admin_url) as connection:
        assert connection.execute("SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s AND payload->>'namespace'='oracle_processing_v1'",
            (job.workspace_id,)).fetchone()==(1,)
    stage('compiler_summary_committed_without_second_projection')
    with unmounted_historical_extraction_wires(extraction,tmp_path/'unmounted-extraction-wire-backups') as absent:
        paid=load_paid_sdk_bundle_v3(delivered_worker,compile_job,artifact_id=qualified[0].artifact_id,artifact_version=1,
            embedding_dispatch_id=embedding['job'].dispatch_id)
        assert len(paid.embedder.data.vectors)==len(paid.embedder.data.inventory.inputs)
        assert all(len(v)==256 for v in paid.embedder.data.vectors)
        stage('protected_paid_bundle_without_historical_raw_wire')
        def raw_compile_negatives():
            with pytest.raises(FileNotFoundError) as raw_denial:
                paid.ledger.read_with_manifest(job.workspace_id,handoff.extractions[0].manifest.artifact_id,1)
            assert __import__('pathlib').Path(raw_denial.value.filename) in absent
            with pytest.raises(FileNotFoundError) as compile_denial:
                paid.ledger.persist(workspace_id=job.workspace_id,artifact_id=qualified[0].artifact_id,version=1,
                    kind='processing_qualified_model_v1',payload=qualified[1],refs=job.source_refs,
                    permission_digest=qualified[0].permission_digest,compiler_digest=qualified[0].compiler_digest,
                    dependencies=tuple(('artifact',str(e.manifest.artifact_id),str(e.manifest.version)) for e in handoff.extractions))
            assert __import__('pathlib').Path(compile_denial.value.filename) in absent
            stage('raw_read_and_direct_compile_refused_missing_paid_proof')
        with deliver_actual_paid_graph(delivered_worker,compile_job,artifact=qualified[0],
            embedding_dispatch_id=embedding['job'].dispatch_id,root=tmp_path/'actual-paid-graph',
            tls=x['platform']['tls'],certificates=__import__('pathlib').Path(x['platform']['binding'](1).ca_file).parent,
            prepared_bundle=paid,stage=stage) as delivery:
            assert delivery['signed']['content_hash']==qualified[0].content_hash and x['state']['posts']==7
            stage('protected_graph_ack_and_compiler_restart')
            from purpose_journey_fixture_executor import verify_protected_executor
            verify_protected_executor(delivery,admin_url=admin_url,worker=delivered_worker,job=compile_job,
                summary_manifest=summary_manifest,extraction_ids=tuple((e.manifest.artifact_id,e.manifest.version) for e in handoff.extractions),
                root=tmp_path/'actual-executor',tls=x['platform']['tls'],
                certificates=__import__('pathlib').Path(x['platform']['binding'](1).ca_file).parent,stage=stage,
                after_positive=raw_compile_negatives)
