"""Pure explicit scope/current metadata comparisons; no legal/rights admission."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import pytest
from pydantic import ValidationError
from oracle_brain.research.registry import Source
from oracle_brain.research.applicability import (DecisionContext,ExternalReference,
    CurrentReference,assess_applicability,assess_references)

NOW=datetime(2026,10,21,12,tzinfo=timezone.utc)
SOURCE=Source('cpsc','CPSC','https://cpsc.example/reference','US','toys','public','weekly')
CONTEXT=DecisionContext(jurisdiction='US',product_scope='toys',channel_scope='retail')


def reference(**changes):
    values=dict(reference_id='ref1',source_id='cpsc',source_version='v1',content_sha256='a'*64,
        original_url=SOURCE.url,publisher=SOURCE.publisher,jurisdiction='US',product_scope='toys',
        channel_scope='retail',license_permission='Public permitted descriptive reference',
        publication_date=(NOW-timedelta(days=30)).date(),effective_date=(NOW-timedelta(days=20)).date(),
        retrieved_at=NOW-timedelta(days=2),reviewed_at=NOW-timedelta(days=1),
        refresh_due=NOW+timedelta(days=5),review_due=NOW+timedelta(days=5))
    return ExternalReference(**(values|changes))


def current(**changes):
    return CurrentReference(**(dict(reference_id='ref1',source_id='cpsc',source_version='v1',
        content_sha256='a'*64)|changes))


def assess(ref=None,**changes):
    options=dict(source=SOURCE,current=current(),now=NOW)
    context=changes.pop('context',CONTEXT)
    return assess_applicability(context,reference() if ref is None else ref,**(options|changes))


def test_explicit_relevant_reference_is_comparison_only_no_grants():
    result=assess()
    assert result.state=='APPLICABLE' and result.comparison_only is True
    assert result.company_policy is False and result.legal_ruling is False
    assert result.source_qualified is False and result.fetch_authorized is False
    assert result.serving_authorized is False and len(result.reference_digest)==64


@pytest.mark.parametrize('field',['jurisdiction','product_scope','channel_scope'])
def test_explicit_mismatch_is_inapplicable_not_fuzzy(field):
    result=assess(reference(**{field:'different'}))
    assert result.state=='INAPPLICABLE' and result.reasons==(field+'_mismatch',)
    lower=getattr(CONTEXT,field).lower()
    if lower!=getattr(CONTEXT,field):assert assess(reference(**{field:lower})).state=='INAPPLICABLE'


@pytest.mark.parametrize('field',['source_version','content_sha256','original_url','publisher',
    'license_permission','publication_date','effective_date','retrieved_at','reviewed_at',
    'refresh_due','review_due','jurisdiction','product_scope','channel_scope'])
def test_missing_metadata_is_unknown_never_implicit_authority(field):
    assert assess(reference(**{field:None})).state=='UNKNOWN'


@pytest.mark.parametrize('token',['UNKNOWN','global','all'])
def test_no_implicit_global_or_unknown_scope_matching(token):
    context=DecisionContext(jurisdiction=token,product_scope='toys',channel_scope='retail')
    assert assess(reference(jurisdiction=token),context=context).state=='UNKNOWN'
    with pytest.raises(ValidationError):DecisionContext(jurisdiction='*')


def test_missing_current_revision_or_unavailable_licensed_rights_is_visible_gap():
    assert assess(current=None).reasons==('current_source_revision_unknown',)
    result=assess(source=replace(SOURCE,access='licensed',rights_confirmed=False))
    assert result.state=='UNKNOWN' and 'rights_gap' in result.reasons
    assert assess(source=replace(SOURCE,enabled=False)).state=='INAPPLICABLE'


@pytest.mark.parametrize('changes',[{'source_version':'v2'},{'content_sha256':'b'*64},
    {'reference_id':'foreign'},{'source_id':'foreign'},{'withdrawn':True}])
def test_foreign_changed_or_withdrawn_current_source_inapplicable(changes):
    assert assess(current=current(**changes)).state=='INAPPLICABLE'


@pytest.mark.parametrize('changes',[{'withdrawn':True},{'review_due':NOW},
    {'refresh_due':NOW},{'effective_date':(NOW+timedelta(days=1)).date()},
    {'publication_date':(NOW+timedelta(days=1)).date()},
    {'original_url':'https://other.example/reference'},{'publisher':'Different Publisher'}])
def test_explicit_expired_future_effective_or_changed_reference_inapplicable(changes):
    assert assess(reference(**changes)).state=='INAPPLICABLE'


def test_sensitive_decision_requires_retrieval_and_review_after_named_fence():
    fence=NOW-timedelta(hours=12)
    context=DecisionContext(jurisdiction='US',product_scope='toys',channel_scope='retail',
        required_review_after=fence)
    assert assess(context=context).state=='INAPPLICABLE'
    # Merely reviewing old fetched bytes does not satisfy a newer refresh fence.
    assert assess(reference(reviewed_at=NOW-timedelta(hours=1)),context=context).state=='INAPPLICABLE'
    assert assess(reference(retrieved_at=fence,reviewed_at=fence),context=context).state=='APPLICABLE'


@pytest.mark.parametrize('changes',[{'retrieved_at':NOW+timedelta(seconds=1)},
    {'reviewed_at':NOW+timedelta(seconds=1)}])
def test_future_observed_fetch_review_refused(changes):
    # Keep the record internally ordered so the caller-clock check is exercised.
    values=dict(retrieved_at=NOW,reviewed_at=NOW)
    values.update(changes)
    with pytest.raises(ValueError):assess(reference(**values))


def test_naive_clock_or_observation_and_inconsistent_dates_refuse():
    with pytest.raises(ValueError):assess(now=NOW.replace(tzinfo=None))
    with pytest.raises(ValidationError):reference(retrieved_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValidationError):reference(reviewed_at=NOW-timedelta(days=3))
    with pytest.raises(ValidationError):reference(review_due=NOW-timedelta(days=2))


@pytest.mark.parametrize('changes',[{'license_permission':'  '},{'publisher':''},
    {'source_version':'../escape'},{'content_sha256':'short'},{'withdrawn':1},
    {'original_url':'https://user:password@example.test/reference'},
    {'original_url':'http://public.example/reference'},{'original_url':'https://pub.example/\npath'}])
def test_malformed_metadata_refuses(changes):
    with pytest.raises(ValidationError):reference(**changes)


def test_registered_actual_boolean_fields_cannot_be_truthy_integers():
    source=replace(SOURCE)
    object.__setattr__(source,'rights_confirmed',1)
    with pytest.raises(ValueError):assess(source=source)


@pytest.mark.parametrize('population',['reference','source','current'])
def test_duplicate_population_ids_never_collapse_conflicting_metadata(population):
    refs=(reference(),);sources=(SOURCE,);versions=(current(),)
    if population=='reference':refs+=(reference(content_sha256='b'*64),)
    if population=='source':sources+=(replace(SOURCE,publisher='conflict'),)
    if population=='current':versions+=(current(source_version='v2'),)
    with pytest.raises(ValueError,match='duplicate'):
        assess_references(CONTEXT,refs,sources=sources,current=versions,now=NOW)


def test_mixed_relevant_inapplicable_and_missing_rights_brief_inputs():
    relevant=reference();wrong=reference(reference_id='wrong',jurisdiction='CA')
    paid_source=replace(SOURCE,source_id='paid',access='member',rights_confirmed=False)
    paid=reference(reference_id='paid-ref',source_id='paid')
    versions=(current(),current(reference_id='wrong'),current(reference_id='paid-ref',source_id='paid'))
    results=assess_references(CONTEXT,(relevant,wrong,paid),sources=(SOURCE,paid_source),current=versions,now=NOW)
    assert [result.state for result in results]==['APPLICABLE','INAPPLICABLE','UNKNOWN']
    assert 'rights_gap' in results[-1].reasons
    assert relevant.license_permission=='Public permitted descriptive reference'


def test_unknown_version_token_never_becomes_explicit_mismatch_or_current_truth():
    assert assess(reference(source_version='UNKNOWN')).state=='UNKNOWN'
    assert assess(current=current(source_version='UNKNOWN')).state=='UNKNOWN'


def test_published_version_cannot_claim_retrieval_before_publication():
    with pytest.raises(ValueError,match='precedes publication'):
        assess(reference(publication_date=(NOW-timedelta(days=1)).date()))
