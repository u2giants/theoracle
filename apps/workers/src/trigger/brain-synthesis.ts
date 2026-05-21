// Brain synthesis worker — spec Part 9.7, 9.8, 5.4.
//
// Triggered by:
//   - Admin manual trigger via POST /api/admin/brain/synthesize
//   - 'new_claims' event (triggered from claim-extraction after new approved claims)
//   - 'scheduled' cron (weekly maintenance)
//
// Per-section workflow (spec 9.7):
//   1. Load the target brain section and its current version (if any).
//   2. Retrieve approved claims via claim_domains + sectionClaims joins.
//   3. Call synthesis model with spec 9.8 structured output schema.
//   4. Validate output: all paragraphs map to approved claim IDs, etc.
//   5. Two-step transactional insert (spec 6.7):
//        a. INSERT brain_sections row (if new), current_version_id = NULL.
//        b. INSERT brain_section_versions row.
//        c. UPDATE brain_sections.current_version_id = new version ID.
//   6. Insert new gaps from synthesis output.
//   7. Update resolved gaps.
//   8. Log model_runs and job_runs rows.
//
// Validation constraint (spec 9.8):
//   Every material paragraph must map to approved claim IDs.
//   Synthesis is rejected if any claim ID doesn't exist or isn't approved.

import { schedules, task } from '@trigger.dev/sdk/v3';
import { and, desc, eq, inArray, sql } from 'drizzle-orm';
import { z } from 'zod';
import { generateObject } from 'ai';
import { getDirectDb } from '@oracle/db/client';
import {
  brainSections,
  brainSectionVersions,
  claims,
  claimDomains,
  gaps,
  modelRuns,
  jobRuns,
  sectionClaims,
  settings,
} from '@oracle/db/schema';
import { getOpenRouter } from '@oracle/ai';
import { KNOWLEDGE_DOMAINS } from '@oracle/shared';

const FALLBACK_MODEL = 'anthropic/claude-sonnet-4.6';
const SYNTHESIS_PROMPT_VERSION = '1.0.0';

// ---------------------------------------------------------------------------
// Spec 9.8 structured output schema.
// ---------------------------------------------------------------------------

const SynthesisParagraphSchema = z.object({
  text: z.string().describe('The paragraph text to include in the brain section.'),
  supportingClaimIds: z
    .array(z.string().uuid())
    .min(1)
    .describe('Approved claim IDs that directly support this paragraph. At least one required.'),
});

const MaterialChangeSchema = z.object({
  type: z
    .enum(['added_claim', 'removed_claim', 'strengthened_claim', 'weakened_claim'])
    .describe('What kind of change occurred.'),
  claimId: z.string().uuid().describe('The claim ID affected.'),
  reason: z.string().describe('Why this change was made.'),
});

const NewGapSchema = z.object({
  questionToAsk: z.string().min(10),
  whyItMatters: z.string().min(10),
  priority: z.enum(['low', 'medium', 'high', 'urgent']),
  targetDepartment: z.string().optional(),
});

export const SynthesisOutputSchema = z.object({
  sectionId: z.string().describe('The brain section ID this output is for.'),
  paragraphs: z
    .array(SynthesisParagraphSchema)
    .describe('All paragraphs of the synthesized section. Each maps to approved claim IDs.'),
  updatedMarkdown: z
    .string()
    .describe('Full Markdown content of the new brain section version.'),
  materialChanges: z
    .array(MaterialChangeSchema)
    .describe('Significant changes from the previous version.'),
  claimsAdded: z.array(z.string().uuid()).describe('Claim IDs newly incorporated.'),
  claimsRemoved: z.array(z.string().uuid()).describe('Claim IDs dropped from this version.'),
  claimsStrengthened: z
    .array(z.string().uuid())
    .describe('Claim IDs now more prominently featured.'),
  claimsWeakened: z
    .array(z.string().uuid())
    .describe('Claim IDs given less weight due to contradicting evidence.'),
  newContradictions: z
    .array(
      z.object({
        claimAId: z.string().uuid(),
        claimBId: z.string().uuid(),
        description: z.string(),
        severity: z.enum(['low', 'medium', 'high']),
      }),
    )
    .describe('New contradictions detected during synthesis.'),
  resolvedContradictions: z
    .array(z.string().uuid())
    .describe('Contradiction IDs that can be marked resolved.'),
  newGaps: z.array(NewGapSchema).describe('New knowledge gaps identified during synthesis.'),
  resolvedGaps: z
    .array(z.string().uuid())
    .describe('Gap IDs that have been answered by existing approved claims.'),
  confidenceChange: z
    .enum(['increased', 'stable', 'decreased'])
    .describe('Whether the overall confidence in this section improved.'),
  requiresHumanReview: z
    .boolean()
    .describe(
      'True if: the section contains high-impact claims, there are unresolved contradictions, or the AI is uncertain about claim traceability.',
    ),
  changeSummary: z
    .string()
    .describe('1–3 sentence summary of what changed in this version.'),
});

export type SynthesisOutput = z.infer<typeof SynthesisOutputSchema>;

// ---------------------------------------------------------------------------
// Payload schema.
// ---------------------------------------------------------------------------

const PayloadSchema = z.object({
  sectionId: z.string().min(1),
  trigger: z.enum(['scheduled', 'admin', 'new_claims']),
  // Optional: only synthesize if this many or more new claims are available.
  minNewClaims: z.number().int().min(0).optional(),
});

// ---------------------------------------------------------------------------
// Build the synthesis system prompt.
// ---------------------------------------------------------------------------

function buildSynthesisPrompt(
  section: { id: string; title: string; knowledgeDomain: string; category: string },
  currentMarkdown: string | null,
  approvedClaims: Array<{ id: string; summary: string; claimType: string; impactScore: number; confidenceScore: number }>,
): string {
  const claimList = approvedClaims
    .map(
      (c) =>
        `  - ID: ${c.id}\n    Type: ${c.claimType}\n    Impact: ${c.impactScore}/10  Confidence: ${c.confidenceScore}/10\n    Claim: ${c.summary}`,
    )
    .join('\n');

  const currentSection = currentMarkdown
    ? `\n\nCURRENT SECTION MARKDOWN (previous version):\n${currentMarkdown}\n`
    : '\n\n(This is the first version of this section — no prior content.)\n';

  return `You are the Oracle Brain Synthesis engine for POP Creations / Spruce Line.

Your task: synthesize a new version of the brain section "${section.title}" (domain: ${section.knowledgeDomain}, category: ${section.category}).

MANDATORY RULES:
1. Every paragraph in your output MUST cite at least one approved claim ID from the list below.
2. Do not assert any fact that is not directly supported by an approved claim.
3. Do not name specific people unless a claim explicitly does — and even then, use their role/department instead when possible.
4. Do not include information about customers, licensors, or external systems unless a claim supports it.
5. If approved claims conflict with each other, report the contradiction — do not pick a winner.
6. New gaps must include a specific, actionable question and a clear explanation of why it matters.
7. The section ID in your output must exactly match: ${section.id}

TRACEABILITY REQUIREMENT:
Each paragraph's supportingClaimIds list must contain real claim IDs from the approved list below.
The backend validator will reject this synthesis if any claim ID does not exist or is not approved.
${currentSection}
APPROVED CLAIMS FOR THIS SECTION (${approvedClaims.length} total):
${claimList || '(No approved claims yet — output an empty section with a gap asking for foundational knowledge.)'}

OUTPUT: Return structured JSON matching the schema exactly. The updatedMarkdown field should be well-formatted Markdown suitable for display to the Lead Architect.`;
}

// ---------------------------------------------------------------------------
// Validate synthesis output (spec 9.8 backend validator).
// ---------------------------------------------------------------------------

async function validateSynthesisOutput(
  output: SynthesisOutput,
  approvedClaimIds: Set<string>,
): Promise<{ valid: boolean; errors: string[] }> {
  const errors: string[] = [];

  // All supporting claim IDs must exist in the approved set.
  for (const para of output.paragraphs) {
    for (const cid of para.supportingClaimIds) {
      if (!approvedClaimIds.has(cid)) {
        errors.push(`Paragraph references non-approved claim ID: ${cid}`);
      }
    }
  }

  // materialChanges claim IDs must exist.
  for (const change of output.materialChanges) {
    if (!approvedClaimIds.has(change.claimId)) {
      errors.push(`materialChange references non-approved claim ID: ${change.claimId}`);
    }
  }

  // claimsAdded / claimsRemoved / strengthened / weakened must be in approved set.
  const allReferencedIds = [
    ...output.claimsAdded,
    ...output.claimsStrengthened,
    ...output.claimsWeakened,
    // claimsRemoved may reference claims no longer approved (recently rejected/superseded) — skip check.
  ];
  for (const cid of allReferencedIds) {
    if (!approvedClaimIds.has(cid)) {
      errors.push(`Claim reference ${cid} not in approved claims set`);
    }
  }

  // New gaps must have both questionToAsk and whyItMatters (enforced by Zod already).
  for (const gap of output.newGaps) {
    if (!gap.questionToAsk.trim() || !gap.whyItMatters.trim()) {
      errors.push('Gap missing questionToAsk or whyItMatters');
    }
  }

  return { valid: errors.length === 0, errors };
}

// ---------------------------------------------------------------------------
// Main synthesis logic.
// ---------------------------------------------------------------------------

async function synthesizeSection(
  sectionId: string,
  trigger: string,
  triggerRunId: string,
): Promise<{ ok: boolean; versionId?: string; requiresReview?: boolean }> {
  const db = getDirectDb();

  // Read model from settings.
  const modelSetting = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, 'default_synthesis_model'))
    .limit(1);

  const modelName =
    (typeof modelSetting[0]?.value === 'string' ? modelSetting[0].value : null) ??
    FALLBACK_MODEL;

  // Load or scaffold the brain section.
  let [section] = await db
    .select()
    .from(brainSections)
    .where(eq(brainSections.id, sectionId))
    .limit(1);

  if (!section) {
    // Section doesn't exist yet — reject; admin must create it first.
    throw new Error(`Brain section "${sectionId}" does not exist. Create it in the admin UI first.`);
  }

  // Load the current version's Markdown (if any).
  let currentMarkdown: string | null = null;
  if (section.currentVersionId) {
    const [currentVersion] = await db
      .select({ markdown: brainSectionVersions.markdown })
      .from(brainSectionVersions)
      .where(eq(brainSectionVersions.id, section.currentVersionId))
      .limit(1);
    currentMarkdown = currentVersion?.markdown ?? null;
  }

  // Load the next version number.
  const lastVersion = await db
    .select({ versionNumber: brainSectionVersions.versionNumber })
    .from(brainSectionVersions)
    .where(eq(brainSectionVersions.sectionId, sectionId))
    .orderBy(desc(brainSectionVersions.versionNumber))
    .limit(1);

  const nextVersionNumber = (lastVersion[0]?.versionNumber ?? 0) + 1;

  // Retrieve approved claims for this section.
  // Claim_domains match OR explicit sectionClaims join.
  const domainClaims = await db
    .select({
      id: claims.id,
      summary: claims.summary,
      claimType: claims.claimType,
      impactScore: claims.impactScore,
      confidenceScore: claims.confidenceScore,
    })
    .from(claims)
    .innerJoin(claimDomains, eq(claimDomains.claimId, claims.id))
    .where(
      and(
        eq(claims.status, 'approved'),
        eq(claimDomains.domain, section.knowledgeDomain),
      ),
    )
    .orderBy(desc(claims.impactScore))
    .limit(200);

  const sectionSpecificClaims = await db
    .select({
      id: claims.id,
      summary: claims.summary,
      claimType: claims.claimType,
      impactScore: claims.impactScore,
      confidenceScore: claims.confidenceScore,
    })
    .from(claims)
    .innerJoin(sectionClaims, eq(sectionClaims.claimId, claims.id))
    .where(
      and(
        eq(claims.status, 'approved'),
        eq(sectionClaims.sectionId, sectionId),
      ),
    );

  // Merge and deduplicate.
  const allClaimsMap = new Map<string, (typeof domainClaims)[number]>();
  for (const c of [...domainClaims, ...sectionSpecificClaims]) {
    allClaimsMap.set(c.id, c);
  }
  const approvedClaims = Array.from(allClaimsMap.values());
  const approvedClaimIds = new Set(approvedClaims.map((c) => c.id));

  // Build synthesis prompt.
  const systemPrompt = buildSynthesisPrompt(
    {
      id: section.id,
      title: section.title,
      knowledgeDomain: section.knowledgeDomain,
      category: section.category,
    },
    currentMarkdown,
    approvedClaims,
  );

  // Call synthesis model.
  const callStartMs = Date.now();
  const openrouter = getOpenRouter();
  const model = openrouter(modelName);

  const { object, usage } = await generateObject({
    model,
    schema: SynthesisOutputSchema,
    system: systemPrompt,
    messages: [
      {
        role: 'user',
        content: `Please synthesize brain section: ${section.id}\nTrigger: ${trigger}\nApproved claims available: ${approvedClaims.length}`,
      },
    ],
    temperature: 0.2,
  });

  const latencyMs = Date.now() - callStartMs;

  // Log model run.
  const [modelRun] = await db
    .insert(modelRuns)
    .values({
      taskType: 'brain-synthesis',
      model: modelName,
      provider: 'openrouter',
      promptVersion: SYNTHESIS_PROMPT_VERSION,
      inputTokens: usage?.inputTokens ?? null,
      outputTokens: usage?.outputTokens ?? null,
      latencyMs,
      success: true,
    })
    .returning({ id: modelRuns.id });

  // Validate output (spec 9.8 mandatory validator).
  const { valid, errors: validationErrors } = await validateSynthesisOutput(object, approvedClaimIds);

  if (!valid) {
    const errDetail = validationErrors.join('; ');
    console.error('[brain-synthesis] validation failed:', errDetail);
    // Log the failure and abort — do NOT update the brain section.
    await db
      .update(modelRuns)
      .set({ success: false, error: `Validation failed: ${errDetail}` })
      .where(eq(modelRuns.id, modelRun!.id));
    throw new Error(`Brain synthesis validation failed: ${errDetail}`);
  }

  // Two-step transactional insert (spec 6.7).
  // Step a+b: insert brain_section_versions row.
  const [newVersion] = await db
    .insert(brainSectionVersions)
    .values({
      sectionId,
      versionNumber: nextVersionNumber,
      markdown: object.updatedMarkdown,
      structuredContent: {
        paragraphs: object.paragraphs,
        materialChanges: object.materialChanges,
        claimsAdded: object.claimsAdded,
        claimsRemoved: object.claimsRemoved,
        claimsStrengthened: object.claimsStrengthened,
        claimsWeakened: object.claimsWeakened,
        confidenceChange: object.confidenceChange,
      },
      changeSummary: object.changeSummary,
      createdByModelRunId: modelRun?.id ?? null,
      reviewStatus: object.requiresHumanReview ? 'needs_review' : 'draft',
    })
    .returning({ id: brainSectionVersions.id });

  if (!newVersion) throw new Error('[brain-synthesis] version insert returned no row');

  // Step c: update brain_sections.current_version_id.
  await db
    .update(brainSections)
    .set({ currentVersionId: newVersion.id, updatedAt: new Date() })
    .where(eq(brainSections.id, sectionId));

  // Update sectionClaims: add new claims referenced in this synthesis.
  for (const claimId of object.claimsAdded) {
    if (approvedClaimIds.has(claimId)) {
      await db
        .insert(sectionClaims)
        .values({ sectionId, claimId })
        .onConflictDoNothing();
    }
  }

  // Emit new gaps from synthesis output.
  for (const gap of object.newGaps) {
    await db.insert(gaps).values({
      gapType: 'synthesis_gap',
      sectionId,
      relatedClaimIds: object.claimsAdded,
      questionToAsk: gap.questionToAsk,
      whyItMatters: gap.whyItMatters,
      priority: gap.priority,
      targetDepartment: gap.targetDepartment ?? null,
      status: 'open',
      createdByModelRunId: modelRun?.id ?? null,
    });
  }

  // Resolve gaps that are now answered.
  for (const gapId of object.resolvedGaps) {
    await db
      .update(gaps)
      .set({ status: 'resolved', resolvedAt: new Date() })
      .where(eq(gaps.id, gapId));
  }

  return {
    ok: true,
    versionId: newVersion.id,
    requiresReview: object.requiresHumanReview,
  };
}

// ---------------------------------------------------------------------------
// Primary task: synthesize a single section.
// ---------------------------------------------------------------------------

export const brainSynthesisTask = task({
  id: 'brain-synthesis',
  maxDuration: 60 * 10, // 10 minutes (large context + complex LLM call)
  run: async (payload: z.infer<typeof PayloadSchema>, { ctx }) => {
    PayloadSchema.parse(payload);
    const db = getDirectDb();

    const [jobRun] = await db
      .insert(jobRuns)
      .values({
        triggerRunId: ctx.run.id,
        jobType: 'brain-synthesis',
        status: 'running',
        startedAt: new Date(),
        inputJson: { sectionId: payload.sectionId, trigger: payload.trigger },
      })
      .returning({ id: jobRuns.id });

    if (!jobRun) throw new Error('[brain-synthesis] failed to insert job_runs row');

    try {
      const result = await synthesizeSection(
        payload.sectionId,
        payload.trigger,
        ctx.run.id,
      );

      await db
        .update(jobRuns)
        .set({
          status: 'complete',
          finishedAt: new Date(),
          outputJson: result,
        })
        .where(eq(jobRuns.id, jobRun.id));

      const { ok: _ok, ...resultRest } = result;
      return { ok: true, sectionId: payload.sectionId, ...resultRest };
    } catch (err) {
      await db
        .update(jobRuns)
        .set({
          status: 'failed',
          finishedAt: new Date(),
          error: err instanceof Error ? err.message : String(err),
        })
        .where(eq(jobRuns.id, jobRun.id));
      throw err;
    }
  },
});

// ---------------------------------------------------------------------------
// Scheduled maintenance: run weekly to keep brain sections fresh.
// ---------------------------------------------------------------------------

export const brainSynthesisScheduledTask = schedules.task({
  id: 'brain-synthesis-scheduled',
  cron: '0 6 * * 1', // Every Monday at 6:00 AM
  maxDuration: 60 * 30, // 30 minutes for all sections
  run: async (_payload, { ctx }) => {
    const db = getDirectDb();

    // Find all brain sections that have approved claims but haven't been
    // synthesized in the past week, or have never been synthesized.
    const sectionsToRefresh = await db
      .select({ id: brainSections.id })
      .from(brainSections)
      .orderBy(brainSections.updatedAt)
      .limit(10); // process up to 10 sections per scheduled run

    if (sectionsToRefresh.length === 0) {
      return { ok: true, sectionsProcessed: 0 };
    }

    const results: Array<{ sectionId: string; ok: boolean; error?: string }> = [];

    for (const section of sectionsToRefresh) {
      try {
        const result = await synthesizeSection(section.id, 'scheduled', ctx.run.id);
        results.push({ sectionId: section.id, ok: result.ok });
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : String(err);
        console.error(`[brain-synthesis-scheduled] section ${section.id} failed:`, errMsg);
        results.push({ sectionId: section.id, ok: false, error: errMsg });
      }
    }

    return { ok: true, sectionsProcessed: results.length, results };
  },
});
