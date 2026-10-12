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
    def __init__(self, url: str): self.url = url

    def can_read(self, workspace_id: UUID, principal: UUID, source_id: UUID) -> bool:
        with psycopg.connect(self.url) as conn:
            return _has_authority_conn(conn,workspace_id,principal,'source-read:' + str(source_id))

    def current(self, workspace_id: UUID, source_id: UUID) -> SourceReceipt:
        with psycopg.connect(self.url) as conn:
            rows = conn.execute('''SELECT s.revision,s.status,d.status,b.text,m.text
              FROM oracle2.sources s JOIN oracle2.drafts d
               ON d.source_id=s.source_id AND d.workspace_id=s.workspace_id
              JOIN oracle2.source_blocks b ON b.source_id=s.source_id AND b.workspace_id=s.workspace_id AND b.kind='original'
              LEFT JOIN oracle2.source_blocks m ON m.source_id=s.source_id AND m.workspace_id=s.workspace_id AND m.kind='original-metadata'
              WHERE s.workspace_id=%s AND s.source_id=%s''',(workspace_id,source_id)).fetchall()
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
