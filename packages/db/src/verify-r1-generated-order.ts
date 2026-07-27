import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const migrationsDir = resolve(import.meta.dirname, '..', 'migrations');
const generated = await readFile(resolve(migrationsDir, '0010_r1_cross_shape_model.sql'), 'utf8');
const rawOwner = await readFile(
  resolve(migrationsDir, 'sql', '95_r1_cross_shape_constraints.sql'),
  'utf8',
);
const snapshot = await readFile(resolve(migrationsDir, 'meta', '0010_snapshot.json'), 'utf8');

const forbiddenGeneratedFragments = [
  '"owner_department_id" "department"',
  'REFERENCES "public"."departments"',
  'REFERENCES "public"."entities"',
  'REFERENCES "public"."knowledge_top_domains"',
  'ALTER TABLE "business_model_changes"',
  'ALTER TABLE "recommendations"',
];
for (const fragment of forbiddenGeneratedFragments) {
  if (generated.includes(fragment)) {
    throw new Error(
      `0010 depends on a raw-SQL-owned type/table before raw migrations run: ${fragment}`,
    );
  }
}

const requiredRawFragments = [
  'ADD COLUMN IF NOT EXISTS owner_department_id department',
  'business_elements_owner_department_id_departments_id_fk',
  'business_elements_owner_entity_id_entities_id_fk',
  'business_element_systems_entity_id_entities_id_fk',
  'business_object_top_domains_top_domain_id_knowledge_top_domains_id_fk',
  'ADD COLUMN IF NOT EXISTS base_object_version_id uuid',
  'ADD COLUMN IF NOT EXISTS object_version_id uuid',
];
for (const fragment of requiredRawFragments) {
  if (!rawOwner.includes(fragment)) {
    throw new Error(`Migration 95 is missing raw-owned R1 dependency: ${fragment}`);
  }
}

const parsedSnapshot = JSON.parse(snapshot) as {
  tables?: Record<string, { columns?: Record<string, { type?: string }> }>;
};
const ownerDepartmentType =
  parsedSnapshot.tables?.['public.business_elements']?.columns?.owner_department_id?.type;
if (ownerDepartmentType !== 'department') {
  throw new Error(
    `0010 snapshot lost the final owner_department_id type: ${String(ownerDepartmentType)}`,
  );
}

console.log(
  'PASS R1 generated/raw order: 0010 has no early raw-owned references; ' +
    'migration 95 owns the final department/entity/domain dependencies.',
);
