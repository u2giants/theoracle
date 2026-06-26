-- R18 — fail-loud model routing bootstrap.
--
-- The application no longer has hard-coded fallback routes. These settings
-- make the approved model chain explicit in the database for existing
-- environments. Admin changes are preserved by ON CONFLICT DO NOTHING.

INSERT INTO settings (key, value, description)
VALUES
  ('model_pool_interview', '["anthropic/claude-haiku-4-5"]'::jsonb, 'Approved interview model chain, tried in order after the selected primary.'),
  ('model_pool_extraction', '["google/gemini-2.5-flash"]'::jsonb, 'Approved extraction model chain, tried in order after the selected primary.'),
  ('model_pool_synthesis', '["anthropic/claude-sonnet-4-6"]'::jsonb, 'Approved synthesis model chain, tried in order after the selected primary.'),
  ('enforce_model_capabilities', 'true'::jsonb, 'When true, model routing rejects configured models that do not meet slot capability requirements.'),
  ('default_vision_route', '"vertex_gemini_2_5_flash_extraction_primary"'::jsonb, 'Auxiliary image-vision model route for document image transcription.'),
  ('default_general_purpose_route', '"vertex_gemini_2_5_flash_extraction_primary"'::jsonb, 'Auxiliary general-purpose model route for internal utility jobs.'),
  ('default_translation_route', '"anthropic_claude_3_5_sonnet_synthesis_primary"'::jsonb, 'Auxiliary translation model route for bilingual claim rendering and review questions.'),
  ('extraction_char_budget', '24000'::jsonb, 'Approximate max characters of active conversation text selected per extraction run before stopping at a conversation boundary.'),
  ('extraction_carry_in_count', '12'::jsonb, 'Prior complete/skipped same-channel messages included as non-quotable context for message extraction.')
ON CONFLICT (key) DO NOTHING;
