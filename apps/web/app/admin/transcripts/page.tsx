export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatNYDateTime } from '@/lib/time';
import { approveTranscript, rejectTranscript } from './_actions';

// Meeting-transcript approval queue.
//
// When the Oracle is brought into a Teams meeting, the transcript-ingestion
// worker holds each meeting's utterances (extraction_status='awaiting_approval')
// instead of letting the extraction cron consume them. This page lets an admin
// review the transcript and approve it (release the utterances into extraction)
// or reject it (mark them skipped — kept but never extracted). See
// teams-transcript-ingestion.ts and ./_actions.ts.

type TranscriptRow = {
  channel_id: string | null;
  transcript_id: string;
  created_at: string;
  approval_status: string;
  reviewed_at: string | null;
  review_note: string | null;
  reviewer_name: string | null;
  channel_name: string | null;
  message_count: number;
  held_count: number;
  speaker_names: string[] | null;
};

type UtteranceRow = {
  channel_id: string;
  id: string;
  content: string;
  created_at: string;
  speaker: string | null;
};

const STATUS_TABS = [
  { label: 'Pending approval', value: 'pending_approval' },
  { label: 'Approved', value: 'approved' },
  { label: 'Rejected', value: 'rejected' },
  { label: 'All', value: 'all' },
] as const;

function statusBadge(status: string) {
  const map: Record<string, string> = {
    pending_approval: 'bg-yellow-100 text-yellow-800',
    approved: 'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
  };
  return map[status] ?? 'bg-gray-100 text-gray-600';
}

export default async function AdminTranscriptsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const activeStatus = status ?? 'pending_approval';

  const db = getDirectDb();

  const whereClause =
    activeStatus !== 'all'
      ? sql`WHERE rt.approval_status = ${activeStatus}`
      : sql``;

  const result = await db.execute(sql`
    SELECT
      rt.channel_id,
      rt.transcript_id,
      rt.created_at,
      rt.approval_status,
      rt.reviewed_at,
      rt.review_note,
      reviewer.name AS reviewer_name,
      ch.name AS channel_name,
      (SELECT count(*) FROM messages m WHERE m.channel_id = rt.channel_id)::int AS message_count,
      (
        SELECT count(*) FROM messages m
        WHERE m.channel_id = rt.channel_id
          AND m.extraction_status = 'awaiting_approval'
      )::int AS held_count,
      (
        SELECT jsonb_agg(DISTINCT e.name)
        FROM messages m
        JOIN employees e ON e.id = m.employee_id
        WHERE m.channel_id = rt.channel_id
      ) AS speaker_names
    FROM raw_transcripts rt
    LEFT JOIN channels ch ON ch.id = rt.channel_id
    LEFT JOIN employees reviewer ON reviewer.id = rt.reviewed_by_employee_id
    ${whereClause}
    ORDER BY rt.created_at DESC
  `);
  const rows = [...result] as unknown as TranscriptRow[];

  // Pull the utterances for the transcripts on screen in one query, then group
  // in JS for the per-transcript preview (admin volume is modest).
  const channelIds = rows
    .map((r) => r.channel_id)
    .filter((id): id is string => Boolean(id));
  const utterancesByChannel = new Map<string, UtteranceRow[]>();
  if (channelIds.length > 0) {
    const uttResult = await db.execute(sql`
      SELECT
        m.channel_id,
        m.id,
        m.content,
        m.created_at,
        COALESCE(e.name, m.metadata_json->>'speaker', 'Unknown speaker') AS speaker
      FROM messages m
      LEFT JOIN employees e ON e.id = m.employee_id
      WHERE m.channel_id IN (
        SELECT value::uuid
        FROM jsonb_array_elements_text(${JSON.stringify(channelIds)}::jsonb)
      )
      ORDER BY m.created_at ASC
    `);
    for (const u of [...uttResult] as unknown as UtteranceRow[]) {
      const list = utterancesByChannel.get(u.channel_id) ?? [];
      list.push(u);
      utterancesByChannel.set(u.channel_id, list);
    }
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Meeting transcripts</h1>
        <p className="text-sm text-muted-foreground">
          Transcripts from meetings the Oracle was brought into are held here. Approve
          a transcript to release its utterances for claim extraction, or reject it to
          keep the record but extract nothing. The live (Recall) meeting path is not
          gated.
        </p>
      </header>

      <div className="flex gap-2 text-sm">
        {STATUS_TABS.map((tab) => {
          const isActive = tab.value === activeStatus;
          return (
            <Link
              key={tab.value}
              href={`/admin/transcripts?status=${tab.value}`}
              className={`rounded px-3 py-1 ${
                isActive
                  ? 'bg-foreground text-background'
                  : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{rows.length} transcripts</CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No transcripts in this view. Transcripts appear here after the Oracle is
              brought into a Teams meeting and the ingestion worker runs.
            </p>
          ) : (
            <div className="space-y-4">
              {rows.map((row) => {
                const utterances = row.channel_id
                  ? utterancesByChannel.get(row.channel_id) ?? []
                  : [];
                const speakers = (row.speaker_names ?? []).filter(Boolean);
                return (
                  <div
                    key={row.transcript_id}
                    className="rounded-md border bg-card p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">
                            {row.channel_name ?? '(unnamed meeting)'}
                          </span>
                          <span
                            className={`rounded px-2 py-0.5 text-xs font-medium ${statusBadge(row.approval_status)}`}
                          >
                            {row.approval_status.replace(/_/g, ' ')}
                          </span>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Ingested {formatNYDateTime(row.created_at)} ·{' '}
                          {row.message_count} utterance
                          {row.message_count === 1 ? '' : 's'}
                          {row.approval_status === 'pending_approval' &&
                            ` · ${row.held_count} held`}
                        </div>
                        {speakers.length > 0 && (
                          <div className="flex flex-wrap gap-1 pt-1">
                            {speakers.map((name) => (
                              <span
                                key={`${row.transcript_id}-${name}`}
                                className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
                              >
                                {name}
                              </span>
                            ))}
                          </div>
                        )}
                        {row.reviewed_at && (
                          <div className="pt-1 text-xs text-muted-foreground">
                            {row.approval_status === 'approved' ? 'Approved' : 'Reviewed'} by{' '}
                            {row.reviewer_name ?? 'an admin'} on{' '}
                            {formatNYDateTime(row.reviewed_at)}
                            {row.review_note ? ` — “${row.review_note}”` : ''}
                          </div>
                        )}
                      </div>

                      {row.approval_status !== 'approved' && row.channel_id && (
                        <div className="flex flex-col items-stretch gap-2">
                          <form action={approveTranscript}>
                            <input type="hidden" name="channelId" value={row.channel_id} />
                            <button
                              type="submit"
                              className="w-full rounded bg-green-600 px-3 py-1 text-xs text-white hover:bg-green-700"
                            >
                              Approve &amp; ingest
                            </button>
                          </form>
                          {row.approval_status !== 'rejected' && (
                            <details className="rounded border bg-background p-2">
                              <summary className="cursor-pointer text-xs font-medium text-red-700">
                                Reject
                              </summary>
                              <form action={rejectTranscript} className="mt-2 space-y-2">
                                <input
                                  type="hidden"
                                  name="channelId"
                                  value={row.channel_id}
                                />
                                <textarea
                                  name="note"
                                  rows={2}
                                  placeholder="Optional reason"
                                  className="w-full rounded border bg-background px-2 py-1 text-xs text-foreground"
                                />
                                <button
                                  type="submit"
                                  className="w-full rounded bg-red-600 px-3 py-1 text-xs text-white hover:bg-red-700"
                                >
                                  Reject transcript
                                </button>
                              </form>
                            </details>
                          )}
                        </div>
                      )}
                      {row.approval_status === 'approved' && row.channel_id && (
                        <form action={rejectTranscript}>
                          <input type="hidden" name="channelId" value={row.channel_id} />
                          <button
                            type="submit"
                            className="rounded border border-red-300 px-3 py-1 text-xs text-red-700 hover:bg-red-50"
                            title="Mark utterances skipped. Claims already extracted are not removed."
                          >
                            Reject
                          </button>
                        </form>
                      )}
                    </div>

                    <details className="mt-3">
                      <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
                        Preview transcript ({utterances.length} utterance
                        {utterances.length === 1 ? '' : 's'})
                      </summary>
                      <div className="mt-2 max-h-96 space-y-2 overflow-y-auto rounded border bg-background p-3">
                        {utterances.length === 0 ? (
                          <p className="text-xs text-muted-foreground">
                            No utterances recorded for this transcript.
                          </p>
                        ) : (
                          utterances.map((u) => (
                            <div key={u.id} className="text-sm">
                              <span className="font-medium text-foreground">
                                {u.speaker}:
                              </span>{' '}
                              <span className="whitespace-pre-wrap text-muted-foreground">
                                {u.content}
                              </span>
                            </div>
                          ))
                        )}
                      </div>
                    </details>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
