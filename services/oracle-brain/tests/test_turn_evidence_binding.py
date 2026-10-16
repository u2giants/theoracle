"""Interview turn evidence binding to current evidence only."""
from oracle_brain.interviews.evidence import (
    EvidenceRef, bind_turn_evidence, filter_current,
)

AT = '2026-10-16T12:00:00Z'


def _ev(eid, **kw) -> EvidenceRef:
    base = dict(evidence_id=eid, source_id='s1', revision=1)
    base.update(kw)
    return EvidenceRef(**base)


def test_employee_turn_binds_current_evidence_in_stable_order():
    b = bind_turn_evidence('t1', [_ev('e2'), _ev('e1')], bound_at=AT)
    assert b.turn_id == 't1' and b.evidence_ids == ('e2', 'e1') and b.bound_at == AT


def test_superseded_or_withdrawn_evidence_refuses_binding():
    for stale in (_ev('e1', superseded=True), _ev('e1', withdrawn=True)):
        try:
            bind_turn_evidence('t1', [stale], bound_at=AT)
        except ValueError:
            pass
        else:
            raise AssertionError('stale evidence must not bind')


def test_assistant_turns_never_bind_and_duplicates_refused():
    try:
        bind_turn_evidence('t1', [_ev('e1')], bound_at=AT, speaker='assistant')
    except ValueError:
        pass
    else:
        raise AssertionError('assistant statement must not bind as evidence')
    try:
        bind_turn_evidence('t1', [_ev('e1'), _ev('e1')], bound_at=AT)
    except ValueError:
        pass
    else:
        raise AssertionError('duplicate evidence_id must fail')


def test_filter_current_is_display_only_and_preserves_order():
    refs = [_ev('a', superseded=True), _ev('b'), _ev('c', withdrawn=True), _ev('d')]
    assert tuple(e.evidence_id for e in filter_current(refs)) == ('b', 'd')
