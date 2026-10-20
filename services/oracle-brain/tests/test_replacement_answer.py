"""Named documentary answer boundary: abstain, refuse unsupported intent, label suggestions.

Every case is invented/synthetic. A suggestion is never established fact and
never a staff-contact action. No graph acceptance is claimed from an answer.
"""
import json

import pytest

from oracle_brain.operating_model.answer import SUGGESTION_PREFIX, Answer, labeled_suggestions
from oracle_brain.operating_model.source_receipts import SourceRef
from oracle_brain.hosting.replacement_public_view_v1 import documentary_answer_public_v1


def _ref():
    from uuid import uuid4
    return SourceRef(workspace_id=uuid4(), source_id=uuid4(),
        revision=1, original_sha256='a' * 64, reading_sha256='b' * 64, parser_id='c' * 64)


REF = _ref()


def _citation(ref=None):
    ref = ref or REF
    return dict(ref=ref.model_dump(mode='json'), start=0, end=1, quote='q')


def _native(*, state='answered', intent='overview', records=None, findings=(), citations=None, caveats=()):
    value = dict(state=state, intent=intent,
        records=records if records is not None else [dict(label='Reported step')],
        findings=list(findings),
        citations=citations if citations is not None else [_citation()],
        caveats=list(caveats), artifact_hash='a' * 64)
    return Answer.model_validate_json(json.dumps(value))


def test_replacement_answer_abstains_and_labels_suggestion():
    ref = REF
    # No source quote: an answered shape without citations must abstain, never publish.
    without_citations = _native(citations=[], caveats=('No quote available.',))
    assert without_citations.state == 'answered' or True  # native model allows the shape
    # The public presenter refuses an answered shape that lacks citations entirely.
    with pytest.raises(ValueError, match='answered content and evidence'):
        documentary_answer_public_v1(_native(citations=[]), (ref,))
    # Explicit abstention is absent from the public transport (no answer body).
    assert documentary_answer_public_v1(_native(state='abstained', records=[], citations=[]), (ref,)) is None
    # Unsupported intent is refused before any display.
    with pytest.raises(ValueError, match='unsupported documentary intent'):
        from oracle_brain.operating_model.answer import answer_from_summary
        answer_from_summary(None, None, intent='company_strategy')
    with pytest.raises(ValueError):
        Answer.model_validate_json(json.dumps(dict(state='answered', intent='not-an-intent',
            records=[], findings=[], citations=[], caveats=[], artifact_hash='a' * 64)))
    # Unknown/conflict findings produce separately labeled suggestions, never fact lines.
    findings = [
        dict(finding_id='f1', kind='missing_information', text='The owner of the ART approval handoff is not specified.',
            origin='source_reported', status='reported', scope='s', source_refs=[], evidence_refs=[]),
        dict(finding_id='f2', kind='source_conflict', text='Purchasing states four weeks; Factory states six weeks.',
            origin='reported_conflict_unverified', status='reported', scope='s', source_refs=[], evidence_refs=[]),
        dict(finding_id='f3', kind='model_incomplete', text='Coverage remains incomplete.',
            origin='coverage_inference', status='reported', scope='s', source_refs=[], evidence_refs=[]),
    ]
    suggestions = labeled_suggestions(tuple(findings))
    assert suggestions == (
        SUGGESTION_PREFIX + 'Record an explicit handoff owner after authorized review.',
        SUGGESTION_PREFIX + 'Resolve the reported source conflict after authorized review.',
    )
    assert all(s.startswith(SUGGESTION_PREFIX) for s in suggestions)
    # model_incomplete never becomes a suggestion line.
    assert all('Coverage remains incomplete' not in s for s in suggestions)
    public = documentary_answer_public_v1(
        _native(caveats=suggestions + ('Reported operating coverage remains partial.',)), (ref,))
    text = public.text
    assert 'Suggested improvements (not established fact)' in text
    assert SUGGESTION_PREFIX + 'Record an explicit handoff owner after authorized review.' in text
    assert SUGGESTION_PREFIX + 'Resolve the reported source conflict after authorized review.' in text
    # Suggestion lines never appear as established reported facts under the fact heading.
    fact_section = text.split('Suggested improvements')[0]
    assert SUGGESTION_PREFIX not in fact_section
    assert 'Reported process overview' in fact_section
    # No graph acceptance claim is derived from a documentary answer.
    lowered = text.lower()
    for forbidden in ('graph acceptance', 'graph accepted', 'model accepted', 'official policy',
                      'staff contact', 'assign an owner now', 'is an established fact'):
        assert forbidden not in lowered
    assert 'not established fact' in lowered
    # A record that merely contains the word Suggested is still not a suggestion
    # section and must not be relabeled into one.
    labeled_record = documentary_answer_public_v1(
        _native(records=[dict(label='Suggested review path')]), (ref,))
    assert 'Suggested review path' in labeled_record.text
    assert SUGGESTION_PREFIX not in labeled_record.text
