'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

type MeetingRow = {
  id: string;
  title: string;
  call_kind: 'meeting' | 'call' | null;
  meeting_at: string | null;
  organizer_name: string | null;
  participants: { name: string }[];
  summary: string | null;
  summary_error: string | null;
  state: string;
  error: string | null;
};

function formatWhen(iso: string | null): string {
  if (!iso) return 'Date unknown';
  return new Date(iso).toLocaleString('en-US', {
    timeZone: 'America/New_York',
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

export function MeetingsClient() {
  const [rows, setRows] = useState<MeetingRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch('/api/brain/meetings');
        if (!response.ok) throw new Error(`Could not load meetings (${response.status})`);
        const body = (await response.json()) as MeetingRow[];
        if (!cancelled) setRows(body);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load meetings');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <p className="text-sm text-red-700">{error}</p>;
  if (rows === null) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (rows.length === 0)
    return <p className="text-sm text-muted-foreground">No transcripts collected yet.</p>;

  return (
    <div className="space-y-3" data-testid="meetings-list">
      <p className="text-sm text-muted-foreground">{rows.length} transcripts</p>
      {rows.map((row) => (
        <Card key={row.id} data-testid="meeting-row">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{row.title}</CardTitle>
            <p className="text-xs text-muted-foreground">
              {formatWhen(row.meeting_at)} ET
              {row.organizer_name ? ` · organized by ${row.organizer_name}` : ''}
              {row.participants.length > 0
                ? ` · ${row.participants.map((p) => p.name).join(', ')}`
                : ''}
            </p>
          </CardHeader>
          <CardContent className="text-sm">
            {row.state === 'failed' ? (
              <p className="text-red-700">Transcript could not be downloaded.</p>
            ) : row.summary ? (
              <p>{row.summary}</p>
            ) : (
              <p className="italic text-muted-foreground">
                {row.summary_error ? 'Summary failed; will retry.' : 'Summary pending.'}
              </p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
