'use server';

import { and, eq, inArray } from 'drizzle-orm';
import { sql } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { messages } from '@oracle/db/schema';

// Approval gate for ingested Teams meeting transcripts.
//
// The transcript-ingestion worker writes each meeting's utterances as
// extraction_status='awaiting_approval' (held) and the raw_transcripts row as
// approval_status='pending_approval'. The claim-extraction cron only ever
// selects 'pending', so a held transcript produces no claims until an admin
// acts here.
//
//   approve → raw_transcripts.approval_status='approved'; the channel's held
//             (and any previously-rejected) messages flip to 'pending' so the
//             existing extraction cron picks them up.
//   reject  → approval_status='rejected'; the channel's held/pending messages
//             flip to 'skipped' so no claims are extracted. The raw VTT is
//             always retained in raw_transcripts, and re-approving flips the
//             messages back to 'pending'.
//
// raw_transcripts is not in the Drizzle schema (the worker uses raw `sql`), so
// it is updated via raw `sql` here too.

function refreshTranscriptPages() {
  revalidatePath('/admin/transcripts');
  revalidatePath('/admin/messages');
  revalidatePath('/admin/channels');
}

export async function approveTranscript(formData: FormData) {
  const me = await requireAdmin();
  const channelId = String(formData.get('channelId') ?? '').trim();
  if (!channelId) return;

  const db = getDirectDb();
  await db.transaction(async (tx) => {
    await tx.execute(sql`
      UPDATE raw_transcripts
      SET approval_status = 'approved',
          reviewed_by_employee_id = ${me.id}::uuid,
          reviewed_at = now(),
          review_note = NULL
      WHERE channel_id = ${channelId}::uuid
    `);
    // Release held (and any previously-rejected) utterances into the extraction
    // queue. For a transcript channel these are the only ways a message reaches
    // 'awaiting_approval'/'skipped', so this never resurrects an extraction-side skip.
    await tx
      .update(messages)
      .set({ extractionStatus: 'pending' })
      .where(
        and(
          eq(messages.channelId, channelId),
          inArray(messages.extractionStatus, ['awaiting_approval', 'skipped']),
        ),
      );
  });

  refreshTranscriptPages();
}

export async function rejectTranscript(formData: FormData) {
  const me = await requireAdmin();
  const channelId = String(formData.get('channelId') ?? '').trim();
  if (!channelId) return;
  const note = String(formData.get('note') ?? '').trim() || null;

  const db = getDirectDb();
  await db.transaction(async (tx) => {
    await tx.execute(sql`
      UPDATE raw_transcripts
      SET approval_status = 'rejected',
          reviewed_by_employee_id = ${me.id}::uuid,
          reviewed_at = now(),
          review_note = ${note}
      WHERE channel_id = ${channelId}::uuid
    `);
    // Keep the messages (still viewable under Channels/Messages) but mark them
    // skipped so no claims are extracted. Covers a just-approved-not-yet-extracted
    // transcript too (pending → skipped). Already-extracted ('complete') claims
    // are not torn down here — reject before approving to avoid that.
    await tx
      .update(messages)
      .set({ extractionStatus: 'skipped' })
      .where(
        and(
          eq(messages.channelId, channelId),
          inArray(messages.extractionStatus, ['awaiting_approval', 'pending']),
        ),
      );
  });

  refreshTranscriptPages();
}
