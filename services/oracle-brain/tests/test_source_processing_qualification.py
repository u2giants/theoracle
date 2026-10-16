"""Actual isolated PostgreSQL role/custody checks; all source text is invented."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from oracle_brain.operating_model.authority_adapter import (
    PostgresSources, ProcessingSourceBinding, ProcessingSourceResolver,
)
from oracle_brain.operating_model.source_binding import SourceRoleBinding

RUNTIME='d'*64
REGISTRY='e'*64


@pytest.fixture
def processing(admin_url):
    def create(profile='candidate-compiler'):
        workspace,source,actor,owner,root,read,extract=(uuid4() for _ in range(7))
        login='processing_'+uuid4().hex[:12]
        reading='Invented source: approval ownership is unknown.'
        reading_hash=hashlib.sha256(reading.encode()).hexdigest()
        provenance=dict(original_hash='a'*64,content_hash=reading_hash,parser_identity='b'*64,
                        content_type='text/plain',evidence_kind='native_text',page_count=1,review_receipt='c'*64)
        expiry=datetime.now(timezone.utc)+timedelta(minutes=20)
        with psycopg.connect(admin_url) as conn:
            owner_role=conn.execute("SELECT r.rolname FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname='oracle2'").fetchone()[0]
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-test-only')))
            conn.execute(sql.SQL('GRANT {} TO {}').format(sql.Identifier('oracle2_'+profile.replace('-','_')),sql.Identifier(login)))
            conn.execute("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) VALUES(%s,%s,%s,'invented.txt','text/plain','draft')",(source,workspace,actor))
            conn.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) VALUES(%s,%s,%s,%s,'unaccepted generated draft','draft')",(uuid4(),source,workspace,actor))
            for index,(kind,text) in enumerate([('original',reading),('original-metadata',json.dumps(provenance))]):
                conn.execute('INSERT INTO oracle2.source_blocks VALUES(%s,%s,%s,%s,%s,%s,0,%s)',(uuid4(),source,workspace,index,kind,text,len(text)))
            conn.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by) VALUES(%s,%s,%s,'root',%s)",(root,workspace,owner,uuid4()))
            for appointment,scope in [(read,'source-read:'),(extract,'source-extraction:')]:
                conn.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(appointment,workspace,actor,scope+str(source),owner,root,expiry))
            conn.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,RUNTIME,REGISTRY,expiry))
            conn.execute('INSERT INTO oracle2.hosting_role_source_admissions VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s)',(login,workspace,source,actor,'a'*64,reading_hash,'b'*64,RUNTIME,REGISTRY,expiry))
        url=psycopg.conninfo.make_conninfo(admin_url,user=login,password='invented-test-only')
        binding=ProcessingSourceBinding(RUNTIME,REGISTRY,owner_role,login,actor,profile,expiry,synthetic=False)
        return dict(url=url,workspace=workspace,source=source,actor=actor,root=root,read=read,extract=extract,
                    login=login,binding=binding,reading=reading,expiry=expiry)
    return create


def resolver(fixture):
    return ProcessingSourceResolver(fixture['url'],binding=fixture['binding'])


def test_draft_original_qualified_without_accepting_generated_claims(admin_url,processing):
    f=processing(); receipt=resolver(f).current_for_processing(f['workspace'],f['source'])
    assert receipt.reading==f['reading'] and receipt.ref.revision==1
    with psycopg.connect(admin_url) as conn:
        assert conn.execute('SELECT status FROM oracle2.drafts WHERE source_id=%s',(f['source'],)).fetchone()==('draft',)
        assert conn.execute('SELECT count(*) FROM oracle2.reviews WHERE workspace_id=%s',(f['workspace'],)).fetchone()==(0,)
    with pytest.raises(PermissionError):
        PostgresSources(f['url'],source_binding=SourceRoleBinding(RUNTIME,REGISTRY)).current(f['workspace'],f['source'])


@pytest.mark.parametrize('profile',['source-reader','candidate-compiler'])
def test_actual_raw_getter_roles(processing,profile):
    f=processing(profile)
    assert resolver(f).current_for_processing(f['workspace'],f['source']).reading==f['reading']


@pytest.mark.parametrize('profile',['documentary-executor','gateway-metadata'])
def test_metadata_role_has_no_raw_processing_capability(processing,profile):
    f=processing(profile); adapter=resolver(f)
    assert adapter.identity(f['workspace'],f['source']).source_id==f['source']
    with pytest.raises(PermissionError):adapter.current_for_processing(f['workspace'],f['source'])
    with psycopg.connect(f['url']) as conn:
        # Old confirmed serving RLS remains; an unconfirmed original is not made directly visible.
        try:
            assert conn.execute("SELECT text FROM oracle2.source_blocks WHERE source_id=%s",(f['source'],)).fetchall()==[]
        except psycopg.errors.InsufficientPrivilege:
            conn.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM oracle2.hosting_processing_source_receipt(%s,%s,%s,%s,%s)',(f['workspace'],f['source'],f['actor'],RUNTIME,REGISTRY))


@pytest.mark.parametrize('scope',['read','extract','root'])
@pytest.mark.parametrize('profile',['candidate-compiler','gateway-metadata'])
def test_current_revocation_denies_each_processing_scope(admin_url,processing,scope,profile):
    f=processing(profile); adapter=resolver(f)
    with psycopg.connect(admin_url) as conn:conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f[scope],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):adapter.identity(f['workspace'],f['source'])


def test_documentary_metadata_does_not_invent_extraction_authority(admin_url,processing):
    f=processing('documentary-executor')
    with psycopg.connect(admin_url) as conn:conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f['extract'],))
    assert resolver(f).identity(f['workspace'],f['source']).source_id==f['source']


@pytest.mark.parametrize('field,value',[
    ('runtime_hash','0'*64),('source_registry_hash','0'*64),('expected_owner_role','incorrect_owner'),
    ('expected_session_role','incorrect_session'),('principal',None),('profile','documentary-executor'),
])
def test_binding_cannot_choose_other_actor_owner_or_weaker_profile(processing,field,value):
    f=processing('gateway-metadata')
    with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):
        binding=replace(f['binding'],**{field:uuid4() if field=='principal' else value})
        ProcessingSourceResolver(f['url'],binding=binding).identity(f['workspace'],f['source'])


@pytest.mark.parametrize('mutation',[
    "UPDATE oracle2.drafts SET status='withdrawn' WHERE source_id=%s",
    'UPDATE oracle2.sources SET revision=2 WHERE source_id=%s',
    "UPDATE oracle2.source_blocks SET text='altered' WHERE source_id=%s AND kind='original'",
    "UPDATE oracle2.source_blocks SET text='{}' WHERE source_id=%s AND kind='original-metadata'",
    "UPDATE oracle2.hosting_role_source_admissions SET parser_id=repeat('f',64) WHERE source_id=%s",
    "UPDATE oracle2.hosting_role_source_admissions SET expires_at=clock_timestamp()-interval '1 second' WHERE source_id=%s",
])
def test_source_status_revision_and_custody_changes_deny(admin_url,processing,mutation):
    f=processing(); adapter=resolver(f)
    with psycopg.connect(admin_url) as conn:conn.execute(mutation,(f['source'],))
    with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):
        adapter.current_for_processing(f['workspace'],f['source'])


def test_metadata_role_must_have_own_source_admission(admin_url,processing):
    f=processing('gateway-metadata');adapter=resolver(f)
    with psycopg.connect(admin_url) as conn:conn.execute('DELETE FROM oracle2.hosting_role_source_admissions WHERE role_name=%s',(f['login'],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):adapter.identity(f['workspace'],f['source'])


def test_source_identity_change_rejected_by_exact_manifest(admin_url,processing):
    f=processing();adapter=resolver(f); receipt=adapter.current_for_processing(f['workspace'],f['source'])
    with pytest.raises(PermissionError):adapter.authorize_refs((receipt.ref,),f['workspace'],uuid4())
    with pytest.raises(PermissionError):adapter.authorize_refs((receipt.ref,),uuid4(),f['actor'])


def test_authority_check_reuses_enclosing_connection_without_deadlock(processing):
    f=processing(); adapter=resolver(f)
    with psycopg.connect(f['url']) as conn:
        conn.execute("SET LOCAL statement_timeout='2s'")
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('oracle2-authz:'+str(f['workspace']),))
        assert adapter.current_for_processing(f['workspace'],f['source'],connection=conn).reading==f['reading']


def test_old_compiler_insert_policy_still_denies_unconfirmed_original(processing):
    f=processing(); receipt=resolver(f).current_for_processing(f['workspace'],f['source'])
    with psycopg.connect(f['url']) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('INSERT INTO oracle2.operating_model_source_receipts VALUES(%s,%s,1,%s,%s,%s,%s)',
                         (f['workspace'],f['source'],receipt.ref.original_sha256,receipt.ref.reading_sha256,receipt.ref.parser_id,Jsonb(receipt.model_dump(mode='json'))))


def test_private_processing_helper_not_executable_by_application(processing):
    f=processing()
    with psycopg.connect(f['url']) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM oracle2._processing_source(%s,%s,%s,%s,%s,true)',
                         (f['workspace'],f['source'],f['actor'],RUNTIME,REGISTRY))


@pytest.mark.parametrize('signature',[
    'oracle2.hosting_processing_source_receipt(uuid,uuid,uuid,text,text)',
    'oracle2.hosting_current_source_identity(uuid,uuid,uuid,text,text)',
    'oracle2.hosting_source_visible(uuid,uuid)',
])
def test_acl_drift_is_rechecked_after_construction(admin_url,processing,signature):
    f=processing(); adapter=resolver(f)
    with psycopg.connect(admin_url) as conn:conn.execute('GRANT EXECUTE ON FUNCTION '+signature+' TO PUBLIC')
    try:
        with pytest.raises(PermissionError,match='ACL'):adapter.identity(f['workspace'],f['source'])
    finally:
        with psycopg.connect(admin_url) as conn:conn.execute('REVOKE EXECUTE ON FUNCTION '+signature+' FROM PUBLIC')


def test_owner_membership_and_extra_group_are_not_a_role_escape(admin_url,processing):
    f=processing()
    with psycopg.connect(admin_url) as conn:
        conn.execute(sql.SQL('GRANT oracle2_documentary_executor TO {}').format(sql.Identifier(f['login'])))
    with pytest.raises(PermissionError,match='exclusive'):resolver(f)
    with psycopg.connect(admin_url) as conn:
        conn.execute(sql.SQL('REVOKE oracle2_documentary_executor FROM {}').format(sql.Identifier(f['login'])))
        conn.execute(sql.SQL('GRANT {} TO {}').format(sql.Identifier(f['binding'].expected_owner_role),sql.Identifier(f['login'])))
    try:
        with pytest.raises(PermissionError,match='owner'):resolver(f)
    finally:
        with psycopg.connect(admin_url) as conn:
            conn.execute(sql.SQL('REVOKE {} FROM {}').format(sql.Identifier(f['binding'].expected_owner_role),sql.Identifier(f['login'])))


@pytest.mark.parametrize('field,value',[('review_receipt',123),('page_count',True),('page_count','1'),('extra',True)])
def test_malformed_provenance_cannot_pass_metadata_validation(admin_url,processing,field,value):
    f=processing('gateway-metadata');adapter=resolver(f)
    with psycopg.connect(admin_url) as conn:
        raw=conn.execute("SELECT text FROM oracle2.source_blocks WHERE source_id=%s AND kind='original-metadata'",(f['source'],)).fetchone()[0]
        provenance=json.loads(raw);provenance[field]=value
        conn.execute("UPDATE oracle2.source_blocks SET text=%s WHERE source_id=%s AND kind='original-metadata'",(json.dumps(provenance),f['source']))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):adapter.identity(f['workspace'],f['source'])


@pytest.mark.parametrize('kind',['original','original-metadata'])
def test_duplicate_original_or_metadata_is_denied(admin_url,processing,kind):
    f=processing();adapter=resolver(f)
    with psycopg.connect(admin_url) as conn:
        conn.execute('INSERT INTO oracle2.source_blocks SELECT %s,source_id,workspace_id,99,kind,text,span_start,span_end FROM oracle2.source_blocks WHERE source_id=%s AND kind=%s',(uuid4(),f['source'],kind))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):adapter.identity(f['workspace'],f['source'])


def test_grantor_identity_and_parent_scope_are_not_ignored(admin_url,processing):
    f=processing();adapter=resolver(f)
    with psycopg.connect(admin_url) as conn:
        conn.execute('UPDATE oracle2.appointments SET granted_by=%s WHERE appointment_id=%s',(uuid4(),f['extract']))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):adapter.identity(f['workspace'],f['source'])


def test_plaintext_and_wrong_certificate_fail_closed(processing,tmp_path):
    f=processing()
    with pytest.raises((PermissionError,psycopg.OperationalError)):
        ProcessingSourceResolver(psycopg.conninfo.make_conninfo(f['url'],sslmode='disable'),binding=f['binding'])
    bad=tmp_path/'wrong-ca.pem';bad.write_text('not a certificate')
    with pytest.raises(psycopg.OperationalError):
        ProcessingSourceResolver(psycopg.conninfo.make_conninfo(f['url'],sslrootcert=str(bad)),binding=f['binding'])


def test_actual_clock_expires_grant_after_transaction_start(admin_url,processing):
    f=processing();adapter=resolver(f)
    with psycopg.connect(f['url']) as conn:
        start=conn.execute('SELECT now()').fetchone()[0]
        with psycopg.connect(admin_url) as admin:
            expiry=admin.execute("UPDATE oracle2.appointments SET expires_at=clock_timestamp()+interval '0.15 second' WHERE appointment_id=%s RETURNING expires_at",(f['read'],)).fetchone()[0]
        assert start<expiry
        conn.execute('SELECT pg_sleep(0.2)')
        # Transaction-start now() remains earlier than expiry; actual clock must deny.
        assert conn.execute('SELECT now()').fetchone()[0]<expiry
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            adapter.identity(f['workspace'],f['source'],connection=conn)


@pytest.mark.parametrize('kind',['original','original-metadata'])
def test_duplicate_insert_cannot_race_qualified_snapshot(admin_url,processing,kind):
    f=processing();adapter=resolver(f)
    with psycopg.connect(f['url']) as held:
        assert adapter.identity(f['workspace'],f['source'],connection=held).source_id==f['source']
        with psycopg.connect(admin_url) as contender:
            contender.execute("SET LOCAL lock_timeout='150ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                contender.execute('INSERT INTO oracle2.source_blocks SELECT %s,source_id,workspace_id,99,kind,text,span_start,span_end FROM oracle2.source_blocks WHERE source_id=%s AND kind=%s',(uuid4(),f['source'],kind))
    with psycopg.connect(admin_url) as conn:
        conn.execute('INSERT INTO oracle2.source_blocks SELECT %s,source_id,workspace_id,99,kind,text,span_start,span_end FROM oracle2.source_blocks WHERE source_id=%s AND kind=%s',(uuid4(),f['source'],kind))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):adapter.identity(f['workspace'],f['source'])


def run_context(f,adapter):
    # This shared contract is supplied by the independently owned context lane;
    # absence must fail, never become a skipped mandatory authority test.
    from oracle_brain.operating_model.processing_context import ProcessingDispatch,ProcessingRunDescriptor
    from oracle_brain.operating_model.contracts import digest
    from oracle_brain.operating_model.authority_adapter import ProcessingRunBinding,BoundProcessingSourceResolver
    ref=adapter.identity(f['workspace'],f['source'])
    fields={k:'a'*64 for k in ('job_hash','request_hash','permission_hash','processing_request_hash','account_policy_hash','terms_hash','pricing_hash','register_hash','budget_identity_hash')}
    dispatch=ProcessingDispatch(dispatch_id=uuid4(),source_ref=ref,model='openai/gpt-6.1-sol',**fields)
    desc=ProcessingRunDescriptor(run_id=uuid4(),workspace_id=f['workspace'],actor_id=f['actor'],
        worker_uri='spiffe://oracle/test/processing',runtime_hash=RUNTIME,source_registry_hash=REGISTRY,
        parent_registry_sha256='1'*64,envelope_sha256='2'*64,ledger_registry_hash='3'*64,key_coverage_hash='4'*64,
        source_refs=(ref,),dispatches=(dispatch,),issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=f['expiry'])
    pins=ProcessingRunBinding(f['binding'],digest(desc.model_dump(mode='json')),desc.parent_registry_sha256,desc.envelope_sha256)
    return BoundProcessingSourceResolver(f['url'],run_binding=pins),desc,dispatch


def test_real_sql_hold_yields_shared_current_bounded_proof(processing):
    from oracle_brain.operating_model.processing_context import ProcessingAuthorityProof
    f=processing('gateway-metadata');adapter,desc,dispatch=run_context(f,resolver(f))
    with adapter.hold(desc,dispatch) as proof:
        assert type(proof) is ProcessingAuthorityProof
        assert proof.actor_id==f['actor'] and proof.source_ref==dispatch.source_ref
        assert proof.profile=='gateway-metadata' and proof.session_role==f['login']
        assert proof.checked_at<proof.expires_at<=desc.expires_at


@pytest.mark.parametrize('field,value',[
    ('actor_id',uuid4()),('runtime_hash','f'*64),('source_registry_hash','f'*64),
    ('parent_registry_sha256','f'*64),('envelope_sha256','f'*64),
])
def test_real_sql_hold_never_blesses_caller_chosen_descriptor(processing,field,value):
    f=processing('gateway-metadata');adapter,desc,dispatch=run_context(f,resolver(f))
    with pytest.raises(PermissionError):
        with adapter.hold(desc.model_copy(update={field:value}),dispatch):pass


def test_real_sql_hold_requires_exact_dispatch_and_current_dual_grants(admin_url,processing):
    f=processing('gateway-metadata');adapter,desc,dispatch=run_context(f,resolver(f))
    with pytest.raises(PermissionError):
        with adapter.hold(desc,dispatch.model_copy(update={'dispatch_id':uuid4()})):pass
    with psycopg.connect(admin_url) as conn:
        conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f['extract'],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with adapter.hold(desc,dispatch):pass


@pytest.mark.parametrize('kind',[
    'processing_extraction_v1','processing_failed_extraction_v1',
    'processing_qualified_model_v1','processing_summary_v1','processing_failed_assembly_v1',
])
@pytest.mark.parametrize('original_status',['draft','confirmed'])
@pytest.mark.parametrize('read_api',['read','read_with_manifest'])
def test_default_ledger_denies_processing_kind_before_blob_even_if_claims_qualified(admin_url,processing,kind,original_status,read_api):
    from oracle_brain.operating_model.contracts import ArtifactManifest
    from oracle_brain.operating_model.ledger import Ledger
    f=processing();artifact=uuid4()
    manifest=ArtifactManifest(workspace_id=f['workspace'],artifact_id=artifact,version=1,kind=kind,
        input_digest='a'*64,source_digest='a'*64,permission_digest='a'*64,compiler_digest=RUNTIME,
        dependency_digest='a'*64,content_hash='a'*64,private_object_key='invented/claims-qualified',state='ready')
    with psycopg.connect(admin_url) as conn:
        conn.execute('UPDATE oracle2.sources SET status=%s WHERE source_id=%s',(original_status,f['source']))
        conn.execute('UPDATE oracle2.drafts SET status=%s WHERE source_id=%s',(original_status,f['source']))
        conn.execute('INSERT INTO oracle2.artifact_manifests(workspace_id,artifact_id,version,kind,input_digest,source_digest,permission_digest,compiler_digest,dependency_digest,content_hash,private_object_key,state,manifest) VALUES(%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                     (f['workspace'],artifact,kind,manifest.input_digest,manifest.source_digest,manifest.permission_digest,
                      manifest.compiler_digest,manifest.dependency_digest,manifest.content_hash,manifest.private_object_key,manifest.state,Jsonb(manifest.model_dump(mode='json'))))
    class NoBlob:
        def read(self,*args):raise AssertionError('unqualified private blob was opened')
    ledger=Ledger(admin_url,NoBlob(),principal=f['actor'],can_read=lambda *args:True,current_source=lambda *args:None)
    with pytest.raises(PermissionError,match='qualification'):
        getattr(ledger,read_api)(f['workspace'],artifact,1,include_failed=True)


def test_hold_rechecks_actual_scope_clock_before_commit(admin_url,processing):
    import time
    f=processing('gateway-metadata');adapter,desc,dispatch=run_context(f,resolver(f))
    with psycopg.connect(admin_url) as conn:
        conn.execute("UPDATE oracle2.appointments SET expires_at=clock_timestamp()+interval '0.3 second' WHERE appointment_id=%s",(f['extract'],))
    entered=False
    with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):
        with adapter.hold(desc,dispatch) as proof:
            entered=True
            assert proof.expires_at<desc.expires_at
            time.sleep(0.35)
    assert entered


def test_manifest_pair_reuses_full_legacy_authorized_read(admin_url,processing,tmp_path):
    from oracle_brain.operating_model.ledger import Ledger
    from oracle_brain.operating_model.artifact_storage import FileBlobStore
    f=processing()
    with psycopg.connect(admin_url) as conn:
        conn.execute("UPDATE oracle2.sources SET status='confirmed' WHERE source_id=%s",(f['source'],))
        conn.execute("UPDATE oracle2.drafts SET status='confirmed' WHERE source_id=%s",(f['source'],))
    sources=PostgresSources(admin_url,synthetic=True)
    receipt=sources.current(f['workspace'],f['source'])
    ledger=Ledger(admin_url,FileBlobStore(tmp_path),principal=f['actor'],can_read=sources.can_read,current_source=sources.current)
    payload={'source_refs':[receipt.ref.model_dump(mode='json')]}
    manifest=ledger.persist(workspace_id=f['workspace'],artifact_id=uuid4(),version=1,kind='extraction',payload=payload,
                            refs=(receipt.ref,),permission_digest='a'*64,compiler_digest=RUNTIME)
    pair=ledger.read_with_manifest(f['workspace'],manifest.artifact_id,1)
    assert pair==(manifest,payload)
    assert ledger.read(f['workspace'],manifest.artifact_id,1)==pair[1]
    with psycopg.connect(admin_url) as conn:
        conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f['read'],))
    with pytest.raises(PermissionError):ledger.read_with_manifest(f['workspace'],manifest.artifact_id,1)
