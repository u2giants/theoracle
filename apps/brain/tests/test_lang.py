"""Step 0.1 gate: language detection classifies zh/en/mixed and never ja/ko as zh."""

from __future__ import annotations

from brain.lang import cjk_ratio, detect_language, is_cjk


def test_zh_detected() -> None:
    assert detect_language("我们的跨境审批卡在哪里？") == "zh"
    assert detect_language("采购流程。") == "zh"
    assert detect_language("採購流程") == "zh"


def test_en_detected() -> None:
    assert detect_language("Where is the cross-border approval stuck?") == "en"
    assert detect_language("purchasing process") == "en"


def test_mixed() -> None:
    assert detect_language("Spruce 的 licensing 流程 is broken") == "mixed"


def test_ja_ko_not_zh() -> None:
    assert detect_language("これは日本語のテキストです") == "other"
    assert detect_language("会議の議事録を確認してください") == "other"
    assert detect_language("한국어 텍스트입니다") == "other"


def test_empty_and_punctuation_only() -> None:
    assert detect_language("") == "other"
    assert detect_language("！！？？…") == "other"
    assert detect_language("123 456 ---") == "other"


def test_helpers() -> None:
    assert is_cjk("采") is True
    assert is_cjk("a") is False
    assert is_cjk("。") is False
    assert is_cjk("采购") is False
    assert cjk_ratio("采购流程") == 1.0
    assert cjk_ratio("purchasing") == 0.0
    assert cjk_ratio("采 a") == 0.5
    assert cjk_ratio("") == 0.0
