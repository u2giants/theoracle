"""Invented typed metadata through the actual canonical assembly decoder."""
from datetime import timedelta
from uuid import uuid4
import pytest
from test_assembly_context import context
from test_consolidation_contracts_v1 import core_fixture
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.industry_reference_v1 import (
    IndustryReferenceEvidenceV1, CompanyDecisionContextEvidenceV1,
    REFERENCE_PREDICATE, CONTEXT_PREDICATE, parse_industry_assertion_v1)
from oracle_brain.operating_model.consolidation_contracts_v1 import ConsolidationCoreV1
from oracle_brain.operating_model.pipeline import assembly_candidate_payload, assembly_inputs


def candidate(context, kind='reference'):
    ctx, core, now = core_fixture(context)
    if kind == 'reference':
        value = IndustryReferenceEvidenceV1(purpose='qualified-industry-reference-evidence-v1',
            reference_id=uuid4(), registered_source_id=uuid4(), original=core.model.source_refs[0],
            source_version='version-1', publication_date=(now-timedelta(days=2)).date(),
            effective_date=(now-timedelta(days=1)).date(), jurisdiction='US', product_scope='home-decor',
            channel_scope='retail', license_permission='Invented permission evidence',
            reviewed_at=now, review_due=now+timedelta(days=7))
        predicate,unit=REFERENCE_PREDICATE,'canonical-industry-reference-v1'
    else:
        value = CompanyDecisionContextEvidenceV1(purpose='qualified-company-decision-context-v1',
            decision_id=uuid4(), jurisdiction='US', product_scope='home-decor',channel_scope='retail')
        predicate,unit=CONTEXT_PREDICATE,'canonical-decision-context-v1'
    raw=core.model_dump(mode='json');a=raw['assertions'][0]
    a.update(predicate=predicate,unit=unit,value=canonical_bytes(value.model_dump(mode='json')).decode())
    refs, observations, findings = assembly_inputs(tuple(e.payload for e in ctx.extractions))
    return raw, dict(workspace_id=ctx.job.workspace_id,refs=refs,observations=observations,findings=findings),value


@pytest.mark.parametrize('kind',['reference','context'])
def test_actual_canonical_decoder_preserves_typed_value_and_exact_support(context,kind):
    raw,args,value=candidate(context,kind)
    payload,evidence=assembly_candidate_payload(canonical_bytes(raw).decode(),**args,candidate_contract='qualified-consolidation-core-v1')
    core=ConsolidationCoreV1.model_validate_json(canonical_bytes(payload['consolidation_core']))
    assert parse_industry_assertion_v1(core.assertions[0])==value
    assert evidence['assertion:'+str(core.assertions[0].assertion_id)+':1']


@pytest.mark.parametrize('damage',['malformed','extra','wrong-unit','noncanonical','no-support','foreign-original','wrong-original-hash','wrong-schema'])
def test_recognized_metadata_cannot_qualify_as_opaque_text(context,damage):
    import json
    raw,args,value=candidate(context);a=raw['assertions'][0];body=json.loads(a['value'])
    if damage=='malformed':a['value']='{'
    elif damage=='extra':body['confirmed']=True
    elif damage=='wrong-unit':a['unit']='kg'
    elif damage=='noncanonical':a['value']=json.dumps(body,indent=1)
    elif damage=='no-support':a['opposing_observations']=a['supporting_observations'];a['supporting_observations']=[]
    elif damage=='foreign-original':body['original']['source_id']=str(uuid4())
    elif damage=='wrong-original-hash':body['original']['original_sha256']='a'*64
    elif damage=='wrong-schema':body['purpose']='qualified-company-decision-context-v1'
    if damage not in {'malformed','noncanonical'}:a['value']=canonical_bytes(body).decode()
    with pytest.raises(ValueError):
        assembly_candidate_payload(canonical_bytes(raw).decode(),**args,candidate_contract='qualified-consolidation-core-v1')


def test_missing_metadata_remains_explicit_unknown_not_global():
    value=CompanyDecisionContextEvidenceV1(purpose='qualified-company-decision-context-v1',decision_id=uuid4())
    assert value.jurisdiction is value.product_scope is value.channel_scope is None
    with pytest.raises(ValueError):
        CompanyDecisionContextEvidenceV1.model_validate_json('{"purpose":"qualified-company-decision-context-v1","decision_id":"'+str(uuid4())+'","company_policy":true}')
