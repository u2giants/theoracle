#!/usr/bin/env python3
"""Regression checks for manifest integrity and held-out isolation."""
import copy
import json
from pathlib import Path
import unittest

from validate_manifest import DEFAULT, SCHEMA, git_baseline, validate


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

    def test_git_baseline_discovers_first_committed_manifest(self):
        from unittest.mock import patch
        from subprocess import CompletedProcess
        replies = [
            CompletedProcess([], 0, 'false\n', ''),
            CompletedProcess([], 0, 'abc123\n', ''),
            CompletedProcess([], 0, json.dumps({'x-manifest-version': 1}), ''),
            CompletedProcess([], 0, json.dumps(self.records[0])+'\n', ''),
        ]
        with patch('validate_manifest.subprocess.run', side_effect=replies):
            old_rows, old_version = git_baseline(1)
            self.assertEqual(old_version, 1)
            self.assertEqual(old_rows[0]['id'], 'A01')

    def test_fixture_without_raw_payload_fails(self):
        self.assert_rejected(lambda rows: rows[-1].update(input_text=rows[-1]['attack_or_shape']))

    def test_fixture_placeholder_with_matching_span_fails(self):
        def mutate(rows):
            for row in rows:
                if row['kind'] == 'source_fixture':
                    row['input_text'] = 'x'
                    row['evidence_spans'][0]['text'] = 'x'
        self.assert_rejected(mutate)

    def test_missing_git_baseline_fails_closed(self):
        from unittest.mock import patch
        from subprocess import CompletedProcess
        with patch('validate_manifest.subprocess.run', return_value=CompletedProcess([], 1, '', 'missing')):
            with self.assertRaisesRegex(ValueError, 'full Git history required'):
                git_baseline(1)

    def test_no_manifest_addition_fails_closed(self):
        from unittest.mock import patch
        from subprocess import CompletedProcess
        results = [CompletedProcess([], 0, 'false\n', ''), CompletedProcess([], 0, '', '')]
        with patch('validate_manifest.subprocess.run', side_effect=results):
            with self.assertRaisesRegex(ValueError, 'committed acceptance schema history unavailable'):
                git_baseline(1)

    def test_second_version_cannot_change_without_third_version(self):
        import hashlib
        version_two = copy.deepcopy(self.records)
        version_two[0]['question'] = 'Version two question'
        changed = copy.deepcopy(version_two)
        changed[0]['question'] = 'Another change under version two'
        schema = copy.deepcopy(self.schema)
        schema['x-manifest-version'] = 2
        schema['x-frozen-acceptance-sha256']['A01'] = hashlib.sha256(
            json.dumps(changed[0], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, 'version bump'):
            validate(changed, schema, version_two, 2)


if __name__ == '__main__':
    unittest.main()
