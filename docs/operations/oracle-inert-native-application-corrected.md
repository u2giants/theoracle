# Corrected empty-domain native Application action

Status: REVIEW_REQUIRED. No corrected action executed.
Owner: Codex chat01a132aa-596e-7d72-9957-cbabf6a79cf6 on #27/#58. Prepared October12,2026,9:19PM EDT.

The first one-use create returned500 at9:09:32PM EDT; fresh GETcensus remains7applications/noneOracle/noneenvironment17. Its spentmarker remains. Independently reviewed bounded read-only diagnostics preserved private logs locally (hasha62c44a121573b3a827991da2512f2d06425f4558d0b6f6de348a3e2ee4b3ef2), never sent rawlogs to anymodel. Exact incident second correlates with attemptmarker epoch1791853771.9343805. The error is Array to string conversion, DBbindValue, ApplicationController save line1558; only non-scalar input is docker_compose_domains emptyarray. Actual platform image docker.io/coollabsio/coolify:4.4.6; deployed controllerSHA7992d7e6b6a5e7d4bf1fe88b1c25aa57ce20ee2968423c0719e3248423b78dbc matches inspectedpublicsource. That code fills the model before offsetUnset; zero domains leave its array attribute intact instead of serializing JSON, so save fails before application creation. No guessed historicalcause.

Repair the Oracle-owned input adapter to OMIT the optional domain field when requesting no domains, with autogenerate_domain explicitly false. Public Git/native application capability remains; no other path, service replacement, vendor patch, weakened admission or platform edit. Actual create/readback must prove repair. Source-only compatibility checks verify every storedfield is scalar, no domain inputs, all inertflags false and mutable source/image refusals. Source/CI approval is distinct from the exact corrected action. The runtime/compose source and published image remain pinned to already merged/approved d97b0023c75c2f83c3c6404dbbdaecf2098e26a0 and sha256:73a2ca47c6525dc35ed41cc6592660d5ba59136d878efce436fe9a66bfd29813; the adapter is not shipped in that documentary image. No private/paid/company work or pause change.

All target identifiers, transport/fresh GETs, exclusive one-use attempt, savedresponse-before-readback, no retry/destructivecleanup and laterissuer/env/deployment gates from the prior record remain. New correctedinput fileSHA e1c7d572b883156f648c947e6e3dda30a291597da675738ec62c1df4c85fd5b3; canonicalbodySHA 3d6316110c252e265dcb919012275d137e0b423e9ac189a61e9996d6297fd456. Dedicated new0700directory, no spentmarker reuse. Ordinary platform may queue Git-compose source fetch/read during inertcreate (public controller LoadComposeFile dispatch after save); this metadata/source preparation is expressly included. No container/image/runtime deployment or native role/certificate issuance. Platform-generated metadata/env placeholders/default webhooks are not exported or used.

## Exact corrected request

```json
{
  "body": {
    "autogenerate_domain": false,
    "build_pack": "dockercompose",
    "connect_to_docker_network": false,
    "description": "Isolated public invented Oracle boundary acceptance; company questions and grading paused.",
    "destination_uuid": "dx12tov58uah20vcxpe03e0v",
    "docker_compose_location": "/dev/oracle2/hosting/coolify-synthetic.yaml",
    "environment_uuid": "kutwfqqgxxyni8g65nhlmcuk",
    "git_branch": "main",
    "git_commit_sha": "d97b0023c75c2f83c3c6404dbbdaecf2098e26a0",
    "git_repository": "https://github.com/u2giants/theoracle",
    "instant_deploy": false,
    "is_auto_deploy_enabled": false,
    "is_force_https_enabled": false,
    "is_http_basic_auth_enabled": false,
    "is_preview_deployments_enabled": false,
    "is_raw_compose_deployment_enabled": true,
    "name": "oracle-public-invented-native",
    "project_uuid": "1zziu90glu5ygdddtsccqr43",
    "server_uuid": "onwp0kd7w1w74w9yeotnoihp"
  },
  "credential_issuance": 0,
  "image_env": "ghcr.io/u2giants/theoracle-native@sha256:73a2ca47c6525dc35ed41cc6592660d5ba59136d878efce436fe9a66bfd29813",
  "instant_deploy": false,
  "method": "POST",
  "path": "/api/v1/applications/public",
  "production_mutations": 0,
  "source_only": true
}
```

## Exact corrected one-use operator

```python
import os,json,urllib.request,urllib.error,hashlib,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE='http://100.66.37.58:8000/api/v1'
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
TOKEN=os.environ.pop('COOLIFY_TOKEN','')
if not TOKEN:raise PermissionError('existing scoped credential required')
if set(x[4][0] for x in socket.getaddrinfo('hetz',22))!={'100.66.37.58'}:raise PermissionError('peer drift')
request_file=ROOT/'current-inert-application-request.json'
raw=request_file.read_bytes()
if hashlib.sha256(raw).hexdigest()!='e1c7d572b883156f648c947e6e3dda30a291597da675738ec62c1df4c85fd5b3':raise PermissionError('exact input drift')
planned=json.loads(raw)['body']
def call(method,path,body=None):
 request=urllib.request.Request(BASE+path,data=body,headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'},method=method)
 with opener.open(request,timeout=20) as r:raw=r.read(2097153);status=r.status
 if len(raw)>2097152:raise PermissionError('bounded response required')
 if not 200<=status<300:raise PermissionError('platform refused')
 return raw
def save(name,raw):
 fd=os.open(ROOT/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
version=call('GET','/version').decode().strip('"\n ')
if version!='4.4.6':raise PermissionError('reviewed platform drift')
project=json.loads(call('GET','/projects/1zziu90glu5ygdddtsccqr43'))
if project.get('uuid')!='1zziu90glu5ygdddtsccqr43':raise PermissionError('project drift')
envs=json.loads(call('GET','/projects/1zziu90glu5ygdddtsccqr43/environments'))
if not any(x.get('uuid')=='kutwfqqgxxyni8g65nhlmcuk' and x.get('id')==17 and x.get('name')=='synthetic-acceptance' for x in envs):raise PermissionError('environment drift')
apps=json.loads(call('GET','/applications'))
if len(apps)!=7 or any(x.get('environment_id')==17 or x.get('name')=='oracle-public-invented-native' for x in apps):raise PermissionError('population drift or existing target')
servers=json.loads(call('GET','/servers'))
if not any(x.get('uuid')=='onwp0kd7w1w74w9yeotnoihp' and x.get('is_reachable') is True and x.get('is_usable') is True for x in servers):raise PermissionError('server unavailable')
fd=os.open(ROOT/'create-attempt.claim',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.write(fd,hashlib.sha256(raw).hexdigest().encode());os.fsync(fd);os.close(fd)
response=call('POST','/applications/public',json.dumps(planned,sort_keys=True,separators=(',',':')).encode());save('create-response.json',response)
created=json.loads(response);uuid=created.get('uuid')
if not isinstance(uuid,str) or not uuid.isalnum() or not 10<=len(uuid)<=64:raise PermissionError('ambiguous created identity: no retry')
readback=call('GET','/applications/'+uuid);save('created-application-readback.json',readback)
x=json.loads(readback)
if x.get('uuid')!=uuid or x.get('name')!=planned['name'] or x.get('git_commit_sha')!=planned['git_commit_sha'] or x.get('environment_id')!=17:raise PermissionError('readback mismatch: no retry')
print(json.dumps({'created_inert_application':True,'uuid':uuid,'readback_sha256':hashlib.sha256(readback).hexdigest(),'deployment_started':False,'native_credential_issuance':0,'provider_calls':0}))
```
