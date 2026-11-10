"""Step 0.4 gate: name normalization keeps CJK and English intact."""

from __future__ import annotations

from brain.extract.normalize import normalize_name


def test_fullwidth_punct_stripped() -> None:
    assert normalize_name("采购流程。", "Process") == "采购流程"
    assert normalize_name("审批（紧急）", "Process") == "审批紧急"
    assert normalize_name("张三：", "Person") == "张三"


def test_no_singularise_on_cjk() -> None:
    assert normalize_name("采购步骤s", "Process") == "采购步骤s"
    assert normalize_name("exceptions", "Exception") == "exception"
    assert normalize_name("Licensing Managers", "Role") == "licensing manager"


def test_english_names_inside_cjk() -> None:
    result = normalize_name("Spruce 的 licensing 流程", "Process")
    assert "spruce" in result
    assert "licensing" in result
    assert "流程" in result
