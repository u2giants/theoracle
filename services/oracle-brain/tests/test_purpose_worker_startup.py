"""Owned invented compiler startup and actual native phase, no public provider."""
import hashlib,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql
import pytest
from test_purpose_native_census_startup import native_census_startup
from test_native_factory import actual_ledger
from test_purpose_source_authority import purpose_population
from test_source_processing_qualification import processing
from test_purpose_transport import bound_tls,certificates
from test_parent_observer_v2 import provision
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.purpose_context import BudgetAllocationPinsV2
from oracle_brain.operating_model.purpose_journey import PurposeWorkerJobV2
from oracle_brain.hosting.purpose_journey_v2 import (
    CompilerWorkerConfigV2,PurposeWorkerRegistryV2,CompilerPhaseCustodyAppointmentV2,
    CompilerPhaseCustodyFileV2,load_purpose_worker_settings_v2,PurposeJourneyCustodyV2,
    run_purpose_worker_once_v2,build_purpose_compiler_ledger_v3)


@pytest.fixture
def compiler_worker(admin_url,native_census_startup,tmp_path):
    x=native_census_startup;f=x['f'];c=x['settings'].config
    now=datetime.now(timezone.utc);end=min(f['expiry'],x['settings'].population.expires_at)
    root=tmp_path/'compiler';root.mkdir(mode=0o700)
    def store(name,value):
        raw=canonical_bytes(value.model_dump(mode='json')) if hasattr(value,'model_dump') else value
        path=root/name;path.write_bytes(raw);path.chmod(0o600)
        return str(path),hashlib.sha256(raw).hexdigest()
    login='purpose_compiler_'+uuid4().hex[:10]
    with psycopg.connect(admin_url) as conn:
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-worker-only')))
        conn.execute(sql.SQL('GRANT oracle2_candidate_compiler TO {}').format(sql.Identifier(login)))
        conn.execute('INSERT INTO oracle2.hosting_role_runtime_admissions SELECT %s,runtime_hash,registry_hash,expires_at FROM oracle2.hosting_role_runtime_admissions WHERE role_name=%s',(login,f['login']))
        conn.execute('INSERT INTO oracle2.hosting_role_source_admissions SELECT %s,workspace_id,source_id,revision,principal_id,original_hash,reading_hash,parser_id,runtime_hash,registry_hash,expires_at FROM oracle2.hosting_role_source_admissions WHERE role_name=%s',(login,f['login']))
        owner=conn.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
        for ref in f['refs']:
            if conn.execute('SELECT 1 FROM oracle2.appointments WHERE workspace_id=%s AND actor_id=%s AND scope=%s AND revoked_at IS NULL',(f['workspace'],f['actor'],'source-extraction:'+str(ref.source_id))).fetchone():continue
            conn.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f['workspace'],f['actor'],'source-extraction:'+str(ref.source_id),owner,f['root'],end))
    # Independent actual SQL login, never a provider/source-reader credential.
    url=psycopg.conninfo.make_conninfo(admin_url,user=login,password='invented-worker-only')
    url_file,_=store('compiler-url',url.encode())
    allocation=BudgetAllocationPinsV2.model_validate_json(Path(c.budget_allocation_projection_file).read_bytes())
    extraction=x['mode']=='extraction'
    job=PurposeWorkerJobV2(job_id=uuid4(),journey_id=uuid4(),workspace_id=f['workspace'],actor_id=f['actor'],
        phase='extraction' if extraction else 'census',source_refs=f['refs'],
        source_id=x['contexts'][0].receipt.ref.source_id if extraction else None,
        parent_journal_hash='e'*64 if extraction else None,prior_receipt_hash='f'*64 if extraction else None,allocation_hash=allocation.allocation_hash,nonce=uuid4().hex,
        runtime_hash=f['runtime'],admission_hash='1'*64,dispatch_id=x['job'].dispatch_id,
        request_hash=x['job'].request_hash,phase_registry_sha256=x['operation_hash'],
        expires_at=end,original_horizon=allocation.original_expires_at)
    issuer,reviewer,cissuer,creviewer,sissuer,sreviewer=(uuid4() for _ in range(6))
    registry=PurposeWorkerRegistryV2(workspace_id=f['workspace'],actor_id=f['actor'],worker_uri=c.worker_uri,
        runtime_hash=f['runtime'],issuer_actor=issuer,reviewer_actor=reviewer,valid_from=now-timedelta(seconds=1),expires_at=end,jobs=(job,))
    registry_file,registry_hash=store('jobs.json',registry)
    outputs=[]
    for kind,suffix in [('phase_commit','.phase-commit.json'),('native_receipt','.json')]:
        outputs.append(CompilerPhaseCustodyFileV2(kind=kind,path=str(x['custody']/(str(job.dispatch_id)+suffix)),
            dispatch_id=job.dispatch_id,native_job_hash=digest(x['job'].model_dump(mode='json')),
            request_hash=job.request_hash,producer_runtime_hash=f['runtime']))
    appointment=CompilerPhaseCustodyAppointmentV2(workspace_id=f['workspace'],actor_id=f['actor'],compiler_login=login,
        runtime_hash=f['runtime'],population_digest=x['settings'].population.population_digest,
        issuer_actor=cissuer,reviewer_actor=creviewer,valid_from=now-timedelta(seconds=1),expires_at=end,files={job.job_id:tuple(outputs)})
    if extraction:
        ctx=x['contexts'][0];target=x['qualification'].target(job.dispatch_id)
        ctx_file,ctx_hash=store('extraction-context.json',ctx)
        native=dict(dispatch_id=job.dispatch_id,native_job_hash=ctx.job_hash,artifact_id=target.artifact_id,
            artifact_version=target.artifact_version,source_ref=target.source_ref)
        outputs=[entry.model_copy(update={k:v for k,v in native.items() if k!='dispatch_id'}) for entry in outputs]
        outputs.extend([
            CompilerPhaseCustodyFileV2(kind='native_job',path=ctx_file,sha256=ctx_hash,**native),
            CompilerPhaseCustodyFileV2(kind='extraction_qualification',path=c.extraction_qualification_file,
                sha256=c.extraction_qualification_sha256,**native),
            CompilerPhaseCustodyFileV2(kind='raw_wire',path=str(x['custody']/(str(job.dispatch_id)+'.wire')),
                request_hash=job.request_hash,producer_runtime_hash=f['runtime'],**native),
            CompilerPhaseCustodyFileV2(kind='wire_metadata',path=str(x['custody']/(str(job.dispatch_id)+'.wire.json')),
                request_hash=job.request_hash,producer_runtime_hash=f['runtime'],**native)])
        appointment=appointment.model_copy(update={'files':{job.job_id:tuple(outputs)}})
    custody_file,custody_hash=store('custody.json',appointment)
    semantic=dict(schema_version=3,qualification_purpose='captured-assembly-semantic-admission-v3',workspace_id=str(f['workspace']),
        runtime_hash=f['runtime'],compiler_profile='candidate-compiler',issuer_actor=str(sissuer),reviewer_actor=str(sreviewer),
        valid_from=(now-timedelta(seconds=1)).isoformat(),expires_at=end.isoformat(),revoked=False,admissions=[])
    semantic_file,semantic_hash=store('semantic.json',canonical_bytes(semantic))
    # Independent restart-safe observation state; signing service remains the
    # explicitly invented existing mTLS fixture, not a production issuer.
    observer=root/'observer';observer.mkdir(mode=0o700)
    admission=x['settings'].observer.admission
    _,replay=provision(observer,admission)
    tls=dict(hostname=c.observer_hostname,port=c.observer_port,server_uri=c.observer_server_uri,client_uri=c.observer_client_uri,
        ca_file=c.observer_ca,certificate_file=c.observer_certificate,key_file=c.observer_key)
    client=x['client'].binding
    provider=dict(hostname=client.hostname,port=client.port,server_uri=client.server_uri,client_uri=client.client_uri,
        ca_file=str(client.ca_file),certificate_file=str(client.certificate_file),key_file=str(client.key_file))
    spool=root/'queue';spool.mkdir(mode=0o700)
    config=CompilerWorkerConfigV2(workspace_id=f['workspace'],actor_id=f['actor'],worker_uri=c.worker_uri,runtime_hash=f['runtime'],
        source_registry_hash=f['registry'],expected_owner_role=f['binding'].expected_owner_role,expected_session_role=login,source_expires_at=end,
        database_url_file=url_file,jobs_registry_file=registry_file,jobs_registry_sha256=registry_hash,worker_issuer_actor=issuer,worker_reviewer_actor=reviewer,
        population_file=c.population_file,population_sha256=digest(x['settings'].population.model_dump(mode='json')),
        allocation_projection_file=c.budget_allocation_projection_file,allocation_projection_sha256=digest(allocation.model_dump(mode='json')),
        custody_appointment_file=custody_file,custody_appointment_sha256=custody_hash,custody_issuer_actor=cissuer,custody_reviewer_actor=creviewer,
        parent_observer_admission_file=c.parent_observer_admission_file,parent_observer_admission_hash=c.parent_observer_admission_hash,
        observer_client=tls,observer_spool=str(observer),observer_namespace='parent-v2',observer_initialization_hash=replay['initialization_receipt_hash'],
        clients={job.phase:provider},spool=str(spool),blob_root=str(root/'blobs'),semantic_registry_file=semantic_file,semantic_registry_sha256=semantic_hash,
        semantic_issuer_actor=sissuer,semantic_reviewer_actor=sreviewer,semantic_valid_from=now-timedelta(seconds=1),semantic_expires_at=end)
    config_file,config_hash=store('worker.json',config)
    settings=load_purpose_worker_settings_v2(config_file,config_hash)
    yield x,settings,job


def test_actual_compiler_startup_native_phase_and_no_repost(compiler_worker):
    x,settings,job=compiler_worker
    ledger=build_purpose_compiler_ledger_v3(settings,job)
    assert ledger.processing_sources.binding.expected_session_role!=x['f']['login']
    PurposeJourneyCustodyV2(settings).admit(job.job_id)
    try:row=run_purpose_worker_once_v2(settings)
    except Exception as error:raise AssertionError(str(x['state']['failure'])) from error
    assert row['state']=='awaiting-external-phase-admission' and x['state']['posts']==1
    assert run_purpose_worker_once_v2(settings) is None
    assert x['state']['posts']==1


def test_actual_post_phase_revocation_retains_cost_and_spent_attempt_no_success(admin_url,compiler_worker):
    x,settings,job=compiler_worker
    def revoke_census_only():
        with psycopg.connect(admin_url) as conn:
            conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['f']['grants'][2],))
    x['state']['after_post']=revoke_census_only
    custody=PurposeJourneyCustodyV2(settings);custody.admit(job.job_id)
    from oracle_brain.hosting.gateway import GatewayDenied
    with pytest.raises(GatewayDenied):run_purpose_worker_once_v2(settings)
    assert x['state']['posts']==1
    rows=custody.journal.read(job.journey_id)
    assert [r['state'] for r in rows]==['attempt-started','awaiting-external-custody']
    assert run_purpose_worker_once_v2(settings) is None and x['state']['posts']==1
    assert not (x['custody']/(str(job.dispatch_id)+'.phase-commit.json')).exists()
    assert (x['custody']/(str(job.dispatch_id)+'.wire')).exists()
    with psycopg.connect(x['billing_admin']) as conn:
        assert conn.execute('SELECT count(*) FROM oracle2.operating_dispatch_reservations').fetchone()[0]==1
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s',(job.workspace_id,)).fetchone()[0]==0


def test_actual_compiler_revoked_before_claim_never_posts_or_opens_results(admin_url,compiler_worker):
    x,settings,job=compiler_worker
    custody=PurposeJourneyCustodyV2(settings);custody.admit(job.job_id)
    with psycopg.connect(admin_url) as conn:
        conn.execute('DELETE FROM oracle2.hosting_role_source_admissions WHERE role_name=%s AND source_id=%s',
            (settings.config.expected_session_role,job.source_refs[2].source_id))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):run_purpose_worker_once_v2(settings)
    assert x['state']['posts']==0 and custody.journal.read(job.journey_id)==[]
    assert not list(Path(settings.config.spool).glob('*.claimed'))


@pytest.mark.parametrize('native_census_startup',['extraction'],indirect=True)
def test_actual_paid_extraction_compiler_guard_persists_and_rereads_original(admin_url,compiler_worker):
    from oracle_brain.hosting.purpose_journey_v2 import persist_purpose_extraction_result_v2
    x,settings,job=compiler_worker
    reply=x['client'].dispatch(job.dispatch_id,job.request_hash,x['operation_hash'],deadline=x['expires_at'])
    assert reply['extraction_qualification_sha256']==job.phase_registry_sha256 and x['state']['posts']==1
    manifest=persist_purpose_extraction_result_v2(settings,job)
    ledger=build_purpose_compiler_ledger_v3(settings,job)
    actual,payload=ledger.read_with_manifest(job.workspace_id,manifest.artifact_id,manifest.version)
    assert actual==manifest and payload['complete'] is True and manifest.kind=='processing_extraction_v1'
    assert payload['findings'][0]['kind']=='missing_information'
    assert payload['findings'][0]['evidence_refs'][0]['quote']==x['contexts'][0].receipt.reading
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT count(*) FROM oracle2.outbox WHERE assertion_id=%s',(manifest.artifact_id,)).fetchone()[0]==0
    assert x['state']['posts']==1


@pytest.mark.parametrize('native_census_startup',['extraction'],indirect=True)
def test_actual_native_failed_attempt_is_reported_without_success_or_settlement(admin_url,compiler_worker):
    from oracle_brain.hosting.purpose_journey_v2 import persist_purpose_extraction_result_v2
    from oracle_brain.hosting.gateway import GatewayDenied
    x,settings,job=compiler_worker
    def revoke_provider_only():
        with psycopg.connect(admin_url) as conn:
            conn.execute('DELETE FROM oracle2.hosting_role_source_admissions WHERE role_name=%s AND source_id=%s',
                (x['f']['login'],job.source_refs[2].source_id))
    x['state']['after_post']=revoke_provider_only
    with pytest.raises(GatewayDenied):
        x['client'].dispatch(job.dispatch_id,job.request_hash,x['operation_hash'],deadline=x['expires_at'])
    assert x['state']['posts']==1
    manifest=persist_purpose_extraction_result_v2(settings,job,failed=True)
    ledger=build_purpose_compiler_ledger_v3(settings,job)
    actual,payload=ledger.read_with_manifest(job.workspace_id,manifest.artifact_id,manifest.version,include_failed=True)
    assert actual==manifest and manifest.kind=='processing_failed_extraction_v1' and manifest.state=='failed'
    assert payload['complete'] is False and payload['observations']==[] and payload['findings']==[]
    assert payload['settlement_verified'] is False and payload['native_failed_custody']['complete_wire'] is True
    assert not (x['custody']/(str(job.dispatch_id)+'.phase-commit.json')).exists()
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT count(*) FROM oracle2.outbox WHERE assertion_id=%s',(manifest.artifact_id,)).fetchone()[0]==0
    assert x['state']['posts']==1


@pytest.mark.parametrize('native_census_startup',['extraction'],indirect=True)
def test_actual_compiler_revoked_during_bundle_returns_no_private_result(admin_url,compiler_worker,monkeypatch):
    import oracle_brain.hosting.purpose_journey_v2 as worker
    x,settings,job=compiler_worker
    x['client'].dispatch(job.dispatch_id,job.request_hash,x['operation_hash'],deadline=x['expires_at'])
    original=worker._worker_file;seen=[]
    def revoke_after_first(path,*args,**kwargs):
        raw=original(path,*args,**kwargs)
        if str(path).endswith(str(job.dispatch_id)+'.wire'):
            seen.append(str(path))
            with psycopg.connect(admin_url) as conn:
                conn.execute('DELETE FROM oracle2.hosting_role_source_admissions WHERE role_name=%s AND source_id=%s',
                    (settings.config.expected_session_role,job.source_refs[2].source_id))
        return raw
    monkeypatch.setattr(worker,'_worker_file',revoke_after_first)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        settings.private_bundle(job,(('raw_wire',dict(dispatch_id=job.dispatch_id)),
            ('native_receipt',dict(dispatch_id=job.dispatch_id))))
    assert len(seen)==1
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s',(job.workspace_id,)).fetchone()[0]==0


def test_actual_phase_output_cannot_replace_registry_parent_or_original_allocation(compiler_worker):
    from oracle_brain.hosting.purpose_journey_v2 import _phase_commit_from_custody
    x,settings,job=compiler_worker
    x['client'].dispatch(job.dispatch_id,job.request_hash,x['operation_hash'],deadline=x['expires_at'])
    committed=_phase_commit_from_custody(settings,job)
    path=x['custody']/(str(job.dispatch_id)+'.phase-commit.json')
    raw=path.read_bytes()
    for field in ('operation_approval_hash','parent_registry_hash','budget_identity_hash'):
        changed=committed.model_dump(mode='json');changed[field]='0'*64
        path.write_bytes(canonical_bytes(changed))
        with pytest.raises(PermissionError,match='authorized phase commit differs'):
            _phase_commit_from_custody(settings,job)
        path.write_bytes(raw)
    assert x['state']['posts']==1
