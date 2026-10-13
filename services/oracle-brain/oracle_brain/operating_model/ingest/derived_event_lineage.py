"""Verify externally admitted original-export to derived-event lineage.

Nothing here authenticates captures, issues authority, registers a SourceRef or
loads an original. Runtime trust must come from an independent current resolver,
never a request body or these diagnostic hashes. The default Ledger has none.
The CSV is an internal machine representation, never a spreadsheet presentation;
any future spreadsheet view must escape a separate presentation copy losslessly.
"""
from datetime import datetime,timedelta
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field
from ..contracts import StrictRecord,digest
from ..source_receipts import SourceRef
from .minimized_observations import PROCESS,prepare_csv,sha

HASH=r'^[0-9a-f]{64}$'

class EventIntakeAdmission(StrictRecord):
    purpose: Literal['derived-point-observation-intake']
    workspace_id: UUID
    actor_id: UUID
    minimized_ref: SourceRef
    original_references_ref: SourceRef
    documentary_refs: tuple[SourceRef,...]=Field(min_length=1)
    source_process: Literal[PROCESS]
    capture_authenticity: Literal['authenticated-original-captures']
    capture_receipt_hash: str=Field(pattern=HASH)
    documentary_mapping_receipt_hash: str=Field(pattern=HASH)
    mapping_hash: str=Field(pattern=HASH)
    permission_digest: str=Field(pattern=HASH)
    issuer_actor: UUID
    reviewer_actor: UUID
    observed_at: AwareDatetime
    expires_at: AwareDatetime

class TrustedEventIntake(StrictRecord):
    """Only the trusted runtime resolver supplies this out-of-band context."""
    admission: EventIntakeAdmission
    trusted_admission_hash: str=Field(pattern=HASH)
    current_capture_receipt_hash: str=Field(pattern=HASH)
    current_mapping_receipt_hash: str=Field(pattern=HASH)
    current_permission_digest: str=Field(pattern=HASH)
    checked_at: AwareDatetime

class EventDerivation(StrictRecord):
    kind: Literal['minimized-clickup-observations-to-point-csv-v1']
    minimized_ref: SourceRef
    original_references_ref: SourceRef
    documentary_refs: tuple[SourceRef,...]=Field(min_length=1)
    minimized_export_sha256: str=Field(pattern=HASH)
    original_references_sha256: str=Field(pattern=HASH)
    derived_csv_sha256: str=Field(pattern=HASH)
    admission_hash: str=Field(pattern=HASH)

def admitted_refs(trust,*,workspace_id,actor_id,mapping,permission_digest,now):
    if not isinstance(trust,TrustedEventIntake):
        raise PermissionError('independently authenticated capture and documentary mapping required')
    proof=trust.admission
    if (digest(proof.model_dump(mode='json'))!=trust.trusted_admission_hash
            or proof.issuer_actor==proof.reviewer_actor
            or proof.workspace_id!=workspace_id or proof.actor_id!=actor_id):
        raise PermissionError('independent current event intake admission required')
    if (now.tzinfo is None or not timedelta(0)<=now-trust.checked_at<=timedelta(seconds=15)
            or proof.observed_at>trust.checked_at or proof.expires_at<=proof.observed_at
            or now>=proof.expires_at):
        raise PermissionError('fresh event intake context required')
    if (proof.capture_receipt_hash!=trust.current_capture_receipt_hash
            or proof.documentary_mapping_receipt_hash!=trust.current_mapping_receipt_hash
            or proof.permission_digest!=permission_digest
            or permission_digest!=trust.current_permission_digest
            or proof.mapping_hash!=digest(mapping.model_dump(mode='json'))):
        raise PermissionError('capture, mapping or permission binding changed')
    required={'event_id':'event_id','case_id':'case_id','activity_id':'activity',
              'timestamp':'timestamp','lifecycle':'lifecycle','status':'status'}
    if any(mapping.columns.get(key)!=value for key,value in required.items()):
        raise PermissionError('explicit point/unknown documentary mapping required')
    refs=(proof.minimized_ref,proof.original_references_ref)+proof.documentary_refs
    if (any(ref.workspace_id!=workspace_id for ref in refs)
            or len({ref.source_id for ref in refs})!=len(refs)):
        raise PermissionError('distinct current export and documentary originals required')
    return refs

def derive_from_receipts(trust,receipts):
    """Call only after externally trusted admission and current source access."""
    proof=trust.admission
    originals=[]
    for ref in (proof.minimized_ref,proof.original_references_ref):
        receipt=receipts[str(ref.source_id)]
        if receipt.ref!=ref:raise PermissionError('original export revision changed')
        raw=receipt.reading.encode('utf-8')
        if sha(raw)!=ref.original_sha256:
            raise ValueError('derived input must be the exact admitted original export')
        originals.append(raw)
    data,_=prepare_csv(*originals,minimized_sha256=proof.minimized_ref.original_sha256,
                       reference_sha256=proof.original_references_ref.original_sha256)
    derivation=EventDerivation(kind='minimized-clickup-observations-to-point-csv-v1',
        minimized_ref=proof.minimized_ref,original_references_ref=proof.original_references_ref,
        documentary_refs=proof.documentary_refs,minimized_export_sha256=sha(originals[0]),
        original_references_sha256=sha(originals[1]),derived_csv_sha256=sha(data),
        admission_hash=trust.trusted_admission_hash)
    return data,derivation
