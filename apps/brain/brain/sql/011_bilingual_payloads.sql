-- Retain both languages from step 1.2 until the translation sidecar consumes them.
-- Existing canonical columns remain English. These payloads inherit table access.
ALTER TABLE cmap.entity ADD COLUMN IF NOT EXISTS describe_payload jsonb;
ALTER TABLE cmap.community ADD COLUMN IF NOT EXISTS report_payload jsonb;
