export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatNYDateTime } from '@/lib/time';
import { ShiftSelect } from '../claims/_components/shift-select';
import { SubmitButton } from './_components/submit-button';
import {
  dismissMeeting,
  generateAvailableTranscriptSummaries,
  generateTranscriptSummary,
  ingestMeetings,
  runDiscoveryScan,
} from './_actions';

// Meeting picker.
//
// The Oracle does NOT auto-ingest meetings. This lists meetings whose transcripts
// are available (discovered as metadata by the webhook + the on-demand scan), and
// lets an admin choose which to ingest. Ingesting pulls the transcript and sends
// it to normal claim extraction. See ./_actions.ts and
// apps/workers/src/trigger/teams-transcript-{discovery-scan,ingestion}.ts.

type MeetingRow = {
  id: string;
  organizer_name: string | null;
  organizer_id: string | null;
  subject: string | null;
  participants: unknown;
  duration_seconds: number | null;
  message_count: number | null;
  transcript_char_count: number | null;
  ai_summary: string | null;
  ai_summary_model: string | null;
  ai_summary_generated_at: string | null;
  meeting_time: string | null;
  status: string;
  discovered_via: string | null;
  discovered_at: string;
};

const STATUS_TABS = [
  { label: 'Available', value: 'available' },
  { label: 'Ingested', value: 'ingested' },
  { label: 'Dismissed', value: 'dismissed' },
  { label: 'All', value: 'all' },
] as const;

// Calls known to be shorter than this are hidden from the picker — too short for
// a meaningful company-process discussion.
const MIN_MEETING_DURATION_SECONDS = 10 * 60;

function statusBadge(status: string) {
  const map: Record<string, string> = {
    available: 'bg-blue-100 text-blue-800',
    ingested: 'bg-green-100 text-green-800',
    dismissed: 'bg-gray-100 text-gray-600',
  };
  return map[status] ?? 'bg-gray-100 text-gray-600';
}

function participantNames(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((p) => {
      if (typeof p === 'string') return p.trim();
      if (p && typeof p === 'object') {
        const item = p as { name?: unknown; email?: unknown };
        const name = typeof item.name === 'string' ? item.name.trim() : '';
        const email = typeof item.email === 'string' ? item.email.trim() : '';
        return name || email;
      }
      return '';
    })
    .filter(Boolean);
}

function formatDuration(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return '—';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rem = minutes % 60;
  return rem ? `${hours}h ${rem}m` : `${hours}h`;
}

function formatSize(messages: number | null, chars: number | null): string {
  const parts = [];
  if (messages != null) parts.push(`${messages.toLocaleString()} utterances`);
  if (chars != null) parts.push(`${chars.toLocaleString()} chars`);
  return parts.length ? parts.join(' / ') : '—';
}

export default async function AdminTranscriptsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const activeStatus = status ?? 'available';

  const db = getDirectDb();
  // Hide calls known to be under the duration floor. Rows with unknown duration
  // (NULL) are kept so we never hide a real meeting we simply couldn't measure.
  const durationFloor = sql`(duration_seconds IS NULL OR duration_seconds >= ${MIN_MEETING_DURATION_SECONDS})`;
  const whereClause =
    activeStatus !== 'all'
      ? sql`WHERE status = ${activeStatus} AND ${durationFloor}`
      : sql`WHERE ${durationFloor}`;
  const result = await db.execute(sql`
    SELECT id, organizer_name, organizer_id, subject, meeting_time, status,
           participants, duration_seconds, message_count, transcript_char_count,
           ai_summary, ai_summary_model, ai_summary_generated_at,
           discovered_via, discovered_at
    FROM meeting_transcripts
    ${whereClause}
    ORDER BY meeting_time DESC NULLS LAST, discovered_at DESC
  `);
  const rows = [...result] as unknown as MeetingRow[];

  let selectIdx = 0;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Meeting transcripts</h1>
        <p className="text-sm text-muted-foreground">
          Meetings the Oracle could ingest. Nothing is ingested automatically — tick
          the meetings you want and click “Ingest selected”. Ingesting pulls the
          transcript and sends it to claim extraction. New meetings appear here
          automatically; use “Scan for recent meetings” to pull in older ones.
        </p>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
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
        <form action={runDiscoveryScan}>
          <input type="hidden" name="sinceDays" value="14" />
          <SubmitButton
            className="rounded border px-3 py-1 text-xs font-medium hover:bg-muted"
            title="Query Microsoft for meeting transcripts from the last 14 days and add them to the list (metadata only — does not ingest)"
            pendingLabel="Scanning…"
          >
            Scan for recent meetings
          </SubmitButton>
        </form>
        <form action={generateAvailableTranscriptSummaries}>
          <SubmitButton
            className="rounded border px-3 py-1 text-xs font-medium hover:bg-muted"
            title="Generate cheap AI summaries for available meetings only; does not ingest or extract claims"
            pendingLabel="Summarizing…"
          >
            Summarize available
          </SubmitButton>
        </form>
      </div>

      {/* Bulk ingest — tick available meetings, then submit. Lives outside the
          table so per-row dismiss forms aren't nested; checkboxes associate via
          form="ingest-meetings". */}
      <form
        id="ingest-meetings"
        action={ingestMeetings}
        className="flex flex-wrap items-center gap-3 rounded border border-dashed p-3 text-sm"
      >
        <SubmitButton
          className="rounded bg-foreground px-3 py-1 text-xs text-background hover:opacity-90"
          pendingLabel="Ingesting…"
        >
          Ingest selected
        </SubmitButton>
        <span className="text-xs text-muted-foreground">
          Tick available meetings (shift-click for a range), then submit to pull their
          transcripts in for extraction.
        </span>
      </form>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{rows.length} meetings</CardTitle>
        </CardHeader>
        <CardContent>
          {rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No meetings in this view. New meetings appear automatically as their
              transcripts become available; “Scan for recent meetings” pulls in older
              ones.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <ShiftSelect />
              <table className="w-full text-sm">
                <thead className="border-b text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4">☑</th>
                    <th className="py-2 pr-4">Organizer</th>
                    <th className="py-2 pr-4">Meeting time</th>
                    <th className="py-2 pr-4">Subject</th>
                    <th className="py-2 pr-4">Participants</th>
                    <th className="py-2 pr-4">Length</th>
                    <th className="py-2 pr-4">Size</th>
                    <th className="py-2 pr-4">AI summary</th>
                    <th className="py-2 pr-4">Source</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const isAvailable = row.status === 'available';
                    const idx = isAvailable ? selectIdx++ : -1;
                    const names = participantNames(row.participants);
                    return (
                      <tr key={row.id} className="border-b last:border-0">
                        <td className="py-3 pr-4 align-top">
                          {isAvailable ? (
                            <input
                              type="checkbox"
                              name="meetingId"
                              value={row.id}
                              form="ingest-meetings"
                              data-claim-select
                              data-select-form="ingest-meetings"
                              data-select-index={idx}
                              aria-label="Select this meeting to ingest"
                            />
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="py-3 pr-4 whitespace-nowrap">
                          {row.organizer_name ?? (row.organizer_id ? 'Unknown' : '—')}
                        </td>
                        <td className="py-3 pr-4 whitespace-nowrap text-xs text-muted-foreground">
                          {row.meeting_time ? formatNYDateTime(row.meeting_time) : '—'}
                        </td>
                        <td className="max-w-[24rem] py-3 pr-4">
                          {row.subject ?? <span className="text-muted-foreground">—</span>}
                        </td>
                        <td className="max-w-[18rem] py-3 pr-4 text-xs">
                          {names.length ? (
                            <span title={names.join(', ')}>
                              {names.slice(0, 4).join(', ')}
                              {names.length > 4 ? ` +${names.length - 4}` : ''}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="py-3 pr-4 whitespace-nowrap text-xs text-muted-foreground">
                          {formatDuration(row.duration_seconds)}
                        </td>
                        <td className="py-3 pr-4 whitespace-nowrap text-xs text-muted-foreground">
                          {formatSize(row.message_count, row.transcript_char_count)}
                        </td>
                        <td className="min-w-[22rem] max-w-[32rem] py-3 pr-4 text-xs leading-5">
                          {row.ai_summary ? (
                            <div className="space-y-1">
                              <p className="whitespace-pre-wrap">{row.ai_summary}</p>
                              <p className="text-[11px] text-muted-foreground">
                                {row.ai_summary_model ?? 'model unknown'}
                                {row.ai_summary_generated_at
                                  ? ` · ${formatNYDateTime(row.ai_summary_generated_at)}`
                                  : ''}
                              </p>
                            </div>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="py-3 pr-4 text-xs text-muted-foreground">
                          {row.discovered_via ?? '—'}
                        </td>
                        <td className="py-3 pr-4">
                          <span
                            className={`rounded px-2 py-0.5 text-xs font-medium ${statusBadge(row.status)}`}
                          >
                            {row.status}
                          </span>
                        </td>
                        <td className="py-3">
                          <div className="flex flex-wrap gap-2">
                            <form action={generateTranscriptSummary}>
                              <input type="hidden" name="meetingId" value={row.id} />
                              <SubmitButton
                                className="rounded border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                                pendingLabel={row.ai_summary ? 'Refreshing…' : 'Summarizing…'}
                              >
                                {row.ai_summary ? 'Refresh summary' : 'Summarize'}
                              </SubmitButton>
                            </form>
                            {isAvailable && (
                              <>
                              <form action={ingestMeetings}>
                                <input type="hidden" name="meetingId" value={row.id} />
                                <SubmitButton
                                  className="rounded bg-green-600 px-2 py-1 text-xs text-white hover:bg-green-700"
                                  pendingLabel="Ingesting…"
                                >
                                  Ingest
                                </SubmitButton>
                              </form>
                              <form action={dismissMeeting}>
                                <input type="hidden" name="meetingId" value={row.id} />
                                <SubmitButton
                                  className="rounded border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                                  pendingLabel="Dismissing…"
                                >
                                  Dismiss
                                </SubmitButton>
                              </form>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
