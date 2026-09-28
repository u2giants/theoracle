-- 56_model_capabilities_more_providers.sql
--
-- Adds 'deepseek' and 'qwen' to the allowed provider values on
-- model_capabilities. The original CHECK constraint from migration 54 only
-- permitted ('anthropic','openai','google'); the new DeepSeekAdapter and
-- QwenAdapter need to register their model lists too.
--
-- 2026-09-28: also 'meta_muse', 'zai', 'stepfun' for the OpenAI-compatible
-- adapters added in PR #48; without them Refresh catalog failed on insert.
--
-- Naming: 'deepseek' for DeepSeek's own API; 'qwen' for Alibaba's Qwen family
-- served via DashScope's OpenAI-compatible endpoint. The provider key matches
-- OpenRouter's slug convention so enrichment lookups remain straightforward.

ALTER TABLE model_capabilities DROP CONSTRAINT IF EXISTS model_capabilities_provider_check;
ALTER TABLE model_capabilities
  ADD CONSTRAINT model_capabilities_provider_check
  CHECK (provider IN ('anthropic','openai','google','deepseek','qwen','meta_muse','zai','stepfun'));
