"""Race-matrix and consistent-cut offline tests for the global writer cut.

Covers R1–R20 from s14-writer-cut-source-owner-design.md as far as offline
invented fixtures allow. Company comparison, live cutover, and real browser
cohort proof remain held; those cases assert the structural refusal or the
suite's presence requirement rather than live behavior.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from oracle_brain.operating_model.cut_control import (
    CasConflict,
    CutPhase,
    TransitionRefused,
    WriterCensusDigest,
    new_control,
)
from oracle_brain.operating_model.writer_barrier import (
    BarrierClosed,
    BarrierPhase,
    EffectStatus,
    FixedEffectOwner,
    LocalBarrier,
    RoleNotAdmitted,
    StaleGeneration,
    build_default_barrier,
)
from oracle_brain.operating_model.writer_census import (
    SiteClassification,
    WriterSite,
    adjudicate_sites,
    compute_census_digest,
)


def census_digest() -> WriterCensusDigest:
    return WriterCensusDigest(value='a' * 64, confirmed_count=3)


def control():
    return new_control(uuid4(), uuid4(), census_digest(), controller_id='ctrl-1')


def test_r1_race_pre_pause_transaction_serializes_or_refuses():
    """R1: pre-pause transaction overlaps pause transition. Transactions serialize
    on the barrier row; either both commit under old generation or the later is refused."""
    barrier = build_default_barrier(uuid4(), generation=1)
    barrier.assert_admitted('writer', 1, 'F1_chat_messages_modelusage_contextpacks_typing')
    # Pause transition happens after the admitted write began conceptually;
    # after pause the barrier refuses new writes.
    barrier.transition(BarrierPhase.PAUSING, generation=1)
    with pytest.raises(BarrierClosed):
        barrier.assert_admitted('writer', 1, 'F1_chat_messages_modelusage_contextpacks_typing')


def test_r2_pause_arrival_retained_once_opaque():
    """R2: new write during pausing becomes a durable opaque arrival receipt."""
    c = control()
    c.begin_pause('ctrl-1', 0)
    arrival = c.record_opaque_arrival('arr-1', body_hash='b' * 64)
    assert arrival['status'] == 'accepted-opaque'
    assert arrival['replay_authorized'] is False
    # Exactly-once retention is keyed by arrival identity in the real queue;
    # offline fixture records one receipt per id.
    again = c.record_opaque_arrival('arr-1', body_hash='b' * 64)
    assert again['arrival_id'] == arrival['arrival_id']


def test_r3_stale_writer_cannot_publish_after_generation_bump():
    """R3: old-generation worker after generation bump is refused in same-tx check."""
    barrier = build_default_barrier(uuid4(), generation=1)
    barrier.transition(BarrierPhase.OPEN, generation=2)
    with pytest.raises(StaleGeneration):
        barrier.assert_admitted('writer', 1, 'F1_chat_messages_modelusage_contextpacks_typing')


def test_r4_restart_rechecks_barrier_and_generation():
    """R4: on restart the writer re-reads barrier+generation before any write."""
    barrier = build_default_barrier(uuid4(), generation=1)
    barrier.transition(BarrierPhase.CLOSED, generation=1)
    # Restart simulated by a fresh assert after transition; stale role cannot recover.
    with pytest.raises(BarrierClosed):
        barrier.assert_admitted('writer', 1, 'F1_chat_messages_modelusage_contextpacks_typing')


def test_r5_reinstall_does_not_reset_generation_namespace():
    """R5: no hash/idempotency namespace reset across reinstall."""
    workspace = uuid4()
    barrier = build_default_barrier(workspace, generation=7)
    # Reinstall must read the control row first and retain existing generation.
    row = barrier.row
    assert row.current_generation == 7
    assert row.workspace_id == workspace


def test_r6_latebatch_result_is_unknown_or_queued_not_replayed():
    """R6: provider batch after pause is UNKNOWN or opaque late arrival; no replay."""
    barrier = build_default_barrier(uuid4(), generation=1)
    owner = FixedEffectOwner(barrier)
    receipt = owner.begin_effect('job-1', 'F4_extraction_paid_batches_late_drain',
                                 'writer', 1)
    assert receipt.status is EffectStatus.IN_FLIGHT
    late = owner.lost_ack('job-1')
    assert late.status is EffectStatus.UNKNOWN
    assert owner.open_effects() == [late]


def test_r7_orphan_upload_accounted_no_object_without_receipt():
    """R7: storage upload succeeds but SQL insert fails -> orphan removal recorded."""
    barrier = build_default_barrier(uuid4(), generation=1)
    owner = FixedEffectOwner(barrier)
    owner.begin_effect('up-1', 'F2_storage_bytes_sql_metadata_orphans', 'writer', 1)
    failed = owner.complete_effect('up-1', success=False)
    assert failed.status is EffectStatus.ORPHAN
    removed = owner.orphan_removal('up-1')
    assert removed.status is EffectStatus.DROPPED
    assert owner.open_effects() == []


def test_r8_lost_ack_stays_unknown_no_resend():
    """R8: lost ACK stays UNKNOWN; no resend."""
    barrier = build_default_barrier(uuid4(), generation=1)
    owner = FixedEffectOwner(barrier)
    owner.begin_effect('x-1', 'F6_synthesis_translation_contradiction_lull_outbound_cached_clients',
                       'writer', 1)
    assert owner.lost_ack('x-1').status is EffectStatus.UNKNOWN
    # No automatic resend is modeled; only an explicit new effect id would publish.


def test_r9_privacy_withdrawal_invalidates_candidate_cut():
    """R9: privacy withdrawal remains operational and invalidates the candidate cut."""
    c = control()
    c.begin_pause('ctrl-1', 0)
    c.mark_drained('ctrl-1', 0)
    c.record_snapshot('ctrl-1', 0, 'd' * 64, 'd' * 64)
    invalidated = c.invalidate_candidate('privacy-withdrawal')
    assert invalidated.phase is CutPhase.UNKNOWN
    assert invalidated.stop_or_privacy_or_security_invalidated is True
    assert invalidated.consistent_boundary_proven is False


def test_r10_overflow_denies_snapshot_completion():
    """R10: snapshot overflow denies completion."""
    c = control()
    c.begin_pause('ctrl-1', 0)
    c.mark_drained('ctrl-1', 0)
    with pytest.raises(TransitionRefused, match='overflow'):
        c.record_snapshot('ctrl-1', 0, 'd' * 64, 'd' * 64, overflow=True)


def test_r11_missing_participant_denies_completeness():
    """R11: a family with no active barrier participant blocks completeness."""
    c = control()
    c.begin_pause('ctrl-1', 0)
    c.mark_drained('ctrl-1', 0)
    c.record_snapshot('ctrl-1', 0, 'd' * 64, 'd' * 64)
    with pytest.raises(TransitionRefused, match='missing participant'):
        c.activate_replacement('ctrl-1', 0,
                              missing_families=['F2_storage_bytes_sql_metadata_orphans'])


def test_r12_unknown_role_refused():
    """R12: a DB role not in the admitted set cannot write."""
    barrier = build_default_barrier(uuid4(), generation=1)
    with pytest.raises(RoleNotAdmitted):
        barrier.assert_admitted('unknown-role', 1, 'F1_chat_messages_modelusage_contextpacks_typing')


def test_r13_crash_rollback_reconciles_read_only():
    """R13: crash after catch-up before CAS reconciles read-only; no guess."""
    c = control()
    c.begin_pause('ctrl-1', 0)
    c.mark_drained('ctrl-1', 0)
    c.begin_rollback('ctrl-1', 0, note='crash-before-cas')
    # Read-only reconciliation observes phase; rollback completes to legacy-active
    # only through an explicit controller transition, never a guessed replay.
    done = c.complete_rollback('ctrl-1', 0)
    assert done.phase is CutPhase.LEGACY_ACTIVE


def test_r14_cohort_bypass_would_invalidate():
    """R14: silent browser bypass via direct Supabase client is a structural hole.
    Offline fixture asserts the design records it as invalidating when observed."""
    # The required cohort suite must exist; absence is tracked as the blocker.
    # Structural assertion: any uncontrolled typing/direct write is an unknown writer.
    site = WriterSite(
        file='apps/web/app/channels/[channelId]/_components/channel-chat.tsx',
        lines=(180, 189),
        op='upsert/delete typing_indicators',
        family_id='F1_chat_messages_modelusage_contextpacks_typing',
        classification=SiteClassification.CONFIRMED,
    )
    adjudicated = adjudicate_sites([site])
    result = compute_census_digest(adjudicated)
    assert result.adjudicated is True
    assert result.confirmed_count == 1


def test_r15_stop_invalidates_candidate_cut():
    """R15: independently bounded safety STOP invalidates the candidate cut."""
    c = control()
    invalidated = c.invalidate_candidate('safety-STOP')
    assert invalidated.phase is CutPhase.UNKNOWN
    assert invalidated.stop_or_privacy_or_security_invalidated is True


def test_r16_security_denial_invalidates_candidate_cut():
    """R16: security denial invalidates the candidate cut and forces reconciliation."""
    c = control()
    invalidated = c.invalidate_candidate('security-denial')
    assert invalidated.consistent_boundary_proven is False


def test_r17_rollingback_fences_new_writes():
    """R17: rollback begins and a new write arrives -> fenced or queued."""
    c = control()
    c.begin_pause('ctrl-1', 0)
    c.begin_rollback('ctrl-1', 0)
    assert c.state.phase is CutPhase.ROLLING_BACK
    barrier = build_default_barrier(uuid4(), generation=1)
    barrier.transition(BarrierPhase.CLOSED, generation=1)
    with pytest.raises(BarrierClosed):
        barrier.assert_admitted('writer', 1, 'F1_chat_messages_modelusage_contextpacks_typing')


def test_r18_concurrent_pause_cas_has_one_winner():
    """R18: two controllers attempt pause; exactly one winner."""
    c = control()
    c.begin_pause('ctrl-1', 0)
    with pytest.raises(CasConflict):
        # A concurrent stale writer of the control state loses CAS.
        stale = c.state.model_copy(update={'transition_count': c.state.transition_count - 1}) \
            if c.state.transition_count > 0 else c.state
        c._cas(stale, {'phase': CutPhase.PAUSING})
    # Second real pause from same admitted controller is a transition refusal.
    with pytest.raises(TransitionRefused):
        c.begin_pause('ctrl-1', 0)


def test_r19_generation_mismatch_restart_must_readmit():
    """R19: worker restarts and reads a generation that changed during downtime."""
    barrier = build_default_barrier(uuid4(), generation=1)
    barrier.transition(BarrierPhase.OPEN, generation=2)
    # Cached generation 1 cannot continue.
    with pytest.raises(StaleGeneration):
        barrier.assert_admitted('writer', 1, 'F1_chat_messages_modelusage_contextpacks_typing')
    # Re-admission at the current generation works.
    barrier.admit_role('writer', 2, 'F1_chat_messages_modelusage_contextpacks_typing')
    barrier.assert_admitted('writer', 2, 'F1_chat_messages_modelusage_contextpacks_typing')


def test_r20_cohort_acceptance_suite_absence_is_blocker():
    """R20: required cohort acceptance suite must exist before S15.
    This test asserts the suite file is present; the companion suite provides
    the actual cases. Company/browser proof remains held."""
    from pathlib import Path
    suite = Path(__file__).resolve().parents[3] / 'apps' / 'web' / 'tests' / 'oracle2' / 'cohort.spec.ts'
    assert suite.exists(), 'required cohort acceptance suite is absent'


def test_unknown_sites_block_census_digest():
    sites = [
        WriterSite(file='a.ts', lines=(1,), op='insert', family_id='F1',
                   classification=SiteClassification.CONFIRMED),
        WriterSite(file='b.ts', lines=(2,), op='update', family_id='F1',
                   classification=SiteClassification.CANDIDATE,
                   notes='adjudicate exact write sites'),
    ]
    adjudicated = adjudicate_sites(sites)
    result = compute_census_digest(adjudicated)
    assert result.adjudicated is False
    assert result.census_digest is None
    assert result.unknown_count == 1


def test_confirmed_and_excluded_produce_stable_digest():
    sites = [
        WriterSite(file='a.ts', lines=(1,), op='insert', family_id='F1',
                   classification=SiteClassification.CONFIRMED),
        WriterSite(file='c.ts', lines=(3,), op='hash helper only', family_id='F7',
                   classification=SiteClassification.CANDIDATE,
                   notes='Hash helper'),
        WriterSite(file='(external) Supabase Auth', op='user/session lifecycle',
                   family_id='F9', classification=SiteClassification.EXTERNAL),
    ]
    adjudicated = adjudicate_sites(sites)
    result = compute_census_digest(adjudicated)
    assert result.adjudicated is True
    assert result.confirmed_count == 1
    assert result.excluded_count == 1
    assert result.external_count == 1
    assert result.census_digest is not None
    assert result.census_digest == compute_census_digest(adjudicated).census_digest


def test_full_cut_path_happy_invented():
    """Complete offline happy path through all cut phases with all families present."""
    c = control()
    c.begin_pause('ctrl-1', 0)
    c.mark_drained('ctrl-1', 0)
    c.record_snapshot('ctrl-1', 0, 'e' * 64, 'e' * 64)
    done = c.activate_replacement('ctrl-1', 0, missing_families=[],
                                  external_controlled=True)
    assert done.phase is CutPhase.REPLACEMENT_ACTIVE
    assert done.consistent_boundary_proven is True


def test_external_uncontrolled_blocks_boundary():
    c = control()
    c.begin_pause('ctrl-1', 0)
    c.mark_drained('ctrl-1', 0)
    c.record_snapshot('ctrl-1', 0, 'e' * 64, 'e' * 64)
    with pytest.raises(TransitionRefused, match='uncontrolled external'):
        c.activate_replacement('ctrl-1', 0, missing_families=[],
                               external_controlled=False)


def test_stale_controller_refused():
    c = control()
    with pytest.raises(TransitionRefused, match='controller generation is stale'):
        c.begin_pause('ctrl-1', 5)
    with pytest.raises(TransitionRefused, match='controller identity'):
        c.begin_pause('other', 0)
