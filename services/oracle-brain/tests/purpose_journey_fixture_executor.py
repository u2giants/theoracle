"""Owned fixture-only executor role and sanitized immutable byte materialization.

No compiler credential, original, extraction, paid wire or signing key is given
to the executor. This is not a deployed artifact distribution mechanism.
"""
import hashlib,json,os,subprocess
from dataclasses import replace
from pathlib import Path,PurePosixPath
from uuid import uuid4

import psycopg
from psycopg import sql

from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.authority_adapter import ProcessingSourceBinding,ProcessingArtifactResolver
from oracle_brain.hosting.custody import _durable_nonce,_sync_spool
from purpose_journey_fixture_models import PRIVATE_MARKERS

EXECUTOR_URI='spiffe://oracle/purpose/invented-executor'


def executor_role(admin_url,worker,job,root):
    """Only a new local invented executor login and rooted source-read grants."""
    actor=uuid4();login='coherent_exec_'+uuid4().hex[:12]
    runtime=digest({'executor':login,'journey':str(job.journey_id)})
    until=min(job.original_horizon,job.expires_at,worker.population.expires_at,worker.config.source_expires_at)
    with psycopg.connect(admin_url) as conn:
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(
            sql.Identifier(login),sql.Literal('invented-executor-only')))
        conn.execute(sql.SQL('GRANT oracle2_documentary_executor TO {}').format(sql.Identifier(login)))
        conn.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',
            (login,runtime,worker.config.source_registry_hash,until))
        for ref in job.source_refs:
            parents=conn.execute("SELECT appointment_id,actor_id FROM oracle2.appointments WHERE workspace_id=%s AND scope='root' AND revoked_at IS NULL",
                (ref.workspace_id,)).fetchall()
            assert len(parents)==1
            parent,owner=parents[0]
            conn.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                (uuid4(),ref.workspace_id,actor,'source-read:'+str(ref.source_id),owner,parent,until))
            conn.execute('INSERT INTO oracle2.hosting_role_source_admissions VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (login,ref.workspace_id,ref.source_id,ref.revision,actor,ref.original_sha256,ref.reading_sha256,ref.parser_id,runtime,worker.config.source_registry_hash,until))
    url=psycopg.conninfo.make_conninfo(admin_url,user=login,password='invented-executor-only')
    binding=ProcessingSourceBinding(runtime_hash=runtime,source_registry_hash=worker.config.source_registry_hash,
        expected_owner_role=worker.config.expected_owner_role,expected_session_role=login,principal=actor,
        profile='documentary-executor',expires_at=until,synthetic=False)
    path=root/'executor-database-url';_durable_nonce(root,path.name,url.encode())
    return path,binding,ProcessingArtifactResolver(url,binding=binding)


def materialize_sanitized_only(compiler,executor,job,manifests,root):
    """Current own-role authorization before/after exact bounded replica writes."""
    root.mkdir(mode=0o700);expected=[]
    for original in manifests:
        assert original.kind in {'processing_qualified_model_v1','processing_summary_v1'}
        before,refs=executor.artifact_metadata(job.workspace_id,original.artifact_id,original.version)
        assert before==original and set(refs)==set(job.source_refs)
        manifest,payload=compiler.read_with_manifest(job.workspace_id,original.artifact_id,original.version)
        assert manifest==original
        raw=canonical_bytes(payload)
        assert len(raw)<=20*1024*1024 and hashlib.sha256(raw).hexdigest()==manifest.content_hash
        assert all(marker.encode() not in raw for marker in PRIVATE_MARKERS)
        key=PurePosixPath(manifest.private_object_key)
        assert not key.is_absolute() and '..' not in key.parts and len(key.parts)>=2
        parent=root
        for part in key.parts[:-1]:
            parent=parent/part
            if not parent.exists():parent.mkdir(mode=0o700)
            assert not parent.is_symlink() and parent.stat().st_mode&0o077==0
        _durable_nonce(parent,key.name,raw)
        with os.fdopen(os.open(parent/key.name,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream:
            actual=stream.read(20*1024*1024+1)
        assert actual==raw and hashlib.sha256(actual).hexdigest()==manifest.content_hash
        _sync_spool(parent);expected.append(str(key))
        assert compiler.read_with_manifest(job.workspace_id,manifest.artifact_id,manifest.version)==(manifest,payload)
        after,current=executor.artifact_metadata(job.workspace_id,manifest.artifact_id,manifest.version)
        assert after==before and set(current)==set(refs)
    assert sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file())==sorted(expected)


def executor_certificate(certificates,root):
    """Explicit synthetic executor URI under the existing owned fixture CA."""
    key=root/'executor.key';csr=root/'executor.csr';certificate=root/'executor.pem';ext=root/'executor.ext'
    ext.write_text('subjectAltName=URI:'+EXECUTOR_URI+'\nextendedKeyUsage=clientAuth\nbasicConstraints=critical,CA:FALSE\n');ext.chmod(0o600)
    def run(*args):subprocess.run(['openssl',*args],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
    run('req','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(csr),'-subj','/CN=owned-executor')
    run('x509','-req','-in',str(csr),'-CA',str(certificates/'ca.pem'),'-CAkey',str(certificates/'ca.key'),
        '-CAcreateserial','-out',str(certificate),'-days','1','-extfile',str(ext))
    for path in (key,csr,certificate):path.chmod(0o600)
    return certificate,key


def prepare_executor_inputs(*,admin_url,worker,job,compiler,qualified_manifest,summary_manifest,root,certificates):
    """All compiler-observer replica work is serial before graph projection."""
    root.mkdir(mode=0o700)
    db_file,binding,resolver=executor_role(admin_url,worker,job,root)
    replica=root/'sanitized-blobs'
    materialize_sanitized_only(compiler,resolver,job,(qualified_manifest,summary_manifest),replica)
    certificate,key=executor_certificate(certificates,root)
    return dict(root=root,db_file=db_file,binding=binding,resolver=resolver,replica=replica,
        certificate=certificate,key=key,qualified_manifest=qualified_manifest,summary_manifest=summary_manifest)


def verify_protected_executor(delivery,*,admin_url,worker,job,summary_manifest,extraction_ids,
        root,tls,certificates,stage,after_positive,prepared=None):
    """The real own-role loader, ACK metadata, readonly TLS graph and answer."""
    import asyncio,pytest
    from urllib.parse import urlsplit,urlunsplit
    from dev.oracle2.test_readonly_graph_fixture import processing_reader_scope
    from dev.oracle2.test_graph_tls_fixture import owned_graph_tls
    from test_paid_executor_v3 import make_paid_executor_fixture_settings_v3
    from test_purpose_transport import SERVER
    from oracle_brain.hosting.paid_executor_v3 import ExecutorSummaryTargetV3,build_paid_executor_projection_v3
    from oracle_brain.operating_model.summaries import serve_summary
    from oracle_brain.operating_model.answer import answer_from_summary
    projector=delivery['settings'];manifest=projector.bundle.manifest;payload=projector.bundle.payload
    if prepared is None:
        prepared=prepare_executor_inputs(admin_url=admin_url,worker=worker,job=job,compiler=projector.bundle.ledger,
            qualified_manifest=manifest,summary_manifest=summary_manifest,root=root,certificates=certificates)
    assert prepared['root']==root and prepared['qualified_manifest']==manifest and prepared['summary_manifest']==summary_manifest
    db_file,binding,resolver,replica,certificate,key=(prepared[k] for k in ('db_file','binding','resolver','replica','certificate','key'))
    def actual_delivery(event):
        actual=worker.resolver.projection_receipt_v3(job.workspace_id,manifest.artifact_id,manifest.version)
        assert actual.receipt.event_id==str(event)
        return actual.receipt.model_dump(mode='json')|{'signature':actual.signature}
    with processing_reader_scope(delivery['container'],delivery['admin_url'],root/'readonly-acl',
            receipt=delivery['signed'],secret=projector.receipt_secret,current_delivery=actual_delivery) as readonly:
        with owned_graph_tls(delivery['container'],delivery['admin_url'],server_context=tls,expected_client_uri=EXECUTOR_URI) as port:
            parsed=urlsplit(readonly['ORACLE2_TEST_PROCESSING_READONLY_GRAPH_URL'])
            graph_url=urlunsplit(('rediss',parsed.netloc.rsplit('@',1)[0]+'@localhost:'+str(port),'','',''))
            graph_file=root/'executor-graph-url';_durable_nonce(root,graph_file.name,graph_url.encode())
            seal=resolver.projection_delivery_seal(job.workspace_id,manifest.artifact_id,manifest.version)
            summary_target=ExecutorSummaryTargetV3(artifact_id=summary_manifest.artifact_id,artifact_version=summary_manifest.version,
                content_hash=summary_manifest.content_hash,qualified_parent_id=manifest.artifact_id,
                qualified_parent_version=manifest.version,qualified_parent_content_hash=manifest.content_hash)
            settings=make_paid_executor_fixture_settings_v3(worker,job,root/'settings',executor_binding=binding,
                database_url_file=db_file,database_ca_file=Path(psycopg.conninfo.conninfo_to_dict(db_file.read_text())['sslrootcert']),
                graph_url_file=graph_file,tls_ca_file=certificates/'ca.pem',tls_certificate_file=certificate,tls_key_file=key,
                tls_client_uri=EXECUTOR_URI,tls_server_uri=SERVER,qualified_manifest=manifest,qualified_payload=payload,
                delivery_seal=seal,qualified_blob_root=replica,summary_targets=(summary_target,))
            assert settings.config.actor_id!=worker.config.actor_id
            stage('protected_executor_own_role_started')
            async def load_and_answer():
                projection=build_paid_executor_projection_v3(settings)
                try:
                    loaded=await projection.load(settings.ledger,job.workspace_id,manifest.artifact_id,manifest.version)
                    assert loaded==payload
                    nodes=(await projection.connection.query('MATCH (n) RETURN properties(n)')).result_set
                    relations=(await projection.connection.query('MATCH ()-[r]->() RETURN properties(r)')).result_set
                    assert all(marker not in json.dumps((nodes,relations),ensure_ascii=False) for marker in PRIVATE_MARKERS)
                    settings.read_summary(summary_manifest.artifact_id,summary_manifest.version)
                    summary=serve_summary(settings.ledger,job.workspace_id,summary_manifest.artifact_id,summary_manifest.version,
                        qualification_guard=settings.guard)
                    answer=answer_from_summary(settings.ledger,summary,intent='overview',qualification_guard=settings.guard)
                    assert answer.state=='answered' and answer.citations
                    assert all(marker not in answer.model_dump_json() for marker in PRIVATE_MARKERS)
                    stage('protected_executor_graph_summary_answer_verified')
                    return projection,summary
                finally:await projection.close()
            from purpose_journey_fixture_delivery import run_independent_fixture_tasks
            c=worker.config
            results=run_independent_fixture_tasks({'compiler_restart':delivery['restart'],
                'executor_answer':lambda:asyncio.run(load_and_answer())},
                deadline=min(job.original_horizon,job.expires_at,settings.config.expires_at),
                identities={'compiler_restart':dict(principal=str(c.actor_id),runtime=c.runtime_hash,
                    login=c.expected_session_role,observer_path=str(worker.observer.replay.state_path.resolve())),
                    'executor_answer':dict(principal=str(settings.config.actor_id),runtime=settings.config.runtime_hash,
                    login=settings.config.expected_session_role,observer_path=None)},record=root/'restart-executor-overlap.json')
            projection,summary=results['executor_answer']
            stage('protected_graph_ack_and_compiler_restart')
            # Both independent positive futures and their connection pools are
            # now joined/closed. Cached objects must still deny source changes.
            async def negatives():
                # Negative assertions follow the complete positive path.
                # This fixture-admin callback grants no runtime authority.
                after_positive()
                denied=(PermissionError,psycopg.errors.InsufficientPrivilege)
                with pytest.raises(denied):settings.resolver.current_for_processing(job.workspace_id,job.source_refs[0].source_id)
                original_read=settings.ledger.blobs.read
                def no_raw_blob(*args):raise AssertionError('executor attempted an extraction blob')
                settings.ledger.blobs.read=no_raw_blob
                try:
                    for artifact,version in extraction_ids:
                        with pytest.raises(denied):settings.ledger.read_with_manifest(job.workspace_id,artifact,version)
                finally:settings.ledger.blobs.read=original_read
                # Current source withdrawal defeats retained model/summary
                # and graph objects; no cached answer becomes authority.
                with psycopg.connect(admin_url) as conn:
                    conn.execute("UPDATE oracle2.drafts SET status='withdrawn' WHERE source_id=%s AND workspace_id=%s",
                        (job.source_refs[-1].source_id,job.workspace_id))
                with pytest.raises(psycopg.errors.InsufficientPrivilege):settings.read_summary(summary_manifest.artifact_id,summary_manifest.version)
                with pytest.raises(psycopg.errors.InsufficientPrivilege):await projection.load(settings.ledger,job.workspace_id,manifest.artifact_id,manifest.version)
                with pytest.raises(psycopg.errors.InsufficientPrivilege):answer_from_summary(settings.ledger,summary,intent='overview',qualification_guard=settings.guard)
                stage('withdrawal_denies_cached_graph_summary_and_answer')
            asyncio.run(negatives())
