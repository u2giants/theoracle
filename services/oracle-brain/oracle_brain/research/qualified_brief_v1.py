"""Concrete current qualified-model/read-reference comparison, never company policy.

The independent model history and external-reference read owners both remain
mandatory. Fetching, source qualification, graph delivery and business acceptance
are distinct capabilities; this comparison creates none of them.
"""
from datetime import datetime, timezone
from uuid import UUID
from ..operating_model.consolidation_authority_v1 import _review_evidence
from ..operating_model.sdk_projection import ConsolidatedMetadataSDKProjectionV1
from ..operating_model.contracts import canonical_bytes, digest
from ..operating_model.industry_reference_v1 import (
    IndustryReferenceEvidenceV1, CompanyDecisionContextEvidenceV1, parse_industry_assertion_v1)
from ..operating_model.request_deadline_v1 import request_remaining_v1
from .maintained_read_v1 import MaintainedResearchReaderV1
from .registry import Source
from .applicability import DecisionContext, ExternalReference, CurrentReference, assess_applicability


def _current_assertion(assertion, now):
    return (assertion.valid_time == 'evidenced' and assertion.valid_from <= now
            and (assertion.valid_to is None or now < assertion.valid_to)
            and not assertion.opposing_observations and not assertion.unknown_finding_ids)


def _compare_reference_v1(context_assertion, context, assertion, evidence, retained, now):
    """Only documentary comparison; input DTOs cannot create a serving grant."""
    source = Source(**retained['registration'])
    reference = retained['reference']
    missing = reference is None
    if str(evidence.registered_source_id) != retained['source_id']:
        raise PermissionError('independently selected research source differs')
    if (evidence.original.workspace_id != UUID(retained['workspace_id'])
            or not missing and evidence.original.original_sha256 != reference['content_sha256']):
        raise PermissionError('qualified original differs from the actual retained reference')
    actual = {} if missing else reference
    qualified = ExternalReference(reference_id=str(evidence.reference_id), source_id=source.source_id,
        source_version=evidence.source_version, content_sha256=actual.get('content_sha256'),
        original_url=source.url, publisher=source.publisher, jurisdiction=evidence.jurisdiction,
        product_scope=evidence.product_scope, channel_scope=evidence.channel_scope,
        license_permission=evidence.license_permission, publication_date=evidence.publication_date,
        effective_date=evidence.effective_date,
        retrieved_at=datetime.fromisoformat(actual['retrieved_at']) if actual else None,
        reviewed_at=evidence.reviewed_at,
        refresh_due=datetime.fromisoformat(actual['refresh_due']) if actual and actual.get('refresh_due') else None,
        review_due=evidence.review_due)
    context_fields=context.model_dump(mode='json')
    wanted = DecisionContext.model_validate_json(canonical_bytes({
        name:context_fields[name] for name in ('jurisdiction','product_scope','channel_scope','required_review_after')
    }))
    # Source version is the version evidenced by this qualified original; its
    # hash must match the independently current retained body's actual receipt.
    current = CurrentReference(reference_id=str(evidence.reference_id), source_id=source.source_id,
        source_version=evidence.source_version, content_sha256=actual['content_sha256']) if actual and evidence.source_version else None
    assessment=assess_applicability(wanted,qualified,source=source,current=current,now=now)
    if not _current_assertion(context_assertion,now) or not _current_assertion(assertion,now):
        assessment=assessment.model_copy(update={'state':'UNKNOWN','reasons':('qualified_context_or_reference_is_conflicted_unknown_or_outside_valid_time',)})
    return {'reference':qualified.model_dump(mode='json'),'comparison':assessment.model_dump(mode='json'),
            'assertion_id':str(assertion.assertion_id),'assertion_revision':assertion.revision,
            'retained_receipt_event_id':actual.get('receipt_event_id'),
            'refresh':retained['refresh'],'source_qualified_by_fetch':False}


class QualifiedIndustryBriefV1:
    def __init__(self, projection, readers):
        if (type(projection) is not ConsolidatedMetadataSDKProjectionV1
                or type(readers) is not tuple or not 1<=len(readers)<=32
                or any(type(r) is not MaintainedResearchReaderV1 for r in readers)):
            raise PermissionError('actual accepted readonly SDK and independent reference readers required')
        authority=projection.authority
        identities=[]
        for reader in readers:
            c=reader._authority.settings.config
            if (c.principal_id,c.workspace_id)!=(authority.binding.principal_id,authority.binding.workspace_id):
                raise PermissionError('reference read cannot borrow another employee or workspace')
            identities.append(c.source_id)
        if len(set(identities))!=len(identities):raise PermissionError('duplicate reference read owner')
        self._authority,self._projection,self._readers=authority,projection,readers

    async def brief_v1(self, *, decision_id, deadline):
        if type(decision_id) is not UUID or deadline!=self._projection.deadline:
            raise PermissionError('exact existing decision and original SDK deadline required')
        request_remaining_v1()
        a=self._authority
        core,metadata,payload,delivery=await self._projection.load()
        parsed=[(item,parse_industry_assertion_v1(item)) for item in core.assertions]
        references=[value for _,value in parsed if type(value) is IndustryReferenceEvidenceV1]
        if len(references)>128 or len({r.reference_id for r in references})!=len(references):
            raise PermissionError('one bounded exact qualified reference version per identity required')
        contexts=[(item,value) for item,value in parsed if type(value) is CompanyDecisionContextEvidenceV1 and value.decision_id==decision_id]
        if len(contexts)!=1:raise PermissionError('one exact qualified company decision context required')
        ca,context=contexts[0];rows=[];receipts=[];now=datetime.now(timezone.utc)
        for reader in self._readers:
            retained=reader.latest_v1(deadline=deadline);receipts.append((reader,retained))
            candidates=[(item,value) for item,value in parsed if type(value) is IndustryReferenceEvidenceV1
                and str(value.registered_source_id)==retained['source_id']]
            if not candidates:
                reasons=['independent_qualified_reference_metadata_missing']
                if retained['refresh']['state']=='rights_gap':reasons.append('licensed_access_unavailable')
                rows.append({'registered_source_id':retained['source_id'],'state':'UNKNOWN',
                    'reasons':reasons,'publisher':retained['registration']['publisher'],
                    'original_url':retained['registration']['url'],'access':retained['registration']['access'],
                    'refresh':retained['refresh']})
                continue
            if len(candidates)>128:raise PermissionError('bounded qualified reference population required')
            for assertion,value in candidates:
                if value.original not in core.model.source_refs:
                    raise PermissionError('reference original absent from complete qualified source population')
                row=_compare_reference_v1(ca,context,assertion,value,retained,now)
                row['evidence']=_review_evidence(payload,assertion.model_dump(mode='json'));rows.append(row)
        # Both independent owners must still authorize the SAME bytes/receipts
        # at delivery. These reads do not renew any source or processing lease.
        for reader,prior in receipts:
            if reader.latest_v1(deadline=deadline)!=prior:raise PermissionError('reference changed during comparison')
        fresh=await self._projection.verify(payload)
        self._projection._same_packet_v1((core,metadata,payload,delivery),fresh)
        request_remaining_v1()
        until=min(deadline,datetime.fromisoformat(metadata['validUntil']),
            *(min(r._authority.settings.config.expires_at,r._authority.settings.config.original_horizon,
                  r._profile.expires_at,r._profile.original_horizon) for r in self._readers))
        checked=datetime.now(timezone.utc)
        if checked>=until:raise PermissionError('original comparison authority expired before delivery')
        return {'schema_version':1,'purpose':'qualified-industry-comparison-v1',
            'workspace_id':str(a.binding.workspace_id),'model_id':str(a.binding.model_id),
            'model_version':core.model.version,'model_content_sha256':metadata['manifest']['content_hash'],
            'decision_id':str(decision_id),'context_assertion_id':str(ca.assertion_id),
            'context_evidence':_review_evidence(payload,ca.model_dump(mode='json')),'references':rows,
            'checked_at':checked.isoformat(),'valid_until':until.isoformat(),
            'comparison_sha256':digest(rows),'company_policy':False,'business_accepted':False,
            'graph_delivery_verified':True,'automatic_action_authorized':False}
