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
    if connection is not None:return connection.execute(statement,args).fetchone()
    with psycopg.connect(f['url']) as conn:return conn.execute(statement,args).fetchone()


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
