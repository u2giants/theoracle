"""Compile a reviewed, recoverable candidate-only ACL delta; never contact a platform."""
from __future__ import annotations
import argparse, copy, hashlib, json, re
from pathlib import Path
import yaml

GRAPH = 'oracle_operating_model_v1_6426980e62874f589e94d1cb49b5cd5d_992fa7e3138e443a99fda466205b2fde_1_b30a0da35a5b4a979c51733e383aa21e'
USERS = {
    'oracle_native_proof_projector_v1': ('ORACLE_NATIVE_PROOF_PROJECTOR_PASSWORD', '+graph.query +graph.ro_query +ping +hello +info|server'),
    'oracle_native_proof_executor_v1': ('ORACLE_NATIVE_PROOF_EXECUTOR_PASSWORD', '+graph.ro_query +ping +hello +info|server'),
}
WORKER = 'echo "user worker on >$$FALKORDB_PASSWORD ~* &* -@all +@connection $$G -@dangerous"'


def compile_delta(raw: bytes, expected_sha256: str) -> dict:
    if len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('reviewed compose bytes differ')
    before = yaml.safe_load(raw)
    if not isinstance(before, dict) or not isinstance(before.get('services'), dict):
        raise ValueError('compose services missing')
    after = copy.deepcopy(before)
    service = after['services'].get('falkordb')
    if not isinstance(service, dict) or service.get('image') != 'falkordb/falkordb:v4.20.7@sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d':
        raise ValueError('candidate immutable image differs')
    encoded = json.dumps(service)
    if 'oracle-falkordb-candidate-data' not in encoded or 'oracle-falkordb-confirmed' in json.dumps(before):
        raise ValueError('candidate-only resource required')
    environment = service.get('environment')
    if not isinstance(environment, dict) or any(env in environment for env, _ in USERS.values()):
        raise ValueError('fresh proof environment required')
    targets = []
    for field in ('entrypoint', 'command'):
        values = service.get(field, [])
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            raise ValueError('compose executable differs')
        for index, value in enumerate(values):
            if isinstance(value, str) and WORKER in value:
                targets.append((field, index, value))
    if len(targets) != 1 or targets[0][2].count(WORKER) != 1:
        raise ValueError('original worker ACL identity differs')
    field, index, script = targets[0]
    additions=[]
    for user, (env, commands) in USERS.items():
        environment[env] = '${' + env + ':?new exact-purpose credential required}'
        # New passwords are exactly hex64. No runtime value can escape its ACL line.
        guard = 'case "$$'+env+'" in *[!0-9a-f]*|"" ) exit 71;; esac; [ "$${#'+env+'}" -eq 64 ] || exit 71\n'
        script = guard + script
        additions.append('echo "user '+user+' on >$$'+env+' ~'+GRAPH+' ~'+GRAPH+'__ontology -@all '+commands+'"')
    script = script.replace(WORKER, WORKER+'\n'+ '\n'.join(additions))
    # Password bytes are no longer needed after the tmpfs ACL file was generated.
    anchor='unset FALKORDB_PASSWORD FALKORDB_SERVER_TLS_B64 G'
    if script.count(anchor) != 1:
        raise ValueError('original secret cleanup differs')
    script=script.replace(anchor,anchor+' '+' '.join(env for env, _ in USERS.values()))
    if isinstance(service[field], str):
        service[field]=script
    else:
        service[field][index]=script
    return {'schema':'oracle-native-proof-acl-delta/v1','input_sha256':expected_sha256,
            'graph':GRAPH,'users':list(USERS),'compose':after}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--compose',type=Path,required=True)
    parser.add_argument('--expected-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch('[a-f0-9]{64}',args.expected_sha256):raise ValueError('exact seal required')
    result=compile_delta(args.compose.read_bytes(),args.expected_sha256)
    with args.output.open('x') as stream: json.dump(result,stream,indent=2)
    args.output.chmod(0o600)
    print(json.dumps({k:v for k,v in result.items() if k!='compose'}))

if __name__=='__main__':main()
