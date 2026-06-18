import { sql } from 'drizzle-orm';
import type { OracleDb } from '@oracle/db';

export type ClaimCorrectionLessonRow = {
  review_event_id: string;
  reviewed_at: string;
  reviewer_name: string | null;
  original_summary: string;
  revised_summary: string;
  reviewer_note: string | null;
  original_domains: string[] | null;
  revised_domains: string[] | null;
};

export type ClaimCorrectionLessonPack = {
  revisionCount: number;
  approvedRevisionCount: number;
  rows: ClaimCorrectionLessonRow[];
  promptBlock: string;
};

const MAX_SUMMARY_CHARS = 420;

function compact(text: string, maxChars = MAX_SUMMARY_CHARS): string {
  const normalized = text.replace(/\s+/g, ' ').trim();
  if (normalized.length <= maxChars) return normalized;
  return normalized.slice(0, maxChars - 1).trimEnd() + '…';
}

function formatDomainList(domains: string[] | null): string {
  return domains && domains.length > 0 ? domains.join(', ') : '(none recorded)';
}

export function buildClaimCorrectionLessonPromptBlock(
  rows: ClaimCorrectionLessonRow[],
): string {
  if (rows.length === 0) return '';

  const examples = rows.slice(0, 10).map((row, index) => {
    const note = row.reviewer_note ? `\n   Reviewer note: ${compact(row.reviewer_note, 260)}` : '';
    return [
      `${index + 1}. Original: ${compact(row.original_summary)}`,
      `   Corrected: ${compact(row.revised_summary)}`,
      `   Domains: ${formatDomainList(row.original_domains)} -> ${formatDomainList(row.revised_domains)}`,
      note,
    ].join('\n');
  });

  return `REVIEWER CORRECTION LESSONS
These are approved human corrections from prior claim reviews. Use them as behavioral guidance for NEW extraction. Do not copy these claims unless the current source text supports them.

Patterns to apply:
- Preserve business-specific terminology, synonyms, divisions, systems, departments, document names, and handoffs that the source makes explicit.
- Avoid broad, vague summaries when the source contains specific operational nuance.
- Do not collapse product costing, costing sheets, factory quote inputs, and customer product pricing into company finance/accounting.
- When a claim describes a handoff, include all materially involved workflow domains rather than only the final department.
- Distinguish process/system problems from generic business process: ERP, PLM, CRM, DAM, shared sheets, and internal tools usually belong in operations_systems and/or it_systems.
- Preserve POP vs Spruce distinctions and customer/licensor/factory context when they affect the operational rule.

Approved correction examples:
${examples.join('\n\n')}`;
}

export async function loadClaimCorrectionLessonPack(
  db: OracleDb,
  options: { limit?: number } = {},
): Promise<ClaimCorrectionLessonPack> {
  const limit = options.limit ?? 14;

  const [countsResult, rowsResult] = await Promise.all([
    db.execute(sql`
      SELECT
        COUNT(*) FILTER (WHERE cre.action = 'revise')::int AS revision_count,
        COUNT(*) FILTER (
          WHERE cre.action = 'revise'
            AND replacement.status = 'approved'
        )::int AS approved_revision_count
      FROM claim_review_events cre
      LEFT JOIN claims replacement ON replacement.id = cre.replacement_claim_id
    `),
    db.execute(sql`
      SELECT
        cre.id AS review_event_id,
        cre.created_at AS reviewed_at,
        reviewer.name AS reviewer_name,
        original.summary AS original_summary,
        replacement.summary AS revised_summary,
        cre.reviewer_note,
        COALESCE(original_domains.domain_ids, ARRAY[]::text[]) AS original_domains,
        COALESCE(revised_domains.domain_ids, ARRAY[]::text[]) AS revised_domains
      FROM claim_review_events cre
      JOIN claims original ON original.id = cre.claim_id
      JOIN claims replacement ON replacement.id = cre.replacement_claim_id
      LEFT JOIN employees reviewer ON reviewer.id = cre.reviewed_by_employee_id
      LEFT JOIN LATERAL (
        SELECT array_agg(ctd.top_domain_id ORDER BY ctd.top_domain_id) AS domain_ids
        FROM claim_top_domains ctd
        WHERE ctd.claim_id = original.id
      ) original_domains ON true
      LEFT JOIN LATERAL (
        SELECT array_agg(ctd.top_domain_id ORDER BY ctd.top_domain_id) AS domain_ids
        FROM claim_top_domains ctd
        WHERE ctd.claim_id = replacement.id
      ) revised_domains ON true
      WHERE cre.action = 'revise'
        AND replacement.status = 'approved'
      ORDER BY cre.created_at DESC
      LIMIT ${limit}
    `),
  ]);

  const counts = [...countsResult] as unknown as Array<{
    revision_count: number;
    approved_revision_count: number;
  }>;
  const rows = [...rowsResult] as unknown as ClaimCorrectionLessonRow[];

  return {
    revisionCount: Number(counts[0]?.revision_count ?? 0),
    approvedRevisionCount: Number(counts[0]?.approved_revision_count ?? 0),
    rows,
    promptBlock: buildClaimCorrectionLessonPromptBlock(rows),
  };
}
