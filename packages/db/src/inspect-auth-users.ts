// One-off — see what Supabase Auth has on file for Albert so we can match
// his M365 identity into the existing employee row. Safe to delete after use.

import { config as loadEnv } from 'dotenv';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import postgres from 'postgres';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..', '..');
loadEnv({ path: resolve(repoRoot, '.env.local') });
loadEnv({ path: resolve(repoRoot, '.env') });

const url = process.env.DIRECT_URL ?? process.env.DATABASE_URL;
if (!url) throw new Error('DIRECT_URL required');
const sql = postgres(url, { max: 1, prepare: true });

try {
  const users = await sql`
    SELECT id, email, raw_app_meta_data->>'provider' AS last_provider,
           raw_app_meta_data->'providers' AS providers,
           email_confirmed_at, last_sign_in_at, created_at
    FROM auth.users
    ORDER BY created_at;
  `;
  console.log('auth.users:');
  console.table(users.map((u) => ({
    id: u.id,
    email: u.email,
    last_provider: u.last_provider,
    providers: JSON.stringify(u.providers),
    last_sign_in_at: u.last_sign_in_at,
  })));
} finally {
  await sql.end({ timeout: 5 });
}
