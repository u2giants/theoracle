"""Actual owned SQL018 reviewer capability; no provider, private original or qualification."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import hashlib
import psycopg
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.original_source_authority_v1 import OriginalReviewReadingInputV1
from test_original_qualification_authority_sql import pair
from test_replacement_qualification_sql import qualified_pair
from test_original_population_sql import raw_reader
from test_replacement_source_intake_sql import requester


@pytest.fixture
def retained_reading(qualified_pair):
    x=qualified_pair
    # Canonical worker bootstrap installs018 ONCE. Never replay an old
    # migration from a retained fixture; the actual capability checks below
    # must fail if the canonical function is absent or differs.
    reader,reviewer=pair(x)
    seal=reader.commit_original_reading_response_v1(canonical_bytes(x['body']))
    return x,reader,reviewer,seal


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
def test_own_current_reviewer_reads_actual_retained_commit_after_reader_expiry(retained_reading):
    x,reader,reviewer,seal=retained_reading
    # Actual retained reader proof is not a renewed or borrowed reader grant.
    with psycopg.connect(x['admin']) as c:
        c.execute('UPDATE oracle2.hosting_original_population_admissions_v1 SET expires_at=clock_timestamp()-interval \'1 second\' WHERE role_name=%s',(x['login'],))
        c.execute('UPDATE oracle2.hosting_role_runtime_admissions SET expires_at=clock_timestamp()-interval \'1 second\' WHERE role_name=%s',(x['login'],))
    result=reviewer.original_review_reading_input_v1(seal.commit_sha256)
    assert type(result) is OriginalReviewReadingInputV1
    assert bytes.fromhex(result.reading_commit_canonical_utf8_hex)==canonical_bytes(x['body'])
    assert result.reader_principal_id==x['actor'] and result.reader_model_id=='reader/model-v1'
    assert result.reviewer_snapshot.actual_principal_id==x['review_x']['actor']
    assert result.reading_commit_sha256==hashlib.sha256(canonical_bytes(x['body'])).hexdigest()
    assert result.valid_until<=result.reviewer_snapshot.valid_until
    with pytest.raises(PermissionError):reader.original_review_reading_input_v1(seal.commit_sha256)
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE source_id=%s',(x['ref'].source_id,)).fetchone()==(0,)


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
@pytest.mark.parametrize('damage',['revoked','wrong_model','body','canonical','model_seal','withdrawn','foreign','acl'])
def test_actual_sql018_current_authority_and_historical_integrity_refusals(retained_reading,damage):
    x,_,reviewer,seal=retained_reading
    with psycopg.connect(x['admin']) as c:
        if damage=='revoked':c.execute('UPDATE oracle2.hosting_original_population_admissions_v1 SET expires_at=clock_timestamp()-interval \'1 second\' WHERE role_name=%s',(x['reviewer'],))
        elif damage=='wrong_model':c.execute("UPDATE oracle2.hosting_original_population_admissions_v1 SET model_id='reader/model-v1' WHERE role_name=%s",(x['reviewer'],))
        elif damage=='body':c.execute("UPDATE oracle2.original_phase_response_commits SET body=body||jsonb_build_object('reading_body_hash',repeat('0',64)) WHERE commit_sha256=%s",(seal.commit_sha256,))
        elif damage=='canonical':c.execute("UPDATE oracle2.original_phase_response_commits SET canonical_body=canonical_body||convert_to(' ','UTF8') WHERE commit_sha256=%s",(seal.commit_sha256,))
        elif damage=='model_seal':c.execute("UPDATE oracle2.original_phase_response_commits SET model_identity_sha256=repeat('0',64) WHERE commit_sha256=%s",(seal.commit_sha256,))
        elif damage=='withdrawn':
            c.execute('UPDATE oracle2.sources SET revision=revision+1 WHERE workspace_id=%s AND source_id=%s',(x['workspace'],x['ref'].source_id))
        elif damage=='acl':c.execute('GRANT EXECUTE ON FUNCTION oracle2.original_review_reading_input_v1(text) TO PUBLIC')
    try:
        with pytest.raises((PermissionError,ValueError,psycopg.errors.InsufficientPrivilege)):
            reviewer.original_review_reading_input_v1('0'*64 if damage=='foreign' else seal.commit_sha256)
    finally:
        if damage=='acl':
            with psycopg.connect(x['admin']) as c:c.execute('REVOKE EXECUTE ON FUNCTION oracle2.original_review_reading_input_v1(text) FROM PUBLIC')


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
def test_sql018_no_raw_table_or_reader_execute_grant_and_closed_return(retained_reading):
    x,_,reviewer,seal=retained_reading
    result=reviewer.original_review_reading_input_v1(seal.commit_sha256)
    assert set(result.model_dump())=={'schema_version','purpose','reading_commit_sha256','reading_commit_canonical_utf8_hex',
        'reader_principal_id','reader_session_role','reader_model_id','reader_runtime_hash','reader_population_id',
        'reader_operation_registry_hash','reader_model_identity_sha256','reviewer_snapshot','checked_at','valid_until'}
    for url in (x['url'],x['review_x']['url']):
        with psycopg.connect(url) as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT * FROM oracle2.original_phase_response_commits')
    with psycopg.connect(x['url']) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.original_review_reading_input_v1(%s)',(seal.commit_sha256,))
