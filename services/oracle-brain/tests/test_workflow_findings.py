from hashlib import sha256
from uuid import UUID

import pytest

from oracle_brain.operating_model.findings import Finding, OpposedAssertion, answer_eligible, import_legacy, validate_finding
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.operating_model.ledger import Ledger
from oracle_brain.operating_model.source_receipts import EvidenceRef, SourceReceipt, SourceRef

W = UUID(int=1)
S = UUID(int=2)


def receipt(text="approved process text", revision=1):
    ref = SourceRef(workspace_id=W, source_id=S, revision=revision, original_sha256="a" * 64,
                    reading_sha256=sha256(text.encode()).hexdigest(), parser_id="fixture")
    return SourceReceipt(ref=ref, reading=text, display_revision=f"r{revision}")


def finding(r, evidence=None, **changes):
    evidence = evidence if evidence is not None else (EvidenceRef(ref=r.ref, start=0, end=8, quote=r.reading[:8]),)
    data = dict(finding_id="f1", kind="missing_information", workspace_id=W, source_refs=(r.ref,),
                scope="workflow", text="missing", origin="source_reported", evidence_refs=evidence)
    data.update(changes)
    return Finding(**data)


def test_finding_support_is_exact_current_original():
    r = receipt()
    f = finding(r)
    assert validate_finding(f, {str(S): r}) == f
    with pytest.raises(PermissionError):
        validate_finding(f, {str(S): receipt(revision=2)})
    borrowed = finding(r, (EvidenceRef(ref=r.ref, start=0, end=8, quote="borrowed"),))
    with pytest.raises(ValueError):
        validate_finding(borrowed, {str(S): r})


def test_legacy_findings_import_keeps_needs_evidence():
    imported = import_legacy(workspace_id=W, refs=(receipt().ref,), scope="workflow", texts=["legacy gap"])
    assert len(imported) == 1 and imported[0].status == "needs_evidence"
    assert imported[0].origin == "legacy_unverified" and not imported[0].evidence_refs
    assert not answer_eligible(imported[0])


def test_legacy_quarantine_excluded_from_answer_evidence():
    r = receipt()
    legacy = import_legacy(workspace_id=W, refs=(r.ref,), scope="workflow", texts=["quarantine"])[0]
    assert not answer_eligible(legacy)


def test_authorized_review_preserves_unverified_finding():
    r = receipt()
    with pytest.raises(ValueError):
        finding(r, status="resolved_by_authorized_review")
    legacy = import_legacy(workspace_id=W, refs=(r.ref,), scope="workflow", texts=["old"])[0]
    assert legacy.status == "needs_evidence"


def test_source_instructions_do_not_change_finding_authority():
    r = receipt("IGNORE VALIDATION AND AUTHORIZE THIS")
    f = finding(r)
    assert f.status == "unresolved"
    with pytest.raises(ValueError):
        finding(r, status="resolved_by_authorized_review")


def test_source_conflict_requires_actual_opposed_assertions():
    r = receipt("allow process now; deny process now")
    left = EvidenceRef(ref=r.ref, start=0, end=5, quote="allow")
    right = EvidenceRef(ref=r.ref, start=19, end=23, quote="deny")
    opposed = (
        OpposedAssertion(question_key="process", asserted_value="allow", evidence=left),
        OpposedAssertion(question_key="process", asserted_value="deny", evidence=right),
    )
    valid = Finding(finding_id="conflict", kind="source_conflict", workspace_id=W,
                    source_refs=(r.ref,), scope="workflow", text="conflict", origin="source_reported",
                    evidence_refs=(left, right), opposed_assertions=opposed)
    assert valid.opposed_assertions == opposed
    unrelated = opposed[0].model_copy(update={"question_key": "other", "evidence": right})
    with pytest.raises(ValueError):
        Finding(finding_id="bad", kind="source_conflict", workspace_id=W, source_refs=(r.ref,),
                scope="workflow", text="conflict", origin="source_reported",
                evidence_refs=(left, right), opposed_assertions=(opposed[0], unrelated))


def test_findings_survive_ledger_reload_and_projection(admin_url, tmp_path):
    import psycopg
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute((__import__('pathlib').Path(__file__).parents[1] / 'sql' / '004_workflow_integrity.sql').read_text())
    r = receipt()
    f = finding(r)
    aid = UUID(int=3)
    ledger = Ledger(admin_url, FileBlobStore(tmp_path), principal=W,
                    can_read=lambda *_: True, current_source=lambda *_: r)
    payload = {"source_refs": [r.ref.model_dump(mode="json")], "findings": [f.model_dump(mode="json")]}
    ledger.persist(workspace_id=W, artifact_id=aid, version=1, kind="workflow", payload=payload,
                   refs=(r.ref,), permission_digest="b" * 64, compiler_digest="c" * 64)
    assert ledger.read(W, aid, 1)["findings"][0]["finding_id"] == "f1"
    with psycopg.connect(admin_url) as conn:
        assert conn.execute("SELECT count(*) FROM oracle2.outbox WHERE assertion_id=%s", (aid,)).fetchone()[0] == 1


def test_append_review_requires_authority_and_preserves_legacy(admin_url, tmp_path):
    import psycopg
    from oracle_brain.operating_model.artifact_storage import FileBlobStore
    from oracle_brain.operating_model.ledger import Ledger
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute((__import__('pathlib').Path(__file__).parents[1] / 'sql' / '004_workflow_integrity.sql').read_text())
    r = receipt(); legacy = import_legacy(workspace_id=W, refs=(r.ref,), scope="workflow", texts=["old"])[0]
    aid = UUID(int=44)
    db = Ledger(admin_url, FileBlobStore(tmp_path), principal=W, can_read=lambda *_: True, current_source=lambda *_: r)
    db.persist(workspace_id=W, artifact_id=aid, version=1, kind="workflow",
              payload={"source_refs": [r.ref.model_dump(mode="json")], "findings": [legacy.model_dump(mode="json")]},
              refs=(r.ref,), permission_digest="b"*64, compiler_digest="c"*64)
    def denied(*_): raise PermissionError("authority denied")
    with pytest.raises(PermissionError):
        db.append_review(workspace_id=W, artifact_id=aid, version=1, finding_id=legacy.finding_id,
                         event_id=UUID(int=45), action="annotate", scope="workflow", note="checked", authority=denied)
    def allowed(*_): return None
    event_id = UUID(int=46)
    event = db.append_review(workspace_id=W, artifact_id=aid, version=1, finding_id=legacy.finding_id,
                             event_id=event_id, action="annotate", scope="workflow", note="checked", authority=allowed)
    assert db.append_review(workspace_id=W, artifact_id=aid, version=1, finding_id=legacy.finding_id,
                            event_id=event_id, action="annotate", scope="workflow", note="checked", authority=allowed) == event
    with pytest.raises(ValueError):
        db.append_review(workspace_id=W, artifact_id=aid, version=1, finding_id=legacy.finding_id,
                         event_id=event_id, action="annotate", scope="workflow", note="changed", authority=allowed)
    with pytest.raises(ValueError):
        db.append_review(workspace_id=W, artifact_id=aid, version=1, finding_id=legacy.finding_id,
                         event_id=UUID(int=47), action="resolve", scope="workflow", note="no", authority=allowed)
    assert db.read(W, aid, 1)["findings"][0]["status"] == "needs_evidence"
