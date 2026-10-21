"""Actual own-role SQL014 transactions, invented native originals only.

This proves custody adapter behavior, never authenticated paid-wire provenance.
"""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
from uuid import uuid4
import psycopg
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.original_source_authority_v1 import (
    OriginalSourceResolverV1,OriginalWriteOutcomeUnknownV1)
from test_replacement_qualification_sql import qualified_pair
from test_original_population_sql import raw_reader,resolver_for
from test_replacement_source_intake_sql import requester


def pair(x):
    reader=resolver_for(x)
    population=x['population'].model_copy(update={'population_id':x['review_population']})
    binding=replace(reader.binding,population=population,principal=x['review_x']['actor'],
        purpose='source-original-review',expected_session_role=x['reviewer'])
    reviewer=OriginalSourceResolverV1(x['review_x']['url'],binding=binding)
    return reader,reviewer


def commit_pair(x,reader,reviewer):
    reading=reader.commit_original_reading_response_v1(canonical_bytes(x['body']))
    body=x['body']|dict(population_id=str(x['review_population']),purpose='observed-authorized-original-review-response-v1',
        context_hash='9'*64,reading_commit_hash=reading.commit_sha256,
        reading_population_id=str(x['population'].population_id),reading_operation_registry_hash='2'*64,
        review_body_hash='a'*64,qualification_pass=True)
    review=reviewer.commit_original_review_response_v1(canonical_bytes(body))
    return reading,review,body


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
def test_actual_own_role_commits_and_atomic_finalize_visible_after_return(qualified_pair):
    x=qualified_pair;reader,reviewer=pair(x)
    reading,review,_=commit_pair(x,reader,reviewer)
    assert reading.principal_id==x['actor'] and review.principal_id==x['review_x']['actor']
    assert reading.commit_sha256==hashlib.sha256(canonical_bytes(x['body'])).hexdigest()
    # Independent connection observes committed rows before any finalize call.
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.original_phase_response_commits WHERE commit_sha256=ANY(%s)',
            ([reading.commit_sha256,review.commit_sha256],)).fetchone()==(2,)
        assert c.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE source_id=%s',(x['ref'].source_id,)).fetchone()==(0,)
    final=reviewer.finalize_original_reading_qualification_v1(reading,review,x['reading_text'])
    assert final.source_ref.original_sha256==x['ref'].original_sha256
    assert final.source_ref.reading_sha256==x['body']['reading_sha256']
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE source_id=%s',(x['ref'].source_id,)).fetchone()==(1,)
        receipt=c.execute('SELECT receipt FROM oracle2.operating_model_source_receipts WHERE source_id=%s',(x['ref'].source_id,)).fetchone()[0]
        assert receipt['reading']==x['reading_text']
    assert reader.commit_original_reading_response_v1(canonical_bytes(x['body'])).commit_sha256==reading.commit_sha256


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
def test_actual_wrong_phase_foreign_population_and_invalid_reading_refused(qualified_pair):
    x=qualified_pair;reader,reviewer=pair(x)
    with pytest.raises(PermissionError):reviewer.commit_original_reading_response_v1(canonical_bytes(x['body']))
    with pytest.raises(PermissionError):reader.commit_original_reading_response_v1(canonical_bytes(x['body']|{'population_id':str(uuid4())}))
    with pytest.raises(ValueError):reader.commit_original_reading_response_v1(b'{"transport":"native-utf8-byte-roundtrip-v1","transport":"paid-native-v1"}')
    reading,review,_=commit_pair(x,reader,reviewer)
    with pytest.raises(PermissionError):reader.finalize_original_reading_qualification_v1(reading,review,x['reading_text'])
    with pytest.raises(psycopg.errors.InvalidParameterValue):reviewer.finalize_original_reading_qualification_v1(reading,review,'wrong')
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE source_id=%s',(x['ref'].source_id,)).fetchone()==(0,)


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
def test_actual_revoked_current_appointment_and_mutated_catalog_stop_writes(qualified_pair):
    x=qualified_pair;reader,reviewer=pair(x);reading,review,_=commit_pair(x,reader,reviewer)
    with psycopg.connect(x['admin']) as c:
        c.execute('UPDATE oracle2.hosting_original_population_admissions_v1 SET runtime_hash=%s WHERE role_name=%s',('0'*64,x['reviewer']))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):reviewer.finalize_original_reading_qualification_v1(reading,review,x['reading_text'])
    with psycopg.connect(x['admin']) as c:
        c.execute('UPDATE oracle2.hosting_original_population_admissions_v1 SET runtime_hash=%s WHERE role_name=%s',('e'*64,x['reviewer']))
        c.execute('GRANT EXECUTE ON FUNCTION oracle2.finalize_original_reading_qualification_v1(text,text,text) TO PUBLIC')
    try:
        with pytest.raises(PermissionError,match='ACL differs'):reviewer.finalize_original_reading_qualification_v1(reading,review,x['reading_text'])
    finally:
        with psycopg.connect(x['admin']) as c:c.execute('REVOKE EXECUTE ON FUNCTION oracle2.finalize_original_reading_qualification_v1(text,text,text) FROM PUBLIC')


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
def test_lost_commit_ack_is_unknown_never_retried_or_requester_borrowed(qualified_pair,monkeypatch):
    x=qualified_pair;reader,_=pair(x);original=reader._connection;calls=[]
    @contextmanager
    def lose_ack(connection=None):
        # Let the REAL SQL transaction commit, then simulate its lost ACK.
        if connection is not None:
            with original(connection) as c:yield c
            return
        with original() as c:
            calls.append('one actual transaction')
            yield c
        raise psycopg.OperationalError('invented connection lost after real commit')
    monkeypatch.setattr(reader,'_connection',lose_ack)
    with pytest.raises(OriginalWriteOutcomeUnknownV1,match='UNKNOWN'):
        reader.commit_original_reading_response_v1(canonical_bytes(x['body']))
    assert calls==['one actual transaction']
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.original_phase_response_commits WHERE commit_sha256=%s',
            (hashlib.sha256(canonical_bytes(x['body'])).hexdigest(),)).fetchone()==(1,)


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
def test_finalize_lost_commit_ack_returns_unknown_without_returning_source_ref(qualified_pair,monkeypatch):
    x=qualified_pair;reader,reviewer=pair(x);reading,review,_=commit_pair(x,reader,reviewer)
    original=reviewer._connection;calls=[]
    @contextmanager
    def lose_ack(connection=None):
        if connection is not None:
            with original(connection) as c:yield c
            return
        with original() as c:
            calls.append('one actual finalize transaction');yield c
        raise psycopg.OperationalError('invented lost final commit acknowledgement')
    monkeypatch.setattr(reviewer,'_connection',lose_ack)
    with pytest.raises(OriginalWriteOutcomeUnknownV1):
        reviewer.finalize_original_reading_qualification_v1(reading,review,x['reading_text'])
    assert calls==['one actual finalize transaction']
    # Test-only independent observation; adapter does NOT borrow this authority.
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE source_id=%s',
            (x['ref'].source_id,)).fetchone()==(1,)
