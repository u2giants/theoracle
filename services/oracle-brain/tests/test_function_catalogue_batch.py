"""Actual current-catalogue differential; no source or provider authority issued."""
from types import SimpleNamespace
from uuid import uuid4
import psycopg
from psycopg import sql
import pytest
from oracle_brain.operating_model.authority_adapter import ProcessingSourceResolver


def old_check(subject,conn,signatures):
    # Verbatim prior two-query semantics retained as a differential oracle.
    b=subject.binding
    for signature,allowed in signatures.items():
        function=conn.execute("SELECT r.rolname,p.prosecdef,p.proconfig FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE p.oid=to_regprocedure(%s)",(signature,)).fetchone()
        if function!=(b.expected_owner_role,True,['search_path=pg_catalog, oracle2']):
            raise PermissionError('fixed processing function owner/config differs')
        if allowed is not None:
            grants=conn.execute("""SELECT coalesce(r.rolname,'PUBLIC'),a.is_grantable
                FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
                LEFT JOIN pg_roles r ON r.oid=a.grantee
                WHERE p.oid=to_regprocedure(%s) AND a.privilege_type='EXECUTE' AND a.grantee<>p.proowner""",(signature,)).fetchall()
            if frozenset(name for name,_ in grants)!=allowed or any(grantable for _,grantable in grants):
                raise PermissionError('fixed processing function ACL differs')

def result(check,subject,conn,signatures):
    try:check(subject,conn,signatures);return 'PASS'
    except PermissionError as error:return str(error)

@pytest.fixture
def catalogue(admin_url):
    with psycopg.connect(admin_url,autocommit=True) as conn:
        owner=conn.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2'").fetchone()[0]
        name='owned_catalogue_'+uuid4().hex[:12];foreign='owned_catalogue_role_'+uuid4().hex[:10]
        conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(foreign)))
        conn.execute(sql.SQL('CREATE FUNCTION oracle2.{}() RETURNS integer LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$ SELECT 1 $$').format(sql.Identifier(name)))
        conn.execute(sql.SQL('ALTER FUNCTION oracle2.{}() OWNER TO {}').format(sql.Identifier(name),sql.Identifier(owner)))
        conn.execute(sql.SQL('REVOKE ALL ON FUNCTION oracle2.{}() FROM PUBLIC').format(sql.Identifier(name)))
        conn.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.{}() TO oracle2_source_reader').format(sql.Identifier(name)))
        try:yield conn,SimpleNamespace(binding=SimpleNamespace(expected_owner_role=owner)),name,foreign
        finally:
            conn.execute(sql.SQL('DROP FUNCTION oracle2.{}()').format(sql.Identifier(name)))
            conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(foreign)))

@pytest.mark.parametrize('damage',['valid','missing','owner','invoker','search-path','PUBLIC','unexpected','grantable','empty','unchecked-acl'])
def test_actual_catalogue_batch_matches_prior_all_function_controls(catalogue,damage):
    conn,subject,name,foreign=catalogue;signature='oracle2.'+name+'()';allowed=frozenset({'oracle2_source_reader'})
    if damage=='missing':signature='oracle2.owned_catalogue_absent_'+uuid4().hex+'()'
    elif damage=='owner':conn.execute(sql.SQL('ALTER FUNCTION oracle2.{}() OWNER TO {}').format(sql.Identifier(name),sql.Identifier(foreign)))
    elif damage=='invoker':conn.execute(sql.SQL('ALTER FUNCTION oracle2.{}() SECURITY INVOKER').format(sql.Identifier(name)))
    elif damage=='search-path':conn.execute(sql.SQL('ALTER FUNCTION oracle2.{}() SET search_path=oracle2,pg_catalog').format(sql.Identifier(name)))
    elif damage=='PUBLIC':conn.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.{}() TO PUBLIC').format(sql.Identifier(name)))
    elif damage=='unexpected':conn.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.{}() TO {}').format(sql.Identifier(name),sql.Identifier(foreign)))
    elif damage=='grantable':conn.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.{}() TO oracle2_source_reader WITH GRANT OPTION').format(sql.Identifier(name)))
    elif damage=='empty':conn.execute(sql.SQL('REVOKE EXECUTE ON FUNCTION oracle2.{}() FROM oracle2_source_reader').format(sql.Identifier(name)))
    elif damage=='unchecked-acl':allowed=None
    signatures={signature:allowed}
    before=result(old_check,subject,conn,signatures)
    after=result(ProcessingSourceResolver._check_function_signatures,subject,conn,signatures)
    assert after==before
    assert (after=='PASS')==(damage in {'valid','unchecked-acl'})

def test_actual_second_current_check_observes_new_acl_mutation(catalogue):
    conn,subject,name,_=catalogue;signatures={'oracle2.'+name+'()':frozenset({'oracle2_source_reader'})}
    ProcessingSourceResolver._check_function_signatures(subject,conn,signatures)
    conn.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.{}() TO PUBLIC').format(sql.Identifier(name)))
    with pytest.raises(PermissionError,match='ACL differs'):
        ProcessingSourceResolver._check_function_signatures(subject,conn,signatures)

def test_actual_missing_middle_function_keeps_ordinal_and_no_row_drops(catalogue):
    conn,subject,name,_=catalogue
    signatures={'oracle2.'+name+'()':frozenset({'oracle2_source_reader'}),'oracle2.absent_'+uuid4().hex+'()':frozenset()}
    assert result(old_check,subject,conn,signatures)==result(ProcessingSourceResolver._check_function_signatures,subject,conn,signatures)=='fixed processing function owner/config differs'

def test_actual_null_default_acl_retains_public_execute(catalogue):
    conn,subject,_,_=catalogue;name='owned_default_'+uuid4().hex[:12]
    conn.execute(sql.SQL('CREATE FUNCTION oracle2.{}() RETURNS integer LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$ SELECT 1 $$').format(sql.Identifier(name)))
    conn.execute(sql.SQL('ALTER FUNCTION oracle2.{}() OWNER TO {}').format(sql.Identifier(name),sql.Identifier(subject.binding.expected_owner_role)))
    try:
        assert conn.execute('SELECT proacl IS NULL FROM pg_proc WHERE oid=to_regprocedure(%s)',('oracle2.'+name+'()',)).fetchone()==(True,)
        for allowed in (frozenset({'PUBLIC'}),frozenset()):
            signatures={'oracle2.'+name+'()':allowed}
            assert result(old_check,subject,conn,signatures)==result(ProcessingSourceResolver._check_function_signatures,subject,conn,signatures)
    finally:conn.execute(sql.SQL('DROP FUNCTION oracle2.{}()').format(sql.Identifier(name)))

def test_actual_inherited_role_is_not_expanded_into_different_direct_acl(catalogue):
    conn,subject,name,foreign=catalogue
    conn.execute(sql.SQL('GRANT {} TO oracle2_source_reader').format(sql.Identifier(foreign)))
    try:
        conn.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.{}() TO {}').format(sql.Identifier(name),sql.Identifier(foreign)))
        signatures={'oracle2.'+name+'()':frozenset({'oracle2_source_reader'})}
        assert result(old_check,subject,conn,signatures)==result(ProcessingSourceResolver._check_function_signatures,subject,conn,signatures)=='fixed processing function ACL differs'
    finally:conn.execute(sql.SQL('REVOKE {} FROM oracle2_source_reader').format(sql.Identifier(foreign)))

def test_actual_alias_ordinals_preserved_and_all_rows_use_one_current_query(catalogue):
    conn,subject,name,_=catalogue;allowed=frozenset({'oracle2_source_reader'})
    signatures={'oracle2.'+name+'()':allowed,'oracle2."'+name+'"()':allowed}
    class Count:
        calls=0
        def execute(self,*args,**kwargs):self.calls+=1;return conn.execute(*args,**kwargs)
    previous=Count();old_check(subject,previous,signatures);assert previous.calls==4
    current=Count();ProcessingSourceResolver._check_function_signatures(subject,current,signatures);assert current.calls==1
