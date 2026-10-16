"""Pure fixture tests for S15 adoption rules; no live proof is claimed here."""

from uuid import uuid4

import pytest

from oracle_brain.release.cohort import (
    CohortMembership,
    CutoverPlan,
    IntakeQueue,
    Oracle2Mode,
    ReconciliationReport,
    SourceReconciliation,
    WatermarkBoundary,
    WriterOwnership,
    route,
)


def _cohort(**changes):
    w = uuid4()
    base = dict(workspace_id=w, cohort_name="pilot-week-1", member_ids=(uuid4(), uuid4()))
    base.update(changes)
    return CohortMembership(**base)


def _source(**changes):
    base = dict(
        source_id=uuid4(),
        inventory_count=3,
        accepted_count=2,
        quarantined_count=1,
        excluded_count=0,
        failed_count=0,
        content_hash_legacy="a" * 64,
        content_hash_replacement="a" * 64,
        permission_digest_legacy="b" * 64,
        permission_digest_replacement="b" * 64,
        approval_state_digest_legacy="c" * 64,
        approval_state_digest_replacement="c" * 64,
    )
    base.update(changes)
    return SourceReconciliation(**base)


def _boundary(workspace_id, **changes):
    base = dict(workspace_id=workspace_id, initial_watermark=10, final_watermark=42)
    base.update(changes)
    return WatermarkBoundary(**base)


def _report(boundary, *sources):
    return ReconciliationReport(boundary=boundary, sources=sources or (_source(),))


def _plan(cohort=None, boundary=None, steps=None):
    cohort = cohort or _cohort()
    boundary = boundary or _boundary(cohort.workspace_id)
    return CutoverPlan(
        workspace_id=cohort.workspace_id,
        cohort=cohort,
        steps=steps
        or (
            "pause_intake",
            "drain_legacy_writers",
            "record_final_watermark",
            "apply_through_watermark",
            "reconcile",
            "transfer_writer_ownership",
            "resume_intake",
        ),
        boundary=boundary,
    )


def test_cohort_membership_is_explicit_and_named():
    c = _cohort()
    assert c.cohort_name == "pilot-week-1"
    assert c.includes(c.member_ids[0])
    assert not c.includes(uuid4())
    with pytest.raises(ValueError, match="duplicate cohort member"):
        _cohort(member_ids=(c.member_ids[0], c.member_ids[0]))


def test_off_mode_always_routes_legacy():
    c = _cohort()
    assert route("off", c.member_ids[0], c) == "legacy"
    assert route("off", uuid4(), None) == "legacy"


def test_shadow_never_serves_employees_or_writes_old_records():
    c = _cohort()
    assert route("shadow", c.member_ids[0], c, employee_visible=False) == "shadow"
    with pytest.raises(PermissionError, match="employees"):
        route("shadow", c.member_ids[0], c, employee_visible=True)
    with pytest.raises(PermissionError, match="old records"):
        route("shadow", c.member_ids[0], c, employee_visible=False, writes_old_records=True)


def test_pilot_routes_only_named_cohort_members():
    c = _cohort()
    assert route("pilot", c.member_ids[1], c) == "oracle2"
    assert route("pilot", uuid4(), c) == "legacy"
    with pytest.raises(PermissionError, match="named cohort"):
        route("pilot", c.member_ids[0], None)


def test_primary_routes_everyone_and_requires_cohort_identity():
    c = _cohort()
    assert route("primary", uuid4(), c) == "oracle2"
    with pytest.raises(PermissionError, match="named cohort"):
        route("primary", uuid4(), None)


def test_watermark_boundary_is_monotonic_and_covers_through_w():
    w = uuid4()
    b = _boundary(w)
    assert b.covers(b.final_watermark)
    assert b.covers(b.initial_watermark)
    assert not b.covers(b.final_watermark + 1)
    with pytest.raises(ValueError, match="precedes initial"):
        _boundary(w, initial_watermark=5, final_watermark=4)


def test_reconciliation_counts_must_sum_to_inventory():
    with pytest.raises(ValueError, match="sum to inventory"):
        _source(inventory_count=3, accepted_count=1, quarantined_count=1, excluded_count=0, failed_count=0)


def test_reconciliation_hash_mismatch_counts_unexplained_differences():
    boundary = _boundary(uuid4())
    assert _report(boundary, _source()).unexplained_differences == 0
    mismatch = _report(boundary, _source(content_hash_replacement="d" * 64))
    assert mismatch.unexplained_differences == 1
    assert _report(boundary, _source(permission_digest_replacement="e" * 64)).unexplained_differences == 1
    assert (
        _report(
            boundary,
            _source(
                content_hash_replacement="d" * 64,
                permission_digest_replacement="e" * 64,
                approval_state_digest_replacement="f" * 64,
            ),
        ).unexplained_differences
        == 3
    )


def test_cutover_plan_requires_ordered_steps_and_matching_boundary():
    plan = _plan()
    assert plan.steps[0] == "pause_intake"
    assert plan.steps[-1] == "resume_intake"
    with pytest.raises(ValueError, match="out of order"):
        _plan(
            steps=(
                "drain_legacy_writers",
                "pause_intake",
                "record_final_watermark",
                "apply_through_watermark",
                "reconcile",
                "transfer_writer_ownership",
                "resume_intake",
            )
        )
    cohort = _cohort()
    other = _boundary(uuid4())
    with pytest.raises(ValueError, match="cross-workspace boundary"):
        _plan(cohort=cohort, boundary=other)


def test_ownership_transfer_requires_zero_unexplained_differences_at_same_w():
    plan = _plan()
    ok = _report(plan.boundary)
    assert plan.permits_ownership_transfer(ok)
    bad = _report(plan.boundary, _source(content_hash_replacement="d" * 64))
    assert not plan.permits_ownership_transfer(bad)
    moved = _report(_boundary(plan.workspace_id, final_watermark=plan.boundary.final_watermark + 1))
    assert not plan.permits_ownership_transfer(moved)


def test_writes_during_pause_are_queued_with_idempotency_keys():
    q = IntakeQueue(workspace_id=uuid4(), paused=True).model_copy(update={"paused": True})
    first = q.arrive("req-1", "a" * 64)
    again = q.arrive("req-1", "a" * 64)
    assert first is again
    assert len(q.receipts) == 1
    second = q.arrive("req-2", "b" * 64)
    assert second.idempotency_key == "req-2"
    assert len(q.receipts) == 2
    with pytest.raises(ValueError, match="different payload"):
        q.arrive("req-1", "c" * 64)


def test_expired_writer_generation_is_denied_and_paused_intake_queues():
    w = WriterOwnership(workspace_id=uuid4(), owner="legacy", generation=3)
    w.claim_write(3)
    with pytest.raises(PermissionError, match="expired writer generation"):
        w.claim_write(2)
    with pytest.raises(PermissionError, match="expired writer generation"):
        w.claim_write(4)
    paused = w.pause()
    with pytest.raises(PermissionError, match="paused"):
        paused.claim_write(3)


def test_transfer_is_atomic_after_catchup_and_abort_restores_legacy():
    plan = _plan()
    legacy = WriterOwnership(workspace_id=plan.workspace_id, owner="legacy", generation=3)
    paused = legacy.pause()
    ok = _report(plan.boundary)
    swapped = paused.transfer(ok, expected_generation=3)
    assert swapped.owner == "oracle2"
    assert swapped.generation == 4
    assert swapped.intake_open is True

    # Failure after catch-up (reconciliation) but before ownership transfer.
    caught_up = WriterOwnership(workspace_id=plan.workspace_id, owner="legacy", generation=7).pause()
    bad = _report(plan.boundary, _source(approval_state_digest_replacement="f" * 64))
    with pytest.raises(PermissionError, match="unexplained reconciliation differences"):
        caught_up.transfer(bad, expected_generation=7)
    restored = caught_up.abort_to_legacy(expected_generation=7)
    assert restored.owner == "legacy"
    assert restored.generation == 8
    assert restored.intake_open is True

    with pytest.raises(PermissionError, match="concurrently"):
        paused.transfer(ok, expected_generation=2)
    with pytest.raises(PermissionError, match="paused intake"):
        legacy.transfer(ok, expected_generation=3)


def test_cutover_workspace_binding_rejects_cross_workspace_cohort():
    cohort = _cohort()
    foreign = cohort.model_copy(update={"workspace_id": uuid4()})
    steps = (
        "pause_intake",
        "drain_legacy_writers",
        "record_final_watermark",
        "apply_through_watermark",
        "reconcile",
        "transfer_writer_ownership",
        "resume_intake",
    )
    with pytest.raises(ValueError, match="cross-workspace cohort"):
        CutoverPlan(
            workspace_id=cohort.workspace_id,
            cohort=foreign,
            steps=steps,
            boundary=_boundary(cohort.workspace_id),
        )
    with pytest.raises(ValueError, match="cross-workspace boundary"):
        CutoverPlan(
            workspace_id=cohort.workspace_id,
            cohort=cohort,
            steps=steps,
            boundary=_boundary(uuid4()),
        )
