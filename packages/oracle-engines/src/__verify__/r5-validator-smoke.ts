/**
 * R5 acceptance gate verification script.
 *
 * Run with: pnpm --filter @oracle/engines verify:r5
 *
 * Proves the 6 cases enumerated in docs/oracle/05-ai-retrofit-phase-packet.md
 * Phase R5 "Required validation tests" plus extra coverage for the
 * source-pointer validator, normalization policy, candidate hash stability,
 * and the promotion decision function.
 *
 * Hard rule from the retrofit packet:
 *   "Do not proceed to Trigger.dev worker wiring [R6] until isolated
 *    validator tests pass."
 *
 * This file is in __verify__ so it's not part of the public package surface.
 */

import {
  validateQuote,
  validateSourcePointer,
  computeCandidateHash,
  canonicalizeSummary,
  decidePromotion,
  mapCandidateRowToSnapshotCandidate,
  mapEvidenceRowToValidatedEvidence,
  MARKDOWN_DOCUMENT_NORMALIZATION_POLICY,
  PDF_OCR_NORMALIZATION_POLICY,
  type CandidateSnapshot,
  type ExtractionCandidateRow,
  type ExtractionCandidateEvidenceRow,
} from '../extraction';

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error(`✗ ${msg}`);
    process.exit(1);
  }
  console.log(`✓ ${msg}`);
}

function main() {
  console.log('R5 quote validator + promotion smoke test\n');

  // ════════════════════════════════════════════════════════════════════
  // The 6 required validator cases from
  // docs/oracle/05-ai-retrofit-phase-packet.md Phase R5.
  // ════════════════════════════════════════════════════════════════════

  // ── R5 Test 1: Perfect match passes ─────────────────────────────────
  {
    const source =
      'I talked to Adam yesterday and we agreed that Burlington seasonal items need to go through the new routing guide.';
    const quote = 'Burlington seasonal items need to go through the new routing guide.';
    const res = validateQuote({ sourceText: source, exactQuoteProvided: quote });
    assert(res.verdict === 'exact_match', 'R5#1 perfect match → exact_match');
    assert(res.validationMethod === 'verbatim_includes', 'R5#1 method is verbatim_includes');
    assert(res.validatedExactQuote === quote, 'R5#1 reports the validated quote');
    assert(
      typeof res.validatedCharStart === 'number' &&
        res.validatedCharStart === source.indexOf(quote),
      'R5#1 reports the correct charStart',
    );
    assert(
      res.validatedCharEnd === res.validatedCharStart! + quote.length,
      'R5#1 reports the correct charEnd',
    );
  }

  // ── R5 Test 2: Grammar-fix hallucination fails ──────────────────────
  // Model "fixed" the typo'd source. Provenance must reject — the source
  // text does NOT contain the corrected wording.
  {
    const source = 'the fctry cant ship til thursday because of the storm.';
    const quote = 'The factory cannot ship until Thursday because of the storm.';
    const res = validateQuote({ sourceText: source, exactQuoteProvided: quote });
    assert(res.verdict === 'failed', 'R5#2 grammar-fix hallucination → failed');
    assert(
      res.failedCheckName === 'quote_exact_match',
      'R5#2 records the failed check as quote_exact_match',
    );
  }

  // ── R5 Test 3: Synthesized quote across two messages fails ──────────
  // The "source text" passed in is the concatenation of two messages with a
  // separator. The model synthesized a quote that DOESN'T literally appear
  // in either message — it bridges them. Provenance must reject.
  {
    const source = 'We need approval from Disney.\n---\nAnd we need it before Friday.';
    const quote = 'We need approval from Disney before Friday.';
    const res = validateQuote({ sourceText: source, exactQuoteProvided: quote });
    assert(res.verdict === 'failed', 'R5#3 synthesized cross-message quote → failed');
  }

  // ── R5 Test 4: Punctuation / whitespace rewrite fails (strict mode) ──
  // Model "cleaned up" the ellipsis. Strict verbatim must reject.
  {
    const source = 'Wait... let me check Coldlion.';
    const quote = 'Wait let me check Coldlion.';
    const res = validateQuote({ sourceText: source, exactQuoteProvided: quote });
    assert(res.verdict === 'failed', 'R5#4 punctuation rewrite under strict policy → failed');
  }
  // And the rewrite still fails even with PDF_OCR normalization — the
  // ellipsis isn't a whitespace difference; it's missing literal characters.
  {
    const source = 'Wait... let me check Coldlion.';
    const quote = 'Wait let me check Coldlion.';
    const res = validateQuote({
      sourceText: source,
      exactQuoteProvided: quote,
      normalizationPolicy: PDF_OCR_NORMALIZATION_POLICY,
    });
    assert(
      res.verdict === 'failed',
      'R5#4 punctuation rewrite is NOT rescued by PDF_OCR normalization',
    );
  }

  // ── R5 Test 5: Repeated quote ambiguity ─────────────────────────────
  // The same quote appears twice; without offsets we cannot pick.
  {
    const source =
      'OK. OK. Burlington items need to go through routing. Burlington items need to go through routing.';
    const quote = 'Burlington items need to go through routing.';
    const resNoOffsets = validateQuote({ sourceText: source, exactQuoteProvided: quote });
    assert(resNoOffsets.verdict === 'ambiguous', 'R5#5a ambiguous without offsets');
    assert(
      resNoOffsets.failedCheckName === 'quote_exact_match',
      'R5#5a records failed check as quote_exact_match',
    );

    // With correct offsets pointing at the second occurrence, validation passes.
    const secondIdx = source.lastIndexOf(quote);
    const resWithOffsets = validateQuote({
      sourceText: source,
      exactQuoteProvided: quote,
      charStartProvided: secondIdx,
      charEndProvided: secondIdx + quote.length,
    });
    assert(resWithOffsets.verdict === 'exact_match', 'R5#5b passes with correct offsets');
    assert(resWithOffsets.validatedCharStart === secondIdx, 'R5#5b reports the supplied charStart');
  }

  // ── R5 Test 6: Duplicate promotion retry safety (decidePromotion) ──
  // The pure decider must:
  //   - return `insert_new_claim` on the first try when no existing claim has the same hash
  //   - return `already_promoted` if the candidate is re-run after promotion
  //   - return `append_to_existing_claim` if another worker won the race
  {
    const baseSnapshot: CandidateSnapshot = {
      candidateHash: 'deadbeef',
      candidate: {
        id: 'cand-1',
        status: 'validated',
        summary: 'Burlington seasonal needs new routing.',
        claimType: 'process_rule',
        impactScore: 6,
        confidenceScore: 8,
        domains: ['customer_ops'],
      },
      validatedEvidence: [
        {
          id: 'ev-1',
          sourceType: 'message',
          sourceMessageId: 'msg-1',
          validatedExactQuote: 'Burlington seasonal needs new routing.',
          validatedCharStart: 0,
          validatedCharEnd: 39,
        },
      ],
      existingClaimWithSameHash: null,
    };

    const first = decidePromotion(baseSnapshot);
    assert(first.kind === 'insert_new_claim', 'R5#6a first promotion → insert_new_claim');

    // Replay the same call after the candidate has been marked promoted.
    const afterPromote = decidePromotion({
      ...baseSnapshot,
      candidate: { ...baseSnapshot.candidate, status: 'promoted', promotedToClaimId: 'claim-1' },
    });
    assert(
      afterPromote.kind === 'reject' && afterPromote.reason === 'already_promoted',
      'R5#6b retry on already-promoted candidate → reject(already_promoted) — no duplicate claim',
    );

    // Race scenario: candidate is still 'validated', but another worker
    // already inserted a claim with the same hash.
    const raced = decidePromotion({
      ...baseSnapshot,
      existingClaimWithSameHash: { claimId: 'claim-other' },
    });
    assert(
      raced.kind === 'append_to_existing_claim' && raced.existingClaimId === 'claim-other',
      'R5#6c race: existing claim with same hash → append_to_existing_claim',
    );
  }

  // ════════════════════════════════════════════════════════════════════
  // Extra coverage beyond the 6 required cases.
  // ════════════════════════════════════════════════════════════════════

  // ── Provided offsets that disagree with the source must fail ────────
  {
    const source = 'Burlington routes via the East Coast DC.';
    const quote = 'Burlington routes via the East Coast DC.';
    const res = validateQuote({
      sourceText: source,
      exactQuoteProvided: quote,
      charStartProvided: 0,
      charEndProvided: quote.length - 5, // wrong end
    });
    assert(
      res.verdict === 'failed' && res.failedCheckName === 'quote_offsets_match',
      'Extra: wrong offsets fail with quote_offsets_match',
    );
  }

  // ── Empty quote fails fast ──────────────────────────────────────────
  {
    const res = validateQuote({ sourceText: 'anything', exactQuoteProvided: '' });
    assert(res.verdict === 'failed', 'Extra: empty quote fails');
  }

  // ── Macro outline guidance is not valid document evidence ───────────
  {
    const sourceChunk =
      'Chunk says: after licensor approval, Design sends the approved art package to Sourcing.';
    const outlineOnlyQuote =
      'The workflow has a cross-functional approval gate before the China factory lane.';
    const res = validateQuote({
      sourceText: sourceChunk,
      exactQuoteProvided: outlineOnlyQuote,
      normalizationPolicy: MARKDOWN_DOCUMENT_NORMALIZATION_POLICY,
    });
    assert(
      res.verdict === 'failed',
      'Extra: source-outline-only prose cannot validate against document chunks',
    );
  }

  // ── Normalized match works when the policy is enabled ───────────────
  // OCR doubled a space; with whitespace normalization the quote matches.
  {
    const source = 'Tooling cost  must be approved by sourcing before sample.';
    const quote = 'Tooling cost must be approved by sourcing before sample.';
    const strict = validateQuote({ sourceText: source, exactQuoteProvided: quote });
    assert(strict.verdict === 'failed', 'Extra: double-space fails strict verbatim');
    const lenient = validateQuote({
      sourceText: source,
      exactQuoteProvided: quote,
      normalizationPolicy: { allowWhitespaceCollapse: true },
    });
    assert(
      lenient.verdict === 'normalized_match',
      'Extra: double-space matches under allowWhitespaceCollapse',
    );
    assert(
      lenient.validationMethod === 'normalized_whitespace',
      'Extra: normalized method is reported precisely',
    );
  }

  // ── Markdown formatting can normalize for uploaded Markdown docs ────
  {
    const source = '| **Project Manager** | Jessica Cortázar | The whole POP pipeline. |';
    const quote = 'Project Manager Jessica Cortázar The whole POP pipeline.';
    const strict = validateQuote({ sourceText: source, exactQuoteProvided: quote });
    assert(strict.verdict === 'failed', 'Extra: Markdown table quote fails strict verbatim');
    const lenient = validateQuote({
      sourceText: source,
      exactQuoteProvided: quote,
      normalizationPolicy: {
        allowMarkdownFormatting: true,
        allowWhitespaceCollapse: true,
        allowLeadingTrailingTrim: true,
      },
    });
    assert(
      lenient.verdict === 'normalized_match',
      'Extra: Markdown formatting matches under allowMarkdownFormatting',
    );
  }

  // ── Markdown/plain-text line wraps normalize to visible prose ───────
  {
    const source =
      'Licensed Team assists Design Team in Downloading Style Guides from the\nLicensor’s Website to the Style Guide Server';
    const quote =
      "Licensed Team assists Design Team in Downloading Style Guides from the Licensor's Website to the Style Guide Server";
    const strict = validateQuote({ sourceText: source, exactQuoteProvided: quote });
    assert(strict.verdict === 'failed', 'Extra: wrapped smart-quote text fails strict verbatim');
    const lenient = validateQuote({
      sourceText: source,
      exactQuoteProvided: quote,
      normalizationPolicy: MARKDOWN_DOCUMENT_NORMALIZATION_POLICY,
    });
    assert(
      lenient.verdict === 'normalized_match',
      'Extra: markdown/plain-text policy matches line-wrapped smart-quote prose',
    );
  }

  // ── Source-pointer validation ───────────────────────────────────────
  {
    const ok = validateSourcePointer({ sourceType: 'message', sourceMessageId: 'msg-1' });
    assert(ok.ok, 'Extra: source_type=message with message id → ok');

    const missing = validateSourcePointer({ sourceType: 'message' });
    assert(
      !missing.ok && missing.failedCheckName === 'source_type_valid',
      'Extra: source_type=message without message id → fails source_type_valid',
    );

    const docChunkOk = validateSourcePointer({
      sourceType: 'document_chunk',
      sourceDocumentChunkId: 'chunk-1',
    });
    assert(docChunkOk.ok, 'Extra: document_chunk with chunk id → ok');

    const externalNeeds = validateSourcePointer({ sourceType: 'external_system' });
    assert(!externalNeeds.ok, 'Extra: external_system without external record id → fails');

    const adminOk = validateSourcePointer({
      sourceType: 'manual_admin',
      createdByEmployeeId: 'emp-1',
    });
    assert(adminOk.ok, 'Extra: manual_admin with creator → ok');
  }

  // ── Candidate hash is deterministic across order changes ────────────
  {
    const h1 = computeCandidateHash({
      summary: 'Burlington seasonal needs new routing.',
      topDomainIds: ['customer_ops', 'logistics_shipping'],
      validatedQuotes: ['quote A', 'quote B'],
      sourcePointers: ['message:msg-1', 'message:msg-2'],
    });
    const h2 = computeCandidateHash({
      summary: '  Burlington Seasonal needs new routing.  ', // case + whitespace differ
      topDomainIds: ['logistics_shipping', 'customer_ops'], // reordered
      validatedQuotes: ['quote B', 'quote A'], // reordered
      sourcePointers: ['message:msg-2', 'message:msg-1'], // reordered
    });
    assert(h1 === h2, 'Extra: candidate hash is stable across case/whitespace/order differences');

    const h3 = computeCandidateHash({
      summary: 'A different claim entirely.',
      topDomainIds: ['customer_ops'],
      validatedQuotes: ['something else'],
      sourcePointers: ['message:msg-3'],
    });
    assert(h3 !== h1, 'Extra: distinct candidate inputs produce distinct hashes');
    assert(/^[0-9a-f]{64}$/.test(h1), 'Extra: hash is 64-char sha256 hex');
  }

  // ── canonicalizeSummary basics ──────────────────────────────────────
  {
    assert(
      canonicalizeSummary('  Hello   WORLD  ') === 'hello world',
      'Extra: canonicalizeSummary lowercases + collapses whitespace + trims',
    );
  }

  // ── decidePromotion rejects non-validated candidates ────────────────
  {
    const res = decidePromotion({
      candidateHash: 'h',
      candidate: {
        id: 'cand-x',
        status: 'pending_validation',
        summary: 'x',
        claimType: 'process_rule',
        impactScore: 3,
        domains: ['customer_ops'],
      },
      validatedEvidence: [],
      existingClaimWithSameHash: null,
    });
    assert(
      res.kind === 'reject' && res.reason === 'not_validated',
      'Extra: pending_validation candidate → reject(not_validated)',
    );
  }

  // ── decidePromotion rejects validated candidates with no evidence ───
  {
    const res = decidePromotion({
      candidateHash: 'h',
      candidate: {
        id: 'cand-x',
        status: 'validated',
        summary: 'x',
        claimType: 'process_rule',
        impactScore: 3,
        domains: ['customer_ops'],
      },
      validatedEvidence: [],
      existingClaimWithSameHash: null,
    });
    assert(
      res.kind === 'reject' && res.reason === 'no_validated_evidence',
      'Extra: validated candidate with no evidence → reject(no_validated_evidence)',
    );
  }

  // ════════════════════════════════════════════════════════════════════
  // Section M — In-lock snapshot loader mappers (R7+ executor refactor)
  //
  // These pure mappers convert raw DB row shapes into the CandidateSnapshot
  // fields decidePromotion consumes. The executor's loadCandidateSnapshotInLock
  // helper is a thin SELECT + map composition; the per-row mapping is here.
  // ════════════════════════════════════════════════════════════════════

  // M1: undefined candidate row → null
  {
    const res = mapCandidateRowToSnapshotCandidate(undefined);
    assert(res === null, 'M1 undefined candidate row → null');
    const resNull = mapCandidateRowToSnapshotCandidate(null);
    assert(resNull === null, 'M1 null candidate row → null');
  }

  // M2: happy-path candidate row → matching snapshot.candidate
  {
    const row: ExtractionCandidateRow = {
      id: 'cand-1',
      status: 'validated',
      summary: 'Burlington seasonal needs new routing.',
      claim_type: 'process_rule',
      impact_score: 7,
      confidence_score: 8,
      domains: ['customer_ops', 'logistics_shipping'],
      promoted_to_claim_id: null,
    };
    const mapped = mapCandidateRowToSnapshotCandidate(row);
    assert(mapped !== null, 'M2 mapped is non-null');
    assert(mapped!.id === 'cand-1', 'M2 id passes through');
    assert(mapped!.claimType === 'process_rule', 'M2 claim_type → claimType');
    assert(mapped!.impactScore === 7, 'M2 impact_score → impactScore');
    assert(mapped!.confidenceScore === 8, 'M2 confidence_score → confidenceScore');
    assert(
      Array.isArray(mapped!.domains) && mapped!.domains.length === 2,
      'M2 domains array passes through',
    );
    assert(mapped!.promotedToClaimId === null, 'M2 null promoted_to_claim_id stays null');
  }

  // M3: confidence_score: null → confidenceScore: undefined (NOT 0 or NaN)
  {
    const row: ExtractionCandidateRow = {
      id: 'cand-2',
      status: 'pending_validation',
      summary: 's',
      claim_type: 'process_rule',
      impact_score: 3,
      confidence_score: null,
      domains: ['it_systems'],
      promoted_to_claim_id: null,
    };
    const mapped = mapCandidateRowToSnapshotCandidate(row);
    assert(
      mapped!.confidenceScore === undefined,
      'M3 null confidence_score → undefined (not 0 or NaN)',
    );
  }

  // M4: domains: null (jsonb null) → []
  {
    const row = {
      id: 'cand-3',
      status: 'validated',
      summary: 's',
      claim_type: 'process_rule',
      impact_score: 5,
      confidence_score: 5,
      domains: null,
      promoted_to_claim_id: null,
    } as unknown as ExtractionCandidateRow;
    const mapped = mapCandidateRowToSnapshotCandidate(row);
    assert(
      Array.isArray(mapped!.domains) && mapped!.domains.length === 0,
      'M4 jsonb-null domains → []',
    );
  }

  // M5: domains: non-array jsonb (defensive) → []
  {
    const row = {
      id: 'cand-4',
      status: 'validated',
      summary: 's',
      claim_type: 'process_rule',
      impact_score: 5,
      confidence_score: 5,
      domains: { not: 'an array' },
      promoted_to_claim_id: null,
    } as unknown as ExtractionCandidateRow;
    const mapped = mapCandidateRowToSnapshotCandidate(row);
    assert(
      Array.isArray(mapped!.domains) && mapped!.domains.length === 0,
      'M5 non-array jsonb domains → [] (defensive)',
    );
  }

  // M6: evidence row with validation_status='exact_match' + populated
  //     validated_* → included with all fields mapped
  {
    const row: ExtractionCandidateEvidenceRow = {
      id: 'ev-1',
      source_type: 'message',
      source_message_id: 'msg-1',
      source_document_chunk_id: null,
      source_external_record_id: null,
      asserted_by_employee_id: 'emp-1',
      uploaded_by_employee_id: null,
      created_by_employee_id: null,
      validation_status: 'exact_match',
      validated_exact_quote: 'Burlington seasonal items need new routing.',
      validated_char_start: 12,
      validated_char_end: 56,
      page_number: null,
      confidence: 9,
    };
    const mapped = mapEvidenceRowToValidatedEvidence(row);
    assert(mapped !== null, 'M6 exact_match with validated fields → included');
    assert(mapped!.id === 'ev-1', 'M6 id passes through');
    assert(mapped!.sourceType === 'message', 'M6 source_type → sourceType');
    assert(
      mapped!.validatedCharStart === 12 && mapped!.validatedCharEnd === 56,
      'M6 char offsets pass through',
    );
    assert(
      mapped!.assertedByEmployeeId === 'emp-1',
      'M6 asserted_by_employee_id → assertedByEmployeeId',
    );
  }

  // M7: evidence row with validation_status='failed' → excluded (null)
  {
    const row: ExtractionCandidateEvidenceRow = {
      id: 'ev-2',
      source_type: 'message',
      source_message_id: 'msg-2',
      source_document_chunk_id: null,
      source_external_record_id: null,
      asserted_by_employee_id: null,
      uploaded_by_employee_id: null,
      created_by_employee_id: null,
      validation_status: 'failed',
      validated_exact_quote: null,
      validated_char_start: null,
      validated_char_end: null,
      page_number: null,
      confidence: null,
    };
    const mapped = mapEvidenceRowToValidatedEvidence(row);
    assert(mapped === null, 'M7 validation_status=failed → null (excluded from validated set)');
  }

  // M8: evidence with validation_status='exact_match' BUT validated_exact_quote
  //     null → defensive null (shouldn't happen because of the
  //     extraction_candidate_evidence_validated_fields_check constraint, but
  //     the mapper refuses to fabricate values regardless).
  {
    const row: ExtractionCandidateEvidenceRow = {
      id: 'ev-3',
      source_type: 'message',
      source_message_id: 'msg-3',
      source_document_chunk_id: null,
      source_external_record_id: null,
      asserted_by_employee_id: null,
      uploaded_by_employee_id: null,
      created_by_employee_id: null,
      validation_status: 'exact_match',
      validated_exact_quote: null, // inconsistent with status
      validated_char_start: 0,
      validated_char_end: 10,
      page_number: null,
      confidence: null,
    };
    const mapped = mapEvidenceRowToValidatedEvidence(row);
    assert(
      mapped === null,
      'M8 exact_match with NULL validated_exact_quote → null (defensive, refuses to fabricate)',
    );
  }

  // M9: evidence with validation_status='normalized_match' → included
  {
    const row: ExtractionCandidateEvidenceRow = {
      id: 'ev-4',
      source_type: 'document_chunk',
      source_message_id: null,
      source_document_chunk_id: 'chunk-1',
      source_external_record_id: null,
      asserted_by_employee_id: null,
      uploaded_by_employee_id: 'emp-2',
      created_by_employee_id: null,
      validation_status: 'normalized_match',
      validated_exact_quote: 'Disney approvals must precede tooling.',
      validated_char_start: 0,
      validated_char_end: 38,
      page_number: 3,
      confidence: 7,
    };
    const mapped = mapEvidenceRowToValidatedEvidence(row);
    assert(mapped !== null, 'M9 normalized_match passes the filter');
    assert(mapped!.sourceType === 'document_chunk', 'M9 document_chunk source type');
    assert(
      mapped!.sourceDocumentChunkId === 'chunk-1' && mapped!.uploadedByEmployeeId === 'emp-2',
      'M9 doc-chunk + uploader fields map through',
    );
  }

  // M10: all optional fields pass through correctly
  {
    const row: ExtractionCandidateEvidenceRow = {
      id: 'ev-5',
      source_type: 'message',
      source_message_id: 'msg-5',
      source_document_chunk_id: null,
      source_external_record_id: null,
      asserted_by_employee_id: 'emp-A',
      uploaded_by_employee_id: 'emp-B',
      created_by_employee_id: 'emp-C',
      validation_status: 'exact_match',
      validated_exact_quote: 'x',
      validated_char_start: 0,
      validated_char_end: 1,
      page_number: 42,
      confidence: 10,
    };
    const mapped = mapEvidenceRowToValidatedEvidence(row);
    assert(
      mapped!.pageNumber === 42 &&
        mapped!.confidence === 10 &&
        mapped!.assertedByEmployeeId === 'emp-A' &&
        mapped!.uploadedByEmployeeId === 'emp-B' &&
        mapped!.createdByEmployeeId === 'emp-C',
      'M10 optional fields (pageNumber, confidence, all 3 employee FKs) pass through',
    );
  }

  console.log('\nR5 smoke gate: PASS');
}

main();
