// Teams transcript DISCOVERY scan — surface already-completed meetings as
// pickable items (metadata only; no content pulled, no ingestion).
//
// The webhook discovers NEW meetings in real time, but only "going forward".
// This on-demand scan enumerates organizers and lists their existing
// scheduled-meeting transcripts (within Teams' retention window), upserting one
// `meeting_transcripts` row per transcript so they appear in the picker at
// /admin/transcripts. An admin then chooses which to ingest. Idempotent: re-runs
// upsert on transcript_id and never change an already-'ingested'/'dismissed' row.
//
// On-demand only (NOT a schedule): Trigger.dev is at its 10/10 schedule limit
// (AGENTS.md §10). Trigger via the picker's "Scan for recent meetings" button or
// the Trigger MCP: trigger_task teams-transcript-discovery-scan { "sinceDays": 14 }

import { task } from '@trigger.dev/sdk/v3';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import {
  getOnlineMeetingMetadata,
  getOnlineMeetingTranscripts,
  listUsers,
} from '../lib/graph-transcripts';

interface ScanPayload {
  /** How far back to scan, in days. Defaults to 14. */
  sinceDays?: number;
}

/** Full Graph transcript id from the content URL (matches the webhook deriver). */
function deriveTranscriptId(contentUrl: string | null): string | null {
  const m = (contentUrl ?? '').match(/transcripts[('/]+([^')/]+)/i);
  return m && m[1] ? m[1] : null;
}

export const teamsTranscriptDiscoveryScanTask = task({
  id: 'teams-transcript-discovery-scan',
  maxDuration: 60 * 8,
  run: async (payload: ScanPayload) => {
    const sinceDays = Math.max(1, Math.min(60, payload?.sinceDays ?? 14));
    const sinceIso = new Date(Date.now() - sinceDays * 24 * 60 * 60 * 1000).toISOString();
    const db = getDirectDb();

    const organizers = await listUsers();
    console.log(`[teams-transcript-discovery-scan] scanning ${organizers.length} organizers since ${sinceIso}`);

    let discovered = 0;
    let organizerErrors = 0;
    let metadataErrors = 0;
    for (const organizer of organizers) {
      try {
        const transcripts = await getOnlineMeetingTranscripts(organizer.id, sinceIso);
        const organizerName =
          organizer.name ?? organizer.mail ?? organizer.userPrincipalName ?? organizer.id;
        for (const t of transcripts) {
          const transcriptId = deriveTranscriptId(t.transcriptContentUrl);
          if (!transcriptId) continue;
          let metadata: Awaited<ReturnType<typeof getOnlineMeetingMetadata>> = null;
          try {
            metadata = await getOnlineMeetingMetadata(organizer.id, t.meetingId);
          } catch (err) {
            metadataErrors += 1;
            console.warn(
              `[teams-transcript-discovery-scan] metadata fetch failed for transcript ${transcriptId}`,
              err,
            );
          }
          await db.execute(sql`
            INSERT INTO meeting_transcripts
              (transcript_id, meeting_id, call_id, organizer_id, organizer_name,
               subject, participants, duration_seconds, transcript_content_url,
               meeting_time, status, discovered_via)
            VALUES
              (${transcriptId}, ${t.meetingId}, ${t.callId}, ${organizer.id}, ${organizerName},
               ${metadata?.subject ?? null}, ${JSON.stringify(metadata?.participants ?? [])}::jsonb,
               ${metadata?.durationSeconds ?? null}, ${t.transcriptContentUrl},
               ${metadata?.startDateTime ?? t.createdDateTime}, 'available', 'scan')
            ON CONFLICT (transcript_id) DO UPDATE SET
              meeting_id = COALESCE(EXCLUDED.meeting_id, meeting_transcripts.meeting_id),
              call_id = COALESCE(EXCLUDED.call_id, meeting_transcripts.call_id),
              organizer_id = COALESCE(EXCLUDED.organizer_id, meeting_transcripts.organizer_id),
              organizer_name = COALESCE(EXCLUDED.organizer_name, meeting_transcripts.organizer_name),
              subject = COALESCE(EXCLUDED.subject, meeting_transcripts.subject),
              participants = CASE
                WHEN jsonb_array_length(EXCLUDED.participants) > 0 THEN EXCLUDED.participants
                ELSE meeting_transcripts.participants
              END,
              duration_seconds = COALESCE(EXCLUDED.duration_seconds, meeting_transcripts.duration_seconds),
              transcript_content_url = COALESCE(EXCLUDED.transcript_content_url, meeting_transcripts.transcript_content_url),
              meeting_time = COALESCE(EXCLUDED.meeting_time, meeting_transcripts.meeting_time)
          `);
          discovered += 1;
        }
      } catch (err) {
        organizerErrors += 1;
        console.warn(`[teams-transcript-discovery-scan] organizer ${organizer.id} failed`, err);
      }
    }

    console.log(
      `[teams-transcript-discovery-scan] upserted ${discovered} transcripts ` +
        `(${organizerErrors} organizer errors, ${metadataErrors} metadata errors)`,
    );
    return {
      sinceDays,
      sinceIso,
      organizersScanned: organizers.length,
      organizerErrors,
      metadataErrors,
      transcriptsDiscovered: discovered,
    };
  },
});
