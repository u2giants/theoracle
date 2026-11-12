-- Repair plan D1: every source has a date. Idempotent.
-- date_origin names which rule won: admin | meeting_start | interview_answer |
-- document_text | file_metadata | upload_time (the never-NULL floor).
ALTER TABLE cmap.source ADD COLUMN IF NOT EXISTS date_origin text;
ALTER TABLE cmap.source DROP CONSTRAINT IF EXISTS source_date_origin_check;
ALTER TABLE cmap.source ADD CONSTRAINT source_date_origin_check
  CHECK (date_origin IS NULL OR date_origin IN
    ('admin','meeting_start','interview_answer','document_text','file_metadata','upload_time'));

-- Relations and mentions inherit their date through their source (D1).
-- One row per relation and one per mention; effective_date and date_origin
-- are the source's. label is rel_type (relation) or entity_type (mention);
-- text is the relation description or the mention's surface name.
CREATE OR REPLACE VIEW cmap.relation_dated AS
SELECT
  'relation'::text AS row_kind,
  r.id,
  r.chunk_id,
  c.source_id,
  s.effective_date,
  s.date_origin,
  r.rel_type AS label,
  r.description AS text
FROM cmap.relation r
JOIN cmap.chunk c ON c.id = r.chunk_id
JOIN cmap.source s ON s.id = c.source_id
UNION ALL
SELECT
  'mention'::text,
  m.id,
  m.chunk_id,
  c.source_id,
  s.effective_date,
  s.date_origin,
  m.entity_type,
  m.surface_name
FROM cmap.mention m
JOIN cmap.chunk c ON c.id = m.chunk_id
JOIN cmap.source s ON s.id = c.source_id;
