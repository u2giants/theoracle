from pathlib import Path
from uuid import UUID, uuid4

import pytest

from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.source_receipts import SourceReceipt, SourceRef
from hashlib import sha256

W = UUID(int=1)

def source():
    text = "ledger source"
    ref = SourceRef(workspace_id=W, source_id=uuid4(), revision=1, original_sha256="a"*64,
                    reading_sha256=sha256(text.encode()).hexdigest(), parser_id="test")
    return SourceReceipt(ref=ref, reading=text, display_revision="r1")

def ledger(admin_url, tmp_path, allowed=lambda: True):
    r = source()
    return Ledger(admin_url, FileBlobStore(tmp_path), principal=W, can_read=lambda *_: allowed(), current_source=lambda *_: r), r

def payload(r):
    return {"source_refs": [r.ref.model_dump(mode="json")], "findings": []}


def test_blob_manifest_outbox_crash_is_recoverable(admin_url, tmp_path: Path):
    db, r = ledger(admin_url, tmp_path)
    aid = uuid4()
    with pytest.raises(RuntimeError):
        db.persist(workspace_id=W, artifact_id=aid, version=1, kind="workflow", payload=payload(r), refs=(r.ref,),
                   permission_digest="b"*64, compiler_digest="c"*64, before_commit=lambda: (_ for _ in ()).throw(RuntimeError("crash")))
    with pytest.raises(PermissionError): db.read(W, aid, 1)
    db.persist(workspace_id=W, artifact_id=aid, version=1, kind="workflow", payload=payload(r), refs=(r.ref,), permission_digest="b"*64, compiler_digest="c"*64)
    assert db.read(W, aid, 1)["source_refs"]
    # Replay uses the original event and manifest rather than creating a second projection.
    db.persist(workspace_id=W, artifact_id=aid, version=1, kind="workflow", payload=payload(r), refs=(r.ref,), permission_digest="b"*64, compiler_digest="c"*64)
    import psycopg
    with psycopg.connect(admin_url) as conn:
        assert conn.execute("SELECT count(*) FROM oracle2.artifact_manifests WHERE artifact_id=%s", (aid,)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM oracle2.outbox WHERE assertion_id=%s", (aid,)).fetchone()[0] == 1



def test_same_id_tampering_fails(admin_url, tmp_path: Path):
    db, r = ledger(admin_url, tmp_path); aid = uuid4()
    db.persist(workspace_id=W, artifact_id=aid, version=1, kind="workflow", payload=payload(r), refs=(r.ref,), permission_digest="b"*64, compiler_digest="c"*64)
    with pytest.raises(ValueError):
        db.persist(workspace_id=W, artifact_id=aid, version=1, kind="workflow", payload={**payload(r), "tampered": True}, refs=(r.ref,), permission_digest="b"*64, compiler_digest="c"*64)


def test_failed_receipt_reloads_but_cannot_serve(admin_url, tmp_path: Path):
    db, r = ledger(admin_url, tmp_path); aid = uuid4()
    db.persist(workspace_id=W, artifact_id=aid, version=1, kind="workflow", payload=payload(r), refs=(r.ref,), permission_digest="b"*64, compiler_digest="c"*64, failed=True)
    with pytest.raises(PermissionError): db.read(W, aid, 1)
    assert db.read(W, aid, 1, include_failed=True)["source_refs"]


def test_permission_removal_denies_serving(admin_url, tmp_path: Path):
    state = {"allowed": True}; db, r = ledger(admin_url, tmp_path, lambda: state["allowed"]); aid = uuid4()
    db.persist(workspace_id=W, artifact_id=aid, version=1, kind="workflow", payload=payload(r), refs=(r.ref,), permission_digest="b"*64, compiler_digest="c"*64)
    state["allowed"] = False
    with pytest.raises(PermissionError): db.read(W, aid, 1)


def test_file_blob_store_seals_corruption_and_symlinks(tmp_path: Path):
    store = FileBlobStore(tmp_path)
    key, seal = store.put(W, {"value": 1})
    path = tmp_path / key
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        store.read(key, seal)
    path.unlink()
    path.symlink_to(tmp_path / "outside")
    with pytest.raises(PermissionError):
        store.read(key, seal)
