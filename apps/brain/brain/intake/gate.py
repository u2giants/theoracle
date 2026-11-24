"""Thread relevance gate: deterministic metadata, GPT-6 Luna batch gate,
verdict rules, and the Step 1.5 ScaleDown probe (#607).

Maintains all pure Step 1.5 helpers (`slices`, `thread_verdict`, `sample`,
`predicted_drop_share`, `run_probe`) while adding the Phase 1 4-way pre-ingest
thread classifier (`knowledge`, `transactional_routine`,
`drop_marketing_auto`, `drop_irrelevant_internal`) backed by the ``intake_gate``
model seat and OpenAI Batch (with sync fallback).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from psycopg.types.json import Json

from brain.config import Settings, get_settings, intake_spend_cap
from brain.intake.clean import (
    _is_internal_human,
    portal_template_domain,
    sender_domain,
)
from brain.llm import message_content, post_chat_json_body
from brain.llm_batch import (
    BatchError,
    BatchItem,
    is_openai_batch_model,
    openai_batch_key,
    submit_and_wait_batch,
)
from brain.read.chunk import count_tokens
from brain.seats import stage_model

logger = logging.getLogger(__name__)

SLICE_TOKENS = 1500
MAX_GATE_SLICES = 3
MIN_DROP_THRESHOLD = 0.9
BATCH_MIN_THREADS = 20
SYNC_GATE_WORKERS = 8
GATE_MAX_OUTPUT_TOKENS = 1200
MIN_IRRELEVANT_INTERNAL_CONFIDENCE = 0.70
MIN_EMPLOYEE_REPLY_MARKETING_CONFIDENCE = 0.90

GATE_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "intake_gate.md"

VALID_CATEGORIES = frozenset(
    {
        "knowledge",
        "transactional_routine",
        "drop_marketing_auto",
        "drop_irrelevant_internal",
    }
)
_AUTOMATED_HEADER_NAMES = frozenset(
    {
        "auto-submitted",
        "list-id",
        "list-unsubscribe",
        "list-unsubscribe-post",
        "precedence",
        "x-autoreply",
        "x-campaign-id",
        "x-hubspot-email-id",
        "x-mailgun-variables",
        "x-mc-user",
    }
)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


class IntakeGateError(RuntimeError):
    """Raised when the pre-ingest gate response is missing or malformed."""


def load_gate_prompt() -> str:
    """Return the intake gate prompt template from disk."""
    return GATE_PROMPT_PATH.read_text(encoding="utf-8")


def gate_prompt_hash() -> str:
    """Stable SHA-256 hash of ``prompts/intake_gate.md`` for re-gating audits."""
    return hashlib.sha256(load_gate_prompt().encode("utf-8")).hexdigest()


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


def gate_slices(messages: list[str], limit: int = SLICE_TOKENS) -> list[str]:
    """First and trailing slices capped at ``MAX_GATE_SLICES`` for gate judgment."""
    all_slices = slices(messages, limit=limit)
    if len(all_slices) <= MAX_GATE_SLICES:
        return all_slices
    return [all_slices[0], *all_slices[-(MAX_GATE_SLICES - 1) :]]


def thread_metadata_header(
    origin: str,
    title: str | None,
    items: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Build deterministic thread-level metadata passed alongside text to the gate."""
    external_domains: list[str] = []
    seen_ext: set[str] = set()
    internal_msgs = 0
    external_msgs = 0
    has_automated_headers = False

    for it in items:
        raw = it.get("raw") or {}
        if origin == "email":
            from_ea = (raw.get("from") or {}).get("emailAddress") or {}
            sender_ea = (raw.get("sender") or {}).get("emailAddress") or {}
            addr = str(
                from_ea.get("address")
                or sender_ea.get("address")
                or it.get("author_ref")
                or ""
            ).strip()
            if _is_internal_human(addr):
                internal_msgs += 1
            elif addr:
                external_msgs += 1
                dom = sender_domain(addr)
                if dom and dom not in seen_ext:
                    seen_ext.add(dom)
                    external_domains.append(dom)
            for hdr in raw.get("internetMessageHeaders") or ():
                if not isinstance(hdr, dict):
                    continue
                hname = str(hdr.get("name") or "").strip().lower()
                if hname in _AUTOMATED_HEADER_NAMES:
                    has_automated_headers = True
                    break
        elif origin == "teams_chat":
            internal_msgs += 1

    item_count = len(items)
    if origin == "teams_chat":
        sender_mix = "internal_teams_chat"
    elif origin == "clickup":
        sender_mix = "clickup"
    elif external_msgs == 0:
        sender_mix = "internal_only"
    elif internal_msgs == 0:
        sender_mix = "external_1msg" if item_count <= 1 else "external_multi"
    else:
        sender_mix = "mixed_internal_external"

    employee_replied = bool(
        (sender_mix == "mixed_internal_external" and internal_msgs > 0)
        or (origin == "email" and internal_msgs > 1)
    )
    return {
        "origin": origin,
        "title": (title or "")[:240],
        "item_count": item_count,
        "sender_mix": sender_mix,
        "employee_replied": employee_replied,
        "external_domains": external_domains[:10],
        "portal_template_domain": portal_template_domain(external_domains),
        "has_automated_headers": has_automated_headers,
    }


def build_gate_prompt(header: dict[str, Any], sliced_texts: Sequence[str]) -> str:
    """Fill ``prompts/intake_gate.md`` with metadata JSON and thread text slices."""
    template = load_gate_prompt()
    body = "\n\n---\n\n".join(s for s in sliced_texts if s.strip())
    return (
        template.replace(
            "{{metadata_json}}",
            json.dumps(header, ensure_ascii=False, indent=2),
        )
        .replace("{{thread_text}}", body)
    )


def _as_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in {"true", "1", "yes"}
    return bool(val)


def parse_gate_response(text: str) -> dict[str, Any]:
    """Parse and validate a gate model JSON response."""
    raw = _FENCE_RE.sub("", (text or "").strip())
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise IntakeGateError(f"gate response is not valid JSON: {raw[:200]!r}") from exc
    if not isinstance(data, dict):
        raise IntakeGateError("gate response is not a JSON object")
    category = str(data.get("category") or "").strip()
    if category not in VALID_CATEGORIES:
        raise IntakeGateError(f"invalid gate category {category!r}")
    try:
        conf = float(data.get("confidence", 0.5))
    except (TypeError, ValueError) as exc:
        raise IntakeGateError(f"invalid confidence {data.get('confidence')!r}") from exc
    conf = max(0.0, min(1.0, conf))
    return {
        "category": category,
        "has_process_rule_or_role": _as_bool(data.get("has_process_rule_or_role")),
        "has_operational_problem_or_decision": _as_bool(
            data.get("has_operational_problem_or_decision")
        ),
        "is_automated_or_bulk_template": _as_bool(
            data.get("is_automated_or_bulk_template")
        ),
        "employee_substantively_engaged": _as_bool(
            data.get("employee_substantively_engaged")
        ),
        "confidence": conf,
        "reason": str(data.get("reason") or "").strip()[:500],
    }


def decide_thread_verdict(
    parsed: dict[str, Any], header: dict[str, Any]
) -> tuple[str, str]:
    """Map model output + metadata safety guards to ``(verdict, tier)``."""
    category = parsed["category"]
    conf = float(parsed.get("confidence") or 0.0)
    if category == "knowledge":
        return "kept", "knowledge"
    if category == "transactional_routine":
        return "kept", "transactional_routine"
    if category == "drop_marketing_auto":
        # Protect forwarded marketing where an internal employee added guidance.
        if (
            header.get("employee_replied")
            and conf < MIN_EMPLOYEE_REPLY_MARKETING_CONFIDENCE
        ):
            return "kept", "transactional_routine"
        return "dropped", "drop_marketing_auto"
    if category == "drop_irrelevant_internal":
        if (
            conf < MIN_IRRELEVANT_INTERNAL_CONFIDENCE
            or parsed.get("has_process_rule_or_role")
            or parsed.get("has_operational_problem_or_decision")
        ):
            return "kept", "transactional_routine"
        return "dropped", "drop_irrelevant_internal"
    raise IntakeGateError(f"unhandled gate category {category!r}")


def _gate_sync_one(
    cid: str, prompt: str, model: str, settings: Settings
) -> tuple[str, dict[str, Any]]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": GATE_MAX_OUTPUT_TOKENS,
        "response_format": {"type": "json_object"},
        "reasoning": {"effort": "low", "exclude": True},
    }
    body = post_chat_json_body(
        payload,
        settings=settings,
        timeout=90.0,
        error_cls=IntakeGateError,
        label="intake gate",
        parse=parse_gate_response,
    )
    return cid, parse_gate_response(message_content(body))


def _load_gate_candidates(
    conn: Any,
    *,
    origin: str | None = None,
    limit: int | None = None,
    thread_prefix: str | None = None,
    since: datetime | None = None,
    recheck_prompt: bool = False,
    prompt_hash: str = "",
) -> list[dict[str, Any]]:
    where = (
        ["(verdict = 'pending' OR gate_prompt_hash IS DISTINCT FROM %(prompt_hash)s)"]
        if recheck_prompt
        else ["verdict = 'pending'"]
    )
    if origin:
        where.append("origin = %(origin)s")
    if thread_prefix is not None:
        where.append("starts_with(thread_key, %(thread_prefix)s)")
    if since is not None:
        where.append("COALESCE(ended_at, started_at, updated_at) >= %(since)s")
    sql = (
        "SELECT origin, thread_key, title FROM cmap.intake_thread WHERE "
        + " AND ".join(where)
        + " ORDER BY started_at NULLS LAST, thread_key"
        + (" LIMIT %(limit)s" if limit else "")
    )
    rows = conn.execute(
        sql,
        {
            "origin": origin,
            "limit": limit,
            "thread_prefix": thread_prefix,
            "since": since,
            "prompt_hash": prompt_hash,
        },
    ).fetchall()
    out: list[dict[str, Any]] = []
    for th_origin, th_key, th_title in rows:
        item_rows = conn.execute(
            "SELECT author_ref, body_text, raw FROM cmap.intake_item "
            "WHERE origin = %s AND thread_key = %s "
            "AND drop_reason IS NULL AND body_text <> '' "
            "ORDER BY sent_at NULLS LAST, id",
            (th_origin, th_key),
        ).fetchall()
        items = [
            {"author_ref": r[0], "body_text": r[1], "raw": r[2] or {}}
            for r in item_rows
        ]
        if not items:
            continue
        out.append(
            {
                "origin": str(th_origin),
                "thread_key": str(th_key),
                "title": th_title,
                "items": items,
            }
        )
    return out


def gate_pending_threads(
    conn: Any,
    settings: Settings,
    *,
    origin: str | None = None,
    limit: int | None = None,
    thread_prefix: str | None = None,
    since: datetime | None = None,
    recheck_prompt: bool = False,
) -> dict[str, int]:
    """Classify pending threads on ``intake_gate`` (OpenAI Batch + sync fallback).

    Any individual thread whose API call or parse fails is left ``pending`` so
    it is never silently dropped or falsely ingested.
    """
    prompt_hash = gate_prompt_hash()
    candidates = _load_gate_candidates(
        conn,
        origin=origin,
        limit=limit,
        thread_prefix=thread_prefix,
        since=since,
        recheck_prompt=recheck_prompt,
        prompt_hash=prompt_hash,
    )
    stats: dict[str, int] = {
        "judged": 0,
        "kept": 0,
        "dropped": 0,
        "errors": 0,
        "knowledge": 0,
        "transactional_routine": 0,
        "drop_marketing_auto": 0,
        "drop_irrelevant_internal": 0,
    }
    if not candidates:
        return stats

    model = stage_model(settings, "intake_gate")
    if not model:
        raise RuntimeError(
            "intake_gate stage has no model configured "
            "(set BRAIN_INTAKE_GATE_MODEL, BRAIN_FRONTIER_MODEL, or seat in /models)"
        )

    prepared: list[tuple[str, dict[str, Any], dict[str, Any], str]] = []
    for idx, cand in enumerate(candidates):
        cid = f"t{idx}"
        header = thread_metadata_header(
            cand["origin"], cand["title"], cand["items"]
        )
        sliced = gate_slices([str(it["body_text"]) for it in cand["items"]])
        prompt = build_gate_prompt(header, sliced)
        prepared.append((cid, cand, header, prompt))

    parsed_by_cid: dict[str, dict[str, Any]] = {}
    use_batch = (
        settings.brain_intake_gate_batch_enabled
        and is_openai_batch_model(model)
        and openai_batch_key(settings) is not None
        and len(prepared) >= BATCH_MIN_THREADS
    )
    if use_batch:
        batch_items = [
            BatchItem(
                custom_id=cid,
                prompt=prompt,
                max_output_tokens=GATE_MAX_OUTPUT_TOKENS,
                reasoning_effort="low",
            )
            for cid, _cand, _hdr, prompt in prepared
        ]
        try:
            batch_results = submit_and_wait_batch(
                model,
                batch_items,
                settings=settings,
                parse=parse_gate_response,
                salvage_with_flex=True,
            )
            for cid, res in batch_results.items():
                if res.status == "ok" and res.payload is not None:
                    parsed_by_cid[cid] = res.payload
                else:
                    stats["errors"] += 1
                    logger.warning(
                        "intake_gate batch item %s %s: %s", cid, res.status, res.error
                    )
        except BatchError as exc:
            logger.warning(
                "intake_gate batch failed (%s); falling back to sync calls", exc
            )

    missing = [item for item in prepared if item[0] not in parsed_by_cid]
    if missing:
        with ThreadPoolExecutor(
            max_workers=min(SYNC_GATE_WORKERS, len(missing))
        ) as pool:
            futs = {
                pool.submit(_gate_sync_one, cid, prompt, model, settings): cid
                for cid, _cand, _hdr, prompt in missing
            }
            for fut in as_completed(futs):
                cid = futs[fut]
                try:
                    _cid, parsed = fut.result()
                    parsed_by_cid[cid] = parsed
                except Exception as exc:  # noqa: BLE001 - leave pending on failure
                    stats["errors"] += 1
                    logger.warning("intake_gate thread %s failed: %s", cid, exc)

    for cid, cand, header, _prompt in prepared:
        parsed = parsed_by_cid.get(cid)
        if parsed is None:
            continue
        verdict, tier = decide_thread_verdict(parsed, header)
        scores_payload = {
            "category": parsed["category"],
            "confidence": parsed["confidence"],
            "has_process_rule_or_role": parsed["has_process_rule_or_role"],
            "has_operational_problem_or_decision": parsed[
                "has_operational_problem_or_decision"
            ],
            "is_automated_or_bulk_template": parsed["is_automated_or_bulk_template"],
            "employee_substantively_engaged": parsed[
                "employee_substantively_engaged"
            ],
            "sender_mix": header["sender_mix"],
            "portal_template_domain": header["portal_template_domain"],
        }
        conn.execute(
            "UPDATE cmap.intake_thread SET verdict = %s, tier = %s, "
            "gate_scores = %s, gate_prompt_hash = %s, gate_reason = %s, "
            "gate_model = %s, updated_at = now() "
            "WHERE origin = %s AND thread_key = %s",
            (
                verdict,
                tier,
                Json(scores_payload),
                prompt_hash,
                parsed["reason"],
                model,
                cand["origin"],
                cand["thread_key"],
            ),
        )
        stats["judged"] += 1
        stats[verdict] += 1
        stats[tier] = stats.get(tier, 0) + 1
    conn.commit()
    return stats


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

    from brain.extract.flat import _classify_half, _post_scaledown, classify_body

    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", type=int, default=200)
    ap.add_argument("--max-calls", type=int, default=0)
    ap.add_argument("--run", action="store_true", help="run Tier 1 LLM gate on pending threads")
    ap.add_argument("--origin", choices=["clickup", "teams_chat", "email"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--recheck", action="store_true")
    a = ap.parse_args(argv)
    settings = get_settings()
    if a.run:
        with psycopg.connect(settings.database_url) as conn:
            stats = gate_pending_threads(
                conn,
                settings,
                origin=a.origin,
                limit=a.limit,
                recheck_prompt=a.recheck,
            )
        print("# intake_gate", stats)
        return
    if a.max_calls <= 0:
        raise SystemExit("--max-calls is required with --probe")
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
