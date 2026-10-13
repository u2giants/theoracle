"""Distinct fixed public scenario; legacy admission never becomes forward authority."""
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
import hashlib,json
import pytest
from oracle_brain.hosting.synthetic_fixture import fixed_scenario,fixture,LEGACY_SCENARIO,FORWARD_SCENARIO
from oracle_brain.hosting.synthetic_seed import compile_seed
from oracle_brain.hosting.runtime import sealed_scenario,FixedScenarioAuthority
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from test_hosting_synthetic_fixture import parameters


def config():
    scenario=fixed_scenario(FORWARD_SCENARIO)
    return {'synthetic':True,'runtime_hash':'a'*64,'synthetic_scenario':scenario.scenario_id,
            'synthetic_scenario_seal':scenario.seal(),'synthetic_review_hash':'c'*64,
            'worker_uri':scenario.worker_uri,'allowed_release_hashes':[fixture('a'*64,'c'*64,scenario.scenario_id)[-1].content_hash()]}


def test_scenarios_disjoint_fixed_identifiers_and_text():
    old,new=fixed_scenario(),fixed_scenario(FORWARD_SCENARIO)
    old_ids=set(str(v) for v in (old.workspace,old.actor,old.owner,old.artifact,old.generation,old.release,old.run,old.root_appointment,old.grantor,*old.draft_ids,*old.appointment_ids,*old.block_ids,*(x[0] for x in old.sources)))
    new_ids=set(str(v) for v in (new.workspace,new.actor,new.owner,new.artifact,new.generation,new.release,new.run,new.root_appointment,new.grantor,*new.draft_ids,*new.appointment_ids,*new.block_ids,*(x[0] for x in new.sources)))
    assert old_ids.isdisjoint(new_ids)
    assert old.parser!=new.parser and old.worker_uri!=new.worker_uri and old.seed_marker!=new.seed_marker
    assert {s[1] for s in old.sources}.isdisjoint({s[1] for s in new.sources})
    assert fixture('a'*64,'c'*64)[-1].graph_name!=fixture('a'*64,'c'*64,FORWARD_SCENARIO)[-1].graph_name


def test_forward_canonical_payload_and_seed_do_not_contain_old_job():
    scenario=fixed_scenario(FORWARD_SCENARIO)
    p=parameters();p.update(synthetic_scenario=scenario.scenario_id,synthetic_scenario_seal=scenario.seal())
    sql,manifest,payload,release=compile_seed(p)
    assert scenario.run.hex in sql and fixed_scenario().run.hex not in sql
    assert scenario.seed_marker in sql and fixed_scenario().seed_marker not in sql
    assert str(scenario.workspace) in sql and str(fixed_scenario().workspace) not in sql
    assert manifest.content_hash==digest(payload)==release.artifact_content_hash
    assert canonical_bytes(payload)==canonical_bytes(fixture('a'*64,'c'*64,FORWARD_SCENARIO)[2])
    assert sealed_scenario(config())==scenario


@pytest.mark.parametrize('field,value',[('synthetic_scenario','arbitrary'),('synthetic_scenario',LEGACY_SCENARIO),('synthetic_scenario_seal','0'*64),('worker_uri','spiffe://oracle/synthetic-worker'),('allowed_release_hashes',[fixture('a'*64,'c'*64)[-1].content_hash()]),('synthetic_review_hash','d'*64),('synthetic',False)])
def test_cross_scenario_or_drifted_authority_refused(field,value):
    c=config();c[field]=value
    with pytest.raises(PermissionError):sealed_scenario(c)


@pytest.mark.parametrize('field',['synthetic_scenario','synthetic_scenario_seal','synthetic_review_hash'])
def test_partial_scenario_pins_refused(field):
    c=config();del c[field]
    with pytest.raises(PermissionError):sealed_scenario(c)


def test_forward_worker_without_scenario_pins_refused():
    c=config()
    for key in ('synthetic_scenario','synthetic_scenario_seal','synthetic_review_hash'):del c[key]
    with pytest.raises(PermissionError):sealed_scenario(c)


def test_seed_accepts_only_closed_scenarios_and_matching_seal():
    p=parameters();p.update(synthetic_scenario=FORWARD_SCENARIO,synthetic_scenario_seal=fixed_scenario().seal())
    with pytest.raises(PermissionError):compile_seed(p)
    with pytest.raises(PermissionError):fixed_scenario('new-arbitrary-data')


def test_legacy_default_equals_explicit_fixture_and_seed():
    assert canonical_bytes(fixture('a'*64,'c'*64)[2])==canonical_bytes(fixture('a'*64,'c'*64,LEGACY_SCENARIO)[2])
    p=parameters();legacy=compile_seed(p)
    p.update(synthetic_scenario=LEGACY_SCENARIO,synthetic_scenario_seal=fixed_scenario().seal())
    explicit=compile_seed(p)
    assert legacy[0]==explicit[0] and legacy[-1]==explicit[-1]


def test_old_job_and_result_denied_before_database_connection(monkeypatch):
    scenario=fixed_scenario(FORWARD_SCENARIO)
    authority=FixedScenarioAuthority('not-a-real-database',scenario=scenario,runtime_hash='a'*64,synthetic=True,allowed_release_hashes=frozenset(config()['allowed_release_hashes']))
    for resolver in (authority.resolve,authority.resolve_result):
        with pytest.raises(PermissionError):resolver(str(fixed_scenario().run),'a'*64,'b'*64)
