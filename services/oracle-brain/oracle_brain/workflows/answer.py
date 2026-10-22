"""Single canonical answer workflow; packing is descriptive, never authorization.

The protected consumer must obtain the qualified body and complete current
recipient scope from the canonical history owner and verify its actual accepted
read-only SDK graph before invoking this bounded deterministic packing step.
No provider, vector query, semantic paraphrase, policy promotion or new fact store.
"""
from datetime import datetime
from collections import Counter
import math
import re
from typing import Literal
from pydantic import AwareDatetime,Field,field_validator,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.consolidation_contracts_v1 import AssertionScopeV1,AssertionRevisionV1,ConsolidationCoreV1,applicable_assertions,validate_core_evidence
from oracle_brain.operating_model.source_receipts import EvidenceRef
from oracle_brain.operating_model.observations import Observation
from oracle_brain.operating_model.findings import Finding
from oracle_brain.operating_model.consolidated_delivery_v1 import AsOfDecisionObservationV1

HASH=r'^[a-f0-9]{64}$'

class AnswerQueryV1(StrictRecord):
    question:str=Field(min_length=1,max_length=4000)
    mode:Literal['local','connected','historical','global']='local'
    scope:AssertionScopeV1|None=None
    process_ids:tuple[str,...]=Field(default=(),max_length=32)
    valid_at:AwareDatetime|None=None
    known_at:AwareDatetime|None=None
    expected_version:int|None=Field(default=None,ge=1)
    max_records:int=Field(default=32,ge=1,le=64)
    max_bytes:int=Field(default=65536,ge=4096,le=131072)
    page:int=Field(default=0,ge=0,le=2047)

    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact answer version required')
        return value

    @model_validator(mode='after')
    def bounded_request(self):
        if not self.question.strip() or '\x00' in self.question or len(self.question.encode('utf-8'))>4000:
            raise ValueError('bounded nonempty original question required')
        if (len(set(self.process_ids))!=len(self.process_ids)
                or any(not p or len(p)>200 or p.strip()!=p or '\x00' in p for p in self.process_ids)):
            raise ValueError('distinct explicit bounded process identities required')
        if (self.mode=='historical') != (self.valid_at is not None and self.known_at is not None):
            raise ValueError('historical question requires both explicit dates only')
        if self.mode!='historical' and (self.valid_at is not None or self.known_at is not None):
            raise ValueError('dates are historical selectors only')
        return self

class AnswerEvidenceV1(StrictRecord):
    supporting:tuple[EvidenceRef,...]=()
    opposing:tuple[EvidenceRef,...]=()
    unknown:tuple[EvidenceRef,...]=()
    temporal:tuple[EvidenceRef,...]=()

class AnswerRecordV1(StrictRecord):
    assertion:AssertionRevisionV1
    evidence:AnswerEvidenceV1
    applicability:Literal['applicable','unknown']
    authority:Literal['reported']='reported'
    company_policy_confirmed:Literal[False]=False

class AnswerCoverageV1(StrictRecord):
    declared_population:str
    declared_process_count:int=Field(ge=1)
    represented_process_ids:tuple[str,...]
    declared_assertion_count:int=Field(ge=1)
    selected_assertion_count:int=Field(ge=0)
    returned_assertion_count:int=Field(ge=0)
    complete_within_declared_model:bool
    entire_company_verified:Literal[False]=False

class AnswerProcessChoiceV1(StrictRecord):
    process_id:str
    label:str

class DocumentaryAnswerV1(StrictRecord):
    state:Literal['answered','partial','missing','clarification','coverage_incomplete']
    answer_text:str
    model_version:int=Field(ge=1)
    model_content_hash:str=Field(pattern=HASH)
    selection:Literal['deterministic-qualified-records-v1']='deterministic-qualified-records-v1'
    mode:Literal['local','connected','historical','global']
    valid_at:AwareDatetime
    known_at:AwareDatetime|None
    records:tuple[AnswerRecordV1,...]=Field(max_length=64)
    findings:tuple[Finding,...]=()
    coverage:AnswerCoverageV1
    continuation_page:int|None=Field(default=None,ge=1)
    plan_sha256:str=Field(pattern=HASH)
    caveats:tuple[str,...]
    provider_generation_used:Literal[False]=False
    query_embedding_used:Literal[False]=False
    business_accepted:Literal[False]=False
    business_decisions_as_of:tuple[AsOfDecisionObservationV1,...]=Field(default=(),max_length=128)
    process_choices:tuple[AnswerProcessChoiceV1,...]=()

    @model_validator(mode='after')
    def evidence_before_answer(self):
        if self.state=='answered' and (not self.records or any(not r.evidence.supporting for r in self.records)):
            raise ValueError('supported records required for answered result')
        if self.coverage.returned_assertion_count!=len(self.records):raise ValueError('exact returned population required')
        return self


def _possible_scope(offer,query):
    return all(not (getattr(offer,k).mode=='exact' and getattr(query,k).mode=='exact'
        and not set(getattr(offer,k).identities)&set(getattr(query,k).identities))
        for k in ('process','customer','product','region'))


def _process_population(core,query):
    available={p.process_id:p for p in core.model.processes}
    if any(p not in available for p in query.process_ids):raise LookupError('requested scope is unavailable')
    selected=set(available) if query.mode=='global' else set(query.process_ids)
    if query.mode=='connected':
        for _ in range(2):
            seeds=frozenset(selected)
            for edge in core.model.interfaces:
                if edge.status=='supported' and (edge.from_process in seeds or edge.to_process in seeds):
                    selected.update((edge.from_process,edge.to_process))
    observations={o for key in selected for o in available[key].observation_ids}
    for flow in core.model.workflows:
        if flow.process_id in selected:
            for collection in ('steps','gateways','transitions','conditions','roles','artifacts','handoffs'):
                for item in getattr(flow,collection):observations.update(item.support.observation_ids)
    return tuple(sorted(selected)),observations


_QUESTION_WORDS=frozenset(('a','an','the','is','are','was','were','be','been','do','does','did',
    'what','who','which','where','when','how','why','please','tell','me','our','this','that','these','those','of','to','in','on','for','and','or'))


class _RankingLimitV1(ValueError):
    pass


def _unicode_terms_v1(text):
    """Ranking only: original question, claims, quotes and IDs never change.

    Negation is deliberately retained. Han bigrams permit lexical Chinese
    matching without dropping a negative or pretending to translate/paraphrase.
    No stem/synonym dictionary chooses business identities or permissions.
    """
    terms=[]
    for word in re.findall(r'[^\W_]+',text.casefold()):
        if word in _QUESTION_WORDS:continue
        terms.append(word)
        for run in re.findall(r'[\u3400-\u9fff\U00020000-\U0002ffff]+',word):
            terms.extend(run[i:i+2] for i in range(len(run)-1))
    return tuple(terms)


def _rank_records_v1(question,assertions,core,observations):
    from oracle_brain.operating_model.request_deadline_v1 import request_remaining_v1
    query=Counter(_unicode_terms_v1(question));documents=[];total_bytes=0;total_terms=0
    for assertion in assertions:
        request_remaining_v1(required=False)
        ids=set(assertion.supporting_observations)|set(assertion.opposing_observations)|set(assertion.temporal_observations)
        # All labels/values come from the SAME permitted qualified body. These
        # are lexical candidates, not newly entailed facts or inferred scope.
        labels=[p.label for p in core.model.processes if ids&set(p.observation_ids)]
        labels.extend(o.label for o in core.model.objects if o.object_id==str(assertion.subject_id))
        text=' '.join((assertion.predicate,assertion.value,*labels,*(observations[k].value for k in sorted(ids))))
        total_bytes+=len(text.encode('utf-8'));terms=Counter(_unicode_terms_v1(text));total_terms+=sum(terms.values())
        if total_bytes>16*1024*1024 or total_terms>1000000:raise _RankingLimitV1('complete lexical population exceeds bounded ranking')
        documents.append((assertion,terms))
    if not documents:return ()
    count=len(documents);average=max(1,total_terms/count)
    frequencies=Counter(term for _,terms in documents for term in terms if term in query)
    ranked=[]
    for assertion,terms in documents:
        length=sum(terms.values());score=0.
        for term in query:
            frequency=terms.get(term,0)
            if frequency:
                inverse=math.log1p((count-frequencies[term]+.5)/(frequencies[term]+.5))
                score+=inverse*frequency*2.2/(frequency+1.2*(.25+.75*length/average))
        exact_id=str(assertion.assertion_id) in question
        phrase=assertion.value.casefold() in question.casefold()
        ranked.append((int(exact_id),int(phrase),score,assertion))
    # Deterministic bounded rerank; a score is NEVER an entailment/quality proof.
    return tuple(sorted(ranked,key=lambda r:(-r[0],-r[1],-r[2],str(r[3].assertion_id))))


def _pack_answer_v1(core,payload,metadata,query,*,observed_at):
    """Private pure pack. Its inputs/output are NOT a current-read capability."""
    from .natural_answer_v1 import NaturalResolvedPlanV1
    if type(core) is not ConsolidationCoreV1 or type(query) not in (AnswerQueryV1,NaturalResolvedPlanV1):
        raise TypeError('exact immutable core and query required')
    query=type(query).model_validate_json(canonical_bytes(query.model_dump(mode='json')))
    core=ConsolidationCoreV1.model_validate_json(canonical_bytes(core.model_dump(mode='json')))
    if (not isinstance(observed_at,datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None
            or query.known_at is not None and query.known_at>observed_at):raise ValueError('actual bounded known time required')
    if (metadata['manifest']['content_hash']!=digest(payload)
            or core.model.model_dump(mode='json')!=payload['operating_models'][0]
            or core.model_dump(mode='json')!=payload['consolidation_core']):raise PermissionError('exact retained qualified model required')
    if query.expected_version is not None and query.expected_version!=core.model.version:raise ValueError('model changed; refresh current answer scope')
    observations={o['observation_id']:Observation.model_validate_json(canonical_bytes(o)) for o in payload['observations']}
    findings={f['finding_id']:Finding.model_validate_json(canonical_bytes(f)) for f in payload.get('findings',[])}
    if len(observations)!=len(payload['observations']) or len(findings)!=len(payload.get('findings',[])):
        raise PermissionError('duplicate retained evidence identity')
    validate_core_evidence(core,observations,{k:v.model_dump(mode='json') for k,v in findings.items()})
    processes,process_observations=_process_population(core,query)
    at=query.valid_at or observed_at
    plan=digest(query.model_dump(mode='json')|{'model_content_hash':digest(payload)})
    base_coverage=dict(declared_population=core.model.declared_population,declared_process_count=len(core.model.processes),
        represented_process_ids=processes,declared_assertion_count=len(core.assertions))
    caveats=('Reported records are not company-policy approval.',
        'Citations are retained-qualified original references; opening originals requires separate current access.',
        'Selection uses exact qualified records and bounded relationships; no semantic generation or vector query.',
        'Coverage describes this exact authorized model; company-wide completeness is not verified.')
    def response(state,text,records=(),selected=0,continuation=None,required_findings=()):
        complete=(query.mode=='global' and selected==len(core.assertions)==len(records)
            and core.model.completeness=='complete' and all(r.applicability=='applicable' for r in records))
        return DocumentaryAnswerV1(state=state,answer_text=text,model_version=core.model.version,model_content_hash=digest(payload),
            mode=query.mode,valid_at=at,known_at=query.known_at,records=records,findings=required_findings,
            coverage=AnswerCoverageV1(**base_coverage,selected_assertion_count=selected,returned_assertion_count=len(records),complete_within_declared_model=complete),
            continuation_page=continuation,plan_sha256=plan,caveats=caveats,process_choices=tuple(AnswerProcessChoiceV1(process_id=p.process_id,label=p.label) for p in core.model.processes))
    if query.scope is None or any(getattr(query.scope,k).mode=='unknown' for k in ('process','customer','product','region')) or not processes:
        return response('clarification','Which exact process and customer, product and region scope should this question cover?')
    applicable={a.assertion_id for a in applicable_assertions(core,valid_at=at,scope=query.scope)}
    eligible=[]
    for a in core.assertions:
        if not _possible_scope(a.scope,query.scope):continue
        ids=set(a.supporting_observations)|set(a.opposing_observations)|set(a.temporal_observations)
        if query.mode!='global' and not ids&process_observations:continue
        unknown=a.valid_time=='unknown' or any(getattr(a.scope,k).mode=='unknown' for k in ('process','customer','product','region'))
        if a.assertion_id in applicable or unknown:eligible.append(a)
    try:scored=_rank_records_v1(query.question,eligible,core,observations)
    except _RankingLimitV1:
        return response('coverage_incomplete','The complete relevant evidence exceeds the bounded lexical search. Narrow the question; no partial search is presented as complete.',selected=len(eligible))
    if query.mode=='global':selected=tuple(a for *_,a in scored)
    else:
        seeds={(a.subject_id,a.predicate) for exact,phrase,score,a in scored if exact or phrase or score>0}
        selected=tuple(a for *_,a in scored if (a.subject_id,a.predicate) in seeds)
    if not selected:return response('missing','The qualified records do not establish an answer for this question and scope.')
    # Never split an opposing/exception assertion group at a top-k or page
    # boundary. A group which cannot fit produces an explicit incomplete result.
    groups={}
    for assertion in selected:groups.setdefault((assertion.subject_id,assertion.predicate),[]).append(assertion)
    if any(len(group)>query.max_records for group in groups.values()):
        return response('coverage_incomplete','A complete assertion and exception group exceeds this answer limit. Narrow the question; no side of the group is omitted.',selected=len(selected))
    pages=[[]]
    for group in groups.values():
        if len(pages[-1])+len(group)>query.max_records:pages.append([])
        pages[-1].extend(group)
    if query.page>=len(pages):raise LookupError('answer page is outside the exact selected population')
    page=pages[query.page]
    records=[];finding_ids=set(core.model.finding_ids)
    for a in page:
        def quotes(ids,unknown=False):
            return tuple(e for key in ids for e in (findings[key].evidence_refs if unknown else observations[key].evidence))
        finding_ids.update(a.unknown_finding_ids)
        records.append(AnswerRecordV1(assertion=a,applicability='applicable' if a.assertion_id in applicable else 'unknown',
            evidence=AnswerEvidenceV1(supporting=quotes(a.supporting_observations),opposing=quotes(a.opposing_observations),
                temporal=quotes(a.temporal_observations),unknown=quotes(a.unknown_finding_ids,True))))
    if not finding_ids<=findings.keys():raise PermissionError('required material findings absent from exact model')
    required=tuple(findings[k] for k in sorted(finding_ids))
    continuation=query.page+1 if query.page+1<len(pages) else None
    incomplete=continuation is not None or any(r.applicability=='unknown' or r.evidence.opposing or r.evidence.unknown or not r.evidence.supporting for r in records) or core.model.completeness!='complete'
    text='\n'.join(('Reported, applicability unknown: ' if r.applicability=='unknown' else 'Reported: ')+r.assertion.value for r in records)
    answer=response('partial' if incomplete else 'answered',text,tuple(records),len(selected),continuation,required)
    if len(canonical_bytes(answer.model_dump(mode='json')))>query.max_bytes:
        return response('coverage_incomplete','Required evidence, exceptions and uncertainty exceed this answer limit; narrow the question.',selected=len(selected))
    return answer


async def answer_from_projection_v1(projection,query):
    """One actual own-role SQL/private/readonly SDK path, shared by web and MCP.

    Packing alone cannot enter this entry point. The exact projection owns its
    current recipient checks and complete retained graph lineage census.
    """
    from oracle_brain.operating_model.sdk_projection import ConsolidatedMetadataSDKProjectionV1
    from oracle_brain.operating_model.request_deadline_v1 import request_remaining_v1
    if type(projection) is not ConsolidatedMetadataSDKProjectionV1 or type(query) is not AnswerQueryV1:
        raise PermissionError('actual exact own-role readonly SDK and strict question required')
    request_remaining_v1()
    before=await projection.load()
    answer=_pack_answer_v1(before[0],before[2],before[1],query,observed_at=before[3].checked_at)
    if query.mode=='historical':
        answer=DocumentaryAnswerV1.model_validate_json(canonical_bytes(answer.model_dump(mode='json')|{
            'business_decisions_as_of':[d.model_dump(mode='json') for d in before[3].business_decisions_as_of]}))
    await projection.verify(before[2])
    request_remaining_v1()
    return answer,before
