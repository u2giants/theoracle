'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { LoadState } from './bits';
import { brainGet, type ContradictionRow } from './brain';

// D3: the contradictions page. Open conflicts first ("sources disagree"),
// then the recorded timeline changes that are explicitly not conflicts.

const KIND_LABELS: Record<string, string> = {
  true_contradiction: 'Contradiction',
  policy_vs_practice: 'Policy vs practice',
  precedes_cycle: 'Process order cycle',
  changed_over_time: 'Changed over time (not a conflict)',
};

function Statement({ row, side }: { row: ContradictionRow; side: 'relation_a' | 'relation_b' }) {
  const rel = row[side];
  return (
    <div className="rounded border-l-4 border-slate-300 bg-slate-50 px-2 py-1 text-sm">
      <p className="italic">“{rel.quote}”</p>
      <p className="mt-0.5">{rel.description}</p>
      <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>{rel.rel_type.replaceAll('_', ' ')}</span>
        <span>{rel.stance}</span>
        <Link href={`/map/source/${rel.source_id}`} className="underline">
          {rel.source_title}
        </Link>
        {rel.effective_date && <span>{rel.effective_date}</span>}
      </div>
    </div>
  );
}

export function ContradictionsClient() {
  const [rows, setRows] = useState<ContradictionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    brainGet<{ contradictions: ContradictionRow[] }>('contradictions')
      .then((body) => {
        if (!cancelled) setRows(body.contradictions);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'load failed');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!rows) return <LoadState error={error} loading={!error} />;

  const conflicts = rows.filter((row) => row.kind !== 'changed_over_time');
  const timeline = rows.filter((row) => row.kind === 'changed_over_time');

  return (
    <div className="space-y-6" data-testid="contradictions-page">
      <div>
        <h1 className="text-xl font-semibold" data-testid="contradictions-title">
          Contradictions across sources
        </h1>
        <p className="text-sm text-muted-foreground">
          Statements from different sources that disagree, and records of how the same claim
          changed over time.
        </p>
      </div>
      <section className="space-y-3">
        <h2 className="text-sm font-semibold" data-testid="contradictions-conflicts-title">
          Sources disagree ({conflicts.length})
        </h2>
        {conflicts.length === 0 && (
          <p className="text-sm text-muted-foreground">No open conflicts.</p>
        )}
        <ul className="space-y-3">
          {conflicts.map((row) => (
            <li
              key={row.id}
              className="rounded border-l-4 border-amber-400 bg-amber-50 p-3"
              data-testid="contradiction-row"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium" data-testid="contradiction-kind">
                  {KIND_LABELS[row.kind] ?? row.kind}
                </span>
                <span className="text-xs text-muted-foreground">{row.status}</span>
              </div>
              <p className="mt-1 text-sm" data-testid="contradiction-summary">
                {row.summary}
              </p>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                <Statement row={row} side="relation_a" />
                <Statement row={row} side="relation_b" />
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {row.entities.map((entity) => (
                  <Link
                    key={entity.id}
                    href={`/map/entity/${entity.id}`}
                    className="text-xs underline"
                  >
                    {entity.name}
                  </Link>
                ))}
              </div>
            </li>
          ))}
        </ul>
      </section>
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Recorded timeline changes ({timeline.length})</h2>
        {timeline.length === 0 && (
          <p className="text-sm text-muted-foreground">None recorded.</p>
        )}
        <ul className="space-y-3">
          {timeline.map((row) => (
            <li
              key={row.id}
              className="rounded border-l-4 border-slate-300 bg-slate-50 p-3"
              data-testid="contradiction-row"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">
                  {KIND_LABELS[row.kind] ?? row.kind}
                </span>
                <span className="text-xs text-muted-foreground">{row.status}</span>
              </div>
              <p className="mt-1 text-sm">{row.summary}</p>
              {row.resolution && (
                <p className="mt-1 text-xs text-muted-foreground">{row.resolution}</p>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
