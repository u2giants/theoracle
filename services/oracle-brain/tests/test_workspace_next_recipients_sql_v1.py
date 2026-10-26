"""Actual Next/two SDK-authenticated invented users, same qualified SQL/SDK owner.

No real Supabase session, employee, company source, provider or business proof.
The 120/115-second fixture is declared before capture; old30/25 defaults stay.
"""
from dataclasses import replace
from pathlib import Path
from datetime import datetime,timezone,timedelta
from uuid import uuid4
import hashlib,json,os,signal,subprocess,threading,time
import psycopg
import pytest
from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationAuthorityV1
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
from test_workspace_workflow_fixture_v1 import sql_qualified_workspace_workflow_v3
from test_connected_answer_sdk_sql_v1 import _exercise_owned_answer_graph_v1
from test_connected_answer_sql_v1 import own_history
from test_connected_answer_service_v1 import install_answer
from test_purpose_transport import bound_tls,certificates
from invented_next_employee_fixture_v1 import invented_next_employee_pair_fixture_v1


def test_actual_next_two_recipients_workspace_and_independent_revocation(admin_url,sql_qualified_workspace_workflow_v3,tmp_path,bound_tls,certificates):
    from dev.oracle2.test_canonical_schema import owned_phase_database
    from dev.oracle2.test_worker_postgres_fixture import owned_worker_database
    container=os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER']
    keys=('ORACLE2_TEST_ADMIN_URL','ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT','ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT_SHA256')
    original={key:os.environ.get(key) for key in keys};database=None
    phase_directory=tmp_path/'phase';phase_directory.mkdir(mode=0o700)
    try:
        with owned_phase_database(admin_url,container,phase_directory) as environment:
            target=environment['ORACLE2_TEST_ADMIN_URL'];database=psycopg.conninfo.conninfo_to_dict(target)['dbname']
            owned_worker_database(container,target)
            os.environ.update({key:environment[key] for key in keys})
            try:
                _exercise_owned_answer_graph_v1(target,sql_qualified_workspace_workflow_v3,tmp_path,bound_tls,certificates,proof_scope='workspace-next-recipients')
            finally:
                owned_worker_database(container,target)
                for key,value in original.items():
                    if value is None:os.environ.pop(key,None)
                    else:os.environ[key]=value
    finally:
        # The existing phase owner drops only its own fresh UUID database.
        for key,value in original.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
        owned_worker_database(container,admin_url)
        if database is not None:
            with psycopg.connect(admin_url) as connection:
                assert connection.execute('SELECT datname FROM pg_database WHERE datname=%s',(database,)).fetchall()==[]
            (tmp_path/'phase-cleanup.json').write_bytes(canonical_bytes(dict(database=database,absent=True,outer_environment_restored=all(os.environ.get(key)==value for key,value in original.items()))))


def exercise_workspace_next_recipients_v1(*,admin_url,state,authority,readonly,generation,settings,certificates,tmp_path):
    """Fixed test-only live seam; baseline server/recipient remain untouched."""
    from oracle_brain.hosting.connected_answer_service_v1 import protected_connected_answer_server_v1
    from dev.oracle2.test_worker_postgres_fixture import owned_worker_database
    f=state['f'];container=os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER']
    owned_worker_database(container,admin_url)
    entries=tuple((uuid4(),uuid4(),is_admin) for is_admin in (False,True))
    employee=invented_next_employee_pair_fixture_v1(admin_url,container=container,entries=entries)
    directory=tmp_path/'two-recipients';directory.mkdir(mode=0o700)
    def protected(name,raw):
        path=directory/name;path.write_bytes(raw);path.chmod(0o600);return path
    def openssl(*args):
        remaining=setup_end-time.monotonic()
        assert remaining>0,'original recipient setup window expired before key operation'
        subprocess.run(['openssl',*map(str,args)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=remaining)
    recipients=[];threads=[];servers=[];histories=[]
    stop=threading.Event();observations=[];errors=[]
    try:
        for index,(auth_user,employee_id,is_admin) in enumerate(entries):
            # One original setup request per independently installed recipient.
            # Capture before its SQL/private-key/config work, exit before browser.
            setup_end=time.monotonic()+30
            setup_deadline=datetime.now(timezone.utc)+timedelta(seconds=29)
            with _request_fence_v1(float(setup_end)):
                h,own=own_history(admin_url,f)
                own=ConsolidationAuthorityV1(h['url'],binding=replace(own.binding,retained_semantic_admissions=state['q']['trusted_admission_hashes']),delivery_capability_body_hashes=own.delivery_capability_body_hashes)
                before=own.projection_delivery_v1(state['manifest'].artifact_id,state['manifest'].version,deadline=setup_deadline)
                assert before.model_content_hash==state['manifest'].content_hash
                histories.append(h)
                uri='spiffe://oracle/invented-workspace-recipient-'+str(index)
                key,csr,cert=(directory/(str(index)+name) for name in ('.key','.csr','.pem'))
                openssl('req','-newkey','rsa:2048','-nodes','-keyout',key,'-out',csr,'-subj','/CN=Invented workspace recipient')
                ext=protected(str(index)+'.ext',('subjectAltName=URI:'+uri+'\nextendedKeyUsage=clientAuth\nbasicConstraints=critical,CA:FALSE\n').encode())
                openssl('x509','-req','-in',csr,'-CA',certificates/'ca.pem','-CAkey',certificates/'ca.key','-CAcreateserial','-out',cert,'-days','1','-extfile',ext)
                key.chmod(0o600);cert.chmod(0o600)
                # Unique graph client key-pair per recipient (same WORKER URI the
                # FalkorDB TLS listener accepts): separate TLS sessions so closing
                # one answer server's pool cannot poison the peer's handshake.
                gkey,gcsr,gcert=(directory/(str(index)+'-graph'+name) for name in ('.key','.csr','.pem'))
                openssl('req','-newkey','rsa:2048','-nodes','-keyout',gkey,'-out',gcsr,'-subj','/CN=Invented workspace graph recipient')
                from test_hosting_boundary import WORKER as _W
                gext=protected(str(index)+'-graph.ext',('subjectAltName=URI:'+_W+'\nextendedKeyUsage=clientAuth\nbasicConstraints=critical,CA:FALSE\n').encode())
                openssl('x509','-req','-in',gcsr,'-CA',certificates/'ca.pem','-CAkey',certificates/'ca.key','-CAcreateserial','-out',gcert,'-days','1','-extfile',gext)
                gkey.chmod(0o600);gcert.chmod(0o600)
                installed=install_answer(state,own,h,readonly,generation,certificates,directory/('answer-'+str(index)),peer_certificate=cert,peer_key=key,peer_uri=uri,server_certificate=Path(settings.peer.server_certificate.path),listen_host='::1',graph_certificate=gcert,graph_key=gkey)
                owned=protected_connected_answer_server_v1(installed)
                thread=threading.Thread(target=owned.serve_forever,kwargs={'poll_interval':.01});thread.start()
                servers.append(owned);threads.append(thread)
                recipients.append(dict(auth_user_id=str(auth_user),employee_id=str(employee_id),is_admin=is_admin,principal_id=str(h['actor']),workspace_id=str(f['workspace']),model_id=str(state['manifest'].artifact_id),runtime_hash=own.binding.runtime_hash,registry_hash=own.binding.registry_hash,answer_config_sha256=installed.config_sha256,answer_peer_sha256=installed.peer_sha256,backend_origin='https://localhost.localdomain:'+str(owned.server_port),client_certificate_file=str(cert),client_key_file=str(key),client_uri=uri,issuer_actor=str(installed.peer.issuer_actor),reviewer_actor=str(installed.peer.reviewer_actor),valid_from=installed.peer.valid_from.isoformat(),expires_at=installed.peer.expires_at.isoformat(),original_horizon=installed.peer.original_horizon.isoformat()))
                after=own.projection_delivery_v1(state['manifest'].artifact_id,state['manifest'].version,deadline=setup_deadline)
                assert after.model_content_hash==state['manifest'].content_hash and time.monotonic()<setup_end
        assert len({h['actor'] for h in histories})==2 and all(h['actor']!=settings.config.principal_id for h in histories)
        proof_end=min(state['ctx'].expires_at,state['q']['admission'].expires_at)
        metadata=dict(proof_valid_until=proof_end.isoformat(),scratch=str(directory),recipients=recipients,web_database_url=employee.web_database_url,server_key_file=settings.peer.server_key.path,server_certificate_file=settings.peer.server_certificate.path,client_ca_file=settings.peer.client_ca.path,workflow_fixture='workspace-artwork-rework-v1',workflow_quote=__import__('test_workspace_workflow_fixture_v1').QUOTE,processes=[dict(process_id=p['process_id'],label=p['label']) for p in state['q']['payload']['consolidation_core']['model']['processes']])
        metadata_path=protected('metadata.json',canonical_bytes(metadata))
        bundle=protected('synthetic-ca-bundle.pem',(certificates/'ca.pem').read_bytes()+Path(employee.database_root_ca).read_bytes())
        def monitor():
            handled=set()
            try:
                while not stop.wait(.05):
                    for marker in ('disable-a','restore-a','revoke-a'):
                        if marker in handled or not (directory/marker).exists():continue
                        owned_worker_database(container,admin_url)
                        with psycopg.connect(admin_url) as connection:
                            assert connection.pgconn.ssl_in_use and connection.execute('SELECT SESSION_USER,current_database()').fetchone()==('oracle2_admin',employee.database)
                            if marker=='disable-a':connection.execute('UPDATE public.employees SET disabled_at=clock_timestamp() WHERE id=%s',(entries[0][1],))
                            elif marker=='restore-a':connection.execute('UPDATE public.employees SET disabled_at=NULL WHERE id=%s',(entries[0][1],))
                            else:connection.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(histories[0]['aid'],))
                        handled.add(marker);protected(marker+'-committed',b'committed')
                    with psycopg.connect(admin_url) as connection:
                        for pid,user,encrypted,query in connection.execute('''SELECT a.pid,a.usename,s.ssl,a.query FROM pg_stat_activity a JOIN pg_stat_ssl s USING(pid) WHERE a.usename=%s AND a.datname=%s''',(employee.login,employee.database)):
                            if 'employee_identities' in query:
                                assert encrypted is True;observations.append(dict(pid=pid,user=user,tls=encrypted,query_sha256=hashlib.sha256(query.encode()).hexdigest()))
            except BaseException as error:errors.append(type(error).__name__)
        watcher=threading.Thread(target=monitor);watcher.start()
        env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','TMPDIR','LANG','SHELL')};env['NODE_EXTRA_CA_CERTS']=str(bundle)
        child=subprocess.Popen(['pnpm','--filter','@oracle/web','exec','tsx','tests/oracle2/workspace-next-recipients-proof.ts',str(metadata_path)],cwd=Path(__file__).resolve().parents[3],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
        output=''
        try:
            remaining=min(110,(proof_end-datetime.now(timezone.utc)).total_seconds()-3)
            assert remaining>0,'original fixture window exhausted before browser'
            output,_=child.communicate(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            output=error.output.decode() if isinstance(error.output,bytes) else (error.output or '')
            raise
        finally:
            for sig in (signal.SIGTERM,signal.SIGKILL):
                try:os.killpg(child.pid,sig)
                except ProcessLookupError:pass
            if child.poll() is None:child.wait(timeout=3)
            protected('browser-output.txt',output.encode())
            cleanup_end=time.monotonic()+2
            while True:
                remaining=[]
                for proc in Path('/proc').iterdir():
                    if proc.name.isdecimal():
                        try:
                            fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
                            if int(fields[2])==child.pid and fields[0]!='Z':remaining.append(int(proc.name))
                        except (FileNotFoundError,ProcessLookupError,PermissionError):pass
                if not remaining or time.monotonic()>=cleanup_end:break
                time.sleep(.05)
            protected('process-cleanup.json',canonical_bytes(dict(process_group=child.pid,remaining_active=remaining)))
            assert not remaining
        assert child.returncode==0,output[-6000:]
        receipt=json.loads((directory/'receipt.json').read_bytes())
        assert receipt['actual_next'] is True and receipt['all_requests_original_window'] is True
        assert receipt['recipient_principals']==[entry['principal_id'] for entry in recipients]
        assert observations and not errors,errors
        protected('actual-boundaries.json',canonical_bytes(dict(actual_response_counts=receipt['response_counts'],employee_sql_observations=observations,baseline_principal=str(settings.config.principal_id),independent_principals=[str(h['actor']) for h in histories])))
    finally:
        stop.set()
        if 'watcher' in locals():watcher.join(3);assert not watcher.is_alive()
        for owned in servers:owned.shutdown();owned.server_close()
        for thread in threads:thread.join(3);assert not thread.is_alive()
        assert all(not owned.answer_owned_loop.thread.is_alive() for owned in servers)


@pytest.mark.parametrize('damage',('empty','one','three','auth-duplicate','employee-duplicate','string-uuid','boolean-admin','unknown-tuple'))
def test_employee_pair_fixture_rejects_malformed_population_before_database(damage):
    first=(uuid4(),uuid4(),False);second=(uuid4(),uuid4(),True);entries=(first,second)
    if damage=='empty':entries=()
    elif damage=='one':entries=(first,)
    elif damage=='three':entries=(first,second,(uuid4(),uuid4(),False))
    elif damage=='auth-duplicate':entries=(first,(first[0],second[1],True))
    elif damage=='employee-duplicate':entries=(first,(second[0],first[1],True))
    elif damage=='string-uuid':entries=((str(first[0]),first[1],False),second)
    elif damage=='boolean-admin':entries=((first[0],first[1],1),second)
    else:entries=(first,(*second,'foreign'))
    with pytest.raises(ValueError,match='(?:exact two|distinct exact) invented'):
        invented_next_employee_pair_fixture_v1('',container='never-connect',entries=entries)
