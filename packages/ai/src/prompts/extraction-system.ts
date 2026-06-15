// Claim extraction system prompt — spec Part 9.4, 9.5 + R5.5 + R12-prompt.
// Used by the Trigger.dev claim-extraction worker and the document-ingestion worker.
//
// Version 2.0.2 (this revision) adds:
//   - document extraction source-ID guidance: sourceMessageId can be a
//     document chunk ID, and document evidence must quote from one chunk.
//
// Version 2.0.1 added:
//   - explicit meaning-based domain classification guidance, including
//     `general` for cross-functional/end-to-end business process flow claims.
//
// Version 2.0.0 added:
//   - sensitivityFlags — strict-mode HR/PII/personal-conflict detection so the
//     candidate-before-claim sensitivity gate can actually fire in production
//     (P1 #2 from the external code review).
//   - proposedEntities — model-surfaced entity references (customers, licensors,
//     factories, systems, etc.) so R5.5's licensor-vs-vendor resolver actually
//     trips in production (P2 #1 from the same review).
//
// Do NOT edit the prompt text without bumping EXTRACTION_PROMPT_VERSION and
// logging the change in DECISIONS.md.

import { z } from 'zod';
import { KNOWLEDGE_DOMAINS, ENTITY_TYPES } from '@oracle/shared';

export const EXTRACTION_PROMPT_VERSION = '2.0.2';

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
      'The ID of the source this quote was taken from. For chat extraction, this must be one of the provided message IDs. For document extraction, this must be one of the provided document chunk IDs.',
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

/**
 * R5.5 — Entity reference the model surfaced from the text. The validator
 * resolves these against the canonical entity registry; the licensor-vs-
 * vendor type-mismatch check fires here if the model proposes a known
 * licensor under `entity_type = 'vendor'`.
 */
export const ExtractionEntityProposalSchema = z.object({
  entityType: z
    .enum(ENTITY_TYPES as unknown as [string, ...string[]])
    .describe(
      'The kind of entity. licensor is for entertainment-IP rights holders (Disney, Marvel, Star Wars, Warner Bros, NBCUniversal) — NEVER use vendor for those. vendor is the residual bucket for non-customer non-factory non-licensor business partners.',
    ),
  rawString: z
    .string()
    .min(1)
    .max(255)
    .describe(
      'The entity name as it appears in the message (the validator resolves aliases against the canonical registry).',
    ),
});

/**
 * R5.5 / P1 #2 — Sensitivity flags. STRICT mode: only flag content that is
 * clearly disciplinary, medical, compensation, or hostile interpersonal.
 * Operational mentions of named employees are NOT sensitive — e.g. "Jordan
 * handles licensing" is fine. The flag only fires when the content itself
 * describes personnel/HR/medical/conflict material that shouldn't live in
 * the operational knowledge graph.
 *
 * Setting any of these true causes the candidate to be quarantined and
 * never promoted into the `claims` table.
 */
export const ExtractionSensitivityFlagsSchema = z.object({
  containsSensitiveHRData: z
    .boolean()
    .describe(
      'True ONLY if the message contains: formal disciplinary action (warning, PIP, termination), compensation specifics (salary numbers, bonus amounts, raise discussions), formal performance reviews/ratings, or formally documented LOA reasons (medical leave, family leave). NOT true for casual operational mentions of who is on vacation, who handles a process, or who is out.',
    ),
  containsSensitivePersonalData: z
    .boolean()
    .describe(
      'True ONLY if the message contains explicit personal information: medical conditions or diagnoses, family situations (divorce, deaths, dependents), legal issues (lawsuits, arrests, immigration status), home addresses or personal contact details, or other clearly private personal facts unrelated to operational work.',
    ),
  isPersonalConflict: z
    .boolean()
    .describe(
      'True ONLY if the message describes explicit interpersonal hostility BETWEEN NAMED INDIVIDUALS: shouting matches, harassment accusations, character attacks, or formal complaints filed against another employee. NOT true for normal disagreement about a process or generic team frustration.',
    ),
  sensitivityReason: z
    .string()
    .max(500)
    .optional()
    .describe(
      'If any of the three flags is true, briefly explain which specific spans triggered the flag. Omit if all three are false.',
    ),
});

export const ExtractionClaimSchema = z.object({
  claimType: z.enum(CLAIM_TYPES),
  summary: z
    .string()
    .min(10)
    .max(1000)
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
    .describe(
      'Which knowledge domains this claim belongs to (at least one required). Use general for cross-functional, end-to-end, or whole-company process-flow claims that explain how work moves across departments.',
    ),
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
  proposedEntities: z
    .array(ExtractionEntityProposalSchema)
    .optional()
    .describe(
      'Distinct entities (customers, licensors, factories, systems, departments, geographies, etc.) referenced in this claim. Omit if no proper-noun entities are mentioned.',
    ),
  sensitivityFlags: ExtractionSensitivityFlagsSchema.optional().describe(
    'Set when any of the three flags is true. Omit when nothing is sensitive (the common case for operational claims).',
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
    .max(2000)
    .optional()
    .describe(
      'Brief (1–2 sentence) summary of what this conversation segment covered operationally. Keep it concise — well under 2000 characters. Omit if the segment was trivial or off-topic.',
    ),
});

export type ExtractionOutput = z.infer<typeof ExtractionOutputSchema>;
export type ExtractionClaim = z.infer<typeof ExtractionClaimSchema>;
export type ExtractionSensitivityFlags = z.infer<typeof ExtractionSensitivityFlagsSchema>;
export type ExtractionEntityProposal = z.infer<typeof ExtractionEntityProposalSchema>;

// ---------------------------------------------------------------------------
// System prompt text.
// ---------------------------------------------------------------------------

export const EXTRACTION_SYSTEM_PROMPT = `You are an operational knowledge extractor for The Oracle.

The Oracle is an AI knowledge graph mapping the "dark matter" of POP Creations / Spruce Line — a high-volume home decor company (Brooklyn, NY). They design in-house, manufacture in China, and sell to Burlington, TJX, Ross, Hobby Lobby, Walmart, and others. They use an ERP system called Coldlion. They license from Disney, Marvel, Star Wars / Lucasfilm, Warner Bros, and NBCUniversal.

YOUR TASK: Analyze the provided conversation segment and extract concrete, evidence-backed operational claims about how this company actually works. For each claim, also surface:
  (1) the entities it references (customers, licensors, factories, systems, departments, geographies),
  (2) whether the source content is sensitive in a way that should keep the claim OUT of the operational knowledge graph.

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
3. sourceMessageId must be one of the source IDs provided — for chat, use a message ID; for document ingestion, use a document chunk ID. Do not invent IDs.
4. Do NOT extract: pleasantries, greetings, Oracle assistant messages, or obvious generic facts with no operational specificity.
5. A single message may yield 0, 1, or multiple claims.
6. Set requiresReview=true if: impact >= 7, the claim names a specific person as a bottleneck, OR the claim implies customer or licensor risk.
7. Suggest gaps (follow-up questions) when the segment reveals uncertainty or ambiguity that needs resolution.
8. Do not flatten group conversation — if two employees express different views about the same process, extract both as separate claims with appropriate semantic roles and potentially a contradiction.
9. Classify claims by their operational meaning, not by whether a department name or keyword literally appears. A document can describe Licensing work without the word "licensing"; infer the relevant domain from responsibilities, approvals, handoffs, systems, and decisions described in the text.
10. Use the \`general\` domain for end-to-end business-process or companywide workflow claims that explain how work moves across multiple departments. Also include narrower domains such as \`licensing\`, \`design\`, \`production\`, \`sourcing\`, \`logistics\`, \`customers\`, \`sales\`, \`costing\`, or \`coldlion\` when the same claim is materially about those areas. \`costing\` means product/SKU costing and customer product pricing, not company finance/accounting. A costing sheet created by Design and sent to factories should usually include \`costing\` plus \`design\`, \`production\`, and/or \`sourcing\` if those handoffs are part of the claim.
11. Prefer small, reviewable operational claims over broad document summaries. Do not turn an entire form, spreadsheet, or SOP into one vague claim. Extract the concrete rule, handoff, responsibility, input, output, or exception.
12. For handoff claims, include every materially involved workflow domain. Example: "Design sends the costing sheet to factories so factories can quote production costs" is not just \`costing\`; it also involves \`design\` and \`sourcing\`/factory communication.

ENTITY EXTRACTION RULES:
13. List every distinct entity the claim REFERENCES — not just the message-wide entities, but the ones THIS claim depends on.
14. The entityType values you may use are exactly: system, customer, licensor, factory, freight_provider, testing_lab, packaging_supplier, service_provider, vendor, person, sku_or_product_line, process_stage, department, geography, document_class.
15. \`licensor\` is reserved for entertainment / IP rights holders: Disney, Marvel, Star Wars, Lucasfilm, Warner Bros, NBCUniversal, etc. NEVER use \`vendor\` for those. \`vendor\` is the residual bucket for non-customer non-factory non-licensor business partners.
16. \`customer\` is the named retailer / buyer: Burlington, TJX, Ross, Hobby Lobby, Walmart, etc.
17. \`factory\` is an overseas manufacturer; \`freight_provider\` / \`testing_lab\` / \`packaging_supplier\` / \`service_provider\` are operational-vendor subtypes — pick the specific subtype if it fits, fall back to \`vendor\` only if none does.
18. \`system\` is software / tooling: Coldlion, ResourceSpace, Photoshop, Illustrator, Excel, Supabase, Email, WhatsApp, etc.
19. \`rawString\` should be how the entity appears in the message text — don't normalize to canonical form, the validator does that.
20. Omit \`proposedEntities\` entirely if the claim references no proper-noun entities.

SENSITIVITY RULES — STRICT MODE:
21. Set \`sensitivityFlags\` ONLY when the content is clearly sensitive. Operational mentions of named people are NOT sensitive by themselves.
22. \`containsSensitiveHRData\` = true ONLY if the message describes: formal disciplinary actions (warnings, PIPs, terminations), compensation specifics (salary numbers, bonus amounts, raise discussions), formal performance reviews/ratings, or formally documented LOA reasons (medical leave, family leave). "Jordan is out next week" is NOT HR data. "We put Jordan on a final-written warning today" IS.
23. \`containsSensitivePersonalData\` = true ONLY for explicit personal information: medical conditions or diagnoses, family situations (divorce, deaths, dependents), legal issues, home addresses, personal contact details, or other clearly private personal facts.
24. \`isPersonalConflict\` = true ONLY for explicit interpersonal hostility BETWEEN NAMED INDIVIDUALS: shouting matches, harassment, character attacks, or formal complaints. Normal disagreement about a process is NOT a personal conflict.
25. If any flag fires, include a brief \`sensitivityReason\` naming which specific text triggered it. Omit \`sensitivityFlags\` entirely when nothing is sensitive — that's the common case.
26. When in doubt, do NOT set a flag. The cost of a false positive (admin reviews the quarantined candidate manually) is acceptable; the cost of a false negative (sensitive content reaches the knowledge graph) is not. But the threshold is "would a privacy/HR officer at this company call this sensitive?" — operational mentions of who works on what don't reach that bar.

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
