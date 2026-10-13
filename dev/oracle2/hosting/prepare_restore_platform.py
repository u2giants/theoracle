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

def stage_packet(application,source,image,expires_at,*,now=None):
    # Resource UUID comes from the separately admitted creation readback, never
    # selected by arbitrary paths, project names, commands or environment input.
    if not re.fullmatch('[a-z0-9]{16,40}',application) or application==OLD_APP:raise PermissionError('distinct platform restore identity required')
    create_packet('validated-project','validated-environment',source,image)
    now=int(time.time()) if now is None else now
    if type(expires_at) is not int or type(now) is not int or expires_at<=now+300:raise PermissionError('insufficient unchanged authority lifetime')
    directory='/data/coolify/applications/'+application
    compose='docker compose --project-directory '+directory+' -f '+directory+'/docker-compose.yaml --env-file '+directory+'/.env'
    # Coolify injects flags into only the first occurrence: each occurrence below
    # explicitly fixes all paths. Compose uses the reviewed file's fixed name.
    commands=[('create',60),('start '+' '.join(BOOTSTRAPS),30),('wait '+' '.join(BOOTSTRAPS),90),('start '+' '.join(STORES),30)]
    command=' && '.join('timeout -s TERM -k 5 '+str(seconds)+' '+compose+' '+operation for operation,seconds in commands)
    return {'method':'PATCH','path':'/api/v1/applications/'+application,'body':{'docker_compose_custom_start_command':command},
      'source_head':source,'image':image,'authority_expires_at':expires_at,'source_only':True,
      'platform_source':'coollabsio/coolify@f55efc859dfcbbf79274c4907b3df89f9767c11d',
      'required_preflight':['exact created-app readback','same reviewed image/env and forward-v2 seal','Docker Compose wait capability','platform helper timeout -s/-k capability','fresh empty volumes and disjoint networks'],
      'must_remain_created':['ledger-init','gateway','executor','synthetic-project'],'bootstrap_roles':list(BOOTSTRAPS),'stores':list(STORES)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--application',required=True);p.add_argument('--source',required=True);p.add_argument('--image',required=True);p.add_argument('--expires-at',required=True,type=int);p.add_argument('--output',required=True)
    a=p.parse_args();packet=stage_packet(a.application,a.source,a.image,a.expires_at)
    fd=os.open(Path(a.output),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(packet,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    print('prospective fixed empty-restore staging packet saved; no action performed')
if __name__=='__main__':main()
