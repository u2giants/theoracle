"""Authorized event exports stay separate from documentary source extraction."""
import base64,hashlib
from uuid import UUID
import psycopg
from oracle_brain.knowledge.authority import _lock,_has_authority_conn
from .operational_export import parse_export,Mapping
from ..contracts import digest


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
