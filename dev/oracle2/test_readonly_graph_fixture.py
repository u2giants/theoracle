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

def owned_target(container,admin_url):
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
    return details,params


def initialize(container,admin_url,directory,*,graph_name=None,username=None):
    details,params=owned_target(container,admin_url)
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

def processing_reader(container,admin_url,directory,*,receipt,secret,current_delivery):
    """New exact readonly ACL for an already ACKed synthetic processing graph.

    The caller supplies the real SQL delivery lookup and existing protected
    projector key. This helper never alters a graph, an existing ACL or a host.
    """
    import hmac
    from uuid import UUID
    from oracle_brain.operating_model.projection_delivery import signature
    details,params=owned_target(container,admin_url)
    if not callable(current_delivery) or not isinstance(receipt,dict):
        raise PermissionError('actual committed processing delivery required')
    body={k:v for k,v in receipt.items() if k!='signature'}
    if not isinstance(secret,bytes) or len(secret)<32 or not hmac.compare_digest(signature(secret,body),receipt.get('signature','')):
        raise PermissionError('exact signed processing delivery required')
    workspace=UUID(body['workspace_id']);artifact=UUID(body['artifact_id']);event=UUID(body['event_id'])
    graph=body['graph_name'];version=body['version']
    if (type(version) is not int or version<1 or body.get('sdk_version')!='1.4.0'
            or not re.fullmatch('oracle_processing_v1_'+workspace.hex+'_'+artifact.hex+'_'+str(version)+r'_[0-9a-f]{32}',graph)
            or body.get('projection_schema')!='qualified-evidence-projection-v1'
            or any(not re.fullmatch(r'[0-9a-f]{64}',body.get(k,'')) for k in ('content_hash','record_digest','source_digest','permission_digest','projection_digest'))
            or current_delivery(event)!=receipt):
        raise PermissionError('processing delivery identity or current SQL ACK differs')
    destination=Path(directory)
    if destination.is_symlink() or (destination.exists() and destination.stat().st_uid!=os.getuid()) or (destination/'environment.json').exists() or (destination/'qualification.json').exists():
        raise PermissionError('fresh owned protected output required')
    client=redis.Redis.from_url(admin_url,socket_timeout=5,socket_connect_timeout=5,decode_responses=True)
    username='oracle_ro_fixture_user_'+uuid4().hex
    try:
        if client.execute_command('ACL','GETUSER',username) is not None:
            raise PermissionError('existing read-only identity cannot be altered')
        rows=client.execute_command('GRAPH.RO_QUERY',graph,'MATCH (s:OperatingModelSnapshot) RETURN s.content_hash,s.record_digest,s.sdk,s.finalized,s.projection_schema,s.projection_digest','TIMEOUT',30000)
        expected=[[body['content_hash'],body['record_digest'],'1.4.0','true',body['projection_schema'],body['projection_digest']]]
        if rows[1]!=expected:raise PermissionError('actual delivered graph seal differs')
        password=secrets.token_urlsafe(32)
        client.execute_command('ACL','SETUSER',username,'on','>'+password,'~'+graph,'-@all',
            '+graph.ro_query','+ping','+hello','+info|server')
        readonly='redis://'+quote(username,safe='')+':'+quote(password,safe='')+'@127.0.0.1:'+str(params.port)
        restricted=redis.Redis.from_url(readonly,socket_timeout=5,socket_connect_timeout=5,decode_responses=True)
        try:
            restricted.ping()
            for command,target,query in (('GRAPH.QUERY',graph,'CREATE (:Forbidden)'),
                    ('GRAPH.RO_QUERY',graph,'CREATE (:Forbidden)'),
                    ('GRAPH.RO_QUERY','oracle_processing_v1_'+uuid4().hex,'MATCH (n) RETURN count(n)')):
                try:restricted.execute_command(command,target,query,'TIMEOUT',30000)
                except redis.exceptions.ResponseError as error:
                    if target!=graph and not any(word in str(error).lower() for word in ('permission','noperm','access')):
                        raise AssertionError('other graph refusal was not an ACL denial') from error
                else:raise AssertionError('processing readonly capability failed a negative check')
            verified=restricted.execute_command('GRAPH.RO_QUERY',graph,'MATCH (s:OperatingModelSnapshot) RETURN s.content_hash','TIMEOUT',30000)
            if verified[1]!=[[body['content_hash']]]:raise PermissionError('readonly processing graph seal differs')
        finally:restricted.close()
        if current_delivery(event)!=receipt:raise PermissionError('current processing delivery changed during qualification')
        destination.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(destination,0o700)
        result={'ORACLE2_TEST_PROCESSING_READONLY_GRAPH_URL':readonly}
        for name,value in (('environment.json',result),('qualification.json',{
                'synthetic_only':True,'container_id':details['Id'],'graph_name':graph,'event_id':str(event),
                'workspace_id':str(workspace),'artifact_id':str(artifact),'version':version,
                'content_hash':body['content_hash'],'record_digest':body['record_digest'],
                'readonly_username':username,'write_command_denied':True,'write_cypher_denied':True,'other_graph_denied':True})):
            with (destination/name).open('x') as stream:json.dump(value,stream);stream.write('\n')
            os.chmod(destination/name,0o600)
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
