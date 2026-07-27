import postgres from 'postgres';

const url = process.env.DIRECT_URL ?? process.env.DATABASE_URL;
if (!url) throw new Error('DIRECT_URL or DATABASE_URL is required.');

const parsed = new URL(url);
if (!['localhost', '127.0.0.1', '::1'].includes(parsed.hostname)) {
  throw new Error(`Refusing R1 mutation fixtures on non-loopback host ${parsed.hostname}.`);
}
if (parsed.pathname.replace(/^\//, '') !== 'oracle_fresh') {
  throw new Error(`Refusing R1 mutation fixtures outside oracle_fresh: ${parsed.pathname}.`);
}

const expectedTables = [
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
  'business_narrative_macro_details',
] as const;

const expectedConstraints = [
  'business_model_changes_type_check',
  'business_model_changes_base_required_check',
  'business_model_changes_generic_target_check',
  'recommendations_generic_target_check',
  'business_element_claims_target_check',
  'business_relations_from_element_fk',
  'business_relations_to_element_fk',
  'business_element_claims_element_version_fk',
  'business_element_claims_relation_version_fk',
  'business_objects_current_version_owner_fk',
  'business_model_changes_base_object_owner_fk',
  'recommendations_object_version_owner_fk',
] as const;

const ids = {
  map: '10000000-0000-4000-8000-000000000001',
  responsibilityObject: '20000000-0000-4000-8000-000000000001',
  responsibilityVersion: '30000000-0000-4000-8000-000000000001',
  processObject: '20000000-0000-4000-8000-000000000002',
  processVersion: '30000000-0000-4000-8000-000000000002',
  secondProcessObject: '20000000-0000-4000-8000-000000000003',
  secondProcessVersion: '30000000-0000-4000-8000-000000000003',
  ruleObject: '20000000-0000-4000-8000-000000000004',
  ruleVersion: '30000000-0000-4000-8000-000000000004',
  referenceObject: '20000000-0000-4000-8000-000000000005',
  referenceVersion: '30000000-0000-4000-8000-000000000005',
  conversationObject: '20000000-0000-4000-8000-000000000006',
  conversationVersion: '30000000-0000-4000-8000-000000000006',
  narrativeObject: '20000000-0000-4000-8000-000000000007',
  narrativeVersion: '30000000-0000-4000-8000-000000000007',
  legacyProcess: '40000000-0000-4000-8000-000000000001',
  legacyVersion: '50000000-0000-4000-8000-000000000001',
} as const;

const sql = postgres(url, { max: 1, prepare: false });
try {
  const tables = await sql<{ table_name: string; rowsecurity: boolean }[]>`
    SELECT c.relname AS table_name, c.relrowsecurity AS rowsecurity
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname IN ${sql(expectedTables)}
  `;
  const byName = new Map(tables.map((row) => [row.table_name, row]));
  for (const table of expectedTables) {
    if (!byName.has(table)) throw new Error(`R1 table missing: ${table}`);
    if (!byName.get(table)?.rowsecurity) throw new Error(`RLS is not enabled: ${table}`);
  }

  const constraints = await sql<{ conname: string }[]>`
    SELECT conname FROM pg_constraint WHERE conname IN ${sql(expectedConstraints)}
  `;
  const constraintNames = new Set(constraints.map((row) => row.conname));
  for (const constraint of expectedConstraints) {
    if (!constraintNames.has(constraint)) throw new Error(`R1 constraint missing: ${constraint}`);
  }

  const settings = await sql<{ key: string; value: unknown }[]>`
    SELECT key, value
    FROM settings
    WHERE key IN (
      'business_model_merge_enabled',
      'business_model_apply_enabled',
      'business_model_serving_enabled'
    )
  `;
  if (settings.length !== 3 || settings.some((row) => row.value !== false)) {
    throw new Error(`R1 fail-safe settings must all equal false: ${JSON.stringify(settings)}`);
  }

  const rollbackProof = new Error('R1_FIXTURE_ROLLBACK');
  try {
    await sql.begin(async (tx) => {
      const expectFailure = async (
        label: string,
        action: (fixtureSql: typeof tx) => Promise<unknown>,
      ): Promise<void> => {
        let failed = false;
        try {
          await tx.savepoint(label, action);
        } catch {
          failed = true;
        }
        if (!failed) throw new Error(`Expected database rejection: ${label}`);
      };

      await tx`
        INSERT INTO source_workflow_maps
          (id, source_type, source_content_hash, status, document_shape, map_kind)
        VALUES
          (${ids.map}, 'document', ${'a'.repeat(64)}, 'validated', 'responsibilities', 'reference')
      `;

      const objects = [
        [ids.responsibilityObject, 'responsibility_model', 'responsibility-fixture'],
        [ids.processObject, 'process', 'process-fixture'],
        [ids.secondProcessObject, 'process', 'process-fixture-two'],
        [ids.ruleObject, 'rule_set', 'rules-fixture'],
        [ids.referenceObject, 'reference_dataset', 'reference-fixture'],
        [ids.conversationObject, 'conversation_model', 'conversation-fixture'],
        [ids.narrativeObject, 'narrative_macro', 'narrative-fixture'],
      ] as const;
      for (const [id, kind, slug] of objects) {
        await tx`
          INSERT INTO business_objects (id, object_kind, name, slug)
          VALUES (${id}, ${kind}, ${slug}, ${slug})
        `;
      }

      const versions = [
        [ids.responsibilityVersion, ids.responsibilityObject],
        [ids.processVersion, ids.processObject],
        [ids.secondProcessVersion, ids.secondProcessObject],
        [ids.ruleVersion, ids.ruleObject],
        [ids.referenceVersion, ids.referenceObject],
        [ids.conversationVersion, ids.conversationObject],
        [ids.narrativeVersion, ids.narrativeObject],
      ] as const;
      for (const [id, objectId] of versions) {
        await tx`
          INSERT INTO business_object_versions (id, object_id, version_number)
          VALUES (${id}, ${objectId}, 1)
        `;
      }

      await tx`
        INSERT INTO business_model_changes
          (source_workflow_map_id, change_type, object_kind, proposed_slug)
        VALUES
          (${ids.map}, 'create_object', 'responsibility_model', 'new-responsibility-model')
      `;
      await tx`
        INSERT INTO business_model_changes
          (source_workflow_map_id, change_type, object_id, object_kind, base_object_version_id)
        VALUES
          (${ids.map}, 'refine_object', ${ids.responsibilityObject},
           'responsibility_model', ${ids.responsibilityVersion})
      `;
      await expectFailure('duplicate_create_namespace', (fixtureSql) =>
        fixtureSql`
          INSERT INTO business_model_changes
            (source_workflow_map_id, change_type, object_kind, proposed_slug)
          VALUES
            (${ids.map}, 'create_object', 'responsibility_model', 'new-responsibility-model')
        `,
      );
      await expectFailure('existing_object_missing_base', (fixtureSql) =>
        fixtureSql`
          INSERT INTO business_model_changes
            (source_workflow_map_id, change_type, object_id, object_kind)
          VALUES
            (${ids.map}, 'refine_object', ${ids.ruleObject}, 'rule_set')
        `,
      );
      await expectFailure('duplicate_existing_object_target', (fixtureSql) =>
        fixtureSql`
          INSERT INTO business_model_changes
            (source_workflow_map_id, change_type, object_id, object_kind, base_object_version_id)
          VALUES
            (${ids.map}, 'refine_object', ${ids.responsibilityObject},
             'responsibility_model', ${ids.responsibilityVersion})
        `,
      );

      await tx`
        INSERT INTO business_processes (id, name, slug)
        VALUES (${ids.legacyProcess}, 'Legacy fixture', 'legacy-fixture')
      `;
      await tx`
        INSERT INTO business_process_versions
          (id, process_id, version_number)
        VALUES (${ids.legacyVersion}, ${ids.legacyProcess}, 1)
      `;
      await tx`
        INSERT INTO business_model_changes
          (source_workflow_map_id, change_type)
        VALUES (${ids.map}, 'create_process')
      `;
      await tx`
        INSERT INTO business_model_changes
          (source_workflow_map_id, change_type, process_id, base_version_id)
        VALUES
          (${ids.map}, 'refine_process', ${ids.legacyProcess}, ${ids.legacyVersion})
      `;
      await expectFailure('dual_target_identity', (fixtureSql) =>
        fixtureSql`
          INSERT INTO business_model_changes
            (source_workflow_map_id, change_type, process_id, base_version_id,
             object_id, object_kind, base_object_version_id)
          VALUES
            (${ids.map}, 'refine_object', ${ids.legacyProcess}, ${ids.legacyVersion},
             ${ids.ruleObject}, 'rule_set', ${ids.ruleVersion})
        `,
      );

      const elements = [
        ['responsibilities', 'responsibility', ids.responsibilityVersion, 'responsibility'],
        ['process', 'step', ids.processVersion, 'process'],
        ['process', 'step', ids.secondProcessVersion, 'process-two'],
        ['ruleset', 'rule', ids.ruleVersion, 'rule'],
        ['reference', 'attribute', ids.referenceVersion, 'reference'],
        ['conversation', 'decision', ids.conversationVersion, 'conversation'],
        ['narrative', 'asserted_fact', ids.narrativeVersion, 'narrative'],
      ] as const;
      const elementIds = new Map<string, string>();
      let elementCounter = 1;
      for (const [shape, kind, versionId, key] of elements) {
        const id = `60000000-0000-4000-8000-${String(elementCounter).padStart(12, '0')}`;
        elementCounter += 1;
        elementIds.set(key, id);
        await tx`
          INSERT INTO business_elements
            (id, version_id, element_key, shape, element_kind, label)
          VALUES (${id}, ${versionId}, ${key}, ${shape}, ${kind}, ${key})
        `;
      }
      const processToId = '60000000-0000-4000-8000-000000000008';
      await tx`
        INSERT INTO business_elements
          (id, version_id, element_key, shape, element_kind, label)
        VALUES
          (${processToId}, ${ids.processVersion}, 'process-to', 'process', 'step', 'to')
      `;

      await tx`
        INSERT INTO business_process_details (element_id, node_type)
        VALUES (${elementIds.get('process')!}, 'step')
      `;
      await tx`
        INSERT INTO business_responsibility_details (element_id, role, action, object)
        VALUES (${elementIds.get('responsibility')!}, 'Sales', 'reviews', 'brief')
      `;
      await tx`
        INSERT INTO business_rule_details (element_id, scope, effect)
        VALUES (${elementIds.get('rule')!}, 'Licensed items', 'Require legal line')
      `;
      await tx`
        INSERT INTO business_reference_details
          (element_id, entity_type, attribute_key, attribute_value, reference_kind)
        VALUES (${elementIds.get('reference')!}, 'product', 'sku', 'ABC-1', 'identifier')
      `;
      await tx`
        INSERT INTO business_conversation_details (element_id, decision_status)
        VALUES (${elementIds.get('conversation')!}, 'confirmed')
      `;
      await tx`
        INSERT INTO business_narrative_macro_details (element_id, macro_kind, goal)
        VALUES (${elementIds.get('narrative')!}, 'goal', 'Reduce revisions')
      `;
      await expectFailure('typed_detail_wrong_shape', (fixtureSql) =>
        fixtureSql`
          INSERT INTO business_process_details (element_id, node_type)
          VALUES (${elementIds.get('responsibility')!}, 'step')
        `,
      );
      await expectFailure('element_wrong_object_kind', (fixtureSql) =>
        fixtureSql`
          INSERT INTO business_elements
            (version_id, element_key, shape, element_kind, label)
          VALUES (${ids.processVersion}, 'wrong-object-shape', 'ruleset', 'rule', 'wrong')
        `,
      );

      const invalidDetailFixtures = [
        `INSERT INTO business_process_details (element_id, node_type)
         VALUES ('60000000-0000-4000-8000-000000000009', '')`,
        `INSERT INTO business_responsibility_details (element_id, role, action, object)
         VALUES ('60000000-0000-4000-8000-000000000010', '', '', '')`,
        `INSERT INTO business_rule_details (element_id, scope, effect)
         VALUES ('60000000-0000-4000-8000-000000000011', '', '')`,
        `INSERT INTO business_reference_details
           (element_id, entity_type, attribute_key, attribute_value, reference_kind)
         VALUES ('60000000-0000-4000-8000-000000000012', '', '', '', '')`,
        `INSERT INTO business_conversation_details (element_id)
         VALUES ('60000000-0000-4000-8000-000000000013')`,
        `INSERT INTO business_narrative_macro_details (element_id, macro_kind)
         VALUES ('60000000-0000-4000-8000-000000000014', '')`,
      ];
      const invalidParents = [
        [ids.processVersion, 'invalid-process', 'process', 'step'],
        [ids.responsibilityVersion, 'invalid-responsibility', 'responsibilities', 'responsibility'],
        [ids.ruleVersion, 'invalid-rule', 'ruleset', 'rule'],
        [ids.referenceVersion, 'invalid-reference', 'reference', 'attribute'],
        [ids.conversationVersion, 'invalid-conversation', 'conversation', 'decision'],
        [ids.narrativeVersion, 'invalid-narrative', 'narrative', 'asserted_fact'],
      ] as const;
      for (let index = 0; index < invalidParents.length; index += 1) {
        const [versionId, key, shape, kind] = invalidParents[index]!;
        const id = `60000000-0000-4000-8000-${String(index + 9).padStart(12, '0')}`;
        await tx`
          INSERT INTO business_elements
            (id, version_id, element_key, shape, element_kind, label)
          VALUES (${id}, ${versionId}, ${key}, ${shape}, ${kind}, ${key})
        `;
        await expectFailure(`invalid_detail_${shape}`, (fixtureSql) =>
          fixtureSql.unsafe(invalidDetailFixtures[index]!),
        );
      }

      await tx`
        INSERT INTO business_relations
          (version_id, relation_key, shape, relation_kind, from_element_key, to_element_key)
        VALUES
          (${ids.processVersion}, 'valid-sequence', 'process', 'sequence', 'process', 'process-to')
      `;
      await expectFailure('relation_wrong_parent_shape', (fixtureSql) =>
        fixtureSql`
          INSERT INTO business_relations
            (version_id, relation_key, shape, relation_kind, from_element_key, to_element_key)
          VALUES
            (${ids.processVersion}, 'wrong-shape', 'ruleset', 'applicability',
             'process', 'process-to')
        `,
      );
      await expectFailure('relation_cross_version_endpoint', (fixtureSql) =>
        fixtureSql`
          INSERT INTO business_relations
            (version_id, relation_key, shape, relation_kind, from_element_key, to_element_key)
          VALUES
            (${ids.processVersion}, 'cross-version', 'process', 'sequence',
             'process', 'process-two')
        `,
      );

      await tx`
        INSERT INTO business_paths
          (version_id, path_key, name, path_type, element_keys_ordered)
        VALUES (${ids.processVersion}, 'main', 'Main', 'main', '["process","process-to"]'::jsonb)
      `;
      await expectFailure('path_non_process', (fixtureSql) =>
        fixtureSql`
          INSERT INTO business_paths
            (version_id, path_key, name, path_type, element_keys_ordered)
          VALUES
            (${ids.responsibilityVersion}, 'invalid', 'Invalid', 'main',
             '["responsibility"]'::jsonb)
        `,
      );

      await tx`
        INSERT INTO recommendations
          (object_id, object_version_id, object_kind, origin, analyzer_key,
           title, narrative, element_keys)
        VALUES
          (${ids.responsibilityObject}, ${ids.responsibilityVersion}, 'responsibility_model',
           'deterministic', 'span-check', 'First', 'First', '["responsibility"]'::jsonb)
      `;
      await expectFailure('recommendation_deterministic_unique', (fixtureSql) =>
        fixtureSql`
          INSERT INTO recommendations
            (object_id, object_version_id, object_kind, origin, analyzer_key,
             title, narrative, element_keys)
          VALUES
            (${ids.responsibilityObject}, ${ids.responsibilityVersion}, 'responsibility_model',
             'deterministic', 'span-check', 'Second', 'Second', '["responsibility"]'::jsonb)
        `,
      );
      await expectFailure('recommendation_version_owner', (fixtureSql) =>
        fixtureSql`
          INSERT INTO recommendations
            (object_id, object_version_id, object_kind, origin, title, narrative)
          VALUES
            (${ids.ruleObject}, ${ids.responsibilityVersion}, 'rule_set',
             'synthesized', 'Wrong owner', 'Wrong owner')
        `,
      );

      await tx`SELECT count(*) FROM business_objects`;
      await tx.savepoint('service_role_read', async (fixtureSql) => {
        await fixtureSql`SET LOCAL ROLE service_role`;
        await fixtureSql`SELECT count(*) FROM business_objects`;
      });
      await expectFailure('authenticated_denied', async (fixtureSql) => {
        await fixtureSql`SET LOCAL ROLE authenticated`;
        await fixtureSql`SELECT count(*) FROM business_objects`;
      });

      throw rollbackProof;
    });
  } catch (error) {
    if (error !== rollbackProof) throw error;
  }

  const fixtureRows = await sql<{ count: number }[]>`
    SELECT count(*)::int AS count
    FROM business_objects
    WHERE id IN ${sql(Object.values(ids).filter((value) => value.startsWith('20000000')))}
  `;
  if (fixtureRows[0]?.count !== 0) throw new Error('R1 transaction fixtures did not roll back.');

  console.log(
    `PASS R1 fresh-DB contract: ${expectedTables.length} RLS tables, ` +
      `${expectedConstraints.length} critical constraints, flags off, valid writes, ` +
      `invalid identities/details/ownership/dedup rejected, roles enforced, rollback clean.`,
  );
} finally {
  await sql.end({ timeout: 5 });
}
