"""Concrete production orchestration with recorded owner seams, NOT actual SQL proof."""
from datetime import datetime,timedelta,timezone
import hashlib,time
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.recovery_authority_v1 import RecoverySQLAuthorityV1,RecoveryOutcomeUnknownV1
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
from oracle_brain.operating_model.recovery_contracts_v1 import RecoveryCurrentV1,RecoveryClaimV1
from oracle_brain.hosting.forward_recovery import ProtectedReplacementRecoveryFactoryV1
from test_recovery_protected_settings_v1 import installed
from test_recovery_contracts_v1 import census,change,uid,H


def recording(tmp_path,monkeypatch,*,change_after=False,lose_target_ack=False,expire_after_claim=False):
 settings,d,p=installed(tmp_path,postrestore=True);factory=ProtectedReplacementRecoveryFactoryV1(settings)
 now=datetime.now(timezone.utc);deadline=now+timedelta(seconds=25)
 restore=RecoveryClaimV1(operation_id=d.operation_id,phase='restore',descriptor_sha256=digest(d.model_dump(mode='json')),claimed_at=p.master_claimed_at,original_phase_deadline=p.original_phase_deadline,fresh=False)
 claim=RecoveryClaimV1(operation_id=d.operation_id,phase='deny-import',descriptor_sha256=digest(d.model_dump(mode='json')),claimed_at=now,original_phase_deadline=now+timedelta(seconds=60),fresh=True)
 c=change(census()[1],descriptor_sha256=claim.descriptor_sha256,source_session_role=d.purpose_bindings[0].sql_identity.session_role,source_principal_id=d.purpose_bindings[0].principal_id,coverage=d.scope_coverage,checked_at=now,valid_until=now+timedelta(seconds=20))
 events=[];state={'claimed':False,'imported':False,'denial_reads':0}
 def current(self,*,deadline):
  events.append(('current',self.purpose,self.target));target=self.target
  binding=next(v for v in (p.purpose_bindings if target else d.purpose_bindings) if v.phase_authority==self.purpose)
  selected=c if self.purpose=='current-denials' else None
  if selected is not None:
   state['denial_reads']+=1
   if change_after and state['denial_reads']>1:
    first=change(selected.watermarks[0],canonical_rows_sha256='b'*64)
    selected=change(selected,watermarks=(first,)+selected.watermarks[1:])
  profile_raw=canonical_bytes(p.model_dump(mode='json')) if target else None
  return RecoveryCurrentV1(admission_id=uid(900),operation_id=d.operation_id,phase_authority=self.purpose,principal_id=binding.principal_id,session_role=binding.sql_identity.session_role,descriptor_bytes_hex=canonical_bytes(d.model_dump(mode='json')).hex(),descriptor_sha256=claim.descriptor_sha256,postrestore_binding_bytes_hex=profile_raw.hex() if profile_raw else None,postrestore_binding_sha256=hashlib.sha256(profile_raw).hexdigest() if profile_raw else None,checked_at=now,valid_until=now+timedelta(seconds=20),original_horizon=d.original_horizon,census=selected,retained_claims=() if target else (restore,),imported_census_sha256s=(digest(c.model_dump(mode='json')),) if target and state['imported'] else ())
 def reserve(self,phase,*,deadline):
  events.append(('claim',phase));fresh=not state['claimed'];state['claimed']=True
  if expire_after_claim:
   from oracle_brain.operating_model import request_deadline_v1 as fence
   monkeypatch.setattr(fence.time,'monotonic',lambda:1e30)
  return change(claim,fresh=fresh)
 def apply(self,census,*,deadline):
  events.append(('target-import',));state['imported']=True
  if lose_target_ack:raise RecoveryOutcomeUnknownV1('recorded possibly committed target close')
  return {'schema_version':1,'operation_id':str(d.operation_id),'census_sha256':digest(census.model_dump(mode='json')),'quarantined':True,'serving_authorized':False,'dispatch_authorized':False,'automatic_retry_allowed':False}
 def observe(self,note,*,deadline):events.append(('observe',note.status));return {}
 monkeypatch.setattr(RecoverySQLAuthorityV1,'current_v1',current)
 monkeypatch.setattr(RecoverySQLAuthorityV1,'_claim_v1',reserve)
 monkeypatch.setattr(RecoverySQLAuthorityV1,'_import_actual_census_v1',apply)
 monkeypatch.setattr(RecoverySQLAuthorityV1,'_observe_actual_v1',observe)
 return factory,deadline,events,state


def test_recorded_connected_source_target_source_order_never_serves_or_dispatches(tmp_path,monkeypatch):
 factory,deadline,events,state=recording(tmp_path,monkeypatch)
 with _request_fence_v1(float(time.monotonic()+25)):
  result=factory.import_current_denials_v1(deadline=deadline)
 assert result.status=='complete' and not result.serving_authorized and not result.dispatch_authorized and not result.automatic_retry_allowed
 index=events.index(('target-import',))
 assert ('current','deny-only-target',False) in events[:index]
 assert ('current','current-denials',False) in events[:index]
 assert ('current','deny-only-target',False) in events[index+1:]
 assert ('current','current-denials',False) in events[index+1:]
 assert events[-1]==('observe','complete')
 assert result.quarantine_reasons and state['claimed']

@pytest.mark.parametrize('case',['changed-current-denials','lost-target-close'])
def test_recorded_possible_target_effect_stays_UNKNOWN_no_second_import(tmp_path,monkeypatch,case):
 factory,deadline,events,state=recording(tmp_path,monkeypatch,change_after=case=='changed-current-denials',lose_target_ack=case=='lost-target-close')
 with _request_fence_v1(float(time.monotonic()+25)):
  with pytest.raises(RecoveryOutcomeUnknownV1):factory.import_current_denials_v1(deadline=deadline)
  with pytest.raises(RecoveryOutcomeUnknownV1):factory.import_current_denials_v1(deadline=deadline)
 assert events.count(('target-import',))==1 and state['claimed'] and state['imported']
 assert not any(e[0]=='observe' for e in events)


def test_original_monotonic_expiry_after_claim_prevents_every_later_effect(tmp_path,monkeypatch):
 factory,deadline,events,state=recording(tmp_path,monkeypatch,expire_after_claim=True)
 with _request_fence_v1(float(time.monotonic()+25)):
  with pytest.raises(RecoveryOutcomeUnknownV1):factory.import_current_denials_v1(deadline=deadline)
 assert state['claimed'] and not state['imported']
 assert not any(e[0] in ('target-import','observe') for e in events)


def test_public_orchestration_accepts_no_caller_packet_hash_or_target(tmp_path):
 import inspect
 assert tuple(inspect.signature(ProtectedReplacementRecoveryFactoryV1.import_current_denials_v1).parameters)==('self','deadline')
