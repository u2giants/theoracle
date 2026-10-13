"""Pure scenario2 recovery receipt checks; no database, host or platform action.

These validate bounded supplied evidence and bytes, never authenticate a capture
or claim hosted/business acceptance. Root must independently admit capture and
check live instance/permissions/SDK receipts before using this result.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Literal
from uuid import UUID

from pydantic import BaseModel,ConfigDict,Field
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from .synthetic_fixture import fixture,fixed_scenario,FORWARD_SCENARIO

ROLES=('gateway-files','executor-files','projector-files','ledger-files','ledger-init',
 'candidate-files','confirmed-files','spool-files','blob-files','candidate-data-files',
 'confirmed-data-files','ledger-data-files','ledger','candidate','confirmed',
 'synthetic-project','executor','gateway')
RUNNING={'ledger','candidate','confirmed','executor','gateway'}
HEX=r'^[a-f0-9]{64}$'
OLD_APP='vhmcdkdk23dgvjvcvhyhcjzd'
MAX_TOTAL=1024**3


class Record(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)


class Seal(Record):
    sha256: str=Field(pattern=HEX)
    size: int=Field(ge=0,le=512*1024**2)
    runtime_uid: int=Field(ge=0)
    runtime_mode: Literal[384,420] # Only the empty lock may retain 0644 beneath private spool.


class Instance(Record):
    application: str=Field(pattern=r'^[a-z0-9]{16,40}$')
    project: str=Field(pattern=r'^oracle-native-[a-z0-9]{16,40}$')
    ledger_container: str=Field(pattern=HEX)
    ledger_volume: str
    spool_volume: str
    blob_volume: str
    candidate_volume: str
    confirmed_volume: str
    networks: list[str]=Field(min_length=5,max_length=5)
    isolation_receipt_sha256: str=Field(pattern=HEX)


class Service(Record):
    container_id: str=Field(pattern=HEX)
    image: str
    state: Literal['running','exited','created']
    exit_code: int


class Authority(Record):
    worker_uri: str
    source_registry_sha256: str=Field(pattern=HEX)
    worker_registry_sha256: str=Field(pattern=HEX)
    issued_at: int=Field(ge=1)
    expires_at: int=Field(ge=1)
    certificate_sha256: str=Field(pattern=HEX)
    source_permission_receipt_sha256: str=Field(pattern=HEX)


class Opaque(Record):
    job_id: str
    runtime_hash: str=Field(pattern=HEX)
    admission_hash: str=Field(pattern=HEX)
    nonce: str
    expires_at: int=Field(ge=1)


class Nonce(Record):
    purpose: Literal['admit','result']
    consumed_at: int=Field(ge=1)
    request: Opaque


class Backup(Record):
    schema: Literal['oracle-forward-backup/v1']
    scenario: Literal['public-invented-forward-v2']
    scenario_seal: str=Field(pattern=HEX)
    source_head: str=Field(pattern=r'^[a-f0-9]{40}$')
    image: str=Field(pattern=r'^ghcr.io/u2giants/theoracle-native@sha256:[a-f0-9]{64}$')
    runtime_hash: str=Field(pattern=HEX)
    review_hash: str=Field(pattern=HEX)
    release_hash: str=Field(pattern=HEX)
    captured_at: int=Field(ge=1)
    instance: Instance
    services: dict[str,Service]
    authority: Authority
    job_id: str
    job_state: Literal['completed']
    pending_jobs: Literal[0]
    ledger_watermark: Literal[11]
    files: dict[str,Seal]
    nonces: list[Nonce]=Field(min_length=1,max_length=64)
    dump_toc_sha256: str=Field(pattern=HEX)
    role_bootstrap_sha256: str=Field(pattern=HEX)
    result_sha256: str=Field(pattern=HEX)
    backup_operation_receipt_sha256: str=Field(pattern=HEX)


class Restore(Record):
    schema: Literal['oracle-forward-restore/v1']
    backup_manifest_sha256: str=Field(pattern=HEX)
    restored_at: int=Field(ge=1)
    instance: Instance
    services: dict[str,Service]
    authority: Authority
    files: dict[str,Seal]
    originally_empty_receipt_sha256: str=Field(pattern=HEX)
    original_instance_routes_denied_receipt_sha256: str=Field(pattern=HEX)
    restore_operation_receipt_sha256: str=Field(pattern=HEX)
    source_permission_receipt_sha256: str=Field(pattern=HEX)
    source_permission_contract_sha256: str=Field(pattern=HEX)
    pending_jobs: Literal[0]
    job_state: Literal['completed']
    job_id: str
    result_sha256: str=Field(pattern=HEX)
    sdk_version: Literal['1.4.0']
    sdk_graph_name: str
    sdk_record_digest: str=Field(pattern=HEX)
    sdk_artifact_digest: str=Field(pattern=HEX)
    sdk_rebuild_receipt_sha256: str=Field(pattern=HEX)
    sdk_reload_receipt_sha256: str=Field(pattern=HEX)
    sdk_was_empty_receipt_sha256: str=Field(pattern=HEX)
    old_job_denied_receipt_sha256: str=Field(pattern=HEX)
    spent_admit_denied_receipt_sha256: str=Field(pattern=HEX)
    wrong_actor_source_denied_receipt_sha256: str=Field(pattern=HEX)
    result_delivery_receipt_sha256: str=Field(pattern=HEX)


def require(value,reason):
    if not value:raise PermissionError(reason)


def validate_instance(instance):
    require(instance.application!=OLD_APP and instance.project=='oracle-native-'+instance.application,'old or mismatched instance denied')
    volumes=[instance.ledger_volume,instance.spool_volume,instance.blob_volume,instance.candidate_volume,instance.confirmed_volume]
    require(len(set(volumes))==5 and all(re.fullmatch(re.escape(instance.project)+r'_[a-z0-9_-]{1,80}',v) for v in volumes),'foreign or shared volume denied')
    require(len(set(instance.networks))==5 and all(re.fullmatch(HEX,n) for n in instance.networks),'network closure differs')


def validate_services(services,image,*,restored=False):
    vendor={'ledger':'postgres:16.10-alpine@sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297',
            'candidate':'falkordb/falkordb:v4.20.7@sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d',
            'confirmed':'falkordb/falkordb:v4.20.7@sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d'}
    require(set(services)==set(ROLES),'18-role snapshot incomplete')
    require(len({s.container_id for s in services.values()})==18,'container identity duplicated')
    for role,s in services.items():
        require(s.image==vendor.get(role,image),'role image drift denied')
        require(s.exit_code==0 and (s.state==('running' if role in RUNNING else 'exited') or (restored and role=='ledger-init' and s.state=='created')),'role completion/availability unproved')


def validate_backup(receipt):
    scenario=fixed_scenario(FORWARD_SCENARIO)
    require(receipt.scenario_seal==scenario.seal() and receipt.job_id==str(scenario.run),'cross-scenario backup denied')
    require(receipt.source_head!='4b6d680a7d0bdc49d5dee519e8635f8ea15c8a1f' and not receipt.image.endswith('52536ce633c7571b9d38feee96c3d6022b2fc81692b71c8ee8639391c2cd6aec'),'legacy source/image denied')
    validate_instance(receipt.instance);validate_services(receipt.services,receipt.image)
    require(receipt.instance.ledger_container==receipt.services['ledger'].container_id,'ledger physical identity differs')
    authority=receipt.authority
    require(authority.worker_uri==scenario.worker_uri and authority.issued_at<=receipt.captured_at<authority.expires_at and authority.expires_at-authority.issued_at<=3600,'expired or extended forward authority denied')
    _,_,payload,manifest,release=fixture(receipt.runtime_hash,receipt.review_hash,FORWARD_SCENARIO)
    require(receipt.release_hash==release.content_hash(),'release differs')
    blob='blobs/'+manifest.private_object_key
    required={'ledger.dump','ledger.toc.json','roles-bootstrap.json','roles.bundle','sources.json','result.json',blob,'spool/'+receipt.job_id+'.claimed','spool/.custody-lock'}
    nonce_names=set()
    admitted=[]
    for nonce in receipt.nonces:
        job=nonce.request
        require(job.job_id==receipt.job_id and job.runtime_hash==receipt.runtime_hash and job.admission_hash==release.documentary_gate_hash and authority.issued_at<=nonce.consumed_at<=receipt.captured_at and nonce.consumed_at<job.expires_at<=authority.expires_at,'expired/foreign spool job denied')
        require(str(UUID(job.nonce))==job.nonce and job.nonce not in nonce_names,'duplicate/noncanonical nonce denied')
        nonce_names.add(job.nonce);required.add('spool/nonce-'+job.nonce)
        if nonce.purpose=='admit':admitted.append(nonce)
    require(len(admitted)==1,'exactly one consumed admission required')
    require(set(receipt.files)==required,'backup corpus incomplete or unexpected')
    for name,seal in receipt.files.items():
        path=PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts and str(path)==name,'unsafe corpus path denied')
        require(seal.runtime_uid==(10001 if name.startswith(('blobs/','spool/')) else 0),'restored ownership differs')
        require(seal.runtime_mode==0o600 or (name=='spool/.custody-lock' and seal.runtime_mode==0o644),'restored file mode differs')
    require(receipt.files['ledger.toc.json'].sha256==receipt.dump_toc_sha256 and receipt.files['result.json'].sha256==receipt.result_sha256 and receipt.files['roles-bootstrap.json'].sha256==receipt.role_bootstrap_sha256,'canonical result/role association differs')
    require(sum(s.size for s in receipt.files.values())<=MAX_TOTAL,'aggregate custody bound exceeded')
    return payload,manifest,release,admitted[0].request


def read_protected(root,name,seal):
    """No-follow bounded immutable descriptor read through every ancestor."""
    root=Path(root).absolute()
    directory=os.open(root.anchor,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for component in (*root.parts[1:],*PurePosixPath(name).parts[:-1]):
            nextfd=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
            os.close(directory);directory=nextfd
        fd=os.open(PurePosixPath(name).name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and stat.S_IMODE(before.st_mode)==0o600 and before.st_size==seal.size,'protected file custody differs')
            data=stream.read(seal.size+1)
            after=os.fstat(stream.fileno())
            require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'backup file changed during check')
            require(len(data)==seal.size and hashlib.sha256(data).hexdigest()==seal.sha256,'backup bytes differ')
            return data
    finally:os.close(directory)


def verify_bundle(root,receipt):
    payload,manifest,release,admitted=validate_backup(receipt)
    root=Path(root)
    require(root.is_dir() and not root.is_symlink() and root.stat().st_uid==os.getuid() and stat.S_IMODE(root.stat().st_mode)==0o700,'protected root custody differs')
    actual=set();actual_dirs=set()
    def failed_walk(error):raise PermissionError('backup directory inventory failed') from error
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=failed_walk):
        for name in (*dirs,*files):
            path=Path(directory)/name
            metadata=path.lstat()
            require(stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode),'linked or special backup path denied')
            if stat.S_ISDIR(metadata.st_mode):
                require(metadata.st_uid==os.getuid() and stat.S_IMODE(metadata.st_mode)==0o700,'backup directory custody differs')
                actual_dirs.add(path.relative_to(root).as_posix())
            else:actual.add(path.relative_to(root).as_posix())
    expected_dirs={str(parent) for name in receipt.files for parent in PurePosixPath(name).parents if str(parent)!='.'}
    require(actual==set(receipt.files) and actual_dirs==expected_dirs,'actual backup corpus differs')
    data={name:read_protected(root,name,seal) for name,seal in receipt.files.items()}
    require(data['ledger.dump'].startswith(b'PGDMP'),'custom PG archive header missing')
    toc=json.loads(data['ledger.toc.json'])
    require(data['ledger.toc.json']==canonical_bytes(toc),'noncanonical TOC denied')
    require(toc=={'schema':'oracle-forward-dump-toc/v1','archive_sha256':receipt.files['ledger.dump'].sha256,'format':'custom','server_major':16,'database':'oracle_synthetic','required_table_names':['appointments','artifact_dependencies','artifact_manifests','drafts','hosting_role_runtime_admissions','hosting_role_source_admissions','operating_model_change_log','operating_model_source_receipts','operating_release_manifests','operating_release_selectors','operating_view_pack_receipts','operating_view_runs','source_blocks','sources','synthetic_hosting_marker']},'PG archive inventory association differs')
    role=json.loads(data['roles-bootstrap.json'])
    require(data['roles-bootstrap.json']==canonical_bytes(role),'noncanonical bootstrap association denied')
    require(role=={'schema':'oracle-forward-role-bootstrap/v1','source_head':receipt.source_head,'runtime_hash':receipt.runtime_hash,'source_registry_sha256':receipt.authority.source_registry_sha256,'dump_toc_sha256':receipt.dump_toc_sha256,'role_bundle_sha256':receipt.files['roles.bundle'].sha256,
        'roles':{'oracle_synthetic_gateway':'oracle2_gateway_metadata','oracle_synthetic_executor':'oracle2_documentary_executor','oracle_synthetic_projector':'oracle2_documentary_executor'},'login_privileges':'NOINHERIT,NOSUPERUSER,NOCREATEDB,NOCREATEROLE,NOBYPASSRLS'},'role/bootstrap association differs')
    receipts=fixture(receipt.runtime_hash,receipt.review_hash,FORWARD_SCENARIO)[0]
    require(data['sources.json']==canonical_bytes({'receipts':[r.model_dump(mode='json') for r in receipts]}),'native source bytes differ')
    require(data['blobs/'+manifest.private_object_key]==canonical_bytes(payload),'canonical artifact blob differs')
    from oracle_brain.operating_model.retrieval import build_pack
    from oracle_brain.operating_model.retrieval import QueryPlan
    expected=build_pack(payload,QueryPlan(view='company_overview',question='invented amber parcel',max_bytes=16384,page=0,page_size=25))
    expected['sdk_candidate_count']=2
    require(data['result.json']==canonical_bytes(expected),'completed canonical result differs')
    require(data['spool/'+receipt.job_id+'.claimed']==canonical_bytes(admitted.model_dump()),'claimed job bytes differ')
    for nonce in receipt.nonces:
        expected_nonce=hashlib.sha256(json.dumps(nonce.request.model_dump(),sort_keys=True).encode()).hexdigest().encode()
        require(data['spool/nonce-'+nonce.request.nonce]==expected_nonce,'durable nonce seal differs')
    return {'schema':'oracle-forward-receipt-check/v1','validated_file_count':len(data),'validated_bytes':sum(len(v) for v in data.values()),'result_sha256':receipt.result_sha256,'hosted_accepted':False,'business_accepted':False,'serving_accepted':False}


def validate_restore(backup,restored):
    _,manifest,release,_=validate_backup(backup)
    require(restored.backup_manifest_sha256==digest(backup.model_dump()),'restore backup association differs')
    validate_instance(restored.instance);validate_services(restored.services,backup.image,restored=True)
    require(restored.instance.ledger_container==restored.services['ledger'].container_id,'restored ledger physical identity differs')
    require(restored.instance.application!=backup.instance.application and restored.instance.ledger_container!=backup.instance.ledger_container,'same instance restore denied')
    require(set(restored.instance.networks).isdisjoint(backup.instance.networks),'original network reused')
    require({restored.instance.ledger_volume,restored.instance.spool_volume,restored.instance.blob_volume,restored.instance.candidate_volume,restored.instance.confirmed_volume}.isdisjoint({backup.instance.ledger_volume,backup.instance.spool_volume,backup.instance.blob_volume,backup.instance.candidate_volume,backup.instance.confirmed_volume}),'original volume reused')
    require({s.container_id for s in restored.services.values()}.isdisjoint({s.container_id for s in backup.services.values()}),'original container reused')
    require(restored.authority==backup.authority and backup.captured_at<=restored.restored_at<backup.authority.expires_at,'renewed or expired restore authority denied')
    require(restored.files==backup.files and restored.result_sha256==backup.result_sha256 and restored.job_id==backup.job_id,'restored bytes/result/job differ')
    require(restored.source_permission_contract_sha256==backup.authority.source_permission_receipt_sha256 and restored.source_permission_receipt_sha256!=backup.authority.source_permission_receipt_sha256,'restored permission contract or distinct observation differs')
    require(restored.sdk_graph_name==release.graph_name and restored.sdk_record_digest==release.graph_record_digest and restored.sdk_artifact_digest==manifest.content_hash,'native SDK rebuilt closure differs')
    require(restored.sdk_rebuild_receipt_sha256!=restored.sdk_reload_receipt_sha256 and restored.sdk_was_empty_receipt_sha256!=restored.sdk_rebuild_receipt_sha256,'distinct empty/rebuild/reload evidence required')
    return {'schema':'oracle-forward-restore-receipt-check/v1','fresh_instance_metadata_consistent':True,'canonical_result_sha256':restored.result_sha256,'hosted_accepted':False,'business_accepted':False,'serving_accepted':False}
