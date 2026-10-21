"""Deterministic final guard after the independent bounded role critique."""
import re
from ..contracts import digest


def validate_report(report,pack,*,metrics=None,event_artifact_hash=None,expected_evidence=None):
    if report.model_artifact_hash!=pack['artifact_hash']:raise ValueError('report model artifact changed')
    wanted={f['finding_id'] for f in pack.get('findings',[]) if f['status']=='unresolved'}
    if not wanted<=set(report.finding_ids):raise ValueError('report erased unresolved source disagreement')
    citations={digest(e) for e in pack.get('citations',[])}
    if any(not set(c.citation_ids)<=citations for c in report.clauses):raise ValueError('report invented evidence citation')
    if report.variant=='documentary':
        if report.measurements is not None or report.event_artifact_hash is not None:raise ValueError('documentary model cannot invent measured numbers')
    elif metrics is None or event_artifact_hash is None or report.measurements!=metrics or report.event_artifact_hash!=event_artifact_hash:
        raise ValueError('writer changed deterministic metric values or event provenance')
    text=' '.join(c.text for c in report.clauses)+' '+' '.join(e.hypothesis for e in report.experiments)
    if report.schema_version==2:
        from .recommendations import EvidenceRevision,recommendation_from_payload
        if type(expected_evidence) is not EvidenceRevision:
            raise PermissionError('root-derived exact recommendation evidence required')
        advice_text=[]
        for raw in report.recommendations:
            recommendation=recommendation_from_payload(raw)
            if recommendation.evidence!=expected_evidence:
                raise ValueError('recommendation evidence differs from exact current upstream binding')
            advice_text.append(recommendation.scope_note)
            for option in recommendation.options:
                advice_text.append(option.title)
                if option.forecast is not None:advice_text.extend(option.forecast.assumptions)
        text+=' '+' '.join(advice_text)
    if re.search(r'\b(ROI|savings|save\s+\d|caused|causes)\b',text,re.I):raise ValueError('unmeasured savings or causation claim')
    if report.actual_data_acceptance=='accepted':raise PermissionError('actual event/business acceptance requires external admitted receipt')
    return report
