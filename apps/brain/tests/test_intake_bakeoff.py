"""Step 2.3: relation bake-off scorer, conditional truncation bounds and call variants."""

from __future__ import annotations

import math

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


def test_score_candidate_truncation_uses_attempted_threads_not_full_frame() -> None:
    meta = {
        f"t{i}": bakeoff.ThreadMeta(f"t{i}", "email", (i % 4) + 1, weight=1.0)
        for i in range(350)
    }
    m_a = KnownMention("m1", None, "Person", "Alice", "alice")
    m_b = KnownMention("m2", None, "Artifact", "Checklist", "checklist")
    attempts = []
    verdicts = {}
    gold_by_thread = {}
    c2g = {}
    text = "Alice: Alice updates the Checklist every Monday."
    quote = "Alice updates the Checklist every Monday."
    for i in range(30):
        tid = f"t{i}"
        payload = {
            "relations": [
                {
                    "from": "m1",
                    "to": "m2",
                    "type": "PERFORMS",
                    "stance": "practice",
                    "confidence": 0.9,
                    "description": quote,
                    "quote": quote,
                }
            ],
            "new_mentions": [],
        }
        attempts.append(
            bakeoff.PassageAttempt(
                thread_id=tid,
                passage_index=0,
                window=(("0", text),),
                known_mentions=(m_a, m_b),
                first_status="ok",
                final_status="ok",
                payload=payload,
                cost_usd=0.001,
            )
        )
        cid = bakeoff.claim_identity(tid, "Alice", "PERFORMS", "Checklist", quote, "practice", quote)
        verdicts[cid] = "keep"
        gold_by_thread[tid] = {f"g{i}"}
        c2g[cid] = [f"g{i}"]

    score = bakeoff.score_candidate(
        "partial-30",
        attempts,
        meta,
        verdicts,
        gold_by_thread,
        c2g,
        bootstrap_resamples=200,
    )
    assert score.truncation_upper_95 == bakeoff.independent_zero_event_upper(30)
    assert score.truncation_upper_95 == pytest.approx(0.095, abs=0.002)
    assert score.truncation_upper_95 > bakeoff.independent_zero_event_upper(350)
    assert score.passes_gates is False

    # With one truncated attempted thread, bootstrap must still run over the 30 attempted threads.
    attempts_one_trunc = list(attempts)
    attempts_one_trunc[0] = bakeoff.PassageAttempt(
        thread_id="t0",
        passage_index=0,
        window=(("0", text),),
        known_mentions=(m_a, m_b),
        first_status="truncated",
        final_status="ok",
        payload=attempts[0].payload,
        cost_usd=0.001,
    )
    score_one = bakeoff.score_candidate(
        "partial-30-one-trunc",
        attempts_one_trunc,
        meta,
        verdicts,
        gold_by_thread,
        c2g,
        bootstrap_resamples=200,
    )
    assert score_one.truncation_upper_95 >= 1.0 / 30.0


def test_conditional_truncation_exact_dp_above_18_splits_across_strata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strata = [
        bakeoff.StratumFrame("email", 1, 100, 10),
        bakeoff.StratumFrame("email", 2, 100, 10),
    ]
    denom = math.comb(100, 10)
    split_p0 = (math.comb(90, 10) / denom) ** 2
    single_p0 = math.comb(80, 10) / denom
    assert split_p0 > single_p0

    alpha0 = (split_p0 + single_p0) / 2.0
    bound0 = bakeoff.conditional_truncation_upper_bound(0, 0, 200, strata, alpha=alpha0)
    assert bound0 == round(20 / 200, 6)

    # Default alpha=0.05: split (13, 13) passes while single-stratum (25, 0) fails at 25.
    default0 = bakeoff.conditional_truncation_upper_bound(0, 0, 200, strata, alpha=0.05)
    assert default0 == round(26 / 200, 6)

    p0_10 = math.comb(90, 10) / denom
    p1_10 = 10 * math.comb(90, 9) / denom
    split_p1 = p0_10**2 + 2.0 * p0_10 * p1_10
    single_p1 = (math.comb(80, 10) + 20 * math.comb(80, 9)) / denom
    assert split_p1 > single_p1

    alpha1 = (split_p1 + single_p1) / 2.0
    bound1 = bakeoff.conditional_truncation_upper_bound(0, 1, 200, strata, alpha=alpha1)
    assert bound1 == round(20 / 200, 6)

    # Default alpha=0.05 with obs_add=1: verify against exact split maximization over k1 + k2 = k_rem.
    def _exact_two_stratum_p1(k_rem: int) -> float:
        best = 0.0
        for k1 in range(min(k_rem, 100) + 1):
            k2 = k_rem - k1
            if k2 > 100:
                continue
            g1 = bakeoff._stratum_hypergeom_pmf(100, k1, 10, 1)
            g2 = bakeoff._stratum_hypergeom_pmf(100, k2, 10, 1)
            p = g1[0] * g2[0] + g1[0] * g2[1] + g1[1] * g2[0]
            if p > best:
                best = p
        return best

    expected_k1 = max(k for k in range(1, 201) if _exact_two_stratum_p1(k) > 0.05)
    default1 = bakeoff.conditional_truncation_upper_bound(0, 1, 200, strata, alpha=0.05)
    assert default1 == round(expected_k1 / 200, 6)
    assert default1 > round(max(k for k in range(1, 101) if (math.comb(100 - k, 10) + k * math.comb(100 - k, 9)) / denom > 0.05) / 200, 6)

    # Frontier budget overflow raises ValueError instead of falling back.
    monkeypatch.setattr(bakeoff, "_FRONTIER_BUDGET", 3)
    with pytest.raises(ValueError, match="exceeded exact DP frontier budget"):
        bakeoff.conditional_truncation_upper_bound(0, 1, 200, strata, alpha=0.05)
