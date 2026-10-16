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
