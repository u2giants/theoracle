"""Exact admissions and conservative atomic cost reservations before any private call."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from typing import Literal
import psycopg
import json
from pydantic import AwareDatetime, Field
from oracle_brain.provider_policy import authorize, ProcessingRequest, ProcessingApproval
from oracle_brain.provider_transport import transport_options
from .contracts import StrictRecord, digest

class Pricing(StrictRecord):
    provider: str
    model: str
    input_per_million_usd: Decimal = Field(ge=0)
    output_per_million_usd: Decimal = Field(ge=0)
    max_output_tokens: int = Field(strict=True, gt=0)
    expires_at: AwareDatetime
    admitted_register_hash: str = Field(pattern=r'^[0-9a-f]{64}$')

class Budget:
    def __init__(self,url: str): self.url=url
    def reserve(self, *, workspace_id: UUID,artifact_id: UUID,batch_id: UUID,purpose: str,attempt: int,
                maximum: Decimal,pricing_hash: str) -> UUID:
        if purpose not in {'source-census','source-extraction','operating-audit'} or attempt not in {1,2} or maximum<=0 or maximum>1:
            raise PermissionError('private dispatch purpose/attempt/cost not admitted')
        reservation_id=uuid4()
        with psycopg.connect(self.url) as conn:
            conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('oracle-operating-budget',))
            prior=conn.execute('SELECT reservation_id FROM oracle2.operating_dispatch_reservations WHERE workspace_id=%s AND artifact_id=%s AND purpose=%s AND attempt=%s',(workspace_id,artifact_id,purpose,attempt)).fetchone()
            if prior: raise PermissionError('attempt already dispatched; replay cannot charge again')
            if attempt==2:
                first=conn.execute('SELECT 1 FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id) WHERE r.workspace_id=%s AND r.artifact_id=%s AND r.purpose=%s AND r.attempt=1 AND s.status=%s',(workspace_id,artifact_id,purpose,'failed')).fetchone()
                if not first: raise PermissionError('one correction requires a diagnosed failed receipt')
            if conn.execute("SELECT 1 FROM oracle2.operating_dispatch_receipts WHERE status='overrun' LIMIT 1").fetchone():
                raise PermissionError('unresolved provider overrun blocks further reservations')
            day=conn.execute("SELECT COALESCE(sum(reserved_usd),0) FROM oracle2.operating_dispatch_reservations WHERE reserved_at >= (date_trunc('day',now() AT TIME ZONE 'America/New_York') AT TIME ZONE 'America/New_York')").fetchone()[0]
            batch=conn.execute('SELECT COALESCE(sum(reserved_usd),0) FROM oracle2.operating_dispatch_reservations WHERE batch_id=%s',(batch_id,)).fetchone()[0]
            if day+maximum>25 or batch+maximum>5: raise PermissionError('daily or batch reservation ceiling exceeded')
            conn.execute('INSERT INTO oracle2.operating_dispatch_reservations(reservation_id,workspace_id,artifact_id,batch_id,purpose,attempt,reserved_usd,pricing_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',(reservation_id,workspace_id,artifact_id,batch_id,purpose,attempt,maximum,pricing_hash))
        return reservation_id

    def finish(self,reservation_id: UUID, *, actual_usd: Decimal, failed: bool, response_hash: str | None):
        with psycopg.connect(self.url) as conn:
            row=conn.execute('SELECT reserved_usd FROM oracle2.operating_dispatch_reservations WHERE reservation_id=%s',(reservation_id,)).fetchone()
            if row is None or actual_usd<0: raise ValueError('invalid dispatch accounting')
            overrun=actual_usd>row[0]
            status='overrun' if overrun else ('failed' if failed else 'completed')
            prior=conn.execute('SELECT actual_usd,status,response_hash FROM oracle2.operating_dispatch_receipts WHERE reservation_id=%s',(reservation_id,)).fetchone()
            if prior and prior!=(actual_usd,status,response_hash): raise ValueError('dispatch receipt tampering')
            conn.execute('INSERT INTO oracle2.operating_dispatch_receipts(reservation_id,actual_usd,status,response_hash) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(reservation_id,actual_usd,status,response_hash))
        if overrun: raise RuntimeError('provider cost overrun; further dispatch denied pending diagnosis')

class AdmittedProvider:
    def __init__(self, *, request: ProcessingRequest, approvals: list[ProcessingApproval], pricing: Pricing, budget: Budget, sender, remaining_daily_allowance=None):
        self.request,self.approvals,self.pricing,self.budget,self.sender=request,approvals,pricing,budget,sender
        self.remaining_daily_allowance=remaining_daily_allowance
    def extract(self, *, workspace_id: UUID,artifact_id: UUID,batch_id: UUID,purpose: str,attempt: int,
                input_tokens_upper_bound: int, messages: list[dict]):
        authorize(self.request,self.approvals)
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
        if maximum > self.remaining_daily_allowance():
            raise PermissionError('current remaining daily allowance cannot fund dispatch')
        rid=self.budget.reserve(workspace_id=workspace_id,artifact_id=artifact_id,batch_id=batch_id,purpose=purpose,attempt=attempt,maximum=maximum,pricing_hash=digest(self.pricing.model_dump(mode='json')))
        try:
            response,actual=self.sender(messages=messages,model=self.pricing.model,max_output_tokens=self.pricing.max_output_tokens,**opts)
        except Exception:
            self.budget.finish(rid,actual_usd=maximum,failed=True,response_hash=None)
            raise RuntimeError('admitted extraction dispatch failed; private response not logged') from None
        self.budget.finish(rid,actual_usd=actual,failed=False,response_hash=digest({'response':response}))
        return response
