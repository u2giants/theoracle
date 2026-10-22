"""Pure comparison negatives; these DTOs are not an access/qualification receipt."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from test_assembly_context import context
from test_industry_reference_v1 import candidate
from oracle_brain.operating_model.industry_reference_v1 import CompanyDecisionContextEvidenceV1
from oracle_brain.operating_model.consolidation_contracts_v1 import ConsolidationCoreV1
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.research.qualified_brief_v1 import _compare_reference_v1, QualifiedIndustryBriefV1


def fixtures(context):
    raw,args,ref=candidate(context)
    assertion=ConsolidationCoreV1.model_validate_json(canonical_bytes(raw)).assertions[0]
    now=datetime.now(timezone.utc)
    decision=CompanyDecisionContextEvidenceV1(purpose='qualified-company-decision-context-v1',decision_id=uuid4(),
        jurisdiction='US',product_scope='home-decor',channel_scope='retail')
    retained=dict(workspace_id=str(ref.original.workspace_id),source_id=str(ref.registered_source_id),
        registration=dict(source_id='invented-industry',publisher='Invented Publisher',url='https://industry.example.test/reference',
            jurisdiction='US',scope='home-decor',access='public',cadence='weekly',enabled=True,rights_confirmed=False),
        reference=dict(content_sha256=ref.original.original_sha256,receipt_event_id=str(uuid4()),
            retrieved_at=(now-timedelta(days=1)).isoformat(),refresh_due=(now+timedelta(days=5)).isoformat()),
        refresh=dict(state='current',attempts=1,exhausted=False))
    return assertion,decision,ref,retained,now


def test_comparison_relevant_reference_stays_separate_from_company_policy(context):
    a,c,r,retained,now=fixtures(context)
    out=_compare_reference_v1(a,c,a,r,retained,now)
    assert out['comparison']['state']=='APPLICABLE'
    assert out['comparison']['company_policy'] is out['comparison']['serving_authorized'] is False
    assert out['source_qualified_by_fetch'] is False


@pytest.mark.parametrize('damage',['foreign-registration','foreign-workspace','different-body'])
def test_actual_retained_identity_cannot_be_replaced_by_documentary_metadata(context,damage):
    a,c,r,retained,now=fixtures(context)
    if damage=='foreign-registration':retained['source_id']=str(uuid4())
    elif damage=='foreign-workspace':retained['workspace_id']=str(uuid4())
    else:retained['reference']['content_sha256']='b'*64
    with pytest.raises(PermissionError):_compare_reference_v1(a,c,a,r,retained,now)


def test_inapplicable_reference_and_missing_company_context_are_visible(context):
    a,c,r,retained,now=fixtures(context)
    mismatch=c.model_copy(update={'jurisdiction':'EU'})
    assert _compare_reference_v1(a,mismatch,a,r,retained,now)['comparison']['state']=='INAPPLICABLE'
    unknown=c.model_copy(update={'channel_scope':None})
    out=_compare_reference_v1(a,unknown,a,r,retained,now)
    assert out['comparison']['state']=='UNKNOWN' and 'channel_scope_unknown' in out['comparison']['reasons']


def test_licensed_unavailable_reference_has_no_fetched_text_or_qualification(context):
    a,c,r,retained,now=fixtures(context)
    retained['registration']['access']='licensed';retained['reference']=None
    out=_compare_reference_v1(a,c,a,r,retained,now)
    assert out['comparison']['state']=='UNKNOWN' and 'rights_gap' in out['comparison']['reasons']
    assert out['reference']['content_sha256'] is None and out['retained_receipt_event_id'] is None


def test_unknown_or_expired_assertion_cannot_become_applicable_by_metadata_alone(context):
    a,c,r,retained,now=fixtures(context)
    a=a.model_copy(update={'valid_time':'unknown','valid_from':None,'temporal_observations':()})
    assert _compare_reference_v1(a,c,a,r,retained,now)['comparison']['state']=='UNKNOWN'


def test_callback_or_fake_owner_cannot_create_a_qualified_brief():
    with pytest.raises(PermissionError):QualifiedIndustryBriefV1(lambda:None,())
