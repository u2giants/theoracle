#!/usr/bin/env python3
"""Offline checks for the S02 model evaluation harness (no network)."""
import json
import unittest

import evaluate_models as em


class EvaluateModelsTests(unittest.TestCase):
    def setUp(self):
        self.cases = em.load_questions()

    def test_only_question_records(self):
        self.assertEqual(len(self.cases), 30)

    def test_policy_denies_unapproved_provider(self):
        approvals = em.approvals_for([("anthropic", False)])
        with self.assertRaises(PermissionError):
            em.run("openai", "x", True, self.cases[:1], approvals, sender=lambda *a: ("{}", 0))

    def test_policy_denies_non_synthetic_scope(self):
        approvals = em.approvals_for([("anthropic", False)])
        req = em.ProcessingRequest(provider="anthropic", account="oracle-eval",
                                   endpoint=em.ENDPOINTS["anthropic"], data_classes={"company"},
                                   purpose=em.PURPOSE, terms_hash=em.terms_hash("anthropic"))
        with self.assertRaises(PermissionError):
            em.dispatch(req, approvals, lambda: None)

    def test_scoring(self):
        c = self.cases[0]
        span = c["evidence_spans"][0]
        good = {"abstain": False, "answer": c["required_facts"][0],
                "citations": [{"source_id": span["source_id"], "locator": span["locator"]}]}
        self.assertTrue(em.score(c, good)["pass"])
        bad = dict(good, citations=[{"source_id": "nope", "locator": "x"}])
        self.assertFalse(em.score(c, bad)["pass"])
        r = em.run("anthropic", "m", False, [c], em.approvals_for([("anthropic", False)]),
                   sender=lambda *a: (json.dumps(good), 5))
        self.assertTrue(r[0]["pass"])


if __name__ == "__main__":
    unittest.main()
