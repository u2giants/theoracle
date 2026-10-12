import pytest
from test_operating_model_cutover import manifest
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.retirement import verify_retirement,require_no_legacy_activation

def inputs():
    m=manifest(acceptance_state='admitted_hosted',restricted_hosting_hash='1'*64,restore_proof_hash='2'*64)
    census={'release_hash':m.content_hash(),'files':{'packages/old.py':{'replaced':True,'references':[],'retention_required':False,'capabilities':['source retrieval']}},'new_legacy_writers':[],'fallback_dispatches':[]}
    equivalents={'release_hash':m.content_hash(),'capabilities':{'source retrieval':{'passed':True,'evidence_hash':'3'*64,'release_hash':m.content_hash()}}}
    return m,census,equivalents

def check(m,c,e):
    return verify_retirement(m,c,proposed_paths=('packages/old.py',),preserved_capabilities=e,accepted_release_hashes=frozenset({m.content_hash()}),admitted_census_hashes=frozenset({digest(c)}),admitted_equivalence_hashes=frozenset({digest(e)}))

def test_retirement_requires_accepted_hosted_and_preserves_review_boundary():
    m,c,e=inputs();proof=check(m,c,e)
    assert proof['deletion_authorized'] is False and proof['reviewed_retirement_pr_required']
    with pytest.raises(PermissionError,match='W11'):check(manifest(),c,e)

@pytest.mark.parametrize('mutation', ['references','retention','missing capability','fallback','writer'])
def test_retirement_fails_closed_for_live_dependencies_or_lost_capabilities(mutation):
    m,c,e=inputs()
    if mutation=='references':c['files']['packages/old.py']['references']=['active route']
    elif mutation=='retention':c['files']['packages/old.py']['retention_required']=True
    elif mutation=='missing capability':e['capabilities']['source retrieval']['passed']=False
    elif mutation=='fallback':c['fallback_dispatches']=['old answer']
    else:c['new_legacy_writers']=['new job']
    with pytest.raises(PermissionError):check(m,c,e)

def test_legacy_activation_is_never_authorized_by_retirement():
    with pytest.raises(PermissionError,match='prohibited'):require_no_legacy_activation()

def test_booleans_and_self_asserted_census_do_not_replace_independent_admission():
    m,c,e=inputs()
    with pytest.raises(PermissionError,match='W11'):
        verify_retirement(m,c,proposed_paths=('packages/old.py',),preserved_capabilities=e,
            accepted_release_hashes=frozenset(),admitted_census_hashes=frozenset({digest(c)}),
            admitted_equivalence_hashes=frozenset({digest(e)}))
    with pytest.raises(PermissionError,match='call census'):
        verify_retirement(m,c,proposed_paths=('packages/old.py',),preserved_capabilities=e,
            accepted_release_hashes=frozenset({m.content_hash()}),admitted_census_hashes=frozenset(),
            admitted_equivalence_hashes=frozenset({digest(e)}))
    with pytest.raises(PermissionError,match='capability equivalents'):
        verify_retirement(m,c,proposed_paths=('packages/old.py',),preserved_capabilities=e,
            accepted_release_hashes=frozenset({m.content_hash()}),admitted_census_hashes=frozenset({digest(c)}),
            admitted_equivalence_hashes=frozenset())
