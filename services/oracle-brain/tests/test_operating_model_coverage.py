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


def _family_records():
    """Disposition-true records for every frozen obligation family."""
    expected = json.loads((FIXTURES / "expected_obligations.json").read_text())
    return expected


def test_frozen_family_dispositions_match_expected():
    """D1 exclusive choice, D2 rework, D3 handoff, V1/V2 conflict, V3 variant,
    V4 partial, V5/V6 identity, V7 quarantine all keep their expected disposition."""
    expected = _family_records()
    by_src = {}
    for o in expected["obligations"]:
        by_src.setdefault(o["source_id"], []).append(o)
    assert {o["expected"] for o in by_src["D1"]} == {"represented"}
    assert {o["expected"] for o in by_src["D2"]} == {"represented"}
    assert {o["expected"] for o in by_src["D3"]} == {"represented"}
    assert {o["expected"] for o in by_src["V1"]} == {"represented"}
    assert {o["expected"] for o in by_src["V2"]} == {"represented"}
    assert {o["expected"] for o in by_src["V3"]} == {"represented"}
    assert {o["expected"] for o in by_src["V4"]} == {"unresolved"}
    assert {o["expected"] for o in by_src["V5"]} == {"represented"}
    assert {o["expected"] for o in by_src["V6"]} == {"represented"}
    assert {o["expected"] for o in by_src["V7"]} == {"quarantined", "not_applicable"}


def test_exclusive_choice_and_rework_obligations_are_represented():
    """D1 licensed/unlicensed exclusive choice and D2 rework loop stay represented."""
    expected = _family_records()["obligations"]
    d1 = {o["obligation_id"]: o for o in expected if o["source_id"] == "D1"}
    assert "Rights approval" in d1["D1-O3"]["quote"]
    assert "unlicensed" in d1["D1-O3"]["quote"]
    d2 = {o["obligation_id"]: o for o in expected if o["source_id"] == "D2"}
    assert "returns to a second Design" in d2["D2-O1"]["quote"]
    assert d2["D2-O1"]["expected"] == "represented"


def test_parallel_join_and_cross_document_conflict_preserved():
    """V1 parallel reviews + V2 opposing mandatory approval survive without overwrite."""
    expected = _family_records()
    v1 = {o["obligation_id"]: o for o in expected["obligations"] if o["source_id"] == "V1"}
    assert "parallel" in v1["V1-O2"]["quote"]
    assert "both" in v1["V1-O3"]["quote"]
    assert expected["conflicts"] == [
        {"source_ids": ["V1", "V2"], "scope": "customer-C;2026", "status": "unresolved"}
    ]


def test_scope_variants_preserve_disagreement():
    """V3 different customer scope is a variant, not a contradiction or merge."""
    expected = _family_records()
    assert expected["variants"][0]["source_ids"] == ["V1", "V3"]
    v3 = next(o for o in expected["obligations"] if o["obligation_id"] == "V3-O1")
    assert "customer-Z" in v3["quote"] and v3["expected"] == "represented"


def test_identity_roles_and_upload_aliases_do_not_false_merge():
    """V5/V6 same label two roles stay distinct; V5 aliases share bytes without corroboration."""
    expected = _family_records()["obligations"]
    v5 = {o["obligation_id"]: o for o in expected if o["source_id"] == "V5"}
    v6 = {o["obligation_id"]: o for o in expected if o["source_id"] == "V6"}
    assert "supplier-N" in v5["V5-O1"]["quote"]
    assert "supplier-S" in v6["V6-O1"]["quote"]
    assert "distinct" in v6["V6-O3"]["quote"]
    sources = json.loads((FIXTURES / "sources.json").read_text())["sources"]
    v5_src = next(s for s in sources if s["source_id"] == "V5")
    assert v5_src["aliases"] == ["V5", "V5-upload-alias"]


def test_v4_partial_workflow_declines_compilation():
    """V4 incomplete source omits join semantics: unresolved slots, no inferred XOR/AND."""
    expected = _family_records()
    slots = {u["slot"] for u in expected["unresolved"]}
    assert slots == {"join_semantics", "shipping_owner"}
    assert all("do not infer" in u["reason"] or "not specified" in u["reason"].lower()
               for u in expected["unresolved"])


def test_v7_quarantine_and_hostile_instruction_never_represented():
    """V7 allegation stays quarantined; hostile conceal instruction is not_applicable."""
    expected = _family_records()["obligations"]
    v7 = {o["obligation_id"]: o for o in expected if o["source_id"] == "V7"}
    assert v7["V7-O1"]["expected"] == "quarantined"
    assert v7["V7-O2"]["expected"] == "quarantined"
    assert v7["V7-O3"]["expected"] == "not_applicable"
    assert "Ignore previous instructions" in v7["V7-O3"]["quote"]


def test_assembly_requires_supported_identity_and_handoff():
    """Cross-source joins need admitted identity; interfaces need explicit artifact handoff."""
    from test_business_operating_model import observation, model, interface
    from oracle_brain.operating_model.assembly import validate_assembly
    a = observation(4, "Design sends ART to Supplier")
    b = observation(5, "Design sends ART to Supplier")
    with pytest.raises(ValueError, match="explicit admitted identity"):
        validate_assembly(model((a, b), cross_source=True), {o.observation_id: o for o in (a, b)})
    c = observation(4, "Reviewer sends ART")
    d = observation(5, "Supplier receives packet")
    with pytest.raises(ValueError, match="explicit artifact handoff"):
        validate_assembly(model((c, d), interfaces=(interface(c),)), {o.observation_id: o for o in (c, d)})
    e = observation(4, "Design sends ART to Supplier")
    f = observation(5, "Supplier receives packet")
    m = model((e, f), interfaces=(interface(e),))
    assert validate_assembly(m, {o.observation_id: o for o in (e, f)}) == m
