-- Macro fallback pool + coverage-first lens budgets (2026-07-03).
--
-- (1) model_pool_macro: the macro slot now has an ordered fallback chain so one
--     malformed structured-output response can't zero the holistic layer
--     (AGENT_ERROR_LOG.md ERR-001). Must contain the default_macro_route primary
--     (google/gemini-2.5-flash) and only strict-json-schema-capable models.
--
-- (2) Lens fan-out budgets: the old defaults (model_calls=4, groups=8) plus the
--     lens-major selection meant a 10-stage swimlane diagram ran ONE lens on the
--     first 4 stages and dropped the terminal stages entirely (fix_enhancement.md
--     §5 Bugs A/B/F). The selection is now coverage-first (every stage gets its
--     top lens before any stage gets a second), so the model-call ceiling must be
--     high enough to cover the stages. These are UPDATEs (not inserts) because the
--     rows already exist from migration 81; this is a deliberate behavior fix.

BEGIN;

-- OpenAI-first: Gemini rejects the nested macro relationship/coverage schemas
-- (400 too-complex), so the primary + top fallbacks are OpenAI strict-json-schema
-- models; gemini-2.5-pro stays as a cross-vendor tail (fine for outlines).
INSERT INTO settings (key, value, description)
VALUES
  (
    'model_pool_macro',
    '["openai/gpt-4.1-mini", "openai/gpt-4.1", "google/gemini-2.5-pro"]'::jsonb,
    'Ordered fallback chain for the macro slot (source outlines, macro relationships, coverage audits). Must include the default_macro_route primary and only strict-structured-output models. OpenAI first — Gemini rejects the nested schemas.'
  )
ON CONFLICT (key) DO NOTHING;

-- Coverage-adequate lens fan-out ceilings. Cost stays bounded by the token
-- ceiling and the model-call cap; the selection covers stages breadth-first.
-- Guarded on the original migration-81 defaults so a re-run of this idempotent
-- file never clobbers an admin's later tuning.
UPDATE settings SET value = '16'::jsonb
  WHERE key = 'macro_max_lens_model_calls_per_document' AND value = '4'::jsonb;
UPDATE settings SET value = '20'::jsonb
  WHERE key = 'macro_max_lens_groups_per_document' AND value = '8'::jsonb;
UPDATE settings SET value = '64000'::jsonb
  WHERE key = 'macro_max_lens_estimated_input_tokens' AND value = '32000'::jsonb;

COMMIT;
