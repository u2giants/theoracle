from datetime import datetime, timezone

from oracle_brain.knowledge.contradictions import find_contradictions
from oracle_brain.knowledge.temporal import FactStore


def d(y, m, day):
    return datetime(y, m, day, tzinfo=timezone.utc)


def test_future_dated_rule_is_not_current_until_effective():
    s = FactStore()
    s.assert_fact("deposit", "percent", "30", valid_from=d(2026, 1, 1),
                  valid_to=d(2027, 1, 1), recorded_at=d(2026, 1, 1))
    s.assert_fact("deposit", "percent", "50", valid_from=d(2027, 1, 1), recorded_at=d(2026, 6, 1))
    assert s.current("deposit", "percent", now=d(2026, 10, 15)).value == "30"
    assert s.current("deposit", "percent", now=d(2027, 2, 1)).value == "50"


def test_customer_specific_policy_stays_distinct_from_company_rule():
    s = FactStore()
    s.assert_fact("deposit", "percent", "30", valid_from=d(2026, 1, 1), recorded_at=d(2026, 1, 1))
    s.assert_fact("deposit", "percent", "0", scope="customer:acme",
                  valid_from=d(2026, 1, 1), recorded_at=d(2026, 1, 1))
    now = d(2026, 5, 1)
    assert s.current("deposit", "percent", now=now).value == "30"
    assert s.current("deposit", "percent", now=now, scope="customer:acme").value == "0"
    assert s.current("deposit", "percent", now=now, scope="customer:other").value == "30"
    assert find_contradictions(s.facts) == []


def test_as_of_history_survives_correction():
    s = FactStore()
    old = s.assert_fact("moq", "units", "500", valid_from=d(2026, 1, 1), recorded_at=d(2026, 1, 1))
    s.correct(old.fact_id, "1000", recorded_at=d(2026, 6, 1))
    assert s.current("moq", "units", now=d(2026, 7, 1)).value == "1000"
    past = s.as_of("moq", "units", valid_at=d(2026, 3, 1), known_at=d(2026, 3, 1))
    assert past.value == "500"
    assert find_contradictions(s.facts) == []


def test_overlapping_conflicting_reports_are_flagged():
    s = FactStore()
    s.assert_fact("lead_time", "days", "30", valid_from=d(2026, 1, 1), recorded_at=d(2026, 1, 2))
    s.assert_fact("lead_time", "days", "45", valid_from=d(2026, 3, 1), recorded_at=d(2026, 3, 2))
    assert len(find_contradictions(s.facts)) == 1
