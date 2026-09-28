#!/usr/bin/env python3
"""Offline checks for the S02 model evaluation harness (no network calls)."""
import json
import os
from datetime import datetime, timedelta, timezone
import unittest

try:
    import pydantic  # noqa: F401
except ImportError as exc:
    if os.environ.get("ORACLE2_REQUIRE_MODEL_TESTS") == "1":
        raise
    # System python3 lacks the oracle-brain venv; the CI venv step requires these tests.
    raise unittest.SkipTest(f"SKIPPED model-harness tests: pydantic not importable ({exc})")
import evaluate_models as em

H = {"anthropic": "a" * 64, "openai": "b" * 64}
ECHO = lambda *a: ("{}", 0)  # noqa: E731


class EvaluateModelsTests(unittest.TestCase):
    def setUp(self):
        self.cases = em.load_questions()

    def req(self, **kw):
        base = dict(provider="anthropic", account="oracle-eval", endpoint=em.ENDPOINTS["anthropic"],
                    data_classes={"synthetic"}, purpose=em.PURPOSE, terms_hash=H["anthropic"])
        return em.ProcessingRequest(**{**base, **kw})

    def test_only_question_records_no_fixtures(self):
        self.assertEqual(len(self.cases), 30)
        self.assertFalse([c for c in self.cases if c["id"].startswith("F") or c["kind"] != "question"])

    def test_pinned_constants_match_listing_artifact(self):
        self.assertEqual(em.PRIMARY_MODEL, "anthropic:claude-sonnet-5")
        self.assertEqual(em.FALLBACK_MODEL, "openai:gpt-5.5-2026-04-23")
        listing = json.loads(em.LISTINGS.read_text())
        for pinned in (em.PRIMARY_MODEL, em.FALLBACK_MODEL):
            provider, model = pinned.split(":", 1)
            self.assertIn(model, {m["id"] for m in listing[provider]["response"]["data"]})

    def test_policy_denies_unapproved_provider(self):
        approvals = em.approvals_for([("anthropic", False)], H)
        with self.assertRaises(PermissionError):
            em.run("openai", "x", True, self.cases[:1], approvals, H, sender=ECHO)

    def test_policy_denies_non_synthetic_scope(self):
        with self.assertRaises(PermissionError):
            em.dispatch(self.req(data_classes={"company"}), em.approvals_for([("anthropic", False)], H), ECHO)

    def test_policy_denies_expired_approval(self):
        approvals = em.approvals_for([("anthropic", False)], H, hours=-1)
        with self.assertRaises(PermissionError):
            em.dispatch(self.req(), approvals, ECHO)

    def test_policy_denies_terms_hash_mismatch(self):
        with self.assertRaises(PermissionError):
            em.dispatch(self.req(terms_hash="c" * 64), em.approvals_for([("anthropic", False)], H), ECHO)

    def test_policy_denies_endpoint_mismatch(self):
        with self.assertRaises(PermissionError):
            em.dispatch(self.req(endpoint="https://example.invalid/v1/messages"),
                        em.approvals_for([("anthropic", False)], H), ECHO)

    def test_changed_terms_page_is_denied_through_evaluate(self):
        good = lambda url: em.TERMS_SHA256[[p for p, u in em.TERMS_URLS.items() if u == url][0]]  # noqa: E731
        report = em.evaluate(em.PRIMARY_MODEL, em.FALLBACK_MODEL, self.cases[:1], fetch=good, sender=ECHO)
        self.assertEqual(len(report["primary"]), 1)
        with self.assertRaises(PermissionError):
            em.evaluate(em.PRIMARY_MODEL, em.FALLBACK_MODEL, self.cases[:1],
                        fetch=lambda url: "d" * 64, sender=ECHO)

    def test_summary_fails_on_errors_or_no_rows(self):
        row = {"model": "m", "pass": True, "tokens": 1, "error": None}
        self.assertTrue(em.summarize({"primary": [row], "fallback": [row]})[1])
        self.assertFalse(em.summarize({"primary": [dict(row, error="HTTPError")], "fallback": [row]})[1])
        self.assertFalse(em.summarize({"primary": [], "fallback": []})[1])
        self.assertEqual(em.main(["--ids", "ZZZ", "--out", os.devnull]), 2)

    def test_scoring(self):
        c = self.cases[0]
        span = c["evidence_spans"][0]
        good = {"abstain": False, "answer": c["required_facts"][0],
                "citations": [{"source_id": span["source_id"], "locator": span["locator"]}]}
        self.assertTrue(em.score(c, good)["pass"])
        self.assertFalse(em.score(c, dict(good, citations=[{"source_id": "nope", "locator": "x"}]))["pass"])
        r = em.run("anthropic", "m", False, [c], em.approvals_for([("anthropic", False)], H), H,
                   sender=lambda *a: (json.dumps(good), 5))
        self.assertTrue(r[0]["pass"])


if __name__ == "__main__":
    unittest.main()
