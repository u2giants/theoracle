"""Exact admissions and conservative atomic cost reservations before any private call."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from uuid import UUID, uuid4
from typing import Literal
import psycopg
from oracle_brain.knowledge.authority import _lock, _has_authority_conn
import json
from pydantic import AwareDatetime, Field
from oracle_brain.provider_policy import authorize, ProcessingRequest, ProcessingApproval
from oracle_brain.provider_transport import transport_options
from .contracts import StrictRecord, digest

class ProviderQuotaError(PermissionError):
    """Terminal quota-only failure; no automatic retry or provider substitution."""

class Pricing(StrictRecord):
    provider: str
    model: str
    input_per_million_usd: Decimal = Field(ge=0)
    output_per_million_usd: Decimal = Field(ge=0)
    max_output_tokens: int = Field(strict=True, gt=0)
    expires_at: AwareDatetime
    admitted_register_hash: str = Field(pattern=r'^[0-9a-f]{64}$')

class Budget:
    """Single Oracle-key central ledger; never a workspace-specific budget shard."""
    def __init__(self,url: str,*,ledger_identity_hash: str | None = None):
        import re
        if ledger_identity_hash is not None and not re.fullmatch('[0-9a-f]{64}',ledger_identity_hash):
            raise PermissionError('verified central ledger identity required')
        self.url=url;self.ledger_identity_hash=ledger_identity_hash
    def reserve(self, *, workspace_id: UUID,artifact_id: UUID,batch_id: UUID,purpose: str,attempt: int,
                maximum: Decimal,pricing_hash: str, account_remaining: Decimal | None = None, correction_hash: str | None = None) -> UUID:
        if purpose not in {'source-census','source-extraction','operating-audit'} or attempt not in {1,2} or not maximum.is_finite() or maximum<=0 or maximum>1:
            raise PermissionError('private dispatch purpose/attempt/cost not admitted')
        # Historical keyword account_remaining denotes this one Oracle key,
        # not unrelated application keys or the provider's whole account.
        if account_remaining is not None and (not account_remaining.is_finite() or account_remaining<0):raise PermissionError('invalid exact Oracle-key allowance')
        maximum=maximum.quantize(Decimal("0.000001"),rounding=ROUND_CEILING)
        reservation_id=uuid4()
        with psycopg.connect(self.url) as conn:
            conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('oracle-operating-budget',))
            prior=conn.execute('SELECT reservation_id FROM oracle2.operating_dispatch_reservations WHERE workspace_id=%s AND artifact_id=%s AND purpose=%s AND attempt=%s',(workspace_id,artifact_id,purpose,attempt)).fetchone()
            if prior: raise PermissionError('attempt already dispatched; replay cannot charge again')
            if attempt==2:
                first=conn.execute('SELECT d.diagnosed_by FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id) JOIN oracle2.operating_dispatch_diagnoses d USING(reservation_id) WHERE d.failure_kind!=%s AND s.failure_kind IS DISTINCT FROM %s AND d.correction_hash=%s AND r.workspace_id=%s AND r.artifact_id=%s AND r.purpose=%s AND r.attempt=1 AND r.batch_id=%s AND s.status=%s',('quota_exhausted','quota_exhausted',correction_hash,workspace_id,artifact_id,purpose,batch_id,'failed')).fetchone()
                if not first: raise PermissionError('one correction requires a diagnosed failed receipt')
                _lock(conn,workspace_id)
                if not _has_authority_conn(conn,workspace_id,first[0],'dispatch-correction:'+str(artifact_id)):raise PermissionError('correction diagnosis authority expired or revoked')
            if conn.execute("SELECT 1 FROM oracle2.operating_dispatch_receipts WHERE status='overrun' LIMIT 1").fetchone():
                raise PermissionError('unresolved provider overrun blocks further reservations')
            day=conn.execute("SELECT COALESCE(sum(reserved_usd),0) FROM oracle2.operating_dispatch_reservations WHERE reserved_at >= (date_trunc('day',now() AT TIME ZONE 'America/New_York') AT TIME ZONE 'America/New_York')").fetchone()[0]
            batch=conn.execute('SELECT COALESCE(sum(reserved_usd),0) FROM oracle2.operating_dispatch_reservations WHERE batch_id=%s',(batch_id,)).fetchone()[0]
            # Include ALL workspaces' reservations for this single key under one
            # central lock. Key totals may include finished calls; double-counting
            # is conservative. This store must never mix unrelated provider keys.
            ceiling=min(Decimal(25),account_remaining) if account_remaining is not None else Decimal(25)
            if day+maximum>ceiling or batch+maximum>5: raise PermissionError('daily or batch reservation ceiling exceeded')
            conn.execute('INSERT INTO oracle2.operating_dispatch_reservations(reservation_id,workspace_id,artifact_id,batch_id,purpose,attempt,reserved_usd,pricing_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',(reservation_id,workspace_id,artifact_id,batch_id,purpose,attempt,maximum,pricing_hash))
        return reservation_id

    def diagnose(self, *, reservation_id: UUID, actor_id: UUID, failure_kind: str, correction_hash: str, diagnosis_hash: str):
        """One immutable, scoped technical diagnosis; quota-only failures cannot retry."""
        import re
        if failure_kind not in {'invalid_output','truncated_output','transport_failure','quota_exhausted'} or any(not re.fullmatch('[0-9a-f]{64}',h) for h in (correction_hash,diagnosis_hash)):
            raise ValueError('sealed exact failure diagnosis required')
        with psycopg.connect(self.url) as conn:
            row=conn.execute('SELECT r.workspace_id,r.artifact_id,s.status FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id) WHERE r.reservation_id=%s AND r.attempt=1',(reservation_id,)).fetchone()
            if row is None or row[2]!='failed':raise PermissionError('diagnosis requires the failed first artifact receipt')
            workspace,artifact,_=row;_lock(conn,workspace)
            if not _has_authority_conn(conn,workspace,actor_id,'dispatch-correction:'+str(artifact)):
                raise PermissionError('current rooted artifact correction authority required')
            conn.execute('INSERT INTO oracle2.operating_dispatch_diagnoses(reservation_id,diagnosed_by,failure_kind,correction_hash,diagnosis_hash) VALUES(%s,%s,%s,%s,%s)',(reservation_id,actor_id,failure_kind,correction_hash,diagnosis_hash))

    def finish(self,reservation_id: UUID, *, actual_usd: Decimal, failed: bool, response_hash: str | None, failure_kind: str | None = None):
        if failure_kind not in {None,'transport_failure','quota_exhausted','invalid_output'} or (failure_kind and not failed):raise ValueError('invalid failure classification')
        if not actual_usd.is_finite() or actual_usd<0:raise ValueError('invalid dispatch accounting')
        actual_usd=actual_usd.quantize(Decimal('0.000001'),rounding=ROUND_CEILING)
        with psycopg.connect(self.url) as conn:
            row=conn.execute('SELECT reserved_usd FROM oracle2.operating_dispatch_reservations WHERE reservation_id=%s',(reservation_id,)).fetchone()
            if row is None or not actual_usd.is_finite() or actual_usd<0: raise ValueError('invalid dispatch accounting')
            overrun=actual_usd>row[0]
            status='overrun' if overrun else ('failed' if failed else 'completed')
            prior=conn.execute('SELECT actual_usd,status,response_hash,failure_kind FROM oracle2.operating_dispatch_receipts WHERE reservation_id=%s',(reservation_id,)).fetchone()
            if prior and prior!=(actual_usd,status,response_hash,failure_kind): raise ValueError('dispatch receipt tampering')
            conn.execute('INSERT INTO oracle2.operating_dispatch_receipts(reservation_id,actual_usd,status,response_hash,failure_kind) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(reservation_id,actual_usd,status,response_hash,failure_kind))
        if overrun: raise RuntimeError('provider cost overrun; further dispatch denied pending diagnosis')

class AdmittedProvider:
    def __init__(self, *, request: ProcessingRequest, approvals: list[ProcessingApproval], pricing: Pricing, budget: Budget, sender, remaining_daily_allowance=None, admitted_register_hash=None):
        from .native_provider import NativeOpenRouter
        native=getattr(sender,'__self__',None)
        if isinstance(native,NativeOpenRouter):
            if (getattr(remaining_daily_allowance,'__self__',None) is not native
                    or getattr(remaining_daily_allowance,'__func__',None) is not NativeOpenRouter.allowance
                    or budget.ledger_identity_hash!=native.ledger_identity_hash):
                raise PermissionError('native sender, admitted key allowance and central ledger must share one binding')
        self.request,self.approvals,self.pricing,self.budget,self.sender=request,approvals,pricing,budget,sender
        self.remaining_daily_allowance=remaining_daily_allowance
        self.admitted_register_hash=admitted_register_hash
    def correction_contract(self, *, workspace_id, artifact_id, batch_id, purpose, input_tokens_upper_bound, messages):
        return digest({'workspace_id':str(workspace_id),'artifact_id':str(artifact_id),'batch_id':str(batch_id),
                       'purpose':purpose,'messages':messages,'processing_request':self.request.model_dump(mode='json'),
                       'pricing':self.pricing.model_dump(mode='json'),'register_hash':self.admitted_register_hash,
                       'input_tokens_upper_bound':input_tokens_upper_bound})

    def extract(self, *, workspace_id: UUID,artifact_id: UUID,batch_id: UUID,purpose: str,attempt: int,
                input_tokens_upper_bound: int, messages: list[dict], response_validator=None):
        authorize(self.request,self.approvals)
        if self.admitted_register_hash!=self.pricing.admitted_register_hash:raise PermissionError('pricing is not bound to the admitted processing register')
        if self.request.purpose!=purpose or self.pricing.provider!=self.request.provider or self.pricing.expires_at<=datetime.now(timezone.utc):
            raise PermissionError('exact purpose/current price admission required')
        if isinstance(input_tokens_upper_bound,bool) or input_tokens_upper_bound<1:
            raise ValueError('bounded input token count required')
        required_bound=len(json.dumps(messages,ensure_ascii=False).encode()) + 1024*len(messages)
        if input_tokens_upper_bound < required_bound:
            raise ValueError('input reservation does not cover the complete dispatch payload')
        if self.remaining_daily_allowance is None:
            raise PermissionError('authoritative remaining daily allowance unavailable')
        opts=transport_options(self.request,self.pricing.model,operation='chat')
        maximum=(Decimal(input_tokens_upper_bound)*self.pricing.input_per_million_usd + Decimal(self.pricing.max_output_tokens)*self.pricing.output_per_million_usd)/Decimal(1_000_000)
        allowance=self.remaining_daily_allowance()
        if maximum > allowance:
            raise PermissionError('current remaining daily allowance cannot fund dispatch')
        rid=self.budget.reserve(workspace_id=workspace_id,artifact_id=artifact_id,batch_id=batch_id,purpose=purpose,attempt=attempt,maximum=maximum,pricing_hash=digest(self.pricing.model_dump(mode='json')),account_remaining=allowance,correction_hash=self.correction_contract(workspace_id=workspace_id,artifact_id=artifact_id,batch_id=batch_id,purpose=purpose,input_tokens_upper_bound=input_tokens_upper_bound,messages=messages))
        self.last_reservation_id=rid
        try:
            response,actual=self.sender(messages=messages,model=self.pricing.model,max_output_tokens=self.pricing.max_output_tokens,store=False,**opts)
        except Exception as error:
            self.budget.finish(rid,actual_usd=maximum,failed=True,response_hash=None,failure_kind='quota_exhausted' if isinstance(error,ProviderQuotaError) else 'transport_failure')
            raise RuntimeError('admitted extraction dispatch failed; private response not logged') from None
        valid=True
        if response_validator is not None:
            try:response_validator(response)
            except (ValueError,TypeError,KeyError):valid=False
        self.budget.finish(rid,actual_usd=actual,failed=not valid,response_hash=digest({'response':response}),failure_kind=None if valid else 'invalid_output')
        return response
