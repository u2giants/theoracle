-- Pilot journey tables. Applied to local test database only in S03.
CREATE TABLE IF NOT EXISTS oracle2.sources (
  source_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  uploaded_by uuid NOT NULL,
  filename text NOT NULL,
  content_type text NOT NULL,
  status text NOT NULL CHECK (status IN ('processing','draft','confirmed','error')),
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  revision integer NOT NULL DEFAULT 1 CHECK (revision > 0)
);
CREATE TABLE IF NOT EXISTS oracle2.source_blocks (
  block_id uuid PRIMARY KEY,
  source_id uuid NOT NULL REFERENCES oracle2.sources(source_id),
  workspace_id uuid NOT NULL,
  block_index integer NOT NULL CHECK (block_index >= 0),
  kind text NOT NULL,
  text text NOT NULL,
  span_start integer NOT NULL CHECK (span_start >= 0),
  span_end integer NOT NULL CHECK (span_end > 0),
  CHECK (span_end > span_start)
);
CREATE INDEX IF NOT EXISTS source_blocks_source ON oracle2.source_blocks(source_id);
CREATE TABLE IF NOT EXISTS oracle2.drafts (
  draft_id uuid PRIMARY KEY,
  source_id uuid NOT NULL REFERENCES oracle2.sources(source_id),
  workspace_id uuid NOT NULL,
  created_by uuid NOT NULL,
  process_name text NOT NULL,
  connections jsonb NOT NULL DEFAULT '[]',
  status text NOT NULL CHECK (status IN ('draft','confirmed','withdrawn')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS oracle2.reviews (
  review_id uuid PRIMARY KEY,
  draft_id uuid NOT NULL REFERENCES oracle2.drafts(draft_id),
  workspace_id uuid NOT NULL,
  actor_id uuid NOT NULL,
  action text NOT NULL CHECK (action IN ('correct','confirm','reject')),
  payload jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS oracle2.runs (
  run_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  actor_id uuid NOT NULL,
  source_id uuid NOT NULL REFERENCES oracle2.sources(source_id),
  draft_id uuid REFERENCES oracle2.drafts(draft_id),
  question text NOT NULL,
  status text NOT NULL CHECK (status IN ('pending','processing','completed','cancelled','error')),
  answer jsonb,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
-- Review concurrency guard: one active confirmation per draft at a time.
CREATE UNIQUE INDEX IF NOT EXISTS reviews_one_active_confirm
  ON oracle2.reviews(draft_id)
  WHERE action = 'confirm';
