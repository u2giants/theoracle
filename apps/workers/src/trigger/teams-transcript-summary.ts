// Teams transcript preview summary.
//
// On-demand only. This fetches transcript VTT to make the picker useful, then
// writes size metadata plus a cheap-model summary. It does NOT create messages,
// candidates, claims, raw_transcripts rows, or Brain artifacts.

import { task } from '@trigger.dev/sdk/v3';
import { eq, sql } from 'drizzle-orm';
import { createHash } from 'node:crypto';
import { getDirectDb } from '@oracle/db/client';
import {
  jobRuns,
  meetingTranscripts,
  modelRuns,
  modelRunUsageDetails,
  oracleContextPacks,
} from '@oracle/db/schema';
import {
  OracleAIClient,
  buildStandardAdapters,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  resolveRouteCandidates,
  type RouteCandidate,
} from '@oracle/ai';
import { fetchTranscriptVtt } from '../lib/graph-transcripts';
import { cuesToPlainText, mergeBySpeaker, parseVtt } from '../lib/transcript-vtt';

const PROMPT_VERSION = 'teams-transcript-summary-1.0.0';
const MAX_TRANSCRIPT_CHARS = 30_000;

type SummaryPayload = {
  meetingTranscriptId?: string;
  allAvailable?: boolean;
  limit?: number;
};

type TranscriptRow = {
  id: string;
  transcriptId: string;
  subject: string | null;
  organizerName: string | null;
  participants: unknown;
  durationSeconds: number | null;
  meetingTime: Date | null;
  transcriptContentUrl: string | null;
  meetingId: string | null;
  callId: string | null;
};

const SYSTEM_PROMPT = `You summarize Microsoft Teams meeting transcripts for an internal admin picker.

Write a concise operational preview so an admin can decide whether the meeting is worth ingesting into the Oracle knowledge graph.

Rules:
- Use only the transcript text provided.
- Do not invent decisions, attendees, dates, or outcomes.
- Keep it short: one 2-3 sentence synopsis, then 4-8 bullet topics.
- Prefer business processes, systems, owners, rules, risks, exceptions, and follow-ups.
- If the transcript is mostly small talk or too thin, say that plainly.`;

function buildOracleClient(): OracleAIClient {
  return new OracleAIClient({ adapters: buildStandardAdapters() });
}

function hashString(s: string): string {
  return createHash('sha256').update(s).digest('hex');
}

function truncateTranscript(text: string): string {
  if (text.length <= MAX_TRANSCRIPT_CHARS) return text;
  return `${text.slice(0, MAX_TRANSCRIPT_CHARS)}\n\n[Transcript truncated for preview cost control.]`;
}

function existingParticipantCount(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function participantsFromCues(cues: ReturnType<typeof mergeBySpeaker>): Array<{ name: string }> {
  const seen = new Set<string>();
  const out: Array<{ name: string }> = [];
  for (const cue of cues) {
    const name = cue.speaker?.trim();
    if (!name) continue;
    const key = name.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ name });
  }
  return out;
}

function durationFromCues(cues: ReturnType<typeof mergeBySpeaker>): number | null {
  const maxEnd = cues.reduce((max, cue) => Math.max(max, cue.endOffsetMs, cue.offsetMs), 0);
  return maxEnd > 0 ? Math.round(maxEnd / 1000) : null;
}

async function loadRows(
  db: ReturnType<typeof getDirectDb>,
  payload: SummaryPayload,
): Promise<TranscriptRow[]> {
  if (payload.allAvailable) {
    const limit = Math.max(1, Math.min(50, payload.limit ?? 25));
    const result = await db.execute(sql`
      SELECT id, transcript_id AS "transcriptId", subject,
             organizer_name AS "organizerName", participants,
             duration_seconds AS "durationSeconds", meeting_time AS "meetingTime",
             transcript_content_url AS "transcriptContentUrl",
             meeting_id AS "meetingId", call_id AS "callId"
      FROM meeting_transcripts
      WHERE status = 'available'
      ORDER BY meeting_time DESC NULLS LAST, discovered_at DESC
      LIMIT ${limit}
    `);
    return [...result] as unknown as TranscriptRow[];
  }

  if (!payload.meetingTranscriptId) {
    throw new Error('meetingTranscriptId is required unless allAvailable=true');
  }

  const rows = await db
    .select({
      id: meetingTranscripts.id,
      transcriptId: meetingTranscripts.transcriptId,
      subject: meetingTranscripts.subject,
      organizerName: meetingTranscripts.organizerName,
      participants: meetingTranscripts.participants,
      durationSeconds: meetingTranscripts.durationSeconds,
      meetingTime: meetingTranscripts.meetingTime,
      transcriptContentUrl: meetingTranscripts.transcriptContentUrl,
      meetingId: meetingTranscripts.meetingId,
      callId: meetingTranscripts.callId,
    })
    .from(meetingTranscripts)
    .where(eq(meetingTranscripts.id, payload.meetingTranscriptId))
    .limit(1);
  return rows;
}

async function summarizeOne(args: {
  db: ReturnType<typeof getDirectDb>;
  client: OracleAIClient;
  routeCandidates: RouteCandidate[];
  row: TranscriptRow;
}): Promise<{
  meetingTranscriptId: string;
  transcriptId: string;
  messageCount: number;
  transcriptCharCount: number;
  model: string;
}> {
  if (!args.row.transcriptContentUrl) {
    throw new Error(`meeting_transcripts ${args.row.id} has no transcript_content_url`);
  }

  const vtt = await fetchTranscriptVtt(args.row.transcriptContentUrl, null);
  const cues = mergeBySpeaker(parseVtt(vtt));
  const transcriptText = cuesToPlainText(cues);
  const vttParticipants = participantsFromCues(cues);
  const vttDurationSeconds = durationFromCues(cues);
  const transcriptForModel = truncateTranscript(transcriptText);
  const primaryRoute = args.routeCandidates[0]!.route;

  const dynamicInput = `Meeting metadata:
Subject: ${args.row.subject ?? 'Unknown'}
Organizer: ${args.row.organizerName ?? 'Unknown'}
Meeting time: ${args.row.meetingTime?.toISOString() ?? 'Unknown'}
Transcript utterances: ${cues.length}
Transcript characters: ${transcriptText.length}

Transcript:
${transcriptForModel}`;

  const blocks = [
    makeBlock({
      id: 'sys',
      label: 'Teams transcript summary system',
      kind: 'stable_system',
      content: SYSTEM_PROMPT,
      cacheEligible: true,
      reasonIncluded: 'cheap preview summary for admin transcript picker',
    }),
    makeBlock({
      id: 'transcript',
      label: 'Teams transcript text',
      kind: 'dynamic_input',
      content: dynamicInput,
      cacheEligible: false,
      reasonIncluded: 'meeting transcript selected for preview summary',
    }),
  ];

  const [contextPack] = await args.db
    .insert(oracleContextPacks)
    .values({
      taskType: 'transcript_summary',
      routeId: primaryRoute.routeId,
      promptVersion: PROMPT_VERSION,
      stablePrefixHash: hashString(SYSTEM_PROMPT),
      dynamicInputHash: hashString(dynamicInput),
      blocksJson: blocks.map((b) => ({
        id: b.id,
        kind: b.kind,
        hash: b.hash,
        tokenEstimate: b.tokenEstimate,
      })),
      selectedSourceTypes: ['teams_transcript'],
    })
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error('failed to insert oracle_context_packs row');

  const started = Date.now();
  try {
    const result = await args.client.runText({
      taskType: 'transcript_summary',
      routeId: primaryRoute.routeId,
      promptVersion: PROMPT_VERSION,
      blocks,
      routeCandidates: args.routeCandidates,
      providerOptions: { temperature: 0.2 },
    });
    const latencyMs = Date.now() - started;
    const actualRouteId = result.routeId ?? primaryRoute.routeId;
    const actualProvider = result.provider ?? primaryRoute.provider;
    const actualModelId = result.modelId ?? primaryRoute.modelId;

    const [modelRun] = await args.db
      .insert(modelRuns)
      .values({
        taskType: 'transcript-summary',
        model: actualModelId,
        provider: actualProvider,
        promptVersion: PROMPT_VERSION,
        inputHash: hashString(dynamicInput),
        inputTokens: result.usage.inputTokens ?? null,
        outputTokens: result.usage.outputTokens ?? null,
        latencyMs,
        success: true,
      })
      .returning({ id: modelRuns.id });
    if (!modelRun) throw new Error('failed to insert model_runs row');

    await args.db.insert(modelRunUsageDetails).values({
      modelRunId: modelRun.id,
      contextPackId: contextPack.id,
      routeId: actualRouteId,
      inputTokens: result.usage.inputTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      cachedInputTokens: result.usage.cachedInputTokens ?? null,
      cacheWriteTokens: result.usage.cacheWriteTokens ?? null,
      reasoningTokens: result.usage.reasoningTokens ?? null,
      providerRequestId: result.usage.providerRequestId ?? null,
      rawUsageJson: (result.usage.rawUsageJson ?? null) as Record<string, unknown> | null,
    });
    await logModelRunAttempts({
      db: args.db,
      metadata: result,
      taskType: 'transcript-summary',
      slot: 'general',
      contextPackId: contextPack.id,
      modelRunId: modelRun.id,
    });
    await args.db
      .update(oracleContextPacks)
      .set({ modelRunId: modelRun.id })
      .where(eq(oracleContextPacks.id, contextPack.id));

    await args.db
      .update(meetingTranscripts)
      .set({
        participants:
          existingParticipantCount(args.row.participants) > 0
            ? args.row.participants
            : vttParticipants,
        durationSeconds: args.row.durationSeconds ?? vttDurationSeconds,
        messageCount: cues.length,
        transcriptCharCount: transcriptText.length,
        aiSummary: result.text.trim(),
        aiSummaryModel: `${actualProvider}/${actualModelId}`,
        aiSummaryGeneratedAt: new Date(),
      })
      .where(eq(meetingTranscripts.id, args.row.id));

    return {
      meetingTranscriptId: args.row.id,
      transcriptId: args.row.transcriptId,
      messageCount: cues.length,
      transcriptCharCount: transcriptText.length,
      model: `${actualProvider}/${actualModelId}`,
    };
  } catch (err) {
    const latencyMs = Date.now() - started;
    const message = err instanceof Error ? err.message : String(err);
    await logAllCandidatesFailedAttempts({
      db: args.db,
      error: err,
      taskType: 'transcript-summary',
      slot: 'general',
      contextPackId: contextPack.id,
    });
    await args.db.insert(modelRuns).values({
      taskType: 'transcript-summary',
      model: primaryRoute.modelId,
      provider: primaryRoute.provider,
      promptVersion: PROMPT_VERSION,
      inputHash: hashString(dynamicInput),
      latencyMs,
      success: false,
      error: message,
    });
    throw err;
  }
}

export const teamsTranscriptSummaryTask = task({
  id: 'teams-transcript-summary',
  maxDuration: 60 * 5,
  retry: { maxAttempts: 1 },
  run: async (payload: SummaryPayload, { ctx }) => {
    const db = getDirectDb();
    const [jobRun] = await db
      .insert(jobRuns)
      .values({
        triggerRunId: ctx.run.id,
        jobType: 'teams-transcript-summary',
        status: 'running',
        startedAt: new Date(),
        inputJson: payload,
      })
      .returning({ id: jobRuns.id });
    if (!jobRun) throw new Error('[teams-transcript-summary] failed to insert job_runs row');

    try {
      const rows = await loadRows(db, payload);
      if (rows.length === 0) {
        const out = { ok: true, processed: 0, reason: 'no matching transcript rows' };
        await db
          .update(jobRuns)
          .set({ status: 'complete', finishedAt: new Date(), outputJson: out })
          .where(eq(jobRuns.id, jobRun.id));
        return out;
      }

      const resolved = await resolveRouteCandidates(db, 'general');
      for (const skipped of resolved.skipped) {
        console.warn('[teams-transcript-summary] skipped general route candidate', skipped);
      }
      const client = buildOracleClient();
      const processed = [];
      for (const row of rows) {
        processed.push(
          await summarizeOne({
            db,
            client,
            routeCandidates: resolved.candidates,
            row,
          }),
        );
      }

      const out = { ok: true, processed: processed.length, rows: processed };
      await db
        .update(jobRuns)
        .set({ status: 'complete', finishedAt: new Date(), outputJson: out })
        .where(eq(jobRuns.id, jobRun.id));
      return out;
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
