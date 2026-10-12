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

    def recheck(self,ledger):
        if self.summary_hash!=digest(self.pack.model_dump(mode='json')):raise ValueError('summary seal mismatch')
        self.pack.recheck(ledger)
        return self

def summarize_from_ledger(ledger,workspace_id,artifact_id,version,plan):
    return DocumentarySummary.from_pack(build_authorized_pack(ledger,workspace_id,artifact_id,version,plan))

def persist_summary(ledger,summary,*,summary_id:UUID,summary_version:int,permission_digest:str,compiler_digest:str):
    summary.recheck(ledger)
    p=summary.pack
    return ledger.persist(workspace_id=p.workspace_id,artifact_id=summary_id,version=summary_version,
        kind='summary',payload={'source_refs':[r.model_dump(mode='json') for r in p.source_refs],'summary':summary.model_dump(mode='json')},
        refs=p.source_refs,permission_digest=permission_digest,compiler_digest=compiler_digest,
        dependencies=(('artifact',str(p.artifact_id),str(p.version)),))

def serve_summary(ledger,workspace_id,summary_id,summary_version):
    payload=ledger.read(workspace_id,summary_id,summary_version)
    summary=DocumentarySummary.model_validate_json(json.dumps(payload['summary']))
    if summary.pack.workspace_id!=workspace_id:raise PermissionError('cross-workspace summary')
    return summary.recheck(ledger)
