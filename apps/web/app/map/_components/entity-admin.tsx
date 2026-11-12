'use client';

// Admin entity actions (repair plan G2): merge into another entity, split
// (choose which mentions go where), rename, change type, add/remove alias and
// "these two are never the same". Every action posts to the brain's entity
// admin endpoints, which write a content-keyed correction and trigger a
// re-projection; non-admins never see this panel.

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { brainGet, brainPost, type EntityDetail } from './brain';

// Mirrors the locked entity-type ontology (B/extract/flat.py).
const ENTITY_TYPES = [
  'Person',
  'Role',
  'Department',
  'Process',
  'Step',
  'System',
  'Artifact',
  'Rule',
  'Exception',
  'Issue',
  'Decision',
  'Metric',
  'Customer',
  'Vendor',
  'Licensor',
  'Product',
];

type PickResult = { id: string; type: string; name: string };
type SplitResult = {
  moved: number;
  destination: { name: string };
  warning: string | null;
};

function EntityPicker({
  testId,
  excludeId,
  onPick,
}: {
  testId: string;
  excludeId: string;
  onPick: (entity: PickResult) => void;
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PickResult[]>([]);
  const trimmed = query.trim();

  useEffect(() => {
    const text = trimmed;
    if (text.length < 2) return;
    let cancelled = false;
    brainGet<{ entities: PickResult[] }>(`search?q=${encodeURIComponent(text)}`)
      .then((body) => {
        if (!cancelled) {
          setResults(body.entities.filter((item) => item.id !== excludeId));
        }
      })
      .catch(() => {
        if (!cancelled) setResults([]);
      });
    return () => {
      cancelled = true;
    };
  }, [trimmed, excludeId]);

  const visible = trimmed.length < 2 ? [] : results;

  return (
    <div data-testid={testId} className="space-y-1">
      <Input
        data-testid="entity-picker-input"
        className="h-7 w-56 text-xs"
        placeholder="Search entity by name"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <ul className="max-h-40 overflow-y-auto">
        {visible.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              data-testid="entity-picker-option"
              data-entity-id={item.id}
              className="block w-full rounded px-2 py-1 text-left text-sm hover:bg-slate-100"
              onClick={() => onPick(item)}
            >
              {item.name}{' '}
              <span className="text-xs text-muted-foreground">{item.type}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function EntityAdmin({
  entity,
  onChanged,
}: {
  entity: EntityDetail;
  onChanged: () => void;
}) {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mergedInto, setMergedInto] = useState<PickResult | null>(null);
  const [rename, setRename] = useState(entity.canonical_name);
  const [newType, setNewType] = useState(entity.type);
  const [alias, setAlias] = useState('');
  const [aliases, setAliases] = useState(entity.aliases);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergePick, setMergePick] = useState<PickResult | null>(null);
  const [neverOpen, setNeverOpen] = useState(false);
  const [neverPick, setNeverPick] = useState<PickResult | null>(null);
  const [splitPicks, setSplitPicks] = useState<Set<string>>(new Set());
  const [splitDest, setSplitDest] = useState<'new' | 'existing'>('new');
  const [splitName, setSplitName] = useState('');
  const [splitType, setSplitType] = useState('Person');
  const [splitExisting, setSplitExisting] = useState<PickResult | null>(null);

  async function act<T>(path: string, body: unknown, done: (data: T) => void) {
    setBusy(true);
    setError(null);
    try {
      done(await brainPost<T>(path, body));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'save failed');
      setMessage(null);
    } finally {
      setBusy(false);
    }
  }

  if (mergedInto) {
    return (
      <section
        data-testid="entity-admin"
        className="rounded border border-emerald-200 bg-emerald-50 p-3"
      >
        <p data-testid="entity-admin-message" className="text-sm">
          Merged into{' '}
          <a href={`/map/entity/${mergedInto.id}`} className="underline">
            {mergedInto.name}
          </a>
          . This entity is gone.
        </p>
      </section>
    );
  }

  return (
    <section data-testid="entity-admin" className="space-y-3 rounded border p-3">
      <h3 className="text-sm font-semibold">Admin</h3>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          data-testid="entity-admin-rename-input"
          className="h-7 w-48 text-xs"
          value={rename}
          onChange={(event) => setRename(event.target.value)}
        />
        <Button
          data-testid="entity-admin-rename-save"
          size="sm"
          variant="outline"
          disabled={busy || !rename.trim()}
          onClick={() =>
            void act(`entities/${encodeURIComponent(entity.id)}/rename`, {
              name: rename.trim(),
            }, () => {
              setMessage('Renamed.');
              onChanged();
            })
          }
        >
          Rename
        </Button>
        <select
          data-testid="entity-admin-type-select"
          aria-label="Entity type"
          className="h-7 rounded border bg-background px-2 text-xs"
          value={newType}
          onChange={(event) => setNewType(event.target.value)}
        >
          {ENTITY_TYPES.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <Button
          data-testid="entity-admin-type-save"
          size="sm"
          variant="outline"
          disabled={busy || newType === entity.type}
          onClick={() =>
            void act(`entities/${encodeURIComponent(entity.id)}/type`, {
              entity_type: newType,
            }, () => {
              setMessage('Type changed.');
              onChanged();
            })
          }
        >
          Change type
        </Button>
      </div>
      <div className="space-y-1">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Aliases
        </h4>
        <ul className="flex flex-wrap items-center gap-2">
          {aliases.map((item) => (
            <li
              key={item}
              className="flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 text-xs"
              data-testid="entity-admin-alias"
              data-alias={item}
            >
              {item}
              <button
                type="button"
                data-testid="entity-admin-alias-remove"
                data-alias={item}
                className="text-red-700 underline"
                disabled={busy}
                onClick={() =>
                  void act<{ aliases: string[] }>(
                    `entities/${encodeURIComponent(entity.id)}/alias`,
                    { alias: item, mode: 'remove' },
                    (data) => {
                      setAliases(data.aliases);
                      setMessage('Alias removed.');
                      onChanged();
                    },
                  )
                }
              >
                remove
              </button>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            data-testid="entity-admin-alias-input"
            className="h-7 w-40 text-xs"
            placeholder="Add an alias"
            value={alias}
            onChange={(event) => setAlias(event.target.value)}
          />
          <Button
            data-testid="entity-admin-alias-add"
            size="sm"
            variant="outline"
            disabled={busy || !alias.trim()}
            onClick={() =>
              void act<{ aliases: string[] }>(
                `entities/${encodeURIComponent(entity.id)}/alias`,
                { alias: alias.trim(), mode: 'add' },
                (data) => {
                  setAliases(data.aliases);
                  setAlias('');
                  setMessage('Alias added.');
                  onChanged();
                },
              )
            }
          >
            Add alias
          </Button>
        </div>
      </div>
      <div className="space-y-1">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Merge into another entity
        </h4>
        {mergePick ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm">
              Merge {entity.canonical_name} into <strong>{mergePick.name}</strong>?
            </span>
            <Button
              data-testid="entity-admin-merge-confirm"
              size="sm"
              disabled={busy}
              onClick={() =>
                void act(`entities/${encodeURIComponent(entity.id)}/merge`, {
                  into: mergePick.id,
                }, () => setMergedInto(mergePick))
              }
            >
              Confirm merge
            </Button>
            <Button
              data-testid="entity-admin-merge-cancel"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => setMergePick(null)}
            >
              Cancel
            </Button>
          </div>
        ) : mergeOpen ? (
          <div className="space-y-1">
            <EntityPicker
              testId="entity-admin-merge-picker"
              excludeId={entity.id}
              onPick={(item) => setMergePick(item)}
            />
            <Button
              data-testid="entity-admin-merge-close"
              size="sm"
              variant="ghost"
              onClick={() => setMergeOpen(false)}
            >
              Close
            </Button>
          </div>
        ) : (
          <Button
            data-testid="entity-admin-merge-open"
            size="sm"
            variant="outline"
            onClick={() => setMergeOpen(true)}
          >
            Merge into another…
          </Button>
        )}
      </div>
      <div className="space-y-1">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          These two are never the same
        </h4>
        {neverPick ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm">
              {entity.canonical_name} and <strong>{neverPick.name}</strong> are never the
              same?
            </span>
            <Button
              data-testid="entity-admin-never-confirm"
              size="sm"
              disabled={busy}
              onClick={() =>
                void act(`entities/${encodeURIComponent(entity.id)}/never-merge`, {
                  other: neverPick.id,
                }, () => {
                  setMessage(`Never merging with ${neverPick.name}.`);
                  setNeverPick(null);
                  setNeverOpen(false);
                })
              }
            >
              Confirm
            </Button>
            <Button
              data-testid="entity-admin-never-cancel"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => setNeverPick(null)}
            >
              Cancel
            </Button>
          </div>
        ) : neverOpen ? (
          <div className="space-y-1">
            <EntityPicker
              testId="entity-admin-never-picker"
              excludeId={entity.id}
              onPick={(item) => setNeverPick(item)}
            />
            <Button
              data-testid="entity-admin-never-close"
              size="sm"
              variant="ghost"
              onClick={() => setNeverOpen(false)}
            >
              Close
            </Button>
          </div>
        ) : (
          <Button
            data-testid="entity-admin-never-open"
            size="sm"
            variant="outline"
            onClick={() => setNeverOpen(true)}
          >
            Never merge with another…
          </Button>
        )}
      </div>
      <div className="space-y-1">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Split — choose which mentions go where
        </h4>
        <ul className="space-y-1">
          {entity.mentions.map((quote, index) => {
            const mentionId = quote.mention_id ?? `${quote.chunk_id}-m${index}`;
            const checked = splitPicks.has(mentionId);
            return (
              <li key={mentionId} className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  data-testid="entity-admin-mention-check"
                  data-mention-id={mentionId}
                  checked={checked}
                  onChange={() =>
                    setSplitPicks((previous) => {
                      const next = new Set(previous);
                      if (next.has(mentionId)) next.delete(mentionId);
                      else next.add(mentionId);
                      return next;
                    })
                  }
                />
                <span className="truncate">“{quote.quote}”</span>
              </li>
            );
          })}
        </ul>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-1">
            <input
              type="radio"
              data-testid="entity-admin-split-dest-new"
              checked={splitDest === 'new'}
              onChange={() => setSplitDest('new')}
            />
            New entity
          </label>
          <Input
            data-testid="entity-admin-split-new-name"
            className="h-7 w-36 text-xs"
            placeholder="New name"
            value={splitName}
            onChange={(event) => setSplitName(event.target.value)}
          />
          <select
            data-testid="entity-admin-split-new-type"
            aria-label="New entity type"
            className="h-7 rounded border bg-background px-2 text-xs"
            value={splitType}
            onChange={(event) => setSplitType(event.target.value)}
          >
            {ENTITY_TYPES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1">
            <input
              type="radio"
              data-testid="entity-admin-split-dest-existing"
              checked={splitDest === 'existing'}
              onChange={() => setSplitDest('existing')}
            />
            Existing entity
          </label>
          {splitDest === 'existing' &&
            (splitExisting ? (
              <span data-testid="entity-admin-split-existing">
                → {splitExisting.name}
              </span>
            ) : (
              <EntityPicker
                testId="entity-admin-split-picker"
                excludeId={entity.id}
                onPick={(item) => setSplitExisting(item)}
              />
            ))}
        </div>
        <Button
          data-testid="entity-admin-split-save"
          size="sm"
          variant="outline"
          disabled={
            busy ||
            splitPicks.size === 0 ||
            (splitDest === 'new' ? !splitName.trim() : !splitExisting)
          }
          onClick={() =>
            void act<SplitResult>(
              `entities/${encodeURIComponent(entity.id)}/split`,
              {
                mention_ids: [...splitPicks],
                into:
                  splitDest === 'new'
                    ? { new_name: splitName.trim(), new_type: splitType }
                    : { entity_id: splitExisting?.id },
              },
              (data) => {
                setMessage(
                  `Moved ${data.moved} mention${data.moved === 1 ? '' : 's'} to ${data.destination.name}.`,
                );
                if (data.warning) setError(data.warning);
                setSplitPicks(new Set());
                onChanged();
              },
            )
          }
        >
          Split selected mentions
        </Button>
      </div>
      {error && (
        <p data-testid="entity-admin-error" className="text-xs text-red-700">
          {error}
        </p>
      )}
      {message && (
        <p data-testid="entity-admin-message" className="text-xs text-emerald-700">
          {message}
        </p>
      )}
    </section>
  );
}
