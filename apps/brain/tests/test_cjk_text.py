"""Step 0.2 gate: sentence splitting, unit counting and folding are CJK-safe."""

from __future__ import annotations

from brain.text_util import count_units, fold_key, sentence_slices, split_sentences


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
    assert fold_key("采购流程是怎样的？") == "采购流程是怎样的"
    assert "采购流程" in fold_key("帮我查一下 采购流程 的进度。")
    assert fold_key("採購流程！") == "採購流程"


def test_english_behaviour_unchanged() -> None:
    assert split_sentences("A. B! C?") == ["A.", "B!", "C?"]
    assert split_sentences("No terminator here") == ["No terminator here"]
    assert split_sentences("One. Two") == ["One.", "Two"]
    assert sentence_slices("One. Two") == [("One.", " "), ("Two", "")]
    rebuilt = "".join(sentence + sep for sentence, sep in sentence_slices("One. Two."))
    assert rebuilt == "One. Two."
    assert count_units("The buyer cannot release the purchase order") == 7
    assert fold_key("What's the purchasing process?") == "whats the purchasing process"
