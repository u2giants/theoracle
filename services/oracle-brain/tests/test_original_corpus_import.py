from __future__ import annotations

import hashlib
import importlib.util
import json
from uuid import uuid4

import pytest
from oracle_brain.ingest.originals import ReadingProvenance, ReadingResponse, ReviewResponse


ROOT = __import__('pathlib').Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "oracle2_import_original_corpus", ROOT / "scripts/oracle2/import_original_corpus.py")
IMPORTER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(IMPORTER)


def _proof(text: str, digest: str, file_type: str, *, evidence_kind: str,
           review_receipt_override: str | None = None, omissions: list[str] | None = None):
    reading = ReadingResponse.model_validate({
        "pages": [{"page_number": 1, "text": text, "visual_elements": [],
                   "connections": [], "uncertainties": []}], "complete": True})
    review = ReviewResponse.model_validate({
        "complete_supported": not omissions, "checked_pages": [1], "unsupported": [],
        "omissions": omissions or [], "uncertainties": []})
    receipt = hashlib.sha256(review.model_dump_json().encode()).hexdigest()
    metadata = ReadingProvenance(
        original_hash=digest, content_hash=hashlib.sha256(text.encode()).hexdigest(),
        parser_identity="a" * 64, content_type=file_type, evidence_kind=evidence_kind,
        page_count=1, review_receipt=review_receipt_override or receipt)
    return {"text": text, "provenance": metadata.model_dump(mode="json"),
            "reading": reading.model_dump(mode="json"), "review": review.model_dump(mode="json")}


def _fixture(tmp_path, *, summary_complete=True, aliases_override=None,
             inventory_override=None, tamper=None, omissions=None, bad_receipt=False):
    native_id, visual_id, alias_id = (uuid4(), uuid4(), uuid4())
    native_text = "Native source text"
    native_digest = hashlib.sha256(native_text.encode()).hexdigest()
    visual_digest = "2" * 64
    manifest = [
        {"source_id": str(native_id), "filename": "native.txt", "file_type": "text/plain", "sha256": native_digest},
        {"source_id": str(visual_id), "filename": "diagram.png", "file_type": "image/png", "sha256": visual_digest},
        {"source_id": str(alias_id), "filename": "diagram-copy.png", "file_type": "image/png", "sha256": visual_digest},
    ]
    inventory = [
        {"source_id": str(native_id), "filename": "native.txt"},
        {"source_id": str(visual_id), "filename": "diagram.png"},
        {"source_id": str(alias_id), "filename": "diagram-copy.png"},
    ]
    if inventory_override is not None:
        inventory = inventory_override
    aliases = aliases_override or {native_digest: [str(native_id)], visual_digest: [str(visual_id), str(alias_id)]}
    summary = {"complete": summary_complete, "failures": [], "original_uploads": len(manifest),
               "aliases": aliases}
    readings = tmp_path / "readings"
    readings.mkdir()
    native = _proof(native_text, native_digest, "text/plain", evidence_kind="native_text")
    native["provenance"]["original_hash"] = native_digest
    native["provenance"]["content_hash"] = native_digest
    native["provenance"]["review_receipt"] = hashlib.sha256(
        (native_digest + ":strict-utf8-byte-roundtrip").encode()).hexdigest()
    visual = _proof("Diagram transcription", visual_digest, "image/png", evidence_kind="visual_transcription",
                    omissions=omissions)
    if bad_receipt:
        visual["provenance"]["review_receipt"] = "f" * 64
    if tamper == "native":
        native["provenance"]["content_hash"] = "f" * 64
    if tamper == "visual":
        visual["provenance"]["content_hash"] = "f" * 64
    (readings / f"{native_digest}.json").write_text(json.dumps(native))
    (readings / f"{visual_digest}.json").write_text(json.dumps(visual))
    manifest_path = tmp_path / "manifest.json"; manifest_path.write_text(json.dumps(manifest))
    inventory_path = tmp_path / "inventory.json"; inventory_path.write_text(json.dumps(inventory))
    (readings / "summary.json").write_text(json.dumps(summary))
    return manifest, readings, inventory


def test_qualified_sources_accepts_native_visual_and_alias_uploads(tmp_path):
    manifest, readings, inventory = _fixture(tmp_path)
    result = IMPORTER.qualified_sources(manifest, readings, inventory)
    assert len(result) == 3
    assert {row[2] for row in result} == {"text/plain", "image/png"}
    assert {row[4].evidence_kind for row in result} == {"native_text", "visual_transcription"}
    assert len({row[4].original_hash for row in result}) == 2


def test_incomplete_summary_rejects_import(tmp_path):
    manifest, readings, inventory = _fixture(tmp_path, summary_complete=False)
    with pytest.raises(ValueError, match="has not passed"):
        IMPORTER.qualified_sources(manifest, readings, inventory)


def test_missing_alias_rejects_import(tmp_path):
    manifest, readings, inventory = _fixture(tmp_path, aliases_override={"1" * 64: []})
    with pytest.raises(ValueError, match="alias missing"):
        IMPORTER.qualified_sources(manifest, readings, inventory)


@pytest.mark.parametrize("tamper", ["native", "visual"])
def test_tampered_content_hash_rejects_import(tmp_path, tamper):
    manifest, readings, inventory = _fixture(tmp_path, tamper=tamper)
    with pytest.raises(ValueError, match="proof does not match"):
        IMPORTER.qualified_sources(manifest, readings, inventory)


def test_missing_native_provenance_rejects_import(tmp_path):
    manifest, readings, inventory = _fixture(tmp_path)
    native_digest = manifest[0]["sha256"]
    native_path = readings / f"{native_digest}.json"
    value = json.loads(native_path.read_text())
    del value["provenance"]
    native_path.write_text(json.dumps(value))
    with pytest.raises((KeyError, ValueError)):
        IMPORTER.qualified_sources(manifest, readings, inventory)


def test_missing_original_upload_inventory_rejects_import(tmp_path):
    manifest, readings, inventory = _fixture(tmp_path, inventory_override=[])
    with pytest.raises(ValueError, match="inventory incomplete"):
        IMPORTER.qualified_sources(manifest, readings, inventory)


def test_visual_review_omissions_reject_import(tmp_path):
    manifest, readings, inventory = _fixture(tmp_path, omissions=["unreadable arrow"])
    with pytest.raises(ValueError, match="proof does not match"):
        IMPORTER.qualified_sources(manifest, readings, inventory)


def test_visual_review_receipt_mismatch_rejects_import(tmp_path):
    manifest, readings, inventory = _fixture(tmp_path, bad_receipt=True)
    with pytest.raises(ValueError, match="proof does not match"):
        IMPORTER.qualified_sources(manifest, readings, inventory)
