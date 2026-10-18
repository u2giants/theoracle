"""Explicit post-paid-output custody metadata for the single native fixture."""
import hashlib,json
from contextlib import contextmanager
from pathlib import Path
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.paid_sdk_embeddings_v3 import PaidSDKEmbeddingPinsV3
from oracle_brain.operating_model.purpose_receipts_v2 import PhaseResponseCommitV2
from oracle_brain.hosting.purpose_journey_v2 import CompilerPhaseCustodyFileV2,CompilerPhaseCustodyAppointmentV2
from test_purpose_worker_startup import make_next_compiler_worker_v2


def fixture_observer_identity(source_binding,observer_state_path,*,expected_principal,expected_runtime,expected_login,expected_profile):
    """Record actual immutable SQL binding pins, never provider body/config IDs."""
    from oracle_brain.operating_model.authority_adapter import ProcessingSourceBinding
    if type(source_binding) is not ProcessingSourceBinding:
        raise AssertionError('actual immutable source binding required for fixture identity')
    if (source_binding.principal,source_binding.runtime_hash,source_binding.expected_session_role,source_binding.profile)!=(
            expected_principal,expected_runtime,expected_login,expected_profile):
        raise AssertionError('foreign fixture source binding differs from actual protected descriptor')
    return dict(principal=str(source_binding.principal),runtime=source_binding.runtime_hash,
        login=source_binding.expected_session_role,observer_path=str(Path(observer_state_path).resolve()))


def run_independent_fixture_tasks(tasks,*,deadline,identities,record):
    """TEST ONLY bounded two-lane DAG; no grant/proof/result is cached here."""
    import concurrent.futures,time
    from datetime import datetime,timezone
    if len(tasks)!=2 or set(tasks)!=set(identities):raise AssertionError('two exact independent fixture lanes required')
    if not isinstance(deadline,datetime) or deadline.tzinfo is None or deadline.utcoffset() is None:
        raise AssertionError('aware original fixture horizon required')
    if deadline<=datetime.now(timezone.utc):raise TimeoutError('original fixture horizon elapsed')
    values=list(identities.values())
    for key in ('principal','runtime','login'):
        if not values[0][key] or values[0][key]==values[1][key]:raise AssertionError('fixture identity collision')
    paths=[v.get('observer_path') for v in values if v.get('observer_path') is not None]
    if len(set(paths))!=len(paths):raise AssertionError('shared observer state cannot run concurrently')
    return _observe_fixture_tasks(tasks,deadline=deadline,identities=identities,record=record)


def _observe_fixture_tasks(tasks,*,deadline,identities,record):
    import concurrent.futures,time
    from datetime import datetime,timezone
    intervals={};results={};errors=[]
    def run(name,task):
        intervals[name]={'started':time.monotonic()}
        try:return task()
        finally:intervals[name]['finished']=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures={name:pool.submit(run,name,task) for name,task in tasks.items()}
        for name,future in futures.items():
            try:
                remaining=(deadline-datetime.now(timezone.utc)).total_seconds()
                if remaining<=0:raise TimeoutError('original fixture horizon elapsed')
                results[name]=future.result(timeout=remaining)
            except BaseException as error:errors.append(error)
        # A timeout/cancel is not stop proof. Observe every actual task before
        # caller may close graph/credentials or dispatch any successor.
        for name,future in futures.items():
            try:results[name]=future.result()
            except BaseException as error:
                if error not in errors:errors.append(error)
    record.write_text(json.dumps({'intervals':intervals,'identities':identities,'deadline':deadline.isoformat(),
        'all_tasks_observed':True,'errors':[type(e).__name__ for e in errors]},sort_keys=True));record.chmod(0o600)
    if errors:raise errors[0]
    if datetime.now(timezone.utc)>=deadline:raise TimeoutError('original fixture horizon elapsed')
    return results

def _assert_readonly_delivery_resources(identities):
    if set(identities)!={'compiler_restart','executor_answer','result_rpc'}:
        raise AssertionError('three closed readonly delivery lanes required')
    compiler,direct,result=(identities[k] for k in ('compiler_restart','executor_answer','result_rpc'))
    if compiler['profile']!='candidate-compiler' or direct['profile']!='documentary-executor' or result['profile']!='documentary-executor':
        raise AssertionError('actual closed delivery profiles required')
    for key in ('principal','runtime','login'):
        if not compiler[key] or not direct[key] or compiler[key]==direct[key] or direct[key]!=result[key]:
            raise AssertionError('actual compiler and same-human executor identity required')
    if not compiler['observer_path'] or direct['observer_path'] is not None or result['observer_path'] is not None:
        raise AssertionError('only compiler observer may execute in delivery lanes')
    for key in ('config_sha256','appointment_sha256','config_path','appointment_path'):
        if not direct[key] or direct[key]!=result[key]:raise AssertionError('same immutable executor appointment required')
    for key in ('settings_object','resolver_object','ledger_object','guard_object','semantic_object','blobs_object'):
        if not direct[key] or direct[key]==result[key]:raise AssertionError('shared executor mutable object refused')


def run_readonly_delivery_fixture_tasks(tasks,*,deadline,compiler,direct,result,record):
    from oracle_brain.hosting.purpose_journey_v2 import CompilerWorkerSettingsV2
    from oracle_brain.hosting.paid_executor_v3 import PaidExecutorSettingsV3
    from oracle_brain.hosting.replacement_result_settings_v1 import ProtectedReplacementResultSettingsV1
    from datetime import datetime,timezone
    if (type(compiler) is not CompilerWorkerSettingsV2 or type(direct) is not PaidExecutorSettingsV3
            or type(result) is not ProtectedReplacementResultSettingsV1 or type(result.executor) is not PaidExecutorSettingsV3):
        raise AssertionError('exact actual protected delivery settings required')
    if set(tasks)!={'compiler_restart','executor_answer','result_rpc'}:
        raise AssertionError('three closed readonly delivery tasks required')
    if not isinstance(deadline,datetime) or deadline.tzinfo is None or deadline.utcoffset() is None:
        raise AssertionError('aware original fixture horizon required')
    if deadline<=datetime.now(timezone.utc):raise TimeoutError('original fixture horizon elapsed')
    def executor_identity(settings):
        c=settings.config
        if getattr(settings,'observer',None) is not None:raise AssertionError('executor must have no observer')
        return dict(principal=str(c.actor_id),runtime=c.runtime_hash,login=c.expected_session_role,
            profile=settings.resolver.binding.profile,observer_path=None,config_sha256=settings.config_sha256,
            appointment_sha256=settings.appointment_sha256,config_path=str(settings.config_path.resolve()),
            appointment_path=str(settings.appointment_path.resolve()),settings_object=id(settings),
            resolver_object=id(settings.resolver),ledger_object=id(settings.ledger),guard_object=id(settings.guard),
            semantic_object=id(settings.semantic),blobs_object=id(settings.ledger.blobs))
    c=compiler.config
    identities=dict(compiler_restart=dict(principal=str(c.actor_id),runtime=c.runtime_hash,
        login=c.expected_session_role,profile=compiler.resolver.binding.profile,
        observer_path=str(compiler.observer.replay.state_path.resolve())),
        executor_answer=executor_identity(direct),result_rpc=executor_identity(result.executor))
    _assert_readonly_delivery_resources(identities)
    return _observe_fixture_tasks(tasks,deadline=deadline,identities=identities,record=record)



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
            def _ack_profile(name):
                if os.environ.get('ORACLE2_TEST_ACK_PROFILE')!='1':
                    return None
                import cProfile
                prof=cProfile.Profile();prof.enable()
                return (prof,name)
            def _ack_profile_end(token):
                if token is None:return
                import cProfile,pstats,io
                prof,name=token;prof.disable()
                buf=io.StringIO();pstats.Stats(prof,stream=buf).strip_dirs().sort_stats('cumulative').print_stats(40)
                (root/('ack-profile-'+name+'.txt')).write_text(buf.getvalue())
                prof.dump_stats(str(root/('ack-profile-'+name+'.pstats')))
            async def deliver():
                token=_ack_profile('project')
                try:
                    signed=await project_paid_projector_event_v3(settings,lease)
                finally:
                    _ack_profile_end(token)
                assert signed['schema_version']==3 and signed['embedding_protocol']=='paid-sdk-embedding-v3'
                stage('protected_graph_ack_committed')
                return signed
            signed=asyncio.run(deliver())
            def restart():
                # Independent readonly reconstruction AFTER the actual ACK.
                async def verify():
                    token=_ack_profile('reload')
                    try:
                        fresh=reload_paid_projector_projection_v3(settings)
                        try:
                            loaded=await fresh.load(settings.bundle.ledger,job.workspace_id,artifact.artifact_id,artifact.version)
                            assert loaded['qualified_lineage']['schema_version']==3
                        finally:await fresh.close()
                    finally:
                        _ack_profile_end(token)
                asyncio.run(verify())
                stage('fresh_compiler_restart_verified')
            yield dict(signed=signed,settings=settings,container=container,admin_url=admin,generation=generation,restart=restart)
            writer.confirm_inactive()  # All timely awaited calls/pools closed.
