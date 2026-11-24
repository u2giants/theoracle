"""Step 1.5: gate slicing, verdict rule and probe arithmetic (no live calls)."""

from __future__ import annotations

from typing import Any

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


def test_metadata_header_and_prompt_contract() -> None:
    items = [
        {
            "author_ref": "vendor@designflow.app",
            "body_text": "OPA submission approved.",
            "raw": {
                "from": {"emailAddress": {"address": "vendor@designflow.app"}},
                "internetMessageHeaders": [{"name": "Auto-Submitted", "value": "auto-generated"}],
            },
        },
        {
            "author_ref": "eparkin@popcre.com",
            "body_text": "Thanks, proceeding with factory.",
            "raw": {"from": {"emailAddress": {"address": "eparkin@popcre.com"}}},
        },
    ]
    hdr = gate.thread_metadata_header("email", "RE: {{thread_text}}", items)
    assert hdr["sender_mix"] == "mixed_internal_external"
    assert hdr["employee_replied"] is True
    assert hdr["external_domains"] == ["designflow.app"]
    assert hdr["portal_template_domain"] == "designflow.app"
    assert hdr["has_automated_headers"] is True

    prompt = gate.build_gate_prompt(hdr, gate.gate_slices([i["body_text"] for i in items]))
    assert '"title": "RE: {{thread_text}}"' in prompt
    assert "OPA submission approved." in prompt


def test_gate_run_requires_spend_cap_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import psycopg

    from brain.config import Settings

    def unexpected_connection(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Gate opened a connection without a spend cap")

    monkeypatch.setattr(gate, "get_settings", lambda: Settings(brain_intake_max_usd=None))
    monkeypatch.setattr(psycopg, "connect", unexpected_connection)
    with pytest.raises(RuntimeError, match="BRAIN_INTAKE_MAX_USD"):
        gate.main(["--run"])


def test_parse_and_decide_thread_verdict_guards() -> None:
    parsed = gate.parse_gate_response(
        '```json\n{"category":"drop_marketing_auto","has_process_rule_or_role":false,'
        '"has_operational_problem_or_decision":false,"is_automated_or_bulk_template":true,'
        '"employee_substantively_engaged":true,"confidence":0.82,"reason":"Promo"}\n```'
    )
    # Forwarded marketing with employee reply and confidence < 0.90 is protected as transactional_routine.
    assert gate.decide_thread_verdict(parsed, {"employee_replied": True}) == (
        "kept",
        "transactional_routine",
    )
    assert gate.decide_thread_verdict(parsed, {"employee_replied": False}) == (
        "dropped",
        "drop_marketing_auto",
    )

    # drop_irrelevant_internal requires confidence >= 0.70 and no process/problem flags.
    low_conf = dict(parsed, category="drop_irrelevant_internal", confidence=0.65)
    assert gate.decide_thread_verdict(low_conf, {}) == ("kept", "transactional_routine")
    has_rule = dict(
        parsed,
        category="drop_irrelevant_internal",
        confidence=0.95,
        has_process_rule_or_role=True,
    )
    assert gate.decide_thread_verdict(has_rule, {}) == ("kept", "transactional_routine")
    clean_drop = dict(parsed, category="drop_irrelevant_internal", confidence=0.88)
    assert gate.decide_thread_verdict(clean_drop, {}) == (
        "dropped",
        "drop_irrelevant_internal",
    )


def test_gate_pending_threads_batch_and_db_persistence(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from brain.config import get_settings
    from brain.llm_batch import BatchResult
    from brain.migrate import migrate

    migrate()
    db.execute("TRUNCATE cmap.intake_item, cmap.intake_thread")
    for idx in range(21):
        key = f"th-{idx:02d}"
        db.execute(
            "INSERT INTO cmap.intake_thread (origin, thread_key, title) "
            "VALUES ('email', %s, %s)",
            (key, f"Subject {idx}"),
        )
        db.execute(
            "INSERT INTO cmap.intake_item (origin, external_id, thread_key, author_ref, "
            "sent_at, body_text, raw, content_hash) "
            "VALUES ('email', %s, %s, 'eparkin@popcre.com', now(), %s, "
            '\'{"from": {"emailAddress": {"address": "eparkin@popcre.com"}}}\'::jsonb, \'h\')',
            (f"m-{idx}", key, "Disney approved SKU 123 and CAD was received today."),
        )
    db.execute(
        "UPDATE cmap.intake_thread SET verdict = 'dropped', "
        """gate_scores = '{"rule": "too_short"}' WHERE thread_key = 'th-20'"""
    )
    db.commit()

    def _fake_batch(model: str, items: Any, **kwargs: Any) -> dict[str, BatchResult]:
        assert model == "openai/gpt-6-luna"
        assert len(items) == 20
        out: dict[str, BatchResult] = {}
        for pos, it in enumerate(items):
            if pos >= 18:
                out[it.custom_id] = BatchResult(it.custom_id, "error", None)
                continue
            if pos == 0:
                cat = "knowledge"
            elif pos == 1:
                cat = "transactional_routine"
            elif pos == 2:
                cat = "drop_marketing_auto"
            else:
                cat = "drop_irrelevant_internal"
            out[it.custom_id] = BatchResult(
                custom_id=it.custom_id,
                status="ok",
                payload={
                    "category": cat,
                    "has_process_rule_or_role": cat == "knowledge",
                    "has_operational_problem_or_decision": cat == "knowledge",
                    "is_automated_or_bulk_template": cat == "drop_marketing_auto",
                    "employee_substantively_engaged": cat == "knowledge",
                    "confidence": 0.95,
                    "reason": f"classified as {cat}",
                },
            )
        return out

    def _fake_sync(cid: str, *args: Any) -> tuple[str, dict[str, Any]]:
        if cid == "t19":
            raise gate.IntakeGateError("sync failed")
        assert cid == "t18"
        return cid, gate.parse_gate_response(
            '{"category":"drop_irrelevant_internal","confidence":0.95}'
        )

    monkeypatch.setattr(gate, "submit_and_wait_batch", _fake_batch)
    monkeypatch.setattr(gate, "_gate_sync_one", _fake_sync)
    monkeypatch.setenv("BRAIN_INTAKE_GATE_MODEL", "openai/gpt-6-luna")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()
    try:
        stats = gate.gate_pending_threads(db, get_settings(), recheck_prompt=True)
    finally:
        get_settings.cache_clear()

    assert stats["judged"] == 19
    assert stats["kept"] == 2
    assert stats["dropped"] == 17
    assert stats["errors"] == 1
    rows = dict(
        db.execute(
            "SELECT thread_key, verdict || ':' || COALESCE(tier, '') "
            "FROM cmap.intake_thread WHERE thread_key IN ('th-00', 'th-01', 'th-02', 'th-03')"
        ).fetchall()
    )
    assert rows == {
        "th-00": "kept:knowledge",
        "th-01": "kept:transactional_routine",
        "th-02": "dropped:drop_marketing_auto",
        "th-03": "dropped:drop_irrelevant_internal",
    }
