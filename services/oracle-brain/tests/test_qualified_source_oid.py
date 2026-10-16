"""Actual prepared callers across additive014 retain original dispatcher OID."""
from pathlib import Path
from uuid import uuid4
import psycopg
import pytest
from test_source_processing_qualification import processing


def test_prepared_source_callers_cannot_bypass_new_intake_branch(admin_url,processing):
    f=processing('source-reader');signature='oracle2._processing_source(uuid,uuid,uuid,text,text,boolean)'
    with psycopg.connect(f['url'],autocommit=True) as caller,psycopg.connect(admin_url,autocommit=True) as owner:
        old=owner.execute('SELECT to_regprocedure(%s)::oid',(signature,)).fetchone()[0]
        caller.execute("SET statement_timeout='5s'")
        caller.execute('PREPARE public_source(uuid,uuid,uuid,text,text) AS SELECT * FROM oracle2.hosting_processing_source_receipt($1,$2,$3,$4,$5)')
        args=(f['workspace'],f['source'],f['actor'],f['binding'].runtime_hash,f['binding'].source_registry_hash)
        from psycopg import sql
        def prepared():return caller.execute(sql.SQL('EXECUTE public_source({})').format(sql.SQL(',').join(sql.Literal(v) for v in args))).fetchone()
        assert prepared()[4]==f['reading']
        owner.execute('PREPARE private_source(uuid,uuid,uuid,text,text) AS SELECT * FROM oracle2._processing_source($1,$2,$3,$4,$5,true)')
        private=sql.SQL('EXECUTE private_source({})').format(sql.SQL(',').join(sql.Literal(v) for v in args))
        # This owner PREPARE is never an admitted source principal: it must deny.
        with pytest.raises(psycopg.errors.InsufficientPrivilege):owner.execute(private)
        owner.execute((Path(__file__).parents[1]/'sql/014_replacement_source_custody.sql').read_text())
        assert owner.execute('SELECT to_regprocedure(%s)::oid',(signature,)).fetchone()[0]==old
        assert prepared()[4]==f['reading']
        # GIVEN owner-recorded unqualified intake history; no operation authority.
        owner.execute("INSERT INTO oracle2.source_intake_reservations_v1 VALUES(%s,%s,%s,%s,0,1,'invented.pdf','application/pdf',7,'fixture-not-read',%s,%s,NULL,NULL,%s,NULL)",(uuid4(),f['workspace'],f['source'],f['actor'],uuid4(),'0'*64,f['expiry']))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):prepared()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):owner.execute(private)
