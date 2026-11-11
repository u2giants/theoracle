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


def _english() -> str:
    paragraph = (
        "The buyer cannot release the purchase order until the artwork log "
        "shows the licensor sign-off date for the program. Jessica records it.\n"
    )
    return "\n".join(paragraph * 3 for _ in range(25)).strip()


def _chinese_sparse_spaces() -> str:
    # Long runs with no spaces at all, an occasional space, few terminators.
    run = "采购审批流程由张三发起并交给李四复核然后由王五终审" * 6
    return (run + " " + run + "。" + run + "\n") * 6


def _csv_rows() -> list[str]:
    return [
        f"PO-{n:05d},Acme Factory {n % 17},wall art {n % 9},{n * 3},2026-0{1 + n % 9}-1{n % 9},"
        f"waiting on licensor sign-off for program {n % 23}"
        for n in range(400)
    ]


def _assert_nothing_lost(text: str) -> None:
    from brain.read.chunk import window_spans

    stripped = text.strip()
    spans = window_spans(stripped)
    chunks = window_chunks(stripped, {})
    assert spans[0][0] == 0 and spans[-1][1] == len(stripped)
    rebuilt = stripped[spans[0][0] : spans[0][1]]
    for (_prev_start, prev_end), (start, end) in zip(spans, spans[1:], strict=False):
        assert start <= prev_end, "a gap between two windows drops text"
        assert end > prev_end, "a window adds nothing"
        rebuilt += stripped[prev_end:end]
    assert rebuilt == stripped
    assert [chunk.text for chunk in chunks] == [
        stripped[start:end].strip() for start, end in spans
    ]
    assert all(chunk.token_count <= WINDOW_TOKENS for chunk in chunks)
    assert all("�" not in chunk.text for chunk in chunks)


def test_no_text_lost_property() -> None:
    """Repair A3: the splitter never drops text.

    Over English, Chinese with sparse spaces, and a 400-row CSV: the windows
    cover every character, and every input line appears whole in at least
    one chunk unless the line itself is longer than a window.
    """
    from brain.read.chunk import count_tokens

    csv_text = "\n".join(_csv_rows())
    for text in (_english(), _chinese_sparse_spaces(), csv_text):
        _assert_nothing_lost(text)
        chunks = window_chunks(text, {})
        assert len(chunks) >= 2
        for line in text.strip().splitlines():
            line = line.strip()
            if not line or count_tokens(line) > WINDOW_TOKENS:
                continue
            assert any(line in chunk.text for chunk in chunks), line[:60]
    # The audit's two demonstrations, as counts.
    chinese = _chinese_sparse_spaces().strip()
    kept = set()
    from brain.read.chunk import window_spans

    for start, end in window_spans(chinese):
        kept.update(range(start, end))
    assert len(kept) == len(chinese)


def test_no_text_lost_on_awkward_inputs() -> None:
    """One enormous unbroken token run, long lines, and mixed scripts."""
    cases = [
        "x" * 9000,
        "采" * 3000,
        ("word " * 390 + "\n") * 5,
        ("A long line without any full stop " * 60 + "\n") * 4,
        "Intro paragraph.\n\n" + ("中文段落没有空格。English sentence follows. " * 80),
        "tail\n" * 2000,
    ]
    for text in cases:
        _assert_nothing_lost(text)
