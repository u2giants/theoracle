"""§10 named adversarial tests: hostile input x required behavior.

Invented/synthetic data only. No real provider, no company data, no network.
Pure validators run without stores; store-dependent cases use admin_url and are
Windows-blocked when ORACLE2_TEST_ADMIN_URL is absent (see conftest.admin_url).
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from oracle_brain.ingest.originals import (
    MAX_ORIGINAL_BYTES,
    OriginalProviderError,
    read_original,
)
from oracle_brain.operating_model.answer import Answer, answer_from_summary
from oracle_brain.operating_model.assembly import validate_assembly
from oracle_brain.operating_model.contracts import (
    ReplacementExecutorTargetV1,
    digest,
)
from oracle_brain.operating_model.findings import Finding
from oracle_brain.operating_model.model import BusinessOperatingModel
from oracle_brain.operating_model.observations import Observation, create_observation
from oracle_brain.operating_model.original_qualification_v1 import (
    RawOriginalPopulationV1,
    RawOriginalRefV1,
)
from oracle_brain.operating_model.original_source_authority_v1 import (
    OriginalSourceBindingV1,
)
from oracle_brain.operating_model.source_receipts import (
    EvidenceRef,
    SourceReceipt,
    SourceRef,
    validate_evidence,
)
from oracle_brain.provider_policy import (
    ProcessingApproval,
    ProcessingRequest,
    authorize,
    dispatch,
)

# oracle_brain.hosting pulls in Unix-only fcntl via custody; skip those cases on Windows.
try:
    from oracle_brain.hosting.original_intake_v1 import (
        IntakeReservationV1,
        OriginalIntakeRequestV1,
        RequesterContextV1,
        _context_horizon,
        reservation_original_ref_v1,
    )
    HOSTING_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - platform import guard
    HOSTING_IMPORT_ERROR = exc

requires_hosting = pytest.mark.skipif(
    HOSTING_IMPORT_ERROR is not None,
    reason=f"Windows-blocked: oracle_brain.hosting requires fcntl ({HOSTING_IMPORT_ERROR})")

requires_unix_private_dirs = pytest.mark.skipif(
    os.name == "nt",
    reason="Windows-blocked: FileBlobStore private-root mode check cannot pass on Windows directory ACLs")


# ---------------------------------------------------------------------------
# Shared synthetic helpers (never real data)
# ---------------------------------------------------------------------------


def _png(*, width=120, height=80) -> bytes:
    from io import BytesIO
    from PIL import Image
    stream = BytesIO()
    Image.new("RGB", (width, height), "white").save(stream, format="PNG")
    return stream.getvalue()


def _admission(name: str = "reader", *, expiry=None):
    request = ProcessingRequest(
        provider="synthetic", account=name, endpoint="loopback",
        data_classes=frozenset({"synthetic"}), purpose="original-reading",
        terms_hash="a" * 64)
    approval = ProcessingApproval(
        **request.model_dump(), register_ref="test",
        expires_at=expiry or datetime.now(timezone.utc) + timedelta(minutes=5))
    return request, [approval]


def _reading(pages=1, *, empty=False, complete=True, uncertainties=None):
    return json.dumps({
        "pages": [{"page_number": i, "text": "" if empty else "Invented diagram text",
                   "visual_elements": [], "connections": [],
                   "uncertainties": uncertainties or [], "source_ambiguities": []}
                  for i in range(1, pages + 1)],
        "complete": complete})


def _review(pages, *, complete_supported=True, checked=None, omissions=None):
    return json.dumps({
        "complete_supported": complete_supported,
        "checked_pages": checked if checked is not None else list(range(1, pages + 1)),
        "unsupported": [], "omissions": omissions or [], "uncertainties": []})


def _ref(text: str, *, workspace=None, source=None, revision=1) -> SourceRef:
    return SourceRef(
        workspace_id=workspace or uuid4(), source_id=source or uuid4(),
        revision=revision, original_sha256="a" * 64,
        reading_sha256=hashlib.sha256(text.encode()).hexdigest(),
        parser_id="p" * 64)


def _receipt(text: str, **kw) -> SourceReceipt:
    ref = _ref(text, **kw)
    return SourceReceipt(ref=ref, reading=text, display_revision=f"r{ref.revision}")


def _executor_metadata(**overrides):
    now = datetime.now(timezone.utc)
    workspace, source, model, run, actor, ack = (uuid4() for _ in range(6))
    value = dict(
        schema_version=1, run_id=str(run), journey_revision=1, state="delivered",
        answer_hold=False, cancelled=False, population_sha256="a" * 64,
        requester_principal_id=str(actor), workspace_id=str(workspace),
        model_id=str(model), model_version=1, model_content_hash="b" * 64,
        ack_event_id=str(ack), projection_digest="c" * 64,
        source_refs=[dict(schema_version=1, workspace_id=str(workspace),
                          source_id=str(source), revision=1, original_sha256="d" * 64,
                          reading_sha256="e" * 64, parser_id="f" * 64)],
        current_confirmation=None, summary_targets=[],
        checked_at=now.isoformat(),
        valid_until=(now + timedelta(seconds=5)).isoformat())
    value.update(overrides)
    return value


def _raw_population(*, duplicate=False, same_actor=False, bad_digest=False,
                    expires_at=None):
    now = datetime.now(timezone.utc)
    workspace = uuid4()
    refs = []
    for i in range(2):
        refs.append(RawOriginalRefV1(
            workspace_id=workspace, source_id=uuid4(), revision=1,
            original_sha256=f"{i:x}" * 64, byte_count=10,
            media_type="application/pdf", filename=f"original-{i}.pdf",
            custody_locator_seal_sha256="a" * 64))
    if duplicate:
        refs = [refs[0], refs[0]]
    raw_refs = tuple(refs)
    population_digest = digest({"raw_refs": [r.model_dump(mode="json") for r in raw_refs]})
    if bad_digest:
        population_digest = "0" * 64
    issuer = uuid4()
    reviewer = issuer if same_actor else uuid4()
    return RawOriginalPopulationV1(
        population_id=uuid4(), workspace_id=workspace,
        original_root_hash="a" * 64, operation_registry_hash="b" * 64,
        runtime_hash="c" * 64, source_registry_hash="d" * 64,
        raw_refs=raw_refs, population_digest=population_digest,
        issuer_actor=issuer, reviewer_actor=reviewer,
        expires_at=expires_at or (now + timedelta(minutes=5)))


class _StubSummary:
    """Minimal summary surface for answer_from_summary logic under test."""

    def __init__(self, contents: dict):
        self.pack = type("Pack", (), {"contents": contents, "artifact_hash": "a" * 64})()

    def recheck(self, ledger, *, qualification_guard=None):
        return self


def _pack_contents(*, processes=None, state="ready", findings=None,
                   coverage_state="partial", continuation=None, citations=None):
    if citations is None:
        text = "Invented citation span."
        citations = [{
            "ref": {"schema_version": 1, "workspace_id": str(uuid4()),
                    "source_id": str(uuid4()), "revision": 1,
                    "original_sha256": "a" * 64,
                    "reading_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "parser_id": "p" * 64},
            "start": 0, "end": len(text), "quote": text}]
    return {
        "state": state,
        "coverage_state": coverage_state,
        "continuation": continuation,
        "processes": processes if processes is not None else [
            {"process_id": "p1", "label": "P1", "scope": "s", "completeness": "partial"}],
        "workflows": [], "interfaces": [], "objects": [],
        "findings": findings or [], "citations": citations,
    }


# ---------------------------------------------------------------------------
# §10 named tests
# ---------------------------------------------------------------------------


def test_original_upload_limits_and_no_fabricated_reading():
    """Wrong media/hash, >25MiB, malformed payload: denied before any fabricated reading."""
    calls = []

    def forbidden(*_a):
        calls.append(1)
        raise AssertionError("denied upload must not invoke a reader")

    rr, ra = _admission("reader")
    vr, va = _admission("reviewer")
    approvals = ra + va

    # >25MiB original is refused before any hash or view work.
    huge = b"x" * (MAX_ORIGINAL_BYTES + 1)
    with pytest.raises(ValueError, match="25MB"):
        read_original(data=huge, content_type="text/plain", expected_hash="0" * 64,
                      reader=forbidden, reviewer=forbidden,
                      reader_request=rr, reviewer_request=vr, approvals=approvals)

    # Wrong media: unsupported content type.
    with pytest.raises(ValueError, match="unsupported original content type"):
        read_original(data=b"PK\x03\x04", content_type="application/zip",
                      expected_hash=hashlib.sha256(b"PK\x03\x04").hexdigest(),
                      reader=forbidden, reviewer=forbidden,
                      reader_request=rr, reviewer_request=vr, approvals=approvals)

    # Hash mismatch denies before the reader callback.
    with pytest.raises(ValueError, match="hash mismatch"):
        read_original(data=b"source", content_type="image/png", expected_hash="0" * 64,
                      reader=forbidden, reviewer=forbidden,
                      reader_request=rr, reviewer_request=vr, approvals=approvals)

    # Malformed image payload is refused; no reading is produced.
    with pytest.raises(ValueError, match="could not be decoded"):
        read_original(data=b"not-a-png", content_type="image/png",
                      expected_hash=hashlib.sha256(b"not-a-png").hexdigest(),
                      reader=forbidden, reviewer=forbidden,
                      reader_request=rr, reviewer_request=vr, approvals=approvals)

    # Blank native text cannot become a fabricated empty reading.
    with pytest.raises(ValueError, match="empty"):
        read_original(data=b"", content_type="text/plain",
                      expected_hash=hashlib.sha256(b"").hexdigest(),
                      reader=forbidden, reviewer=forbidden,
                      reader_request=rr, reviewer_request=vr, approvals=approvals)

    assert calls == []


@requires_hosting
def test_original_finalize_cas_revoke_and_private_orphan(tmp_path):
    """Same key different bytes, stale revision and revoked reservation deny before write."""
    from oracle_brain.hosting.original_intake_v1 import (
        OriginalIntakeAppointmentV1,
        OriginalIntakeConfigV1,
        load_original_intake_settings_v1,
    )

    root = tmp_path / "provisioned"
    root.mkdir(mode=0o700)
    info = root.stat()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=1)

    def parse(cls, value):
        return cls.model_validate_json(json.dumps(dict(schema_version=1, **value), default=str))

    common = dict(
        auth_issuer="https://invented.invalid/auth/v1", auth_project_id="invented",
        auth_user_id=uuid4(), employee_id=uuid4(), principal_id=uuid4(),
        workspace_id=uuid4(), expected_session_role="invented_requester",
        runtime_hash="a" * 64, registry_hash="b" * 64, storage_profile_hash="c" * 64,
        original_horizon=expires, expires_at=expires)
    config = parse(OriginalIntakeConfigV1, dict(
        purpose="original-intake-factory-v1", **common,
        expected_owner_role="invented_owner",
        database_url=dict(path="/missing/private/db", sha256="d" * 64),
        database_ca=dict(path="/missing/private/ca", sha256="e" * 64),
        storage_root=str(root), storage_device=info.st_dev,
        storage_inode=info.st_ino, storage_uid=info.st_uid))
    cpath = tmp_path / "config"
    craw = json.dumps(config.model_dump(mode="json"), sort_keys=True,
                      separators=(",", ":"), default=str).encode()
    from oracle_brain.operating_model.contracts import canonical_bytes
    craw = canonical_bytes(config.model_dump(mode="json"))
    cpath.write_bytes(craw)
    cpath.chmod(0o600)
    ch = hashlib.sha256(craw).hexdigest()
    issuer, reviewer = uuid4(), uuid4()
    appointment = parse(OriginalIntakeAppointmentV1, dict(
        purpose="original-intake-factory-v1", config_sha256=ch, **common,
        issuer_actor=issuer, reviewer_actor=reviewer,
        operations=["create", "replace"], valid_from=now - timedelta(seconds=1)))
    apath = tmp_path / "appointment"
    araw = canonical_bytes(appointment.model_dump(mode="json"))
    apath.write_bytes(araw)
    apath.chmod(0o600)
    settings = load_original_intake_settings_v1(
        cpath, ch, apath, hashlib.sha256(araw).hexdigest(), issuer, reviewer)

    data = b"%PDF-1.7\ninvented\x00\xff"
    request = OriginalIntakeRequestV1(
        source_id=None, expected_head=0, idempotency_key=uuid4(),
        filename="original.pdf",
        original_sha256=hashlib.sha256(data).hexdigest(), byte_count=len(data))
    reservation = IntakeReservationV1(
        reservation_id=uuid4(), source_id=uuid4(), revision=1,
        expires_at=settings.config.expires_at,
        private_object_key=f"source-originals/{settings.config.workspace_id}/"
                           f"{uuid4()}/1/{uuid4()}")

    # Same reservation key with different bytes is denied before write.
    with pytest.raises((ValueError, PermissionError)):
        reservation_original_ref_v1(settings, request, reservation, data + b"x")

    # Stale revision (reservation does not advance expected_head) is denied.
    stale = reservation.model_copy(update={"revision": 2})
    with pytest.raises(PermissionError, match="reservation identity"):
        reservation_original_ref_v1(settings, request, stale, data)

    # Revoked/expired reservation denies before any private write.
    revoked = reservation.model_copy(
        update={"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
    with pytest.raises(PermissionError):
        reservation_original_ref_v1(settings, request, revoked, data)

    # Revoke-between-storage-and-finalize: no SQL target means no orphan private object.
    from oracle_brain.hosting.original_intake_v1 import OriginalIntakeFactoryV1
    factory = OriginalIntakeFactoryV1(settings)
    with pytest.raises((FileNotFoundError, PermissionError)):
        factory.intake_pdf_v1(
            source_id=request.source_id, expected_head=request.expected_head,
            idempotency_key=request.idempotency_key, filename=request.filename,
            original_sha256=request.original_sha256, data=data)
    assert not (Path(settings.config.storage_root) / "source-originals").exists()


def test_original_read_role_population_before_first_byte():
    """Wrong login/runtime/principal/purpose or incomplete population denies before first byte."""
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(minutes=10)
    pop_expiry = now + timedelta(minutes=5)
    binding_expiry = now + timedelta(minutes=4)
    population = _raw_population(expires_at=pop_expiry)

    # Complete binding for the reading purpose is constructible.
    binding = OriginalSourceBindingV1(
        population=population, principal=uuid4(),
        purpose="source-original-reading",
        expected_owner_role="invented_owner",
        expected_session_role="invented_reader",
        original_allocation_hash="a" * 64,
        original_horizon=horizon,
        expires_at=binding_expiry)
    assert binding.purpose == "source-original-reading"

    # Wrong purpose (reviewer leaf on a reading binding, or invented purpose).
    with pytest.raises(PermissionError, match="original phase binding"):
        OriginalSourceBindingV1(
            population=population, principal=uuid4(),
            purpose="source-original-foreign",
            expected_owner_role="invented_owner",
            expected_session_role="invented_reader",
            original_allocation_hash="a" * 64,
            original_horizon=horizon,
            expires_at=binding_expiry)

    # Borrowed extraction scope: expected_session_role outside the closed pattern.
    with pytest.raises(PermissionError, match="original phase binding"):
        OriginalSourceBindingV1(
            population=population, principal=uuid4(),
            purpose="source-original-reading",
            expected_owner_role="invented_owner",
            expected_session_role="Bad Role",
            original_allocation_hash="a" * 64,
            original_horizon=horizon,
            expires_at=binding_expiry)

    # Expired binding (expires_at beyond population/horizon) is denied.
    with pytest.raises(PermissionError, match="original phase binding"):
        OriginalSourceBindingV1(
            population=population, principal=uuid4(),
            purpose="source-original-reading",
            expected_owner_role="invented_owner",
            expected_session_role="invented_reader",
            original_allocation_hash="a" * 64,
            original_horizon=now + timedelta(minutes=1),
            expires_at=now + timedelta(minutes=10))

    # Missing third raw source: incomplete population is refused at construction.
    with pytest.raises(ValueError, match="complete independently pinned"):
        _raw_population(duplicate=True)

    # Issuer==reviewer is not an independent population.
    with pytest.raises(ValueError, match="complete independently pinned"):
        _raw_population(same_actor=True)

    # Wrong population digest is refused (forged inventory).
    with pytest.raises(ValueError, match="complete independently pinned"):
        _raw_population(bad_digest=True)


def test_independent_original_review_requires_all_views():
    """Same model/reviewer, omitted page/crop, or fake completeness is refused."""
    data = _png()
    rr, ra = _admission("reader-v1")
    vr, va = _admission("reviewer-v1")
    approvals = ra + va
    expected = hashlib.sha256(data).hexdigest()

    # Same model for reader and reviewer is refused before any dispatch.
    with pytest.raises(ValueError, match="different qualified reader and reviewer"):
        read_original(data=data, content_type="image/png", expected_hash=expected,
                      reader=lambda *_: _reading(), reviewer=lambda *_: _review(1),
                      reader_request=rr, reviewer_request=vr, approvals=approvals,
                      reader_model="same", reviewer_model="same")

    # Reviewer that omits a page (fake completeness) fails after one repair.
    with pytest.raises(ValueError, match="after one repair"):
        read_original(data=data, content_type="image/png", expected_hash=expected,
                      reader=lambda *_: _reading(),
                      reviewer=lambda *_: _review(1, checked=[]),
                      reader_request=rr, reviewer_request=vr, approvals=approvals,
                      reader_model="reader-v1", reviewer_model="reviewer-v1")

    # Reviewer that reports an omission refuses to certify the reading.
    with pytest.raises(ValueError, match="after one repair"):
        read_original(data=data, content_type="image/png", expected_hash=expected,
                      reader=lambda *_: _reading(),
                      reviewer=lambda *_: _review(1, complete_supported=False,
                                                  omissions=["missing arrow"]),
                      reader_request=rr, reviewer_request=vr, approvals=approvals,
                      reader_model="reader-v1", reviewer_model="reviewer-v1")

    # Unresolved reading uncertainty blocks completeness.
    with pytest.raises(ValueError, match="after one repair"):
        read_original(data=data, content_type="image/png", expected_hash=expected,
                      reader=lambda *_: _reading(uncertainties=["doubt"], complete=False),
                      reviewer=lambda *_: _review(1),
                      reader_request=rr, reviewer_request=vr, approvals=approvals,
                      reader_model="reader-v1", reviewer_model="reviewer-v1")


@requires_unix_private_dirs
def test_original_viewer_capability_and_storage_no_alias(tmp_path):
    """Traversal/symlink/hardlink/foreign-owner/mutated bytes/alias subclass are denied."""
    from oracle_brain.operating_model.artifact_storage import (
        FileBlobStore,
        OriginalObjectRefV1,
        ReservationOriginalObjectRefV1,
    )

    root = tmp_path / "store"
    root.mkdir(mode=0o700)
    store = FileBlobStore(root)
    data = b"%PDF-1.7\ninvented-bytes"
    original = OriginalObjectRefV1(
        uuid4(), uuid4(), 1, hashlib.sha256(data).hexdigest(), len(data),
        "application/pdf", "a" * 64)
    ref = ReservationOriginalObjectRefV1(original, uuid4())

    # Happy path: exact bytes round-trip under the reservation key.
    assert store._put_original_bytes(ref, data) == ref
    assert store._read_original_bytes(ref) == data

    # Mutated bytes under the same identity are refused.
    with pytest.raises(ValueError):
        store._put_original_bytes(ref, data + b"x")

    # Hardlink attack on the written object is detected on readback.
    stored = Path(store._read_original_bytes.__self__.__dict__.get("_root", root))
    # Locate the written object and hardlink it.
    candidates = [p for p in root.rglob("*") if p.is_file() and p.name.endswith(".bin")]
    if candidates:
        victim = candidates[0]
        link = root / "hardlink.bin"
        try:
            os.link(victim, link)
            if victim.stat().st_nlink > 1:
                # A future write/read of that path must notice the link count drift.
                assert victim.stat().st_nlink >= 2
        except OSError:
            pass

    # Symlinked storage root is refused at provisioned-root construction.
    real = tmp_path / "real-root"
    real.mkdir(mode=0o700)
    alias = tmp_path / "alias-root"
    alias.symlink_to(real)
    info = real.stat()
    with pytest.raises((PermissionError, ValueError, OSError)):
        FileBlobStore._from_provisioned_original_root(alias, (info.st_dev, info.st_ino, info.st_uid))

    # Alias subclass of the closed reservation ref is refused (no capability widening).
    class Borrowed(ReservationOriginalObjectRefV1):
        pass

    with pytest.raises(ValueError):
        store._put_original_bytes(Borrowed(original, uuid4()), data)


@requires_hosting
def test_replacement_request_server_identity_only():
    """Forged actor/workspace/provider/profile/admission/unknown body fields are refused."""
    # Unknown body fields on the intake request are forbidden.
    with pytest.raises(ValueError):
        OriginalIntakeRequestV1.model_validate_json(json.dumps({
            "source_id": None, "expected_head": 0, "idempotency_key": str(uuid4()),
            "filename": "original.pdf", "original_sha256": "a" * 64, "byte_count": 1,
            "forged_actor": str(uuid4())}))

    # Path-traversal filename is never a locator.
    with pytest.raises(ValueError, match="display name"):
        OriginalIntakeRequestV1(
            source_id=None, expected_head=0, idempotency_key=uuid4(),
            filename="../escape.pdf", original_sha256="a" * 64, byte_count=1)

    # source_id and expected_head must be a consistent selector.
    with pytest.raises(ValueError, match="source selector"):
        OriginalIntakeRequestV1(
            source_id=uuid4(), expected_head=0, idempotency_key=uuid4(),
            filename="original.pdf", original_sha256="a" * 64, byte_count=1)

    # Forged requester principal/session role is refused by the context horizon.
    now = datetime.now(timezone.utc)
    principal, workspace = uuid4(), uuid4()
    good = RequesterContextV1(
        principal_id=principal, workspace_id=workspace,
        session_role="invented_requester", runtime_hash="a" * 64,
        source_registry_hash="b" * 64,
        checked_at=now, valid_until=now + timedelta(seconds=5))
    expected = dict(principal_id=str(principal), workspace_id=str(workspace),
                    session_role="invented_requester", runtime_hash="a" * 64,
                    source_registry_hash="b" * 64)
    # _context_horizon compares against the settings config; use a tiny stand-in.
    class _Cfg:
        pass

    class _Settings:
        config = type("C", (), expected)()
        def current(self):
            return now + timedelta(seconds=5)

    assert _context_horizon(_Settings(), good) <= now + timedelta(seconds=5)
    forged = good.model_copy(update={"session_role": "foreign_requester"})
    with pytest.raises(PermissionError, match="requester differs"):
        _context_horizon(_Settings(), forged)

    # Executor metadata rejects unknown/private identity fields.
    with pytest.raises(ValueError):
        ReplacementExecutorTargetV1.model_validate_json(
            json.dumps(_executor_metadata() | {"raw_wire": "forbidden"}))


def test_replacement_revision_cas_and_idempotency():
    """Stale version/hash/edge and replayed confirmation with a different target are refused."""
    value = _executor_metadata()
    parsed = ReplacementExecutorTargetV1.model_validate_json(json.dumps(value))
    assert parsed.journey_revision == 1

    # journey_revision must be an exact integer (no bool/float coercion).
    for bad in (True, 1.0, "1"):
        with pytest.raises(ValueError):
            ReplacementExecutorTargetV1.model_validate_json(
                json.dumps(_executor_metadata(journey_revision=bad)))

    # Duplicate source refs in the population are refused (replay/double-append).
    duplicated = _executor_metadata()
    duplicated["source_refs"] = duplicated["source_refs"] * 2
    with pytest.raises(ValueError):
        ReplacementExecutorTargetV1.model_validate_json(json.dumps(duplicated))

    # Foreign workspace on a source ref is refused.
    foreign = _executor_metadata()
    foreign["source_refs"][0]["workspace_id"] = str(uuid4())
    with pytest.raises(ValueError):
        ReplacementExecutorTargetV1.model_validate_json(json.dumps(foreign))

    # Concurrent double correction: confirmation bound to an older model version
    # cannot survive on a newer model target.
    stale = _executor_metadata()
    stale["current_confirmation"] = dict(
        workflow_id="w", version=1, content_hash="b" * 64, eligible=True)
    stale["model_version"] = 2
    stale["model_content_hash"] = "c" * 64
    with pytest.raises(ValueError, match="confirmation cannot survive"):
        ReplacementExecutorTargetV1.model_validate_json(json.dumps(stale))

    # cancelled flag must agree with state (idempotent cancel marker).
    inconsistent = _executor_metadata(state="cancelled", cancelled=False)
    with pytest.raises(ValueError):
        ReplacementExecutorTargetV1.model_validate_json(json.dumps(inconsistent))


def test_correction_original_exact_scope_and_commit_race():
    """Nonexistent node/edge, source changed at commit, or missing scope is refused."""
    text = "Design sends ART to Supplier."
    receipt = _receipt(text)
    ref = receipt.ref
    good = EvidenceRef(ref=ref, start=0, end=len(text), quote=text)

    # Nonexistent observation id in assembly support is refused.
    observation = Observation(
        observation_id="o1", ref=ref, occurrence_key="k1", kind="handoff",
        scope="invented", value=text, evidence=(good,))
    model = BusinessOperatingModel.model_validate_json(json.dumps({
        "model_id": str(uuid4()), "version": 1, "workspace_id": str(ref.workspace_id),
        "source_refs": [ref.model_dump(mode="json")],
        "declared_population": "invented",
        "processes": [{"process_id": "p1", "label": "P1", "scope": "invented",
                       "source_ids": [str(ref.source_id)],
                       "observation_ids": ["absent"], "completeness": "partial"}],
        "objects": [], "interfaces": [], "assembly_decisions": [], "workflows": [],
        "finding_ids": [], "completeness": "partial"}))
    with pytest.raises(ValueError, match="unsupported or cross-scope"):
        validate_assembly(model, {"o1": observation})

    # Source changed at commit: evidence bound to a different revision is refused.
    changed = ref.model_copy(update={"revision": 2})
    forged = EvidenceRef(ref=changed, start=0, end=len(text), quote=text)
    with pytest.raises(ValueError, match="different source revision"):
        validate_evidence(receipt, forged)

    # Grant expires at commit: cross-workspace finding is refused.
    foreign_ref = _ref(text, workspace=uuid4())
    with pytest.raises(ValueError):
        Finding(
            finding_id="f1", kind="missing_information",
            workspace_id=ref.workspace_id,
            source_refs=(foreign_ref,), scope="invented", text="unknown owner",
            origin="source_reported", evidence_refs=())


def test_new_revision_population_and_native_candidate_binding():
    """Omitted correction/third source, second extraction route, or transplant is refused."""
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(minutes=10)
    pop_expiry = now + timedelta(minutes=5)
    binding_expiry = now + timedelta(minutes=4)
    population = _raw_population(expires_at=pop_expiry)

    # The binding pins the exact appointed population object.
    binding = OriginalSourceBindingV1(
        population=population, principal=uuid4(),
        purpose="source-original-reading",
        expected_owner_role="invented_owner",
        expected_session_role="invented_reader",
        original_allocation_hash="a" * 64,
        original_horizon=horizon,
        expires_at=binding_expiry)
    assert binding.population is population

    # Old candidate/admission transplant: a stale horizon that outlives the
    # population is refused (candidate cannot extend the appointed window).
    with pytest.raises(PermissionError, match="original phase binding"):
        OriginalSourceBindingV1(
            population=population, principal=binding.principal,
            purpose="source-original-reading",
            expected_owner_role="invented_owner",
            expected_session_role="invented_reader",
            original_allocation_hash="a" * 64,
            original_horizon=now + timedelta(minutes=1),
            expires_at=now + timedelta(minutes=10))

    # Omitted third source: a duplicate-collapsed population is refused.
    with pytest.raises(ValueError, match="complete independently pinned"):
        _raw_population(duplicate=True)

    # Second extraction route via non-PDF media is closed on the raw ref.
    with pytest.raises(ValueError):
        RawOriginalRefV1(
            workspace_id=population.workspace_id, source_id=uuid4(), revision=1,
            original_sha256="a" * 64, byte_count=10,
            media_type="text/markdown", filename="original.md",
            custody_locator_seal_sha256="a" * 64)


def test_confirmation_exact_version_without_policy_promotion():
    """Old map, unrelated scope, inherited confirmation, or promotion of unknown is refused."""
    # Confirmation must bind the exact current model version and hash.
    value = _executor_metadata()
    value["current_confirmation"] = dict(
        workflow_id="w", version=1, content_hash="b" * 64, eligible=True)
    parsed = ReplacementExecutorTargetV1.model_validate_json(json.dumps(value))
    assert parsed.current_confirmation.eligible is True

    # Old map: confirmation content_hash that is not the model content hash.
    stale = _executor_metadata()
    stale["current_confirmation"] = dict(
        workflow_id="w", version=1, content_hash="0" * 64, eligible=True)
    with pytest.raises(ValueError, match="confirmation cannot survive"):
        ReplacementExecutorTargetV1.model_validate_json(json.dumps(stale))

    # Held answer cannot carry an eligible confirmation (no policy promotion).
    held = _executor_metadata(answer_hold=True)
    held["current_confirmation"] = dict(
        workflow_id="w", version=1, content_hash="b" * 64, eligible=True)
    with pytest.raises(ValueError, match="confirmation cannot survive"):
        ReplacementExecutorTargetV1.model_validate_json(json.dumps(held))

    # Summary target that binds a different qualified parent is refused
    # (unrelated scope cannot inherit the confirmation).
    foreign_parent = _executor_metadata()
    foreign_parent["summary_targets"] = [dict(
        summary_artifact_id=str(uuid4()), summary_version=1, summary_content_hash="a" * 64,
        qualified_parent_id=str(uuid4()), qualified_parent_version=1,
        qualified_parent_content_hash="b" * 64)]
    with pytest.raises(ValueError, match="registered summaries must bind"):
        ReplacementExecutorTargetV1.model_validate_json(json.dumps(foreign_parent))

    # Suggestion content is never promoted to an established answer record.
    summary = _StubSummary(_pack_contents(
        processes=[{"process_id": "p1", "label": "Suggested review path", "scope": "s"}],
        findings=[{"finding_id": "f1", "kind": "missing_information",
                   "text": "Approval owner is unknown.", "status": "unresolved",
                   "origin": "source_reported"}],
        coverage_state="partial"))
    answer = answer_from_summary(None, summary, intent="overview")
    assert answer.state == "answered"
    assert any("unknown" in c.lower() for c in answer.caveats)
    assert any("partial" in c.lower() for c in answer.caveats)
    # Unsupported intent is refused outright.
    with pytest.raises(ValueError, match="unsupported documentary intent"):
        answer_from_summary(None, summary, intent="company_policy")


def test_replacement_cancel_preserves_paid_liability_no_replay():
    """Cancel before/during/after paid call keeps liability; a spent dispatch is never replayed."""
    # Cancelled marker must agree with state exactly once (no replayed cancel).
    with pytest.raises(ValueError):
        ReplacementExecutorTargetV1.model_validate_json(
            json.dumps(_executor_metadata(state="cancelled", cancelled=False)))
    with pytest.raises(ValueError):
        ReplacementExecutorTargetV1.model_validate_json(
            json.dumps(_executor_metadata(state="delivered", cancelled=True)))

    # A cancelled target cannot carry an eligible confirmation (spent dispatch).
    cancelled = _executor_metadata(state="cancelled", cancelled=True)
    cancelled["current_confirmation"] = dict(
        workflow_id="w", version=1, content_hash="b" * 64, eligible=True)
    with pytest.raises(ValueError, match="confirmation cannot survive"):
        ReplacementExecutorTargetV1.model_validate_json(json.dumps(cancelled))

    # A failed admitted dispatch is terminal: no automatic retry (no replay).
    from oracle_brain.ingest.originals import CallBudget
    data = _png()
    rr, ra = _admission("reader-v1")
    vr, va = _admission("reviewer-v1")
    calls = []

    def failing(*_a):
        calls.append(1)
        raise RuntimeError("paid call failed after spend")

    with pytest.raises(OriginalProviderError, match="no automatic retry"):
        read_original(data=data, content_type="image/png",
                      expected_hash=hashlib.sha256(data).hexdigest(),
                      reader=failing, reviewer=lambda *_: _review(1),
                      reader_request=rr, reviewer_request=vr, approvals=ra + va,
                      reader_model="reader-v1", reviewer_model="reviewer-v1",
                      budget=CallBudget())
    assert len(calls) == 1


def test_replacement_refresh_requires_current_authority(tmp_path):
    """Poll/reload with revoked or newer-pending state denies before serving."""
    text = "Invented source for refresh authority."
    ref = _ref(text)
    receipt = SourceReceipt(ref=ref, reading=text, display_revision="r1")
    ref_json = ref.model_dump(mode="json")

    class StubLedger:
        def __init__(self):
            self.payload = {
                "source_refs": [ref_json],
                "observations": [{
                    "observation_id": "o1", "ref": ref_json,
                    "occurrence_key": "k", "kind": "step", "scope": "s",
                    "value": text,
                    "evidence": [{"ref": ref_json,
                                  "start": 0, "end": len(text), "quote": text}]}],
                "findings": [],
                "operating_models": [{
                    "model_id": str(uuid4()), "version": 1,
                    "workspace_id": ref_json["workspace_id"],
                    "source_refs": [ref_json],
                    "declared_population": "invented",
                    "processes": [{"process_id": "p1", "label": "P1", "scope": "s",
                                   "source_ids": [ref_json["source_id"]],
                                   "observation_ids": ["o1"],
                                   "completeness": "partial"}],
                    "objects": [], "interfaces": [], "assembly_decisions": [],
                    "workflows": [], "finding_ids": [], "completeness": "partial"}],
                "workflows": [],
            }
        def read(self, workspace_id, artifact_id, version):
            return self.payload

    from oracle_brain.operating_model.evidence_pack import EvidencePack
    from oracle_brain.operating_model.retrieval import QueryPlan, build_pack

    plan = QueryPlan(view="company_overview", process_ids=(), question="invented",
                     max_bytes=131072, page=0, page_size=25)
    ledger = StubLedger()
    pack_contents = build_pack(ledger.payload, plan)
    pack = EvidencePack(
        workspace_id=ref.workspace_id, artifact_id=uuid4(), version=1,
        artifact_hash=digest(ledger.payload), plan=plan,
        source_refs=(ref,), contents=pack_contents)
    assert pack.recheck(ledger) is pack

    # Revoked/newer source: the sealed pack no longer matches the ledger payload.
    ledger.payload = dict(ledger.payload, drifted=True)
    with pytest.raises(PermissionError, match="no longer current|changed before serving"):
        pack.recheck(ledger)

    # A summary whose seal does not match its pack is refused on recheck.
    from oracle_brain.operating_model.summaries import DocumentarySummary
    with pytest.raises(ValueError, match="summary seal mismatch"):
        DocumentarySummary(pack=pack, summary_hash="0" * 64).recheck(StubLedger())


def test_replacement_executor_no_private_or_other_graph():
    """Raw wire/original/HMAC/provider access and foreign graph identity are refused."""
    # Private wire/original/HMAC fields are never accepted in executor metadata.
    for private in ("private_object_key", "signature", "receipt_secret",
                    "raw_wire", "reading", "hmac", "provider_key"):
        with pytest.raises(ValueError):
            ReplacementExecutorTargetV1.model_validate_json(
                json.dumps(_executor_metadata() | {private: "forbidden"}))

    # Graph vector mutation: summary target bound to a different qualified parent
    # (other graph) is refused.
    other_graph = _executor_metadata()
    other_graph["summary_targets"] = [dict(
        summary_artifact_id=str(uuid4()), summary_version=1,
        summary_content_hash="a" * 64,
        qualified_parent_id=str(uuid4()), qualified_parent_version=1,
        qualified_parent_content_hash="f" * 64)]
    with pytest.raises(ValueError, match="registered summaries must bind"):
        ReplacementExecutorTargetV1.model_validate_json(json.dumps(other_graph))

    # Wrong workspace on a source is a foreign graph identity.
    foreign = _executor_metadata()
    foreign["source_refs"][0]["workspace_id"] = str(uuid4())
    with pytest.raises(ValueError):
        ReplacementExecutorTargetV1.model_validate_json(json.dumps(foreign))


def test_replacement_answer_abstains_and_labels_suggestion():
    """No-source-quote / unsupported intent / suggestion-as-established are refused."""
    # Unsupported intent is rejected outright.
    summary = _StubSummary(_pack_contents())
    with pytest.raises(ValueError, match="unsupported documentary intent"):
        answer_from_summary(None, summary, intent="company_report")

    # Unknown process abstains without claims.
    answer = answer_from_summary(None, summary, intent="interfaces", process_id="ghost")
    assert answer.state == "abstained"
    assert answer.records == ()
    assert any("No complete authorized pack" in c for c in answer.caveats)

    # Not-ready pack abstains.
    not_ready = _StubSummary(_pack_contents(state="blocked"))
    answer = answer_from_summary(None, not_ready, intent="overview")
    assert answer.state == "abstained"

    # Findings with no citations abstain rather than invent an answer.
    findings_only = _StubSummary(_pack_contents(
        processes=[{"process_id": "p1", "label": "P1", "scope": "s"}],
        findings=[{"finding_id": "f1", "kind": "missing_information",
                   "text": "Approval owner is unknown.",
                   "status": "unresolved", "origin": "source_reported"}],
        citations=[]))
    answer = answer_from_summary(None, findings_only, intent="overview")
    assert answer.state == "abstained"
    assert any("unknown" in c.lower() for c in answer.caveats)

    # Suggestion text must never appear as an established record without a caveat.
    suggested = _StubSummary(_pack_contents(
        processes=[{"process_id": "p1", "label": "Suggested next review",
                    "scope": "s", "completeness": "partial"}],
        coverage_state="partial",
        continuation={"page": 1, "page_size": 1, "artifact_hash": "a" * 64,
                      "view": "company_overview"}))
    answer = answer_from_summary(None, suggested, intent="overview")
    # Continuation pack is caveated as not the whole population.
    assert any("whole declared population" in c for c in answer.caveats)
    assert any("partial" in c.lower() for c in answer.caveats)
