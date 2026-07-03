-- Macro-understanding model route.
--
-- The source-outline, macro-relationship-extraction, and source-coverage-audit
-- workers previously borrowed the `default_general_purpose_route` (utility)
-- slot. That slot pointed at qwen/qwen3.7-max, which only supports loose
-- `json_object` output (not strict JSON schema) and intermittently omits the
-- required top-level arrays, hard-failing the macro layer with
-- AllCandidatesFailedError (see AGENT_ERROR_LOG.md). The macro layer now has its
-- own explicit, admin-visible slot that requires strict structured output.
--
-- Default seeded to openai/gpt-4.1-mini. IMPORTANT: Gemini's responseJsonSchema
-- REJECTS these deeply-nested macro schemas with 400 "specified schema produces
-- a constraint too complex" (verified in prod 2026-07-03 — see AGENT_ERROR_LOG.md
-- ERR-001), so the primary must be an OpenAI strict-json-schema model. Gemini
-- stays in the fallback pool (it can handle the simpler source-outline schema).
-- Admins can change this at Admin -> Settings -> "Macro understanding model" with
-- no redeploy. Idempotent: never clobbers an admin's existing choice.

BEGIN;

INSERT INTO settings (key, value, description)
VALUES
  (
    'default_macro_route',
    '"openai/gpt-4.1-mini"'::jsonb,
    'Model for the macro/holistic layer (source outlines, macro relationship extraction, coverage audits). Requires strict structured-output support. Gemini rejects the nested schemas (400 too-complex); use an OpenAI strict-json-schema model.'
  )
ON CONFLICT (key) DO NOTHING;

COMMIT;
