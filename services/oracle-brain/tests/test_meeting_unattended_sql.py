"""Actual Linux processes, independent signer, SQL and invented provider TLS.

No installed production supervisor, actual provider account or employee proof.
"""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from contextlib import ExitStack
import hashlib,json,os,signal,socket,ssl,subprocess,sys,tempfile,time,threading,shutil
import pytest,psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat,PrivateFormat,NoEncryption
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.hosting.original_intake_v1 import load_original_intake_settings_v1
from oracle_brain.hosting.meeting_capture_v1 import load_meeting_capture_settings_v1,MeetingCaptureFactoryV1
from oracle_brain.hosting.meeting_capture_worker_v1 import CaptureWorkerConfigV1,load_capture_worker_settings_v1
from oracle_brain.hosting.meeting_worker_service_v1 import (CaptureWorkerPeerProfileV1,protected_meeting_create_worker_server_v1,
 protected_meeting_leave_worker_server_v1,protected_meeting_pre_stop_retrieve_worker_server_v1,protected_meeting_post_stop_retrieve_worker_server_v1)
from oracle_brain.hosting.meeting_supervision_service_v1 import MeetingSupervisionConfigV1,load_meeting_supervision_settings_v1,MeetingSupervisionPeerProfileV1,protected_meeting_stop_supervision_server_v1
from oracle_brain.hosting.parent_observer_v2 import MeetingSupervisorScopeV1,MeetingSupervisorAdmissionV2
from oracle_brain.hosting.meeting_supervisor_observer_v1 import MeetingSupervisorObserverConfigV2,MeetingSupervisorPeerProfileV2,load_meeting_supervisor_observer_settings_v2,protected_meeting_supervisor_server_v2
from oracle_brain.hosting.meeting_capture_supervisor_v1 import SupervisorClientInstallationV1,SupervisorReplayInstallationV1
from oracle_brain.hosting.meeting_scheduler_process_v1 import MeetingSchedulerRuntimeV1
from oracle_brain.meetings.supervisor_process import InstalledSupervisorProcessV2
from oracle_brain.meetings.create_stop_relation import CreateOperationStopRelationV1
from test_meeting_capture_sql import meeting_sql,admin,invite,original_request_fence
from test_replacement_requester_sql import configured_settings
ROOT=Path(__file__).resolve().parents[3]

def pin(path,record):
    raw=record if type(record) is bytes else canonical_bytes(record.model_dump(mode='json') if hasattr(record,'model_dump') else record)
    path.write_bytes(raw);path.chmod(0o600);return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())
def now():return datetime.now(timezone.utc)
def text(t):return t.isoformat().replace('+00:00','Z')

# ---- Fixture-only diagnostic helpers (plan v5 §1–§8). No production effect. ----
# §8: one module lock for jsonl appends AND the per-request sequence counter.
_JSONL_LOCK=threading.Lock()
_REQUEST_SEQ=0
_diag_jsonl_path=None

def _next_seq():
    global _REQUEST_SEQ
    with _JSONL_LOCK:
        _REQUEST_SEQ+=1
        return _REQUEST_SEQ

def _jsonl_append(record):
    """§8 locked append. record must already be redact_record-clean."""
    if _diag_jsonl_path is None:return
    line=json.dumps(record,sort_keys=True,separators=(',',':'))
    with _JSONL_LOCK:
        with open(_diag_jsonl_path,'a',encoding='utf-8') as f:
            f.write(line+'\n')

# §5 allow-list + redact_record live in meeting_unattended_redact so offline
# unit tests can import them without the heavy meeting-test dependencies.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0,str(Path(__file__).resolve().parent))
from meeting_unattended_redact import redact_record,_write_json_artifact

# §1 wrap recorder: monotonic time, sequence index under the §8 lock, wrap_trace.
class _WrapRecorder:
    def __init__(self):
        self.local=threading.local()
    def _ctx(self):
        ctx=getattr(self.local,'ctx',None)
        if ctx is None:
            ctx=dict(request_id=_next_seq(),trace=[],operation=None,caller_deadline=None,raise_site='UNKNOWN')
            self.local.ctx=ctx
        return ctx
    def begin(self,wrap):
        ctx=self._ctx();seq=_next_seq()
        ctx['trace'].append(dict(wrap=wrap,event='enter',seq=seq,mono=time.monotonic()))
        return seq
    def ok(self,wrap,seq):
        ctx=self._ctx();ctx['trace'].append(dict(wrap=wrap,event='exit',seq=_next_seq(),mono=time.monotonic()))
    def fail(self,wrap,error,code_name='UNKNOWN'):
        ctx=self._ctx();name=type(error).__name__
        site=name if code_name=='UNKNOWN' or code_name is None else name+':'+code_name
        if ctx['raise_site']=='UNKNOWN':ctx['raise_site']=site
        ctx['trace'].append(dict(wrap=wrap,event='error',seq=_next_seq(),mono=time.monotonic(),error_type=name,raise_site=site))
    def attach(self,operation,caller_deadline):
        ctx=self._ctx();ctx['operation']=operation;ctx['caller_deadline']=caller_deadline
    def flush(self,outcome):
        ctx=getattr(self.local,'ctx',None)
        if ctx is None:return None
        self.local.ctx=None
        record=dict(kind='request',request_id=ctx['request_id'],operation=ctx['operation'],
            caller_deadline=ctx['caller_deadline'],raise_site=ctx['raise_site'],
            outcome=outcome,wrap_trace=ctx['trace'])
        _jsonl_append(redact_record(record))
        return record
    def mark(self,wrap,event):
        ctx=self._ctx();ctx['trace'].append(dict(wrap=wrap,event=event,seq=_next_seq(),mono=time.monotonic()))

_WRAP=_WrapRecorder()

def _frame_code_name(error=None):
    """type(error).__name__ plus the Python frame's code name at the raise site."""
    try:
        tb=error.__traceback__ if error is not None else None
        name='UNKNOWN'
        while tb is not None:
            name=tb.tb_frame.f_code.co_name
            tb=tb.tb_next
        return name if name and name!='<module>' else 'UNKNOWN'
    except Exception:return 'UNKNOWN'

def role(x,d,name):
    d.mkdir(mode=0o700);actor,leaf,selected=uuid4(),uuid4(),uuid4();login='unattended_'+uuid4().hex[:12];seal=hashlib.sha256(selected.bytes).hexdigest()
    with admin(x) as c:
        c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-unattended-only')))
        c.execute(sql.SQL('GRANT oracle2_replacement_requester TO {}').format(sql.Identifier(login)))
        c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,x['runtime'],x['registry'],x['until']))
        c.execute('INSERT INTO oracle2.hosting_request_principal_admissions VALUES(%s,%s,%s,%s,%s,%s)',(login,actor,x['workspace'],x['runtime'],x['registry'],x['until']))
        c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,'meeting-capture',%s,%s,%s)",(leaf,x['workspace'],actor,x['owner'],x['root'],x['until']))
    own=x|dict(login=login,actor=actor,url=psycopg.conninfo.make_conninfo(x['admin'],user=login,password='invented-unattended-only'));host=configured_settings(d,own)
    cfg=host.config.model_copy(update=dict(expires_at=x['until'],original_horizon=x['until']));cr=pin(d/'host-long.json',cfg)
    apt=host.appointment.model_copy(update=dict(config_sha256=cr['sha256'],expires_at=x['until'],original_horizon=x['until']));ar=pin(d/'appointment-long.json',apt)
    host=load_original_intake_settings_v1(cr['path'],cr['sha256'],ar['path'],ar['sha256'],host.expected_issuer_actor,host.expected_reviewer_actor)
    cfg=x['worker']['settings'].config.model_copy(update=dict(host_config_sha256=host.config_sha256,host_appointment_sha256=host.appointment_sha256,admission_id=selected,admission_sha256=seal,channel='worker',expires_at=x['until'],original_horizon=x['until']))
    cp=pin(d/'capture.json',cfg);capture=load_meeting_capture_settings_v1(host,cp['path'],cp['sha256'])
    return dict(name=name,dir=d,actor=actor,leaf=leaf,admission=selected,seal=seal,login=login,host=host,capture=capture)

def peer_fields(own,certs,identity,end,*,purpose):
    host=own['host'];b=host.config;sha=lambda n:hashlib.sha256((certs/n).read_bytes()).hexdigest();cert=x509.load_pem_x509_certificate((certs/(identity+'.pem')).read_bytes())
    return dict(schema_version=1,purpose=purpose,intake_config_sha256=host.config_sha256,intake_appointment_sha256=host.appointment_sha256,principal_id=b.principal_id,workspace_id=b.workspace_id,runtime_hash=b.runtime_hash,registry_hash=b.registry_hash,client_uri='spiffe://oracle/'+identity,client_certificate_sha256=hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest(),listen_host='::1',listen_port=0,server_hostname='localhost.localdomain',server_certificate_file=str(certs/'server.pem'),server_certificate_sha256=sha('server.pem'),server_key_file=str(certs/'server.key'),server_key_sha256=sha('server.key'),client_ca_file=str(certs/'ca.pem'),client_ca_sha256=sha('ca.pem'),issuer_actor=host.expected_issuer_actor,reviewer_actor=host.expected_reviewer_actor,valid_from=now()-timedelta(seconds=1),expires_at=end,original_horizon=b.original_horizon)

def start_server(stack,server):
    t=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});t.start()
    def close():server.shutdown();server.server_close();t.join(3);assert not t.is_alive() and not server._active
    stack.callback(close);return server

def process_profile(process,runtime,config,sock,scope,purpose,executable):
    stat=sock.stat();proc=Path('/proc')/str(process.pid);record=(proc/'stat').read_text();ticks=record[record.rfind(')')+2:].split()[19]
    return InstalledSupervisorProcessV2(schema_version=2,observation_protocol='meeting-process-currentness-v2',purpose=purpose,scope=scope,socket_file=str(sock),socket_device=stat.st_dev,socket_inode=stat.st_ino,peer_pid=process.pid,peer_uid=os.getuid(),process_start_ticks=ticks,executable_file=str(executable),executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),command_sha256=hashlib.sha256((proc/'cmdline').read_bytes()).hexdigest(),runtime_file=str(runtime),runtime_sha256=hashlib.sha256(runtime.read_bytes()).hexdigest(),config_file=str(config),config_sha256=hashlib.sha256(config.read_bytes()).hexdigest(),issuer_actor='invented-independent-installer',reviewer_actor='invented-independent-reviewer',valid_from=scope.stop_valid_from,expires_at=scope.capture_until if purpose=='meeting-scheduler-process-v1' else scope.stop_until)

@pytest.fixture
def certs(tmp_path):
    d=tmp_path/'tls';d.mkdir(mode=0o700)
    def run(*a):subprocess.run(['openssl',*a],cwd=d,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    run('req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.pem','-days','1','-subj','/CN=Invented Unattended CA','-addext','basicConstraints=critical,CA:TRUE,pathlen:0','-addext','keyUsage=critical,keyCertSign,cRLSign')
    for name in ('server','create','leave','pre','post','queue','observer-client','other'):
        run('req','-newkey','rsa:2048','-nodes','-keyout',name+'.key','-out',name+'.csr','-subj','/CN='+name)
        san='DNS:localhost.localdomain,URI:spiffe://oracle/independent-observer' if name=='server' else 'URI:spiffe://oracle/'+name
        (d/(name+'.ext')).write_text('subjectAltName='+san+'\nextendedKeyUsage='+('serverAuth' if name=='server' else 'clientAuth')+'\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer')
        run('x509','-req','-in',name+'.csr','-CA','ca.pem','-CAkey','ca.key','-CAcreateserial','-out',name+'.pem','-days','1','-extfile',name+'.ext')
    for p in d.iterdir():p.chmod(0o600)
    return d

@pytest.fixture
def unattended(meeting_sql,certs,tmp_path):
    x=meeting_sql;private=tempfile.TemporaryDirectory(prefix='s07-u-');short=Path(private.name);short.chmod(0o700);stack=ExitStack();processes=[];sockets=[];provider_seen=[]
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    def terminate(p):
        if p.poll() is None:p.terminate()
        p.wait(timeout=5)
    def child(argv,env,name,*,input_pipe=False):
        out=(tmp_path/(name+'.stdout')).open('w');err=(tmp_path/(name+'.stderr')).open('w');p=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=out,stderr=err,stdin=subprocess.PIPE if input_pipe else None);processes.append(p);stack.callback(out.close);stack.callback(err.close);stack.callback(terminate,p);return p
    def socket_ready(path,p):
        end=time.monotonic()+5
        while not path.exists() and p.poll() is None and time.monotonic()<end:time.sleep(.01)
        assert path.exists() and p.poll() is None,'actual process startup refused; private diagnostic retained'
    try:
        owners={name:role(x,tmp_path/name,name) for name in ('scheduler','stop','observer','create','pre','post')}
        body=canonical_bytes(dict(meeting_url='https://teams.microsoft.com/l/meetup-join/invented',bot_name='Invented',recording_config=dict(transcript=dict(provider=dict(elevenlabs_streaming={})),realtime_endpoints=[dict(type='webhook',url='https://ingress.example.test/recall',events=['transcript.data'])])))
        operation=uuid4();body_sha=hashlib.sha256(body).hexdigest();body_ref=pin(short/'create-body.json',body)
        scheduler_runtime=short/'scheduler.py';scheduler_runtime.write_bytes((ROOT/'services/oracle-brain/oracle_brain/hosting/meeting_scheduler_process_v1.py').read_bytes());scheduler_runtime.chmod(0o600)
        stop_runtime=ROOT/'apps/workers/src/services/oracle2-meeting-stop-process.ts';old_stop_mode=stop_runtime.stat().st_mode&0o777;stop_runtime.chmod(0o600);stack.callback(stop_runtime.chmod,old_stop_mode)
        with admin(x) as c:base=c.execute('SELECT to_jsonb(a) FROM oracle2.meeting_capture_admissions_v1 a WHERE admission_id=%s',(x['worker']['admission'],)).fetchone()[0]
        start=datetime.fromisoformat(base['stop_valid_from']);common=dict(workspace_id=x['workspace'],meeting_id=x['meeting'],provider_account=x['account'],create_operation_id=operation,create_request_sha256=body_sha,capture_until=x['capture_until'],stop_valid_from=start,stop_until=x['until'],original_horizon=x['until'],scheduler_poll_seconds=2,stop_request_seconds=10,safety_allowance_seconds=1,stop_margin_seconds=13)
        scheduler=owners['scheduler'];h=scheduler['host'];c=scheduler['capture']
        sc=MeetingSchedulerRuntimeV1(purpose='meeting-scheduler-runtime-v1',**common,socket_file=str(short/'scheduler.sock'),observer_uid=os.getuid(),host_config=dict(path=str(h.config_path),sha256=h.config_sha256),host_appointment=dict(path=str(h.appointment_path),sha256=h.appointment_sha256),capture_config=dict(path=str(c.config_path),sha256=c.config_sha256),expected_issuer_actor=h.expected_issuer_actor,expected_reviewer_actor=h.expected_reviewer_actor,valid_from=now()-timedelta(seconds=1),expires_at=x['capture_until'])
        sr=pin(short/'scheduler.json',sc)
        stop_config=dict(schema_version=1,purpose='meeting-stop-process-runtime-v1',**common,socket_file=str(short/'stop.sock'),observer_uid=os.getuid(),valid_from=now()-timedelta(seconds=1),expires_at=x['until'],readonly_wait_count=30,readonly_wait_milliseconds=75,post_stop_delay_milliseconds=0,issuer_actor=str(uuid4()),reviewer_actor=str(uuid4()))
        # JSON encode UUID/time fields canonically without claiming model authority.
        stop_config={k:str(v) if isinstance(v,__import__('uuid').UUID) else text(v) if isinstance(v,datetime) else v for k,v in stop_config.items()};tr=pin(short/'stop.json',stop_config)
        scope=MeetingSupervisorScopeV1(**common,scheduler_id=scheduler['actor'],scheduler_runtime_sha256=sha(scheduler_runtime),scheduler_config_sha256=sr['sha256'],stop_owner_id=owners['stop']['actor'],stop_runtime_sha256=sha(stop_runtime),stop_config_sha256=tr['sha256'])
        relation=CreateOperationStopRelationV1(purpose='meeting-create-operation-stop-relation-v1',mapping_id=uuid4(),provider='recall',tenant_id='tenant1',provider_meeting_id='meeting1',supervision_scope_sha256=digest(scope.model_dump(mode='json')),issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=start,expires_at=x['until'],**{k:getattr(scope,k) for k in ('workspace_id','meeting_id','provider_account','create_operation_id','create_request_sha256','scheduler_id','scheduler_runtime_sha256','scheduler_config_sha256','stop_owner_id','stop_runtime_sha256','stop_config_sha256','capture_until','stop_valid_from','stop_until','original_horizon')})
        with admin(x) as db:db.execute('INSERT INTO oracle2.meeting_create_stop_relations_v1(mapping_id,workspace_id,meeting_id,mapping_sha256,mapping_payload) VALUES(%s,%s,%s,%s,%s)',(relation.mapping_id,x['workspace'],x['meeting'],relation.sha256,Jsonb(relation.model_dump(mode='json'))))
        effects={'create':'capture-create','stop':'capture-leave','pre':'capture-retrieve','post':'capture-retrieve'}
        stages={'pre':'pre-stop-consistency','post':'post-stop-terminal'}
        for name,o in owners.items():
            o['worker_id']=uuid4();o['retrieve_op']=uuid4() if name in stages else None
            actions={'scheduler':['supervise','status','stop_intent'],'observer':['supervised','supervise','status'],'create':['create_intent','create_observed','create_unknown','status'],'stop':['supervise','status','stop_intent','stop_observed','stop_unknown'],'pre':['status','stop_reconciled'],'post':['status','stop_reconciled']}[name]
            row=dict(base,admission_id=str(o['admission']),admission_sha256=o['seal'],role_name=o['login'],principal_id=str(o['actor']),leaf_appointment_id=str(o['leaf']),bot_id=None,actions=actions,issuer_actor=str(o['host'].expected_issuer_actor),reviewer_actor=str(o['host'].expected_reviewer_actor),supervision_scope_sha256=relation.supervision_scope_sha256,stop_relation_id=str(relation.mapping_id),stop_mapping_sha256=relation.sha256)
            if name in effects:row.update(worker_id=str(o['worker_id']),worker_effect=effects[name],worker_policy_sha256='d'*64,worker_create_operation_id=str(operation) if name=='create' else None,worker_create_request_sha256=body_sha if name=='create' else None,worker_retrieve_stage=stages.get(name),worker_retrieve_operation_id=str(o['retrieve_op']) if o['retrieve_op'] else None)
            if name=='create':row['supervisor_admission_id']=str(owners['observer']['admission'])
            with admin(x) as db:db.execute('INSERT INTO oracle2.meeting_capture_admissions_v1 SELECT (jsonb_populate_record(NULL::oracle2.meeting_capture_admissions_v1,%s)).*',(Jsonb(row),))
        supervisions={}
        for name in ('scheduler','stop'):
            o=owners[name];cfg=MeetingSupervisionConfigV1(purpose='meeting-supervision-queue-consumer-v1',capture_config_sha256=o['capture'].config_sha256,process_purpose='meeting-scheduler-process-v1' if name=='scheduler' else 'meeting-stop-worker-process-v1',scope=scope,issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=now()-timedelta(seconds=1),expires_at=x['capture_until'] if name=='scheduler' else x['until'])
            ref=pin(o['dir']/'supervision.json',cfg);supervisions[name]=load_meeting_supervision_settings_v1(o['capture'],ref['path'],ref['sha256'])
        # Invented provider exposes only exact documented routes. Authorization
        # and request bytes never enter diagnostics or public output.
        bot=uuid4();left=[False];context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(str(certs/'server.pem'),str(certs/'server.key'))
        listener=socket.socket(socket.AF_INET6);listener.bind(('::1',0));listener.listen();listener.settimeout(.1);closing=threading.Event();provider_threads=[]
        def provider_request(raw_socket):
            try:
                with context.wrap_socket(raw_socket,server_side=True) as conn:
                    conn.settimeout(4);raw=bytearray()
                    while b'\r\n\r\n' not in raw:
                        part=conn.recv(16384)
                        if not part:return
                        raw.extend(part);assert len(raw)<65536
                    header,tail=bytes(raw).split(b'\r\n\r\n',1);length=int(next(v.split(b':',1)[1] for v in header.split(b'\r\n') if v.lower().startswith(b'content-length:')))
                    while len(tail)<length:
                        part=conn.recv(length-len(tail))
                        if not part:return
                        tail+=part
                    route=header.split(b'\r\n',1)[0];provider_seen.append(route.decode())
                    if route==b'POST /api/v1/bot/ HTTP/1.1':assert tail==body;status=201;out=canonical_bytes({'id':str(bot)})
                    elif route==f'POST /api/v1/bot/{bot}/leave_call/ HTTP/1.1'.encode():left[0]=True;status=200;out=b''
                    else:
                        assert route==f'GET /api/v1/bot/{bot}/ HTTP/1.1'.encode();status=200;out=canonical_bytes({'id':str(bot),'status_changes':[{'code':'call_ended' if left[0] else 'in_call_recording','created_at':text(now()-timedelta(seconds=1))}]})
                    conn.sendall(f'HTTP/1.1 {status} OK\r\nContent-Type: application/json\r\nContent-Length: {len(out)}\r\nConnection: close\r\n\r\n'.encode()+out)
                    try:conn.unwrap().close()
                    except (OSError,ssl.SSLError):pass
            except (OSError,ssl.SSLError):pass
        def accept():
            while not closing.is_set():
                try:s,_=listener.accept()
                except socket.timeout:continue
                except OSError:break
                t=threading.Thread(target=provider_request,args=(s,));t.start();provider_threads.append(t)
        provider_thread=threading.Thread(target=accept);provider_thread.start()
        def close_provider():
            closing.set();listener.close();provider_thread.join(2)
            for t in provider_threads:t.join(5);assert not t.is_alive()
        stack.callback(close_provider)
        env={**os.environ,'PYTHONHOME':sys.base_prefix,'PYTHONPATH':':'.join(str(p) for p in sys.path if p),'ORACLE2_INVENTED_PROVIDER_PORT':str(listener.getsockname()[1])}
        # Remaining independent process profiles, signer and service pins are
        # installed BEFORE invitation and BEFORE any Create request.
        yield dict(x=x,owners=owners,scope=scope,relation=relation,supervisions=supervisions,short=short,stack=stack,child=child,socket_ready=socket_ready,scheduler_runtime=scheduler_runtime,scheduler_ref=sr,stop_runtime=stop_runtime,stop_runtime_old_mode=old_stop_mode,stop_ref=tr,env=env,certs=certs,body_ref=body_ref,body_sha=body_sha,operation=operation,provider_seen=provider_seen,bot=bot,processes=processes)
    finally:
        # §6 teardown raise must not eat evidence: nested try/finally per step so
        # private.cleanup() still runs and the hung-child packet is not skipped.
        teardown_steps=[]
        def _step(name,fn):
            try:fn();teardown_steps.append(dict(step=name,ok=True))
            except Exception as error:teardown_steps.append(dict(step=name,ok=False,error_type=type(error).__name__))
        def _pin_scope():
            # §4 supervision scope model_dump pinned BEFORE teardown deletes scratch.
            _write_json_artifact(tmp_path/'supervision-scope.json',scope.model_dump(mode='json'))
        def _copy_spool():
            # §4/§7 step 1: spool copy BEFORE teardown close. Spool holds
            # nonce-sequence state and appointment hashes only (no secrets).
            src=short/'replay';dst=tmp_path/'replay-spool'
            if src.exists() and not dst.exists():
                shutil.copytree(src,dst)
                _write_json_artifact(tmp_path/'replay-spool-manifest.json',dict(
                    copy_monotonic=time.monotonic(),
                    members=sorted(p.name for p in dst.iterdir()),
                    note='nonce-sequence state and appointment hashes only; no secrets'))
        def _selected_state():
            with admin(x) as c:
                snapshot={name:c.execute('SELECT to_jsonb(t) FROM oracle2.'+name+' t WHERE workspace_id=%s',(x['workspace'],)).fetchall() for name in ('meeting_capture_heads_v1','meeting_capture_events_v1','meeting_capture_worker_claims_v1')}
                snapshot['receipts']=c.execute('SELECT to_jsonb(r) FROM oracle2.meeting_capture_worker_receipts_v1 r JOIN oracle2.meeting_capture_worker_claims_v1 q USING(claim_id) WHERE q.workspace_id=%s',(x['workspace'],)).fetchall()
            _write_json_artifact(tmp_path/'actual-selected-state.json',snapshot)
        def _provider_routes():
            _write_json_artifact(tmp_path/'actual-provider-routes.json',list(provider_seen))
        def _observer_files():
            if (short/'observer-port-errors.json').exists():(tmp_path/'actual-observer-refusals.json').write_bytes((short/'observer-port-errors.json').read_bytes())
            if (short/'observer-port-observations.json').exists():(tmp_path/'actual-observer-process-observations.json').write_bytes((short/'observer-port-observations.json').read_bytes())
        def _close_stack():
            stack.close()
        def _copy_jsonl():
            # §7 step 3: close-then-copy AFTER stack.close() (servers stopped).
            src=short/'create-server-responses.jsonl'
            if src.exists():
                (tmp_path/'create-server-responses.jsonl').write_bytes(src.read_bytes())
        def _owned_cleanup():
            remaining=[p.pid for p in processes if p.poll() is None]
            _write_json_artifact(tmp_path/'owned-process-cleanup.json',dict(remaining_pids=remaining,unix_sockets_absent=all(not (short/n).exists() for n in ('scheduler.sock','stop.sock'))))
            assert not remaining and all(not (short/n).exists() for n in ('scheduler.sock','stop.sock'))
        def _private_cleanup():
            private.cleanup();assert not short.exists()
        # §7 numbered write order: spool copy before teardown close; jsonl
        # close-then-copy after stack.close(); then owned-process-cleanup;
        # then private.cleanup(). Supervision-scope before scratch deletion.
        for name,fn in (
            ('supervision-scope',_pin_scope),('replay-spool-copy',_copy_spool),
            ('selected-state',_selected_state),('provider-routes',_provider_routes),
            ('observer-files',_observer_files),('stack-close',_close_stack),
            ('jsonl-close-then-copy',_copy_jsonl),
            ('owned-process-cleanup',_owned_cleanup),('private-cleanup',_private_cleanup)):
            _step(name,fn)
        try:_write_json_artifact(tmp_path/'teardown-steps.json',teardown_steps)
        except Exception:pass

def ts_profile(u,name,worker_settings,peer,server):
    o=u['owners'][name];h=o['host'].config;c=worker_settings.config;certs=u['certs'];p=peer;short=u['short'];sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
    identity='leave' if name=='stop' else name
    root=short/('receipts-'+name);root.mkdir(mode=0o700);st=root.stat()
    init=pin(root/'initialization.json',dict(schema_version=1,purpose='meeting-worker-receipt-root-v1',worker_id=str(o['worker_id']),receipt_root=str(root),receipt_device=st.st_dev,receipt_inode=st.st_ino,receipt_uid=st.st_uid,issuer_actor=str(o['host'].expected_issuer_actor),reviewer_actor=str(o['host'].expected_reviewer_actor)))
    return dict(schema_version=1,purpose='replacement-meeting-worker-binding-v1',principal_id=str(h.principal_id),workspace_id=str(h.workspace_id),runtime_hash=h.runtime_hash,registry_hash=h.registry_hash,backend_origin='https://localhost.localdomain:'+str(server.server_port),server_dns='localhost.localdomain',server_certificate_der_sha256=hashlib.sha256(x509.load_pem_x509_certificate((certs/'server.pem').read_bytes()).public_bytes(Encoding.DER)).hexdigest(),server_ca_file=str(certs/'ca.pem'),server_ca_sha256=sha(certs/'ca.pem'),client_certificate_file=str(certs/(identity+'.pem')),client_certificate_sha256=sha(certs/(identity+'.pem')),client_certificate_der_sha256=p.client_certificate_sha256,client_uri=p.client_uri,client_key_file=str(certs/(identity+'.key')),client_key_sha256=sha(certs/(identity+'.key')),issuer_actor=str(o['host'].expected_issuer_actor),reviewer_actor=str(o['host'].expected_reviewer_actor),valid_from=text(p.valid_from),expires_at=text(p.expires_at),original_horizon=text(h.original_horizon),worker_path='/v1/replacement/meetings/worker',worker_id=str(o['worker_id']),meeting_id=str(u['x']['meeting']),effect_purpose=c.effect,worker_config_sha256=worker_settings.sha256,worker_peer_profile_sha256=digest(p.model_dump(mode='json')),worker_admission_sha256=o['seal'],provider_account=u['x']['account'],provider_region='us-east-1',provider_ca_file=str(certs/'ca.pem'),provider_ca_sha256=sha(certs/'ca.pem'),provider_server_der_sha256=hashlib.sha256(x509.load_pem_x509_certificate((certs/'server.pem').read_bytes()).public_bytes(Encoding.DER)).hexdigest(),provider_key_file=str(short/'provider.key'),provider_key_sha256=sha(short/'provider.key'),operation_policy_sha256='d'*64,composer_program_sha256=None,create_operation_id=str(u['operation']) if name=='create' else None,create_request_sha256=u['body_sha'] if name=='create' else None,stop_mapping_sha256=None if name=='create' else u['relation'].sha256,retrieve_stage=c.retrieve_stage,retrieve_operation_id=str(c.retrieve_operation_id) if c.retrieve_operation_id else None,capture_until=text(u['x']['capture_until']),stop_until=text(u['x']['until']),receipt_root=str(root),receipt_device=st.st_dev,receipt_inode=st.st_ino,receipt_uid=st.st_uid,receipt_initialization_file=init['path'],receipt_initialization_sha256=init['sha256'])

def start_unattended(u):
    x=u['x'];short=u['short'];certs=u['certs'];owners=u['owners'];env=dict(u['env']);stack=u['stack'];sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    pin(short/'provider.key',b'invented-unattended-provider-key')
    def worker(name,extra=None):
        o=owners[name];c=o['capture'];end=x['capture_until'] if name=='create' else x['until']
        cfg=CaptureWorkerConfigV1(purpose='meeting-capture-worker-consumer-v1',capture_config_sha256=c.config_sha256,worker_id=o['worker_id'],effect='capture-create' if name=='create' else 'capture-leave' if name=='stop' else 'capture-retrieve',operation_policy_sha256='d'*64,create_operation_id=u['operation'] if name=='create' else None,create_body=u['body_ref'] if name=='create' else None,retrieve_stage='pre-stop-consistency' if name=='pre' else 'post-stop-terminal' if name=='post' else None,retrieve_operation_id=o['retrieve_op'],stop_mapping_sha256=None if name=='create' else u['relation'].sha256,issuer_actor=o['host'].expected_issuer_actor,reviewer_actor=o['host'].expected_reviewer_actor,valid_from=now()-timedelta(seconds=1),expires_at=end,original_horizon=x['until'],**(extra or {}))
        ref=pin(o['dir']/'worker.json',cfg);s=load_capture_worker_settings_v1(c,ref['path'],ref['sha256'])
        identity='leave' if name=='stop' else name
        p=CaptureWorkerPeerProfileV1(**peer_fields(o,certs,identity,end,purpose='replacement-meeting-capture-worker-peer-v1'),effect_purpose=cfg.effect,retrieve_stage=cfg.retrieve_stage,worker_id=o['worker_id'],meeting_id=x['meeting'],provider_account=x['account'],worker_config_sha256=s.sha256,worker_admission_sha256=o['seal'],operation_policy_sha256='d'*64)
        pr=pin(o['dir']/'worker-peer.json',p)
        f={'create':protected_meeting_create_worker_server_v1,'stop':protected_meeting_leave_worker_server_v1,'pre':protected_meeting_pre_stop_retrieve_worker_server_v1,'post':protected_meeting_post_stop_retrieve_worker_server_v1}[name]
        server=start_server(stack,f(s,pr['path'],pr['sha256']));binding=ts_profile(u,name,s,p,server)
        if name not in ('pre','post'):
            binding.pop('retrieve_stage');binding.pop('retrieve_operation_id')
        # Client identity is independently pinned, not chosen by a request.
        if name=='stop':
            binding.update(client_certificate_file=str(certs/'leave.pem'),client_certificate_sha256=sha(certs/'leave.pem'),client_certificate_der_sha256=p.client_certificate_sha256,client_key_file=str(certs/'leave.key'),client_key_sha256=sha(certs/'leave.key'))
        br=pin(o['dir']/'web-worker-binding.json',binding)
        key={'stop':'LEAVE','pre':'PRE_STOP_RETRIEVE','post':'POST_STOP_RETRIEVE','create':'CREATE'}[name];env['ORACLE2_MEETING_'+key+'_WORKER_BINDING_FILE']=br['path'];env['ORACLE2_MEETING_'+key+'_WORKER_BINDING_SHA256']=br['sha256']
        if name=='create':
            u['create_server']=server
            # Fixture-only response diagnostic: log nonsecret status/header fields
            # for every create-worker response so a refusal can be diagnosed.
            # §8: locked append; §5: redact_record on every jsonl write.
            global _diag_jsonl_path
            _diag_jsonl_path=str(short/'create-server-responses.jsonl')
            _orig_send_response=server.RequestHandlerClass.send_response
            _orig_send_header=server.RequestHandlerClass.send_header
            _orig_end_headers=server.RequestHandlerClass.end_headers
            def _logged_send_response(self,code,message=None):
                self._diag_status=code;self._diag_headers=[]
                return _orig_send_response(self,code,message)
            def _logged_send_header(self,keyword,value):
                self._diag_headers.append([keyword,value])
                return _orig_send_header(self,keyword,value)
            def _logged_end_headers(self):
                try:
                    # Inline do_POST raises never reach execute_v1; flush any
                    # pending request context here so wrap_trace is not lost.
                    # Non-200 is the exact refused path (e.g. 503), not 'response'.
                    _status=getattr(self,'_diag_status',None)
                    _WRAP.flush('response' if _status==200 else 'refused')
                    _jsonl_append(redact_record(dict(kind='response',seq=_next_seq(),
                        status=_status,
                        headers=getattr(self,'_diag_headers',[]),
                        mono=time.monotonic())))
                except Exception:pass
                return _orig_end_headers(self)
            server.RequestHandlerClass.send_response=_logged_send_response
            server.RequestHandlerClass.send_header=_logged_send_header
            server.RequestHandlerClass.end_headers=_logged_end_headers
        return s
    for name in ('pre','stop','post'):worker(name)
    stop=owners['stop'];qs=u['supervisions']['stop'];qp=MeetingSupervisionPeerProfileV1(**peer_fields(stop,certs,'queue',x['until'],purpose='meeting-supervision-service-peer-v1'),process_purpose='meeting-stop-worker-process-v1',supervision_config_sha256=qs.sha256,scope_sha256=digest(u['scope'].model_dump(mode='json')))
    qr=pin(short/'queue-peer.json',qp);server=start_server(stack,protected_meeting_stop_supervision_server_v1(qs,qr['path'],qr['sha256']))
    # Same concrete mTLS binding owner, own distinct queue certificate/purpose.
    root_common=peer_fields(stop,certs,'queue',x['until'],purpose='meeting-supervision-service-peer-v1')
    binding={k:root_common[k] for k in ('principal_id','workspace_id','runtime_hash','registry_hash','client_uri','issuer_actor','reviewer_actor')}
    binding={k:str(v) for k,v in binding.items()}
    binding.update(schema_version=1,purpose='meeting-supervision-service-binding-v1',supervision_path='/v1/replacement/meetings/supervision',backend_origin='https://localhost.localdomain:'+str(server.server_port),server_dns='localhost.localdomain',server_certificate_der_sha256=hashlib.sha256(x509.load_pem_x509_certificate((certs/'server.pem').read_bytes()).public_bytes(Encoding.DER)).hexdigest(),server_ca_file=str(certs/'ca.pem'),server_ca_sha256=sha(certs/'ca.pem'),client_certificate_file=str(certs/'queue.pem'),client_certificate_sha256=sha(certs/'queue.pem'),client_certificate_der_sha256=qp.client_certificate_sha256,client_key_file=str(certs/'queue.key'),client_key_sha256=sha(certs/'queue.key'),valid_from=text(qp.valid_from),expires_at=text(x['until']),original_horizon=text(x['until']),meeting_id=str(x['meeting']),process_purpose='meeting-stop-worker-process-v1',supervision_config_sha256=qs.sha256,supervision_peer_profile_sha256=qr['sha256'],scope_sha256=digest(u['scope'].model_dump(mode='json')),process_runtime_sha256=u['scope'].stop_runtime_sha256,process_config_sha256=u['scope'].stop_config_sha256,capture_until=text(x['capture_until']),stop_until=text(x['until']))
    br=pin(short/'queue-binding.json',binding);env.update(ORACLE2_MEETING_STOP_SUPERVISION_BINDING_FILE=br['path'],ORACLE2_MEETING_STOP_SUPERVISION_BINDING_SHA256=br['sha256'],ORACLE2_MEETING_STOP_PROCESS_CONFIG_FILE=u['stop_ref']['path'],ORACLE2_MEETING_STOP_PROCESS_CONFIG_SHA256=u['stop_ref']['sha256'])
    h=owners['scheduler']['host'];s=u['supervisions']['scheduler'];se={**env,'ORACLE2_MEETING_SCHEDULER_CONFIG_FILE':u['scheduler_ref']['path'],'ORACLE2_MEETING_SCHEDULER_CONFIG_SHA256':u['scheduler_ref']['sha256'],'ORACLE2_MEETING_SCHEDULER_RUNTIME_SHA256':sha(u['scheduler_runtime']),'ORACLE2_MEETING_SCHEDULER_SUPERVISION_SETTINGS_FILE':s.path,'ORACLE2_MEETING_SCHEDULER_SUPERVISION_SETTINGS_SHA256':s.sha256}
    executable=short/'python';shutil.copyfile(os.readlink('/proc/self/exe'),executable);executable.chmod(0o700)
    scheduler=u['child']([str(executable),str(u['scheduler_runtime']),u['scheduler_ref']['path']],se,'scheduler');u['socket_ready'](short/'scheduler.sock',scheduler)
    driver=ROOT/'services/oracle-brain/tests/fixtures/meeting-unattended-driver.mts';node='/usr/bin/node';node_env={**env,'ORACLE2_INVENTED_DRIVER_PRELOAD':'1'}
    stop_process=u['child']([node,'--import','tsx','--import',str(driver),str(u['stop_runtime']),u['stop_ref']['path']],node_env,'stop');u['socket_ready'](short/'stop.sock',stop_process)
    profiles=[]
    for p,r,c,s,purpose,e in ((scheduler,u['scheduler_runtime'],Path(u['scheduler_ref']['path']),short/'scheduler.sock','meeting-scheduler-process-v1',executable),(stop_process,u['stop_runtime'],Path(u['stop_ref']['path']),short/'stop.sock','meeting-stop-worker-process-v1',Path('/usr/bin/node').resolve())):
        profiles.append(pin(short/(purpose+'.json'),process_profile(p,r,c,s,u['scope'],purpose,e)))
    key=Ed25519PrivateKey.generate();public=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw);signer=pin(short/'observer-signing.key',key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
    observer=owners['observer'];a=MeetingSupervisorAdmissionV2(schema_version=2,purpose='meeting-supervisor-currentness-v2',scope=u['scope'],principal_id=observer['actor'],observer_uri='spiffe://oracle/independent-observer',client_uri='spiffe://oracle/observer-client',signing_public_key=public.hex(),signing_key_fingerprint=hashlib.sha256(public).hexdigest(),issuer_actor=uuid4(),reviewer_actor=uuid4(),minimum_sequence=0,max_age_seconds=2,expires_at=x['capture_until'],scheduler_process_sha256=profiles[0]['sha256'],stop_process_sha256=profiles[1]['sha256'])
    ar=pin(short/'supervisor-admission.json',a);cfg=MeetingSupervisorObserverConfigV2(schema_version=2,purpose='meeting-supervisor-observer-owner-v2',meeting_config_sha256=observer['capture'].config_sha256,observer_admission=ar,scheduler_process=profiles[0],stop_worker_process=profiles[1],signing_key=signer);cr=pin(short/'observer.json',cfg)
    qp=peer_fields(observer,certs,'observer-client',x['capture_until'],purpose='meeting-supervisor-peer-v2');qp['schema_version']=2
    peer=MeetingSupervisorPeerProfileV2(**qp,observer_config_sha256=cr['sha256']);pr=pin(short/'observer-peer.json',peer)
    h=observer['host'];portfile=short/'observer-port';runtime=dict(host=dict(path=str(h.config_path),sha256=h.config_sha256),appointment=dict(path=str(h.appointment_path),sha256=h.appointment_sha256),issuer=str(h.expected_issuer_actor),reviewer=str(h.expected_reviewer_actor),capture=dict(path=str(observer['capture'].config_path),sha256=observer['capture'].config_sha256),observer=cr,peer=pr,port_file=str(portfile));rr=pin(short/'observer-runtime.json',runtime)
    pe={**env,'ORACLE2_INVENTED_OBSERVER_CONFIG_FILE':rr['path'],'ORACLE2_INVENTED_OBSERVER_CONFIG_SHA256':rr['sha256']};producer=u['child']([str(executable),str(ROOT/'services/oracle-brain/tests/fixtures/meeting-observer-driver.py')],pe,'observer')
    end=time.monotonic()+5
    while not portfile.exists() and producer.poll() is None and time.monotonic()<end:time.sleep(.01)
    assert portfile.exists() and producer.poll() is None,'independent producer startup refused; private diagnostic retained'
    client=SupervisorClientInstallationV1(purpose='meeting-supervisor-client-installation-v1',hostname='localhost.localdomain',port=int(portfile.read_text()),server_uri=a.observer_uri,client_uri=a.client_uri,ca_file=dict(path=str(certs/'ca.pem'),sha256=sha(certs/'ca.pem')),certificate_file=dict(path=str(certs/'observer-client.pem'),sha256=sha(certs/'observer-client.pem')),key_file=dict(path=str(certs/'observer-client.key'),sha256=sha(certs/'observer-client.key')));clientref=pin(short/'supervisor-client.json',client)
    spool=short/'replay';spool.mkdir(mode=0o700);initial=dict(schema_version=2,namespace='meeting-create',appointment_hash=ar['sha256'],minimum_sequence=0)
    init=pin(spool/'meeting-create-init.json',initial);pin(spool/'meeting-create-state.json',initial|dict(sequence=0));(spool/'meeting-create-lock').write_bytes(b'');(spool/'meeting-create-lock').chmod(0o600)
    replay=SupervisorReplayInstallationV1(purpose='meeting-supervisor-replay-installation-v1',spool=str(spool),namespace='meeting-create',initialization_receipt_sha256=init['sha256']);replayref=pin(short/'supervisor-replay.json',replay)
    worker('create',dict(supervisor_admission=ar,supervisor_transport=clientref,supervisor_replay=replayref))
    invite(x)
    u.update(env=env,scheduler=scheduler,stop_process=stop_process,producer=producer,process_profiles=profiles,supervisor_admission=ar)
    return u

def install_wraps():
    """§1 fixture-only raise-site capture. Install AFTER start_unattended()
    returns and BEFORE the first worker_request (covers refused-prepare warmup).
    Every wrap re-raises / returns-through unchanged. Restores originals on
    uninstall so the second test node is not double-wrapped."""
    from oracle_brain.hosting import meeting_worker_service_v1 as mws
    from oracle_brain.hosting import _protected_control_listener_v1 as listener_mod
    saved=[]
    def _save(module,name):
        saved.append((module,name,getattr(module,name)))
    def _restore():
        while saved:
            module,name,orig=saved.pop()
            setattr(module,name,orig)
    # Class-level: factory.execute_v1 (PRIMARY) and settings.current.
    _save(mws._CaptureWorkerAdapter,'execute_v1')
    _save(mws._CaptureWorkerSettings,'current')
    orig_execute=mws._CaptureWorkerAdapter.execute_v1
    orig_current=mws._CaptureWorkerSettings.current
    def execute_v1(self,raw):
        seq=_WRAP.begin('execute_v1')
        operation='UNKNOWN';deadline=None
        try:
            try:
                body=json.loads(raw) if isinstance(raw,(bytes,bytearray)) else {}
                operation=str(body.get('operation') or 'UNKNOWN')
                deadline=body.get('caller_deadline')
            except Exception:pass
            _WRAP.attach(operation,deadline)
            _WRAP.ok('execute_v1',seq)
            value=orig_execute(self,raw)
            _WRAP.flush('ok')
            return value
        except BaseException as error:
            _WRAP.fail('execute_v1',error,_frame_code_name(error))
            _WRAP.flush('error')
            raise
    def current(self):
        seq=_WRAP.begin('settings.current')
        try:
            value=orig_current(self)
            _WRAP.ok('settings.current',seq)
            return value
        except BaseException as error:
            _WRAP.fail('settings.current',error,_frame_code_name(error))
            raise
    mws._CaptureWorkerAdapter.execute_v1=execute_v1
    mws._CaptureWorkerSettings.current=current
    # Module-global wraps of names imported into the listener / worker module.
    # _parse is looked up at call time in meeting_worker_service_v1 globals
    # (parse_request lambda and execute_v1), so wrap that binding.
    _save(mws,'_parse')
    orig_parse=mws._parse
    def wrapped_parse(*args,**kwargs):
        seq=_WRAP.begin('_parse')
        try:
            value=orig_parse(*args,**kwargs)
            _WRAP.ok('_parse',seq)
            return value
        except BaseException as error:
            _WRAP.fail('_parse',error,_frame_code_name(error))
            raise
    mws._parse=wrapped_parse
    for target in ('peer_der_v1','fixed_request_length_v1','read_request_body_v1'):
        _save(listener_mod,target)
        orig=getattr(listener_mod,target)
        def _make(name,fn):
            def wrapped(*args,**kwargs):
                seq=_WRAP.begin(name)
                try:
                    value=fn(*args,**kwargs)
                    _WRAP.ok(name,seq)
                    return value
                except BaseException as error:
                    _WRAP.fail(name,error,_frame_code_name(error))
                    raise
            return wrapped
        setattr(listener_mod,target,_make(target,orig))
    # §1/_request_fence_v1 wrap MUST preserve context-manager protocol
    # (re-yield, re-raise). Fence import pin: listener module line 12.
    _save(listener_mod,'_request_fence_v1')
    orig_fence=listener_mod._request_fence_v1
    from contextlib import contextmanager as _contextmanager
    @_contextmanager
    def wrapped_fence(original_monotonic_end):
        seq=_WRAP.begin('_request_fence_v1')
        entered=False
        try:
            with orig_fence(original_monotonic_end):
                entered=True
                _WRAP.ok('_request_fence_v1',seq)
                try:
                    yield
                except BaseException as error:
                    _WRAP.fail('_request_fence_v1',error,_frame_code_name(error))
                    raise
        except BaseException as error:
            if not entered:
                _WRAP.fail('_request_fence_v1',error,_frame_code_name(error))
            raise
    listener_mod._request_fence_v1=wrapped_fence
    return _restore

def worker_request(u,body,identity='create'):
    context=ssl.create_default_context(cafile=str(u['certs']/'ca.pem'));context.verify_flags|=ssl.VERIFY_X509_STRICT
    context.load_cert_chain(str(u['certs']/(identity+'.pem')),str(u['certs']/(identity+'.key')))
    raw=canonical_bytes(body)
    packet=b'POST /v1/replacement/meetings/worker HTTP/1.1\r\nHost: localhost.localdomain\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: '+str(len(raw)).encode()+b'\r\n\r\n'+raw
    with socket.create_connection(('::1',u['create_server'].server_port),timeout=3) as connected:
        with context.wrap_socket(connected,server_hostname='localhost.localdomain') as tls:
            tls.settimeout(3);tls.sendall(packet);parts=[]
            while True:
                part=tls.recv(65536)
                if not part:break
                parts.append(part)
    wire=b''.join(parts);header,data=wire.split(b'\r\n\r\n',1);status=int(header.split(b' ')[1])
    headers=dict((k.lower(),v.strip()) for k,v in (line.split(b':',1) for line in header.split(b'\r\n')[1:]))
    assert len(data)==int(headers[b'content-length'])
    if status==200:assert headers[b'connection']==b'close'
    if status!=200:assert status==503 and data==b''
    return status,json.loads(data) if data else None,wire

@pytest.mark.parametrize('meeting_sql',[{'capture_seconds':50,'scheduler_poll_seconds':2,'stop_request_seconds':10,'stop_margin_seconds':13}],indirect=True)
def test_actual_independent_V2_processes_Create_to_unattended_STOP_terminal_receipt(unattended,tmp_path):
    # §6: named try/finally from start_unattended() through the early asserts.
    # Pre-child includes the warmup loop (Muse m5). On failure the packet keeps
    # whatever was already written plus pre-child-failure.json naming the step.
    u=None;restore_wraps=None;step='start_unattended';pre_child=True
    def _fail_record(error):
        _write_json_artifact(tmp_path/'pre-child-failure.json',
            dict(step=step,error_type=type(error).__name__,error_message=str(error)))
    try:
        u=start_unattended(unattended);x=u['x'];driver=ROOT/'services/oracle-brain/tests/fixtures/meeting-unattended-driver.mts'
        from oracle_brain.meetings.supervisor_process import observe_supervisor_process_v2
        # §1 wrap installation: after start_unattended() returns, before the
        # first worker_request (covers refused-prepare warmup).
        step='install-wraps'
        restore_wraps=install_wraps()
        step='queue-diagnostic'
        queue_diagnostic=subprocess.run(['/usr/bin/node','--import','tsx',str(driver)],cwd=ROOT,env={**u['env'],'ORACLE2_INVENTED_QUEUE_DIAGNOSTIC':'1'},capture_output=True,timeout=12)
        (tmp_path/'queue-diagnostic.stdout').write_bytes(queue_diagnostic.stdout);(tmp_path/'queue-diagnostic.stderr').write_bytes(queue_diagnostic.stderr)
        assert queue_diagnostic.returncode==0,'actual SAME queue client refused; private diagnostic retained'
        step='cycle-diagnostic'
        cycle_diagnostic=subprocess.run(['/usr/bin/node','--import','tsx',str(driver)],cwd=ROOT,env={**u['env'],'ORACLE2_INVENTED_CYCLE_DIAGNOSTIC':'1'},capture_output=True,timeout=12)
        (tmp_path/'cycle-diagnostic.stdout').write_bytes(cycle_diagnostic.stdout);(tmp_path/'cycle-diagnostic.stderr').write_bytes(cycle_diagnostic.stderr)
        assert cycle_diagnostic.returncode==0,'actual SAME cycle client refused; private diagnostic retained'
        # Read-only warm-up proves actual current loops/queues, never creates a
        # witness, intent or provider effect. No dispatch is retried on failure.
        from oracle_brain.hosting.meeting_supervision_service_v1 import MeetingSupervisionFactoryV1
        step='warmup-queue-reads'
        for name,settings in u['supervisions'].items():
            value=MeetingSupervisionFactoryV1(settings).current_queue_v1(caller_deadline=min(now()+timedelta(seconds=8),settings.current()))
            _write_json_artifact(tmp_path/(name+'-actual-queue.json'),value.model_dump(mode='json'))
        step='refused-prepare-warmup'
        refused=dict(schema_version=1,operation='prepare',operation_id=None,claim_event_id=None,wire_base64=None,error=None,caller_deadline=text(min(now()+timedelta(seconds=15),x['capture_until'])))
        assert worker_request(u,refused,identity='other')[0]==503
        assert worker_request(u,refused|dict(actor_id=str(x['owner'])))[0]==503
        step='sql-zero-asserts'
        with admin(x) as c:
            assert c.execute("SELECT count(*) FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=%s AND action='create_intent'",(x['workspace'],)).fetchone()==(0,)
            assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
        step='child-spawn-ready'
        ready=u['short']/'create-driver-ready'
        actual=u['child'](['/usr/bin/node','--import','tsx',str(driver)],{**u['env'],'ORACLE2_INVENTED_READY_FILE':str(ready)},'actual-create-child',input_pipe=True)
        ready_end=time.monotonic()+5
        while not ready.exists() and actual.poll() is None and time.monotonic()<ready_end:time.sleep(.01)
        assert ready.read_bytes()==b'ready' and actual.poll() is None
        # Warmup loop is inside the named try/finally (Muse m5).
        step='warmup-observations'
        observations=[];attempt=0
        end=time.monotonic()+6;profiles=[InstalledSupervisorProcessV2.model_validate_json(Path(p['path']).read_bytes()) for p in u['process_profiles']]
        while True:
            attempt+=1
            try:
                for profile in profiles:
                    try:observe_supervisor_process_v2(profile,challenge=hashlib.sha256(uuid4().bytes).hexdigest(),deadline=min(now()+timedelta(seconds=5),profile.expires_at))
                    except Exception as error:
                        observations.append(dict(purpose=profile.purpose,error=type(error).__name__,message=str(error)))
                        # n8: cumulative snapshots, one file per attempt N.
                        # Both files are written on every path so the final
                        # warmup-refusals.json equals the last attempt file.
                        _write_json_artifact(tmp_path/('warmup-refusals-attempt-%d.json'%attempt),observations)
                        _write_json_artifact(tmp_path/'warmup-refusals.json',observations)
                        raise
                _write_json_artifact(tmp_path/('warmup-refusals-attempt-%d.json'%attempt),observations)
                _write_json_artifact(tmp_path/'warmup-refusals.json',observations)
                break
            except (PermissionError,ConnectionResetError,BrokenPipeError):
                if time.monotonic()>=end:raise
                time.sleep(.02)
        step='child-wait'
        pre_child=False
        hung=False
        actual.stdin.write(b'go\n');actual.stdin.flush();actual.stdin.close()
        waited=True
        try:
            actual.wait(timeout=12)
            waited=True
        except subprocess.TimeoutExpired:
            waited=False;hung=True
            # §6 TimeoutExpired → record and SIGKILL. Restore stop_runtime chmod.
            try:os.kill(actual.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            try:actual.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
            try:u['stop_runtime'].chmod(u['stop_runtime_old_mode'])
            except Exception:pass
        # M11: post-wait read/redact/rewrite of child stdout (child() writes it
        # directly). Do this AFTER wait so we never race the child's write.
        step='stdout-redact'
        _redact_child_stdout(tmp_path)
        # Fixture-only diagnostic metadata: capture nonsecret status/header
        # fields, stage, exception type, supervisor witness and claim-time state
        # before the assertion so a refusal retains exact evidence without
        # leaking production error detail. No guard change, no retry, no fallback.
        step='collect-diagnostics'
        diag=dict(returncode=actual.returncode,waited=waited,hung=hung)
        if hung:
            diag.update(stage='wait',error_type='TimeoutExpired',error_message='REDACTED')
        try:
            if not hung:
                outcome=json.loads((tmp_path/'actual-create-child.stdout').read_bytes())
                diag.update(stage=outcome.get('stage'),error_type=outcome.get('error_type'),
                    error_message=outcome.get('error_message'),
                    error_cause_type=outcome.get('error_cause_type'),
                    deadline=outcome.get('deadline'),
                    wire_byte_count=outcome.get('wire_byte_count'),
                    wire_sha256=outcome.get('wire_sha256'),
                    exchange_elapsed_wall_ms=outcome.get('exchange_elapsed_wall_ms'),
                    exchange_elapsed_mono_ms=outcome.get('exchange_elapsed_mono_ms'),
                    wall_remaining_at_exchange_ms=outcome.get('wall_remaining_at_exchange_ms'),
                    wall_remaining_at_catch_ms=outcome.get('wall_remaining_at_catch_ms'))
        except Exception as error:
            diag['stdout_parse_error']=type(error).__name__
        try:
            witness_results=[]
            for profile in profiles:
                try:
                    observe_supervisor_process_v2(profile,challenge=hashlib.sha256(uuid4().bytes).hexdigest(),deadline=min(now()+timedelta(seconds=5),profile.expires_at))
                    witness_results.append(dict(purpose=profile.purpose,ok=True))
                except Exception as error:
                    witness_results.append(dict(purpose=profile.purpose,ok=False,error_type=type(error).__name__))
            diag['supervisor_witness']=witness_results
        except Exception as error:
            diag['supervisor_witness_error']=type(error).__name__
        try:
            with admin(x) as c:
                # §4 exact columns: claim_id, original_deadline, created_at,
                # effect, stage. Do NOT select state — it does not exist.
                # Per-query-group try/except so one bad expression cannot wipe
                # all five groups together.
                try:
                    claims=c.execute('SELECT claim_id::text,original_deadline::text,created_at::text,effect,stage,operation_id::text,request_sha256,bot_id::text,worker_id::text FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchall()
                    diag['claim_time']=[dict(claim_id=r[0],original_deadline=r[1],created_at=r[2],effect=r[3],stage=r[4],operation_id=r[5],request_sha256=r[6],bot_id=r[7],worker_id=r[8]) for r in claims]
                except Exception as error:
                    diag['claim_time_error']=type(error).__name__
                try:
                    receipt_count=c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_receipts_v1 r JOIN oracle2.meeting_capture_worker_claims_v1 q USING(claim_id) WHERE q.workspace_id=%s',(x['workspace'],)).fetchone()[0]
                    receipt_rows=c.execute('SELECT q.effect,q.stage,r.wire_object_key,r.wire_sha256,r.wire_byte_count,r.receipt_id::text,r.observation FROM oracle2.meeting_capture_worker_receipts_v1 r JOIN oracle2.meeting_capture_worker_claims_v1 q USING(claim_id) WHERE q.workspace_id=%s',(x['workspace'],)).fetchall()
                    diag['receipts']=dict(count=receipt_count,rows=[dict(effect=r[0],stage=r[1],wire_object_key=r[2],wire_sha256=r[3],wire_byte_count=r[4],receipt_id=r[5],observation=r[6]) for r in receipt_rows])
                except Exception as error:
                    diag['receipts_error']=type(error).__name__
                try:
                    latest=c.execute('SELECT action,payload,created_at::text FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=%s ORDER BY created_at DESC LIMIT 1',(x['workspace'],)).fetchone()
                    diag['latest_event']=dict(action=latest[0],payload=latest[1],created_at=latest[2]) if latest else None
                except Exception as error:
                    diag['latest_event_error']=type(error).__name__
                try:
                    head=c.execute('SELECT state,capture_open,stop_state FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=%s AND meeting_id=%s',(x['workspace'],x['meeting'])).fetchone()
                    diag['head_state']=dict(state=head[0],capture_open=head[1],stop_state=head[2]) if head else None
                except Exception as error:
                    diag['head_state_error']=type(error).__name__
                try:
                    adm=c.execute('SELECT admission_id::text,admission_sha256,role_name,actions,capture_until::text,stop_until::text,original_horizon::text,expires_at::text FROM oracle2.meeting_capture_admissions_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchall()
                    diag['admission_state']=[dict(admission_id=r[0],admission_sha256=r[1],role_name=r[2],actions=list(r[3]),capture_until=r[4],stop_until=r[5],original_horizon=r[6],expires_at=r[7]) for r in adm]
                except Exception as error:
                    diag['admission_state_error']=type(error).__name__
        except Exception as error:
            diag['claim_time_error']=type(error).__name__
        _write_json_artifact(tmp_path/'create-child-diagnostics.json',diag)
        step='returncode-assert'
        if hung:
            assert False,'actual Create child hung; UNKNOWN-cause-hung-child packet retained'
        assert actual.returncode==0,'actual Create child refused; exact private diagnostic retained'
        step='outcome-parse'
        outcome=json.loads((tmp_path/'actual-create-child.stdout').read_bytes());assert outcome['state']=='observed'
        assert outcome['qualification'] is False and outcome['remote_stop_proven'] is False and outcome['resend_authorized'] is False
        assert outcome['request_sha256']==u['body_sha'] and outcome['operation_id']==str(u['operation'])
        step='repeated-claim'
        repeated=dict(schema_version=1,operation='claim',operation_id=outcome['operation_id'],claim_event_id=None,wire_base64=None,error=None,caller_deadline=outcome['deadline'])
        repeated_status,repeated_body,repeated_wire=worker_request(u,repeated)
        if repeated_status==200:assert repeated_body['body_base64'] is None and repeated_body['executable'] is False
        (tmp_path/'actual-repeated-claim.wire').write_bytes(repeated_wire)
        with admin(x) as c:
            assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
            receipt=c.execute('SELECT r.wire_object_key,r.wire_sha256,r.wire_byte_count FROM oracle2.meeting_capture_worker_receipts_v1 r JOIN oracle2.meeting_capture_worker_claims_v1 q USING(claim_id) WHERE q.workspace_id=%s',(x['workspace'],)).fetchone()
        retained=(Path(u['owners']['create']['host'].config.storage_root)/receipt[0]).read_bytes()
        assert len(retained)==receipt[2] and hashlib.sha256(retained).hexdigest()==receipt[1]
        assert retained.endswith(canonical_bytes({'id':str(u['bot'])}))

        # Same own current queue read diagnoses the actual durable state; it cannot
        # retry any effect or manufacture a supervisor observation.
        step='post-create-current-queue'
        try:
            post_create_queue=MeetingSupervisionFactoryV1(u['supervisions']['stop']).current_queue_v1(caller_deadline=min(now()+timedelta(seconds=8),u['supervisions']['stop'].current()))
            _write_json_artifact(tmp_path/'post-create-current-queue.json',post_create_queue.model_dump(mode='json'))
        except Exception as error:
            # Record and continue (base behavior; positives retained). The
            # refusal artifact is the evidence; this diagnostic read cannot
            # retry an effect or manufacture a supervisor observation.
            _write_json_artifact(tmp_path/'post-create-current-queue-refusal.json',dict(error=type(error).__name__,message=str(error)))
        step='terminal-loop'
        end=time.monotonic()+max(0,(x['capture_until']-now()).total_seconds())+3
        terminal=None
        while time.monotonic()<end:
            with admin(x) as c:terminal=c.execute('SELECT state,capture_open,stop_state FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=%s AND meeting_id=%s',(x['workspace'],x['meeting'])).fetchone()
            if terminal[2]=='terminal_observed':break
            assert (now()>=x['capture_until'] or u['scheduler'].poll() is None) and u['stop_process'].poll() is None
            time.sleep(.1)
        # The existing lifecycle label remains unknown after ACK; independent exact
        # terminal receipt does not reopen capture or rewrite that retained label.
        step='terminal-asserts'
        assert terminal==('capture_status_unknown',False,'terminal_observed')
        assert u['provider_seen']==['POST /api/v1/bot/ HTTP/1.1',f'GET /api/v1/bot/{u["bot"]}/ HTTP/1.1',f'POST /api/v1/bot/{u["bot"]}/leave_call/ HTTP/1.1',f'GET /api/v1/bot/{u["bot"]}/ HTTP/1.1']
        with admin(x) as c:
            assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(4,)
            assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_receipts_v1 r JOIN oracle2.meeting_capture_worker_claims_v1 q USING(claim_id) WHERE q.workspace_id=%s',(x['workspace'],)).fetchone()==(4,)
            assert c.execute('SELECT count(*) FROM oracle2.meeting_create_stop_relations_v1 r JOIN oracle2.meeting_capture_events_v1 e ON e.workspace_id=r.workspace_id AND e.meeting_id=r.meeting_id WHERE r.mapping_id=%s AND e.action=%s AND r.installed_at<e.created_at',(u['relation'].mapping_id,'invite')).fetchone()==(1,)
            assert c.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
            wires=c.execute('SELECT q.effect,q.stage,r.wire_object_key,r.wire_sha256,r.wire_byte_count,r.receipt_id,r.observation FROM oracle2.meeting_capture_worker_receipts_v1 r JOIN oracle2.meeting_capture_worker_claims_v1 q USING(claim_id) WHERE q.workspace_id=%s',(x['workspace'],)).fetchall()
            terminal_event=c.execute("SELECT payload FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=%s AND action='stop_reconciled'",(x['workspace'],)).fetchone()[0]
        assert len(wires)==4
        for effect,stage,key,seal,count,receipt_id,observation in wires:
            owner='create' if effect=='capture-create' else 'stop' if effect=='capture-leave' else 'pre' if stage=='pre-stop-consistency' else 'post'
            retained_path=Path(u['owners'][owner]['host'].config.storage_root)/key
            raw=retained_path.read_bytes();assert not retained_path.is_symlink() and retained_path.stat().st_mode&0o077==0
            assert len(raw)==count and hashlib.sha256(raw).hexdigest()==seal
            header,body=raw.split(b'\r\n\r\n',1)
            lengths=[int(v.split(b':',1)[1]) for v in header.split(b'\r\n') if v.lower().startswith(b'content-length:')]
            assert lengths==[len(body)] and b'Connection: close' in header
            if stage=='post-stop-terminal':
                assert observation['kind']=='metadata-observed' and observation['complete'] is True
                assert observation['latest_status']['code']=='call_ended'
                assert terminal_event['terminal_event_id']==str(receipt_id)
                assert terminal_event['metadata_sha256']==hashlib.sha256(body).hexdigest()==observation['metadata_sha256']

        step='unattended-outcome'
        _write_json_artifact(tmp_path/'actual-unattended-outcome.json',{'head':terminal,'provider_routes':u['provider_seen'],'source_qualification':False,'installation_proven':False})
    except BaseException as error:
        if pre_child:_fail_record(error)
        raise
    finally:
        if restore_wraps is not None:
            try:restore_wraps()
            except Exception:pass

def _redact_child_stdout(tmp_path):
    """M11 fixture post-pass: parse the driver's canonicalJson stdout line and
    run redact_record before the file is finalized. A line that does not parse
    is written as the UnparsedStdout template (stage UNKNOWN, no unbound
    <stage>); the raw bytes are not kept."""
    path=tmp_path/'actual-create-child.stdout'
    if not path.exists():return
    raw=path.read_bytes()
    try:
        record=json.loads(raw)
        if not isinstance(record,dict):raise ValueError('not an object')
        _write_json_artifact(path,record)
    except Exception:
        _write_json_artifact(path,dict(state='UNKNOWN',stage='UNKNOWN',error_type='UnparsedStdout',raw_kind='unlisted'))

@pytest.mark.parametrize('meeting_sql',[{'capture_seconds':40,'scheduler_poll_seconds':2,'stop_request_seconds':10,'stop_margin_seconds':13}],indirect=True)
def test_actual_producer_death_refuses_Create_before_any_provider_HTTP(unattended,tmp_path):
    u=start_unattended(unattended);u['producer'].terminate();u['producer'].wait(timeout=4)
    driver=ROOT/'services/oracle-brain/tests/fixtures/meeting-unattended-driver.mts'
    result=subprocess.run(['/usr/bin/node','--import','tsx',str(driver)],cwd=ROOT,env=u['env'],capture_output=True,timeout=10)
    (tmp_path/'dead-producer-child.stdout').write_bytes(result.stdout);(tmp_path/'dead-producer-child.stderr').write_bytes(result.stderr)
    assert result.returncode!=0 and u['provider_seen']==[]
    with admin(u['x']) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(u['x']['workspace'],)).fetchone()==(0,)
