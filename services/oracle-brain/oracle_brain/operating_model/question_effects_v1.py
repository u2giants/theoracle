"""Actual SQL024 purpose owner. Operational metadata is never a paid receipt.

Uses the SAME concrete history SQL connection/current-source owner and captured
original query window. No alternate connection, identity, allowance or ledger.
"""
from datetime import datetime,timezone
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,model_validator
from .contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.provider_policy import ProcessingRequest,ProcessingApproval,authorize
from .source_receipts import SourceRef
from .protected_inputs_v1 import ProtectedInputV1,_pinned,_parse
from .consolidation_authority_v1 import ConsolidationAuthorityV1,_connection_v1,_execute_v1
from .consolidated_delivery_v1 import validate_direct_history_getter_acl_v1
from .request_deadline_v1 import request_remaining_v1
HASH=r'^[0-9a-f]{64}$'
PUBLIC_QUESTION_SIGNATURES_V1=(
 'oracle2.question_effect_input_v1(uuid,uuid,timestamptz,timestamptz,timestamptz)',
 'oracle2.claim_question_effect_v1(uuid,uuid,timestamptz,timestamptz,bytea,timestamptz)',
 'oracle2.question_effect_status_v1(uuid,timestamptz)',
 'oracle2.record_question_effect_observation_v1(uuid,bytea,timestamptz)')
PRIVATE_QUESTION_SIGNATURES_V1=('oracle2._question_effect_input_v1(uuid,uuid,timestamptz,timestamptz,timestamptz)','oracle2._question_effect_cost_context_v1(uuid,timestamptz)')

def validate_question_effect_acl_v1(connection,signature,oid,*,required_login=None,deadline=None):
    if signature not in PUBLIC_QUESTION_SIGNATURES_V1:raise PermissionError('only four fixed question capabilities permit installed direct LOGIN grants')
    execute=lambda *args:_execute_v1(connection,deadline,*args) if deadline is not None else connection.execute(*args)
    actual=execute('SELECT to_regprocedure(%s)::oid',(signature,)).fetchone()[0]
    if actual!=oid:raise PermissionError('exact actual question function OID required')
    # SAME cumulative direct lowpriv no-membership validator. This wrapper fixes
    # the permitted signatures rather than introducing an ACL-ignore option.
    validate_direct_history_getter_acl_v1(connection,oid,required_login=required_login,deadline=deadline)

class QuestionEffectConfigV1(StrictRecord):
    purpose:Literal['question-effects-settings-v1']='question-effects-settings-v1'
    admission_id:UUID
    workspace_id:UUID
    worker_principal_id:UUID
    enduser_principal_id:UUID
    thread_id:UUID
    model_id:UUID
    worker_history_admission:UUID
    effect_purpose:Literal['qualified-query-embedding-v1','qualified-answer-synthesis-v1']
    issuer_actor:UUID
    reviewer_actor:UUID
    database_url:ProtectedInputV1
    database_ca:ProtectedInputV1
    billing_bounds:ProtectedInputV1
    pricing:ProtectedInputV1
    approvals:ProtectedInputV1
    cost_settlement:ProtectedInputV1|None=None
    processing_request:ProcessingRequest
    source_export_scope:tuple[SourceRef,...]=Field(min_length=1,max_length=64)
    original_horizon:AwareDatetime
    expires_at:AwareDatetime
    catalog:dict[str,str]
    @model_validator(mode='after')
    def exact_capabilities(self):
        if set(self.catalog)!=set(PUBLIC_QUESTION_SIGNATURES_V1+PRIVATE_QUESTION_SIGNATURES_V1) or any(len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in self.catalog.values()):raise ValueError('complete exact fixed question catalog required')
        if not self.expires_at<=self.original_horizon or len({self.worker_principal_id,self.issuer_actor,self.reviewer_actor})!=3:raise ValueError('independent finite installed purpose required')
        return self

class ProtectedQuestionEffectsV1:
    def __init__(self,authority,config_pin,*,expected_issuer_actor,expected_reviewer_actor):
        if type(authority) is not ConsolidationAuthorityV1 or type(config_pin) is not ProtectedInputV1:raise TypeError('actual concrete history owner and independently pinned installation required')
        self.authority=authority;self.pin=config_pin
        self.expected_issuer_actor=expected_issuer_actor;self.expected_reviewer_actor=expected_reviewer_actor
        self.config=self._config()
        self._check_sql_inputs_v1()
        c=self.config;b=authority.binding
        if(c.workspace_id,c.worker_principal_id,c.model_id,c.worker_history_admission)!=(b.workspace_id,b.principal_id,b.model_id,b.appointment_id):raise PermissionError('question purpose and actual own history differ')
    def _config(self):
        request_remaining_v1();c=_parse(QuestionEffectConfigV1,_pinned(self.pin.path,self.pin.sha256,65536))
        if(c.issuer_actor,c.reviewer_actor)!=(self.expected_issuer_actor,self.expected_reviewer_actor) or datetime.now(timezone.utc)>=min(c.expires_at,c.original_horizon):raise PermissionError('original independently appointed question settings expired')
        return c
    def _check_sql_inputs_v1(self):
        c=self.config;b=self.authority.binding
        if _pinned(c.database_url.path,c.database_url.sha256,65536).decode('utf8')!=self.authority.url or(c.database_ca.path,c.database_ca.sha256)!=(b.ca_path,b.ca_sha256):raise PermissionError('original protected actual SQL URL/CA differs')
        _pinned(c.database_ca.path,c.database_ca.sha256,65536)
    def _check(self,connection,deadline):
        c=self._config()
        if c!=self.config:raise PermissionError('original installed question settings changed')
        self._check_sql_inputs_v1();self.authority._check(connection,deadline)
        self._check_catalog_v1(connection,deadline)
    def _check_catalog_v1(self,connection,deadline):
        c=self.config
        owner=self.authority.binding.expected_owner
        for signature,pin in c.catalog.items():
            row=_execute_v1(connection,deadline,"SELECT oid,encode(sha256(convert_to(prosrc,'UTF8')),'hex'),pg_get_userbyid(proowner),prosecdef,proconfig FROM pg_proc WHERE oid=to_regprocedure(%s)",(signature,)).fetchone()
            if row is None or row[1]!=pin or row[2]!=owner or row[3] is not True or row[4]!=['search_path=pg_catalog, oracle2']:raise PermissionError('current fixed question catalog differs')
            if signature in PUBLIC_QUESTION_SIGNATURES_V1:validate_question_effect_acl_v1(connection,signature,row[0],required_login=self.authority.binding.session_login,deadline=deadline)
            else:
                acl=_execute_v1(connection,deadline,"SELECT x.grantee,x.privilege_type,x.is_grantable FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x WHERE p.oid=%s AND x.grantee<>p.proowner",(row[0],)).fetchall()
                if acl:raise PermissionError('private question helper must remain owner-only')
        request_remaining_v1()
    def _call(self,signature,args,deadline):
        if signature not in PUBLIC_QUESTION_SIGNATURES_V1:raise PermissionError('fixed public question capability required')
        self._config();request_remaining_v1()
        name=signature.split('(')[0];placeholders=','.join(['%s']*len(args))
        try:
            with _connection_v1(self.authority.url,deadline,require_pinned_address=True) as connection:
                self._check(connection,deadline)
                result=_execute_v1(connection,deadline,'SELECT '+name+'('+placeholders+')',args).fetchone()[0]
                self._check(connection,deadline)
            self._config();request_remaining_v1()
            if datetime.now(timezone.utc)>=deadline:raise PermissionError('original question window expired after close')
            return result
        except BaseException:
            # Claim/observation may have committed. Never retry from this owner.
            raise
    def input_v1(self,event,*,deadline,valid_at=None,known_at=None):
        if type(event) is not UUID:raise TypeError('exact immutable employee event required')
        result=self._call(PUBLIC_QUESTION_SIGNATURES_V1[0],(self.config.admission_id,event,valid_at,known_at,deadline),deadline)
        self._validate_context(result,event)
        return result
    def _validate_context(self,result,event):
        c=self.config;a=result['admission'];b=self.authority.binding
        if(result['admission_id'],result['worker_principal_id'],result['workspace_id'],result['enduser_principal_id'],result['thread_id'],result['employee_event_id'],result['effect_purpose'],result['model_id'])!=(str(c.admission_id),str(c.worker_principal_id),str(c.workspace_id),str(c.enduser_principal_id),str(c.thread_id),str(event),c.effect_purpose,str(c.model_id)):
            raise PermissionError('actual independently installed question context differs')
        if a['catalog']!=c.catalog:raise PermissionError('installed question catalog pins differ')
        if(a['config_sha256'],a['runtime_hash'],a['registry_hash'],a['billing_bounds_sha256'],a['pricing_sha256'],a['approval_packet_sha256'])!=(self.pin.sha256,b.runtime_hash,b.registry_hash,c.billing_bounds.sha256,c.pricing.sha256,c.approvals.sha256):raise PermissionError('actual original question/config/billing/approval pins differ')
        if datetime.now(timezone.utc)>=datetime.fromisoformat(result['valid_until']):raise PermissionError('actual question scope expired')
    def claim_v1(self,event,job,*,deadline,valid_at=None,known_at=None):
        current=self.input_v1(event,deadline=deadline,valid_at=valid_at,known_at=known_at)
        if current['original_sha256']!=job.original_sha256:raise PermissionError('complete original query differs')
        raw=canonical_bytes(job.model_dump(mode='json'))
        result=self._call(PUBLIC_QUESTION_SIGNATURES_V1[1],(self.config.admission_id,event,valid_at,known_at,raw,deadline),deadline)
        if result.get('job_sha256')!=digest(job.model_dump(mode='json')):raise PermissionError('claim outcome UNKNOWN; actual job commitment differs')
        original=datetime.fromisoformat(result['operation_deadline'])
        if original.tzinfo is None or original>deadline:raise PermissionError('claim outcome UNKNOWN; original operation horizon differs')
        self._operation_deadline=original
        self._active_deadline=min(getattr(self,'_active_deadline',deadline),original)
        return result
    def status_v1(self,operation,*,deadline):return self._call(PUBLIC_QUESTION_SIGNATURES_V1[2],(operation,deadline),deadline)
    def observe_v1(self,operation,observation,*,deadline):return self._call(PUBLIC_QUESTION_SIGNATURES_V1[3],(operation,canonical_bytes(observation),deadline),deadline)

    def approvals_v1(self):
        import json
        raw=_pinned(self.config.approvals.path,self.config.approvals.sha256,65536)
        def unique(pairs):
            out={}
            for key,value in pairs:
                if key in out:raise PermissionError('duplicate approval field')
                out[key]=value
            return out
        values=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite approval')))
        if type(values) is not list or not 1<=len(values)<=32 or canonical_bytes(values)!=raw:raise PermissionError('complete canonical independently pinned approvals required')
        result=tuple(ProcessingApproval.model_validate_json(canonical_bytes(x)) for x in values)
        if canonical_bytes([x.model_dump(mode='json') for x in result])!=raw:raise PermissionError('original approval types differ')
        authorize(self.config.processing_request,list(result));return result
    def current_for_job_v1(self,job,*,deadline):
        from .native_factory import QualifiedQueryEmbeddingDispatchJobV1,QualifiedAnswerSynthesisDispatchJobV1
        from .provider_adapter import QualifiedQueryEmbeddingPricingV1,QualifiedAnswerTextPricingV1
        if type(job) not in(QualifiedQueryEmbeddingDispatchJobV1,QualifiedAnswerSynthesisDispatchJobV1):raise PermissionError('exact independently admitted question job required')
        c=self._config();status=self.status_v1(job.dispatch_id,deadline=deadline);context=status['context'];self._validate_context(context,job.employee_event_id)
        original=datetime.fromisoformat(status['operation_deadline'])
        if original.tzinfo is None or datetime.now(timezone.utc)>=original:raise PermissionError('original operation deadline expired; fresh read cannot renew it')
        if hasattr(self,'_operation_deadline') and self._operation_deadline!=original:raise PermissionError('immutable original operation deadline changed')
        if status['job_utf8'].encode('utf8')!=canonical_bytes(job.model_dump(mode='json')):raise PermissionError('actual durable question job differs')
        if(job.admission_id,job.workspace_id,job.thread_id,job.qualified_model_id,job.purpose)!=(c.admission_id,c.workspace_id,c.thread_id,c.model_id,c.effect_purpose):raise PermissionError('actual fixed question-purpose context differs')
        if context['original_sha256']!=job.original_sha256 or context['query_sha256']!=job.query_sha256:raise PermissionError('actual employee original differs')
        approvals=self.approvals_v1()
        if self.config.processing_request!=job.processing_request or approvals!=job.approvals:raise PermissionError('actual independently installed processing approval differs')
        refs=[r.model_dump(mode='json') for r in c.source_export_scope]
        if context['source_refs']!=refs or job.source_export_scope_sha256!=digest({'source_refs':refs}):raise PermissionError('exact complete source export population differs')
        quote_type=QualifiedQueryEmbeddingPricingV1 if job.purpose=='qualified-query-embedding-v1' else QualifiedAnswerTextPricingV1
        quote=_parse(quote_type,_pinned(c.pricing.path,c.pricing.sha256,65536))
        if quote!=job.pricing or self.pin.sha256!=context['admission']['config_sha256']:raise PermissionError('actual pinned quote or config differs')
        expected_permission=digest({'processing_request':job.processing_request.model_dump(mode='json'),'approvals':[a.model_dump(mode='json') for a in approvals],'admission_id':str(c.admission_id),'source_export_scope_sha256':job.source_export_scope_sha256})
        if job.permission_hash!=expected_permission:raise PermissionError('exact independent source export approval commitment differs')
        return context

    async def prepare_grounding_v1(self,projection,event,*,deadline):
        from .sdk_projection import ConsolidatedMetadataSDKProjectionV1
        from .natural_question_v1 import NaturalQuestionRequestV1,answer_natural_from_projection_v1
        if type(projection) is not ConsolidatedMetadataSDKProjectionV1 or projection.authority is not self.authority:raise PermissionError('same actual own-role readonly SDK authority required')
        context=self.input_v1(event,deadline=deadline,valid_at=projection.valid_at,known_at=projection.known_at)
        request=NaturalQuestionRequestV1(caller_deadline=deadline,question=context['original_text'])
        answer,clarification,mode,packet=await answer_natural_from_projection_v1(projection,request)
        self._active_deadline=deadline;self._grounding_answer=answer;self._grounding_packet=packet;self._grounding_projection=projection
        return context,answer,clarification,mode,packet
    def validate_content_v1(self,job,content):
        if job.purpose=='qualified-answer-synthesis-v1':
            if self._grounding_answer is None or digest(self._grounding_answer.model_dump(mode='json'))!=job.grounding_sha256:raise PermissionError('actual prepared qualified grounding differs')
            from .qualified_synthesis_v1 import validate_qualified_synthesis_v1
            if type(content) is not str:raise ValueError('complete structured synthesis content required')
            context=self.current_for_job_v1(job,deadline=self._active_deadline)
            validate_qualified_synthesis_v1(content.encode('utf8'),self._grounding_answer,interview=context['thread_mode']=='interview')

    def cost_scope_v1(self,job,broker,*,deadline):
        from .question_cost_settlement_v1 import OriginalQuestionCostScopeV1
        c=self._config();pin=c.cost_settlement
        if pin is None:raise PermissionError('independently installed original cost settlement authority missing')
        scope=_parse(OriginalQuestionCostScopeV1,_pinned(pin.path,pin.sha256,65536))
        result=self.observe_v1(job.dispatch_id,{'schema_version':1,'protocol':'question-effect-cost-check-v1','operation_id':str(job.dispatch_id)},deadline=deadline)
        scope.check_v1(result['cost_context'],c,broker)
        return scope,result['cost_context']

    def read_effect_receipt_v1(self,job,broker):
        """Only actual current SQL job + native custody + settled central truth."""
        import hashlib
        from .native_factory import NativeBrokerEgress,verify_ledger
        from .provider_adapter import Budget,_budget_execute_v1
        from .protected_inputs_v1 import protected_file,parse_canonical_object_v1
        from .question_native_authority_v1 import validate_question_wire_v1
        if type(broker) is not NativeBrokerEgress:raise TypeError('actual native custody owner required')
        deadline=self._active_deadline
        self.current_for_job_v1(job,deadline=deadline)
        raw,wire,wire_record_sha=broker._question_custody_v1(job.dispatch_id,expected_job_sha256=digest(job.model_dump(mode='json')))
        if wire['complete'] is not True:raise PermissionError('incomplete retained question wire; UNKNOWN')
        native_path=str(broker._receipts/str(job.dispatch_id))+'.json'
        native_raw=protected_file(native_path,limit=32*1024*1024)
        _pinned(native_path,hashlib.sha256(native_raw).hexdigest(),32*1024*1024)
        native=parse_canonical_object_v1(native_raw,limit=32*1024*1024)
        if native.get('failed') is not False or(native.get('dispatch_id'),native.get('reservation_id'),native.get('job_hash'),native.get('wire_custody'),native.get('raw_response'))!=(str(job.dispatch_id),wire['reservation_id'],wire['job_hash'],wire,raw.decode('utf8')):raise PermissionError('actual native response custody is not successful')
        data=validate_question_wire_v1(raw.decode('utf8'),job)
        identity=verify_ledger(broker._url,broker._registry,trusted_registry_hash=broker._registry_hash,key_fingerprint=broker._key_fingerprint,now=datetime.now(timezone.utc),protected_deadline=deadline)
        budget=Budget(broker._url,ledger_identity_hash=identity,protected_deadline=deadline)
        with budget._connection_v1() as connection:
            row=_budget_execute_v1(connection,'SELECT r.workspace_id,r.artifact_id,r.batch_id,r.purpose,r.attempt,r.pricing_hash,s.actual_usd,s.status,s.response_hash,s.failure_kind FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id) WHERE r.reservation_id=%s',(UUID(wire['reservation_id']),)).fetchone()
        response_sha=hashlib.sha256(raw).hexdigest() if job.purpose=='qualified-query-embedding-v1' else digest({'response':data['choices'][0]['message']['content']})
        if row is None or row[:6]!=(job.workspace_id,job.artifact_id,job.batch_id,job.purpose,1,digest(job.pricing.model_dump(mode='json'))) or row[7:]!=('completed',response_sha,None):raise PermissionError('actual central settlement unavailable/UNKNOWN; no answer')
        self.current_for_job_v1(job,deadline=deadline)
        if _pinned(native_path,hashlib.sha256(native_raw).hexdigest(),32*1024*1024)!=native_raw:raise PermissionError('actual native custody changed')
        # Return retained bytes only to the same already-current source consumer.
        return {'raw':raw,'wire':wire,'wire_record_sha256':wire_record_sha,'native_receipt_sha256':hashlib.sha256(native_raw).hexdigest(),'settled_response_sha256':response_sha}
