"""Step 0.2 gate: sentence splitting, unit counting and folding are CJK-safe."""

from __future__ import annotations

from brain.text_util import count_units, fold_key, sentence_slices, sentence_spans, split_sentences


def test_split_fullwidth_punctuation() -> None:
    assert split_sentences("第一句。第二句！第三句？") == ["第一句。", "第二句！", "第三句？"]
    assert split_sentences("先确认供应商；再走审批。") == ["先确认供应商；", "再走审批。"]


def test_split_mixed_languages() -> None:
    assert split_sentences("Hello world. 你好世界。Done now!") == [
        "Hello world.",
        "你好世界。",
        "Done now!",
    ]
    assert split_sentences("他说没问题。Then we shipped it. 完成。") == [
        "他说没问题。",
        "Then we shipped it.",
        "完成。",
    ]


def test_split_no_break_inside_quotes_or_brackets() -> None:
    assert split_sentences("他说：“你好。世界。”然后走了。") == ["他说：“你好。世界。”", "然后走了。"]
    assert split_sentences("See (e.g. this). Done.") == ["See (e.g. this).", "Done."]


def test_count_units_chinese_sentence() -> None:
    assert count_units("我们的跨境审批现在到底卡在哪里了呢") == 17
    assert count_units("做完了") == 3
    assert count_units("this is four words") == 4
    assert count_units("Spruce 的 licensing 流程") == 5


def test_fold_key_keeps_cjk() -> None:
    assert fold_key("采购流程是怎样的？") == "采购流程是怎样的 "
    assert "采购流程" in fold_key("帮我查一下 采购流程 的进度。")
    assert fold_key("採購流程！") == "採購流程 "


def test_english_behaviour_unchanged() -> None:
    assert split_sentences("A. B! C?") == ["A.", "B!", "C?"]
    assert split_sentences("No terminator here") == ["No terminator here"]
    assert split_sentences("One. Two") == ["One.", "Two"]
    assert sentence_slices("One. Two") == [("One.", " "), ("Two", "")]
    rebuilt = "".join(sentence + sep for sentence, sep in sentence_slices("One. Two."))
    assert rebuilt == "One. Two."
    assert count_units("The buyer cannot release the purchase order") == 7
    assert fold_key("What's the purchasing process?") == "whats the purchasing process "


def test_ascii_semicolon_is_not_a_boundary() -> None:
    assert split_sentences("a; b. Next.") == ["a; b.", "Next."]


def test_punctuation_does_not_count_as_a_word() -> None:
    assert count_units("做完了。") == 3
    assert count_units("你好世界。再见。") == 6
    assert count_units("hello, world!") == 2
    assert count_units("。！？；… -- !!!") == 0
    assert count_units("Spruce 的 licensing 流程。") == 5


def test_extended_ideographs_survive_and_count() -> None:
    text = "㐀𠀀豈丽𰀀"
    assert fold_key(text) == text.casefold()
    assert count_units(text) == 5


def test_sentence_whitespace_round_trip_and_contiguous_offsets() -> None:
    for text in ("", "  ", "  One. Two.  ", "第一句。 第二句。", "One. Two"):
        slices = sentence_slices(text)
        assert "".join(sentence + sep for sentence, sep in slices) == text
        spans = sentence_spans(text)
        assert "".join(text[left:right] for left, right in spans) == text
        assert all(right == next_left for (_, right), (next_left, _) in zip(spans, spans[1:]))
    assert sentence_slices("") == [("", "")]
    assert sentence_spans("One. Two") == [(0, 5), (5, 8)]
    assert sentence_spans("  One. Two") == [(0, 7), (7, 10)]


def test_nested_closers_do_not_end_outer_brackets() -> None:
    assert split_sentences('Before (he said "x." then left). After.') == [
        'Before (he said "x." then left).', 'After.'
    ]
    assert split_sentences("他说（她说‘好了。’然后离开）。完成。") == [
        "他说（她说‘好了。’然后离开）。", "完成。"
    ]


def test_fold_preserves_historical_spacing_and_apostrophes() -> None:
    assert fold_key("  A  B  ") == "  a  b  "
    assert fold_key("a’b") == "a b"
    assert fold_key("a'b") == "ab"
    assert fold_key(" !!A?!  B.. ") == "  a   b  "
