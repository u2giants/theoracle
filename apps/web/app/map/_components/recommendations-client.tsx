'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { LoadState, SourceChip } from './bits';
import { brainGet, brainPost, type SourceRef } from './brain';

// Recommendations page (plan step 13): cards sorted by number of distinct
// sources; admins mark Accept / Reject / Running / Measured. Rejected cards
// disappear. Nothing else is asked of anyone.

type Explanation = { hypothesis: string; support: SourceRef[]; against: SourceRef[] };
type Option = { option: string; effort: string; risk: string; includes_no_change: boolean };
type Experiment = {
  change: string;
  metric: string;
  baseline_needed: boolean;
  review_after_days: number;
  owner_role: string;
};
type Recommendation = {
  id: string;
  community_id: string | null;
  community_title: string | null;
  problem: string;
  explanations: Explanation[];
  options: Option[];
  experiment: Experiment;
  status: string;
  source_count: number;
  sources: SourceRef[];
};

const ACTIONS: { status: string; label: string }[] = [
  { status: 'accepted', label: 'Accept' },
  { status: 'rejected', label: 'Reject' },
  { status: 'running', label: 'Running' },
  { status: 'measured', label: 'Measured' },
];

function Card({
  rec,
  isAdmin,
  onStatus,
}: {
  rec: Recommendation;
  isAdmin: boolean;
  onStatus: (id: string, status: string) => void;
}) {
  const exp = rec.experiment;
  return (
    <article data-testid="recommendation" className="space-y-3 rounded border p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <h2 className="font-semibold">{rec.problem}</h2>
        <span className="text-xs text-muted-foreground" data-testid="recommendation-status">
          {rec.source_count} sources · {rec.status}
        </span>
      </header>
      {rec.community_id && rec.community_title && (
        <p className="text-xs">
          Area:{' '}
          <Link className="underline" href={`/map/community/${rec.community_id}`}>
            {rec.community_title}
          </Link>
        </p>
      )}
      <section>
        <h3 className="text-sm font-medium">Possible explanations</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {rec.explanations.map((item, index) => (
            <li key={index}>
              {item.hypothesis}
              {item.support.length > 0 && (
                <span className="ml-1 inline-flex flex-wrap gap-1">
                  <span className="text-xs text-green-700">for:</span>
                  {item.support.map((source) => (
                    <SourceChip key={source.id} source={source} />
                  ))}
                </span>
              )}
              {item.against.length > 0 && (
                <span className="ml-1 inline-flex flex-wrap gap-1">
                  <span className="text-xs text-red-700">against:</span>
                  {item.against.map((source) => (
                    <SourceChip key={source.id} source={source} />
                  ))}
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h3 className="text-sm font-medium">Options</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm" data-testid="recommendation-options">
          {rec.options.map((item, index) => (
            <li key={index}>
              {item.option}{' '}
              <span className="text-xs text-muted-foreground">
                effort {item.effort}
                {item.risk ? ` · risk: ${item.risk}` : ''}
              </span>
            </li>
          ))}
        </ul>
      </section>
      <section className="text-sm">
        <h3 className="font-medium">Try first</h3>
        <p>{exp.change}</p>
        <p className="text-xs text-muted-foreground">
          Measure: {exp.metric}
          {exp.baseline_needed ? ' · no baseline in the data yet' : ''} · review after{' '}
          {exp.review_after_days} days · owner: {exp.owner_role || 'not named'}
        </p>
      </section>
      {isAdmin && (
        <div className="flex flex-wrap gap-2">
          {ACTIONS.map((action) => (
            <Button
              key={action.status}
              size="sm"
              variant={rec.status === action.status ? 'default' : 'outline'}
              onClick={() => onStatus(rec.id, action.status)}
            >
              {action.label}
            </Button>
          ))}
        </div>
      )}
    </article>
  );
}

export function RecommendationsClient({ isAdmin }: { isAdmin: boolean }) {
  const [recs, setRecs] = useState<Recommendation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);
  const load = useCallback(() => setReloads((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    brainGet<{ recommendations: Recommendation[] }>('recommendations')
      .then((body) => {
        if (cancelled) return;
        setRecs(body.recommendations);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : 'could not load recommendations');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloads]);

  async function setStatus(id: string, status: string) {
    setMessage(null);
    try {
      await brainPost(`recommendations/${id}/status`, { status });
      load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'could not update');
    }
  }

  return (
    <main className="mx-auto max-w-5xl space-y-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Recommendations</h1>
        <Link className="text-sm underline" href="/map">
          Back to the map
        </Link>
      </header>
      <LoadState error={error} loading={loading} />
      {message && <p className="text-sm text-red-700">{message}</p>}
      {recs && recs.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No recommendations yet. They appear after the map is rebuilt.
        </p>
      )}
      <div className="space-y-4" data-testid="recommendations">
        {recs?.map((rec) => (
          <Card key={rec.id} rec={rec} isAdmin={isAdmin} onStatus={setStatus} />
        ))}
      </div>
    </main>
  );
}
