"""One newly authored population for the owned synthetic native journey.

Original input custody precedes operation admission. No old paid result is adopted.
"""
import hashlib

import psycopg

from purpose_journey_fixture_models import RICH_SOURCE_TEXTS
from test_purpose_source_authority import purpose_population,context
from test_source_processing_qualification import processing


def test_rich_originals_are_sealed_before_source_admission(admin_url,purpose_population):
    f=purpose_population('census','source-reader',source_texts=RICH_SOURCE_TEXTS)
    resolver,_,_=context(f)
    receipts=resolver.read_population()
    assert tuple(receipt.reading for receipt in receipts)==RICH_SOURCE_TEXTS
    with psycopg.connect(admin_url) as connection:
        for receipt,text in zip(receipts,RICH_SOURCE_TEXTS):
            expected=hashlib.sha256(text.encode()).hexdigest()
            assert receipt.ref.reading_sha256==expected
            admitted=connection.execute(
                'SELECT reading_hash FROM oracle2.hosting_role_source_admissions '
                'WHERE role_name=%s AND workspace_id=%s AND source_id=%s',
                (f['login'],f['workspace'],receipt.ref.source_id)).fetchone()
            assert admitted==(expected,)
        assert connection.execute('SELECT DISTINCT status FROM oracle2.drafts WHERE workspace_id=%s',(f['workspace'],)).fetchall()==[('draft',)]
        assert connection.execute('SELECT count(*) FROM oracle2.reviews WHERE workspace_id=%s',(f['workspace'],)).fetchone()==(0,)


import pytest
from test_purpose_native_census_startup import native_census_startup
from test_purpose_worker_startup import compiler_worker
from test_native_factory import actual_ledger
from test_purpose_transport import bound_tls,certificates
from test_parent_observer_v2 import provision
from oracle_brain.operating_model.contracts import digest
from oracle_brain.hosting.purpose_journey_v2 import PurposeJourneyCustodyV2,run_purpose_worker_once_v2


@pytest.mark.parametrize('native_census_startup',[{'phase':'census','coherent':True}],indirect=True)
def test_coherent_native_census_uses_real_prior_input_parent(compiler_worker):
    x,settings,job=compiler_worker
    parent=x['input_parent']
    assert parent is not None and len(parent.contexts)==3
    assert tuple(c.receipt.reading for c in parent.contexts)==RICH_SOURCE_TEXTS
    assert parent.runtime_hash==x['input_runtime'] and all(c.actor_id==x['input_actor'] for c in parent.contexts)
    assert settings.population.parent_registry_sha256==digest(parent.model_dump(mode='json'))
    assert {c.job.batch_id for c in parent.contexts}=={x['job'].batch_id}
    custody=PurposeJourneyCustodyV2(settings);custody.admit(job.job_id)
    try:row=run_purpose_worker_once_v2(settings)
    except Exception as error:raise AssertionError(str(x['state'].get('failure'))) from error
    assert row['state']=='awaiting-external-phase-admission' and x['state']['posts']==1
    assert len(custody.journal.read(job.journey_id))==2
    assert x['state']['requests'][0]['messages']==x['job'].request['messages']
    # Original-input custody is sealed; no extraction operation registry, paid
    # result, or future phase body was manufactured to establish this barrier.
    assert not list(x['custody'].glob('*.extraction*'))
