-- 65_document_context_and_domain_hints.sql
--
-- Adds optional uploader-provided context to documents:
--   * context      — a free-text description of what the document is, fed into
--                    the extraction prompt and the image vision prompt to
--                    disambiguate the content.
--   * domain_hints — an array of knowledge_top_domains.id values the uploader
--                    suggests are likely relevant. Used as a PRIOR in the
--                    extraction prompt only; per-claim domain validation
--                    remains authoritative and is never overridden.
--
-- Both are nullable and non-breaking. Hand-written + idempotent.

ALTER TABLE documents ADD COLUMN IF NOT EXISTS context text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS domain_hints jsonb;
