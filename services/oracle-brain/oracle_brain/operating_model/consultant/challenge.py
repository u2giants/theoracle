"""Deterministic final guard after the independent bounded role critique."""
import re
from ..contracts import digest


def validate_report(report,pack,*,metrics=None,event_artifact_hash=None):
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
    if re.search(r'\b(ROI|savings|save\s+\d|caused|causes)\b',text,re.I):raise ValueError('unmeasured savings or causation claim')
    if report.actual_data_acceptance=='accepted':raise PermissionError('actual event/business acceptance requires external admitted receipt')
    return report
