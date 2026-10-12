"""Deny every dependent artifact before scheduling recomputation."""
from uuid import UUID, uuid4
import psycopg
from psycopg.types.json import Jsonb
from oracle_brain.knowledge.authority import _lock,_has_authority_conn


def invalidate(database_url: str, *, workspace_id: UUID, upstream_kind: str,
               upstream_id: str, reason: str, event_id: UUID | None = None) -> int:
    if upstream_kind not in {'source','permission','identity','artifact','event_window','compiler','dependency'} or not upstream_id or not reason:
        raise ValueError('explicit invalidation identity/reason required')
    event_id = event_id or uuid4()
    with psycopg.connect(database_url) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'operating-lineage:{workspace_id}',))
        rows = conn.execute('''WITH RECURSIVE affected(artifact_id,version) AS (
          SELECT artifact_id,version FROM oracle2.artifact_dependencies
           WHERE workspace_id=%s AND upstream_kind=%s AND upstream_id=%s
          UNION
          SELECT d.artifact_id,d.version FROM oracle2.artifact_dependencies d JOIN affected a
           ON d.upstream_kind='artifact' AND d.upstream_id=a.artifact_id::text
            AND d.upstream_revision=a.version::text WHERE d.workspace_id=%s
        ) SELECT artifact_id,version FROM affected''',(workspace_id,upstream_kind,upstream_id,workspace_id)).fetchall()
        for artifact_id,version in rows:
            conn.execute('INSERT INTO oracle2.artifact_invalidations(workspace_id,artifact_id,version,reason,event_id) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(workspace_id,artifact_id,version,reason,event_id))
            conn.execute('INSERT INTO oracle2.operating_recompute_requests(request_id,workspace_id,artifact_id,version,event_id,reason) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(workspace_id,artifact_id,version,event_id) DO NOTHING',(uuid4(),workspace_id,artifact_id,version,event_id,reason))
    return len(rows)


def appoint_steward(ledger,*,workspace_id:UUID,source_id:UUID,steward_id:UUID):
    """Record an explicitly supplied responsible person with current rooted authority."""
    receipt=ledger.current_source(workspace_id,source_id)
    ledger.authorize_refs((receipt.ref,),workspace_id)
    scope='source-steward:'+str(source_id)
    event_id=uuid4()
    with psycopg.connect(ledger.url) as conn:
        _lock(conn,workspace_id)
        if not _has_authority_conn(conn,workspace_id,ledger.principal,'root') or not _has_authority_conn(conn,workspace_id,steward_id,scope):
            raise PermissionError('source steward requires current rooted authority')
        if ledger.current_source(workspace_id,source_id)!=receipt:raise PermissionError('source changed before stewardship')
        conn.execute('INSERT INTO oracle2.operating_source_stewards(event_id,workspace_id,source_id,steward_id,appointed_by,scope,source_revision) VALUES(%s,%s,%s,%s,%s,%s,%s)',(event_id,workspace_id,source_id,steward_id,ledger.principal,scope,receipt.ref.revision))
    return event_id


def recompute_one(ledger,*,workspace_id:UUID,rebuild,verify_projection):
    """Run an admitted deterministic rebuild callback; never infer a paid dispatch.

    Old artifacts remain denied. The callback must authorize current sources and
    produce a newly sealed artifact and projection before it returns a manifest.
    Unavailable source/permission/admission leaves an append-only blocked receipt.
    """
    with psycopg.connect(ledger.url) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'operating-recompute:{workspace_id}',))
        row=conn.execute("""SELECT r.request_id,r.artifact_id,r.version FROM oracle2.operating_recompute_requests r
          WHERE r.workspace_id=%s AND NOT EXISTS(SELECT 1 FROM oracle2.operating_recompute_events e WHERE e.request_id=r.request_id AND e.state='rebuilt')
          ORDER BY COALESCE((SELECT max(e.created_at) FROM oracle2.operating_recompute_events e WHERE e.request_id=r.request_id),r.created_at),r.request_id LIMIT 1""",(workspace_id,)).fetchone()
        if not row:return None
        request_id,artifact_id,version=row
        # Unknown technical failures propagate and are repaired; no false success.
        try:
            replacement=rebuild(artifact_id,version)
            if replacement.workspace_id!=workspace_id or (replacement.artifact_id==artifact_id and replacement.version<=version):raise ValueError('recompute must produce a new artifact version')
            payload_current=ledger.read(workspace_id,replacement.artifact_id,replacement.version)
            verify_projection(replacement,payload_current)
            state='rebuilt';payload={'artifact_id':str(replacement.artifact_id),'version':replacement.version,'content_hash':replacement.content_hash}
        except PermissionError:
            state='blocked';payload={'reason':'Current source, permission or rebuild admission unavailable; prior artifact remains denied'}
        conn.execute('INSERT INTO oracle2.operating_recompute_events(request_id,event_id,state,payload) VALUES(%s,%s,%s,%s)',(request_id,uuid4(),state,Jsonb(payload)))
    return {'request_id':str(request_id),'state':state,**payload}
