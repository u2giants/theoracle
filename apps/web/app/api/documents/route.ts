// POST /api/documents — server-side document upload.
//
// Handles the full upload flow on the server so that:
//   * The Storage PUT uses the service-role client (bypasses storage RLS).
//   * The documents / messages / message_attachments inserts use getDirectDb()
//     (service role, bypasses table RLS).
//   * The caller's session is validated server-side via requireEmployee().
//
// Accepts multipart/form-data with fields:
//   file      — the binary file (required)
//   channelId — UUID of the target channel (required)

import { NextResponse, type NextRequest } from 'next/server';
import { and, eq } from 'drizzle-orm';
import { requireEmployee } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { createServiceRoleClient } from '@oracle/auth/server';
import {
  channels,
  channelParticipants,
  documents,
  messages,
  messageAttachments,
} from '@oracle/db/schema';
import { triggerTask } from '@/lib/trigger';

export const dynamic = 'force-dynamic';

// Allow up to 50 MB per upload (Next.js default is 4 MB).
export const maxDuration = 60; // seconds

const BUCKET = 'company_documents';

export async function POST(req: NextRequest) {
  // 1. Auth.
  let me;
  try {
    me = await requireEmployee();
  } catch {
    return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 });
  }

  // 2. Parse multipart body.
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: 'Expected multipart/form-data' }, { status: 400 });
  }

  const fileEntry = formData.get('file');
  const channelId = formData.get('channelId');
  const captionRaw = formData.get('caption');
  const caption = typeof captionRaw === 'string' ? captionRaw.trim() : '';

  if (!(fileEntry instanceof File)) {
    return NextResponse.json({ error: 'Missing file field' }, { status: 400 });
  }
  if (typeof channelId !== 'string' || !channelId.trim()) {
    return NextResponse.json({ error: 'Missing channelId field' }, { status: 400 });
  }

  const db = getDirectDb();

  // 3. Confirm channel membership.
  const membership = await db
    .select()
    .from(channelParticipants)
    .where(
      and(
        eq(channelParticipants.channelId, channelId),
        eq(channelParticipants.employeeId, me.id),
      ),
    )
    .limit(1);

  if (membership.length === 0) {
    return NextResponse.json({ error: 'Not a channel participant' }, { status: 403 });
  }

  // 4. Confirm channel is active.
  const channelRows = await db
    .select({ status: channels.status })
    .from(channels)
    .where(eq(channels.id, channelId))
    .limit(1);

  if (!channelRows[0] || channelRows[0].status !== 'active') {
    return NextResponse.json({ error: 'Channel not found or not active' }, { status: 404 });
  }

  // 5. Upload bytes to Supabase Storage via service-role client (bypasses RLS).
  const safeName = fileEntry.name.replace(/[^a-zA-Z0-9._-]/g, '_');
  const storagePath = `${me.id}/${channelId}/${Date.now()}-${safeName}`;

  const bytes = await fileEntry.arrayBuffer();
  const serviceSupabase = createServiceRoleClient();

  const { error: uploadError } = await serviceSupabase.storage
    .from(BUCKET)
    .upload(storagePath, bytes, {
      contentType: fileEntry.type || 'application/octet-stream',
      upsert: false,
    });

  if (uploadError) {
    console.error('[documents] storage upload failed', uploadError);
    return NextResponse.json(
      { error: 'Storage upload failed', detail: uploadError.message },
      { status: 502 },
    );
  }

  // 6. Insert documents row.
  let docId: string;
  try {
    const [doc] = await db
      .insert(documents)
      .values({
        uploaderId: me.id,
        fileName: fileEntry.name,
        storageBucket: BUCKET,
        storagePath,
        fileType: fileEntry.type || 'application/octet-stream',
        status: 'pending_processing',
      })
      .returning({ id: documents.id });

    if (!doc) throw new Error('Insert returned no row');
    docId = doc.id;
  } catch (err) {
    // Roll back the storage object so we don't leave orphaned files.
    await serviceSupabase.storage.from(BUCKET).remove([storagePath]);
    console.error('[documents] documents insert failed', err);
    return NextResponse.json({ error: 'DB insert failed' }, { status: 500 });
  }

  // 7. Insert an "Attached: <filename>" message + the attachment join row.
  //    This makes the upload visible in the channel timeline.
  let attachmentMessage: {
    id: string;
    channelId: string;
    employeeId: string | null;
    role: string;
    content: string;
    createdAt: Date;
  } | null = null;

  try {
    const [msg] = await db
      .insert(messages)
      .values({
        channelId,
        employeeId: me.id,
        role: 'user',
        content: caption || `Attached: ${fileEntry.name}`,
        extractionStatus: 'skipped',
      })
      .returning({
        id: messages.id,
        channelId: messages.channelId,
        employeeId: messages.employeeId,
        role: messages.role,
        content: messages.content,
        createdAt: messages.createdAt,
      });

    if (msg) {
      attachmentMessage = msg;
      await db.insert(messageAttachments).values({
        messageId: msg.id,
        documentId: docId,
      });
    }
  } catch (err) {
    // Non-fatal: the document is stored; the attachment message is cosmetic.
    console.error('[documents] message/attachment insert failed', err);
  }

  // Kick off ingestion before returning. Serverless functions may stop
  // fire-and-forget work as soon as the response is sent.
  const dispatched = await triggerTask('document-ingestion', { documentId: docId });
  if (!dispatched) {
    await db
      .update(documents)
      .set({
        processingError:
          'Immediate ingestion dispatch failed. The scheduled sweep will retry this document automatically.',
      })
      .where(eq(documents.id, docId));
  }

  return NextResponse.json(
    {
      ok: true,
      documentId: docId,
      storagePath,
      message: attachmentMessage
        ? {
            id: attachmentMessage.id,
            channelId: attachmentMessage.channelId,
            employeeId: attachmentMessage.employeeId,
            role: attachmentMessage.role,
            content: attachmentMessage.content,
            createdAt: attachmentMessage.createdAt,
            authorName: me.name,
          }
        : null,
    },
    { status: 201 },
  );
}
