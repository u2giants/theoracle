'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { brainGet, sourceHref, type EntityDetail, type Quote, type ReviewFlag } from './brain';
import { LoadState, SourceChip, StanceBadge } from './bits';
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

export function EntityPanel({ entityId, isAdmin }: { entityId: string; isAdmin: boolean }) {
  const [entity, setEntity] = useState<EntityDetail | null>(null);
  const [relationFlags, setRelationFlags] = useState<{
    entityId: string;
    flags: ReviewFlag[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
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

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    brainGet<{ flags: ReviewFlag[] }>(`flags?entity_id=${encodeURIComponent(entityId)}`)
      .then((body) => {
        if (!cancelled) setRelationFlags({ entityId, flags: body.flags });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'load failed');
          setRelationFlags({ entityId, flags: [] });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [entityId, isAdmin]);

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
      {error && <p role="alert">{error}</p>}
      {entity.description && <p className="text-sm">{entity.description}</p>}
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
                      {(!isAdmin || relationFlags?.entityId === entityId) && (
                        <MarkWrongButton
                        isAdmin={isAdmin}
                        itemType="relation"
                        itemId={relationItemId(fromId, toId, relType)}
                        initialFlag={relationFlags?.flags.find((flag) =>
                          flag.item_id === relationItemId(fromId, toId, relType)) ?? null}
                        />
                      )}
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
}: {
  entityId: string | null;
  isAdmin: boolean;
  onClose: () => void;
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
      <EntityPanel key={entityId} entityId={entityId} isAdmin={isAdmin} />
    </aside>
  );
}
