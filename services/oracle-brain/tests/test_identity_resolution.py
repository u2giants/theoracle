import pytest

from oracle_brain.knowledge.identity import IdentityRegistry


def test_same_name_people_stay_distinct():
    reg = IdentityRegistry()
    a = reg.register("Wei Zhang", email="wei.a@example.test", team="sourcing")
    b = reg.register("Wei Zhang", email="wei.b@example.test", team="finance")
    assert a.person_id != b.person_id
    ambiguous = reg.resolve("wei  zhang")
    assert ambiguous.ambiguous and ambiguous.person_id is None
    assert set(ambiguous.candidates) == {a.person_id, b.person_id}
    assert reg.resolve("Wei Zhang", team="Finance").person_id == b.person_id


def test_unknown_person_is_explicit_and_name_alone_is_rejected():
    reg = IdentityRegistry()
    r = reg.resolve("Nobody")
    assert r.person_id is None and not r.ambiguous and r.candidates == ()
    with pytest.raises(ValueError):
        reg.register("Only Name")
