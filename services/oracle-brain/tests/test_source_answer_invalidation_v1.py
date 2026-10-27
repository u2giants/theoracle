"""S04 offline: current answers become unservable when their sources change."""

from __future__ import annotations

from uuid import uuid4

import pytest

from oracle_brain.sources.answer_invalidation import (
    AnswerInvalidationRegistry,
    AnswerSourceRef,
    AnswerStaleReason,
)


def test_answer_is_servable_while_sources_are_current():
    reg = AnswerInvalidationRegistry()
    a = reg.record([AnswerSourceRef("s1", 1), AnswerSourceRef("s2", 1)])
    assert reg.is_servable(a.answer_id) is True
    assert reg.stale_reason(a.answer_id) is None


def test_source_revision_invalidates_answers_on_older_revisions():
    reg = AnswerInvalidationRegistry()
    a1 = reg.record([AnswerSourceRef("s1", 1)])
    a2 = reg.record([AnswerSourceRef("s2", 1)])
    hit = reg.on_revision("s1", 2)
    assert hit == [a1.answer_id]
    assert reg.is_servable(a1.answer_id) is False
    assert reg.stale_reason(a1.answer_id) == AnswerStaleReason.SOURCE_REVISED
    assert reg.is_servable(a2.answer_id) is True


def test_answer_on_same_revision_stays_servable_until_that_revision_moves():
    reg = AnswerInvalidationRegistry()
    a = reg.record([AnswerSourceRef("s1", 2)])
    assert reg.on_revision("s1", 2) == []
    assert reg.is_servable(a.answer_id) is True
    assert reg.on_revision("s1", 3) == [a.answer_id]
    assert reg.is_servable(a.answer_id) is False


def test_withdrawal_invalidates_dependent_answers():
    reg = AnswerInvalidationRegistry()
    a1 = reg.record([AnswerSourceRef("s1", 1)])
    a2 = reg.record([AnswerSourceRef("s2", 1)])
    hit = reg.on_withdrawal("s1")
    assert hit == [a1.answer_id]
    assert reg.stale_reason(a1.answer_id) == AnswerStaleReason.SOURCE_WITHDRAWN
    assert reg.is_servable(a2.answer_id) is True


def test_revision_scoped_withdrawal_leaves_other_revisions():
    reg = AnswerInvalidationRegistry()
    a_old = reg.record([AnswerSourceRef("s1", 1)])
    a_new = reg.record([AnswerSourceRef("s1", 2)])
    hit = reg.on_withdrawal("s1", revision=1)
    assert hit == [a_old.answer_id]
    assert reg.is_servable(a_new.answer_id) is True


def test_revision_cannot_move_backwards():
    reg = AnswerInvalidationRegistry()
    reg.record([AnswerSourceRef("s1", 3)])
    with pytest.raises(ValueError):
        reg.on_revision("s1", 2)


def test_unknown_answer_is_not_servable():
    reg = AnswerInvalidationRegistry()
    with pytest.raises(KeyError):
        reg.is_servable(uuid4())


def test_answer_must_cite_at_least_one_source():
    reg = AnswerInvalidationRegistry()
    with pytest.raises(ValueError):
        reg.record([])


def test_dependents_lists_every_answer_citing_the_source():
    reg = AnswerInvalidationRegistry()
    a1 = reg.record([AnswerSourceRef("s1", 1)])
    a2 = reg.record([AnswerSourceRef("s1", 1), AnswerSourceRef("s2", 1)])
    reg.record([AnswerSourceRef("s2", 1)])
    assert set(reg.dependents("s1")) == {a1.answer_id, a2.answer_id}
