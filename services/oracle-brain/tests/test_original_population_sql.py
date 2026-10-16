"""Given invented raw revisions, prove actual complete-phase SQL authority."""
from datetime import timedelta
from uuid import UUID,uuid4
import psycopg
from psycopg import sql
import pytest

from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.original_qualification_v1 import RawOriginalRefV1,RawOriginalPopulationV1
from test_replacement_source_intake_sql import requester,call,reserve,custody


@pytest.fixture
def raw_reader(requester,request):
    x=requester.copy();refs=[]
    short=getattr(request,'param',None)=='short-horizon'
    if short:x['until']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc)+timedelta(seconds=5)
    native=getattr(request,'param',None)=='native-utf8'
    media='text/plain' if native else 'application/pdf'
    original_hash=__import__('hashlib').sha256(b'invent!').hexdigest() if native else 'c'*64
    for _ in range(3):
        e=call(x,'reserve_source_revision_v1',0,psycopg.types.json.Jsonb(dict(source_id=None,filename='invented.txt' if native else 'invented.pdf',media_type=media,byte_count=7,caller_deadline=x['until'].isoformat())),uuid4());r=e['reservation']
        call(x,'finalize_source_revision_v1',r['reservation_id'],0,psycopg.types.json.Jsonb(custody(e,original_sha256=original_hash)))
        refs.append(RawOriginalRefV1(workspace_id=x['workspace'],source_id=UUID(r['source_id']),revision=1,
            original_sha256=original_hash,byte_count=7,media_type=media,filename='invented.txt' if native else 'invented.pdf',custody_locator_seal_sha256='d'*64))
    login='raw_reader_'+uuid4().hex[:12];actor,population=uuid4(),uuid4();runtime='e'*64;registry='f'*64
    phase_until=x['until']-timedelta(seconds=.3 if short else 10);role_until=phase_until-timedelta(seconds=.2 if short else 5)
    pop=RawOriginalPopulationV1(population_id=population,workspace_id=x['workspace'],original_root_hash='1'*64,
        operation_registry_hash='2'*64,runtime_hash=runtime,source_registry_hash=registry,raw_refs=tuple(refs),
        population_digest=digest({'raw_refs':[r.model_dump(mode='json') for r in refs]}),issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=phase_until)
    grants=[]
    with psycopg.connect(x['admin']) as c:
        schema_owner=c.execute("SELECT r.rolname FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname='oracle2'").fetchone()[0]
        c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(
            sql.Identifier(login),sql.Literal('invented-raw-reader-only')))
        c.execute(sql.SQL('GRANT oracle2_source_original_reader TO {}').format(sql.Identifier(login)))
        c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,runtime,registry,role_until))
        c.execute('''INSERT INTO oracle2.original_source_populations_v1(population_id,workspace_id,purpose,original_root_hash,
            population_digest,operation_registry_hash,runtime_hash,source_registry_hash,original_allocation_hash,original_horizon,
            issuer_actor,reviewer_actor,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (population,x['workspace'],'source-original-reading',pop.original_root_hash,pop.population_digest,pop.operation_registry_hash,
             runtime,registry,'3'*64,x['until'],pop.issuer_actor,pop.reviewer_actor,phase_until))
        c.execute('INSERT INTO oracle2.hosting_original_population_admissions_v1 VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
            (login,population,actor,'source-original-reading',runtime,registry,pop.operation_registry_hash,role_until))
        for ordinal,ref in enumerate(refs):
            c.execute('INSERT INTO oracle2.original_source_population_members_v1 VALUES(%s,%s,%s,%s,%s,%s)',
                (population,ordinal,x['workspace'],ref.source_id,ref.revision,digest(ref.model_dump(mode='json'))))
            c.execute('''INSERT INTO oracle2.hosting_original_source_admissions(role_name,workspace_id,source_id,revision,principal_id,
                original_sha256,purpose,runtime_hash,registry_hash,population_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (login,x['workspace'],ref.source_id,1,actor,ref.original_sha256,'source-original-reading',runtime,registry,population,role_until))
            for scope in ('source-read:','source-original-reading:'):
                grant=uuid4();grants.append(grant)
                c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                    (grant,x['workspace'],actor,scope+str(ref.source_id),x['owner'],x['root'],role_until))
    url=psycopg.conninfo.make_conninfo(x['admin'],user=login,password='invented-raw-reader-only')
    try:yield x|dict(url=url,login=login,actor=actor,population=pop,refs=refs,grants=grants,role_until=role_until,schema_owner=schema_owner)
    finally:
        with psycopg.connect(x['admin']) as c:
            c.execute('DELETE FROM oracle2.hosting_original_source_admissions WHERE role_name=%s',(login,))
            c.execute('DELETE FROM oracle2.hosting_original_population_admissions_v1 WHERE role_name=%s',(login,))
            c.execute('DELETE FROM oracle2.hosting_role_runtime_admissions WHERE role_name=%s',(login,))
            c.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(login)))


def test_actual_raw_population_is_complete_current_ordered_and_has_no_locator(raw_reader):
    x=raw_reader;result=call(x,'original_population_current_v1',x['population'].population_id)
    assert set(result)=={'population','original_allocation_hash','original_horizon','actual_principal_id','session_role','checked_at','valid_until'}
    assert result['actual_principal_id']==str(x['actor']) and result['session_role']==x['login']
    assert RawOriginalPopulationV1.model_validate_json(__import__('json').dumps(result['population']))==x['population']
    assert 'private_object_key' not in __import__('json').dumps(result)
    assert result['original_allocation_hash']=='3'*64
    assert __import__('datetime').datetime.fromisoformat(result['valid_until'])<=x['role_until']
    original=call(x,'original_revision_read_v1',x['refs'][0].source_id,1)
    assert original['private_object_key'] and original['population_id']==str(x['population'].population_id)


def test_actual_third_source_revoke_denies_population_and_first_original_before_locator(raw_reader):
    x=raw_reader
    with psycopg.connect(x['admin']) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['grants'][-2],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'original_population_current_v1',x['population'].population_id)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'original_revision_read_v1',x['refs'][0].source_id,1)


@pytest.mark.parametrize('mutation',['gap','seal','runtime'])
def test_actual_registered_population_mutation_fails_closed(raw_reader,mutation):
    x=raw_reader
    with psycopg.connect(x['admin']) as c:
        if mutation=='gap':c.execute('UPDATE oracle2.original_source_population_members_v1 SET ordinal=3 WHERE population_id=%s AND ordinal=2',(x['population'].population_id,))
        elif mutation=='seal':c.execute("UPDATE oracle2.original_source_population_members_v1 SET raw_ref_sha256=%s WHERE population_id=%s AND ordinal=2",('9'*64,x['population'].population_id))
        else:c.execute('UPDATE oracle2.hosting_original_population_admissions_v1 SET runtime_hash=%s WHERE role_name=%s',('9'*64,x['login']))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'original_population_current_v1',x['population'].population_id)


def resolver_for(x):
    from oracle_brain.operating_model.original_source_authority_v1 import OriginalSourceBindingV1,OriginalSourceResolverV1
    binding=OriginalSourceBindingV1(population=x['population'],principal=x['actor'],purpose='source-original-reading',
        expected_owner_role=x['schema_owner'],expected_session_role=x['login'],original_allocation_hash='3'*64,
        original_horizon=x['until'],expires_at=x['role_until'])
    return OriginalSourceResolverV1(x['url'],binding=binding)


def test_actual_typed_raw_resolver_rechecks_same_own_connection_and_rejects_admin_borrow(raw_reader):
    x=raw_reader;resolver=resolver_for(x)
    with psycopg.connect(x['url']) as c:
        before=resolver.original_population_current_v1(x['population'].population_id,connection=c)
        original=resolver.original_revision_access_v1(x['refs'][0].source_id,1,connection=c)
        assert original['principal_id']==str(x['actor']) and before.population==x['population']
    with psycopg.connect(x['admin']) as c,pytest.raises(PermissionError,match='target differs'):
        resolver.original_population_current_v1(x['population'].population_id,connection=c)


def test_actual_role_to_subject_drift_is_reported_by_sql_but_rejected_by_old_protected_pins(raw_reader):
    x=raw_reader;resolver=resolver_for(x);foreign=uuid4()
    with psycopg.connect(x['admin']) as c:
        c.execute('UPDATE oracle2.hosting_original_population_admissions_v1 SET principal_id=%s WHERE role_name=%s',(foreign,x['login']))
        c.execute('UPDATE oracle2.hosting_original_source_admissions SET principal_id=%s WHERE role_name=%s',(foreign,x['login']))
        for ref in x['refs']:
            for scope in ('source-read:','source-original-reading:'):
                c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                    (uuid4(),x['workspace'],foreign,scope+str(ref.source_id),x['owner'],x['root'],x['role_until']))
    actual=call(x,'original_population_current_v1',x['population'].population_id)
    assert actual['actual_principal_id']==str(foreign)
    with pytest.raises(PermissionError,match='protected pins'):
        resolver.original_population_current_v1(x['population'].population_id)
    with pytest.raises(PermissionError,match='protected pins'):
        resolver.original_revision_access_v1(x['refs'][0].source_id,1)
