// Increment 4 — Teams transcript ingestion.
//
// Triggered by the webhook (apps/web/app/api/teams/notifications) when Graph
// pushes a transcript notification. Fetches the WebVTT, turns each speaker turn
// into a `messages` row inside a channel that represents the call, and leaves
// them as extraction_status='pending' so the existing claim-extraction cron
// picks them up — NOTHING here writes to claims directly (candidate-before-claim).
//
// Design notes:
//   - Each utterance = one message with role='user', employeeId = the resolved
//     speaker (or null when we can't match the name). This preserves speaker
//     attribution + verbatim quotes for evidence, exactly like chat messages.
//   - Idempotent: re-running for the same transcript is a no-op (clientMessageId
//     `teams:<transcriptId>:<n>` is the dedupe key).
//
// Known v1 limitations (intentional, documented for follow-up):
//   - Speaker→employee match is by display-name (case-insensitive) against
//     employees.name. Teams VTT carries display names, not emails/AAD ids, so
//     unmatched speakers get a null employeeId. TODO: resolve via AAD id when
//     the decrypted resource exposes participant identities.
//   - Message createdAt is anchored to ingestion time + the cue offset (so all
//     cues cluster into a single extraction segment). TODO: anchor to the real
//     meeting start when available.

import { task } from '@trigger.dev/sdk/v3';
import { eq, sql } from 'drizzle-orm';
import { createHash } from 'node:crypto';
import { getDirectDb } from '@oracle/db/client';
import {
  channels,
  channelParticipants,
  employees,
  jobRuns,
  messages,
} from '@oracle/db';
import { fetchTranscriptVtt } from '../lib/graph-transcripts';

interface IngestionPayload {
  resourcePath?: string | null;
  transcriptContentUrl?: string | null;
  meetingId?: string | null;
  callId?: string | null;
  subscriptionId?: string | null;
}

interface Cue {
  speaker: string | null;
  text: string;
  offsetMs: number;
}

function vttTimeToMs(t: string): number {
  const p = t.trim().split(':').map((x) => Number.parseFloat(x) || 0);
  if (p.length === 3) {
    return Math.round(((p[0] ?? 0) * 3600 + (p[1] ?? 0) * 60 + (p[2] ?? 0)) * 1000);
  }
  if (p.length === 2) {
    return Math.round(((p[0] ?? 0) * 60 + (p[1] ?? 0)) * 1000);
  }
  return 0;
}

/** Parse Teams WebVTT into cues. Handles `<v Speaker Name>text</v>` voice tags. */
export function parseVtt(vtt: string): Cue[] {
  const cues: Cue[] = [];
  const blocks = vtt.replace(/\r/g, '').split(/\n\n+/);
  for (const block of blocks) {
    const lines = block.split('\n').filter((l) => l.trim() !== '');
    const timingIdx = lines.findIndex((l) => l.includes('-->'));
    if (timingIdx === -1) continue;
    const timingLine = lines[timingIdx];
    if (!timingLine) continue;
    const offsetMs = vttTimeToMs(timingLine.split('-->')[0] ?? '');

    let text = lines.slice(timingIdx + 1).join(' ').trim();
    let speaker: string | null = null;
    const voice = text.match(/<v\s+([^>]+)>([\s\S]*?)<\/v>/i);
    if (voice) {
      speaker = (voice[1] ?? '').trim();
      text = (voice[2] ?? '').trim();
    } else {
      text = text.replace(/<[^>]+>/g, '').trim();
    }
    if (text) cues.push({ speaker, text, offsetMs });
  }
  return cues;
}

/** Merge consecutive cues from the same speaker into one fuller utterance. */
function mergeBySpeaker(cues: Cue[]): Cue[] {
  const out: Cue[] = [];
  for (const c of cues) {
    const last = out[out.length - 1];
    if (last && last.speaker === c.speaker) {
      last.text = `${last.text} ${c.text}`.trim();
    } else {
      out.push({ ...c });
    }
  }
  return out;
}

/** Stable id for this transcript, used for idempotency + provenance. */
function deriveTranscriptId(p: IngestionPayload): string {
  const src = p.transcriptContentUrl || p.resourcePath || '';
  const m = src.match(/transcripts[('/]+([^')/]+)/i);
  if (m && m[1]) return m[1];
  return createHash('sha256')
    .update(src + (p.meetingId ?? '') + (p.callId ?? ''))
    .digest('hex')
    .slice(0, 32);
}

export const teamsTranscriptIngestionTask = task({
  id: 'teams-transcript-ingestion',
  maxDuration: 60 * 5,
  run: async (payload: IngestionPayload, { ctx }) => {
    const db = getDirectDb();
    const [jobRun] = await db
      .insert(jobRuns)
      .values({
        triggerRunId: ctx.run.id,
        jobType: 'teams-transcript-ingestion',
        status: 'running',
        startedAt: new Date(),
        inputJson: payload,
      })
      .returning({ id: jobRuns.id });
    if (!jobRun) throw new Error('[teams-transcript-ingestion] failed to insert job_runs row');

    try {
      const transcriptId = deriveTranscriptId(payload);

      // Idempotency: bail if we've already ingested this transcript.
      const already = await db
        .select({ id: messages.id })
        .from(messages)
        .where(sql`${messages.clientMessageId} like ${`teams:${transcriptId}:%`}`)
        .limit(1);
      if (already.length > 0) {
        const out = { skipped: true, reason: 'already ingested', transcriptId };
        await db
          .update(jobRuns)
          .set({ status: 'complete', finishedAt: new Date(), outputJson: out })
          .where(eq(jobRuns.id, jobRun.id));
        return { ok: true, ...out };
      }

      const vtt = await fetchTranscriptVtt(
        payload.transcriptContentUrl ?? null,
        payload.resourcePath ?? null,
      );
      const cues = mergeBySpeaker(parseVtt(vtt));

      if (cues.length === 0) {
        const out = { transcriptId, messages: 0, reason: 'empty transcript' };
        await db
          .update(jobRuns)
          .set({ status: 'complete', finishedAt: new Date(), outputJson: out })
          .where(eq(jobRuns.id, jobRun.id));
        return { ok: true, ...out };
      }

      // Speaker → employee resolution (display-name match; null when unmatched).
      const emps = await db.select({ id: employees.id, name: employees.name }).from(employees);
      const byName = new Map(emps.map((e) => [e.name.trim().toLowerCase(), e.id]));

      const base = Date.now(); // TODO: anchor to real meeting start when available
      const [channel] = await db
        .insert(channels)
        .values({
          name: `Teams call ${new Date(base).toISOString().slice(0, 16).replace('T', ' ')} UTC`,
          isGroupChat: true,
          status: 'active',
        })
        .returning({ id: channels.id });
      if (!channel) throw new Error('failed to create channel for transcript');

      const participantIds = new Set<string>();
      const rows = cues.map((c, i) => {
        const employeeId = c.speaker
          ? (byName.get(c.speaker.trim().toLowerCase()) ?? null)
          : null;
        if (employeeId) participantIds.add(employeeId);
        return {
          channelId: channel.id,
          employeeId,
          role: 'user' as const,
          content: c.text,
          clientMessageId: `teams:${transcriptId}:${i}`,
          extractionStatus: 'pending' as const,
          createdAt: new Date(base + c.offsetMs),
          metadataJson: {
            source: 'teams_transcript',
            transcriptId,
            meetingId: payload.meetingId ?? null,
            callId: payload.callId ?? null,
            speaker: c.speaker,
            offsetMs: c.offsetMs,
            resolvedEmployeeId: employeeId,
          },
        };
      });

      await db.insert(messages).values(rows);
      for (const employeeId of participantIds) {
        await db
          .insert(channelParticipants)
          .values({ channelId: channel.id, employeeId })
          .onConflictDoNothing();
      }

      const out = {
        transcriptId,
        channelId: channel.id,
        messages: rows.length,
        speakersResolved: participantIds.size,
        speakersTotal: new Set(cues.map((c) => c.speaker)).size,
      };
      await db
        .update(jobRuns)
        .set({ status: 'complete', finishedAt: new Date(), outputJson: out })
        .where(eq(jobRuns.id, jobRun.id));
      return { ok: true, ...out };
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      await db
        .update(jobRuns)
        .set({ status: 'failed', finishedAt: new Date(), error: errMsg })
        .where(eq(jobRuns.id, jobRun.id));
      throw err;
    }
  },
});
