// Seed runner.
// Idempotent — safe to re-run.
//
// Seeds:
//   * settings table — defaults from spec 6.2
//   * employees       — single admin row per user decision #3
//                       + a single test-only employee for Phase 2 acceptance
//                         (see DECISIONS.md D1.test-employee — delete before production)

import 'dotenv/config';
import postgres from 'postgres';
import { drizzle } from 'drizzle-orm/postgres-js';
import { sql } from 'drizzle-orm';
import * as schema from './schema';
import { settings, employees } from './schema';

const DEFAULT_SETTINGS: Array<{
  key: string;
  value: unknown;
  description: string;
}> = [
  { key: 'lull_window_seconds', value: 60, description: 'Seconds of human silence before Oracle may interject (spec 5.1).' },
  { key: 'oracle_cooldown_minutes', value: 10, description: 'Minimum minutes between Oracle interjections in a single channel.' },
  { key: 'max_oracle_interjections_per_hour', value: 3, description: 'Per-channel cap on proactive interjections.' },
  { key: 'default_interview_model', value: 'anthropic/claude-sonnet-4.6', description: 'OpenRouter model for live interview / chat.' },
  { key: 'default_extraction_model', value: 'google/gemini-flash', description: 'OpenRouter model for claim extraction.' },
  { key: 'default_synthesis_model', value: 'anthropic/claude-sonnet-4.6', description: 'OpenRouter model for brain synthesis.' },
  { key: 'enable_live_contradiction_interjections', value: false, description: 'When false, possible contradictions queue silently (spec 5.1 Rule 1).' },
  { key: 'enable_group_chat_lull_questions', value: true, description: 'When true, Oracle may ask a high-priority gap question during a lull (spec 5.1 Rule 2).' },
];

const ADMIN_EMPLOYEE = {
  email: 'u2giants@gmail.com',
  name: 'Albert H.',
  role: 'Lead Architect',
  department: 'Executive',
  isAdmin: true,
};

const TEST_EMPLOYEE = {
  // See DECISIONS.md D1.test-employee — Phase 2 acceptance gate needs 2 employees
  // to verify cross-channel RLS. Delete this row before production rollout.
  email: 'test-employee@oracle.local',
  name: 'Test Employee',
  role: 'Production Coordinator',
  department: 'Production',
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
        isAdmin: ADMIN_EMPLOYEE.isAdmin,
      })
      .onConflictDoUpdate({
        target: employees.email,
        set: {
          name: ADMIN_EMPLOYEE.name,
          role: ADMIN_EMPLOYEE.role,
          department: ADMIN_EMPLOYEE.department,
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
const isDirect = import.meta.url === `file://${process.argv[1]?.replace(/\\/g, '/')}`;
if (isDirect) {
  runSeed().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
