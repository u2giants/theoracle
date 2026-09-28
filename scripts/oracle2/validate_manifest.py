#!/usr/bin/env python3
"""Dependency-free validation of the public Oracle 2 synthetic evaluation manifest."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / 'evals/oracle2/manifest.schema.json'
DEFAULT = ROOT / 'evals/oracle2/synthetic-cases.jsonl'


def fail(message):
    raise ValueError(message)


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        fail(f'{label}: nonempty string required')


def validate_record(record, line):
    if not isinstance(record, dict):
        fail(f'line {line}: object required')
    kind = record.get('kind')
    question = kind == 'question'
    fixture = kind == 'source_fixture'
    if not (question or fixture):
        fail(f'line {line}: invalid kind')
    common = {'kind', 'id', 'split', 'category', 'source_ids', 'evidence_spans'}
    extra = ({'process', 'question', 'required_facts', 'forbidden_inferences', 'time_scope', 'expectation', 'reviewer_rubric'}
             if question else {'source_format', 'attack_or_shape', 'expected_handling'})
    if set(record) != common | extra:
        fail(f'line {line}: missing or unknown fields {sorted(set(record) ^ (common | extra))}')
    for field in ['id', 'split', 'category']:
        nonempty(record[field], f'line {line} {field}')
    if not re.fullmatch(r'[AD][0-9]{2}' if question else r'F[0-9]{2}', record['id']):
        fail(f'line {line}: invalid ID')
    if record['split'] not in (('acceptance', 'development') if question else ('fixture',)):
        fail(f'line {line}: invalid split')
    if question and record['id'][0] != {'acceptance': 'A', 'development': 'D'}[record['split']]:
        fail(f'line {line}: ID prefix does not match frozen split')
    if not isinstance(record['source_ids'], list) or not record['source_ids']:
        fail(f'line {line}: source IDs required')
    for source in record['source_ids']:
        nonempty(source, f'line {line} source ID')
    if len(set(record['source_ids'])) != len(record['source_ids']):
        fail(f'line {line}: duplicate source ID')
    spans = record['evidence_spans']
    if not isinstance(spans, list) or not spans:
        fail(f'line {line}: evidence span required')
    for span in spans:
        if not isinstance(span, dict) or set(span) != {'source_id', 'locator', 'text'}:
            fail(f'line {line}: invalid evidence span')
        for field in ('source_id', 'locator', 'text'):
            nonempty(span[field], f'line {line} span {field}')
        if span['source_id'] not in record['source_ids']:
            fail(f'line {line}: span source absent from source IDs')
    covered_sources = {span['source_id'] for span in spans}
    if covered_sources != set(record['source_ids']):
        fail(f'line {line}: declared source without evidence span')
    span_keys = [(span['source_id'], span['locator'], span['text'].strip().casefold()) for span in spans]
    if len(span_keys) != len(set(span_keys)):
        fail(f'line {line}: duplicate evidence span within record')
    if question:
        for field in ('process', 'question', 'time_scope'):
            nonempty(record[field], f'line {line} {field}')
        if record['expectation'] not in ('answer', 'abstain'):
            fail(f'line {line}: invalid expectation')
        for field in ('required_facts', 'forbidden_inferences'):
            values = record[field]
            if not isinstance(values, list) or not values:
                fail(f'line {line}: {field} required')
            for value in values:
                nonempty(value, f'line {line} {field}')
        rubric = record['reviewer_rubric']
        if not isinstance(rubric, dict) or set(rubric) != {'fact', 'boundary', 'evidence', 'decision'}:
            fail(f'line {line}: invalid reviewer rubric')
        for field, value in rubric.items():
            nonempty(value, f'line {line} rubric {field}')
    else:
        for field in ('source_format', 'attack_or_shape', 'expected_handling'):
            nonempty(record[field], f'line {line} {field}')


def validate(records, schema, prior_records=None, prior_version=None):
    expected = schema['x-exact-synthetic-counts']
    frozen = schema['x-frozen-acceptance-sha256']
    counts = Counter()
    ids = set()
    by_split = {split: {'source_ids': set(), 'processes': set(), 'questions': set(), 'spans': set()} for split in expected}
    for line, record in enumerate(records, 1):
        validate_record(record, line)
        identifier = record['id']
        if identifier in ids:
            fail(f'line {line}: duplicate ID {identifier}')
        ids.add(identifier)
        split, category = record['split'], record['category']
        if category not in expected[split]:
            fail(f'line {line}: invalid category for {split}')
        if split == 'acceptance':
            actual = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
            if actual != frozen.get(identifier):
                fail(f'line {line}: held-out case differs from frozen {identifier}; version the set before changing it')
        counts[(split, category)] += 1
        partition = by_split[split]
        if partition['source_ids'].intersection(record['source_ids']):
            fail(f'line {line}: source reused within {split}')
        normalized_spans = {span['text'].strip().casefold() for span in record['evidence_spans']}
        if partition['spans'].intersection(normalized_spans):
            fail(f'line {line}: evidence duplicated within {split}')
        partition['source_ids'].update(record['source_ids'])
        partition['spans'].update(normalized_spans)
        if record['kind'] == 'question':
            process = record['process'].strip().casefold()
            prompt = record['question'].strip().casefold()
            if process in partition['processes'] or prompt in partition['questions']:
                fail(f'line {line}: process or question duplicated within {split}')
            partition['processes'].add(process)
            partition['questions'].add(prompt)
    for split, categories in expected.items():
        for category, count in categories.items():
            if counts[(split, category)] != count:
                fail(f'{split}/{category}: expected {count}, got {counts[(split, category)]}')
    for left, right in (('acceptance', 'development'), ('acceptance', 'fixture'), ('development', 'fixture')):
        for key in by_split[left]:
            overlap = by_split[left][key] & by_split[right][key]
            if overlap:
                fail(f'split leakage {left}/{right} in {key}: {sorted(overlap)[:2]}')
    if ids != {f'A{i:02d}' for i in range(1, 21)} | {f'D{i:02d}' for i in range(1, 11)} | {f'F{i:02d}' for i in range(1, 13)}:
        fail('missing or unexpected manifest IDs')
    if set(frozen) != {f'A{i:02d}' for i in range(1, 21)}:
        fail('frozen acceptance digest list is incomplete')
    if prior_records is not None:
        old_acceptance = {row['id']: row for row in prior_records if row.get('split') == 'acceptance'}
        new_acceptance = {row['id']: row for row in records if row.get('split') == 'acceptance'}
        if old_acceptance != new_acceptance and schema['x-manifest-version'] == prior_version:
            fail('acceptance content changed without a manifest version bump from the Git baseline')
    return counts


def git_baseline():
    """Read the accepted base revision, if one exists, without editing the repository."""
    ref = subprocess.run(['git', 'merge-base', 'HEAD', 'origin/main'], cwd=ROOT, capture_output=True, text=True)
    if ref.returncode != 0:
        return None, None
    commit = ref.stdout.strip()
    def read(path):
        result = subprocess.run(['git', 'show', f'{commit}:{path}'], cwd=ROOT, capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else None
    manifest = read('evals/oracle2/synthetic-cases.jsonl')
    old_schema = read('evals/oracle2/manifest.schema.json')
    if manifest is None or old_schema is None:
        return None, None  # First publication: Git main has no accepted Oracle 2 corpus yet.
    return [json.loads(line) for line in manifest.splitlines() if line.strip()], json.loads(old_schema)['x-manifest-version']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--synthetic', action='store_true', required=True)
    parser.add_argument('--manifest', type=Path, default=DEFAULT)
    args = parser.parse_args()
    try:
        schema = json.loads(SCHEMA.read_text())
        records = [json.loads(line) for line in args.manifest.read_text().splitlines() if line.strip()]
        prior_records, prior_version = git_baseline()
        counts = validate(records, schema, prior_records, prior_version)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    print(f'PASS: {sum(counts.values())} synthetic records; 20 acceptance, 10 development, 12 source fixtures; evidence and splits valid')
    return 0


if __name__ == '__main__':
    sys.exit(main())
