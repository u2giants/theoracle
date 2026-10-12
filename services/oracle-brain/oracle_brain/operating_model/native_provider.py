"""Fixed OpenRouter transport and conservative account allowance; no hidden retries."""
import json
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from .provider_adapter import Pricing,ProviderQuotaError
from .key_coverage import VerifiedKeyCoverage

ENDPOINT='https://openrouter.ai/api/v1'
NY=ZoneInfo('America/New_York')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise PermissionError('provider redirects are not admitted')


def amount(value):
    if isinstance(value,bool) or value is None:raise PermissionError('authoritative account amount unavailable')
    try:result=Decimal(str(value))
    except Exception:raise PermissionError('authoritative account amount unavailable') from None
    if not result.is_finite() or result<0:raise PermissionError('authoritative account amount unavailable')
    return result


def conservative_allowance(data:dict,*,observed_at:datetime,now:datetime,coverage_current:bool)->Decimal:
    if not coverage_current or observed_at.tzinfo is None or now.tzinfo is None or not timedelta(0)<=now-observed_at<=timedelta(seconds=15):
        raise PermissionError('account reservation coverage or fresh observation unavailable')
    utc=now.astimezone(timezone.utc);local=now.astimezone(NY)
    if utc.date()==local.date():
        # The current UTC day starts before today's New York midnight. Before
        # UTC resets, its spend is a conservative superset of today's NY spend.
        used=amount(data.get('usage_daily'))+amount(data.get('byok_usage_daily'))
    else:
        if (utc.year,utc.month)!=(local.year,local.month):raise PermissionError('UTC/New York month boundary cannot establish daily allowance')
        # After UTC reset the prior UTC segment remains in this NY day. A daily
        # counter alone loses it; the complete UTC month is a safe upper bound.
        used=amount(data.get('usage_monthly'))+amount(data.get('byok_usage_monthly'))
    allowance=max(Decimal(0),Decimal(25)-used)
    if data.get('limit') is not None:allowance=min(allowance,amount(data.get('limit_remaining')))
    if data.get('is_free_tier') is not False:raise PermissionError('existing funded route is not established')
    return allowance


def current_pricing(models:dict,*,model:str,max_output_tokens:int,register_hash:str,now:datetime)->Pricing:
    if model not in {'openai/gpt-6.1-sol','openai/gpt-6-astra'} or isinstance(max_output_tokens,bool) or not 1<=max_output_tokens<=8192:
        raise PermissionError('exact bounded admitted model required')
    matches=[m for m in models.get('data',[]) if m.get('id')==model]
    if len(matches)!=1:raise PermissionError('current exact model pricing unavailable')
    info=matches[0];price=info.get('pricing',{});variants=[price,*price.get('overrides',[])]
    # Charge the worst published context/cache-write tier up front. No tools,
    # web search, images, plugins, batches or cache write are requested.
    input_rate=max(amount(p[k]) for p in variants for k in ('prompt','input_cache_write') if k in p)
    output_rate=max(amount(p.get('completion')) for p in variants)
    top=info.get('top_provider',{})
    if not isinstance(top.get('max_completion_tokens'),int) or max_output_tokens>top['max_completion_tokens']:
        raise PermissionError('bounded output incompatible with current model')
    return Pricing(provider='openrouter',model=model,input_per_million_usd=input_rate*1_000_000,
                   output_per_million_usd=output_rate*1_000_000,max_output_tokens=max_output_tokens,
                   expires_at=now+timedelta(minutes=2),admitted_register_hash=register_hash)

class NativeOpenRouter:
    """Credentials stay in memory; fixed TLS endpoints, bounded responses, no redirects."""
    def __init__(self,api_key:str,*,coverage_receipt, trusted_coverage_hash:str, ledger_identity_hash:str):
        if not api_key:raise PermissionError('existing admitted account credential unavailable')
        import re
        if any(not isinstance(h,str) or not re.fullmatch('[0-9a-f]{64}',h) for h in (trusted_coverage_hash,ledger_identity_hash)):
            raise PermissionError('externally admitted central key reservation binding required')
        self._key=api_key;self.coverage_receipt=coverage_receipt
        self.key_fingerprint=hashlib.sha256(api_key.encode()).hexdigest()
        self.trusted_coverage_hash=trusted_coverage_hash;self.ledger_identity_hash=ledger_identity_hash
    def _coverage(self,now):
        receipt=self.coverage_receipt()
        if (not isinstance(receipt,VerifiedKeyCoverage) or receipt.admission_hash!=self.trusted_coverage_hash
                or receipt.key_fingerprint!=self.key_fingerprint or receipt.ledger_identity_hash!=self.ledger_identity_hash
                or not timedelta(0)<=now-receipt.observed_at<=timedelta(seconds=15) or now>=receipt.expires_at):
            raise PermissionError('current exact-key central reservation coverage unavailable')
        return True
    def _request(self,path,body=None):
        if path not in {'/key','/models','/chat/completions'}:raise PermissionError('unadmitted provider operation')
        if path=='/chat/completions':self.last_response_text=None
        request=urllib.request.Request(ENDPOINT+path,data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+self._key,'Content-Type':'application/json','Cache-Control':'no-store'})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=60) as response:
                raw=response.read(16*1024*1024+1)
            if len(raw)>16*1024*1024:raise ValueError('provider response exceeds bounded envelope')
            if path=='/chat/completions':self.last_response_text=raw.decode('utf-8')
            return json.loads(raw,parse_float=Decimal)
        except urllib.error.HTTPError as error:
            if error.code==402:raise ProviderQuotaError('existing provider credit quota exhausted; terminal') from None
            raise RuntimeError('fixed admitted provider request failed; private request not logged') from None
        except Exception:raise RuntimeError('fixed admitted provider request failed; private request not logged') from None
    def allowance(self):
        observed=datetime.now(timezone.utc)
        data=self._request('/key').get('data',{})
        now=datetime.now(timezone.utc)
        return conservative_allowance(data,observed_at=observed,now=now,coverage_current=self._coverage(now))
    def pricing(self,*,model,max_output_tokens,register_hash):
        return current_pricing(self._request('/models'),model=model,max_output_tokens=max_output_tokens,register_hash=register_hash,now=datetime.now(timezone.utc))
    def send(self,*,messages,model,max_output_tokens,store,extra_body):
        self._coverage(datetime.now(timezone.utc))
        expected={'provider':{'only':['openai'],'allow_fallbacks':False,'require_parameters':True,'data_collection':'deny'}}
        if store is not False or extra_body!=expected or model not in {'openai/gpt-6.1-sol','openai/gpt-6-astra'} or not 1<=max_output_tokens<=8192:
            raise PermissionError('exact private transport parameters required')
        response=self._request('/chat/completions',{'model':model,'messages':messages,'max_tokens':max_output_tokens,'store':False,'stream':False,'response_format':{'type':'json_object'},**extra_body})
        if response.get('model')!=model or len(response.get('choices',[]))!=1:raise RuntimeError('provider model/response identity mismatch')
        choice=response['choices'][0];content=choice.get('message',{}).get('content')
        if not isinstance(content,str) or choice.get('finish_reason') not in {'stop','length'}:raise RuntimeError('private extraction response unavailable')
        usage=response.get('usage',{});actual=amount(usage.get('cost'))
        if usage.get('is_byok') is True:actual+=amount(usage.get('cost_details',{}).get('upstream_inference_cost'))
        if usage.get('server_tool_use') or usage.get('cost_details',{}).get('server_tool_cost'):raise RuntimeError('unrequested provider tools incurred cost')
        self.last_receipt={k:response.get(k) for k in ('id','model','created')}
        self.last_receipt.update(finish_reason=choice['finish_reason'],usage=usage)
        # Cost includes reasoning in completion usage; no unrequested paid tools.
        return content,actual
