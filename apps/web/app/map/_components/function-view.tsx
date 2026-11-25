'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { brainGet, pickText, type CommunityDetail, type FunctionDetail } from './brain';
import { LoadState, Markdown, SourceChip, StanceBadge } from './bits';
import { CommunityGraph, type GraphRelation } from './community-graph';
import { EntityDrawer } from './entity-panel';
import { MarkWrongButton, relationItemId } from './mark-wrong';

// Repair C5: the function page. Its report (the C3 per-function level-1
// community, translated), its processes linking to their sources (E5's
// ordered flow pages are not landed), its sub-topics, its people, and the
// open gaps and disagreements that touch it.

export function FunctionView({
  functionRef,
  isAdmin,
  lang = '',
}: {
  functionRef: string;
  isAdmin: boolean;
  lang?: string;
}) {
  const [detail, setDetail] = useState<FunctionDetail | null>(null);
  const [community, setCommunity] = useState<CommunityDetail | null>(null);
  const [canCorrect, setCanCorrect] = useState(isAdmin);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [relation, setRelation] = useState<GraphRelation | null>(null);
  const close = useCallback(() => setSelected(null), []);
  const closeRelation = useCallback(() => setRelation(null), []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      brainGet<FunctionDetail>(`map/functions/${encodeURIComponent(functionRef)}`),
      brainGet<{ can_correct: boolean }>('corrections/access').catch(() => ({
        can_correct: isAdmin,
      })),
    ])
      .then(async ([body, accessBody]) => {
        if (cancelled) return;
        setDetail(body);
        setCanCorrect(Boolean(accessBody.can_correct || isAdmin));
        setError(null);
        // The report row id is the function id (C3); the existing community
        // endpoint serves the graph canvas and translations for it. The graph
        // is decoration — a failure to load it never fails the page.
        if (body.report) {
          try {
            const graphBody = await brainGet<CommunityDetail>(
              `communities/${encodeURIComponent(body.report.id)}`,
            );
            if (!cancelled) setCommunity(graphBody);
          } catch {
            /* no graph for this report */
          }
        } else if (!cancelled) {
          setCommunity(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'load failed');
      });
    return () => {
      cancelled = true;
    };
  }, [functionRef, isAdmin]);

  const report = detail?.report ?? null;

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-6">
      <Link href="/map" className="text-sm underline">
        ← Company Map
      </Link>
      {!detail && <LoadState error={error} loading={!error} />}
      {detail && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <section className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h1 className="text-2xl font-semibold" data-testid="function-name">
                {detail.function.name}
              </h1>
              {canCorrect && (
                <Link
                  href={`/map/corrections?function=${encodeURIComponent(detail.function.key)}&from=${encodeURIComponent(`/map/function/${detail.function.key}`)}`}
                  data-testid="function-corrections-link"
                  className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted"
                >
                  Submit a correction
                </Link>
              )}
            </div>
            {detail.function.description && (
              <p className="text-sm text-muted-foreground">{detail.function.description}</p>
            )}
            {report ? (
              <div className="space-y-4" data-testid="function-report">
                <h2 className="text-lg font-semibold" data-testid="community-title">
                  {pickText(community?.translations, lang, 'title', report.title)}
                </h2>
                <MarkWrongButton isAdmin={isAdmin} itemType="community" itemId={report.id} />
                <Markdown
                  text={pickText(
                    community?.translations,
                    lang,
                    'summary',
                    (report.report_md.split('\n## Findings')[0] ?? '').replace(/^# .*\n+/, ''),
                  )}
                />
                <div>
                  <h3 className="mb-2 font-semibold">Findings</h3>
                  <ul className="space-y-3" data-testid="findings">
                    {report.findings.map((finding, index) => (
                      <li
                        key={`${index}-${finding.text}`}
                        className="space-y-1"
                        data-testid="finding"
                      >
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
              </div>
            ) : (
              <p className="text-sm text-muted-foreground" data-testid="function-report">
                No report for this function yet. Rebuild the map from the Sources page.
              </p>
            )}

            {detail.processes.length > 0 && (
              <div>
                <h3 className="mb-2 font-semibold">Processes</h3>
                <ul className="space-y-2" data-testid="function-processes">
                  {detail.processes.map((process) => (
                    <li
                      key={process.id}
                      className="rounded border p-2"
                      data-testid="function-process"
                      data-process-id={process.id}
                    >
                      <Link
                        href={`/map/entity/${encodeURIComponent(process.id)}`}
                        className="text-sm font-medium underline"
                        data-testid="function-process-name"
                      >
                        {process.name}
                      </Link>
                      <span className="ml-2 text-xs text-muted-foreground">
                        {process.source_count} source{process.source_count === 1 ? '' : 's'}
                      </span>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {process.sources.map((source) => (
                          <SourceChip key={source.id} source={source} />
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
                <p className="mt-1 text-xs text-muted-foreground">
                  Ordered step-by-step flows arrive with the flow view.
                </p>
              </div>
            )}

            {detail.sub_topics.length > 0 && (
              <div>
                <h3 className="mb-2 font-semibold">Sub-topics</h3>
                <ul className="space-y-1 text-sm" data-testid="function-subtopics">
                  {detail.sub_topics.map((topic) => (
                    <li key={topic.id}>
                      <Link
                        href={`/map/community/${encodeURIComponent(topic.id)}`}
                        className="underline"
                        data-testid="function-subtopic"
                      >
                        {topic.title}
                      </Link>
                      <span className="ml-2 text-xs text-muted-foreground">
                        {topic.entity_count} thing{topic.entity_count === 1 ? '' : 's'}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {detail.people.length > 0 && (
              <div>
                <h3 className="mb-2 font-semibold">People</h3>
                <ul className="flex flex-wrap gap-1" data-testid="function-people">
                  {detail.people.map((person) => (
                    <li key={person.id}>
                      <Link
                        href={`/map/entity/${encodeURIComponent(person.id)}`}
                        data-testid="function-person"
                        data-entity-id={person.id}
                        className="inline-block rounded-full border px-2 py-0.5 text-xs hover:bg-muted"
                        title={`${person.type} · ${person.source_count} source(s)`}
                      >
                        {person.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {detail.gaps.length > 0 && (
              <div>
                <h3 className="mb-2 font-semibold">Open gaps</h3>
                <ul className="space-y-1 text-sm" data-testid="function-gaps">
                  {detail.gaps.map((gap) => (
                    <li key={gap.id} data-testid="function-gap" data-state={gap.state}>
                      {gap.question}
                      <span className="ml-2 text-xs text-muted-foreground">{gap.why}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {detail.contradictions.length > 0 && (
              <div>
                <h3 className="mb-2 font-semibold">Sources disagree</h3>
                <ul className="space-y-1 text-sm" data-testid="function-contradictions">
                  {detail.contradictions.map((row) => (
                    <li key={row.id} data-testid="function-contradiction">
                      {row.summary}
                      <span className="ml-2 text-xs text-muted-foreground">
                        {row.source_a_title} vs {row.source_b_title}
                      </span>
                    </li>
                  ))}
                </ul>
                <Link className="text-xs underline" href="/map/contradictions">
                  All disagreements
                </Link>
              </div>
            )}
          </section>
          <section className="space-y-3">
            {relation && community && (
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
                        relation.source) +
                        ' → ' +
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
            {community && (
              <CommunityGraph
                graph={community.graph}
                onSelect={setSelected}
                onSelectRelation={setRelation}
              />
            )}
          </section>
        </div>
      )}
      <EntityDrawer entityId={selected} isAdmin={isAdmin} onClose={close} lang={lang} />
    </main>
  );
}
