"""Custody uses actual restricted PostgreSQL jobs; startup is deny by default."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from oracle_brain.hosting.custody import FileCustody
from oracle_brain.hosting.gateway import OpaqueJob
from oracle_brain.hosting.runtime import main,protected_file,settings
from oracle_brain.operating_model.contracts import digest
# Reuse real dedicated PG fixtures, rather than substitute authorization mocks.
from test_hosting_job_authority import gateway_database,fixture_job,authority


def custody(tmp_path,url,fixture):
    job=fixture[0]
    registry={'worker_uri':'spiffe://oracle/test','runtime_hash':'a'*64,
              'active':True,'expires_at':2000000000,'allowed_release_hashes':[fixture[9]]}
    path=tmp_path/'policy';path.write_text(json.dumps(registry));path.chmod(0o600)
    spool=tmp_path/'spool';spool.mkdir(mode=0o700)
    current=authority(url,fixture)
    obj=FileCustody(registry=path,spool=spool,trusted_registry_hash=digest(registry),
        runtime_hash='a'*64,worker_uri=registry['worker_uri'],job_authority=current,clock=lambda:100)
    request=OpaqueJob(job_id=job['run_id'],runtime_hash='a'*64,
                     admission_hash=job['admission_hash'],nonce=str(uuid4()),expires_at=110)
    return obj,request


def test_actual_metadata_resolves_enqueue_claim_and_replay(tmp_path,gateway_database,fixture_job):
    store,job=custody(tmp_path,gateway_database,fixture_job)
    store.admit(job,'spiffe://oracle/test')
    with pytest.raises(PermissionError):store.admit(job,'spiffe://oracle/test')
    claimed,row=store.claim()
    assert claimed==job and row['workspace_id']==fixture_job[0]['workspace_id']
    assert store.claim() is None


def test_revocation_before_queue_has_no_pending_bytes(tmp_path,admin_url,gateway_database,fixture_job):
    import psycopg
    store,job=custody(tmp_path,gateway_database,fixture_job)
    with psycopg.connect(admin_url) as conn:
        conn.execute('UPDATE oracle2.appointments SET revoked_at=now() WHERE appointment_id=%s',(fixture_job[7],))
    with pytest.raises(PermissionError):store.admit(job,'spiffe://oracle/test')
    assert not list(store.spool.glob('*.pending'))


def test_changed_policy_denies(tmp_path,gateway_database,fixture_job):
    store,job=custody(tmp_path,gateway_database,fixture_job)
    data=json.loads(store.registry.read_text());data['active']=False
    store.registry.write_text(json.dumps(data))
    with pytest.raises(PermissionError):store.admit(job,'spiffe://oracle/test')


def test_no_optional_authorizer(tmp_path):
    with pytest.raises(TypeError):FileCustody(registry=tmp_path/'missing',spool=tmp_path,
        trusted_registry_hash='a'*64,runtime_hash='a'*64,worker_uri='spiffe://oracle/test')


def test_validate_never_declares_admitted(capsys):
    main(['validate'])
    output=json.loads(capsys.readouterr().out)
    assert output['admitted'] is False and output['company_questions']==output['grading']=='paused'


def test_protected_file_denies_public_and_symlink(tmp_path):
    path=tmp_path/'public';path.write_text('invented');path.chmod(0o644)
    with pytest.raises(PermissionError):protected_file(path)
    path.chmod(0o600); link=tmp_path/'link';link.symlink_to(path)
    with pytest.raises(PermissionError):protected_file(link)


def test_settings_require_external_seal_and_fixed_profile(tmp_path):
    path=tmp_path/'settings';path.write_text(json.dumps({'profile':'arbitrary-import'}));path.chmod(0o600)
    seal=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(PermissionError):settings('gateway',path,'a'*64)
    with pytest.raises(PermissionError):settings('gateway',path,seal)
