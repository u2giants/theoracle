from datetime import datetime,timedelta,timezone
from uuid import uuid4
import hashlib

import pytest
from pydantic import ValidationError

from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.key_coverage import KeyConsumer,KeyCoverageAdmission,verify_key_coverage
from oracle_brain.operating_model.native_provider import NativeOpenRouter
from oracle_brain.operating_model.provider_adapter import Budget,AdmittedProvider
from types import SimpleNamespace

NOW=datetime.now(timezone.utc)
FP=hashlib.sha256(b'synthetic-only').hexdigest()

def admission():
 return KeyCoverageAdmission(domain='existing-owner-authorized-oracle-key',key_fingerprint=FP,
  provider_key_record_hash='a'*64,consumers=(KeyConsumer(consumer_id='new-native-worker',runtime_revision_hash='b'*64,mode='central-reservation',proof_hash='c'*64),
   KeyConsumer(consumer_id='legacy-web',runtime_revision_hash='d'*64,mode='read-only-catalog',proof_hash='e'*64),
   KeyConsumer(consumer_id='local-recovery',runtime_revision_hash='f'*64,mode='inactive-preserved',proof_hash='1'*64)),
  census_hash='2'*64,ledger_identity_hash='3'*64,external_liability_receipt_hash='4'*64,issuer_actor=uuid4(),reviewer_actor=uuid4(),
  observed_at=NOW,expires_at=NOW+timedelta(hours=1),census_complete=True,unreserved_paid_callers=0,unreserved_outstanding_liabilities=0)

def verify(a,**change):
 opts=dict(trusted_admission_hash=digest(a.model_dump(mode='json')),key_fingerprint=FP,current_census_hash='2'*64,current_provider_key_record_hash='a'*64,
  current_ledger_identity_hash='3'*64,current_external_liability_receipt_hash='4'*64,current_observed_at=NOW,now=NOW)
 opts.update(change)
 return verify_key_coverage(a,**opts)

def test_current_independent_exact_key_coverage():
 a=admission();proof=verify(a)
 assert proof.key_fingerprint==FP and proof.ledger_identity_hash=='3'*64

@pytest.mark.parametrize('field',['trusted_admission_hash','key_fingerprint','current_provider_key_record_hash','current_census_hash','current_ledger_identity_hash','current_external_liability_receipt_hash'])
def test_seal_or_live_binding_drift_denies(field):
 with pytest.raises(PermissionError):verify(admission(),**{field:'0'*64})

def test_same_actor_stale_future_expired_or_incomplete_census_denies():
 a=admission()
 for changed in [a.model_copy(update={'reviewer_actor':a.issuer_actor}),a.model_copy(update={'expires_at':NOW}),
  a.model_copy(update={'consumers':()}),a.model_copy(update={'consumers':(a.consumers[0],a.consumers[0])}),
  a.model_copy(update={'consumers':(a.consumers[1],)})]:
  with pytest.raises(PermissionError):verify(changed)
 for observed in [NOW-timedelta(seconds=16),NOW+timedelta(seconds=1)]:
  with pytest.raises(PermissionError):verify(a,current_observed_at=observed)

def test_unreserved_callers_or_liabilities_cannot_be_admitted():
 for field in ['unreserved_paid_callers','unreserved_outstanding_liabilities']:
  for value in [1,False,'0']:
   with pytest.raises(ValidationError):KeyCoverageAdmission.model_validate({**admission().model_dump(),field:value})
 with pytest.raises(ValidationError):KeyCoverageAdmission.model_validate({**admission().model_dump(),'census_complete':1})

def test_native_transport_rejects_arbitrary_boolean_and_other_key_before_send(monkeypatch):
 a=admission();proof=verify(a)
 for callback,key in [(lambda:True,'synthetic-only'),(lambda:proof,'other-synthetic-key')]:
  native=NativeOpenRouter(key,coverage_receipt=callback,trusted_coverage_hash=proof.admission_hash,ledger_identity_hash='3'*64)
  calls=[];monkeypatch.setattr(native,'_request',lambda *args:calls.append(args))
  with pytest.raises(PermissionError):native.send(messages=[],model='openai/gpt-6.1-sol',max_output_tokens=100,store=False,extra_body={})
  assert calls==[]

def test_native_adapter_binds_real_allowance_and_exact_single_key_ledger():
 proof=verify(admission())
 native=NativeOpenRouter('synthetic-only',coverage_receipt=lambda:proof,trusted_coverage_hash=proof.admission_hash,ledger_identity_hash='3'*64)
 request=SimpleNamespace(account='key-sha256:'+FP)
 for allowance,budget in [(lambda:25,Budget('synthetic-only',ledger_identity_hash='3'*64)),
                         (native.allowance,Budget('synthetic-only')),
                         (native.allowance,Budget('synthetic-only',ledger_identity_hash='5'*64))]:
  with pytest.raises(PermissionError):AdmittedProvider(request=request,approvals=[],pricing=None,budget=budget,sender=native.send,remaining_daily_allowance=allowance)
 with pytest.raises(PermissionError):AdmittedProvider(request=SimpleNamespace(account='wrong-key'),approvals=[],pricing=None,budget=Budget('synthetic-only',ledger_identity_hash='3'*64),sender=native.send,remaining_daily_allowance=native.allowance)
 valid=AdmittedProvider(request=request,approvals=[],pricing=None,budget=Budget('synthetic-only',ledger_identity_hash='3'*64),sender=native.send,remaining_daily_allowance=native.allowance)
 assert valid.remaining_daily_allowance.__self__ is native
