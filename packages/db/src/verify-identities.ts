// One-off verification script for the D2.multi-identity refactor.
// Reports current employees, their identities, and any orphan state.
//
// Run with: pnpm --filter @oracle/db tsx src/verify-identities.ts
// Safe to delete after the refactor is confirmed working.

import { config as loadEnv } from 'dotenv';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import postgres from 'postgres';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..', '..');
loadEnv({ path: resolve(repoRoot, '.env.local') });
loadEnv({ path: resolve(repoRoot, '.env') });

const url = process.env.DIRECT_URL ?? process.env.DATABASE_URL;
if (!url) {
  throw new Error('DIRECT_URL (or DATABASE_URL) is required.');
}

const sql = postgres(url, { max: 1, prepare: true });

try {
  const employees = await sql`
    SELECT e.id, e.email, e.name, e.is_admin,
           e.auth_user_id AS deprecated_auth_user_id,
           e.auth_provider AS deprecated_auth_provider
    FROM employees e
    ORDER BY e.created_at;
  `;
  console.log('\nemployees rows:');
  console.table(employees);

  const identities = await sql`
    SELECT ei.id, ei.employee_id, e.email AS employee_email,
           ei.auth_provider, ei.email AS identity_email,
           ei.linked_at, ei.last_login_at
    FROM employee_identities ei
    JOIN employees e ON e.id = ei.employee_id
    ORDER BY ei.linked_at;
  `;
  console.log('\nemployee_identities rows:');
  console.table(identities);

  const orphans = await sql`
    SELECT ei.id, ei.employee_id, ei.auth_provider, ei.email
    FROM employee_identities ei
    LEFT JOIN employees e ON e.id = ei.employee_id
    WHERE e.id IS NULL;
  `;
  if (orphans.length > 0) {
    console.error('\nORPHAN identities (no matching employee — should be 0):');
    console.table(orphans);
  } else {
    console.log('\nNo orphan identities. ✓');
  }
} finally {
  await sql.end({ timeout: 5 });
}
