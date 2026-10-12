"""Retained authority primitives, with exact source visibility rather than workspace-only access."""
import hashlib
from uuid import UUID
import psycopg
from oracle_brain.knowledge.authority import _lock, _has_authority_conn
from oracle_brain.ingest.originals import ReadingProvenance
from .source_receipts import SourceRef, SourceReceipt


def require_review(connection, workspace_id: UUID, actor_id: UUID, scope: str):
    _lock(connection, workspace_id)
    if not _has_authority_conn(connection, workspace_id, actor_id, 'finding-review:' + scope):
        raise PermissionError('current owner-rooted scoped finding review authority required')

class PostgresSources:
    def __init__(self, url: str, *, source_binding=None, synthetic: bool=False):
        from oracle_brain.operating_model.source_binding import SourceRoleBinding
        if source_binding is not None and not isinstance(source_binding,SourceRoleBinding):
            raise PermissionError('fixed source-role binding required')
        self.url,self.source_binding,self.synthetic = url,source_binding,synthetic
        with psycopg.connect(url) as conn:self._check(conn)

    def _check(self, conn):
        if self.source_binding is not None:
            self.source_binding.check(conn)
            return
        params=conn.info.get_parameters()
        if self.synthetic is not True or params.get('host') not in {'127.0.0.1','localhost','::1'} or not (params.get('dbname','').startswith('oracle_operating_model_test') or params.get('dbname') in {'oracle2','hosting_permissions_test'}):
            raise PermissionError('externally issued source-role binding required')
        roles=conn.execute("""WITH RECURSIVE memberships(oid) AS (
          SELECT oid FROM pg_roles WHERE rolname=SESSION_USER
          UNION SELECT m.roleid FROM pg_auth_members m JOIN memberships x ON m.member=x.oid)
          SELECT rolname FROM pg_roles WHERE oid IN (SELECT oid FROM memberships)
          AND rolname IN ('oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor')""").fetchall()
        if roles:raise PermissionError('registered source role requires external binding')

    def can_read(self, workspace_id: UUID, principal: UUID, source_id: UUID) -> bool:
        with psycopg.connect(self.url) as conn:
            self._check(conn)
            allowed=_has_authority_conn(conn,workspace_id,principal,'source-read:' + str(source_id))
            self._check(conn)
            return allowed

    def current(self, workspace_id: UUID, source_id: UUID) -> SourceReceipt:
        with psycopg.connect(self.url) as conn:
            self._check(conn)
            rows = conn.execute('''SELECT s.revision,s.status,d.status,b.text,m.text
              FROM oracle2.sources s JOIN oracle2.drafts d
               ON d.source_id=s.source_id AND d.workspace_id=s.workspace_id
              JOIN oracle2.source_blocks b ON b.source_id=s.source_id AND b.workspace_id=s.workspace_id AND b.kind='original'
              LEFT JOIN oracle2.source_blocks m ON m.source_id=s.source_id AND m.workspace_id=s.workspace_id AND m.kind='original-metadata'
              WHERE s.workspace_id=%s AND s.source_id=%s''',(workspace_id,source_id)).fetchall()
            self._check(conn)
        if len(rows)!=1 or rows[0][1] not in {'draft','confirmed'} or rows[0][2]!='confirmed':
            raise PermissionError('current qualified source unavailable or withdrawn')
        revision, _, _, reading, metadata = rows[0]
        if not metadata:
            raise PermissionError('source lacks immutable original-reading provenance')
        provenance = ReadingProvenance.model_validate_json(metadata)
        reading_hash = hashlib.sha256(reading.encode()).hexdigest()
        if reading_hash != provenance.content_hash:
            raise ValueError('current original reading seal mismatch')
        ref = SourceRef(workspace_id=workspace_id,source_id=source_id,revision=revision,
                        original_sha256=provenance.original_hash,reading_sha256=reading_hash,
                        parser_id=provenance.parser_identity)
        return SourceReceipt(ref=ref,reading=reading,display_revision=f'r{revision}')
