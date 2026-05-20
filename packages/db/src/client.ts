// Postgres clients for The Oracle.
//
// Per spec 3.4:
// - Migrations and Trigger.dev workers use DIRECT_URL (unpooled).
// - Vercel route handlers should use DATABASE_URL (Supavisor pooler) with
//   prepared statements disabled.
//
// We export two flavours so callers pick deliberately:
//
//   import { getDirectDb } from '@oracle/db/client';   // migrations, workers
//   import { getPooledDb } from '@oracle/db/client';   // route handlers
//
// Both are lazily constructed so `import`ing this module never connects.

import { drizzle } from 'drizzle-orm/postgres-js';
import type { PostgresJsDatabase } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import * as schema from './schema';

type OracleDb = PostgresJsDatabase<typeof schema>;

let directDb: OracleDb | null = null;
let pooledDb: OracleDb | null = null;

function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v) {
    throw new Error(
      `Missing required env var ${name}. ` +
        `Check .env.local — see DECISIONS.md D0.4 for the blocker on empty Vercel secrets.`,
    );
  }
  return v;
}

export function getDirectDb(): OracleDb {
  if (directDb) return directDb;
  const url = requireEnv('DIRECT_URL');
  const client = postgres(url, {
    max: 1,
    prepare: true,
    // Drizzle's postgres-js driver works fine with prepared statements on a
    // direct (unpooled) connection. The pool below disables prepare.
  });
  directDb = drizzle(client, { schema });
  return directDb;
}

export function getPooledDb(): OracleDb {
  if (pooledDb) return pooledDb;
  const url = process.env.DATABASE_URL ?? process.env.DIRECT_URL;
  if (!url) {
    throw new Error(
      'Missing DATABASE_URL (Supavisor pooler). ' +
        'For route handlers we prefer the pooler. See DECISIONS.md D0.4.',
    );
  }
  const client = postgres(url, {
    max: 1,
    // Spec 3.4: disable prepared statements when going through the transaction pooler.
    prepare: false,
  });
  pooledDb = drizzle(client, { schema });
  return pooledDb;
}

export { schema };
