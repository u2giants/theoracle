"""Thread relevance gate: slicing, verdict rule and the step 1.5 probe (#607).

The plan builds the paid gate only if a 200-thread probe predicts it would
drop at least 30% of thread tokens. This module holds the pure parts the gate
would use (slices of at most 1,500 tokens on message boundaries; a thread is
dropped only when EVERY slice is chatter at or above the threshold, never
below 0.9) and the probe itself.

Probe: ``python -m brain.intake.gate --probe 200 --max-calls 600``. It reads
cleaned, pending threads from staging, samples them by origin and length,
classifies each slice once with ScaleDown, and prints counts and shares only.
Requires BRAIN_INTAKE_MAX_USD (spend cap) and SCALEDOWN_API_KEY.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from brain.read.chunk import count_tokens

SLICE_TOKENS = 1500
MIN_DROP_THRESHOLD = 0.9


def slices(messages: list[str], limit: int = SLICE_TOKENS) -> list[str]:
    """Join messages into slices of at most ``limit`` tokens, never splitting one.

    A single message over the limit becomes its own slice (cut at the limit
    by words, for classification only; stored text is never changed).
    """
    out: list[str] = []
    cur: list[str] = []
    n = 0
    for m in messages:
        t = count_tokens(m)
        if t > limit:
            if cur:
                out.append("\n".join(cur))
                cur, n = [], 0
            words = m.split()
            out.append(" ".join(words[: max(1, len(words) * limit // t)]))
            continue
        if cur and n + t > limit:
            out.append("\n".join(cur))
            cur, n = [], 0
        cur.append(m)
        n += t
    if cur:
        out.append("\n".join(cur))
    return out


def thread_verdict(
    slice_scores: list[tuple[str | None, dict[str, float]]], threshold: float
) -> str:
    """'dropped' only if every slice is chatter at >= threshold; else 'kept'."""
    if threshold < MIN_DROP_THRESHOLD:
        raise ValueError("drop threshold may never be below 0.9 (plan L2)")
    if not slice_scores:
        return "kept"
    for top, scores in slice_scores:
        if top != "chatter" or scores.get("chatter", 0.0) < threshold:
            return "kept"
    return "dropped"


def sample(
    threads: list[dict[str, Any]], n: int, min_per_origin: int = 30
) -> list[dict[str, Any]]:
    """Stratified sample: per origin a share by thread count (at least
    ``min_per_origin``), spread evenly across that origin's length order."""
    by: dict[str, list[dict[str, Any]]] = {}
    for t in threads:
        by.setdefault(t["origin"], []).append(t)
    total = sum(len(v) for v in by.values()) or 1
    out: list[dict[str, Any]] = []
    for _origin, ts in sorted(by.items()):
        k = min(len(ts), max(min_per_origin, round(n * len(ts) / total)))
        ts = sorted(ts, key=lambda t: (t["tokens"], t["thread_key"]))
        step = len(ts) / k
        out.extend(ts[int(i * step)] for i in range(k))
    return out


def predicted_drop_share(
    probed: list[dict[str, Any]],
    origin_tokens: dict[str, int],
    threshold: float,
) -> tuple[float, dict[str, float]]:
    """Token share predicted dropped, each origin weighted by its full token total."""
    per: dict[str, float] = {}
    for origin in origin_tokens:
        rows = [p for p in probed if p["origin"] == origin]
        tok = sum(p["tokens"] for p in rows)
        drop = sum(
            p["tokens"]
            for p in rows
            if thread_verdict(p["scores"], threshold) == "dropped"
        )
        per[origin] = drop / tok if tok else 0.0
    grand = sum(origin_tokens.values()) or 1
    return sum(per[o] * origin_tokens[o] for o in origin_tokens) / grand, per


def run_probe(
    threads: list[dict[str, Any]],
    classify: Callable[[str], tuple[str | None, dict[str, float]]],
    max_calls: int,
) -> tuple[list[dict[str, Any]], int]:
    """Classify each slice of each sampled thread; stop at ``max_calls``."""
    calls = 0
    done: list[dict[str, Any]] = []
    for t in threads:
        sl = slices(t["messages"])
        if calls + len(sl) > max_calls:
            break
        t = dict(t, scores=[classify(s) for s in sl])
        calls += len(sl)
        done.append(t)
    return done, calls


def _load(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT t.origin, t.thread_key, i.body_text FROM cmap.intake_thread t "
        "JOIN cmap.intake_item i ON i.origin = t.origin AND i.thread_key = t.thread_key "
        "WHERE t.verdict = 'pending' AND i.drop_reason IS NULL AND i.body_text <> '' "
        "ORDER BY t.origin, t.thread_key, i.sent_at, i.id"
    ).fetchall()
    by: dict[tuple[str, str], dict[str, Any]] = {}
    for origin, key, body in rows:
        t = by.setdefault(
            (origin, key),
            {"origin": origin, "thread_key": key, "messages": [], "tokens": 0},
        )
        t["messages"].append(body)
        t["tokens"] += count_tokens(body)
    return list(by.values())


def main(argv: list[str] | None = None) -> None:
    import psycopg

    from brain.config import get_settings, intake_spend_cap
    from brain.extract.flat import _classify_half, _post_scaledown, classify_body

    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", type=int, default=200)
    ap.add_argument("--max-calls", type=int, required=True)
    a = ap.parse_args(argv)
    settings = get_settings()
    intake_spend_cap(settings)  # refuses to run without a cap
    with psycopg.connect(settings.database_url) as conn:
        threads = _load(conn)
    origin_tokens: dict[str, int] = {}
    for t in threads:
        origin_tokens[t["origin"]] = origin_tokens.get(t["origin"], 0) + t["tokens"]
    picked = sample(threads, a.probe)

    def classify(text: str) -> tuple[str | None, dict[str, float]]:
        body = dict(classify_body(text), reasoning=False)
        return _classify_half(_post_scaledown("/classify", body, settings))

    probed, calls = run_probe(picked, classify, a.max_calls)
    print(f"# gate probe: {len(probed)} threads, {calls} ScaleDown calls")
    print("pending threads", len(threads), "tokens by origin", origin_tokens)
    for thr in (0.9, 0.95):
        share, per = predicted_drop_share(probed, origin_tokens, thr)
        dropped = sum(
            1 for p in probed if thread_verdict(p["scores"], thr) == "dropped"
        )
        print(
            f"threshold {thr}: threads dropped {dropped}/{len(probed)}  "
            f"predicted token share dropped {share:.3f}  by origin "
            + ", ".join(f"{o} {v:.3f}" for o, v in sorted(per.items()))
        )
    chatter_top = sum(1 for p in probed for top, _ in p["scores"] if top == "chatter")
    print("slices with chatter on top", chatter_top, "of", calls)


if __name__ == "__main__":
    main()
