"""S04 offline building block: visible failures and bounded processing."""
from __future__ import annotations

import pytest

from oracle_brain.ingest.limits import ProcessingBudget, SourceRejected
from oracle_brain.ingest.normalize import normalize

SHEET = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet+xml"


@pytest.mark.parametrize(("data", "fmt", "reason"), [
    (b"", "text/plain", "empty_source"),
    (b"%PDF-1.7 /Encrypt 5 0 R", "text/plain", "encrypted_source"),
    (b"\xd0\xcf\x11\xe0EncryptedPackage", SHEET, "encrypted_source"),
    (b"\xff\xfe\x00bad", "text/plain", "corrupt_source"),
    (b"<worksheet><row>", SHEET, "corrupt_source"),
    (b'{"text": ', "application/vnd.oracle.ocr+json", "corrupt_source"),
    (b'a,"unterminated\n', "text/csv", "corrupt_source"),
    (b"hello", "application/x-unknown", "unsupported_format"),
])
def test_bad_sources_fail_visibly(data, fmt, reason):
    with pytest.raises(SourceRejected) as error:
        normalize("s", fmt, data)
    assert error.value.reason == reason


def test_oversize_source_rejected(monkeypatch):
    monkeypatch.setattr("oracle_brain.ingest.limits.MAX_SOURCE_BYTES", 8)
    from oracle_brain.ingest import limits

    with pytest.raises(SourceRejected, match="source_too_large"):
        limits.check_bytes(b"x" * 9, max_bytes=limits.MAX_SOURCE_BYTES)


def test_block_budget_stops_runaway_sources():
    data = "\n".join(f"line {n}" for n in range(50)).encode()
    with pytest.raises(SourceRejected, match="block_budget_exhausted"):
        normalize("s", "text/plain", data, ProcessingBudget(max_blocks=10))


def test_repair_budget_prevents_endless_repair():
    budget = ProcessingBudget(max_repairs=2)
    budget.take_repair("retry 1")
    budget.take_repair("retry 2")
    with pytest.raises(SourceRejected, match="repair_budget_exhausted"):
        budget.take_repair("retry 3")
    assert budget.log == ["retry 1", "retry 2", "retry 3"]
