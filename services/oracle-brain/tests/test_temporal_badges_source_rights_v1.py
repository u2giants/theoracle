"""S05 offline: current/historical badges, source-rights revocation, ACK lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from oracle_brain.knowledge.source_rights import (
    AckRegistry,
    SourceRightsRegistry,
    badge_facts,
)
from oracle_brain.knowledge.temporal import FactStore


def d(y, m, day, hour=0):
    return datetime(y, m, day, hour, tzinfo=timezone.utc)


def test_current_fact_is_badged_current():
    s = FactStore()
    f = s.assert_fact("moq", "units", "500", valid_from=d(2026, 1, 1), recorded_at=d(2026, 1, 1))
    badges = dict((fact.fact_id, badge) for fact, badge in badge_facts(s.facts, now=d(2026, 6, 1)))
    assert badges[f.fact_id] == "current"


def test_superseded_fact_is_badged_superseded_and_successor_current():
    s = FactStore()
    old = s.assert_fact("moq", "units", "500", valid_from=d(2026, 1, 1), recorded_at=d(2026, 1, 1))
    new = s.correct(old.fact_id, "1000", recorded_at=d(2026, 3, 1))
    badges = dict((fact.fact_id, badge) for fact, badge in badge_facts(s.facts, now=d(2026, 6, 1)))
    assert badges[old.fact_id] == "superseded"
    assert badges[new.fact_id] == "current"


def test_future_dated_rule_is_badged_future():
    s = FactStore()
    f = s.assert_fact(
        "deposit", "percent", "50", valid_from=d(2027, 1, 1), recorded_at=d(2026, 6, 1)
    )
    badges = dict((fact.fact_id, badge) for fact, badge in badge_facts(s.facts, now=d(2026, 6, 1)))
    assert badges[f.fact_id] == "future"


def test_expired_validity_is_badged_historical():
    s = FactStore()
    f = s.assert_fact(
        "deposit",
        "percent",
        "30",
        valid_from=d(2026, 1, 1),
        valid_to=d(2026, 4, 1),
        recorded_at=d(2026, 1, 1),
    )
    badges = dict((fact.fact_id, badge) for fact, badge in badge_facts(s.facts, now=d(2026, 6, 1)))
    assert badges[f.fact_id] == "historical"


def test_revocation_denies_future_reads():
    rights = SourceRightsRegistry()
    rights.grant("s1", "alice")
    assert rights.can_read("s1", "alice") is True
    rights.revoke("s1", "alice")
    assert rights.can_read("s1", "alice") is False
    assert rights.can_read("s1", "bob") is False


def test_acknowledge_requires_current_source_read_right():
    rights = SourceRightsRegistry()
    acks = AckRegistry(rights)
    cid = uuid4()
    acks.open(cid, subject="alice", source_ids=("s1",))
    with pytest.raises(PermissionError):
        acks.acknowledge(cid, at=d(2026, 6, 1))
    rights.grant("s1", "alice")
    ack = acks.acknowledge(cid, at=d(2026, 6, 1))
    assert ack.state == "acknowledged"
    assert acks.settled(cid, now=d(2026, 6, 2)) is True


def test_revocation_does_not_erase_ack_longevity():
    rights = SourceRightsRegistry()
    acks = AckRegistry(rights)
    cid = uuid4()
    rights.grant("s1", "alice")
    acks.open(cid, subject="alice", source_ids=("s1",))
    acks.acknowledge(cid, at=d(2026, 6, 1))
    rights.revoke("s1", "alice")
    assert acks.status(cid).state == "acknowledged"
    assert acks.settled(cid, now=d(2026, 6, 2)) is True


def test_withdrawal_ends_settled_ack():
    rights = SourceRightsRegistry()
    acks = AckRegistry(rights)
    cid = uuid4()
    rights.grant("s1", "alice")
    acks.open(cid, subject="alice", source_ids=("s1",))
    acks.acknowledge(cid, at=d(2026, 6, 1))
    ack = acks.withdraw(cid, subject="alice", at=d(2026, 6, 3))
    assert ack.state == "withdrawn"
    assert acks.settled(cid, now=d(2026, 6, 4)) is False


def test_only_confirming_subject_may_withdraw():
    rights = SourceRightsRegistry()
    acks = AckRegistry(rights)
    cid = uuid4()
    rights.grant("s1", "alice")
    acks.open(cid, subject="alice", source_ids=("s1",))
    acks.acknowledge(cid, at=d(2026, 6, 1))
    with pytest.raises(PermissionError):
        acks.withdraw(cid, subject="bob", at=d(2026, 6, 2))


def test_cannot_acknowledge_twice_or_reopen():
    rights = SourceRightsRegistry()
    acks = AckRegistry(rights)
    cid = uuid4()
    rights.grant("s1", "alice")
    acks.open(cid, subject="alice", source_ids=("s1",))
    acks.acknowledge(cid, at=d(2026, 6, 1))
    with pytest.raises(ValueError):
        acks.acknowledge(cid, at=d(2026, 6, 2))
    with pytest.raises(ValueError):
        acks.open(cid, subject="alice", source_ids=("s1",))
