"""Fixed synthesis references over retained qualified answers, never new facts.

Provider output may group exact existing assertion IDs and name only observed
limitations. Rendering derives factual text and citations from the original
validated packet. Optional interpretation is explicitly unverified and ordinary
chat only; this validator proves structure/reference membership, NOT entailment.
"""
from typing import Literal
from uuid import UUID
from pydantic import Field,field_validator,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes
from .qualified_answer_v1 import DocumentaryAnswerV1,QualifiedVectorAnswerV1,QualifiedSynthesisAnswerV1

class FactualGroupV1(StrictRecord):
    assertion_ids:tuple[UUID,...]=Field(min_length=1,max_length=64)
    classification:Literal['reported','opposed','unknown']
    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact factual group version required')
        return value
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.assertion_ids))!=len(self.assertion_ids):raise ValueError('distinct exact retained assertion references required')
        return self

class QualifiedSynthesisResponseV1(StrictRecord):
    protocol:Literal['qualified-answer-synthesis-output-v1']='qualified-answer-synthesis-output-v1'
    factual_groups:tuple[FactualGroupV1,...]=Field(max_length=64)
    gap_codes:tuple[Literal['coverage_incomplete','missing_evidence','opposing_accounts','applicability_unknown','unconfirmed_policy'],...]=Field(max_length=5)
    unverified_interpretation:str|None=Field(default=None,max_length=2000)
    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact synthesis output version required')
        return value
    @model_validator(mode='after')
    def bounded(self):
        if len(set(self.gap_codes))!=len(self.gap_codes):raise ValueError('duplicate gap code')
        if self.unverified_interpretation is not None and (not self.unverified_interpretation.strip() or '\0' in self.unverified_interpretation or len(self.unverified_interpretation.encode('utf8'))>8000):
            raise ValueError('bounded explicitly unverified interpretation required')
        return self

def synthesis_groups_v1(answer):
    if type(answer) not in (DocumentaryAnswerV1,QualifiedVectorAnswerV1,QualifiedSynthesisAnswerV1):raise TypeError('exact retained documentary answer required')
    groups={}
    for r in answer.records:groups.setdefault((r.assertion.subject_id,r.assertion.predicate),[]).append(r)
    return tuple(groups.values())

def synthesis_gap_codes_v1(answer):
    codes={'unconfirmed_policy'}
    if answer.state=='coverage_incomplete' or answer.continuation_page is not None or not answer.coverage.complete_within_declared_model:codes.add('coverage_incomplete')
    if not answer.records or any(not r.evidence.supporting for r in answer.records):codes.add('missing_evidence')
    if any(r.evidence.opposing for r in answer.records):codes.add('opposing_accounts')
    if any(r.applicability=='unknown' or r.evidence.unknown for r in answer.records):codes.add('applicability_unknown')
    return tuple(sorted(codes))

def validate_qualified_synthesis_v1(raw,answer,*,interview):
    if type(answer) not in (DocumentaryAnswerV1,QualifiedVectorAnswerV1,QualifiedSynthesisAnswerV1) or type(interview) is not bool:raise TypeError('exact qualified answer and actual conversation mode required')
    import json
    if type(raw) is not bytes or not 1<=len(raw)<=65536:raise ValueError('bounded actual synthesis response required')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate synthesis field')
            result[key]=value
        return result
    obj=json.loads(raw.decode('utf8'),object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite synthesis')))
    if type(obj) is not dict:raise ValueError('closed synthesis object required')
    if set(obj)!=set(QualifiedSynthesisResponseV1.model_fields):raise ValueError('closed complete synthesis output required')
    parsed=QualifiedSynthesisResponseV1.model_validate_json(canonical_bytes(obj))
    expected={frozenset(r.assertion.assertion_id for r in group):group for group in synthesis_groups_v1(answer)}
    actual=[frozenset(g.assertion_ids) for g in parsed.factual_groups]
    if len(actual)!=len(set(actual)) or set(actual)!=set(expected):raise ValueError('all complete retained assertion and opposition groups must be preserved')
    for group in parsed.factual_groups:
        records=expected[frozenset(group.assertion_ids)]
        classification=('opposed' if any(r.evidence.opposing for r in records) else 'unknown' if any(r.applicability=='unknown' or r.evidence.unknown or not r.evidence.supporting for r in records) else 'reported')
        if group.classification!=classification:raise ValueError('model cannot relabel opposition or unknown applicability')
    if set(parsed.gap_codes)!=set(synthesis_gap_codes_v1(answer)):raise ValueError('all exact observed gaps must be retained; no invented omission')
    if interview and parsed.unverified_interpretation is not None:raise PermissionError('active interview permits only deterministic facts before its sole SQL question')
    return parsed

def render_qualified_synthesis_v1(parsed,answer,*,interview):
    if type(parsed) is not QualifiedSynthesisResponseV1:raise TypeError('exact synthesis output required')
    validate_qualified_synthesis_v1(canonical_bytes(parsed.model_dump(mode='json')),answer,interview=interview)
    records={r.assertion.assertion_id:r for r in answer.records}
    # The model contributes ordering only. All factual words/citations remain
    # exactly the actual retained qualified packet, including opposing quotes.
    return {'protocol':'qualified-answer-synthesis-render-v1','factual_groups':[
        {'classification':g.classification,'records':[records[a].model_dump(mode='json') for a in g.assertion_ids]} for g in parsed.factual_groups],
        'gap_codes':list(parsed.gap_codes),'interpretation':None if parsed.unverified_interpretation is None else {'classification':'inference/unverified interpretation','text':parsed.unverified_interpretation},
        'coverage':answer.coverage.model_dump(mode='json'),'semantic_entailment_verified':False,'business_accepted':False}


def validate_synthesis_render_v1(value,answer,*,interview):
    """Same renderer membership guards for new closed body types; no old-body rewrite."""
    if type(value) is not dict or set(value)!={'protocol','factual_groups','gap_codes','interpretation','coverage','semantic_entailment_verified','business_accepted'} or value['protocol']!='qualified-answer-synthesis-render-v1':raise ValueError('closed synthesis render required')
    groups=value['factual_groups']
    if type(groups) is not list or len(groups)>64:raise ValueError('bounded exact rendered groups required')
    factual=[]
    for group in groups:
        if type(group) is not dict or set(group)!={'classification','records'} or type(group['records']) is not list or not 1<=len(group['records'])<=64:raise ValueError('complete exact rendered group required')
        factual.append(dict(schema_version=1,classification=group['classification'],assertion_ids=[r['assertion']['assertion_id'] for r in group['records']]))
    interpretation=value['interpretation']
    if interpretation is not None and(type(interpretation) is not dict or set(interpretation)!={'classification','text'} or interpretation['classification']!='inference/unverified interpretation'):raise ValueError('interpretation must remain explicitly unverified')
    parsed=validate_qualified_synthesis_v1(canonical_bytes(dict(schema_version=1,protocol='qualified-answer-synthesis-output-v1',factual_groups=factual,gap_codes=value['gap_codes'],unverified_interpretation=None if interpretation is None else interpretation['text'])),answer,interview=interview)
    if canonical_bytes(render_qualified_synthesis_v1(parsed,answer,interview=interview))!=canonical_bytes(value):raise ValueError('render changed exact factual words, citations, opposition, gaps or coverage')
    return parsed

def synthesis_references_v1(parsed,answer,*,interview):
    """New public references only; canonical facts/quotes appear once in answer.

    The retained internal renderer remains unchanged. Complete ID groups resolve
    to exactly that answer's full records, including opposition and uncertainty.
    """
    validate_qualified_synthesis_v1(canonical_bytes(parsed.model_dump(mode='json')),answer,interview=interview)
    return {'protocol':'qualified-answer-synthesis-references-v1','factual_groups':[
        {'classification':g.classification,'assertion_ids':[str(a) for a in g.assertion_ids]} for g in parsed.factual_groups],
        'gap_codes':list(parsed.gap_codes),'interpretation':None if parsed.unverified_interpretation is None else {'classification':'inference/unverified interpretation','text':parsed.unverified_interpretation},
        'coverage':answer.coverage.model_dump(mode='json'),'semantic_entailment_verified':False,'business_accepted':False}

def validate_synthesis_references_v1(value,answer,*,interview):
    if type(value) is not dict or set(value)!={'protocol','factual_groups','gap_codes','interpretation','coverage','semantic_entailment_verified','business_accepted'} or value['protocol']!='qualified-answer-synthesis-references-v1':raise ValueError('closed public synthesis references required')
    groups=value['factual_groups']
    if type(groups) is not list or len(groups)>64 or any(type(g) is not dict or set(g)!={'classification','assertion_ids'} for g in groups):raise ValueError('complete exact reference groups required')
    interpretation=value['interpretation']
    if interpretation is not None and(type(interpretation) is not dict or set(interpretation)!={'classification','text'} or interpretation['classification']!='inference/unverified interpretation'):raise ValueError('interpretation remains explicitly unverified')
    parsed=validate_qualified_synthesis_v1(canonical_bytes(dict(schema_version=1,protocol='qualified-answer-synthesis-output-v1',factual_groups=[{'schema_version':1}|g for g in groups],gap_codes=value['gap_codes'],unverified_interpretation=None if interpretation is None else interpretation['text'])),answer,interview=interview)
    if canonical_bytes(synthesis_references_v1(parsed,answer,interview=interview))!=canonical_bytes(value):raise ValueError('references changed exact groups, opposition, gaps, coverage or labels')
    return parsed
