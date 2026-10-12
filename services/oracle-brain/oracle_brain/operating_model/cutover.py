"""Atomic compatible selector switch, current-source denial on forward and rollback."""
import json
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from .release_manifest import ReleaseManifest
from .contracts import digest


def watermark(connection,workspace_id:UUID):
    return connection.execute('SELECT COALESCE(max(sequence),0) FROM oracle2.operating_model_change_log WHERE workspace_id=%s',(workspace_id,)).fetchone()[0]

def activate(database_url:str,manifest:ReleaseManifest,*,expected_generation:int,ledger,verify_projection,
             runtime_digest:str,synthetic:bool,reviewed_release_hashes:frozenset[str]):
    seal=manifest.content_hash()
    if seal not in reviewed_release_hashes:raise PermissionError('exact release input has no independent admission')
    if manifest.runtime_digest!=runtime_digest:raise PermissionError('runtime compatibility mismatch')
    if synthetic!=(manifest.acceptance_state=='synthetic'):raise PermissionError('synthetic/hosted selector context mismatch')
    if not synthetic and manifest.acceptance_state!='admitted_hosted':raise PermissionError('hosted serving requires accepted restricted restore/live gate')
    payload=ledger.read(manifest.workspace_id,manifest.artifact_id,manifest.artifact_version)
    if digest(payload)!=manifest.artifact_content_hash:raise ValueError('release artifact seal mismatch')
    if payload['source_refs']!=[r.model_dump(mode='json') for r in manifest.source_refs]:raise ValueError('release source population mismatch')
    verify_projection(manifest,payload)
    with psycopg.connect(database_url) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'operating-selector:{manifest.workspace_id}',))
        current=conn.execute('SELECT generation FROM oracle2.operating_release_selectors WHERE workspace_id=%s FOR UPDATE',(manifest.workspace_id,)).fetchone()
        generation=current[0] if current else 0
        if generation!=expected_generation:raise ValueError('serving selector moved concurrently')
        # A newer source/authority event requires a replayed and newly reviewed manifest.
        # No source writer is frozen while a projection is built.
        if watermark(conn,manifest.workspace_id)!=manifest.ledger_watermark:raise ValueError('new ledger revisions require replay before switch')
        if ledger.read(manifest.workspace_id,manifest.artifact_id,manifest.artifact_version)!=payload:raise PermissionError('current source/access changed before selector switch')
        prior=conn.execute('SELECT content_hash,payload FROM oracle2.operating_release_manifests WHERE workspace_id=%s AND release_id=%s',(manifest.workspace_id,manifest.release_id)).fetchone()
        if prior and prior!=(seal,manifest.model_dump(mode='json')):raise ValueError('immutable release tampering')
        conn.execute('INSERT INTO oracle2.operating_release_manifests(workspace_id,release_id,content_hash,payload) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(manifest.workspace_id,manifest.release_id,seal,Jsonb(manifest.model_dump(mode='json'))))
        conn.execute('INSERT INTO oracle2.operating_release_selectors(workspace_id,release_id,generation,watermark) VALUES(%s,%s,%s,%s) ON CONFLICT(workspace_id) DO UPDATE SET release_id=EXCLUDED.release_id,generation=EXCLUDED.generation,watermark=EXCLUDED.watermark',(manifest.workspace_id,manifest.release_id,generation+1,manifest.ledger_watermark))
    return generation+1


def selected(database_url:str,workspace_id:UUID) -> ReleaseManifest:
    with psycopg.connect(database_url) as conn:
        current_watermark=watermark(conn,workspace_id)
        row=conn.execute('SELECT m.payload,m.content_hash FROM oracle2.operating_release_selectors s JOIN oracle2.operating_release_manifests m ON m.workspace_id=s.workspace_id AND m.release_id=s.release_id WHERE s.workspace_id=%s',(workspace_id,)).fetchone()
    if row is None:raise PermissionError('no admitted operating-model serving selector')
    manifest=ReleaseManifest.model_validate_json(json.dumps(row[0]))
    if current_watermark!=manifest.ledger_watermark:raise PermissionError('new source/authority revisions require replay; stale selector cannot serve')
    if manifest.content_hash()!=row[1]:raise ValueError('release manifest seal changed')
    return manifest
