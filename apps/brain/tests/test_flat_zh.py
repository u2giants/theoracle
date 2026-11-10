"""Step 1.1 gate: Chinese chunks yield Chinese names and verbatim quotes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from conftest import fake_embeddings, fake_frontier, fake_scaledown
from test_flat import _mentions, _seed_text

from brain.config import get_settings
from brain.extract.flat import ENTITY_TYPES, handle_classify_extract

ZH_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "verification"
    / "chinese"
    / "fixtures"
    / "sample-zh-process.txt"
)

EXPECTED_SURFACES = [
    "采购审批流程",
    "采购部",
    "张三",
    "采购单",
    "李四",
    "ERP系统",
    "王五",
    "总经理",
]


def _zh_text() -> str:
    return ZH_FIXTURE.read_text(encoding="utf-8")


@pytest.fixture()
def scaledown_on(monkeypatch: pytest.MonkeyPatch):
    """Route the flat stage to ScaleDown (as a deployed run would)."""
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_zh_names_and_quotes_verbatim(
    monkeypatch: pytest.MonkeyPatch, db: Any, scaledown_on: None
) -> None:
    text = _zh_text()
    fake_embeddings(monkeypatch)
    fake_scaledown(monkeypatch, "zh_process.json")
    source_id = _seed_text(db, text, "zh")
    handle_classify_extract({"payload": {"source_id": source_id}})
    mentions = _mentions(db, source_id)
    surfaces = [surface for _, surface, _, _ in mentions]
    for expected in EXPECTED_SURFACES:
        assert expected in surfaces
    for kind, surface, normalized, quote in mentions:
        assert surface in text
        assert quote in text
        assert kind in ENTITY_TYPES
        assert normalized
    kind_row = db.execute(
        "SELECT passage_kind FROM cmap.chunk WHERE source_id = %s", (source_id,)
    ).fetchone()
    assert kind_row[0] == "process"


def test_frontier_fallback_catches_zh_names(monkeypatch: pytest.MonkeyPatch, db: Any) -> None:
    text = _zh_text()
    fake_embeddings(monkeypatch)
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "false")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "")
    get_settings.cache_clear()
    fake_frontier(monkeypatch, "zh_frontier.json")
    source_id = _seed_text(db, text, "zh-frontier")
    handle_classify_extract({"payload": {"source_id": source_id}})
    mentions = _mentions(db, source_id)
    surfaces = [surface for _, surface, _, _ in mentions]
    for expected in EXPECTED_SURFACES:
        assert expected in surfaces
    for _, surface, _, quote in mentions:
        assert surface in text
        assert quote in text
