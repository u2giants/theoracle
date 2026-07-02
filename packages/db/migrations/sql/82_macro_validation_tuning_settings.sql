-- Runtime tuning knobs for macro/lens validation thresholds.
-- These defaults match the first shipped macro implementation; storing them in
-- settings lets admins tune after evals without a worker redeploy.

INSERT INTO settings (key, value, description)
VALUES
  (
    'macro_relationship_near_duplicate_distance',
    '0.08'::jsonb,
    'Cosine-distance cutoff for suppressing semantically near-duplicate macro relationship proposals. Lower is stricter.'
  ),
  (
    'macro_lens_dedup_distance',
    '0.08'::jsonb,
    'Cosine-distance cutoff for suppressing semantically near-duplicate claims produced by document lens extraction.'
  ),
  (
    'macro_lens_dedup_density_threshold_per_10k',
    '10'::jsonb,
    'Minimum existing claim density per 10k document characters before lens semantic dedup runs.'
  ),
  (
    'macro_entity_validation_extra_stopwords',
    '[]'::jsonb,
    'Optional JSON array of additional capitalized terms ignored by macro summary named-entity validation.'
  )
ON CONFLICT (key) DO UPDATE
SET
  description = EXCLUDED.description,
  updated_at = now();
