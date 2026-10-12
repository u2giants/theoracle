from hashlib import sha256

import pytest
from pydantic import ValidationError

from oracle_brain.operating_model.observations import Observation, create_observation
from oracle_brain.operating_model.source_receipts import EvidenceRef, SourceReceipt, SourceRef
from uuid import UUID


def receipt():
    text = "same phrase; same phrase"
    ref = SourceRef(workspace_id=UUID(int=1), source_id=UUID(int=2), revision=1,
                    original_sha256="a" * 64, reading_sha256=sha256(text.encode()).hexdigest(), parser_id="p")
    return SourceReceipt(ref=ref, reading=text, display_revision="r1", aliases=("alias",))


def test_identity_is_deterministic_and_aliases_do_not_inflate():
    r = receipt()
    e = EvidenceRef(ref=r.ref, start=0, end=11, quote="same phrase")
    a = create_observation(r, "occ", "step", "scope", "value", (e,))
    b = create_observation(r.model_copy(update={"aliases": ()}), "occ", "step", "scope", "value", (e,))
    assert a.observation_id == b.observation_id


def test_repeated_occurrences_and_scopes_are_distinct():
    r = receipt()
    e1 = EvidenceRef(ref=r.ref, start=0, end=11, quote="same phrase")
    e2 = EvidenceRef(ref=r.ref, start=13, end=24, quote="same phrase")
    assert create_observation(r, "one", "step", "s", "v", (e1,)).observation_id != create_observation(r, "two", "step", "s", "v", (e2,)).observation_id
    assert create_observation(r, "one", "step", "s1", "v", (e1,)).observation_id != create_observation(r, "one", "step", "s2", "v", (e1,)).observation_id


def test_invalid_span_and_strict_fields_rejected():
    r = receipt()
    with pytest.raises(ValueError):
        create_observation(r, "o", "step", "s", "v", (EvidenceRef(ref=r.ref, start=0, end=11, quote="wrong"),))
    with pytest.raises(ValidationError):
        Observation(observation_id="id", ref=r.ref, occurrence_key="o", kind="bad", scope="s", value="v", evidence=())

    with pytest.raises(ValidationError):
        Observation(observation_id="id", ref=r.ref, occurrence_key="o", kind="step", scope="s", value="v", evidence=())

