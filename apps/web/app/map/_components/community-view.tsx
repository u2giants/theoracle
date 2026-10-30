'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { brainGet, type CommunityDetail } from './brain';
import { LoadState, Markdown, SourceChip, StanceBadge } from './bits';
import { CommunityGraph } from './community-graph';
import { EntityDrawer } from './entity-panel';

export function CommunityView({ communityId }: { communityId: string }) {
  const [community, setCommunity] = useState<CommunityDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const close = useCallback(() => setSelected(null), []);

  useEffect(() => {
    let cancelled = false;
    brainGet<CommunityDetail>(`communities/${encodeURIComponent(communityId)}`)
      .then((body) => {
        if (!cancelled) setCommunity(body);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'load failed');
      });
    return () => {
      cancelled = true;
    };
  }, [communityId]);

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-6">
      <Link href="/map" className="text-sm underline">
        ← Company Map
      </Link>
      {!community && <LoadState error={error} loading={!error} />}
      {community && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <section className="space-y-4">
            <h1 className="text-2xl font-semibold" data-testid="community-title">
              {community.title}
            </h1>
            <Markdown
              text={(community.report_md.split('\n## Findings')[0] ?? '').replace(/^# .*\n+/, '')}
            />
            <div>
              <h2 className="mb-2 font-semibold">Findings</h2>
              <ul className="space-y-3" data-testid="findings">
                {community.findings.map((finding, index) => (
                  <li key={`${index}-${finding.text}`} className="space-y-1" data-testid="finding">
                    <div className="flex flex-wrap items-center gap-2">
                      <StanceBadge stance={finding.stance} />
                      {finding.kind && (
                        <span className="text-xs text-muted-foreground">{finding.kind}</span>
                      )}
                    </div>
                    <p className="text-sm">{finding.text}</p>
                    <div className="flex flex-wrap gap-1">
                      {finding.sources.map((source) => (
                        <SourceChip key={source.id} source={source} />
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
            {community.children.length > 0 && (
              <div>
                <h2 className="mb-2 font-semibold">Smaller areas inside</h2>
                <ul className="list-disc pl-5 text-sm">
                  {community.children.map((child) => (
                    <li key={child.id}>
                      <Link href={`/map/community/${child.id}`} className="underline">
                        {child.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
          <section>
            <CommunityGraph graph={community.graph} onSelect={setSelected} />
          </section>
        </div>
      )}
      <EntityDrawer entityId={selected} onClose={close} />
    </main>
  );
}
