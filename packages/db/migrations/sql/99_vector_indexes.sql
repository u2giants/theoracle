-- Spec 6.9 — HNSW vector indexes.
-- Run ONCE there is enough data to justify vector indexing. Building an HNSW
-- index on an empty table is wasteful and the index quality is meaningless
-- without representative data.
--
-- To apply, set ORACLE_RUN_VECTOR_INDEXES=1 when running the migrate script.
-- The runner detects this flag and only then evaluates this file.

CREATE INDEX IF NOT EXISTS claims_embedding_hnsw_idx
  ON claims
  USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw_idx
  ON document_chunks
  USING hnsw (embedding vector_cosine_ops);

-- Bilingual claim layer (china_imp.md): the per-language rendering of a claim
-- carries its own embedding, searched the same way as claims.embedding. Mirror
-- the claims HNSW index so localized retrieval has the same ANN coverage.
CREATE INDEX IF NOT EXISTS claim_translations_embedding_hnsw_idx
  ON claim_translations
  USING hnsw (embedding vector_cosine_ops);
