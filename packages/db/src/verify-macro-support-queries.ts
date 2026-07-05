import { sql } from 'drizzle-orm';
import { getDirectDb } from './client';

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
  console.log(`✓ ${message}`);
}

async function main() {
  const db = getDirectDb();
  const [seed] = await db.execute<{ documentId: string }>(sql`
    SELECT dc.document_id AS "documentId"
    FROM document_chunks dc
    JOIN claim_evidence ce ON ce.source_document_chunk_id = dc.id
    JOIN claims c ON c.id = ce.claim_id
    WHERE c.status IN ('pending_review', 'approved')
    LIMIT 1
  `);
  if (!seed) {
    console.log('No document-backed pending/approved claims found; macro support SQL smoke skipped.');
    return;
  }

  const documentId = seed.documentId;
  const singleSourceRows = await db.execute(sql`
    SELECT DISTINCT
      c.id,
      c.summary,
      c.claim_type AS "claimType",
      c.claim_kind AS "claimKind",
      c.claim_kind_confidence AS "claimKindConfidence",
      c.claim_kind_review_status AS "claimKindReviewStatus",
      c.status,
      c.impact_score AS "impactScore",
      c.confidence_score AS "confidenceScore",
      c.created_at
    FROM claims c
    JOIN claim_evidence ce ON ce.claim_id = c.id
    JOIN document_chunks dc ON dc.id = ce.source_document_chunk_id
    WHERE dc.document_id = ${documentId}::uuid
      AND c.status IN ('pending_review', 'approved')
    ORDER BY c.impact_score DESC, c.confidence_score DESC, c.created_at DESC
    LIMIT 2
  `);
  assert(singleSourceRows.length >= 1, 'single-source macro support query executes');

  const crossSourceRows = await db.execute(sql`
    WITH seed_claims AS (
      SELECT DISTINCT c.id
      FROM claims c
      JOIN claim_evidence ce ON ce.claim_id = c.id
      JOIN document_chunks dc ON dc.id = ce.source_document_chunk_id
      WHERE dc.document_id = ${documentId}::uuid
        AND c.status IN ('pending_review', 'approved')
    ),
    seed_domains AS (
      SELECT DISTINCT ctd.top_domain_id
      FROM claim_top_domains ctd
      JOIN seed_claims sc ON sc.id = ctd.claim_id
    ),
    related_claims AS (
      SELECT DISTINCT c.id
      FROM claims c
      JOIN claim_top_domains ctd ON ctd.claim_id = c.id
      WHERE c.status IN ('pending_review', 'approved')
        AND ctd.top_domain_id IN (SELECT top_domain_id FROM seed_domains)
    )
    SELECT
      c.id,
      c.summary,
      c.claim_type AS "claimType",
      c.claim_kind AS "claimKind",
      c.claim_kind_confidence AS "claimKindConfidence",
      c.claim_kind_review_status AS "claimKindReviewStatus",
      c.status,
      c.impact_score AS "impactScore",
      c.confidence_score AS "confidenceScore"
    FROM claims c
    WHERE c.id IN (
      SELECT id FROM seed_claims
      UNION
      SELECT id FROM related_claims
    )
    ORDER BY
      CASE WHEN c.id IN (SELECT id FROM seed_claims) THEN 0 ELSE 1 END,
      c.impact_score DESC,
      c.confidence_score DESC,
      c.created_at DESC
    LIMIT 2
  `);
  assert(crossSourceRows.length >= 1, 'cross-source macro support query executes');

  const coverageRows = await db.execute(sql`
    SELECT DISTINCT c.id, c.summary, c.claim_type, c.claim_kind, c.status, c.created_at
    FROM claims c
    JOIN claim_evidence ce ON ce.claim_id = c.id
    JOIN document_chunks dc ON dc.id = ce.source_document_chunk_id
    WHERE dc.document_id = ${documentId}::uuid
    ORDER BY c.created_at DESC
    LIMIT 2
  `);
  assert(coverageRows.length >= 1, 'coverage-audit claim query executes');

  console.log('\nMacro support SQL smoke gate: PASS');
}

main().then(() => process.exit(0)).catch((err) => {
  console.error(err);
  process.exit(1);
});
