"""Navigable evidence-supported company model; separate workflows remain separate."""
from typing import Literal
from uuid import UUID
from pydantic import Field,model_validator
from .source_receipts import _StrictModel,SourceRef
from .workflows.process_model import Support,WorkflowModel

class ProcessRecord(_StrictModel):
    process_id: str
    label: str
    scope: str
    source_ids: tuple[UUID,...] = Field(min_length=1)
    observation_ids: tuple[str,...] = Field(min_length=1)
    workflow_ids: tuple[str,...] = ()
    completeness: Literal['complete','partial','ambiguous','conflicted']

class BusinessRecord(_StrictModel):
    object_id: str
    kind: Literal['role','artifact','objective','metric_definition','decision_variant']
    label: str
    scope: str
    support: Support

class Interface(_StrictModel):
    interface_id: str
    from_process: str
    to_process: str
    artifact_id: str
    scope: str
    support: Support
    status: Literal['supported','unresolved']

class AssemblyDecision(_StrictModel):
    decision_id: str
    observation_ids: tuple[str,...] = Field(min_length=2)
    semantic_identity: str = Field(min_length=1)
    scope: str
    method: Literal['explicit_shared_identity','authorized_mapping']
    authority_event_id: UUID | None = None

class BusinessOperatingModel(_StrictModel):
    schema_version: Literal[1] = 1
    model_id: UUID
    version: int = Field(strict=True,ge=1)
    workspace_id: UUID
    source_refs: tuple[SourceRef,...] = Field(min_length=1)
    declared_population: str = Field(min_length=1)
    processes: tuple[ProcessRecord,...] = Field(min_length=1)
    objects: tuple[BusinessRecord,...]
    interfaces: tuple[Interface,...]
    assembly_decisions: tuple[AssemblyDecision,...]
    workflows: tuple[WorkflowModel,...]
    finding_ids: tuple[str,...]
    completeness: Literal['complete','partial','ambiguous','conflicted']
    value_chain_hypotheses: tuple[str,...] = ()

    @model_validator(mode='after')
    def shape(self):
        if any(r.workspace_id!=self.workspace_id for r in self.source_refs):raise ValueError('cross-workspace model')
        for items,key in [(self.processes,'process_id'),(self.objects,'object_id'),(self.interfaces,'interface_id'),(self.workflows,'workflow_id'),(self.assembly_decisions,'decision_id')]:
            ids=[getattr(i,key) for i in items]
            if len(ids)!=len(set(ids)):raise ValueError('duplicate model object identity')
        processes={p.process_id for p in self.processes};objects={o.object_id:o for o in self.objects}
        if any(i.from_process not in processes or i.to_process not in processes or i.artifact_id not in objects for i in self.interfaces):raise ValueError('dangling process interface')
        if any(w.process_id not in processes or w.workspace_id!=self.workspace_id for w in self.workflows):raise ValueError('workflow belongs to unknown process')
        manifest=set(self.source_refs)
        if any(not set(w.source_refs)<=manifest for w in self.workflows):raise ValueError('workflow source outside company manifest')
        for process in self.processes:
            expected={w.workflow_id for w in self.workflows if w.process_id==process.process_id}
            if set(process.workflow_ids)!=expected or len(process.workflow_ids)!=len(expected):raise ValueError('process workflow population mismatch')
            if process.completeness=='complete' and not expected:raise ValueError('complete process requires a documented workflow')
        if self.completeness=='complete' and (any(p.completeness!='complete' for p in self.processes) or any(w.completeness!='complete' for w in self.workflows) or any(i.status=='unresolved' for i in self.interfaces)):
            raise ValueError('incomplete components cannot confer complete company model')
        return self
