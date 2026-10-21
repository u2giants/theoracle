"""Actual TLS SQL qualification and raw→qualified journey custody; invented only."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from oracle_brain.operating_model.contracts import canonical_bytes, digest
from test_replacement_source_intake_sql import requester, call
from test_original_population_sql import raw_reader


@pytest.fixture
def qualified_pair(raw_reader):
    x=raw_reader; reviewer='reviewer_'+uuid4().hex[:12]; principal=uuid4(); population=uuid4()
    ref=x['refs'][0]; reading_text='invent!'
    with psycopg.connect(x['admin']) as c:
        c.execute('UPDATE oracle2.hosting_original_population_admissions_v1 SET model_id=%s WHERE role_name=%s',('reader/model-v1',x['login']))
        c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(reviewer),sql.Literal('invented-reviewer-only')))
        c.execute(sql.SQL('GRANT oracle2_source_original_reviewer TO {}').format(sql.Identifier(reviewer)))
        c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(reviewer,'e'*64,'f'*64,x['role_until']))
        c.execute('''INSERT INTO oracle2.original_source_populations_v1 SELECT %s,workspace_id,'source-original-review',original_root_hash,population_digest,operation_registry_hash,runtime_hash,source_registry_hash,original_allocation_hash,original_horizon,issuer_actor,reviewer_actor,expires_at FROM oracle2.original_source_populations_v1 WHERE population_id=%s''',(population,x['population'].population_id))
        c.execute('INSERT INTO oracle2.hosting_original_population_admissions_v1 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(reviewer,population,principal,'source-original-review','e'*64,'f'*64,'2'*64,x['role_until'],'reviewer/model-v2'))
        c.execute('INSERT INTO oracle2.original_source_population_members_v1 SELECT %s,ordinal,workspace_id,source_id,revision,raw_ref_sha256 FROM oracle2.original_source_population_members_v1 WHERE population_id=%s',(population,x['population'].population_id))
        for original in x['refs']:
            c.execute('INSERT INTO oracle2.hosting_original_source_admissions VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(reviewer,x['workspace'],original.source_id,1,principal,original.original_sha256,'source-original-review','e'*64,'f'*64,population,x['role_until']))
            for scope in ('source-read:','source-original-review:'):
                c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),x['workspace'],principal,scope+str(original.source_id),x['owner'],x['root'],x['role_until']))
    body=dict(schema_version=1,transport='native-utf8-byte-roundtrip-v1',purpose='observed-authorized-original-reading-response-v1',raw_ref=ref.model_dump(mode='json'),population_id=str(x['population'].population_id),operation_registry_hash='2'*64,original_root_hash='1'*64,allocation_hash='3'*64,population_hash=x['population'].population_digest,source_registry_hash='f'*64,context_hash='6'*64,view_manifest_hash='7'*64,locator_map_hash='8'*64,reading_sha256=hashlib.sha256(reading_text.encode()).hexdigest(),parser_id='4'*64,committed_at=datetime.now(timezone.utc).isoformat(),original_horizon=x['until'].isoformat(),reading_body_hash='5'*64)
    review_x=x|{'url':psycopg.conninfo.make_conninfo(x['admin'],user=reviewer,password='invented-reviewer-only'),'login':reviewer,'actor':principal}
    def commit_pair():
        reading=call(x,'commit_original_reading_response_v1',canonical_bytes(body))
        review_body=body|dict(population_id=str(population),purpose='observed-authorized-original-review-response-v1',context_hash='9'*64,reading_commit_hash=reading['commit_sha256'],reading_population_id=str(x['population'].population_id),reading_operation_registry_hash='2'*64,review_body_hash='a'*64,qualification_pass=True)
        review=call(review_x,'commit_original_review_response_v1',canonical_bytes(review_body))
        return reading['commit_sha256'],review['commit_sha256']
    try:
        yield x|dict(review_x=review_x,reviewer=reviewer,review_population=population,body=body,ref=ref,reading_text=reading_text,commit_pair=commit_pair)
    finally:
        with psycopg.connect(x['admin']) as c:
            c.execute('DELETE FROM oracle2.hosting_original_source_admissions WHERE role_name=%s',(reviewer,))
            c.execute('DELETE FROM oracle2.hosting_original_population_admissions_v1 WHERE role_name=%s',(reviewer,))
            c.execute('DELETE FROM oracle2.hosting_role_runtime_admissions WHERE role_name=%s',(reviewer,))
            c.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(reviewer)))


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
def test_actual_phase_model_pins_are_host_owned_and_independent(qualified_pair):
    x=qualified_pair
    with psycopg.connect(x['url']) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE oracle2.hosting_original_population_admissions_v1 SET model_id='forged'")
    with psycopg.connect(x['url']) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute('SET ROLE oracle2_source_original_reviewer')
    with pytest.raises(psycopg.errors.InvalidParameterValue):
        call(x,'commit_original_reading_response_v1',canonical_bytes(x['body']|{'model_id':'forged'}))
    with psycopg.connect(x['admin']) as c:
        c.execute('UPDATE oracle2.hosting_original_population_admissions_v1 SET model_id=%s WHERE role_name=%s',('reader/model-v1',x['reviewer']))
    with pytest.raises(psycopg.errors.InsufficientPrivilege): x['commit_pair']()
    with psycopg.connect(x['admin']) as c:
        c.execute('UPDATE oracle2.hosting_original_population_admissions_v1 SET model_id=NULL WHERE role_name=%s',(x['login'],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege,match='host-pinned'):call(x,'commit_original_reading_response_v1',canonical_bytes(x['body']))


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
def test_actual_expired_phase_pin_and_same_historical_model_cannot_finalize(qualified_pair):
    x=qualified_pair;reading,review=x['commit_pair']()
    with psycopg.connect(x['admin']) as c:
        c.execute("UPDATE oracle2.original_phase_response_commits SET model_id='reader/model-v1' WHERE commit_sha256=%s",(review,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege,match='distinct host-pinned'):
        call(x['review_x'],'finalize_original_reading_qualification_v1',reading,review,x['reading_text'])
    with psycopg.connect(x['admin']) as c:
        c.execute("UPDATE oracle2.hosting_original_population_admissions_v1 SET expires_at=clock_timestamp()-interval '1 second' WHERE role_name=%s",(x['reviewer'],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege): x['commit_pair']()


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
@pytest.mark.parametrize('reading_text',[None,'','wrong-text'])
def test_actual_incomplete_reading_never_creates_qualification(qualified_pair,reading_text):
    x=qualified_pair;reading,review=x['commit_pair']()
    with pytest.raises(psycopg.errors.InvalidParameterValue,match='hash-matching'):
        call(x['review_x'],'finalize_original_reading_qualification_v1',reading,review,reading_text)
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE source_id=%s',(x['ref'].source_id,)).fetchone()==(0,)
        assert c.execute('SELECT count(*) FROM oracle2.operating_model_source_receipts WHERE source_id=%s',(x['ref'].source_id,)).fetchone()==(0,)


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
def test_actual_conflicting_receipt_rolls_back_qualification(qualified_pair):
    x=qualified_pair;reading,review=x['commit_pair']();ref=x['ref']
    with psycopg.connect(x['admin']) as c:
        c.execute('INSERT INTO oracle2.operating_model_source_receipts(workspace_id,source_id,revision,original_hash,reading_hash,parser_id,receipt) VALUES(%s,%s,1,%s,%s,%s,%s)',(x['workspace'],ref.source_id,ref.original_sha256,x['body']['reading_sha256'],'4'*64,Jsonb({'reading':'conflicting'})))
    with pytest.raises(psycopg.errors.UniqueViolation,match='conflicting'):
        call(x['review_x'],'finalize_original_reading_qualification_v1',reading,review,x['reading_text'])
    with psycopg.connect(x['admin']) as c:assert c.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE source_id=%s',(ref.source_id,)).fetchone()==(0,)


def grant_requester(x):
    # The intake requester (not raw reader/reviewer) owns journey capabilities.
    with psycopg.connect(x['admin']) as c:
        actor=c.execute('SELECT principal_id FROM oracle2.hosting_request_principal_admissions WHERE workspace_id=%s',(x['workspace'],)).fetchone()[0]
        login=c.execute('SELECT role_name FROM oracle2.hosting_request_principal_admissions WHERE workspace_id=%s',(x['workspace'],)).fetchone()[0]
        for scope in ('source-read:'+str(x['ref'].source_id),'process-confirm'):
            c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),x['workspace'],actor,scope,x['owner'],x['root'],x['until']))
    return x|dict(url=psycopg.conninfo.make_conninfo(x['admin'],user=login,password='synthetic-requester-only'),actor=actor,login=login)


def request_for(x):
    raw=[dict(source_id=str(x['ref'].source_id),revision=1,original_sha256=x['ref'].original_sha256)]
    return dict(source_selectors=[dict(source_id=str(x['ref'].source_id),revision=1)],population_sha256=digest({'source_refs':raw}),caller_deadline=x['until'].isoformat())


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
def test_actual_raw_reservation_then_atomic_qualified_promotion(qualified_pair):
    x=qualified_pair;r=grant_requester(x);request=request_for(x)
    journey=call(r,'reserve_replacement_journey',Jsonb(request),uuid4())
    run=journey['run_id'];assert journey['state']=='pending'
    call(r,'compare_and_advance_replacement_journey',run,1,Jsonb({'target_state':'processing'}),uuid4())
    with pytest.raises(psycopg.errors.InsufficientPrivilege,match='qualification'):
        call(r,'compare_and_advance_replacement_journey',run,2,Jsonb({'target_state':'delivered'}),uuid4())
    reading,review=x['commit_pair']()
    result=call(x['review_x'],'finalize_original_reading_qualification_v1',reading,review,x['reading_text']);assert result['qualified'] is True
    promoted=call(r,'compare_and_advance_replacement_journey',run,2,Jsonb({'target_state':'delivered'}),uuid4());assert promoted['state']=='delivered'
    with psycopg.connect(x['admin']) as c:
        refs,raw,raw_hash,pop_hash=c.execute('SELECT original_population,reserved_raw_population,reserved_raw_sha256,population_sha256 FROM oracle2.processing_journey_runs_v1 WHERE run_id=%s',(run,)).fetchone()
        assert refs[0]['reading_sha256']==x['body']['reading_sha256'] and refs[0]['schema_version']==1
        assert raw_hash==request['population_sha256'] and pop_hash==digest({'source_refs':refs})
        proof=c.execute("SELECT payload FROM oracle2.replacement_journey_events WHERE run_id=%s AND action='confirm' AND payload->>'target_state'='delivered'",(run,)).fetchone()[0]
        assert proof['reserved_raw_sha256']==raw_hash and proof['qualified_population_sha256']==pop_hash


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
@pytest.mark.parametrize('mutation',['duplicate','stale','digest','withdrawn'])
def test_actual_reservation_denies_invalid_population(qualified_pair,mutation):
    x=qualified_pair;r=grant_requester(x);request=request_for(x)
    if mutation=='duplicate':request['source_selectors']*=2
    elif mutation=='stale':request['source_selectors'][0]['revision']=2
    elif mutation=='digest':request['population_sha256']='0'*64
    else:
        with psycopg.connect(x['admin']) as c:c.execute('INSERT INTO oracle2.source_original_withdrawals_v1 VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())',(uuid4(),x['workspace'],x['ref'].source_id,x['ref'].original_sha256,r['actor'],r['login'],'a'*64,'invented withdrawal',uuid4(),'b'*64))
    with pytest.raises((psycopg.errors.InvalidParameterValue,psycopg.errors.InsufficientPrivilege)):
        call(r,'reserve_replacement_journey',Jsonb(request),uuid4())


@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
@pytest.mark.parametrize('mutation',['head','qualification','withdrawn'])
def test_actual_promotion_denies_drift_after_reservation(qualified_pair,mutation):
    x=qualified_pair;r=grant_requester(x);request=request_for(x)
    journey=call(r,'reserve_replacement_journey',Jsonb(request),uuid4());run=journey['run_id']
    call(r,'compare_and_advance_replacement_journey',run,1,Jsonb({'target_state':'processing'}),uuid4())
    reading,review=x['commit_pair']();call(x['review_x'],'finalize_original_reading_qualification_v1',reading,review,x['reading_text'])
    with psycopg.connect(x['admin']) as c:
        if mutation=='head':c.execute('UPDATE oracle2.sources SET revision=2 WHERE source_id=%s',(x['ref'].source_id,))
        elif mutation=='qualification':c.execute("UPDATE oracle2.source_reading_qualifications SET reading_sha256=repeat('0',64) WHERE source_id=%s",(x['ref'].source_id,))
        else:c.execute('INSERT INTO oracle2.source_original_withdrawals_v1 VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())',(uuid4(),x['workspace'],x['ref'].source_id,x['ref'].original_sha256,r['actor'],r['login'],'a'*64,'invented withdrawal',uuid4(),'b'*64))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        call(r,'compare_and_advance_replacement_journey',run,2,Jsonb({'target_state':'delivered'}),uuid4())
