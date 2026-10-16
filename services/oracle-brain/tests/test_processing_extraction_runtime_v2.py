"""Injected paid-wire consistency only; no compiler/custody authority is issued."""
import hashlib,json
from datetime import timedelta
from uuid import uuid4
import pytest
from test_processing_context import processing
from test_operating_model_extraction import response
from oracle_brain.hosting.processing_extraction_runtime_v2 import (
 ExtractionOperationQualificationV2,ExtractionTargetV2,ExtractionResponseCommitV2,verify_extraction_paid_response_v2)
from oracle_brain.operating_model.purpose_context import ParentPopulationAdmissionV2,source_population_digest
from oracle_brain.operating_model.semantic_acceptance import sealed
from oracle_brain.operating_model.contracts import digest

@pytest.fixture
def paid(processing):
 s=processing;ctx=s['ctx'];now=s['now'];refs=s['envelope'].source_refs
 pop=ParentPopulationAdmissionV2(workspace_id=ctx.job.workspace_id,parent_registry_sha256=s['pins'].parent_registry_sha256,
  runtime_hash=s['registry'].runtime_hash,source_registry_hash='e'*64,source_refs=refs,population_digest=source_population_digest(refs),
  issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=now+timedelta(seconds=60))
 q=ExtractionOperationQualificationV2(workspace_id=ctx.job.workspace_id,actor_id=ctx.actor_id,provider_login='oracle_extract',
  worker_uri=s['envelope'].worker_uri,runtime_hash=pop.runtime_hash,source_registry_hash=pop.source_registry_hash,
  parent_registry_sha256=pop.parent_registry_sha256,envelope_sha256=sealed(s['envelope']),
  source_qualification_sha256=sealed(s['qualification']),descriptor_sha256='1'*64,projection_sha256='2'*64,
  population_admission_sha256=sealed(pop),budget_allocation_projection_sha256='3'*64,source_refs=refs,population_digest=pop.population_digest,
  targets=tuple(ExtractionTargetV2(dispatch_id=c.job.dispatch_id,artifact_id=c.job.artifact_id,artifact_version=1,
   source_ref=c.receipt.ref,native_job_hash=sealed(c.job),context_hash=sealed(c)) for c in s['registry'].contexts),
  issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=pop.expires_at)
 content=json.dumps(response(ctx.receipt));raw=json.dumps({'model':q.model,'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':content}}]}).encode()
 commit=ExtractionResponseCommitV2(phase='extraction',operation='chat',processing_purpose='source-extraction',dispatch_id=ctx.job.dispatch_id,
  workspace_id=q.workspace_id,actor_id=q.actor_id,provider_login=q.provider_login,actual_caller_login=q.provider_login,runtime_hash=q.runtime_hash,
  descriptor_hash=q.descriptor_sha256,operation_approval_hash=sealed(q),population_digest=q.population_digest,source_refs=refs,
  context_hash=sealed(ctx),parent_registry_hash=q.parent_registry_sha256,current_proof_hash='4'*64,parent_witness_hash='5'*64,
  account_policy_hash=digest({k:v for k,v in ctx.job.processing_request.model_dump(mode='json').items() if k!='terms_hash'}),
  model=q.model,valid_until=pop.expires_at,job_hash=sealed(ctx.job),request_hash=ctx.job.request_hash,permission_hash=ctx.permission_hash,
  budget_identity_hash=q.budget_allocation_projection_sha256,raw_response_hash=hashlib.sha256(raw).hexdigest(),native_custody_receipt_hash='6'*64,
  committed_at=now,extraction_source_ref=ctx.receipt.ref,model_content_hash=hashlib.sha256(content.encode()).hexdigest())
 return ctx,commit,raw,q,pop

def verify(p):
 ctx,c,r,q,pop=p
 return verify_extraction_paid_response_v2(ctx,c,r,q,pop,expected_qualification_hash=sealed(q),artifact_version=1)

def test_exact_wire_returns_typed_content_and_non_authorizing_witness(paid):
 result,witness=verify(paid)
 assert result.source_id==paid[0].receipt.ref.source_id
 assert witness.source_ref==paid[0].receipt.ref and witness.source_refs==paid[3].source_refs
 assert witness.artifact_id==paid[0].job.artifact_id and witness.phase_commit_hash==sealed(paid[1])

@pytest.mark.parametrize('field',['job_hash','context_hash','parent_registry_hash','budget_identity_hash','model_content_hash','account_policy_hash','permission_hash','native_custody_receipt_hash'])
def test_committed_binding_substitution_denies_or_changes_witness(paid,field):
 ctx,c,raw,q,pop=paid
 altered=c.model_copy(update={field:'f'*64})
 if field=='native_custody_receipt_hash':
  # Pure verifier binds this seal; R5 authenticates its externally appointed file.
  assert verify((ctx,altered,raw,q,pop))[1].native_custody_receipt_hash=='f'*64
 else:
  with pytest.raises(Exception):verify((ctx,altered,raw,q,pop))

@pytest.mark.parametrize('change',['borrow_source','wrong_version','raw','omitted','expired','runtime','extra_choice','forged_quote'])
def test_paid_payload_and_population_refusals(paid,change):
 ctx,c,raw,q,pop=paid
 if change=='borrow_source':c=c.model_copy(update={'extraction_source_ref':q.source_refs[1]})
 elif change=='wrong_version':q=q.model_copy(update={'targets':(q.targets[0].model_copy(update={'artifact_version':2}),*q.targets[1:])});c=c.model_copy(update={'operation_approval_hash':sealed(q)})
 elif change=='raw':raw+=b' '
 elif change=='omitted':pop=pop.model_copy(update={'source_refs':pop.source_refs[:1]})
 elif change=='expired':c=c.model_copy(update={'committed_at':q.expires_at,'valid_until':q.expires_at+timedelta(seconds=1)})
 elif change=='runtime':pop=pop.model_copy(update={'runtime_hash':'f'*64});q=q.model_copy(update={'population_admission_sha256':sealed(pop)});c=c.model_copy(update={'operation_approval_hash':sealed(q)})
 else:
  wire=json.loads(raw)
  if change=='extra_choice':wire['choices']*=2
  else:
   content=json.loads(wire['choices'][0]['message']['content']);content['findings'][0]['evidence_refs'][0]['quote']='invented';wire['choices'][0]['message']['content']=json.dumps(content)
  raw=json.dumps(wire).encode();c=c.model_copy(update={'raw_response_hash':hashlib.sha256(raw).hexdigest(),'model_content_hash':hashlib.sha256(wire['choices'][0]['message']['content'].encode()).hexdigest()})
 with pytest.raises(Exception):verify((ctx,c,raw,q,pop))


def test_invalid_paid_content_has_consistency_witness_but_cannot_promote(paid):
 from oracle_brain.hosting.processing_extraction_runtime_v2 import verify_extraction_paid_wire_v2
 ctx,c,raw,q,pop=paid
 wire=json.loads(raw);wire['choices'][0]['message']['content']='{"invalid":"extraction"}'
 raw=json.dumps(wire).encode();c=c.model_copy(update={'raw_response_hash':hashlib.sha256(raw).hexdigest(),
  'model_content_hash':hashlib.sha256(wire['choices'][0]['message']['content'].encode()).hexdigest()})
 content,witness=verify_extraction_paid_wire_v2(ctx,c,raw,q,pop,expected_qualification_hash=sealed(q),artifact_version=1)
 assert content=='{"invalid":"extraction"}' and witness.raw_wire_hash==hashlib.sha256(raw).hexdigest()
 with pytest.raises(Exception):verify((ctx,c,raw,q,pop))


def test_extraction_provider_and_metadata_mounts_are_separate():
 from oracle_brain.hosting.processing_extraction_runtime_v2 import ExtractionProviderConfigV2,ExtractionMetadataConfigV2
 from test_purpose_runtime_v2 import config
 from pydantic import ValidationError
 raw=config('metadata');raw.update(phase='extraction',extraction_qualification_file='/own/extraction-op',extraction_qualification_sha256='a'*64)
 assert ExtractionMetadataConfigV2.model_validate(raw).phase=='extraction'
 for field in ('parent_registry_file','source_qualification_file','envelope_file','provider_key_file','ledger_url_file'):
  with pytest.raises(ValidationError):ExtractionMetadataConfigV2.model_validate({**raw,field:'/private/forbidden'})
 with pytest.raises(ValidationError):ExtractionProviderConfigV2.model_validate(raw)
