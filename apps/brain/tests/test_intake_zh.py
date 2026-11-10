"""Step 0.3 gate: Chinese commands and contribution counting work in intake."""

from __future__ import annotations

from brain.interview import intake
from brain.text_util import fold_key


def test_nihao_greets() -> None:
    assert intake.is_greeting(fold_key("你好！")) is True
    assert intake.is_greeting(fold_key("您好")) is True
    assert intake.is_greeting(fold_key("在吗？")) is True
    assert intake.is_greeting(fold_key("hello")) is True


def test_wancheng_is_done() -> None:
    assert intake.is_done(fold_key("完成")) is True
    assert intake.is_done(fold_key("好了。")) is True
    assert intake.is_done(fold_key("说完了")) is True
    assert intake.is_done(fold_key("就这些")) is True
    assert intake.is_done(fold_key("done")) is True
    assert intake.is_done(fold_key("还没说完")) is False


def test_cjk_contribution_accepted() -> None:
    text = "我负责跨境采购审批流程的日常跟进工作"
    assert intake.word_count(text) >= intake.MIN_CONTRIBUTION_WORDS
    assert intake.word_count(text) != 1


def test_zh_join_request() -> None:
    assert intake.is_join_request("加入会议") is True
    assert intake.is_join_request("拉我进会议室") is True
    assert intake.is_join_request("join the call") is True
