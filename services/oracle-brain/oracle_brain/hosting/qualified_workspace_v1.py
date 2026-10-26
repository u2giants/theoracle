"""Descriptive workspace over the same current, qualified, read-only SDK owner.

No producer, permission issuer, policy decision, correction or source fetch lives
here. Display and export are the same bounded current read; omitted populations
are counted and never called complete. Original access remains separate.
"""
from datetime import datetime, timezone
from typing import Literal
import hashlib
from pydantic import AwareDatetime, Field, model_validator
from ..operating_model.contracts import StrictRecord, canonical_bytes, digest
from ..operating_model.protected_inputs_v1 import parse_canonical_object_v1
from ..operating_model.request_deadline_v1 import request_remaining_v1
from ..operating_model.consolidation_contracts_v1 import AssertionScopeV1
from ..operating_model.observations import Observation
from ..operating_model.workflows.process_model import canonical_workflow_items
from ..workflows.answer import AnswerQueryV1, _pack_answer_v1


class WorkspaceRequestV1(StrictRecord):
    protocol: Literal['qualified-workspace-question-v1']
    operation: Literal['overview', 'process']
    process_id: str | None = Field(default=None, min_length=1, max_length=200)
    page: int = Field(ge=0, le=2047)
    caller_deadline: AwareDatetime

    @property
    def expires_at(self):
        return self.caller_deadline

    @model_validator(mode='after')
    def selected_process(self):
        if ((self.operation == 'process') != (self.process_id is not None)
                or self.process_id is not None and ('\x00' in self.process_id or self.process_id.strip() != self.process_id)):
            raise ValueError('one exact existing process or overview required')
        return self


def parse_workspace_request_v1(raw):
    value = parse_canonical_object_v1(raw, limit=4096)
    if set(value) != set(WorkspaceRequestV1.model_fields) or type(value.get('schema_version')) is not int:
        raise PermissionError('complete closed workspace request required')
    return WorkspaceRequestV1.model_validate_json(raw)


def _workspace_view_v1(packet, request):
    """Private packing only; this function supplies no current-read authority."""
    if type(request) is not WorkspaceRequestV1:
        raise PermissionError('exact workspace request required')
    core, metadata, payload, delivery = packet
    model = core.model
    selected = next((p for p in model.processes if p.process_id == request.process_id), None)
    if request.operation == 'process' and selected is None:
        raise PermissionError('process outside current qualified model')
    all_scope = AssertionScopeV1.model_validate_json(canonical_bytes(dict(schema_version=1,
        **{k:dict(schema_version=1, mode='all', identities=[]) for k in ('process','customer','product','region')})))
    query = AnswerQueryV1(question='Current documentary accounts' if selected is None else selected.label, mode='global' if selected is None else 'connected',
        scope=all_scope, process_ids=() if selected is None else (selected.process_id,),
        max_records=64, max_bytes=131072, page=request.page)
    # Reuse the actual answer owner for exact-body identity, evidence validation,
    # exception grouping, historical status and honest bounded record coverage.
    answer = _pack_answer_v1(core, payload, metadata, query, observed_at=delivery.checked_at)
    observations = {o['observation_id']:Observation.model_validate_json(canonical_bytes(o)) for o in payload['observations']}
    def evidence(ids):
        if not set(ids) <= observations.keys():
            raise PermissionError('qualified workflow evidence missing')
        quotes=[e.model_dump(mode='json') for oid in ids for e in observations[oid].evidence]
        if not quotes or len(quotes)>1000:
            raise PermissionError('whole quote-supported item required within display bound')
        return quotes
    processes = sorted(model.processes, key=lambda p:p.process_id)
    shown = processes[:64]
    workflows = []
    if selected is not None:
        for workflow in model.workflows:
            if workflow.process_id != selected.process_id:
                continue
            items = []
            for collection, identity, item in canonical_workflow_items(workflow):
                items.append(dict(collection=collection, identity=identity,
                    value=item.model_dump(mode='json', exclude={'support'}),
                    evidence=evidence(item.support.observation_ids)))
            # Never split one workflow or silently drop a branch/condition.
            if len(items)>512 or len(workflows)>=32:
                raise PermissionError('whole process exceeds bounded workspace; no partial map')
            workflows.append(dict(workflow_id=workflow.workflow_id,version=workflow.version,
                scope=workflow.scope,completeness=workflow.completeness,reported_status=workflow.status,
                items=items))
    def process_row(p):
        return dict(process_id=p.process_id,label=p.label,scope=p.scope,
            completeness=p.completeness,workflow_count=len(p.workflow_ids),evidence=evidence(p.observation_ids))
    result=dict(schema_version=1,purpose='qualified-workspace-view-v1',
        model_version=model.version,model_content_sha256=digest(payload),
        declared_population=model.declared_population,model_completeness=model.completeness,
        processes=[process_row(p) for p in shown],selected_process=process_row(selected) if selected else None,
        process_count=len(processes),returned_process_count=len(shown),
        process_list_complete=len(shown)==len(processes),selected_process_id=request.process_id,
        workflows=workflows,answer=answer.model_dump(mode='json'),
        company_wide_completeness_verified=False,company_policy_confirmed=False,
        source_health_observed=False,automatic_action_authorized=False)
    if len(canonical_bytes(result))>240000:
        raise PermissionError('whole workspace exceeds installed response bound')
    return result


async def answer_workspace_v1(owner, request, raw):
    from .connected_answer_service_v1 import ProtectedConnectedAnswerServiceV1
    from .replacement_result_service_v1 import _close_owned_projection_v1
    if type(owner) is not ProtectedConnectedAnswerServiceV1 or type(request) is not WorkspaceRequestV1:
        raise PermissionError('same concrete protected workspace owner required')
    settings=owner.settings
    if settings.config.purpose!='qualified-connected-answer-v1':
        raise PermissionError('existing qualified answer read purpose required')
    request_remaining_v1();deadline=min(request.caller_deadline,settings.current())
    authority,_=settings.consumer()
    metadata=authority._metadata(settings.config.model_id,deadline=deadline)
    projection=None
    try:
        import sys;print('ORACLE-DIAG-BACKEND-STAGE projection-enter',file=sys.stderr,flush=True)
        projection=settings.projection(metadata['manifest']['version'],deadline=deadline)
        print('ORACLE-DIAG-BACKEND-STAGE projection-exit',file=sys.stderr,flush=True)
        print('ORACLE-DIAG-BACKEND-STAGE load-enter',file=sys.stderr,flush=True)
        packet=await projection.load()
        print('ORACLE-DIAG-BACKEND-STAGE load-exit',file=sys.stderr,flush=True)
        result=_workspace_view_v1(packet,request)
        await projection.verify(packet[2])
        settings.current();request_remaining_v1()
    finally:
        if projection is not None:
            await _close_owned_projection_v1(owner,projection,deadline)
    latest=authority.projection_delivery_v1(settings.config.model_id,metadata['manifest']['version'],deadline=deadline)
    projection._same_packet_v1(packet,(packet[0],packet[1],packet[2],latest))
    end=min(deadline,settings.current(),latest.valid_until)
    checked=datetime.now(timezone.utc);request_remaining_v1()
    if checked>=end:
        raise PermissionError('original workspace reading window expired')
    original=parse_canonical_object_v1(raw,limit=4096)
    return dict(schema_version=1,protocol='qualified-workspace-answer-v1',
        principal_id=str(settings.config.principal_id),workspace_id=str(settings.config.workspace_id),
        model_id=str(settings.config.model_id),channel=settings.peer.channel,
        operation=request.operation,process_id=request.process_id,page=request.page,
        request_sha256=hashlib.sha256(raw).hexdigest(),
        query_sha256=digest({k:v for k,v in original.items() if k!='caller_deadline'}),
        checked_at=checked.isoformat(),expires_at=end.isoformat(),current_read_lease_only=True,
        retained_receipt_body_sha256=latest.retained_receipt_body_sha256,result=result,
        retained_delivered_at=latest.retained_delivered_at.isoformat(),
        retained_receipt_recorded_at=latest.retained_receipt_recorded_at.isoformat(),
        retained_projection_lease_until=latest.retained_receipt.lease_until,
        company_policy=False,business_accepted=False,automatic_action_authorized=False)
