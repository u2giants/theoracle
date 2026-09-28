#!/usr/bin/env python3
"""Regression checks for manifest integrity and held-out isolation."""
import copy
import json
from pathlib import Path
import unittest

from validate_manifest import DEFAULT, SCHEMA, validate


class ManifestValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = [json.loads(line) for line in DEFAULT.read_text().splitlines()]
        cls.schema = json.loads(SCHEMA.read_text())

    def test_real_manifest_passes(self):
        self.assertEqual(sum(validate(self.records, self.schema).values()), 42)

    def assert_rejected(self, mutate):
        records = copy.deepcopy(self.records)
        mutate(records)
        with self.assertRaises(ValueError):
            validate(records, self.schema)

    def test_missing_evidence(self):
        self.assert_rejected(lambda rows: rows[0].update(evidence_spans=[]))

    def test_declared_source_without_span(self):
        self.assert_rejected(lambda rows: rows[0]['source_ids'].append('uncovered-source'))

    def test_swapped_split(self):
        self.assert_rejected(lambda rows: rows[0].update(split='development'))

    def test_split_leakage(self):
        def mutate(rows):
            rows[20]['source_ids'] = rows[0]['source_ids']
            rows[20]['evidence_spans'] = rows[0]['evidence_spans']
        self.assert_rejected(mutate)

    def test_missing_case(self):
        self.assert_rejected(lambda rows: rows.pop(0))


if __name__ == '__main__':
    unittest.main()
