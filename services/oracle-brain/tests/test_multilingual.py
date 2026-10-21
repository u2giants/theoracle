"""S06 offline gate: preserve original-language evidence in Chinese/English turns.

Turn.language and unicode-safe state serialization are real on main.
Exact original/translation binding is tested; translations remain unreviewed.
Invented/synthetic only.
"""
from __future__ import annotations

import json

import pytest

from oracle_brain.interviews.state import InterviewState, Turn

ZH = "最小起订量是 1000 件。"
EN = "The lead time is 30 days."


def test_turn_records_language_tag_without_mangling_text():
    zh = Turn(turn_id="t-zh", need_key="fact:moq", answer=ZH, language="zh")
    en = Turn(turn_id="t-en", need_key="fact:lead_time", answer=EN, language="en")
    assert zh.language == "zh" and zh.answer == ZH
    assert en.language == "en" and en.answer == EN


def test_state_roundtrip_preserves_chinese_and_english_evidence():
    state = InterviewState(interview_id="synthetic-multi-1")
    state.apply_turn(Turn(turn_id="t-zh", need_key="fact:moq", answer=ZH, language="zh"))
    state.apply_turn(Turn(turn_id="t-en", need_key="fact:lead_time", answer=EN, language="en"))
    restored = InterviewState.loads(state.dumps())
    assert restored.known["moq"] == ZH
    assert restored.known["lead_time"] == EN
    assert [t.language for t in restored.turns] == ["zh", "en"]
    # ensure_ascii=False preserves wording in serialization; this is not durable storage
    assert "最小起订量" in state.dumps()


def test_mixed_language_session_keeps_both_turns_distinct():
    state = InterviewState(interview_id="synthetic-multi-2")
    state.apply_turn(Turn(turn_id="t-zh", need_key="fact:moq", answer=ZH, language="zh"))
    state.apply_turn(Turn(turn_id="t-en", need_key="fact:lead_time", answer=EN, language="en"))
    assert len(state.turns) == 2
    assert state.turns[0].answer == ZH
    assert state.turns[1].answer == EN


def test_original_language_evidence_preservation_api():
    from uuid import uuid4
    from oracle_brain.interviews.language import preserve_original,UnreviewedTranslation,bind_translation
    original=preserve_original(workspace_id=uuid4(),actor_id=uuid4(),thread_id=uuid4(),
        turn_id=uuid4(),revision=1,language='zh-CN',text='仅样品不需审批，量产不得跳过批准。')
    translation=UnreviewedTranslation(original_identity_digest=original.identity_digest(),
        original_sha256=original.original_sha256,target_language='en',
        text='Samples do not need approval; production must not skip it.')
    bind_translation(original,translation)
    assert original.text=='仅样品不需审批，量产不得跳过批准。'
    assert translation.review_state=='unreviewed' and translation.replaces_original is False
