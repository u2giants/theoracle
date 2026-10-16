"""GIVEN invented custody seals, actual SQL commits; no provider cryptoproof."""
from datetime import datetime,timezone
from uuid import uuid4
import psycopg
from psycopg import sql
import pytest
from test_original_population_sql import raw_reader
from test_replacement_source_intake_sql import requester,call
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.original_qualification_v1 import OriginalReadingCommitV1


def reading_body(x):
    p=x['population'];ref=x['refs'][0]
    values=dict(raw_ref=ref,population_id=p.population_id,operation_registry_hash=p.operation_registry_hash,
        original_root_hash=p.original_root_hash,allocation_hash='3'*64,population_hash=p.population_digest,
        source_registry_hash=p.source_registry_hash,context_hash='4'*64,view_manifest_hash='5'*64,locator_map_hash='6'*64,
        reading_sha256='7'*64,parser_id='8'*64,committed_at=datetime.now(timezone.utc),original_horizon=x['until'],
        reading_body_hash='9'*64,native_dispatch_id=uuid4(),native_job_hash='a'*64,request_hash='b'*64,
        raw_wire_hash='c'*64,model_content_hash='d'*64,native_custody_receipt_hash='e'*64,authorized_phase_commit_hash='f'*64)
    if ref.media_type=='text/plain':
        from oracle_brain.operating_model.original_qualification_v1 import NativeUTF8ReadingCommitV1
        for k in ('native_dispatch_id','native_job_hash','request_hash','raw_wire_hash','model_content_hash','native_custody_receipt_hash','authorized_phase_commit_hash'):values.pop(k)
        values['reading_sha256']=ref.original_sha256
        return NativeUTF8ReadingCommitV1(**values).model_dump(mode='json')
    return OriginalReadingCommitV1(**values).model_dump(mode='json')


def test_actual_reader_commit_canonical_idempotent_and_not_body_principal(raw_reader):
    x=raw_reader;b=reading_body(x);wire=canonical_bytes(b)
    r=call(x,'commit_original_reading_response_v1',wire)
    assert r['commit_sha256']==digest(b) and r['principal_id']==str(x['actor']) and r['session_role']==x['login']
    assert call(x,'commit_original_reading_response_v1',wire)['commit_sha256']==r['commit_sha256']
    with psycopg.connect(x['url']) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT * FROM oracle2.original_phase_response_commits')
    b['raw_wire_hash']='0'*64
    with pytest.raises(psycopg.errors.UniqueViolation):call(x,'commit_original_reading_response_v1',canonical_bytes(b))

@pytest.mark.parametrize('change',['unknown','bool-schema','float-schema','paid-missing','native-paid-fields','native-pdf','pop','registry','root','horizon','future','noncanonical','third-revoke'])
def test_actual_reader_strict_transport_and_current_population(raw_reader,change):
    x=raw_reader;b=reading_body(x)
    if change=='unknown':b['actor_id']=str(x['actor'])
    elif change=='bool-schema':b['schema_version']=True
    elif change=='float-schema':b['schema_version']=1.0
    elif change=='paid-missing':b.pop('native_job_hash')
    elif change in ('native-paid-fields','native-pdf'):
        b['transport']='native-utf8-byte-roundtrip-v1'
        if change=='native-pdf':
            for k in ('native_dispatch_id','native_job_hash','request_hash','raw_wire_hash','model_content_hash','native_custody_receipt_hash','authorized_phase_commit_hash'):b.pop(k)
    elif change=='pop':b['population_id']=str(uuid4())
    elif change=='registry':b['operation_registry_hash']='0'*64
    elif change=='root':b['original_root_hash']='0'*64
    elif change=='horizon':b['original_horizon']='2099-01-01T00:00:00Z'
    elif change=='future':b['committed_at']='2099-01-01T00:00:00Z'
    elif change=='third-revoke':
        with psycopg.connect(x['admin']) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['grants'][-2],))
    wire=canonical_bytes(b)+(b' ' if change=='noncanonical' else b'')
    with pytest.raises((psycopg.errors.InvalidParameterValue,psycopg.errors.InsufficientPrivilege)):
        call(x,'commit_original_reading_response_v1',wire)

@pytest.fixture
def independent_reviewer(raw_reader):
    x=raw_reader;login='raw_review_'+uuid4().hex[:12];actor,pop=uuid4(),uuid4();runtime,registry='6'*64,'7'*64;operation='8'*64
    with psycopg.connect(x['admin']) as c:
        c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-review-only')))
        c.execute(sql.SQL('GRANT oracle2_source_original_reviewer TO {}').format(sql.Identifier(login)))
        c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,runtime,registry,x['role_until']))
        c.execute("INSERT INTO oracle2.original_source_populations_v1 SELECT %s,workspace_id,'source-original-review',original_root_hash,population_digest,%s,%s,%s,original_allocation_hash,original_horizon,issuer_actor,reviewer_actor,expires_at FROM oracle2.original_source_populations_v1 WHERE population_id=%s",(pop,operation,runtime,registry,x['population'].population_id))
        c.execute('INSERT INTO oracle2.original_source_population_members_v1 SELECT %s,ordinal,workspace_id,source_id,revision,raw_ref_sha256 FROM oracle2.original_source_population_members_v1 WHERE population_id=%s',(pop,x['population'].population_id))
        c.execute("INSERT INTO oracle2.hosting_original_population_admissions_v1 VALUES(%s,%s,%s,'source-original-review',%s,%s,%s,%s)",(login,pop,actor,runtime,registry,operation,x['role_until']))
        for ref in x['refs']:
            c.execute("INSERT INTO oracle2.hosting_original_source_admissions VALUES(%s,%s,%s,1,%s,%s,'source-original-review',%s,%s,%s,%s)",(login,x['workspace'],ref.source_id,actor,ref.original_sha256,runtime,registry,pop,x['role_until']))
            for scope in ('source-read:','source-original-review:'):
                c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),x['workspace'],actor,scope+str(ref.source_id),x['owner'],x['root'],x['role_until']))
    y=x|dict(login=login,actor=actor,url=psycopg.conninfo.make_conninfo(x['admin'],user=login,password='invented-review-only'),review_pop=pop,review_operation=operation,review_registry=registry)
    try:yield x,y
    finally:
        with psycopg.connect(x['admin']) as c:
            c.execute('DELETE FROM oracle2.hosting_original_source_admissions WHERE role_name=%s',(login,))
            c.execute('DELETE FROM oracle2.hosting_original_population_admissions_v1 WHERE role_name=%s',(login,))
            c.execute('DELETE FROM oracle2.hosting_role_runtime_admissions WHERE role_name=%s',(login,))
            c.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(login)))


def review_body(b,r,y):
    return b|dict(purpose='observed-authorized-original-review-response-v1',population_id=str(y['review_pop']),
        operation_registry_hash=y['review_operation'],source_registry_hash=y['review_registry'],context_hash='0'*64,
        native_dispatch_id=str(uuid4()),reading_commit_hash=r['commit_sha256'],reading_population_id=b['population_id'],
        reading_operation_registry_hash=b['operation_registry_hash'],review_body_hash='1'*64,qualification_pass=True)

@pytest.mark.parametrize('change',['none','historical-reader-revoked','wrong-reader-pop','wrong-reader-registry','same-actor','review-revoked','integer-pass'])
def test_current_independent_review_binds_historical_reader_actual_commit(independent_reviewer,change):
    x,y=independent_reviewer;b=reading_body(x);r=call(x,'commit_original_reading_response_v1',canonical_bytes(b));review=review_body(b,r,y)
    if change=='historical-reader-revoked':
        with psycopg.connect(x['admin']) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=ANY(%s)',(x['grants'],))
    elif change=='wrong-reader-pop':review['reading_population_id']=str(uuid4())
    elif change=='wrong-reader-registry':review['reading_operation_registry_hash']='0'*64
    elif change=='integer-pass':review['qualification_pass']=1
    elif change=='review-revoked':
        with psycopg.connect(x['admin']) as c:c.execute("UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE actor_id=%s AND scope LIKE 'source-original-review:%%'",(y['actor'],))
    elif change=='same-actor':
        with psycopg.connect(x['admin']) as c:
            c.execute('UPDATE oracle2.hosting_original_source_admissions SET principal_id=%s WHERE role_name=%s',(x['actor'],y['login']))
            c.execute('UPDATE oracle2.hosting_original_population_admissions_v1 SET principal_id=%s WHERE role_name=%s',(x['actor'],y['login']))
            c.execute('UPDATE oracle2.appointments SET actor_id=%s WHERE actor_id=%s',(x['actor'],y['actor']))
    if change in ('none','historical-reader-revoked'):
        result=call(y,'commit_original_review_response_v1',canonical_bytes(review));assert result['principal_id']==str(y['actor']) and result['population_id']==str(y['review_pop'])
    else:
        with pytest.raises((psycopg.errors.InsufficientPrivilege,psycopg.errors.InvalidParameterValue)):
            call(y,'commit_original_review_response_v1',canonical_bytes(review))

@pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)
def test_native_utf8_actual_sql_commit_has_no_paid_fields(raw_reader):
    x=raw_reader;b=reading_body(x)
    b['transport']='native-utf8-byte-roundtrip-v1';b['reading_sha256']=x['refs'][0].original_sha256
    for key in ('native_dispatch_id','native_job_hash','request_hash','raw_wire_hash','model_content_hash','native_custody_receipt_hash','authorized_phase_commit_hash'):b.pop(key,None)
    # Fixture authors exact seven original bytes BEFORE reserve/admission.
    assert b['reading_sha256']==__import__('hashlib').sha256(b'invent!').hexdigest()
    r=call(x,'commit_original_reading_response_v1',canonical_bytes(b))
    with psycopg.connect(x['admin']) as c:
        row=c.execute('SELECT transport,native_dispatch_id,body FROM oracle2.original_phase_response_commits WHERE commit_sha256=%s',(r['commit_sha256'],)).fetchone()
        assert row[0]=='native-utf8-byte-roundtrip-v1' and row[1] is None and row[2]==b
