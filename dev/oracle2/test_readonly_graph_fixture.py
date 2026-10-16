#!/usr/bin/env python3
"""Create one invented graph and a new exact-namespace read-only native ACL."""
import argparse,asyncio,json,os,re,secrets,subprocess,sys
from pathlib import Path
from urllib.parse import quote,urlparse
from uuid import uuid4
import redis
from contextlib import contextmanager
import hashlib,stat

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


class _OwnedProcessingWriter:
    """TEST fixture ownership, never runtime/source authority or stop proof."""
    def __init__(self,directory,ownership,ownership_bytes,environment):
        self.directory=directory;self.ownership=ownership;self.ownership_bytes=ownership_bytes
        self.environment=environment;self.inactive=False
    def _owned_admin(self):
        current,_=owned_target(self._container,self._admin_url)
        info=(self.directory/'ownership.json').lstat()
        if (current['Id']!=self.ownership['container_id'] or not stat.S_ISREG(info.st_mode)
                or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_mode&0o077
                or (self.directory/'ownership.json').read_bytes()!=self.ownership_bytes
                or json.loads(self.ownership_bytes)!=self.ownership):
            raise PermissionError('exact writer fence ownership differs')
        client=redis.Redis.from_url(self._admin_url,socket_timeout=2,socket_connect_timeout=2,decode_responses=True)
        acl=client.acl_getuser(self.ownership['username'])
        keys=acl.get('keys',[]) if acl else []
        if isinstance(keys,str):keys=keys.split()
        if (not acl or set(keys)!={'~'+self.ownership['graph_name'],'~'+self.ownership['ontology_name']}
                or acl.get('selectors')):
            client.close();raise PermissionError('writer ACL ownership differs; preserve')
        return client

    def fence_producer(self):
        """LOCAL TEST ONLY: fence this NEW exact username; never shared/admin users."""
        from oracle_brain.hosting.custody import _durable_nonce
        if getattr(self,'_fenced',False):raise PermissionError('writer fence is single use')
        client=self._owned_admin()
        try:
            username=self.ownership['username']
            client.execute_command('ACL','SETUSER',username,'off')
            killed=client.execute_command('CLIENT','KILL','USER',username,'SKIPME','YES')
            acl=client.acl_getuser(username)
            if 'off' not in acl.get('flags',[]) or any(c.get('user')==username for c in client.client_list()):
                raise PermissionError('exact producer fence unproved; preserve')
            _durable_nonce(self.directory,'fenced.json',json.dumps({
                'ownership_hash':hashlib.sha256(self.ownership_bytes).hexdigest(),
                'status':'exact-new-writer-disabled-and-clients-absent','killed_clients':killed}).encode())
            self._fenced=True
        finally:client.close()

    def confirm_fenced_inactive(self,*,timeout=5):
        """After caller closes ALL owned pools/tasks, prove server idle under fence.

        No runtime privilege; no claim that cancellation or an idle snapshot by
        itself stops a query. Only this fresh dedicated writer may be fenced.
        """
        import time
        from oracle_brain.hosting.custody import _durable_nonce
        if not getattr(self,'_fenced',False) or type(timeout) not in (int,float) or not 0<timeout<=5:
            raise PermissionError('exact bounded producer fence required')
        client=self._owned_admin();deadline=time.monotonic()+timeout;observations=0
        try:
            while True:
                username=self.ownership['username'];acl=client.acl_getuser(username)
                if 'off' not in acl.get('flags',[]) or any(c.get('user')==username for c in client.client_list()):
                    raise PermissionError('producer fence changed; preserve')
                result=client.execute_command('GRAPH.INFO','RunningQueries','WaitingQueries')
                if (type(result) is not list or len(result)!=4 or result[0]!='# Running queries'
                        or result[2]!='# Waiting queries' or any(type(result[i]) is not list for i in (1,3))):
                    raise PermissionError('actual graph idle evidence unavailable; preserve')
                active=0
                for entries in (result[1],result[3]):
                    for entry in entries:
                        if type(entry) is not list or len(entry)%2:raise PermissionError('malformed graph activity; preserve')
                        row=dict(zip(entry[::2],entry[1::2]))
                        if 'Graph name' not in row:raise PermissionError('missing graph activity identity; preserve')
                        if row['Graph name'] in (self.ownership['graph_name'],self.ownership['ontology_name']):active+=1
                observations+=1
                if not active:break
                if time.monotonic()>=deadline:raise PermissionError('owned graph still running or waiting; preserve')
                time.sleep(min(.01,max(0,deadline-time.monotonic())))
            _durable_nonce(self.directory,'fenced-idle.json',json.dumps({
                'ownership_hash':hashlib.sha256(self.ownership_bytes).hexdigest(),
                'status':'fenced-own-producer-and-no-own-running-or-waiting-query',
                'observations':observations}).encode())
            self.confirm_inactive()
        finally:client.close()

    def confirm_inactive(self):
        """Caller must have actual timely owned completion; UNKNOWN cannot call."""
        from oracle_brain.hosting.custody import _durable_nonce
        _durable_nonce(self.directory,'inactive.json',json.dumps({'ownership_hash':hashlib.sha256(self.ownership_bytes).hexdigest(),
            'status':'caller-observed-inactive'}).encode())
        self.inactive=True


@contextmanager
def processing_writer(container,admin_url,directory,*,workspace_id,artifact_id,version,generation):
    """Create ONLY a new own graph/ontology writer ACL on a proven local target.

    Default UNKNOWN preserves exact ownership/resources. Caller confirms actual
    inactive completion only after timely work; no timeout implies cleanup.
    """
    from uuid import UUID
    from oracle_brain.hosting.custody import _durable_nonce
    if (any(type(i) is not UUID for i in (workspace_id,artifact_id,generation))
            or type(version) is not int or version<1):raise PermissionError('exact own UUID graph namespace required')
    details,params=owned_target(container,admin_url)
    graph=f'oracle_processing_v1_{workspace_id.hex}_{artifact_id.hex}_{version}_{generation.hex}'
    ontology=graph+'__ontology';username='oracle_writer_fixture_user_'+uuid4().hex
    destination=Path(directory)
    if destination.exists() or destination.is_symlink():raise PermissionError('fresh owned writer directory required')
    destination.mkdir(mode=0o700,parents=True)
    client=redis.Redis.from_url(admin_url,socket_timeout=5,socket_connect_timeout=5,decode_responses=True)
    try:
        if client.exists(graph) or client.exists(ontology) or client.acl_getuser(username) is not None:
            raise PermissionError('existing graph/ontology/ACL cannot be adopted')
        password=secrets.token_urlsafe(32)
        url='redis://'+quote(username,safe='')+':'+quote(password,safe='')+'@127.0.0.1:'+str(params.port)
        ownership={'schema_version':1,'synthetic_only':True,'container_id':details['Id'],
            'graph_name':graph,'ontology_name':ontology,'username':username,'nonce':uuid4().hex}
        raw=json.dumps(ownership,sort_keys=True,separators=(',',':')).encode()
        environment={'ORACLE2_TEST_PROCESSING_WRITER_GRAPH_URL':url}
        # Actual retained O_EXCL/fsync primitive, durable BEFORE first ACL write.
        _durable_nonce(destination,'ownership.json',raw)
        _durable_nonce(destination,'environment.json',json.dumps(environment).encode())
        if (destination/'ownership.json').read_bytes()!=raw:raise PermissionError('writer ownership readback differs')
        lease=_OwnedProcessingWriter(destination,ownership,raw,environment)
        lease._container=container;lease._admin_url=admin_url
        client.execute_command('ACL','SETUSER',username,'on','>'+password,'~'+graph,'~'+ontology,'-@all',
            '+graph.query','+graph.ro_query','+ping','+hello','+info|server')
        restricted=redis.Redis.from_url(url,socket_timeout=3,socket_connect_timeout=3,decode_responses=True)
        try:
            restricted.ping()
            # Empty exact namespaces only: no documentary content or extra node.
            for key in (graph,ontology):restricted.execute_command('GRAPH.QUERY',key,'RETURN 1','TIMEOUT',1000)
            for args in (('GRAPH.QUERY','oracle_processing_v1_'+uuid4().hex,'RETURN 1','TIMEOUT',1000),
                         ('ACL','GETUSER',username),('GRAPH.LIST',),('GRAPH.DELETE',graph)):
                try:restricted.execute_command(*args)
                except redis.exceptions.NoPermissionError:pass
                else:raise AssertionError('writer acquired unrelated graph/admin/list/delete capability')
        finally:restricted.close()
        try:yield lease
        finally:
            if not lease.inactive:
                _durable_nonce(destination,'unknown.json',json.dumps({'ownership_hash':hashlib.sha256(raw).hexdigest(),
                    'status':'UNKNOWN-preserved-no-cleanup'}).encode())
            else:
                # Re-prove target and immutable ownership, never prefix cleanup.
                current,_=owned_target(container,admin_url)
                info=(destination/'ownership.json').lstat()
                if (current['Id']!=details['Id'] or not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
                    or info.st_nlink!=1 or info.st_mode&0o077 or (destination/'ownership.json').read_bytes()!=raw):
                    raise PermissionError('exact writer cleanup ownership differs')
                acl=client.acl_getuser(username)
                keys=acl.get('keys',[]) if acl else []
                if isinstance(keys,str):keys=keys.split()
                if set(keys)!={'~'+graph,'~'+ontology}:raise PermissionError('writer ACL namespace drifted; preserve resources')
                for key in (graph,ontology):
                    if client.exists(key):client.execute_command('GRAPH.DELETE',key)
                if client.execute_command('ACL','DELUSER',username)!=1:raise PermissionError('owned writer retirement differs')
                _durable_nonce(destination,'retired.json',json.dumps({'ownership_hash':hashlib.sha256(raw).hexdigest(),
                    'status':'exact-inactive-resources-retired'}).encode())
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
