"""Compile fixed Coolify v4.4.6 prospective staging packets; never sends them."""
import argparse,json,os,re,time
from pathlib import Path
from prepare_coolify_payload import payload
OLD_APP='vhmcdkdk23dgvjvcvhyhcjzd'
BOOTSTRAPS=('gateway-files','executor-files','projector-files','ledger-files','candidate-files','confirmed-files','spool-files','blob-files','candidate-data-files','confirmed-data-files','ledger-data-files')
STORES=('ledger','candidate','confirmed')
LOCATION='/dev/oracle2/hosting/coolify-forward-restore.yaml'

def create_packet(project,environment,source,image):
    result=payload(project,environment,source,image)
    if source=='4b6d680a7d0bdc49d5dee519e8635f8ea15c8a1f' or image.endswith('52536ce633c7571b9d38feee96c3d6022b2fc81692b71c8ee8639391c2cd6aec'):raise PermissionError('legacy source/image denied')
    result.update(name='oracle-forward-empty-restore',docker_compose_location=LOCATION)
    return {'method':'POST','path':'/api/v1/applications/public','body':result,'instant_deploy':False,'source_only':True}

def stage_packet(application,source,image,expires_at,review_lease_expires_at,review_report_sha256,*,now=None):
    # Resource UUID comes from the separately admitted creation readback, never
    # selected by arbitrary paths, project names, commands or environment input.
    if not re.fullmatch('[a-z0-9]{16,40}',application) or application==OLD_APP:raise PermissionError('distinct platform restore identity required')
    create_packet('validated-project','validated-environment',source,image)
    now=int(time.time()) if now is None else now
    if any(type(v) is not int or v<=0 for v in (expires_at,review_lease_expires_at,now)) or min(expires_at,review_lease_expires_at)<=now+300:raise PermissionError('insufficient unchanged authority/reviewer lease lifetime')
    if not isinstance(review_report_sha256,str) or not re.fullmatch('[a-f0-9]{64}',review_report_sha256):raise PermissionError('exact genuine reviewer report identity required')
    directory='/data/coolify/applications/'+application
    compose='docker compose --project-directory '+directory+' -f '+directory+'/docker-compose.yaml --env-file '+directory+'/.env'
    # Coolify injects flags into only the first occurrence: each occurrence below
    # explicitly fixes all paths. Compose uses the reviewed file's fixed name.
    # Compose wait over multiple services can return a successful member's exit
    # code. Require each fixed bootstrap separately before any store starts.
    commands=[('create',60),('start '+' '.join(BOOTSTRAPS),30),
              *(('wait '+role,90) for role in BOOTSTRAPS),('start '+' '.join(STORES),30)]
    phases=[]
    for i,(operation,seconds) in enumerate(commands):
        margin=300 if i==0 else seconds+5+15
        guard="/bin/sh -c 'test "+str(expires_at-margin)+" -gt $(/bin/date +%s) && test "+str(review_lease_expires_at-margin)+" -gt $(/bin/date +%s)'"
        if operation.startswith('wait '):
            role=operation.split()[1]
            # wait can miss an already-exited one-shot. Its return status is
            # insufficient: require exactly this service to be exited:0.
            check=compose+' ps --all --format "{{.State}}:{{.ExitCode}}" '+role
            action="/bin/sh -c '"+compose+' '+operation+' >/dev/null 2>&1; test "$('+check+')" = exited:0'+"'"
        else:action=compose+' '+operation
        phases.append(guard+' && timeout -s TERM -k 5 '+str(seconds)+' '+action)
    command=' && '.join(phases)
    return {'method':'PATCH','path':'/api/v1/applications/'+application,'body':{'docker_compose_custom_start_command':command},
      'source_head':source,'image':image,'authority_expires_at':expires_at,'reviewer_lease_expires_at':review_lease_expires_at,'reviewer_report_sha256':review_report_sha256,'source_only':True,'authorizing':False,
      'phase_execution_guards':[{'authority_cutoff':expires_at-(300 if i==0 else seconds+20),'reviewer_cutoff':review_lease_expires_at-(300 if i==0 else seconds+20)} for i,(_,seconds) in enumerate(commands)],
      'platform_source':'coollabsio/coolify@f55efc859dfcbbf79274c4907b3df89f9767c11d',
      'required_preflight':['exact created-app readback','same reviewed image/env and forward-v2 seal','genuine current exact action-review report and lease binding','platform helper sh/date/test and pinned Coolify shell-safe grammar qualification','Docker Compose wait capability','platform helper timeout -s/-k capability','fresh empty volumes and disjoint networks'],
      'must_remain_created':['ledger-init','gateway','executor','synthetic-project'],'bootstrap_roles':list(BOOTSTRAPS),'stores':list(STORES)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--application',required=True);p.add_argument('--source',required=True);p.add_argument('--image',required=True);p.add_argument('--expires-at',required=True,type=int);p.add_argument('--review-lease-expires-at',required=True,type=int);p.add_argument('--review-report-sha256',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();packet=stage_packet(a.application,a.source,a.image,a.expires_at,a.review_lease_expires_at,a.review_report_sha256)
    fd=os.open(Path(a.output),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(packet,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    print('prospective fixed empty-restore staging packet saved; no action performed')
if __name__=='__main__':main()
