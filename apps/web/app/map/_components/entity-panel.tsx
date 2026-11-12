'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { brainGet, pickText, sourceHref, type EntityDetail, type Quote } from './brain';
import { LoadState, SourceChip, StanceBadge } from './bits';
import { EntityAdmin } from './entity-admin';
import { FunctionAssign } from './function-assign';
import { MarkWrongButton, relationItemId } from './mark-wrong';

function QuoteLink({ quote }: { quote: Quote }) {
  return (
    <li className="space-y-0.5">
      <Link
        href={sourceHref(quote.source_id, quote.chunk_id)}
        data-testid="entity-quote"
        data-source-id={quote.source_id}
        data-chunk-id={quote.chunk_id}
        className="block rounded border-l-4 border-slate-300 bg-slate-50 px-2 py-1 text-sm italic hover:bg-slate-100"
      >
        “{quote.quote}”
      </Link>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {quote.stance && <StanceBadge stance={quote.stance} />}
        <span>{quote.source_title}</span>
      </div>
    </li>
  );
}

export function EntityPanel({
  entityId,
  isAdmin,
  lang = '',
}: {
  entityId: string;
  isAdmin: boolean;
  lang?: string;
}) {
  const [entity, setEntity] = useState<EntityDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    let cancelled = false;
    brainGet<EntityDetail>(`entities/${encodeURIComponent(entityId)}`)
      .then((body) => {
        if (!cancelled) setEntity(body);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'load failed');
      });
    return () => {
      cancelled = true;
    };
  }, [entityId]);

  useEffect(() => reload(), [reload]);

  if (!entity) return <LoadState error={error} loading={!error} />;

  return (
    <div className="space-y-4" data-testid="entity-panel" data-entity-id={entity.id}>
      <div>
        <h2 className="text-xl font-semibold" data-testid="entity-name">
          {entity.canonical_name}
        </h2>
        <p className="text-sm text-muted-foreground">
          {entity.type} · {entity.source_count} source{entity.source_count === 1 ? '' : 's'} ·{' '}
          {entity.mention_count} mention{entity.mention_count === 1 ? '' : 's'}
        </p>
        <div className="mt-1">
          <MarkWrongButton isAdmin={isAdmin} itemType="entity" itemId={entity.id} />
        </div>
      </div>
      {isAdmin && <EntityAdmin entity={entity} onChanged={reload} />}
      {entity.description && (
        <p className="text-sm">
          {pickText(entity.translations, lang, 'description', entity.description)}
        </p>
      )}
      <FunctionAssign
        kind="entities"
        itemId={entity.id}
        initial={entity.functions ?? []}
        isAdmin={isAdmin}
      />
      {(entity.contradictions ?? []).length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold" data-testid="entity-contradictions-title">
            Sources disagree
          </h3>
          <ul className="space-y-2">
            {(entity.contradictions ?? []).map((item) => (
              <li
                key={item.id}
                className="rounded border-l-4 border-amber-400 bg-amber-50 px-2 py-1 text-sm"
                data-testid="entity-contradiction"
              >
                <div className="font-medium" data-testid="entity-contradiction-kind">
                  {item.kind === 'policy_vs_practice'
                    ? 'Policy vs practice'
                    : item.kind === 'precedes_cycle'
                      ? 'Process order cycle'
                      : item.kind === 'changed_over_time'
                        ? 'Changed over time'
                        : 'Contradiction'}
                </div>
                <p data-testid="entity-contradiction-summary">{item.summary}</p>
                <div className="text-xs text-muted-foreground">
                  {item.source_a_title} vs {item.source_b_title}
                  {item.resolution ? ` · ${item.resolution}` : ''}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {entity.aliases.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold">Also called</h3>
          <p className="text-sm" data-testid="entity-aliases">
            {entity.aliases.join(', ')}
          </p>
        </div>
      )}
      <div>
        <h3 className="text-sm font-semibold">Sources</h3>
        <div className="mt-1 flex flex-wrap gap-1">
          {entity.sources.map((source) => (
            <SourceChip key={source.id} source={source} />
          ))}
        </div>
      </div>
      {Object.keys(entity.neighbours).length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold">Connections</h3>
          {Object.entries(entity.neighbours).map(([relType, group]) => (
            <section key={relType} className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {relType.replaceAll('_', ' ').toLowerCase()}
              </h4>
              {group.map((neighbour) => {
                const fromId = neighbour.direction === 'out' ? entity.id : neighbour.entity_id;
                const toId = neighbour.direction === 'out' ? neighbour.entity_id : entity.id;
                return (
                  <div key={`${neighbour.entity_id}-${neighbour.direction}`} className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/map/entity/${neighbour.entity_id}`}
                        className="text-sm font-medium underline"
                      >
                        {neighbour.direction === 'in' ? '← ' : '→ '}
                        {neighbour.name}
                      </Link>
                      <span className="text-xs text-muted-foreground">{neighbour.type}</span>
                      <MarkWrongButton
                        isAdmin={isAdmin}
                        itemType="relation"
                        itemId={relationItemId(fromId, toId, relType)}
                      />
                    </div>
                    <ul className="space-y-1">
                      {neighbour.quotes.map((quote, index) => (
                        <QuoteLink key={`${quote.chunk_id}-${index}`} quote={quote} />
                      ))}
                    </ul>
                  </div>
                );
              })}
            </section>
          ))}
        </div>
      )}
      {entity.mentions.length > 0 && (
        <div className="space-y-1">
          <h3 className="text-sm font-semibold">Where it is mentioned</h3>
          <ul className="space-y-1">
            {entity.mentions.map((quote, index) => (
              <QuoteLink key={`${quote.chunk_id}-m${index}`} quote={quote} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function EntityDrawer({
  entityId,
  isAdmin,
  onClose,
  lang = '',
}: {
  entityId: string | null;
  isAdmin: boolean;
  onClose: () => void;
  lang?: string;
}) {
  useEffect(() => {
    if (!entityId) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [entityId, onClose]);

  if (!entityId) return null;
  return (
    <aside
      role="dialog"
      aria-label="Entity details"
      data-testid="entity-drawer"
      className="fixed inset-y-0 right-0 z-40 w-full max-w-md overflow-y-auto border-l bg-background p-5 shadow-xl"
    >
      <div className="mb-3 flex items-center justify-between">
        <Link href={`/map/entity/${entityId}`} className="text-xs underline">
          Open full page
        </Link>
        <button type="button" onClick={onClose} className="text-sm underline">
          Close
        </button>
      </div>
      <EntityPanel key={entityId} entityId={entityId} isAdmin={isAdmin} lang={lang} />
    </aside>
  );
}
