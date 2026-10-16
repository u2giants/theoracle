from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, model_validator
from ..source_receipts import SourceRef, _StrictModel

Nonempty = Annotated[str, Field(min_length=1)]
SupportIds = Annotated[tuple[str, ...], Field(min_length=1)]

# One identity contract for capture, independent evidence and SDK records.
WORKFLOW_ITEM_IDENTITIES=(('steps','step_id'),('gateways','gateway_id'),
    ('transitions','transition_id'),('roles','assignment_id'),('artifacts','artifact_id'),
    ('handoffs','handoff_id'),('conditions','condition_id'))

def canonical_workflow_items(model):
    """Yield typed items by OWN identity, never a referenced step/artifact ID."""
    if type(model) is not WorkflowModel:raise TypeError('exact typed workflow required')
    seen=set()
    for collection,field in WORKFLOW_ITEM_IDENTITIES:
        for item in getattr(model,collection):
            identity=getattr(item,field)
            if identity in seen:raise ValueError('duplicate canonical workflow item identity')
            seen.add(identity)
            yield collection,identity,item

class Support(_StrictModel):
    observation_ids: SupportIds

class Step(_StrictModel):
    step_id: Nonempty; label: Nonempty; support: Support
    role_id: str | None = None
    kind: Literal["activity","start","end","rejection","call","return"]

class Gateway(_StrictModel):
    gateway_id: Nonempty
    kind: Literal["exclusive_split","exclusive_join","parallel_split","parallel_join","unsupported"]
    support: Support

class Condition(_StrictModel):
    condition_id: Nonempty; wording: Nonempty
    applicability: Literal["known","unknown"]; support: Support

class Transition(_StrictModel):
    transition_id: Nonempty; from_id: Nonempty; to_id: Nonempty
    support: Support; condition_id: str | None = None; rework: bool = False

class RoleAssignment(_StrictModel):
    assignment_id: Nonempty; step_id: Nonempty; role_id: Nonempty; support: Support

class Artifact(_StrictModel):
    artifact_id: Nonempty; label: Nonempty; support: Support

class Handoff(_StrictModel):
    handoff_id: Nonempty; from_step: Nonempty; to_step: Nonempty; artifact_id: Nonempty; support: Support

class WorkflowModel(_StrictModel):
    schema_version: Literal[1] = 1
    workflow_id: Nonempty; version: Annotated[int, Field(strict=True, ge=1)]
    workspace_id: UUID; process_id: Nonempty; scope: Nonempty
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    status: Literal["reported","confirmed"] = "reported"
    completeness: Literal["complete","partial","ambiguous","conflicted"]
    steps: tuple[Step, ...] = Field(min_length=1)
    gateways: tuple[Gateway, ...] = ()
    transitions: tuple[Transition, ...] = ()
    conditions: tuple[Condition, ...] = ()
    roles: tuple[RoleAssignment, ...] = ()
    artifacts: tuple[Artifact, ...] = ()
    handoffs: tuple[Handoff, ...] = ()
    finding_ids: tuple[str, ...] = ()
    coverage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_shape(self):
        def unique(values, label):
            ids = [getattr(v, label) for v in values]
            if len(ids) != len(set(ids)): raise ValueError(f"duplicate {label}")
            return set(ids)
        node_ids = unique(self.steps, "step_id") | unique(self.gateways, "gateway_id")
        if len(node_ids) != len(self.steps) + len(self.gateways): raise ValueError("duplicate node id")
        unique(self.transitions, "transition_id")
        unique(self.roles, "assignment_id")
        unique(self.handoffs, "handoff_id")
        condition_ids = unique(self.conditions, "condition_id")
        step_ids = {s.step_id for s in self.steps}; artifact_ids = unique(self.artifacts, "artifact_id")
        for t in self.transitions:
            if t.from_id not in node_ids or t.to_id not in node_ids: raise ValueError("dangling transition")
            if t.condition_id is not None and t.condition_id not in condition_ids: raise ValueError("unknown condition")
        for role in self.roles:
            if role.step_id not in step_ids: raise ValueError("unknown role step")
        for handoff in self.handoffs:
            if handoff.from_step not in step_ids or handoff.to_step not in step_ids or handoff.artifact_id not in artifact_ids: raise ValueError("dangling handoff")
        if any(ref.workspace_id != self.workspace_id for ref in self.source_refs): raise ValueError("source workspace mismatch")
        return self
