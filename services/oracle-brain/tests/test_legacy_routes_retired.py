import pytest
from uuid import uuid4
from oracle_brain.operating_model.retirement_checklist import (
    CitationRedirect, CitationRestoreContract, CitationRestoreProof, GovernedRetirement,
    LegacyRouteEntry, NoActiveConsumerCensus, RetentionPlan, RetirementChecklist,
    RollbackConditions, validate_citation_restore, validate_no_active_consumers,
    validate_retirement_checklist,
)

REL = 'a' * 64


def admitted():
    return frozenset({REL})


def census(**entry_changes):
    entry = LegacyRouteEntry(path='apps/workers/src/trigger/claim-extraction.ts', replaced=True,
                             active_callers=(), active_schedules=(), active_queues=())
    if entry_changes:
        entry = entry.model_copy(update=entry_changes)
    return NoActiveConsumerCensus(release_hash=REL, routes=(entry,))


def test_clean_census_proves_no_remaining_active_consumers():
    proof = validate_no_active_consumers(census(), proposed_paths=('apps/workers/src/trigger/claim-extraction.ts',),
                                         admitted_release_hashes=admitted())
    assert proof.deletion_authorized is False and proof.reviewed_retirement_pr_required
    assert proof.release_hash == REL and proof.paths == ('apps/workers/src/trigger/claim-extraction.ts',)
    assert len(proof.census_hash) == 64


@pytest.mark.parametrize('field', ['active_callers', 'active_schedules', 'active_queues'])
def test_any_remaining_consumer_schedule_or_queue_blocks_retirement(field):
    blocked = census(**{field: ('still-dispatching',)})
    with pytest.raises(PermissionError, match='active caller, schedule or queue'):
        validate_no_active_consumers(blocked, proposed_paths=('apps/workers/src/trigger/claim-extraction.ts',),
                                     admitted_release_hashes=admitted())


def test_unreplaced_route_and_absent_census_entry_fail_closed():
    with pytest.raises(PermissionError, match='not replaced'):
        validate_no_active_consumers(census(replaced=False),
                                     proposed_paths=('apps/workers/src/trigger/claim-extraction.ts',),
                                     admitted_release_hashes=admitted())
    with pytest.raises(PermissionError, match='absent from the active-consumer census'):
        validate_no_active_consumers(census(), proposed_paths=('packages/missing.ts',),
                                     admitted_release_hashes=admitted())


def test_unadmitted_release_self_asserted_census_and_bad_paths_are_rejected():
    with pytest.raises(PermissionError, match='admitted release'):
        validate_no_active_consumers(census(), proposed_paths=('apps/workers/src/trigger/claim-extraction.ts',),
                                     admitted_release_hashes=frozenset())
    with pytest.raises(ValueError, match='nonempty unique'):
        validate_no_active_consumers(census(), proposed_paths=(), admitted_release_hashes=admitted())
    with pytest.raises(ValueError, match='nonempty unique'):
        validate_no_active_consumers(census(), proposed_paths=('a.ts', 'a.ts'), admitted_release_hashes=admitted())
    for bad in ('/etc/passwd', 'packages/../../secret', 'packages\\old.ts'):
        with pytest.raises(ValueError, match='repository relative'):
            validate_no_active_consumers(census(), proposed_paths=(bad,), admitted_release_hashes=admitted())
    with pytest.raises(ValueError, match='duplicate legacy route'):
        validate_no_active_consumers(
            NoActiveConsumerCensus(release_hash=REL, routes=(census().routes[0], census().routes[0])),
            proposed_paths=('apps/workers/src/trigger/claim-extraction.ts',), admitted_release_hashes=admitted())


def citation_proof():
    contract = CitationRestoreContract(
        release_hash=REL, legacy_ids=('legacy-claim-1',),
        redirects=(CitationRedirect(legacy_id='legacy-claim-1', current_id='current-claim-9'),))
    return validate_citation_restore(contract, restored_current_ids=frozenset({'current-claim-9'}),
                                     admitted_release_hashes=admitted())


def test_retirement_checklist_binds_retention_rollback_consumers_and_citations():
    checklist = RetirementChecklist(
        release_hash=REL,
        retention=RetentionPlan(retention_window_days=30, restorable_state_exported=True,
                                stable_adoption_reached=True),
        rollback=RollbackConditions(final_watermark=7, legacy_writer_fencing_proved=True,
                                    rollback_rehearsal_hash='b' * 64),
        no_active_consumers=validate_no_active_consumers(
            census(), proposed_paths=('apps/workers/src/trigger/claim-extraction.ts',),
            admitted_release_hashes=admitted()),
        citation_restore=citation_proof(),
        governed=GovernedRetirement())
    proof = validate_retirement_checklist(checklist)
    assert proof['deletion_authorized'] is False and proof['reviewed_retirement_pr_required']
    assert proof['live_deployed_smoke_required'] and proof['live_proof_still_required']
    assert proof['retention_window_days'] == 30 and proof['final_watermark'] == 7
    assert proof['release_hash'] == REL and len(proof['checklist_hash']) == 64


def test_retirement_checklist_fails_closed_when_a_gate_is_incomplete():
    good = dict(
        release_hash=REL,
        retention=RetentionPlan(retention_window_days=30, restorable_state_exported=True,
                                stable_adoption_reached=True),
        rollback=RollbackConditions(final_watermark=7, legacy_writer_fencing_proved=True,
                                    rollback_rehearsal_hash='b' * 64),
        no_active_consumers=validate_no_active_consumers(
            census(), proposed_paths=('apps/workers/src/trigger/claim-extraction.ts',),
            admitted_release_hashes=admitted()),
        citation_restore=citation_proof(),
        governed=GovernedRetirement())
    with pytest.raises(PermissionError, match='restorable state export'):
        validate_retirement_checklist(RetirementChecklist(
            **{**good, 'retention': RetentionPlan(retention_window_days=30, restorable_state_exported=False,
                                                  stable_adoption_reached=True)}))
    with pytest.raises(PermissionError, match='stable primary adoption'):
        validate_retirement_checklist(RetirementChecklist(
            **{**good, 'retention': RetentionPlan(retention_window_days=30, restorable_state_exported=True,
                                                  stable_adoption_reached=False)}))
    with pytest.raises(PermissionError, match='legacy writer fencing'):
        validate_retirement_checklist(RetirementChecklist(
            **{**good, 'rollback': RollbackConditions(final_watermark=7, legacy_writer_fencing_proved=False,
                                                      rollback_rehearsal_hash='b' * 64)}))
    foreign = good['citation_restore'].model_copy(update={'release_hash': 'c' * 64})
    with pytest.raises(ValueError, match='citation proof binds a different release'):
        validate_retirement_checklist(RetirementChecklist(**{**good, 'citation_restore': foreign}))
    foreign = good['no_active_consumers'].model_copy(update={'release_hash': 'c' * 64})
    with pytest.raises(ValueError, match='consumer proof binds a different release'):
        validate_retirement_checklist(RetirementChecklist(**{**good, 'no_active_consumers': foreign}))
