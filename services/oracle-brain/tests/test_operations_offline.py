from datetime import datetime, timedelta, timezone

import pytest

from oracle_brain.operations.health import StageHealth, alarms
from oracle_brain.operations.redaction import redact
from oracle_brain.operations.retention import Record, RetentionRule, decide

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


def test_redaction_drops_raw_payloads_and_secrets():
    out = redact({"trace_id": "t1", "latency_ms": 12, "payload": {"text": "confidential"},
                  "prompt": "secret plan", "error_code": "Bearer abc.def.ghi"})
    assert out["trace_id"] == "t1" and out["latency_ms"] == 12
    assert "confidential" not in repr(out) and "secret plan" not in repr(out)
    assert out["error_code"].startswith("sha256:")
    assert out["redacted_fields"] == ["payload", "prompt"]


def test_redaction_fingerprints_long_or_nested_allowed_values():
    out = redact({"stage": "x" * 500, "count": [1, 2]})
    assert out["stage"].startswith("sha256:") and out["count"].startswith("sha256:")


RULES = {"meeting": RetentionRule("meeting", timedelta(days=30)),
         "policy": RetentionRule("policy", None)}


def test_retention_rules():
    old = NOW - timedelta(days=31)
    assert decide(Record("meeting", old), RULES, NOW) == "purge"
    assert decide(Record("meeting", NOW), RULES, NOW) == "keep"
    assert decide(Record("meeting", old, legal_hold=True), RULES, NOW) == "keep"
    assert decide(Record("policy", old), RULES, NOW) == "keep"
    assert decide(Record("policy", NOW, tombstoned=True), RULES, NOW) == "purge"
    assert decide(Record("policy", NOW, tombstoned=True, legal_hold=True), RULES, NOW) == "hide"


def test_retention_fails_closed():
    with pytest.raises(KeyError):
        decide(Record("unknown", NOW), RULES, NOW)
    with pytest.raises(ValueError):
        decide(Record("meeting", NOW.replace(tzinfo=None)), RULES, NOW)


def test_health_alarms():
    stages = [StageHealth("ingest", 5, NOW - timedelta(hours=1), 0, 30.0),
              StageHealth("project", 0, None, 3, 25.0)]
    assert alarms(stages, NOW) == ["cost_cap", "failing:project", "stuck:ingest"]
    assert alarms([StageHealth("ingest", 0, None, 0, 1.0)], NOW) == []
