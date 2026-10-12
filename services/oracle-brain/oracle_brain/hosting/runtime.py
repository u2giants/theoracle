"""Fixed hosted profiles. Operator-sealed files grant authority; HTTP never does."""
import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from pathlib import Path
from uuid import UUID

from oracle_brain.operating_model.contracts import digest
from .custody import FileCustody
from .gateway import OpaqueGateway, server_tls
from .job_authority import PostgresJobAuthority


def protected_file(path, *, limit=1_000_000):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise PermissionError('protected operator file required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        if os.fstat(stream.fileno()).st_mode & 0o077:
            raise PermissionError('protected operator file required')
        raw=stream.read(limit+1)
    if len(raw)>limit:raise PermissionError('operator file exceeds bound')
    return raw


def settings(profile, path, seal):
    raw=protected_file(path)
    if not re.fullmatch('[a-f0-9]{64}',seal or '') or hashlib.sha256(raw).hexdigest()!=seal:
        raise PermissionError('independently pinned operator settings required')
    value=json.loads(raw)
    common={'profile','runtime_hash','synthetic','allowed_release_hashes','worker_uri',
            'database_url_file','registry','registry_hash','spool'}
    extra={'gateway':{'server_cert','server_key','client_ca','hmac_key_file','bind_host','bind_port'},
           'executor':{'graph_url_file','blob_root','source_role_registry_hash'}}
    if profile not in extra or not isinstance(value,dict) or set(value)!=common|extra[profile]:
        raise PermissionError('exact fixed profile schema required')
    if value['profile']!=profile or type(value['synthetic']) is not bool:
        raise PermissionError('profile environment mismatch')
    if not re.fullmatch('[a-f0-9]{64}',value['runtime_hash']):raise PermissionError('runtime pin required')
    releases=value['allowed_release_hashes']
    if not isinstance(releases,list) or not releases or len(releases)!=len(set(releases)):
        raise PermissionError('independently admitted release hashes required')
    if any(not isinstance(r,str) or not re.fullmatch('[a-f0-9]{64}',r) for r in releases):
        raise PermissionError('release hash unavailable')
    if not isinstance(value['worker_uri'],str) or not value['worker_uri'].startswith('spiffe://oracle/'):
        raise PermissionError('fixed worker identity required')
    database=protected_file(value['database_url_file'],limit=8192).decode().strip()
    from psycopg.conninfo import conninfo_to_dict
    parsed=conninfo_to_dict(database)
    if parsed.get('sslmode')!='verify-full' or not parsed.get('sslrootcert'):
        raise PermissionError('ledger authenticated TLS required')
    protected_file(parsed['sslrootcert'])
    # No password, host, URL or original content is returned by validation.
    value['_database_url']=database
    if profile=='executor':
        from oracle_brain.operating_model.source_binding import SourceRoleBinding
        binding=SourceRoleBinding(value['runtime_hash'],value['source_role_registry_hash'],synthetic=value['synthetic'])
        binding.check_url(database)
        value['_source_binding']=binding
    if profile=='executor' and not value['synthetic']:
        raise PermissionError('private embedding admission has no qualified fixed factory')
    return value


def build_custody(config):
    authority=PostgresJobAuthority(config['_database_url'],runtime_hash=config['runtime_hash'],
        synthetic=config['synthetic'],allowed_release_hashes=frozenset(config['allowed_release_hashes']))
    return FileCustody(registry=Path(config['registry']),spool=Path(config['spool']),
        trusted_registry_hash=config['registry_hash'],runtime_hash=config['runtime_hash'],
        worker_uri=config['worker_uri'],job_authority=authority),authority


def execute_one(config,custody,authority):
    binding=config.get('_source_binding')
    from oracle_brain.operating_model.source_binding import SourceRoleBinding
    if not isinstance(binding,SourceRoleBinding):raise PermissionError('sealed source-role binding required')
    binding.check_url(config['_database_url'])
    claimed=custody.claim()
    if claimed is None:return False
    job,row=claimed
    binding.check_url(config['_database_url'])
    authority(row)
    # Import the actual retained native implementation, never an env-selected
    # callable or a generic serving interface. Semantic jobs fail in authority.
    from oracle_brain.operating_model.artifact_storage import FileBlobStore
    from oracle_brain.operating_model.runtime import run_view,run_event,SyntheticEmbedding
    if not config['synthetic']:raise PermissionError('qualified private embedder unavailable')
    blobs=FileBlobStore(Path(config['blob_root']))
    workspace,run=UUID(row['workspace_id']),UUID(row['run_id'])
    if row['scope']=='documentary-view':
        graph=protected_file(config['graph_url_file'],limit=8192).decode().strip()
        asyncio.run(run_view(run,workspace,database_url=config['_database_url'],graph_url=graph,
            blobs=blobs,embedder=SyntheticEmbedding(),dimensions=8,synthetic=True,source_binding=binding))
    elif row['scope']=='finding-review':
        run_event(run,workspace,database_url=config['_database_url'],blobs=blobs,
                  synthetic=True,operation='finding_review',source_binding=binding)
    else:raise PermissionError('fixed documentary execution scope unavailable')
    return True


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('profile',choices=('validate','gateway','executor'))
    args=parser.parse_args(argv)
    if args.profile=='validate':
        # Image startup validation proves fixed code imports, never live readiness.
        print(json.dumps({'profiles':['gateway','executor'],'admitted':False,'company_questions':'paused','grading':'paused'}))
        return
    config=settings(args.profile,os.environ.get('ORACLE_HOSTING_SETTINGS','/run/oracle-auth/settings.json'),
                    os.environ.get('ORACLE_HOSTING_SETTINGS_SHA256',''))
    custody,authority=build_custody(config)
    if args.profile=='gateway':
        for field in ('server_cert','server_key','client_ca'):protected_file(config[field])
        tls=server_tls(certfile=config['server_cert'],keyfile=config['server_key'],cafile=config['client_ca'])
        key=protected_file(config['hmac_key_file'],limit=8192)
        if type(config['bind_port']) is not int or not 1<=config['bind_port']<=65535:
            raise PermissionError('bounded gateway port required')
        OpaqueGateway((config['bind_host'],config['bind_port']),tls=tls,worker_uri=config['worker_uri'],
                      signing_key=key,admit=custody.admit).serve_forever()
    else:
        while True:
            if not execute_one(config,custody,authority):time.sleep(0.5)


if __name__=='__main__':
    try:main()
    except Exception:
        # Exception details may contain secret URLs or private driver messages.
        print('hosted profile denied or stopped',file=__import__('sys').stderr)
        raise SystemExit(1)
