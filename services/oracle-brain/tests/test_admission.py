"""S05 offline gate: assertion admission and confirmation authority.

AssertionLedger confirmation semantics are the S05 admission contract
(employee confirms own account only; company policy needs process owner;
unknown ownership is explicit; stale review returns a readable conflict).
That API is not on main yet, so those cases skip with the exact gap.
Document-scope admission (admit_document) that IS on main is asserted for real.
"""
from __future__ import annotations

import importlib
import importlib.util
from uuid import uuid4

import pytest

from oracle_brain.knowledge.admission import (
    AdmissionDecision,
    SourceDocument,
    admit_document,
)

_HAS_LEDGER = hasattr(importlib.import_module("oracle_brain.knowledge.admission"), "AssertionLedger")

_LEDGER_SKIP = (
    "AssertionLedger confirmation API absent on main (knowledge/admission.py "
    "has only SourceDocument/admit_document; AssertionLedger lives on the "
    "s05-confirmation-admission worktree and was not part of merged #133/#141). "
    "S05 admission gate keeps the named cases registered; they activate when "
    "AssertionLedger lands."
)


def _doc() -> SourceDocument:
    return SourceDocument(
        source_id=uuid4(),
        workspace_id=uuid4(),
        filename="synthetic.txt",
        content_type="text/plain",
        text="Invented synthetic document text for offline gate.",
    )


def test_admit_document_requires_intake_authority(monkeypatch):
    import oracle_brain.knowledge.admission as adm

    monkeypatch.setattr(adm, "has_authority", lambda *a, **k: False)
    decision = admit_document(
        _doc(),
        actor_id=uuid4(),
        database_url="postgresql://synthetic/offline",
        approvals=[],
    )
    assert isinstance(decision, AdmissionDecision)
    assert decision.admitted is False
    assert "intake" in decision.reason


def test_admit_document_requires_processing_approval(monkeypatch):
    import oracle_brain.knowledge.admission as adm

    monkeypatch.setattr(adm, "has_authority", lambda *a, **k: True)
    decision = admit_document(
        _doc(),
        actor_id=uuid4(),
        database_url="postgresql://synthetic/offline",
        approvals=[],
    )
    assert decision.admitted is False
    assert decision.reason  # visible refusal, not a silent drop


def test_admitted_document_decision_is_explicit(monkeypatch):
    import oracle_brain.knowledge.admission as adm
    from oracle_brain.provider_policy import ProcessingApproval

    monkeypatch.setattr(adm, "has_authority", lambda *a, **k: True)
    now = adm.datetime(2026, 6, 1, tzinfo=adm.timezone.utc)
    approval = ProcessingApproval.model_construct(
        provider="local-synthetic",
        account="test",
        endpoint="memory://local",
        data_classes=frozenset({"document_text"}),
        purpose="pilot_ingest",
        approved=True,
        approved_at=now,
        expires_at=now.replace(year=2027),
        terms_hash="0" * 64,
    ) if hasattr(ProcessingApproval, "model_construct") else None
    if approval is None:
        pytest.skip("ProcessingApproval constructor shape differs; cannot synthesize approval offline")
    decision = admit_document(
        _doc(),
        actor_id=uuid4(),
        database_url="postgresql://synthetic/offline",
        approvals=[approval],
        now=now,
    )
    assert decision.admitted is True
    assert decision.reason == ""


@pytest.mark.skipif(not _HAS_LEDGER, reason=_LEDGER_SKIP)
def test_employee_confirms_own_account():
    from oracle_brain.knowledge.admission import (
        KIND_EMPLOYEE_ACCOUNT, Actor, AssertionLedger, Ownership,
    )
    owner = uuid4()
    ledger = AssertionLedger()
    assertion = ledger.submit("alice", "account role is buyer", Ownership(KIND_EMPLOYEE_ACCOUNT, owner))
    result = ledger.confirm(assertion.assertion_id, actor=Actor(owner), based_on_version=1)
    assert result.admitted
    assert assertion.assertion_id in ledger.confirmed


@pytest.mark.skipif(not _HAS_LEDGER, reason=_LEDGER_SKIP)
def test_employee_cannot_confirm_another_account():
    from oracle_brain.knowledge.admission import (
        KIND_EMPLOYEE_ACCOUNT, Actor, AssertionLedger, Ownership,
    )
    owner = uuid4()
    ledger = AssertionLedger()
    assertion = ledger.submit("alice", "account role is buyer", Ownership(KIND_EMPLOYEE_ACCOUNT, owner))
    result = ledger.confirm(assertion.assertion_id, actor=Actor(uuid4()), based_on_version=1)
    assert not result.admitted
    assert "single employee" in result.reason


@pytest.mark.skipif(not _HAS_LEDGER, reason=_LEDGER_SKIP)
def test_company_policy_confirmation_requires_process_owner():
    from oracle_brain.knowledge.admission import (
        KIND_COMPANY_POLICY, Actor, AssertionLedger, Ownership,
    )
    ledger = AssertionLedger()
    assertion = ledger.submit("alice", "policy text", Ownership(KIND_COMPANY_POLICY, uuid4()))
    denied = ledger.confirm(assertion.assertion_id, actor=Actor(uuid4()), based_on_version=1)
    assert not denied.admitted
    assert "process-owner" in denied.reason
    allowed = ledger.confirm(assertion.assertion_id, actor=Actor(uuid4(), process_owner=True), based_on_version=1)
    assert allowed.admitted


@pytest.mark.skipif(not _HAS_LEDGER, reason=_LEDGER_SKIP)
def test_unknown_ownership_is_explicit_and_blocks_confirmation():
    from oracle_brain.knowledge.admission import (
        KIND_UNKNOWN, Actor, AssertionLedger, Ownership,
    )
    ledger = AssertionLedger()
    assertion = ledger.submit("alice", "text", Ownership(KIND_UNKNOWN))
    assert assertion.ownership.kind == KIND_UNKNOWN
    result = ledger.confirm(assertion.assertion_id, actor=Actor(uuid4(), process_owner=True), based_on_version=1)
    assert not result.admitted
    assert "unknown" in result.reason


@pytest.mark.skipif(not _HAS_LEDGER, reason=_LEDGER_SKIP)
def test_stale_review_returns_conflict_with_readable_diff():
    from oracle_brain.knowledge.admission import (
        KIND_EMPLOYEE_ACCOUNT, Actor, AssertionLedger, Ownership,
    )
    owner = uuid4()
    ledger = AssertionLedger()
    assertion = ledger.submit("alice", "account role is buyer", Ownership(KIND_EMPLOYEE_ACCOUNT, owner))
    ledger.correct(assertion.assertion_id, "account role is planner")
    result = ledger.confirm(assertion.assertion_id, actor=Actor(owner), based_on_version=1)
    assert not result.admitted
    assert result.conflict is not None
    assert result.conflict.your_version == 1
    assert result.conflict.current_version == 2
    assert "account role is buyer" in result.conflict.diff
    assert "account role is planner" in result.conflict.diff


@pytest.mark.skipif(not _HAS_LEDGER, reason=_LEDGER_SKIP)
def test_correction_keeps_prior_version_and_stales_dependent_recommendation():
    from oracle_brain.knowledge.admission import (
        KIND_EMPLOYEE_ACCOUNT, REC_ACTIVE, REC_STALE, AssertionLedger, Ownership,
    )
    owner = uuid4()
    ledger = AssertionLedger()
    assertion = ledger.submit("alice", "account role is buyer", Ownership(KIND_EMPLOYEE_ACCOUNT, owner))
    ledger.add_recommendation("buying", "Buyer handles POs", frozenset({assertion.assertion_id}))
    assert ledger.recommendations["buying"].status == REC_ACTIVE
    ledger.correct(assertion.assertion_id, "account role is planner")
    assert ledger.recommendations["buying"].status == REC_STALE
    assert [v.content for v in ledger.history[assertion.assertion_id]] == [
        "account role is buyer", "account role is planner",
    ]


@pytest.mark.skipif(not _HAS_LEDGER, reason=_LEDGER_SKIP)
def test_promotion_respects_authority_and_bumps_version():
    from oracle_brain.knowledge.admission import (
        KIND_COMPANY_POLICY, KIND_EMPLOYEE_ACCOUNT, Actor, AssertionLedger, Ownership,
    )
    employee = uuid4()
    ledger = AssertionLedger()
    assertion = ledger.submit("alice", "text", Ownership(KIND_EMPLOYEE_ACCOUNT, employee))
    denied = ledger.promote_to_company_policy(assertion.assertion_id, actor=Actor(employee), based_on_version=1)
    assert not denied.admitted
    assert "process-owner" in denied.reason
    promoted = ledger.promote_to_company_policy(
        assertion.assertion_id, actor=Actor(uuid4(), process_owner=True), based_on_version=1,
    )
    assert promoted.admitted
    assert ledger.assertions[assertion.assertion_id].ownership.kind == KIND_COMPANY_POLICY
