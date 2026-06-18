// Claim recertification worker (china_imp.md / verify-selected-claims feature).
//
// Given an approved claim and a target (a specific employee, a department, or a
// locale group like the China team), drafts a short "is this still accurate?"
// question and records it as a GAP (gap_type='claim_recertification') so it
// surfaces to the target through the existing gap machinery (getRelevantOpenGaps
// injects it into the target's next Oracle chat; lull-interjection can post it).
//
// Reuses the gaps table — no schema change. The employee's reply flows through
// the normal extraction pipeline (evidence / a new or contradicting claim), and
// an admin resolves the gap via /admin/gaps.
//
// Idempotent: skips creating a duplicate when an OPEN recertification gap for the
// same (claim, target) already exists. All drafting goes through OracleAIClient.

import { task } from '@trigger.dev/sdk/v3';
import { and, eq, isNull, sql } from 'drizzle-orm';
import { z } from 'zod';
import { getDirectDb } from '@oracle/db/client';
import { claims, employees, gaps } from '@oracle/db';
import {
  OracleAIClient,
  buildStandardAdapters,
  getOracleRoute,
  resolveRouteFromSettings,
  makeBlock,
  type OracleModelRoute,
} from '@oracle/ai';
import { coerceLocale, type SupportedLocale } from '@oracle/shared';

const RECERT_PROMPT_VERSION = 'claim-recertification-v1';
const INTERVIEW_FALLBACK_ROUTE_ID = 'anthropic_claude_haiku_4_5_interview_primary';

const LANGUAGE_LABELS: Record<SupportedLocale, string> = {
  en: 'English',
  'zh-CN': 'Simplified Chinese (简体中文)',
};

// whyItMatters is NOT NULL on gaps — a fixed, localized rationale line.
const WHY_IT_MATTERS: Record<SupportedLocale, string> = {
  en: 'Recertification check — confirming this is still accurate keeps the Oracle’s knowledge trustworthy.',
  'zh-CN': '复核确认——确认该信息仍然准确，有助于保持知识库的可信度。',
};

const payloadSchema = z.object({
  claimId: z.string().uuid(),
  target: z.discriminatedUnion('kind', [
    z.object({ kind: z.literal('employee'), employeeId: z.string().uuid() }),
    z.object({ kind: z.literal('department'), department: z.string().min(1) }),
    z.object({ kind: z.literal('locale'), locale: z.string().min(1) }),
  ]),
});
type RecertPayload = z.infer<typeof payloadSchema>;

type ResolvedTarget = {
  targetEmployeeId: string | null;
  targetDepartment: string | null;
  lang: SupportedLocale;
};

function buildOracleClient(): OracleAIClient {
  return new OracleAIClient({ adapters: buildStandardAdapters(), fallbackOnError: true });
}

async function resolveDraftingRoute(
  db: ReturnType<typeof getDirectDb>,
): Promise<OracleModelRoute> {
  const resolved = await resolveRouteFromSettings(db, 'interview');
  if (resolved) return resolved;
  const fb = getOracleRoute(INTERVIEW_FALLBACK_ROUTE_ID);
  if (!fb) {
    throw new Error(
      `[claim-recertification] interview route unset and fallback "${INTERVIEW_FALLBACK_ROUTE_ID}" missing.`,
    );
  }
  return fb;
}

/** Expand a target spec into the concrete gap-target rows it should produce. */
async function resolveTargets(
  db: ReturnType<typeof getDirectDb>,
  target: RecertPayload['target'],
): Promise<ResolvedTarget[]> {
  if (target.kind === 'employee') {
    const [emp] = await db
      .select({ locale: employees.locale })
      .from(employees)
      .where(eq(employees.id, target.employeeId))
      .limit(1);
    return [
      {
        targetEmployeeId: target.employeeId,
        targetDepartment: null,
        lang: coerceLocale(emp?.locale),
      },
    ];
  }
  if (target.kind === 'department') {
    // One department-targeted gap; surfaces to everyone in that department.
    // Department membership is language-mixed, so draft in English.
    return [{ targetEmployeeId: null, targetDepartment: target.department, lang: 'en' }];
  }
  // locale group (e.g. the China team): fan out to one gap per active employee
  // in that locale, drafted in that language.
  const lang = coerceLocale(target.locale);
  const members = await db
    .select({ id: employees.id })
    .from(employees)
    .where(and(eq(employees.locale, target.locale), isNull(employees.disabledAt)));
  return members.map((m) => ({ targetEmployeeId: m.id, targetDepartment: null, lang }));
}

function buildSystemPrompt(targetLabel: string): string {
  return `You write a single, short, friendly recertification question for The Oracle (POP Creations / Spruce Line).

You are given an existing approved company "claim" (a factual operational statement). Write ONE question that asks the reader to confirm whether it is STILL accurate today, or to correct it if it has changed.

RULES:
1. Output ONLY the question — no preamble, no quotes, no explanation.
2. Write it in ${targetLabel}.
3. Restate the claim's substance briefly so the reader knows exactly what they are confirming.
4. Friendly and concise; invite a correction if it is out of date.`;
}

async function draftQuestion(
  client: OracleAIClient,
  route: OracleModelRoute,
  claimSummary: string,
  lang: SupportedLocale,
): Promise<string> {
  const result = await client.runText({
    taskType: 'claim_recertification',
    routeId: route.routeId,
    promptVersion: RECERT_PROMPT_VERSION,
    blocks: [
      makeBlock({
        id: 'recert-system',
        label: 'Recertification system prompt',
        kind: 'stable_system',
        content: buildSystemPrompt(LANGUAGE_LABELS[lang]),
        reasonIncluded: 'Recertification question instructions',
      }),
      makeBlock({
        id: 'recert-input',
        label: 'Claim to recertify',
        kind: 'dynamic_input',
        content: `Claim to confirm:\n\n${claimSummary}`,
        reasonIncluded: 'The approved claim being recertified',
      }),
    ],
  });
  const text = result.text.trim();
  if (!text) throw new Error('[claim-recertification] model returned an empty question');
  return text;
}

async function recertifyClaim(payload: RecertPayload): Promise<{
  claimId: string;
  status: 'asked' | 'skipped_not_found' | 'skipped_not_approved' | 'skipped_no_targets';
  gapsCreated: number;
}> {
  const db = getDirectDb();

  const [claim] = await db
    .select({ id: claims.id, summary: claims.summary, status: claims.status })
    .from(claims)
    .where(eq(claims.id, payload.claimId))
    .limit(1);
  if (!claim) return { claimId: payload.claimId, status: 'skipped_not_found', gapsCreated: 0 };
  if (claim.status !== 'approved') {
    return { claimId: payload.claimId, status: 'skipped_not_approved', gapsCreated: 0 };
  }

  const targets = await resolveTargets(db, payload.target);
  if (targets.length === 0) {
    return { claimId: payload.claimId, status: 'skipped_no_targets', gapsCreated: 0 };
  }

  const client = buildOracleClient();
  const route = await resolveDraftingRoute(db);
  // Draft once per distinct language (most batches are a single language).
  const draftByLang = new Map<SupportedLocale, string>();
  let created = 0;

  for (const t of targets) {
    // Idempotency: skip if an open recertification gap already exists for this
    // (claim, target).
    const targetClause = t.targetEmployeeId
      ? sql`target_employee_id = ${t.targetEmployeeId}`
      : sql`target_department = ${t.targetDepartment}`;
    const existing = await db.execute(sql`
      SELECT 1 FROM gaps
      WHERE gap_type = 'claim_recertification'
        AND status IN ('open', 'queued', 'asked')
        AND related_claim_ids @> ${JSON.stringify([payload.claimId])}::jsonb
        AND ${targetClause}
      LIMIT 1
    `);
    if (existing.length > 0) continue;

    let question = draftByLang.get(t.lang);
    if (!question) {
      question = await draftQuestion(client, route, claim.summary, t.lang);
      draftByLang.set(t.lang, question);
    }

    await db.insert(gaps).values({
      gapType: 'claim_recertification',
      relatedClaimIds: [payload.claimId],
      questionToAsk: question,
      whyItMatters: WHY_IT_MATTERS[t.lang],
      targetEmployeeId: t.targetEmployeeId,
      targetDepartment: t.targetDepartment,
      priority: 'medium',
      status: 'queued',
    });
    created += 1;
  }

  return { claimId: payload.claimId, status: 'asked', gapsCreated: created };
}

export const claimRecertificationTask = task({
  id: 'claim-recertification',
  run: async (rawPayload: unknown) => {
    const payload = payloadSchema.parse(rawPayload);
    return recertifyClaim(payload);
  },
});
