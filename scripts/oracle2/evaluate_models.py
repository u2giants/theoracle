#!/usr/bin/env python3
"""S02 model evaluation on the PUBLIC synthetic corpus only.

Sends only the invented question records from evals/oracle2/synthetic-cases.jsonl
to a primary and a fallback model, each call admitted by the default-deny
provider policy with approvals scoped to data class "synthetic". Scores are
deterministic diagnostics (citation resolution, answer/abstain match, required
fact term coverage); they are not the blinded human S01 review.

Keys come from the environment (ANTHROPIC_API_KEY, OPENAI_API_KEY); run under
`op run`. Never pass keys as arguments.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "oracle-brain"))
from oracle_brain.provider_policy import ProcessingApproval, ProcessingRequest, dispatch  # noqa: E402

CORPUS = ROOT / "evals" / "oracle2" / "synthetic-cases.jsonl"
PURPOSE = "s02-model-evaluation"
DATA_CLASSES = frozenset({"synthetic"})
MAX_TOKENS = 1200
ENDPOINTS = {
    "anthropic": "https://api.anthropic.com/v1/messages",
    "openai": "https://api.openai.com/v1/chat/completions",
}
# Pinned from the 2026-09-28 listing responses (docs/verification/oracle2/S02-model-listings.json).
PRIMARY_MODEL = "anthropic:claude-sonnet-5"
FALLBACK_MODEL = "openai:gpt-5.5-2026-04-23"
LISTINGS = ROOT / "docs" / "verification" / "oracle2" / "S02-model-listings.json"
# Terms/data-use page whose retrieved body is hashed into the approval. The hash is an
# identity for this synthetic run only; it is not a legal review of the terms.
TERMS_URLS = {
    "anthropic": "https://www.anthropic.com/legal/commercial-terms",
    # openai.com/policies/* answers 403 to non-browser clients; the platform data-controls
    # page is the retrievable provider statement on API data use.
    "openai": "https://platform.openai.com/docs/guides/your-data",
}
# Body hashes retrieved 2026-09-28 10:49 AM EDT. Approvals carry these pinned values; requests
# carry the freshly fetched hash, so a changed terms page is DENIED until re-reviewed and re-pinned.
TERMS_SHA256 = {
    "anthropic": "67a7888aadd67c717f2d09d3958cdfd462d71b712b4fde5ba1301fe636977038",
    "openai": "fe8fbfae935c5cc881682b8bd929bb915c05cda4134ce9538f38fbaa672843f2",
}
SYSTEM = (
    "You answer questions about an invented company using ONLY the numbered source spans given. "
    "Reply with a single JSON object: {\"abstain\": bool, \"answer\": str, \"citations\": "
    "[{\"source_id\": str, \"locator\": str}]}. Set abstain true when the sources do not establish "
    "the requested policy, approval, owner or decision; then state the exact gap and any narrower "
    "supported facts. Never invent approvals, savings or figures. Cite every span you rely on. "
    "For improvement questions, separate observed evidence, hypothesis, measure and missing inputs."
)
STOP = {"which", "their", "there", "about", "after", "before", "should", "would", "under", "where"}


def fetch_terms_hash(url: str) -> str:
    req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0 oracle2-s02-eval"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return hashlib.sha256(resp.read()).hexdigest()


def load_questions(path: Path = CORPUS) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [r for r in rows if r["kind"] == "question"]


def build_prompt(case: dict) -> str:
    spans = "\n".join(f"[{s['source_id']} | {s['locator']}] {s['text']}" for s in case["evidence_spans"])
    return f"Scope: {case['time_scope']}\nSources:\n{spans}\n\nQuestion: {case['question']}"


def approvals_for(pairs: list[tuple[str, bool]], hashes: dict[str, str],
                  hours: float = 2) -> list[ProcessingApproval]:
    exp = datetime.now(timezone.utc) + timedelta(hours=hours)
    return [ProcessingApproval(provider=p, account="oracle-eval", endpoint=ENDPOINTS[p],
                               data_classes=DATA_CLASSES, purpose=PURPOSE, terms_hash=hashes[p],
                               expires_at=exp, register_ref="docs/verification/oracle2/S02-models.md",
                               fallback=fb) for p, fb in pairs]


def _post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={**headers, "content-type": "application/json"})
    for attempt in range(3):  # retry transient provider errors (e.g. 429/529)
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if attempt == 2 or exc.code not in (408, 429, 500, 502, 503, 529):
                raise
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("provider request retries exhausted")


def call(provider: str, model: str, prompt: str) -> tuple[str, int]:
    if provider == "anthropic":
        r = _post(ENDPOINTS[provider], {"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                        "anthropic-version": "2023-06-01"},
                  {"model": model, "max_tokens": MAX_TOKENS, "system": SYSTEM,
                   "messages": [{"role": "user", "content": prompt}]})
        text = "".join(b.get("text", "") for b in r["content"] if b["type"] == "text")
        return text, r["usage"]["input_tokens"] + r["usage"]["output_tokens"]
    r = _post(ENDPOINTS[provider], {"authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
              {"model": model, "max_completion_tokens": MAX_TOKENS * 2, "reasoning_effort": "low",
               "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]})
    return r["choices"][0]["message"]["content"] or "", r["usage"]["total_tokens"]


def parse(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def terms(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if (len(w) >= 5 or w.isdigit()) and w not in STOP}


def score(case: dict, out: dict | None) -> dict:
    if not isinstance(out, dict):
        return {"parsed": False, "citations_resolve": False, "expectation_match": False,
                "fact_coverage": 0.0, "pass": False}
    allowed = {(s["source_id"], s["locator"]) for s in case["evidence_spans"]}
    cites = out.get("citations") or []
    resolve = bool(cites) and all(isinstance(c, dict) and (c.get("source_id"), c.get("locator")) in allowed
                                  for c in cites)
    expect = bool(out.get("abstain")) == (case["expectation"] == "abstain")
    need = set().union(*(terms(f) for f in case["required_facts"]))
    cov = len(need & terms(str(out.get("answer", "")))) / len(need) if need else 1.0
    return {"parsed": True, "citations_resolve": resolve, "expectation_match": expect,
            "fact_coverage": round(cov, 2), "pass": resolve and expect and cov >= 0.5}


def run(provider: str, model: str, fallback: bool, cases: list[dict],
        approvals: list[ProcessingApproval], hashes: dict[str, str], sender=call) -> list[dict]:
    results = []
    for case in cases:
        req = ProcessingRequest(provider=provider, account="oracle-eval", endpoint=ENDPOINTS[provider],
                                data_classes=DATA_CLASSES, purpose=PURPOSE, terms_hash=hashes[provider],
                                fallback=fallback)
        t0 = time.monotonic()
        try:
            text, tokens = dispatch(req, approvals, lambda: sender(provider, model, build_prompt(case)))
            out, err = parse(text), None
        except PermissionError:
            raise
        except Exception as exc:  # network/provider error recorded per case
            out, tokens, err = None, 0, type(exc).__name__
        results.append({"id": case["id"], "category": case["category"], "expectation": case["expectation"],
                        "model": model, "tokens": tokens, "elapsed_ms": int((time.monotonic() - t0) * 1000),
                        "error": err, "output": out, **score(case, out)})
    return results


def evaluate(primary: str, fallback: str, cases: list[dict], fetch=None, sender=call) -> dict:
    """Admit every call through the policy: pinned terms hash in approvals, fetched hash in requests."""
    fetch = fetch or fetch_terms_hash
    (pp, pm), (fp, fm) = primary.split(":", 1), fallback.split(":", 1)
    fetched = {p: fetch(TERMS_URLS[p]) for p in (pp, fp)}
    approvals = approvals_for([(pp, False), (fp, True)], TERMS_SHA256)
    return {"run_at": datetime.now(timezone.utc).isoformat(), "data_classes": sorted(DATA_CLASSES),
            "purpose": PURPOSE, "terms_urls": {p: TERMS_URLS[p] for p in fetched},
            "terms_sha256_fetched": fetched,
            "approvals": [json.loads(x.model_dump_json()) for x in approvals],
            "primary": run(pp, pm, False, cases, approvals, fetched, sender),
            "fallback": run(fp, fm, True, cases, approvals, fetched, sender)}


def summarize(report: dict) -> tuple[list[str], bool]:
    """Return summary lines and whether the run is clean (rows present, no call errors)."""
    lines, ok = [], True
    for k in ("primary", "fallback"):
        r = report[k]
        if not r:
            lines.append(f"{k}: no rows")
            ok = False
            continue
        errors = sum(bool(x["error"]) for x in r)
        ok = ok and errors == 0
        lines.append(f"{k} {r[0]['model']} pass {sum(x['pass'] for x in r)} / {len(r)} "
                     f"tokens {sum(x['tokens'] for x in r)} errors {errors}")
    return lines, ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--primary", default=PRIMARY_MODEL, help="provider:model")
    ap.add_argument("--fallback", default=FALLBACK_MODEL, help="provider:model")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ids", default="", help="comma-separated case IDs to rerun (default all)")
    a = ap.parse_args(argv)
    cases = load_questions()
    if a.ids:
        cases = [c for c in cases if c["id"] in set(a.ids.split(","))]
    if not cases:
        print("no cases matched --ids", file=sys.stderr)
        return 2
    report = evaluate(a.primary, a.fallback, cases)
    if a.ids and a.out.exists():
        print("refusing to overwrite an existing report with a partial --ids run", file=sys.stderr)
        return 3
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=1) + "\n")
    lines, ok = summarize(report)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
