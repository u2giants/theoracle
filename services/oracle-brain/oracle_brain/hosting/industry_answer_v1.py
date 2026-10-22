"""Qualified outside-reference reads through the existing own-recipient channel.

This supplies no research registration, fetch, schedule, qualification or policy
authority. All reference readers are independently installed for the same actual
model-history recipient. The original request fence and close owner are shared.
"""
from datetime import datetime,timezone
from typing import Literal
from uuid import UUID
import hashlib
from pydantic import AwareDatetime,model_validator
from ..operating_model.contracts import StrictRecord,digest
from ..operating_model.protected_inputs_v1 import parse_canonical_object_v1
from ..operating_model.request_deadline_v1 import request_remaining_v1
from ..research.qualified_brief_v1 import QualifiedIndustryBriefV1


class IndustryQuestionRequestV1(StrictRecord):
    protocol:Literal['qualified-industry-question-v1']
    operation:Literal['contexts','brief']
    decision_id:UUID|None
    caller_deadline:AwareDatetime
    @property
    def expires_at(self):
        # SAME owned result loop consumes the original caller window; no new
        # clock, field, deadline, default or authority is introduced here.
        return self.caller_deadline

    @model_validator(mode='after')
    def closed_selection(self):
        if (self.operation=='brief')!=(self.decision_id is not None):
            raise ValueError('only an existing qualified decision selects a brief')
        return self


def parse_industry_question_v1(raw):
    value=parse_canonical_object_v1(raw,limit=4096)
    if (set(value)!=set(IndustryQuestionRequestV1.model_fields)
            or type(value.get('schema_version')) is not int or value['schema_version']!=1
            or value.get('decision_id') is not None and str(UUID(value['decision_id']))!=value['decision_id']):
        raise PermissionError('complete canonical industry question required')
    return IndustryQuestionRequestV1.model_validate_json(raw)


async def answer_industry_v1(owner,request,raw):
    """Called only by the SAME concrete authenticated answer service/owned loop."""
    from .connected_answer_service_v1 import ProtectedConnectedAnswerServiceV1
    from .replacement_result_service_v1 import _close_owned_projection_v1
    if type(owner) is not ProtectedConnectedAnswerServiceV1 or type(request) is not IndustryQuestionRequestV1:
        raise PermissionError('same concrete protected answer owner required')
    request_remaining_v1();settings=owner.settings;c=settings.config
    deadline=min(request.caller_deadline,settings.current())
    if not datetime.now(timezone.utc)<deadline:raise PermissionError('original comparison request elapsed')
    authority,_=settings.consumer()
    metadata=authority._metadata(c.model_id,deadline=deadline)
    version=metadata['manifest']['version'];projection=None
    try:
        projection=settings.projection(version,deadline=deadline)
        comparison=QualifiedIndustryBriefV1(projection,settings.reference_readers_v1())
        if request.operation=='contexts':result=await comparison.contexts_v1(deadline=deadline)
        else:result=await comparison.brief_v1(decision_id=request.decision_id,deadline=deadline)
        packet=comparison._verified_packet_v1
        settings.current();request_remaining_v1()
    finally:
        if projection is not None:await _close_owned_projection_v1(owner,projection,deadline)
    for reader,retained in comparison._verified_reference_receipts_v1:
        if reader.latest_v1(deadline=deadline)!=retained:
            raise PermissionError('reference changed during owned projection close')
    latest=authority.projection_delivery_v1(c.model_id,version,deadline=deadline)
    projection._same_packet_v1(packet,(packet[0],packet[1],packet[2],latest))
    end=min(deadline,settings.current(),latest.valid_until,datetime.fromisoformat(result['valid_until']))
    request_remaining_v1();checked=datetime.now(timezone.utc)
    if checked>=end:raise PermissionError('comparison access expired before publication')
    original=parse_canonical_object_v1(raw,limit=4096)
    return dict(schema_version=1,protocol='qualified-industry-answer-v1',
        principal_id=str(c.principal_id),workspace_id=str(c.workspace_id),model_id=str(c.model_id),
        channel=settings.peer.channel,operation=request.operation,decision_id=original['decision_id'],
        request_sha256=hashlib.sha256(raw).hexdigest(),
        query_sha256=digest({k:original[k] for k in ('schema_version','protocol','operation','decision_id')}),
        checked_at=checked.isoformat(),expires_at=end.isoformat(),current_read_lease_only=True,
        retained_receipt_body_sha256=latest.retained_receipt_body_sha256,
        result=result,company_policy=False,business_accepted=False,automatic_action_authorized=False)
