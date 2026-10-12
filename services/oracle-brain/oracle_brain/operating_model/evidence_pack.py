"""Typed current-ledger documentary packing. SDK candidates never authorize facts."""
import json
from uuid import UUID
from typing import Literal
from pydantic import Field
from .contracts import StrictRecord,digest
from .retrieval import QueryPlan,build_pack
from .source_receipts import SourceRef,EvidenceRef

class EvidencePack(StrictRecord):
    schema_version:Literal[1]=1
    workspace_id:UUID
    artifact_id:UUID
    version:int=Field(strict=True,ge=1)
    artifact_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    plan:QueryPlan
    source_refs:tuple[SourceRef,...]
    contents:dict

    def recheck(self,ledger):
        payload=ledger.read(self.workspace_id,self.artifact_id,self.version)
        if digest(payload)!=self.artifact_hash or build_pack(payload,self.plan)!=self.contents:
            raise PermissionError('documentary pack changed before serving')
        return self

def build_authorized_pack(ledger,workspace_id,artifact_id,version,plan):
    payload=ledger.read(workspace_id,artifact_id,version)
    pack=EvidencePack(workspace_id=workspace_id,artifact_id=artifact_id,version=version,
        artifact_hash=digest(payload),plan=plan,source_refs=tuple(SourceRef.model_validate_json(json.dumps(r)) for r in payload['source_refs']),contents=build_pack(payload,plan))
    return pack.recheck(ledger)
