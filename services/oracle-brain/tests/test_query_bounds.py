"""Offline gate test retained from the building-block branch. Invented/synthetic only.

Import guard: oracle_brain.retrieval.packing is required; skip with reason when absent.
"""
from __future__ import annotations

import importlib.util

import pytest

_REQUIRED = 'oracle_brain.retrieval.packing'
try:
    _spec = importlib.util.find_spec(_REQUIRED)
except ModuleNotFoundError:
    _spec = None
if _spec is None:
    pytest.skip(
        'S09 retrieval packing/bounds implementation absent on main (not built). Named offline gate test retained with the s09-connected-answers branch assertions; activates when retrieval.packing lands.',
        allow_module_level=True,
    )

"""S09 query bounds: role/workspace access filter, history span, coverage honesty."""


from uuid import UUID, uuid4

import pytest

from oracle_brain.retrieval.packing import (
    AssembledAnswer,
    CoverageBounds,
    SpanCandidate,
    assemble_answer,
    filter_by_access,
    filter_by_history,
)
from oracle_brain.retrieval.planner import AccessBounds, HistorySpan
from retrieval_testkit import ACTOR, host_reader
from oracle_brain.retrieval.packing import assemble_answer as _raw_assemble


def assemble_answer(**fields):
    fields.setdefault("current_source_reader", host_reader(fields["spans"]))
    return _raw_assemble(**fields)


def _span(
    span_id: str,
    *,
    workspace: UUID | None = None,
    roles: tuple[str, ...] = ("analyst",),
    revision: int = 1,
    supports: tuple[str, ...] = ("claim.a",),
    contradicts: tuple[str, ...] = (),
) -> SpanCandidate:
    return SpanCandidate(
        span_id=span_id, workspace_id=workspace or uuid4(), source_id=uuid4(),
        revision=revision, quote=f"evidence for {span_id}", roles=roles,
        supports=supports, contradicts=contradicts,
    )


@pytest.fixture()
def workspace() -> UUID:
    return uuid4()


@pytest.fixture()
def access(workspace: UUID) -> AccessBounds:
    return AccessBounds(
        role="analyst", actor_id=ACTOR, workspace_id=workspace,
        allowed_workspace_ids=(workspace,),
    )


def test_access_filter_drops_other_workspace_and_other_role(workspace, access):
    mine = _span("mine", workspace=workspace)
    other_ws = _span("other-ws", workspace=uuid4())
    other_role = _span("other-role", workspace=workspace, roles=("viewer",))
    kept = filter_by_access((mine, other_ws, other_role), access)
    assert [s.span_id for s in kept] == ["mine"]


def test_access_filter_allows_second_workspace_when_bounds_permit(workspace):
    second = uuid4()
    bounds = AccessBounds(
        role="analyst", actor_id=ACTOR, workspace_id=workspace,
        allowed_workspace_ids=(workspace, second),
    )
    spans = (_span("a", workspace=workspace), _span("b", workspace=second),
             _span("c", workspace=uuid4()))
    assert {s.span_id for s in filter_by_access(spans, bounds)} == {"a", "b"}


def test_history_filter_keeps_only_closed_window(workspace, access):
    spans = (
        _span("r1", workspace=workspace, revision=1),
        _span("r2", workspace=workspace, revision=2),
        _span("r4", workspace=workspace, revision=4),
    )
    history = HistorySpan(revision_from=2, revision_to=3)
    kept = filter_by_history(spans, history)
    assert [s.span_id for s in kept] == ["r2"]


def test_missing_evidence_abstains(access):
    answer = assemble_answer(
        question="Who releases the kit?", mode="local", spans=(), access=access,
    )
    assert answer.state == "abstained"
    assert answer.claim is None and answer.citations == ()
    assert any("Missing evidence" in c for c in answer.caveats)


def test_out_of_bounds_evidence_abstains(access, workspace):
    answer = assemble_answer(
        question="Who releases the kit?", mode="local",
        spans=(_span("hidden", workspace=uuid4()),), access=access,
    )
    assert answer.state == "abstained" and answer.citations == ()


def test_historical_without_span_asks_clarification(access, workspace):
    answer = assemble_answer(
        question="What changed in the release queue?", mode="historical",
        spans=(_span("r1", workspace=workspace),), access=access,
    )
    assert answer.state == "needs_clarification"
    assert "revision range" in answer.clarifying_question
    assert answer.claim is None and answer.citations == ()


def test_historical_answer_cites_only_in_window(access, workspace):
    history = HistorySpan(revision_from=1, revision_to=2)
    answer = assemble_answer(
        question="What changed in the release queue?", mode="historical",
        spans=(
            _span("r1", workspace=workspace, revision=1),
            _span("r3", workspace=workspace, revision=3),
        ),
        access=access, history=history, claim="The queue added a signed proof step.",
    )
    assert answer.state == "answered"
    assert answer.citations == ("r1",)


def test_global_without_coverage_bounds_abstains(access, workspace):
    answer = assemble_answer(
        question="Company-wide, who releases kits?", mode="global",
        spans=(_span("s1", workspace=workspace),), access=access,
        claim="Every process uses the warehouse lead.",
    )
    assert answer.state == "abstained"
    assert any("coverage bounds" in c for c in answer.caveats)
    assert answer.coverage is None


def test_global_partial_coverage_never_claims_complete_total(access, workspace):
    coverage = CoverageBounds(declared_population=4, represented=2, complete=False)
    answer = assemble_answer(
        question="Company-wide, how many processes use kits?", mode="global",
        spans=(_span("s1", workspace=workspace), _span("s2", workspace=workspace)),
        access=access, coverage=coverage,
        claim="Two processes use kits.",
    )
    assert answer.state == "answered" and answer.coverage == coverage
    assert "partial_coverage" in answer.labels
    assert any("not a complete aggregate total" in c for c in answer.caveats)
    assert any("2 of 4" in c for c in answer.caveats)


def test_global_complete_coverage_states_bounds(access, workspace):
    coverage = CoverageBounds(declared_population=2, represented=2, complete=True)
    answer = assemble_answer(
        question="Company-wide, how many processes use kits?", mode="global",
        spans=(_span("s1", workspace=workspace),), access=access,
        coverage=coverage, claim="Both processes use kits.",
    )
    assert answer.state == "answered"
    assert "partial_coverage" not in answer.labels
    assert any("Coverage bounds: 2 of 2" in c for c in answer.caveats)


def test_contradiction_is_labeled_and_retained(access, workspace):
    answer = assemble_answer(
        question="Who releases the kit?", mode="local",
        spans=(
            _span("pro", workspace=workspace, supports=("claim.release",)),
            _span("con", workspace=workspace, supports=(), contradicts=("claim.release",)),
        ),
        access=access, claim="The warehouse lead releases the kit.",
    )
    assert answer.state == "answered"
    assert "contradiction" in answer.labels
    assert set(answer.citations) == {"pro", "con"}
    assert any("Contradictory evidence retained" in c for c in answer.caveats)
    assert any("unsupported causal links remain labeled" in c for c in answer.caveats)


def test_answer_without_claim_abstains_even_with_evidence(access, workspace):
    answer = assemble_answer(
        question="Who releases the kit?", mode="local",
        spans=(_span("s1", workspace=workspace),), access=access,
    )
    assert answer.state == "abstained" and answer.citations == ()


def test_coverage_bounds_reject_oversize_representation():
    with pytest.raises(ValueError):
        CoverageBounds(declared_population=2, represented=3, complete=False)


def test_complete_coverage_requires_full_representation():
    with pytest.raises(ValueError):
        CoverageBounds(declared_population=3, represented=2, complete=True)


def test_history_only_applies_to_historical_mode(access, workspace):
    with pytest.raises(ValueError):
        assemble_answer(
            question="Who releases the kit?", mode="local",
            spans=(_span("s1", workspace=workspace),), access=access,
            history=HistorySpan(revision_from=1, revision_to=1),
        )


def test_answered_requires_citations(access):
    with pytest.raises(ValueError):
        AssembledAnswer(
            state="answered", mode="local", question="q", claim="c",
            citations=(),
        )


def test_denied_claim_text_cannot_be_laundered_by_unrelated_allowed_span(access, workspace):
    allowed = _span('allowed', workspace=workspace)
    hidden = _span('hidden', workspace=uuid4())
    answer = _raw_assemble(question='What evidence is available?', mode='local',
                           spans=(allowed, hidden), access=access,
                           claim='DENIED SECRET DERIVED CLAIM',
                           current_source_reader=host_reader((allowed, hidden)))
    assert answer.state == 'answered'
    assert answer.claim == allowed.quote and answer.citations == ('allowed',)
    assert len(answer.dependencies) == 1
    assert answer.dependencies[0].source_id == allowed.source_id
    assert 'DENIED SECRET' not in answer.model_dump_json()


def test_final_current_access_prunes_revoked_span_but_keeps_allowed_answer(access, workspace):
    allowed = _span('allowed', workspace=workspace)
    revoked = _span('revoked', workspace=workspace, contradicts=('hidden-sensitive-label',))
    answer = _raw_assemble(question='What evidence is available?', mode='connected',
                           spans=(allowed, revoked), access=access, claim='untrusted cached claim',
                           current_source_reader=host_reader((allowed, revoked),
                                                              denied_sources={revoked.source_id}))
    assert answer.claim == allowed.quote
    assert answer.citations == ('allowed',)
    assert 'revoked' not in answer.model_dump_json()
    assert 'hidden-sensitive-label' not in answer.model_dump_json()


def test_missing_current_proof_abstains_even_with_accessible_candidate(access, workspace):
    answer = _raw_assemble(question='Question?', mode='local', spans=(_span('s', workspace=workspace),),
                           access=access, claim='caller statement')
    assert answer.state == 'abstained' and answer.claim is None


@pytest.mark.parametrize('damage', ['quote', 'workspace', 'revision', 'actor', 'forged', 'replay', 'expired'])
def test_content_identity_and_principal_current_proofs_are_required(access, workspace, damage):
    from oracle_brain.retrieval.packing import CurrentSourceAccess
    import time
    original = _span('s', workspace=workspace)
    candidate = original
    reader = host_reader((original,))
    if damage == 'quote':
        candidate = original.model_copy(update={'quote': 'fabricated inaccessible information'})
    elif damage == 'workspace':
        candidate = original.model_copy(update={'workspace_id': uuid4()})
    elif damage == 'revision':
        candidate = original.model_copy(update={'revision': 2})
    else:
        valid_reader = reader
        def reader(dep, bounds, challenge):
            proof = valid_reader(dep, bounds, challenge)
            if damage == 'actor':
                return proof.model_copy(update={'actor_id': uuid4()})
            if damage == 'forged':
                return proof.model_copy(update={'mac': '00' * 64})
            if damage == 'replay':
                return proof.model_copy(update={'challenge': 'prior-challenge'})
            return proof.model_copy(update={'valid_until': time.time() - 1})
    answer = _raw_assemble(question='Question?', mode='local', spans=(candidate,), access=access,
                           claim='caller claim', current_source_reader=reader)
    assert answer.state == 'abstained' and not answer.dependencies


def test_current_proof_is_requested_for_every_retained_dependency(access, workspace):
    first, second = _span('one', workspace=workspace), _span('two', workspace=workspace)
    requests = []
    current = host_reader((first, second))
    def reader(dep, bounds, challenge):
        requests.append((dep, challenge))
        return current(dep, bounds, challenge)
    answer = _raw_assemble(question='Question?', mode='connected', spans=(first, second),
                           access=access, claim='caller claim', current_source_reader=reader)
    assert answer.claim == first.quote + '\n' + second.quote
    assert tuple(dep for dep, _ in requests) == answer.dependencies
    assert len({challenge for _, challenge in requests}) == 2


def test_untrusted_relation_labels_cannot_echo_denied_claim_text(access, workspace):
    first = _span('one', workspace=workspace, supports=('DENIED SECRET',))
    second = _span('two', workspace=workspace, supports=(), contradicts=('DENIED SECRET',))
    answer = _raw_assemble(question='Available evidence?', mode='connected', spans=(first, second),
                           access=access, claim='DENIED SECRET',
                           current_source_reader=host_reader((first, second)))
    assert answer.state == 'answered' and 'contradiction' in answer.labels
    assert 'DENIED SECRET' not in answer.model_dump_json()
