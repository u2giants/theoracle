-- R12 — provider cache metadata
--
-- Stores provider-specific metadata alongside provider_cached_content so
-- lifecycle sweepers can clean up auxiliary resources such as temporary
-- GCS objects used to build Vertex file-backed caches.

ALTER TABLE provider_cached_content
  ADD COLUMN IF NOT EXISTS provider_metadata_json jsonb;
