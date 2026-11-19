"""Step 1.5: gate slicing, verdict rule and probe arithmetic (no live calls)."""

from __future__ import annotations

import pytest

from brain.intake import gate


@pytest.fixture(scope="session", autouse=True)
def _brain_env() -> None:
    """No database needed."""


@pytest.fixture(autouse=True)
def _clean_cmap() -> None:
    """Nothing here truncates tables."""


CHAT = ("chatter", {"chatter": 0.97})
WORK = ("process", {"process": 0.8, "chatter": 0.1})


def test_slices_respect_message_boundaries_and_limit() -> None:
    msgs = ["word " * 100] * 40
    out = gate.slices(msgs, limit=1500)
    assert all(gate.count_tokens(s) <= 1500 for s in out)
    assert sum(s.count("word") for s in out) == 4000


def test_huge_thread_sliced_and_capped() -> None:
    out = gate.slices(["word " * 5000], limit=1500)
    assert len(out) == 1 and gate.count_tokens(out[0]) <= 1600


def test_dropped_only_when_every_slice_is_chatter() -> None:
    assert gate.thread_verdict([CHAT, CHAT], 0.9) == "dropped"
    assert gate.thread_verdict([CHAT, WORK], 0.9) == "kept"
    assert gate.thread_verdict([("chatter", {"chatter": 0.85})], 0.9) == "kept"
    assert gate.thread_verdict([], 0.9) == "kept"
    with pytest.raises(ValueError):
        gate.thread_verdict([CHAT], 0.8)


def test_probe_respects_call_cap_and_weights_by_origin() -> None:
    threads = [
        {"origin": "email", "thread_key": f"e{i}", "messages": ["hi"], "tokens": 100}
        for i in range(10)
    ]
    probed, calls = gate.run_probe(threads, lambda s: CHAT, max_calls=4)
    assert calls == 4 and len(probed) == 4
    share, per = gate.predicted_drop_share(
        probed, {"email": 1000, "clickup": 1000}, 0.9
    )
    assert per == {"email": 1.0, "clickup": 0.0} and share == 0.5


def test_sample_covers_each_origin() -> None:
    threads = [
        {"origin": o, "thread_key": f"{o}{i}", "tokens": i}
        for o, n in (("email", 500), ("clickup", 20))
        for i in range(n)
    ]
    s = gate.sample(threads, 100)
    assert sum(1 for t in s if t["origin"] == "clickup") == 20
    assert len({t["thread_key"] for t in s}) == len(s)
