CREATE SCHEMA IF NOT EXISTS cmap;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS cmap.source (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL CHECK (kind IN ('pdf','docx','xlsx','pptx','text','image','transcript')),
  title text NOT NULL,
  original_filename text,
  storage_path text NOT NULL,          -- bucket company_documents, key cmap/<id>/<filename>
  sha256 text NOT NULL UNIQUE,
  bytes bigint NOT NULL,
  department_hint text,                -- optional, from folder name on bulk import
  effective_date date,                 -- unknown stays NULL; never default to upload date
  uploaded_by uuid,                    -- auth.users id
  created_at timestamptz NOT NULL DEFAULT now(),
  read_state text NOT NULL DEFAULT 'queued' CHECK (read_state IN ('queued','read','failed')),
  read_error text
);

CREATE TABLE IF NOT EXISTS cmap.chunk (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES cmap.source(id) ON DELETE CASCADE,
  ordinal int NOT NULL,
  locator jsonb NOT NULL,              -- {"page":3} | {"sheet":"PO","range":"A2:F40"} | {"slide":4} | {"turn":112,"speaker":"Ilona","t0":"00:14:02"} | {"image":true}
  text text NOT NULL,
  token_count int NOT NULL,
  passage_kind text,                   -- step 4 label
  embedding vector(1024),
  UNIQUE (source_id, ordinal)
);
CREATE INDEX IF NOT EXISTS chunk_embedding_idx ON cmap.chunk USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS cmap.extraction (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_id uuid NOT NULL REFERENCES cmap.chunk(id) ON DELETE CASCADE,
  stage text NOT NULL CHECK (stage IN ('flat','relations')),
  prompt_hash text NOT NULL,
  model text NOT NULL,                 -- 'scaledown/extract' | 'scaledown/classify' | openrouter model id
  payload jsonb NOT NULL,              -- exact model output after validation
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (chunk_id, stage, prompt_hash)
);

CREATE TABLE IF NOT EXISTS cmap.mention (            -- raw thing-as-named-in-one-chunk
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_id uuid NOT NULL REFERENCES cmap.chunk(id) ON DELETE CASCADE,
  entity_type text NOT NULL,
  surface_name text NOT NULL,
  normalized_name text NOT NULL,       -- lower, trimmed, punctuation stripped, honorifics removed
  description text,
  quote text NOT NULL,
  embedding vector(1024),
  entity_id uuid                       -- filled by step 6
);
CREATE INDEX IF NOT EXISTS mention_norm_idx ON cmap.mention (entity_type, normalized_name);

CREATE TABLE IF NOT EXISTS cmap.entity (             -- one per real-world thing
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type text NOT NULL,
  canonical_name text NOT NULL,
  description text,                    -- merged, rewritten by step 6
  embedding vector(1024),
  mention_count int NOT NULL DEFAULT 0,
  source_count int NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cmap.entity_alias (
  entity_id uuid NOT NULL REFERENCES cmap.entity(id) ON DELETE CASCADE,
  entity_type text NOT NULL,
  normalized_name text NOT NULL,
  PRIMARY KEY (entity_type, normalized_name)
);

CREATE TABLE IF NOT EXISTS cmap.relation (           -- one per (source edge) before merging
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_id uuid NOT NULL REFERENCES cmap.chunk(id) ON DELETE CASCADE,
  from_mention_id uuid NOT NULL REFERENCES cmap.mention(id) ON DELETE CASCADE,
  to_mention_id uuid NOT NULL REFERENCES cmap.mention(id) ON DELETE CASCADE,
  rel_type text NOT NULL,
  description text NOT NULL,
  stance text NOT NULL CHECK (stance IN ('policy','practice','report','inference')),
  confidence real NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  quote text NOT NULL
);

CREATE TABLE IF NOT EXISTS cmap.community (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  level int NOT NULL,                  -- 0 fine, 1 coarse
  parent_id uuid REFERENCES cmap.community(id),
  title text,
  report_md text,                      -- step 8 frontier output
  findings jsonb,                      -- [{"text":..., "entity_ids":[...], "source_ids":[...]}]
  entity_ids uuid[] NOT NULL,
  graph_version int NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cmap.job (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL,                  -- read_source | classify_extract | relations | resolve | project | communities | evaluate | interview_tick | recommend
  payload jsonb NOT NULL DEFAULT '{}',
  state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','running','done','failed')),
  attempts int NOT NULL DEFAULT 0,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz, finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS job_state_idx ON cmap.job (state, created_at);

CREATE TABLE IF NOT EXISTS cmap.graph_version (
  version int PRIMARY KEY,
  projected_at timestamptz NOT NULL DEFAULT now(),
  node_count int, edge_count int, note text
);

CREATE TABLE IF NOT EXISTS cmap.open_question (      -- step 12
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  question text NOT NULL,
  why text NOT NULL,                   -- what the system is unsure about
  entity_ids uuid[] NOT NULL,
  target_employee_id uuid,             -- public.employees.id
  state text NOT NULL DEFAULT 'open' CHECK (state IN ('open','asked','answered','dismissed')),
  asked_at timestamptz, answer text, answered_at timestamptz,
  answer_source_id uuid REFERENCES cmap.source(id)
);

CREATE TABLE IF NOT EXISTS cmap.eval_question (      -- step 11
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  question text NOT NULL,
  expected_points text[] NOT NULL,     -- 3-6 facts the answer must contain, plain English
  expected_source_titles text[] NOT NULL,
  author text NOT NULL
);
CREATE TABLE IF NOT EXISTS cmap.eval_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  graph_version int NOT NULL,
  prompt_hashes jsonb NOT NULL,
  results jsonb NOT NULL,              -- [{"question_id":..,"score":0-1,"missing":[..],"cited_sources":[..]}]
  mean_score real NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cmap.recommendation (     -- step 13
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  community_id uuid REFERENCES cmap.community(id),
  problem text NOT NULL,
  explanations jsonb NOT NULL,         -- [{"hypothesis":..,"support":[source_ids],"against":[source_ids]}]
  options jsonb NOT NULL,              -- [{"option":..,"effort":"low|med|high","risk":..,"includes_no_change":bool}]
  experiment jsonb NOT NULL,           -- {"change":..,"metric":..,"baseline_needed":..,"review_after_days":n,"owner_role":..}
  status text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','accepted','rejected','running','measured')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cmap.employee_flags (
  employee_id uuid PRIMARY KEY,        -- public.employees.id
  is_admin boolean NOT NULL DEFAULT false
);
