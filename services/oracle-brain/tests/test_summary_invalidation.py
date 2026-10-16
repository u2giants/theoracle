from datetime import datetime, timezone

from oracle_brain.knowledge.temporal import FactStore


def test_correction_invalidates_only_dependent_summaries():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    s = FactStore()
    cache = s.summaries
    moq = s.assert_fact("moq", "units", "500", valid_from=t, recorded_at=t)
    lead = s.assert_fact("lead_time", "days", "30", valid_from=t, recorded_at=t)
    cache.build("pricing", [moq], lambda fs: f"MOQ {fs[0].value}")
    cache.build("shipping", [lead], lambda fs: f"Lead {fs[0].value}")
    s.correct(moq.fact_id, "1000", recorded_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert cache.summaries["pricing"].stale
    assert cache.get("pricing") is None
    assert cache.get("shipping").text == "Lead 30"


def test_rebuilt_summary_is_invalidated_on_second_correction():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    s = FactStore()
    original = s.assert_fact("moq", "units", "500", valid_from=t, recorded_at=t)
    s.summaries.build("pricing", [original], lambda fs: fs[0].value)
    corrected = s.correct(original.fact_id, "1000", recorded_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert s.summaries.get("pricing") is None
    s.summaries.build("pricing", [corrected], lambda fs: fs[0].value)
    assert s.summaries.get("pricing").text == "1000"
    s.correct(corrected.fact_id, "1500", recorded_at=datetime(2026, 3, 1, tzinfo=timezone.utc))
    assert s.summaries.get("pricing") is None
    assert s.as_of("moq", "units", valid_at=t, known_at=t).value == "500"


def test_rejected_correction_keeps_current_summary():
    import pytest
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    s = FactStore()
    original = s.assert_fact("moq", "units", "500", valid_from=t, recorded_at=t)
    corrected = s.correct(original.fact_id, "1000", recorded_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    s.summaries.build("pricing", [corrected], lambda fs: fs[0].value)
    with pytest.raises(ValueError, match="already superseded"):
        s.correct(original.fact_id, "1500", recorded_at=datetime(2026, 3, 1, tzinfo=timezone.utc))
    assert s.summaries.get("pricing").text == "1000"
