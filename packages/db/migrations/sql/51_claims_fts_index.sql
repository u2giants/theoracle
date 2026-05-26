-- P1 #3 — Full-text search index on claims.summary for hybrid RRF retrieval.
--
-- searchWithRetrievalPlan() in packages/ai/src/retrieval.ts runs both:
--   1. pgvector cosine ranking (claims.embedding <=> query_vec)
--   2. tsvector rank (to_tsvector('english', summary) @@ plainto_tsquery(...))
--
-- Without this GIN index, the tsvector clause does a sequential scan over all
-- approved claims, which is fine today (~few hundred claims) but degrades as
-- the corpus grows. The index costs ~0 on an empty / small table.
--
-- Idempotent: CREATE INDEX IF NOT EXISTS.

CREATE INDEX IF NOT EXISTS claims_summary_fts_idx
  ON claims
  USING GIN (to_tsvector('english', summary));
