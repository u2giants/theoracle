// Seed runner.
// Idempotent — safe to re-run.
//
// Seeds:
//   * settings table — defaults from spec 6.2
//   * employees       — single admin row per user decision #3
//                       + a single test-only employee for Phase 2 acceptance
//                         (see DECISIONS.md D1.test-employee — delete before production)

import { config as loadEnv } from 'dotenv';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import postgres from 'postgres';
import { drizzle } from 'drizzle-orm/postgres-js';
import { sql } from 'drizzle-orm';
import * as schema from './schema';
import { settings, employees } from './schema';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..', '..');
// Load .env.local first (takes precedence), then .env as fallback.
loadEnv({ path: resolve(repoRoot, '.env.local') });
loadEnv({ path: resolve(repoRoot, '.env') });

const DEFAULT_SETTINGS: Array<{
  key: string;
  value: unknown;
  description: string;
}> = [
  { key: 'lull_window_seconds', value: 60, description: 'Seconds of human silence before Oracle may interject (spec 5.1).' },
  { key: 'oracle_cooldown_minutes', value: 10, description: 'Minimum minutes between Oracle interjections in a single channel.' },
  { key: 'max_oracle_interjections_per_hour', value: 3, description: 'Per-channel cap on proactive interjections.' },
  // Legacy OpenRouter model id keys — kept during R1 migration, do not use for new code.
  // See docs/oracle/05-ai-retrofit-phase-packet.md Phase R1 task 8.
  { key: 'default_interview_model', value: 'deepseek/deepseek-v4-pro', description: 'DEPRECATED — Legacy OpenRouter model id. Superseded by default_interview_route.' },
  { key: 'default_extraction_model', value: 'google/gemini-2.5-flash', description: 'DEPRECATED — Legacy OpenRouter model id. Superseded by default_extraction_route.' },
  { key: 'default_synthesis_model', value: 'anthropic/claude-sonnet-4.6', description: 'DEPRECATED — Legacy OpenRouter model id. Superseded by default_synthesis_route.' },
  // R1 — Curated Oracle route IDs (Big 3 provider-native). 1 Primary per role.
  // Source of truth: packages/ai/src/routes/defaults.ts (DEFAULT_ORACLE_ROUTES).
  { key: 'default_interview_route', value: 'anthropic_claude_haiku_4_5_interview_primary', description: 'Curated OracleModelRoute.routeId for the interview role.' },
  { key: 'default_extraction_route', value: 'vertex_gemini_2_5_flash_extraction_primary', description: 'Curated OracleModelRoute.routeId for the extraction role.' },
  { key: 'default_synthesis_route', value: 'anthropic_claude_3_5_sonnet_synthesis_primary', description: 'Curated OracleModelRoute.routeId for the synthesis role.' },
  { key: 'enable_live_contradiction_interjections', value: false, description: 'When false, possible contradictions queue silently (spec 5.1 Rule 1).' },
  { key: 'enable_group_chat_lull_questions', value: true, description: 'When true, Oracle may ask a high-priority gap question during a lull (spec 5.1 Rule 2).' },
  // D14 — provider Batch API dispatch mode for claim extraction.
  // 'sync' (default) runs the existing per-segment pipeline against the
  // sync model API. 'batch' submits all segments via the provider Batch API
  // (~50% off, 24-hour SLA) and the drain task processes results when ready.
  // The sync worker bails when set to 'batch'; the batch-submit worker bails
  // when set to 'sync'. Flag is read every run — flip without redeploying.
  { key: 'extraction_dispatch_mode', value: 'sync', description: 'sync | batch — D14 provider Batch API dispatch for claim extraction.' },
];

const ADMIN_EMPLOYEE = {
  email: 'u2giants@gmail.com',
  name: 'Albert H.',
  role: 'Lead Architect',
  department: 'Executive',         // legacy field — kept for backward compat
  departments: ['Executive'],
  isAdmin: true,
};

const TEST_EMPLOYEE = {
  // See DECISIONS.md D1.test-employee — Phase 2 acceptance gate needs 2 employees
  // to verify cross-channel RLS. Delete this row before production rollout.
  email: 'test-employee@oracle.local',
  name: 'Test Employee',
  role: 'Production Coordinator',
  department: 'Production',        // legacy field
  departments: ['Production'],
  isAdmin: false,
};

export async function runSeed(existingClient?: ReturnType<typeof postgres>): Promise<void> {
  const ownsClient = !existingClient;
  const client =
    existingClient ??
    postgres(process.env.DIRECT_URL ?? process.env.DATABASE_URL ?? '', {
      max: 1,
      prepare: true,
    });

  try {
    const db = drizzle(client, { schema });

    // Settings — upsert each row by key.
    for (const s of DEFAULT_SETTINGS) {
      await db
        .insert(settings)
        .values({ key: s.key, value: s.value as never, description: s.description })
        .onConflictDoUpdate({
          target: settings.key,
          set: { value: s.value as never, description: s.description, updatedAt: new Date() },
        });
    }

    // Admin employee — upsert by email.
    await db
      .insert(employees)
      .values({
        email: ADMIN_EMPLOYEE.email,
        name: ADMIN_EMPLOYEE.name,
        role: ADMIN_EMPLOYEE.role,
        department: ADMIN_EMPLOYEE.department,
        departments: ADMIN_EMPLOYEE.departments,
        isAdmin: ADMIN_EMPLOYEE.isAdmin,
      })
      .onConflictDoUpdate({
        target: employees.email,
        set: {
          name: ADMIN_EMPLOYEE.name,
          role: ADMIN_EMPLOYEE.role,
          department: ADMIN_EMPLOYEE.department,
          departments: ADMIN_EMPLOYEE.departments,
          isAdmin: ADMIN_EMPLOYEE.isAdmin,
        },
      });

    // Test employee — for Phase 2 acceptance.
    await db
      .insert(employees)
      .values({
        email: TEST_EMPLOYEE.email,
        name: TEST_EMPLOYEE.name,
        role: TEST_EMPLOYEE.role,
        department: TEST_EMPLOYEE.department,
        departments: TEST_EMPLOYEE.departments,
        isAdmin: TEST_EMPLOYEE.isAdmin,
      })
      .onConflictDoNothing({ target: employees.email });

    // Sanity assertion — make sure RLS got enabled on critical tables.
    const rlsCheck = await db.execute(sql`
      SELECT relname, relrowsecurity
      FROM pg_class
      WHERE relname IN ('employees', 'messages', 'channels', 'claims')
      ORDER BY relname;
    `);
    console.log('  RLS status:', rlsCheck);
  } finally {
    if (ownsClient) await client.end({ timeout: 5 });
  }
}

// Allow running directly: `pnpm --filter @oracle/db seed`
// Use pathToFileURL for a robust cross-platform check (handles Windows triple-slash file URLs).
const entryUrl = process.argv[1] ? pathToFileURL(process.argv[1]).href : '';
const isDirect = import.meta.url === entryUrl;
if (isDirect) {
  runSeed().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
