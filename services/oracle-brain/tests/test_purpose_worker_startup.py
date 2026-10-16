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


def make_initial_compiler_worker_v2(admin_url,x,compiler_root):
    """TEST ONLY independent fixture provisioning; not a runtime issuer."""
    f=x['f'];c=x['settings'].config
    now=datetime.now(timezone.utc);end=min(f['expiry'],x['settings'].population.expires_at)
    root=Path(compiler_root);root.mkdir(mode=0o700)
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
        expires_at=min(end,x.get('phase_expires_at',end),datetime.now(timezone.utc)+timedelta(seconds=x.get('worker_job_seconds',600))),original_horizon=allocation.original_expires_at)
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
            CompilerPhaseCustodyFileV2(kind='extraction_population',path=c.population_file,
                sha256=x['qualification'].population_admission_sha256,**native),
            CompilerPhaseCustodyFileV2(kind='extraction_qualification',path=c.extraction_qualification_file,
                sha256=c.extraction_qualification_sha256,**native),
            CompilerPhaseCustodyFileV2(kind='raw_wire',path=str(x['custody']/(str(job.dispatch_id)+'.wire')),
                request_hash=job.request_hash,producer_runtime_hash=f['runtime'],**native),
            CompilerPhaseCustodyFileV2(kind='wire_metadata',path=str(x['custody']/(str(job.dispatch_id)+'.wire.json')),
                request_hash=job.request_hash,producer_runtime_hash=f['runtime'],**native)])
        appointment=appointment.model_copy(update={'files':{job.job_id:tuple(outputs)}})
    if not extraction:
        outputs.extend(CompilerPhaseCustodyFileV2(kind=kind,
            path=str(x['custody']/(str(job.dispatch_id)+suffix)),dispatch_id=job.dispatch_id,
            native_job_hash=digest(x['job'].model_dump(mode='json')),request_hash=job.request_hash,
            producer_runtime_hash=f['runtime']) for kind,suffix in [('raw_wire','.wire'),('wire_metadata','.wire.json')])
        context_path=Path(x['context_file'])
        outputs.append(CompilerPhaseCustodyFileV2(kind='census_context',path=str(context_path),
            sha256=hashlib.sha256(context_path.read_bytes()).hexdigest(),dispatch_id=job.dispatch_id))
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
        observer_client=tls,observer_timeout_seconds=5.0,provider_rpc_timeout_seconds=float(client.timeout),observer_spool=str(observer),observer_namespace='parent-v2',observer_initialization_hash=replay['initialization_receipt_hash'],
        clients={job.phase:provider},spool=str(spool),blob_root=str(root/'blobs'),semantic_registry_file=semantic_file,semantic_registry_sha256=semantic_hash,
        semantic_issuer_actor=sissuer,semantic_reviewer_actor=sreviewer,semantic_valid_from=now-timedelta(seconds=1),semantic_expires_at=end)
    config_file,config_hash=store('worker.json',config)
    settings=load_purpose_worker_settings_v2(config_file,config_hash)
    return settings,(job,)


@pytest.fixture
def compiler_worker(admin_url,native_census_startup,tmp_path):
    settings,jobs=make_initial_compiler_worker_v2(admin_url,native_census_startup,tmp_path/'compiler')
    return native_census_startup,settings,jobs[0]


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


def make_next_compiler_worker_v2(x,compiler_root,*,prior_settings,jobs,custody_files,spool=None):
    """TEST ONLY late external appointment, same actual compiler/root/allocation.

    Call only after actual predecessor outputs. This helper creates no phase
    job/context/provider approval: its explicit jobs and exact file capabilities
    are supplied by the independently authored coherent fixture owner.
    """
    from oracle_brain.hosting.purpose_journey_v2 import CompilerWorkerSettingsV2
    assert type(prior_settings) is CompilerWorkerSettingsV2 and type(jobs) is tuple and jobs
    old=prior_settings.config;root=Path(compiler_root);root.mkdir(mode=0o700)
    now=datetime.now(timezone.utc)
    assert set(custody_files)=={j.job_id for j in jobs}
    assert all(type(j) is PurposeWorkerJobV2 and j.workspace_id==old.workspace_id and j.actor_id==old.actor_id
        and j.runtime_hash==old.runtime_hash and j.source_refs==prior_settings.population.source_refs
        and j.allocation_hash==prior_settings.allocation.allocation_hash
        and j.original_horizon==prior_settings.allocation.original_expires_at for j in jobs)
    assert spool is None or str(spool)==old.spool
    current_population=x['population']
    assert current_population.source_refs==prior_settings.population.source_refs
    assert current_population.parent_registry_sha256==prior_settings.population.parent_registry_sha256
    assert current_population.source_registry_hash==old.source_registry_hash
    phase_config=x['settings'].config
    allocation=BudgetAllocationPinsV2.model_validate_json(Path(phase_config.budget_allocation_projection_file).read_bytes())
    assert allocation==prior_settings.allocation
    end=min(old.source_expires_at,prior_settings.allocation.original_expires_at,*(j.expires_at for j in jobs))
    def store(name,record):
        raw=canonical_bytes(record.model_dump(mode='json'));path=root/name
        path.write_bytes(raw);path.chmod(0o600)
        return str(path),hashlib.sha256(raw).hexdigest()
    registry=PurposeWorkerRegistryV2(workspace_id=old.workspace_id,actor_id=old.actor_id,worker_uri=old.worker_uri,
        runtime_hash=old.runtime_hash,issuer_actor=old.worker_issuer_actor,reviewer_actor=old.worker_reviewer_actor,
        valid_from=now,expires_at=end,jobs=jobs)
    registry_file,registry_hash=store('jobs.json',registry)
    appointment=CompilerPhaseCustodyAppointmentV2(workspace_id=old.workspace_id,actor_id=old.actor_id,
        compiler_login=old.expected_session_role,runtime_hash=old.runtime_hash,
        population_digest=prior_settings.population.population_digest,issuer_actor=old.custody_issuer_actor,
        reviewer_actor=old.custody_reviewer_actor,valid_from=now,expires_at=end,files=custody_files)
    custody_file,custody_hash=store('custody.json',appointment)
    binding=x['client'].binding
    client=dict(hostname=binding.hostname,port=binding.port,server_uri=binding.server_uri,client_uri=binding.client_uri,
        ca_file=str(binding.ca_file),certificate_file=str(binding.certificate_file),key_file=str(binding.key_file))
    assert client['client_uri']==old.worker_uri
    config=old.model_copy(update=dict(jobs_registry_file=registry_file,jobs_registry_sha256=registry_hash,
        custody_appointment_file=custody_file,custody_appointment_sha256=custody_hash,
        clients={j.phase:client for j in jobs if j.phase!='compile'}))
    # Revalidate strict type instead of granting authority via model_copy alone.
    config=CompilerWorkerConfigV2.model_validate(config.model_dump(mode='python'))
    config_file,config_hash=store('worker.json',config)
    return load_purpose_worker_settings_v2(config_file,config_hash),jobs


def test_actual_provider_rpc_can_exceed_five_seconds_without_renewing_horizon(compiler_worker):
    import time
    x,settings,job=compiler_worker
    assert settings.clients['census'].binding.timeout==90.0
    original=job.original_horizon
    x['state']['after_post']=lambda:time.sleep(5.2)
    PurposeJourneyCustodyV2(settings).admit(job.job_id)
    row=run_purpose_worker_once_v2(settings)
    assert row['state']=='awaiting-external-phase-admission' and x['state']['posts']==1
    assert row['original_horizon']==original.isoformat() and job.original_horizon==original
    for field,value in (('observer_timeout_seconds',5.01),('provider_rpc_timeout_seconds',90.01),
                        ('observer_timeout_seconds',float('inf')),('provider_rpc_timeout_seconds',True)):
        with pytest.raises(ValueError):
            CompilerWorkerConfigV2.model_validate({**settings.config.model_dump(mode='python'),field:value})


def test_actual_worker_short_original_job_deadline_wins_over_long_provider_rpc(admin_url,native_census_startup,tmp_path):
    import time
    x=native_census_startup;x['worker_job_seconds']=4
    settings,jobs=make_initial_compiler_worker_v2(admin_url,x,tmp_path/'short-worker');job=jobs[0]
    original=job.original_horizon
    x['state']['after_post']=lambda:time.sleep(5.5)
    custody=PurposeJourneyCustodyV2(settings);custody.admit(job.job_id)
    with pytest.raises((PermissionError,TimeoutError,OSError)):
        run_purpose_worker_once_v2(settings)
    assert datetime.now(timezone.utc)>=job.expires_at and job.original_horizon==original
    assert x['state']['posts']==1
    assert custody.journal.read(job.journey_id)[0]['state']=='attempt-started'
    assert not list(Path(settings.config.spool).glob('*.pending'))


def test_foreign_observer_subject_denied_before_compiler_credentials_or_phase_bytes(compiler_worker):
    from unittest.mock import patch
    from oracle_brain.hosting import provider_runtime as worker
    x,settings,job=compiler_worker
    config=settings.config
    raw=json.loads(Path(config.parent_observer_admission_file).read_bytes())
    raw['principal_id']=str(uuid4())
    path=Path(config.jobs_registry_file).parent/'foreign-observer.json'
    data=canonical_bytes(raw);path.write_bytes(data);path.chmod(0o600)
    changed=config.model_copy(update={'parent_observer_admission_file':str(path),
        'parent_observer_admission_hash':hashlib.sha256(data).hexdigest()})
    cfg=path.parent/'foreign-worker.json';data=canonical_bytes(changed.model_dump(mode='json'))
    cfg.write_bytes(data);cfg.chmod(0o600)
    with patch.object(worker,'tls_url',wraps=worker.tls_url) as credential_read:
        with pytest.raises(Exception,match='actual compiler parent observation appointment differs'):
            load_purpose_worker_settings_v2(str(cfg),hashlib.sha256(data).hexdigest())
        credential_read.assert_not_called()
    assert x['state']['posts']==0

@pytest.mark.parametrize('native_census_startup',['extraction'],indirect=True)
def test_historical_extractor_population_is_separate_but_exact_original_journey(compiler_worker):
    from oracle_brain.hosting.purpose_journey_v2 import _historical_extraction_population_v2
    x,settings,job=compiler_worker
    original=x['settings'].population;q=x['qualification']
    def check(population,qualification=None):
        raw=canonical_bytes(population.model_dump(mode='json'));sha=hashlib.sha256(raw).hexdigest()
        qualification=(qualification or q).model_copy(update={'population_admission_sha256':sha})
        entry=CompilerPhaseCustodyFileV2(kind='extraction_population',path=str(Path(x['context_file']).parent/'metadata-only'),sha256=sha)
        return _historical_extraction_population_v2(settings,job,qualification,raw,entry)
    assert check(original)==original
    # Pure relation proof: historical producer runtime is allowed to differ,
    # but must equal its separately externally appointed qualification runtime.
    distinct=original.model_copy(update={'runtime_hash':'a'*64})
    assert check(distinct,q.model_copy(update={'runtime_hash':'a'*64}))==distinct
    for changed in (original.model_copy(update={'parent_registry_sha256':'b'*64}),
                    original.model_copy(update={'source_refs':original.source_refs[:-1],
                        'population_digest':digest({'source_refs':[r.model_dump(mode='json') for r in original.source_refs[:-1]]})}),
                    distinct):
        with pytest.raises(Exception):check(changed)
    assert x['state']['posts']==0


def test_worker_startup_requires_external_hash_before_any_file_read():
    from unittest.mock import patch
    from oracle_brain.hosting import purpose_journey_v2 as worker
    for value in (None,'','placeholder',True):
        with patch.object(worker,'_worker_file',wraps=worker._worker_file) as private_read:
            with pytest.raises(Exception,match='explicit externally pinned worker'):
                load_purpose_worker_settings_v2('/absent',value)
            private_read.assert_not_called()


@pytest.mark.parametrize('revoke_after_validation',[False,True])
def test_actual_compiler_final_current_proof_follows_controlled_slow_validation(
        admin_url,compiler_worker,monkeypatch,revoke_after_validation):
    """Real SQL/observer scope, controlled validator timing; no model acceptance."""
    import time
    from types import SimpleNamespace
    x,settings,job=compiler_worker
    ledger=build_purpose_compiler_ledger_v3(settings,job)
    guard=ledger.processing_read_guard
    began=datetime.now(timezone.utc)
    def controlled_validation(*args):
        # Exceed the genuine fixture parent's <=5s observation horizon. This
        # is test timing only, never an operational expiry/clock mutation.
        time.sleep(5.05)
        if revoke_after_validation:
            with psycopg.connect(admin_url) as conn:
                conn.execute('DELETE FROM oracle2.hosting_role_source_admissions WHERE role_name=%s AND source_id=%s',
                    (settings.config.expected_session_role,job.source_refs[2].source_id))
        return job.original_horizon
    monkeypatch.setattr(guard.qualified,'valid_until',controlled_validation)
    # Controlled summary semantics need no invented qualified admission.
    # Actual full qualified-model paths still require authorize_semantic.
    manifest=SimpleNamespace(kind='processing_summary_v1')
    if revoke_after_validation:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            guard.valid_until(manifest,{},job.actor_id,began)
    else:
        until=guard.valid_until(manifest,{},job.actor_id,began)
        assert datetime.now(timezone.utc)<until<=job.expires_at
        assert datetime.now(timezone.utc)-began>timedelta(seconds=5)
    assert x['state']['posts']==0
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s',
            (job.workspace_id,)).fetchone()[0]==0


def test_actual_compiler_v3_window_separates_freshness_and_original_operation(
        admin_url,compiler_worker):
    """Actual roles/observer, no graph/provider or semantic-quality claim."""
    import time
    x,settings,job=compiler_worker
    first=settings.custody_window_v3(job)
    assert datetime.now(timezone.utc)<first.current_until<first.operation_horizon<=job.expires_at
    with psycopg.connect(admin_url) as conn:
        conn.execute("UPDATE oracle2.hosting_role_source_admissions SET expires_at=LEAST(expires_at,clock_timestamp()+interval '30 seconds') WHERE role_name=%s",
            (settings.config.expected_session_role,))
    time.sleep(5.05)
    assert first.current_until<datetime.now(timezone.utc)
    fresh=settings.custody_window_v3(job)
    assert datetime.now(timezone.utc)<fresh.current_until<fresh.operation_horizon<first.operation_horizon
    assert fresh.operation_horizon<=datetime.now(timezone.utc)+timedelta(seconds=30)
    with psycopg.connect(admin_url) as conn:
        conn.execute('DELETE FROM oracle2.hosting_role_source_admissions WHERE role_name=%s AND source_id=%s',
            (settings.config.expected_session_role,job.source_refs[2].source_id))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):settings.custody_window_v3(job)
    assert x['state']['posts']==0


@pytest.mark.parametrize('revoke_after_validation',[False,True])
def test_qualified_read_boundary_consolidates_observer_but_keeps_actual_source_sql(
        admin_url,compiler_worker,monkeypatch,revoke_after_validation):
    """Controlled semantic work, actual compiler SQL/custody/mTLS; no model-quality claim."""
    import time
    from types import SimpleNamespace
    from oracle_brain.hosting.purpose_journey_v2 import build_purpose_qualified_reader_v3
    x,settings,job=compiler_worker
    ledger=build_purpose_qualified_reader_v3(settings,job);guard=ledger.processing_read_guard
    assert ledger.processing_compile_guard.ledger is not ledger
    assert ledger.processing_compile_guard.ledger.processing_read_guard is ledger.processing_compile_guard
    assert ledger.processing_compile_guard.ledger.processing_extraction_guard is ledger.processing_extraction_guard
    assert guard.ledger is ledger
    original=x['state']['sequence']
    for ref in job.source_refs:guard.source(ref.workspace_id,job.actor_id,ref.source_id)
    assert guard.trust()==frozenset()  # This fixture has no semantic admission.
    assert x['state']['sequence']==original  # Metadata SQL and registry, no parent network.
    def controlled_validation(*args):
        for ref in job.source_refs:guard.source(ref.workspace_id,job.actor_id,ref.source_id)
        guard.trust()
        if revoke_after_validation:
            with psycopg.connect(admin_url) as conn:
                conn.execute('DELETE FROM oracle2.hosting_role_source_admissions WHERE role_name=%s AND source_id=%s',
                    (settings.config.expected_session_role,job.source_refs[2].source_id))
        else:time.sleep(5.05)
        return job.original_horizon
    monkeypatch.setattr(guard.qualified,'valid_until',controlled_validation)
    # Mock only expensive pure summary semantics; no private artifact is seeded.
    manifest=SimpleNamespace(kind='processing_summary_v1',workspace_id=job.workspace_id)
    if revoke_after_validation:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            guard.valid_until(manifest,{},job.actor_id,datetime.now(timezone.utc))
        assert x['state']['sequence']==original+1
    else:
        until=guard.valid_until(manifest,{},job.actor_id,datetime.now(timezone.utc))
        assert datetime.now(timezone.utc)<until<=job.original_horizon
        assert x['state']['sequence']==original+2  # Real BEFORE and NEW fresh LAST.
    assert x['state']['posts']==0
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s',(job.workspace_id,)).fetchone()[0]==0

@pytest.mark.parametrize('kind',['processing_extraction_v1','processing_failed_extraction_v1','processing_qualified_model_v1','processing_summary_v1'])
def test_full_validation_fused_boundary_calls_once(kind,monkeypatch):
    """Dispatch/count proof only; injected method is not runtime authority."""
    from types import SimpleNamespace
    from oracle_brain.hosting.purpose_journey_v2 import (
        PurposeProcessingCompilerLedgerV3,_PurposeCompilerReadGuardV3,ProcessingCompilerExtractionGuardV2)
    now=datetime.now(timezone.utc);until=now+timedelta(seconds=20);calls=[]
    ledger=object.__new__(PurposeProcessingCompilerLedgerV3)
    ledger.principal=uuid4();ledger.clock=lambda:now
    extraction=object.__new__(ProcessingCompilerExtractionGuardV2)
    combined=object.__new__(_PurposeCompilerReadGuardV3)
    ledger.processing_extraction_guard=extraction;ledger.processing_read_guard=combined
    def counted(self,*args):calls.append(type(self));return until
    monkeypatch.setattr(ProcessingCompilerExtractionGuardV2,'validate_current',counted)
    monkeypatch.setattr(_PurposeCompilerReadGuardV3,'validate_current',counted)
    manifest=SimpleNamespace(kind=kind)
    ledger._validate_processing_read_guard(manifest,{},now)
    ledger._validate_processing_extraction_after_read(manifest,{},now)
    assert calls==[ProcessingCompilerExtractionGuardV2 if 'extraction' in kind else _PurposeCompilerReadGuardV3]

@pytest.mark.parametrize('bad',['naive','expired','object'])
def test_fused_full_validation_refuses_invalid_guard_or_deadline(bad,monkeypatch):
    from types import SimpleNamespace
    from oracle_brain.hosting.purpose_journey_v2 import PurposeProcessingCompilerLedgerV3,ProcessingCompilerExtractionGuardV2
    now=datetime.now(timezone.utc)
    ledger=object.__new__(PurposeProcessingCompilerLedgerV3);ledger.principal=uuid4();ledger.clock=lambda:now
    guard=object.__new__(ProcessingCompilerExtractionGuardV2)
    deadline=now.replace(tzinfo=None) if bad=='naive' else now
    monkeypatch.setattr(ProcessingCompilerExtractionGuardV2,'validate_current',lambda *args:deadline)
    if bad=='object':guard=object()  # Missing pure protocol, never a runtime appointment.
    with pytest.raises(PermissionError):ledger._validate_processing_guard(guard,SimpleNamespace(),{},now)
