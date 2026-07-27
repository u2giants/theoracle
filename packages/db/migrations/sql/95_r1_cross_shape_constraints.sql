-- R1: additive cross-shape business-model constraints, RLS, and fail-safe flags.
-- No legacy process content is copied. The mandatory production audit recorded
-- zero rows in all process/change/recommendation destination tables.

DO $r1_constraints$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_objects_current_version_fk'
  ) THEN
    ALTER TABLE business_objects
      ADD CONSTRAINT business_objects_current_version_fk
      FOREIGN KEY (current_version_id) REFERENCES business_object_versions(id)
      ON DELETE SET NULL;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_object_versions_created_from_change_fk'
  ) THEN
    ALTER TABLE business_object_versions
      ADD CONSTRAINT business_object_versions_created_from_change_fk
      FOREIGN KEY (created_from_change_id) REFERENCES business_model_changes(id)
      ON DELETE SET NULL;
  END IF;
END $r1_constraints$;

-- Migration 86's process-only proposal constraints conflict with the R1
-- object identity. Replace each old definition once under its stable name.
-- Later migration-runner executions leave the final constraints untouched.
DO $r1_replace_legacy_checks$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'business_model_changes_type_check'
      AND pg_get_constraintdef(oid) NOT LIKE '%create_object%'
  ) THEN
    ALTER TABLE business_model_changes
      DROP CONSTRAINT business_model_changes_type_check;
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'business_model_changes_base_required_check'
      AND pg_get_constraintdef(oid) NOT LIKE '%base_object_version_id%'
  ) THEN
    ALTER TABLE business_model_changes
      DROP CONSTRAINT business_model_changes_base_required_check;
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'business_model_changes_generic_target_check'
      AND pg_get_constraintdef(oid) NOT LIKE '%base_object_version_id IS NOT NULL%'
  ) THEN
    ALTER TABLE business_model_changes
      DROP CONSTRAINT business_model_changes_generic_target_check;
  END IF;
END $r1_replace_legacy_checks$;

DO $r1_checks$
DECLARE
  constraint_record record;
BEGIN
  FOR constraint_record IN
    SELECT *
    FROM (VALUES
      ('business_objects_kind_check',
       'business_objects',
       $$object_kind IN ('process','responsibility_model','rule_set','reference_dataset','conversation_model','narrative_macro')$$),
      ('business_objects_status_check',
       'business_objects',
       $$status IN ('draft','pending_review','approved','superseded','archived')$$),
      ('business_objects_slug_check',
       'business_objects',
       $$slug = lower(slug) AND slug ~ '^[a-z0-9][a-z0-9-]{0,159}$'$$),
      ('business_object_versions_number_check',
       'business_object_versions',
       $$version_number > 0$$),
      ('business_object_versions_status_check',
       'business_object_versions',
       $$status IN ('pending_review','approved','superseded','rejected')$$),
      ('business_elements_shape_kind_check',
       'business_elements',
       $$(
         (shape = 'process' AND element_kind IN ('step','decision','approval_gate','system_entry','artifact','terminal'))
         OR (shape = 'responsibilities' AND element_kind = 'responsibility')
         OR (shape = 'ruleset' AND element_kind = 'rule')
         OR (shape = 'reference' AND element_kind IN ('attribute','relationship'))
         OR (shape = 'conversation' AND element_kind IN ('decision','assertion','open_question','problem','action_item'))
         OR (shape = 'narrative' AND element_kind IN ('asserted_fact','goal','constraint','risk','rationale'))
       )$$),
      ('business_elements_confidence_check',
       'business_elements',
       $$confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100$$),
      ('business_relations_shape_kind_check',
       'business_relations',
       $$(
         (shape = 'process' AND relation_kind IN ('sequence','handoff','branch','loop','exception'))
         OR (shape = 'ruleset' AND relation_kind IN ('applicability','exception'))
         OR (shape = 'reference' AND relation_kind = 'relationship')
       )$$),
      ('business_relations_distinct_endpoints_check',
       'business_relations',
       $$from_element_key <> to_element_key$$),
      ('business_relations_confidence_check',
       'business_relations',
       $$confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100$$),
      ('business_element_claims_target_check',
       'business_element_claims',
       $$num_nonnulls(element_id, relation_id) = 1$$),
      ('business_element_claims_support_role_check',
       'business_element_claims',
       $$support_role IN ('primary','corroborating')$$),
      ('business_paths_element_keys_check',
       'business_paths',
       $$jsonb_typeof(element_keys_ordered) = 'array'$$),
      ('business_process_details_required_check',
       'business_process_details',
       $$length(btrim(node_type)) > 0$$),
      ('business_responsibility_details_required_check',
       'business_responsibility_details',
       $$length(btrim(role)) > 0 AND length(btrim(action)) > 0 AND length(btrim(object)) > 0$$),
      ('business_rule_details_required_check',
       'business_rule_details',
       $$length(btrim(scope)) > 0 AND length(btrim(effect)) > 0$$),
      ('business_reference_details_required_check',
       'business_reference_details',
       $$length(btrim(entity_type)) > 0 AND length(btrim(attribute_key)) > 0
         AND length(btrim(attribute_value)) > 0 AND length(btrim(reference_kind)) > 0$$),
      ('business_conversation_details_required_check',
       'business_conversation_details',
       $$contested OR num_nonnulls(decision_status, speaker, due_date, action_status, meeting_reference) > 0$$),
      ('business_narrative_macro_details_required_check',
       'business_narrative_macro_details',
       $$length(btrim(macro_kind)) > 0$$),
      ('business_model_changes_generic_target_check',
       'business_model_changes',
       $$(
         (object_id IS NULL AND object_kind IS NULL AND proposed_slug IS NULL
          AND base_object_version_id IS NULL
          AND (
            (change_type = 'create_process' AND process_id IS NULL)
            OR
            (change_type IN ('refine_process','confirm','contradict') AND process_id IS NOT NULL)
          ))
         OR
         (process_id IS NULL AND base_version_id IS NULL
          AND object_kind IN ('process','responsibility_model','rule_set','reference_dataset','conversation_model','narrative_macro')
          AND (
            (object_id IS NOT NULL AND proposed_slug IS NULL
             AND base_object_version_id IS NOT NULL
             AND change_type IN ('refine_object','confirm','contradict'))
            OR
            (object_id IS NULL AND change_type = 'create_object'
             AND proposed_slug IS NOT NULL
             AND proposed_slug = lower(proposed_slug)
             AND proposed_slug ~ '^[a-z0-9][a-z0-9-]{0,159}$'
             AND base_object_version_id IS NULL)
          ))
       )$$),
      ('business_model_changes_type_check',
       'business_model_changes',
       $$change_type IN ('create_process','refine_process','create_object','refine_object','confirm','contradict')$$),
      ('business_model_changes_base_required_check',
       'business_model_changes',
       $$(
         (change_type = 'create_process'
          AND process_id IS NULL AND base_version_id IS NULL
          AND object_id IS NULL AND base_object_version_id IS NULL)
         OR
         (change_type IN ('refine_process','confirm','contradict')
          AND process_id IS NOT NULL AND base_version_id IS NOT NULL
          AND object_id IS NULL AND base_object_version_id IS NULL)
         OR
         (change_type = 'create_object'
          AND process_id IS NULL AND base_version_id IS NULL
          AND object_id IS NULL AND base_object_version_id IS NULL)
         OR
         (change_type IN ('refine_object','confirm','contradict')
          AND process_id IS NULL AND base_version_id IS NULL
          AND object_id IS NOT NULL AND base_object_version_id IS NOT NULL)
       )$$),
      ('recommendations_generic_target_check',
       'recommendations',
       $$(
         (process_id IS NOT NULL AND version_id IS NOT NULL
          AND object_id IS NULL AND object_version_id IS NULL AND object_kind IS NULL)
         OR
         (process_id IS NULL AND version_id IS NULL
          AND object_id IS NOT NULL AND object_version_id IS NOT NULL
          AND object_kind IN ('process','responsibility_model','rule_set','reference_dataset','conversation_model','narrative_macro'))
       )$$)
    ) AS definitions(constraint_name, table_name, expression)
    WHERE NOT EXISTS (
      SELECT 1 FROM pg_constraint WHERE conname = definitions.constraint_name
    )
  LOOP
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (%s)',
      constraint_record.table_name,
      constraint_record.constraint_name,
      constraint_record.expression
    );
  END LOOP;
END $r1_checks$;

CREATE UNIQUE INDEX IF NOT EXISTS business_elements_id_version_unique
  ON business_elements(id, version_id);
CREATE UNIQUE INDEX IF NOT EXISTS business_relations_id_version_unique
  ON business_relations(id, version_id);
CREATE UNIQUE INDEX IF NOT EXISTS business_object_versions_object_id_id_unique
  ON business_object_versions(object_id, id);
DROP INDEX IF EXISTS business_model_changes_active_idempotency_unique;
CREATE UNIQUE INDEX IF NOT EXISTS business_model_changes_active_legacy_target_unique
  ON business_model_changes(
    source_workflow_map_id,
    COALESCE(base_version_id, '00000000-0000-0000-0000-000000000000'::uuid)
  )
  WHERE object_kind IS NULL AND status <> 'superseded';
CREATE UNIQUE INDEX IF NOT EXISTS business_model_changes_active_object_target_unique
  ON business_model_changes(source_workflow_map_id, object_id, base_object_version_id)
  WHERE object_id IS NOT NULL AND status <> 'superseded';
CREATE UNIQUE INDEX IF NOT EXISTS business_model_changes_active_map_create_namespace_unique
  ON business_model_changes(source_workflow_map_id, object_kind, proposed_slug)
  WHERE object_id IS NULL
    AND proposed_slug IS NOT NULL
    AND status <> 'superseded';
CREATE UNIQUE INDEX IF NOT EXISTS business_model_changes_active_create_namespace_unique
  ON business_model_changes(object_kind, proposed_slug)
  WHERE process_id IS NULL
    AND object_id IS NULL
    AND proposed_slug IS NOT NULL
    AND status IN ('pending_review', 'approved', 'needs_rebase');
CREATE UNIQUE INDEX IF NOT EXISTS recommendations_object_deterministic_unique
  ON recommendations(object_version_id, analyzer_key, md5(element_keys::text))
  WHERE origin = 'deterministic'
    AND object_version_id IS NOT NULL
    AND analyzer_key IS NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_objects_current_version_owner_fk'
  ) THEN
    ALTER TABLE business_objects
      ADD CONSTRAINT business_objects_current_version_owner_fk
      FOREIGN KEY (id, current_version_id)
      REFERENCES business_object_versions(object_id, id);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_model_changes_base_object_owner_fk'
  ) THEN
    ALTER TABLE business_model_changes
      ADD CONSTRAINT business_model_changes_base_object_owner_fk
      FOREIGN KEY (object_id, base_object_version_id)
      REFERENCES business_object_versions(object_id, id)
      ON DELETE SET NULL (base_object_version_id);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'recommendations_object_version_owner_fk'
  ) THEN
    ALTER TABLE recommendations
      ADD CONSTRAINT recommendations_object_version_owner_fk
      FOREIGN KEY (object_id, object_version_id)
      REFERENCES business_object_versions(object_id, id)
      ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_relations_from_element_fk'
  ) THEN
    ALTER TABLE business_relations
      ADD CONSTRAINT business_relations_from_element_fk
      FOREIGN KEY (version_id, from_element_key)
      REFERENCES business_elements(version_id, element_key)
      ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_relations_to_element_fk'
  ) THEN
    ALTER TABLE business_relations
      ADD CONSTRAINT business_relations_to_element_fk
      FOREIGN KEY (version_id, to_element_key)
      REFERENCES business_elements(version_id, element_key)
      ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_element_claims_element_version_fk'
  ) THEN
    ALTER TABLE business_element_claims
      ADD CONSTRAINT business_element_claims_element_version_fk
      FOREIGN KEY (element_id, version_id)
      REFERENCES business_elements(id, version_id)
      ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_element_claims_relation_version_fk'
  ) THEN
    ALTER TABLE business_element_claims
      ADD CONSTRAINT business_element_claims_relation_version_fk
      FOREIGN KEY (relation_id, version_id)
      REFERENCES business_relations(id, version_id)
      ON DELETE CASCADE;
  END IF;
END $$;

CREATE OR REPLACE FUNCTION enforce_business_object_kind_identity()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  actual_kind text;
BEGIN
  IF NEW.object_id IS NULL THEN
    RETURN NEW;
  END IF;
  SELECT object_kind INTO actual_kind FROM business_objects WHERE id = NEW.object_id;
  IF actual_kind IS DISTINCT FROM NEW.object_kind THEN
    RAISE EXCEPTION '% object_kind % does not match business object kind %',
      TG_TABLE_NAME, NEW.object_kind, coalesce(actual_kind, '<missing>');
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS business_model_changes_object_kind_guard ON business_model_changes;
CREATE TRIGGER business_model_changes_object_kind_guard
BEFORE INSERT OR UPDATE OF object_id, object_kind ON business_model_changes
FOR EACH ROW EXECUTE FUNCTION enforce_business_object_kind_identity();

DROP TRIGGER IF EXISTS recommendations_object_kind_guard ON recommendations;
CREATE TRIGGER recommendations_object_kind_guard
BEFORE INSERT OR UPDATE OF object_id, object_kind ON recommendations
FOR EACH ROW EXECUTE FUNCTION enforce_business_object_kind_identity();

CREATE OR REPLACE FUNCTION enforce_business_element_object_shape()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  actual_kind text;
  expected_kind text;
BEGIN
  SELECT o.object_kind INTO actual_kind
  FROM business_object_versions v
  JOIN business_objects o ON o.id = v.object_id
  WHERE v.id = NEW.version_id;
  expected_kind := CASE NEW.shape
    WHEN 'process' THEN 'process'
    WHEN 'responsibilities' THEN 'responsibility_model'
    WHEN 'ruleset' THEN 'rule_set'
    WHEN 'reference' THEN 'reference_dataset'
    WHEN 'conversation' THEN 'conversation_model'
    WHEN 'narrative' THEN 'narrative_macro'
  END;
  IF actual_kind IS DISTINCT FROM expected_kind THEN
    RAISE EXCEPTION 'business element shape % requires object kind %, got %',
      NEW.shape, expected_kind, coalesce(actual_kind, '<missing>');
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS business_elements_object_shape_guard ON business_elements;
CREATE TRIGGER business_elements_object_shape_guard
BEFORE INSERT OR UPDATE OF version_id, shape ON business_elements
FOR EACH ROW EXECUTE FUNCTION enforce_business_element_object_shape();

CREATE OR REPLACE FUNCTION enforce_business_relation_object_shape()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  actual_kind text;
  expected_kind text;
  from_shape text;
  to_shape text;
BEGIN
  SELECT o.object_kind INTO actual_kind
  FROM business_object_versions v
  JOIN business_objects o ON o.id = v.object_id
  WHERE v.id = NEW.version_id;
  expected_kind := CASE NEW.shape
    WHEN 'process' THEN 'process'
    WHEN 'ruleset' THEN 'rule_set'
    WHEN 'reference' THEN 'reference_dataset'
  END;
  SELECT shape INTO from_shape
  FROM business_elements
  WHERE version_id = NEW.version_id AND element_key = NEW.from_element_key;
  SELECT shape INTO to_shape
  FROM business_elements
  WHERE version_id = NEW.version_id AND element_key = NEW.to_element_key;
  IF actual_kind IS DISTINCT FROM expected_kind THEN
    RAISE EXCEPTION 'business relation shape % requires object kind %, got %',
      NEW.shape, expected_kind, coalesce(actual_kind, '<missing>');
  END IF;
  IF from_shape IS DISTINCT FROM NEW.shape OR to_shape IS DISTINCT FROM NEW.shape THEN
    RAISE EXCEPTION 'business relation shape % must match endpoint shapes % and %',
      NEW.shape, coalesce(from_shape, '<missing>'), coalesce(to_shape, '<missing>');
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS business_relations_object_shape_guard ON business_relations;
CREATE TRIGGER business_relations_object_shape_guard
BEFORE INSERT OR UPDATE OF version_id, shape, from_element_key, to_element_key
ON business_relations
FOR EACH ROW EXECUTE FUNCTION enforce_business_relation_object_shape();

CREATE OR REPLACE FUNCTION enforce_business_path_process_only()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  actual_kind text;
BEGIN
  SELECT o.object_kind INTO actual_kind
  FROM business_object_versions v
  JOIN business_objects o ON o.id = v.object_id
  WHERE v.id = NEW.version_id;
  IF actual_kind IS DISTINCT FROM 'process' THEN
    RAISE EXCEPTION 'business paths require process objects, got %',
      coalesce(actual_kind, '<missing>');
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS business_paths_process_only_guard ON business_paths;
CREATE TRIGGER business_paths_process_only_guard
BEFORE INSERT OR UPDATE OF version_id ON business_paths
FOR EACH ROW EXECUTE FUNCTION enforce_business_path_process_only();

CREATE OR REPLACE FUNCTION enforce_business_detail_shape()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  expected_shape text := TG_ARGV[0];
  actual_shape text;
BEGIN
  SELECT shape INTO actual_shape FROM business_elements WHERE id = NEW.element_id;
  IF actual_shape IS DISTINCT FROM expected_shape THEN
    RAISE EXCEPTION '% requires parent business element shape %, got %',
      TG_TABLE_NAME, expected_shape, coalesce(actual_shape, '<missing>');
  END IF;
  RETURN NEW;
END;
$$;

DO $$
DECLARE
  detail_record record;
BEGIN
  FOR detail_record IN
    SELECT *
    FROM (VALUES
      ('business_process_details', 'process'),
      ('business_responsibility_details', 'responsibilities'),
      ('business_rule_details', 'ruleset'),
      ('business_reference_details', 'reference'),
      ('business_conversation_details', 'conversation'),
      ('business_narrative_macro_details', 'narrative')
    ) AS detail_tables(table_name, expected_shape)
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I',
      detail_record.table_name || '_shape_guard', detail_record.table_name);
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION enforce_business_detail_shape(%L)',
      detail_record.table_name || '_shape_guard',
      detail_record.table_name,
      detail_record.expected_shape
    );
  END LOOP;
END $$;

DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'business_objects',
    'business_object_versions',
    'business_elements',
    'business_relations',
    'business_element_claims',
    'business_element_systems',
    'business_paths',
    'business_object_top_domains',
    'business_process_details',
    'business_responsibility_details',
    'business_rule_details',
    'business_reference_details',
    'business_conversation_details',
    'business_narrative_macro_details'
  ]
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
      EXECUTE format('REVOKE ALL ON TABLE %I FROM anon', table_name);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
      EXECUTE format('REVOKE ALL ON TABLE %I FROM authenticated', table_name);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
      EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE %I TO service_role',
        table_name
      );
    END IF;
  END LOOP;
END $$;

INSERT INTO settings (key, value, description)
VALUES
  ('business_model_merge_enabled', 'false'::jsonb,
   'Fail-safe R1 flag. When false, no source map may create shadow business-model proposals.'),
  ('business_model_apply_enabled', 'false'::jsonb,
   'Fail-safe R1 flag. When false, reviewed proposals cannot mutate the durable business model.'),
  ('business_model_serving_enabled', 'false'::jsonb,
   'Fail-safe R1 flag. When false, employee answers cannot use the durable business model.')
ON CONFLICT (key) DO NOTHING;
