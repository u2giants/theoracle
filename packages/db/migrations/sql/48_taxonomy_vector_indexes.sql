-- R3.5 — Vector indexes for the taxonomy layer.
--
-- knowledge_sub_topics is empty on install (sub-topics activate only after
-- enough corpus accumulates per docs/oracle/07-knowledge-segmentation.md
-- "Layer 2 — activation threshold"). Building an HNSW index on the empty
-- table costs ~nothing and avoids us having to remember to add it later
-- when the re-evaluation worker first writes sub-topics.
--
-- Idempotent: CREATE INDEX IF NOT EXISTS.
--
-- Distinct from 99_vector_indexes.sql, which is the larger / opt-in index
-- for claims.embedding and document_chunks.embedding. Those are gated by
-- ORACLE_RUN_VECTOR_INDEXES=1 because they're expensive on populated tables.

CREATE INDEX IF NOT EXISTS knowledge_sub_topics_centroid_hnsw_idx
  ON knowledge_sub_topics
  USING hnsw (centroid vector_cosine_ops);
