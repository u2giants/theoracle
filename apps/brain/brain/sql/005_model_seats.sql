-- Per-stage model seats chosen on the admin model page (Albert's direction
-- 2026-11-03: pick each stage's model from the bake-off's top three on the
-- settings page). A row overrides the env fallback for that one stage; no row
-- means the env seat (BRAIN_FRONTIER_MODEL and friends) still applies.
CREATE TABLE IF NOT EXISTS cmap.model_seat (
  stage text PRIMARY KEY CHECK (stage IN (
    'vision','embed','flat','relations','resolve','reports','answer','recommend','grade'
  )),
  model text NOT NULL CHECK (length(btrim(model)) > 0),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid
);
