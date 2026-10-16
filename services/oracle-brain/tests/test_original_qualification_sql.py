"""GIVEN independently appointed evidence seals; SQL does not prove paid wire."""
from dataclasses import replace
from datetime import datetime,timezone
from uuid import uuid4
import time
import psycopg
from psycopg.types.json import Jsonb
import pytest
from test_original_response_commit_sql import raw_reader,requester,independent_reviewer,reading_body,review_body
from test_replacement_source_intake_sql import call
from test_source_processing_qualification import processing
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.authority_adapter import QualifiedRevisionProcessingSourceResolverV1


def qualified_input(x,y):
    text='Invented independently reviewed reading.';view={'schema_version':1,'given_view':'invented SQL boundary'};locators={'locators':[]}
    b=reading_body(x,reading_sha256=__import__('hashlib').sha256(text.encode()).hexdigest(),view_manifest_hash=digest(view),locator_map_hash=digest(locators))
    r=call(x,'commit_original_reading_response_v1',canonical_bytes(b));review=review_body(b,r,y);v=call(y,'commit_original_review_response_v1',canonical_bytes(review))
    ref=x['refs'][0]
    with psycopg.connect(x['admin']) as c:
        c.execute('INSERT INTO oracle2.hosting_original_qualification_admissions_v1 VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (y['login'],x['workspace'],ref.source_id,y['actor'],y['review_pop'],y['review_operation'],r['commit_sha256'],v['commit_sha256'],'a'*64,'b'*64,'c'*64,x['until']))
    payload=dict(reading_commit_hash=r['commit_sha256'],review_commit_hash=v['commit_sha256'],reading_text=text,
        parser_provenance=dict(original_hash=ref.original_sha256,content_hash=b['reading_sha256'],parser_identity=b['parser_id'],content_type=ref.media_type,evidence_kind='visual_transcription',page_count=1,review_receipt='c'*64),
        view_manifest=view,locator_map=locators,qualification_registry_sha256='a'*64,qualifier_custody_sha256='b'*64,caller_deadline=x['until'].isoformat())
    return payload


def current_processing(x,f,ref):
    with psycopg.connect(x['admin']) as c:
        c.execute('DELETE FROM oracle2.hosting_role_source_admissions WHERE role_name=%s',(f['login'],))
        c.execute('INSERT INTO oracle2.hosting_role_source_admissions VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s)',(f['login'],x['workspace'],ref.source_id,f['actor'],ref.original_sha256,ref.reading_sha256,ref.parser_id,f['binding'].runtime_hash,f['binding'].source_registry_hash,f['expiry']))
        for scope in ('source-read:','source-extraction:'):
            c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),x['workspace'],f['actor'],scope+str(ref.source_id),x['owner'],x['root'],f['expiry']))
    return QualifiedRevisionProcessingSourceResolverV1(f['url'],binding=f['binding'])


def test_actual_qualification_publishes_first_ref_without_legacy_draft(independent_reviewer,processing):
    from oracle_brain.operating_model.contracts import SourceRef
    x,y=independent_reviewer;p=qualified_input(x,y);ref=x['refs'][0]
    result=call(y,'original_reading_qualify_v1',ref.source_id,1,Jsonb(p));expected=SourceRef.model_validate_json(__import__('json').dumps(result))
    assert expected.reading_sha256==p['parser_provenance']['content_hash']
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.drafts WHERE source_id=%s',(ref.source_id,)).fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM oracle2.source_blocks WHERE source_id=%s',(ref.source_id,)).fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM oracle2.hosting_role_source_admissions WHERE source_id=%s',(ref.source_id,)).fetchone()[0]==0
    f=processing('source-reader');resolver=current_processing(x,f,expected)
    assert resolver.identity(x['workspace'],ref.source_id)==expected
    assert resolver.current_for_processing(x['workspace'],ref.source_id).reading==p['reading_text']

@pytest.mark.parametrize('change',['reading','view','locator','provenance','registry','custody','unknown','current-review','current-root','deadline'])
def test_qualification_refuses_before_receipt_and_source_promotion(independent_reviewer,change):
    x,y=independent_reviewer;p=qualified_input(x,y);ref=x['refs'][0]
    if change=='reading':p['reading_text']+=' changed'
    elif change=='view':p['view_manifest']['extra']='changed'
    elif change=='locator':p['locator_map']['locators']=[{'changed':True}]
    elif change=='provenance':p['parser_provenance']['private_key']='forbidden'
    elif change=='registry':p['qualification_registry_sha256']='0'*64
    elif change=='custody':p['qualifier_custody_sha256']='0'*64
    elif change=='unknown':p['actor_id']=str(y['actor'])
    elif change=='deadline':p['caller_deadline']='2000-01-01T00:00:00Z'
    else:
        with psycopg.connect(x['admin']) as c:
            if change=='current-root':c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['root'],))
            else:c.execute("UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE actor_id=%s AND scope LIKE 'source-original-review:%%'",(y['actor'],))
    with pytest.raises((psycopg.errors.InsufficientPrivilege,psycopg.errors.InvalidParameterValue)):
        call(y,'original_reading_qualify_v1',ref.source_id,1,Jsonb(p))
    with psycopg.connect(x['admin']) as c:
        assert c.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE source_id=%s',(ref.source_id,)).fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM oracle2.operating_model_source_receipts WHERE source_id=%s',(ref.source_id,)).fetchone()[0]==0
        assert c.execute('SELECT status FROM oracle2.sources WHERE source_id=%s',(ref.source_id,)).fetchone()[0]=='processing'

@pytest.mark.parametrize('change',['read','root','head','withdraw','qualification'])
def test_new_processing_reads_remain_current_after_qualification(independent_reviewer,processing,change):
    from oracle_brain.operating_model.contracts import SourceRef
    x,y=independent_reviewer;p=qualified_input(x,y);raw=x['refs'][0]
    ref=SourceRef.model_validate_json(__import__('json').dumps(call(y,'original_reading_qualify_v1',raw.source_id,1,Jsonb(p))))
    f=processing('source-reader');resolver=current_processing(x,f,ref)
    assert resolver.identity(x['workspace'],raw.source_id)==ref
    with psycopg.connect(x['admin']) as c:
        if change=='read':c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE actor_id=%s AND workspace_id=%s',(f['actor'],x['workspace']))
        elif change=='root':c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['root'],))
        elif change=='head':c.execute('UPDATE oracle2.sources SET revision=2 WHERE source_id=%s',(raw.source_id,))
        elif change=='qualification':c.execute("UPDATE oracle2.source_reading_qualifications SET reading_sha256=repeat('0',64) WHERE source_id=%s",(raw.source_id,))
        else:c.execute("INSERT INTO oracle2.source_original_withdrawals_v1 VALUES(%s,%s,%s,1,%s,%s,%s,%s,'given immutable withdrawal',%s,%s,clock_timestamp())",(uuid4(),x['workspace'],raw.source_id,raw.original_sha256,x['actor'],x['login'],'e'*64,uuid4(),'f'*64))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):resolver.current_for_processing(x['workspace'],raw.source_id)

@pytest.mark.parametrize('raw_reader',['short-horizon'],indirect=True)
def test_historical_original_horizon_never_expires_current_qualified_content(independent_reviewer,processing):
    from oracle_brain.operating_model.contracts import SourceRef
    x,y=independent_reviewer;p=qualified_input(x,y);raw=x['refs'][0]
    ref=SourceRef.model_validate_json(__import__('json').dumps(call(y,'original_reading_qualify_v1',raw.source_id,1,Jsonb(p))))
    f=processing('source-reader');resolver=current_processing(x,f,ref)
    with psycopg.connect(x['admin']) as c:old_wire=bytes(c.execute('SELECT canonical_body FROM oracle2.original_phase_response_commits WHERE commit_sha256=%s',(p['reading_commit_hash'],)).fetchone()[0])
    time.sleep(max(0,(x['until']-datetime.now(timezone.utc)).total_seconds())+.05)
    assert resolver.current_for_processing(x['workspace'],raw.source_id).ref==ref
    with pytest.raises(psycopg.errors.InsufficientPrivilege):call(y,'original_reading_qualify_v1',raw.source_id,1,Jsonb(p))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'commit_original_reading_response_v1',old_wire)


def test_closed_new_resolver_refuses_arbitrary_subclass_without_connection():
    class Foreign(QualifiedRevisionProcessingSourceResolverV1):pass
    with pytest.raises(PermissionError,match='exact qualified'):Foreign('never-used',binding=object())
