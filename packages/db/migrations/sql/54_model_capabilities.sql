-- 54_model_capabilities.sql
--
-- Persistent cache of the live model catalog discovered from OpenRouter.
-- One row per "provider/modelId" id. Refreshed via the admin "Refresh
-- catalog" button or a future scheduled job. Stays here forever unless
-- explicitly refreshed — no automatic expiry.
--
-- Pricing is stored as USD per 1 million tokens (already multiplied from
-- OpenRouter's per-token figures).

CREATE TABLE IF NOT EXISTS model_capabilities (
  id text PRIMARY KEY,                       -- "anthropic/claude-sonnet-4-6"
  provider text NOT NULL CHECK (provider IN ('anthropic','openai','google')),
  display_name text NOT NULL,
  context_length integer,
  max_output_tokens integer,
  prompt_per_1m_usd numeric(10,6),
  completion_per_1m_usd numeric(10,6),
  vision boolean NOT NULL DEFAULT false,
  pdf boolean NOT NULL DEFAULT false,
  thinking boolean NOT NULL DEFAULT false,
  structured_outputs boolean NOT NULL DEFAULT false,
  tool_calling boolean NOT NULL DEFAULT false,
  prompt_caching boolean NOT NULL DEFAULT false,
  knowledge_cutoff date,
  source text NOT NULL,                      -- 'openrouter' | future: 'anthropic_api' | 'classifier'
  refreshed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS model_capabilities_provider_idx ON model_capabilities (provider);
CREATE INDEX IF NOT EXISTS model_capabilities_refreshed_idx ON model_capabilities (refreshed_at DESC);
