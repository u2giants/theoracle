'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { brainGet, describeLocator, type SourceChunks } from './brain';
import { LoadState } from './bits';

export function SourceViewer({ sourceId, chunkId }: { sourceId: string; chunkId: string | null }) {
  const [data, setData] = useState<SourceChunks | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    brainGet<SourceChunks>(`sources/${encodeURIComponent(sourceId)}/chunks`)
      .then((body) => {
        if (!cancelled) setData(body);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'load failed');
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId]);

  useEffect(() => {
    if (!data || !chunkId) return;
    const element = document.getElementById(`chunk-${chunkId}`);
    element?.scrollIntoView({ block: 'center' });
  }, [data, chunkId]);

  if (!data) {
    return (
      <main className="mx-auto max-w-4xl p-6">
        <LoadState error={error} loading={!error} />
      </main>
    );
  }
  const { source, chunks } = data;
  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <Link href="/map" className="text-sm underline">
        ← Company Map
      </Link>
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold" data-testid="source-title">
          {source.title}
        </h1>
        <p className="text-sm text-muted-foreground" data-testid="source-meta">
          {source.kind}
          {source.original_filename ? ` · ${source.original_filename}` : ''}
          {source.department_hint ? ` · ${source.department_hint}` : ''}
          {source.effective_date
            ? ` · effective ${source.effective_date}`
            : ' · effective date unknown'}
          {source.created_at ? ` · added ${source.created_at.slice(0, 10)}` : ''}
          {` · ${chunks.length} passage${chunks.length === 1 ? '' : 's'}`}
        </p>
      </header>
      <ol className="space-y-3">
        {chunks.map((chunk) => {
          const active = chunk.id === chunkId;
          return (
            <li
              key={chunk.id}
              id={`chunk-${chunk.id}`}
              data-testid="source-chunk"
              data-chunk-id={chunk.id}
              data-highlighted={active ? 'true' : 'false'}
              aria-current={active ? 'true' : undefined}
              className={cn(
                'scroll-mt-24 rounded border p-3',
                active && 'border-amber-500 bg-amber-50 ring-2 ring-amber-400',
              )}
            >
              <div className="mb-1 text-xs text-muted-foreground">
                #{chunk.ordinal + 1}
                {describeLocator(chunk.locator) ? ` · ${describeLocator(chunk.locator)}` : ''}
              </div>
              <p className="whitespace-pre-wrap text-sm">{chunk.text}</p>
            </li>
          );
        })}
      </ol>
    </main>
  );
}
