// GAP-10 identity cleanup gate.
//
// Contract-only (safe offline):
//   pnpm --filter @oracle/db verify:identity-cleanup -- --contract-only
//
// Live database audit (read-only transaction, aggregate output only):
//   pnpm --filter @oracle/db verify:identity-cleanup
//
// The live audit intentionally fails while deprecated data or inbound database
// dependencies remain. It never prints employee or identity values.

import { config as loadEnv } from 'dotenv';
import { readFile, readdir } from 'node:fs/promises';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import postgres from 'postgres';
import './verify-identity-cleanup-contract';
import {
  classifyLegacyIdentityColumnState,
  describeBlockedDropMigration,
  GAP10_FINAL_RELEASE_PROOF,
  hasDeprecatedEmployeeReader,
  isIgnoredOwnedPath,
  repoRelative,
} from './identity-cleanup-contract';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..', '..');
const contractOnly = process.argv.includes('--contract-only');

const ownedRoots = ['apps', 'packages', 'scripts'];
const sourceExtensions = new Set(['.ts', '.tsx', '.js', '.mjs', '.cjs', '.sql']);

async function walk(path: string): Promise<string[]> {
  const entries = await readdir(path, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const child = join(path, entry.name);
    const rel = repoRelative(repoRoot, child);
    if (isIgnoredOwnedPath(rel)) continue;
    if (entry.isDirectory()) files.push(...(await walk(child)));
    else if (sourceExtensions.has(extname(entry.name))) files.push(child);
  }
  return files;
}

async function verifyOwnedReaders(): Promise<void> {
  const violations: string[] = [];
  for (const root of ownedRoots) {
    for (const path of await walk(resolve(repoRoot, root))) {
      const source = await readFile(path, 'utf8');
      const rel = repoRelative(repoRoot, path);
      if (hasDeprecatedEmployeeReader(rel, source)) {
        violations.push(rel);
      }
    }
  }
  if (violations.length > 0) {
    throw new Error(
      `Deprecated employees identity-column reader(s) found: ${violations.join(', ')}`,
    );
  }
  console.log('Owned reader guard: PASS');
}

async function verifyMigrationOrder(): Promise<void> {
  const sqlDir = resolve(repoRoot, 'packages', 'db', 'migrations', 'sql');
  const generatedDir = resolve(repoRoot, 'packages', 'db', 'migrations');
  const names = (await readdir(sqlDir)).filter((name) => name.endsWith('.sql')).sort();
  const backfillIndex = names.indexOf('40_employee_identities_data.sql');
  if (backfillIndex < 0) throw new Error('Identity backfill migration 40 is missing.');

  const violations: string[] = [];
  const generatedNames = (await readdir(generatedDir)).filter((name) => name.endsWith('.sql'));
  for (const name of generatedNames) {
    const violation = describeBlockedDropMigration(
      `packages/db/migrations/${name}`,
      await readFile(join(generatedDir, name), 'utf8'),
      names,
    );
    if (violation) violations.push(violation);
  }
  for (const name of names) {
    const violation = describeBlockedDropMigration(
      `packages/db/migrations/sql/${name}`,
      await readFile(join(sqlDir, name), 'utf8'),
      names,
    );
    if (violation) violations.push(violation);
  }
  if (violations.length > 0) {
    throw new Error(`Deprecated identity-column drop is blocked:\n${violations.join('\n')}`);
  }
  console.log('Migration order guard: PASS');
}

await verifyOwnedReaders();
await verifyMigrationOrder();

if (contractOnly) process.exit(0);

loadEnv({ path: resolve(repoRoot, '.env.local'), quiet: true });
loadEnv({ path: resolve(repoRoot, '.env'), quiet: true });
const url = process.env.DIRECT_URL ?? process.env.DATABASE_URL;
if (!url) {
  throw new Error(
    'DIRECT_URL (or DATABASE_URL) is required for the read-only live identity cleanup gate.',
  );
}

const sql = postgres(url, { max: 1, prepare: false });
try {
  const liveState = await sql.begin('read only', async (tx) => {
    const legacyColumnRows = await tx<{ attname: string }[]>`
      SELECT attname
      FROM pg_attribute
      WHERE attrelid = 'public.employees'::regclass
        AND attname IN ('auth_user_id', 'auth_provider', 'auth_provider_subject')
        AND NOT attisdropped
      ORDER BY attname
    `;
    const columnState = classifyLegacyIdentityColumnState(
      legacyColumnRows.map((row) => row.attname),
    );
    if (columnState === 'post-drop') {
      console.log(
        JSON.stringify(
          {
            postDrop: true,
            deprecatedColumnsPresent: [],
            finalReleaseCommit: GAP10_FINAL_RELEASE_PROOF.commit,
          },
          null,
          2,
        ),
      );
      return columnState;
    }

    const countRows = await tx<{
      employees_total: number;
      auth_user_id_non_null: number;
      auth_provider_non_null: number;
      auth_provider_subject_non_null: number;
    }[]>`
      SELECT
        count(*)::int AS employees_total,
        count(auth_user_id)::int AS auth_user_id_non_null,
        count(auth_provider)::int AS auth_provider_non_null,
        count(auth_provider_subject)::int AS auth_provider_subject_non_null
      FROM public.employees
    `;
    const counts = countRows[0];
    if (!counts) throw new Error('Identity cleanup count query returned no row.');

    // String.raw is required here. PostgreSQL regex escapes such as \m and \M
    // make a JavaScript tagged template's cooked segment undefined, which
    // postgres.js serializes into invalid SQL.
    const dependencies = await tx.unsafe<
      { dependency_type: string; object_name: string }[]
    >(String.raw`
      WITH deprecated_columns AS (
        SELECT attrelid, attnum, attname
        FROM pg_attribute
        WHERE attrelid = 'public.employees'::regclass
          AND attname IN ('auth_user_id', 'auth_provider', 'auth_provider_subject')
          AND NOT attisdropped
      ),
      catalog_dependencies AS (
        SELECT
          'pg_depend'::text AS dependency_type,
          pg_describe_object(d.classid, d.objid, d.objsubid) AS object_name
        FROM pg_depend d
        JOIN deprecated_columns c
          ON c.attrelid = d.refobjid
         AND c.attnum = d.refobjsubid
        WHERE d.deptype <> 'i'
          AND NOT (
            d.classid = 'pg_constraint'::regclass
            AND EXISTS (
              SELECT 1 FROM pg_constraint local_constraint
              WHERE local_constraint.oid = d.objid
                AND local_constraint.conrelid = 'public.employees'::regclass
            )
          )
          AND NOT (
            d.classid = 'pg_class'::regclass
            AND EXISTS (
              SELECT 1 FROM pg_index local_index
              WHERE local_index.indexrelid = d.objid
                AND local_index.indrelid = 'public.employees'::regclass
            )
          )
      ),
      policy_dependencies AS (
        SELECT
          'policy'::text,
          format('%I.%I on %I.%I', pn.nspname, p.polname, tn.nspname, t.relname)
        FROM pg_policy p
        JOIN pg_class t ON t.oid = p.polrelid
        JOIN pg_namespace tn ON tn.oid = t.relnamespace
        JOIN pg_namespace pn ON pn.oid = t.relnamespace
        WHERE (
          p.polrelid = 'public.employees'::regclass
          AND concat_ws(' ', pg_get_expr(p.polqual, p.polrelid), pg_get_expr(p.polwithcheck, p.polrelid))
            ~* '\m(auth_user_id|auth_provider_subject|auth_provider)\M'
        ) OR concat_ws(' ', pg_get_expr(p.polqual, p.polrelid), pg_get_expr(p.polwithcheck, p.polrelid))
          ~* '\memployees\.(auth_user_id|auth_provider_subject|auth_provider)\M'
      ),
      function_dependencies AS (
        SELECT
          'function'::text,
          format('%I.%I(%s)', n.nspname, p.proname, pg_get_function_identity_arguments(p.oid))
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND p.prokind IN ('f', 'p')
          AND (
            pg_get_functiondef(p.oid)
              ~* '\memployees\.(auth_user_id|auth_provider_subject|auth_provider)\M'
            OR pg_get_functiondef(p.oid)
              ~* '\mupdate\s+(public\.)?employees\s+set\s+(auth_user_id|auth_provider_subject|auth_provider)\M'
            OR pg_get_functiondef(p.oid)
              ~* '\m(from|join)\s+(public\.)?employees\s+(as\s+)?([a-z_][a-z0-9_]*)[^;]{0,255}[^;]{0,255}[^;]{0,255}[^;]{0,255}[^;]{0,255}[^;]{0,255}[^;]{0,255}[^;]{0,255}\4\.(auth_user_id|auth_provider_subject|auth_provider)\M'
          )
      ),
      trigger_dependencies AS (
        SELECT
          'trigger'::text,
          format('%I on %I.%I', tg.tgname, n.nspname, c.relname)
        FROM pg_trigger tg
        JOIN pg_class c ON c.oid = tg.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE NOT tg.tgisinternal
          AND (
            (
              tg.tgrelid = 'public.employees'::regclass
              AND pg_get_triggerdef(tg.oid)
                ~* '\m(auth_user_id|auth_provider_subject|auth_provider)\M'
            )
            OR pg_get_triggerdef(tg.oid)
              ~* '\memployees\.(auth_user_id|auth_provider_subject|auth_provider)\M'
          )
      ),
      rule_dependencies AS (
        SELECT
          CASE WHEN c.relkind IN ('v', 'm') THEN 'view' ELSE 'rewrite_rule' END::text,
          format('%I.%I', n.nspname, c.relname)
        FROM pg_rewrite r
        JOIN pg_class c ON c.oid = r.ev_class
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE pg_get_ruledef(r.oid)
            ~* '\memployees\.(auth_user_id|auth_provider_subject|auth_provider)\M'
           OR pg_get_ruledef(r.oid)
            ~* '\m(from|join)\s+(public\.)?employees\s+(as\s+)?([a-z_][a-z0-9_]*)[^;]{0,255}[^;]{0,255}[^;]{0,255}[^;]{0,255}[^;]{0,255}[^;]{0,255}[^;]{0,255}[^;]{0,255}\4\.(auth_user_id|auth_provider_subject|auth_provider)\M'
      ),
      index_dependencies AS (
        SELECT
          CASE WHEN i.indrelid = 'public.employees'::regclass
            THEN 'local_index' ELSE 'external_index' END::text,
          format('%I.%I', n.nspname, c.relname)
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE EXISTS (
          SELECT 1
          FROM deprecated_columns dc
          WHERE dc.attnum = ANY(i.indkey)
            AND dc.attrelid = i.indrelid
        )
      ),
      constraint_dependencies AS (
        SELECT
          CASE WHEN con.conrelid = 'public.employees'::regclass
            THEN 'local_constraint' ELSE 'external_constraint' END::text,
          format('%I on %s', con.conname, con.conrelid::regclass)
        FROM pg_constraint con
        WHERE EXISTS (
          SELECT 1
          FROM deprecated_columns dc
          WHERE (dc.attnum = ANY(con.conkey) AND dc.attrelid = con.conrelid)
             OR (dc.attnum = ANY(con.confkey) AND dc.attrelid = con.confrelid)
        )
      )
      SELECT DISTINCT dependency_type, object_name
      FROM (
        SELECT * FROM catalog_dependencies
        UNION ALL SELECT * FROM policy_dependencies
        UNION ALL SELECT * FROM function_dependencies
        UNION ALL SELECT * FROM trigger_dependencies
        UNION ALL SELECT * FROM rule_dependencies
        UNION ALL SELECT * FROM index_dependencies
        UNION ALL SELECT * FROM constraint_dependencies
      ) dependencies
      ORDER BY dependency_type, object_name
    `);

    console.log(
      JSON.stringify(
        {
          employeesTotal: counts.employees_total,
          deprecatedNonNull: {
            authUserId: counts.auth_user_id_non_null,
            authProvider: counts.auth_provider_non_null,
            authProviderSubject: counts.auth_provider_subject_non_null,
          },
          inboundDependencyCount: dependencies.length,
          inboundDependencies: dependencies,
        },
        null,
        2,
      ),
    );

    const nonNullTotal =
      counts.auth_user_id_non_null +
      counts.auth_provider_non_null +
      counts.auth_provider_subject_non_null;
    const blockingDependencies = dependencies.filter(
      (row) => !['local_index', 'local_constraint'].includes(row.dependency_type),
    );
    if (nonNullTotal > 0 || blockingDependencies.length > 0) {
      throw new Error(
        `Identity cleanup gate failed: deprecated data or ${blockingDependencies.length} external/inbound dependencies remain.`,
      );
    }
    return columnState;
  });
  console.log(
    liveState === 'post-drop'
      ? 'Post-drop identity cleanup gate: PASS'
      : 'Live pre-drop identity cleanup gate: PASS',
  );
} finally {
  await sql.end({ timeout: 5 });
}
