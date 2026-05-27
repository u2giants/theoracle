-- 55_model_capabilities_output_cap.sql
--
-- Adds `output_cap` boolean to model_capabilities — true when the model
-- supports an output-length cap (either max_completion_tokens or max_tokens
-- in OpenRouter's supported_parameters). Used by the admin model-pool
-- Synthesis stage requirement.

ALTER TABLE model_capabilities
  ADD COLUMN IF NOT EXISTS output_cap boolean NOT NULL DEFAULT false;
