"""Step 0.4 gate: window chunk edges are safe for CJK text."""

from __future__ import annotations

from brain.read.chunk import WINDOW_TOKENS, window_chunks


def test_cjk_text_chunked() -> None:
    text = "采购审批流程由张三发起，李四复核，王五终审。" * 30
    chunks = window_chunks(text, {})
    assert len(chunks) >= 2
    assert all(chunk.token_count <= WINDOW_TOKENS for chunk in chunks)
    assert all(chunk.text.strip() for chunk in chunks)
    assert all("�" not in chunk.text for chunk in chunks)


def test_window_edge_not_mid_ascii_word() -> None:
    sentence = (
        "The buyer cannot release the purchase order until the artwork log "
        "shows the licensor sign-off date for the program. "
    )
    stripped = (sentence * 40).strip()
    chunks = window_chunks(stripped, {})
    assert len(chunks) >= 2
    haystack = f" {stripped} "
    for chunk in chunks:
        assert chunk.text in stripped
        assert f" {chunk.text} " in haystack
