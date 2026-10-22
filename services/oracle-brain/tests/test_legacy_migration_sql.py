"""Owned invented SQL027/source-RLS proof. No production schema or permission claim.

The canonical inventory and027 MUST be installed exactly once by the owned
proof bootstrap before this suite. Fixtures never replay/repair migrations.
Only the seven queried existing Drizzle column/type shapes are reproduced.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4,UUID
import hashlib,json,os,time

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
from oracle_brain.hosting.original_intake_v1 import OriginalIntakeFactoryV1,load_original_intake_settings_v1
from oracle_brain.hosting.legacy_migration_v1 import LegacyMigrationFactoryV1,MigrationIntakeUnknown
from oracle_brain.migration.migration_authority_v1 import MigrationAuthorityV1,MigrationOutcomeUnknown,TABLES
from oracle_brain.migration.migration_settings_v1 import MigrationConsumerConfigV1,MigrationConsumerSettingsV1,SIGNATURES,PUBLIC_SIGNATURES
from oracle_brain.migration.legacy_export_reader_v1 import TechnicalLegacyExportReaderV1,LegacyExportProfileV1,SOURCE_TABLES,actual_export_program_sha256_v1,_json
from test_replacement_source_intake_sql import requester
from test_hosting_boundary import certificates
from test_replacement_requester_sql import owned_admin,configured_settings
from oracle_brain.migration.legacy_storage_capture_v1 import LegacyStorageCaptureProfileV1
from test_legacy_storage_capture_v1 import invented_capture_peer_v1,invented_s3_auth_responder_v1

_NAMESPACE={}
OPERATIONS=('snapshot-register','batch-prepare','batch-observe','read','reconcile','citation-read')
FUNCTION_OPS={
 'register_migration_inventory_v1':('snapshot-register',),
 'prepare_migration_batch_v1':('batch-prepare',),
 'observe_migration_intake_v1':('batch-observe',),
 'record_migration_resolution_v1':('batch-observe',),
 'current_migration_v1':('snapshot-register','read'),
 'reconcile_migration_command_v1':('reconcile',),
 'resolve_migration_citation_v1':('citation-read',),
}


def pin(path,data):
    path.write_bytes(data);path.chmod(0o600)
    return dict(path=str(path),sha256=hashlib.sha256(data).hexdigest())


def canonical_fixture_record_v1(model,values):
    # Test setup uses the SAME strict owner serializer, including its UTC and
    # declared-default representation. No instants, scopes or horizons change.
    return canonical_bytes(model.model_validate_json(canonical_bytes(values)).model_dump(mode='json'))


def private_exception_stage_v1(path,error):
    # TEST-ONLY diagnostics for invented fixtures. Never stringify exceptions,
    # arguments, URLs, original bytes, locals or response/request payloads.
    def text(value,maximum):return value[:maximum] if type(value) is str else None
    chain=[];seen=set();current=error
    while current is not None and id(current) not in seen and len(chain)<8:
        seen.add(id(current));diag=getattr(current,'diag',None);frames=[];tb=current.__traceback__
        while tb is not None and len(frames)<4:
            frames.append(dict(file=Path(tb.tb_frame.f_code.co_filename).name[:256],function=tb.tb_frame.f_code.co_name[:128],line=tb.tb_lineno));tb=tb.tb_next
        chain.append(dict(error_type=type(current).__name__[:128],sqlstate=text(getattr(current,'sqlstate',None),16),
            database_message=text(getattr(diag,'message_primary',None),512),database_context=text(getattr(diag,'context',None),2048),frames=frames))
        current=current.__cause__ or current.__context__
    raw=canonical_bytes(dict(schema_version=1,purpose='invented-test-exception-stage-v1',chain=chain))
    if len(raw)>65536:raise ValueError('bounded private diagnostic required')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())


def namespace(x):
    database=psycopg.conninfo.conninfo_to_dict(x['admin'])['dbname']
    with owned_admin(x) as c:
        assert c.execute("SELECT to_regprocedure('oracle2.register_migration_inventory_v1(uuid,text,text,text,timestamptz,bytea,uuid)') IS NOT NULL").fetchone()==(True,), '027 must already be installed once; no repair'
        actual=c.execute(catalog_query(TechnicalLegacyExportReaderV1._check,'SELECT c.relname'),(list(SOURCE_TABLES),)).fetchall()
        if database in _NAMESPACE:
            assert digest(_json(actual))==_NAMESPACE[database], 'owned source namespace drift, never repair'
            return
        assert actual==[], 'fresh dedicated source namespace required, never adopt existing objects'
        assert c.execute("SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public' AND t.typname=ANY(%s)",(['auth_provider','message_role','channel_status'],)).fetchone()==(0,)
        statements=(
          "CREATE TYPE public.auth_provider AS ENUM('microsoft','google','authentik','magic_link_dev')",
          "CREATE TYPE public.message_role AS ENUM('user','assistant','system')",
          "CREATE TYPE public.channel_status AS ENUM('active','archived','locked')",
          "CREATE TABLE public.employees(id uuid PRIMARY KEY,disabled_at timestamp)",
          "CREATE TABLE public.employee_identities(id uuid PRIMARY KEY,employee_id uuid NOT NULL REFERENCES public.employees,auth_provider public.auth_provider NOT NULL,auth_user_id uuid NOT NULL UNIQUE,UNIQUE(employee_id,auth_provider))",
          "CREATE TABLE public.channels(id uuid PRIMARY KEY,status public.channel_status NOT NULL)",
          "CREATE TABLE public.channel_participants(channel_id uuid NOT NULL REFERENCES public.channels,employee_id uuid NOT NULL REFERENCES public.employees,PRIMARY KEY(channel_id,employee_id))",
          "CREATE TABLE public.messages(id uuid PRIMARY KEY,channel_id uuid NOT NULL REFERENCES public.channels,employee_id uuid REFERENCES public.employees,role public.message_role NOT NULL,content text NOT NULL,edited_at timestamp,deleted_at timestamp,created_at timestamp NOT NULL)",
          "CREATE TABLE public.documents(id uuid PRIMARY KEY,uploader_id uuid NOT NULL REFERENCES public.employees,file_name varchar(255) NOT NULL,file_type varchar(50) NOT NULL,storage_bucket varchar(100) NOT NULL,storage_path varchar(500) NOT NULL,created_at timestamp NOT NULL)",
          "CREATE TABLE public.message_attachments(id uuid PRIMARY KEY,message_id uuid NOT NULL REFERENCES public.messages,document_id uuid NOT NULL REFERENCES public.documents)",
        )
        for statement in statements:c.execute(statement)
        for name in SOURCE_TABLES:
            c.execute(sql.SQL('ALTER TABLE public.{} ENABLE ROW LEVEL SECURITY').format(sql.Identifier(name)))
            c.execute(sql.SQL('REVOKE ALL ON public.{} FROM PUBLIC').format(sql.Identifier(name)))
        actual=c.execute(catalog_query(TechnicalLegacyExportReaderV1._check,'SELECT c.relname'),(list(SOURCE_TABLES),)).fetchall()
        _NAMESPACE[database]=digest(_json(actual))


def catalog_query(function,needle):
    # Fixture pins the exact current owner's catalog projection, no second
    # production validator or permissive expected-catalog fallback.
    values=[v for v in function.__code__.co_consts if type(v) is str and needle in v]
    assert len(values)==1
    return values[0]


@pytest.fixture
def migration_sql(requester,tmp_path,request):
    x=requester;namespace(x);now=datetime.now(timezone.utc);until=now+timedelta(seconds=55)
    s=configured_settings(tmp_path,x)
    a=s.appointment.model_copy(update=dict(media_types=('application/pdf','text/plain')))
    raw=canonical_bytes(a.model_dump(mode='json'));s.appointment_path.write_bytes(raw)
    intake=OriginalIntakeFactoryV1(load_original_intake_settings_v1(s.config_path,s.config_sha256,s.appointment_path,hashlib.sha256(raw).hexdigest(),s.expected_issuer_actor,s.expected_reviewer_actor))
    role_names={op:'migration_'+uuid4().hex[:16] for op in OPERATIONS};source_role='legacy_'+uuid4().hex[:16]
    password='invented-owned-fixture-only';origin='invented_'+uuid4().hex[:12]
    employee,auth_user,channel,message,document,attachment=(uuid4() for _ in range(6))
    mode=getattr(request,'param','message')
    policy='owned_'+uuid4().hex[:16]
    scope=dict(source_database_identity=str(uuid4()),employee_id=str(employee),auth_user_id=str(auth_user),auth_provider='microsoft',channel_id=str(channel),message_ids=[str(message)],document_ids=[str(document)] if mode!='message' else [])
    appointments={op:uuid4() for op in OPERATIONS};export=uuid4();admissions={op:uuid4() for op in OPERATIONS}
    public_roles={name:tuple(role_names[op] for op in ops) for name,ops in FUNCTION_OPS.items()}
    roles=tuple(role_names.values())+(source_role,)
    try:
        with owned_admin(x) as c:
            for role in roles:
                c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
                c.execute(sql.SQL('GRANT USAGE ON SCHEMA oracle2,public TO {}').format(sql.Identifier(role)))
            for signature in PUBLIC_SIGNATURES:
                name=signature.split('(')[0]
                for role in public_roles[name]:c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.{} TO {}').format(sql.SQL(signature),sql.Identifier(role)))
            for name in SOURCE_TABLES:
                c.execute(sql.SQL('GRANT SELECT ON public.{} TO {}').format(sql.Identifier(name),sql.Identifier(source_role)))
            predicates=dict(employees=sql.SQL('id={}').format(sql.Literal(employee)),employee_identities=sql.SQL('employee_id={} AND auth_user_id={}').format(sql.Literal(employee),sql.Literal(auth_user)),
                channels=sql.SQL('id={}').format(sql.Literal(channel)),channel_participants=sql.SQL('channel_id={} AND employee_id={}').format(sql.Literal(channel),sql.Literal(employee)),
                messages=sql.SQL('id={} AND channel_id={}').format(sql.Literal(message),sql.Literal(channel)),documents=sql.SQL('id={}').format(sql.Literal(document)),message_attachments=sql.SQL('id={} AND message_id={} AND document_id={}').format(sql.Literal(attachment),sql.Literal(message),sql.Literal(document)))
            for name in SOURCE_TABLES:c.execute(sql.SQL('CREATE POLICY {} ON public.{} FOR SELECT TO {} USING({})').format(sql.Identifier(policy),sql.Identifier(name),sql.Identifier(source_role),predicates[name]))
            c.execute('INSERT INTO public.employees VALUES(%s,NULL)',(employee,))
            c.execute("INSERT INTO public.employee_identities VALUES(%s,%s,'microsoft',%s)",(uuid4(),employee,auth_user))
            c.execute("INSERT INTO public.channels VALUES(%s,'active')",(channel,))
            c.execute('INSERT INTO public.channel_participants VALUES(%s,%s)',(channel,employee))
            c.execute("INSERT INTO public.messages VALUES(%s,%s,%s,'user',%s,NULL,NULL,clock_timestamp())",(message,channel,employee,'Invented authorized legacy message.'))
            c.execute("INSERT INTO public.documents VALUES(%s,%s,'invented.pdf','application/pdf','invented','a file.pdf',clock_timestamp())",(document,employee))
            c.execute('INSERT INTO public.message_attachments VALUES(%s,%s,%s)',(attachment,message,document))
            for op in OPERATIONS:
                c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(appointments[op],x['workspace'],x['actor'],'migration-'+op+':'+origin,x['owner'],x['root'],until))
            c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(export,x['workspace'],x['actor'],'migration-source-export:'+origin,x['owner'],x['root'],until))
        ca=pin(tmp_path/'migration-ca',Path(os.environ['ORACLE2_TEST_TLS_ROOT']).read_bytes())
        source_url=psycopg.conninfo.make_conninfo(x['admin'],user=source_role,password=password,sslrootcert=ca['path'])
        with psycopg.connect(source_url) as c:
            source_catalog=c.execute(catalog_query(TechnicalLegacyExportReaderV1._check,'SELECT c.relname'),(list(SOURCE_TABLES),)).fetchall()
        source_pin=pin(tmp_path/'source-url',source_url.encode())
        profile=dict(schema_version=1,purpose='technical-legacy-channel-export-v1',permission_producer_kind='technical-channel-v1',source_scope=dict(schema_version=1,**scope),
            database_url=source_pin,database_ca=ca,session_role=source_role,source_catalog_sha256=digest(_json(source_catalog)),source_program_sha256=actual_export_program_sha256_v1(),
            max_original_bytes=64*1024*1024,valid_from=(now-timedelta(seconds=1)).isoformat(),expires_at=until.isoformat(),original_horizon=until.isoformat())
        peer=None;capture_subject=None;document_bytes=b'%PDF-1.4\nInvented currently captured document.\n%%EOF\n'
        if mode!='message':
            import base64
            peer=request.getfixturevalue('invented_capture_peer_v1');peer_owner,peer_state=peer
            capture_subject=uuid4();claims=base64.urlsafe_b64encode(json.dumps(dict(exp=int(until.timestamp())+30)).encode()).decode().rstrip('=')
            token='invented.'+claims+'.fixture';anonymous='invented.anon.fixture'
            p=peer_owner.profile;root=intake.settings.config
            cp=dict(schema_version=1,purpose='legacy-storage-current-capture-v1',origin_system=origin,principal_id=str(x['actor']),workspace_id=str(x['workspace']),
                source_scope_sha256=digest(scope),source_program_sha256=profile['source_program_sha256'],project_ref=p.project_ref,auth_subject=str(capture_subject),
                credential_kind='externally-issued-ordinary-authenticated-session',expected_auth_role='authenticated',
                session_token=pin(tmp_path/'ordinary-technical-session',token.encode()),anonymous_key=pin(tmp_path/'public-fixture-anonymous-key',anonymous.encode()),
                auth_address=p.auth_address,storage_address=p.storage_address,auth_port=p.auth_port,storage_port=p.storage_port,region='us-east-1',
                auth_ca=p.auth_ca.model_dump(mode='json'),storage_ca=p.storage_ca.model_dump(mode='json'),auth_server_der_sha256=p.auth_server_der_sha256,storage_server_der_sha256=p.storage_server_der_sha256,
                storage_root=root.storage_root,storage_device=root.storage_device,storage_inode=root.storage_inode,storage_uid=root.storage_uid,
                max_document_bytes=25*1024*1024,max_aggregate_bytes=64*1024*1024,valid_from=(now-timedelta(seconds=1)).isoformat(),expires_at=until.isoformat(),original_horizon=until.isoformat())
            profile['document_capture_profile']=pin(tmp_path/'capture-profile',canonical_fixture_record_v1(LegacyStorageCaptureProfileV1,cp))
            peer_state.response,provider_operations=invented_s3_auth_responder_v1(token=token,anonymous=anonymous,subject=capture_subject,data=document_bytes,etag='"invented-opaque-current"',mode='ok')
        selected=pin(tmp_path/'source-profile',canonical_fixture_record_v1(LegacyExportProfileV1,profile))
        with owned_admin(x) as c:
            rows=c.execute(catalog_query(MigrationAuthorityV1._check,'SELECT n.nspname,p.proname'),(['oracle2.'+sig for sig in SIGNATURES],)).fetchall()
            fingerprints=sorted((r[1],r[5],r[6]) for r in rows)
        consumers=[]
        for op in OPERATIONS:
            role=role_names[op];url=pin(tmp_path/(role+'-url'),psycopg.conninfo.make_conninfo(x['admin'],user=role,password=password,sslrootcert=ca['path']).encode())
            config=dict(schema_version=1,purpose='legacy-migration-consumer-v1',operation=op,admission_id=str(admissions[op]),principal_id=str(x['actor']),workspace_id=str(x['workspace']),origin_system=origin,session_role=role,expected_owner='oracle2_admin',
                runtime_sha256='a'*64,registry_sha256='b'*64,descriptor_sha256=selected['sha256'],source_scope_sha256=digest(scope),source_program_sha256=profile['source_program_sha256'],intake_principal_id=str(x['actor']),intake_config_sha256=intake.settings.config_sha256,
                database_url=url,database_ca=ca,capability_fingerprints=fingerprints,public_capability_roles=sorted(public_roles.items()),valid_from=(now-timedelta(seconds=1)).isoformat(),expires_at=until.isoformat(),original_horizon=until.isoformat())
            installed=pin(tmp_path/(role+'-config'),canonical_fixture_record_v1(MigrationConsumerConfigV1,config));consumer=MigrationAuthorityV1(MigrationConsumerSettingsV1.load(installed['path'],installed['sha256']));consumers.append(consumer)
            with owned_admin(x) as c:
                c.execute('INSERT INTO oracle2.migration_admissions_v1 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (admissions[op],role,x['actor'],x['workspace'],origin,op,'a'*64,'b'*64,installed['sha256'],selected['sha256'],profile['source_program_sha256'],Jsonb(scope),digest(scope),'technical-channel-v1',appointments[op],export,x['actor'],intake.settings.config_sha256,10000,100,uuid4(),uuid4(),now-timedelta(seconds=1),until,until))
        source=TechnicalLegacyExportReaderV1(selected['path'],selected['sha256'],consumers[0])
        factory=LegacyMigrationFactoryV1(**dict(zip(('register','prepare','observe','read','reconcile','citation'),consumers)),source=source,intake=intake)
        yield SimpleNamespace(x=x,factory=factory,source=source,intake=intake,consumers=consumers,roles=role_names,source_role=source_role,
            employee=employee,auth_user=auth_user,channel=channel,message=message,document=document,attachment=attachment,
            appointments=appointments,export=export,admissions=admissions,origin=origin,until=until,profile=profile,source_profile=selected,peer=peer,document_bytes=document_bytes)
    finally:
        with owned_admin(x) as c:
            for name in SOURCE_TABLES:c.execute(sql.SQL('DROP POLICY IF EXISTS {} ON public.{}').format(sql.Identifier(policy),sql.Identifier(name)))
            for signature in PUBLIC_SIGNATURES:
                for role in public_roles[signature.split('(')[0]]:c.execute(sql.SQL('REVOKE ALL ON FUNCTION oracle2.{} FROM {}').format(sql.SQL(signature),sql.Identifier(role)))
            for name in SOURCE_TABLES:c.execute(sql.SQL('REVOKE ALL ON public.{} FROM {}').format(sql.Identifier(name),sql.Identifier(source_role)))
            for role in roles:
                c.execute(sql.SQL('REVOKE ALL ON SCHEMA oracle2,public FROM {}').format(sql.Identifier(role)))
                c.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def operation_window():
    return _request_fence_v1(time.monotonic()+29),datetime.now(timezone.utc)+timedelta(seconds=25)


def known_head_v1(fixture,receipt,deadline):
    # A write receipt is not current CAS metadata. Read the actual independently
    # admitted current getter; never infer a revision from event sequence.
    status=fixture.factory.reader.status_v1(UUID(receipt['inventory_id']),caller_deadline=deadline)
    assert status['inventory_id']==receipt['inventory_id']
    assert type(status['revision']) is int and status['revision']>0
    return status['revision']


def test_actual_snapshot_register_reserve_finalize_control_without_source_grant(migration_sql):
    f=migration_sql;window,end=operation_window()
    with window:
        registered=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end);inventory=UUID(registered['inventory_id'])
        result=f.factory.import_batch_v1(inventory,known_head_v1(f,registered,end),uuid4(),caller_deadline=end)
        assert result['qualification'] is False and result['source_read_authorized'] is False and result['company_acceptance'] is False
    with owned_admin(f.x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.migration_source_bindings_v1 WHERE workspace_id=%s AND target_source_uuid IS NOT NULL',(f.x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s AND finalized_at IS NOT NULL',(f.x['workspace'],)).fetchone()==(1,)
        assert c.execute("SELECT count(*) FROM oracle2.appointments WHERE workspace_id=%s AND scope LIKE 'source-read:%%'",(f.x['workspace'],)).fetchone()==(0,)
        assert c.execute('SELECT count(*) FROM oracle2.operating_model_source_receipts WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(0,)
    window,end=operation_window()
    with window:
        again=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
        f.factory.import_batch_v1(UUID(again['inventory_id']),known_head_v1(f,again,end),uuid4(),caller_deadline=end)
    with owned_admin(f.x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.migration_source_versions_v1 v JOIN oracle2.migration_source_bindings_v1 b USING(binding_id) WHERE b.workspace_id=%s',(f.x['workspace'],)).fetchone()==(1,)


@pytest.mark.parametrize('failure',['disabled','membership','archived','identity','deleted','oracle-authored'])
def test_actual_current_legacy_permissions_never_borrow_admin_or_intake(failure,migration_sql):
    f=migration_sql
    with owned_admin(f.x) as c:
        if failure=='disabled':c.execute('UPDATE public.employees SET disabled_at=clock_timestamp() WHERE id=%s',(f.employee,))
        elif failure=='membership':c.execute('DELETE FROM public.channel_participants WHERE channel_id=%s',(f.channel,))
        elif failure=='archived':c.execute("UPDATE public.channels SET status='archived' WHERE id=%s",(f.channel,))
        elif failure=='identity':c.execute('DELETE FROM public.employee_identities WHERE employee_id=%s',(f.employee,))
        elif failure=='deleted':c.execute('UPDATE public.messages SET deleted_at=clock_timestamp() WHERE id=%s',(f.message,))
        else:c.execute("UPDATE public.messages SET role='assistant' WHERE id=%s",(f.message,))
    window,end=operation_window()
    with window:
        if failure in ('disabled','membership','archived','identity'):
            with pytest.raises(PermissionError):f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
        else:
            registered=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
            result=f.factory.import_batch_v1(UUID(registered['inventory_id']),known_head_v1(f,registered,end),uuid4(),caller_deadline=end)
            assert result['counts']['quarantined']==1
    with owned_admin(f.x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(0,)


def test_actual_source_catalog_RLS_and_ACL_drift_refuses(migration_sql):
    f=migration_sql
    with owned_admin(f.x) as c:c.execute(sql.SQL('GRANT UPDATE ON public.messages TO {}').format(sql.Identifier(f.source_role)))
    try:
        window,end=operation_window()
        with window:
            with pytest.raises(PermissionError):f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
    finally:
        with owned_admin(f.x) as c:c.execute(sql.SQL('REVOKE UPDATE ON public.messages FROM {}').format(sql.Identifier(f.source_role)))


def test_actual_wrong_admission_and_private_helpers_are_not_runtime_authority(migration_sql):
    f=migration_sql;consumer=f.consumers[0];c=consumer.settings.config
    with psycopg.connect(consumer.url) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):connection.execute('SELECT oracle2._migration_flags_v1()')
    with psycopg.connect(consumer.url) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):connection.execute('SELECT oracle2.current_migration_v1(%s,%s,%s,%s,%s,NULL)',
            (f.admissions['read'],c.runtime_sha256,c.registry_sha256,consumer.settings.config_sha256,datetime.now(timezone.utc)+timedelta(seconds=5)))


def test_actual_source_currentness_after_snapshot_before_prepare_withholds_intake(migration_sql):
    f=migration_sql;window,end=operation_window()
    with window:registered=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
    with owned_admin(f.x) as c:c.execute('UPDATE public.messages SET content=%s,edited_at=clock_timestamp() WHERE id=%s',('Invented corrected source.',f.message))
    window,end=operation_window()
    with window:
        head=known_head_v1(f,registered,end)
        with pytest.raises(PermissionError):f.factory.import_batch_v1(UUID(registered['inventory_id']),head,uuid4(),caller_deadline=end)
    with owned_admin(f.x) as c:assert c.execute('SELECT count(*) FROM oracle2.migration_intents_v1 t JOIN oracle2.migration_inventories_v1 i USING(inventory_id) WHERE i.workspace_id=%s',(f.x['workspace'],)).fetchone()==(0,)


def test_actual_lost_finalize_ACK_one_intake_then_explicit_metadata_observation(migration_sql,monkeypatch):
    f=migration_sql;actual=OriginalIntakeFactoryV1.intake_text_v1;dispatches=[]
    def lost(self,**kwargs):
        value=actual(self,**kwargs);dispatches.append(value)
        raise OSError('invented lost acknowledgement after actual canonical finalize')
    monkeypatch.setattr(OriginalIntakeFactoryV1,'intake_text_v1',lost)
    window,end=operation_window()
    with window:
        registered=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end);inventory=UUID(registered['inventory_id'])
        with pytest.raises(MigrationIntakeUnknown):f.factory.import_batch_v1(inventory,known_head_v1(f,registered,end),uuid4(),caller_deadline=end)
    with owned_admin(f.x) as c:
        intent,dispatch_deadline=c.execute('SELECT t.intent_id,t.original_dispatch_deadline FROM oracle2.migration_intents_v1 t JOIN oracle2.migration_inventories_v1 i USING(inventory_id) WHERE i.inventory_id=%s',(inventory,)).fetchone()
        assert c.execute('SELECT count(*),count(finalized_at) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(1,1)
    window,later=operation_window()
    with window:
        observed=f.factory.observe_intent_v1(intent,uuid4(),caller_deadline=later)
        assert observed['observation_only'] is True and observed['source_read_authorized'] is False
        status=f.factory.reader.status_v1(inventory,caller_deadline=later)
        # Historical unresolved failure persists until separately evidenced repair.
        assert status['applied_sequence']<=status['read_sequence']
    assert len(dispatches)==1
    with owned_admin(f.x) as c:
        assert c.execute('SELECT original_dispatch_deadline FROM oracle2.migration_intents_v1 WHERE intent_id=%s',(intent,)).fetchone()==(dispatch_deadline,)
        assert c.execute('SELECT count(*),count(finalized_at) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(1,1)
        assert c.execute("SELECT count(*) FROM oracle2.appointments WHERE workspace_id=%s AND scope LIKE 'source-read:%%'",(f.x['workspace'],)).fetchone()==(0,)


def test_actual_changed_body_CAS_same_source_requires_independent_source_read(migration_sql):
    f=migration_sql;window,end=operation_window()
    with window:
        first=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
        f.factory.import_batch_v1(UUID(first['inventory_id']),known_head_v1(f,first,end),uuid4(),caller_deadline=end)
    with owned_admin(f.x) as c:
        source=c.execute('SELECT target_source_uuid FROM oracle2.migration_source_bindings_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()[0]
        before=c.execute('SELECT original_sha256 FROM oracle2.source_original_revisions WHERE source_id=%s AND revision=1',(source,)).fetchone()[0]
        c.execute('UPDATE public.messages SET content=%s,edited_at=clock_timestamp() WHERE id=%s',('Actual invented corrected legacy body.',f.message))
    window,end=operation_window()
    with window:
        changed=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
        head=known_head_v1(f,changed,end)
        with pytest.raises((MigrationOutcomeUnknown,psycopg.errors.InsufficientPrivilege)):
            f.factory.import_batch_v1(UUID(changed['inventory_id']),head,uuid4(),caller_deadline=end)
    with owned_admin(f.x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(1,)
        c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f.x['workspace'],f.x['actor'],'source-read:'+str(source),f.x['owner'],f.x['root'],f.until))
    window,end=operation_window()
    with window:
        fresh=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
        f.factory.import_batch_v1(UUID(fresh['inventory_id']),known_head_v1(f,fresh,end),uuid4(),caller_deadline=end)
    with owned_admin(f.x) as c:
        assert c.execute('SELECT target_source_uuid FROM oracle2.migration_source_bindings_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchall()==[(source,)]
        revisions=c.execute('SELECT revision,original_sha256 FROM oracle2.source_original_revisions WHERE source_id=%s ORDER BY revision',(source,)).fetchall()
        assert revisions==[(1,before),(2,hashlib.sha256(b'Actual invented corrected legacy body.').hexdigest())]


def test_actual_concurrent_prepare_CAS_only_one_canonical_intake(migration_sql):
    import concurrent.futures,threading
    f=migration_sql;window,end=operation_window()
    with window:
        registered=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
        shared_head=known_head_v1(f,registered,end)
    inventory=UUID(registered['inventory_id']);barrier=threading.Barrier(2)
    def execute():
        window,end=operation_window()
        with window:
            barrier.wait(timeout=2)
            try:return f.factory.import_batch_v1(inventory,shared_head,uuid4(),caller_deadline=end)
            except (MigrationOutcomeUnknown,psycopg.Error,PermissionError):return 'refused-or-UNKNOWN'
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:execute(),range(2)))
    assert sum(type(r) is dict for r in results)==1
    with owned_admin(f.x) as c:
        assert c.execute('SELECT count(*),count(finalized_at) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(1,1)
        assert c.execute('SELECT count(*) FROM oracle2.migration_source_bindings_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.migration_source_versions_v1 v JOIN oracle2.migration_source_bindings_v1 b USING(binding_id) WHERE b.workspace_id=%s',(f.x['workspace'],)).fetchone()==(1,)


def test_actual_duplicate_identity_constraint_cannot_become_second_permission_path(migration_sql):
    f=migration_sql
    with owned_admin(f.x) as c:
        with pytest.raises(psycopg.errors.UniqueViolation):
            c.execute("INSERT INTO public.employee_identities VALUES(%s,%s,'microsoft',%s)",(uuid4(),f.employee,uuid4()))


def test_actual_independent_viewer_absent_never_synthesizes_citation_permission(migration_sql):
    f=migration_sql;window,end=operation_window()
    with window:
        registered=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
        with pytest.raises(PermissionError,match='viewer unavailable'):
            f.factory.resolve_citation_v1(UUID(registered['inventory_id']),'message:'+str(f.message),caller_deadline=end)


@pytest.mark.parametrize('migration_sql',['pdf'],indirect=True)
def test_actual_Auth_Storage_TLS_SQL_RLS_private_custody_PDF_intake_and_body_only_dedupe(migration_sql,tmp_path):
    f=migration_sql;window,end=operation_window()
    with window:
        try:
            registered=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
        except MigrationOutcomeUnknown as error:
            try:private_exception_stage_v1(tmp_path/'private-register-exception-stage.json',error)
            except Exception:raise error from None
            raise  # Public UNKNOWN and no-resend contract remains exact.
        inventory=UUID(registered['inventory_id'])
        f.factory.import_batch_v1(inventory,known_head_v1(f,registered,end),uuid4(),caller_deadline=end)
    with owned_admin(f.x) as c:
        assert c.execute('SELECT count(*),count(finalized_at) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(2,2)
        body=c.execute("SELECT o.private_receipt_key,o.original_sha256,o.byte_count,o.capture->>'private_body_key' FROM oracle2.migration_capture_observations_v1 o WHERE inventory_id=%s",(inventory,)).fetchone()
        assert body[1:3]==(hashlib.sha256(f.document_bytes).hexdigest(),len(f.document_bytes))
        assert (Path(f.intake.settings.config.storage_root)/body[3]).read_bytes()==f.document_bytes
        assert c.execute('SELECT count(*) FROM oracle2.operating_model_source_receipts WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(0,)
        assert c.execute("SELECT count(*) FROM oracle2.appointments WHERE workspace_id=%s AND scope LIKE 'source-read:%%'",(f.x['workspace'],)).fetchone()==(0,)
    # Fresh Auth/HTTP/private receipt observations differ, identical actual bytes
    # cannot create another original version or another canonical reservation.
    window,end=operation_window()
    with window:
        again=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
        f.factory.import_batch_v1(UUID(again['inventory_id']),known_head_v1(f,again,end),uuid4(),caller_deadline=end)
    with owned_admin(f.x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(2,)
        assert c.execute('SELECT count(*) FROM oracle2.migration_capture_observations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(2,)
        assert c.execute('SELECT count(*) FROM oracle2.migration_source_versions_v1 v JOIN oracle2.migration_source_bindings_v1 b USING(binding_id) WHERE b.workspace_id=%s',(f.x['workspace'],)).fetchone()==(2,)


@pytest.mark.parametrize('migration_sql',['pdf'],indirect=True)
@pytest.mark.parametrize('failure',['link','media','profile'])
def test_actual_document_link_media_and_capture_pin_refusals_never_intake(failure,migration_sql):
    f=migration_sql
    if failure=='profile':
        Path(f.profile['document_capture_profile']['path']).write_bytes(b'{}')
    else:
        with owned_admin(f.x) as c:
            if failure=='link':c.execute('DELETE FROM public.message_attachments WHERE id=%s',(f.attachment,))
            else:c.execute("UPDATE public.documents SET file_type='image/png' WHERE id=%s",(f.document,))
    window,end=operation_window()
    with window:
        if failure=='profile':
            with pytest.raises(PermissionError):f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
        else:
            registered=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
            result=f.factory.import_batch_v1(UUID(registered['inventory_id']),known_head_v1(f,registered,end),uuid4(),caller_deadline=end)
            assert result['counts']['quarantined']==1
    with owned_admin(f.x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(0,)


def test_actual_PostgreSQL_ETag_predicate_compiles_and_keeps_exact_bounds(requester):
    # Actual PostgreSQL evaluates the exact installed refusal predicate. NUL is
    # excluded here because PostgreSQL text itself cannot represent it; the
    # pure language-equivalence test covers all128 ASCII code points.
    with owned_admin(requester) as c:
        definition=c.execute("SELECT pg_get_functiondef('oracle2.register_migration_inventory_v1(uuid,text,text,text,timestamptz,bytea,uuid)'::regprocedure)").fetchone()[0]
        predicate="capture->>'etag'!~'^\"[!#-~]*\"$' OR char_length(capture->>'etag')>512"
        assert predicate in definition
        values=[('"'+'a'*n+'"',n<=510) for n in (0,1,255,256,510,511)]
        values += [('"'+chr(n)+'"',False) for n in range(1,128) if not(n==33 or 35<=n<=126)]
        values += [(x,False) for x in ('"é"','"双"','"😀"','unquoted','W/"tag"','"a"b"','"a"\n')]
        for value,accepted in values:
            actual=c.execute("SELECT NOT ("+predicate+") FROM (SELECT jsonb_build_object('etag',%s::text) AS capture) selected",(value,)).fetchone()[0]
            assert actual is accepted




def reinstalled_migration_factory_v1(fixture,tmp_path):
    # Fixture administrator alone appends distinct immutable installations.
    # Exact existing roles/principal/origin/program/root and expiry remain; old
    # files/admissions are never overwritten, revoked, repaired or renewed.
    f=fixture;tmp_path.mkdir(mode=0o700);consumers=[];before={};after={}
    for old in f.consumers:
        config=old.settings.config;new_id=uuid4()
        updated=config.model_copy(update=dict(admission_id=new_id))
        selected=pin(tmp_path/(config.operation+'-config'),canonical_bytes(updated.model_dump(mode='json')))
        with owned_admin(f.x) as c:
            row=c.execute('SELECT * FROM oracle2.migration_admissions_v1 WHERE admission_id=%s',(config.admission_id,)).fetchone()
            assert len(row)==25 and row[0]==config.admission_id and row[8]==old.settings.config_sha256
            before[str(config.admission_id)]=row
            new=list(row);new[0]=new_id;new[8]=selected['sha256']
            c.execute('INSERT INTO oracle2.migration_admissions_v1 VALUES('+','.join(['%s']*25)+')',tuple(Jsonb(v) if type(v) is dict else v for v in new))
            after[str(new_id)]=c.execute('SELECT * FROM oracle2.migration_admissions_v1 WHERE admission_id=%s',(new_id,)).fetchone()
            assert after[str(new_id)][1:8]==row[1:8] and after[str(new_id)][9:]==row[9:]
        consumers.append(MigrationAuthorityV1(MigrationConsumerSettingsV1.load(selected['path'],selected['sha256'])))
    source=TechnicalLegacyExportReaderV1(f.source_profile['path'],f.source_profile['sha256'],consumers[0])
    factory=LegacyMigrationFactoryV1(**dict(zip(('register','prepare','observe','read','reconcile','citation'),consumers)),source=source,
        intake=OriginalIntakeFactoryV1(f.intake.settings))
    with owned_admin(f.x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.migration_admissions_v1 WHERE workspace_id=%s AND origin_system=%s',(f.x['workspace'],f.origin)).fetchone()==(12,)
        for key,row in before.items():assert c.execute('SELECT * FROM oracle2.migration_admissions_v1 WHERE admission_id=%s',(UUID(key),)).fetchone()==row
    return factory


def test_actual_reinstall_same_body_reuses_global_binding_version_intent_and_intake(migration_sql,tmp_path,monkeypatch):
    f=migration_sql;window,end=operation_window()
    with window:
        first=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end)
        f.factory.import_batch_v1(UUID(first['inventory_id']),known_head_v1(f,first,end),uuid4(),caller_deadline=end)
    with owned_admin(f.x) as c:
        identities=c.execute('SELECT b.binding_id,b.target_source_uuid,v.version_id,t.intent_id,t.intake_idempotency,t.original_dispatch_deadline FROM oracle2.migration_source_bindings_v1 b JOIN oracle2.migration_source_versions_v1 v USING(binding_id) JOIN oracle2.migration_intents_v1 t USING(binding_id,version_id) WHERE b.workspace_id=%s',(f.x['workspace'],)).fetchall()
        reservations=c.execute('SELECT reservation_id,idempotency_key,finalized_at FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchall()
    restarted=reinstalled_migration_factory_v1(f,tmp_path/'reinstalled')
    def no_dispatch(*args,**kwargs):pytest.fail('reinstallation must never redispatch existing original')
    monkeypatch.setattr(OriginalIntakeFactoryV1,'intake_text_v1',no_dispatch)
    window,end=operation_window()
    with window:
        again=restarted.register_snapshot_v1(uuid4(),caller_deadline=end)
        status=restarted.reader.status_v1(UUID(again['inventory_id']),caller_deadline=end)
        result=restarted.import_batch_v1(UUID(again['inventory_id']),status['revision'],uuid4(),caller_deadline=end)
        assert result['applied_sequence']==result['read_sequence']==1
        assert result['dispatch_authorized'] is False and result['qualification'] is False
    with owned_admin(f.x) as c:
        assert c.execute('SELECT b.binding_id,b.target_source_uuid,v.version_id,t.intent_id,t.intake_idempotency,t.original_dispatch_deadline FROM oracle2.migration_source_bindings_v1 b JOIN oracle2.migration_source_versions_v1 v USING(binding_id) JOIN oracle2.migration_intents_v1 t USING(binding_id,version_id) WHERE b.workspace_id=%s',(f.x['workspace'],)).fetchall()==identities
        assert c.execute('SELECT reservation_id,idempotency_key,finalized_at FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchall()==reservations
        assert len(identities)==len(reservations)==1


def test_actual_reinstall_after_lost_ACK_preserves_UNKNOWN_deadline_and_never_resends(migration_sql,tmp_path,monkeypatch):
    f=migration_sql;actual=OriginalIntakeFactoryV1.intake_text_v1;dispatches=[]
    def lost(self,**kwargs):
        value=actual(self,**kwargs);dispatches.append(value)
        raise OSError('invented lost canonical finalize acknowledgement')
    monkeypatch.setattr(OriginalIntakeFactoryV1,'intake_text_v1',lost)
    window,end=operation_window();command=uuid4()
    with window:
        first=f.factory.register_snapshot_v1(uuid4(),caller_deadline=end);inventory=UUID(first['inventory_id'])
        head=known_head_v1(f,first,end)
        with pytest.raises(MigrationIntakeUnknown):f.factory.import_batch_v1(inventory,head,command,caller_deadline=end)
    with owned_admin(f.x) as c:
        original=c.execute('SELECT b.binding_id,b.target_source_uuid,v.version_id,t.intent_id,t.intake_idempotency,t.original_dispatch_deadline FROM oracle2.migration_source_bindings_v1 b JOIN oracle2.migration_source_versions_v1 v USING(binding_id) JOIN oracle2.migration_intents_v1 t USING(binding_id,version_id) WHERE b.workspace_id=%s',(f.x['workspace'],)).fetchall()
        assert len(original)==1 and original[0][1] is None
    restarted=reinstalled_migration_factory_v1(f,tmp_path/'reinstalled')
    def no_dispatch(*args,**kwargs):pytest.fail('UNKNOWN survives reinstall; no original resend')
    monkeypatch.setattr(OriginalIntakeFactoryV1,'intake_text_v1',no_dispatch)
    window,later=operation_window()
    with window:
        fresh=restarted.register_snapshot_v1(uuid4(),caller_deadline=later);new_inventory=UUID(fresh['inventory_id'])
        before=restarted.reader.status_v1(new_inventory,caller_deadline=later)
        result=restarted.import_batch_v1(new_inventory,before['revision'],uuid4(),caller_deadline=later)
        assert result['applied_sequence']==0 and result['read_sequence']==1
        assert result['dispatch_authorized'] is False and result['qualification'] is False
        receipt=restarted.reconcile_v1(command,caller_deadline=later)
        assert receipt['receipt_read_only'] is True and receipt['write_authorized'] is False and receipt['resend_authorized'] is False
    with owned_admin(f.x) as c:
        assert c.execute('SELECT b.binding_id,b.target_source_uuid,v.version_id,t.intent_id,t.intake_idempotency,t.original_dispatch_deadline FROM oracle2.migration_source_bindings_v1 b JOIN oracle2.migration_source_versions_v1 v USING(binding_id) JOIN oracle2.migration_intents_v1 t USING(binding_id,version_id) WHERE b.workspace_id=%s',(f.x['workspace'],)).fetchall()==original
        assert c.execute('SELECT count(*),count(finalized_at) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(f.x['workspace'],)).fetchone()==(1,1)
        assert c.execute('SELECT count(*) FROM oracle2.migration_intent_observations_v1 o JOIN oracle2.migration_intents_v1 t USING(intent_id) JOIN oracle2.migration_inventories_v1 i USING(inventory_id) WHERE i.workspace_id=%s',(f.x['workspace'],)).fetchone()==(0,)
    assert len(dispatches)==1
