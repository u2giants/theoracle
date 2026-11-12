'use client';

import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

// Admin-only pipeline health panel (repair plan B4). One endpoint,
// /api/brain/sources/health, backs every section: sources by read state,
// failed and retrying jobs with their error text, passages whose extraction
// failed (A2), the last successful graph build, and the New York day's
// recorded model usage. Error text is always shown — nothing here falls back
// silently.

type HealthJob = {
  id: string;
  kind: string;
  state: string;
  attempts: number;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  run_after: string | null;
};

type Health = {
  sources_by_state: Record<string, number>;
  jobs: { failed: HealthJob[]; retrying: HealthJob[] };
  failed_extractions: {
    chunk_id: string;
    source_id: string;
    source_title: string;
    ordinal: number;
    locator: Record<string, unknown> | null;
    stage: string;
    error: string | null;
  }[];
  last_build: {
    version: number;
    projected_at: string | null;
    node_count: number | null;
    edge_count: number | null;
    map_version: number | null;
  } | null;
  spend_today: {
    day: string;
    timezone: string;
    tokens: number;
    calls: number;
    usage: Record<string, number>;
  };
};

const STATE_STYLES: Record<string, string> = {
  queued: 'bg-amber-100 text-amber-900',
  reading: 'bg-sky-100 text-sky-900',
  extracting: 'bg-sky-100 text-sky-900',
  partial: 'bg-orange-100 text-orange-900',
  read: 'bg-emerald-100 text-emerald-900',
  failed: 'bg-red-100 text-red-900',
};

function formatNy(iso: string | null): string {
  if (!iso) return '—';
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(new Date(iso));
}

function JobTable({ label, jobs }: { label: string; jobs: HealthJob[] }) {
  return (
    <div>
      <h4 className="text-sm font-medium">
        {label} ({jobs.length})
      </h4>
      {jobs.length === 0 ? (
        <p className="text-sm text-muted-foreground">None.</p>
      ) : (
        <ul className="mt-1 space-y-2">
          {jobs.map((job) => (
            <li key={job.id} className="rounded-md border p-2 text-sm" data-testid="health-job">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{job.kind}</span>
                <span className="text-xs text-muted-foreground">
                  tried {job.attempts}x · added {formatNy(job.created_at)}
                </span>
                {job.state === 'queued' && job.run_after && (
                  <span className="text-xs text-muted-foreground">
                    retries after {formatNy(job.run_after)}
                  </span>
                )}
              </div>
              {job.error && (
                <p className="mt-1 text-xs text-red-700" data-testid="health-job-error">
                  {job.error}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function HealthPanel() {
  const [health, setHealth] = useState<Health | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const fetchHealth = useCallback(async (): Promise<{
    body: Health | null;
    error: string | null;
  }> => {
    try {
      const response = await fetch('/api/brain/sources/health', { cache: 'no-store' });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(body.detail ?? body.error ?? `load failed (${response.status})`);
      }
      return { body: body as Health, error: null };
    } catch (err) {
      return {
        body: null,
        error: err instanceof Error ? err.message : 'load failed',
      };
    }
  }, []);

  const refresh = useCallback(async () => {
    const result = await fetchHealth();
    setHealth(result.body);
    setLoadError(result.error);
    setLoaded(true);
  }, [fetchHealth]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const result = await fetchHealth();
      if (cancelled) return;
      setHealth(result.body);
      setLoadError(result.error);
      setLoaded(true);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [fetchHealth]);

  return (
    <Card data-testid="health-panel">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle>Pipeline health</CardTitle>
          <CardDescription>
            Sources, jobs, extraction failures, the last map build and today&apos;s
            model usage. Error text is shown as recorded.
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refresh()}>
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </CardHeader>
      <CardContent className="space-y-6">
        {loadError && <p className="text-sm text-red-700">{loadError}</p>}
        {!loadError && !loaded && (
          <p className="text-sm text-muted-foreground">Loading…</p>
        )}
        {health && (
          <>
            <div data-testid="health-sources-by-state">
              <h4 className="text-sm font-medium">Sources by read state</h4>
              <div className="mt-2 flex flex-wrap gap-2">
                {Object.entries(health.sources_by_state).map(([state, count]) => (
                  <span
                    key={state}
                    className={cn(
                      'rounded-full px-2 py-0.5 text-xs font-medium',
                      STATE_STYLES[state] ?? 'bg-gray-100 text-gray-900',
                    )}
                  >
                    {state}: {count}
                  </span>
                ))}
              </div>
            </div>

            <div data-testid="health-last-build">
              <h4 className="text-sm font-medium">Last successful build</h4>
              {health.last_build ? (
                <p className="mt-1 text-sm">
                  version {health.last_build.version} · projected{' '}
                  {formatNy(health.last_build.projected_at)} ·{' '}
                  {health.last_build.node_count ?? '—'} nodes /{' '}
                  {health.last_build.edge_count ?? '—'} edges
                  {health.last_build.map_version !== null &&
                    health.last_build.map_version !== health.last_build.version && (
                      <span className="text-orange-700">
                        {' '}
                        (map still shows version {health.last_build.map_version})
                      </span>
                    )}
                </p>
              ) : (
                <p className="mt-1 text-sm text-muted-foreground">
                  No build yet — the map has never been projected.
                </p>
              )}
            </div>

            <div data-testid="health-spend-today">
              <h4 className="text-sm font-medium">
                Model usage today ({health.spend_today.day}, New York day)
              </h4>
              <p className="mt-1 text-sm">
                {health.spend_today.tokens.toLocaleString()} tokens ·{' '}
                {health.spend_today.calls.toLocaleString()} calls
              </p>
              <p className="text-xs text-muted-foreground">
                Counters recorded per job; the system keeps no dollar-cost store.
              </p>
            </div>

            <div className="space-y-4" data-testid="health-jobs">
              <JobTable label="Failed jobs" jobs={health.jobs.failed} />
              <JobTable label="Retrying jobs" jobs={health.jobs.retrying} />
            </div>

            <div data-testid="health-failed-extractions">
              <h4 className="text-sm font-medium">
                Passages with failed extraction ({health.failed_extractions.length})
              </h4>
              {health.failed_extractions.length === 0 ? (
                <p className="text-sm text-muted-foreground">None.</p>
              ) : (
                <ul className="mt-1 space-y-2">
                  {health.failed_extractions.map((item) => (
                    <li
                      key={item.chunk_id}
                      className="rounded-md border p-2 text-sm"
                      data-testid="health-failed-extraction"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{item.source_title}</span>
                        <span className="text-xs text-muted-foreground">
                          passage {item.ordinal} · {item.stage}
                        </span>
                      </div>
                      {item.error && (
                        <p className="mt-1 text-xs text-red-700">{item.error}</p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
