"""Step 0.4 gate: legacy Chinese files decode instead of turning to mush."""

from __future__ import annotations

from brain.read.pipeline import read_chunks


def test_utf8_bom() -> None:
    data = "采购流程说明".encode("utf-8-sig")
    chunks = read_chunks("text", data)
    assert chunks[0].text == "采购流程说明"


def test_gb18030_fallback() -> None:
    data = "采购流程说明".encode("gb18030")
    chunks = read_chunks("text", data)
    assert chunks[0].text == "采购流程说明"
