"""Protected conversation composition; external installation is independently required.

No API caller supplies a job, prompt, hash, receipt, actor or qualified sources.
The existing broker retains the key/ledger/wire owners. A durable claim commits
before any native effect. A claim is never a permission grant or retry ticket.
"""
from datetime import datetime,timezone
from pathlib import Path
from decimal import Decimal
from oracle_brain.operating_model.raw_endpoint_inventory_v1 import RawBillingBoundsV1
from .purpose_journey_v2 import _worker_file
from uuid import UUID,uuid5
import hashlib,json
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.native_factory import NativeBrokerEgress,EmployeeConversationDispatchJobV1
from .conversation_control_v1 import ConversationControlV1,ConversationUnknown
from .original_intake_v1 import _pinned,_parse
from .conversation_processing_v1 import ProtectedConversationProcessingV1


from oracle_brain.operating_model.conversation_native_authority_v1 import (
    conversation_request_v1,_current_billing,current_text_metadata_v1,
    current_conversation_dispatch_v1,ConversationWireLiabilityUnknown,
    conversation_wire_liability_lower_bound_v1,validate_conversation_wire_v1)


def _actual_conversation_settlement_v1(broker,job,observed,wire):
    # Actual central Budget owner, read only after its transaction commits.
    # Native private metadata selects its own reservation, never caller input.
    import psycopg
    from oracle_brain.operating_model.native_factory import verify_ledger
    verify_ledger(broker._url,broker._registry,trusted_registry_hash=broker._registry_hash,
        key_fingerprint=broker._key_fingerprint,now=datetime.now(timezone.utc))
    rid=UUID(observed['reservation_id'])
    cost=Decimal(str(wire['usage']['cost']))
    with psycopg.connect(broker._url,connect_timeout=5) as c:
        c.execute('SET TRANSACTION READ ONLY')
        c.execute("SET LOCAL statement_timeout='5s'")
        row=c.execute("""SELECT r.workspace_id,r.artifact_id,r.batch_id,r.purpose,r.attempt,r.pricing_hash,
            s.actual_usd,s.status,s.response_hash,s.failure_kind FROM oracle2.operating_dispatch_reservations r
            JOIN oracle2.operating_dispatch_receipts s USING(reservation_id) WHERE r.reservation_id=%s""",(rid,)).fetchone()
    if row!=(job.workspace_id,job.artifact_id,job.batch_id,job.purpose,1,digest(job.pricing.model_dump(mode='json')),
            cost.quantize(Decimal('.000001'),rounding='ROUND_CEILING'), 'completed',digest({'response':wire['choices'][0]['message']['content']}),None):
        raise PermissionError('actual committed central conversation settlement unavailable')

class ProtectedConversationFactoryV1:
    def __init__(self,control,broker):
        if type(control) is not ConversationControlV1 or type(broker) is not NativeBrokerEgress:raise TypeError('existing exact protected control and native broker required')
        self.control=control;self.broker=broker
    def _job(self):
        from ._protected_control_listener_v1 import request_remaining_v1
        request_remaining_v1()
        s=self.control.settings;s.current();pin=s.config.response_job
        allocation=self.broker._allocation
        if allocation is None or not datetime.now(timezone.utc)<allocation.expires_at:raise PermissionError('separately admitted finite conversation allocation missing')
        if pin is None:raise PermissionError('separately appointed immutable conversation job missing')
        raw=_pinned(pin.path,pin.sha256,262144);job=_parse(EmployeeConversationDispatchJobV1,raw)
        actual=self.broker._resolve(job.dispatch_id)
        if type(actual) is not EmployeeConversationDispatchJobV1 or canonical_bytes(actual.model_dump(mode='json'))!=raw or self.broker._authorize(actual) is not True:
            raise PermissionError('actual independently appointed conversation job unavailable')
        if job.batch_id!=allocation.batch_id or job.pricing.expires_at>allocation.expires_at:raise PermissionError('original conversation allocation/job horizon differs')
        _current_billing(self.control,job,self.broker)
        if s.config.processing_config is None:raise PermissionError('independent actual model-worker appointment missing')
        actual=ProtectedConversationProcessingV1(s.config.processing_config).current_for_job_v1(job)
        if actual.snapshot.get('mode')!='ordinary':raise PermissionError('native free-text output cannot bypass interview question cap')
        s.current();return job
    def respond_v1(self,thread_id):
        if type(thread_id) is not UUID:raise TypeError('exact thread selector required')
        job=self._job();snapshot=self.control.snapshot_v1(thread_id)
        actual=ProtectedConversationProcessingV1(self.control.settings.config.processing_config).current_for_job_v1(job)
        expected=conversation_request_v1(snapshot,job,qualified_readings=actual.qualified_readings)
        if canonical_bytes(expected)!=canonical_bytes(job.request) or digest(expected)!=job.request_hash:
            raise PermissionError('actual request does not match committed conversation')
        if job.processing_request.purpose!='employee-conversation':raise PermissionError('separate conversation processing admission required')
        # No future response/body hash is selected here. This immutable operation
        # is bound to already committed input and independently appointed job.
        command=dict(schema_version=1,command_id=str(uuid5(job.dispatch_id,'conversation-claim')),
            caller_deadline=self.control.settings.current().isoformat(),thread_id=str(thread_id),expected_revision=snapshot['revision'],
            operation='claim_response',event_id=str(job.employee_event_id),dispatch_id=str(job.dispatch_id),
            job_sha256=digest(job.model_dump(mode='json')),request_sha256=job.request_hash)
        claimed=self.control._call('apply',(canonical_bytes(command),))
        try:
            # Recheck the original protected installation/job after durable claim,
            # then broker performs all current native pricing/coverage/Budget gates.
            if self._job()!=job:raise PermissionError('conversation job drift')
            raw=self.broker.dispatch(canonical_bytes(dict(dispatch_id=str(job.dispatch_id),request_hash=job.request_hash,request=expected)),_conversation_control=self.control)
            self._job()
            def unique(pairs):
                d={}
                for k,v in pairs:
                    if k in d:raise ValueError('duplicate provider field')
                    d[k]=v
                return d
            def constant(_):raise ValueError('nonfinite provider output')
            wire=json.loads(raw,object_pairs_hook=unique,parse_constant=constant)
            choices=wire.get('choices')
            if wire.get('model')!=job.pricing.model or not isinstance(choices,list) or len(choices)!=1 or choices[0].get('finish_reason')!='stop':raise ValueError('actual complete model response required')
            message=choices[0].get('message')
            if not isinstance(message,dict) or message.get('role')!='assistant' or not isinstance(message.get('content'),str) or message.get('tool_calls') or message.get('function_call'):raise ValueError('actual display-only assistant response required')
            answer=json.loads(message['content'],object_pairs_hook=unique,parse_constant=constant)
            if not isinstance(answer,dict) or set(answer)!={'display_text'} or not isinstance(answer['display_text'],str) or not 1<=len(answer['display_text'].encode('utf-8'))<=32768:raise ValueError('bounded display-only response required')
            receipt=self.broker._receipts/(str(job.dispatch_id)+'.json')
            retained=_worker_file(receipt)
            # Existing broker owns this actual native receipt; no caller receipt.
            observed=json.loads(retained)
            wire_bytes=_worker_file(self.broker._receipts/(str(job.dispatch_id)+'.wire'),limit=16*1024*1024)
            if (wire_bytes!=raw or observed.get('failed') is not False or observed.get('job_hash')!=digest(job.model_dump(mode='json')) or observed.get('request_hash')!=job.request_hash or observed.get('key_fingerprint')!=self.broker._key_fingerprint or observed.get('ledger_identity_hash')!=self.broker._registry_hash):raise PermissionError('actual retained native custody differs')
            _actual_conversation_settlement_v1(self.broker,job,observed,wire)
            current=self.control.snapshot_v1(thread_id)
            if current['revision']!=claimed['revision']:raise PermissionError('conversation changed after paid effect')
            complete=dict(schema_version=1,command_id=str(uuid5(job.dispatch_id,'conversation-display')),
                caller_deadline=self.control.settings.current().isoformat(),thread_id=str(thread_id),expected_revision=current['revision'],
                operation='complete_response',dispatch_id=str(job.dispatch_id),response_text=answer['display_text'],native_receipt_sha256=hashlib.sha256(retained).hexdigest())
            return self.control._call('apply',(canonical_bytes(complete),))
        except Exception:
            raise ConversationUnknown('Conversation response UNKNOWN; original operation/wire/receipt retained; no automatic resend') from None
