"""Fixed public source compilation; no platform requests or credentials."""
import importlib.util,subprocess,sys
from pathlib import Path
import pytest,yaml
ROOT=Path(__file__).resolve().parents[3]
HOSTING=ROOT/'dev/oracle2/hosting'
sys.path.insert(0,str(HOSTING))
from prepare_restore_platform import stage_packet,create_packet,BOOTSTRAPS,STORES
APP='newrestoreapplication0001';SOURCE='c'*40;IMAGE='ghcr.io/u2giants/theoracle-native@sha256:'+'d'*64

def test_exact_create_and_all_chained_commands_bound_to_same_platform_paths():
    create=create_packet('project','environment',SOURCE,IMAGE)
    assert create['body']['instant_deploy'] is False and create['body']['docker_compose_location'].endswith('coolify-forward-restore.yaml')
    packet=stage_packet(APP,SOURCE,IMAGE,2000,2000,'e'*64,now=1000)
    import re
    raw=packet['body']['docker_compose_custom_start_command']
    guards=re.findall(r"/bin/sh -c 'test [0-9]+ -gt \$\(/bin/date \+%s\) && test [0-9]+ -gt \$\(/bin/date \+%s\)'",raw)
    assert len(guards)==len(BOOTSTRAPS)+3
    commands=re.split(r"/bin/sh -c 'test [0-9]+ -gt \$\(/bin/date \+%s\) && test [0-9]+ -gt \$\(/bin/date \+%s\)' && ",raw)[1:]
    commands=[x.removesuffix(' && ') for x in commands]
    assert len(commands)==len(BOOTSTRAPS)+3
    for command in commands:
        assert '--project-directory /data/coolify/applications/'+APP in command
        assert '-f /data/coolify/applications/'+APP+'/docker-compose.yaml' in command
        assert '--env-file /data/coolify/applications/'+APP+'/.env' in command
        assert command.startswith('timeout -s TERM -k 5 ')
        if ' wait ' not in command:assert '$' not in command and ';' not in command
    assert commands[0].endswith(' create')
    assert commands[1].endswith(' start '+' '.join(BOOTSTRAPS))
    assert all((' wait '+role+' >/dev/null 2>&1; test ') in command and command.endswith(' '+role+')" = exited:0\'') for command,role in zip(commands[2:-1],BOOTSTRAPS))
    assert commands[-1].endswith(' start '+' '.join(STORES))
    assert all(role not in command.split(' start ')[-1].split() for command in commands[1:] for role in ('ledger-init','gateway','executor','synthetic-project'))

@pytest.mark.parametrize('app',["../../foreign",'x; reboot','vhmcdkdk23dgvjvcvhyhcjzd','x'*41,''])
def test_foreign_paths_commands_old_app_denied(app):
    with pytest.raises(PermissionError):stage_packet(app,SOURCE,IMAGE,2000,2000,'e'*64,now=1000)

@pytest.mark.parametrize('expiry',[1000,1300,1299])
def test_original_lifetime_boundary_denied(expiry):
    with pytest.raises(PermissionError):stage_packet(APP,SOURCE,IMAGE,expiry,2000,'e'*64,now=1000)

def test_restore_compose_preserves_all18_and_never_mounts_or_starts_seed():
    original=yaml.safe_load((HOSTING/'coolify-synthetic.yaml').read_text());restore=yaml.safe_load((HOSTING/'coolify-forward-restore.yaml').read_text())
    assert set(restore['services'])==set(original['services']) and len(restore['services'])==18
    assert restore['networks']==original['networks'] and restore['volumes']==original['volumes']
    for role in restore['services']:
        if role!='ledger':assert restore['services'][role]==original['services'][role]
    ledger=restore['services']['ledger'];assert not any('/docker-entrypoint-initdb.d' in m for m in ledger['volumes'])
    assert 'ledger-init' not in ledger['depends_on']
    assert 'NOT EXISTS' in ledger['healthcheck']['test'][-1] and 'public-invented-remote-forward-v2' in ledger['healthcheck']['test'][-1]
    assert all(restore['services'][r]['network_mode']=='none' for r in BOOTSTRAPS)
    assert set(BOOTSTRAPS)==set(restore['services'])-set(STORES)-{'ledger-init','gateway','executor','synthetic-project'}

@pytest.mark.parametrize('failed_role',[BOOTSTRAPS[0],BOOTSTRAPS[-1],None])
def test_actual_generated_chain_requires_every_bootstrap_before_storage(tmp_path,failed_role):
    # Execute the generated chain locally: either failure ordering must prevent
    # all stores, while all successful bootstraps must preserve store startup.
    import uuid,time,shlex
    project='oracle-source-wait-'+uuid.uuid4().hex
    image='postgres:16.10-alpine@sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297'
    services={role:{'image':image,'entrypoint':['/bin/false' if role==failed_role else '/bin/true'],'network_mode':'none'} for role in (*BOOTSTRAPS,*STORES)}
    path=tmp_path/'compose.yaml';path.write_text(yaml.safe_dump({'services':services}))
    base=['docker','compose','--project-name',project,'-f',str(path)]
    def run(args):return subprocess.run(base+args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    directory='/data/coolify/applications/'+APP
    platform='docker compose --project-directory '+directory+' -f '+directory+'/docker-compose.yaml --env-file '+directory+'/.env'
    epoch=int(time.time());packet=stage_packet(APP,SOURCE,IMAGE,epoch+1000,epoch+1000,'e'*64,now=epoch)
    chain=packet['body']['docker_compose_custom_start_command'].replace(platform,shlex.join(base))
    try:
        assert run(['create','--pull','never']).returncode==0
        result=subprocess.run(['sh','-c',chain],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90)
        assert (result.returncode==0)==(failed_role is None)
        for store in STORES:
            identity=run(['ps','--all','-q',store]);assert identity.returncode==0
            state=subprocess.run(['docker','inspect','--format','{{.State.Status}}',identity.stdout.decode().strip()],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
            assert state.returncode==0
            assert state.stdout.strip()!=(b'created') if failed_role is None else state.stdout.strip()==b'created'
    finally:assert run(['down']).returncode==0

def test_actual_local_empty_postgres_custom_dump_roles_only_restore(tmp_path):
    """Two private networkless local test instances, zero seed on restore target."""
    import json,time,uuid
    from test_hosting_synthetic_fixture import parameters
    from oracle_brain.hosting.synthetic_fixture import fixed_scenario,FORWARD_SCENARIO
    from oracle_brain.hosting.synthetic_seed import compile_seed,compile_restore_roles
    image='postgres:16.10-alpine@sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297'
    names=['oracle-source-empty-restore-'+uuid.uuid4().hex for _ in range(2)]
    def command(args,data=None):
        p=subprocess.run(['docker',*args],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        assert p.returncode==0,'bounded local PostgreSQL qualification command failed'
        return p.stdout
    def sql(name,text):return command(['exec','-i',name,'psql','-X','-q','-A','-t','-v','ON_ERROR_STOP=1','-U','oracle_bootstrap','-d','oracle_synthetic'],text.encode())
    try:
        for name in names:
            command(['run','-d','--pull','never','--name',name,'--network','none','-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_USER=oracle_bootstrap','-e','POSTGRES_DB=oracle_synthetic',image])
            ready=False
            for _ in range(30):
                p=subprocess.run(['docker','exec',name,'pg_isready','-U','oracle_bootstrap','-d','oracle_synthetic'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
                if p.returncode==0:
                    pid=subprocess.run(['docker','exec',name,'cat','/proc/1/comm'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=3)
                    if pid.returncode==0 and pid.stdout.strip()==b'postgres':ready=True;break
                time.sleep(.2)
            assert ready
        source,target=names
        assert sql(target,"SELECT NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_toast' AND c.relkind IN ('r','p','v','m','S')); ").strip()==b't'
        sqlroot=ROOT/'services/oracle-brain/sql'
        for file in ('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql','006_hosting_gateway_authority.sql','007_hosting_candidate_permissions.sql','008_hosting_runtime_permissions.sql','009_hosting_result_permissions.sql','010_hosting_job_permissions.sql'):
            sql(source,(sqlroot/file).read_text())
        params=parameters();scenario=fixed_scenario(FORWARD_SCENARIO);params.update(synthetic_scenario=FORWARD_SCENARIO,synthetic_scenario_seal=scenario.seal())
        seed,_,_,_=compile_seed(params);sql(source,seed)
        sql(source,"CREATE TABLE public.invented_result_bytes(value bytea NOT NULL); INSERT INTO public.invented_result_bytes VALUES (decode('7b22696e76656e746564223a747275657d','hex')); ")
        dump=command(['exec',source,'pg_dump','--format=custom','-U','oracle_bootstrap','-d','oracle_synthetic']);assert dump.startswith(b'PGDMP')
        sql(target,compile_restore_roles(params))
        command(['exec','-i',target,'pg_restore','--exit-on-error','--single-transaction','-U','oracle_bootstrap','-d','oracle_synthetic'],dump)
        assert sql(target,"SELECT marker FROM oracle2.synthetic_hosting_marker;").strip()==b'public-invented-remote-forward-v2'
        assert sql(target,"SELECT encode(value,'hex') FROM public.invented_result_bytes;").strip()==b'7b22696e76656e746564223a747275657d'
        assert sql(target,"SELECT count(*) FROM oracle2.operating_view_runs;")==sql(source,"SELECT count(*) FROM oracle2.operating_view_runs;")
    finally:
        for name in names:
            subprocess.run(['docker','rm','-f','-v',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)

@pytest.mark.parametrize('field,value',[('authority',True),('authority','2000'),('reviewer',True),('reviewer',0),('reviewer',1300),('report','not-a-report')])
def test_no_caller_script_or_invalid_expiry_lease(field,value):
    args={'authority':2000,'reviewer':2000,'report':'e'*64};args[field]=value
    with pytest.raises(PermissionError):stage_packet(APP,SOURCE,IMAGE,args['authority'],args['reviewer'],args['report'],now=1000)


def test_actual_execution_prefix_valid_expired_and_queue_delay_never_dispatches(tmp_path):
    import re,time
    epoch=int(time.time())
    valid=stage_packet(APP,SOURCE,IMAGE,epoch+1000,epoch+1000,'e'*64,now=epoch)
    guards=re.findall(r"/bin/sh -c 'test [0-9]+ -gt \$\(/bin/date \+%s\) && test [0-9]+ -gt \$\(/bin/date \+%s\)'",valid['body']['docker_compose_custom_start_command'])
    assert len(guards)==len(BOOTSTRAPS)+3
    for guard in guards:assert subprocess.run(['sh','-c',guard],timeout=2).returncode==0
    delayed=stage_packet(APP,SOURCE,IMAGE,epoch+301,epoch+1000,'e'*64,now=epoch)
    first=re.findall(r"/bin/sh -c 'test [0-9]+ -gt \$\(/bin/date \+%s\) && test [0-9]+ -gt \$\(/bin/date \+%s\)'",delayed['body']['docker_compose_custom_start_command'])[0]
    time.sleep(2)
    marker=tmp_path/'must-not-dispatch'
    result=subprocess.run(['sh','-c',first+' && touch '+str(marker)],timeout=2)
    assert result.returncode!=0 and not marker.exists()
    # Separately expired review lease fails even with unchanged live authority.
    review_expired="/bin/sh -c 'test "+str(epoch+1000)+" -gt $(/bin/date +%s) && test 1 -gt $(/bin/date +%s)'"
    assert subprocess.run(['sh','-c',review_expired+' && touch '+str(marker)],timeout=2).returncode!=0 and not marker.exists()
    assert valid['authorizing'] is False
