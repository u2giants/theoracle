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
import { KNOWLEDGE_DOMAINS, type KnowledgeDomain } from '@oracle/shared';
import { brainSections, settings, employees } from './schema';

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
  // The approved model pools below are the explicit fallback chain.
  { key: 'default_interview_route', value: 'anthropic/claude-haiku-4-5-20251001', description: 'Conversation model route for chat, review questions, and live interjection drafting.' },
  { key: 'default_extraction_route', value: 'google/gemini-2.5-flash', description: 'Claim extraction model route.' },
  { key: 'default_synthesis_route', value: 'anthropic/claude-sonnet-5', description: 'Deep synthesis model route for Brain and consultant recommendations.' },
  { key: 'model_pool_interview', value: ['anthropic/claude-haiku-4-5-20251001', 'google/gemini-2.5-flash', 'anthropic/claude-sonnet-5'], description: 'Approved conversation model chain, tried in order after the selected primary.' },
  { key: 'model_pool_extraction', value: ['google/gemini-2.5-flash', 'vertex_gemini_2_5_flash_extraction_primary', 'openai/gpt-4.1-mini'], description: 'Approved extraction model chain, tried in order after the selected primary.' },
  { key: 'model_pool_synthesis', value: ['anthropic/claude-sonnet-5', 'google/gemini-2.5-pro', 'openai/gpt-4.1'], description: 'Approved deep-synthesis model chain, tried in order after the selected primary.' },
  { key: 'enforce_model_capabilities', value: true, description: 'When true, model routing rejects configured models that do not meet slot capability requirements.' },
  { key: 'default_vision_route', value: 'qwen/qwen3-vl-235b-a22b-thinking', description: 'Auxiliary image-vision model route for document image transcription.' },
  { key: 'model_pool_vision', value: ['qwen/qwen3-vl-235b-a22b-thinking', 'google/gemini-2.5-flash', 'anthropic/claude-sonnet-5'], description: 'Ordered fallback chain for image vision transcription.' },
  { key: 'default_workflow_read_route', value: 'openai/gpt-4.1', description: 'Macro-first source workflow read model route. OpenAI first: the 2026-07-07 Stage 2 gate found claude-sonnet-5 rejects the adapter temperature parameter and Gemini 2.5 Pro rejects the schema as too complex.' },
  { key: 'model_pool_workflow_read', value: ['openai/gpt-4.1', 'anthropic/claude-sonnet-5', 'google/gemini-2.5-pro'], description: 'Ordered fallback chain for source workflow read. OpenAI first based on the live Stage 2 gate.' },
  { key: 'default_model_merge_route', value: 'openai/gpt-4.1-mini', description: 'Macro-first business-model merge alignment model route.' },
  { key: 'model_pool_model_merge', value: ['openai/gpt-4.1-mini', 'google/gemini-2.5-flash', 'anthropic/claude-haiku-4-5-20251001'], description: 'Ordered fallback chain for business-model merge alignment.' },
  { key: 'default_general_purpose_route', value: 'qwen/qwen3.7-max', description: 'Auxiliary general-purpose model route for internal utility jobs.' },
  { key: 'model_pool_general', value: ['qwen/qwen3.7-max', 'anthropic/claude-haiku-4-5-20251001', 'google/gemini-2.5-flash'], description: 'Ordered fallback chain for general utility tasks.' },
  { key: 'default_macro_route', value: 'openai/gpt-4.1-mini', description: 'Macro/holistic-layer model (source outlines, macro relationship extraction, coverage audits). Requires strict structured-output support. Gemini rejects the nested schemas (400 too-complex) — use an OpenAI strict-json-schema model.' },
  { key: 'model_pool_macro', value: ['openai/gpt-4.1-mini', 'openai/gpt-4.1', 'google/gemini-2.5-pro'], description: 'Ordered fallback chain for the macro slot. OpenAI first — Gemini rejects the nested macro schemas.' },
  { key: 'default_translation_route', value: 'qwen/qwen-mt-plus', description: 'Auxiliary translation model route for bilingual claim rendering and review questions.' },
  { key: 'model_pool_translation', value: ['qwen/qwen-mt-plus', 'qwen/qwen3.7-max', 'google/gemini-2.5-flash'], description: 'Ordered fallback chain for translation.' },
  { key: 'serve_provisional_process_elements', value: true, description: 'When true, chat may serve process elements with unapproved support as explicitly provisional.' },
  { key: 'workflow_map_max_dropped_ratio', value: 0.2, description: 'Maximum dropped workflow-map element ratio before a validated map is marked degraded.' },
  { key: 'model_merge_min_alignment_confidence', value: 70, description: 'Minimum confidence score for accepting a source-map to business-model alignment.' },
  { key: 'merge_candidate_top_k', value: 5, description: 'Internal domain-scoped process shortlist width for business-model merge.' },
  { key: 'process_match_top_k', value: 2, description: 'Number of business processes to render into chat context.' },
  { key: 'workflow_read_max_estimated_input_tokens', value: 150000, description: 'Estimated-token threshold above which workflow read uses sequential windows instead of one call.' },
  { key: 'extraction_char_budget', value: 24000, description: 'Approximate max characters of active conversation text selected per extraction run before stopping at a conversation boundary.' },
  { key: 'extraction_carry_in_count', value: 12, description: 'Prior complete/skipped same-channel messages included as non-quotable context for message extraction.' },
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

function titleCaseDomain(domain: string): string {
  return domain
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

const DEFAULT_BRAIN_SECTIONS = KNOWLEDGE_DOMAINS.map((domain) => ({
  id: `domain-${domain}`,
  knowledgeDomain: domain as KnowledgeDomain,
  title: `${titleCaseDomain(domain)} Brain`,
  category: 'domain',
}));

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

    // Settings — fill missing defaults, but never reset runtime/admin choices.
    // Migrations call seed inline; overwriting values here caused prod model
    // routes to drift back to legacy defaults during a test-plan migration run.
    for (const s of DEFAULT_SETTINGS) {
      await db
        .insert(settings)
        .values({ key: s.key, value: s.value as never, description: s.description })
        .onConflictDoUpdate({
          target: settings.key,
          set: { description: s.description },
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

    // Brain sections — synthesis needs at least one target section. Seed one
    // stable section per legacy knowledge domain; versions remain model-owned.
    await db
      .insert(brainSections)
      .values(DEFAULT_BRAIN_SECTIONS)
      .onConflictDoNothing({ target: brainSections.id });

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
