#!/usr/bin/env python3
"""Create one invented graph and a new exact-namespace read-only native ACL."""
import argparse,asyncio,json,os,re,secrets,subprocess,sys
from pathlib import Path
from urllib.parse import quote,urlparse
from uuid import uuid4
import redis

IDENTITY=re.compile('oracle_ro_fixture_(?:graph_|user_)[0-9a-f]{32}')

def inspect(container):
    return json.loads(subprocess.check_output(['docker','inspect',container],text=True,stderr=subprocess.PIPE,timeout=15))[0]

def initialize(container,admin_url,directory,*,graph_name=None,username=None):
    details=inspect(container);params=urlparse(admin_url)
    ports=details['NetworkSettings']['Ports'].get('6379/tcp') or []
    project=os.environ.get('COMPOSE_PROJECT_NAME','')
    labels=details['Config'].get('Labels',{})
    networks=details['NetworkSettings'].get('Networks',{})
    if (not re.fullmatch(r'oracle2-(?:ci|synthetic)-[a-z0-9-]{1,80}',project) or labels.get('com.docker.compose.project')!=project
        or labels.get('com.docker.compose.service')!='falkor-candidate' or set(networks)!={project+'_default'}):
        raise PermissionError('exact owned synthetic Compose project and network required')
    if (details['Config'].get('Labels',{}).get('oracle.operating.synthetic')!='true' or params.scheme!='redis'
        or params.hostname!='127.0.0.1' or params.username or params.password!='oracle2_candidate_local_only'
        or params.path not in ('','/0') or params.query or params.fragment or not ports
        or any(p['HostIp']!='127.0.0.1' for p in ports) or not any(p['HostPort']==str(params.port) for p in ports)):
        raise PermissionError('exact owned invented loopback graph fixture required')
    graph_name=graph_name or 'oracle_ro_fixture_graph_'+uuid4().hex
    username=username or 'oracle_ro_fixture_user_'+uuid4().hex
    if not IDENTITY.fullmatch(graph_name) or not graph_name.startswith('oracle_ro_fixture_graph_') or not IDENTITY.fullmatch(username) or not username.startswith('oracle_ro_fixture_user_'):
        raise PermissionError('unique invented fixture identity required')
    destination=Path(directory)
    if destination.is_symlink() or (destination.exists() and destination.stat().st_uid!=os.getuid()) or (destination/'environment.json').exists() or (destination/'qualification.json').exists():
        raise PermissionError('fresh owned protected output required')
    client=redis.Redis.from_url(admin_url,socket_timeout=5,socket_connect_timeout=5,decode_responses=True)
    try:
        graphs=client.execute_command('GRAPH.LIST')
        if not isinstance(graphs,list) or len(graphs)>10000:raise PermissionError('bounded graph census required')
        if graph_name in graphs or client.exists(graph_name) or client.execute_command('ACL','GETUSER',username) is not None:
            raise PermissionError('existing namespace or user cannot be altered')
        # Only this new namespace/user is written. Existing graphs/ACLs are preserved.
        client.execute_command('GRAPH.QUERY',graph_name,'CREATE (:InventedFixture {synthetic: true})','TIMEOUT',30000)
        password=secrets.token_urlsafe(32)
        client.execute_command('ACL','SETUSER',username,'on','>'+password,'~'+graph_name,'-@all',
                               '+graph.ro_query','+ping','+hello','+info|server')
        readonly='redis://'+quote(username,safe='')+':'+quote(password,safe='')+'@127.0.0.1:'+str(params.port)
        other='oracle_ro_fixture_graph_'+uuid4().hex
        restricted=redis.Redis.from_url(readonly,socket_timeout=5,socket_connect_timeout=5)
        try:
            restricted.ping()
            for command,graph,query in (('GRAPH.QUERY',graph_name,'CREATE (:Forbidden)'),('GRAPH.RO_QUERY',graph_name,'CREATE (:Forbidden)'),('GRAPH.RO_QUERY',other,'MATCH (n) RETURN count(n)')):
                try:restricted.execute_command(command,graph,query,'TIMEOUT',30000)
                except redis.exceptions.ResponseError:pass
                else:raise AssertionError('read-only ACL failed a negative capability check')
            rows=restricted.execute_command('GRAPH.RO_QUERY',graph_name,'MATCH (n) RETURN count(n)','TIMEOUT',30000)
            if rows[1]!=[[1]]:raise AssertionError('exact single invented node required')
        finally:restricted.close()
        result={'ORACLE2_TEST_READONLY_GRAPH_URL':readonly,'ORACLE2_TEST_READONLY_GRAPH_NAME':graph_name,
                'ORACLE2_TEST_READONLY_OTHER_GRAPH_NAME':other}
        destination=Path(directory);destination.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(destination,0o700)
        file=destination/'environment.json'
        with file.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
        os.chmod(file,0o600)
        proof=destination/'qualification.json'
        with proof.open('x') as stream:json.dump({'synthetic_only':True,'container_id':details['Id'],'graph_name':graph_name,'readonly_username':username,'invented_nodes':1,'write_command_denied':True,'write_cypher_denied':True,'other_graph_denied':True},stream,indent=2);stream.write('\n')
        os.chmod(proof,0o600)
        return result
    finally:client.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--container',required=True);parser.add_argument('--directory',required=True)
    args=parser.parse_args();os.umask(0o077)
    try:
        result=initialize(args.container,os.environ['ORACLE2_TEST_CANDIDATE_URL'],args.directory)
        if os.getenv('GITHUB_ENV'):
            with open(os.environ['GITHUB_ENV'],'a') as stream:
                for name,value in result.items():stream.write(name+'='+value+'\n')
        print('Invented exact graph read-only ACL: count1; writes and other namespaces refused')
    except Exception:
        print('Owned read-only graph fixture refused; no credentials logged',file=sys.stderr);raise SystemExit(1)
