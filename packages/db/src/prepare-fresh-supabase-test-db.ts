/**
 * Prepare an empty local Postgres database with the Supabase-owned primitives
 * that application migrations legitimately depend on.
 *
 * This is CI/test support only. It refuses non-loopback hosts and any database
 * not named oracle_fresh so it cannot mutate production by accident.
 */
import postgres from 'postgres';

const url = process.env.DIRECT_URL ?? process.env.DATABASE_URL;
if (!url) throw new Error('DIRECT_URL or DATABASE_URL is required.');

const parsed = new URL(url);
if (!['localhost', '127.0.0.1', '::1'].includes(parsed.hostname)) {
  throw new Error(`Refusing Supabase test bootstrap on non-loopback host ${parsed.hostname}.`);
}
if (parsed.pathname.replace(/^\//, '') !== 'oracle_fresh') {
  throw new Error(`Refusing Supabase test bootstrap outside oracle_fresh: ${parsed.pathname}.`);
}

const sql = postgres(url, { max: 1, prepare: false });
try {
  await sql.unsafe(`
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN;
      END IF;
    END
    $$;

    CREATE SCHEMA IF NOT EXISTS auth;

    CREATE OR REPLACE FUNCTION auth.uid()
    RETURNS uuid
    LANGUAGE sql
    STABLE
    AS $$ SELECT NULL::uuid $$;

    GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
    GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated, service_role;
  `);
  console.log('PASS fresh Supabase test prerequisites');
} finally {
  await sql.end({ timeout: 5 });
}
