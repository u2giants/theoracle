from hashlib import sha256
from uuid import UUID

import pytest
from pydantic import ValidationError

from oracle_brain.operating_model.source_receipts import (
    EvidenceRef, SourceReceipt, SourceRef, resolve_receipt, validate_evidence,
)


W = UUID("00000000-0000-0000-0000-000000000001")
S = UUID("00000000-0000-0000-0000-000000000002")


def make_receipt(text="alpha beta"):
    digest = sha256(text.encode()).hexdigest()
    ref = SourceRef(workspace_id=W, source_id=S, revision=2,
                    original_sha256="a" * 64, reading_sha256=digest, parser_id="parser-1")
    return SourceReceipt(ref=ref, reading=text, display_revision="r2", aliases=("old",))


def test_exact_evidence_span_and_receipt_hash():
    receipt = make_receipt()
    evidence = EvidenceRef(ref=receipt.ref, start=6, end=10, quote="beta")
    assert validate_evidence(receipt, evidence) == evidence


@pytest.mark.parametrize("kwargs", [
    {"display_revision": "r1"}, {"reading": "changed"},
])
def test_receipt_rejects_forged_display_or_reading(kwargs):
    receipt = make_receipt()
    data = receipt.model_dump()
    data.update(kwargs)
    with pytest.raises(ValidationError):
        SourceReceipt(**data)


def test_resolve_rejects_stale_or_borrowed_revision():
    receipt = make_receipt()
    borrowed = receipt.ref.model_copy(update={"revision": 1})
    with pytest.raises(ValueError):
        resolve_receipt(borrowed, "r1", lambda *_: receipt)
    with pytest.raises(ValueError):
        resolve_receipt(receipt.ref, "r1", lambda *_: receipt)


def test_strict_fields_and_extra_forbidden():
    with pytest.raises(ValidationError):
        SourceRef(workspace_id=str(W), source_id=S, revision=2,
                  original_sha256="a" * 64, reading_sha256="b" * 64, parser_id="p")
    with pytest.raises(ValidationError):
        SourceRef(workspace_id=W, source_id=S, revision=2,
                  original_sha256="A" * 64, reading_sha256="b" * 64, parser_id="p")
    with pytest.raises(ValidationError):
        SourceRef(workspace_id=W, source_id=S, revision=2,
                  original_sha256="a" * 64, reading_sha256="b" * 64, parser_id="p", extra="x")



def test_distinct_upload_ids_are_not_independent_originals():
    import hashlib
    from uuid import UUID
    from oracle_brain.operating_model.source_receipts import canonical_receipts
    text='Invented original';seal=hashlib.sha256(text.encode()).hexdigest()
    receipts=tuple(SourceReceipt(ref=SourceRef(workspace_id=UUID(int=1),source_id=UUID(int=i),revision=1,original_sha256=seal,reading_sha256=seal,parser_id='same'),reading=text,display_revision='r1') for i in (9,2))
    grouped=canonical_receipts(receipts)
    assert len(grouped)==1 and grouped[0].ref.source_id==UUID(int=2) and str(UUID(int=9)) in grouped[0].aliases
