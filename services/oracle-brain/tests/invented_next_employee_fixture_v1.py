"""ONE fresh-owned actual employee SQL fixture; not app/session authority.

Preserves the existing S05 setup and least-privilege behavior. Existing identity
schema refuses; no adoption, if-exists repair, role borrowing or real target.
"""
from dataclasses import dataclass,field
from uuid import UUID,uuid4
from urllib.parse import quote
import psycopg
from psycopg import sql
from dev.oracle2.test_worker_postgres_fixture import owned_worker_database

@dataclass(frozen=True)
class InventedNextEmployeeFixtureV1:
    auth_user_id:UUID
    employee_id:UUID
    login:str
    database:str
    web_database_url:str=field(repr=False)
    database_root_ca:str=field(repr=False)


@dataclass(frozen=True)
class InventedNextEmployeePairFixtureV1:
    recipients:tuple
    login:str
    database:str
    web_database_url:str=field(repr=False)
    database_root_ca:str=field(repr=False)


def invented_next_employee_fixture_v1(admin_url,*,container):
    auth_user,employee=uuid4(),uuid4()
    pair=_invented_next_employee_rows_v1(admin_url,container=container,entries=((auth_user,employee,False),))
    return InventedNextEmployeeFixtureV1(auth_user,employee,pair.login,pair.database,pair.web_database_url,pair.database_root_ca)


def invented_next_employee_pair_fixture_v1(admin_url,*,container,entries):
    if type(entries) is not tuple or len(entries)!=2:
        raise ValueError('exact two invented employee entries required')
    return _invented_next_employee_rows_v1(admin_url,container=container,entries=entries)


def _invented_next_employee_rows_v1(admin_url,*,container,entries):
    if (not entries or len(entries)>2 or any(type(entry) is not tuple or len(entry)!=3
            or type(entry[0]) is not UUID or type(entry[1]) is not UUID or type(entry[2]) is not bool for entry in entries)
            or len({entry[0] for entry in entries})!=len(entries) or len({entry[1] for entry in entries})!=len(entries)):
        raise ValueError('distinct exact invented authuser/employee/bool tuples required')
    owned_worker_database(container,admin_url)
    login='invented_web_'+uuid4().hex;password=uuid4().hex
    dbname=psycopg.conninfo.conninfo_to_dict(admin_url)['dbname']
    with psycopg.connect(admin_url) as c:
        assert c.pgconn.ssl_in_use and c.execute('SELECT SESSION_USER,current_database()').fetchone()==('oracle2_admin',dbname)
        c.execute("CREATE TYPE public.auth_provider AS ENUM ('microsoft','google','authentik','magic_link_dev')")
        c.execute("""CREATE TABLE public.employees(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),email varchar(320) NOT NULL UNIQUE,name varchar(255) NOT NULL,role varchar(255) NOT NULL,department varchar(255),departments text[] NOT NULL DEFAULT '{}',is_admin boolean NOT NULL DEFAULT false,locale varchar(12) NOT NULL DEFAULT 'en',disabled_at timestamp,last_login_at timestamp,created_at timestamp NOT NULL DEFAULT now());
          CREATE TABLE public.employee_identities(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),employee_id uuid NOT NULL REFERENCES public.employees(id) ON DELETE CASCADE,auth_provider public.auth_provider NOT NULL,auth_user_id uuid NOT NULL UNIQUE,auth_provider_subject varchar(255),email varchar(320) NOT NULL,linked_at timestamp NOT NULL DEFAULT now(),last_login_at timestamp);
          ALTER TABLE public.employees ENABLE ROW LEVEL SECURITY; ALTER TABLE public.employees FORCE ROW LEVEL SECURITY;
          ALTER TABLE public.employee_identities ENABLE ROW LEVEL SECURITY; ALTER TABLE public.employee_identities FORCE ROW LEVEL SECURITY""")
        c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION').format(sql.Identifier(login),sql.Literal(password)))
        c.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(dbname),sql.Identifier(login)))
        c.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(login)))
        c.execute(sql.SQL('GRANT SELECT ON public.employees,public.employee_identities TO {}').format(sql.Identifier(login)))
        employee_terms=sql.SQL(' OR ').join(sql.SQL('id={}').format(sql.Literal(employee)) for _,employee,_ in entries)
        identity_terms=sql.SQL(' OR ').join(sql.SQL('(employee_id={} AND auth_user_id={})').format(sql.Literal(employee),sql.Literal(auth_user)) for auth_user,employee,_ in entries)
        c.execute(sql.SQL('CREATE POLICY invented_employee_only ON public.employees FOR SELECT TO {} USING ({})').format(sql.Identifier(login),employee_terms))
        c.execute(sql.SQL('CREATE POLICY invented_identity_only ON public.employee_identities FOR SELECT TO {} USING ({})').format(sql.Identifier(login),identity_terms))
        for index,(auth_user,employee,is_admin) in enumerate(entries):
            email='invented-next@example.invalid' if index==0 else 'invented-next-'+str(index)+'@example.invalid'
            c.execute("INSERT INTO public.employees(id,email,name,role,is_admin) VALUES(%s,%s,'Invented Next employee','invented',%s)",(employee,email,is_admin))
            c.execute("INSERT INTO public.employee_identities(employee_id,auth_provider,auth_user_id,email) VALUES(%s,'magic_link_dev',%s,%s)",(employee,auth_user,email))
    params=psycopg.conninfo.conninfo_to_dict(admin_url)
    web_url='postgresql://'+quote(login)+':'+quote(password)+'@127.0.0.1:'+params['port']+'/'+dbname+'?sslmode=verify-full&application_name=oracle2-invented-next-identity'
    # Independently prove exact least privilege, RLS row binding and TLS now.
    with psycopg.connect(psycopg.conninfo.make_conninfo(admin_url,user=login,password=password)) as c:
        assert c.pgconn.ssl_in_use and c.execute('SELECT SESSION_USER,current_database()').fetchone()==(login,dbname)
        assert set(c.execute('SELECT id FROM public.employees').fetchall())=={(entry[1],) for entry in entries}
        assert set(c.execute('SELECT auth_user_id FROM public.employee_identities').fetchall())=={(entry[0],) for entry in entries}
        assert c.execute("SELECT has_table_privilege(current_user,'public.employees','INSERT,UPDATE,DELETE')").fetchone()==(False,)
    return InventedNextEmployeePairFixtureV1(entries,login,dbname,web_url,params['sslrootcert'])
