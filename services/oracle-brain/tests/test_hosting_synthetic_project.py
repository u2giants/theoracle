"""Real public-only projector proof under registered TLS/SCRAM source authority."""
import asyncio, base64, hashlib, hmac, os, secrets
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict,make_conninfo
import pytest
from redis import Redis
from oracle_brain.hosting import synthetic_fixture,synthetic_project
from oracle_brain.hosting.synthetic_seed import compile_seed
from oracle_brain.operating_model.authority_adapter import PostgresSources
from oracle_brain.operating_model.source_binding import SourceRoleBinding


def verifier(password):
    salt=secrets.token_bytes(16)
    salted=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,4096)
    client=hmac.digest(salted,b'Client Key','sha256')
    enc=lambda x:base64.b64encode(x).decode()
    return 'SCRAM-SHA-256$4096:'+enc(salt)+'$'+enc(hashlib.sha256(client).digest())+':'+enc(hmac.digest(salted,b'Server Key','sha256'))


@pytest.mark.parametrize('scenario_id',[synthetic_fixture.LEGACY_SCENARIO,synthetic_fixture.FORWARD_SCENARIO])
def test_registered_public_projector_preserves_release(tmp_path,monkeypatch,scenario_id):
    admin=os.environ.get('ORACLE2_TEST_ADMIN_URL')
    graph_admin=os.environ.get('ORACLE2_OPERATING_TEST_GRAPH_URL')
    if not admin or not graph_admin:pytest.fail('actual isolated TLS/SCRAM and native graph fixtures required')
    token=uuid4().hex
    database='oracle_operating_model_test_'+token
    roles={kind:'synthetic_'+kind+'_'+token for kind in ('gateway','executor','projector')}
    password=secrets.token_urlsafe(24)
    generation=uuid4()
    if scenario_id==synthetic_fixture.LEGACY_SCENARIO:
        monkeypatch.setattr(synthetic_fixture,'GENERATION',generation)
        monkeypatch.setattr(synthetic_project,'GENERATION',generation)
    scenario=synthetic_fixture.fixed_scenario(scenario_id)
    params={'runtime_hash':'a'*64,'source_role_registry_hash':'b'*64,'review_hash':'c'*64,'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),**{kind+'_scram':verifier(password) for kind in roles}}
    if scenario_id!=synthetic_fixture.LEGACY_SCENARIO:
        params.update(synthetic_scenario=scenario_id,synthetic_scenario_seal=scenario.seal())
    seed,manifest,payload,release=compile_seed(params)
    for kind,role in roles.items():seed=seed.replace('oracle_synthetic_'+kind,role)
    graph=Redis.from_url(graph_admin,decode_responses=True)
    user='projector_'+token
    executor_user='executor_'+token
    graph_password=secrets.token_hex(32)
    from graphrag_sdk.storage.ontology_store import OntologyStore
    assert OntologyStore.ONTOLOGY_GRAPH_SUFFIX=='__ontology'
    ontology_graph=release.graph_name+OntologyStore.ONTOLOGY_GRAPH_SUFFIX
    assert not graph.exists(release.graph_name) and not graph.exists(ontology_graph)
    assert graph.acl_getuser(user) is None
    with psycopg.connect(admin,autocommit=True) as conn:
        assert conn.pgconn.ssl_in_use
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    dbparams=conninfo_to_dict(admin);dbparams['dbname']=database
    dbadmin=make_conninfo(**dbparams)
    try:
        with psycopg.connect(dbadmin,autocommit=True) as conn:
            for name in ('001_foundation','002_pilot','004_workflow_integrity','006_hosting_gateway_authority','007_hosting_candidate_permissions','008_hosting_runtime_permissions','009_hosting_result_permissions','010_hosting_job_permissions'):
                conn.execute((Path(__file__).parents[1]/'sql'/f'{name}.sql').read_text())
            conn.execute(seed)
        limited=make_conninfo(**{**dbparams,'user':roles['projector'],'password':password})
        with pytest.raises(PermissionError):PostgresSources(limited)
        binding=SourceRoleBinding(params['runtime_hash'],params['source_role_registry_hash'])
        binding.check_url(limited)
        sealed=synthetic_fixture.graph_acl_users(release.graph_name,graph_password,graph_password).splitlines()
        graph.execute_command('ACL','SETUSER',user,'resetkeys','-@all',*sealed[2].split()[2:])
        from urllib.parse import urlsplit,urlunsplit,quote
        parsed=urlsplit(graph_admin)
        restricted=urlunsplit((parsed.scheme,quote(user)+':'+quote(graph_password)+'@'+parsed.hostname+':'+str(parsed.port),parsed.path,parsed.query,''))
        urlfile=tmp_path/'graph-url';urlfile.write_text(restricted);urlfile.chmod(0o600)
        config={'synthetic':True,'runtime_hash':params['runtime_hash'],'source_role_registry_hash':params['source_role_registry_hash'],'allowed_release_hashes':[release.content_hash()],'_database_url':limited,'_source_binding':binding,'blob_root':str(tmp_path/'blobs'),'graph_url_file':str(urlfile)}
        if scenario_id!=synthetic_fixture.LEGACY_SCENARIO:
            config.update(synthetic_scenario=scenario_id,synthetic_scenario_seal=scenario.seal(),synthetic_review_hash=params['review_hash'],worker_uri=scenario.worker_uri)
        receipt=asyncio.run(synthetic_project.project(config,params['review_hash']))
        assert receipt['finalized'] and receipt['source_count']==2 and not receipt['private_admission']
        assert receipt['artifact_hash']==manifest.content_hash==release.artifact_content_hash
        assert receipt['record_digest']==release.graph_record_digest
        native=Redis.from_url(restricted,decode_responses=True)
        from redis.exceptions import NoPermissionError
        with pytest.raises(NoPermissionError):native.execute_command('GRAPH.QUERY',release.graph_name+'_foreign__ontology','MATCH (n) RETURN count(n)')
        native.close()
        graph.execute_command('ACL','SETUSER',executor_user,'resetkeys','-@all',*sealed[1].split()[2:])
        executor_url=restricted.replace(quote(user)+':',quote(executor_user)+':',1)
        reader=Redis.from_url(executor_url,decode_responses=True)
        assert reader.execute_command('GRAPH.RO_QUERY',release.graph_name,'MATCH (n) RETURN count(n)')[1][0][0]>0
        for command,name,query in [('GRAPH.QUERY',release.graph_name,'CREATE (:Forbidden)'),('GRAPH.QUERY',ontology_graph,'CREATE (:Forbidden)'),('GRAPH.RO_QUERY',ontology_graph+'_foreign','MATCH (n) RETURN count(n)'),('GRAPH.RO_QUERY',release.graph_name+'_foreign','MATCH (n) RETURN count(n)')]:
            with pytest.raises(NoPermissionError):reader.execute_command(command,name,query)
        assert reader.execute_command('GRAPH.RO_QUERY',ontology_graph,'MATCH (n:Entity) RETURN count(n)')[1][0][0]>0
        reader.close()
        # Exercise the full documentary path with actual registered NOINHERIT
        # executor credentials, native TLS and the stock read-only graph SDK.
        from oracle_brain.operating_model.artifact_storage import FileBlobStore
        from oracle_brain.operating_model.runtime import run_view,SyntheticEmbedding
        executor_database=make_conninfo(**{**dbparams,'user':roles['executor'],'password':password})
        binding.check_url(executor_database)
        with psycopg.connect(executor_database) as conn:
            assert conn.execute('SELECT rolinherit FROM pg_roles WHERE rolname=SESSION_USER').fetchone()==(False,)
        outcome=asyncio.run(run_view(scenario.run,scenario.workspace,
            database_url=executor_database,graph_url=executor_url,blobs=FileBlobStore(tmp_path/'blobs'),
            embedder=SyntheticEmbedding(),dimensions=8,synthetic=True,source_binding=binding))
        assert outcome=={'state':'completed','run_id':str(scenario.run)}
        with psycopg.connect(executor_database) as conn:
            status,pack=conn.execute('SELECT status,pack FROM oracle2.operating_view_runs WHERE run_id=%s',(scenario.run,)).fetchone()
        assert status=='completed' and pack['artifact_hash']==manifest.content_hash
        assert pack['sdk_candidate_count']>0
        # Warm result reads reuse the completed pack; completion authority is
        # one-use and must not be refreshed by executing the job again.
        with psycopg.connect(executor_database) as conn:
            for _ in range(2):
                assert conn.execute('SELECT pack FROM oracle2.operating_view_runs WHERE run_id=%s',(scenario.run,)).fetchone()[0]==pack
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                from oracle_brain.operating_model.contracts import canonical_bytes
                conn.execute('SELECT oracle2.complete_documentary_view(%s,%s)',(scenario.run,canonical_bytes(pack)))
        # Actual gateway delivery must return the exact completion bytes, never
        # a reconstructed serialization or a renamed legacy job.
        from oracle_brain.operating_model.contracts import canonical_bytes
        expected_bytes=canonical_bytes(pack)
        gateway_database=make_conninfo(**{**dbparams,'user':roles['gateway'],'password':password})
        for _ in range(2):
            with psycopg.connect(gateway_database) as conn:
                delivered_status,delivered=conn.execute('SELECT * FROM oracle2.gateway_view_result(%s,%s,%s)',
                    (scenario.run,params['runtime_hash'],release.documentary_gate_hash)).fetchone()
                assert delivered_status=='completed' and bytes(delivered)==expected_bytes
                assert hashlib.sha256(bytes(delivered)).digest()==hashlib.sha256(expected_bytes).digest()
        if scenario_id!=synthetic_fixture.LEGACY_SCENARIO:
            with psycopg.connect(gateway_database) as conn:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    conn.execute('SELECT * FROM oracle2.gateway_view_result(%s,%s,%s)',
                        (synthetic_fixture.RUN,params['runtime_hash'],release.documentary_gate_hash))
        # An absent persisted ontology must fail closed; no registration writes
        # or guessed in-memory ontology may rescue a damaged generation.
        graph.delete(ontology_graph)
        from redis.exceptions import ResponseError
        with pytest.raises(ResponseError,match='Invalid graph operation on empty key'):
            asyncio.run(run_view(scenario.run,scenario.workspace,
                database_url=executor_database,graph_url=executor_url,blobs=FileBlobStore(tmp_path/'blobs'),
                embedder=SyntheticEmbedding(),dimensions=8,synthetic=True,source_binding=binding))
        assert not graph.exists(ontology_graph)
    finally:
        # Only this test's newly created public graph, user, database and roles.
        graph.delete(release.graph_name,ontology_graph)
        graph.acl_deluser(user,executor_user)
        graph.close()
        with psycopg.connect(admin,autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))
            for role in roles.values():conn.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))
