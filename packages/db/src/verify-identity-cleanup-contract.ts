import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  AUTHORIZED_IDENTITY_DROP_MIGRATION,
  GAP10_ROLLBACK_PROOF,
  describeBlockedDropMigration,
  findDeprecatedDropColumns,
  hasDeprecatedEmployeeReader,
  isIgnoredOwnedPath,
  normalizeRepoPath,
  shouldSkipRawMigration,
  validateAuthorizedIdentityDropMigration,
} from './identity-cleanup-contract';

export function runIdentityCleanupContractFixtures(): void {
assert.deepEqual(GAP10_ROLLBACK_PROOF, {
  commit: '53047981e2580bbba56451aaf4aeb034d9a92b3b',
  ciRun: '30424102001',
  deployment: 'dpl_7MVqENiyLL3FeQCiB9f4vmTiMCQq',
});
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
const rawNames = readdirSync(resolve(fixtureDir, '..', 'migrations', 'sql'))
  .filter((name) => name.endsWith('.sql'))
  .sort();
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
    AUTHORIZED_IDENTITY_DROP_MIGRATION,
    'ALTER TABLE employees DROP COLUMN auth_provider;',
    rawNames,
  ) ?? '',
  /authorized GAP-10 migration is invalid/,
);
assert.equal(
  describeBlockedDropMigration(
    'packages/db/migrations/sql/98_drop_identity_columns.sql',
    'SELECT 1;',
    rawNames,
  ),
  null,
);
const authorizedDropSql = readFileSync(
  resolve(fixtureDir, '..', 'migrations', 'sql', '98_drop_deprecated_employee_identity_columns.sql'),
  'utf8',
);
assert.deepEqual(validateAuthorizedIdentityDropMigration(authorizedDropSql), []);
assert.equal(
  describeBlockedDropMigration(AUTHORIZED_IDENTITY_DROP_MIGRATION, authorizedDropSql, rawNames),
  null,
);
assert.ok(
  rawNames.indexOf('98_drop_deprecated_employee_identity_columns.sql') >
    rawNames.indexOf('40_employee_identities_data.sql'),
);
assert.ok(
  rawNames.indexOf('98_drop_deprecated_employee_identity_columns.sql') <
    rawNames.indexOf('99_vector_indexes.sql'),
);
assert.match(
  describeBlockedDropMigration(
    'packages/db/migrations/sql/97_unapproved_drop.sql',
    authorizedDropSql,
    rawNames,
  ) ?? '',
  /before migration 40|before the live GAP-10 proof/,
);
assert.match(
  validateAuthorizedIdentityDropMigration(
    `${authorizedDropSql}\nALTER TABLE public.employees DROP COLUMN IF EXISTS email;`,
  ).join('; '),
  /unrelated employees columns: email/,
);

assert.equal(shouldSkipRawMigration('40_employee_identities_data.sql', true), false);
assert.equal(shouldSkipRawMigration('40_employee_identities_data.sql', false), true);
assert.equal(shouldSkipRawMigration('41_albert_post_merge_fix.sql', false), false);
assert.throws(
  () => shouldSkipRawMigration('40_employee_identities_data.sql', undefined),
  /state is unknown/,
);

// Mock the state transition across the relevant raw sequence. On the first
// pass, 40 must run before 98. On the second pass, only 40 is skipped and the
// rerun-safe 98 executes again.
function simulateIdentityRawSequence(initialColumnExists: boolean): {
  ran: string[];
  skipped: string[];
} {
  let columnExists = initialColumnExists;
  const ran: string[] = [];
  const skipped: string[] = [];
  for (const name of rawNames.filter((candidate) => candidate !== '99_vector_indexes.sql')) {
    if (shouldSkipRawMigration(name, columnExists)) {
      skipped.push(name);
      continue;
    }
    ran.push(name);
    if (name === '98_drop_deprecated_employee_identity_columns.sql') columnExists = false;
  }
  return { ran, skipped };
}
const firstPass = simulateIdentityRawSequence(true);
assert.ok(firstPass.ran.indexOf('40_employee_identities_data.sql') < firstPass.ran.indexOf('98_drop_deprecated_employee_identity_columns.sql'));
assert.deepEqual(firstPass.skipped, []);
const secondPass = simulateIdentityRawSequence(false);
assert.deepEqual(secondPass.skipped, ['40_employee_identities_data.sql']);
assert.ok(secondPass.ran.includes('98_drop_deprecated_employee_identity_columns.sql'));

const migrateSource = readFileSync(resolve(fixtureDir, 'migrate.ts'), 'utf8');
assert.match(
  migrateSource,
  /if \(f === '40_employee_identities_data\.sql'\)[\s\S]*await legacyAuthUserIdColumnExists\(client\)[\s\S]*shouldSkipRawMigration\(f, columnExists\)/,
);

console.log('Identity cleanup contract fixtures: PASS');
}

runIdentityCleanupContractFixtures();
