'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { brainGet, pickText, type CommunityDetail } from './brain';
import { LoadState, Markdown, SourceChip, StanceBadge } from './bits';
import { CommunityGraph, type GraphRelation } from './community-graph';
import { EntityDrawer } from './entity-panel';
import { MarkWrongButton, relationItemId } from './mark-wrong';

export function CommunityView({
  communityId,
  isAdmin,
  lang = '',
}: {
  communityId: string;
  isAdmin: boolean;
  lang?: string;
}) {
  const [community, setCommunity] = useState<CommunityDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [relation, setRelation] = useState<GraphRelation | null>(null);
  const close = useCallback(() => setSelected(null), []);
  const closeRelation = useCallback(() => setRelation(null), []);

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
              {pickText(community.translations, lang, 'title', community.title)}
            </h1>
            <MarkWrongButton
              isAdmin={isAdmin}
              itemType="community"
              itemId={community.id}
            />
            <Markdown
              text={pickText(
                community.translations,
                lang,
                'summary',
                (community.report_md.split('\n## Findings')[0] ?? '').replace(/^# .*\n+/, ''),
              )}
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
          <section className="space-y-3">
            {relation && (
              <div
                data-testid="relation-detail"
                data-rel-type={relation.rel_type}
                className="space-y-2 rounded border bg-slate-50 p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold">
                      {relation.rel_type.replaceAll('_', ' ').toLowerCase()}
                    </p>
                    <p className="text-sm">
                      {(community.graph.nodes.find((node) => node.id === relation.source)?.name ??
                        relation.source) + ' → ' +
                        (community.graph.nodes.find((node) => node.id === relation.target)?.name ??
                          relation.target)}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {relation.weight} source{relation.weight === 1 ? '' : 's'}
                    </p>
                  </div>
                  <button type="button" className="text-xs underline" onClick={closeRelation}>
                    Close
                  </button>
                </div>
                <MarkWrongButton
                  isAdmin={isAdmin}
                  itemType="relation"
                  itemId={relationItemId(relation.source, relation.target, relation.rel_type)}
                />
              </div>
            )}
            <CommunityGraph
              graph={community.graph}
              onSelect={setSelected}
              onSelectRelation={setRelation}
            />
          </section>
        </div>
      )}
      <EntityDrawer entityId={selected} isAdmin={isAdmin} onClose={close} lang={lang} />
    </main>
  );
}
