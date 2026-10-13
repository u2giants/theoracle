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
    packet=stage_packet(APP,SOURCE,IMAGE,2000,now=1000)
    commands=packet['body']['docker_compose_custom_start_command'].split(' && ')
    assert len(commands)==4
    for command in commands:
        assert '--project-directory /data/coolify/applications/'+APP in command
        assert '-f /data/coolify/applications/'+APP+'/docker-compose.yaml' in command
        assert '--env-file /data/coolify/applications/'+APP+'/.env' in command
        assert command.startswith('timeout -s TERM -k 5 ')
        assert '$' not in command and ';' not in command
    assert commands[0].endswith(' create')
    assert commands[1].endswith(' start '+' '.join(BOOTSTRAPS))
    assert commands[2].endswith(' wait '+' '.join(BOOTSTRAPS))
    assert commands[3].endswith(' start '+' '.join(STORES))
    assert all(role not in command.split(' start ')[-1].split() for command in commands[1:] for role in ('ledger-init','gateway','executor','synthetic-project'))

@pytest.mark.parametrize('app',["../../foreign",'x; reboot','vhmcdkdk23dgvjvcvhyhcjzd','x'*41,''])
def test_foreign_paths_commands_old_app_denied(app):
    with pytest.raises(PermissionError):stage_packet(app,SOURCE,IMAGE,2000,now=1000)

@pytest.mark.parametrize('expiry',[1000,1300,1299])
def test_original_lifetime_boundary_denied(expiry):
    with pytest.raises(PermissionError):stage_packet(APP,SOURCE,IMAGE,expiry,now=1000)

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

def test_actual_local_compose_wait_refuses_failed_bootstrap(tmp_path):
    # Public one-shot tools only, no auth/stores/mounts/network and no image pull.
    import uuid
    project='oracle-source-wait-'+uuid.uuid4().hex
    image='postgres:16.10-alpine@sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297'
    path=tmp_path/'compose.yaml';path.write_text(yaml.safe_dump({'services':{'pass':{'image':image,'entrypoint':['/bin/true'],'network_mode':'none'},'fail':{'image':image,'entrypoint':['/bin/false'],'network_mode':'none'}}}))
    base=['docker','compose','--project-name',project,'-f',str(path)]
    def run(args):return subprocess.run(base+args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    try:
        assert run(['create','--pull','never']).returncode==0
        assert run(['start']).returncode==0
        result=run(['wait','pass','fail'])
        assert result.returncode!=0,'Compose wait must reject failed bootstrap before any storage start'
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
                if p.returncode==0:ready=True;break
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
