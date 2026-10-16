"""Versioned deterministic summaries preserve the complete bounded documentary pack."""
import json
from uuid import UUID
from .evidence_pack import EvidencePack,build_authorized_pack
from .retrieval import QueryPlan
from .contracts import StrictRecord,digest

class DocumentarySummary(StrictRecord):
    pack:EvidencePack
    summary_hash:str

    @classmethod
    def from_pack(cls,pack):
        return cls(pack=pack,summary_hash=digest(pack.model_dump(mode='json')))

    def recheck(self,ledger,*,qualification_guard=None):
        if self.summary_hash!=digest(self.pack.model_dump(mode='json')):raise ValueError('summary seal mismatch')
        from .assembly_qualification import read_documentary_artifact
        read_documentary_artifact(ledger,self.pack.workspace_id,self.pack.artifact_id,self.pack.version,qualification_guard=qualification_guard)
        self.pack.recheck(ledger)
        return self

def summarize_from_ledger(ledger,workspace_id,artifact_id,version,plan,*,qualification_guard=None):
    from .assembly_qualification import read_documentary_artifact
    read_documentary_artifact(ledger,workspace_id,artifact_id,version,qualification_guard=qualification_guard)
    return DocumentarySummary.from_pack(build_authorized_pack(ledger,workspace_id,artifact_id,version,plan))

def persist_summary(ledger,summary,*,summary_id:UUID,summary_version:int,permission_digest:str,compiler_digest:str,qualification_guard=None):
    summary.recheck(ledger,qualification_guard=qualification_guard)
    p=summary.pack
    from .assembly_qualification import read_documentary_artifact
    parent,_=read_documentary_artifact(ledger,p.workspace_id,p.artifact_id,p.version,qualification_guard=qualification_guard,with_manifest=True)
    kind='processing_summary_v1' if parent is not None and parent.kind=='processing_qualified_model_v1' else 'summary'
    return ledger.persist(workspace_id=p.workspace_id,artifact_id=summary_id,version=summary_version,
        kind=kind,payload={'source_refs':[r.model_dump(mode='json') for r in p.source_refs],'summary':summary.model_dump(mode='json')},
        refs=p.source_refs,permission_digest=permission_digest,compiler_digest=compiler_digest,
        dependencies=(('artifact',str(p.artifact_id),str(p.version)),))

def serve_summary(ledger,workspace_id,summary_id,summary_version,*,qualification_guard=None):
    from .assembly_qualification import read_documentary_artifact
    payload=read_documentary_artifact(ledger,workspace_id,summary_id,summary_version,qualification_guard=qualification_guard)
    summary=DocumentarySummary.model_validate_json(json.dumps(payload['summary']))
    if summary.pack.workspace_id!=workspace_id:raise PermissionError('cross-workspace summary')
    return summary.recheck(ledger,qualification_guard=qualification_guard)
