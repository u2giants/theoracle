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
  employeeIdentities,
  jobRuns,
  messages,
} from '@oracle/db';
import { fetchTranscriptVtt, listDisplayNameToEmail } from '../lib/graph-transcripts';

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

      // Speaker → employee resolution.
      // Primary path: VTT display name -> M365 directory email -> employee by
      // email (employees.email or any employee_identities.email). This mirrors
      // the auth linker's email-based identity model and is robust to display
      // names that don't equal employees.name. Fallback: display-name match.
      const emps = await db
        .select({ id: employees.id, name: employees.name, email: employees.email })
        .from(employees);
      const idents = await db
        .select({ employeeId: employeeIdentities.employeeId, email: employeeIdentities.email })
        .from(employeeIdentities);
      const byName = new Map<string, string>();
      const byEmail = new Map<string, string>();
      for (const e of emps) {
        if (e.name) byName.set(e.name.trim().toLowerCase(), e.id);
        if (e.email) byEmail.set(e.email.trim().toLowerCase(), e.id);
      }
      for (const i of idents) {
        const key = i.email?.trim().toLowerCase();
        if (key && !byEmail.has(key)) byEmail.set(key, i.employeeId);
      }
      let displayNameToEmail = new Map<string, string>();
      try {
        displayNameToEmail = await listDisplayNameToEmail();
      } catch (err) {
        console.warn('[teams-transcript-ingestion] directory lookup failed; using name match only', err);
      }
      const resolveExisting = (speaker: string): string | null => {
        const key = speaker.trim().toLowerCase();
        const email = displayNameToEmail.get(key);
        if (email) {
          const viaEmail = byEmail.get(email);
          if (viaEmail) return viaEmail;
        }
        return byName.get(key) ?? null;
      };

      // Resolve each distinct speaker once. Bootstrap-create an employee for a
      // speaker who maps to an @popcre.com directory user but isn't onboarded
      // yet — mirrors the auth linker's email-based bootstrap. Scoped to
      // @popcre.com so external/guest participants stay unattributed (null).
      const resolvedBySpeaker = new Map<string, string | null>();
      const bootstrapped: string[] = [];
      const distinctSpeakers = [
        ...new Set(cues.map((c) => c.speaker).filter((s): s is string => Boolean(s))),
      ];
      for (const speaker of distinctSpeakers) {
        let empId = resolveExisting(speaker);
        if (!empId) {
          const email = displayNameToEmail.get(speaker.trim().toLowerCase());
          if (email && email.endsWith('@popcre.com')) {
            const [created] = await db
              .insert(employees)
              .values({ name: speaker.trim(), email, role: 'Employee' })
              .onConflictDoNothing({ target: employees.email })
              .returning({ id: employees.id });
            if (created) {
              empId = created.id;
              bootstrapped.push(email);
            } else {
              const [ex] = await db
                .select({ id: employees.id })
                .from(employees)
                .where(eq(employees.email, email))
                .limit(1);
              empId = ex?.id ?? null;
            }
            if (empId) byEmail.set(email, empId);
          }
        }
        resolvedBySpeaker.set(speaker, empId);
      }

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

      // Persist the raw VTT so the entire pipeline (parsing → messages →
      // extraction → synthesis) stays re-runnable from true source even after
      // Microsoft expires the transcript. The `messages` rows are already a
      // lossy transform (merged turns, resolved speakers); this is the raw.
      await db.execute(sql`
        insert into raw_transcripts (channel_id, call_id, transcript_id, vtt)
        values (${channel.id}::uuid, ${payload.callId ?? null}, ${transcriptId}, ${vtt})
        on conflict (transcript_id) do nothing
      `);

      const participantIds = new Set<string>();
      const rows = cues.map((c, i) => {
        const employeeId = c.speaker ? (resolvedBySpeaker.get(c.speaker) ?? null) : null;
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
        bootstrapped: bootstrapped.length,
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
