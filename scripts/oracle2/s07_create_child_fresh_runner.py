"""Fail-closed S07 fresh-invented runner packet (plan v5 design a).

Owns the runner sequence: source-before.json, owned Compose up, TLS bootstrap,
canonical schema receipt s07fresh-schema.json, exact pytest invocation pins,
source-after.json, artifact-index.json, cleanup proof. Infra failure writes
infra-failed.json and does not consume the one-fresh budget.

Invocation pins (M6): cwd = worktree root for runner and pytest;
PYTHONPATH="<WORKTREE_ROOT>:<WORKTREE_ROOT>/services/oracle-brain";
pytest is sys.executable -m pytest with --basetemp and -p no:cacheprovider
(never bare pytest). Basetemp layout: enumerate pytest-generated subdirs;
do not assume testid names.

HEAD pin: refuse a dirty worktree or a mismatched EXPECTED_HEAD before the
one-fresh budget is consumed. PYTHONHOME is NOT exported to the venv pytest
invocation (it can skew stdlib/site resolution under a venv interpreter).

pytest stdout/stderr are captured into pytest-output.stdout/.stderr and the
returncode is recorded; the subprocess is bounded by PYTEST_TIMEOUT_SECONDS.

No company originals, no production, no paid providers. Business-acceptance hold.
"""
from __future__ import annotations
import hashlib,json,os,re,stat,subprocess,sys,traceback
from pathlib import Path
from uuid import uuid4

EXCLUDE_DIRS={'.git'}
# Bound on the single pytest invocation (seconds). The S07 child wait is 12 s
# and meeting_sql capture_seconds is 50; 600 s covers the full selector with
# margin for Compose-backed setup without hanging forever.
PYTEST_TIMEOUT_SECONDS=600
INDEX_MEMBERS=[
 'actual-create-child.stdout','actual-create-child.stderr','create-child-diagnostics.json',
 'create-server-responses.jsonl','actual-provider-routes.json','actual-observer-refusals.json',
 'actual-observer-process-observations.json','owned-process-cleanup.json','actual-selected-state.json',
 'queue-diagnostic.stdout','queue-diagnostic.stderr','cycle-diagnostic.stdout','cycle-diagnostic.stderr',
 'scheduler-actual-queue.json','stop-actual-queue.json','warmup-refusals.json',
 'post-create-current-queue.json','post-create-current-queue-refusal.json',
 'actual-repeated-claim.wire','actual-unattended-outcome.json',
 'source-before.json','source-after.json','runner-environment.json','s07fresh-schema.json',
 'supervision-scope.json','replay-spool','pre-child-failure.json','infra-failed.json',
 'teardown-steps.json','replay-spool-manifest.json',
 'pytest-output.stdout','pytest-output.stderr','pytest-returncode.json',
]

def _sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()

def _mode(path:Path)->str:
    return format(stat.S_IMODE(path.stat().st_mode),'04o')

def snapshot(root:Path)->dict:
    files=[]
    for p in sorted(root.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(root).as_posix()
        if rel.split('/',1)[0] in EXCLUDE_DIRS:continue
        files.append(dict(path=rel,sha256=_sha256(p),mode=_mode(p)))
    files.sort(key=lambda r:r['path'])
    return dict(root=str(root.resolve()),files=files)

def _write(path:Path,obj)->None:
    path.write_text(json.dumps(obj,sort_keys=True,indent=2),encoding='utf-8')

def _run(*args,env=None,cwd=None)->str:
    return subprocess.check_output(list(args),env=env,cwd=cwd,text=True,stderr=subprocess.PIPE,timeout=120)

def _write_index(runner_dir:Path)->None:
    members=[];named=set()
    pytest_tmp=runner_dir/'pytest-tmp'
    discovered=set()
    if pytest_tmp.is_dir():
        # m6/m7: enumerate pytest-generated subdirs; do not assume testid names.
        for child in sorted(pytest_tmp.iterdir()):
            if child.is_dir():
                for p in sorted(child.rglob('*')):
                    if p.is_file():discovered.add(p.relative_to(runner_dir).as_posix())
            elif child.is_file():
                discovered.add(child.relative_to(runner_dir).as_posix())
    for name in INDEX_MEMBERS:
        if name=='replay-spool':
            hits=[]
            if pytest_tmp.is_dir():
                hits=[p for p in sorted(pytest_tmp.rglob('replay-spool/*')) if p.is_file()]
            if hits:
                for p in hits:
                    members.append(dict(path=p.relative_to(runner_dir).as_posix(),sha256=_sha256(p),mode=_mode(p),present=True,note=''))
                    named.add(p.relative_to(runner_dir).as_posix())
            else:
                members.append(dict(path='replay-spool',sha256='',mode='0000',present=False,note='absent'))
            continue
        candidates=[runner_dir/name]
        if pytest_tmp.is_dir():candidates.extend(sorted(pytest_tmp.rglob(name)))
        hit=next((c for c in candidates if c.is_file()),None)
        if hit is not None:
            named.add(hit.relative_to(runner_dir).as_posix())
            members.append(dict(path=hit.relative_to(runner_dir).as_posix(),sha256=_sha256(hit),mode=_mode(hit),present=True,note=''))
        else:
            members.append(dict(path=name,sha256='',mode='0000',present=False,note='absent'))
    for rel in sorted(discovered-named):
        p=runner_dir/rel
        if p.is_file():
            note='cumulative snapshot' if rel.rsplit('/',1)[-1].startswith('warmup-refusals-attempt-') else ''
            members.append(dict(path=rel,sha256=_sha256(p),mode=_mode(p),present=True,note=note))
    members.sort(key=lambda m:m['path'])
    _write(runner_dir/'artifact-index.json',dict(root=str(runner_dir.resolve()),members=members))

def _redact_stream(data:bytes,worktree:Path)->str:
    '''Redact path tokens in captured free-form streams (pytest output).'''
    try:
        tests=worktree/'services/oracle-brain/tests'
        if str(tests) not in sys.path:sys.path.insert(0,str(tests))
        from meeting_unattended_redact import redact_text
        return redact_text(data.decode('utf-8','replace'))
    except Exception:
        return 'REDACTED'

def _redact_infra_message(message:str,worktree:Path|None=None)->str:
    """Keep infra-failed.json free of paths/hosts; reuse the fixture allow-list."""
    try:
        root=worktree if worktree is not None else Path(__file__).resolve().parents[2]
        tests=root/'services/oracle-brain/tests'
        if str(tests) not in sys.path:
            sys.path.insert(0,str(tests))
        from meeting_unattended_redact import redact_record
        return redact_record(dict(message=message)).get('message','REDACTED')
    except Exception:
        return 'REDACTED'

def main(argv)->int:
    if len(argv) not in (3,4):
        print('usage: s07_create_child_fresh_runner.py RUNNER_DIR WORKTREE [EXPECTED_HEAD]',file=sys.stderr)
        return 2
    runner_dir=Path(argv[1]).resolve();worktree=Path(argv[2]).resolve()
    expected_head=argv[3] if len(argv)==4 else None
    runner_dir.mkdir(parents=True,exist_ok=True)
    step='head-pin'
    project='';container=''
    try:
        if not (worktree/'services/oracle-brain/tests/test_meeting_unattended_sql.py').is_file():
            raise RuntimeError('worktree missing S07 test module')
        head=subprocess.check_output(['git','-C',str(worktree),'rev-parse','HEAD'],text=True,timeout=30).strip()
        dirty=subprocess.check_output(['git','-C',str(worktree),'status','--porcelain'],text=True,timeout=30).strip()
        if dirty:
            raise RuntimeError('worktree dirty; refusing to consume the one-fresh budget')
        if expected_head is not None and head!=expected_head:
            raise RuntimeError('HEAD mismatch: expected '+expected_head+' got '+head)
        step='source-before'
        _write(runner_dir/'source-before.json',snapshot(worktree))
        # M6 pins exported to the runner and every child. PYTHONHOME is
        # deliberately NOT exported: under a venv interpreter it can skew
        # stdlib/site resolution for the pytest child.
        pythonpath=os.pathsep.join([str(worktree),str(worktree/'services/oracle-brain')])
        env={**os.environ,'PYTHONPATH':pythonpath,'PYTHONDONTWRITEBYTECODE':'1'}
        env.pop('PYTHONHOME',None)  # never inherit; pin is pythonhome_exported: False
        # Owned Compose project. UUID lowercase (test_worker_postgres_fixture regex).
        project='oracle2-synthetic-s07f-'+uuid4().hex[:24]  # container DNS name (project-postgres-1) must fit OpenSSL 64-char CN
        env['COMPOSE_PROJECT_NAME']=project
        env['ORACLE2_POSTGRES_PORT']='0'
        step='compose-up'
        compose=['docker','compose','-f',str(worktree/'dev/oracle2/compose.yaml'),'-p',project]
        _run(*compose,'up','-d','--wait','postgres',env=env,cwd=str(worktree))
        container=_run(*compose,'ps','-q','postgres',env=env,cwd=str(worktree)).strip()
        if not re.fullmatch(r'[0-9a-f]{64}',container):
            raise RuntimeError('exact owned postgres container identity required')
        env['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER']=container
        details=json.loads(_run('docker','inspect',container))[0]
        ports=details['NetworkSettings']['Ports'].get('5432/tcp') or []
        if len(ports)!=1 or ports[0]['HostIp']!='127.0.0.1':
            raise RuntimeError('loopback-only postgres port required')
        plain_url='postgresql://oracle2_admin:oracle2_local_admin_only@127.0.0.1:'+str(ports[0]['HostPort'])+'/oracle2'
        step='tls-bootstrap'
        sys.path.insert(0,str(worktree))
        from dev.oracle2.test_tls_bootstrap import bootstrap
        tls=bootstrap(container,plain_url,runner_dir/'tls')
        env.update(tls)
        admin_url=tls['ORACLE2_TEST_ADMIN_URL']
        step='schema-bootstrap'
        from dev.oracle2.test_canonical_schema import bootstrap_canonical_test_schema
        receipt=bootstrap_canonical_test_schema(admin_url,container_id=container,receipt_path=runner_dir/'s07fresh-schema.json')
        env['ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT']=str(runner_dir/'s07fresh-schema.json')
        if (runner_dir/'s07fresh-schema.json').is_file():
            env['ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT_SHA256']=_sha256(runner_dir/'s07fresh-schema.json')
        # Build the exact pytest invocation BEFORE recording it so the pin is complete.
        pytest_tmp=runner_dir/'pytest-tmp'
        pytest_cmd=[sys.executable,'-m','pytest',
             'services/oracle-brain/tests/test_meeting_unattended_sql.py::test_actual_independent_V2_processes_Create_to_unattended_STOP_terminal_receipt',
             '-q','--tb=short',
             '--basetemp='+str(pytest_tmp),
             '-p','no:cacheprovider']
        _write(runner_dir/'runner-environment.json',dict(
            cwd=str(worktree),PYTHONPATH=pythonpath,
            python_executable=sys.executable,
            pytest_invocation=' '.join(pytest_cmd),
            python_version=sys.version,
            compose_project=project,container=container,
            basetemp=str(runner_dir/'pytest-tmp'),
            cacheprovider_disabled=True,
            head=head,
            expected_head=expected_head,
            pytest_timeout_seconds=PYTEST_TIMEOUT_SECONDS,
            pythonhome_exported=False,
        ))
        step='pytest'
        pytest_tmp.mkdir(parents=True,exist_ok=True)
        proc=subprocess.run(pytest_cmd,cwd=str(worktree),env=env,capture_output=True,timeout=PYTEST_TIMEOUT_SECONDS)
        # Minor 19: path tokens in captured pytest output must not enter the packet raw.
        (runner_dir/'pytest-output.stdout').write_text(_redact_stream(proc.stdout or b'',worktree),encoding='utf-8')
        (runner_dir/'pytest-output.stderr').write_text(_redact_stream(proc.stderr or b'',worktree),encoding='utf-8')
        _write(runner_dir/'pytest-returncode.json',dict(returncode=proc.returncode))
        step='source-after'
        _write(runner_dir/'source-after.json',snapshot(worktree))
        step='cleanup-proof'
        cleanup={}
        try:
            _run(*compose,'down','--volumes',env=env,cwd=str(worktree))
            for key,filt in (('containers','docker ps -aq'),('networks','docker network ls -q'),('volumes','docker volume ls -q')):
                out=_run('docker',*filt.split()[1:],'--filter','label=com.docker.compose.project='+project)
                cleanup[key+'_absent']=not out.strip()
            cleanup['absence_proven']=all(cleanup[k] for k in ('containers_absent','networks_absent','volumes_absent'))
        except Exception as error:
            cleanup['absence_proven']=False
            cleanup['cleanup_error']=type(error).__name__
        env_doc=json.loads((runner_dir/'runner-environment.json').read_text())
        env_doc['cleanup_proof']=cleanup
        _write(runner_dir/'runner-environment.json',env_doc)
        step='artifact-index'
        _write_index(runner_dir)
        return proc.returncode
    except BaseException as error:
        try:_write(runner_dir/'infra-failed.json',dict(step=step,error_type=type(error).__name__,error_message=_redact_infra_message(str(error),worktree)))
        except Exception:pass
        if project:
            try:
                env={**os.environ,'COMPOSE_PROJECT_NAME':project,'ORACLE2_POSTGRES_PORT':'0'}
                _run('docker','compose','-f',str(worktree/'dev/oracle2/compose.yaml'),'-p',project,'down','--volumes',env=env,cwd=str(worktree))
            except Exception:pass
        try:_write_index(runner_dir)
        except Exception:pass
        traceback.print_exc()
        return 1

if __name__=='__main__':
    raise SystemExit(main(sys.argv))
