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

    def test_held_out_payload_replacement(self):
        self.assert_rejected(lambda rows: rows[0].update(question='What changed?'))

    def test_same_split_duplicate(self):
        def mutate(rows):
            copied = copy.deepcopy(rows[0])
            copied['id'] = rows[1]['id']
            rows[1] = copied
        self.assert_rejected(mutate)

    def test_duplicate_span_inside_record(self):
        self.assert_rejected(lambda rows: rows[0]['evidence_spans'].append(copy.deepcopy(rows[0]['evidence_spans'][0])))

    def test_coordinated_checksum_change_cannot_hide_same_version_edit(self):
        import hashlib
        rows = copy.deepcopy(self.records)
        schema = copy.deepcopy(self.schema)
        rows[0]['question'] = 'Changed question with same version?'
        schema['x-frozen-acceptance-sha256']['A01'] = hashlib.sha256(
            json.dumps(rows[0], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, 'version bump'):
            validate(rows, schema, self.records, self.schema['x-manifest-version'])


if __name__ == '__main__':
    unittest.main()
