-- Repair plan A2: reading that failed is retried and never shows as "read".
-- read_state now follows the whole chain: queued -> reading -> extracting ->
-- read | partial (some passages failed) | failed. Idempotent.
ALTER TABLE cmap.source DROP CONSTRAINT IF EXISTS source_read_state_check;
ALTER TABLE cmap.source ADD CONSTRAINT source_read_state_check
  CHECK (read_state IN ('queued','reading','extracting','read','partial','failed'));

-- A passage whose model call failed after retries is recorded here with the
-- error text (prompt_hash 'failed'); the row is removed when it later succeeds.
ALTER TABLE cmap.extraction ADD COLUMN IF NOT EXISTS error text;
CREATE INDEX IF NOT EXISTS extraction_error_idx ON cmap.extraction (chunk_id)
  WHERE error IS NOT NULL;
