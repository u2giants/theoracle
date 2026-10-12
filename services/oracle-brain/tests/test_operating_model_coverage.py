"""W01 source-only inventory consistency, not extractor/semantic acceptance."""
import hashlib
import json
import subprocess
from pathlib import Path
import pytest
from uuid import UUID, uuid5
from oracle_brain.operating_model.coverage import Obligation, CoverageRecord, validate_coverage
from oracle_brain.operating_model.source_receipts import SourceRef, SourceReceipt, EvidenceRef
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.model import BusinessOperatingModel

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / 'evals/oracle2/workflow'


def test_validation_fixture_checksum_immutable():
    checks = json.loads((FIXTURES / 'checksums.json').read_text())['files']
    for name, expected in checks.items():
        target = FIXTURES / name if not name.startswith('docs/') else ROOT / name
        assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
    # Source expectations are anchored in their first Git version, not mutable hashes alone.
    for name in ('sources.json','development.json','validation.json','expected_obligations.json'):
        relative = 'evals/oracle2/workflow/' + name
        history = subprocess.check_output(['git','log','--reverse','--format=%H','--',relative],cwd=ROOT,text=True).splitlines()
        assert history, 'full fixture history required'
        original = subprocess.check_output(['git','show',history[0]+':'+relative],cwd=ROOT)
        current = (FIXTURES/name).read_bytes()
        assert current == original, 'frozen source inventory changed; separate reviewed version required'
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

def test_every_frozen_essential_obligation_must_be_accounted_for():
    expected = json.loads((FIXTURES / 'expected_obligations.json').read_text())
    sources = {s['source_id']: s for s in json.loads((FIXTURES / 'sources.json').read_text())['sources']}
    refs = {sid: SourceRef(workspace_id=UUID(int=1), source_id=uuid5(UUID(int=99), sid), revision=s['source_revision'], original_sha256=s['original_hash'], reading_sha256=s['reading_hash'], parser_id=s['parser_identity']) for sid,s in sources.items()}
    obligations = tuple(Obligation(obligation_id=o['obligation_id'], priority=o['priority'], expected=o['expected'], evidence=EvidenceRef(ref=refs[o['source_id']], start=o['start'], end=o['end'], quote=o['quote']), reason=o['reason']) for o in expected['obligations'])
    records = tuple(CoverageRecord(obligation_id=o.obligation_id, disposition=o.expected, object_ids=(o.obligation_id,), reason='fixture') for o in obligations)
    evidence = {o.obligation_id: (o.evidence,) for o in obligations}; inventory = digest({'obligations':[o.model_dump(mode='json') for o in obligations]})
    assert validate_coverage(obligations, records, object_evidence=evidence, independent_inventory_hash=inventory)['complete_accounting']
    for o in obligations:
        if o.priority == 'essential':
            with pytest.raises(ValueError): validate_coverage(obligations, tuple(r for r in records if r.obligation_id != o.obligation_id), object_evidence=evidence, independent_inventory_hash=inventory)

def test_outer_manifest_fields_cannot_supply_source_obligations():
    from test_business_operating_model import observation,model
    baseline=model((observation(4,'Design sends ART'),observation(5,'Supplier receives packet')))
    raw=baseline.model_dump(mode='json');raw['outer_obligations']=['D1-O1']
    with pytest.raises(ValueError,match='outer_obligations'):
        BusinessOperatingModel.model_validate_json(json.dumps(raw))
