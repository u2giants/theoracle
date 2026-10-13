import base64
from datetime import datetime,timedelta,timezone
import hashlib,json
from uuid import uuid4
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from oracle_brain.hosting.provider_runtime import load_settings,signed_coverage,CurrentJobs,main
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.key_coverage import KeyCoverageAdmission
NOW=datetime.now(timezone.utc);H='a'*64

def fixture(tmp_path):
 admission=KeyCoverageAdmission.model_validate_json(json.dumps({'domain':'existing-owner-authorized-oracle-key','key_fingerprint':H,'provider_key_record_hash':H,'consumers':[{'consumer_id':'broker','runtime_revision_hash':H,'mode':'central-reservation','proof_hash':H}],'census_hash':H,'ledger_identity_hash':H,'external_liability_receipt_hash':H,'issuer_actor':str(uuid4()),'reviewer_actor':str(uuid4()),'observed_at':(NOW-timedelta(seconds=5)).isoformat(),'expires_at':(NOW+timedelta(minutes=2)).isoformat(),'census_complete':True,'unreserved_paid_callers':0,'unreserved_outstanding_liabilities':0}))
 key=Ed25519PrivateKey.generate();witness={'census_hash':H,'provider_key_record_hash':H,'ledger_identity_hash':H,'external_liability_receipt_hash':H,'observed_at':NOW.isoformat()};path=tmp_path/'witness.json'
 def write(value=witness,signer=key):
  path.write_text(json.dumps({'witness':value,'signature':base64.b64encode(signer.sign(canonical_bytes(value))).decode()}));path.chmod(0o600)
 write();kwargs=dict(public_key=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex(),admission=admission,admission_hash=digest(admission.model_dump(mode='json')),key_fingerprint=H,now=NOW)
 return path,witness,write,kwargs

def test_external_signature_preserves_observation_time(tmp_path):
 path,witness,write,kwargs=fixture(tmp_path);verified=signed_coverage(path,**kwargs);assert verified.observed_at==NOW

@pytest.mark.parametrize('change',['tamper','wrong_signer','stale','future','census','provider','ledger','liability','admission'])
def test_signed_witness_fail_closed(tmp_path,change):
 path,witness,write,kwargs=fixture(tmp_path)
 if change=='tamper':
  value=json.loads(path.read_text());value['witness']['census_hash']='b'*64;path.write_text(json.dumps(value))
 elif change=='wrong_signer':write(signer=Ed25519PrivateKey.generate())
 elif change in {'stale','future'}:witness['observed_at']=(NOW+timedelta(seconds=1) if change=='future' else NOW-timedelta(seconds=16)).isoformat();write()
 elif change=='admission':kwargs['admission_hash']='b'*64
 else:
  witness[{'census':'census_hash','provider':'provider_key_record_hash','ledger':'ledger_identity_hash','liability':'external_liability_receipt_hash'}[change]]='b'*64;write()
 with pytest.raises(Exception):signed_coverage(path,**kwargs)

def test_private_permissions_and_duplicate_fields(tmp_path):
 path,witness,write,kwargs=fixture(tmp_path);path.chmod(0o644)
 with pytest.raises(PermissionError):signed_coverage(path,**kwargs)
 path.chmod(0o600);path.write_text('{"witness":{},"witness":{},"signature":""}')
 with pytest.raises(Exception):signed_coverage(path,**kwargs)

def test_unsealed_unknown_profile_and_public_settings_denied(tmp_path):
 path=tmp_path/'settings';path.write_text('{"profile":"arbitrary"}');path.chmod(0o600)
 with pytest.raises(PermissionError):load_settings(path,H)
 seal=hashlib.sha256(path.read_bytes()).hexdigest()
 with pytest.raises(PermissionError):load_settings(path,seal)
 path.chmod(0o644)
 with pytest.raises(PermissionError):load_settings(path,seal)

def test_registry_hash_drift_before_context_reads(tmp_path):
 path=tmp_path/'jobs';path.write_text('{}');path.chmod(0o600);jobs=CurrentJobs({'job_registry_file':str(path),'job_registry_hash':H,'runtime_hash':H})
 with pytest.raises(PermissionError):jobs.registry()

def test_validate_profile_not_admitted(capsys):
 main(['validate']);assert json.loads(capsys.readouterr().out)['admitted'] is False

def registry_fixture(tmp_path):
 from test_native_factory import job
 from oracle_brain.operating_model.source_receipts import SourceReceipt,SourceRef
 from oracle_brain.hosting.provider_runtime import JobContext,JobRegistry
 j=job();reading='synthetic source'
 ref=SourceRef(workspace_id=j.workspace_id,source_id=uuid4(),revision=1,original_sha256=H,reading_sha256=hashlib.sha256(reading.encode()).hexdigest(),parser_id='fixture')
 ctx=JobContext(job=j,actor_id=uuid4(),job_hash=digest(j.model_dump(mode='json')),permission_hash=j.permission_hash,receipt=SourceReceipt(ref=ref,reading=reading,display_revision='r1'),inventories={})
 registry=JobRegistry(issuer_actor=uuid4(),reviewer_actor=uuid4(),runtime_hash=H,expires_at=NOW+timedelta(minutes=5),contexts=(ctx,))
 path=tmp_path/'registry';path.write_text(registry.model_dump_json());path.chmod(0o600)
 config={'job_registry_file':str(path),'job_registry_hash':hashlib.sha256(path.read_bytes()).hexdigest(),'runtime_hash':H,'_metadata_url':'not-a-credential'}
 return CurrentJobs(config),ctx,path,registry

@pytest.mark.parametrize('change',['issuer','expired','runtime','permission','job_hash','purpose','duplicate'])
def test_registry_bound_context_denials(tmp_path,change):
 jobs,ctx,path,registry=registry_fixture(tmp_path);value=json.loads(path.read_text())
 if change=='issuer':value['issuer_actor']=value['reviewer_actor']
 elif change=='expired':value['expires_at']=(NOW-timedelta(seconds=1)).isoformat()
 elif change=='runtime':value['runtime_hash']='b'*64
 elif change=='permission':value['contexts'][0]['permission_hash']='b'*64
 elif change=='job_hash':value['contexts'][0]['job_hash']='b'*64
 elif change=='duplicate':value['contexts']*=2
 else:
  value['contexts'][0]['job']['purpose']='operating-audit'
  # Even correctly resealed non-source purpose has no validator here.
  from oracle_brain.operating_model.native_factory import NativeDispatchJob
  changed=NativeDispatchJob.model_validate_json(json.dumps(value['contexts'][0]['job']));value['contexts'][0]['job_hash']=digest(changed.model_dump(mode='json'))
 path.write_text(json.dumps(value));jobs.config['job_registry_hash']=hashlib.sha256(path.read_bytes()).hexdigest()
 with pytest.raises(PermissionError):jobs.registry()

@pytest.mark.parametrize('change',['revoked','revision','status','draft','receipt','registry'])
def test_current_source_rechecks_fail_closed(tmp_path,monkeypatch,change):
 import oracle_brain.hosting.provider_runtime as runtime
 jobs,ctx,path,registry=registry_fixture(tmp_path);ref=ctx.receipt.ref
 class Cursor:
  def __init__(self,value):self.value=value
  def fetchone(self):return self.value
  def fetchall(self):return self.value
 class Connection:
  pgconn=type('Libpq',(),{'ssl_in_use':True})()
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def execute(self,sql,args=None):
   if 'rolsuper' in sql:return Cursor((False,))
   if 'has_table_privilege' in sql:return Cursor((False,))
   if 'FROM oracle2.sources' in sql:return Cursor([(2 if change=='revision' else 1,'withdrawn' if change=='status' else 'confirmed','draft' if change=='draft' else 'confirmed')])
   if 'operating_model_source_receipts' in sql:
    if change=='registry':path.write_text('{}')
    return Cursor(('b'*64 if change=='receipt' else ref.original_sha256,ref.reading_sha256,ref.parser_id))
   return Cursor(None)
 monkeypatch.setattr(runtime.psycopg,'connect',lambda *args,**kwargs:Connection())
 monkeypatch.setattr(runtime,'_has_authority_conn',lambda *args:change!='revoked')
 with pytest.raises(PermissionError):jobs.authorize(ctx.job)

@pytest.mark.parametrize('mode',['disable','require','verify-ca'])
def test_database_tls_requires_verify_full(tmp_path,mode):
 from oracle_brain.hosting.provider_runtime import tls_url
 path=tmp_path/'url';path.write_text('host=invalid.example dbname=fixture user=fixture sslmode='+mode);path.chmod(0o600)
 with pytest.raises(PermissionError):tls_url(path)

def test_valid_registry_context_then_revocation(tmp_path):
 jobs,ctx,path,registry=registry_fixture(tmp_path)
 assert jobs.resolve(ctx.job.dispatch_id)==ctx.job
 path.write_text('{}')
 with pytest.raises(PermissionError):jobs.resolve(ctx.job.dispatch_id)

def test_signed_witness_missing_observation_does_not_manufacture_time(tmp_path):
 path,witness,write,kwargs=fixture(tmp_path);del witness['observed_at'];write()
 with pytest.raises(Exception):signed_coverage(path,**kwargs)


def test_extraction_profile_refuses_embedding_before_job_authority(tmp_path):
 jobs,ctx,path,registry=registry_fixture(tmp_path)
 request={**ctx.job.request,'model':'openai/text-embedding-3-small','input':['invented only']}
 changed=ctx.job.model_copy(update={'request':request})
 context=ctx.model_copy(update={'job':changed,'job_hash':digest(changed.model_dump(mode='json'))})
 path.write_text(registry.model_copy(update={'contexts':(context,)}).model_dump_json())
 jobs.config['job_registry_hash']=hashlib.sha256(path.read_bytes()).hexdigest()
 with pytest.raises(PermissionError):jobs.registry()
