-- GAP-12: topical lull-question selection.
-- Rerun safe. The vector is a search aid for gap questions, never claim evidence.
ALTER TABLE gaps
  ADD COLUMN IF NOT EXISTS embedding vector(1536);
ALTER TABLE gaps
  ADD COLUMN IF NOT EXISTS embedding_model varchar(255);
ALTER TABLE gaps
  ADD COLUMN IF NOT EXISTS embedding_source_hash varchar(64);

INSERT INTO settings (key, value, description)
VALUES (
  'lull_gap_minimum_relevance',
  '0.35'::jsonb,
  'Minimum cosine similarity between recent channel messages and an eligible open gap.'
)
ON CONFLICT (key) DO NOTHING;

COMMENT ON COLUMN gaps.embedding IS
  'Embedding of question_to_ask plus why_it_matters for topical lull selection only; not claim evidence.';
