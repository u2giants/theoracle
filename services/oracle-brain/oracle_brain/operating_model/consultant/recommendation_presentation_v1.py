"""Bounded current permitted documentary presentation; no source/viewer grant."""
from datetime import datetime
from ..contracts import canonical_bytes
from ..source_receipts import EvidenceRef,SourceRef
from ..consolidation_authority_v1 import _review_evidence
from .recommendation_actions_v1 import _planned_source_measurement_v1

MAX_SELECTORS=64
MAX_QUOTES=64
MAX_QUOTE_BYTES=32768


def readable_recommendation_evidence_v1(core,item,parent_payload,*,now:datetime):
    allowed=set(core.model.source_refs)
    if allowed!={SourceRef.model_validate_json(canonical_bytes(ref)) for ref in parent_payload['source_refs']}:
        raise PermissionError('complete actual current parent source population required')
    candidates=[]
    for plan in sorted(item.experiments,key=lambda p:str(p.experiment_id)):
        for phase in ('baseline','followup'):
            for assertion in sorted(core.assertions,key=lambda a:(str(a.assertion_id),a.revision)):
                try:
                    selected=_planned_source_measurement_v1(core,item,experiment_id=plan.experiment_id,phase=phase,
                        assertion_id=assertion.assertion_id,assertion_revision=assertion.revision,now=now)
                except PermissionError:continue
                candidates.append({'experiment_id':str(plan.experiment_id),'phase':phase,'assertion_id':str(assertion.assertion_id),
                    'assertion_revision':assertion.revision,'measurement':selected['measurement'],'reported_only':True,'causal_savings':False,'realized_savings_verified':False})
    candidate_gap=len(candidates)>MAX_SELECTORS
    selected_candidates=candidates[:MAX_SELECTORS]
    # Include evidence for options/opposition AND every eligible measurement
    # selector. Complete captured value remains bound to its actual assertion.
    refs={ref for option in item.advice['options'] for ref in option['evidence_refs']}|set(item.advice['opposing_evidence'])
    ids={str(c['assertion_id']) for c in selected_candidates}
    ids|={ref.split(':')[1] for ref in refs}
    quotes={polarity:[] for polarity in ('supporting','opposing','unknown','temporal')};seen=set();used=0;quote_gap=False
    for assertion in sorted(core.assertions,key=lambda a:(str(a.assertion_id),a.revision)):
        if str(assertion.assertion_id) not in ids:continue
        evidence=_review_evidence(parent_payload,assertion.model_dump(mode='json'))
        for polarity,values in evidence.items():
            for value in values:
                quote=EvidenceRef.model_validate_json(canonical_bytes(value))
                if quote.ref not in allowed:raise PermissionError('quote source outside exact current parent population')
                identity=(polarity,str(quote.ref.source_id),quote.ref.revision,quote.start,quote.end,quote.quote)
                if identity in seen:continue
                seen.add(identity);count=len(quote.quote.encode('utf8'))
                if sum(len(v) for v in quotes.values())>=MAX_QUOTES or used+count>MAX_QUOTE_BYTES:
                    quote_gap=True;continue
                used+=count
                quotes[polarity].append({'source_id':str(quote.ref.source_id),'source_revision':quote.ref.revision,
                    'start':quote.start,'end':quote.end,'quote':quote.quote,'original_sha256':quote.ref.original_sha256,'reading_sha256':quote.ref.reading_sha256})
    return {'measurement_sources':selected_candidates,'measurement_coverage_gap':candidate_gap,
        'evidence':quotes,'evidence_coverage_gap':quote_gap}
