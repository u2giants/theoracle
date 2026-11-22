-- Google Colab pull-based batch lease & submit tables (#664 Step 3.1). Idempotent.
-- Enforces <= 30-minute lease ceiling at the database level (standing 30-minute rule)
-- and guarantees at most one active lease per chunk via partial unique index.

ALTER TABLE cmap.source ADD COLUMN IF NOT EXISTS colab_offload boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS source_colab_offload_idx ON cmap.source (id)
  WHERE colab_offload = true;

CREATE TABLE IF NOT EXISTS cmap.colab_lease (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  worker_id text NOT NULL,
  prompt_hash text NOT NULL,
  leased_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL CHECK (
    expires_at > leased_at AND expires_at <= leased_at + interval '30 minutes'
  ),
  state text NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'completed', 'expired')),
  model_tag text,
  chunk_count int NOT NULL CHECK (chunk_count >= 0),
  completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS colab_lease_state_expires_idx
  ON cmap.colab_lease (state, expires_at);

CREATE TABLE IF NOT EXISTS cmap.colab_lease_item (
  lease_id uuid NOT NULL REFERENCES cmap.colab_lease(id) ON DELETE CASCADE,
  chunk_id uuid NOT NULL REFERENCES cmap.chunk(id) ON DELETE CASCADE,
  source_id uuid NOT NULL REFERENCES cmap.source(id) ON DELETE CASCADE,
  state text NOT NULL DEFAULT 'leased' CHECK (state IN ('leased', 'accepted', 'failed')),
  PRIMARY KEY (lease_id, chunk_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS colab_lease_one_active_chunk_idx
  ON cmap.colab_lease_item (chunk_id)
  WHERE state = 'leased';

CREATE INDEX IF NOT EXISTS colab_lease_item_chunk_id_idx
  ON cmap.colab_lease_item (chunk_id);

CREATE INDEX IF NOT EXISTS colab_lease_item_source_id_idx
  ON cmap.colab_lease_item (source_id);

