"""Purpose V2 actual-role/source checks, invented originals only; no live admission."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import hashlib,json
from uuid import uuid4
import psycopg
from psycopg import sql
import pytest
from test_source_processing_qualification import processing
from oracle_brain.operating_model.source_receipts import SourceRef

PHASES={
    'census':('source-census','source_census'),
    'assembly':('operating-audit','operating_audit'),
    'assessment':('independent-source-semantic-acceptance','independent_semantic'),
    'embedding':('source-extraction','projection_embedding'),
}


@pytest.fixture
def purpose_population(admin_url,processing):
    def create(phase='census',profile='source-reader'):
        purpose,name=PHASES[phase];f=processing(profile)
        runtime=hashlib.sha256(('invented-runtime:'+phase).encode()).hexdigest()
        registry=hashlib.sha256(('invented-registry:'+phase+str(f['workspace'])).encode()).hexdigest()
        f.update(phase=phase,purpose=purpose,function=name,runtime=runtime,registry=registry)
        f['binding']=replace(f['binding'],runtime_hash=runtime,source_registry_hash=registry)
        refs=[];grants=[];readings=[]
        with psycopg.connect(admin_url) as conn:
            owner=conn.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
            conn.execute('DELETE FROM oracle2.appointments WHERE appointment_id=%s',(f['extract'],))
            conn.execute('UPDATE oracle2.hosting_role_runtime_admissions SET runtime_hash=%s,registry_hash=%s WHERE role_name=%s',(runtime,registry,f['login']))
            conn.execute('UPDATE oracle2.hosting_role_source_admissions SET runtime_hash=%s,registry_hash=%s WHERE role_name=%s',(runtime,registry,f['login']))
            for index in range(3):
                source=f['source'] if index==0 else uuid4()
                reading=f['reading'] if index==0 else f'Invented original {index}: separate approval responsibility remains unknown.'
                sha=hashlib.sha256(reading.encode()).hexdigest()
                ref=SourceRef(workspace_id=f['workspace'],source_id=source,revision=1,original_sha256='a'*64,reading_sha256=sha,parser_id='b'*64)
                if index:
                    provenance=dict(original_hash='a'*64,content_hash=sha,parser_identity='b'*64,content_type='text/plain',evidence_kind='native_text',page_count=1,review_receipt='c'*64)
                    conn.execute("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) VALUES(%s,%s,%s,'invented.txt','text/plain','draft')",(source,f['workspace'],f['actor']))
                    conn.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) VALUES(%s,%s,%s,%s,'unaccepted generated interpretation','draft')",(uuid4(),source,f['workspace'],f['actor']))
                    for block,(kind,text) in enumerate([('original',reading),('original-metadata',json.dumps(provenance))]):
                        conn.execute('INSERT INTO oracle2.source_blocks VALUES(%s,%s,%s,%s,%s,%s,0,%s)',(uuid4(),source,f['workspace'],block,kind,text,len(text)))
                    conn.execute('INSERT INTO oracle2.hosting_role_source_admissions VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s)',(f['login'],f['workspace'],source,f['actor'],'a'*64,sha,'b'*64,runtime,registry,f['expiry']))
                    conn.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f['workspace'],f['actor'],'source-read:'+str(source),owner,f['root'],f['expiry']))
                grant=uuid4()
                conn.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(grant,f['workspace'],f['actor'],purpose+':'+str(source),owner,f['root'],f['expiry']))
                refs.append(ref);grants.append(grant);readings.append(reading)
        f.update(refs=tuple(refs),grants=tuple(grants),readings=tuple(readings))
        return f
    return create


def query(f,ref,*,raw=False,connection=None):
    suffix='receipt' if raw else 'identity'
    statement=f'SELECT * FROM oracle2.hosting_{f["function"]}_{suffix}_v2(%s,%s,%s,%s,%s)'
    args=(ref.workspace_id,ref.source_id,f['actor'],f['runtime'],f['registry'])
    if connection is not None:
        connection.execute("SET LOCAL statement_timeout='5s'")
        return connection.execute(statement,args).fetchone()
    with psycopg.connect(f['url']) as conn:
        conn.execute("SET LOCAL statement_timeout='5s'")
        return conn.execute(statement,args).fetchone()


@pytest.mark.parametrize('phase',['census','assembly','assessment'])
def test_named_purpose_actual_reader_requires_new_leaf_not_extraction(admin_url,purpose_population,phase):
    f=purpose_population(phase)
    for ref,reading in zip(f['refs'],f['readings']):assert query(f,ref,raw=True)[4]==reading
    with psycopg.connect(f['url']) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM oracle2.hosting_processing_source_receipt(%s,%s,%s,%s,%s)',
                (f['workspace'],f['source'],f['actor'],f['runtime'],f['registry']))
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT DISTINCT status FROM oracle2.drafts WHERE workspace_id=%s',(f['workspace'],)).fetchall()==[('draft',)]
        assert conn.execute('SELECT count(*) FROM oracle2.reviews WHERE workspace_id=%s',(f['workspace'],)).fetchone()[0]==0


@pytest.mark.parametrize('phase',['census','assembly','assessment'])
def test_gateway_gets_only_own_current_purpose_identity(purpose_population,phase):
    f=purpose_population(phase,'gateway-metadata')
    for ref in f['refs']:
        row=query(f,ref);assert len(row)==6 and row[:4]==(ref.revision,ref.original_sha256,ref.reading_sha256,ref.parser_id)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):query(f,ref,raw=True)


def test_embedding_gateway_metadata_cannot_borrow_v1_raw_capability(purpose_population):
    f=purpose_population('embedding','gateway-metadata');assert query(f,f['refs'][0])
    with psycopg.connect(f['url']) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM oracle2.hosting_processing_source_receipt(%s,%s,%s,%s,%s)',
                (f['workspace'],f['source'],f['actor'],f['runtime'],f['registry']))


@pytest.mark.parametrize('profile',['source-reader','candidate-compiler','documentary-executor'])
def test_embedding_identity_function_denies_nonmetadata_role(purpose_population,profile):
    f=purpose_population('embedding',profile)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):query(f,f['refs'][0])


@pytest.mark.parametrize('mutation',['revoked','expired','wrong-grantor','wrong-parent-scope','withdrawn','changed-reading','extra-role'])
def test_purpose_actual_current_revocation_custody_role_denials(admin_url,purpose_population,mutation):
    f=purpose_population();ref=f['refs'][2]
    with psycopg.connect(admin_url) as conn:
        if mutation=='revoked':conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f['grants'][2],))
        elif mutation=='expired':conn.execute("UPDATE oracle2.appointments SET expires_at=clock_timestamp()-interval '1 second' WHERE appointment_id=%s",(f['grants'][2],))
        elif mutation=='wrong-grantor':conn.execute('UPDATE oracle2.appointments SET granted_by=%s WHERE appointment_id=%s',(uuid4(),f['grants'][2]))
        elif mutation=='wrong-parent-scope':conn.execute("UPDATE oracle2.appointments SET scope='unrelated' WHERE appointment_id=%s",(f['root'],))
        elif mutation=='withdrawn':conn.execute("UPDATE oracle2.drafts SET status='withdrawn' WHERE source_id=%s",(ref.source_id,))
        elif mutation=='changed-reading':conn.execute("UPDATE oracle2.source_blocks SET text='changed invented body' WHERE source_id=%s AND kind='original'",(ref.source_id,))
        else:conn.execute(sql.SQL('GRANT pg_monitor TO {}').format(sql.Identifier(f['login'])))
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):query(f,ref,raw=True)
    finally:
        if mutation=='extra-role':
            with psycopg.connect(admin_url) as conn:conn.execute(sql.SQL('REVOKE pg_monitor FROM {}').format(sql.Identifier(f['login'])))


def test_private_purpose_validator_not_public_application_capability(purpose_population):
    f=purpose_population()
    with psycopg.connect(f['url']) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM oracle2._purpose_source_v2(%s,%s,%s,%s,%s,%s,true)',
                (f['workspace'],f['source'],f['actor'],f['runtime'],f['registry'],f['purpose']))


def context(f,*,caller_kind='provider',expiry=None):
    from oracle_brain.operating_model.contracts import digest
    from oracle_brain.operating_model.purpose_context import (
        PHASE_CONTRACTS,PurposeDispatchV2,PurposeRunDescriptorV2,PurposeMetadataProjectionV2,source_population_digest)
    from oracle_brain.operating_model.authority_adapter import PurposeSourceBindingV2,PurposeSourceResolverV2
    purpose,operation,model=PHASE_CONTRACTS[f['phase']]
    dispatch=PurposeDispatchV2(dispatch_id=uuid4(),source_refs=f['refs'],model=model,
        **{name:'d'*64 for name in ('job_hash','request_hash','permission_hash','context_hash',
        'processing_request_hash','account_policy_hash','terms_hash','pricing_hash','register_hash',
        'approvals_hash','budget_identity_hash','ledger_registry_hash','key_coverage_hash')})
    provider=f['login'] if caller_kind=='provider' else f['login']+'_provider'
    descriptor=PurposeRunDescriptorV2(run_id=uuid4(),workspace_id=f['workspace'],actor_id=f['actor'],
        provider_login=provider,worker_uri='spiffe://oracle/purpose-worker',phase=f['phase'],purpose=purpose,operation=operation,
        runtime_hash=f['runtime'],source_registry_hash=f['registry'],parent_registry_sha256='1'*64,
        population_admission_sha256='2'*64,phase_registry_sha256='3'*64,population_digest=source_population_digest(f['refs']),
        source_refs=f['refs'],dispatches=(dispatch,),issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=expiry or f['expiry'])
    projection=PurposeMetadataProjectionV2(descriptor=descriptor,descriptor_sha256=digest(descriptor.model_dump(mode='json')))
    binding=PurposeSourceBindingV2(source=f['binding'],phase=f['phase'],purpose=purpose,operation=operation,
        expected_provider_login=provider,caller_kind=caller_kind,source_refs=f['refs'],population_digest=descriptor.population_digest,
        descriptor_sha256=projection.descriptor_sha256,parent_registry_sha256=descriptor.parent_registry_sha256,
        population_admission_sha256=descriptor.population_admission_sha256,phase_registry_sha256=descriptor.phase_registry_sha256,
        projection_sha256=digest(projection.model_dump(mode='json')))
    return PurposeSourceResolverV2(f['url'],binding=binding),descriptor,dispatch


@pytest.mark.parametrize('phase',['census','assembly','assessment'])
def test_v2_resolver_checks_all_three_sources_before_raw_population(purpose_population,phase):
    f=purpose_population(phase);adapter,descriptor,dispatch=context(f)
    assert tuple(r.reading for r in adapter.read_population())==f['readings']
    with adapter.hold(descriptor,dispatch) as proof:
        assert proof.source_refs==f['refs'] and proof.actual_caller_login==f['login']
        assert proof.admitted_provider_login==f['login'] and proof.session_role==f['login']
        assert proof.checked_at<proof.expires_at<=descriptor.expires_at
    assert not hasattr(adapter,'current_for_processing')


def test_v2_missing_third_grant_never_starts_body_read(admin_url,purpose_population,monkeypatch):
    f=purpose_population();adapter,descriptor,dispatch=context(f)
    with psycopg.connect(admin_url) as conn:conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f['grants'][2],))
    actual=adapter._population;calls=[]
    def observed(conn,*,raw=False):
        calls.append(raw)
        return actual(conn,raw=raw)
    monkeypatch.setattr(adapter,'_population',observed)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):adapter.read_population()
    assert calls==[False]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with adapter.hold(descriptor,dispatch):pass


@pytest.mark.parametrize('phase,kind',[('census','gateway'),('assembly','gateway'),('assessment','gateway'),('embedding','provider')])
def test_actual_gateway_and_embedding_proof_preserves_distinct_provider_login(purpose_population,phase,kind):
    from oracle_brain.operating_model.purpose_context import verify_purpose_authority_proof_v2
    f=purpose_population(phase,'gateway-metadata');adapter,d,j=context(f,caller_kind=kind)
    with adapter.hold(d,j) as proof:
        assert proof.actual_caller_login==f['login']
        assert (proof.admitted_provider_login==f['login'])==(kind=='provider')
        verify_purpose_authority_proof_v2(proof,d,j,projection_sha256=adapter.binding.projection_sha256,
            actual_caller_login=f['login'],profile='gateway-metadata',now=datetime.now(timezone.utc))
    with pytest.raises(PermissionError):adapter.read_population()


@pytest.mark.parametrize('field,value',[('actor_id',uuid4()),('provider_login','different_provider'),('parent_registry_sha256','f'*64),('phase_registry_sha256','f'*64)])
def test_v2_hold_never_blesses_changed_descriptor(purpose_population,field,value):
    f=purpose_population();adapter,d,j=context(f)
    with pytest.raises(PermissionError):
        with adapter.hold(d.model_copy(update={field:value}),j):pass


def test_v2_omission_and_reorder_cannot_change_full_admitted_parent_population(purpose_population):
    f=purpose_population();adapter,d,j=context(f)
    for refs in (f['refs'][:2],tuple(reversed(f['refs']))):
        with pytest.raises(PermissionError):
            with adapter.hold(d.model_copy(update={'source_refs':refs}),j):pass
        with pytest.raises(PermissionError):
            with adapter.hold(d,j.model_copy(update={'source_refs':refs})):pass


def test_v2_expiry_while_hold_is_open_denies_before_commit(purpose_population):
    import time
    f=purpose_population();adapter,d,j=context(f,expiry=datetime.now(timezone.utc)+timedelta(seconds=.2))
    with pytest.raises(PermissionError):
        with adapter.hold(d,j):time.sleep(.25)


def test_new_purpose_does_not_accept_extraction_leaf_or_root_shortcut(admin_url,purpose_population):
    f=purpose_population();ref=f['refs'][0]
    with psycopg.connect(admin_url) as conn:
        conn.execute('UPDATE oracle2.appointments SET scope=%s WHERE appointment_id=%s',('source-extraction:'+str(ref.source_id),f['grants'][0]))
        conn.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by) VALUES(%s,%s,%s,'root',%s)",(uuid4(),f['workspace'],f['actor'],uuid4()))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):query(f,ref,raw=True)


def test_v2_membership_drift_during_hold_denies_current_caller(admin_url,purpose_population):
    f=purpose_population('census','gateway-metadata');adapter,d,j=context(f,caller_kind='gateway')
    try:
        with pytest.raises(PermissionError):
            with adapter.hold(d,j):
                with psycopg.connect(admin_url) as conn:conn.execute(sql.SQL('GRANT pg_monitor TO {}').format(sql.Identifier(f['login'])))
    finally:
        with psycopg.connect(admin_url) as conn:conn.execute(sql.SQL('REVOKE pg_monitor FROM {}').format(sql.Identifier(f['login'])))


@pytest.mark.parametrize('signature',[
    'oracle2._purpose_source_v2(uuid,uuid,uuid,text,text,text,boolean)',
    'oracle2.hosting_source_census_receipt_v2(uuid,uuid,uuid,text,text)',
    'oracle2.hosting_projection_embedding_identity_v2(uuid,uuid,uuid,text,text)',
])
def test_v2_adapter_rechecks_private_and_public_acl_before_access(admin_url,purpose_population,signature):
    f=purpose_population();adapter,_,_=context(f)
    with psycopg.connect(admin_url) as conn:conn.execute('GRANT EXECUTE ON FUNCTION '+signature+' TO PUBLIC')
    try:
        with pytest.raises(PermissionError,match='ACL'):adapter.identity(f['workspace'],f['source'])
    finally:
        with psycopg.connect(admin_url) as conn:conn.execute('REVOKE EXECUTE ON FUNCTION '+signature+' FROM PUBLIC')
    assert adapter.identity(f['workspace'],f['source'])==f['refs'][0]


def test_v2_fixed_function_configuration_and_owner_are_not_discovered_as_authority(admin_url,purpose_population):
    f=purpose_population();adapter,_,_=context(f)
    signature='oracle2.hosting_source_census_receipt_v2(uuid,uuid,uuid,text,text)'
    with psycopg.connect(admin_url) as conn:
        original=conn.execute('SELECT pg_get_functiondef(to_regprocedure(%s))',(signature,)).fetchone()[0]
        conn.execute('ALTER FUNCTION '+signature+' SET search_path=public,oracle2')
    try:
        with pytest.raises(PermissionError,match='owner/config'):adapter.identity(f['workspace'],f['source'])
    finally:
        with psycopg.connect(admin_url) as conn:conn.execute(original)
    assert adapter.identity(f['workspace'],f['source'])==f['refs'][0]


@pytest.mark.parametrize('mutation',['runtime-expired','source-expired','root-revoked','read-revoked','wrong-actor','wrong-registry','duplicate-original'])
def test_v2_additional_actual_source_and_admission_denials(admin_url,purpose_population,mutation):
    f=purpose_population();ref=f['refs'][1]
    with psycopg.connect(admin_url) as conn:
        if mutation=='runtime-expired':conn.execute("UPDATE oracle2.hosting_role_runtime_admissions SET expires_at=clock_timestamp()-interval '1 second' WHERE role_name=%s",(f['login'],))
        elif mutation=='source-expired':conn.execute("UPDATE oracle2.hosting_role_source_admissions SET expires_at=clock_timestamp()-interval '1 second' WHERE role_name=%s AND source_id=%s",(f['login'],ref.source_id))
        elif mutation=='root-revoked':conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f['root'],))
        elif mutation=='read-revoked':conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE actor_id=%s AND scope=%s',(f['actor'],'source-read:'+str(ref.source_id)))
        elif mutation=='wrong-actor':conn.execute('UPDATE oracle2.hosting_role_source_admissions SET principal_id=%s WHERE role_name=%s AND source_id=%s',(uuid4(),f['login'],ref.source_id))
        elif mutation=='wrong-registry':conn.execute("UPDATE oracle2.hosting_role_runtime_admissions SET registry_hash=%s WHERE role_name=%s",('f'*64,f['login']))
        else:conn.execute('INSERT INTO oracle2.source_blocks SELECT %s,source_id,workspace_id,block_index+50,kind,text,span_start,span_end FROM oracle2.source_blocks WHERE source_id=%s AND kind=%s',(uuid4(),ref.source_id,'original'))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):query(f,ref,raw=True)


def test_v2_actual_set_role_proof_distinguishes_original_login_and_effective_group(purpose_population):
    f=purpose_population();adapter,d,j=context(f)
    with psycopg.connect(f['url']) as conn:
        conn.execute('SET LOCAL ROLE oracle2_source_reader')
        with adapter.hold(d,j,connection=conn) as proof:
            assert proof.actual_caller_login==f['login'] and proof.session_role=='oracle2_source_reader'


def test_purpose_original_reader_has_no_compiler_write_capability(purpose_population):
    f=purpose_population()
    with psycopg.connect(f['url']) as conn:
        assert conn.execute("SELECT has_function_privilege(current_user,'oracle2.commit_processing_candidate(jsonb,bytea,bytea,bytea,jsonb,text,text,timestamptz)','EXECUTE')").fetchone()==(False,)


def seed_embedding_metadata(admin_url,f):
    """Admin seeds invented relational identity only, never semantic admission."""
    from oracle_brain.operating_model.contracts import ArtifactManifest,digest
    from psycopg.types.json import Jsonb
    def insert(conn,kind,refs,parents=()):
        artifact=uuid4();deps=tuple(sorted([('source',str(r.source_id),str(r.revision)) for r in refs]+[('artifact',str(p.artifact_id),str(p.version)) for p in parents]))
        m=ArtifactManifest(workspace_id=f['workspace'],artifact_id=artifact,version=1,kind=kind,state='ready',
            input_digest='a'*64,source_digest='b'*64,permission_digest='c'*64,compiler_digest='d'*64,
            dependency_digest=digest({'dependencies':deps}),content_hash='e'*64,private_object_key='PRIVATE_NEVER_RETURNED')
        columns=tuple(k for k in type(m).model_fields if k!='schema_version')
        conn.execute(sql.SQL('INSERT INTO oracle2.artifact_manifests ({},manifest) VALUES ({},%s)').format(
            sql.SQL(',').join(map(sql.Identifier,columns)),sql.SQL(',').join(sql.Placeholder() for _ in columns)),
            tuple(getattr(m,k) for k in columns)+(Jsonb(m.model_dump(mode='json')),))
        for kind_,id_,revision in deps:
            conn.execute('INSERT INTO oracle2.artifact_dependencies VALUES(%s,%s,1,%s,%s,%s)',(f['workspace'],artifact,kind_,id_,revision))
        return m
    with psycopg.connect(admin_url) as conn:
        extractions=tuple(insert(conn,'processing_extraction_v1',(r,)) for r in f['refs'])
        model=insert(conn,'processing_qualified_model_v1',f['refs'],extractions)
    return model,extractions


def test_embedding_qualified_seal_real_gateway_no_private_body(admin_url,purpose_population):
    from oracle_brain.operating_model.contracts import ProcessingQualifiedProjectionSealV2,digest
    f=purpose_population('embedding','gateway-metadata');res,_,_=context(f)
    model,extractions=seed_embedding_metadata(admin_url,f)
    seal=res.embedding_eligibility_seal(f['workspace'],model.artifact_id,1)
    assert type(seal) is ProcessingQualifiedProjectionSealV2 and seal.manifest_hash==digest(model.model_dump(mode='json'))
    assert seal.source_refs==f['refs'] and len(seal.extraction_seals)==3
    assert {s.manifest_hash for s in seal.extraction_seals}=={digest(m.model_dump(mode='json')) for m in extractions}
    assert 'PRIVATE_NEVER_RETURNED' not in seal.model_dump_json() and 'private_object_key' not in seal.model_dump_json()
    with psycopg.connect(f['url']) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM oracle2.hosting_processing_artifact(%s,%s,1,%s,%s,%s)',(f['workspace'],model.artifact_id,f['actor'],f['runtime'],f['registry']))
    with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):
        res.embedding_eligibility_seal(f['workspace'],extractions[0].artifact_id,1)


@pytest.mark.parametrize('mutation',['read','purpose','withdraw','dependency','invalidation','runtime'])
def test_embedding_seal_rechecks_actual_current_authority(admin_url,purpose_population,mutation):
    f=purpose_population('embedding','gateway-metadata');res,_,_=context(f)
    model,_=seed_embedding_metadata(admin_url,f)
    assert res.embedding_eligibility_seal(f['workspace'],model.artifact_id,1)
    with psycopg.connect(admin_url) as conn:
        if mutation in {'read','purpose'}:
            scope=('source-read' if mutation=='read' else 'source-extraction')+':'+str(f['refs'][2].source_id)
            conn.execute('UPDATE oracle2.appointments SET revoked_at=now() WHERE workspace_id=%s AND actor_id=%s AND scope=%s',(f['workspace'],f['actor'],scope))
        elif mutation=='withdraw':conn.execute("UPDATE oracle2.drafts SET status='withdrawn' WHERE source_id=%s",(f['refs'][2].source_id,))
        elif mutation=='dependency':conn.execute("INSERT INTO oracle2.artifact_dependencies VALUES(%s,%s,1,'source',%s,'99')",(f['workspace'],model.artifact_id,str(f['refs'][2].source_id)))
        elif mutation=='invalidation':conn.execute('INSERT INTO oracle2.artifact_invalidations(workspace_id,artifact_id,version,reason,event_id) VALUES(%s,%s,1,%s,%s)',(f['workspace'],model.artifact_id,'invented test invalidation',uuid4()))
        else:conn.execute("UPDATE oracle2.hosting_role_runtime_admissions SET expires_at=now()-interval '1 second' WHERE role_name=%s",(f['login'],))
    with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):
        res.embedding_eligibility_seal(f['workspace'],model.artifact_id,1)


def test_direct_purpose_getter_requires_prearmed_statement_deadline(purpose_population):
    f=purpose_population();r=f['refs'][0]
    with psycopg.connect(f['url']) as conn:
        conn.execute("SET LOCAL statement_timeout='0'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM oracle2.hosting_source_census_identity_v2(%s,%s,%s,%s,%s)',
                (r.workspace_id,r.source_id,f['actor'],f['runtime'],f['registry']))


@pytest.mark.parametrize('statement,lock,error',[('300ms','100ms',psycopg.errors.LockNotAvailable),('100ms','300ms',psycopg.errors.QueryCanceled)])
def test_actual_tighter_caller_deadline_aborts_held_workspace(admin_url,purpose_population,statement,lock,error):
    from concurrent.futures import ThreadPoolExecutor
    f=purpose_population();r=f['refs'][0]
    def read():
        with psycopg.connect(f['url']) as conn:
            conn.execute('SELECT set_config(%s,%s,true),set_config(%s,%s,true)',('statement_timeout',statement,'lock_timeout',lock))
            conn.execute('SELECT * FROM oracle2.hosting_source_census_identity_v2(%s,%s,%s,%s,%s)',
                (r.workspace_id,r.source_id,f['actor'],f['runtime'],f['registry']))
    with psycopg.connect(admin_url) as owner:
        owner.execute("SELECT pg_advisory_xact_lock(hashtext('oracle2-authz:'||%s::text))",(f['workspace'],))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(read)
            with pytest.raises(error):future.result(timeout=2)
    assert query(f,r)


def test_v2_adapter_preserves_tighter_preexisting_statement_deadline(purpose_population):
    f=purpose_population();adapter,_,_=context(f)
    with psycopg.connect(f['url']) as conn:
        conn.execute("SET LOCAL statement_timeout='150ms'")
        adapter._check(conn)
        assert conn.execute("SHOW statement_timeout").fetchone()[0]=='150ms'
