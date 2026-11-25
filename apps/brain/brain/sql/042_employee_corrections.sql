-- Employee correction notes and per-employee submission permissions.
-- Idempotent. Only designated reviewers (or admins) can submit/view text
-- corrections; admins review, apply as authoritative text sources, or dismiss.

ALTER TABLE cmap.employee_flags
  ADD COLUMN IF NOT EXISTS can_correct boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS cmap.correction_note (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL,
  employee_name text NOT NULL DEFAULT '',
  function_id uuid REFERENCES cmap.function(id) ON DELETE SET NULL,
  page_ref text,
  what_is_wrong text NOT NULL,
  correction_text text NOT NULL,
  status text NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'applied', 'dismissed')),
  source_id uuid REFERENCES cmap.source(id) ON DELETE SET NULL,
  reviewed_by uuid,
  reviewed_at timestamptz,
  review_note text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS correction_note_status_created_idx
  ON cmap.correction_note (status, created_at DESC);

CREATE INDEX IF NOT EXISTS correction_note_employee_idx
  ON cmap.correction_note (employee_id, created_at DESC);

-- One-time initial reviewer roster requested by Albert (2026-11-24).
-- Guarded on public.employees existing (test DBs migrate before creating
-- employee stubs) and no reviewer already having can_correct=true so later
-- admin UI edits are never overwritten on restart.
DO $$
BEGIN
  IF to_regclass('public.employees') IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM cmap.employee_flags WHERE can_correct = true) THEN
    INSERT INTO cmap.employee_flags (employee_id, can_correct)
    SELECT id, true
    FROM public.employees
    WHERE lower(email) IN (
      'ikereki@popcre.com',
      'larevalo@popcre.com',
      'mzabo@popcre.com',
      'eparkin@popcre.com',
      'jcortazar@popcre.com',
      'ccorral@popcre.com',
      'jchaffier@popcre.com'
    )
    ON CONFLICT (employee_id) DO UPDATE SET can_correct = true;
  END IF;
END $$;
