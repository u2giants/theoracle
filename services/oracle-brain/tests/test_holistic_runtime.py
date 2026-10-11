from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest

from oracle_brain.authz import appoint_owner, delegate
from oracle_brain.holistic_runtime import execute, read_corpus
from oracle_brain.ingest.originals import ReadingProvenance


def _owner_and_reviewer(admin_url, workspace, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    owner, reviewer = uuid4(), uuid4()
    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("ORACLE2_OWNER_PUBLIC_KEY", key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw).hex())
    appointment = uuid4()
    message = f"oracle2-owner-appointment-v1:{workspace}:{owner}:{appointment}".encode()
    appoint_owner(admin_url, workspace_id=workspace, owner_id=owner, appointed_by=uuid4(),
                  appointment_id=appointment, owner_signature_hex=key.sign(message).hex())
    delegate(admin_url, workspace_id=workspace, grantor_id=owner, actor_id=reviewer, scope="review")
    return owner, reviewer


def _insert_sources(admin_url, workspace, *, count=3, draft_status="confirmed", text_prefix="Synthetic source"):
    rows = []
    with psycopg.connect(admin_url) as connection:
        for index in range(count):
            source_id, draft_id, actor = uuid4(), uuid4(), uuid4()
            text = f"{text_prefix} {index + 1}. Step {index + 1} is documented."
            connection.execute(
                "INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (source_id, workspace, actor, f"source-{index + 1}.txt", "text/plain", "confirmed"))
            connection.execute(
                "INSERT INTO oracle2.source_blocks(block_id,source_id,workspace_id,block_index,kind,text,span_start,span_end) "
                "VALUES (%s,%s,%s,0,'original',%s,0,%s)",
                (uuid4(), source_id, workspace, text, len(text)))
            connection.execute(
                "INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) "
                "VALUES (%s,%s,%s,%s,%s,'confirmed')",
                (draft_id, source_id, workspace, actor, f"Process {index + 1}"))
            if draft_status != "confirmed":
                connection.execute("UPDATE oracle2.drafts SET status=%s WHERE draft_id=%s",
                                   (draft_status, draft_id))
            rows.append((source_id, draft_id, text))
    return rows


def _insert_run(admin_url, workspace, actor, source_id, draft_id, *, status="pending"):
    run_id = uuid4()
    with psycopg.connect(admin_url) as connection:
        connection.execute(
            "INSERT INTO oracle2.runs(run_id,workspace_id,actor_id,source_id,draft_id,question,status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (run_id, workspace, actor, source_id, draft_id, "How does this process work?", status))
    return run_id


def _holistic_url(admin_url: str) -> str:
    """Apply local least-privilege SQL only to a loopback test database."""
    parsed = urlsplit(admin_url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.skip("least-privilege role test requires loopback Postgres")
    return urlunsplit((parsed.scheme, "oracle2_holistic:oracle2_local_holistic_only@" +
                       (parsed.hostname or "127.0.0.1") +
                       ((f":{parsed.port}") if parsed.port else ""), parsed.path,
                      parsed.query, parsed.fragment))


def _ensure_holistic_role(admin_url: str) -> str:
    role_url = _holistic_url(admin_url)
    root = Path(__file__).resolve().parents[3]
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute((root / "dev/oracle2/init-postgres.sql").read_text())
        connection.execute((root / "dev/oracle2/grant-postgres.sql").read_text())
    return role_url


class FakePilot:
    digest = "synthetic-reviewed-digest"

    def __init__(self, answer_started=None):
        self.answer_started = answer_started
        self.loaded = False
        self.closed = False

    async def load_reviewed_snapshot(self):
        self.loaded = True

    async def answer(self, question, corpus):
        if self.answer_started:
            self.answer_started()
        return {"answer": {"explanation": [{"text": "Synthetic answer", "citations": []}],
                            "conflicts": [], "unknowns": [], "hypothetical_improvements": []},
                "corpus_digest": self.digest}

    async def close(self):
        self.closed = True


def test_read_corpus_requires_complete_manifest_and_excludes_withdrawn_sources(admin_url, monkeypatch):
    workspace = uuid4()
    rows = _insert_sources(admin_url, workspace)
    monkeypatch.setenv("ORACLE2_HOLISTIC_SOURCE_IDS", json.dumps([str(row[0]) for row in rows]))
    corpus = read_corpus(psycopg.connect(admin_url), workspace)
    assert {item.source_id for item in corpus.sources} == {row[0] for row in rows}
    assert all(item.complete and item.text for item in corpus.sources)

    with psycopg.connect(admin_url) as connection:
        connection.execute("UPDATE oracle2.drafts SET status='withdrawn' WHERE source_id=%s", (rows[0][0],))
    monkeypatch.setenv("ORACLE2_HOLISTIC_SOURCE_IDS", json.dumps([str(row[0]) for row in rows[1:]]))
    with psycopg.connect(admin_url) as connection:
        active = read_corpus(connection, workspace)
    assert {item.source_id for item in active.sources} == {rows[1][0], rows[2][0]}

    monkeypatch.setenv("ORACLE2_HOLISTIC_SOURCE_IDS", json.dumps([str(row[0]) for row in rows]))
    with pytest.raises(ValueError, match="multi-document"):
        with psycopg.connect(admin_url) as connection:
            read_corpus(connection, workspace)


def test_read_corpus_rejects_unconfirmed_or_empty_original(admin_url, monkeypatch):
    workspace = uuid4()
    rows = _insert_sources(admin_url, workspace, count=2, draft_status="draft")
    monkeypatch.setenv("ORACLE2_HOLISTIC_SOURCE_IDS", json.dumps([str(row[0]) for row in rows]))
    monkeypatch.setenv("ORACLE2_DATABASE_URL", admin_url)
    with pytest.raises(RuntimeError, match="unconfirmed or incomplete"):
        with psycopg.connect(admin_url) as connection:
            read_corpus(connection, workspace)
    with psycopg.connect(admin_url) as connection:
        connection.execute("UPDATE oracle2.sources SET status='confirmed' WHERE source_id=%s", (rows[0][0],))
        connection.execute("UPDATE oracle2.source_blocks SET text='' WHERE source_id=%s", (rows[1][0],))
    with pytest.raises(RuntimeError, match="unconfirmed or incomplete"):
        with psycopg.connect(admin_url) as connection:
            read_corpus(connection, workspace)


def test_read_corpus_requires_verified_visual_original_metadata(admin_url, monkeypatch):
    workspace = uuid4()
    rows = _insert_sources(admin_url, workspace, count=2)
    monkeypatch.setenv("ORACLE2_HOLISTIC_SOURCE_IDS", json.dumps([str(row[0]) for row in rows]))
    with psycopg.connect(admin_url) as connection:
        connection.execute("UPDATE oracle2.sources SET content_type='image/png' WHERE workspace_id=%s",
                           (workspace,))
    with pytest.raises(RuntimeError, match="visual original lacks"):
        with psycopg.connect(admin_url) as connection:
            read_corpus(connection, workspace)

    with psycopg.connect(admin_url) as connection:
        for source_id, _, text in rows:
            digest = hashlib.sha256(text.encode()).hexdigest()
            provenance = ReadingProvenance(
                original_hash=digest, content_hash=digest, parser_identity="a" * 64,
                content_type="image/png", evidence_kind="visual_transcription",
                page_count=1, review_receipt="b" * 64).model_dump_json()
            connection.execute(
                "INSERT INTO oracle2.source_blocks(block_id,source_id,workspace_id,block_index,kind,text,span_start,span_end) "
                "VALUES (%s,%s,%s,2147483646,'original-metadata',%s,0,%s)",
                (uuid4(), source_id, workspace, provenance, len(provenance)))
    with psycopg.connect(admin_url) as connection:
        corpus = read_corpus(connection, workspace)
    assert all(item.evidence_kind == "visual_transcription" for item in corpus.sources)
    assert all(item.original_hash == item.content_hash for item in corpus.sources)

    with psycopg.connect(admin_url) as connection:
        connection.execute("UPDATE oracle2.source_blocks SET text=%s WHERE workspace_id=%s AND kind='original-metadata'",
                           (ReadingProvenance(original_hash="c" * 64, content_hash="0" * 64,
                                               parser_identity="a" * 64, content_type="image/png",
                                               evidence_kind="visual_transcription", page_count=1,
                                               review_receipt="b" * 64).model_dump_json(), workspace))
    with pytest.raises(RuntimeError, match="provenance"):
        with psycopg.connect(admin_url) as connection:
            read_corpus(connection, workspace)
def test_execute_run_requires_review_authority_and_cancellation_never_completes(admin_url, monkeypatch):
    workspace = uuid4()
    _, reviewer = _owner_and_reviewer(admin_url, workspace, monkeypatch)
    rows = _insert_sources(admin_url, workspace, count=2)
    monkeypatch.setenv("ORACLE2_HOLISTIC_SOURCE_IDS", json.dumps([str(row[0]) for row in rows]))
    monkeypatch.setenv("ORACLE2_HOLISTIC_WORKSPACE_ID", str(workspace))
    monkeypatch.setenv("ORACLE2_DATABASE_URL", admin_url)
    monkeypatch.setenv("ORACLE2_HOLISTIC_CORPUS_DIGEST", FakePilot.digest)
    fake = FakePilot()
    monkeypatch.setattr("oracle_brain.holistic_runtime.make_pilot", lambda corpus: fake)

    unauthorized = _insert_run(admin_url, workspace, uuid4(), rows[0][0], rows[0][1])
    with pytest.raises(PermissionError, match="authority"):
        asyncio.run(execute("answer", {"workspaceId": str(workspace), "runId": str(unauthorized),
                                        "corpusDigest": FakePilot.digest}))
    cancelled = _insert_run(admin_url, workspace, reviewer, rows[0][0], rows[0][1], status="cancelled")
    with pytest.raises(PermissionError, match="pending"):
        asyncio.run(execute("answer", {"workspaceId": str(workspace), "runId": str(cancelled),
                                        "corpusDigest": FakePilot.digest}))
    with psycopg.connect(admin_url) as connection:
        assert connection.execute("SELECT status FROM oracle2.runs WHERE run_id=%s", (cancelled,)).fetchone()[0] == "cancelled"

    published_then_cancelled = _insert_run(admin_url, workspace, reviewer, rows[0][0], rows[0][1])
    def cancel_during_answer():
        with psycopg.connect(admin_url) as connection:
            connection.execute("UPDATE oracle2.runs SET status='cancelled' WHERE run_id=%s", (published_then_cancelled,))
    monkeypatch.setattr("oracle_brain.holistic_runtime.make_pilot",
                        lambda corpus: FakePilot(answer_started=cancel_during_answer))
    with pytest.raises(PermissionError, match="cancelled or changed"):
        asyncio.run(execute("answer", {"workspaceId": str(workspace), "runId": str(published_then_cancelled),
                                        "corpusDigest": FakePilot.digest}))
    with psycopg.connect(admin_url) as connection:
        assert connection.execute("SELECT status FROM oracle2.runs WHERE run_id=%s",
                                  (published_then_cancelled,)).fetchone()[0] == "cancelled"


def test_execute_rechecks_exact_corpus_before_completion(admin_url, monkeypatch):
    workspace = uuid4()
    _, reviewer = _owner_and_reviewer(admin_url, workspace, monkeypatch)
    rows = _insert_sources(admin_url, workspace, count=2)
    monkeypatch.setenv("ORACLE2_HOLISTIC_SOURCE_IDS", json.dumps([str(row[0]) for row in rows]))
    monkeypatch.setenv("ORACLE2_HOLISTIC_WORKSPACE_ID", str(workspace))
    monkeypatch.setenv("ORACLE2_DATABASE_URL", admin_url)
    monkeypatch.setenv("ORACLE2_HOLISTIC_CORPUS_DIGEST", FakePilot.digest)
    original = read_corpus
    changed = original(psycopg.connect(admin_url), workspace).model_copy(update={"expected_source_ids": frozenset()})
    calls = [original, lambda connection, scope: changed]
    monkeypatch.setattr("oracle_brain.holistic_runtime.read_corpus", lambda connection, scope: calls.pop(0)(connection, scope))
    monkeypatch.setattr("oracle_brain.holistic_runtime.make_pilot", lambda corpus: FakePilot())
    run_id = _insert_run(admin_url, workspace, reviewer, rows[0][0], rows[0][1])
    with pytest.raises(PermissionError, match="corpus or authority changed"):
        asyncio.run(execute("answer", {"workspaceId": str(workspace), "runId": str(run_id),
                                        "corpusDigest": FakePilot.digest}))
    with psycopg.connect(admin_url) as connection:
        assert connection.execute("SELECT status FROM oracle2.runs WHERE run_id=%s", (run_id,)).fetchone()[0] == "processing"


def test_holistic_role_can_read_corpus_and_update_only_run_lifecycle(admin_url):
    holistic_url = _ensure_holistic_role(admin_url)
    workspace = uuid4()
    rows = _insert_sources(admin_url, workspace, count=1)
    run_id = _insert_run(admin_url, workspace, uuid4(), rows[0][0], rows[0][1])
    appointment_id = uuid4()
    with psycopg.connect(admin_url) as connection:
        connection.execute(
            "INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by) "
            "VALUES (%s,%s,%s,'review',%s)",
            (appointment_id, workspace, uuid4(), uuid4()))

    with psycopg.connect(holistic_url) as connection:
        assert connection.execute("SELECT count(*) FROM oracle2.sources WHERE source_id=%s",
                                  (rows[0][0],)).fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM oracle2.appointments WHERE appointment_id=%s",
                                  (appointment_id,)).fetchone()[0] == 1
        connection.execute("UPDATE oracle2.runs SET status='processing', error='synthetic' WHERE run_id=%s",
                           (run_id,))

    forbidden = (
        "UPDATE oracle2.runs SET question='rewritten' WHERE run_id=%s",
        "UPDATE oracle2.sources SET filename='rewritten' WHERE source_id=%s",
        "UPDATE oracle2.appointments SET actor_id=%s WHERE appointment_id=%s",
        "UPDATE oracle2.accepted SET status='withdrawn' WHERE workspace_id=%s",
    )
    args = ((run_id,), (rows[0][0],), (uuid4(), appointment_id), (workspace,))
    for statement, parameters in zip(forbidden, args):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with psycopg.connect(holistic_url) as connection:
                connection.execute(statement, parameters)
