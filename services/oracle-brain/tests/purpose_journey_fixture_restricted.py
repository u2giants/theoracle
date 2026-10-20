"""Restricted documentary answer proof: abstain or label suggestion; no graph acceptance.

Pure invented/synthetic helpers with no fcntl, DB, TLS or graphrag_sdk dependency.
"""
import json
from types import SimpleNamespace


class _RestrictedPack:
    """Invented conflicted summary pack: partial coverage, no graph acceptance."""

    def __init__(self, contents, artifact_hash='a' * 64):
        self.contents = contents
        self.artifact_hash = artifact_hash

    def recheck(self, ledger):
        return None


class _RestrictedSummary:
    def __init__(self, contents):
        self.pack = _RestrictedPack(contents)

    def recheck(self, ledger, *, qualification_guard=None):
        self.pack.recheck(ledger)


def restricted_answer_from_conflicted_model(model_json, *, intent='overview'):
    """Restricted answer for a conflicted/partial model: abstain or label suggestion.

    Never claims graph acceptance. Deterministic suggestions from linked
    unknown/conflict findings are separately labeled and never established fact.
    """
    from oracle_brain.operating_model.answer import answer_from_summary, labeled_suggestions
    from oracle_brain.hosting.replacement_public_view_v1 import documentary_answer_public_v1
    from oracle_brain.operating_model.source_receipts import SourceRef
    model = json.loads(model_json) if isinstance(model_json, (str, bytes)) else model_json
    refs = tuple(SourceRef.model_validate_json(json.dumps(r)) for r in model['source_refs'])
    findings = []
    for fid in model.get('finding_ids', ()):
        findings.append(dict(finding_id=str(fid), kind='missing_information',
            text='The owner of the ART approval handoff is not specified.',
            origin='source_reported', status='reported', scope=model.get('declared_population', ''),
            source_refs=[r.model_dump(mode='json') for r in refs], evidence_refs=[]))
    if any(w.get('completeness') == 'conflicted' for w in model.get('workflows', ())):
        findings.append(dict(finding_id='conflict-1', kind='source_conflict',
            text='Purchasing states ART production lead time is four weeks. Factory states ART production lead time is six weeks.',
            origin='reported_conflict_unverified', status='reported',
            scope=model.get('declared_population', ''),
            source_refs=[r.model_dump(mode='json') for r in refs], evidence_refs=[]))
    coverage_state = 'partial' if any(
        w.get('completeness') in ('partial', 'conflicted') for w in model.get('workflows', ())) else 'complete'
    contents = dict(state='ready', processes=model.get('processes', ()),
        workflows=model.get('workflows', ()), interfaces=(), findings=findings,
        citations=[dict(ref=r.model_dump(mode='json'), start=0, end=1, quote='q') for r in refs[:1]],
        coverage_state=coverage_state, continuation=False)
    summary = _RestrictedSummary(contents)
    answer = answer_from_summary(None, summary, intent=intent)
    suggestions = labeled_suggestions(tuple(findings))
    if answer.state == 'answered':
        public = documentary_answer_public_v1(answer, refs)
        text = public.text.lower()
        assert 'graph acceptance' not in text and 'graph accepted' not in text
        assert 'model accepted' not in text and 'official policy' not in text
        if suggestions:
            assert 'suggested improvements (not established fact)' in text
            for line in suggestions:
                assert line.lower() in text
        return answer, public, suggestions
    assert answer.state == 'abstained'
    return answer, None, suggestions
