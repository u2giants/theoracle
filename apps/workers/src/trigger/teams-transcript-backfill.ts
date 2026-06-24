// Teams transcript backfill — recover already-completed scheduled-meeting
// transcripts.
//
// Change-notification subscriptions only "listen going forward", so a meeting
// that was transcribed before its subscription existed is never pushed to the
// webhook. This on-demand task pulls scheduled online-meeting transcripts that
// already exist (within Teams' retention window) and feeds each through the
// SAME path the webhook uses — triggering `teams-transcript-ingestion` per
// transcript. That worker dedupes on transcriptId, so this is safe to re-run
// and won't double-ingest anything the live subscription already captured.
//
// On-demand only (NOT a schedule): Trigger.dev is at its 10/10 schedule limit
// (AGENTS.md §10). Trigger it manually, e.g. via the Trigger MCP:
//   trigger_task teams-transcript-backfill { "sinceDays": 7 }

import { task, tasks } from '@trigger.dev/sdk/v3';
import {
  listUserIds,
  getOnlineMeetingTranscripts,
  type BackfillTranscript,
} from '../lib/graph-transcripts';

interface BackfillPayload {
  /** How far back to pull, in days. Defaults to 7. */
  sinceDays?: number;
}

export const teamsTranscriptBackfillTask = task({
  id: 'teams-transcript-backfill',
  maxDuration: 60 * 8,
  run: async (payload: BackfillPayload) => {
    const sinceDays = Math.max(1, Math.min(60, payload?.sinceDays ?? 7));
    const sinceIso = new Date(Date.now() - sinceDays * 24 * 60 * 60 * 1000).toISOString();

    const organizers = await listUserIds();
    console.log(
      `[teams-transcript-backfill] scanning ${organizers.length} organizers since ${sinceIso}`,
    );

    // Collect across organizers, de-duped by transcript content URL (the same
    // meeting can surface under multiple organizers / pages).
    const byUrl = new Map<string, BackfillTranscript>();
    let organizerErrors = 0;
    for (const organizerId of organizers) {
      try {
        const transcripts = await getOnlineMeetingTranscripts(organizerId, sinceIso);
        for (const t of transcripts) {
          const key = t.transcriptContentUrl ?? `${t.meetingId ?? ''}:${t.createdDateTime ?? ''}`;
          if (key && !byUrl.has(key)) byUrl.set(key, t);
        }
      } catch (err) {
        organizerErrors += 1;
        console.warn(`[teams-transcript-backfill] organizer ${organizerId} failed`, err);
      }
    }

    const found = [...byUrl.values()];
    console.log(`[teams-transcript-backfill] found ${found.length} distinct transcripts; dispatching ingestion`);

    // Hand each off to the gated ingestion worker (lands 'awaiting_approval').
    // Idempotent downstream — re-runs are no-ops for already-ingested transcripts.
    for (const t of found) {
      await tasks.trigger('teams-transcript-ingestion', {
        resourcePath: t.resourcePath,
        transcriptContentUrl: t.transcriptContentUrl,
        meetingId: t.meetingId,
        callId: t.callId,
      });
    }

    return {
      sinceDays,
      sinceIso,
      organizersScanned: organizers.length,
      organizerErrors,
      transcriptsDispatched: found.length,
    };
  },
});
