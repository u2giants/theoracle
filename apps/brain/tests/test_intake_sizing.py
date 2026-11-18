"""Step 0.1 sizing helpers: free-rule counting, member matching, spend cap. Synthetic data only."""

from __future__ import annotations

import pytest

from brain.config import Settings, intake_spend_cap
from brain.intake import sizing


def test_tally_free_rules_and_passages():
    t = sizing.Tally()
    kept = (
        t.message("")
        + t.message("👍")
        + t.message("word " * 300)
        + t.message("word " * 300)
    )
    t.thread(kept)
    t.thread(t.message("ok"))
    assert t.records == 5
    assert set(t.dropped) == {"empty", "reaction", "duplicate", "too_short_thread"}
    assert t.threads == 2 and t.threads_kept == 1
    assert t.passages == 1


def test_clickup_member_falls_back_to_unique_first_name():
    members = [
        {"user": {"id": 1, "email": "a@example.test", "username": "Ann Lee"}},
        {"user": {"id": 2, "email": "b@other.test", "username": "Bo"}},
    ]
    assert sizing.clickup_member(members, "a@example.test", "X Y") == 1
    assert sizing.clickup_member(members, "b@example.test", "Bo Diaz") == 2
    assert sizing.clickup_member(members, "c@example.test", "Cy") is None


def test_html_text_strips_tags():
    assert sizing.html_text("<p>Hi &amp; bye</p>") == "Hi & bye"


@pytest.mark.parametrize("cap", [None, 0, -1])
def test_intake_refuses_without_cap(cap):
    with pytest.raises(RuntimeError):
        intake_spend_cap(Settings(brain_intake_max_usd=cap))


def test_intake_cap_returned():
    assert intake_spend_cap(Settings(brain_intake_max_usd=5)) == 5
