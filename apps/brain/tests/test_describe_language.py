"""Step 1.2 gate: derived prose matches the evidence language (with en companion)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from conftest import fake_embeddings
from test_flat import _seed_text
from test_resolve import _mention, _unit

from brain.config import get_settings
from brain.resolve import resolve as resolve_mod
from brain.resolve.resolve import describe_fields, run_resolve

ZH_DESCRIPTION = "采购审批流程是采购部发起的内部审批流程。"
EN_DESCRIPTION = "The purchasing approval process is the internal approval flow."
ZH_QUOTE = "采购审批流程由采购部发起并逐级复核。"


@pytest.fixture()
def frontier_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _DescribeFake:
    """Answers describe prompts from fixed fields; judges nothing."""

    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = answer
        self.describe_prompts: list[str] = []

    def __call__(
        self, messages: list[dict[str, Any]], settings: Any, max_tokens: int = 4000
    ) -> dict[str, Any]:
        del settings, max_tokens
        prompt = str(messages[-1]["content"])
        if "CANDIDATES:" in prompt:
            body = {"same_as": None, "confidence": 0.9, "reason": "test"}
        else:
            self.describe_prompts.append(prompt)
            body = self.answer
        return {
            "choices": [{"message": {"content": json.dumps(body)}}],
            "usage": {"total_tokens": 50},
        }


def _seed_three(db: Any, surface: str, quote: str, tag: str) -> None:
    source = _seed_text(db, quote, tag)
    for index in range(3):
        _mention(db, source, "Process", surface, _unit(f"{tag}-{index}"), quote=quote)


def test_zh_quotes_produce_zh_description(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env: None
) -> None:
    fake = _DescribeFake(
        {
            "canonical_name": "采购审批流程",
            "description": ZH_DESCRIPTION,
            "description_en": EN_DESCRIPTION,
        }
    )
    monkeypatch.setattr(resolve_mod, "_post_chat", fake)
    fake_embeddings(monkeypatch)
    _seed_three(db, "采购审批流程", ZH_QUOTE, "zh-desc")
    run_resolve()
    row = db.execute("SELECT description, describe_payload FROM cmap.entity").fetchone()
    assert row[0] == EN_DESCRIPTION
    assert row[1]["description"] == ZH_DESCRIPTION
    assert row[1]["description_en"] == EN_DESCRIPTION
    assert "IN THE LANGUAGE OF THE QUOTES" in fake.describe_prompts[0]
    assert ZH_QUOTE in fake.describe_prompts[0]


def test_en_companion_returned() -> None:
    description, description_en, description_zh = describe_fields(
        {
            "description": ZH_DESCRIPTION,
            "description_en": EN_DESCRIPTION,
            "description_zh": "",
        }
    )
    assert description == ZH_DESCRIPTION
    assert description_en == EN_DESCRIPTION
    assert description_zh == ""
    _, _, description_zh = describe_fields(
        {"description": EN_DESCRIPTION, "description_zh": ZH_DESCRIPTION}
    )
    assert description_zh == ZH_DESCRIPTION


def test_en_source_unchanged(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env: None
) -> None:
    fake = _DescribeFake(
        {
            "canonical_name": "Artwork Log",
            "description": "Described.",
            "description_en": "",
        }
    )
    monkeypatch.setattr(resolve_mod, "_post_chat", fake)
    fake_embeddings(monkeypatch)
    _seed_three(db, "artwork log", "the artwork log holds sign-off dates", "en-desc")
    run_resolve()
    row = db.execute("SELECT canonical_name, description FROM cmap.entity").fetchone()
    assert row == ("Artwork Log", "Described.")
    assert "IN THE LANGUAGE OF THE QUOTES" in fake.describe_prompts[0]
