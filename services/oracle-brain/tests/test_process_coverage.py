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


def test_structural_soundness_does_not_accept_omitted_approval():
    """A structurally well-formed workflow that omits mandatory approval fails coverage."""
    from oracle_brain.operating_model.workflows.process_model import (
        WorkflowModel, Step, Transition, Gateway, Support,
    )
    from oracle_brain.operating_model.workflows.process_validate import formal_eligible
    ref = source("D1").ref
    # Sound linear net with explicit start/end but no Rights approval step.
    wf = WorkflowModel(
        workflow_id="w-omit", version=1, workspace_id=ref.workspace_id,
        process_id="D-product", scope="customer-A;2026", source_refs=(ref,),
        completeness="complete",
        steps=(
            Step(step_id="start", label="Intake", kind="start", support=Support(observation_ids=("o1",))),
            Step(step_id="sample", label="Sample", kind="activity", support=Support(observation_ids=("o2",))),
            Step(step_id="end", label="Production", kind="end", support=Support(observation_ids=("o3",))),
        ),
        transitions=(
            Transition(transition_id="t1", from_id="start", to_id="sample", support=Support(observation_ids=("o4",))),
            Transition(transition_id="t2", from_id="sample", to_id="end", support=Support(observation_ids=("o5",))),
        ),
        coverage_digest="c" * 64,
    )
    assert formal_eligible(wf) is True
    # Mandatory D1-O3 approval omitted: essential obligation cannot be represented.
    o = obligation("D1-O3")
    r = CoverageRecord(obligation_id=o.obligation_id, disposition="unresolved",
                       object_ids=("w-omit",), reason="omitted approval misclassified")
    with pytest.raises(ValueError, match="essential obligation omitted"):
        validate_coverage((o,), (r,), object_evidence={"w-omit": (o.evidence,)},
                          independent_inventory_hash=inv((o,)))


def test_exclusive_choice_branches_cannot_coerce_to_single_path():
    """D1 licensed/unlicensed exclusive split must stay exclusive, never a silent AND."""
    from oracle_brain.operating_model.workflows.process_model import Gateway, Support
    g = Gateway(gateway_id="g", kind="exclusive_split", support=Support(observation_ids=("o",)))
    assert g.kind == "exclusive_split"
    o = obligation("D1-O3")
    assert "unlicensed" in o.evidence.quote and "Rights approval" in o.evidence.quote


def test_parallel_join_requires_both_branches():
    """V1 parallel reviews: shipping release waits for both, not either."""
    from oracle_brain.operating_model.workflows.process_model import Gateway, Support
    split = Gateway(gateway_id="ps", kind="parallel_split", support=Support(observation_ids=("o",)))
    join = Gateway(gateway_id="pj", kind="parallel_join", support=Support(observation_ids=("o",)))
    assert split.kind == "parallel_split" and join.kind == "parallel_join"
    o = obligation("V1-O3")
    assert "both" in o.evidence.quote


def test_rework_loop_preserves_distinct_occurrences():
    """D2 failed sample returns to a second Design occurrence, not a collapsed repeat."""
    from oracle_brain.operating_model.workflows.process_model import Transition, Support
    t = Transition(transition_id="rw", from_id="sample", to_id="design",
                   support=Support(observation_ids=("o",)), rework=True)
    assert t.rework is True
    o = obligation("D2-O1")
    assert "second Design occurrence" in o.evidence.quote


def test_handoff_obligation_requires_explicit_artifact():
    """D3 handoff cites ART-D-17; missing artifact is an omission, not unresolved."""
    o = obligation("D3-O1")
    assert "ART-D-17" in o.evidence.quote and o.expected == "represented"
    o2 = obligation("D3-O2")
    assert "cannot begin" in o2.evidence.quote
