// Oracle MCP — hidden capability registry.
//
// Each entry is a real operation against the Oracle's APPROVED knowledge. None
// of these are registered as MCP tools; they are discovered via tool_search /
// get_capability_details and run via invoke_tool (see server-tools.ts).
//
// All capabilities are tier-1 read-only and route through the same retrieval /
// query path as the employee chat, so they can never surface unapproved
// knowledge. To add a capability, append a Capability here and (if needed) add
// keyword routing to KEYWORD_GROUPS below — nothing else changes.

import { and, asc, eq, inArray } from 'drizzle-orm';
import { z } from 'zod';
import {
  brainSections,
  brainSectionVersions,
  claimEvidence,
  knowledgeTopDomains,
  sectionClaims,
} from '@oracle/db';
import { buildRetrievalPlanFromQuery, searchWithRetrievalPlan } from '@oracle/ai';
import type { Capability, CapabilityContext, SafetyInfo } from './types';

const READ_ONLY: SafetyInfo = {
  tier: 1,
  label: 'read-only',
  description: 'Read-only lookup. Can run automatically.',
};

// ── search_business_knowledge ────────────────────────────────────────────
const searchBusinessKnowledge: Capability = {
  name: 'search_business_knowledge',
  title: 'Search business knowledge',
  group: 'knowledge',
  safety: READ_ONLY,
  description:
    "Search POP Creations / Spruce Line's approved business knowledge for how the company " +
    'actually operates: processes, systems of record, naming and file rules, approvals, and ' +
    'operational facts. Returns evidence-backed approved claims ranked by semantic relevance. ' +
    'Use before designing software so the design matches real business process.',
  argsDescription:
    '{ query: string, domains?: string[], limit?: number (1-20, default 8), includeEvidence?: boolean }',
  argsSchema: z.object({
    query: z.string().min(2),
    domains: z.array(z.string()).optional(),
    limit: z.number().int().min(1).max(20).optional(),
    includeEvidence: z.boolean().optional(),
  }),
  exampleArgs: {
    query: 'how do we name and store design files',
    limit: 5,
    includeEvidence: true,
  },
  commonFailures: [
    'The knowledge base does not yet cover this topic (no approved claims) — returns an empty result with a note.',
    'A `domains` value is not a real knowledge_top_domains id — use list_knowledge_domains first.',
  ],
  relatedTools: ['list_knowledge_domains', 'list_brain_sections'],
  invoke: async (rawArgs, ctx) => {
    const { query, domains, limit, includeEvidence } = rawArgs as {
      query: string;
      domains?: string[];
      limit?: number;
      includeEvidence?: boolean;
    };
    const plan = buildRetrievalPlanFromQuery(query, {
      topK: limit ?? 8,
      ...(domains && domains.length > 0 ? { topDomainHints: domains } : {}),
    });
    const claims = await searchWithRetrievalPlan(ctx.db, plan);

    let evidenceByClaim = new Map<string, { quote: string; sourceType: string }[]>();
    if (includeEvidence && claims.length > 0) {
      const rows = await ctx.db
        .select({
          claimId: claimEvidence.claimId,
          quote: claimEvidence.exactQuote,
          sourceType: claimEvidence.sourceType,
        })
        .from(claimEvidence)
        .where(
          inArray(
            claimEvidence.claimId,
            claims.map((c) => c.id),
          ),
        );
      evidenceByClaim = rows.reduce((acc, r) => {
        const list = acc.get(r.claimId) ?? [];
        if (list.length < 3) list.push({ quote: r.quote, sourceType: r.sourceType });
        acc.set(r.claimId, list);
        return acc;
      }, new Map<string, { quote: string; sourceType: string }[]>());
    }

    return {
      query,
      searchScope: plan.searchScope,
      domainHints: plan.topDomainHints,
      resultCount: claims.length,
      results: claims.map((c) => ({
        id: c.id,
        summary: c.summary,
        claimType: c.claimType,
        impactScore: c.impactScore,
        confidenceScore: c.confidenceScore,
        ...(includeEvidence ? { evidence: evidenceByClaim.get(c.id) ?? [] } : {}),
      })),
      note:
        claims.length === 0
          ? 'No approved claims matched. The knowledge base may not yet cover this topic.'
          : undefined,
    };
  },
};

// ── list_knowledge_domains ───────────────────────────────────────────────
const listKnowledgeDomains: Capability = {
  name: 'list_knowledge_domains',
  title: 'List knowledge domains',
  group: 'taxonomy',
  safety: READ_ONLY,
  description:
    'List the Oracle top-level knowledge domains with their boundary rules (what belongs / ' +
    'does not belong in each). Use to understand how the business organizes its operational ' +
    'knowledge and to choose `domains` for search_business_knowledge.',
  argsDescription: '{ includeInactive?: boolean }',
  argsSchema: z.object({ includeInactive: z.boolean().optional() }),
  exampleArgs: {},
  commonFailures: ['None expected — returns the curated domain list.'],
  relatedTools: ['search_business_knowledge', 'list_brain_sections'],
  invoke: async (rawArgs, ctx) => {
    const { includeInactive } = rawArgs as { includeInactive?: boolean };
    const rows = await ctx.db
      .select({
        id: knowledgeTopDomains.id,
        name: knowledgeTopDomains.name,
        description: knowledgeTopDomains.description,
        belongsHere: knowledgeTopDomains.belongsHere,
        doesNotBelongHere: knowledgeTopDomains.doesNotBelongHere,
        neighboringDomainIds: knowledgeTopDomains.neighboringDomainIds,
        isActive: knowledgeTopDomains.isActive,
        displayOrder: knowledgeTopDomains.displayOrder,
      })
      .from(knowledgeTopDomains)
      .where(includeInactive ? undefined : eq(knowledgeTopDomains.isActive, true))
      .orderBy(asc(knowledgeTopDomains.displayOrder));
    return { domainCount: rows.length, domains: rows };
  },
};

// ── list_brain_sections ──────────────────────────────────────────────────
const listBrainSections: Capability = {
  name: 'list_brain_sections',
  title: 'List Brain sections',
  group: 'brain',
  safety: READ_ONLY,
  description:
    'List the Oracle Brain sections — synthesized, human-reviewed narratives of a business ' +
    'process or topic. Only approved sections are returned. Use get_brain_section to read one.',
  argsDescription: '{ domain?: string }',
  argsSchema: z.object({ domain: z.string().optional() }),
  exampleArgs: { domain: 'operations_systems' },
  commonFailures: ['No approved sections exist yet for the given domain — returns an empty list.'],
  relatedTools: ['get_brain_section', 'list_knowledge_domains'],
  invoke: async (rawArgs, ctx) => {
    const { domain } = rawArgs as { domain?: string };
    const conditions = [eq(brainSectionVersions.reviewStatus, 'approved')];
    if (domain) {
      conditions.push(
        eq(
          brainSections.knowledgeDomain,
          domain as (typeof brainSections.knowledgeDomain.enumValues)[number],
        ),
      );
    }
    const rows = await ctx.db
      .select({
        id: brainSections.id,
        title: brainSections.title,
        category: brainSections.category,
        knowledgeDomain: brainSections.knowledgeDomain,
        relatedDomains: brainSections.relatedDomains,
        versionNumber: brainSectionVersions.versionNumber,
        updatedAt: brainSections.updatedAt,
      })
      .from(brainSections)
      .innerJoin(brainSectionVersions, eq(brainSectionVersions.id, brainSections.currentVersionId))
      .where(and(...conditions))
      .orderBy(asc(brainSections.knowledgeDomain), asc(brainSections.title));
    return { sectionCount: rows.length, sections: rows };
  },
};

// ── get_brain_section ────────────────────────────────────────────────────
const getBrainSection: Capability = {
  name: 'get_brain_section',
  title: 'Get Brain section',
  group: 'brain',
  safety: READ_ONLY,
  description:
    'Read the full markdown of one approved Oracle Brain section by ID, plus the IDs of the ' +
    'approved claims it was synthesized from.',
  argsDescription: '{ id: string }',
  argsSchema: z.object({ id: z.string().min(1) }),
  exampleArgs: { id: 'operations_systems_overview' },
  commonFailures: [
    'The section id does not exist.',
    'The section exists but its current version is not approved — it is withheld.',
  ],
  relatedTools: ['list_brain_sections'],
  invoke: async (rawArgs, ctx) => {
    const { id } = rawArgs as { id: string };
    const rows = await ctx.db
      .select({
        id: brainSections.id,
        title: brainSections.title,
        category: brainSections.category,
        knowledgeDomain: brainSections.knowledgeDomain,
        relatedDomains: brainSections.relatedDomains,
        markdown: brainSectionVersions.markdown,
        versionNumber: brainSectionVersions.versionNumber,
        changeSummary: brainSectionVersions.changeSummary,
        reviewedAt: brainSectionVersions.reviewedAt,
      })
      .from(brainSections)
      .innerJoin(brainSectionVersions, eq(brainSectionVersions.id, brainSections.currentVersionId))
      .where(and(eq(brainSections.id, id), eq(brainSectionVersions.reviewStatus, 'approved')))
      .limit(1);

    const section = rows[0];
    if (!section) {
      return {
        found: false,
        message: `No approved Brain section found with id "${id}". Use list_brain_sections to see available sections.`,
      };
    }

    const claimRows = await ctx.db
      .select({ claimId: sectionClaims.claimId })
      .from(sectionClaims)
      .where(eq(sectionClaims.sectionId, id));

    return { found: true, ...section, sourceClaimIds: claimRows.map((r) => r.claimId) };
  },
};

/** The full hidden registry. Order here is the default browse order. */
export const CAPABILITIES: Capability[] = [
  searchBusinessKnowledge,
  listKnowledgeDomains,
  listBrainSections,
  getBrainSection,
];

/**
 * Intent keyword → capability groups. Lets tool_search match on what an agent
 * is trying to do, not just exact names. Extend when adding capabilities.
 */
export const KEYWORD_GROUPS: Record<string, string[]> = {
  // knowledge / claims
  claim: ['knowledge'],
  claims: ['knowledge'],
  process: ['knowledge', 'brain'],
  rule: ['knowledge'],
  rules: ['knowledge'],
  policy: ['knowledge'],
  knowledge: ['knowledge'],
  search: ['knowledge'],
  fact: ['knowledge'],
  facts: ['knowledge'],
  operation: ['knowledge'],
  operations: ['knowledge', 'taxonomy'],
  system: ['knowledge'],
  workflow: ['knowledge', 'brain'],
  approval: ['knowledge'],
  evidence: ['knowledge'],
  file: ['knowledge'],
  naming: ['knowledge'],
  // taxonomy / domains
  domain: ['taxonomy'],
  domains: ['taxonomy'],
  taxonomy: ['taxonomy'],
  category: ['taxonomy'],
  categories: ['taxonomy'],
  boundary: ['taxonomy'],
  organize: ['taxonomy'],
  // brain / narratives
  brain: ['brain'],
  narrative: ['brain'],
  section: ['brain'],
  sections: ['brain'],
  summary: ['brain'],
  overview: ['brain'],
  synthesis: ['brain'],
  document: ['brain', 'knowledge'],
  docs: ['brain'],
};

export type { Capability, CapabilityContext };
