// Claim extraction system prompt — spec Part 9.4, 9.5.
// Used by the Trigger.dev claim-extraction worker.
// Do NOT edit the prompt text without bumping EXTRACTION_PROMPT_VERSION
// and logging the change in DECISIONS.md.

import { z } from 'zod';
import { KNOWLEDGE_DOMAINS } from '@oracle/shared';

export const EXTRACTION_PROMPT_VERSION = '1.0.0';

// ---------------------------------------------------------------------------
// Claim type taxonomy (spec 9.4 + Part 6).
// ---------------------------------------------------------------------------
export const CLAIM_TYPES = [
  'process_rule',      // How something normally works
  'exception_rule',    // An exception to a standard process
  'bottleneck',        // A constraint or delay point (person, system, or approval)
  'workaround',        // An unofficial solution for a missing capability
  'system_limitation', // What a system (Coldlion, ERP, etc.) fails to do
  'dependency',        // Something that must occur before something else
  'handoff_gap',       // Information lost between departments
  'contradiction',     // Two conflicting facts about the same process
  'process_ambiguity', // Unclear ownership or unclear when/how something happens
] as const;

export type ClaimType = (typeof CLAIM_TYPES)[number];

// Group chat semantic roles (spec 9.5).
export const SEMANTIC_ROLES = [
  'claim_stated',
  'claim_confirmed',
  'claim_challenged',
  'claim_refined',
  'exception_introduced',
  'process_ambiguity_revealed',
] as const;

export type SemanticRole = (typeof SEMANTIC_ROLES)[number];

// ---------------------------------------------------------------------------
// Zod output schema for generateObject calls.
// ---------------------------------------------------------------------------

export const ExtractionEvidenceSchema = z.object({
  exactQuote: z
    .string()
    .min(5)
    .describe(
      'Verbatim substring from the source message — must appear character-for-character in the message content. Do not paraphrase.',
    ),
  sourceMessageId: z
    .string()
    .describe(
      'The ID of the message this quote was taken from. Must be one of the provided message IDs.',
    ),
  confidence: z
    .number()
    .int()
    .min(1)
    .max(10)
    .describe('Confidence that this quote supports the claim (1=uncertain, 10=certain).'),
});

export const ExtractionGapSchema = z.object({
  questionToAsk: z
    .string()
    .min(10)
    .describe('A follow-up question that would resolve an uncertainty revealed in this segment.'),
  whyItMatters: z
    .string()
    .min(10)
    .describe('Why resolving this gap is operationally important for POP Creations / Spruce Line.'),
  priority: z.enum(['low', 'medium', 'high', 'urgent']),
});

export const ExtractionClaimSchema = z.object({
  claimType: z.enum(CLAIM_TYPES),
  summary: z
    .string()
    .min(10)
    .max(500)
    .describe(
      'One declarative sentence stating what this claim asserts about company operations. Should be independently comprehensible without the source messages.',
    ),
  impactScore: z
    .number()
    .int()
    .min(1)
    .max(10)
    .describe('Business impact if this claim is true (1=trivial curiosity, 10=critical blocker).'),
  confidenceScore: z
    .number()
    .int()
    .min(1)
    .max(10)
    .describe(
      'How confident you are that this is a reliable, well-supported operational claim (1=speculative, 10=certain from explicit statement).',
    ),
  domains: z
    .array(z.enum(KNOWLEDGE_DOMAINS as unknown as [string, ...string[]]))
    .min(1)
    .describe('Which knowledge domains this claim belongs to (at least one required).'),
  evidence: ExtractionEvidenceSchema,
  semanticRole: z
    .enum(SEMANTIC_ROLES)
    .optional()
    .describe(
      'In group chats: how this claim was introduced. Omit for single-speaker segments.',
    ),
  requiresReview: z
    .boolean()
    .describe(
      'Set true if any of: impact >= 7, the claim names a specific person as a bottleneck, or the claim implies customer or licensor risk.',
    ),
  suggestedGaps: z
    .array(ExtractionGapSchema)
    .optional()
    .describe(
      'Follow-up questions that would resolve uncertainties or ambiguities revealed in this segment.',
    ),
});

export const ExtractionOutputSchema = z.object({
  claims: z
    .array(ExtractionClaimSchema)
    .describe('All operational claims extracted from this conversation segment. Empty array if no claims found.'),
  segmentSummary: z
    .string()
    .max(300)
    .optional()
    .describe(
      'Brief (1–2 sentence) summary of what this conversation segment covered operationally. Omit if the segment was trivial or off-topic.',
    ),
});

export type ExtractionOutput = z.infer<typeof ExtractionOutputSchema>;
export type ExtractionClaim = z.infer<typeof ExtractionClaimSchema>;

// ---------------------------------------------------------------------------
// System prompt text.
// ---------------------------------------------------------------------------

export const EXTRACTION_SYSTEM_PROMPT = `You are an operational knowledge extractor for The Oracle.

The Oracle is an AI knowledge graph mapping the "dark matter" of POP Creations / Spruce Line — a high-volume home decor company (Brooklyn, NY). They design in-house, manufacture in China, and sell to Burlington, TJX, Ross, Hobby Lobby, Walmart, and others. They use an ERP system called Coldlion.

YOUR TASK: Analyze the provided conversation segment and extract concrete, evidence-backed operational claims about how this company actually works.

CLAIM TYPES:
- process_rule: How something normally works ("We always send artwork to China after licensor approval")
- exception_rule: An exception to a standard process ("For Walmart seasonal, sourcing sees it earlier")
- bottleneck: A constraint, delay, or dependency on a specific person/system/approval
- workaround: An unofficial solution someone built because the official system is insufficient
- system_limitation: What a system (Coldlion, ERP, email, spreadsheet) fails to do or show
- dependency: Something that must occur before something else can proceed
- handoff_gap: Information that tends to get lost between departments or people
- contradiction: Two conflicting statements about the same process
- process_ambiguity: Unclear ownership, unclear when something happens, or unclear who is responsible

GROUP CHAT SEMANTICS — track how claims interact when multiple employees speak:
- claim_stated: First assertion of a new fact
- claim_confirmed: Another employee agrees
- claim_challenged: Another employee disagrees
- claim_refined: A nuance or caveat is added to a prior claim
- exception_introduced: An exception to a stated rule is revealed
- process_ambiguity_revealed: The conversation reveals that employees have conflicting understandings

EXTRACTION RULES:
1. Only extract claims supported by what employees actually said.
2. exactQuote MUST be a verbatim substring of the source message — never paraphrase.
3. sourceMessageId must be one of the message IDs provided — do not invent IDs.
4. Do NOT extract: pleasantries, greetings, Oracle assistant messages, or obvious generic facts with no operational specificity.
5. A single message may yield 0, 1, or multiple claims.
6. Set requiresReview=true if: impact >= 7, the claim names a specific person as a bottleneck, OR the claim implies customer or licensor risk.
7. Suggest gaps (follow-up questions) when the segment reveals uncertainty or ambiguity that needs resolution.
8. Do not flatten group conversation — if two employees express different views about the same process, extract both as separate claims with appropriate semantic roles and potentially a contradiction.

OUTPUT: Return only the structured JSON matching the schema. No narrative explanation outside the JSON.`;

// ---------------------------------------------------------------------------
// Helper: format a conversation segment for the extraction model.
// ---------------------------------------------------------------------------

export type FormattedMessage = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  authorName: string | null;
  createdAt: Date;
};

/**
 * Format a list of messages into a labeled conversation string for the extraction model.
 * Each message gets its ID, speaker, timestamp, and content clearly marked.
 */
export function formatConversationSegment(msgs: FormattedMessage[]): string {
  const lines: string[] = ['CONVERSATION SEGMENT:', '---'];
  for (const m of msgs) {
    if (m.role === 'system') continue;
    const speaker =
      m.role === 'assistant' ? '[Oracle — do not extract claims from this]' : `[${m.authorName ?? 'Unknown Employee'}]`;
    const timestamp = new Date(m.createdAt).toISOString().slice(0, 16).replace('T', ' ');
    lines.push(`Message ID: ${m.id}`);
    lines.push(`Speaker: ${speaker}`);
    lines.push(`Time: ${timestamp}`);
    lines.push(`Content: ${m.content}`);
    lines.push('---');
  }
  return lines.join('\n');
}
