-- 043: Source authority tier, role (ideal_policy vs observed_practice vs reference),
-- and weighted evidence scoring (#607/#664 follow-up).

ALTER TABLE cmap.source
    ADD COLUMN IF NOT EXISTS source_role text NOT NULL DEFAULT 'observed_practice';

ALTER TABLE cmap.source
    ADD COLUMN IF NOT EXISTS authority_tier text NOT NULL DEFAULT 'standard';

ALTER TABLE cmap.source
    DROP CONSTRAINT IF EXISTS source_source_role_check;
ALTER TABLE cmap.source
    ADD CONSTRAINT source_source_role_check
    CHECK (source_role IN ('ideal_policy', 'observed_practice', 'reference'));

ALTER TABLE cmap.source
    DROP CONSTRAINT IF EXISTS source_authority_tier_check;
ALTER TABLE cmap.source
    ADD CONSTRAINT source_authority_tier_check
    CHECK (authority_tier IN ('authoritative', 'standard'));

CREATE INDEX IF NOT EXISTS source_authority_role_idx
    ON cmap.source (authority_tier, source_role)
    WHERE map_eligible = true;
