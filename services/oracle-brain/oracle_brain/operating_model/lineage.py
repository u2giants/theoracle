"""Deny every dependent artifact before scheduling recomputation."""
from uuid import UUID, uuid4
import psycopg


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
    return len(rows)
