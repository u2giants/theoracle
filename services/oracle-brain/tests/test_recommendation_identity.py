"""Exact revision/feedback identity and bounded non-authoritative advice proposals."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from test_recommendation_contract import (
    END, alternative, forecast, hours, money, observation, recommendation, revision,
)
from oracle_brain.operating_model.consultant.calculations import Forecast
from oracle_brain.operating_model.consultant.recommendations import (
    MAX_FEEDBACK, MAX_ID, MAX_MEASURES, MAX_OPTIONS, MAX_REFS, MAX_TEXT,
    CostedMeasure, DecisionFeedback, EvidenceRevision, FeedbackLoop, ImprovementClaim, Recommendation,
)


def bound():
    rec = recommendation(evidence=revision('ev:a', 'ev:b', 'ev:c'))
    workspace, actor = uuid4(), uuid4()
    loop = FeedbackLoop(rec.recommendation_id, expected_workspace_id=workspace,
                        expected_actor_id=actor, current_recommendation=rec)
    return rec, loop


def decision(loop, choice='reject', reason='中文：本季度没有足够人手。', **updates):
    fields = dict(recommendation_id=loop.recommendation_id, decision=choice, reason=reason,
        workspace_id=loop.expected_workspace_id, actor_id=loop.expected_actor_id,
        recommendation_hash=loop.current_recommendation.content_hash())
    fields.update(updates)
    return DecisionFeedback(**fields)


@pytest.mark.parametrize('current', [EvidenceRevision('rev:1', ('ev:b', 'ev:a')),
    EvidenceRevision('rev:1', ('ev:a', 'ev:c')), EvidenceRevision('rev:1', ('ev:a', 'ev:b'), 'f' * 64)])
def test_same_revision_label_cannot_hide_changed_order_refs_or_seal(current):
    rec = recommendation()
    assert rec.evidence.revision_id == current.revision_id
    assert rec.is_stale(current) is True


def test_exact_recommendation_content_hash_changes_with_scope_options_and_evidence():
    rec = recommendation()
    assert rec.content_hash() == replace(rec).content_hash()
    assert rec.content_hash() != replace(rec, scope_note='A different source population').content_hash()
    option = replace(rec.options[1], downstream_costs=(CostedMeasure('capacity_estimate', hours('2')),))
    assert rec.content_hash() != replace(rec, options=(rec.options[0], option)).content_hash()
    assert rec.content_hash() != replace(rec, evidence=EvidenceRevision('rev:1', ('ev:a', 'ev:b'), 'f' * 64)).content_hash()


@pytest.mark.parametrize('bad', [None, '', '   ', 'x' * (MAX_TEXT + 1), 1, False, []])
def test_scope_is_required_bounded_and_nonblank(bad):
    with pytest.raises(ValueError, match='scope note'):
        replace(recommendation(), scope_note=bad)


def test_omitted_scope_is_not_a_complete_recommendation():
    rec = recommendation()
    with pytest.raises(ValueError, match='scope note'):
        Recommendation(rec.recommendation_id, rec.lens, rec.evidence, rec.options, rec.opposing_evidence)


@pytest.mark.parametrize('bad', [None, object(), {}, 'option', 1, False])
def test_alternative_types_are_checked_before_any_option_field_is_read(bad):
    with pytest.raises(ValueError, match='validated alternatives'):
        replace(recommendation(), options=(alternative('keep', is_no_change=True), bad))


def test_downstream_omission_is_explicit_unknown_never_zero_or_empty():
    option = alternative()
    assert option.downstream_costs == (CostedMeasure('missing'),)
    assert option.downstream_costs[0].measure is None
    assert replace(option, downstream_costs=()).downstream_costs == (CostedMeasure('missing'),)
    zero = alternative(downstream_costs=(CostedMeasure('actual_cost', money('0')),))
    assert zero.downstream_costs[0].measure.amount == Decimal('0')
    assert zero.downstream_costs != option.downstream_costs


def test_reference_option_measure_and_feedback_populations_are_bounded():
    with pytest.raises(ValueError, match='bounded'):
        EvidenceRevision('r', tuple(f'e:{n}' for n in range(MAX_REFS + 1)))
    with pytest.raises(ValueError, match='no-change plus'):
        replace(recommendation(), options=tuple(alternative(f'option:{n}', is_no_change=n == 0)
                                                for n in range(MAX_OPTIONS + 1)))
    with pytest.raises(ValueError, match='costed measure'):
        alternative(downstream_costs=(CostedMeasure('missing'),) * (MAX_MEASURES + 1))
    with pytest.raises(ValueError, match='history'):
        FeedbackLoop('rec:1', history=(DecisionFeedback('rec:1', 'defer', 'Later'),) * (MAX_FEEDBACK + 1))
    with pytest.raises(ValueError, match='canonical'):
        EvidenceRevision('r' * (MAX_ID + 1), ('e',))


def test_legacy_unbound_feedback_can_be_displayed_but_cannot_open_repair():
    feedback = DecisionFeedback('rec:1', 'reject', '中文理由仍是普通反馈。')
    loop = FeedbackLoop('rec:1').record(feedback)
    assert loop.history[0].reason == feedback.reason
    assert feedback.actor_id is None and feedback.workspace_id is None
    assert feedback.event_id is None and feedback.recommendation_hash is None
    assert loop.can_repair() is False
    with pytest.raises(ValueError, match='repair'):
        loop.repaired()


@pytest.mark.parametrize('latest', ['accept', 'defer'])
def test_only_latest_current_reject_can_propose_one_repair(latest):
    rec, loop = bound()
    rejected = loop.record(decision(loop))
    assert rejected.can_repair() is True
    changed = rejected.record(decision(loop, latest, reason='先暂缓；稍后再评估。'))
    assert changed.can_repair() is False
    with pytest.raises(ValueError, match='repair'):
        changed.repaired()
    repaired = rejected.repaired()
    assert repaired.repairs_used == 1 and repaired.can_repair() is False
    assert rec.content_hash() == loop.current_recommendation.content_hash()


def test_duplicate_exact_feedback_is_idempotent_even_after_later_decision():
    _, loop = bound()
    rejected = decision(loop, event_id='event:reject')
    first = loop.record(rejected)
    assert first.record(rejected) is first
    accepted = first.record(decision(loop, 'accept', event_id='event:accept'))
    assert accepted.record(rejected) is accepted and accepted.can_repair() is False
    assert len(accepted.history) == 2
    reconstructed = replace(loop, history=(rejected, accepted.history[-1], rejected))
    assert reconstructed.history == accepted.history and reconstructed.can_repair() is False


def test_explicit_same_event_id_with_changed_decision_or_reason_refuses():
    _, loop = bound()
    feedback = decision(loop, event_id='event:1')
    first = loop.record(feedback)
    for changed in (replace(feedback, decision='accept'), replace(feedback, reason='不同的原因')):
        with pytest.raises(ValueError, match='event id collision'):
            first.record(changed)


@pytest.mark.parametrize('change', ['workspace', 'actor', 'hash', 'recommendation'])
def test_foreign_actor_workspace_or_exact_recommendation_binding_refuses(change):
    _, loop = bound()
    updates = {'workspace': dict(workspace_id=uuid4()), 'actor': dict(actor_id=uuid4()),
               'hash': dict(recommendation_hash='f' * 64),
               'recommendation': dict(recommendation_id='foreign-rec')}[change]
    with pytest.raises(ValueError):
        loop.record(decision(loop, **updates))


def test_stale_same_label_feedback_cannot_repair_new_advice():
    old, loop = bound()
    feedback = decision(loop)
    new = replace(old, evidence=EvidenceRevision('rev:1', ('ev:c', 'ev:b', 'ev:a')))
    current_view = replace(loop, current_recommendation=new)
    with pytest.raises(ValueError, match='expected current server scope'):
        current_view.record(feedback)
    assert current_view.can_repair() is False


def test_bound_envelope_without_expected_server_scope_is_not_actor_authority():
    _, loop = bound()
    with pytest.raises(ValueError, match='expected current server scope'):
        FeedbackLoop('rec:1').record(decision(loop))
    with pytest.raises(ValueError, match='complete explicit'):
        DecisionFeedback('rec:1', 'reject', 'reason', actor_id=uuid4())
    assert loop.record(DecisionFeedback('rec:1', 'reject', 'unbound display')).can_repair() is False


def test_checked_observed_difference_requires_current_exact_recommendation_and_option():
    rec, _ = bound()
    claim = ImprovementClaim('claim:1', rec.recommendation_id, 'opt:1', rec.evidence,
                             observation(), recommendation_hash=rec.content_hash())
    assert claim.checked_observed_difference(rec, rec.evidence, now=END) == Decimal('2')
    with pytest.raises(ValueError, match='exact recommendation'):
        claim.checked_observed_difference(replace(rec, scope_note='changed scope'), rec.evidence, now=END)
    with pytest.raises(ValueError, match='option is absent'):
        replace(claim, option_id='missing').checked_observed_difference(rec, rec.evidence, now=END)
    with pytest.raises(ValueError, match='exact recommendation'):
        replace(claim, recommendation_hash=None).checked_observed_difference(rec, rec.evidence, now=END)
    with pytest.raises(ValueError, match='stale'):
        claim.checked_observed_difference(rec, EvidenceRevision('rev:1', ('ev:c', 'ev:b', 'ev:a')), now=END)


def test_attached_observed_difference_preserves_existing_unit_and_window_guards():
    rec, _ = bound()
    claim = ImprovementClaim('claim:1', rec.recommendation_id, 'opt:1', rec.evidence,
                             observation(), recommendation_hash=rec.content_hash())
    with pytest.raises(ValueError, match='incomplete'):
        claim.checked_observed_difference(rec, rec.evidence, now=END - timedelta(seconds=1))
    incompatible = replace(claim.observation, followup=hours('8'))
    with pytest.raises(ValueError, match='incompatible'):
        replace(claim, observation=incompatible).checked_observed_difference(rec, rec.evidence, now=END)
    assert 'causal' in ImprovementClaim.__doc__
