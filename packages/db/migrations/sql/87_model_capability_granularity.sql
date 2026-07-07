-- Split broad "structured outputs" into Oracle-runtime capabilities.
-- `structured_outputs` remains for compatibility and broad UI filtering, but
-- workflow/macro routing now needs stricter proof.

ALTER TABLE model_capabilities
  ADD COLUMN IF NOT EXISTS strict_json_schema boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS deep_schema_accepted boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS adapter_params_safe boolean NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS adapter_param_notes jsonb NOT NULL DEFAULT '{}'::jsonb;

UPDATE model_capabilities
SET
  strict_json_schema =
    structured_outputs
    AND provider IN ('openai', 'google', 'anthropic'),
  deep_schema_accepted =
    provider = 'openai'
    AND id IN ('openai/gpt-4.1', 'openai/gpt-4.1-mini'),
  adapter_params_safe = true,
  adapter_param_notes =
    CASE
      WHEN provider = 'google' THEN
        jsonb_build_object('deep_schema', 'Gemini can support schema mode but has rejected Oracle workflow/macro deep schemas as too complex.')
      WHEN provider IN ('qwen', 'deepseek') THEN
        jsonb_build_object('strict_schema', 'Provider path uses loose JSON mode, not provider-enforced JSON Schema.')
      ELSE '{}'::jsonb
    END
WHERE true;
