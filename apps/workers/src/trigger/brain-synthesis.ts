// R9 — Brain synthesis worker (refactored through OracleAIClient + diff validator).
//
// Per docs/oracle/05-ai-retrofit-phase-packet.md Phase R9.
//
// What changed vs the legacy worker:
//   - Model calls go through OracleAIClient (R2) via direct provider adapters
//     (Vertex / Anthropic / OpenAI raw SDKs — DECISIONS.md D6 / D9) using
//     the curated synthesis route from `settings.default_synthesis_route`
//     (R1 setting key).
//   - oracle_context_packs + model_run_usage_details rows are written for
//     every synthesis call so cost / cache / fallback dashboards work.
//   - The validator in `packages/oracle-engines/src/synthesis/diff-validator.ts`
//     replaces the inline `validateSynthesisOutput`. It adds the R9 rule:
//     "Reject unsupported named people, systems, customers, stages,
//      departments, or process rules" — every capitalized proper-noun-shaped
//     name in `updatedMarkdown` must be backed by an approved claim summary
//     or by a canonical entity in the R3.5 registry.
//   - On validation failure: the worker now inserts a brain_section_versions
//     row with reviewStatus='rejected' and does NOT update
//     brain_sections.currentVersionId. The failed output is preserved for
//     admin review without touching the current Brain version.
//
// What stays the same:
//   - Two-step transactional insert (spec 6.7) for new approved versions.
//   - sectionClaims membership maintenance for claimsAdded.
//   - Gap emission + resolution.
//   - Scheduled (Monday 6 AM) + on-demand task variants.

import { schedules, task } from '@trigger.dev/sdk/v3';
import { and, desc, eq, inArray, sql } from 'drizzle-orm';
import { z } from 'zod';
import { createHash } from 'node:crypto';
import { getDirectDb } from '@oracle/db/client';
import {
  brainSections,
  brainSectionVersions,
  claims,
  claimTopDomains,
  entities,
  gaps,
  jobRuns,
  modelRunUsageDetails,
  modelRuns,
  oracleContextPacks,
  sectionClaims,
  settings,
  type OracleDb,
} from '@oracle/db';
import {
  OracleAIClient,
  buildStandardAdapters,
  getOracleRoute,
  resolveRouteFromSettings,
  makeBlock,
  type OracleModelRoute,
  type OraclePromptPlan,
} from '@oracle/ai';
import {
  mapLegacyDomainToTopDomain,
  validateSynthesisDiff,
  type SynthesisOutput as PureSynthesisOutput,
  type SynthesisValidationResult,
} from '@oracle/engines';
import { KNOWLEDGE_DOMAINS, type KnowledgeDomain } from '@oracle/shared';

/**
 * Parse the brain section's `relatedDomains` jsonb column (typed as
 * `unknown` because Drizzle doesn't constrain jsonb content) into a
 * validated list of legacy KnowledgeDomain values. Per spec 10.1, the
 * synthesis read scope is the union of `knowledgeDomain` + `relatedDomains`.
 * Anything that isn't a known legacy enum value is dropped silently —
 * the column is admin-editable and we'd rather lose a typo than crash.
 */
function parseRelatedDomains(value: unknown): KnowledgeDomain[] {
  if (!Array.isArray(value)) return [];
  const allowed = new Set<string>(KNOWLEDGE_DOMAINS);
  return value.filter((v): v is KnowledgeDomain => typeof v === 'string' && allowed.has(v));
}

const FALLBACK_ROUTE_ID = 'anthropic_claude_3_5_sonnet_synthesis_primary';
const SYNTHESIS_PROMPT_VERSION = '1.0.0';

// ─────────────────────────────────────────────────────────────────────────
// Spec 9.8 structured output schema — unchanged from legacy.
// The shape mirrors the SynthesisOutput type in @oracle/engines.
// ─────────────────────────────────────────────────────────────────────────

const SynthesisParagraphSchema = z.object({
  text: z.string(),
  supportingClaimIds: z.array(z.string().uuid()).min(1),
});

const MaterialChangeSchema = z.object({
  type: z.enum(['added_claim', 'removed_claim', 'strengthened_claim', 'weakened_claim']),
  claimId: z.string().uuid(),
  reason: z.string(),
});

const NewGapSchema = z.object({
  questionToAsk: z.string().min(10),
  whyItMatters: z.string().min(10),
  priority: z.enum(['low', 'medium', 'high', 'urgent']),
  targetDepartment: z.string().optional(),
});

export const SynthesisOutputSchema = z.object({
  sectionId: z.string(),
  paragraphs: z.array(SynthesisParagraphSchema),
  updatedMarkdown: z.string(),
  materialChanges: z.array(MaterialChangeSchema),
  claimsAdded: z.array(z.string().uuid()),
  claimsRemoved: z.array(z.string().uuid()),
  claimsStrengthened: z.array(z.string().uuid()),
  claimsWeakened: z.array(z.string().uuid()),
  newContradictions: z
    .array(
      z.object({
        claimAId: z.string().uuid(),
        claimBId: z.string().uuid(),
        description: z.string(),
        severity: z.enum(['low', 'medium', 'high']),
      }),
    ),
  resolvedContradictions: z.array(z.string().uuid()),
  newGaps: z.array(NewGapSchema),
  resolvedGaps: z.array(z.string().uuid()),
  confidenceChange: z.enum(['increased', 'stable', 'decreased']),
  requiresHumanReview: z.boolean(),
  changeSummary: z.string(),
});

export type SynthesisOutput = z.infer<typeof SynthesisOutputSchema>;

// ─────────────────────────────────────────────────────────────────────────
// Payload schema.
// ─────────────────────────────────────────────────────────────────────────

const PayloadSchema = z.object({
  sectionId: z.string().min(1),
  trigger: z.enum(['scheduled', 'admin', 'new_claims']),
  minNewClaims: z.number().int().min(0).optional(),
});

// ─────────────────────────────────────────────────────────────────────────
// Shared OracleAIClient (one per worker process)
// ─────────────────────────────────────────────────────────────────────────

function buildOracleClient(): OracleAIClient {
  return new OracleAIClient({
    adapters: buildStandardAdapters(),
    fallbackOnError: true,
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Prompt builder — unchanged from legacy (same shape, same rules).
// ─────────────────────────────────────────────────────────────────────────

function buildSynthesisSystemPrompt(
  section: { id: string; title: string; knowledgeDomain: string; category: string },
): string {
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
The backend validator will reject this synthesis if:
  - any claim ID does not exist or is not approved, OR
  - the markdown mentions a named entity (person, system, customer, licensor, department) that is not backed by an approved claim or the canonical entity registry.

OUTPUT: Return structured JSON matching the schema exactly. The updatedMarkdown field should be well-formatted Markdown suitable for display to the Lead Architect.`;
}

function buildSynthesisCorpus(
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
    ? `CURRENT SECTION MARKDOWN (previous version):\n${currentMarkdown}\n`
    : '(This is the first version of this section — no prior content.)\n';

  return `${currentSection}

APPROVED CLAIMS FOR THIS SECTION (${approvedClaims.length} total):
${claimList || '(No approved claims yet — output an empty section with a gap asking for foundational knowledge.)'}`;
}

// ─────────────────────────────────────────────────────────────────────────
// Main synthesis logic
// ─────────────────────────────────────────────────────────────────────────

async function synthesizeSection(
  sectionId: string,
  trigger: string,
  jobRunId: string,
): Promise<{
  ok: boolean;
  versionId?: string;
  versionStatus?: 'draft' | 'approved' | 'needs_review' | 'rejected';
  requiresReview?: boolean;
  validationFailures?: number;
}> {
  const db = getDirectDb();
  const client = buildOracleClient();

  // ── 1. Resolve curated synthesis route + load section + claims ───────
  const route = await resolveSynthesisRoute(db);

  const [section] = await db
    .select()
    .from(brainSections)
    .where(eq(brainSections.id, sectionId))
    .limit(1);
  if (!section) {
    throw new Error(`Brain section "${sectionId}" does not exist. Create it in the admin UI first.`);
  }

  let currentMarkdown: string | null = null;
  if (section.currentVersionId) {
    const [currentVersion] = await db
      .select({ markdown: brainSectionVersions.markdown })
      .from(brainSectionVersions)
      .where(eq(brainSectionVersions.id, section.currentVersionId))
      .limit(1);
    currentMarkdown = currentVersion?.markdown ?? null;
  }

  const lastVersion = await db
    .select({ versionNumber: brainSectionVersions.versionNumber })
    .from(brainSectionVersions)
    .where(eq(brainSectionVersions.sectionId, sectionId))
    .orderBy(desc(brainSectionVersions.versionNumber))
    .limit(1);
  const nextVersionNumber = (lastVersion[0]?.versionNumber ?? 0) + 1;

  // Approved claims via claim_top_domains (R3.5) + sectionClaims joins.
  // Spec 10.1: the synthesis read scope is the union of the section's
  // `knowledgeDomain` and any entries in its `relatedDomains` jsonb array.
  // Each legacy enum value is run through the same mechanical mapping used by
  // the 42_* backfill SQL and the R6 worker, so this read path stays in
  // lockstep with the write path in promotion-executor.ts (which only writes
  // claim_top_domains).
  const sectionDomains: KnowledgeDomain[] = [
    section.knowledgeDomain,
    ...parseRelatedDomains(section.relatedDomains),
  ];
  const topDomainIds = Array.from(
    new Set(sectionDomains.map((d) => mapLegacyDomainToTopDomain(d))),
  );
  const domainClaims = await db
    .select({
      id: claims.id,
      summary: claims.summary,
      claimType: claims.claimType,
      impactScore: claims.impactScore,
      confidenceScore: claims.confidenceScore,
    })
    .from(claims)
    .innerJoin(claimTopDomains, eq(claimTopDomains.claimId, claims.id))
    .where(
      and(
        eq(claims.status, 'approved'),
        inArray(claimTopDomains.topDomainId, topDomainIds),
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

  const allClaimsMap = new Map<string, (typeof domainClaims)[number]>();
  for (const c of [...domainClaims, ...sectionSpecificClaims]) {
    allClaimsMap.set(c.id, c);
  }
  const approvedClaims = Array.from(allClaimsMap.values());
  const approvedClaimIds = new Set(approvedClaims.map((c) => c.id));
  const approvedClaimSummariesLower = approvedClaims.map((c) => c.summary.toLowerCase());

  // Canonical entity names from the R3.5 registry. Used by the unsupported-
  // named-entity check in the validator.
  const registryRows = await db.select({ canonicalValue: entities.canonicalValue }).from(entities);
  const registryEntityCanonicalsLower = new Set(
    registryRows.map((r) => r.canonicalValue.toLowerCase()),
  );

  // ── 2. Compile prompt blocks ─────────────────────────────────────────
  const systemPrompt = buildSynthesisSystemPrompt(
    {
      id: section.id,
      title: section.title,
      knowledgeDomain: section.knowledgeDomain,
      category: section.category,
    },
  );
  const synthesisCorpus = buildSynthesisCorpus(currentMarkdown, approvedClaims);

  const blocks = [
    makeBlock({
      id: 'synthesis-system',
      label: 'Synthesis system prompt',
      kind: 'stable_system',
      content: systemPrompt,
      reasonIncluded: `synthesis prompt v${SYNTHESIS_PROMPT_VERSION}`,
    }),
    makeBlock({
      id: 'synthesis-corpus',
      label: 'Current section markdown + approved claim corpus',
      kind: 'retrieved_context',
      content: synthesisCorpus,
      reasonIncluded: `${approvedClaims.length} approved claim(s) + current section snapshot`,
    }),
    makeBlock({
      id: 'turn-request',
      label: 'Synthesis request',
      kind: 'dynamic_input',
      content: `Please synthesize brain section: ${section.id}\nTrigger: ${trigger}\nApproved claims available: ${approvedClaims.length}`,
      reasonIncluded: `trigger=${trigger}`,
    }),
  ];

  const plan = client.compile({
    taskType: 'brain_synthesis',
    routeId: route.routeId,
    promptVersion: SYNTHESIS_PROMPT_VERSION,
    blocks,
    observability: { includedClaimIds: approvedClaims.map((c) => c.id) },
  });

  // ── 3. Stage context pack BEFORE the model call ──────────────────────
  const [contextPack] = await db
    .insert(oracleContextPacks)
    .values(buildContextPackInsert(plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error('[brain-synthesis] failed to insert oracle_context_packs row');

  // ── 4. Dispatch through OracleAIClient ───────────────────────────────
  const callStartedAt = Date.now();
  let modelOutput: SynthesisOutput | null = null;
  let modelRunId: string | null = null;
  let inputTokens: number | undefined;
  let outputTokens: number | undefined;
  let cachedInputTokens: number | undefined;
  let providerRequestId: string | undefined;
  let usageRaw: unknown = null;

  try {
    // The bridge adapter calls Vercel AI SDK generateObject with
    // temperature=0.1 by default — sensible for synthesis. If a future
    // phase needs to tune temperature for synthesis, extend
    // GenerateObjectArgs with providerOptions parallel to
    // GenerateTextArgs (R8's pattern) and pass it here.
    const result = await client.runObject<SynthesisOutput>({
      taskType: 'brain_synthesis',
      routeId: route.routeId,
      promptVersion: SYNTHESIS_PROMPT_VERSION,
      blocks,
      schema: SynthesisOutputSchema,
      observability: { includedClaimIds: approvedClaims.map((c) => c.id) },
      providerOptions: {
        cache: {
          preferLongLivedCache: true,
          preferExplicitCache: route.provider === 'vertex',
          cacheTtlSeconds: 24 * 60 * 60,
          expectedReuseCount: 4,
          persistProviderCacheRecord: route.provider === 'vertex',
          sourceDescription: `brain section ${section.id} synthesis corpus`,
          cleanupOwner: 'brain-synthesis-worker',
          createdByJobRunId: jobRunId,
          latestPlannedReuseStep: 'brain_synthesis',
        },
      },
    });
    const latencyMs = Date.now() - callStartedAt;
    inputTokens = result.usage.inputTokens;
    outputTokens = result.usage.outputTokens;
    cachedInputTokens = result.usage.cachedInputTokens;
    providerRequestId = result.usage.providerRequestId;
    usageRaw = result.usage.rawUsageJson;
    const actualRouteId = result.routeId ?? route.routeId;
    const actualProvider = result.provider ?? route.provider;
    const actualModelId = result.modelId ?? route.modelId;

    const [modelRun] = await db
      .insert(modelRuns)
      .values({
        taskType: 'brain-synthesis',
        model: actualModelId,
        provider: actualProvider,
        promptVersion: SYNTHESIS_PROMPT_VERSION,
        inputHash: plan.metadata.stablePrefixHash,
        inputTokens: inputTokens ?? null,
        outputTokens: outputTokens ?? null,
        latencyMs,
        success: result.validation.ok,
      })
      .returning({ id: modelRuns.id });
    if (!modelRun) throw new Error('[brain-synthesis] failed to insert model_runs row');
    modelRunId = modelRun.id;

    await db.insert(modelRunUsageDetails).values({
      modelRunId: modelRun.id,
      contextPackId: contextPack.id,
      routeId: actualRouteId,
      inputTokens: inputTokens ?? null,
      cachedInputTokens: cachedInputTokens ?? null,
      outputTokens: outputTokens ?? null,
      providerRequestId: providerRequestId ?? null,
      rawUsageJson: usageRaw ?? null,
      fellBackFromRouteId: result.fellBackFromRouteId ?? null,
      fallbackReason: result.fallbackReason ?? null,
    });
    await db
      .update(oracleContextPacks)
      .set({ modelRunId: modelRun.id })
      .where(eq(oracleContextPacks.id, contextPack.id));

    if (!result.validation.ok) {
      throw new Error(
        '[brain-synthesis] model output failed Zod schema validation: ' +
          result.validation.error.message,
      );
    }
    modelOutput = result.object;
  } catch (err) {
    if (!modelRunId) {
      await db.insert(modelRuns).values({
        taskType: 'brain-synthesis',
        model: route.modelId,
        provider: route.provider,
        promptVersion: SYNTHESIS_PROMPT_VERSION,
        latencyMs: Date.now() - callStartedAt,
        success: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
    throw err;
  }

  if (!modelOutput) throw new Error('[brain-synthesis] modelOutput is null after dispatch');

  // ── 5. R9 validator — claim IDs + unsupported named entities ─────────
  const validation: SynthesisValidationResult = validateSynthesisDiff({
    output: modelOutput as PureSynthesisOutput,
    approvedClaimIds,
    approvedClaimSummariesLower,
    registryEntityCanonicalsLower,
    expectedSectionId: sectionId,
  });

  // ── 6. Insert brain_section_versions row in BOTH branches ────────────
  //    Failure: reviewStatus='rejected', currentVersionId untouched.
  //    Success: reviewStatus='needs_review' or 'draft', then update
  //             currentVersionId.

  if (!validation.ok) {
    const failureSummary = validation.failures
      .slice(0, 10)
      .map((f) => `${f.kind}: ${f.detail}`)
      .join('; ');
    console.error(`[brain-synthesis] validation failed: ${failureSummary}`);

    const [rejectedVersion] = await db
      .insert(brainSectionVersions)
      .values({
        sectionId,
        versionNumber: nextVersionNumber,
        markdown: modelOutput.updatedMarkdown,
        structuredContent: {
          paragraphs: modelOutput.paragraphs,
          materialChanges: modelOutput.materialChanges,
          claimsAdded: modelOutput.claimsAdded,
          claimsRemoved: modelOutput.claimsRemoved,
          claimsStrengthened: modelOutput.claimsStrengthened,
          claimsWeakened: modelOutput.claimsWeakened,
          confidenceChange: modelOutput.confidenceChange,
          validationFailures: validation.failures,
          unsupportedNames: validation.unsupportedNames,
        },
        changeSummary: `[REJECTED] Synthesis failed validation (${validation.failures.length} failure(s)): ${failureSummary}`,
        createdByModelRunId: modelRunId,
        reviewStatus: 'rejected',
      })
      .returning({ id: brainSectionVersions.id });

    // currentVersionId intentionally NOT updated.
    return {
      ok: false,
      versionId: rejectedVersion?.id,
      versionStatus: 'rejected',
      validationFailures: validation.failures.length,
      requiresReview: true,
    };
  }

  // Validation passed. Insert version + update currentVersionId + membership +
  // gaps as ONE atomic unit. Previously these ran as separate un-transactioned
  // statements: a mid-sequence crash could leave currentVersionId pointing at a
  // version with no sectionClaims membership, or gaps half-resolved.
  const newVersionId = await db.transaction(async (tx) => {
    const [newVersion] = await tx
      .insert(brainSectionVersions)
      .values({
        sectionId,
        versionNumber: nextVersionNumber,
        markdown: modelOutput.updatedMarkdown,
        structuredContent: {
          paragraphs: modelOutput.paragraphs,
          materialChanges: modelOutput.materialChanges,
          claimsAdded: modelOutput.claimsAdded,
          claimsRemoved: modelOutput.claimsRemoved,
          claimsStrengthened: modelOutput.claimsStrengthened,
          claimsWeakened: modelOutput.claimsWeakened,
          confidenceChange: modelOutput.confidenceChange,
        },
        changeSummary: modelOutput.changeSummary,
        createdByModelRunId: modelRunId,
        reviewStatus: modelOutput.requiresHumanReview ? 'needs_review' : 'draft',
      })
      .returning({ id: brainSectionVersions.id });
    if (!newVersion) throw new Error('[brain-synthesis] version insert returned no row');

    await tx
      .update(brainSections)
      .set({ currentVersionId: newVersion.id, updatedAt: new Date() })
      .where(eq(brainSections.id, sectionId));

    // sectionClaims membership for newly-added claims — single multi-row insert.
    const claimRowsToAdd = modelOutput.claimsAdded
      .filter((claimId) => approvedClaimIds.has(claimId))
      .map((claimId) => ({ sectionId, claimId }));
    if (claimRowsToAdd.length > 0) {
      await tx.insert(sectionClaims).values(claimRowsToAdd).onConflictDoNothing();
    }

    // New gaps.
    for (const gap of modelOutput.newGaps) {
      await tx.insert(gaps).values({
        gapType: 'synthesis_gap',
        sectionId,
        relatedClaimIds: modelOutput.claimsAdded,
        questionToAsk: gap.questionToAsk,
        whyItMatters: gap.whyItMatters,
        priority: gap.priority,
        targetDepartment: gap.targetDepartment ?? null,
        status: 'open',
        createdByModelRunId: modelRunId,
      });
    }

    // Resolved gaps — single inArray update, constrained to THIS section + open
    // status so a hallucinated gap UUID can't resolve an arbitrary open gap
    // belonging to another section.
    if (modelOutput.resolvedGaps.length > 0) {
      await tx
        .update(gaps)
        .set({ status: 'resolved', resolvedAt: new Date() })
        .where(
          and(
            inArray(gaps.id, modelOutput.resolvedGaps),
            eq(gaps.sectionId, sectionId),
            eq(gaps.status, 'open'),
          ),
        );
    }

    return newVersion.id;
  });

  return {
    ok: true,
    versionId: newVersionId,
    versionStatus: modelOutput.requiresHumanReview ? 'needs_review' : 'draft',
    requiresReview: modelOutput.requiresHumanReview,
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Tasks
// ─────────────────────────────────────────────────────────────────────────

export const brainSynthesisTask = task({
  id: 'brain-synthesis',
  maxDuration: 60 * 10,
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
      const result = await synthesizeSection(payload.sectionId, payload.trigger, jobRun.id);
      await db
        .update(jobRuns)
        .set({ status: 'complete', finishedAt: new Date(), outputJson: result })
        .where(eq(jobRuns.id, jobRun.id));
      return { sectionId: payload.sectionId, ...result };
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

export const brainSynthesisScheduledTask = schedules.task({
  id: 'brain-synthesis-scheduled',
  cron: '0 6 * * 1',
  maxDuration: 60 * 30,
  // Retries disabled: scheduled cron; a retry would re-synthesize sections and
  // create duplicate versions. The next weekly run is the natural retry.
  retry: { maxAttempts: 1 },
  run: async (_payload, { ctx }) => {
    const db = getDirectDb();
    const sectionsToRefresh = await db
      .select({ id: brainSections.id })
      .from(brainSections)
      .orderBy(brainSections.updatedAt)
      .limit(10);
    if (sectionsToRefresh.length === 0) return { ok: true, sectionsProcessed: 0 };

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

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

async function resolveSynthesisRoute(db: OracleDb): Promise<OracleModelRoute> {
  // Reads BOTH default_synthesis_route AND default_synthesis_reasoning_effort
  // in one query; effort is attached to the returned route for the adapter.
  const resolved = await resolveRouteFromSettings(db, 'synthesis');
  if (resolved) return resolved;
  const fb = getOracleRoute(FALLBACK_ROUTE_ID);
  if (!fb) {
    throw new Error(
      `[brain-synthesis] default_synthesis_route unset / unresolvable and fallback "${FALLBACK_ROUTE_ID}" missing.`,
    );
  }
  console.warn(
    `[brain-synthesis] default_synthesis_route unset / unresolvable; using fallback "${FALLBACK_ROUTE_ID}".`,
  );
  return fb;
}

function buildContextPackInsert(plan: OraclePromptPlan) {
  return {
    taskType: plan.taskType,
    routeId: plan.routeId,
    promptVersion: plan.promptVersion,
    schemaVersion: plan.schemaVersion ?? null,
    stablePrefixHash: plan.metadata.stablePrefixHash,
    semiStableContextHash: plan.metadata.semiStableContextHash ?? null,
    retrievedContextHash: plan.metadata.retrievedContextHash ?? null,
    dynamicInputHash: plan.metadata.dynamicInputHash,
    toolSchemaHash: plan.metadata.toolSchemaHash ?? null,
    outputSchemaHash: plan.metadata.outputSchemaHash ?? null,
    blocksJson: plan.blocks.map((b) => ({
      id: b.id,
      label: b.label,
      kind: b.kind,
      hash: b.hash,
      tokenEstimate: b.tokenEstimate ?? null,
      cacheEligible: b.cacheEligible,
      reasonIncluded: b.reasonIncluded,
    })),
    retrievalPlanId: plan.metadata.retrievalPlanId ?? null,
    selectedDomains: plan.metadata.selectedDomains ?? null,
    selectedSourceTypes: plan.metadata.selectedSourceTypes ?? null,
    selectedProcessStages: plan.metadata.selectedProcessStages ?? null,
    selectedEntityIds: plan.metadata.selectedEntityIds ?? null,
    includedMessageIds: plan.metadata.includedMessageIds ?? null,
    includedDocumentChunkIds: plan.metadata.includedDocumentChunkIds ?? null,
    includedClaimIds: plan.metadata.includedClaimIds ?? null,
    includedGapIds: plan.metadata.includedGapIds ?? null,
    includedContradictionIds: plan.metadata.includedContradictionIds ?? null,
  };
}
