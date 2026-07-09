// Teams transcript DISCOVERY scan — surface already-completed meetings as
// pickable items (metadata only; no content pulled, no ingestion).
//
// The webhook discovers NEW meetings in real time, but only "going forward".
// This on-demand scan enumerates organizers and lists their existing transcripts
// (within Teams' retention window) — BOTH scheduled onlineMeetings AND ad-hoc
// ("Meet Now" / group-chat) calls, which come from two distinct Graph functions.
// It upserts one `meeting_transcripts` row per transcript so they appear in the
// picker at /admin/transcripts. An admin then chooses which to ingest. Ad-hoc
// calls carry no subject/scheduled-metadata, so we synthesize a title and gate
// them by a minimum transcription duration to keep short/accidental calls out.
// Idempotent: re-runs upsert on transcript_id and never change an already-
// 'ingested'/'dismissed' row.
//
// On-demand only (NOT a schedule): Trigger.dev is at its 10/10 schedule limit
// (AGENTS.md §10). Trigger via the picker's "Scan for recent meetings" button or
// the Trigger MCP: trigger_task teams-transcript-discovery-scan { "sinceDays": 14 }

import { task } from '@trigger.dev/sdk/v3';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import {
  getAdhocCallTranscripts,
  getOnlineMeetingMetadata,
  getOnlineMeetingTranscripts,
  listUsers,
} from '../lib/graph-transcripts';

interface ScanPayload {
  /** How far back to scan, in days. Defaults to 14. */
  sinceDays?: number;
}

/** Ad-hoc calls whose transcription is shorter than this are treated as noise. */
const MIN_ADHOC_DURATION_SECONDS = 10 * 60;

/** Full Graph transcript id from the content URL (matches the webhook deriver). */
function deriveTranscriptId(contentUrl: string | null): string | null {
  const m = (contentUrl ?? '').match(/transcripts[('/]+([^')/]+)/i);
  return m && m[1] ? m[1] : null;
}

/** Transcription span in seconds, or null when timestamps are missing/invalid. */
function transcriptDurationSeconds(start: string | null, end: string | null): number | null {
  const s = start ? Date.parse(start) : NaN;
  const e = end ? Date.parse(end) : NaN;
  if (!Number.isFinite(s) || !Number.isFinite(e) || e < s) return null;
  return Math.round((e - s) / 1000);
}

export const teamsTranscriptDiscoveryScanTask = task({
  id: 'teams-transcript-discovery-scan',
  maxDuration: 60 * 12,
  run: async (payload: ScanPayload) => {
    const sinceDays = Math.max(1, Math.min(60, payload?.sinceDays ?? 14));
    const sinceIso = new Date(Date.now() - sinceDays * 24 * 60 * 60 * 1000).toISOString();
    const db = getDirectDb();

    const organizers = await listUsers();
    console.log(`[teams-transcript-discovery-scan] scanning ${organizers.length} organizers since ${sinceIso}`);

    let discovered = 0;
    let organizerErrors = 0;
    let metadataErrors = 0;
    let adhocDiscovered = 0;
    let adhocSkippedShort = 0;
    let adhocErrors = 0;

    // Graph's getAllTranscripts calls run ~seconds each; scanning 50 organizers
    // strictly sequentially times the task out. Fan out with bounded concurrency
    // (counters mutate safely under Node's single-threaded event loop; postgres-js
    // pools the upsert connections). Concurrency is modest to stay well under
    // Graph's per-app throttle.
    const CONCURRENCY = 6;
    const scanOrganizer = async (organizer: (typeof organizers)[number]): Promise<void> => {
      const organizerName =
        organizer.name ?? organizer.mail ?? organizer.userPrincipalName ?? organizer.id;

      // 1. Scheduled onlineMeeting transcripts.
      try {
        const transcripts = await getOnlineMeetingTranscripts(organizer.id, sinceIso);
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

      // 2. Ad-hoc ("Meet Now" / group-chat) call transcripts. Enumerable only via
      // a separate Graph function; they carry no subject and no scheduled
      // metadata, so we synthesize a title and gate on transcription duration.
      // Kept in its own try/catch so an ad-hoc access gap for one organizer never
      // discards that organizer's scheduled results.
      try {
        const adhoc = await getAdhocCallTranscripts(organizer.id, sinceIso);
        for (const t of adhoc) {
          const transcriptId = deriveTranscriptId(t.transcriptContentUrl);
          if (!transcriptId) continue;
          const durationSeconds = transcriptDurationSeconds(t.createdDateTime, t.endDateTime);
          // Skip calls we KNOW are under the threshold. Unknown-duration calls
          // (null timestamps) are surfaced rather than silently dropped.
          if (durationSeconds !== null && durationSeconds < MIN_ADHOC_DURATION_SECONDS) {
            adhocSkippedShort += 1;
            continue;
          }
          const createdDate = (t.createdDateTime ?? '').slice(0, 10);
          const subject = createdDate ? `Ad-hoc call · ${createdDate}` : 'Ad-hoc call';
          await db.execute(sql`
            INSERT INTO meeting_transcripts
              (transcript_id, meeting_id, call_id, organizer_id, organizer_name,
               subject, participants, duration_seconds, transcript_content_url,
               meeting_time, status, discovered_via)
            VALUES
              (${transcriptId}, ${null}, ${t.callId}, ${t.organizerId ?? organizer.id}, ${organizerName},
               ${subject}, '[]'::jsonb,
               ${durationSeconds}, ${t.transcriptContentUrl},
               ${t.createdDateTime}, 'available', 'scan')
            ON CONFLICT (transcript_id) DO UPDATE SET
              call_id = COALESCE(EXCLUDED.call_id, meeting_transcripts.call_id),
              organizer_id = COALESCE(EXCLUDED.organizer_id, meeting_transcripts.organizer_id),
              organizer_name = COALESCE(EXCLUDED.organizer_name, meeting_transcripts.organizer_name),
              subject = COALESCE(EXCLUDED.subject, meeting_transcripts.subject),
              duration_seconds = COALESCE(EXCLUDED.duration_seconds, meeting_transcripts.duration_seconds),
              transcript_content_url = COALESCE(EXCLUDED.transcript_content_url, meeting_transcripts.transcript_content_url),
              meeting_time = COALESCE(EXCLUDED.meeting_time, meeting_transcripts.meeting_time)
          `);
          adhocDiscovered += 1;
        }
      } catch (err) {
        adhocErrors += 1;
        console.warn(
          `[teams-transcript-discovery-scan] adhoc scan for organizer ${organizer.id} failed`,
          err,
        );
      }
    };

    for (let i = 0; i < organizers.length; i += CONCURRENCY) {
      await Promise.all(organizers.slice(i, i + CONCURRENCY).map(scanOrganizer));
    }

    // Backfill organizer names for rows the webhook recorded without one.
    // Ad-hoc "Meet Now" call notifications carry the organizer id but no display
    // name, so those rows render as "Unknown" in the picker. We already hold the
    // full id→name directory map from listUsers(), so filling them in is free —
    // one narrow UPDATE per named organizer, touching only still-NULL rows.
    let namesBackfilled = 0;
    for (const organizer of organizers) {
      const name = organizer.name ?? organizer.mail ?? organizer.userPrincipalName;
      if (!name) continue;
      const res = await db.execute(sql`
        UPDATE meeting_transcripts
        SET organizer_name = ${name}
        WHERE organizer_id = ${organizer.id} AND organizer_name IS NULL
      `);
      // postgres-js reports affected rows on `.count` for non-RETURNING writes.
      namesBackfilled += Number((res as { count?: number }).count ?? 0);
    }

    console.log(
      `[teams-transcript-discovery-scan] upserted ${discovered} scheduled + ` +
        `${adhocDiscovered} ad-hoc transcripts ` +
        `(${organizerErrors} organizer errors, ${metadataErrors} metadata errors, ` +
        `${adhocErrors} ad-hoc errors, ${adhocSkippedShort} short ad-hoc calls skipped, ` +
        `${namesBackfilled} organizer names backfilled)`,
    );
    return {
      sinceDays,
      sinceIso,
      organizersScanned: organizers.length,
      organizerErrors,
      metadataErrors,
      transcriptsDiscovered: discovered,
      adhocTranscriptsDiscovered: adhocDiscovered,
      adhocShortSkipped: adhocSkippedShort,
      adhocErrors,
      namesBackfilled,
    };
  },
});
