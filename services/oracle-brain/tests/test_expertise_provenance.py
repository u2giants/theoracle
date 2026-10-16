"""Pure expertise claim provenance tests. No network, no provider, no policy writes."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from oracle_brain.research.provenance import (
    ExternalReference,
    ExpertiseClaim,
    bind_claims,
)

T0 = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def make_reference(**overrides) -> ExternalReference:
    base = dict(
        reference_id='ref-1',
        publisher='U.S. Consumer Product Safety Commission',
        original_url='https://www.cpsc.gov/Recalls',
        jurisdiction='US',
        product_scope='consumer products / retail',
        channel_scope='retail',
        access='public',
        license_permission='public web reuse',
        source_version='2026.10',
        publication_date=date(2026, 9, 1),
        effective_date=date(2026, 9, 15),
        retrieval_date=date(2026, 10, 1),
        refresh_due=T0,
        review_due=T0,
    )
    base.update(overrides)
    return ExternalReference(**base)


def test_reference_accepts_complete_bibliographic_record():
    ref = make_reference()
    assert ref.publisher.startswith('U.S.')
    assert ref.original_url.startswith('https://')
    assert ref.publication_date == date(2026, 9, 1)
    assert ref.effective_date == date(2026, 9, 15)
    assert ref.retrieval_date == date(2026, 10, 1)
    assert ref.refresh_due == T0
    assert ref.source_version == '2026.10'


def test_reference_requires_https_and_nonempty_identity_fields():
    with pytest.raises(ValueError, match='original_url must be https'):
        make_reference(original_url='http://www.cpsc.gov/Recalls')
    for field in ('reference_id', 'publisher', 'jurisdiction', 'product_scope', 'channel_scope', 'license_permission', 'source_version'):
        with pytest.raises(ValueError, match=field):
            make_reference(**{field: ''})
        with pytest.raises(ValueError, match=field):
            make_reference(**{field: '   '})


def test_reference_rejects_unknown_access():
    with pytest.raises(ValueError, match='unknown access'):
        make_reference(access='pirated')


def test_reference_dates_are_optional_but_typed():
    ref = make_reference(
        publication_date=None, effective_date=None, retrieval_date=None,
        refresh_due=None, review_due=None,
    )
    assert ref.publication_date is None
    assert ref.refresh_due is None


def test_claim_requires_at_least_one_primary_reference():
    with pytest.raises(ValueError, match='at least one reference'):
        ExpertiseClaim('c1', 'Toy safety thresholds tightened.', ())


def test_claim_rejects_empty_statement_or_id():
    with pytest.raises(ValueError, match='statement'):
        ExpertiseClaim('c1', '  ', ('ref-1',))
    with pytest.raises(ValueError, match='claim_id'):
        ExpertiseClaim('', 'Statement.', ('ref-1',))


def test_claim_is_suggestion_only_and_never_overwrites_policy():
    claim = ExpertiseClaim('c1', 'Compare labeling against the current FTC guide.', ('ref-1',))
    assert claim.suggests_comparison_only is True
    with pytest.raises(ValueError, match='never overwrite'):
        ExpertiseClaim('c1', 'Replace company policy.', ('ref-1',), suggests_comparison_only=False)
    with pytest.raises(ValueError, match='suggests_comparison_only must be a bool'):
        ExpertiseClaim('c1', 'Statement.', ('ref-1',), suggests_comparison_only=1)


def test_bind_claims_requires_known_reference_ids():
    refs = (make_reference(), make_reference(reference_id='ref-2', original_url='https://www.ftc.gov/business-guidance'))
    ok = ExpertiseClaim('c1', 'Statement.', ('ref-1', 'ref-2'))
    assert bind_claims((ok,), refs) == (ok,)
    orphan = ExpertiseClaim('c2', 'Statement.', ('ref-missing',))
    with pytest.raises(ValueError, match='unknown references'):
        bind_claims((orphan,), refs)


def test_bind_claims_allows_suggestion_bundle_citing_primary_source():
    refs = (make_reference(),)
    claims = (
        ExpertiseClaim('c1', 'Relevant comparison available.', ('ref-1',)),
        ExpertiseClaim('c2', 'Inapplicable to our channel scope.', ('ref-1',)),
    )
    bound = bind_claims(claims, refs)
    assert len(bound) == 2
    assert all(c.suggests_comparison_only for c in bound)
