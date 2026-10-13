"""Authorized event exports stay separate from documentary source extraction."""
import base64,hashlib
from uuid import UUID
import psycopg
from oracle_brain.knowledge.authority import _lock,_has_authority_conn
from .operational_export import parse_export,Mapping
from ..contracts import digest
from .derived_event_lineage import admitted_refs,derive_from_receipts


def import_events(ledger,receipt,data:bytes,*,format,mapping:Mapping,window_start,window_end,permission_digest,compiler_digest):
    if receipt.ref.original_sha256!=hashlib.sha256(data).hexdigest():raise ValueError('export bytes differ from authoritative original')
    with psycopg.connect(ledger.url) as connection:
        _lock(connection,receipt.ref.workspace_id)
        if not _has_authority_conn(connection,receipt.ref.workspace_id,ledger.principal,'event-import:'+mapping.scope):raise PermissionError('current event-import scope required')
    log,quarantine=parse_export(data,format,receipt.ref.workspace_id,mapping,window_start,window_end)
    payload={'source_refs':[receipt.ref.model_dump(mode='json')],'event_import':log.model_dump(mode='json'),
      'format':format,'mapping':mapping.model_dump(mode='json'),'raw_export_base64':base64.b64encode(data).decode(),
      'quarantine':list(quarantine),'actual_data_acceptance':'unavailable'}
    manifest=ledger.persist(workspace_id=receipt.ref.workspace_id,artifact_id=log.import_id,version=1,
      kind='event_import',payload=payload,refs=(receipt.ref,),permission_digest=permission_digest,
      compiler_digest=compiler_digest,dependencies=(('event_window',str(log.import_id),digest({'start':log.window_start.isoformat(),'end':log.window_end.isoformat()})),))
    return manifest,log

def import_derived_events(ledger,*,mapping:Mapping,window_start,window_end,permission_digest,compiler_digest):
    """No caller CSV/SourceRef/admission: resolve existing independent runtime trust."""
    trust=ledger.resolve_event_intake()
    refs=admitted_refs(trust,workspace_id=trust.admission.workspace_id,actor_id=ledger.principal,
        mapping=mapping,permission_digest=permission_digest,now=ledger.clock())
    with psycopg.connect(ledger.url) as connection:
        _lock(connection,trust.admission.workspace_id)
        if not _has_authority_conn(connection,trust.admission.workspace_id,ledger.principal,'event-import:'+mapping.scope):
            raise PermissionError('current event-import scope required')
    # Admission and actual current scope precede original reading/conversion.
    receipts=ledger.authorize_refs(refs,trust.admission.workspace_id)
    data,derivation=derive_from_receipts(trust,receipts)
    log,quarantine=parse_export(data,'csv',trust.admission.workspace_id,mapping,window_start,window_end)
    if quarantine or len(log.events)!=816 or any(event.status!='unknown' or event.lifecycle!='point' for event in log.events):
        raise PermissionError('complete explicitly mapped point observation population required')
    payload={'source_refs':[ref.model_dump(mode='json') for ref in refs],
        'event_import':log.model_dump(mode='json'),'format':'csv','mapping':mapping.model_dump(mode='json'),
        'raw_export_base64':base64.b64encode(data).decode(),'event_derivation':derivation.model_dump(mode='json'),
        'input_bytes_kind':'derived-point-observation-csv',
        'quarantine':list(quarantine),'actual_data_acceptance':'unavailable'}
    manifest=ledger.persist(workspace_id=trust.admission.workspace_id,artifact_id=log.import_id,version=1,
        kind='event_import',payload=payload,refs=refs,permission_digest=permission_digest,compiler_digest=compiler_digest,
        dependencies=(('event_window',str(log.import_id),digest({'start':log.window_start.isoformat(),'end':log.window_end.isoformat()})),
                      ('dependency','authenticated-event-intake',trust.trusted_admission_hash)))
    return manifest,log
