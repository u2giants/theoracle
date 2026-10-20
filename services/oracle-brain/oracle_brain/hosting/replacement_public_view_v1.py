"""Pure public projection. Validation conveys no source, semantic or serving authority."""
from typing import Annotated, Literal
import json
from pydantic import BaseModel, ConfigDict, Field, AfterValidator, model_validator

MAX_SAFE = 9007199254740991

def _text(limit, *, trim=False, minimum=1):
    def check(value):
        if trim: value=value.strip('\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff')
        size=len(value.encode('utf-16-le',errors='surrogatepass'))//2
        if not minimum <= size <= limit: raise ValueError('public text bound')
        return value
    return Annotated[str,AfterValidator(check)]
Name=_text(200,trim=True)
Hash=Annotated[str,Field(pattern=r'^[a-f0-9]{64}$')]
ID=Annotated[str,Field(pattern=r'^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}|00000000-0000-0000-0000-000000000000|[fF]{8}-[fF]{4}-[fF]{4}-[fF]{4}-[fF]{12})$')]
Revision=Annotated[int,Field(ge=1,le=MAX_SAFE)]
Offset=Annotated[int,Field(ge=0,le=MAX_SAFE)]
class Public(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid',frozen=True)
    @model_validator(mode='before')
    @classmethod
    def no_optional_null(cls,value):
        if isinstance(value,dict) and any(key in value and value[key] is None for key in ('pageView','role_id','condition_id')):raise ValueError('optional field is not nullable')
        return value
class Source(Public):
    workspaceId:ID;sourceId:ID;revision:Revision;originalSha256:Hash;readingSha256:Hash;parserId:Name
class EvidenceSource(Public):
    source_id:ID;revision:Revision
class Span(Public):
    start:Offset;end:Revision;quote:_text(16000)
    @model_validator(mode='after')
    def span(self):
        if self.end<=self.start or len(self.quote)!=self.end-self.start:raise ValueError('Unicode span differs')
        return self
class Evidence(Span):
    ref:EvidenceSource
class Page(Public):
    viewId:Annotated[str,Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$')]
    pageNumber:Annotated[int,Field(ge=1,le=40)]
    imageSha256:Hash;byteCount:Annotated[int,Field(ge=1,le=25*1024*1024)]
    width:Annotated[int,Field(ge=1,le=20000)];height:Annotated[int,Field(ge=1,le=20000)]
    @model_validator(mode='after')
    def pixels(self):
        if self.width*self.height>20000000:raise ValueError('pixel bound')
        return self
class Citation(Span):
    source:Source;pageView:Page|None=Field(default=None,exclude_if=lambda v:v is None)
    @model_validator(mode='before')
    @classmethod
    def optional_not_null(cls,value):
        if isinstance(value,dict) and 'pageView' in value and value['pageView'] is None:raise ValueError('optional page is not nullable')
        return value
class Support(Public):
    observation_ids:Annotated[list[Name],Field(min_length=1,max_length=200)]
class Step(Public):
    step_id:Name;label:Name;kind:Literal['activity','start','end','rejection','call','return'];role_id:Name|None=Field(default=None,exclude_if=lambda v:v is None);support:Support
class Gateway(Public):
    gateway_id:Name;kind:Literal['exclusive_split','exclusive_join','parallel_split','parallel_join','unsupported'];support:Support
class Transition(Public):
    transition_id:Name;from_id:Name;to_id:Name;condition_id:Name|None=Field(default=None,exclude_if=lambda v:v is None);rework:bool;support:Support
class Condition(Public):
    condition_id:Name;wording:_text(2000);applicability:Name
class Workflow(Public):
    workflow_id:Name;scope:Name;completeness:Literal['partial','complete','ambiguous','conflicted']
    steps:Annotated[list[Step],Field(min_length=1,max_length=200)]
    gateways:Annotated[list[Gateway],Field(max_length=100)]
    transitions:Annotated[list[Transition],Field(max_length=500)]
    conditions:Annotated[list[Condition],Field(max_length=200)]
class Finding(Public):
    scope:Name;finding_id:Name;kind:Literal['missing_information','source_conflict','model_incomplete'];text:_text(4000)
    status:Literal['unresolved','resolved_by_authorized_review','superseded','withdrawn','needs_evidence']
    origin:Literal['source_reported','reported_conflict_unverified','coverage_inference','legacy_unverified','structural_diagnostic']
    evidence_refs:Annotated[list[Evidence],Field(max_length=100)]
class Observation(Public):
    observation_id:Name;evidence:Annotated[list[Evidence],Field(min_length=1,max_length=100)]
class MapView(Public):
    workflow:Workflow;findings:Annotated[list[Finding],Field(max_length=1000)]
    observations:Annotated[list[Observation],Field(min_length=1,max_length=1000)]
    @model_validator(mode='after')
    def links(self):
        w=self.workflow;nodes=[x.step_id for x in w.steps]+[x.gateway_id for x in w.gateways]
        ids=nodes+[x.transition_id for x in w.transitions]+[x.condition_id for x in w.conditions]
        observations=[x.observation_id for x in self.observations]
        if len(set(ids))!=len(ids) or len(set(observations))!=len(observations):raise ValueError('duplicate identity')
        if any(not set(x.support.observation_ids)<=set(observations) for x in [*w.steps,*w.gateways,*w.transitions]):raise ValueError('missing support')
        if any(x.from_id not in nodes or x.to_id not in nodes or (x.condition_id is not None and x.condition_id not in [c.condition_id for c in w.conditions]) for x in w.transitions):raise ValueError('dangling connection')
        return self
class Model(Public):
    modelId:ID;version:Revision;contentHash:Hash;ackEventId:ID
class Confirmation(Public):
    workflowId:Name;version:Revision;contentHash:Hash;current:bool
class Answer(Public):
    text:_text(32000);citations:Annotated[list[Citation],Field(min_length=1,max_length=100)]
State=Literal['uploading','awaiting_original_reading','awaiting_admission','processing','draft_ready','revision_pending','confirmed_for_scope','answer_ready','cancel_requested','cancelled','failed_spent','error','evidence_missing']
class ReplacementSnapshotV1(Public):
    journeyId:ID;journeyRevision:Revision;state:State;sources:Annotated[list[Source],Field(max_length=100)]
    model:Model|None;confirmation:Confirmation|None;answer:Answer|None;message:_text(1000,minimum=0);mapView:MapView|None
    @model_validator(mode='after')
    def current(self):
        m=self.model;c=self.confirmation;v=self.mapView
        if len({s.sourceId for s in self.sources})!=len(self.sources):raise ValueError('duplicate source')
        if v and not m:raise ValueError('map requires model')
        if c and c.current:
            if not m or c.version!=m.version or c.contentHash!=m.contentHash or self.state not in ('confirmed_for_scope','answer_ready') or (v and c.workflowId!=v.workflow.workflow_id):raise ValueError('confirmation differs')
        if m and self.state not in ('draft_ready','confirmed_for_scope','answer_ready'):raise ValueError('stale model')
        if self.state=='confirmed_for_scope' and not (c and c.current):raise ValueError('confirmation required')
        if self.state=='answer_ready' and not (m and self.answer):raise ValueError('answer required')
        if self.answer and self.state!='answer_ready':raise ValueError('stale answer')
        if v:
            for evidence in [*[e for f in v.findings for e in f.evidence_refs],*[e for o in v.observations for e in o.evidence]]:
                if not any(s.sourceId==evidence.ref.source_id and s.revision==evidence.ref.revision for s in self.sources):raise ValueError('foreign evidence')
        if self.answer and any(citation.source not in self.sources for citation in self.answer.citations):raise ValueError('foreign citation')
        return self

def validate_public_snapshot_v1(value:object)->ReplacementSnapshotV1:
    result=ReplacementSnapshotV1.model_validate(value)
    if len(json.dumps(result.model_dump(mode='json',by_alias=True,exclude_unset=True),ensure_ascii=False,separators=(',',':')).encode())>2*1024*1024:raise ValueError('public snapshot byte bound')
    return result

def public_snapshot_v1(*,journey_id,journey_revision,state,sources,model,confirmation,answer,message,map_view)->ReplacementSnapshotV1:
    return validate_public_snapshot_v1(dict(journeyId=journey_id,journeyRevision=journey_revision,state=state,sources=sources,model=model,confirmation=confirmation,answer=answer,message=message,mapView=map_view))

def qualified_map_view_v1(model, *, workflow_id:str, observations:tuple, findings:tuple)->MapView:
    """Project already-qualified typed content; caller must prove current serving authority.

    No payload parsing, grants, confirmations, original reads or semantic admission occur.
    Only explicitly supported display fields and evidence quotations leave this helper.
    """
    from oracle_brain.operating_model.model import BusinessOperatingModel
    from oracle_brain.operating_model.observations import Observation as NativeObservation
    from oracle_brain.operating_model.findings import Finding as NativeFinding
    if type(model) is not BusinessOperatingModel or type(observations) is not tuple or type(findings) is not tuple or any(type(x) is not NativeObservation for x in observations) or any(type(x) is not NativeFinding for x in findings):raise TypeError('exact typed qualified projection inputs required')
    if len({x.observation_id for x in observations})!=len(observations) or len({x.finding_id for x in findings})!=len(findings) or {x.finding_id for x in findings}!=set(model.finding_ids):raise ValueError('projection evidence population differs')
    refs=set(model.source_refs)
    if any(x.ref not in refs or any(e.ref not in refs for e in x.evidence) for x in observations) or any(not set(x.source_refs)<=refs for x in findings):raise ValueError('projection source differs')
    matches=[w for w in model.workflows if w.workflow_id==workflow_id]
    if len(matches)!=1:raise ValueError('exact current workflow required')
    w=matches[0]
    def evidence(e):return dict(ref=dict(source_id=str(e.ref.source_id),revision=e.ref.revision),start=e.start,end=e.end,quote=e.quote)
    # Explicit collections/fields: no raw payload, private locations or hidden authority records.
    steps=[dict(step_id=x.step_id,label=x.label,kind=x.kind,support=dict(observation_ids=list(x.support.observation_ids)))|({'role_id':x.role_id} if x.role_id is not None else {}) for x in w.steps]
    gateways=[dict(gateway_id=x.gateway_id,kind=x.kind,support=dict(observation_ids=list(x.support.observation_ids))) for x in w.gateways]
    transitions=[dict(transition_id=x.transition_id,from_id=x.from_id,to_id=x.to_id,rework=x.rework,support=dict(observation_ids=list(x.support.observation_ids)))|({'condition_id':x.condition_id} if x.condition_id is not None else {}) for x in w.transitions]
    return MapView.model_validate(dict(workflow=dict(workflow_id=w.workflow_id,scope=w.scope,completeness=w.completeness,steps=steps,gateways=gateways,transitions=transitions,conditions=[dict(condition_id=x.condition_id,wording=x.wording,applicability=x.applicability) for x in w.conditions]),observations=[dict(observation_id=x.observation_id,evidence=[evidence(e) for e in x.evidence]) for x in observations],findings=[dict(scope=x.scope,finding_id=x.finding_id,kind=x.kind,text=x.text,status=x.status,origin=x.origin,evidence_refs=[evidence(e) for e in x.evidence_refs]) for x in findings]))

def documentary_answer_public_v1(answer,source_refs:tuple)->Answer|None:
    """Present an already-authorized documentary answer; abstention remains absent.

    Exact current source population is supplied by the protected caller. These types,
    text and citations are transport validation, never an access or semantic grant.
    """
    from oracle_brain.operating_model.answer import Answer as NativeAnswer
    from oracle_brain.operating_model.source_receipts import SourceRef
    if type(answer) is not NativeAnswer or type(source_refs) is not tuple or not source_refs or any(type(ref) is not SourceRef for ref in source_refs):raise TypeError('exact documentary answer/current refs required')
    if len(set(source_refs))!=len(source_refs) or len({ref.workspace_id for ref in source_refs})!=1:raise ValueError('exact unique current population required')
    if any(citation.ref not in source_refs for citation in answer.citations):raise ValueError('answer citation outside current population')
    if answer.state=='abstained':return None
    if not answer.records or not answer.citations:raise ValueError('answered content and evidence required')
    headings={'overview':'Reported process overview','process_steps':'Reported process steps','roles':'Reported roles','artifacts':'Reported artifacts','interfaces':'Reported interfaces','findings':'Reported findings'}
    fallback={'overview':'A reported process is supported by the cited evidence.','process_steps':'A reported step is supported by the cited evidence.','roles':'A reported role assignment is supported by the cited evidence.','artifacts':'A reported artifact is supported by the cited evidence.','interfaces':'A reported interface is supported by the cited evidence.','findings':'A reported finding is retained with the cited evidence.'}
    lines=[headings[answer.intent]]
    for record in answer.records:
        fields=('text',) if answer.intent=='findings' else ('label','wording')
        displayed=[]
        for key in fields:
            if key in record:
                value=record[key]
                if type(value) is not str or not value:raise ValueError('invalid documentary display field')
                displayed.append(value)
        lines.append(' '.join(displayed) if displayed else fallback[answer.intent])
    # Preserve every retained caveat; never silently truncate, relabel suggestions,
    # or serialize arbitrary native record fields/private context.
    for finding in answer.findings:
        text=finding.get('text')
        if type(text) is not str or not text:raise ValueError('invalid retained finding text')
        if text not in lines and text not in answer.caveats:lines.append('Retained finding: '+text)
    from oracle_brain.operating_model.answer import SUGGESTION_PREFIX
    suggestions=tuple(c for c in answer.caveats if type(c) is str and c.startswith(SUGGESTION_PREFIX))
    caveats=tuple(c for c in answer.caveats if type(c) is str and not c.startswith(SUGGESTION_PREFIX))
    if suggestions:lines.extend(['Suggested improvements (not established fact)',*suggestions])
    if caveats:lines.extend(['Caveats',*caveats])
    citations=[]
    for citation in answer.citations:
        ref=citation.ref
        source=dict(workspaceId=str(ref.workspace_id),sourceId=str(ref.source_id),revision=ref.revision,originalSha256=ref.original_sha256,readingSha256=ref.reading_sha256,parserId=ref.parser_id)
        citations.append(dict(source=source,start=citation.start,end=citation.end,quote=citation.quote))
    return Answer.model_validate(dict(text='\n'.join(lines),citations=citations))
