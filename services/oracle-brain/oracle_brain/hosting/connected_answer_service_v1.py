"""One separately installed read-only answering service for web or employee MCP.

Actual peer verification belongs to the existing shared bounded listener. The
owned asynchronous loop carries its exact original fence; no expected peer bytes
are substituted as observed bytes. No provider, write, ACK adoption or retry.
"""
from datetime import datetime,timezone
from dataclasses import dataclass
from types import SimpleNamespace
import time
from pydantic import AwareDatetime
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.protected_inputs_v1 import parse_canonical_object_v1,_parse
from oracle_brain.operating_model.request_deadline_v1 import request_remaining_v1
from oracle_brain.workflows.answer import AnswerQueryV1,answer_from_projection_v1
from oracle_brain.workflows.natural_answer_v1 import (NaturalQuestionRequestV1,parse_natural_question_request_v1,
    natural_intent_v1,answer_natural_from_projection_v1)
from .connected_answer_settings_v1 import ConnectedAnswerSettingsV1
from ._protected_control_listener_v1 import _protected_control_listener_v1

class AnswerRequestV1(StrictRecord):
    caller_deadline:AwareDatetime
    query:AnswerQueryV1
    @property
    def expires_at(self):return self.caller_deadline

def parse_answer_request_v1(raw):
    obj=parse_canonical_object_v1(raw,limit=65536)
    if obj.get('protocol')=='qualified-industry-question-v1':
        from .industry_answer_v1 import parse_industry_question_v1
        return parse_industry_question_v1(raw)
    if obj.get('protocol')=='qualified-workspace-question-v1':
        from .qualified_workspace_v1 import parse_workspace_request_v1
        return parse_workspace_request_v1(raw)
    if 'protocol' in obj:
        return parse_natural_question_request_v1(raw)
    if type(obj.get('schema_version')) is not int or obj['schema_version']!=1:raise ValueError('exact answer request version required')
    if set(obj)!=set(AnswerRequestV1.model_fields) or type(obj.get('query')) is not dict or set(obj['query'])!=set(AnswerQueryV1.model_fields):raise ValueError('complete closed answer request and query required')
    return AnswerRequestV1.model_validate_json(raw)

class ProtectedConnectedAnswerServiceV1:
    def __init__(self,settings):
        if type(settings) is not ConnectedAnswerSettingsV1:raise TypeError('actual protected answer settings required')
        settings.current();self.settings=settings;self._owned_closes={};self._cleanup_unknown=False
    async def handle_answer_v1(self,raw):
        from .replacement_result_service_v1 import _close_owned_projection_v1
        request_remaining_v1()
        if self._cleanup_unknown:raise PermissionError('owned answer cleanup requires observation')
        request=parse_answer_request_v1(raw);s=self.settings;c=s.config
        from .industry_answer_v1 import IndustryQuestionRequestV1,answer_industry_v1
        if type(request) is IndustryQuestionRequestV1:return await answer_industry_v1(self,request,raw)
        from .qualified_workspace_v1 import WorkspaceRequestV1,answer_workspace_v1
        if type(request) is WorkspaceRequestV1:return await answer_workspace_v1(self,request,raw)
        natural=type(request) is NaturalQuestionRequestV1
        if natural:
            intent=natural_intent_v1(request.question,now=datetime.now(timezone.utc))
            valid_at,known_at=(intent.valid_at,intent.known_at) if intent.clarification is None else (None,None)
        else:valid_at,known_at=request.query.valid_at,request.query.known_at
        until=s.current();deadline=min(request.caller_deadline,until)
        if not datetime.now(timezone.utc)<deadline:raise PermissionError('original answer window expired')
        authority,blobs=s.consumer()
        # Current/historical selection is exclusively the actual fixed SQL017
        # owner. Client expected_version only narrows, never selects authority.
        metadata=authority._metadata(c.model_id,deadline=deadline,valid_at=valid_at,known_at=known_at)
        version=metadata['manifest']['version']
        if not natural and request.query.expected_version is not None and version!=request.query.expected_version:raise PermissionError('selected authorized model version changed')
        projection=None
        try:
            projection=s.projection(version,deadline=deadline,valid_at=valid_at,known_at=known_at)
            if natural:answer,clarification,resolved_mode,packet=await answer_natural_from_projection_v1(projection,request)
            else:answer,packet=await answer_from_projection_v1(projection,request.query)
            s.current();request_remaining_v1()
        finally:
            if projection is not None:await _close_owned_projection_v1(self,projection,deadline)
        # Keep authority after the last actual graph/private read and observed
        # pool close. Loss of any source permission withholds the entire answer.
        latest=authority.projection_delivery_v1(c.model_id,version,deadline=deadline,valid_at=valid_at,known_at=known_at)
        projection._same_packet_v1(packet,(packet[0],packet[1],packet[2],latest))
        end=min(deadline,s.current(),latest.valid_until)
        request_remaining_v1();now=datetime.now(timezone.utc)
        if not now<end:raise PermissionError('original answer window expired before publication')
        common=dict(schema_version=1,protocol='qualified-connected-answer-v1',principal_id=str(c.principal_id),workspace_id=str(c.workspace_id),model_id=str(c.model_id),channel=s.peer.channel,
            checked_at=now.isoformat(),expires_at=end.isoformat(),
            current_read_lease_only=True,retained_receipt_body_sha256=latest.retained_receipt_body_sha256,
            retained_delivered_at=latest.retained_delivered_at.isoformat(),retained_receipt_recorded_at=latest.retained_receipt_recorded_at.isoformat(),retained_projection_lease_until=latest.retained_receipt.lease_until)
        if natural:
            import hashlib
            original=parse_canonical_object_v1(raw)
            return common|dict(protocol='qualified-natural-answer-v1',state='answer' if answer is not None else 'clarification',
                query_sha256=digest({k:original[k] for k in ('schema_version','protocol','question')}),
                request_sha256=hashlib.sha256(raw).hexdigest(),resolved_mode=resolved_mode,
                answer=answer.model_dump(mode='json') if answer is not None else None,clarification=clarification)
        return common|dict(query_sha256=digest(parse_canonical_object_v1(raw)['query']),answer=answer.model_dump(mode='json'))

@dataclass(frozen=True)
class _AnswerPeerSettingsV1:
    settings:ConnectedAnswerSettingsV1
    @property
    def profile(self):
        p=self.settings.peer
        return SimpleNamespace(listen_host=p.listen_host,listen_port=p.listen_port,client_uri=p.client_uri,client_certificate_sha256=p.client_certificate_sha256,
            server_certificate_file=p.server_certificate.path,server_key_file=p.server_key.path,client_ca_file=p.client_ca.path)
    def current(self):return self.settings.current()

class _AnswerIngressV1:
    def __init__(self,owned):self.owned=owned
    def execute_v1(self,raw):
        from oracle_brain.operating_model.request_deadline_v1 import _request_end_v1
        request_remaining_v1();original_end=_request_end_v1.get()
        # Trusted same-handler ContextVar only; no caller supplied clock/fence.
        return self.owned.result(None,raw,absolute_monotonic_deadline=original_end)

def protected_connected_answer_server_v1(settings):
    from .replacement_result_service_v1 import _ResultOwnedLoopV1
    if type(settings) is not ConnectedAnswerSettingsV1:raise TypeError('actual protected answer settings required')
    settings.current();service=ProtectedConnectedAnswerServiceV1(settings);owned=_ResultOwnedLoopV1(service)
    try:
        path='/v1/employee/answer' if settings.peer.channel=='web' else '/v1/employee/mcp-answer'
        server=_protected_control_listener_v1(_AnswerPeerSettingsV1(settings),_AnswerIngressV1(owned),path=path,parse_request=parse_answer_request_v1,encode_response=canonical_bytes,maximum_response_bytes=262144)
        original_close=server.server_close
        def close():
            original_close();owned.close()
        server.server_close=close;server.answer_owned_loop=owned
        return server
    except BaseException:
        owned.close();raise
