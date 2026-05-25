-- R7 — Partial UNIQUE index on claims.candidate_hash.
--
-- The candidate_hash column is nullable so historic claims (promoted
-- before R7's executor learned to compute it) don't violate any new
-- constraint. The partial UNIQUE prevents two distinct claims from
-- being inserted with the SAME non-null hash, which is exactly the
-- "historical duplicate detection across cron runs" guarantee R7 needs.
--
-- Idempotent.

CREATE UNIQUE INDEX IF NOT EXISTS claims_candidate_hash_unique
  ON claims (candidate_hash)
  WHERE candidate_hash IS NOT NULL;
