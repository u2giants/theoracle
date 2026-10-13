"""Platform translation checks never issue a certificate or credential."""
import ast
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[3]
HOSTING=ROOT/'dev/oracle2/hosting'


def test_every_emitted_bundle_matches_raw_compose():
    tree=ast.parse((HOSTING/'prepare_synthetic.py').read_text())
    assignments=[n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='env_profile' for t in n.targets)]
    expression=ast.Expression(assignments[0].value)
    from oracle_brain.hosting.bootstrap import FILES
    emitted=set()
    for profile in FILES:
        prefix=eval(compile(expression,'<fixed issuer mapping>','eval'),{'profile':profile})
        emitted|={'ORACLE_'+prefix+'_BUNDLE','ORACLE_'+prefix+'_BUNDLE_SHA256'}
    consumed=set(re.findall(r'\$\{(ORACLE_\w+_BUNDLE(?:_SHA256)?)', (HOSTING/'coolify-synthetic.yaml').read_text()))
    assert emitted==consumed


def test_router_and_external_network_interpolate_same_app_identity():
    source=(HOSTING/'coolify-synthetic.yaml').read_text()
    names=set(re.findall(r'\$\{([A-Z0-9_]+)',source))
    env={**os.environ,**{n:'invented-placeholder' for n in names}}
    # CI's local stack identity must not override the managed YAML namespace.
    env.pop('COMPOSE_PROJECT_NAME',None)
    env.update(ORACLE_LEDGER_IPV4_SUBNET='172.30.42.0/24',ORACLE_LEDGER_IPV6_SUBNET='fd42:6f72:6163:42::/64',ORACLE_HOSTING_IMAGE='ghcr.io/u2giants/theoracle-native@sha256:'+'a'*64,COOLIFY_RESOURCE_UUID='syntheticownedapp',ORACLE_GATEWAY_HOST='oracle-native-acceptance.178.156.180.212.sslip.io')
    result=subprocess.run(['docker','compose','-f',str(HOSTING/'coolify-synthetic.yaml'),'config','--format','json'],env=env,capture_output=True,check=True)
    config=json.loads(result.stdout)
    assert config['name']=='oracle-native-syntheticownedapp'
    assert config['networks']['ledger']['ipam']['config']==[{'subnet':'172.30.42.0/24'},{'subnet':'fd42:6f72:6163:42::/64'}]
    labels=config['services']['gateway']['labels']
    assert labels['traefik.tcp.routers.oracle-syntheticownedapp.service']=='oracle-syntheticownedapp'
    assert labels['traefik.tcp.routers.oracle-syntheticownedapp.rule']=='HostSNI(`'+env['ORACLE_GATEWAY_HOST']+'`)'
    assert labels['traefik.docker.network']==config['networks']['ingress']['name']=='syntheticownedapp'
    assert all('ingress' not in v.get('networks',{}) for k,v in config['services'].items() if k!='gateway')


def test_public_gateway_san_and_platform_environment_are_bound_without_issuance():
    source=(HOSTING/'prepare_synthetic.py').read_text()
    assert "folder=='gateway' and args.gateway_host!='gateway'" in source
    assert "x509.DNSName(args.gateway_host)" in source
    assert "'ORACLE_HOSTING_IMAGE':args.image" in source
    assert "'ORACLE_GATEWAY_HOST':args.gateway_host" in source


def test_private_issuer_ranges_denied_before_any_issuance(tmp_path):
    import importlib.util
    import pytest
    spec=importlib.util.spec_from_file_location('owned_synthetic_issuer',HOSTING/'prepare_synthetic.py')
    issuer=importlib.util.module_from_spec(spec);spec.loader.exec_module(issuer)
    for family,value in [('ipv4','8.8.8.0/24'),('ipv4','172.30.42.0/16'),('ipv6','2001:4860::/64'),('ipv6','fd42::/48')]:
        directory=tmp_path/(family+value.replace('/','_').replace(':','_'))
        with pytest.raises(ValueError):issuer.main(['--directory',str(directory),'--image','sha256:'+'a'*64,
            '--runtime-hash','a'*64,'--review-hash','a'*64,'--synthetic','--ledger-'+family+'-subnet',value])
        assert not directory.exists()
