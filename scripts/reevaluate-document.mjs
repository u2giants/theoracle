// One-off ops tool: re-evaluate a single uploaded document through the
// document-ingestion pipeline with a clean slate.
//
// WHY: ingestion is idempotent only by content/candidate hash. Re-running after
// a chunking/prompt change therefore ADDS new claims beside the old ones instead
// of replacing them. This script removes a document's prior extraction artifacts
// (claims, evidence, chunks, candidates, batches, domain tags) and resets the
// document to `pending_processing` so the worker re-extracts it from scratch.
//
// SAFETY:
//   - DRY-RUN by default. It only deletes when APPLY=1 is set.
//   - It REFUSES to proceed if any target claim is (a) cited in the Brain
//     (section_claims), (b) part of a contradiction, (c) referenced by a gap, or
//     (d) multi-source (has evidence from other documents/messages). Those cases
//     need manual handling (supersede via /admin/claims), not deletion.
//   - All deletes run inside ONE transaction.
//
// USAGE (PowerShell):
//   $env:PROD_URL = "<session-pooler connection string>"
//   $env:DOCUMENT_ID = "9d09fa89-3a46-465e-a98b-837287c9e22a"
//   node scripts/reevaluate-document.mjs           # dry run — prints the plan
//   $env:APPLY = "1"; node scripts/reevaluate-document.mjs   # actually do it
//
// AFTER APPLY: trigger the `document-ingestion` task for DOCUMENT_ID (or wait for
// the document-ingestion-sweep cron). The NEW worker code must be deployed first,
// otherwise you just re-run the old logic.

import postgres from 'postgres';

const url = process.env.PROD_URL || process.env.DIRECT_URL || process.env.DATABASE_URL;
const docId = process.env.DOCUMENT_ID;
const APPLY = process.env.APPLY === '1';

if (!url) throw new Error('Set PROD_URL (or DIRECT_URL/DATABASE_URL).');
if (!docId) throw new Error('Set DOCUMENT_ID.');

const sql = postgres(url, { max: 1, prepare: false, connect_timeout: 30 });

function log(...a) {
  console.log(...a);
}

try {
  const [doc] = await sql`select id, file_name, status from documents where id = ${docId}`;
  if (!doc) throw new Error(`document ${docId} not found`);
  log(`Document: ${doc.file_name} (${doc.id}) — status=${doc.status}`);

  const chunkIds = (
    await sql`select id from document_chunks where document_id = ${docId}`
  ).map((r) => r.id);
  const claimIds = (
    await sql`select distinct ce.claim_id from claim_evidence ce
              join document_chunks dc on dc.id = ce.source_document_chunk_id
              where dc.document_id = ${docId} and ce.claim_id is not null`
  ).map((r) => r.claim_id);
  const candidateIds = (
    await sql`select distinct cce.candidate_id from extraction_candidate_evidence cce
              join document_chunks dc on dc.id = cce.source_document_chunk_id
              where dc.document_id = ${docId} and cce.candidate_id is not null`
  ).map((r) => r.candidate_id);
  const batchIds = (
    await sql`select distinct eb.id from extraction_batches eb
              join job_runs jr on jr.id = eb.job_run_id
              where jr.input_json->>'documentId' = ${docId}`
  ).map((r) => r.id);

  log(
    `Scope: ${chunkIds.length} chunks, ${claimIds.length} claims, ` +
      `${candidateIds.length} candidates, ${batchIds.length} batches`,
  );

  // ── Safety guards ──────────────────────────────────────────────────────
  const guard = async (label, q) => {
    if (claimIds.length === 0) return 0;
    const [{ n }] = await q;
    const num = Number(n);
    if (num > 0) log(`  ⚠ BLOCKER — ${label}: ${num}`);
    return num;
  };
  let blockers = 0;
  blockers += await guard(
    'claims also have evidence from OTHER sources (multi-source)',
    sql`select count(*) n from (
          select ce.claim_id from claim_evidence ce
          left join document_chunks dc on dc.id = ce.source_document_chunk_id
          where ce.claim_id = any(${claimIds})
          group by ce.claim_id
          having bool_or(dc.document_id is distinct from ${docId} or ce.source_document_chunk_id is null)
        ) x`,
  );
  blockers += await guard(
    'claims cited in the Brain (section_claims)',
    sql`select count(*) n from section_claims where claim_id = any(${claimIds})`,
  );
  blockers += await guard(
    'claims in contradictions',
    sql`select count(*) n from contradictions
        where claim_a_id = any(${claimIds}) or claim_b_id = any(${claimIds}) or resolved_by_claim_id = any(${claimIds})`,
  );
  blockers += await guard(
    'claims referenced by gaps',
    sql`select count(*) n from gaps g
        where g.resolved_by_claim_id = any(${claimIds})
           or exists (select 1 from jsonb_array_elements_text(g.related_claim_ids) x(v) where x.v = any(${claimIds}))`,
  );

  if (blockers > 0) {
    log(`\nABORTING: ${blockers} provenance blocker(s). Handle these claims via /admin/claims (supersede/reject) first.`);
    await sql.end();
    process.exit(1);
  }
  log('  ✓ no provenance blockers (safe to delete)');

  if (!APPLY) {
    log('\nDRY RUN — nothing deleted. Re-run with APPLY=1 (after deploying the new worker) to execute.');
    log('Then trigger `document-ingestion` for this DOCUMENT_ID.');
    await sql.end();
    process.exit(0);
  }

  // ── Apply (single transaction) ─────────────────────────────────────────
  const deleted = {};
  await sql.begin(async (tx) => {
    const del = async (key, q) => {
      const r = await q;
      deleted[key] = r.count ?? 0;
    };
    // Delete extraction artifacts FIRST so candidate→claim back-pointers
    // (promoted_to_claim_id / duplicate_of_claim_id) disappear by row deletion.
    // Nulling them in place would violate extraction_candidates' promoted/
    // duplicate consistency CHECK; deleting the row does not.
    if (candidateIds.length) {
      await del('extraction_validation_results', tx`delete from extraction_validation_results where candidate_id = any(${candidateIds})`);
      await del('extraction_candidate_evidence', tx`delete from extraction_candidate_evidence where candidate_id = any(${candidateIds})`);
      await del('extraction_candidates', tx`delete from extraction_candidates where id = any(${candidateIds})`);
    }
    if (claimIds.length) {
      // Safety net: any stray candidate (outside candidateIds) still pointing at
      // a target claim — delete it too, so the claim delete can't hit an FK.
      await tx`delete from extraction_candidates where promoted_to_claim_id = any(${claimIds}) or duplicate_of_claim_id = any(${claimIds})`;
      await del('claim_review_events', tx`delete from claim_review_events where claim_id = any(${claimIds}) or replacement_claim_id = any(${claimIds})`);
      await del('claim_domains', tx`delete from claim_domains where claim_id = any(${claimIds})`);
      await del('claim_entities', tx`delete from claim_entities where claim_id = any(${claimIds})`);
      await del('claim_top_domains', tx`delete from claim_top_domains where claim_id = any(${claimIds})`);
      await del('claim_sub_topics', tx`delete from claim_sub_topics where claim_id = any(${claimIds})`);
      await del('claim_translations', tx`delete from claim_translations where claim_id = any(${claimIds})`);
      // NOTE: employee_claims is a VIEW (not a base table), so it is not deleted here.
      await del('claim_metadata', tx`delete from claim_metadata where claim_id = any(${claimIds})`);
      await del('claim_evidence', tx`delete from claim_evidence where claim_id = any(${claimIds})`);
      await del('claims', tx`delete from claims where id = any(${claimIds})`);
    }
    if (batchIds.length) {
      // Only batches with no surviving candidates (all were doc-scoped).
      await del('extraction_batches', tx`delete from extraction_batches eb where eb.id = any(${batchIds})
        and not exists (select 1 from extraction_candidates c where c.extraction_batch_id = eb.id)`);
    }
    if (chunkIds.length) {
      await del('document_chunk_top_domains', tx`delete from document_chunk_top_domains where document_chunk_id = any(${chunkIds})`);
      await del('document_chunk_entities', tx`delete from document_chunk_entities where document_chunk_id = any(${chunkIds})`);
      // Belt-and-suspenders: any extraction evidence still pointing at these chunks.
      await tx`delete from extraction_candidate_evidence where source_document_chunk_id = any(${chunkIds})`;
    }
    await del('document_chunks', tx`delete from document_chunks where document_id = ${docId}`);
    await del('document_top_domains', tx`delete from document_top_domains where document_id = ${docId}`);
    await tx`update documents set status = 'pending_processing', processed_at = null, processing_error = null where id = ${docId}`;
  });

  log('\nDELETED:');
  for (const [k, v] of Object.entries(deleted)) log(`  ${k}: ${v}`);
  log(`\nDocument reset to pending_processing. Now trigger the document-ingestion task for ${docId}.`);
} finally {
  await sql.end();
}
