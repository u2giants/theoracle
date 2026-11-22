"""Step 2.3: relation bake-off scorer, conditional truncation bounds and call variants."""

from __future__ import annotations

import pytest

from brain.extract.relations import KnownMention
from brain.intake import bakeoff


@pytest.fixture(scope="session", autouse=True)
def _brain_env() -> None:
    """No database needed."""


@pytest.fixture(autouse=True)
def _clean_cmap() -> None:
    """Nothing here truncates tables."""


def test_conditional_truncation_reproduces_350_thread_zero_event_bound() -> None:
    # Matches the preregistered 641-thread target frame (150 initial + 200 added).
    strata = [
        bakeoff.StratumFrame("clickup", q, 0, 0) for q in (1, 2, 3, 4)
    ] + [
        bakeoff.StratumFrame("email", q, 99, 40) for q in (1, 2, 3, 4)
    ] + [
        bakeoff.StratumFrame("teams_chat", 1, 23, 10),
        bakeoff.StratumFrame("teams_chat", 2, 24, 10),
        bakeoff.StratumFrame("teams_chat", 3, 24, 10),
        bakeoff.StratumFrame("teams_chat", 4, 24, 10),
    ]
    upper_zero = bakeoff.conditional_truncation_upper_bound(0, 0, 641, strata)
    assert upper_zero == round(5 / 641, 6)
    assert upper_zero < bakeoff.MAX_TRUNCATION

    # One observed truncation in the additional sample raises the valid bound above 1%.
    upper_one = bakeoff.conditional_truncation_upper_bound(0, 1, 641, strata)
    assert upper_one > upper_zero
    assert upper_one > bakeoff.MAX_TRUNCATION


def test_call_shape_helpers_cover_all_four_variants() -> None:
    m1 = KnownMention("m1", None, "Person", "Alice", "alice")
    m2 = KnownMention("m2", None, "System", "ClickUp", "clickup")
    assert bakeoff.should_skip_low_mentions([]) is True
    assert bakeoff.should_skip_low_mentions([m1]) is True
    assert bakeoff.should_skip_low_mentions([m1, m2]) is False

    assert bakeoff.is_short_joint_eligible(["Alice: quick check on task 42"]) is True
    assert bakeoff.is_short_joint_eligible(["word " * 450]) is False

    passages = ["turn " * 80, "turn " * 80, "turn " * 80, "turn " * 80, "turn " * 80]
    assert bakeoff.wider_window_indices(passages, 0) == (0,)
    assert bakeoff.wider_window_indices(passages, 3) == (0, 1, 2, 3)
    assert bakeoff.wider_window_indices(passages, 4, max_tokens=200) == (3, 4)

    dups = bakeoff.find_near_duplicate_threads(
        {
            "t1": ("email", "Automated daily digest for project board alpha status green all items"),
            "t2": ("email", "Automated daily digest for project board alpha status green all items"),
            "t3": ("teams_chat", "Automated daily digest for project board alpha status green all items"),
            "t4": ("email", "Completely separate discussion about packaging dielines and transit"),
        }
    )
    assert len(dups) == 1 and dups[0][:2] == ("t1", "t2") and dups[0][2] == 1.0


def test_score_candidate_and_winner_selection_enforce_all_gates() -> None:
    meta = {
        f"t{i}": bakeoff.ThreadMeta(f"t{i}", "email", (i % 4) + 1, weight=1.0)
        for i in range(10)
    }
    m_a = KnownMention("m1", None, "Person", "Alice", "alice")
    m_b = KnownMention("m2", None, "Artifact", "Checklist", "checklist")

    def _make_attempts(quote: str, cost: float, *, bad_one: bool = False) -> list[bakeoff.PassageAttempt]:
        out = []
        for i in range(10):
            tid = f"t{i}"
            text = "Alice: Alice updates the Checklist every Monday."
            desc = "Wrong claim" if (bad_one and i < 3) else "Alice updates the Checklist every Monday."
            payload = {
                "relations": [
                    {
                        "from": "m1",
                        "to": "m2",
                        "type": "PERFORMS",
                        "stance": "practice",
                        "confidence": 0.9,
                        "description": desc,
                        "quote": quote,
                    }
                ],
                "new_mentions": [],
            }
            out.append(
                bakeoff.PassageAttempt(
                    thread_id=tid,
                    passage_index=0,
                    window=(("0", text),),
                    known_mentions=(m_a, m_b),
                    first_status="ok",
                    final_status="ok",
                    payload=payload,
                    cost_usd=cost,
                )
            )
        return out

    verdicts = {}
    gold_by_thread = {}
    c2g = {}
    for i in range(10):
        tid = f"t{i}"
        good = bakeoff.claim_identity(
            tid,
            "Alice",
            "PERFORMS",
            "Checklist",
            "Alice updates the Checklist every Monday.",
            "practice",
            "Alice updates the Checklist every Monday.",
        )
        bad = bakeoff.claim_identity(
            tid,
            "Alice",
            "PERFORMS",
            "Checklist",
            "Alice updates the Checklist every Monday.",
            "practice",
            "Wrong claim",
        )
        verdicts[good] = "keep"
        verdicts[bad] = "correct"
        gold_by_thread[tid] = {f"g{i}"}
        c2g[good] = [f"g{i}"]

    cheap_fail = bakeoff.score_candidate(
        "cheap-fail",
        _make_attempts("Alice updates the Checklist every Monday.", 0.0005, bad_one=True),
        meta,
        verdicts,
        gold_by_thread,
        c2g,
        truncation_upper_override=0.0078,
        bootstrap_resamples=500,
    )
    assert cheap_fail.passes_gates is False

    pass_dear = bakeoff.score_candidate(
        "pass-dear",
        _make_attempts("Alice updates the Checklist every Monday.", 0.0020),
        meta,
        verdicts,
        gold_by_thread,
        c2g,
        truncation_upper_override=0.0078,
        bootstrap_resamples=500,
    )
    pass_cheap = bakeoff.score_candidate(
        "pass-cheap",
        _make_attempts("Alice updates the Checklist every Monday.", 0.0008),
        meta,
        verdicts,
        gold_by_thread,
        c2g,
        truncation_upper_override=0.0078,
        bootstrap_resamples=500,
    )
    assert pass_dear.passes_gates is True
    assert pass_cheap.passes_gates is True
    winner = bakeoff.select_winner([cheap_fail, pass_dear, pass_cheap])
    assert winner is not None and winner.label == "pass-cheap"
    assert bakeoff.select_winner([cheap_fail]) is None


def test_blend_fallback_replaces_failed_passages_and_sums_cost() -> None:
    m_a = KnownMention("m1", None, "Person", "Alice", "alice")
    m_b = KnownMention("m2", None, "Artifact", "Checklist", "checklist")
    win = (("0", "Alice: Alice updates the Checklist."),)
    primary = [
        bakeoff.PassageAttempt(
            "t0",
            0,
            win,
            (m_a, m_b),
            "malformed",
            "malformed",
            None,
            0.0005,
        )
    ]
    fb_payload = {
        "relations": [
            {
                "from": "m1",
                "to": "m2",
                "type": "PERFORMS",
                "stance": "practice",
                "confidence": 0.9,
                "description": "Alice updates the Checklist.",
                "quote": "Alice updates the Checklist.",
            }
        ]
    }
    fb = {
        ("t0", 0): bakeoff.PassageAttempt(
            "t0", 0, win, (m_a, m_b), "ok", "ok", fb_payload, 0.0010
        )
    }
    blended = bakeoff.blend_fallback(primary, fb)
    assert len(blended) == 1
    assert blended[0].first_status == "malformed"
    assert blended[0].final_status == "ok"
    assert blended[0].cost_usd == pytest.approx(0.0015)
