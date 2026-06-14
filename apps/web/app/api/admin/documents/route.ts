// POST /api/admin/documents — admin company-document upload (no channel).
//
// Unlike POST /api/documents (which attaches a file to a chat channel), this
// endpoint uploads knowledge documents directly: it stores the bytes, inserts a
// `documents` row, and triggers `document-ingestion`. The ingestion worker reads
// the document by id and does not need a channel, so company/process documents
// can be uploaded from Admin → Documents without starting a chat.
//
// Accepts multipart/form-data with one or more `files` (and/or a single `file`).
// Requires admin.

import { NextResponse, type NextRequest } from 'next/server';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { createServiceRoleClient } from '@oracle/auth/server';
import { documents } from '@oracle/db/schema';
import { triggerTask } from '@/lib/trigger';

export const dynamic = 'force-dynamic';
// Allow time for several files to upload in one request.
export const maxDuration = 60;

const BUCKET = 'company_documents';

type UploadResult =
  | { fileName: string; ok: true; documentId: string }
  | { fileName: string; ok: false; error: string };

export async function POST(req: NextRequest) {
  // 1. Auth — admin only.
  let me;
  try {
    me = await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  // 2. Parse multipart body.
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: 'Expected multipart/form-data' }, { status: 400 });
  }

  const files: File[] = [
    ...formData.getAll('files').filter((f): f is File => f instanceof File),
  ];
  const single = formData.get('file');
  if (single instanceof File) files.push(single);

  if (files.length === 0) {
    return NextResponse.json({ error: 'No files provided' }, { status: 400 });
  }

  const db = getDirectDb();
  const serviceSupabase = createServiceRoleClient();
  const results: UploadResult[] = [];

  for (const file of files) {
    const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_');
    const storagePath = `admin/${me.id}/${Date.now()}-${safeName}`;

    // Upload bytes via service-role client (bypasses storage RLS).
    const bytes = await file.arrayBuffer();
    const { error: uploadError } = await serviceSupabase.storage
      .from(BUCKET)
      .upload(storagePath, bytes, {
        contentType: file.type || 'application/octet-stream',
        upsert: false,
      });
    if (uploadError) {
      results.push({ fileName: file.name, ok: false, error: uploadError.message });
      continue;
    }

    // Insert the documents row.
    let docId: string;
    try {
      const [doc] = await db
        .insert(documents)
        .values({
          uploaderId: me.id,
          fileName: file.name,
          storageBucket: BUCKET,
          storagePath,
          fileType: file.type || 'application/octet-stream',
          status: 'pending_processing',
        })
        .returning({ id: documents.id });
      if (!doc) throw new Error('Insert returned no row');
      docId = doc.id;
    } catch (err) {
      // Roll back the orphaned storage object.
      await serviceSupabase.storage.from(BUCKET).remove([storagePath]);
      console.error('[admin/documents] insert failed', err);
      results.push({ fileName: file.name, ok: false, error: 'DB insert failed' });
      continue;
    }

    // Kick off ingestion. Fails silently if Trigger.dev is unreachable — the
    // document-ingestion-sweep cron retries pending documents within 4h.
    void triggerTask('document-ingestion', { documentId: docId });
    results.push({ fileName: file.name, ok: true, documentId: docId });
  }

  const anyOk = results.some((r) => r.ok);
  return NextResponse.json({ ok: anyOk, results }, { status: anyOk ? 201 : 502 });
}
