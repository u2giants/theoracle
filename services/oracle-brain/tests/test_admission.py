from uuid import uuid4

from oracle_brain.knowledge.admission import (
    KIND_COMPANY_POLICY,
    KIND_EMPLOYEE_ACCOUNT,
    KIND_UNKNOWN,
    REC_ACTIVE,
    REC_STALE,
    Actor,
    AssertionLedger,
    Ownership,
)


def _ledger_with(ownership):
    ledger = AssertionLedger()
    assertion = ledger.submit("alice", "account role is buyer", ownership)
    return ledger, assertion


def test_employee_confirms_own_account():
    owner = uuid4()
    ledger, assertion = _ledger_with(Ownership(KIND_EMPLOYEE_ACCOUNT, owner))
    result = ledger.confirm(
        assertion.assertion_id,
        actor=Actor(owner),
        based_on_version=1,
    )
    assert result.admitted
    assert assertion.assertion_id in ledger.confirmed


def test_employee_cannot_confirm_another_account():
    owner = uuid4()
    other = uuid4()
    ledger, assertion = _ledger_with(Ownership(KIND_EMPLOYEE_ACCOUNT, owner))
    result = ledger.confirm(
        assertion.assertion_id,
        actor=Actor(other),
        based_on_version=1,
    )
    assert not result.admitted
    assert "single employee" in result.reason
    assert assertion.assertion_id not in ledger.confirmed


def test_company_policy_confirmation_requires_process_owner():
    ledger, assertion = _ledger_with(Ownership(KIND_COMPANY_POLICY, uuid4()))
    denied = ledger.confirm(
        assertion.assertion_id,
        actor=Actor(uuid4()),
        based_on_version=1,
    )
    assert not denied.admitted
    assert "process-owner" in denied.reason
    allowed = ledger.confirm(
        assertion.assertion_id,
        actor=Actor(uuid4(), process_owner=True),
        based_on_version=1,
    )
    assert allowed.admitted


def test_unknown_ownership_is_explicit_and_blocks_confirmation():
    owner = uuid4()
    ledger, assertion = _ledger_with(Ownership(KIND_UNKNOWN))
    assert assertion.ownership.kind == KIND_UNKNOWN
    assert assertion.ownership.owner_id is None
    result = ledger.confirm(
        assertion.assertion_id,
        actor=Actor(owner, process_owner=True),
        based_on_version=1,
    )
    assert not result.admitted
    assert "unknown" in result.reason


def test_unknown_ownership_rejects_named_owner():
    try:
        Ownership(KIND_UNKNOWN, uuid4())
    except ValueError as exc:
        assert "must not name an owner" in str(exc)
    else:
        raise AssertionError("unknown ownership must not accept an owner_id")


def test_stale_review_returns_conflict_with_readable_diff():
    owner = uuid4()
    ledger, assertion = _ledger_with(Ownership(KIND_EMPLOYEE_ACCOUNT, owner))
    ledger.correct(assertion.assertion_id, "account role is planner")
    result = ledger.confirm(
        assertion.assertion_id,
        actor=Actor(owner),
        based_on_version=1,
    )
    assert not result.admitted
    assert result.conflict is not None
    conflict = result.conflict
    assert conflict.your_version == 1
    assert conflict.current_version == 2
    assert "account role is buyer" in conflict.diff
    assert "account role is planner" in conflict.diff


def test_current_version_review_is_not_stale():
    owner = uuid4()
    ledger, assertion = _ledger_with(Ownership(KIND_EMPLOYEE_ACCOUNT, owner))
    ledger.correct(assertion.assertion_id, "account role is planner")
    result = ledger.confirm(
        assertion.assertion_id,
        actor=Actor(owner),
        based_on_version=2,
    )
    assert result.admitted
    assert result.conflict is None


def test_correction_updates_dependent_recommendation_status():
    owner = uuid4()
    ledger, assertion = _ledger_with(Ownership(KIND_EMPLOYEE_ACCOUNT, owner))
    other = ledger.submit("bob", "account role is viewer", Ownership(KIND_EMPLOYEE_ACCOUNT, uuid4()))
    ledger.add_recommendation("buying", "Buyer handles POs", frozenset({assertion.assertion_id}))
    ledger.add_recommendation("viewing", "Viewer is read-only", frozenset({other.assertion_id}))
    assert ledger.recommendations["buying"].status == REC_ACTIVE
    ledger.correct(assertion.assertion_id, "account role is planner")
    assert ledger.recommendations["buying"].status == REC_STALE
    assert ledger.recommendations["viewing"].status == REC_ACTIVE


def test_correction_keeps_prior_version_in_history():
    owner = uuid4()
    ledger, assertion = _ledger_with(Ownership(KIND_EMPLOYEE_ACCOUNT, owner))
    ledger.correct(assertion.assertion_id, "account role is planner")
    versions = ledger.history[assertion.assertion_id]
    assert [v.content for v in versions] == [
        "account role is buyer",
        "account role is planner",
    ]
    assert [v.version for v in versions] == [1, 2]


def test_promotion_respects_authority_and_bumps_version():
    employee = uuid4()
    ledger, assertion = _ledger_with(Ownership(KIND_EMPLOYEE_ACCOUNT, employee))
    denied = ledger.promote_to_company_policy(
        assertion.assertion_id,
        actor=Actor(employee),
        based_on_version=1,
    )
    assert not denied.admitted
    assert "process-owner" in denied.reason
    promoted = ledger.promote_to_company_policy(
        assertion.assertion_id,
        actor=Actor(uuid4(), process_owner=True),
        based_on_version=1,
    )
    assert promoted.admitted
    current = ledger.assertions[assertion.assertion_id]
    assert current.ownership.kind == KIND_COMPANY_POLICY
    assert current.version == 2


def test_promotion_of_unknown_ownership_is_denied():
    ledger, assertion = _ledger_with(Ownership(KIND_UNKNOWN))
    result = ledger.promote_to_company_policy(
        assertion.assertion_id,
        actor=Actor(uuid4(), process_owner=True),
        based_on_version=1,
    )
    assert not result.admitted
    assert "unknown" in result.reason
