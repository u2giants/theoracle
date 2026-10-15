#!/usr/bin/env python3
"""Automated S01-rubric proxy score for the S03 pilot answer path on synthetic data.

Runs the 20 S01 acceptance questions through the pilot retrieval + consultant
path over one pooled corpus built from every acceptance evidence span, then
scores each S01 rubric dimension with mechanical checks. No provider, network
or company data is used. This is an invented/automated check, not staff review
or business acceptance.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "oracle-brain"))

from oracle_brain.consultant.pilot import answer_question  # noqa: E402
from oracle_brain.retrieval.pilot import retrieve_spans  # noqa: E402

CASES = ROOT / "evals" / "oracle2" / "synthetic-cases.jsonl"
STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "after",
        "before", "with", "must", "is", "are", "be", "by", "not", "do", "does"}
CATEGORY_FLOORS = {"procedure_ownership": 4, "conditional_exception": 4,
                   "cross_department": 4, "historical_change": 3,
                   "improvement_decision": 4}


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3 and w not in STOP}


def _coverage(required: str, answer: str) -> float:
    terms = _terms(required)
    if not terms:
        return 1.0
    found = _terms(answer)
    return len(terms & found) / len(terms)


def main() -> int:
    cases = [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]
    questions = [c for c in cases if c["kind"] == "question" and c["split"] == "acceptance"]
    blocks = []
    for case in questions:
        for i, span in enumerate(case["evidence_spans"]):
            sid = uuid5(NAMESPACE_URL, span["source_id"])
            blocks.append({"block_id": uuid5(NAMESPACE_URL, f"{case['id']}:{i}"),
                           "source_id": sid, "span_start": 0,
                           "span_end": len(span["text"]), "text": span["text"],
                           "block_index": len(blocks), "case": case["id"]})
    span_texts = {b["text"] for b in blocks}
    rows = []
    for case in questions:
        spans = retrieve_spans(case["question"], blocks)
        answer = answer_question(case["question"], spans)
        text = answer.answer_text
        own = {uuid5(NAMESPACE_URL, s["source_id"]) for s in case["evidence_spans"]}
        cited = {c.source_id for c in answer.citations}
        abstain = case["expectation"] == "abstain"
        gap = "no source evidence" in text.lower()
        fact = (gap if abstain else
                all(_coverage(f, text) >= 0.6 for f in case["required_facts"]))
        citation = all(c.quote in span_texts for c in answer.citations) and (
            abstain or bool(cited & own))
        # Scope: every cited source belongs to this case (no off-scope evidence).
        scope = cited <= own
        exceptions = fact and scope  # missed exception or off-scope clause fails
        improvement = True
        if case["category"] == "improvement_decision" and not abstain:
            h = answer.hypothetical
            improvement = bool(h and "not established" in h.label.lower()
                               and h.measure and h.missing_inputs)
        clarity = abstain or text.count("According to the source:") <= 1
        usefulness = fact and citation
        dims = {"fact": fact, "exceptions": exceptions, "citation": citation,
                "scope": scope, "usefulness": usefulness, "clarity": clarity,
                "improvement_contract": improvement}
        rows.append({"id": case["id"], "category": case["category"],
                     "expectation": case["expectation"], **dims,
                     "pass": all(dims.values())})
    by_cat: dict[str, list[bool]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r["pass"])
    total = sum(r["pass"] for r in rows)
    floors = {c: (sum(v), len(v), sum(v) >= CATEGORY_FLOORS[c]) for c, v in by_cat.items()}
    dim_totals = {d: sum(r[d] for r in rows) for d in
                  ("fact", "exceptions", "citation", "scope", "usefulness",
                   "clarity", "improvement_contract")}
    result = {"cases": len(rows), "passed": total, "threshold": 19,
              "meets_threshold": total >= 19 and all(f[2] for f in floors.values()),
              "category_floors": floors, "dimension_totals": dim_totals,
              "rows": rows, "business_accepted": False}
    print(json.dumps(result, indent=2, default=list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
