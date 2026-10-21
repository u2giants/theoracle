"""Actual owned SQL contract controls; injected qualified bodies are NOT native proof."""
from datetime import datetime,timezone,timedelta
import json
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from test_source_processing_qualification import processing,resolver,RUNTIME,REGISTRY
from test_processing_compiler_capabilities import persist_extraction,bundle


def test_canonical_owner_capabilities_and_unissued_admissions(admin_url):
    with psycopg.connect(admin_url) as c:
        assert c.execute('SELECT count(*) FROM oracle2.processing_model_admissions_v1').fetchone()[0]==0
        rows=c.execute("SELECT p.proname,p.proowner=n.nspowner,p.prosecdef FROM pg_proc p JOIN pg_namespace n ON p.pronamespace=n.oid WHERE n.nspname='oracle2' AND p.proname IN('commit_processing_model_revision_v1','hosting_historical_consolidated_model_v1','record_processing_model_review_v1')").fetchall()
        assert len(rows)==3 and all(owner and security for _,owner,security in rows)


def appointment(admin,f,operation='consolidate',*,refs=None,scope_hash=None,membership=None,login=None,actor=None,model=None,decision_kind='employee-account'):
    aid=uuid4();actor=actor or f['actor'];login=login or f['login']
    receipt=resolver(f).current_for_processing(f['workspace'],f['source'])
    refs=refs or [r.model_dump(mode='json') for r in f.get('all_refs',(receipt.ref,))]
    with psycopg.connect(admin) as c:
        c.execute('INSERT INTO oracle2.processing_model_admissions_v1(admission_id,role_name,principal_id,workspace_id,model_id,operation,runtime_hash,registry_hash,config_hash,issuer_actor,reviewer_actor,decision_kind,decision_valid_until,scope_hash,membership_appointment,source_refs,issued_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
          (aid,login,actor,f['workspace'],model or f['model'],operation,RUNTIME,REGISTRY,'f'*64,uuid4(),uuid4(),decision_kind if operation=='business-review' else None,f['expiry'] if operation=='business-review' else None,scope_hash,membership,Jsonb(refs),datetime.now(timezone.utc)-timedelta(seconds=1),f['expiry']))
        if operation=='consolidate':
            owner=c.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
            c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f['workspace'],actor,'processing-consolidate',owner,f['root'],f['expiry']))
            c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.commit_processing_model_revision_v1(jsonb,bytea,bytea,bytea,jsonb,uuid,text,text,text,timestamptz,uuid),oracle2.hosting_processing_model_revision_v1(uuid,integer,uuid,text,text,text,timestamptz) TO {}').format(sql.Identifier(login)))
    return aid


def prepare_correction_original(admin,f):
    """Fixture host installs a distinct invented original, never runtime issuance."""
    if 'correction_source' in f:return
    original=f['source'];fresh=uuid4()
    with psycopg.connect(admin) as c:
        c.execute("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) SELECT %s,workspace_id,uploaded_by,'invented-correction.txt',content_type,status FROM oracle2.sources WHERE source_id=%s",(fresh,original))
        c.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) SELECT gen_random_uuid(),%s,workspace_id,created_by,'invented new correction source','draft' FROM oracle2.drafts WHERE source_id=%s",(fresh,original))
        c.execute("INSERT INTO oracle2.source_blocks SELECT gen_random_uuid(),%s,workspace_id,block_index,kind,text,span_start,span_end FROM oracle2.source_blocks WHERE source_id=%s",(fresh,original))
        c.execute("INSERT INTO oracle2.hosting_role_source_admissions SELECT role_name,workspace_id,%s,revision,principal_id,original_hash,reading_hash,parser_id,runtime_hash,registry_hash,expires_at FROM oracle2.hosting_role_source_admissions WHERE role_name=%s AND source_id=%s",(fresh,f['login'],original))
        owner=c.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
        for prefix in ('source-read:','source-extraction:'):
            c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f['workspace'],f['actor'],prefix+str(fresh),owner,f['root'],f['expiry']))
    f['correction_source']=fresh
    f['history_refs']=(resolver(f).current_for_processing(f['workspace'],original).ref,resolver(f).current_for_processing(f['workspace'],fresh).ref)


def revision(admin,f,tmp_path,*,aid=None,artifact=None,version=1,previous_hash=None,new_correction=True,provenance='employee_account'):
    prepare_correction_original(admin,f)
    if version>1 and new_correction:f['source']=f['correction_source']
    ledger,parent,_=persist_extraction(f,tmp_path)
    receipt=resolver(f).current_for_processing(f['workspace'],f['source']);ref=receipt.ref.model_dump(mode='json')
    artifact=artifact or uuid4();f['model']=artifact;scope={k:{'mode':'all','identities':[]} for k in ('process','customer','product','region')}
    # Host-injected schema3 shape exercises SQL only; no native generation claim.
    core={'contract':'qualified-consolidation-core-v1','model':{'model_id':str(artifact),'version':version},'expected_predecessor_version':version-1,'expected_predecessor_hash':previous_hash,'correction_source_ids':[] if version==1 else [str(f['source'])],
      'assertions':[{'assertion_id':str(uuid4()),'revision':1,'scope':scope,'provenance':provenance,'valid_time':'unknown','valid_from':None,'valid_to':None}]}
    payload={'source_refs':[ref],'findings':[],'operating_models':[core['model']],'consolidation_core':core,
      'assembly_capture':{'candidate_schema':'purpose-captured-consolidation-v1'},
      'assembly_qualification':{'schema_version':3,'admission':{'captured_schema':'purpose-captured-consolidation-v1','compiler_actor':str(f['actor']),'expires_at':f['expiry'].isoformat()}}}
    args,m,_=bundle(f,kind='processing_qualified_model_v1',payload=payload,dependencies=(('artifact',str(parent.artifact_id),'1'),))
    from oracle_brain.operating_model.contracts import canonical_bytes,digest
    m=m.model_copy(update={'artifact_id':artifact,'version':version})
    args[0]=Jsonb(m.model_dump(mode='json'))
    return appointment(admin,f,refs=[ref]) if version>1 else (aid or appointment(admin,f,refs=[ref])),m,args,payload


def call_revision(f,aid,args,*,idempotency=None):
    with psycopg.connect(f['url']) as c:
        return c.execute('SELECT oracle2.commit_processing_model_revision_v1(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (*args[:5],aid,RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=20),idempotency or uuid4())).fetchone()[0]


def test_actual_revision_atomic_consecutive_head_and_readback(admin_url,processing,tmp_path):
    f=processing();aid,m,args,payload=revision(admin_url,f,tmp_path)
    first=call_revision(f,aid,args)
    aid,m2,args2,_=revision(admin_url,f,tmp_path,aid=aid,artifact=m.artifact_id,version=2,previous_hash=m.content_hash)
    second=call_revision(f,aid,args2)
    assert first['recordedAt']<second['recordedAt']
    with psycopg.connect(f['url']) as c:
        fresh=c.execute('SELECT oracle2.hosting_processing_model_revision_v1(%s,%s,%s,%s,%s,%s,%s)',(m.artifact_id,2,aid,RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10))).fetchone()[0]
        assert fresh['manifest']==m2.model_dump(mode='json')
    with pytest.raises(psycopg.errors.SerializationFailure):call_revision(f,aid,args2)
    with psycopg.connect(admin_url) as c:
        assert c.execute('SELECT count(*) FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=%s',(f['workspace'],)).fetchone()[0]==2
        assert c.execute("SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s AND payload->>'namespace'='oracle_processing_v1'",(f['workspace'],)).fetchone()[0]==2


@pytest.mark.parametrize('damage',('no-appointment','wrong-config','expired','revoked','wrong-actor','old-capture','old-schema','skipped-version','invented-field'))
def test_actual_admission_and_fresh_contract_refusal_is_atomic(admin_url,processing,tmp_path,damage):
    f=processing();aid,m,args,payload=revision(admin_url,f,tmp_path)
    if damage=='no-appointment':aid=uuid4()
    elif damage in ('expired','revoked','wrong-actor'):
        with psycopg.connect(admin_url) as c:
            if damage=='revoked':c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(aid,))
            else:
                # Host fixture alters admission before invocation only; production rows immutable.
                c.execute('ALTER TABLE oracle2.processing_model_admissions_v1 DISABLE TRIGGER USER')
                if damage=='expired':c.execute("UPDATE oracle2.processing_model_admissions_v1 SET issued_at=clock_timestamp()-interval '2 seconds',expires_at=clock_timestamp()-interval '1 second' WHERE admission_id=%s",(aid,))
                else:c.execute('UPDATE oracle2.processing_model_admissions_v1 SET principal_id=%s WHERE admission_id=%s',(uuid4(),aid))
                c.execute('ALTER TABLE oracle2.processing_model_admissions_v1 ENABLE TRIGGER USER')
    elif damage=='wrong-config':
        with psycopg.connect(admin_url) as c:
            c.execute('ALTER TABLE oracle2.processing_model_admissions_v1 DISABLE TRIGGER USER');c.execute("UPDATE oracle2.processing_model_admissions_v1 SET config_hash=%s WHERE admission_id=%s",('0'*64,aid));c.execute('ALTER TABLE oracle2.processing_model_admissions_v1 ENABLE TRIGGER USER')
    else:
        if damage=='old-capture':payload['assembly_capture']['candidate_schema']='purpose-captured-assembly-v2'
        elif damage=='old-schema':payload['assembly_qualification']['schema_version']=2
        elif damage=='skipped-version':payload['consolidation_core']['expected_predecessor_version']=2
        elif damage=='invented-field':payload['consolidation_core']['assertions'][0]['confirmed']=True
        from oracle_brain.operating_model.contracts import canonical_bytes,digest
        args[1]=canonical_bytes(payload);m=m.model_copy(update={'content_hash':digest(payload),'private_object_key':f"operating-model/{f['workspace']}/{digest(payload)}.json"});args[0]=Jsonb(m.model_dump(mode='json'))
    with pytest.raises(psycopg.Error):call_revision(f,aid,args)
    with psycopg.connect(admin_url) as c:
        assert c.execute('SELECT count(*) FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=%s',(f['workspace'],)).fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s',(f['workspace'],m.artifact_id)).fetchone()[0]==0


def history_actor(admin,f,*,operation='history-read',scope_hash=None,decision_kind='employee-account',principal=None):
    login='temporal_'+uuid4().hex[:12];actor=principal or uuid4();membership=uuid4()
    ref=resolver(f).current_for_processing(f['workspace'],f['source']).ref
    with psycopg.connect(admin) as c:
        owner=c.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
        c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-history-only')))
        c.execute(sql.SQL('GRANT USAGE ON SCHEMA oracle2 TO {}').format(sql.Identifier(login)))
        scopes=['source-read:'+str(f['source'])]
        if operation=='history-read':scopes+=['processing-history','source-history:'+str(f['source'])+':1']
        else:scopes+=['processing-business:'+decision_kind+':'+scope_hash]
        for scope in scopes:
            c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(membership if scope.startswith('processing-business:') else uuid4(),f['workspace'],actor,scope,owner,f['root'],f['expiry']))
        if operation=='history-read':
            funcs=['hosting_consolidated_model_version_v1(uuid,integer,uuid,text,text,text,timestamptz)','hosting_historical_consolidated_model_v1(uuid,timestamptz,timestamptz,uuid,text,text,text,timestamptz)','hosting_current_consolidated_model_v1(uuid,uuid,text,text,text,timestamptz)','hosting_historical_source_revision_v1(jsonb,uuid,text,text,text,timestamptz)']
        else:funcs=['record_processing_model_review_v1(uuid,integer,text,text,bytea,jsonb,text,uuid,uuid,text,text,text,timestamptz)','hosting_processing_review_diff_v1(uuid,integer,uuid,text,text,text,timestamptz)']
        for signature in funcs:c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.'+signature+' TO {}').format(sql.Identifier(login)))
        c.execute("INSERT INTO oracle2.source_original_revisions VALUES(%s,%s,1,%s,12,'application/pdf','invented.pdf',%s,'invented/sealed-original',%s,clock_timestamp()) ON CONFLICT DO NOTHING",(f['workspace'],f['source'],ref.original_sha256,'1'*64,f['actor']))
        c.execute('INSERT INTO oracle2.source_reading_qualifications VALUES(%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp()) ON CONFLICT DO NOTHING',(f['workspace'],f['source'],ref.original_sha256,ref.reading_sha256,ref.parser_id,'2'*64,'3'*64,'4'*64,'5'*64,uuid4(),uuid4()))
    if 'all_refs' in f or 'history_refs' in f:
        for other in f.get('history_refs',f.get('all_refs',())):
            if other==ref:continue
            with psycopg.connect(admin) as c:
                for scope in ('source-read:'+str(other.source_id),'source-history:'+str(other.source_id)+':'+str(other.revision)):
                    c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f['workspace'],actor,scope,owner,f['root'],f['expiry']))
                c.execute("INSERT INTO oracle2.source_original_revisions VALUES(%s,%s,1,%s,12,'application/pdf','invented.pdf',%s,'invented/sealed-original',%s,clock_timestamp()) ON CONFLICT DO NOTHING",(f['workspace'],other.source_id,other.original_sha256,'1'*64,f['actor']))
                c.execute('INSERT INTO oracle2.source_reading_qualifications VALUES(%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp()) ON CONFLICT DO NOTHING',(f['workspace'],other.source_id,other.original_sha256,other.reading_sha256,other.parser_id,'2'*64,'3'*64,'4'*64,'5'*64,uuid4(),uuid4()))
    aid=appointment(admin,f,operation=operation,login=login,actor=actor,refs=[r.model_dump(mode='json') for r in f.get('history_refs',f.get('all_refs',(ref,)))],scope_hash=scope_hash,membership=membership if operation=='business-review' else None,decision_kind=decision_kind)
    return dict(url=psycopg.conninfo.make_conninfo(f['url'],user=login,password='invented-history-only'),login=login,actor=actor,aid=aid,ref=ref)


def historical(h,model,known_at):
    with psycopg.connect(h['url']) as c:
        return c.execute('SELECT oracle2.hosting_historical_consolidated_model_v1(%s,%s,%s,%s,%s,%s,%s,%s)',(model,datetime.now(timezone.utc),known_at,h['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10))).fetchone()[0]


def test_old_public_entry_and_owner_private_helper_cannot_bypass_revision(admin_url,processing,tmp_path):
    f=processing();aid,m,args,payload=revision(admin_url,f,tmp_path)
    with psycopg.connect(f['url']) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.commit_processing_candidate(%s,%s,%s,%s,%s,%s,%s,%s)',args)
    with psycopg.connect(f['url']) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2._commit_processing_candidate_canonical_v1(%s,%s,%s,%s,%s,%s,%s,%s)',args)
    with psycopg.connect(admin_url) as c:
        assert c.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE artifact_id=%s',(m.artifact_id,)).fetchone()[0]==0
    call_revision(f,aid,args)


def test_bitemporal_registered_versions_and_exact_history_source_metadata(admin_url,processing,tmp_path):
    f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);first=call_revision(f,aid,args)
    h=history_actor(admin_url,f)
    aid,m2,args2,_=revision(admin_url,f,tmp_path,aid=aid,artifact=m.artifact_id,version=2,previous_hash=m.content_hash);second=call_revision(f,aid,args2)
    one=historical(h,m.artifact_id,datetime.fromisoformat(first['recordedAt']))
    two=historical(h,m.artifact_id,datetime.fromisoformat(second['recordedAt']))
    assert one['manifest']['version']==1 and two['manifest']['version']==2
    assert one['policyAccepted'] is False
    with psycopg.connect(h['url']) as c:
        citation=c.execute('SELECT oracle2.hosting_historical_source_revision_v1(%s,%s,%s,%s,%s,%s)',(Jsonb(h['ref'].model_dump(mode='json')),h['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10))).fetchone()[0]
        assert citation['sourceRef']==h['ref'].model_dump(mode='json') and citation['historical'] is True
    with pytest.raises(psycopg.errors.NoDataFound):historical(h,m.artifact_id,datetime.fromisoformat(first['recordedAt'])-timedelta(seconds=1))
    with psycopg.connect(h['url']) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.hosting_current_consolidated_model_v1(%s,%s,%s,%s,%s,%s)',(m.artifact_id,h['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10)))


@pytest.mark.parametrize('damage',('history-revoked','source-read-revoked','source-history-revoked','old-untyped-invalidation','withdrawn','wrong-role','unknown-history-time'))
def test_actual_history_current_authority_denies_no_cache_or_role_borrowing(admin_url,processing,tmp_path,damage):
    f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);first=call_revision(f,aid,args);h=history_actor(admin_url,f)
    known=datetime.fromisoformat(first['recordedAt'])
    with psycopg.connect(admin_url) as c:
        if damage=='history-revoked':c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(h['aid'],))
        elif damage in ('source-read-revoked','source-history-revoked'):
            prefix='source-read:' if damage=='source-read-revoked' else 'source-history:'
            c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE workspace_id=%s AND actor_id=%s AND scope LIKE %s',(f['workspace'],h['actor'],prefix+'%'))
        elif damage=='old-untyped-invalidation':c.execute("INSERT INTO oracle2.artifact_invalidations VALUES(%s,%s,1,'source revision replaced',%s,clock_timestamp())",(f['workspace'],m.artifact_id,uuid4()))
        elif damage=='withdrawn':c.execute("UPDATE oracle2.sources SET status='error' WHERE source_id=%s",(f['source'],))
        elif damage=='wrong-role':h['url']=f['url']
        elif damage=='unknown-history-time':known=datetime.now(timezone.utc)+timedelta(days=1)
    with pytest.raises(psycopg.Error):historical(h,m.artifact_id,known)


def test_exact_fresh_business_review_never_inherited_and_stale_refresh_redacts(admin_url,processing,tmp_path):
    from oracle_brain.operating_model.contracts import canonical_bytes
    import hashlib
    f=processing();aid,m,args,payload=revision(admin_url,f,tmp_path);call_revision(f,aid,args)
    scope=payload['consolidation_core']['assertions'][0]['scope'];scope_raw=canonical_bytes(scope)
    business=history_actor(admin_url,f,operation='business-review',scope_hash=hashlib.sha256(scope_raw).hexdigest())
    assertion=payload['consolidation_core']['assertions'][0];selected=[{'assertion_id':assertion['assertion_id'],'revision':assertion['revision']}]
    key=uuid4()
    def decide(version,content):
        with psycopg.connect(business['url']) as c:
            return c.execute('SELECT oracle2.record_processing_model_review_v1(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(m.artifact_id,version,content,'accept',scope_raw,Jsonb(selected),'a'*64,key,business['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10))).fetchone()[0]
    assert decide(1,m.content_hash)['decision']=='accept'
    with pytest.raises(psycopg.errors.UniqueViolation):decide(1,m.content_hash)
    aid,m2,args2,_=revision(admin_url,f,tmp_path,aid=aid,artifact=m.artifact_id,version=2,previous_hash=m.content_hash);call_revision(f,aid,args2)
    with pytest.raises(psycopg.errors.SerializationFailure):decide(1,m.content_hash)
    with psycopg.connect(business['url']) as c:
        refresh=c.execute('SELECT oracle2.hosting_processing_review_diff_v1(%s,%s,%s,%s,%s,%s,%s)',(m.artifact_id,1,business['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10))).fetchone()[0]
        assert refresh['conflict'] is True and refresh['basePermitted'] is False and 'reload' in refresh['message']
    with psycopg.connect(admin_url) as c:
        assert c.execute("SELECT count(*) FROM oracle2.processing_model_events_v1 WHERE workspace_id=%s AND artifact_id=%s AND version=2 AND kind='business-accept'",(f['workspace'],m.artifact_id)).fetchone()[0]==0


def test_actual_new_version_invalidates_only_dependent_summary_and_recommendation(admin_url,processing,tmp_path):
    from test_processing_compiler_capabilities import commit
    f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);call_revision(f,aid,args)
    children=[]
    for kind in ('processing_summary_v1','processing_recommendation_v1'):
        wire,child,_=bundle(f,kind=kind,dependencies=(('artifact',str(m.artifact_id),'1'),))
        commit(f,wire);children.append(child)
    other_id=uuid4();other_aid,other,other_args,_=revision(admin_url,f,tmp_path,artifact=other_id);call_revision(f,other_aid,other_args)
    def metadata(item):
        with psycopg.connect(f['url']) as c:return c.execute('SELECT * FROM oracle2.hosting_processing_artifact(%s,%s,%s,%s,%s,%s)',(f['workspace'],item.artifact_id,item.version,f['actor'],RUNTIME,REGISTRY)).fetchone()
    assert all(metadata(item)[0]['kind']==item.kind for item in children)
    aid,m2,args2,_=revision(admin_url,f,tmp_path,aid=aid,artifact=m.artifact_id,version=2,previous_hash=m.content_hash);call_revision(f,aid,args2)
    for item in children+[m]:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):metadata(item)
    assert metadata(other)[0]['content_hash']==other.content_hash
    with psycopg.connect(admin_url) as c:
        assert c.execute("SELECT count(*) FROM oracle2.processing_model_events_v1 WHERE workspace_id=%s AND kind='derived-stale'",(f['workspace'],)).fetchone()[0]==2
        assert c.execute('SELECT count(*) FROM oracle2.artifact_dependencies WHERE workspace_id=%s AND artifact_id=%s AND version=2 AND upstream_id=%s',(f['workspace'],m.artifact_id,str(m.artifact_id))).fetchone()[0]==0


def test_actual_concurrent_corrected_revision_has_one_winner(admin_url,processing,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);call_revision(f,aid,args)
    aid,m2,args2,_=revision(admin_url,f,tmp_path,aid=aid,artifact=m.artifact_id,version=2,previous_hash=m.content_hash)
    def one(_):
        try:call_revision(f,aid,args2);return 'committed'
        except psycopg.errors.SerializationFailure:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(one,range(2)))==['committed','conflict']
    with psycopg.connect(admin_url) as c:
        assert c.execute('SELECT count(*) FROM oracle2.processing_model_revisions_v1 WHERE artifact_id=%s AND version=2',(m.artifact_id,)).fetchone()[0]==1


def test_actual_explicit_business_withdraw_keeps_accepted_then_record(admin_url,processing,tmp_path):
    from oracle_brain.operating_model.contracts import canonical_bytes
    import hashlib
    f=processing();aid,m,args,payload=revision(admin_url,f,tmp_path);call_revision(f,aid,args)
    scope=canonical_bytes(payload['consolidation_core']['assertions'][0]['scope']);business=history_actor(admin_url,f,operation='business-review',scope_hash=hashlib.sha256(scope).hexdigest())
    a=payload['consolidation_core']['assertions'][0];selection=[{'assertion_id':a['assertion_id'],'revision':a['revision']}]
    with psycopg.connect(business['url']) as c:
        event=c.execute('SELECT oracle2.record_processing_model_review_v1(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(m.artifact_id,1,m.content_hash,'accept',scope,Jsonb(selection),'a'*64,uuid4(),business['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10))).fetchone()[0]
    with psycopg.connect(admin_url) as c:c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.record_processing_model_decision_change_v1(uuid,text,uuid,uuid,text,text,text,timestamptz) TO {}').format(sql.Identifier(business['login'])))
    with psycopg.connect(business['url']) as c:
        change=c.execute('SELECT oracle2.record_processing_model_decision_change_v1(%s,%s,%s,%s,%s,%s,%s,%s)',(event['eventId'],'withdraw',uuid4(),business['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10))).fetchone()[0]
        assert change['targetEventId']==event['eventId']
    with psycopg.connect(admin_url) as c:
        assert c.execute("SELECT kind FROM oracle2.processing_model_events_v1 WHERE artifact_id=%s ORDER BY recorded_at",(m.artifact_id,)).fetchall()==[('business-accept',),('business-withdraw',)]
        accepted=c.execute("SELECT payload FROM oracle2.processing_model_events_v1 WHERE event_id=%s",(event['eventId'],)).fetchone()[0]
        assert accepted['policy_longevity']=='not-company-policy' and 'decision_valid_until' in accepted


def test_actual_source_owner_replacement_classifies_only_its_new_event(admin_url,processing,tmp_path):
    f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);first=call_revision(f,aid,args);h=history_actor(admin_url,f)
    login='intake_history_'+uuid4().hex[:10]
    with psycopg.connect(admin_url) as c:
        owner=c.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
        c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS').format(sql.Identifier(login),sql.Literal('invented-intake-only')))
        c.execute(sql.SQL('GRANT oracle2_replacement_requester TO {}').format(sql.Identifier(login)))
        c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,RUNTIME,REGISTRY,f['expiry']))
        c.execute('INSERT INTO oracle2.hosting_request_principal_admissions VALUES(%s,%s,%s,%s,%s,%s)',(login,f['actor'],f['workspace'],RUNTIME,REGISTRY,f['expiry']))
        c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,'intake',%s,%s,%s)",(uuid4(),f['workspace'],f['actor'],owner,f['root'],f['expiry']))
    url=psycopg.conninfo.make_conninfo(f['url'],user=login,password='invented-intake-only')
    deadline=datetime.now(timezone.utc)+timedelta(seconds=20)
    with psycopg.connect(url) as c:
        c.execute("SET LOCAL statement_timeout='5s'")
        reserved=c.execute('SELECT oracle2.reserve_source_revision_v1(%s,%s,%s)',(1,Jsonb({'source_id':str(f['source']),'filename':'correction.pdf','media_type':'application/pdf','byte_count':12,'caller_deadline':deadline.isoformat()}),uuid4())).fetchone()[0]
    context=reserved['context'];custody={'original_sha256':'c'*64,'byte_count':12,'custody_seal_sha256':'d'*64,'caller_deadline':context['valid_until'],'expected_context':{k:context[k] for k in ('principal_id','workspace_id','session_role','runtime_hash','source_registry_hash')}}
    with psycopg.connect(url) as c:
        c.execute("SET LOCAL statement_timeout='5s'")
        result=c.execute('SELECT oracle2.finalize_source_revision_v1(%s,%s,%s)',(reserved['reservation']['reservation_id'],1,Jsonb(custody))).fetchone()[0]
        assert result['snapshot']['revision']==2
    old=historical(h,m.artifact_id,datetime.fromisoformat(first['recordedAt']))
    assert old['sourceRefs'][0]['revision']==1
    with psycopg.connect(admin_url) as c:
        events=c.execute('SELECT DISTINCT event_id,source_id,old_revision,new_revision FROM oracle2.processing_preserved_supersessions_v1 WHERE workspace_id=%s',(f['workspace'],)).fetchall()
        assert len(events)==1 and events[0][1:]==(f['source'],1,2)
    with psycopg.connect(f['url']) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT * FROM oracle2.hosting_processing_artifact(%s,%s,%s,%s,%s,%s)',(f['workspace'],m.artifact_id,1,f['actor'],RUNTIME,REGISTRY))


def adapter(admin,f,h):
    from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationAuthorityV1,ConsolidationBindingV1,_FUNCTIONS
    from pathlib import Path
    import hashlib
    params=psycopg.conninfo.conninfo_to_dict(h['url'])
    with psycopg.connect(admin) as c:
        rows=c.execute("SELECT p.proname,encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),r.rolname FROM pg_proc p JOIN pg_namespace n ON p.pronamespace=n.oid JOIN pg_roles r ON p.proowner=r.oid WHERE n.nspname='oracle2' AND p.proname=ANY(%s)",([s.split('(')[0] for s in _FUNCTIONS]+['_commit_processing_candidate_canonical_v1'],)).fetchall()
    binding=ConsolidationBindingV1(appointment_id=h['aid'],principal_id=h['actor'],workspace_id=f['workspace'],model_id=f['model'],session_login=h['login'],
        expected_owner=rows[0][2],operation='history-read',runtime_hash=RUNTIME,registry_hash=REGISTRY,config_hash='f'*64,
        ca_path=params['sslrootcert'],ca_sha256=hashlib.sha256(Path(params['sslrootcert']).read_bytes()).hexdigest(),original_horizon=f['expiry'],retained_semantic_admissions=frozenset({'a'*64}),capability_body_hashes=tuple((n,v) for n,v,_ in rows))
    return ConsolidationAuthorityV1(h['url'],binding=binding)


def test_actual_adapter_pins_tls_login_owner_bodies_and_current_permissions(admin_url,processing,tmp_path):
    f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);first=call_revision(f,aid,args);h=history_actor(admin_url,f)
    authority=adapter(admin_url,f,h);deadline=datetime.now(timezone.utc)+timedelta(seconds=20);known=datetime.fromisoformat(first['recordedAt'])
    current=authority._metadata(m.artifact_id,deadline=deadline,valid_at=known,known_at=known)
    assert current['manifest']['content_hash']==m.content_hash
    with psycopg.connect(admin_url) as c:c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(h['aid'],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):authority._metadata(m.artifact_id,deadline=deadline,valid_at=known,known_at=known)


@pytest.mark.parametrize('damage',('wrong-body-pin','wrong-owner','extra-helper-acl','wrong-tls'))
def test_actual_adapter_catalog_substitution_fails_closed(admin_url,processing,tmp_path,damage):
    from dataclasses import replace
    from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationAuthorityV1
    f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);first=call_revision(f,aid,args);h=history_actor(admin_url,f)
    original=adapter(admin_url,f,h);binding=original.binding;url=h['url']
    if damage=='wrong-body-pin':binding=replace(binding,capability_body_hashes=tuple((n,'0'*64) for n,_ in binding.capability_body_hashes))
    elif damage=='wrong-owner':binding=replace(binding,expected_owner='unrelated_owner')
    elif damage=='extra-helper-acl':
        with psycopg.connect(admin_url) as c:c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2._commit_processing_candidate_canonical_v1(jsonb,bytea,bytea,bytea,jsonb,text,text,timestamptz) TO {}').format(sql.Identifier(h['login'])))
    elif damage=='wrong-tls':url=psycopg.conninfo.make_conninfo(url,sslmode='require')
    try:
        with pytest.raises(PermissionError):
            authority=ConsolidationAuthorityV1(url,binding=binding)
            authority._metadata(m.artifact_id,deadline=datetime.now(timezone.utc)+timedelta(seconds=20),valid_at=datetime.fromisoformat(first['recordedAt']),known_at=datetime.fromisoformat(first['recordedAt']))
    finally:
        if damage=='extra-helper-acl':
            with psycopg.connect(admin_url) as c:c.execute(sql.SQL('REVOKE ALL ON FUNCTION oracle2._commit_processing_candidate_canonical_v1(jsonb,bytea,bytea,bytea,jsonb,text,text,timestamptz) FROM {}').format(sql.Identifier(h['login'])))


@pytest.mark.parametrize('damage',('none','wrong-predecessor','other-model-scope','old-invalidated'))
def test_old_protocol_bootstrap_registers_only_new_actual_recorded_revision(admin_url,processing,tmp_path,damage):
    from test_processing_compiler_capabilities import commit
    f=processing();_,parent,_=persist_extraction(f,tmp_path)
    old_wire,old,_=bundle(f,kind='processing_qualified_model_v1',dependencies=(('artifact',str(parent.artifact_id),'1'),))
    commit(f,old_wire)
    if damage=='old-invalidated':
        with psycopg.connect(admin_url) as c:c.execute("INSERT INTO oracle2.artifact_invalidations VALUES(%s,%s,1,'prior untyped denial',%s,clock_timestamp())",(f['workspace'],old.artifact_id,uuid4()))
    aid,new,args,_=revision(admin_url,f,tmp_path,artifact=old.artifact_id,version=2,previous_hash=old.content_hash if damage!='wrong-predecessor' else '0'*64)
    if damage=='other-model-scope':
        with psycopg.connect(admin_url) as c:
            c.execute('ALTER TABLE oracle2.processing_model_admissions_v1 DISABLE TRIGGER USER');c.execute('UPDATE oracle2.processing_model_admissions_v1 SET model_id=%s WHERE admission_id=%s',(uuid4(),aid));c.execute('ALTER TABLE oracle2.processing_model_admissions_v1 ENABLE TRIGGER USER')
    if damage in ('wrong-predecessor','other-model-scope'):
        with pytest.raises(psycopg.Error):call_revision(f,aid,args)
    else:
        result=call_revision(f,aid,args);h=history_actor(admin_url,f)
        with psycopg.connect(admin_url) as c:
            assert c.execute('SELECT version,predecessor_version FROM oracle2.processing_model_revisions_v1 WHERE artifact_id=%s',(old.artifact_id,)).fetchall()==[(2,1)]
        assert historical(h,new.artifact_id,datetime.fromisoformat(result['recordedAt']))['manifest']['version']==2
        with pytest.raises(psycopg.errors.NoDataFound):historical(h,new.artifact_id,datetime.fromisoformat(result['recordedAt'])-timedelta(microseconds=1))


from test_purpose_qualification_v3 import qualified_v3
from test_assembly_context import context


@pytest.fixture
def sql_qualified_v3(monkeypatch):
    # Build FRESH wire/census/assessment fixtures from SQL-valid original parser
    # identity before any context/capture/admission is produced; never retrofit
    # raw response bindings or relax the canonical SQL provenance guard.
    import test_assembly_context as foundation
    from oracle_brain.operating_model.source_receipts import SourceReceipt,EvidenceRef
    from oracle_brain.operating_model.observations import create_observation
    original=foundation.invented_inputs;original_model=foundation.model;workspace=uuid4()
    import test_business_operating_model as original_business
    monkeypatch.setattr(original_business,'W',workspace)
    monkeypatch.setattr(foundation,'model',lambda observations:original_model(observations).model_copy(update={'workspace_id':workspace,'model_id':uuid4()}))
    def valid_inputs():
        before,_=original();observations=[]
        for item in before:
            ref=item.ref.model_copy(update={'parser_id':'b'*64,'workspace_id':workspace,'source_id':uuid4()})
            receipt=SourceReceipt(ref=ref,reading=item.value,display_revision='r1')
            quote=EvidenceRef(ref=ref,start=0,end=len(item.value),quote=item.value)
            observations.append(create_observation(receipt,item.occurrence_key,item.kind,item.scope,item.value,(quote,)))
        return tuple(observations),tuple({'source_refs':[o.ref.model_dump(mode='json')],'observations':[o.model_dump(mode='json')],'findings':[]} for o in observations)
    monkeypatch.setattr(foundation,'invented_inputs',valid_inputs)
    return qualified_v3.__wrapped__(foundation.context.__wrapped__())


def prepared_qualified_model(admin_url,sql_qualified_v3,tmp_path,*,return_fixture=False,return_stage=False,predecessor=None):
    """Injected complete paid wires/semantic pins, ACTUAL compiler SQL/private bytes.

    Host prepares immutable extraction fixtures; this is not original D or paid
    generation. It DOES run actual new capture/qualification guard, canonical
    ledger, current SQL capability, closed private read and second authority pass.
    """
    from dataclasses import replace
    from oracle_brain.operating_model.contracts import canonical_bytes,digest
    from oracle_brain.operating_model.semantic_acceptance import sealed
    from oracle_brain.operating_model.assembly_context import SealedAssemblyExtraction
    from oracle_brain.operating_model.authority_adapter import ProcessingArtifactResolver,ProcessingSourceBinding
    from oracle_brain.operating_model.processing_ledger import ProcessingCompilerLedger
    from oracle_brain.operating_model.purpose_qualification_v3 import PurposeQualifiedAssemblyReadGuardV3
    from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationAuthorityV1
    from oracle_brain.operating_model.consolidation_ledger_v1 import persist_consolidation_revision_v1
    from oracle_brain.operating_model.artifact_storage import FileBlobStore
    from test_consolidation_contracts_v1 import temporal_qualified_fixture
    q=dict(sql_qualified_v3);wire=dict(q['wire']);ctx=wire['context'];w=ctx.job.workspace_id;actor=q['admission'].compiler_actor
    login='temporal_compiler_'+uuid4().hex[:10];root=uuid4();owner=uuid4();expiry=datetime.now(timezone.utc)+timedelta(minutes=5)
    sources=tuple(r.ref for r in ctx.receipts);exts=[]
    app_name='temporal_bytes_'+uuid4().hex
    with psycopg.connect(admin_url) as c:
        schema_owner=c.execute("SELECT r.rolname FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname='oracle2'").fetchone()[0]
        c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS').format(sql.Identifier(login),sql.Literal('invented-compiler-only')))
        c.execute(sql.SQL('GRANT oracle2_candidate_compiler TO {}').format(sql.Identifier(login)))
        c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,RUNTIME,REGISTRY,expiry))
        c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,expires_at) VALUES(%s,%s,%s,'root',%s,%s)",(root,w,owner,uuid4(),expiry))
        for receipt,extraction in zip(ctx.receipts,ctx.extractions,strict=True):
            ref=receipt.ref;prov={'original_hash':ref.original_sha256,'content_hash':ref.reading_sha256,'parser_identity':ref.parser_id,'content_type':'text/plain','evidence_kind':'native_text','page_count':1,'review_receipt':'c'*64}
            c.execute("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) VALUES(%s,%s,%s,'invented.txt','text/plain','draft')",(ref.source_id,w,actor))
            c.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) VALUES(%s,%s,%s,%s,'host-prepared unaccepted source fixture','draft')",(uuid4(),ref.source_id,w,actor))
            for index,(kind,text) in enumerate((('original',receipt.reading),('original-metadata',json.dumps(prov)))):c.execute('INSERT INTO oracle2.source_blocks VALUES(%s,%s,%s,%s,%s,%s,0,%s)',(uuid4(),ref.source_id,w,index,kind,text,len(text)))
            for prefix in ('source-read:','source-extraction:'):c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),w,actor,prefix+str(ref.source_id),owner,root,expiry))
            c.execute('INSERT INTO oracle2.hosting_role_source_admissions VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s)',(login,w,ref.source_id,actor,ref.original_sha256,ref.reading_sha256,ref.parser_id,RUNTIME,REGISTRY,expiry))
            deps=(('source',str(ref.source_id),'1'),);m=extraction.manifest.model_copy(update={'input_digest':digest({'refs':[ref.model_dump(mode='json')]}),'dependency_digest':digest({'dependencies':deps}),'private_object_key':f'operating-model/{w}/{digest(extraction.payload)}.json'})
            c.execute('INSERT INTO oracle2.artifact_manifests VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())',(w,m.artifact_id,m.version,m.kind,m.input_digest,m.source_digest,m.permission_digest,m.compiler_digest,m.dependency_digest,m.content_hash,m.private_object_key,m.state,Jsonb(m.model_dump(mode='json'))))
            c.execute('INSERT INTO oracle2.artifact_dependencies VALUES(%s,%s,1,%s,%s,%s)',(w,m.artifact_id,*deps[0]))
            c.execute('INSERT INTO oracle2.operating_model_source_receipts VALUES(%s,%s,1,%s,%s,%s,%s)',(w,ref.source_id,ref.original_sha256,ref.reading_sha256,ref.parser_id,Jsonb(receipt.model_dump(mode='json'))))
            exts.append(SealedAssemblyExtraction(manifest=m,payload=extraction.payload))
    handoff=ctx.handoff.model_copy(update={'extractions':tuple(exts),'source_registry_hash':REGISTRY})
    ctx=ctx.model_copy(update={'handoff':handoff,'expected_handoff_hash':sealed(handoff),'source_registry_hash':REGISTRY,'compiler_digest':RUNTIME})
    wire['context']=ctx;q['wire']=wire;q['manifest']=q['manifest'].model_copy(update={'compiler_digest':RUNTIME})
    q['admission']=q['admission'].model_copy(update={'runtime_hash':RUNTIME,'compiler_login':login})
    q=temporal_qualified_fixture(q,predecessor=predecessor['q']['payload'] if predecessor is not None else None)
    url=psycopg.conninfo.make_conninfo(admin_url,user=login,password='invented-compiler-only',application_name=app_name)
    source=ProcessingArtifactResolver(url,binding=ProcessingSourceBinding(RUNTIME,REGISTRY,schema_owner,login,actor,'candidate-compiler',expiry,False))
    class CheckedBlobs(FileBlobStore):
        def outside_sql(self):
            with psycopg.connect(admin_url) as c:assert c.execute("SELECT count(*) FROM pg_stat_activity WHERE application_name=%s AND state IN('active','idle in transaction')",(app_name,)).fetchone()[0]==0
        def put(self,*args):self.outside_sql();return super().put(*args)
        def read(self,*args):self.outside_sql();return super().read(*args)
    blobs=CheckedBlobs(predecessor['blobs'].root if predecessor is not None else tmp_path/'actual-private')
    guard=PurposeQualifiedAssemblyReadGuardV3(trusted_admissions=lambda:q['trusted_admission_hashes'],runtime_hash=RUNTIME,
      current_source_identity=lambda workspace,principal,s:source.identity(workspace,s),current_extraction_seal=lambda workspace,principal,a,v:source.extraction_seal(workspace,a,v),qualified_parent_reader=lambda *a:None)
    ledger=ProcessingCompilerLedger(url,blobs,principal=actor,processing_sources=source,processing_compile_guard=guard,processing_read_guard=guard)
    f={'url':url,'login':login,'workspace':w,'actor':actor,'root':root,'source':sources[0].source_id,'expiry':expiry,'model':ctx.model_id,'all_refs':sources,'binding':source.binding}
    aid=appointment(admin_url,f)
    # Reuse fixed catalog/TLS installation consumer, then select exact separate operation.
    compiler_h={'url':url,'login':login,'actor':actor,'aid':aid}
    history_binding=adapter(admin_url,f,compiler_h).binding
    authority=ConsolidationAuthorityV1(url,binding=replace(history_binding,operation='consolidate',retained_semantic_admissions=q['trusted_admission_hashes']))
    if return_stage:return locals()
    manifest,receipt=persist_consolidation_revision_v1(ledger,authority,payload=q['payload'],permission_digest=q['admission'].compiler_permission_hash,
      dependencies=tuple(('artifact',str(e.manifest.artifact_id),'1') for e in exts),idempotency=uuid4(),deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
    assert manifest.content_hash==digest(q['payload']) and json.loads(blobs.read(manifest.private_object_key,manifest.content_hash))==q['payload']
    if predecessor is not None:f['all_refs']=tuple(dict.fromkeys((*predecessor['sources'],*sources)))
    h=history_actor(admin_url,f);history=adapter(admin_url,f,h)
    history=ConsolidationAuthorityV1(h['url'],binding=replace(history.binding,retained_semantic_admissions=q['trusted_admission_hashes']))
    known=datetime.fromisoformat(receipt['recordedAt'])
    if return_fixture:return locals()
    core,metadata=history.read_model_v1(manifest.artifact_id,blobs=blobs,deadline=datetime.now(timezone.utc)+timedelta(seconds=10),valid_at=known,known_at=known)
    assert core.model.model_id==ctx.model_id and metadata['policyAccepted'] is False
    from oracle_brain.operating_model.consolidation_contracts_v1 import AssertionScopeV1
    query=AssertionScopeV1.model_validate_json(json.dumps({k:{'mode':'all','identities':[]} for k in ('process','customer','product','region')}))
    answer=history.read_answer_v1(manifest.artifact_id,scope=query,blobs=blobs,deadline=datetime.now(timezone.utc)+timedelta(seconds=10),valid_at=known,known_at=known)
    assert answer['modelConfirmed'] is False and answer['policyEligibility']=='unknown'
    assert answer['totalApplicable']+answer['totalUnresolved']>0
    class RevokeDuringRead(CheckedBlobs):
        def read(self,*args):
            body=super().read(*args)
            with psycopg.connect(admin_url) as c:c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(h['aid'],))
            return body
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        history.read_answer_v1(manifest.artifact_id,scope=query,blobs=RevokeDuringRead(tmp_path/'actual-private'),deadline=datetime.now(timezone.utc)+timedelta(seconds=10),valid_at=known,known_at=known)



def test_actual_fresh_admission_cannot_relabel_predecessor_population(admin_url,processing,tmp_path):
    f=processing();old_aid,m,args,_=revision(admin_url,f,tmp_path);call_revision(f,old_aid,args)
    new_aid,m2,args2,_=revision(admin_url,f,tmp_path,artifact=m.artifact_id,version=2,previous_hash=m.content_hash,new_correction=False)
    assert new_aid!=old_aid
    with pytest.raises(psycopg.errors.InsufficientPrivilege,match='new qualified original'):
        call_revision(f,new_aid,args2)
    with psycopg.connect(admin_url) as c:
        assert c.execute('SELECT count(*) FROM oracle2.processing_model_revisions_v1 WHERE artifact_id=%s',(m.artifact_id,)).fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM oracle2.processing_model_admissions_v1 WHERE model_id=%s',(m.artifact_id,)).fetchone()[0]==2



def test_actual_company_policy_survives_former_approver_loss_until_explicit_withdrawal(admin_url,processing,tmp_path):
    from oracle_brain.operating_model.contracts import canonical_bytes,digest
    f=processing();aid,m,args,payload=revision(admin_url,f,tmp_path,provenance='reported_policy');call_revision(f,aid,args)
    scope=payload['consolidation_core']['assertions'][0]['scope'];scope_hash=digest(scope)
    approver=history_actor(admin_url,f,operation='business-review',scope_hash=scope_hash,decision_kind='company-policy')
    selected=[{'assertion_id':payload['consolidation_core']['assertions'][0]['assertion_id'],'revision':1}]
    def decision(h):
        with psycopg.connect(h['url']) as c:
            return c.execute('SELECT oracle2.record_processing_model_review_v1(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(m.artifact_id,1,m.content_hash,'accept',canonical_bytes(scope),Jsonb(selected),'a'*64,uuid4(),h['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10))).fetchone()[0]
    event=decision(approver);history=history_actor(admin_url,f)
    def recorded_policy():
        value=historical(history,m.artifact_id,datetime.now(timezone.utc))
        return next(x for x in value['businessDecisions'] if x['eventId']==event['eventId'])
    assert recorded_policy()['policyInForce'] is True
    with psycopg.connect(admin_url) as c:
        c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(approver['aid'],))
        c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE workspace_id=%s AND actor_id=%s AND scope=%s',(f['workspace'],approver['actor'],'processing-business:company-policy:'+scope_hash))
    assert recorded_policy()['policyInForce'] is True
    with pytest.raises(psycopg.errors.InsufficientPrivilege):decision(approver)
    withdrawer=history_actor(admin_url,f,operation='business-review',scope_hash=scope_hash,decision_kind='company-policy')
    with psycopg.connect(admin_url) as c:c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.record_processing_model_decision_change_v1(uuid,text,uuid,uuid,text,text,text,timestamptz) TO {}').format(sql.Identifier(withdrawer['login'])))
    with psycopg.connect(withdrawer['url']) as c:c.execute('SELECT oracle2.record_processing_model_decision_change_v1(%s,%s,%s,%s,%s,%s,%s,%s)',(event['eventId'],'challenge',uuid4(),withdrawer['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10)))
    assert recorded_policy()['policyInForce'] is True and recorded_policy()['challenged'] is True
    with psycopg.connect(withdrawer['url']) as c:c.execute('SELECT oracle2.record_processing_model_decision_change_v1(%s,%s,%s,%s,%s,%s,%s,%s)',(event['eventId'],'withdraw',uuid4(),withdrawer['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10)))
    assert recorded_policy()['policyInForce'] is False and recorded_policy()['withdrawn'] is True


@pytest.mark.parametrize('damage',('none','zero','unknown','foreign-model','wrong-admission','revoked','withdrawn'))
def test_actual_exact_history_version_capability(admin_url,processing,tmp_path,damage):
    f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);call_revision(f,aid,args);h=history_actor(admin_url,f)
    model=m.artifact_id;version=1;appointment_id=h['aid']
    if damage=='zero':version=0
    elif damage=='unknown':version=2
    elif damage=='foreign-model':model=uuid4()
    elif damage=='wrong-admission':appointment_id=appointment(admin_url,f,operation='history-read',login=h['login'],actor=uuid4())
    elif damage in ('revoked','withdrawn'):
        with psycopg.connect(admin_url) as c:
            if damage=='revoked':c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(h['aid'],))
            else:c.execute("UPDATE oracle2.sources SET status='error' WHERE source_id=%s",(f['source'],))
    def read():
        with psycopg.connect(h['url']) as c:return c.execute('SELECT oracle2.hosting_consolidated_model_version_v1(%s,%s,%s,%s,%s,%s,%s)',(model,version,appointment_id,RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10))).fetchone()[0]
    if damage=='none':
        value=read();assert value['mode']=='retained-version' and 'validAt' not in value and 'knownAt' not in value
    else:
        with pytest.raises(psycopg.Error):read()



def test_actual_fresh_capture_guard_canonical_ledger_private_bytes_history_chain(admin_url,sql_qualified_v3,tmp_path):
    prepared_qualified_model(admin_url,sql_qualified_v3,tmp_path)



@pytest.mark.parametrize('damage',('readback-connection-loss','readback-revocation','commit-close-permission-error'))
def test_actual_committed_revision_readback_failure_is_unknown_no_retry(admin_url,sql_qualified_v3,tmp_path,monkeypatch,damage):
    from oracle_brain.operating_model.consolidation_ledger_v1 import persist_consolidation_revision_v1,ConsolidationCommitUnknown
    stage=prepared_qualified_model(admin_url,sql_qualified_v3,tmp_path,return_stage=True)
    ledger,authority,q=stage['ledger'],stage['authority'],stage['q'];original=psycopg.connect;writes=[]
    class Connection:
        def __init__(self,c):self.c=c;self.wrote=False
        def __getattr__(self,key):return getattr(self.c,key)
        def __enter__(self):self.c.__enter__();return self
        def __exit__(self,*args):
            result=self.c.__exit__(*args)
            if self.wrote and damage=='commit-close-permission-error' and args[0] is None:raise PermissionError('invented close failure AFTER actual commit')
            return result
        def execute(self,query,*args,**kwargs):
            if 'commit_processing_model_revision_v1(' in str(query):writes.append(query);self.wrote=True
            if 'hosting_processing_model_revision_v1(' in str(query):
                if damage=='readback-connection-loss':raise psycopg.OperationalError('invented lost readonly connection')
                with original(admin_url) as c:c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(authority.binding.appointment_id,))
            return self.c.execute(query,*args,**kwargs)
    monkeypatch.setattr(psycopg,'connect',lambda url,*a,**kw:Connection(original(url,*a,**kw)) if url==authority.url else original(url,*a,**kw))
    with pytest.raises(ConsolidationCommitUnknown,match='read-only reconciliation'):
        persist_consolidation_revision_v1(ledger,authority,payload=q['payload'],permission_digest=q['admission'].compiler_permission_hash,
            dependencies=tuple(('artifact',str(e.manifest.artifact_id),'1') for e in stage['exts']),idempotency=uuid4(),deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
    assert len(writes)==1
    with original(admin_url) as c:
        assert c.execute('SELECT count(*) FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=%s AND artifact_id=%s',(stage['w'],stage['ctx'].model_id)).fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s AND assertion_id=%s',(stage['w'],stage['ctx'].model_id)).fetchone()[0]==1


@pytest.mark.parametrize('damage',('readback-connection-loss','readback-revocation','commit-close-permission-error'))
def test_actual_business_decision_readback_failure_is_unknown_no_retry(admin_url,processing,tmp_path,monkeypatch,damage):
    from dataclasses import replace
    from oracle_brain.operating_model.contracts import canonical_bytes,digest
    from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationAuthorityV1,ConsolidationOutcomeUnknown
    f=processing();aid,m,args,payload=revision(admin_url,f,tmp_path);call_revision(f,aid,args)
    scope=payload['consolidation_core']['assertions'][0]['scope'];h=history_actor(admin_url,f,operation='business-review',scope_hash=digest(scope))
    authority=ConsolidationAuthorityV1(h['url'],binding=replace(adapter(admin_url,f,h).binding,operation='business-review'))
    selected=[{'assertion_id':payload['consolidation_core']['assertions'][0]['assertion_id'],'revision':1}]
    original=psycopg.connect;writes=[]
    class Connection:
        def __init__(self,c):self.c=c;self.wrote=False
        def __getattr__(self,key):return getattr(self.c,key)
        def __enter__(self):self.c.__enter__();return self
        def __exit__(self,*args):
            result=self.c.__exit__(*args)
            if self.wrote and damage=='commit-close-permission-error' and args[0] is None:raise PermissionError('invented close failure AFTER actual commit')
            return result
        def execute(self,query,*args,**kwargs):
            if 'record_processing_model_review_v1(' in str(query):writes.append(query);self.wrote=True
            if 'hosting_processing_review_diff_v1(' in str(query):
                if damage=='readback-connection-loss':raise psycopg.OperationalError('invented lost readonly decision connection')
                with original(admin_url) as c:c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(h['aid'],))
            return self.c.execute(query,*args,**kwargs)
    monkeypatch.setattr(psycopg,'connect',lambda url,*a,**kw:Connection(original(url,*a,**kw)) if url==h['url'] else original(url,*a,**kw))
    with pytest.raises(ConsolidationOutcomeUnknown,match='read-only reconciliation'):
        authority.review_v1(model=m.artifact_id,version=1,content_hash=m.content_hash,decision='accept',scope=scope,assertions=selected,bundle_hash='a'*64,idempotency=uuid4(),deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
    assert len(writes)==1
    with original(admin_url) as c:assert c.execute("SELECT count(*) FROM oracle2.processing_model_events_v1 WHERE artifact_id=%s AND kind='business-accept'",(m.artifact_id,)).fetchone()[0]==1


def test_actual_old_protocol_cannot_append_adopted_model_but_legacy_only_is_unchanged(admin_url,processing,tmp_path):
    """SQL contract fixtures only; semantic/native quality is not inferred."""
    from test_processing_compiler_capabilities import commit
    f=processing();aid,m,args,_=revision(admin_url,f,tmp_path);call_revision(f,aid,args)
    _,extraction,_=persist_extraction(f,tmp_path)
    wire,ordinary,_=bundle(f,kind='processing_qualified_model_v1',dependencies=(('artifact',str(extraction.artifact_id),'1'),));commit(f,wire)
    forbidden=ordinary.model_copy(update={'artifact_id':m.artifact_id,'version':2});wire[0]=Jsonb(forbidden.model_dump(mode='json'))
    with psycopg.connect(admin_url) as c:
        before=c.execute('SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s',(f['workspace'],)).fetchone()[0]
    with pytest.raises(psycopg.errors.InsufficientPrivilege,match='registered temporal model'):
        commit(f,wire)
    with psycopg.connect(admin_url) as c:
        assert c.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s',(f['workspace'],m.artifact_id)).fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s',(f['workspace'],)).fetchone()[0]==before
        assert c.execute('SELECT max(version) FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=%s AND artifact_id=%s',(f['workspace'],m.artifact_id)).fetchone()[0]==1


@pytest.mark.parametrize('damage',('broken-selected-parent','short-selected-path','short-command-window'))
def test_actual_business_named_delegation_cannot_borrow_alternate_scope(admin_url,processing,tmp_path,damage):
    from oracle_brain.operating_model.contracts import digest
    f=processing();aid,m,args,payload=revision(admin_url,f,tmp_path);call_revision(f,aid,args)
    scope_hash=digest(payload['consolidation_core']['assertions'][0]['scope']);h=history_actor(admin_url,f,operation='business-review',scope_hash=scope_hash)
    with psycopg.connect(admin_url) as c:
        membership=c.execute('SELECT membership_appointment FROM oracle2.processing_model_admissions_v1 WHERE admission_id=%s',(h['aid'],)).fetchone()[0]
        named=c.execute('SELECT scope,granted_by,parent_id FROM oracle2.appointments WHERE appointment_id=%s',(membership,)).fetchone()
        c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f['workspace'],h['actor'],*named,f['expiry']))
        if damage=='broken-selected-parent':c.execute('UPDATE oracle2.appointments SET granted_by=%s WHERE appointment_id=%s',(uuid4(),membership))
        elif damage=='short-selected-path':
            limit=datetime.now(timezone.utc)+timedelta(seconds=8)
            c.execute('UPDATE oracle2.appointments SET expires_at=%s WHERE appointment_id=%s',(limit,membership))
        else:
            limit=datetime.now(timezone.utc)+timedelta(seconds=8)
            c.execute('ALTER TABLE oracle2.processing_model_admissions_v1 DISABLE TRIGGER USER')
            c.execute('UPDATE oracle2.processing_model_admissions_v1 SET decision_valid_until=%s WHERE admission_id=%s',(limit,h['aid']))
            c.execute('ALTER TABLE oracle2.processing_model_admissions_v1 ENABLE TRIGGER USER')
    def read():
        with psycopg.connect(h['url']) as c:return c.execute('SELECT oracle2.hosting_processing_review_diff_v1(%s,%s,%s,%s,%s,%s,%s)',(m.artifact_id,1,h['aid'],RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=20))).fetchone()[0]
    if damage=='broken-selected-parent':
        with pytest.raises(psycopg.errors.InsufficientPrivilege,match='exact appointed business delegation'):read()
    else:assert datetime.fromisoformat(read()['validUntil'])<=limit


@pytest.mark.parametrize('damage',('readback-connection-loss','readback-revocation','commit-close-permission-error'))
def test_actual_decision_change_committed_readback_is_unknown_no_retry(admin_url,processing,tmp_path,monkeypatch,damage):
    from dataclasses import replace
    from uuid import UUID
    from oracle_brain.operating_model.contracts import digest
    from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationAuthorityV1,ConsolidationOutcomeUnknown
    f=processing();aid,m,args,payload=revision(admin_url,f,tmp_path);call_revision(f,aid,args)
    scope=payload['consolidation_core']['assertions'][0]['scope'];h=history_actor(admin_url,f,operation='business-review',scope_hash=digest(scope))
    authority=ConsolidationAuthorityV1(h['url'],binding=replace(adapter(admin_url,f,h).binding,operation='business-review'))
    selected=[{'assertion_id':payload['consolidation_core']['assertions'][0]['assertion_id'],'revision':1}]
    event=authority.review_v1(model=m.artifact_id,version=1,content_hash=m.content_hash,decision='accept',scope=scope,assertions=selected,bundle_hash='a'*64,idempotency=uuid4(),deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
    with psycopg.connect(admin_url) as c:
        c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.record_processing_model_decision_change_v1(uuid,text,uuid,uuid,text,text,text,timestamptz),oracle2.hosting_processing_decision_event_v1(uuid,uuid,text,text,text,timestamptz) TO {}').format(sql.Identifier(h['login'])))
    original=psycopg.connect;writes=[]
    class Connection:
        def __init__(self,c):self.c=c;self.wrote=False
        def __getattr__(self,key):return getattr(self.c,key)
        def __enter__(self):self.c.__enter__();return self
        def __exit__(self,*args):
            result=self.c.__exit__(*args)
            if self.wrote and damage=='commit-close-permission-error' and args[0] is None:raise PermissionError('invented close failure AFTER actual commit')
            return result
        def execute(self,query,*args,**kwargs):
            if 'record_processing_model_decision_change_v1(' in str(query):writes.append(query);self.wrote=True
            if 'hosting_processing_decision_event_v1(' in str(query):
                if damage=='readback-connection-loss':raise psycopg.OperationalError('invented lost readonly change connection')
                with original(admin_url) as c:c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(h['aid'],))
            return self.c.execute(query,*args,**kwargs)
    monkeypatch.setattr(psycopg,'connect',lambda url,*a,**kw:Connection(original(url,*a,**kw)) if url==h['url'] else original(url,*a,**kw))
    with pytest.raises(ConsolidationOutcomeUnknown,match='read-only reconciliation'):
        authority.decision_change_v1(target_event=UUID(event['eventId']),action='withdraw',idempotency=uuid4(),deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
    assert len(writes)==1
    with original(admin_url) as c:assert c.execute("SELECT kind,count(*) FROM oracle2.processing_model_events_v1 WHERE artifact_id=%s GROUP BY kind ORDER BY kind",(m.artifact_id,)).fetchall()==[('business-accept',1),('business-withdraw',1)]


@pytest.mark.parametrize('damage',('runtime-denial','callback-cannot-grant'))
def test_actual_optional_runtime_narrowing_cannot_replace_sql_authority(admin_url,sql_qualified_v3,tmp_path,damage):
    from oracle_brain.operating_model.consolidation_ledger_v1 import persist_consolidation_revision_v1,ConsolidationCommitUnknown
    stage=prepared_qualified_model(admin_url,sql_qualified_v3,tmp_path,return_stage=True)
    ledger,authority,q=stage['ledger'],stage['authority'],stage['q'];calls=[]
    def restrict():
        calls.append(1)
        if damage=='runtime-denial':raise PermissionError('invented runtime configuration changed')
        return True  # descriptive return cannot authorize any SQL operation
    if damage=='callback-cannot-grant':
        with psycopg.connect(admin_url) as c:c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1 VALUES(%s,clock_timestamp())',(authority.binding.appointment_id,))
    expected=ConsolidationCommitUnknown if damage=='runtime-denial' else psycopg.errors.InsufficientPrivilege
    with pytest.raises(expected):
        persist_consolidation_revision_v1(ledger,authority,payload=q['payload'],permission_digest=q['admission'].compiler_permission_hash,
            dependencies=tuple(('artifact',str(e.manifest.artifact_id),'1') for e in stage['exts']),idempotency=uuid4(),
            deadline=datetime.now(timezone.utc)+timedelta(seconds=10),_runtime_recheck=restrict)
    assert len(calls)==int(damage=='runtime-denial')
    with psycopg.connect(admin_url) as c:
        assert c.execute('SELECT count(*) FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=%s AND artifact_id=%s',(stage['w'],stage['ctx'].model_id)).fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM oracle2.outbox WHERE workspace_id=%s AND assertion_id=%s',(stage['w'],stage['ctx'].model_id)).fetchone()[0]==0
