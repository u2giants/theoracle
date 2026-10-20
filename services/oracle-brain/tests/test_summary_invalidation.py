from datetime import datetime, timezone

from oracle_brain.knowledge.summaries import SummaryCache
from oracle_brain.knowledge.temporal import FactStore


def test_correction_invalidates_only_dependent_summaries():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    s, cache = FactStore(), SummaryCache()
    moq = s.assert_fact("moq", "units", "500", valid_from=t, recorded_at=t)
    lead = s.assert_fact("lead_time", "days", "30", valid_from=t, recorded_at=t)
    cache.build("pricing", [moq], lambda fs: f"MOQ {fs[0].value}")
    cache.build("shipping", [lead], lambda fs: f"Lead {fs[0].value}")
    s.correct(moq.fact_id, "1000", recorded_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert cache.invalidate_fact(moq.fact_id) == ["pricing"]
    assert cache.get("pricing") is None
    assert cache.get("shipping").text == "Lead 30"
