// Claim recertification worker (china_imp.md / verify-selected-claims feature).
//
// Given an approved claim and one or more targets (the China-team locale group,
// individual employees, and/or department "groups"), asks each recipient whether
// the claim is still accurate. Every target is fanned out to concrete employees
// and ONE gap is created per recipient (gap_type='claim_recertification',
// target_employee_id set), with the question drafted IN THAT RECIPIENT'S
// LANGUAGE. So the China-translation rule falls out for free: only zh-CN
// recipients get a Chinese question; English recipients get English; a mixed
// department gets each member's language. Nothing is translated for an all-English
// target.
//
// Reuses the gaps table — no schema change. Surfaced through the existing gap
// machinery (getRelevantOpenGaps injects it into the recipient's next Oracle
// chat). Replies flow through normal extraction; an admin resolves via /admin/gaps.
// Idempotent: skips when an OPEN recertification gap for the same (claim,
// employee) already exists. All drafting goes through OracleAIClient.

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

const targetSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('employee'), employeeId: z.string().uuid() }),
  z.object({ kind: z.literal('department'), department: z.string().min(1) }),
  z.object({ kind: z.literal('locale'), locale: z.string().min(1) }),
]);

const payloadSchema = z.object({
  claimId: z.string().uuid(),
  targets: z.array(targetSchema).min(1),
});
type RecertPayload = z.infer<typeof payloadSchema>;

type Recipient = { employeeId: string; lang: SupportedLocale };

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

/**
 * Expand a set of target specs (locale group / individual employee / department)
 * into a deduped list of recipient employees, each carrying their own locale.
 * Disabled employees are excluded.
 */
async function resolveRecipients(
  db: ReturnType<typeof getDirectDb>,
  targets: RecertPayload['targets'],
): Promise<Recipient[]> {
  const byEmployee = new Map<string, SupportedLocale>();

  for (const t of targets) {
    if (t.kind === 'employee') {
      const [emp] = await db
        .select({ id: employees.id, locale: employees.locale, disabledAt: employees.disabledAt })
        .from(employees)
        .where(eq(employees.id, t.employeeId))
        .limit(1);
      if (emp && !emp.disabledAt) byEmployee.set(emp.id, coerceLocale(emp.locale));
    } else if (t.kind === 'locale') {
      const members = await db
        .select({ id: employees.id, locale: employees.locale })
        .from(employees)
        .where(and(eq(employees.locale, t.locale), isNull(employees.disabledAt)));
      for (const m of members) byEmployee.set(m.id, coerceLocale(m.locale));
    } else {
      // department "group" — resolve membership via the employee_departments
      // junction (enum-keyed, exact) rather than free-text matching. Raw SQL
      // avoids enum-typing friction on the department_id bind.
      const members = await db.execute<{ id: string; locale: string }>(sql`
        SELECT e.id, e.locale
        FROM employee_departments ed
        JOIN employees e ON e.id = ed.employee_id
        WHERE ed.department_id = ${t.department}
          AND e.disabled_at IS NULL
      `);
      for (const m of members) byEmployee.set(m.id, coerceLocale(m.locale));
    }
  }

  return [...byEmployee].map(([employeeId, lang]) => ({ employeeId, lang }));
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
  status: 'asked' | 'skipped_not_found' | 'skipped_not_approved' | 'skipped_no_recipients';
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

  const recipients = await resolveRecipients(db, payload.targets);
  if (recipients.length === 0) {
    return { claimId: payload.claimId, status: 'skipped_no_recipients', gapsCreated: 0 };
  }

  const client = buildOracleClient();
  const route = await resolveDraftingRoute(db);
  // Draft once per distinct language — only zh-CN recipients trigger a Chinese
  // draft, so an all-English target never pays for a translation.
  const draftByLang = new Map<SupportedLocale, string>();
  let created = 0;

  for (const r of recipients) {
    // Idempotency: skip if an open recertification gap already exists for this
    // (claim, employee).
    const existing = await db.execute(sql`
      SELECT 1 FROM gaps
      WHERE gap_type = 'claim_recertification'
        AND status IN ('open', 'queued', 'asked')
        AND related_claim_ids @> ${JSON.stringify([payload.claimId])}::jsonb
        AND target_employee_id = ${r.employeeId}
      LIMIT 1
    `);
    if (existing.length > 0) continue;

    let question = draftByLang.get(r.lang);
    if (!question) {
      question = await draftQuestion(client, route, claim.summary, r.lang);
      draftByLang.set(r.lang, question);
    }

    await db.insert(gaps).values({
      gapType: 'claim_recertification',
      relatedClaimIds: [payload.claimId],
      questionToAsk: question,
      whyItMatters: WHY_IT_MATTERS[r.lang],
      targetEmployeeId: r.employeeId,
      targetDepartment: null,
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
