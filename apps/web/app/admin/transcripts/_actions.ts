'use server';

import { sql } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { triggerTask } from '@/lib/trigger';

// Meeting picker actions.
//
// The Oracle does NOT auto-ingest meetings. `meeting_transcripts` holds the
// discovered meetings (status 'available'); an admin chooses which to ingest.
// Ingesting triggers teams-transcript-ingestion (which pulls the VTT, writes
// messages as 'pending' for normal extraction, and flips the row to 'ingested').

function refresh() {
  revalidatePath('/admin/transcripts');
}

/** Pull the discovery scan (past meetings) on demand. */
export async function runDiscoveryScan(formData: FormData) {
  await requireAdmin();
  const sinceDays = Number.parseInt(String(formData.get('sinceDays') ?? '14'), 10);
  const dispatched = await triggerTask('teams-transcript-discovery-scan', {
    sinceDays: Number.isFinite(sinceDays) ? sinceDays : 14,
  });
  refresh();
  // On-demand task with NO sweep — if dispatch fails the scan never runs and the
  // admin would just see nothing change. Surface it.
  if (!dispatched) {
    throw new Error(
      'Discovery scan was not dispatched (no cron sweep will retry). Check TRIGGER_SECRET_KEY, then re-run.',
    );
  }
}

/** Generate/refresh cheap preview summaries without ingesting into the Brain. */
export async function generateTranscriptSummary(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get('meetingId') ?? '').trim();
  if (!id) return;
  const dispatched = await triggerTask('teams-transcript-summary', {
    meetingTranscriptId: id,
  });
  refresh();
  if (!dispatched) {
    throw new Error(
      'Transcript summary was not dispatched (no cron sweep will retry). Check TRIGGER_SECRET_KEY, then re-run.',
    );
  }
}

/** Generate/refresh summaries for currently available meetings, capped in worker. */
export async function generateAvailableTranscriptSummaries(_formData: FormData) {
  await requireAdmin();
  const dispatched = await triggerTask('teams-transcript-summary', {
    allAvailable: true,
    limit: 25,
  });
  refresh();
  if (!dispatched) {
    throw new Error(
      'Transcript summary batch was not dispatched (no cron sweep will retry). Check TRIGGER_SECRET_KEY, then re-run.',
    );
  }
}

/** Ingest the selected available meetings — the explicit "pull this in" action. */
export async function ingestMeetings(formData: FormData) {
  await requireAdmin();
  const ids = [
    ...new Set(formData.getAll('meetingId').map((v) => String(v).trim()).filter(Boolean)),
  ];
  if (ids.length === 0) return;

  const db = getDirectDb();
  const result = await db.execute(sql`
    SELECT transcript_id, transcript_content_url, meeting_id, call_id, meeting_time
    FROM meeting_transcripts
    WHERE status = 'available'
      AND id IN (
        SELECT value::uuid FROM jsonb_array_elements_text(${JSON.stringify(ids)}::jsonb)
      )
  `);
  const rows = [...result] as unknown as Array<{
    transcript_id: string;
    transcript_content_url: string | null;
    meeting_id: string | null;
    call_id: string | null;
    meeting_time: string | null;
  }>;

  let failed = 0;
  for (const row of rows) {
    const dispatched = await triggerTask('teams-transcript-ingestion', {
      resourcePath: null,
      transcriptContentUrl: row.transcript_content_url,
      meetingId: row.meeting_id,
      callId: row.call_id,
      meetingTime: row.meeting_time,
      discoveryTranscriptId: row.transcript_id,
    });
    if (!dispatched) failed += 1;
  }
  refresh();
  // teams-transcript-ingestion has NO sweep — a failed dispatch means that
  // meeting is never ingested. Surface it rather than silently leaving it
  // 'available' as if nothing happened.
  if (failed > 0) {
    throw new Error(
      `${failed}/${rows.length} meeting ingestion dispatch(es) failed — those meetings were NOT ingested ` +
        `and no sweep will retry them. Check TRIGGER_SECRET_KEY, then re-select and re-run.`,
    );
  }
}

/** Hide a meeting you don't want to ingest. */
export async function dismissMeeting(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get('meetingId') ?? '').trim();
  if (!id) return;
  const db = getDirectDb();
  await db.execute(sql`
    UPDATE meeting_transcripts SET status = 'dismissed'
    WHERE id = ${id}::uuid AND status = 'available'
  `);
  refresh();
}
