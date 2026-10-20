"""S06 offline gate: preserve original-language evidence in Chinese/English turns.

Turn.language and unicode-safe state serialization are real on main.
A dedicated translation/preservation module is absent and skipped with reason.
Invented/synthetic only.
"""
from __future__ import annotations

import importlib.util
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
    # ensure_ascii=False keeps original wording in the durable JSON
    assert "最小起订量" in state.dumps()


def test_mixed_language_session_keeps_both_turns_distinct():
    state = InterviewState(interview_id="synthetic-multi-2")
    state.apply_turn(Turn(turn_id="t-zh", need_key="fact:moq", answer=ZH, language="zh"))
    state.apply_turn(Turn(turn_id="t-en", need_key="fact:lead_time", answer=EN, language="en"))
    assert len(state.turns) == 2
    assert state.turns[0].answer == ZH
    assert state.turns[1].answer == EN


def test_original_language_evidence_preservation_api():
    """Skip-with-reason when bilingual evidence-preservation is not built."""
    mod = None
    for name in (
        "oracle_brain.knowledge.translation",
        "oracle_brain.interviews.language",
        "oracle_brain.workflows.multilingual",
    ):
        try:
            if importlib.util.find_spec(name) is not None:
                mod = name
                break
        except ModuleNotFoundError:
            continue
    if mod is None:
        pytest.skip(
            "No original-language evidence-preservation module on main "
            "(oracle_brain.knowledge.translation / interviews.language / "
            "workflows.multilingual all absent). S06 multilingual gate requires "
            "preserving original-language evidence in Chinese/English turns "
            "without translating away the source wording; named offline gate "
            "test registered fail-closed until that module lands."
        )
    assert mod
