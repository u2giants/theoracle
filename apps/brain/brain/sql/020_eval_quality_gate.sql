-- B3 (repair plan §9 Phase B): the live quality gate marks an eval run
-- accepted when it passes (mean within 0.05 of the last accepted run and no
-- question errors). The last accepted run is the gate's baseline.
ALTER TABLE cmap.eval_run
  ADD COLUMN IF NOT EXISTS accepted boolean NOT NULL DEFAULT false;
