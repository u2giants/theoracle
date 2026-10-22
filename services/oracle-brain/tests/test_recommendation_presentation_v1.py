"""Current documentary choices, not numeric entry or evidence authority."""
import pytest
from oracle_brain.operating_model.pipeline import assembly_inputs
from oracle_brain.operating_model.consultant.recommendation_presentation_v1 import readable_recommendation_evidence_v1
from test_assembly_context import context
from test_recommendation_actions_v1 import item_case,NOW


def case(context):
    item,_,core,payload,_=item_case(context)
    ctx,_,_=__import__('test_consolidation_contracts_v1').core_fixture(context)
    # The fixture's observation identities are deterministic for this source;
    # use the actual assembly owner rather than fabricated evidence dictionaries.
    payload|={'observations':[o for e in ctx.extractions for o in e.payload['observations']],
              'findings':[f for e in ctx.extractions for f in e.payload.get('findings',[])]}
    return item,core,payload


def test_readable_quotes_retain_actual_original_revision_hash_and_span(context):
    item,core,payload=case(context)
    view=readable_recommendation_evidence_v1(core,item,payload,now=NOW)
    assert not view['measurement_sources'] and not view['measurement_coverage_gap']
    assert view['evidence']['supporting'] and view['evidence']['temporal']
    quote=view['evidence']['supporting'][0]
    actual=payload['observations'][0]['evidence'][0]
    assert quote['quote']==actual['quote'] and quote['start']==actual['start'] and quote['end']==actual['end']
    assert quote['original_sha256']==actual['ref']['original_sha256']
    assert not {'workspace_id','private_object_key','parser_id'}&quote.keys()


def test_presentation_cannot_borrow_partial_or_other_original_population(context):
    item,core,payload=case(context);payload['source_refs']=[]
    with pytest.raises(PermissionError):readable_recommendation_evidence_v1(core,item,payload,now=NOW)


def test_evidence_overflow_is_explicit_and_never_truncates_quote(context,monkeypatch):
    item,core,payload=case(context)
    monkeypatch.setattr('oracle_brain.operating_model.consultant.recommendation_presentation_v1.MAX_QUOTE_BYTES',1)
    view=readable_recommendation_evidence_v1(core,item,payload,now=NOW)
    assert view['evidence_coverage_gap'] and all(not value for value in view['evidence'].values())


@pytest.mark.parametrize('extra',[{'actor_id':'invented'},{'model_id':'invented'},{'selector':{}},{'amount':'4'}])
def test_list_wire_is_deadline_only(extra):
    from oracle_brain.hosting.recommendation_actions_v1 import parse_recommendation_request_v1
    from oracle_brain.operating_model.contracts import canonical_bytes
    with pytest.raises((PermissionError,ValueError)):
        parse_recommendation_request_v1(canonical_bytes({'schema_version':1,'operation':'list','caller_deadline':'2026-10-21T00:00:20Z',**extra}))
