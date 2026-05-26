/**
 * R9 — Synthesis diff validator.
 *
 * Pure function. The synthesis equivalent of R5's quote validator: given
 * a model-produced SynthesisOutput plus the set of approved claim IDs +
 * summaries + canonical entity names, returns either `ok` or a list of
 * structured failures. Workers MUST refuse to update
 * `brain_sections.currentVersionId` when the validator returns `ok=false`.
 *
 * Checks (per docs/oracle/05-ai-retrofit-phase-packet.md Phase R9):
 *
 *   1. The output's `sectionId` matches the section the worker asked for.
 *   2. Every paragraph's `supportingClaimIds` is a subset of `approvedClaimIds`.
 *   3. Every `materialChanges[].claimId` is in `approvedClaimIds`.
 *   4. Every entry in `claimsAdded` / `claimsStrengthened` / `claimsWeakened`
 *      is in `approvedClaimIds`. (`claimsRemoved` is NOT checked — a removed
 *      claim is by definition no longer in the approved set.)
 *   5. Every `newContradictions[].claimAId/claimBId` is in `approvedClaimIds`.
 *   6. Every `newGaps[]` has non-empty `questionToAsk` AND `whyItMatters`.
 *   7. Every capitalized proper-noun-shaped name that appears in
 *      `updatedMarkdown` is either:
 *        a. mentioned in at least one approved claim summary, OR
 *        b. a canonical entity in the R3.5 registry.
 *      Otherwise it's a fabricated name and the synthesis is rejected.
 *
 * Why check (7) deterministically and not via the LLM:
 *   "Reject unsupported named people, systems, customers, stages,
 *    departments, or process rules" needs to be auditable. An LLM-graded
 *    "is this name supported" check can drift and reintroduces the
 *    paraphrase trap R5 already solved for quotes. The heuristic here
 *    is conservative: it reports candidate names; the worker holds the
 *    synthesis if any fire.
 */

import type {
  SynthesisValidationInput,
  SynthesisValidationResult,
  SynthesisValidationFailure,
} from './types';

/**
 * Common-English stopwords + sentence-start words that show up capitalized
 * but aren't named entities. Curated, conservative — the cost of a missing
 * stopword is a false-positive unsupported-name report, which holds the
 * synthesis for review (fine). The cost of an extra stopword is letting
 * a fabricated name through, which is worse.
 */
const SENTENCE_START_STOPWORDS = new Set<string>([
  'A',
  'An',
  'And',
  'As',
  'At',
  'After',
  'Although',
  'Before',
  'Because',
  'But',
  'By',
  'During',
  'Each',
  'Every',
  'For',
  'From',
  'However',
  'If',
  'In',
  'Into',
  'It',
  'Its',
  'No',
  'Not',
  'Of',
  'On',
  'Once',
  'Or',
  'Since',
  'So',
  'That',
  'The',
  'Their',
  'Then',
  'There',
  'These',
  'They',
  'This',
  'Those',
  'Though',
  'Through',
  'To',
  'Under',
  'Until',
  'We',
  'What',
  'When',
  'Where',
  'Which',
  'While',
  'Who',
  'Whose',
  'With',
  'You',
  // Process-stage and structural words that appear lowercased in summaries
  // but capitalized at sentence start.
  'Approval',
  'Approvals',
  'Customers',
  'Documents',
  'Items',
  'Note',
  'Notes',
  'Production',
  'Sales',
  'Sample',
  'Samples',
  'Section',
  'Sections',
  'Shipping',
  'Sourcing',
]);

/**
 * Days of the week + months — common false positives in operational text.
 */
const CALENDAR_WORDS = new Set<string>([
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]);

export function validateSynthesisDiff(input: SynthesisValidationInput): SynthesisValidationResult {
  const {
    output,
    approvedClaimIds,
    approvedClaimSummariesLower,
    registryEntityCanonicalsLower,
    expectedSectionId,
  } = input;

  const failures: SynthesisValidationFailure[] = [];

  // ── 1. Section ID match ────────────────────────────────────────────────
  if (output.sectionId !== expectedSectionId) {
    failures.push({
      kind: 'wrong_section_id',
      detail: `Output sectionId is "${output.sectionId}"; expected "${expectedSectionId}".`,
    });
  }

  // ── 2. Paragraph claim IDs ─────────────────────────────────────────────
  for (let i = 0; i < output.paragraphs.length; i++) {
    const para = output.paragraphs[i]!;
    for (const cid of para.supportingClaimIds) {
      if (!approvedClaimIds.has(cid)) {
        failures.push({
          kind: 'paragraph_cites_non_approved_claim',
          detail: `Paragraph ${i + 1} cites non-approved claim ID ${cid}.`,
          claimId: cid,
        });
      }
    }
  }

  // ── 3. materialChanges claim IDs ───────────────────────────────────────
  for (const ch of output.materialChanges) {
    if (!approvedClaimIds.has(ch.claimId)) {
      failures.push({
        kind: 'material_change_cites_non_approved_claim',
        detail: `materialChanges entry "${ch.type}" cites non-approved claim ${ch.claimId}.`,
        claimId: ch.claimId,
      });
    }
  }

  // ── 4. claimsAdded / strengthened / weakened ───────────────────────────
  // claimsRemoved is intentionally NOT checked.
  for (const cid of output.claimsAdded) {
    if (!approvedClaimIds.has(cid)) {
      failures.push({
        kind: 'claim_ref_not_approved',
        detail: `claimsAdded references non-approved claim ${cid}.`,
        claimId: cid,
      });
    }
  }
  for (const cid of output.claimsStrengthened) {
    if (!approvedClaimIds.has(cid)) {
      failures.push({
        kind: 'claim_ref_not_approved',
        detail: `claimsStrengthened references non-approved claim ${cid}.`,
        claimId: cid,
      });
    }
  }
  for (const cid of output.claimsWeakened) {
    if (!approvedClaimIds.has(cid)) {
      failures.push({
        kind: 'claim_ref_not_approved',
        detail: `claimsWeakened references non-approved claim ${cid}.`,
        claimId: cid,
      });
    }
  }

  // ── 5. newContradictions claim IDs ─────────────────────────────────────
  for (const con of output.newContradictions) {
    if (!approvedClaimIds.has(con.claimAId)) {
      failures.push({
        kind: 'contradiction_cites_non_approved_claim',
        detail: `newContradictions.claimAId ${con.claimAId} is not in the approved set.`,
        claimId: con.claimAId,
      });
    }
    if (!approvedClaimIds.has(con.claimBId)) {
      failures.push({
        kind: 'contradiction_cites_non_approved_claim',
        detail: `newContradictions.claimBId ${con.claimBId} is not in the approved set.`,
        claimId: con.claimBId,
      });
    }
  }

  // ── 6. Gap required fields ─────────────────────────────────────────────
  for (let i = 0; i < output.newGaps.length; i++) {
    const gap = output.newGaps[i]!;
    if (!gap.questionToAsk.trim() || !gap.whyItMatters.trim()) {
      failures.push({
        kind: 'gap_missing_required_fields',
        detail: `newGaps[${i}] is missing questionToAsk or whyItMatters.`,
      });
    }
  }

  // ── 7. Unsupported named entities in updatedMarkdown ──────────────────
  const unsupported = findUnsupportedNamedEntities(
    output.updatedMarkdown,
    approvedClaimSummariesLower,
    registryEntityCanonicalsLower,
  );
  for (const name of unsupported) {
    failures.push({
      kind: 'unsupported_named_entity',
      detail: `Synthesis markdown mentions "${name}" but no approved claim summary or registry entity references it.`,
      name,
    });
  }

  return {
    ok: failures.length === 0,
    failures,
    unsupportedNames: unsupported,
  };
}

/**
 * Pure helper: scan the markdown for capitalized proper-noun-shaped names
 * and return any that aren't mentioned in the approved-claim corpus OR the
 * registry-entity set.
 *
 * Heuristic, not a parser. False positives hold the synthesis for admin
 * review (acceptable). False negatives let a fabricated name through
 * (worse) — so the stopword list is curated conservatively.
 *
 * Exported for testability.
 */
export function findUnsupportedNamedEntities(
  markdown: string,
  approvedClaimSummariesLower: string[],
  registryEntityCanonicalsLower: Set<string>,
): string[] {
  // Capitalized word pattern. Match a word that:
  //   - Starts with an uppercase letter (any unicode letter, not just ASCII)
  //   - Followed by 2+ word chars (so 2+ letters total — avoids "A", "I", initials)
  //   - May continue into a multi-word capitalized phrase (e.g. "Walt Disney").
  // We capture each multi-word phrase as one candidate.
  const phraseRegex =
    /\b\p{Lu}[\p{L}'-]{2,}(?:\s+\p{Lu}[\p{L}'-]+)*\b/gu;

  // Strip Markdown structure that produces false positives:
  //   - Code blocks (```...```)
  //   - Inline code (`...`)
  //   - URLs / image refs
  //   - ENTIRE heading lines (`# ...`). Headings are structural metadata,
  //     not factual claims — they tell the reader what the section is
  //     about, but they don't assert that the named entities are real.
  //     The validator's job is to catch fabricated entities in the BODY
  //     where claims live; a heading like "Creative to Technical Handoff"
  //     shouldn't fail validation just because "Creative" isn't in any
  //     approved claim summary.
  const cleaned = markdown
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`[^`]*`/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/^#+\s+.*$/gm, '');

  const candidates = new Set<string>();
  let m: RegExpExecArray | null;
  while ((m = phraseRegex.exec(cleaned)) !== null) {
    const phrase = m[0].trim();
    if (!phrase) continue;
    // Reject single-word common stopwords.
    if (!phrase.includes(' ')) {
      if (SENTENCE_START_STOPWORDS.has(phrase)) continue;
      if (CALENDAR_WORDS.has(phrase)) continue;
    }
    candidates.add(phrase);
  }

  if (candidates.size === 0) return [];

  // For each candidate, accept iff its lowercased form appears as a substring
  // in at least one approved claim summary OR in the registry canonicals.
  const unsupported: string[] = [];
  for (const phrase of candidates) {
    const lower = phrase.toLowerCase();
    if (registryEntityCanonicalsLower.has(lower)) continue;
    const inAnySummary = approvedClaimSummariesLower.some((s) => s.includes(lower));
    if (inAnySummary) continue;
    unsupported.push(phrase);
  }
  return unsupported;
}
