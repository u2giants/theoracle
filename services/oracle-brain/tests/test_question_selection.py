"""Synthetic fields only; no provider, database or employee data."""
from oracle_brain.interviews.questions import Conflict, FieldSpec, select_need

FIELDS = [FieldSpec('approver', 1), FieldSpec('cutoff_day', 2), FieldSpec('exceptions', 2)]


def test_conflict_selected_before_missing_fields():
    need = select_need(FIELDS, {}, [Conflict('cutoff_day', ('Fri', 'Thu', 'Fri'))])
    assert need.key == 'conflict:cutoff_day' and need.detail == ('Fri', 'Thu')


def test_missing_fields_by_priority_then_name_and_deterministic():
    picks = {select_need(list(reversed(FIELDS)), {}).key for _ in range(5)}
    assert picks == {'missing:approver'}
    assert select_need(FIELDS, {'approver': 'Invented Lead'}).key == 'missing:cutoff_day'


def test_declined_and_asked_needs_are_not_repeated_then_examples_requested():
    need = select_need(FIELDS, {'approver': 'X'}, asked=['missing:cutoff_day'],
                       declined=['missing:exceptions'])
    assert need.key == 'example:approver'


def test_nothing_left_returns_none():
    known = {f.name: 'v' for f in FIELDS}
    assert select_need(FIELDS, known, asked=[f'example:{f.name}' for f in FIELDS]) is None
