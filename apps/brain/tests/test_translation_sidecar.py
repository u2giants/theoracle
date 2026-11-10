"""Step 1.3 gate: the translation sidecar stores companions and serves the map."""

from __future__ import annotations

from typing import Any

from test_schema import run_migrate

from brain.translate import translations_for, upsert_translation

REF_ID = "00000000-0000-4000-8000-0000000000c1"


def test_migrate_twice() -> None:
    run_migrate()
    run_migrate()


def test_write_and_read_roundtrip(db: Any) -> None:
    del db
    upsert_translation("entity", REF_ID, "description", "en", "The purchasing process.")
    upsert_translation("entity", REF_ID, "description", "zh-CN", "采购流程。")
    upsert_translation("entity", REF_ID, "description", "zh-CN", "采购审批流程。")
    assert translations_for("entity", REF_ID) == {
        "en": {"description": "The purchasing process."},
        "zh-CN": {"description": "采购审批流程。"},
    }


def test_map_payload_includes_translations(
    db: Any, client: Any, user_headers: dict[str, str]
) -> None:
    row = db.execute(
        "INSERT INTO cmap.entity (entity_type, canonical_name, description) "
        "VALUES ('Process', '采购审批流程', 'The purchasing approval process.') "
        "RETURNING id"
    ).fetchone()
    db.commit()
    entity_id = str(row[0])
    upsert_translation(
        "entity", entity_id, "description", "zh-CN", "采购审批流程是内部审批流程。"
    )
    body = client.get(f"/entities/{entity_id}", headers=user_headers).json()
    assert body["description"] == "The purchasing approval process."
    assert body["translations"]["zh-CN"]["description"] == "采购审批流程是内部审批流程。"
