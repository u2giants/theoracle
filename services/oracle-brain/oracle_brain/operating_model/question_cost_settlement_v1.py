"""Independent original financial truth only; no source/read/POST renewal.

Prospective external scope remains an installation input. A matching record is
never authority without actual SQL024 original current cost leaf + actual own
ledger/key registry and existing native/private-custody reservation binding.
"""
from datetime import datetime,timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,model_validator
from .contracts import StrictRecord,canonical_bytes,digest
from .question_effects_v1 import ProtectedQuestionEffectsV1,QuestionEffectConfigV1,PUBLIC_QUESTION_SIGNATURES_V1
from .consolidation_authority_v1 import ConsolidationAuthorityV1,_connection_v1,_execute_v1
from .protected_inputs_v1 import ProtectedInputV1,_pinned,_parse
from .request_deadline_v1 import request_remaining_v1
HASH=r'^[0-9a-f]{64}$'

class OriginalQuestionCostScopeV1(StrictRecord):
    purpose:Literal['original-question-cost-settlement-v1']='original-question-cost-settlement-v1'
    admission_id:UUID
    workspace_id:UUID
    worker_principal_id:UUID
    effect_purpose:Literal['qualified-query-embedding-v1','qualified-answer-synthesis-v1']
    account:str
    key_fingerprint:str=Field(pattern=HASH)
    ledger_registry_hash:str=Field(pattern=HASH)
    terms_hash:str=Field(pattern=HASH)
    allocation_batch:UUID
    allocation_hash:str=Field(pattern=HASH)
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    original_horizon:AwareDatetime
    @model_validator(mode='after')
    def finite_scope(self):
        if not self.valid_from<self.expires_at<=self.original_horizon or self.issuer_actor==self.reviewer_actor or self.account!='key-sha256:'+self.key_fingerprint:raise ValueError('separate original finite cost scope required')
        return self
    def check_v1(self,context,config,broker):
        from .native_factory import NativeBrokerEgress
        if type(broker) is not NativeBrokerEgress or type(config) is not QuestionEffectConfigV1:raise PermissionError('actual original configured native/key owners required')
        OriginalQuestionCostScopeV1.model_validate(self.model_dump(mode='python'))
        expected=(str(self.admission_id),str(self.workspace_id),str(self.worker_principal_id),self.effect_purpose,self.account,self.key_fingerprint,self.ledger_registry_hash,self.terms_hash,str(self.allocation_batch),self.allocation_hash)
        if tuple(context[k] for k in('admission_id','workspace_id','worker_principal_id','effect_purpose','account','key_fingerprint','ledger_registry_hash','terms_hash','allocation_batch','allocation_hash'))!=expected:raise PermissionError('actual independent original cost context differs')
        if(config.admission_id,config.workspace_id,config.worker_principal_id,config.effect_purpose,config.issuer_actor,config.reviewer_actor)!=(self.admission_id,self.workspace_id,self.worker_principal_id,self.effect_purpose,self.issuer_actor,self.reviewer_actor):raise PermissionError('separate original cost scope and installed purpose differ')
        if config.cost_settlement is None or context['config_sha256']!=digest(config.model_dump(mode='json')) or context['cost_settlement_sha256']!=config.cost_settlement.sha256:raise PermissionError('original installed cost/file commitment differs')
        if(broker._key_fingerprint,broker._registry_hash)!=(self.key_fingerprint,self.ledger_registry_hash):raise PermissionError('actual original billing key/ledger differs')
        now=datetime.now(timezone.utc)
        if not self.valid_from<=now<min(self.expires_at,self.original_horizon,config.original_horizon,datetime.fromisoformat(context['valid_until'])):raise PermissionError('original independent cost horizon elapsed')

class ProtectedQuestionCostSettlementV1(ProtectedQuestionEffectsV1):
    """Exact distinct type: never admitted by native dispatch/source methods."""
    def _config(self):
        request_remaining_v1();c=_parse(QuestionEffectConfigV1,_pinned(self.pin.path,self.pin.sha256,65536))
        if(c.issuer_actor,c.reviewer_actor)!=(self.expected_issuer_actor,self.expected_reviewer_actor) or datetime.now(timezone.utc)>=c.original_horizon or c.cost_settlement is None:raise PermissionError('independent original financial horizon missing/expired')
        return c
    def input_v1(self,*args,**kwargs):raise PermissionError('financial metadata cannot read original question or source')
    def claim_v1(self,*args,**kwargs):raise PermissionError('financial metadata cannot claim native effect')
    def status_v1(self,*args,**kwargs):raise PermissionError('financial metadata cannot read retained job/source body')
    def current_for_job_v1(self,*args,**kwargs):raise PermissionError('financial metadata cannot authorize provider dispatch')
    def _cost_call_v1(self,operation,observation,deadline):
        self._config();self._check_sql_inputs_v1();request_remaining_v1()
        with _connection_v1(self.authority.url,deadline,require_pinned_address=True) as connection:
            if not connection.pgconn.ssl_in_use or _execute_v1(connection,deadline,'SELECT session_user,current_user').fetchone()!=(self.authority.binding.session_login,self.authority.binding.session_login):raise PermissionError('actual original cost SQL identity differs')
            self._check_catalog_v1(connection,deadline)
            result=_execute_v1(connection,deadline,'SELECT oracle2.record_question_effect_observation_v1(%s,%s,%s)',(operation,canonical_bytes(observation),deadline)).fetchone()[0]
            self._check_catalog_v1(connection,deadline)
        self._config();self._check_sql_inputs_v1();request_remaining_v1();return result
    def scope_v1(self,operation,broker,*,deadline):
        c=self._config();scope=_parse(OriginalQuestionCostScopeV1,_pinned(c.cost_settlement.path,c.cost_settlement.sha256,65536))
        result=self._cost_call_v1(operation,{'schema_version':1,'protocol':'question-effect-cost-check-v1','operation_id':str(operation)},deadline)
        scope.check_v1(result['cost_context'],c,broker);return scope,result['cost_context']

    def reconcile_unknown_v1(self,operation,broker,*,deadline):
        """Settle original liability only; operation always UNKNOWN/no dispatch.

        A fresh financial window does not renew the original source/read lease.
        Commit or close uncertainty propagates; reservation remains counted and
        the existing central lock prevents new spend until actual reconciliation.
        """
        import hashlib
        from uuid import uuid5,NAMESPACE_URL
        from .native_factory import verify_ledger
        from .provider_adapter import Budget,_budget_execute_v1
        from .protected_inputs_v1 import protected_file,parse_canonical_object_v1
        from .conversation_native_authority_v1 import conversation_wire_liability_lower_bound_v1
        if type(operation) is not UUID:raise TypeError('exact original operation required')
        scope,context=self.scope_v1(operation,broker,deadline=deadline)
        raw,wire,_=broker._question_custody_v1(operation,expected_job_sha256=context['job_sha256'])
        native_path=str(broker._receipts/str(operation))+'.json'
        native_raw=protected_file(native_path,limit=32*1024*1024)
        _pinned(native_path,hashlib.sha256(native_raw).hexdigest(),32*1024*1024)
        native=parse_canonical_object_v1(native_raw,limit=32*1024*1024)
        if(native.get('dispatch_id'),native.get('reservation_id'),native.get('job_hash'),native.get('wire_custody'),native.get('key_fingerprint'),native.get('ledger_identity_hash'))!=(str(operation),wire['reservation_id'],context['job_sha256'],wire,scope.key_fingerprint,scope.ledger_registry_hash):raise PermissionError('actual original native custody differs')
        identity=verify_ledger(broker._url,broker._registry,trusted_registry_hash=broker._registry_hash,key_fingerprint=broker._key_fingerprint,now=datetime.now(timezone.utc),protected_deadline=deadline)
        budget=Budget(broker._url,ledger_identity_hash=identity,protected_deadline=deadline)
        reservation=UUID(wire['reservation_id'])
        with budget._connection_v1() as connection:
            row=_budget_execute_v1(connection,'SELECT r.workspace_id,r.artifact_id,r.batch_id,r.purpose,r.attempt,r.reserved_usd,r.pricing_hash,s.actual_usd,s.status,s.response_hash,s.failure_kind FROM oracle2.operating_dispatch_reservations r LEFT JOIN oracle2.operating_dispatch_receipts s USING(reservation_id) WHERE r.reservation_id=%s',(reservation,)).fetchone()
        if row is None or row[:5]!=(scope.workspace_id,operation,scope.allocation_batch,scope.effect_purpose,1) or row[6]!=native.get('pricing_hash'):raise PermissionError('actual original central reservation differs')
        # Never overwrite completed/known receipts or count a second liability.
        # Unknown receipts use the exact existing central convention. Overrun is
        # committed by Budget.finish and deliberately raises/block-spend.
        observed=conversation_wire_liability_lower_bound_v1(raw.decode('utf8',errors='replace'))
        if row[7] is None:
            self.scope_v1(operation,broker,deadline=deadline)
            budget.finish(reservation,actual_usd=max(row[5],observed),failed=True,response_hash=None,failure_kind='transport_failure')
        elif row[8] not in('failed','overrun') or row[9] is not None or row[7]<max(row[5],observed) or row[10]!='transport_failure':
            raise PermissionError('existing liability truth differs; no replacement receipt')
        self.scope_v1(operation,broker,deadline=deadline)
        if _pinned(native_path,hashlib.sha256(native_raw).hexdigest(),32*1024*1024)!=native_raw:raise PermissionError('actual native cost custody changed')
        observation={'schema_version':1,'protocol':'question-effect-observation-v1','observation_id':str(uuid5(NAMESPACE_URL,'oracle-question-unknown:'+str(operation)+':'+wire['raw_sha256'])),'operation_id':str(operation),'outcome':'unknown','reservation_id':str(reservation),'wire_sha256':wire['raw_sha256'],'native_receipt_sha256':hashlib.sha256(native_raw).hexdigest(),'settled_response_sha256':None}
        return self._cost_call_v1(operation,observation,deadline)
