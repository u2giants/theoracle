import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  describeBlockedDropMigration,
  findDeprecatedDropColumns,
  hasDeprecatedEmployeeReader,
  isIgnoredOwnedPath,
  normalizeRepoPath,
} from './identity-cleanup-contract';

export function runIdentityCleanupContractFixtures(): void {
const fixtureDir = dirname(fileURLToPath(import.meta.url));
const liveVerifierSource = readFileSync(resolve(fixtureDir, 'verify-identities.ts'), 'utf8');
assert.match(
  liveVerifierSource,
  /const dependencies = await tx\.unsafe<[\s\S]*?>\(String\.raw`[\s\S]*?\\m[\s\S]*?`\);/,
  'dependency audit SQL must use String.raw before postgres.js receives PostgreSQL regex escapes',
);
assert.doesNotMatch(
  liveVerifierSource,
  /const dependencies = await tx(?:<[\s\S]*?>)?`/,
  'a postgres.js tagged template cannot safely cook PostgreSQL regex escapes',
);
const dependencySqlSource =
  liveVerifierSource.match(
    /const dependencies = await tx\.unsafe<[\s\S]*?>\(String\.raw`([\s\S]*?)`\);/,
  )?.[1] ?? '';
const repetitionBounds = [...dependencySqlSource.matchAll(/\{\d+,(\d+)\}/g)].map((match) =>
  Number(match[1]),
);
assert.ok(repetitionBounds.length > 0, 'dependency SQL must exercise bounded regex coverage');
assert.ok(
  repetitionBounds.every((bound) => bound <= 255),
  `PostgreSQL ARE repetition bounds cannot exceed 255: ${repetitionBounds.join(', ')}`,
);
const readers = [
  `import { employees as staff } from '@oracle/db/schema'; staff.authUserId;`,
  `import * as schema from '@oracle/db/schema'; schema.employees.authProviderSubject;`,
  'SELECT e.auth_user_id FROM public.employees AS e',
  'SELECT auth_provider_subject FROM employees staff',
  'UPDATE employees SET auth_provider = null',
  `UPDATE employees
      SET auth_user_id = NULL
    WHERE EXISTS (SELECT 1 FROM employee_identities ei WHERE ei.employee_id = employees.id)`,
  `INSERT INTO employee_identities (employee_id, auth_user_id)
   SELECT id, auth_user_id FROM employees`,
];
for (const source of readers) {
  assert.equal(hasDeprecatedEmployeeReader('apps/web/example.ts', source), true, source);
}

assert.equal(
  hasDeprecatedEmployeeReader(
    'apps/web/example.ts',
    `import { employees, employeeIdentities } from '@oracle/db/schema';
     employeeIdentities.authUserId; employees.email;`,
  ),
  false,
);
assert.equal(
  hasDeprecatedEmployeeReader(
    'apps/web/example.ts',
    `SELECT e.email, ei.auth_user_id
       FROM employees e
       JOIN employee_identities ei ON ei.employee_id = e.id`,
  ),
  false,
);
assert.equal(
  hasDeprecatedEmployeeReader(
    'apps/web/example.ts',
    `import type { employees as StaffTable } from '@oracle/db/schema';
     type Row = typeof StaffTable;`,
  ),
  false,
);
assert.equal(
  hasDeprecatedEmployeeReader(
    'apps/web/example.ts',
    `-- SELECT auth_user_id FROM employees
     SELECT email FROM employees`,
  ),
  false,
);
assert.equal(
  hasDeprecatedEmployeeReader(
    'packages/db/src/schema.ts',
    `authUserId: uuid('auth_user_id');`,
  ),
  false,
);
assert.equal(
  hasDeprecatedEmployeeReader(
    'packages/db/migrations/sql/40_employee_identities_data.sql',
    'UPDATE employees SET auth_user_id = null',
  ),
  false,
);

assert.equal(normalizeRepoPath('.\\packages\\db\\migrations\\0001.sql'), 'packages/db/migrations/0001.sql');
assert.equal(isIgnoredOwnedPath('packages/db/migrations/0001.sql'), true);
assert.equal(isIgnoredOwnedPath('packages\\db\\migrations\\sql\\40.sql'), true);

assert.deepEqual(
  findDeprecatedDropColumns(
    'ALTER TABLE public.employees DROP COLUMN IF EXISTS auth_user_id, DROP COLUMN auth_provider;',
  ).sort(),
  ['auth_provider', 'auth_user_id'],
);
assert.deepEqual(
  findDeprecatedDropColumns('ALTER TABLE "employees" DROP COLUMN "auth_provider_subject";'),
  ['auth_provider_subject'],
);
assert.deepEqual(
  findDeprecatedDropColumns('ALTER TABLE ONLY public.employees DROP COLUMN auth_user_id;'),
  ['auth_user_id'],
);
assert.deepEqual(
  findDeprecatedDropColumns('-- ALTER TABLE employees DROP COLUMN auth_user_id; SELECT 1;'),
  [],
);
const rawNames = ['40_employee_identities_data.sql', '98_drop_identity_columns.sql'];
assert.match(
  describeBlockedDropMigration(
    'packages/db/migrations/0012_cleanup.sql',
    'ALTER TABLE employees DROP COLUMN auth_user_id;',
    rawNames,
  ) ?? '',
  /generated .* before raw migration 40/,
);
assert.match(
  describeBlockedDropMigration(
    'packages/db/migrations/sql/98_drop_identity_columns.sql',
    'ALTER TABLE employees DROP COLUMN auth_provider;',
    rawNames,
  ) ?? '',
  /before the live GAP-10 proof/,
);
assert.equal(
  describeBlockedDropMigration(
    'packages/db/migrations/sql/98_drop_identity_columns.sql',
    'SELECT 1;',
    rawNames,
  ),
  null,
);

console.log('Identity cleanup contract fixtures: PASS');
}

runIdentityCleanupContractFixtures();
