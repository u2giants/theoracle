from datetime import datetime,timedelta,timezone
from decimal import Decimal
import hashlib
import pytest
from oracle_brain.operating_model.native_provider import _conservative_key_allowance,current_pricing,NativeOpenRouter
from oracle_brain.operating_model.key_coverage import VerifiedKeyCoverage
NOW=datetime(2026,10,12,2,0,tzinfo=timezone.utc)
DATA={'usage_monthly':'3.5','byok_usage_monthly':'2.25','usage_daily':'3.5','byok_usage_daily':'2.25','limit':None,'is_free_tier':False}
def test_month_spend_and_byok_conservatively_bound_new_york_day():
 assert _conservative_key_allowance(DATA,observed_at=NOW,now=NOW,coverage_current=True)==Decimal('19.25')
 assert _conservative_key_allowance({**DATA,'limit':'10','limit_remaining':'2'},observed_at=NOW,now=NOW,coverage_current=True)==2
 assert _conservative_key_allowance({**DATA,'usage_monthly':'27'},observed_at=NOW,now=NOW,coverage_current=True)==0
@pytest.mark.parametrize('change',[{'byok_usage_monthly':None},{'usage_monthly':'NaN'},{'is_free_tier':True},{'limit':'10','limit_remaining':None}])
def test_unknown_nonfinite_unfunded_allowance_denies(change):
 with pytest.raises(PermissionError):_conservative_key_allowance({**DATA,**change},observed_at=NOW,now=NOW,coverage_current=True)
def test_stale_unknown_coverage_and_month_boundary_deny():
 for observed,now,coverage in [(NOW-timedelta(seconds=16),NOW,True),(NOW+timedelta(seconds=1),NOW,True),(NOW,NOW,False),(datetime(2026,11,1,1,tzinfo=timezone.utc),datetime(2026,11,1,1,tzinfo=timezone.utc),True)]:
  with pytest.raises(PermissionError):_conservative_key_allowance(DATA,observed_at=observed,now=now,coverage_current=coverage)
@pytest.mark.parametrize('now',[
 datetime(2026,10,12,16,0,tzinfo=timezone.utc),
 datetime(2026,10,12,4,0,tzinfo=timezone.utc),
 datetime(2026,11,2,5,0,tzinfo=timezone.utc),
 datetime(2026,11,1,5,59,tzinfo=timezone.utc),
 datetime(2026,11,1,6,0,tzinfo=timezone.utc),
 datetime(2026,3,8,6,59,tzinfo=timezone.utc),
 datetime(2026,3,8,7,0,tzinfo=timezone.utc)])
def test_current_utc_day_superset_preserves_daily_budget_across_dst(now):
 data={**DATA,'usage_monthly':'90','byok_usage_monthly':'10','usage_daily':'2','byok_usage_daily':'1'}
 assert _conservative_key_allowance(data,observed_at=now,now=now,coverage_current=True)==Decimal('22')
@pytest.mark.parametrize('now',[
 datetime(2026,10,13,0,0,tzinfo=timezone.utc),
 datetime(2026,11,3,0,0,tzinfo=timezone.utc)])
def test_utc_reset_before_new_york_midnight_does_not_erase_prior_spend(now):
 data={**DATA,'usage_daily':'0','byok_usage_daily':'0','usage_monthly':'20','byok_usage_monthly':'2'}
 assert _conservative_key_allowance(data,observed_at=now,now=now,coverage_current=True)==Decimal('3')
@pytest.mark.parametrize('field',['usage_daily','byok_usage_daily'])
def test_missing_daily_or_byok_amount_denies_same_calendar_date(field):
 now=datetime(2026,10,12,16,0,tzinfo=timezone.utc)
 with pytest.raises(PermissionError):_conservative_key_allowance({**DATA,field:None},observed_at=now,now=now,coverage_current=True)
def test_current_pricing_reserves_worst_context_and_cache_tier():
 data={'data':[{'id':'openai/gpt-6.1-sol','pricing':{'prompt':'0.000002','completion':'0.00001','input_cache_write':'0.0000025','overrides':[{'prompt':'0.000004','completion':'0.000015','input_cache_write':'0.000005'}]},'top_provider':{'max_completion_tokens':128000}}]}
 p=current_pricing(data,model='openai/gpt-6.1-sol',max_output_tokens=8192,register_hash='a'*64,now=NOW)
 assert p.input_per_million_usd==5 and p.output_per_million_usd==15
 with pytest.raises(PermissionError):current_pricing(data,model='openai/gpt-6-astra',max_output_tokens=8192,register_hash='a'*64,now=NOW)
 with pytest.raises(PermissionError):current_pricing(data,model='openai/gpt-6.1-sol',max_output_tokens=8193,register_hash='a'*64,now=NOW)
def test_native_sender_has_no_fallback_or_store_override(monkeypatch):
 now=datetime.now(timezone.utc)
 receipt=VerifiedKeyCoverage(admission_hash='a'*64,key_fingerprint=hashlib.sha256(b'synthetic-only').hexdigest(),ledger_identity_hash='b'*64,observed_at=now,expires_at=now+timedelta(minutes=1))
 native=NativeOpenRouter('synthetic-only',coverage_receipt=lambda:receipt,trusted_coverage_hash='a'*64,ledger_identity_hash='b'*64,paid_wire_receiver=lambda raw,**kw:None);calls=[]
 def fake(path,body):
  calls.append((path,body));native._receive_paid_wire(b'{}',complete=True)
  return {'model':'openai/gpt-6.1-sol','choices':[{'finish_reason':'stop','message':{'content':'{}'}}],'usage':{'cost':'0.01'}}
 monkeypatch.setattr(native,'_request',fake)
 opts={'provider':{'only':['openai'],'allow_fallbacks':False,'require_parameters':True,'data_collection':'deny'}}
 assert native.send(messages=[],model='openai/gpt-6.1-sol',max_output_tokens=100,store=False,extra_body=opts)==('{}',Decimal('.01'))
 assert calls[0][1]['stream'] is False and calls[0][1]['store'] is False and 'tools' not in calls[0][1]
 for store,extra in [(True,opts),(False,{'provider':{'allow_fallbacks':True}})]:
  with pytest.raises(PermissionError):native.send(messages=[],model='openai/gpt-6.1-sol',max_output_tokens=100,store=store,extra_body=extra)
 assert len(calls)==1
