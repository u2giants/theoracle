from datetime import datetime, timedelta, timezone

import pytest

from oracle_brain.provider_policy import (ProcessingApproval, ProcessingRequest,
                                          authorize, dispatch, safe_telemetry)


def test_default_deny_exact_scope_and_no_outbound_call():
    now = datetime.now(timezone.utc)
    request = ProcessingRequest(provider="mock", account="local", endpoint="http://localhost:1",
                                data_classes=frozenset({"synthetic"}), purpose="test",
                                terms_hash="a" * 64)
    approval = ProcessingApproval(**request.model_dump(), expires_at=now+timedelta(days=1),
                                  register_ref="synthetic-fixture")
    calls = []
    sender = lambda: calls.append(1)
    assert dispatch(request, [approval], sender) is None and calls == [1]
    for changed in (dict(endpoint="https://real.example"), dict(terms_hash="b"*64),
                    dict(fallback=True), dict(data_classes=frozenset({"company"}))):
        denied = request.model_copy(update=changed)
        with pytest.raises(PermissionError):
            dispatch(denied, [approval], sender)
    with pytest.raises(PermissionError):
        dispatch(request, [approval.model_copy(update={"expires_at": now-timedelta(seconds=1)})], sender)
    with pytest.raises(ValueError):
        ProcessingApproval(**request.model_dump(), expires_at=datetime(2027, 1, 1),
                           register_ref="invalid-naive-expiry")
    with pytest.raises(PermissionError):
        dispatch(request, [approval.model_copy(update={"expires_at": datetime(2027, 1, 1)})], sender)
    with pytest.raises(ValueError, match="timezone-aware"):
        authorize(request, [approval], now=datetime(2026, 9, 28))
    assert calls == [1]
    with pytest.raises(ValueError):
        safe_telemetry({"source_text": "private"})
    with pytest.raises(ValueError):
        safe_telemetry({"model": "private company procedure"})
    with pytest.raises(ValueError):
        safe_telemetry({"status": "Approval from Alice"})
    assert safe_telemetry({"run_id": "11111111-1111-4111-8111-111111111111",
                           "model": "openai/gpt-4o", "status": "passed"})["status"] == "passed"
