"""Deterministic strict recommendation wire; no providers, stores or actor grants."""
from copy import deepcopy
from decimal import Decimal

import pytest

from oracle_brain.operating_model.consultant.calculations import Forecast, Measurement
from oracle_brain.operating_model.consultant.recommendations import (
    Alternative, CostedMeasure, EvidenceRevision, Recommendation,
    recommendation_from_payload, recommendation_to_payload,
)
from oracle_brain.operating_model.consultant.process_analysis import Report, ReportV2, parse_report


def advice(evidence=None):
    evidence=evidence or EvidenceRevision('rev:1',('citation:a',),'a'*64)
    amount=Measurement(Decimal('10.25'),'money','per_week','USD')
    option=Alternative('change','保留所有例外后再调整',False,evidence.evidence_refs,
        Forecast(amount,Measurement(Decimal('8.00'),'money','per_week','USD'),('相同的工作量',)),
        (CostedMeasure('missing'),),(CostedMeasure('actual_cost',amount),))
    keep=Alternative('keep','维持现状',True,evidence.evidence_refs)
    return Recommendation('rec:1','approval_exception',evidence,(keep,option),(),True,'只涵盖引用范围；仍有未知信息。')


def report_payload(recommendation=None):
    return dict(schema_version=2,variant='documentary',state='ready',model_artifact_hash='b'*64,
        clauses=[],finding_ids=[],actual_data_acceptance='synthetic',
        recommendations=[recommendation_to_payload(recommendation or advice())])


@pytest.mark.parametrize('version',[True,False,1.0,2.0,'2',None])
def test_direct_v2_and_requested_version_never_coerce(version):
    value=report_payload()
    value['schema_version']=version
    with pytest.raises(ValueError):ReportV2.model_validate_json(__import__('json').dumps(value))
    with pytest.raises(ValueError):parse_report(report_payload(),expected_schema_version=version if version is not None else 3)


def test_exact_wire_roundtrip_preserves_decimal_unicode_and_explicit_unknowns():
    original=advice();wire=recommendation_to_payload(original)
    assert wire['options'][1]['forecast']['baseline']['amount']=='10.25'
    assert wire['options'][1]['forecast']['alternative']['amount']=='8.00'
    assert recommendation_from_payload(wire)==original
    assert recommendation_from_payload(wire).content_hash()==original.content_hash()
    assert wire['options'][0]['downstream_costs']==[dict(kind='missing',measure=None)]
    assert wire['scope_note']==original.scope_note


@pytest.mark.parametrize('target', ['root','evidence','option','cost','forecast','measurement'])
def test_unknown_fields_cannot_be_laundered_at_any_nested_level(target):
    wire=recommendation_to_payload(advice())
    selected={'root':wire,'evidence':wire['evidence'],'option':wire['options'][1],
        'cost':wire['options'][1]['downstream_costs'][0],
        'forecast':wire['options'][1]['forecast'],
        'measurement':wire['options'][1]['forecast']['baseline']}[target]
    selected['trusted_actor']='invented'
    with pytest.raises(ValueError,match='exact recommendation payload fields'):
        recommendation_from_payload(wire)


@pytest.mark.parametrize('target', ['evidence_seal','scope_note','downstream_costs'])
def test_required_wire_fields_are_never_inferred_from_defaults(target):
    wire=recommendation_to_payload(advice())
    selected=wire['evidence'] if target=='evidence_seal' else wire['options'][0] if target=='downstream_costs' else wire
    del selected[target]
    with pytest.raises(ValueError,match='exact recommendation payload fields'):
        recommendation_from_payload(wire)


@pytest.mark.parametrize('bad', [True,10.25,10,None,'NaN','Infinity','+10.25','010.25','1E+999999999999'])
def test_measurement_wire_requires_canonical_finite_exact_decimal_strings(bad):
    wire=recommendation_to_payload(advice())
    wire['options'][1]['forecast']['baseline']['amount']=bad
    with pytest.raises(ValueError):recommendation_from_payload(wire)


def test_no_unknown_cost_absence_or_numeric_authority_coercion():
    wire=recommendation_to_payload(advice())
    wire['options'][0]['downstream_costs']=[]
    with pytest.raises(ValueError):recommendation_from_payload(wire)
    wire=recommendation_to_payload(advice());wire['opposing_unknown']=1
    with pytest.raises(ValueError):recommendation_from_payload(wire)
    wire=recommendation_to_payload(advice());wire['options'][0]='invalid'
    with pytest.raises(ValueError):recommendation_from_payload(wire)


def test_version_dispatch_preserves_v1_and_explicitly_validates_v2():
    wire=report_payload()
    parsed=parse_report(wire,expected_schema_version=2)
    assert type(parsed) is ReportV2
    assert parsed.model_dump(mode='json')['recommendations']==wire['recommendations']
    v1={key:value for key,value in wire.items() if key!='recommendations'};v1['schema_version']=1
    assert type(parse_report(v1)) is Report
    with pytest.raises(ValueError):parse_report(wire,expected_schema_version=1)
    with pytest.raises(ValueError):parse_report({**v1,'recommendations':wire['recommendations']})
    for version in (True,3,'2'):
        with pytest.raises(ValueError):parse_report({**wire,'schema_version':version})


def test_duplicate_recommendations_and_unbounded_population_refuse():
    wire=report_payload()
    with pytest.raises(ValueError):parse_report({**wire,'recommendations':wire['recommendations']*2})
    with pytest.raises(ValueError):parse_report({**wire,'recommendations':wire['recommendations']*17})
