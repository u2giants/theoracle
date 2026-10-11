"""Offline tests for original-inventory validation and alias preservation."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from uuid import UUID, uuid4

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/oracle2/read_original_corpus.py"
SPEC = importlib.util.spec_from_file_location("read_original_corpus", SCRIPT)
assert SPEC and SPEC.loader
reader_script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reader_script
SPEC.loader.exec_module(reader_script)


def _invoke(monkeypatch, manifest: Path, originals: Path, output: Path) -> int:
    monkeypatch.setattr(sys, "argv", ["read_original_corpus", "--manifest", str(manifest),
                                       "--originals", str(originals), "--output", str(output)])
    return reader_script.main()


def _native_row(source_id: UUID, data: bytes) -> dict:
    return {"source_id": str(source_id), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data), "file_type": "text/plain"}


def test_manifest_is_fully_validated_before_any_reader_dispatch(tmp_path, monkeypatch):
    originals = tmp_path / "originals"
    originals.mkdir()
    first = uuid4()
    second = uuid4()
    data = b"complete source\n"
    (originals / str(first)).write_bytes(data)
    (originals / str(second)).write_bytes(b"tampered source\n")
    rows = [_native_row(first, data), _native_row(second, data)]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(rows))
    calls = []
    monkeypatch.setattr(reader_script, "read_original", lambda **_: calls.append(True))

    with pytest.raises(ValueError, match="original inventory changed"):
        _invoke(monkeypatch, manifest, originals, tmp_path / "out")
    assert calls == []
    assert not (tmp_path / "out" / "summary.json").exists()


def test_duplicate_original_hash_preserves_every_manifest_alias_without_provider(tmp_path, monkeypatch):
    originals = tmp_path / "originals"
    originals.mkdir()
    data = "step one → review\n".encode("utf-8")
    first, second = uuid4(), uuid4()
    (originals / str(first)).write_bytes(data)
    (originals / str(second)).write_bytes(data)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([_native_row(first, data), _native_row(second, data)]))

    # Native UTF-8 reading must not even inspect provider/admission environment.
    assert _invoke(monkeypatch, manifest, originals, tmp_path / "out") == 0
    digest = hashlib.sha256(data).hexdigest()
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    artifact = json.loads((tmp_path / "out" / f"{digest}.json").read_text())
    assert summary["complete"] is True
    assert summary["distinct_originals_processed"] == 1
    assert summary["aliases"] == {digest: [str(first), str(second)]}
    assert artifact["source_ids"] == [str(first), str(second)]
    assert artifact["text"] == data.decode("utf-8")
