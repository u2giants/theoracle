"""W01 source-only inventory consistency, not extractor/semantic acceptance."""
import hashlib
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / 'evals/oracle2/workflow'


def test_validation_fixture_checksum_immutable():
    checks = json.loads((FIXTURES / 'checksums.json').read_text())['files']
    for name, expected in checks.items():
        target = FIXTURES / name if not name.startswith('docs/') else ROOT / name
        assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
    development = json.loads((FIXTURES / 'development.json').read_text())
    validation = json.loads((FIXTURES / 'validation.json').read_text())
    for field in ('source_ids', 'process_ids', 'activities'):
        assert not set(development[field]) & set(validation[field])
    sources = {s['source_id']: s for s in json.loads((FIXTURES / 'sources.json').read_text())['sources']}
    expected = json.loads((FIXTURES / 'expected_obligations.json').read_text())
    for item in expected['obligations']:
        assert sources[item['source_id']]['text'][item['start']:item['end']] == item['quote']
    assert expected['independent_of_extraction'] is True
    for split, manifest in [('development',development),('validation',validation)]:
        assert set(manifest['source_ids']) == {s['source_id'] for s in sources.values() if s['split'] == split}
    assert expected['conflicts'] == [{'source_ids':['V1','V2'],'scope':'customer-C;2026','status':'unresolved'}]
    assert {v['slot'] for v in expected['unresolved']} == {'join_semantics','shipping_owner'}
    assert expected['variants'][0]['source_ids'] == ['V1','V3']
    assert expected['interfaces'][0]['artifact_id'] == 'ART-D-17'
    assert sources['V5']['aliases'] == ['V5','V5-upload-alias']
    quarantine = [o for o in expected['obligations'] if o['source_id']=='V7']
    assert {o['expected'] for o in quarantine} == {'quarantined','not_applicable'}
    assert all(o['expected']=='unresolved' for o in expected['obligations'] if o['source_id']=='V4')


def require_obligations(represented):
    expected = json.loads((FIXTURES / 'expected_obligations.json').read_text())
    required = {o['obligation_id'] for o in expected['obligations'] if o['expected'] == 'represented'}
    if required - set(represented): raise ValueError('missing essential source obligation')


def test_independent_obligation_inventory_detects_missing_handoff():
    expected = json.loads((FIXTURES / 'expected_obligations.json').read_text())
    all_ids = {o['obligation_id'] for o in expected['obligations']}
    require_obligations(all_ids)
    with pytest.raises(ValueError, match='missing essential'):
        require_obligations(all_ids - {'D3-O1'})
