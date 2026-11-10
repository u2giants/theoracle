"""Step 1.4 gate: cross-lingual resolution merges what is the same, only then."""

from __future__ import annotations

import json
from typing import Any

import psycopg
import pytest
from conftest import fake_embeddings
from test_flat import _seed_text
from test_resolve import _at_cosine, _mention, _unit

from brain.config import get_settings
from brain.resolve import resolve as resolve_mod
from brain.resolve.resolve import run_resolve


@pytest.fixture()
def frontier_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def name_vectors(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[float]]:
    """Pin a name's vector here; otherwise a fresh unit direction."""
    pinned: dict[str, list[float]] = {}

    def fake(
        names: list[str], settings: Any, usage: dict[str, int]
    ) -> list[list[float]]:
        del settings, usage
        return [pinned.get(name, _unit(f"name:{name}")) for name in names]

    monkeypatch.setattr(resolve_mod, "embed_names", fake)
    return pinned


class _JudgeFake:
    """Judge answers from ``same`` (mention name → candidate canonical substring)."""

    def __init__(self, same: dict[str, str] | None = None) -> None:
        self.same = same or {}
        self.judge_prompts: list[dict[str, Any]] = []

    def __call__(
        self, messages: list[dict[str, Any]], settings: Any, max_tokens: int = 4000
    ) -> dict[str, Any]:
        del settings, max_tokens
        prompt = str(messages[-1]["content"])
        if "CANDIDATES:" not in prompt:
            return {
                "choices": [{"message": {"content": json.dumps({"canonical_name": "", "description": ""})}}],
                "usage": {"total_tokens": 10},
            }
        mention = json.loads(prompt.split("MENTION:\n<<<\n", 1)[1].split("\n>>>", 1)[0])
        candidates = json.loads(
            prompt.split("CANDIDATES:\n<<<\n", 1)[1].split("\n>>>", 1)[0]
        )
        self.judge_prompts.append({"mention": mention, "candidates": candidates})
        target = self.same.get(str(mention.get("name")))
        pick = None
        for candidate in candidates:
            if target and target in str(candidate.get("canonical_name")):
                pick = candidate["id"]
        body = {
            "same_as": pick,
            "confidence": 0.95 if pick else 0.0,
            "reason": "test",
        }
        return {
            "choices": [{"message": {"content": json.dumps(body)}}],
            "usage": {"total_tokens": 50},
        }


def _entity_rows(db: Any) -> list[tuple[str, str]]:
    return [
        (str(row[0]), str(row[1]))
        for row in db.execute(
            "SELECT id, canonical_name FROM cmap.entity ORDER BY canonical_name"
        ).fetchall()
    ]


def test_same_thing_en_zh_merges(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env: None, name_vectors: dict
) -> None:
    fake = _JudgeFake(same={"采购流程": "Purchasing Process"})
    monkeypatch.setattr(resolve_mod, "_post_chat", fake)
    fake_embeddings(monkeypatch)
    base = _unit("process")
    name_vectors["Purchasing Process"] = base
    name_vectors["采购流程"] = _at_cosine(base, 0.9, "zh-name")

    en_source = _seed_text(db, "the purchasing process covers approvals", "en")
    _mention(
        db,
        en_source,
        "Process",
        "purchasing process",
        _unit("en-mention"),
        quote="the purchasing process covers approvals",
    )
    run_resolve()
    zh_source = _seed_text(db, "采购流程由李四负责。", "zh")
    _mention(
        db,
        zh_source,
        "Process",
        "采购流程",
        _unit("zh-mention"),
        quote="采购流程由李四负责。",
    )
    run_resolve()

    entities = _entity_rows(db)
    assert len(entities) == 1
    assert str(entities[0][1]) == "Purchasing Process"
    linked = {
        str(row[0])
        for row in db.execute("SELECT DISTINCT entity_id FROM cmap.mention").fetchall()
    }
    assert len(linked) == 1
    aliases = {
        (str(row[0]), str(row[1]), str(row[2]))
        for row in db.execute(
            "SELECT normalized_name, lang, source FROM cmap.entity_alias"
        ).fetchall()
    }
    assert ("purchasing process", "en", "resolve") in aliases
    assert ("采购流程", "zh-CN", "resolve") in aliases


def test_no_false_crosslingual_merge(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env: None, name_vectors: dict
) -> None:
    fake = _JudgeFake(same={})
    monkeypatch.setattr(resolve_mod, "_post_chat", fake)
    fake_embeddings(monkeypatch)
    base = _unit("bank")
    name_vectors["Bank Of China Branch"] = base
    name_vectors["中国银行"] = _at_cosine(base, 0.9, "zh-bank")

    en_source = _seed_text(db, "the Bank of China branch signs the letter", "en")
    _mention(
        db,
        en_source,
        "Organization",
        "Bank of China branch",
        _unit("en-bank-mention"),
        quote="the Bank of China branch signs the letter",
    )
    run_resolve()
    zh_source = _seed_text(db, "中国银行开户需要两天。", "zh")
    _mention(
        db,
        zh_source,
        "Organization",
        "中国银行",
        _unit("zh-bank-mention"),
        quote="中国银行开户需要两天。",
    )
    run_resolve()

    assert len(_entity_rows(db)) == 2
    assert fake.judge_prompts  # the pair was judged, and rejected


def test_trad_simpl_merge(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env: None, name_vectors: dict
) -> None:
    fake = _JudgeFake(same={})
    monkeypatch.setattr(resolve_mod, "_post_chat", fake)
    fake_embeddings(monkeypatch)
    name_vectors["采购流程"] = _unit("flow")
    name_vectors["採購流程"] = _unit("flow")

    first = _seed_text(db, "采购流程由李四负责。", "simp")
    _mention(db, first, "Process", "采购流程", _unit("s1"), quote="采购流程由李四负责。")
    run_resolve()
    second = _seed_text(db, "採購流程在台灣分支也適用。", "trad")
    _mention(db, second, "Process", "採購流程", _unit("s2"), quote="採購流程在台灣分支也適用。")
    run_resolve()

    assert len(_entity_rows(db)) == 1
    assert not fake.judge_prompts  # folded match auto-aliases before the judge
    aliases = {
        str(row[0])
        for row in db.execute("SELECT normalized_name FROM cmap.entity_alias").fetchall()
    }
    assert {"采购流程", "採購流程"} <= aliases


def test_alias_row_written(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env: None, name_vectors: dict
) -> None:
    fake = _JudgeFake(same={"采购流程": "Purchasing Process"})
    monkeypatch.setattr(resolve_mod, "_post_chat", fake)
    fake_embeddings(monkeypatch)
    base = _unit("process")
    name_vectors["Purchasing Process"] = base
    name_vectors["采购流程"] = _at_cosine(base, 0.9, "zh-name")

    en_source = _seed_text(db, "the purchasing process covers approvals", "en")
    _mention(
        db,
        en_source,
        "Process",
        "purchasing process",
        _unit("en-mention"),
        quote="the purchasing process covers approvals",
    )
    run_resolve()
    zh_source = _seed_text(db, "采购流程由李四负责。", "zh")
    _mention(
        db,
        zh_source,
        "Process",
        "采购流程",
        _unit("zh-mention"),
        quote="采购流程由李四负责。",
    )
    run_resolve()

    rows = db.execute(
        "SELECT normalized_name FROM cmap.entity_alias WHERE normalized_name = '采购流程'"
    ).fetchall()
    assert len(rows) == 1


def test_canonical_name_language_untouched(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env: None, name_vectors: dict
) -> None:
    fake = _JudgeFake(same={"采购流程": "Purchasing Process"})
    monkeypatch.setattr(resolve_mod, "_post_chat", fake)
    fake_embeddings(monkeypatch)
    base = _unit("process")
    name_vectors["Purchasing Process"] = base
    name_vectors["采购流程"] = _at_cosine(base, 0.9, "zh-name")

    en_source = _seed_text(db, "the purchasing process covers approvals", "en")
    _mention(
        db,
        en_source,
        "Process",
        "purchasing process",
        _unit("en-mention"),
        quote="the purchasing process covers approvals",
    )
    run_resolve()
    before = _entity_rows(db)
    zh_source = _seed_text(db, "采购流程由李四负责。", "zh")
    _mention(
        db,
        zh_source,
        "Process",
        "采购流程",
        _unit("zh-mention"),
        quote="采购流程由李四负责。",
    )
    run_resolve()
    after = _entity_rows(db)
    assert after == before


def test_unknown_name_not_promoted(
    monkeypatch: pytest.MonkeyPatch, db: Any, frontier_env: None, name_vectors: dict
) -> None:
    fake = _JudgeFake(same={"影子流程": "Purchasing Process"})
    monkeypatch.setattr(resolve_mod, "_post_chat", fake)
    fake_embeddings(monkeypatch)
    base = _unit("process")
    name_vectors["Purchasing Process"] = base
    name_vectors["影子流程"] = _at_cosine(base, 0.95, "fake-name")

    en_source = _seed_text(db, "the purchasing process covers approvals", "en")
    _mention(
        db,
        en_source,
        "Process",
        "purchasing process",
        _unit("en-mention"),
        quote="the purchasing process covers approvals",
    )
    run_resolve()
    # The fabricated name never appears in its own quote.
    zh_source = _seed_text(db, "李四负责采购审批。", "zh")
    _mention(db, zh_source, "Process", "影子流程", _unit("fake"), quote="李四负责采购审批。")
    run_resolve()

    assert not fake.judge_prompts  # the judge is never asked about un-evidenced names
    entities = _entity_rows(db)
    assert len(entities) == 2  # own node at most; never merged into the real one
    names = {str(row[1]) for row in entities}
    assert "Purchasing Process" in names
    with psycopg.connect(get_settings().database_url) as conn:
        real_id = conn.execute(
            "SELECT id FROM cmap.entity WHERE canonical_name = 'Purchasing Process'"
        ).fetchone()[0]
        leaked = conn.execute(
            "SELECT 1 FROM cmap.entity_alias WHERE entity_id = %s AND normalized_name = %s",
            (real_id, "影子流程"),
        ).fetchone()
    assert leaked is None
