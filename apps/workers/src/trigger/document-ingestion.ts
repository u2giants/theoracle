// PHASE 4 STUB — document ingestion worker (spec 9.6).
//
// Triggered by an INSERT on `documents` (Phase 4 will wire this either via
// Supabase webhook -> trigger.dev event or a periodic poll).
//
// Workflow:
//   1. Download bytes from Supabase Storage (bucket = documents.storage_bucket,
//      path = documents.storage_path).
//   2. Parse — PDF / XLSX / DOCX / CSV depending on documents.file_type.
//      Use a parser library (pdf-parse, xlsx, mammoth, etc.) — server-side.
//   3. Chunk preserving page_number, sheet_name, row_start/row_end, bbox.
//   4. contentHash each chunk for dedup.
//   5. Embed chunks via @oracle/ai embedText().
//   6. INSERT document_chunks rows.
//   7. Call extraction model on chunks to produce claims; link via claim_evidence
//      with source_type='document_chunk' and source_document_chunk_id=<id>.
//   8. Update documents.status to 'complete' or 'failed'.

import { task } from '@trigger.dev/sdk/v3';
import { z } from 'zod';

const PayloadSchema = z.object({ documentId: z.string().uuid() });

export const documentIngestionTask = task({
  id: 'document-ingestion',
  maxDuration: 60 * 10,
  run: async (payload: z.infer<typeof PayloadSchema>, { ctx }) => {
    PayloadSchema.parse(payload);
    return {
      ok: true,
      note: 'phase-4 stub — see comment block at top of file',
      documentId: payload.documentId,
      runId: ctx.run.id,
    };
  },
});
