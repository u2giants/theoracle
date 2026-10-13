"""Prepare an exact reviewed public-Git raw Application request; never sends it."""
import argparse,json,os,re
from pathlib import Path
SERVER='onwp0kd7w1w74w9yeotnoihp'
DESTINATION='dx12tov58uah20vcxpe03e0v'

def payload(project,environment,commit,image):
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('merged source SHA required')
    if not re.fullmatch(r'ghcr\.io/u2giants/theoracle-native@sha256:[0-9a-f]{64}',image):raise ValueError('exact reviewed GHCR image required')
    if not project or not environment:raise ValueError('reviewed project and environment identities required')
    # Coolify4.4.6 fills model attributes before unsetting domain input. An
    # explicit empty list survives as an array and fails SQL string binding.
    # Omit the optional domain field; autogeneration remains explicitly denied.
    return {'project_uuid':project,'environment_uuid':environment,'server_uuid':SERVER,'destination_uuid':DESTINATION,
        'name':'oracle-public-invented-native','description':'Isolated public invented Oracle boundary acceptance; company questions and grading paused.',
        'git_repository':'https://github.com/u2giants/theoracle','git_branch':'main','git_commit_sha':commit,
        'build_pack':'dockercompose','docker_compose_location':'/dev/oracle2/hosting/coolify-synthetic.yaml',
        'is_raw_compose_deployment_enabled':True,'connect_to_docker_network':False,'instant_deploy':False,
        'is_auto_deploy_enabled':False,'is_preview_deployments_enabled':False,'is_force_https_enabled':False,
        'is_http_basic_auth_enabled':False,'autogenerate_domain':False}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True);parser.add_argument('--environment',required=True)
    parser.add_argument('--commit',required=True);parser.add_argument('--image',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();result=payload(args.project,args.environment,args.commit,args.image)
    # Image is a separately reviewed platform env value; no credential values.
    receipt={'method':'POST','path':'/api/v1/applications/public','body':result,'image_env':args.image,
             'source_only':True,'production_mutations':0,'credential_issuance':0,'instant_deploy':False}
    fd=os.open(Path(args.output),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(receipt,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    print('prospective public raw Application inputs saved')

if __name__=='__main__':main()
