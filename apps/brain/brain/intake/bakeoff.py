"""Score message-intake relation bake-off runs against blind gold (plan step 2.3).

Pure aggregate scorer and call-shape helpers:
- Validates candidate payloads with ``brain.extract.relations.validate_response``.
- Computes stratified whole-thread bootstrap 95% one-sided bounds for quote
  validation, semantic correctness and gold recall, plus exact finite-frame
  stratified upper bounds for whole-thread first-attempt truncation.
- Evaluates the four registered call-shape variants (low-mention skip, short
  joint-call eligibility, wider context windows, recurring machine-digest screen)
  and failure-only candidate fallback blending.
- Emits aggregate counts, rates and hashes only — never source text or quotes.
"""

from __future__ import annotations

import math
import random
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations_with_replacement
from typing import Any

from brain.extract import relations as rel_mod
from brain.read.chunk import count_tokens

MIN_CORRECTNESS = 0.95
MIN_RECALL = 0.90
MIN_QUOTE_VALID = 0.98
MAX_TRUNCATION = 0.01

JOINT_MAX_TOKENS = 400
WIDER_MAX_PASSAGES = 4
WIDER_MAX_TOKENS = 1200
DIGEST_SIMILARITY = 0.95

VERDICTS = frozenset({"keep", "correct", "reject", "withhold"})


@dataclass(frozen=True)
class ThreadMeta:
    thread_id: str
    origin: str
    length_quartile: int
    weight: float = 1.0


@dataclass(frozen=True)
class StratumFrame:
    origin: str
    length_quartile: int
    eligible_remaining: int
    selected_additional: int


@dataclass(frozen=True)
class PassageAttempt:
    thread_id: str
    passage_index: int
    window: tuple[tuple[str, str], ...]
    known_mentions: tuple[rel_mod.KnownMention, ...]
    first_status: str  # ok | truncated | malformed | error
    final_status: str  # ok | truncated | malformed | error
    payload: dict[str, Any] | None
    cost_usd: float


@dataclass(frozen=True)
class BoundSummary:
    estimate: float
    lower_95: float
    upper_95: float


@dataclass(frozen=True)
class CandidateScore:
    label: str
    threads: int
    passages_attempted: int
    passages_usable: int
    first_truncation_threads: int
    first_malformed_passages: int
    raw_relations: int
    quote_valid_relations: int
    validated_unique_relations: int
    kept_relations: int
    matched_gold_relations: int
    total_gold_relations: int
    quote_validation: BoundSummary
    correctness: BoundSummary
    recall: BoundSummary
    truncation_upper_95: float
    usd_per_1000_passages: float
    passes_gates: bool


def claim_identity(
    thread_id: str,
    from_name: str,
    rel_type: str,
    to_name: str,
    quote: str,
    stance: str,
    description: str,
) -> tuple[str, str, str, str, str, str, str]:
    """Canonical 7-tuple identity matching the sandbox blind-pool schema."""
    return (
        thread_id,
        from_name,
        rel_type,
        to_name,
        quote,
        stance,
        description,
    )


def stratified_bootstrap_bounds(
    thread_ratios: Mapping[str, tuple[float, float]],
    meta_by_thread: Mapping[str, ThreadMeta],
    *,
    resamples: int = 10_000,
    seed: int = 60723,
) -> BoundSummary:
    """Whole-thread stratified bootstrap with one-sided 95% confidence bounds."""
    if not thread_ratios:
        return BoundSummary(0.0, 0.0, 0.0)
    strata: dict[tuple[str, int], list[str]] = defaultdict(list)
    for tid in sorted(thread_ratios):
        m = meta_by_thread[tid]
        strata[(m.origin, m.length_quartile)].append(tid)

    def _rate(counts: Mapping[str, int]) -> float:
        num = 0.0
        den = 0.0
        for tid, mult in counts.items():
            w = meta_by_thread[tid].weight * mult
            n_val, d_val = thread_ratios[tid]
            num += n_val * w
            den += d_val * w
        return num / den if den > 0 else 0.0

    point = _rate(dict.fromkeys(thread_ratios, 1))
    rng = random.Random(seed)
    draws: list[float] = []
    ordered_strata = [strata[k] for k in sorted(strata)]
    for _ in range(resamples):
        picked: dict[str, int] = defaultdict(int)
        for group in ordered_strata:
            for tid in rng.choices(group, k=len(group)):
                picked[tid] += 1
        draws.append(_rate(picked))
    draws.sort()
    lo_idx = max(0, int(math.floor(0.05 * resamples)) - 1)
    hi_idx = min(resamples - 1, int(math.floor(0.95 * resamples)) - 1)
    return BoundSummary(
        estimate=round(point, 6),
        lower_95=round(draws[lo_idx], 6),
        upper_95=round(draws[hi_idx], 6),
    )


_FRONTIER_BUDGET = 50_000


def _stratum_hypergeom_pmf(
    pop_n: int, pop_k: int, draw_n: int, max_obs: int
) -> tuple[float, ...]:
    """Exact (P(X = 0), ..., P(X = max_obs)) for X ~ Hypergeometric(pop_n, pop_k, draw_n)."""
    if pop_k < 0 or pop_k > pop_n or draw_n < 0 or draw_n > pop_n:
        return (0.0,) * (max_obs + 1)
    denom = math.comb(pop_n, draw_n)
    pmf = [0.0] * (max_obs + 1)
    low = max(0, draw_n - (pop_n - pop_k))
    high = min(max_obs, pop_k, draw_n)
    for x in range(low, high + 1):
        pmf[x] = math.comb(pop_k, x) * math.comb(pop_n - pop_k, draw_n - x) / denom
    return tuple(pmf)


def _pareto_prune(candidates: Sequence[tuple[float, ...]]) -> list[tuple[float, ...]]:
    """Keep only tuples not componentwise dominated by another tuple."""
    kept: list[tuple[float, ...]] = []
    for cand in sorted(candidates, reverse=True):
        if not any(
            all(a >= b for a, b in zip(prev, cand, strict=True)) for prev in kept
        ):
            kept.append(cand)
    return kept


def conditional_truncation_upper_bound(
    observed_initial_failures: int,
    observed_additional_failures: int,
    target_frame_total: int,
    additional_strata: Sequence[StratumFrame],
    *,
    alpha: float = 0.05,
) -> float:
    """Exact design-based 1-alpha upper bound on affected threads in target_frame_total.

    Conditions on the initial held-out draw (where all initial held-out threads were
    observed with ``observed_initial_failures``) and maximizes ``P(X <= obs_add)``
    over allocations of ``k_rem`` unobserved affected threads across ``additional_strata``.
    """
    if target_frame_total <= 0:
        raise ValueError("target_frame_total must be positive")
    if observed_additional_failures < 0:
        raise ValueError("observed_additional_failures must be non-negative")
    active = [s for s in additional_strata if s.eligible_remaining > 0]
    rem_capacity = sum(s.eligible_remaining for s in active)
    if not active or observed_additional_failures > rem_capacity:
        return round(observed_initial_failures / target_frame_total, 6)

    alpha_prune = max(0.0, alpha - 1e-12)
    if observed_additional_failures == 0:
        dp: list[float] = [1.0]
        for s in active:
            cap = s.eligible_remaining
            draw = s.selected_additional
            p_zero = [
                _stratum_hypergeom_pmf(cap, kh, draw, 0)[0] for kh in range(cap + 1)
            ]
            nxt = [0.0] * (len(dp) + cap)
            for k_used, p_prev in enumerate(dp):
                if p_prev <= alpha_prune:
                    continue
                for kh, p_h in enumerate(p_zero):
                    prod = p_prev * p_h
                    if prod <= alpha_prune:
                        break
                    if prod > nxt[k_used + kh]:
                        nxt[k_used + kh] = prod
            while len(nxt) > 1 and nxt[-1] <= alpha_prune:
                nxt.pop()
            dp = nxt

        max_feasible = observed_initial_failures
        for k_rem in range(min(rem_capacity, len(dp) - 1) + 1):
            if dp[k_rem] > alpha:
                max_feasible = observed_initial_failures + k_rem
            else:
                break
        return round(max_feasible / target_frame_total, 6)

    obs = observed_additional_failures
    frontier: dict[int, list[tuple[float, ...]]] = {0: [(1.0,) * (obs + 1)]}
    for s in active:
        cap = s.eligible_remaining
        draw = s.selected_additional
        pmfs: list[tuple[float, ...]] = []
        for kh in range(cap + 1):
            g = _stratum_hypergeom_pmf(cap, kh, draw, obs)
            if sum(g) <= alpha_prune:
                break
            pmfs.append(g)

        raw_next: dict[int, list[tuple[float, ...]]] = defaultdict(list)
        for k_used, states in frontier.items():
            for kh, g in enumerate(pmfs):
                k_new = k_used + kh
                bucket = raw_next[k_new]
                for f_old in states:
                    f_new = tuple(
                        sum(f_old[t - x] * g[x] for x in range(t + 1))
                        for t in range(obs + 1)
                    )
                    if f_new[obs] > alpha_prune:
                        bucket.append(f_new)
                if len(bucket) > 256:
                    raw_next[k_new] = _pareto_prune(bucket)

        next_frontier: dict[int, list[tuple[float, ...]]] = {}
        total_states = 0
        for k_new, bucket in raw_next.items():
            if not bucket:
                continue
            pruned = _pareto_prune(bucket)
            if pruned:
                next_frontier[k_new] = pruned
                total_states += len(pruned)
                if total_states > _FRONTIER_BUDGET:
                    raise ValueError(
                        "conditional_truncation_upper_bound exceeded exact DP frontier budget"
                    )
        frontier = next_frontier

    max_feasible = observed_initial_failures
    for k_rem in range(obs, rem_capacity + 1):
        states = frontier.get(k_rem)
        best_p = max((st[obs] for st in states), default=0.0) if states else 0.0
        if best_p > alpha:
            max_feasible = observed_initial_failures + k_rem
        else:
            break
    return round(max_feasible / target_frame_total, 6)


def independent_zero_event_upper(n_threads: int, *, alpha: float = 0.05) -> float:
    """Conservative infinite-population 1-alpha upper bound for zero observed events."""
    if n_threads <= 0:
        return 1.0
    return round(1.0 - alpha ** (1.0 / n_threads), 6)


def should_skip_low_mentions(
    mentions: Sequence[rel_mod.KnownMention], *, min_mentions: int = 2
) -> bool:
    """Variant (a): skip the relations call when flat found fewer than min_mentions."""
    return len(mentions) < min_mentions


def is_short_joint_eligible(
    thread_passages: Sequence[str], *, max_tokens: int = JOINT_MAX_TOKENS
) -> bool:
    """Variant (b): one joint flat+relations call for short threads under max_tokens."""
    total = sum(count_tokens(p) for p in thread_passages)
    return 0 < total <= max_tokens


def wider_window_indices(
    passages: Sequence[str],
    anchor: int,
    *,
    max_passages: int = WIDER_MAX_PASSAGES,
    max_tokens: int = WIDER_MAX_TOKENS,
) -> tuple[int, ...]:
    """Variant (c): include preceding passages up to max_passages and max_tokens."""
    if anchor < 0 or anchor >= len(passages):
        raise IndexError("anchor out of range")
    chosen = [anchor]
    budget = count_tokens(passages[anchor])
    cursor = anchor - 1
    while cursor >= 0 and len(chosen) < max_passages:
        t_len = count_tokens(passages[cursor])
        if budget + t_len > max_tokens:
            break
        chosen.append(cursor)
        budget += t_len
        cursor -= 1
    chosen.reverse()
    return tuple(chosen)


def _norm_tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def find_near_duplicate_threads(
    threads: Mapping[str, tuple[str, str]],
    *,
    threshold: float = DIGEST_SIMILARITY,
) -> list[tuple[str, str, float]]:
    """Variant (d): screen same-origin threads for >= threshold 3-gram Jaccard similarity.

    ``threads`` maps ``thread_id -> (origin, full_text)``. Returns ``(id_a, id_b, sim)``
    for lead verification; never auto-drops without confirmation.
    """
    by_origin: dict[str, list[tuple[str, set[tuple[str, ...]]]]] = defaultdict(list)
    for tid in sorted(threads):
        origin, body = threads[tid]
        toks = _norm_tokens(body)
        shingles = (
            {tuple(toks[i : i + 3]) for i in range(len(toks) - 2)}
            if len(toks) >= 3
            else {tuple(toks)}
        )
        by_origin[origin].append((tid, shingles))

    pairs: list[tuple[str, str, float]] = []
    for group in by_origin.values():
        for idx, (tid_a, sh_a) in enumerate(group):
            for tid_b, sh_b in group[idx + 1 :]:
                union = len(sh_a | sh_b)
                if union == 0:
                    continue
                sim = len(sh_a & sh_b) / union
                if sim >= threshold:
                    pairs.append((tid_a, tid_b, round(sim, 4)))
    return pairs


def blend_fallback(
    primary: Sequence[PassageAttempt],
    fallback: Mapping[tuple[str, int], PassageAttempt],
    *,
    retry_on_validation_drop: bool = True,
) -> list[PassageAttempt]:
    """Replace failed primary passages with fallback attempts and sum both costs."""
    blended: list[PassageAttempt] = []
    for p in primary:
        need_fallback = p.final_status != "ok" or p.payload is None
        if not need_fallback and retry_on_validation_drop and p.payload is not None:
            known = {m.key: m for m in p.known_mentions}
            _rels, _new, drops = rel_mod.validate_response(
                list(p.window), known, p.payload
            )
            need_fallback = sum(drops.values()) > 0
        fb = fallback.get((p.thread_id, p.passage_index)) if need_fallback else None
        if fb is None:
            blended.append(p)
            continue
        blended.append(
            PassageAttempt(
                thread_id=p.thread_id,
                passage_index=p.passage_index,
                window=p.window,
                known_mentions=p.known_mentions,
                first_status=p.first_status,
                final_status=fb.final_status,
                payload=fb.payload,
                cost_usd=p.cost_usd + fb.cost_usd,
            )
        )
    return blended


def score_candidate(
    label: str,
    attempts: Sequence[PassageAttempt],
    meta_by_thread: Mapping[str, ThreadMeta],
    claim_verdicts: Mapping[tuple[str, str, str, str, str, str, str], str],
    gold_by_thread: Mapping[str, set[str]],
    claim_to_gold_ids: Mapping[
        tuple[str, str, str, str, str, str, str], Iterable[str]
    ],
    *,
    truncation_upper_override: float | None = None,
    bootstrap_resamples: int = 10_000,
    seed: int = 60723,
) -> CandidateScore:
    """Compute all step 2.3 quality and cost metrics for one candidate route."""
    attempted_threads = sorted({a.thread_id for a in attempts})
    threads = sorted(set(attempted_threads) | set(meta_by_thread))
    trunc_threads = {
        a.thread_id for a in attempts if a.first_status == "truncated"
    }
    first_malformed = sum(1 for a in attempts if a.first_status == "malformed")
    usable = sum(1 for a in attempts if a.final_status == "ok" and a.payload is not None)
    total_cost = sum(a.cost_usd for a in attempts)

    quote_ledger: dict[str, list[int]] = {t: [0, 0] for t in threads}
    unique_by_thread: dict[str, set[tuple[str, str, str, str, str, str, str]]] = {
        t: set() for t in threads
    }

    for att in attempts:
        if att.final_status != "ok" or att.payload is None:
            continue
        raw_rels = att.payload.get("relations") or []
        win_list = list(att.window)
        quote_ledger[att.thread_id][1] += len(raw_rels)
        quote_ledger[att.thread_id][0] += sum(
            1
            for item in raw_rels
            if isinstance(item, dict)
            and rel_mod.find_quote(win_list, str(item.get("quote") or "")) is not None
        )
        known = {m.key: m for m in att.known_mentions}
        rels, new_ms, _drops = rel_mod.validate_response(win_list, known, att.payload)
        names = {m.key: m.name for m in att.known_mentions}
        names.update({m.key: m.surface_name for m in new_ms})
        for r in rels:
            cid = claim_identity(
                att.thread_id,
                names[r.from_key],
                r.rel_type,
                names[r.to_key],
                r.quote,
                r.stance,
                r.description,
            )
            unique_by_thread[att.thread_id].add(cid)

    corr_ledger: dict[str, tuple[float, float]] = {}
    recall_ledger: dict[str, tuple[float, float]] = {}
    quote_ratios: dict[str, tuple[float, float]] = {}

    kept_total = 0
    unique_total = 0
    matched_gold_total = 0
    gold_total = 0

    for tid in threads:
        qv, qr = quote_ledger[tid]
        quote_ratios[tid] = (float(qv), float(qr))

        cids = unique_by_thread[tid]
        unique_total += len(cids)
        kept = sum(1 for cid in cids if claim_verdicts.get(cid) == "keep")
        kept_total += kept
        corr_ledger[tid] = (float(kept), float(len(cids)))

        g_set = gold_by_thread.get(tid, set())
        gold_total += len(g_set)
        matched: set[str] = set()
        for cid in cids:
            if claim_verdicts.get(cid) == "keep":
                matched.update(gid for gid in claim_to_gold_ids.get(cid, ()) if gid in g_set)
        matched_gold_total += len(matched)
        recall_ledger[tid] = (float(len(matched)), float(len(g_set)))

    q_bounds = stratified_bootstrap_bounds(
        quote_ratios, meta_by_thread, resamples=bootstrap_resamples, seed=seed
    )
    c_bounds = stratified_bootstrap_bounds(
        corr_ledger, meta_by_thread, resamples=bootstrap_resamples, seed=seed
    )
    r_bounds = stratified_bootstrap_bounds(
        recall_ledger, meta_by_thread, resamples=bootstrap_resamples, seed=seed
    )

    if truncation_upper_override is not None:
        trunc_upper = truncation_upper_override
    elif not attempted_threads:
        trunc_upper = 1.0
    elif len(trunc_threads) == 0:
        trunc_upper = independent_zero_event_upper(len(attempted_threads))
    else:
        trunc_ratios = {
            t: (1.0 if t in trunc_threads else 0.0, 1.0) for t in attempted_threads
        }
        attempted_meta = {
            t: meta_by_thread[t] for t in attempted_threads if t in meta_by_thread
        }
        trunc_upper = stratified_bootstrap_bounds(
            trunc_ratios, attempted_meta, resamples=bootstrap_resamples, seed=seed
        ).upper_95

    n_att = len(attempts)
    usd_per_1000 = round((total_cost * 1000.0 / n_att) if n_att else 0.0, 4)

    passes = (
        c_bounds.lower_95 >= MIN_CORRECTNESS
        and r_bounds.lower_95 >= MIN_RECALL
        and q_bounds.lower_95 >= MIN_QUOTE_VALID
        and trunc_upper <= MAX_TRUNCATION
    )

    return CandidateScore(
        label=label,
        threads=len(threads),
        passages_attempted=n_att,
        passages_usable=usable,
        first_truncation_threads=len(trunc_threads),
        first_malformed_passages=first_malformed,
        raw_relations=sum(v[1] for v in quote_ledger.values()),
        quote_valid_relations=sum(v[0] for v in quote_ledger.values()),
        validated_unique_relations=unique_total,
        kept_relations=kept_total,
        matched_gold_relations=matched_gold_total,
        total_gold_relations=gold_total,
        quote_validation=q_bounds,
        correctness=c_bounds,
        recall=r_bounds,
        truncation_upper_95=trunc_upper,
        usd_per_1000_passages=usd_per_1000,
        passes_gates=passes,
    )


def select_winner(scores: Sequence[CandidateScore]) -> CandidateScore | None:
    """Among candidates passing all four quality gates, return the lowest-cost route."""
    passing = [s for s in scores if s.passes_gates]
    if not passing:
        return None
    return min(passing, key=lambda s: (s.usd_per_1000_passages, s.label))


__all__ = [
    "BoundSummary",
    "CandidateScore",
    "DIGEST_SIMILARITY",
    "JOINT_MAX_TOKENS",
    "MAX_TRUNCATION",
    "MIN_CORRECTNESS",
    "MIN_QUOTE_VALID",
    "MIN_RECALL",
    "PassageAttempt",
    "StratumFrame",
    "ThreadMeta",
    "VERDICTS",
    "WIDER_MAX_PASSAGES",
    "WIDER_MAX_TOKENS",
    "blend_fallback",
    "claim_identity",
    "combinations_with_replacement",
    "conditional_truncation_upper_bound",
    "find_near_duplicate_threads",
    "independent_zero_event_upper",
    "is_short_joint_eligible",
    "score_candidate",
    "select_winner",
    "should_skip_low_mentions",
    "stratified_bootstrap_bounds",
    "wider_window_indices",
]
