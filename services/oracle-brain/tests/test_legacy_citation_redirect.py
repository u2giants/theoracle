import pytest
from oracle_brain.operating_model.retirement_checklist import (
    CitationRedirect, CitationRestoreContract, validate_citation_restore,
)

REL = 'a' * 64


def admitted():
    return frozenset({REL})


def contract(legacy_ids=('legacy-claim-1', 'legacy-claim-2'),
             redirects=None):
    if redirects is None:
        redirects = (CitationRedirect(legacy_id='legacy-claim-1', current_id='current-claim-9'),
                     CitationRedirect(legacy_id='legacy-claim-2', current_id='current-claim-4'))
    return CitationRestoreContract(release_hash=REL, legacy_ids=legacy_ids, redirects=redirects)


def restore_ids():
    return frozenset({'current-claim-9', 'current-claim-4'})


def test_every_legacy_citation_resolves_through_its_redirect_after_restore():
    proof = validate_citation_restore(contract(), restored_current_ids=restore_ids(),
                                      admitted_release_hashes=admitted())
    assert proof.deletion_authorized is False and proof.reviewed_retirement_pr_required
    assert proof.resolved_legacy_ids == ('legacy-claim-1', 'legacy-claim-2')
    assert proof.release_hash == REL and len(proof.redirect_hash) == 64


def test_missing_redirect_and_dangling_target_fail_closed():
    only_one = contract(redirects=(CitationRedirect(legacy_id='legacy-claim-1', current_id='current-claim-9'),))
    with pytest.raises(PermissionError, match='has no redirect'):
        validate_citation_restore(only_one, restored_current_ids=restore_ids(),
                                  admitted_release_hashes=admitted())
    dangling = contract(redirects=(CitationRedirect(legacy_id='legacy-claim-1', current_id='current-claim-9'),
                                   CitationRedirect(legacy_id='legacy-claim-2', current_id='vanished')))
    with pytest.raises(PermissionError, match='missing from the restore'):
        validate_citation_restore(dangling, restored_current_ids=restore_ids(),
                                  admitted_release_hashes=admitted())


def test_duplicate_legacy_ids_duplicate_redirects_and_self_redirect_are_rejected():
    with pytest.raises(ValueError, match='duplicate legacy citation ids'):
        validate_citation_restore(contract(legacy_ids=('legacy-claim-1', 'legacy-claim-1')),
                                  restored_current_ids=restore_ids(), admitted_release_hashes=admitted())
    twice = (CitationRedirect(legacy_id='legacy-claim-1', current_id='current-claim-9'),
             CitationRedirect(legacy_id='legacy-claim-1', current_id='current-claim-4'),
             CitationRedirect(legacy_id='legacy-claim-2', current_id='current-claim-4'))
    with pytest.raises(ValueError, match='duplicate legacy citation redirect'):
        validate_citation_restore(contract(redirects=twice), restored_current_ids=restore_ids(),
                                  admitted_release_hashes=admitted())
    with pytest.raises(ValueError, match='must change identity'):
        CitationRedirect(legacy_id='legacy-claim-1', current_id='legacy-claim-1')


def test_unadmitted_release_empty_restore_and_empty_contract_fail_closed():
    with pytest.raises(PermissionError, match='admitted release'):
        validate_citation_restore(contract(), restored_current_ids=restore_ids(),
                                  admitted_release_hashes=frozenset())
    with pytest.raises(ValueError, match='restored citation population'):
        validate_citation_restore(contract(), restored_current_ids=frozenset(),
                                  admitted_release_hashes=admitted())
    with pytest.raises(ValueError):
        CitationRestoreContract(release_hash=REL, legacy_ids=(), redirects=())
    with pytest.raises(ValueError):
        CitationRestoreContract(release_hash=REL, legacy_ids=('legacy-claim-1',), redirects=())
    with pytest.raises(ValueError):
        CitationRestoreContract(release_hash=REL, legacy_ids=(),
                                redirects=(CitationRedirect(legacy_id='legacy-claim-1', current_id='current-claim-9'),))
