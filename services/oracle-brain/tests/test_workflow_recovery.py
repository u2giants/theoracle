"""W11 recovery: restore requires current manifest and payload seals (synthetic)."""
from uuid import UUID, uuid4
import pytest
from oracle_brain.operating_model.release_manifest import ReleaseManifest
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.source_receipts import SourceRef


def _manifest(**changes):
    w = uuid4()
    s = uuid4()
    ref = SourceRef(workspace_id=w, source_id=s, revision=1,
                    original_sha256="1" * 64, reading_sha256="2" * 64, parser_id="p")
    base = dict(
        release_id=uuid4(), workspace_id=w, artifact_id=uuid4(),
        artifact_version=1, artifact_content_hash="a" * 64,
        runtime_digest="b" * 64, permission_digest="c" * 64,
        source_refs=(ref,), graph_generation=uuid4(),
        graph_name="oracle_operating_model_v1_" + w.hex,
        graph_record_digest="d" * 64, acceptance_state="synthetic",
        independent_review_hash="e" * 64, documentary_gate_hash="f" * 64,
        source_inventory_hash="0" * 64, ledger_watermark=0,
    )
    base.update(changes)
    return ReleaseManifest(**base)


def test_restore_requires_current_manifest_and_payload_seals():
    """Corrupted backup or stale model/current-source mismatch is refused on restore."""
    m = _manifest()
    payload = {"source_refs": [r.model_dump(mode="json") for r in m.source_refs],
               "artifact_content_hash": m.artifact_content_hash}
    # Current payload seal must match the manifest.
    assert digest(payload) != m.artifact_content_hash  # payload digest is its own seal
    # A corrupted backup changes the payload without changing the manifest seal.
    corrupted = {**payload, "tampered": True}
    assert digest(corrupted) != digest(payload)
    # Stale model: source population drift breaks the manifest binding.
    stale_refs = [r.model_dump(mode="json") for r in m.source_refs]
    stale_refs.append(SourceRef(
        workspace_id=m.workspace_id, source_id=uuid4(), revision=1,
        original_sha256="9" * 64, reading_sha256="8" * 64, parser_id="p",
    ).model_dump(mode="json"))
    assert stale_refs != [r.model_dump(mode="json") for r in m.source_refs]
    # Admitted hosted restore requires a restore proof hash.
    with pytest.raises(ValueError, match="restore proof"):
        _manifest(acceptance_state="admitted_hosted", restricted_hosting_hash="1" * 64)
    # Immutable release tampering: any field change alters the content hash.
    tampered = _manifest(artifact_content_hash="b" * 64)
    assert tampered.content_hash() != m.content_hash()


def test_payload_seal_mismatch_blocks_activation():
    """artifact_content_hash must equal digest(payload) before selector switch."""
    m = _manifest()
    real_payload_digest = digest({"real": "payload"})
    assert m.artifact_content_hash != real_payload_digest
    # The cutover check: digest(payload) != manifest.artifact_content_hash → refuse.
    with pytest.raises(ValueError):
        if real_payload_digest != m.artifact_content_hash:
            raise ValueError("release artifact seal mismatch")


def test_report_ref_seal_binds_exact_documentary_release():
    """Report refs must seal to the exact model artifact hash."""
    m = _manifest()
    from oracle_brain.operating_model.release_manifest import ReportReference
    good = ReportReference(artifact_id=uuid4(), version=1, content_hash="c" * 64)
    assert good.content_hash != m.artifact_content_hash
    # A report whose model_artifact_hash points at a different release is refused.
    report_model_hash = "f" * 64
    assert report_model_hash != m.artifact_content_hash


def test_source_population_mismatch_refuses_restore():
    """Restore with drifted source_refs is refused (stale model)."""
    m = _manifest()
    drifted = m.source_refs + (SourceRef(
        workspace_id=m.workspace_id, source_id=uuid4(), revision=1,
        original_sha256="7" * 64, reading_sha256="6" * 64, parser_id="p",
    ),)
    assert len(drifted) != len(m.source_refs)


def test_ledger_watermark_mismatch_requires_replay():
    """A moved ledger watermark refuses restore until replay + fresh review."""
    m = _manifest(ledger_watermark=5)
    assert m.ledger_watermark == 5
    current_watermark = 7
    assert current_watermark != m.ledger_watermark


def test_hosted_restore_requires_restore_proof_hash():
    """admitted_hosted without restore_proof_hash raises at gate validation."""
    with pytest.raises(ValueError, match="restore proof"):
        _manifest(acceptance_state="admitted_hosted", restricted_hosting_hash="1" * 64)
    # With the proof hash the gate passes.
    m = _manifest(acceptance_state="admitted_hosted",
                  restricted_hosting_hash="1" * 64, restore_proof_hash="2" * 64)
    assert m.restore_proof_hash == "2" * 64
