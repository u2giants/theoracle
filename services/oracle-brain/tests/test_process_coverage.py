import json
from pathlib import Path
from uuid import UUID, uuid5
import pytest
from oracle_brain.operating_model.coverage import Obligation, CoverageRecord, validate_coverage
from oracle_brain.operating_model.source_receipts import SourceRef, SourceReceipt, EvidenceRef
from oracle_brain.operating_model.contracts import digest

ROOT=Path(__file__).parents[3]/'evals/oracle2/workflow'
SOURCES=json.loads((ROOT/'sources.json').read_text())['sources']; EXPECTED=json.loads((ROOT/'expected_obligations.json').read_text())['obligations']
def source(name):
 s=next(x for x in SOURCES if x['source_id']==name); ref=SourceRef(workspace_id=UUID(int=1),source_id=uuid5(UUID(int=99),name),revision=s['source_revision'],original_sha256=s['original_hash'],reading_sha256=s['reading_hash'],parser_id=s['parser_identity']); return SourceReceipt(ref=ref,reading=s['text'],display_revision=s['display_revision'])
def obligation(oid):
 o=next(x for x in EXPECTED if x['obligation_id']==oid); r=source(o['source_id']); return Obligation(obligation_id=oid,priority=o['priority'],expected=o['expected'],evidence=EvidenceRef(ref=r.ref,start=o['start'],end=o['end'],quote=o['quote']),reason=o['reason'])
def inv(items): return digest({'obligations':[o.model_dump(mode='json') for o in items]})
def test_missing_mandatory_approval_fails_well_formed_workflow():
 o=obligation('D1-O3'); start=obligation('D1-O1'); r=CoverageRecord(obligation_id=o.obligation_id,disposition='represented',object_ids=('start',),reason='mapped')
 with pytest.raises(ValueError): validate_coverage((o,),(r,),object_evidence={'start':(start.evidence,)},independent_inventory_hash=inv((o,)))
def test_missing_unclassified_essential_and_borrowed_source_rejected():
 o=obligation('D1-O3'); bad=o.model_copy(update={'evidence':EvidenceRef(ref=o.evidence.ref.model_copy(update={'revision':2}),start=o.evidence.start,end=o.evidence.end,quote=o.evidence.quote)}); r=CoverageRecord(obligation_id='other',disposition='represented',object_ids=('x',),reason='x')
 with pytest.raises(ValueError): validate_coverage((o,),(r,),object_evidence={'x':(bad.evidence,)},independent_inventory_hash=inv((o,)))
def test_v4_genuine_unresolved_exact_span_and_inventory_change_rejected():
 o=obligation('V4-O2'); r=CoverageRecord(obligation_id=o.obligation_id,disposition='unresolved',object_ids=('v4',),reason=o.reason); assert validate_coverage((o,),(r,),object_evidence={'v4':(o.evidence,)},independent_inventory_hash=inv((o,)))['complete_accounting']
 with pytest.raises(ValueError): validate_coverage((o,),(r,),object_evidence={'v4':(o.evidence,)},independent_inventory_hash='d'*64)
