-- Bilingual claim layer (china_imp.md) — full-text search indexes on the
-- translated claim summaries, mirroring 51_claims_fts_index.sql for claims.
--
-- searchWithRetrievalPlan() in packages/ai/src/retrieval.ts ranks claims with a
-- hybrid of pgvector + tsvector. When a reader's locale has a row in
-- claim_translations, retrieval reads COALESCE(ct.summary, c.summary) and runs
-- ts_rank against it. The FTS regconfig is chosen by locale:
--   * 'english' for English readers
--   * 'simple'  for Chinese (zh-CN) readers — Postgres's English/stemmed
--     configs cannot tokenize Chinese (no inter-word spaces), so 'simple' is
--     used and the vector half of the RRF carries ranking quality. (A future
--     upgrade could install a Chinese segmenter like zhparser/pg_jieba.)
--
-- We index both regconfigs so whichever a locale uses is covered. Without these,
-- the tsvector clause sequentially scans claim_translations as the corpus grows.
--
-- Idempotent: CREATE INDEX IF NOT EXISTS.

CREATE INDEX IF NOT EXISTS claim_translations_summary_fts_english_idx
  ON claim_translations
  USING GIN (to_tsvector('english', summary));

CREATE INDEX IF NOT EXISTS claim_translations_summary_fts_simple_idx
  ON claim_translations
  USING GIN (to_tsvector('simple', summary));
