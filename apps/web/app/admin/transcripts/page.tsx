export const dynamic = 'force-dynamic';

import Link from 'next/link';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatNYDateTime } from '@/lib/time';
import { ShiftSelect } from '../claims/_components/shift-select';
import { ingestMeetings, dismissMeeting, runDiscoveryScan } from './_actions';

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

function statusBadge(status: string) {
  const map: Record<string, string> = {
    available: 'bg-blue-100 text-blue-800',
    ingested: 'bg-green-100 text-green-800',
    dismissed: 'bg-gray-100 text-gray-600',
  };
  return map[status] ?? 'bg-gray-100 text-gray-600';
}

export default async function AdminTranscriptsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const activeStatus = status ?? 'available';

  const db = getDirectDb();
  const whereClause =
    activeStatus !== 'all' ? sql`WHERE status = ${activeStatus}` : sql``;
  const result = await db.execute(sql`
    SELECT id, organizer_name, organizer_id, subject, meeting_time, status,
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
          <button
            type="submit"
            className="rounded border px-3 py-1 text-xs font-medium hover:bg-muted"
            title="Query Microsoft for meeting transcripts from the last 14 days and add them to the list (metadata only — does not ingest)"
          >
            Scan for recent meetings
          </button>
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
        <button
          type="submit"
          className="rounded bg-foreground px-3 py-1 text-xs text-background hover:opacity-90"
        >
          Ingest selected
        </button>
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
                    <th className="py-2 pr-4">Source</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const isAvailable = row.status === 'available';
                    const idx = isAvailable ? selectIdx++ : -1;
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
                          {isAvailable && (
                            <div className="flex gap-2">
                              <form action={ingestMeetings}>
                                <input type="hidden" name="meetingId" value={row.id} />
                                <button
                                  type="submit"
                                  className="rounded bg-green-600 px-2 py-1 text-xs text-white hover:bg-green-700"
                                >
                                  Ingest
                                </button>
                              </form>
                              <form action={dismissMeeting}>
                                <input type="hidden" name="meetingId" value={row.id} />
                                <button
                                  type="submit"
                                  className="rounded border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                                >
                                  Dismiss
                                </button>
                              </form>
                            </div>
                          )}
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
