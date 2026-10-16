"""Invented provider CONTENT fixtures only; never authority or a quality verdict.

Author these originals before admission. Call model_json only with the actual
persisted extraction payloads. No IO, manifests, grants, timestamps or receipts
are synthesized here. Assessment answers are deliberately injected test outputs.
"""
import json
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.source_receipts import EvidenceRef
from oracle_brain.operating_model.extraction import validate_response
from oracle_brain.operating_model.pipeline import assembly_inputs, assembly_candidate_payload
from oracle_brain.operating_model.acceptance_profiles import CensusPayload, AssessmentPayload
from oracle_brain.operating_model.coverage import Obligation, CoverageRecord
from oracle_brain.operating_model.semantic_acceptance import CRITERIA, CriterionReview

SCOPE = 'invented ART order lifecycle'
PARAGRAPHS = (
 ('Sales records the order and Design prepares approved ART, then sends ART to Factory.',
  'The owner of the ART approval handoff is not specified.'),
 ('Factory receives approved ART from Design, makes the order, and sends ART and finished goods to Quality.',
  'Purchasing states ART production lead time is four weeks. Factory states ART production lead time is six weeks.'),
 ('Quality receives ART and finished goods from Factory, checks the order, and sends the approved shipment to Shipping.',
  'The ART rejection escalation owner is not specified.'),
)
PRIVATE_MARKERS = tuple(f'UNCITED_PRIVATE_ORIGINAL_{i}_7c19' for i in range(3))
RICH_SOURCE_TEXTS = tuple('\n'.join((*p, marker)) for p, marker in zip(PARAGRAPHS, PRIVATE_MARKERS))


def _index(receipt):
    matches = [i for i, text in enumerate(RICH_SOURCE_TEXTS) if receipt.reading == text]
    if len(matches) != 1: raise ValueError('exact fresh invented original required')
    return matches[0]


def _evidence(receipt, quote):
    start = receipt.reading.index(quote)
    return EvidenceRef(ref=receipt.ref, start=start, end=start+len(quote), quote=quote)


def extraction_json(receipt):
    """One paid fake generation: literal observation AND retained local finding."""
    i = _index(receipt)
    quote, issue = PARAGRAPHS[i]
    evidence = _evidence(receipt, issue)
    finding = dict(finding_id=f'issue-{receipt.ref.source_id}', kind='missing_information',
        workspace_id=str(receipt.ref.workspace_id), source_refs=[receipt.ref.model_dump(mode='json')],
        scope=SCOPE, text=issue, origin='source_reported', evidence_refs=[evidence.model_dump(mode='json')])
    if i == 1:
        # Keep the two incompatible assertions as two exact, distinct locators.
        sides = ('Purchasing states ART production lead time is four weeks.',
                 'Factory states ART production lead time is six weeks.')
        es = [_evidence(receipt, s) for s in sides]
        finding.update(kind='source_conflict', evidence_refs=[evidence.model_dump(mode='json'),*[e.model_dump(mode='json') for e in es]],
            opposed_assertions=[dict(question_key='ART production lead time', asserted_value=value,
                evidence=e.model_dump(mode='json')) for value,e in zip(('four weeks','six weeks'),es)])
    raw = dict(schema_version=1, source_id=str(receipt.ref.source_id), source_revision=receipt.ref.revision,
        complete=True, observations=[dict(occurrence_key='literal-lifecycle', kind='handoff', scope=SCOPE,
            value=quote, evidence=[_evidence(receipt,quote).model_dump(mode='json')])],
        findings=[finding], unresolved_items=[])
    validate_response(receipt, raw)
    return json.dumps(raw)


def census_json(context):
    """Source-only inventory: every literal lifecycle and every explicit issue."""
    obligations=[]
    for receipt in context.scope.receipts:
        i=_index(receipt)
        for j, quote in enumerate(PARAGRAPHS[i]):
            obligations.append(Obligation(obligation_id=f'{receipt.ref.source_id}:{j}', priority='essential',
                expected='represented' if j==0 else 'unresolved', evidence=_evidence(receipt,quote),
                reason='Invented explicit lifecycle' if j==0 else 'Invented unresolved source issue'))
    return CensusPayload(obligations=tuple(obligations)).model_dump_json()


def model_json(extractions, *, source_refs, model_id, version=1):
    """Cross-document test suggestion from actual persisted observation identities."""
    payloads=tuple(e.payload if hasattr(e,'payload') else e for e in extractions)
    refs, observations, findings=assembly_inputs(payloads,enforce_unique_sources=True)
    if len(refs)!=3 or set(refs)!=set(source_refs) or len(observations)!=3 or len(findings)!=3:
        raise ValueError('exact three durable rich extractions required')
    by_quote={o.evidence[0].quote:o for o in observations.values()}
    if set(by_quote)!={p[0] for p in PARAGRAPHS}: raise ValueError('rich literal observations required')
    ordered=[by_quote[p[0]] for p in PARAGRAPHS]
    if any(o.scope!=SCOPE or len(o.evidence)!=1 for o in ordered): raise ValueError('unexpected support scope')
    ids=[o.observation_id for o in ordered]
    support=lambda values:dict(observation_ids=values)
    steps=[dict(step_id=f's{i}',label=label,kind='activity',role_id=role,support=support([ids[i]]))
           for i,(label,role) in enumerate((('Order intake and approved ART handoff','Design'),
               ('Factory production and goods handoff','Factory'),('Quality check and shipping handoff','Quality')))]
    wf=dict(schema_version=1,workflow_id='art-flow',version=1,workspace_id=str(refs[0].workspace_id),
        process_id='art-chain',scope=SCOPE,source_refs=[r.model_dump(mode='json') for r in source_refs],
        status='reported',completeness='conflicted',steps=steps,
        transitions=[dict(transition_id=f't{i}',from_id=f's{i}',to_id=f's{i+1}',support=support(ids[i:i+2])) for i in range(2)],
        roles=[dict(assignment_id=f'r{i}',step_id=f's{i}',role_id=role,support=support([ids[i]])) for i,role in enumerate(('Design','Factory','Quality'))],
        artifacts=[dict(artifact_id='ART',label='ART',support=support(ids))],
        handoffs=[dict(handoff_id=f'h{i}',from_step=f's{i}',to_step=f's{i+1}',artifact_id='ART',support=support(ids[i:i+2])) for i in range(2)],
        finding_ids=list(findings),
        # Legacy structural field, NOT independent semantic coverage/admission.
        coverage_digest=digest({'untrusted_fixture_support':ids}))
    model=dict(schema_version=1,model_id=str(model_id),version=version,workspace_id=str(refs[0].workspace_id),
        source_refs=[r.model_dump(mode='json') for r in source_refs],declared_population='Three invented ART lifecycle originals',
        processes=[dict(process_id='art-chain',label='ART order lifecycle',scope=SCOPE,source_ids=[str(r.source_id) for r in source_refs],
            observation_ids=ids,workflow_ids=['art-flow'],completeness='conflicted')],
        objects=[dict(object_id=role,kind='role',label=role,scope=SCOPE,support=support([ids[i]])) for i,role in enumerate(('Design','Factory','Quality'))]+
            [dict(object_id='ART',kind='artifact',label='ART',scope=SCOPE,support=support(ids))],
        interfaces=[],assembly_decisions=[dict(decision_id='explicit-art',observation_ids=ids,semantic_identity='ART',scope=SCOPE,method='explicit_shared_identity')],
        workflows=[wf],finding_ids=list(findings),completeness='conflicted')
    raw=json.dumps(model)
    assembly_candidate_payload(raw,workspace_id=refs[0].workspace_id,refs=refs,observations=observations,findings=findings)
    return raw


def assessment_json(context):
    """Injected independent-model CONTENT only, checked against actual candidate."""
    records=[]
    for obligation in context.census.obligations:
        matching=tuple(key for key,items in context.object_evidence.items() if any(
            e.ref==obligation.evidence.ref and e.start<=obligation.evidence.start and e.end>=obligation.evidence.end
            and e.quote[obligation.evidence.start-e.start:obligation.evidence.end-e.start]==obligation.evidence.quote for e in items))
        if not matching: raise ValueError('candidate omitted a frozen source obligation')
        records.append(CoverageRecord(obligation_id=obligation.obligation_id,disposition=obligation.expected,
            object_ids=matching,reason='Injected fixture assessor located exact supported candidate evidence'))
    evidence=tuple(o.evidence for o in context.census.obligations)
    criteria=tuple(CriterionReview(criterion=name,verdict='pass',
        explanation='Injected fixture verdict; unresolved source conflict and missing owners remain visible, not resolved.',
        evidence=evidence,object_ids=tuple(context.object_evidence)) for name in sorted(CRITERIA))
    return AssessmentPayload(coverage=tuple(records),criteria=criteria).model_dump_json()


def embedding_response(count):
    if type(count) is not int or not 0<count<=10000: raise ValueError('bounded exact input count required')
    return {'object':'list','model':'openai/text-embedding-3-small','data':[
        {'object':'embedding','index':i,'embedding':[1.0]+[0.0]*255} for i in range(count)],
        'usage':{'prompt_tokens':count,'total_tokens':count}}
